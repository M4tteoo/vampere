import { useMemo } from 'react'
import { useApp } from '../store'
import { METRIC_LABEL, fmtMetric, locationTotals } from '../data/compute'
import {
  DEPT_ACCENT,
  DEPT_LABEL,
  ISLAND_LOCATION,
  WINDOW_ENTITY,
  groupId,
  labelOf,
  makeCtx,
  resourceOf,
  roomItems,
  sceneIdFor,
  statusOf,
  type Ctx,
  type Visual,
} from '../data/twin'
import type { Calc, LayoutItem, MetricKey } from '../data/types'
import { MeasureRow } from './ModePanel'
import { Card, Chip, Divider, Kicker, Row, type Tone } from './primitives'

/** Scheda a destra (come la «reservation card» di Airbnb): tutto quello che sappiamo dell'oggetto selezionato. */
export function Detail() {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  const selectedId = useApp((s) => s.selectedId)
  const select = useApp((s) => s.select)
  const ctx = useMemo(() => makeCtx(data, active), [data, active])
  if (!selectedId) return null

  let body: React.ReactNode = null
  if (selectedId.startsWith('room:')) body = <RoomDetail ctx={ctx} room={selectedId.slice(5)} />
  else if (selectedId.startsWith('loc:')) body = <LocationDetail ctx={ctx} island={selectedId.slice(4)} />
  else if (selectedId === 'handover:queue') body = <ApprovalQueue />
  else {
    const item = findItem(data.layout, selectedId)
    if (item) body = <ItemDetail ctx={ctx} item={item} />
  }
  if (!body) return null

  return (
    <Card className="flex max-h-full w-[400px] flex-col overflow-hidden">
      <div className="flex items-center justify-between px-6 pt-4">
        <Breadcrumb ctx={ctx} id={selectedId} />
        <button onClick={() => select(null)} aria-label="Chiudi" className="grid h-8 w-8 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 pt-2 pb-6">{body}</div>
    </Card>
  )
}

function findItem(layout: LayoutItem[], id: string): LayoutItem | undefined {
  return layout.find((i) => i.id === id)
}

function Breadcrumb({ ctx, id }: { ctx: Ctx; id: string }) {
  const select = useApp((s) => s.select)
  const item = ctx.data.layout.find((i) => i.id === id)
  const room = item?.room ?? (id.startsWith('room:') ? id.slice(5) : undefined)
  let island = item?.island ?? (id.startsWith('loc:') ? id.slice(4) : undefined)
  // Un server spostato da una misura appare nella sede nuova.
  const moved = item && statusOf(ctx, item).moved ? statusOf(ctx, item).entity?.location : undefined
  if (moved) island = Object.entries(ISLAND_LOCATION).find(([, l]) => l === moved)?.[0] ?? island
  const loc = island ? ctx.data.summary.locations.find((l) => l.id === ISLAND_LOCATION[island]) : undefined
  return (
    <div className="flex items-center gap-1.5 text-[13px] text-muted">
      <span>Basilea</span>
      {room && DEPT_LABEL[room] && (
        <>
          <span>›</span>
          <button onClick={() => select(`room:${room}`)} className="font-medium text-ink hover:underline">
            {DEPT_LABEL[room]}
          </button>
        </>
      )}
      {loc && (
        <>
          <span>›</span>
          <button onClick={() => select(`loc:${island}`)} className="font-medium text-ink hover:underline">
            {loc.label}
          </button>
        </>
      )}
    </div>
  )
}

const VISUAL: Record<Visual, { label: string; tone: Tone }> = {
  ok: { label: 'In uso', tone: 'primary' },
  driver: { label: 'Grande consumo', tone: 'neutral' },
  idle: { label: 'Informativo', tone: 'neutral' },
  waste: { label: 'Spreco', tone: 'warn' },
  reduced: { label: 'Ridotto da una misura', tone: 'primary' },
  off: { label: 'Spento da una misura', tone: 'primary' },
  removed: { label: 'Tolto da una misura', tone: 'primary' },
  locked: { label: 'Protetto', tone: 'lock' },
  human: { label: 'Decide una persona', tone: 'human' },
  contradiction: { label: 'Dati in conflitto', tone: 'warn' },
}

