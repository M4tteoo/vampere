// File del backend per i passi 2–4 (anno di baseline, pacchetti, previsione), letti così come sono.
// Gli id restano quelli del backend (res:…, srv:…, lic:…): il collegamento alla scena è in usage.ts.
import type { MetricKey, Metrics } from './types'

/* eslint-disable @typescript-eslint/no-explicit-any */
type R = { low: number; mid: number; high: number } | null | undefined
const mid = (r: R) => (r ? r.mid : NaN)
const metrics = (m: any): Metrics => ({ cost_chf: mid(m?.cost_chf), kwh: mid(m?.kwh), co2_kg: mid(m?.co2_kg) })

export interface XEffect {
  scope: string
  saved: Metrics
  relocate_to: string | null
}

export interface XMeasure {
  id: string
  title: string
  description: string
  type: string
  status: 'ok' | 'human' | 'blocked'
  /** Perché decide una persona, in etichette brevi («Critical», «Protected»…); vuoto se «ok». */
  triggers: string[]
  owner_role: string
  reason: string
  risks: string
  entity_ids: string[]
  finding_ids: string[]
  limit_ids: string[]
  effort_days: number
  savings: Metrics
  start_date: string
  effects: XEffect[]
}

export interface XFinding {
  id: string
  kind: string
  severity: 'high' | 'medium' | 'low'
  title: string
  entity_ids: string[]
  evidence: { statement: string; value: number; unit: string }[]
  impact: Metrics
  measure_ids: string[]
}

export interface XLimit {
  id: string
  type: string
  title: string
  entity_ids: string[]
  period_text: string
  decided_by: string | null
  source: string
}

export interface XPackage {
  goal: string
  measure_ids: string[]
  effort_days: number
  effort_chf: number
  savings: Metrics
  /** Riduzione rispetto alla baseline, 0–1 (valore centrale e con i fattori pessimisti). */
  co2: number
  co2_low: number
  cost: number
  meets: { co2: boolean; cost: boolean; budget: boolean }
  meets_at_low: { co2: boolean; cost: boolean }
}

export interface XHours {
  /** g CO₂/kWh nelle 24 ore (giorni lavorativi), per sede e stagione. */
  profiles: { loc: string; season: 'winter' | 'summer' | 'year'; values: number[] }[]
  stats: Record<string, { min: number; max: number; cleanest: number; dirtiest: number; spread: number }>
  jobs: { name: string; resource: string; loc: string; window: string; rule: string; start: string; hours: number; runs: number; shiftable: boolean; locked: boolean; reason: string; suggested: string | null; saving: number | null; locAfter: string | null }[]
  saving: { low: number; mid: number; high: number }
  baselineCo2: number
  note: string
  source: string
}

export interface Extra {
  /** I 12 mesi della baseline (YYYY-MM-01). */
  months: string[]
  /** id backend → valori mensili nei 12 mesi della baseline. */
  series: Map<string, Record<MetricKey, number[]>>
  raw: Map<string, { location: string | null; parent: string | null; cost: number; label: string }>
  findings: XFinding[]
  measures: XMeasure[]
  packages: Record<string, XPackage>
  goals: string[]
  defaultGoal: string
  keptOn: { target: string; reason: string; ref: string; entity_ids: string[] }[]
  limits: XLimit[]
  forecast: {
    months: { month: string; without: Metrics; with: Metrics; byLoc: Record<string, { without: number; with: number }>; byRes: Record<string, Metrics> }[]
    /** Previsione di ogni pacchetto (lato «con»): totale e per risorsa, mese per mese. */
    packages: Record<string, { with: Metrics; byRes: Record<string, Metrics> }[]>
    events: { date: string; label: string; source: string; resource_id: string }[]; goal: string } | null
  clusters: { groups: { id: string; name: string; description: string; share_co2: number; size: number }[]; member: Map<string, string> } | null
  /** Vista market-based (bonus): totali, fattore kg/kWh per sede e risparmio CO₂ di ogni misura. */
  market: { location_co2: number; market_co2: number; factor: Record<string, number>; measureCo2: Record<string, number> } | null
  cleanHours: { saving: number; low: number; high: number; m01: number } | null
  /** Fasce del giorno (bonus carbon-aware): CO₂ della rete ora per ora per sede e i job della piattaforma dati. */
  hours: XHours | null
  confidence: { headline: string; byGoal: Record<string, number> } | null
  baseline: Metrics
}

const KEYS: MetricKey[] = ['cost_chf', 'kwh', 'co2_kg']

async function opt(base: string, name: string): Promise<any | null> {
  const r = await fetch(`${base}/${name}.json`).catch(() => null)
  if (!r?.ok || (r.headers.get('content-type') ?? '').includes('html')) return null
  return r.json()
}

