import { useMemo } from 'react'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'
import { DEPT_ACCENT, DEPT_LABEL, labelOf, makeCtx, resourceOf, statusOf, type Ctx, type Visual } from '../data/twin'
import type { Calc, Entity, LayoutItem, MetricKey, Metrics } from '../data/types'
import { PANEL_W } from '../scene/Scene'
import { Chip, Row, type Tone } from './primitives'

/** Scheda a destra: cosa consuma l'oggetto cliccato (soldi, energia, CO₂ e ore di utilizzo) e come è calcolato. */
export function ItemPanel() {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const selectedId = useApp((s) => s.selectedId)
  const select = useApp((s) => s.select)
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const item = selectedId ? data.layout.find((i) => i.id === selectedId) : undefined
  if (!room || !item) return null

  return (
    <aside
      className="pill-shadow pointer-events-auto absolute top-6 right-6 bottom-6 flex flex-col overflow-hidden rounded-[14px] bg-white"
      style={{ width: PANEL_W }}
    >
      <div className="flex items-start justify-between gap-4 px-6 pt-6">
        <div className="min-w-0">
          <div className="text-[13px] text-muted">
            {DEPT_LABEL[item.room ?? ''] ?? ''} · {kindOf(item)}
          </div>
          <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px] text-ink">{labelOf(ctx, item)}</h2>
        </div>
        <button onClick={() => select(null)} aria-label="Close" className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 pt-3 pb-6">
        <Body ctx={ctx} item={item} />
      </div>
    </aside>
  )
}

function kindOf(item: LayoutItem): string {
  const id = item.id
  if (id.startsWith('seat:')) return 'Workstation · Microsoft 365 licence'
  if (id.startsWith('lic:')) return 'AI subscription seat'
  if (id.startsWith('pbi-')) return 'Power BI report'
  if (id.startsWith('saas:')) return 'SaaS contract'
  if (id.startsWith('ai-')) return 'AI application'
  if (id.startsWith('agent:')) return 'AI agent'
  if (id.startsWith('window:')) return 'Protected window'
  if (id === 'handover:queue') return 'Approval desk'
  return 'Cloud resource owned by this department'
}

/** «Spreco» detto in modo diverso per tipo di oggetto. */
function wasteLabel(item: LayoutItem): string {
  const id = item.id
  if (/^(seat:|lic:|saas:|pbi-)/.test(id)) return 'Paid but barely used'
  if (/^(ai-|agent:)/.test(id)) return 'Oversized for the task'
  return 'Mostly idle'
}

const STATE: Record<Visual, { label: string; tone: Tone }> = {
  ok: { label: 'In use', tone: 'primary' },
  driver: { label: 'In use', tone: 'primary' },
  idle: { label: 'Info', tone: 'neutral' },
  waste: { label: 'Paid but barely used', tone: 'warn' },
  reduced: { label: 'Reduced', tone: 'primary' },
  off: { label: 'Off', tone: 'neutral' },
  removed: { label: 'Removed', tone: 'neutral' },
  locked: { label: 'Protected', tone: 'lock' },
  human: { label: 'Needs a decision', tone: 'human' },
  contradiction: { label: 'Sources disagree', tone: 'warn' },
}

const METRICS: { key: MetricKey; label: string }[] = [
  { key: 'cost_chf', label: 'Cost' },
  { key: 'kwh', label: 'Energy' },
  { key: 'co2_kg', label: 'CO₂' },
]

/** Le ore di utilizzo stanno negli input del calcolo (node-hours, vCPU-hours, GPU-hours…). */
function usageHours(calc?: Calc): { label: string; value: number } | null {
  if (!calc?.inputs) return null
  const hit = Object.entries(calc.inputs).find(([k, v]) => /hours|\((h|node-h|GPU-h|vCPU-h)\)$/i.test(k) && typeof v === 'number')
  return hit ? { label: hit[0], value: hit[1] as number } : null
}