// --- Oggetto ---------------------------------------------------------------------------------------------

function ItemDetail({ ctx, item }: { ctx: Ctx; item: LayoutItem }) {
  const metric = useApp((s) => s.metric)
  const st = statusOf(ctx, item)
  const label = labelOf(ctx, item)
  const eff = st.entity
  const e = eff?.entity
  const info = st.info
  const loc = eff ? ctx.data.summary.locations.find((l) => l.id === eff.location) : undefined
  const findings = e ? ctx.data.findings.filter((f) => f.entity_id === e.id) : []
  const winEntities = WINDOW_ENTITY[item.id] ?? []
  const limits = ctx.data.limits.filter((l) => (e && l.entity_id === e.id) || (winEntities.includes(l.entity_id) && l.type === 'window'))
  const measures = ctx.data.measures.filter((m) =>
    m.effects.some((x) => (e && x.entity_id === e.id) || (x.entity_id === 'seats' && (item.id.startsWith('seat:') || item.id.startsWith('lic:'))) || winEntities.includes(x.entity_id)),
  )
  const v = VISUAL[st.visual]

  return (
    <>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Chip tone={v.tone}>{v.label}</Chip>
        {st.moved && <Chip tone="primary">spostato a {loc?.label}</Chip>}
        {item.representedCount && <Chip>rappresenta {item.representedCount} macchine</Chip>}
      </div>
      <h2 className="mt-2 text-[22px] leading-tight font-medium tracking-[-0.44px]">{label}</h2>
      <p className="mt-1 text-[14px] text-muted">
        {[e?.tool, loc && `${loc.label} · rete ${loc.grid_kg_per_kwh.mid} kg CO₂/kWh`].filter(Boolean).join(' · ')}
      </p>

      <SeatLine ctx={ctx} item={item} />
      {info && (
        <>
          <p className="mt-4 text-[16px] leading-snug text-ink">{info.headline}</p>
          <div className="mt-2 divide-y divide-hairline-soft">
            {info.facts.map((f) => (
              <Row key={f.label} label={f.label} value={f.value} />
            ))}
          </div>
          <p className="mt-1 text-[12px] text-muted">Fonte: {info.source}</p>
        </>
      )}

      {eff && e && (
        <>
          <Divider />
          {info && <Kicker>Fa parte di · {e.label}</Kicker>}
          <div className="mt-2 text-[40px] leading-none font-semibold tracking-[-1px] tabular-nums">{fmtMetric(eff.metrics[metric], metric)}</div>
          <div className="mt-1 text-[13px] text-muted">
            {METRIC_LABEL[metric]} all’anno{eff.reduction > 0 && <> · prima {fmtMetric(e.metrics[metric], metric)}</>}
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {(['co2_kg', 'cost_chf', 'kwh'] as MetricKey[])
              .filter((k) => k !== metric)
              .map((k) => (
                <div key={k} className="rounded-[8px] bg-surface-soft px-3 py-2">
                  <div className="text-[11px] font-semibold text-muted">{METRIC_LABEL[k]}</div>
                  <div className="text-[14px] font-semibold tabular-nums">{fmtMetric(eff.metrics[k], k)}</div>
                </div>
              ))}
            {e.utilisation !== undefined && (
              <div className="rounded-[8px] bg-surface-soft px-3 py-2">
                <div className="text-[11px] font-semibold text-muted">Utilizzo</div>
                <div className="text-[14px] font-semibold tabular-nums">{Math.round(e.utilisation * 100)}%</div>
              </div>
            )}
          </div>
          {e.idle_ratio !== undefined && <IdleBar idle={e.idle_ratio} />}
          {e.note && <p className="mt-3 text-[14px] leading-snug text-body">{e.note}</p>}
        </>
      )}

      {findings.length > 0 && (
        <Section title="Scoperte">
          {findings.map((f) => (
            <div key={f.id} className="rounded-[14px] bg-warn-soft p-3.5">
              <div className="text-[14px] font-semibold text-ink">🔎 {f.title}</div>
              <div className="mt-0.5 text-[13px] text-body">{f.evidence}</div>
              <div className="mt-1 text-[12px] text-muted">{f.source}</div>
            </div>
          ))}
        </Section>
      )}

      {limits.length > 0 && (
        <Section title="Limiti">
          {limits.map((l) => (
            <div key={l.id} className={`rounded-[14px] p-3.5 ${l.type === 'block' ? 'bg-error-soft' : l.type === 'human' ? 'bg-human-soft' : l.type === 'contradiction' ? 'bg-warn-soft' : 'bg-lock-soft'}`}>
              <div className="text-[14px] font-semibold text-ink">
                {l.type === 'block' ? '🔒' : l.type === 'human' ? '👤' : l.type === 'contradiction' ? '⚠️' : '🕒'} {l.title}
              </div>
              <div className="mt-0.5 text-[13px] text-body">{l.text}</div>
              <div className="mt-1 text-[12px] text-muted">{l.source}</div>
            </div>
          ))}
        </Section>
      )}

      {measures.length > 0 && (
        <Section title="Misure su questo oggetto">
          <div className="-my-2 divide-y divide-hairline-soft">
            {measures.map((m) => (
              <MeasureRow key={m.id} m={m} />
            ))}
          </div>
        </Section>
      )}

      {e?.calc && <CalcBox calc={e.calc} />}
    </>
  )
}

