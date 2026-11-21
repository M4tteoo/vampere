// Adattatore: legge i file VERI della pipeline (output/*.json, contratto in contract/types.ts)
// e li traduce nel formato interno del frontend (src/data/types.ts), così la scena non cambia.
// I file si copiano con: web/scripts/sync-backend.sh  →  web/public/data/real/
import type { Dataset, Entity, EntityKind, EntityTag, ItemInfo, LayoutItem, Limit, LocalAiFile, Location, LocationId, Measure, Metrics, QualityItem, Finding } from './types'

type R = { low: number; mid: number; high: number } | null | undefined
interface RMetrics {
  cost_chf: R
  kwh: R
  co2_kg: R
}
interface RCalc {
  formula: string
  inputs: { name: string; value: number; unit: string; source: string }[]
  source_files: string[]
}
interface REntity {
  id: string
  kind: 'room' | 'island' | 'resource' | 'server' | 'license_group'
  label: string
  parent_id: string | null
  department: string | null
  tool: string | null
  location: LocationId | null
  metrics: RMetrics
  utilisation: number | null
  idle_ratio: number | null
  seats?: { purchased: number; active: number }
  allocation?: { department: string; share: number; key: 'row_tag' | 'cost_center' | 'mapping' | 'fte' }[]
  fte?: number
  state: string
  flags: string[]
  finding_ids: string[]
  calc: RCalc
}

/** null / mancante → NaN: il frontend mostra «–», mai 0 (regola 4 del contratto). */
const mid = (r: R) => (r ? r.mid : NaN)
const metrics = (m: RMetrics): Metrics => ({ cost_chf: mid(m.cost_chf), kwh: mid(m.kwh), co2_kg: mid(m.co2_kg) })
const dept = (d: string | null | undefined) => (d ? d.toLowerCase() : '')
const strip = (id: string) => id.replace(/^(res|srv|dept|loc):/, '')
const slug = (s: string) => s.toLowerCase().replace(/\s+/g, '-')

const TAG: Record<string, EntityTag> = { waste: 'waste', driver: 'driver', locked: 'locked', handover: 'human', contradiction: 'contradiction' }

const KIND: Record<string, EntityKind> = {
  'dp-prod': 'cluster',
  'dp-dev': 'cluster',
  'gpu-ml': 'gpu',
  'pbi-kap': 'reporting',
  cicd: 'build',
}

/** Oggetti della scena (layout.json) che rappresentano una risorsa vera quando l'id non coincide. */
const SCENE_IDS: Record<string, string[]> = {
  sandbox: ['sandboxes'],
  'ai-assistant': ['consulting', 'sales', 'marketing', 'it', 'finance', 'hr', 'management'].map((d) => `ai-assistant:${d}`),
  'ai-agent': ['agent:support-agent'],
  'ai-agent2': ['agent:sales-agent', 'agent:research-agent', 'agent:code-agent'],
  'ai-report': ['agent:report-agent'],
  'ai-chatbot': ['ai-chatbot:consulting'],
}

/** Posti di licenza: lic:<Prodotto>@<Reparto> → gruppi della scena (postazioni, dischetti AI, terminali SaaS). */
function licenceSceneIds(e: REntity): string[] {
  const product = e.tool ?? e.label.split(' · ')[0]
  const d = dept(e.department)
  if (product === 'Microsoft 365') return [`m365:${d}`]
  if (product === 'Microsoft Copilot') return [`lic:copilot:${d}`]
  if (product === 'Claude Team') return [`lic:claude:${d}`]
  if (product === 'ChatGPT Team') return [`lic:chatgpt:${d}`]
  return [`saas:${slug(product)}:${d}`]
}

const LOC_LABEL: Record<LocationId, string> = { CH: 'Zurich', DE: 'Frankfurt', IE: 'Dublin', EU: 'AI & SaaS · location not stated' }
const GRID_FACTOR: Record<LocationId, string> = {
  CH: 'grid_mix_location_based_switzerland',
  DE: 'grid_mix_location_based_germany',
  IE: 'grid_mix_location_based_ireland',
  EU: 'grid_mix_location_based_eu',
}

async function get<T>(base: string, name: string): Promise<T> {
  const res = await fetch(`${base}/${name}.json`)
  if (!res.ok) throw new Error(`Could not load ${name}.json (${res.status})`)
  return res.json() as Promise<T>
}

