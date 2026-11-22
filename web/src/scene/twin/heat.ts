import { useMemo } from 'react'
import { useApp } from '../../store'
import { makeCtx, type Ctx } from '../../data/twin'
import type { Extra } from '../../data/extra'
import { allUnits, clusterOf, findingsOf, keptOnOf, locMonthly, locSaved, measuresOf, sum } from '../../data/usage'
import { activeIds, forecastPlan, goalOf, savedByRaw } from '../../data/plan'
import { marketRatios, useCo2 } from '../../data/co2'

export const CLOUD_LOCS: string[] = ['CH', 'DE', 'IE']

/** Stato di un oggetto nella mappa dei punti critici. */
export type Mark = 'none' | 'waste' | 'driver' | 'kept'

/**
 * Pochi colori, sempre gli stessi in tutti i passi: verde = a posto, blu = tenuto così di proposito (regola dell'azienda),
 * arancio = spreco, rosso = grande fonte. Con le misure attive un punto critico risolto torna verde.
 */
export const MARK_COLOR: Record<Mark, string> = { none: '#A8D5A2', waste: '#E8955A', driver: '#CF4F45', kept: '#6E9FD6' }
export const MARK_LABEL: Record<Mark, string> = {
  none: 'No issue found',
  waste: 'Waste found',
  driver: 'Big source of CO₂',
  kept: 'Kept as is on purpose (company rule)',
}

/** Cosa mostra la scena nei passi 2–4 in questo momento. */
export interface HeatView {
  /** Passo 2–4 con i dati del backend. */
  step: boolean
  /** Dentro un reparto: plastico neutro, oggetti colorati per punto critico, nuvole. */
  on: boolean
  ctx: Ctx
  x: Extra | null
  markOf: (unit: string) => Mark
  colorOf: (unit: string) => string
  /** kg CO₂ di una sede (CH, DE, IE) mostrati dalla nuvola in questo momento, e il massimo annuo della baseline. */
  cloudKg: (loc: string) => number
  cloudMax: number
  /** Le nuvole si stanno riempiendo (simulazione): l'etichetta dice «so far». */
  cumulative: boolean
  /** Unità con punti critici ancora aperti (spreco o grande fonte) e quanti. */
  pains: Map<string, number>
  /** Gruppo di comportamento (clustering) di un'unità hardware. */
  behaviourOf: (unit: string) => string | null
  /** Misure attive in questo momento (nuvole, colori e totali le tengono già in conto). */
  active: string[]
  /** Passo 3: unità toccate dalla misura aperta (velate di blu nella scena). */
  focusUnits: Set<string>
  /** Unità toccate da una misura (per trovare il reparto da mostrare). */
  unitsOfMeasure: (id: string) => string[]
  goal: string
}

interface UnitMarks {
  findings: { kind: 'waste' | 'driver'; ms: string[] }[]
  /** Misure che toccano l'unità direttamente (anche senza un punto critico collegato). */
  direct: string[]
  kept: boolean
}

/**
 * Stato della mappa nei passi 2–4. `opts.withPackage` forza un lato: nel passo 4 la pagina è divisa in due,
 * a sinistra la baseline (senza pacchetto), a destra con il pacchetto, con la stessa simulazione.
 */