/** Righe specifiche per postazioni e licenze (gruppo di reparto + stato del singolo posto). */
function SeatLine({ ctx, item }: { ctx: Ctx; item: LayoutItem }) {
  if (!item.id.startsWith('seat:') && !item.id.startsWith('lic:')) return null
  const group = ctx.info.get(groupId(item.id))
  const text = item.active
    ? 'Licenza usata negli ultimi 30 giorni.'
    : ctx.seatsHidden
      ? 'Licenza da disdire con la misura M6 (alla scadenza del contratto).'
      : 'Licenza pagata ma senza accessi negli ultimi 30 giorni.'
  const lic = ctx.data.layout.filter((l) => l.seatId === item.id && l.id.startsWith('lic:'))
  return (
    <div className="mt-4 rounded-[14px] border border-hairline p-4">
      <div className="text-[14px] font-semibold">{text}</div>
      {group && (
        <div className="mt-1 text-[13px] text-muted">
          {group.label} · {DEPT_LABEL[group.department ?? ''] ?? ''}: {group.headline}
        </div>
      )}
      {lic.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {lic.map((l) => (
            <Chip key={l.id} tone={l.active ? 'primary' : 'warn'}>
              {l.id.split(':')[1]} {l.active ? 'attiva' : 'inattiva'}
            </Chip>
          ))}
        </div>
      )}
    </div>
  )
}

