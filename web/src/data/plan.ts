// Il «piano» dei passi 2–4: quali misure sono attive in questo momento e quanto fanno risparmiare,
// in totale, per reparto e per risorsa. Una sola fonte, così scena, schede e totali dicono sempre la stessa cosa.
import type { Ctx } from './twin'
import type { Extra } from './extra'
import type { MetricKey, Metrics } from './types'
import { deptUnits, savedByRaw, unitDiv, unitSaved } from './usage'

const ZERO: Metrics = { cost_chf: 0, kwh: 0, co2_kg: 0 }
const KEYS: MetricKey[] = ['cost_chf', 'kwh', 'co2_kg']

/** Strategia proposta per prima (e scelta all'inizio): «Best value», se il backend la offre. */
export const preferredGoal = (x: Extra) => (x.packages.best_value ? 'best_value' : x.defaultGoal)
/** Strategie nell'ordine del menu: la proposta in cima, poi le altre come le dà il backend. */
export const goalOrder = (x: Extra) => [preferredGoal(x), ...x.goals.filter((g) => g !== preferredGoal(x))]
export const goalOf = (x: Extra, sel: string | null) => (sel && x.packages[sel] ? sel : preferredGoal(x))

/** Misure del pacchetto senza quelle tolte a mano (e mai quelle «non possibili»). */
export function planIds(x: Extra, goal: string, dropped: string[]): string[] {
  return (x.packages[goal]?.measure_ids ?? []).filter((id) => !dropped.includes(id) && x.measures.find((m) => m.id === id)?.status !== 'blocked')
}

/** Misure attive nella scena per passo: baseline con l'interruttore = pacchetto consigliato intero; passi 3–4 = la scelta del passo 3. */
export function activeIds(
  x: Extra,
  s: { step: string; showMeasures: boolean; withPackage: boolean; goal: string | null; dropped: string[]; focus: string | null; compareBefore: boolean },
  /** Passo 4: mese della simulazione (ISO); una misura conta solo da quando parte (start_date). null = anno intero. */
  monthDate: string | null = null,
): string[] {
  if (s.step === 'baseline') return s.showMeasures ? planIds(x, preferredGoal(x), []) : []
  if (s.step === 'packages') {
    const ids = planIds(x, goalOf(x, s.goal), s.dropped)
    return s.focus && s.compareBefore ? ids.filter((id) => id !== s.focus) : ids
  }
  if (s.step === 'forecast') {
    if (!s.withPackage) return []
    const ids = planIds(x, goalOf(x, s.goal), s.dropped)
    return monthDate ? ids.filter((id) => (x.measures.find((m) => m.id === id)?.start_date || '0000') <= monthDate) : ids
  }
  return []
}

export function totalSaved(saved: Map<string, Metrics>): Metrics {
  const t = { ...ZERO }
  for (const m of saved.values()) for (const k of KEYS) t[k] += m[k]
  return t
}

/** Quota di un reparto su una risorsa: tutta se è sua, altrimenti la quota della ripartizione. */
function shareOf(ctx: Ctx, unit: string, room: string): number {
  const e = ctx.entities.get(unit)?.entity
  if (!e) return 0
  if (e.allocation) return e.allocation.find((a) => a.department === room)?.share ?? 0
  return e.department === room ? 1 : 0
}

/** Risparmio di un reparto: i suoi computer e la sua quota delle risorse cloud che usa. */
export function deptSaved(ctx: Ctx, saved: Map<string, Metrics>, room: string): Metrics {
  const t = { ...ZERO }
  for (const u of deptUnits(ctx, room)) {
    const f = u.startsWith('pcs:') ? unitDiv(ctx, u) : shareOf(ctx, u, room)
    if (!f) continue
    for (const k of KEYS) t[k] += unitSaved(ctx, saved, u, k) * f
  }
  return t
}

export { savedByRaw }

export interface ForecastMonth {
  month: string
  without: Metrics
  with: Metrics
  /** kg CO₂ per sede (CH, DE, IE, EU), senza e con il piano. */
  loc: Record<string, { without: number; with: number }>
  /** Per risorsa del backend (senza «res:»), senza e con il piano. */
  res: Record<string, { without: Metrics; with: Metrics }>
}

