import type { Dataset, Entity, LocationId, Measure, MetricKey, Metrics } from './types'

export const ZERO: Metrics = { cost_chf: 0, kwh: 0, co2_kg: 0 }

export function addMetrics(a: Metrics, b: Metrics): Metrics {
  return { cost_chf: a.cost_chf + b.cost_chf, kwh: a.kwh + b.kwh, co2_kg: a.co2_kg + b.co2_kg }
}

export function scaleMetrics(m: Metrics, f: number): Metrics {
  return { cost_chf: m.cost_chf * f, kwh: m.kwh * f, co2_kg: m.co2_kg * f }
}

export interface PackageTotals {
  savings: Metrics
  effortDays: number
  effortChf: number
  co2Pct: number
  costPct: number
  co2Ok: boolean
  costOk: boolean
  budgetOk: boolean
}

/** Somma dei risparmi delle misure attive, confrontata con target e budget. */
export function packageTotals(data: Dataset, active: string[]): PackageTotals {
  const { baseline, target } = data.summary
  const chosen = data.measures.filter((m) => active.includes(m.id) && m.status !== 'blocked')
  const savings = chosen.reduce((acc, m) => addMetrics(acc, m.savings), ZERO)
  const effortDays = chosen.reduce((acc, m) => acc + m.effort_days, 0)
  const effortChf = effortDays * target.day_rate_chf
  const co2Pct = savings.co2_kg / baseline.co2_kg
  const costPct = savings.cost_chf / baseline.cost_chf
  return {
    savings,
    effortDays,
    effortChf,
    co2Pct,
    costPct,
    co2Ok: co2Pct >= target.co2_reduction,
    costOk: costPct >= target.cost_reduction,
    budgetOk: effortChf <= target.budget_chf,
  }
}

export type VisualState = 'normal' | 'reduced' | 'off' | 'removed'

export interface EffectiveEntity {
  entity: Entity
  location: LocationId
  metrics: Metrics
  /** 0–1: riduzione totale applicata dalle misure attive. */
  reduction: number
  visual: VisualState
  moved: boolean
  measures: Measure[]
}

/** Stato di un'entità nella scena dopo le misure attive (solo per la visualizzazione). */
export function effectiveEntity(e: Entity, data: Dataset, active: string[]): EffectiveEntity {
  const measures = data.measures.filter(
    (m) => active.includes(m.id) && m.status !== 'blocked' && m.effects.some((x) => x.entity_id === e.id),
  )
  let remaining = 1
  let location = e.location
  let hasOff = false
  for (const m of measures) {
    for (const fx of m.effects) {
      if (fx.entity_id !== e.id) continue
      remaining *= 1 - fx.reduction
      if (fx.kind === 'move' && fx.to) location = fx.to
      if (fx.kind === 'off') hasOff = true
    }
  }
  const reduction = 1 - remaining
  let visual: VisualState = 'normal'
  if (reduction >= 0.999) visual = 'removed'
  else if (hasOff) visual = 'off'
  else if (reduction > 0) visual = 'reduced'
  return {
    entity: e,
    location,
    metrics: scaleMetrics(e.metrics, remaining),
    reduction,
    visual,
    moved: location !== e.location,
    measures,
  }
}

export function seatsHidden(data: Dataset, active: string[]): boolean {
  return data.measures.some(
    (m) => active.includes(m.id) && m.status !== 'blocked' && m.effects.some((x) => x.entity_id === 'seats'),
  )
}

const CHF = new Intl.NumberFormat('de-CH', { maximumFractionDigits: 0 })

export function fmtMetric(v: number, key: MetricKey): string {
  if (!Number.isFinite(v)) return '–'
  // Valori piccoli (per singolo computer): un decimale, così non diventano «0».
  const small = (x: number) => (x > 0 && x < 10 ? x.toFixed(1) : CHF.format(x))
  if (key === 'kwh' && v < 10000) return `${small(v)} kWh`
  if (key === 'co2_kg' && v < 1000) return `${small(v)} kg CO₂`
  if (key === 'cost_chf') return v >= 10000 ? `CHF ${CHF.format(Math.round(v / 1000))}k` : `CHF ${CHF.format(v)}`
  if (key === 'kwh') return v >= 10000 ? `${CHF.format(Math.round(v / 1000))} MWh` : `${CHF.format(v)} kWh`
  return v >= 1000 ? `${(v / 1000).toFixed(1)} t CO₂` : `${CHF.format(v)} kg CO₂`
}

export function fmtChf(v: number): string {
  return `CHF ${CHF.format(Math.round(v))}`
}

export const METRIC_LABEL: Record<MetricKey, string> = {
  co2_kg: 'CO₂',
  cost_chf: 'CHF',
  kwh: 'kWh',
}

/** Totali per sede dopo le misure attive. Se un'entità cambia sede, la CO₂ si ricalcola con la rete della nuova sede. */
export function locationTotals(data: Dataset, active: string[]) {
  const z = (): Metrics => ({ ...ZERO })
  const now: Record<LocationId, Metrics> = { CH: z(), DE: z(), IE: z(), EU: z() }
  const base: Record<LocationId, Metrics> = { CH: z(), DE: z(), IE: z(), EU: z() }
  const grid = (id: LocationId) => data.summary.locations.find((l) => l.id === id)?.grid_kg_per_kwh.mid ?? 1
  for (const e of data.entities) {
    base[e.location] = addMetrics(base[e.location], e.metrics)
    const eff = effectiveEntity(e, data, active)
    const m = eff.moved ? { ...eff.metrics, co2_kg: (eff.metrics.co2_kg * grid(eff.location)) / grid(e.location) } : eff.metrics
    now[eff.location] = addMetrics(now[eff.location], m)
  }
  return { now, base }
}