function IdleBar({ idle }: { idle: number }) {
  return (
    <div className="mt-3">
      <div className="mb-1 flex justify-between text-[12px] text-muted">
        <span>Lavora {Math.round((1 - idle) * 24 * 10) / 10} h su 24</span>
        <span className="text-warn">inattivo {Math.round(idle * 100)}%</span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full">
        <div className="bg-primary" style={{ width: `${(1 - idle) * 100}%` }} />
        <div className="flex-1 bg-warn-soft" />
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6">
      <h3 className="mb-2 text-[16px] font-semibold">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function CalcBox({ calc }: { calc: Calc }) {
  return (
    <details className="group mt-6 rounded-[14px] border border-hairline p-4">
      <summary className="flex cursor-pointer list-none items-center justify-between text-[14px] font-semibold">
        🧮 Come è calcolato
        <span className="text-muted transition group-open:rotate-180">⌄</span>
      </summary>
      <div className="mt-2 rounded-[8px] bg-surface-soft px-3 py-2 font-mono text-[12px] text-ink">{calc.formula}</div>
      {calc.inputs && (
        <div className="mt-1 divide-y divide-hairline-soft">
          {Object.entries(calc.inputs).map(([k, v]) => (
            <Row key={k} label={k} value={typeof v === 'number' ? v.toLocaleString('de-CH') : v} />
          ))}
        </div>
      )}
      <div className="mt-2 text-[12px] text-muted">Fonti: {calc.sources.join(' · ')}</div>
    </details>
  )
}

// --- Stanza ----------------------------------------------------------------------------------------------

function RoomDetail({ ctx, room }: { ctx: Ctx; room: string }) {
  const metric = useApp((s) => s.metric)
  const select = useApp((s) => s.select)
  const dept = ctx.data.summary.departments.find((d) => d.id === room)
  const items = roomItems(ctx.data.layout, room)
  const seats = items.filter((i) => i.id.startsWith('seat:'))
  const lic = items.filter((i) => i.id.startsWith('lic:'))
  const reports = items.filter((i) => i.id.startsWith('pbi-'))
  const wasteReports = reports.filter((i) => ctx.info.get(i.id)?.state === 'waste')
  const objects = items.filter((i) => !/^(seat|lic|pbi|saas|ai-assistant|window):|^pbi-/.test(i.id))
  const saas = ctx.data.items.filter((i) => i.kind === 'saas' && i.department === room)
  if (!dept) return null
  return (
    <>
      <div className="mt-2 flex items-center gap-2">
        <span className="h-3 w-3 rounded-full" style={{ background: DEPT_ACCENT[room] }} />
        <Kicker>Reparto · {dept.fte} FTE</Kicker>
      </div>
      <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px]">{dept.label}</h2>
      <div className="mt-3 text-[40px] leading-none font-semibold tracking-[-1px] tabular-nums">{fmtMetric(dept.metrics[metric], metric)}</div>
      <div className="mt-1 text-[13px] text-muted">{METRIC_LABEL[metric]} all’anno attribuiti al reparto (chiave FTE per i costi condivisi)</div>

      <div className="mt-4 divide-y divide-hairline-soft">
        <Row label="Postazioni (Microsoft 365)" value={`${seats.filter((s) => s.active).length} / ${seats.length} usate`} />
        <Row label="Posti AI (Copilot, Claude, ChatGPT)" value={`${lic.filter((s) => s.active).length} / ${lic.length} attivi`} />
        <Row label="Report Power BI" value={`${reports.length}`} sub={wasteReports.length ? `${wasteReports.length} quasi mai aperti` : undefined} />
        <Row label="Contratti SaaS" value={`${saas.length}`} sub={`${saas.filter((s) => s.state === 'waste').length} sotto il 60% d’uso`} />
      </div>

      {objects.length > 0 && (
        <Section title="Risorse di questo reparto">
          <div className="-mx-2">
            {objects.map((o) => {
              const st = statusOf(ctx, o)
              return (
                <button key={o.id} onClick={() => select(o.id)} className="flex w-full items-center justify-between gap-3 rounded-[8px] px-2 py-2 text-left hover:bg-surface-soft">
                  <span className="min-w-0 truncate text-[14px]">{labelOf(ctx, o)}</span>
                  <Chip tone={VISUAL[st.visual].tone}>{st.entity ? fmtMetric(st.entity.metrics[metric], metric) : VISUAL[st.visual].label}</Chip>
                </button>
              )
            })}
          </div>
        </Section>
      )}

      {wasteReports.length > 0 && (
        <Section title="Report quasi mai aperti">
          <div className="-mx-2">
            {wasteReports.map((r) => (
              <button key={r.id} onClick={() => select(r.id)} className="flex w-full justify-between gap-3 rounded-[8px] px-2 py-1.5 text-left text-[13px] hover:bg-surface-soft">
                <span className="truncate">{labelOf(ctx, r)}</span>
                <span className="shrink-0 text-muted">{r.id}</span>
              </button>
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

// --- Sede (isola) ----------------------------------------------------------------------------------------

function LocationDetail({ ctx, island }: { ctx: Ctx; island: string }) {
  const metric = useApp((s) => s.metric)
  const select = useApp((s) => s.select)
  const locId = ISLAND_LOCATION[island]
  const l = ctx.data.summary.locations.find((x) => x.id === locId)
  const { now, base } = useMemo(() => locationTotals(ctx.data, ctx.active), [ctx])
  if (!l) return null
  const here = [...ctx.entities.values()].filter((e) => e.location === locId)
  return (
    <>
      <Kicker>Data center · {island === 'eu-mixed' ? 'fornitori AI e SaaS' : 'cloud'}</Kicker>
      <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px]">{l.label}</h2>
      <div className="mt-3 text-[40px] leading-none font-semibold tracking-[-1px] tabular-nums">{fmtMetric(now[locId][metric], metric)}</div>
      <div className="mt-1 text-[13px] text-muted">
        {METRIC_LABEL[metric]} all’anno{now[locId][metric] !== base[locId][metric] && <> · prima {fmtMetric(base[locId][metric], metric)}</>}
      </div>
      <div className="mt-4 divide-y divide-hairline-soft">
        <Row
          label="Intensità della rete"
          value={`${l.grid_kg_per_kwh.mid} kg CO₂/kWh`}
          sub={`intervallo ${l.grid_kg_per_kwh.low}–${l.grid_kg_per_kwh.high}${l.grid_alt_kg_per_kwh ? ` · mix di produzione ${l.grid_alt_kg_per_kwh.mid}` : ''}`}
        />
        <Row label="Fonte" value={<span className="font-normal">{l.source}</span>} />
      </div>
      <Section title="Cosa gira qui">
        <div className="-mx-2">
          {here
            .sort((a, b) => b.metrics[metric] - a.metrics[metric])
            .map((x) => (
              <button
                key={x.entity.id}
                onClick={() => {
                  const id = sceneIdFor(ctx, ctx.data.layout, x.entity.id)
                  const island = ctx.data.layout.find((i) => i.view === 'island' && resourceOf(i) === id)
                  select(island?.id ?? id)
                }}
                className="flex w-full justify-between gap-3 rounded-[8px] px-2 py-2 text-left hover:bg-surface-soft"
              >
                <span className="truncate text-[14px]">
                  {x.entity.label}
                  {x.moved && <span className="text-primary"> · arrivato con una misura</span>}
                </span>
                <span className="shrink-0 text-[14px] font-semibold tabular-nums">{fmtMetric(x.metrics[metric], metric)}</span>
              </button>
            ))}
        </div>
      </Section>
    </>
  )
}

// --- Coda di approvazione (bonus B5) ---------------------------------------------------------------------

function ApprovalQueue() {
  const data = useApp((s) => s.data)!
  const decisions = useApp((s) => s.decisions)
  const decide = useApp((s) => s.decide)
  const active = useApp((s) => s.active)
  const toggle = useApp((s) => s.toggleMeasure)
  const human = data.measures.filter((m) => m.status === 'human')
  return (
    <>
      <Kicker>Management · scrivania delle approvazioni</Kicker>
      <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px]">Da decidere</h2>
      <p className="mt-2 text-[14px] text-body">Il sistema prepara la proposta con i numeri; la decisione resta a chi è responsabile.</p>
      <div className="mt-4 space-y-3">
        {human.map((m) => {
          const d = decisions[m.id]
          return (
            <div key={m.id} className="rounded-[14px] border border-hairline p-4">
              <div className="flex items-start justify-between gap-2">
                <span className="text-[15px] leading-snug font-semibold">{m.title}</span>
                <Chip tone="human">👤 {m.owner_role}</Chip>
              </div>
              <p className="mt-1.5 text-[13px] text-body">{m.reason}</p>
              <div className="mt-2 text-[12px] text-muted tabular-nums">
                −{fmtMetric(m.savings.co2_kg, 'co2_kg')} · −{fmtMetric(m.savings.cost_chf, 'cost_chf')} · {m.effort_days} gg
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => {
                    decide(m.id, d === 'approved' ? null : 'approved')
                    if (d !== 'approved' && !active.includes(m.id)) toggle(m.id)
                  }}
                  className={`flex-1 rounded-[8px] py-2 text-[14px] font-medium ${d === 'approved' ? 'bg-primary text-white' : 'bg-primary-soft text-primary hover:bg-primary hover:text-white'}`}
                >
                  {d === 'approved' ? '✓ Approvata' : 'Approva'}
                </button>
                <button
                  onClick={() => decide(m.id, d === 'rejected' ? null : 'rejected')}
                  className={`flex-1 rounded-[8px] border py-2 text-[14px] font-medium ${d === 'rejected' ? 'border-error bg-error-soft text-error' : 'border-hairline text-ink hover:border-ink'}`}
                >
                  {d === 'rejected' ? 'Respinta' : 'Respingi'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}