/**
 * Previsione dei prossimi 12 mesi con il piano scelto al passo 3: si parte dalla previsione per risorsa del pacchetto;
 * le risorse toccate da una misura tolta a mano tornano ai valori «senza» (approssimazione: una risorsa toccata
 * anche da un'altra misura del pacchetto perde tutto il suo risparmio).
 */
export function forecastPlan(ctx: Ctx, x: Extra, goal: string, dropped: string[]): ForecastMonth[] {
  const fc = x.forecast
  if (!fc) return []
  const pm = fc.packages[goal] ?? null
  const off = new Set<string>()
  for (const raw of savedByRaw(ctx, x, dropped.filter((id) => x.packages[goal]?.measure_ids.includes(id))).keys()) {
    const p = raw.startsWith('res:') ? raw : (x.raw.get(raw)?.parent ?? '')
    if (p.startsWith('res:')) off.add(p.slice(4))
  }
  // Da quando conta il pacchetto su ogni risorsa: la data di partenza più vicina fra le sue misure (come i colori della scena).
  const startOf = new Map<string, string>()
  for (const id of planIds(x, goal, dropped)) {
    const m = x.measures.find((y) => y.id === id)
    if (!m) continue
    for (const raw of savedByRaw(ctx, x, [id]).keys()) {
      const p = raw.startsWith('res:') ? raw : (x.raw.get(raw)?.parent ?? '')
      if (!p.startsWith('res:')) continue
      const r = p.slice(4)
      const d = m.start_date || '0000'
      if (!startOf.has(r) || d < startOf.get(r)!) startOf.set(r, d)
    }
  }
  const locOf = (id: string) => x.raw.get(`res:${id}`)?.location ?? null
  return fc.months.map((m, i) => {
    const res: ForecastMonth['res'] = {}
    const loc: ForecastMonth['loc'] = {}
    const w = { ...ZERO }
    for (const [id, wo] of Object.entries(m.byRes)) {
      const early = startOf.has(id) && m.month < startOf.get(id)!
      const withM = pm && !off.has(id) && !early ? (pm[i]?.byRes[id] ?? wo) : wo
      res[id] = { without: wo, with: withM }
      for (const k of KEYS) w[k] += withM[k]
      const l = locOf(id)
      if (l) {
        const t = (loc[l] ??= { without: 0, with: 0 })
        t.without += wo.co2_kg
        t.with += withM.co2_kg
      }
    }
    return { month: m.month, without: m.without, with: pm ? w : m.with, loc, res }
  })
}

/**
 * Risorse della previsione (id senza «res:») che compongono un'unità, con il peso: un server conta per la sua quota
 * di costo sulla risorsa a cui appartiene (la previsione è per risorsa, non per server).
 */
export function forecastParts(x: Extra, parts: { raw: string; w: number }[]): { id: string; w: number }[] {
  const out = new Map<string, number>()
  for (const { raw, w } of parts) {
    if (raw.startsWith('res:')) {
      out.set(raw.slice(4), (out.get(raw.slice(4)) ?? 0) + w)
      continue
    }
    const r = x.raw.get(raw)
    const p = r?.parent
    if (!p?.startsWith('res:')) continue
    const pc = x.raw.get(p)?.cost ?? 0
    const share = pc > 0 ? Math.min(1, (r!.cost ?? 0) / pc) : 0
    out.set(p.slice(4), (out.get(p.slice(4)) ?? 0) + share * w)
  }
  return [...out].filter(([, w]) => w > 0).map(([id, w]) => ({ id, w }))
}

/** Costo e CO₂ dei prossimi 12 mesi per un'unità (risorse con una previsione propria, o la quota dei loro server). */
export function unitForecast(x: Extra, parts: { raw: string; w: number }[], fm: ForecastMonth[]): { without: Metrics; with: Metrics } | null {
  const ids = forecastParts(x, parts)
  if (!ids.length || !fm.length || !ids.some(({ id }) => fm[0].res[id])) return null
  const out = { without: { ...ZERO }, with: { ...ZERO } }
  for (const m of fm)
    for (const { id, w } of ids) {
      const r = m.res[id]
      if (!r) continue
      for (const k of KEYS) {
        out.without[k] += r.without[k] * w
        out.with[k] += r.with[k] * w
      }
    }
  return out
}