function Body({ ctx, item }: { ctx: Ctx; item: LayoutItem }) {
  const st = statusOf(ctx, item)
  const eff = st.entity
  const e = eff?.entity
  const info = st.info
  const loc = eff ? ctx.data.summary.locations.find((l) => l.id === eff.location) : undefined
  const hours = usageHours(e?.calc)
  // Un oggetto rappresenta tutta la risorsa (es. dp-prod) oppure è una parte di un gruppo (es. un report della capacità Power BI).
  const whole = e && (e.id === resourceOf(item) || e.scene_ids?.includes(resourceOf(item)))

  return (
    <>
      <div className="flex flex-wrap gap-1.5">
        <Chip tone={STATE[st.visual].tone}>{st.visual === 'waste' ? wasteLabel(item) : STATE[st.visual].label}</Chip>
        {e?.allocation && <Chip tone="human">Shared resource</Chip>}
        {loc && <Chip>{loc.id === 'EU' ? 'Provider · location not stated' : `Runs in ${loc.label}`}</Chip>}
      </div>

      <SeatInfo ctx={ctx} item={item} />

      {info && (
        <section className="mt-5">
          <p className="text-[16px] leading-snug text-ink">{info.headline}</p>
          <div className="mt-1 divide-y divide-hairline-soft">
            {info.facts.map((f) => (
              <Row key={f.label} label={f.label} value={f.value} />
            ))}
          </div>
          <p className="mt-1 text-[12px] text-muted">Source: {info.source}</p>
        </section>
      )}

      {eff && e?.allocation && <SharedSplit allocation={e.allocation} room={item.room ?? ''} metrics={eff.metrics} />}

      {eff && e && (
        <section className="mt-6">
          <h3 className="text-[16px] font-semibold text-ink">
            {e.allocation ? `Whole resource · ${e.label}` : whole ? 'Consumption per year' : `Part of · ${e.label}`}
          </h3>
          {e.allocation && <p className="mt-0.5 text-[13px] text-muted">Per year, all departments together.</p>}
          {!whole && !e.allocation && <p className="mt-0.5 text-[13px] text-muted">Totals of the whole resource, shared by all its objects.</p>}
          <div className="mt-3 grid grid-cols-3 gap-2">
            {METRICS.map((m) => (
              <div key={m.key} className="rounded-[8px] bg-surface-soft px-3 py-2.5">
                <div className="text-[12px] font-medium text-muted">{m.label}</div>
                <div className="text-[16px] font-semibold text-ink tabular-nums">{fmtMetric(eff.metrics[m.key], m.key)}</div>
              </div>
            ))}
          </div>
          {e.hours && (
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div className="rounded-[8px] bg-surface-soft px-3 py-2.5">
                <div className="text-[12px] font-medium text-muted">Running</div>
                <div className="text-[16px] font-semibold text-ink tabular-nums">{Math.round(e.hours.runtime).toLocaleString('en-US')} h</div>
              </div>
              <div className="rounded-[8px] bg-surface-soft px-3 py-2.5">
                <div className="text-[12px] font-medium text-muted">Actually working</div>
                <div className="text-[16px] font-semibold text-ink tabular-nums">{Math.round(e.hours.active).toLocaleString('en-US')} h</div>
              </div>
            </div>
          )}
          {!e.hours && hours && (
            <div className="mt-2 rounded-[8px] bg-surface-soft px-3 py-2.5">
              <div className="text-[12px] font-medium text-muted">Usage</div>
              <div className="text-[16px] font-semibold text-ink tabular-nums">
                {hours.value.toLocaleString('en-US')} {hours.label}
              </div>
            </div>
          )}
          {e.idle_ratio !== undefined && <IdleBar idle={e.idle_ratio} />}
          {e.utilisation !== undefined && e.idle_ratio === undefined && (
            <p className="mt-3 text-[14px] text-body">Average utilisation {Math.round(e.utilisation * 100)}%</p>
          )}
          {e.note && <p className="mt-3 text-[14px] leading-snug text-body">{e.note}</p>}
          {loc && (
            <div className="mt-3 divide-y divide-hairline-soft">
              <Row label="Data centre" value={loc.id === 'EU' ? 'Not stated (AI & SaaS providers)' : loc.label} />
              <Row label="Grid intensity" value={`${loc.grid_kg_per_kwh.mid} kg CO₂/kWh`} sub={`range ${loc.grid_kg_per_kwh.low}–${loc.grid_kg_per_kwh.high}`} />
            </div>
          )}
          {e.calc && <CalcBox calc={e.calc} />}
        </section>
      )}

      {!eff && !info && (
        <p className="mt-5 text-[14px] text-body">No consumption data is linked to this object yet.</p>
      )}
    </>
  )
}

const KEY_LABEL: Record<string, string> = { row_tag: 'by usage', cost_center: 'by cost centre', mapping: 'by owner', fte: 'by headcount (FTE)' }