/** Prova a caricare i dati veri. Se mancano, restituisce null (il frontend usa i mock). */
export async function loadReal(base: string, items: ItemInfo[], layout: LayoutItem[]): Promise<Dataset | null> {
  const probe = await fetch(`${base}/summary.json`).catch(() => null)
  if (!probe?.ok || (probe.headers.get('content-type') ?? '').includes('html')) return null

  /* eslint-disable @typescript-eslint/no-explicit-any */
  const [summary, entitiesFile, factorsFile, findingsFile, measuresFile, limitsFile, qualityFile] = await Promise.all([
    probe.json() as Promise<any>,
    get<any>(base, 'entities'),
    get<any>(base, 'factors'),
    get<any>(base, 'findings'),
    get<any>(base, 'measures'),
    get<any>(base, 'limits'),
    get<any>(base, 'quality'),
  ])
  const ents: REntity[] = entitiesFile.entities
  // Ore accese / al lavoro nell'anno di baseline (serie mensili, solo dp-prod, dp-dev, gpu-ml).
  const hours = new Map<string, { runtime: number; active: number }>()
  const ts = await get<any>(base, 'timeseries').catch(() => null)
  const { start, end } = summary.meta.baseline
  for (const sr of ts?.series ?? []) {
    if (sr.granularity !== 'month' || !sr.points.some((p: any) => p.runtime_h !== undefined)) continue
    const pts = sr.points.filter((p: any) => p.t >= start && p.t <= end)
    hours.set(strip(sr.entity_id), {
      runtime: pts.reduce((a: number, p: any) => a + (p.runtime_h ?? 0), 0),
      active: pts.reduce((a: number, p: any) => a + (p.active_h ?? 0), 0),
    })
  }
  const findings: any[] = findingsFile.findings

  // --- entità: risorse, licenze e i due casi speciali (server di emergenza, server orfani)
  const toEntity = (e: REntity, id: string, scene_ids?: string[]): Entity => ({
    id,
    label: e.label,
    kind: KIND[id] ?? (e.kind === 'license_group' ? 'subscriptions' : e.kind === 'server' ? 'server_group' : 'server_group'),
    location: (e.location ?? 'EU') as LocationId,
    department: dept(e.department),
    tool: e.tool ?? '',
    metrics: metrics(e.metrics),
    utilisation: e.utilisation ?? undefined,
    idle_ratio: e.idle_ratio ?? undefined,
    tags: [...new Set(e.flags.map((f) => TAG[f]).filter(Boolean))],
    note: findings.find((f) => f.id === e.finding_ids[0])?.title,
    calc: {
      formula: e.calc.formula,
      inputs: Object.fromEntries(e.calc.inputs.map((i) => [`${i.name} (${i.unit})`, i.value])),
      sources: e.calc.source_files,
    },
    scene_ids,
    hours: hours.get(id),
    allocation: e.allocation?.map((a) => ({ ...a, department: dept(a.department) })),
    seats: e.seats,
    provider: e.calc.source_files.some((f) => f.startsWith('azure'))
      ? 'Azure'
      : e.calc.source_files.some((f) => f.startsWith('aws'))
        ? 'AWS'
        : e.calc.source_files.some((f) => f.startsWith('hoster'))
          ? 'Swiss hoster'
          : undefined,
  })

  const entities: Entity[] = []
  for (const e of ents) {
    if (e.kind === 'resource') entities.push(toEntity(e, strip(e.id), SCENE_IDS[strip(e.id)]))
    if (e.kind === 'license_group') entities.push(toEntity(e, e.id, licenceSceneIds(e)))
    if (e.id === 'srv:dr-failover') entities.push(toEntity(e, 'dr-failover'))
  }
  const orphans = ents.filter((e) => ['srv:poc-ki-2024', 'srv:migration-alt', 'srv:build-agent-old'].includes(e.id))
  if (orphans.length) {
    const sum = (k: keyof RMetrics) => orphans.reduce((a, o) => a + mid(o.metrics[k]), 0)
    const first = toEntity(orphans[0], 'orphans')
    entities.push({
      ...first,
      label: `Orphaned servers (${orphans.map((o) => o.label).join(', ')})`,
      metrics: { cost_chf: sum('cost_chf'), kwh: sum('kwh'), co2_kg: sum('co2_kg') },
      tags: [...new Set(orphans.flatMap((o) => o.flags.map((f) => TAG[f]).filter(Boolean)))],
      calc: { formula: 'sum of the three servers', sources: first.calc?.sources ?? [] },
    })
  }

  // --- sedi e reparti
  const factors: any[] = factorsFile.factors
  const locations: Location[] = (['CH', 'DE', 'IE', 'EU'] as LocationId[]).map((id) => {
    const f = factors.find((x) => x.id === GRID_FACTOR[id])
    return {
      id,
      label: LOC_LABEL[id],
      grid_kg_per_kwh: { low: f?.low ?? NaN, mid: f?.mid ?? NaN, high: f?.high ?? NaN },
      source: (f?.source ?? '').split('; ')[0],
    }
  })
  const departments = ents
    .filter((e) => e.kind === 'room' && e.fte)
    .map((e) => {
      const d = dept(e.department)
      const seats = layout.filter((i) => i.id.startsWith(`seat:${d}:`))
      return { id: d, label: e.label, fte: e.fte!, seats_total: seats.length, seats_active: seats.filter((s) => s.active).length, metrics: metrics(e.metrics) }
    })

  // --- dati rapidi per oggetto: si ricollegano alle entità vere
  const alias = new Map<string, string>()
  for (const e of entities) for (const s of e.scene_ids ?? []) alias.set(s, e.id)
  const fixedItems = items.map((i) => ({ ...i, entity_id: alias.get(i.id) ?? (entities.some((e) => e.id === i.entity_id) ? i.entity_id : undefined) }))

  // --- misure, scoperte, limiti, qualità (per i passi successivi)
  const measures: Measure[] = measuresFile.measures.map((m: any) => ({
    id: m.id,
    title: m.title,
    description: m.description,
    effort_days: m.effort_days,
    savings: metrics(m.savings),
    status: m.status,
    owner_role: m.owner_role ?? undefined,
    reason: m.reason ?? undefined,
    recommended: !!m.in_package,
    start_month: m.start_date?.slice(0, 7),
    effects: (m.effects ?? []).map((fx: any) => ({
      entity_id: strip(fx.scope),
      kind: fx.relocate_to ? 'move' : fx.cost_share >= 0.999 ? 'off' : 'shrink',
      reduction: fx.energy_share ?? fx.cost_share ?? 0,
      to: fx.relocate_to ?? undefined,
    })),
    calc: { formula: m.calc?.formula ?? '', sources: m.calc?.source_files ?? [] },
    sources: m.calc?.source_files ?? [],
  }))
  const limits: Limit[] = limitsFile.limits.map((l: any) => ({
    id: l.id,
    entity_id: strip(l.entity_ids[0] ?? ''),
    type: l.type === 'block' ? 'block' : l.type === 'contradiction' ? 'contradiction' : l.decided_by && l.type !== 'window' ? 'human' : 'window',
    title: l.title,
    text: l.period_text ?? '',
    source: `${l.source?.kind ?? ''} ${l.source?.ref ?? ''}`.trim(),
  }))
  const outFindings: Finding[] = findings.map((f) => ({
    id: f.id,
    entity_id: strip(f.entity_ids[0] ?? ''),
    title: f.title,
    evidence: f.evidence.map((e: any) => `${e.statement}: ${e.value} ${e.unit}`).join(' · '),
    severity: f.severity,
    source: [...new Set(f.evidence.flatMap((e: any) => e.source_files))].join(' · '),
  }))
  const quality: QualityItem[] = qualityFile.issues.map((q: any) => ({ source_file: q.source_file, issue: q.issue_type, rows: q.rows_affected ?? 0, action: q.action }))
  /* eslint-enable @typescript-eslint/no-explicit-any */
  // Vista consultiva facoltativa: se il file manca, il resto non cambia.
  const localAi = await get<LocalAiFile>(base, 'local_ai').catch(() => null)

  const b = summary.meta.baseline
  const fmt = (d: string) => new Date(d).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
  return {
    summary: {
      is_mock: false,
      baseline_period: `${fmt(b.start)} – ${fmt(b.end)}`,
      baseline: metrics(summary.baseline),
      target: {
        co2_reduction: summary.target.co2_reduction,
        cost_reduction: summary.target.cost_reduction,
        budget_chf: summary.target.budget_chf,
        day_rate_chf: summary.target.chf_per_person_day,
      },
      departments,
      locations,
    },
    entities,
    measures,
    limits,
    findings: outFindings,
    quality,
    items: fixedItems,
    layout,
    localAi,
  }
}