export function useHeat(opts?: { withPackage?: boolean }): HeatView {
  const data = useApp((s) => s.data)!
  const step = useApp((s) => s.step)
  const room = useApp((s) => s.room)
  const month = useApp((s) => s.month)
  const goalSel = useApp((s) => s.goal)
  const withPackageSel = useApp((s) => s.withPackage)
  const showMeasures = useApp((s) => s.showMeasures)
  const dropped = useApp((s) => s.dropped)
  const focus = useApp((s) => s.focus)
  const compareBefore = useApp((s) => s.compareBefore)
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const co2 = useCo2(ctx)
  const x = data.extra ?? null
  const isStep = !!x && (step === 'baseline' || step === 'packages' || step === 'forecast')
  // Passo 4: il lato principale è sempre «con il pacchetto»; la baseline è l'altra metà dello schermo.
  const withPackage = opts?.withPackage ?? (step === 'forecast' ? true : withPackageSel)

  // Parti fisse: punti critici per unità con le misure che li risolvono, sedi, gruppi di comportamento.
  const base = useMemo(() => {
    if (!x) return null
    const units = allUnits(ctx)
    const marks = new Map<string, UnitMarks>()
    for (const u of units) {
      const f = findingsOf(ctx, x, u).filter((y) => y.kind === 'waste' || y.kind === 'driver')
      const kept = keptOnOf(ctx, x, u).length > 0
      const direct = measuresOf(ctx, x, u).map((m) => m.id)
      if (!f.length && !kept && !direct.length) continue
      marks.set(u, { findings: f.map((y) => ({ kind: y.kind as 'waste' | 'driver', ms: y.measure_ids })), direct, kept })
    }
    const loc = new Map(CLOUD_LOCS.map((l) => [l, locMonthly(x, l)]))
    const cloudMax = Math.max(...CLOUD_LOCS.map((l) => sum(loc.get(l)!)))
    const behaviour = new Map(units.map((u) => [u, clusterOf(ctx, x, u)]))
    return { marks, loc, cloudMax, behaviour }
  }, [ctx, x])

  return useMemo<HeatView>(() => {
    const goal = x ? goalOf(x, goalSel) : ''
    const unitsOfMeasure = (id: string) =>
      base ? [...base.marks].filter(([, m]) => m.direct.includes(id) || m.findings.some((f) => f.ms.includes(id))).map(([u]) => u) : []
    const none: HeatView = {
      step: isStep,
      on: false,
      ctx,
      x,
      markOf: () => 'none',
      colorOf: () => MARK_COLOR.none,
      cloudKg: () => 0,
      cloudMax: 1,
      cumulative: false,
      pains: new Map(),
      behaviourOf: () => null,
      active: [],
      focusUnits: new Set(),
      unitsOfMeasure,
      goal,
    }
    if (!isStep || !x || !base) return none
    const annual = (l: string) => sum(base.loc.get(l)!)
    // Passo 4: i colori cambiano nel mese in cui ogni misura parte (simulazione mese per mese).
    const monthDate = step === 'forecast' && month !== null ? (x.forecast?.months[month]?.month ?? null) : null
    const active = activeIds(x, { step, showMeasures, withPackage, goal: goalSel, dropped, focus, compareBefore }, monthDate)
    const on = new Set(active)
    const saved = savedByRaw(ctx, x, active)

    // Punti critici ancora aperti con le misure attive: un punto si chiude se una sua misura è attiva
    // (o, se non ne ha, se una misura attiva tocca direttamente l'unità).
    const open = (m: UnitMarks) => m.findings.filter((f) => !(f.ms.some((id) => on.has(id)) || (!f.ms.length && m.direct.some((id) => on.has(id)))))
    const markOf = (u: string): Mark => {
      const m = base.marks.get(u)
      if (!m) return 'none'
      const rest = open(m)
      if (rest.some((f) => f.kind === 'driver')) return 'driver'
      if (rest.length) return 'waste'
      return m.kept ? 'kept' : 'none'
    }

    let cloudKg: (l: string) => number
    let cumulative = false
    if (step === 'forecast') {
      // Prossimi 12 mesi: le nuvole si riempiono mese per mese con la previsione per sede (senza o con il piano del passo 3).
      const fm = forecastPlan(ctx, x, goal, dropped)
      const upTo = (month ?? fm.length - 1) + 1
      cloudKg = (l) => fm.slice(0, upTo).reduce((a, m) => a + (withPackage ? (m.loc[l]?.with ?? 0) : (m.loc[l]?.without ?? 0)), 0)
      cumulative = upTo < fm.length
    } else if (step === 'baseline' && month !== null) {
      cumulative = true
      cloudKg = (l) => sum(base.loc.get(l)!.slice(0, month + 1))
    } else {
      cloudKg = (l) => Math.max(0, annual(l) - (active.length ? locSaved(x, saved, l) : 0))
    }

    // Vista market-based: stessa nuvola, CO₂ con il fattore della sede (scala comune, così si confrontano).
    const kgLocation = cloudKg
    cloudKg = (l) => kgLocation(l) * co2.loc(l)
    // Scala fissa per entrambe le viste: passando a market-based la nuvola di Zurigo resta uguale, Francoforte cresce.
    const ratios = x.market ? marketRatios(x) : {}
    const cloudMax = Math.max(base.cloudMax, ...CLOUD_LOCS.map((l) => annual(l) * (ratios[l] ?? 1)))

    const pains = new Map<string, number>()
    for (const [u, m] of base.marks) {
      const n = open(m).length
      if (n) pains.set(u, n)
    }
    return {
      step: true,
      // Passo 4: niente reparti, si vedono solo le isole (sempre «dentro»).
      on: !!room || step === 'forecast',
      ctx,
      x,
      markOf,
      colorOf: (u) => MARK_COLOR[markOf(u)],
      cloudKg,
      cloudMax,
      cumulative,
      pains,
      behaviourOf: (u) => base.behaviour.get(u) ?? null,
      active,
      focusUnits: new Set(step === 'packages' && focus ? unitsOfMeasure(focus) : []),
      unitsOfMeasure,
      goal,
    }
  }, [isStep, x, base, step, room, month, goalSel, withPackage, showMeasures, dropped, focus, compareBefore, ctx, co2])
}

const SEVERITY: Mark[] = ['none', 'kept', 'waste', 'driver']

/** Stato più grave fra le unità di un reparto (i suoi computer e le risorse cloud che usa): colora il reparto nella pianta. */
export function deptMark(heat: HeatView, units: string[]): Mark {
  return units.map((u) => heat.markOf(u)).reduce<Mark>((a, m) => (SEVERITY.indexOf(m) > SEVERITY.indexOf(a) ? m : a), 'none')
}
