// Dal backend alla scena per i passi 2–4: ogni «unità» colorata della scena (i computer di un reparto, una risorsa
// sulle isole) ha i suoi valori mensili, i risparmi di un pacchetto e la previsione. Tutto si ricava dagli id del backend.
import type { Extra, XFinding, XLimit, XMeasure } from './extra'
import type { Entity, LayoutItem, MetricKey, Metrics } from './types'
import { effectiveOf, resourceOf, type Ctx } from './twin'

export const GOAL_LABEL: Record<string, string> = { climate_first: 'Climate first', best_value: 'Best value', francs_first: 'Francs first', safest: 'Safest' }
export const GOAL_HINT: Record<string, string> = {
  climate_first: 'Most CO₂ cut within the budget',
  best_value: 'Most CO₂ per franc spent',
  francs_first: 'Most money saved within the budget',
  safest: 'Least risk for operations',
}
export const ISLAND_LOC: Record<string, string> = { zurich: 'CH', frankfurt: 'DE', dublin: 'IE' }

/** Unità della scena: «pcs:<reparto>» (tutti i computer di un reparto) oppure l'id di una risorsa sulle isole. */
export function unitOf(ctx: Ctx, item: LayoutItem): string | null {
  if (item.id.startsWith('seat:')) return item.room ? `pcs:${item.room}` : null
  if (item.view === 'island') return effectiveOf(ctx, resourceOf(item))?.entity.id ?? null
  return null
}

export function computersIn(ctx: Ctx, room: string): number {
  return ctx.data.layout.filter((i) => i.id.startsWith(`seat:${room}:`)).length || 1
}

/** Entità del frontend usate dai computer di un reparto (licenze del reparto e app AI, con la quota se condivise). */
export function computerEntities(ctx: Ctx, room: string): { e: Entity; w: number }[] {
  const out: { e: Entity; w: number }[] = []
  for (const { entity: e } of ctx.entities.values()) {
    if (e.id.startsWith('lic:') && e.department === room) out.push({ e, w: 1 })
    else if (e.id.startsWith('ai-')) {
      const share = e.allocation ? (e.allocation.find((a) => a.department === room)?.share ?? 0) : e.department === room ? 1 : 0
      if (share > 0) out.push({ e, w: share })
    }
  }
  return out
}

/** Id del backend che compongono un'unità, con il peso. */
export function unitParts(ctx: Ctx, unit: string): { raw: string; w: number }[] {
  if (unit.startsWith('pcs:')) return computerEntities(ctx, unit.slice(4)).flatMap(({ e, w }) => (e.raw_ids ?? []).map((raw) => ({ raw, w })))
  const e = ctx.entities.get(unit)?.entity
  return (e?.raw_ids ?? []).map((raw) => ({ raw, w: 1 }))
}

/** Valori per un computer (pcs) oppure per la risorsa intera. */
export function unitDiv(ctx: Ctx, unit: string): number {
  return unit.startsWith('pcs:') ? computersIn(ctx, unit.slice(4)) : 1
}

export function unitMonthly(ctx: Ctx, x: Extra, unit: string, k: MetricKey): number[] {
  const div = unitDiv(ctx, unit)
  const out = x.months.map(() => 0)
  for (const { raw, w } of unitParts(ctx, unit)) {
    const s = x.series.get(raw)?.[k]
    if (s) s.forEach((v, i) => (out[i] += (v * w) / div))
  }
  return out
}

const sum = (a: number[]) => a.reduce((t, v) => t + v, 0)

/** Tutti gli id del backend «noti» alla scena (quelli delle entità del frontend). */
function knownRaws(ctx: Ctx): Set<string> {
  const s = new Set<string>()
  for (const { entity: e } of ctx.entities.values()) for (const r of e.raw_ids ?? []) s.add(r)
  return s
}

/** Un id del backend (anche un server, un prodotto su più reparti o un compito AI) → id noti alla scena. */
export function expandScope(ctx: Ctx, x: Extra, scope: string, known = knownRaws(ctx)): string[] {
  if (known.has(scope)) return [scope]
  if (scope.startsWith('ai:')) return expandScope(ctx, x, `res:${scope.split(':')[1]}`, known)
  if (scope.startsWith('lic:') && !scope.includes('@')) return [...known].filter((r) => r.startsWith(`${scope}@`))
  const parent = x.raw.get(scope)?.parent
  return parent ? expandScope(ctx, x, parent, known) : []
}

/** Risparmio di un insieme di misure su ogni id noto (un prodotto su più reparti si divide in base al costo). */
export function savedByRaw(ctx: Ctx, x: Extra, measureIds: string[]): Map<string, Metrics> {
  const known = knownRaws(ctx)
  const out = new Map<string, Metrics>()
  for (const m of x.measures) {
    if (!measureIds.includes(m.id) || m.status === 'blocked') continue
    for (const fx of m.effects) {
      const raws = expandScope(ctx, x, fx.scope, known)
      const tot = raws.reduce((a, r) => a + (x.raw.get(r)?.cost ?? 0), 0)
      for (const r of raws) {
        const f = raws.length === 1 ? 1 : tot > 0 ? (x.raw.get(r)?.cost ?? 0) / tot : 1 / raws.length
        const cur = out.get(r) ?? { cost_chf: 0, kwh: 0, co2_kg: 0 }
        out.set(r, { cost_chf: cur.cost_chf + fx.saved.cost_chf * f, kwh: cur.kwh + fx.saved.kwh * f, co2_kg: cur.co2_kg + fx.saved.co2_kg * f })
      }
    }
  }
  return out
}

