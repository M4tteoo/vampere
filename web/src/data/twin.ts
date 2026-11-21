// Collega gli oggetti della scena (layout.json) ai dati (entities / items / measures) e decide il loro stato visivo.
import { effectiveEntity, seatsHidden, type EffectiveEntity } from './compute'
import type { Dataset, Entity, ItemInfo, LayoutItem } from './types'

export const DEPARTMENTS = ['consulting', 'sales', 'marketing', 'it', 'finance', 'hr', 'management'] as const
export type DeptId = (typeof DEPARTMENTS)[number]

export const DEPT_LABEL: Record<string, string> = {
  consulting: 'Consulting',
  sales: 'Sales',
  marketing: 'Marketing',
  it: 'IT',
  finance: 'Finance',
  hr: 'HR',
  management: 'Management',
  corridor: 'Corridor',
  reception: 'Reception',
}

/** Colori d'accento dei reparti (design/office-spec.md §2), usati per sedie e robot. */
export const DEPT_ACCENT: Record<string, string> = {
  consulting: '#9DBFA8',
  sales: '#D98C6A',
  marketing: '#F2A7A0',
  it: '#7F9CC2',
  finance: '#D9B45A',
  hr: '#B9A7D9',
  management: '#4F7F86',
}

export const ISLAND_LOCATION: Record<string, 'CH' | 'DE' | 'IE' | 'EU'> = {
  zurich: 'CH',
  frankfurt: 'DE',
  dublin: 'IE',
  'eu-mixed': 'EU',
}

/** Stato visivo di un oggetto: guida colori di schermi e LED, badge e visibilità. */
export type Visual = 'ok' | 'driver' | 'waste' | 'off' | 'reduced' | 'removed' | 'locked' | 'human' | 'contradiction' | 'idle'

export interface ItemStatus {
  visual: Visual
  /** Nascosto con animazione (es. licenza disdetta, server dismesso). */
  hidden: boolean
  /** Sede attuale, se l'oggetto è un server su un'isola (può cambiare con una misura). */
  moved: boolean
  /** 0–1: quanto «lavora» (velocità di ventole e nastri). */
  activity: number
  entity?: EffectiveEntity
  info?: ItemInfo
}

export interface Ctx {
  data: Dataset
  active: string[]
  entities: Map<string, EffectiveEntity>
  /** id oggetto scena → id entità */
  alias: Map<string, string>
  info: Map<string, ItemInfo>
  seatsHidden: boolean
}

export function makeCtx(data: Dataset, active: string[]): Ctx {
  const entities = new Map(data.entities.map((e) => [e.id, effectiveEntity(e, data, active)]))
  const alias = new Map<string, string>()
  for (const e of data.entities) for (const s of e.scene_ids ?? []) alias.set(s, e.id)
  for (const i of data.items) if (i.entity_id) alias.set(i.id, i.entity_id)
  return { data, active, entities, alias, info: new Map(data.items.map((i) => [i.id, i])), seatsHidden: seatsHidden(data, active) }
}

/** L'id «di risorsa» di un oggetto: le copie sulle isole puntano alla stessa risorsa dell'ufficio. */
export function resourceOf(item: LayoutItem): string {
  return item.resourceId ?? item.id
}

/** Licenze AI: lic:<prodotto>:<reparto>:NN → gruppo lic:<prodotto>:<reparto>. */
export function groupId(id: string): string {
  if (id.startsWith('lic:')) return id.split(':').slice(0, 3).join(':')
  if (id.startsWith('seat:')) return `m365:${id.split(':')[1]}`
  return id
}

export function entityOf(ctx: Ctx, id: string): Entity | undefined {
  const rid = ctx.alias.get(id) ?? ctx.alias.get(groupId(id)) ?? id
  return ctx.entities.get(rid)?.entity
}

export function effectiveOf(ctx: Ctx, id: string): EffectiveEntity | undefined {
  const rid = ctx.alias.get(id) ?? ctx.alias.get(groupId(id)) ?? id
  return ctx.entities.get(rid)
}

function fromEntity(eff: EffectiveEntity): Visual {
  if (eff.visual === 'removed') return 'removed'
  if (eff.visual === 'off') return 'off'
  if (eff.visual === 'reduced') return 'reduced'
  const t = eff.entity.tags
  if (t.includes('locked')) return 'locked'
  if (t.includes('waste')) return 'waste'
  if (t.includes('contradiction')) return 'contradiction'
  if (t.includes('human')) return 'human'
  if (t.includes('driver')) return 'driver'
  return 'ok'
}

