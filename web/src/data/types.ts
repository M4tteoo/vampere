// Contratto dati tra backend (pipeline Python → output/*.json) e frontend (web/public/data/*.json).
// I file mock in public/data/ seguono esattamente questi tipi: per passare ai dati veri basta sostituirli.

export type LocationId = 'CH' | 'DE' | 'IE' | 'EU'
export type MetricKey = 'cost_chf' | 'kwh' | 'co2_kg'

export interface Range {
  low: number
  mid: number
  high: number
}

/** Valori annui (scenario medio). */
export interface Metrics {
  cost_chf: number
  kwh: number
  co2_kg: number
}

/** «Ogni numero si apre»: formula, input e fonti dietro una cifra. */
export interface Calc {
  formula: string
  inputs?: Record<string, string | number>
  sources: string[]
}

export interface Department {
  id: string
  label: string
  fte: number
  /** Posti di licenza visualizzati come scrivanie (scalati per la scena). */
  seats_total: number
  seats_active: number
  metrics: Metrics
}

export interface Location {
  id: LocationId
  label: string
  /** kg CO₂ per kWh, location-based. */
  grid_kg_per_kwh: Range
  /** Solo per la Svizzera: mix di produzione (bonus B2). */
  grid_alt_kg_per_kwh?: Range
  source: string
}

export interface Summary {
  is_mock: boolean
  baseline_period: string
  baseline: Metrics
  baseline_range?: { kwh: Range; co2_kg: Range }
  target: {
    co2_reduction: number
    cost_reduction: number
    budget_chf: number
    day_rate_chf: number
  }
  departments: Department[]
  locations: Location[]
}

export type EntityKind =
  | 'cluster'
  | 'server_group'
  | 'gpu'
  | 'storage'
  | 'ai_api'
  | 'subscriptions'
  | 'saas'
  | 'reporting'
  | 'build'

export type EntityTag = 'driver' | 'waste' | 'locked' | 'human' | 'contradiction'

export interface Entity {
  id: string
  label: string
  kind: EntityKind
  location: LocationId
  department: string
  tool: string
  metrics: Metrics
  /** 0–1, utilizzo medio (CPU/GPU) se disponibile. */
  utilisation?: number
  /** 0–1, quota di tempo accesa ma inattiva. */
  idle_ratio?: number
  /** Numero di macchine o elementi (per disegnare più server). */
  count?: number
  tags: EntityTag[]
  note?: string
  calc?: Calc
  /** Gruppi di licenze: posti comprati e attivi negli ultimi 30 giorni. */
  seats?: { purchased: number; active: number }
  /** Chi fornisce il servizio cloud: Azure, AWS, Swiss hoster (dai file di fattura). */
  provider?: string
  /** Risorsa condivisa: quota di ogni reparto sul costo di baseline e chiave usata (contract/types.ts → Allocation). */
  allocation?: { department: string; share: number; key: 'row_tag' | 'cost_center' | 'mapping' | 'fte' }[]
  /** Ore nell'anno di baseline: accesa (runtime) e al lavoro (active). Solo dove il backend le misura. */
  hours?: { runtime: number; active: number }
  /** ID di oggetti della scena (layout.json) che rappresentano questa entità, oltre all'id stesso. */
  scene_ids?: string[]
}

/** Effetto di una misura su un'entità, usato solo per animare la scena. */
export interface Effect {
  /** id di un'entità, oppure "seats" = le scrivanie con licenza inutilizzata. */
  entity_id: string
  kind: 'off' | 'shrink' | 'move'
  /** 0–1: quanto si riducono energia e CO₂ dell'entità nella scena. */
  reduction: number
  to?: LocationId
}

export type MeasureStatus = 'ok' | 'human' | 'blocked'

export interface Measure {
  id: string
  title: string
  description: string
  effort_days: number
  savings: Metrics
  status: MeasureStatus
  /** Ruolo che decide (da mapping_departments_tools.csv → responsible_role). */
  owner_role?: string
  /** Motivo per human / blocked. */
  reason?: string
  /** Fa parte del pacchetto scelto dall'ottimizzatore. */
  recommended: boolean
  /** Primo mese in cui il risparmio è effettivo (YYYY-MM). */
  start_month?: string
  effects: Effect[]
  calc?: Calc
  sources: string[]
}

