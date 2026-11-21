import { useMemo } from 'react'
import { useApp } from '../../store'
import { makeCtx, type Ctx } from '../../data/twin'
import type { Extra } from '../../data/extra'
import type { MetricKey } from '../../data/types'
import {
  CLUSTER_COLORS,
  NEUTRAL,
  allUnits,
  clusterOf,
  findingsOf,
  heatScale,
  locMonthly,
  locSaved,
  savedByRaw,
  sum,
  unitMonthly,
  unitSaved,
  type HeatScale,
} from '../../data/usage'

export const CLOUD_LOCS: string[] = ['CH', 'DE', 'IE']

/** Cosa mostra la mappa «a colori» (passi 2–4) in questo momento. */
export interface HeatView {
  on: boolean
  ctx: Ctx
  x: Extra | null
  metric: MetricKey
  /** Didascalia del momento: «Mar 2026», «Baseline year», «With Climate first»… */
  label: string
  colorOf: (unit: string) => string
  /** Valore annuo (o annualizzato, durante la simulazione) di un'unità. */
  valueOf: (unit: string) => number
  baseOf: (unit: string) => number
  /** kg CO₂ all'anno di una sede (CH, DE, IE) in questo momento, e il massimo della baseline (per la grandezza delle nuvole). */
  cloudKg: (loc: string) => number
  cloudMax: number
  scale: HeatScale | null
  /** Unità con un punto critico (spreco o grande fonte): solo a fine simulazione della baseline. */
  pains: Map<string, number>
  goal: string
}

const MONTH = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })

export function useHeat(): HeatView {
  const data = useApp((s) => s.data)!
  const step = useApp((s) => s.step)
  const month = useApp((s) => s.month)
  const goalSel = useApp((s) => s.goal)
  const colorBy = useApp((s) => s.colorBy)
  const withPackage = useApp((s) => s.withPackage)
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const x = data.extra ?? null
  const on = !!x && (step === 'baseline' || step === 'packages' || step === 'forecast')
  const metric: MetricKey = colorBy === 'cost_chf' ? 'cost_chf' : 'co2_kg'

  // Parti fisse (non dipendono dal mese): serie, risparmi dei pacchetti, scala.
  const base = useMemo(() => {
    if (!x) return null
    const units = allUnits(ctx)
    const monthly = (k: MetricKey) => new Map(units.map((u) => [u, unitMonthly(ctx, x, u, k)]))
    const series: Record<MetricKey, Map<string, number[]>> = { co2_kg: monthly('co2_kg'), cost_chf: monthly('cost_chf'), kwh: monthly('kwh') }
    const scales = Object.fromEntries((['co2_kg', 'cost_chf', 'kwh'] as MetricKey[]).map((k) => [k, heatScale(units.map((u) => sum(series[k].get(u)!)))])) as Record<MetricKey, HeatScale>
    const saved = new Map(Object.entries(x.packages).map(([g, p]) => [g, savedByRaw(ctx, x, p.measure_ids)]))
    const loc = new Map(CLOUD_LOCS.map((l) => [l, locMonthly(x, l)]))
    const cloudMax = Math.max(...CLOUD_LOCS.map((l) => sum(loc.get(l)!)))
    const clusters = new Map(units.map((u) => [u, clusterOf(ctx, x, u)]))
    const pains = new Map<string, number>()
    for (const u of units) {
      const n = findingsOf(ctx, x, u).filter((f) => f.kind === 'waste' || f.kind === 'driver').length
      if (n) pains.set(u, n)
    }
    return { units, series, scales, saved, loc, cloudMax, clusters, pains }
  }, [ctx, x])

  return useMemo<HeatView>(() => {
    const goal = goalSel && x?.packages[goalSel] ? goalSel : (x?.defaultGoal ?? '')
    const empty: HeatView = { on: false, ctx, x, metric, label: '', colorOf: () => NEUTRAL, valueOf: () => NaN, baseOf: () => NaN, cloudKg: () => 0, cloudMax: 1, scale: null, pains: new Map(), goal }
    if (!on || !x || !base) return empty
    const annual = (u: string, k: MetricKey) => sum(base.series[k].get(u) ?? [])
    const fGoal = x.forecast?.goal && x.packages[x.forecast.goal] ? x.forecast.goal : x.defaultGoal

    let valueOf: (u: string) => number
    let cloudKg: (l: string) => number
    let label: string
    if (step === 'baseline') {
      if (month === null) {
        valueOf = (u) => annual(u, metric)
        cloudKg = (l) => sum(base.loc.get(l)!)
        label = 'Baseline year · Sep 2025 – Aug 2026'
      } else {
        valueOf = (u) => (base.series[metric].get(u)?.[month] ?? 0) * 12
        cloudKg = (l) => (base.loc.get(l)?.[month] ?? 0) * 12
        label = MONTH(x.months[month])
      }
    } else if (step === 'packages') {
      const sv = base.saved.get(goal)!
      valueOf = (u) => Math.max(0, annual(u, metric) - unitSaved(ctx, sv, u, metric))
      cloudKg = (l) => Math.max(0, sum(base.loc.get(l)!) - locSaved(x, sv, l))
      label = 'One year with the package'
    } else {
      // Previsione: l'andamento del totale (con o senza pacchetto) applicato a ogni oggetto.
      const fm = x.forecast?.months[month ?? 11]
      const tot = x.baseline
      const pk = x.packages[fGoal]
      const sv = base.saved.get(fGoal)!
      const rWithout = (k: MetricKey) => (fm ? fm.without[k] / (tot[k] / 12) : 1)
      const rWith = (k: MetricKey) => (fm && pk ? fm.with[k] / ((tot[k] - pk.savings[k]) / 12) : 1)
      valueOf = withPackage
        ? (u) => Math.max(0, annual(u, metric) - unitSaved(ctx, sv, u, metric)) * rWith(metric)
        : (u) => annual(u, metric) * rWithout(metric)
      cloudKg = withPackage
        ? (l) => Math.max(0, sum(base.loc.get(l)!) - locSaved(x, sv, l)) * rWith('co2_kg')
        : (l) => sum(base.loc.get(l)!) * rWithout('co2_kg')
      label = fm ? `${MONTH(fm.month)} · ${withPackage ? 'with the package' : 'without changes'}` : ''
    }
    const scale = base.scales[metric]
    const colorOf =
      colorBy === 'cluster'
        ? (u: string) => {
            const g = base.clusters.get(u)
            const i = g ? (x.clusters?.groups.findIndex((c) => c.id === g) ?? -1) : -1
            return i >= 0 ? CLUSTER_COLORS[i % CLUSTER_COLORS.length] : NEUTRAL
          }
        : (u: string) => scale.color(valueOf(u))
    return {
      on,
      ctx,
      x,
      metric,
      label,
      colorOf,
      valueOf,
      baseOf: (u) => annual(u, metric),
      cloudKg,
      cloudMax: base.cloudMax,
      scale,
      pains: step === 'baseline' && month === null ? base.pains : new Map(),
      goal,
    }
  }, [on, x, base, step, month, metric, goalSel, colorBy, withPackage, ctx])
}