export function unitSaved(ctx: Ctx, saved: Map<string, Metrics>, unit: string, k: MetricKey): number {
  const div = unitDiv(ctx, unit)
  return unitParts(ctx, unit).reduce((a, { raw, w }) => a + ((saved.get(raw)?.[k] ?? 0) * w) / div, 0)
}

/** CO₂ di una sede (loc:CH …) mese per mese, e il risparmio di un pacchetto su quella sede. */
export function locMonthly(x: Extra, loc: string): number[] {
  return x.series.get(`loc:${loc}`)?.co2_kg ?? x.months.map(() => 0)
}

export function locSaved(x: Extra, saved: Map<string, Metrics>, loc: string): number {
  let t = 0
  for (const [raw, m] of saved) {
    const r = x.raw.get(raw)
    const l = r?.location ?? (r?.parent ? x.raw.get(r.parent)?.location : null)
    if (l === loc) t += m.co2_kg
  }
  return t
}

/** Unità colorabili della scena: i computer di ogni reparto e ogni risorsa con un oggetto sulle isole. */
export function allUnits(ctx: Ctx): string[] {
  const s = new Set<string>()
  for (const item of ctx.data.layout) {
    const u = unitOf(ctx, item)
    if (u) s.add(u)
  }
  return [...s]
}

// --- Colori -------------------------------------------------------------------------------------------------

/** Cinque gradini, dal verde chiaro (poco) al rosso (molto). */
export const HEAT = ['#CFE6D4', '#9CCFA7', '#EBCB6E', '#E8955A', '#CF4F45']
export const NEUTRAL = '#E4E1DB'
export const CLUSTER_COLORS = ['#8FB8DE', '#CF4F45', '#EBCB6E', '#7FB58C']

export interface HeatScale {
  lo: number
  hi: number
  color: (v: number) => string
  /** Limiti dei gradini, per la legenda. */
  steps: number[]
}

/** Scala logaritmica: le risorse vanno da pochi kg a più di una tonnellata. Stessa scala per tutti i passi. */
export function heatScale(values: number[]): HeatScale {
  const pos = values.filter((v) => v > 0 && Number.isFinite(v))
  const lo = Math.max(Math.min(...pos), 1e-3)
  const hi = Math.max(...pos, lo * 10)
  const L = Math.log(lo)
  const H = Math.log(hi)
  // Gradini più fitti in alto: le differenze fra le risorse grandi (e i loro risparmi) restano visibili.
  const steps = [0.35, 0.6, 0.78, 0.9].map((f) => Math.exp(L + (H - L) * f))
  return {
    lo,
    hi,
    steps,
    color: (v) => {
      if (!(v > 0)) return HEAT[0]
      const i = steps.findIndex((s) => v < s)
      return HEAT[i === -1 ? 4 : i]
    },
  }
}

// --- Collegamenti: scoperte, misure, limiti di un'unità ----------------------------------------------------------

function unitRawSet(ctx: Ctx, unit: string): Set<string> {
  return new Set(unitParts(ctx, unit).map((p) => p.raw))
}

function touches(ctx: Ctx, x: Extra, ids: string[], set: Set<string>, known: Set<string>): boolean {
  return ids.some((id) => expandScope(ctx, x, id, known).some((r) => set.has(r)))
}

export function findingsOf(ctx: Ctx, x: Extra, unit: string): XFinding[] {
  const set = unitRawSet(ctx, unit)
  const known = knownRaws(ctx)
  return x.findings.filter((f) => touches(ctx, x, f.entity_ids, set, known))
}

export function measuresOf(ctx: Ctx, x: Extra, unit: string): XMeasure[] {
  const set = unitRawSet(ctx, unit)
  const known = knownRaws(ctx)
  return x.measures.filter((m) => touches(ctx, x, [...m.entity_ids, ...m.effects.map((f) => f.scope)], set, known))
}

export function limitsOf(ctx: Ctx, x: Extra, unit: string): XLimit[] {
  const set = unitRawSet(ctx, unit)
  const known = knownRaws(ctx)
  return x.limits.filter((l) => touches(ctx, x, l.entity_ids, set, known))
}

export function keptOnOf(ctx: Ctx, x: Extra, unit: string) {
  const set = unitRawSet(ctx, unit)
  const known = knownRaws(ctx)
  return x.keptOn.filter((k) => touches(ctx, x, k.entity_ids, set, known))
}

/** Gruppo di comportamento (clustering) più frequente fra i server di una risorsa. */
export function clusterOf(ctx: Ctx, x: Extra, unit: string): string | null {
  if (!x.clusters || unit.startsWith('pcs:')) return null
  const set = unitRawSet(ctx, unit)
  const count = new Map<string, number>()
  for (const [srv, g] of x.clusters.member) {
    const inUnit = set.has(srv) || set.has(x.raw.get(srv)?.parent ?? '')
    if (inUnit) count.set(g, (count.get(g) ?? 0) + 1)
  }
  let best: string | null = null
  for (const [g, n] of count) if (!best || n > count.get(best)!) best = g
  return best
}

export { sum }

/** Unità di un reparto: i suoi computer e le risorse cloud (con un oggetto sulle isole) che usa, da proprietario o in quota. */
export function deptUnits(ctx: Ctx, room: string): string[] {
  const hw = new Set<string>()
  for (const item of ctx.data.layout) {
    if (item.view !== 'island') continue
    const e = effectiveOf(ctx, resourceOf(item))?.entity
    if (e && (e.department === room || e.allocation?.some((a) => a.department === room))) hw.add(e.id)
  }
  return [`pcs:${room}`, ...hw]
}