/** Risorsa condivisa: quota di questo reparto + barra con tutti i reparti e la chiave di ripartizione. */
function SharedSplit({ allocation, room, metrics }: { allocation: NonNullable<Entity['allocation']>; room: string; metrics: Metrics }) {
  const mine = allocation.find((a) => a.department === room)
  const keys = [...new Set(allocation.map((a) => KEY_LABEL[a.key]))]
  return (
    <section className="mt-6">
      <h3 className="text-[16px] font-semibold text-ink">Share of {DEPT_LABEL[room] ?? room}</h3>
      <p className="mt-0.5 text-[13px] text-muted">
        Used by {allocation.length} departments. Who uses it pays: split {keys.join(' and ')}.
      </p>
      {mine && (
        <div className="mt-3 grid grid-cols-3 gap-2">
          {METRICS.map((m) => (
            <div key={m.key} className="rounded-[8px] bg-primary-soft px-3 py-2.5">
              <div className="text-[12px] font-medium text-primary">{m.label}</div>
              <div className="text-[16px] font-semibold text-ink tabular-nums">{fmtMetric(metrics[m.key] * mine.share, m.key)}</div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-4 flex h-3 overflow-hidden rounded-full">
        {allocation.map((a) => (
          <div
            key={a.department}
            title={`${DEPT_LABEL[a.department] ?? a.department} ${Math.round(a.share * 100)}%`}
            style={{ width: `${a.share * 100}%`, background: DEPT_ACCENT[a.department] ?? '#ccc', opacity: !mine || a.department === room ? 1 : 0.35 }}
          />
        ))}
      </div>
      <ul className="mt-2 divide-y divide-hairline-soft">
        {allocation.map((a) => (
          <li key={a.department} className={`flex items-center justify-between py-1.5 text-[13px] ${a.department === room ? 'font-semibold text-ink' : 'text-body'}`}>
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: DEPT_ACCENT[a.department] ?? '#ccc' }} />
              {DEPT_LABEL[a.department] ?? a.department}
            </span>
            <span className="tabular-nums">
              {Math.round(a.share * 1000) / 10}% <span className="font-normal text-muted">· {KEY_LABEL[a.key]}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Postazioni e posti AI: stato del singolo posto + dati del gruppo del reparto. */
function SeatInfo({ ctx, item }: { ctx: Ctx; item: LayoutItem }) {
  if (!item.id.startsWith('seat:') && !item.id.startsWith('lic:')) return null
  const seat = item.id.startsWith('seat:')
  const text = item.active
    ? `${seat ? 'Microsoft 365 licence' : 'Seat'} used in the last 30 days.`
    : `${seat ? 'Microsoft 365 licence' : 'Seat'} paid, but no sign-in in the last 30 days.`
  const ai = seat ? ctx.data.layout.filter((l) => l.seatId === item.id && l.id.startsWith('lic:')) : []
  return (
    <section className="mt-5 rounded-[14px] border border-hairline p-4">
      <p className="text-[15px] font-semibold text-ink">{text}</p>
      {ai.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {ai.map((l) => (
            <Chip key={l.id} tone={l.active ? 'primary' : 'warn'}>
              {labelOf(ctx, l).split(' · ')[0]} · {l.active ? 'active' : 'inactive'}
            </Chip>
          ))}
        </div>
      )}
    </section>
  )
}

function IdleBar({ idle }: { idle: number }) {
  const h = Math.round((1 - idle) * 24 * 10) / 10
  return (
    <div className="mt-3">
      <div className="mb-1 flex justify-between text-[13px]">
        <span className="text-body">Works {h} h of 24</span>
        <span className="text-warn">idle {Math.round(idle * 100)}%</span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full">
        <div className="bg-primary" style={{ width: `${(1 - idle) * 100}%` }} />
        <div className="flex-1 bg-warn-soft" />
      </div>
    </div>
  )
}

function CalcBox({ calc }: { calc: Calc }) {
  return (
    <details className="group mt-5 rounded-[14px] border border-hairline p-4">
      <summary className="flex cursor-pointer list-none items-center justify-between text-[14px] font-semibold text-ink">
        How it is calculated
        <svg viewBox="0 0 24 24" className="h-4 w-4 text-muted transition group-open:rotate-180" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </summary>
      <div className="mt-3 rounded-[8px] bg-surface-soft px-3 py-2 font-mono text-[12px] text-ink">{calc.formula}</div>
      {calc.inputs && (
        <div className="mt-1 divide-y divide-hairline-soft">
          {Object.entries(calc.inputs).map(([k, v]) => (
            <Row key={k} label={k} value={typeof v === 'number' ? v.toLocaleString('en-US') : v} />
          ))}
        </div>
      )}
      <p className="mt-2 text-[12px] text-muted">Sources: {calc.sources.join(' · ')}</p>
    </details>
  )
}