export interface Limit {
  id: string
  entity_id: string
  type: 'window' | 'block' | 'human' | 'contradiction'
  title: string
  text: string
  source: string
}

export interface Finding {
  id: string
  entity_id: string
  title: string
  evidence: string
  severity: 'high' | 'medium' | 'low'
  source: string
}

export interface QualityItem {
  source_file: string
  issue: string
  rows: number
  action: string
}

/** Dati rapidi per un singolo oggetto della scena (items.json): posto, licenza, report, contratto, app AI, agente. */
export type ItemState = 'ok' | 'waste' | 'locked' | 'human' | 'contradiction'

export interface ItemInfo {
  id: string
  entity_id?: string
  label: string
  kind: 'report' | 'saas' | 'm365' | 'licence' | 'ai_app' | 'agent'
  department?: string
  state: ItemState
  headline: string
  facts: { label: string; value: string }[]
  source: string
}

/** Un oggetto posizionato nella scena (web/public/models/layout.json, generato da design/blender/env/layout.py). */
export interface LayoutChild {
  asset: string
  pos: [number, number, number]
  rotY: number
}

export interface LayoutItem {
  id: string
  asset: string
  pos: [number, number, number]
  rotY: number
  room?: string
  active?: boolean
  seatId?: string
  children?: LayoutChild[]
  view?: 'island'
  island?: string
  resourceId?: string
  resourceIds?: string[]
  representedCount?: number
  alternateSlotM1?: string
}

export interface Dataset {
  summary: Summary
  entities: Entity[]
  measures: Measure[]
  limits: Limit[]
  findings: Finding[]
  quality: QualityItem[]
  /** Facoltativo: se manca, la scena usa solo le entità. */
  items: ItemInfo[]
  /** Scena: posizioni e ID di tutti gli oggetti interattivi. */
  layout: LayoutItem[]
  /** Vista consultiva «AI locale» (local_ai.json): null se il file manca. Non cambia nessun altro numero. */
  localAi?: LocalAiFile | null
}

// --- AI locale (contract/types.ts LocalAiFile; i valori restano range del backend) -----------------------

export type LocalAiTier = 'basic' | 'standard' | 'advanced'
/** Metriche del contratto: range in tre valute, kWh e CO₂. */
export interface RangeMetrics {
  cost_chf: Range
  kwh: Range | null
  co2_kg: Range | null
}

export interface LocalAiWorkload {
  id: string
  label: string
  resource_id: string
  why_private: string
  tier: LocalAiTier
  models_today: string[]
  out_eq_tokens: number
  peak_tps: number
  api: RangeMetrics
}

export interface LocalAiModel {
  id: string
  label: string
  licence: string
  tier: LocalAiTier
  languages: string
  quality_note: string
  weights_gb: number
}

export interface LocalAiHardware {
  id: string
  label: string
  provider: string
  location: LocationId
  gpu: string
  vram_gb: number
  owned: boolean
  entity_id: string | null
  note: string
  estimate: boolean
}

export interface LocalAiFit {
  id: string
  workload_id: string
  model_id: string
  hardware_id: string
  feasible: boolean
  reasons: string[]
}

export interface LocalAiScenario {
  id: string
  label: string
  hardware_id: string
  workload_ids: string[]
  kept_on_api: string[]
  model_id: string | null
  alternatives: string[]
  feasible: boolean
  reasons: string[]
  utilisation?: number
  api_3y?: RangeMetrics
  local_3y?: RangeMetrics
  savings_3y?: RangeMetrics
  setup_chf?: Range
  yearly_chf?: Range
  breakeven_month?: { low: number | null; mid: number | null; high: number | null }
  interacts_with?: { measure_id: string; title: string; in_package: boolean; cost_chf_per_year: Range | null; note: string }[]
  pros?: string[]
  cons?: string[]
}

export interface LocalAiFile {
  advisory: true
  horizon_years: number
  note: string
  catalog_date: string
  workloads: LocalAiWorkload[]
  models: LocalAiModel[]
  hardware: LocalAiHardware[]
  fits: LocalAiFit[]
  scenarios: LocalAiScenario[]
  best: { by_cost: string | null; by_co2: string | null; by_workload: { workload_id: string; fit: string | null }[] }
}