export function statusOf(ctx: Ctx, item: LayoutItem): ItemStatus {
  const id = item.id
  // Posti di lavoro = licenze Microsoft 365: attivo, oppure pagato e non usato.
  if (id.startsWith('seat:')) {
    const info = ctx.info.get(groupId(id))
    const entity = effectiveOf(ctx, id)
    if (item.active) return { visual: 'ok', hidden: false, moved: false, activity: 1, info, entity }
    return { visual: ctx.seatsHidden ? 'removed' : 'waste', hidden: false, moved: false, activity: 0, info, entity }
  }
  if (id.startsWith('lic:')) {
    const info = ctx.info.get(groupId(id))
    const entity = effectiveOf(ctx, id)
    if (item.active) return { visual: 'ok', hidden: false, moved: false, activity: 1, info, entity }
    return { visual: ctx.seatsHidden ? 'removed' : 'waste', hidden: ctx.seatsHidden, moved: false, activity: 0, info, entity }
  }
  if (id.startsWith('window:')) return { visual: 'locked', hidden: false, moved: false, activity: 0 }
  if (id === 'handover:queue') {
    const pending = ctx.data.measures.some((m) => m.status === 'human' && ctx.active.includes(m.id))
    return { visual: pending ? 'human' : 'ok', hidden: false, moved: false, activity: pending ? 1 : 0 }
  }

  const info = ctx.info.get(id) ?? ctx.info.get(resourceOf(item))
  const eff = effectiveOf(ctx, resourceOf(item))
  // Oggetti con dati propri (report, contratti SaaS, app AI, agenti).
  if (info) {
    let visual: Visual = info.state === 'ok' ? 'ok' : info.state
    if (eff && eff.reduction > 0 && visual === 'waste') visual = 'reduced'
    return { visual, hidden: false, moved: false, activity: eff ? 1 - eff.reduction * 0.8 : 1, info, entity: eff }
  }
  if (eff) {
    const visual = fromEntity(eff)
    const island = item.view === 'island'
    return {
      visual,
      hidden: visual === 'removed',
      moved: island && eff.moved,
      activity: visual === 'off' || visual === 'removed' ? 0 : 1 - eff.reduction * 0.85,
      entity: eff,
    }
  }
  return { visual: 'idle', hidden: false, moved: false, activity: 0.6 }
}

/** Nome leggibile di un oggetto della scena. */
export function labelOf(ctx: Ctx, item: LayoutItem): string {
  const id = item.id
  if (id.startsWith('seat:')) return `${DEPT_LABEL[item.room ?? ''] ?? ''} workstation ${id.split(':')[2]}`
  if (id.startsWith('lic:')) {
    const [, product, , n] = id.split(':')
    return `${PRODUCT_LABEL[product] ?? product} · seat ${n}`
  }
  if (id.startsWith('window:')) return WINDOW_LABEL[id] ?? 'Protected window'
  if (id === 'handover:queue') return 'Approval queue'
  const info = ctx.info.get(id) ?? ctx.info.get(resourceOf(item))
  if (info) return info.label.replace(/^Report: /, '')
  const rid = resourceOf(item)
  return ctx.entities.get(rid)?.entity.label ?? EXTRA_LABEL[rid] ?? rid
}

export const PRODUCT_LABEL: Record<string, string> = { copilot: 'Microsoft Copilot', claude: 'Claude Team', chatgpt: 'ChatGPT Team' }

const WINDOW_LABEL: Record<string, string> = {
  'window:nightly-processing': 'Night window: ETL, Power BI, exports',
  'window:quarterly-training': 'Quarterly training (days 1–3)',
  'window:finance-closing': 'Month-end finance closing',
  'window:acceptance-freeze': 'Freeze and acceptance tests',
}

/** Collegamento finestre protette → entità a cui si riferiscono (limits.json). */
export const WINDOW_ENTITY: Record<string, string[]> = {
  'window:nightly-processing': ['dp-prod'],
  'window:quarterly-training': ['dp-dev', 'gpu-ml'],
  'window:finance-closing': ['dp-prod'],
  'window:acceptance-freeze': ['vm-test'],
}

const EXTRA_LABEL: Record<string, string> = {
  'st-proj': 'Project file storage',
  'dp-storage': 'Data platform storage',
  'st-archive': 'Legacy project archive',
  sandboxes: 'Personal sandboxes (24)',
  logs: 'Logging and monitoring',
  'web-cdn': 'Website and CDN',
  'net-egress': 'Outbound data traffic',
  'saas-m365': 'Microsoft 365 · shared services',
}

/** Tutti gli oggetti di una stanza, per il pannello della stanza. */
export function roomItems(layout: LayoutItem[], room: string) {
  return layout.filter((i) => i.room === room && i.view !== 'island')
}

/** Oggetto della scena da inquadrare per un'entità (es. «ai-api» → la macchina di analisi testi). */
export function sceneIdFor(ctx: Ctx, layout: LayoutItem[], id: string): string | null {
  if (layout.some((i) => i.id === id)) return id
  const PREFERRED: Record<string, string> = { 'ai-api': 'ai-marketing', saas: 'saas-m365', 'ai-subs': 'lic:chatgpt:sales:01', 'storage-ch': 'st-proj' }
  if (PREFERRED[id] && layout.some((i) => i.id === PREFERRED[id])) return PREFERRED[id]
  const hit = layout.find((i) => i.view !== 'island' && (ctx.alias.get(i.id) ?? ctx.alias.get(groupId(i.id))) === id)
  return hit?.id ?? null
}