export async function loadExtra(base: string, entitiesFile: any, findingsFile: any, measuresFile: any, limitsFile: any, ts: any): Promise<Extra> {
  if (!ts?.series) throw new Error('timeseries.json missing')
  const [forecast, clusters, market, jobs, montecarlo, summary] = await Promise.all(
    ['forecast', 'clusters', 'market', 'jobs', 'montecarlo', 'summary'].map((n) => opt(base, n)),
  )
  const { start, end } = ts.meta.baseline
  const months: string[] = []
  for (let d = new Date(start); d.toISOString().slice(0, 10) <= end; d.setMonth(d.getMonth() + 1)) months.push(d.toISOString().slice(0, 8) + '01')

  const series = new Map<string, Record<MetricKey, number[]>>()
  for (const s of ts.series) {
    if (s.granularity !== 'month') continue
    const by = new Map<string, any>(s.points.map((p: any) => [String(p.t).slice(0, 7), p]))
    const row = {} as Record<MetricKey, number[]>
    for (const k of KEYS) row[k] = months.map((m) => Number(by.get(m.slice(0, 7))?.[k] ?? 0) || 0)
    series.set(s.entity_id, row)
  }

  const raw = new Map<string, { location: string | null; parent: string | null; cost: number; label: string }>()
  for (const e of entitiesFile.entities) raw.set(e.id, { location: e.location, parent: e.parent_id, cost: mid(e.metrics?.cost_chf) || 0, label: e.label })

  const mfile = measuresFile
  const pkg = (p: any): XPackage => ({
    goal: p.goal,
    measure_ids: p.measure_ids,
    effort_days: p.effort_days,
    effort_chf: p.effort_chf,
    savings: metrics(p.savings),
    co2: p.reduction.co2.mid,
    co2_low: p.reduction.co2.low,
    cost: p.reduction.cost.mid,
    meets: p.meets,
    meets_at_low: p.meets_at_low,
  })
  const packages: Record<string, XPackage> = {}
  for (const [g, p] of Object.entries<any>(mfile.packages ?? {})) if (p.feasible !== false) packages[g] = pkg(p)
  if (!Object.keys(packages).length && mfile.package) packages[mfile.package.goal ?? 'default'] = pkg({ goal: 'default', ...mfile.package })

  const member = new Map<string, string>()
  for (const m of clusters?.members ?? []) member.set(m.entity_id, m.group_id)

  const goal = forecast?.optimized_history?.goal ?? mfile.package?.goal ?? Object.keys(packages)[0]
  return {
    months,
    series,
    raw,
    findings: findingsFile.findings.map((f: any) => ({
      id: f.id,
      kind: f.kind,
      severity: f.severity,
      title: f.title,
      entity_ids: f.entity_ids,
      evidence: f.evidence.map((e: any) => ({ statement: e.statement, value: e.value, unit: e.unit })),
      impact: metrics(f.impact),
      measure_ids: f.measure_ids ?? [],
    })),
    measures: mfile.measures.map((m: any) => ({
      id: m.id,
      title: m.title,
      description: m.description,
      type: m.type,
      status: m.status,
      triggers: (m.triggers ?? []).map((t: any) => t.label ?? t.id),
      owner_role: m.owner_role ?? '',
      reason: m.reason ?? '',
      risks: m.risks ?? '',
      entity_ids: m.entity_ids ?? [],
      finding_ids: m.finding_ids ?? [],
      limit_ids: m.limit_ids ?? [],
      effort_days: m.effort_days,
      savings: metrics(m.savings),
      start_date: m.start_date ?? '',
      effects: (m.effects ?? []).map((x: any) => ({
        scope: x.scope,
        relocate_to: x.relocate_to ?? null,
        saved: { cost_chf: x.saved_cost_chf ?? 0, kwh: x.saved_kwh ?? 0, co2_kg: x.saved_co2_kg ?? 0 },
      })),
    })),
    packages,
    goals: (mfile.goals ?? Object.keys(packages)).filter((g: string) => packages[g]),
    defaultGoal: mfile.package?.goal && packages[mfile.package.goal] ? mfile.package.goal : Object.keys(packages)[0],
    keptOn: (mfile.kept_on ?? []).map((k: any) => ({ target: k.target, reason: k.reason, ref: k.source?.ref ?? '', entity_ids: k.entity_ids ?? [] })),
    limits: limitsFile.limits.map((l: any) => ({
      id: l.id,
      type: l.type,
      title: l.title,
      entity_ids: l.entity_ids ?? [],
      period_text: l.period_text ?? '',
      decided_by: l.decided_by ?? null,
      source: `${l.source?.kind ?? ''} ${l.source?.ref ?? ''}`.trim(),
    })),
    forecast: forecast
      ? {
          months: forecast.months.map((m: any) => {
            // kg CO₂ del mese per sede (CH, DE, IE, EU), sommando le singole risorse della previsione.
            const byLoc: Record<string, { without: number; with: number }> = {}
            for (const [id, r] of Object.entries<any>(m.by_resource ?? {})) {
              const e = raw.get(`res:${id}`) ?? raw.get(id)
              const loc = e?.location ?? (e?.parent ? raw.get(e.parent)?.location : null)
              if (!loc) continue
              const t = (byLoc[loc] ??= { without: 0, with: 0 })
              t.without += mid(r.without?.co2_kg) || 0
              t.with += mid((r.with ?? r.without)?.co2_kg) || 0
            }
            const byRes: Record<string, Metrics> = {}
            for (const [id, r] of Object.entries<any>(m.by_resource ?? {})) byRes[id] = metrics(r.without)
            return { month: m.month, without: metrics(m.without), with: metrics(m.with), byLoc, byRes }
          }),
          events: (forecast.events ?? []).map((e: any) => ({ date: e.date, label: e.label, source: e.source, resource_id: e.resource_id ?? '' })),
          packages: Object.fromEntries(
            Object.entries<any>(forecast.packages ?? {})
              .filter(([, p]) => p.feasible !== false && p.months)
              .map(([g, p]) => [
                g,
                p.months.map((m: any) => ({
                  with: metrics(m.with),
                  byRes: Object.fromEntries(Object.entries<any>(m.by_resource ?? {}).map(([id, r]) => [id, metrics(r.with)])),
                })),
              ]),
          ),
          goal,
        }
      : null,
    clusters: clusters
      ? { groups: clusters.groups.map((g: any) => ({ id: g.id, name: g.name, description: g.description, share_co2: g.share_co2, size: g.size })), member }
      : null,
    market: market
      ? {
          location_co2: mid(market.baseline?.co2_kg),
          market_co2: mid(market.baseline?.co2_kg_market),
          factor: Object.fromEntries(Object.entries<any>(market.factors ?? {}).map(([l, f]) => [l, mid(f.kg_per_kwh)])),
          measureCo2: Object.fromEntries(Object.entries<any>(market.measure_savings ?? {}).map(([id, v]) => [id, mid(v.co2_kg_market)])),
        }
      : null,
    cleanHours: jobs?.after_package?.saving?.saving_dynamic
      ? {
          saving: jobs.after_package.saving.saving_dynamic.mid,
          low: jobs.after_package.saving.saving_dynamic.low,
          high: jobs.after_package.saving.saving_dynamic.high,
          m01: mid(mfile.measures.find((m: any) => m.id === 'M-01')?.savings?.co2_kg),
        }
      : null,
    hours: jobs?.profiles
      ? {
          profiles: jobs.profiles.map((p: any) => ({ loc: p.location, season: p.season, values: p.g_per_kwh })),
          stats: Object.fromEntries(
            Object.entries<any>(jobs.profile_stats ?? {}).map(([l, v]) => [
              l,
              { min: v.hourly_min_max_g_per_kwh?.[0] ?? 0, max: v.hourly_min_max_g_per_kwh?.[1] ?? 0, cleanest: v.cleanest_hour_year, dirtiest: v.dirtiest_hour_year, spread: v.median_daily_spread_pct },
            ]),
          ),
          jobs: (jobs.jobs ?? []).map((j: any) => {
            const after = (jobs.after_package?.jobs ?? []).find((a: any) => a.job_name === j.job_name)
            return {
              name: j.job_name,
              resource: j.resource_id,
              loc: j.location,
              window: j.window_type,
              rule: j.window_rule ?? '',
              start: j.usual_start,
              hours: j.avg_duration_h,
              runs: j.runs,
              shiftable: !!j.shiftable,
              locked: !!j.locked,
              reason: j.reason ?? '',
              suggested: after?.suggested_start ?? j.suggested_start ?? null,
              saving: after ? mid(after.saving_dynamic) : null,
              locAfter: after?.location ?? null,
            }
          }),
          saving: { low: jobs.after_package?.saving?.saving_dynamic?.low ?? 0, mid: jobs.after_package?.saving?.saving_dynamic?.mid ?? 0, high: jobs.after_package?.saving?.saving_dynamic?.high ?? 0 },
          baselineCo2: jobs.totals?.baseline_co2_kg ?? 0,
          note: jobs.after_package?.note ?? '',
          source: jobs.profile_source ?? '',
        }
      : null,
    confidence: montecarlo
      ? {
          headline: montecarlo.headline ?? '',
          byGoal: Object.fromEntries(Object.entries<any>(montecarlo.by_goal ?? {}).map(([g, v]) => [g, v.p_meet_both ?? v.co2_reduction?.p_meet ?? NaN])),
        }
      : null,
    baseline: metrics(summary?.baseline),
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */
