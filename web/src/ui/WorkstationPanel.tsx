import { useState } from 'react'
import { fmtMetric } from '../data/compute'
import { DEPT_LABEL, type Ctx } from '../data/twin'
import type { Entity, LayoutItem, MetricKey, Metrics } from '../data/types'
import { Chip, type Tone } from './primitives'

/** Una riga della scheda del computer: un servizio usato da questa postazione. */
interface Service {
  key: string
  name: string
  what: string
  unit: Metrics
  deptTotal: Metrics
  basis: string
  status?: { label: string; tone: Tone }
  sources: string[]
}

const AI_SEAT: Record<string, string> = { copilot: 'Microsoft Copilot', claude: 'Claude Team', chatgpt: 'ChatGPT Team' }

/** Cosa fa ogni servizio, in una riga. */
const WHAT: Record<string, string> = {
  'Microsoft 365': 'Mail, Teams, Office and file storage for one person.',
  'Microsoft Copilot': 'AI assistant inside Microsoft 365, one seat per person.',
  'Claude Team': 'AI chat subscription (Anthropic), one seat per person.',
  'ChatGPT Team': 'AI chat subscription (OpenAI), one seat per person.',
  'Accounting software': 'Bookkeeping and invoicing.',
  'CRM platform': 'Customers, contacts and sales pipeline.',
  'Chat tool': 'Team chat.',
  'Design tool': 'Graphics and layouts.',
  'E-signature': 'Signing contracts online.',
  'HR software': 'Payroll, absences and recruiting.',
  'Note-taking tool': 'Shared notes.',
  'Password manager': 'Shared passwords and logins.',
  'Project scheduling': 'Planning people and project time.',
  'Project management': 'Tasks and project tracking.',
  'Ticket system': 'Support and IT tickets.',
  'Survey tool': 'Customer and staff surveys.',
  'Video conferencing tool': 'Video calls and webinars.',
  'Knowledge base': 'Internal documentation.',
  'Time tracking': 'Hours per project.',
  'ai-assistant': 'Office AI assistant: summaries, translations and questions, through an API.',
  'ai-chatbot': 'Chatbot that answers from internal documents.',
  'ai-marketing': 'Classifies customer texts in large batches.',
  'ai-quote': 'Drafts sales quotes.',
  'ai-agent': 'Support agent: works on tickets on its own.',
  'ai-agent2': 'Sales, research and code agents.',
  'ai-report': 'Agent that writes recurring reports.',
}

const scale = (m: Metrics, f: number): Metrics => ({ cost_chf: m.cost_chf * f, kwh: m.kwh * f, co2_kg: m.co2_kg * f })
const add = (a: Metrics, b: Metrics): Metrics => ({
  cost_chf: a.cost_chf + (Number.isFinite(b.cost_chf) ? b.cost_chf : 0),
  kwh: a.kwh + (Number.isFinite(b.kwh) ? b.kwh : 0),
  co2_kg: a.co2_kg + (Number.isFinite(b.co2_kg) ? b.co2_kg : 0),
})
const pct = (x: number) => `${Math.round(x * 100)}%`

/** Tutti i servizi di una postazione: licenze personali (esatte) + software e AI del reparto (divisi per i computer). */
function servicesOf(ctx: Ctx, seat: LayoutItem) {
  const room = seat.room ?? ''
  const dept = DEPT_LABEL[room] ?? room
  const n = ctx.data.layout.filter((i) => i.id.startsWith(`seat:${room}:`)).length || 1
  const ents = [...ctx.entities.values()].map((x) => x.entity)
  const lic = (tool: string) => ents.find((e) => e.id.startsWith('lic:') && e.tool === tool && e.department === room)
  const sources = (e: Entity) => e.calc?.sources ?? []

  const personal: Service[] = []
  const m365 = lic('Microsoft 365')
  if (m365?.seats) {
    personal.push({
      key: m365.id,
      name: 'Microsoft 365',
      what: WHAT['Microsoft 365'],
      unit: scale(m365.metrics, 1 / m365.seats.purchased),
      deptTotal: m365.metrics,
      basis: `This computer's own seat: 1 of ${m365.seats.purchased} in ${dept} (${m365.seats.active} active).`,
      status: seat.active ? { label: 'Active', tone: 'primary' } : { label: 'No sign-in for 30 days', tone: 'warn' },
      sources: sources(m365),
    })
  }
  for (const puck of ctx.data.layout.filter((l) => l.seatId === seat.id && l.id.startsWith('lic:'))) {
    const tool = AI_SEAT[puck.id.split(':')[1]]
    const e = tool ? lic(tool) : undefined
    if (!e?.seats) continue
    personal.push({
      key: puck.id,
      name: tool,
      what: WHAT[tool],
      unit: scale(e.metrics, 1 / e.seats.purchased),
      deptTotal: e.metrics,
      basis: `This computer's own seat: 1 of ${e.seats.purchased} in ${dept} (${e.seats.active} active).`,
      status: puck.active ? { label: 'Active', tone: 'primary' } : { label: 'Paid, not used', tone: 'warn' },
      sources: sources(e),
    })
  }

  const software: Service[] = ents
    .filter((e) => e.id.startsWith('lic:') && e.department === room && e.tool && !['Microsoft 365', ...Object.values(AI_SEAT)].includes(e.tool))
    .map((e) => {
      const use = e.seats ? e.seats.active / e.seats.purchased : 1
      return {
        key: e.id,
        name: e.tool,
        what: WHAT[e.tool] ?? 'Software bought per seat.',
        unit: scale(e.metrics, 1 / n),
        deptTotal: e.metrics,
        basis: `${dept} contract${e.seats ? ` (${e.seats.active} of ${e.seats.purchased} licences used)` : ''}, split across its ${n} computers.`,
        status: use < 0.6 ? { label: `Only ${pct(use)} of licences used`, tone: 'warn' as Tone } : undefined,
        sources: sources(e),
      }
    })
    .sort((a, b) => b.unit.cost_chf - a.unit.cost_chf)

  const ai: Service[] = ents
    .filter((e) => e.id.startsWith('ai-') && (e.department === room || e.allocation?.some((a) => a.department === room)))
    .map((e) => {
      const share = e.allocation ? (e.allocation.find((a) => a.department === room)?.share ?? 0) : 1
      return {
        key: e.id,
        name: e.label,
        what: WHAT[e.id] ?? 'AI application used through an API.',
        unit: scale(e.metrics, share / n),
        deptTotal: scale(e.metrics, share),
        basis: e.allocation
          ? `Shared by ${e.allocation.length} departments; ${dept} pays ${pct(share)} by usage, split across its ${n} computers.`
          : `Used by ${dept} only, split across its ${n} computers.`,
        sources: sources(e),
      }
    })
    .sort((a, b) => b.unit.cost_chf - a.unit.cost_chf)

  const all = [...personal, ...software, ...ai]
  const total = all.reduce((t, s) => add(t, s.unit), { cost_chf: 0, kwh: 0, co2_kg: 0 })
  return { personal, software, ai, total, n, dept }
}

const METRICS: { key: MetricKey; label: string }[] = [
  { key: 'cost_chf', label: 'Cost' },
  { key: 'kwh', label: 'Energy' },
  { key: 'co2_kg', label: 'CO₂' },
]

/** Scheda di un computer: totale della postazione e, sotto, ogni servizio chiuso e apribile. */
export function WorkstationBody({ ctx, seat }: { ctx: Ctx; seat: LayoutItem }) {
  const { personal, software, ai, total, n, dept } = servicesOf(ctx, seat)
  return (
    <>
      <div className="flex flex-wrap gap-1.5">
        {seat.active ? <Chip tone="primary">In use</Chip> : <Chip tone="warn">No sign-in for 30 days</Chip>}
        <Chip>{personal.length + software.length + ai.length} services</Chip>
      </div>

      <section className="mt-5">
        <h3 className="text-[16px] font-semibold text-ink">This computer, per year</h3>
        <div className="mt-2 grid grid-cols-3 gap-2">
          {METRICS.map((m) => (
            <div key={m.key} className="rounded-[8px] bg-surface-soft px-3 py-2.5">
              <div className="text-[12px] font-medium text-muted">{m.label}</div>
              <div className="text-[16px] font-semibold text-ink tabular-nums">{fmtMetric(total[m.key], m.key)}</div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[12px] leading-snug text-muted">
          Personal seats are exact. Department software and AI are split evenly across the {n} computers in {dept}: the data has no per-person usage.
        </p>
      </section>

      <Group title="Personal licences" items={personal} />
      <Group title={`${dept} software`} items={software} />
      <Group title="AI applications" items={ai} />
    </>
  )
}

function Group({ title, items }: { title: string; items: Service[] }) {
  if (!items.length) return null
  return (
    <section className="mt-6">
      <h3 className="mb-1 text-[14px] font-semibold text-ink">{title}</h3>
      <div className="divide-y divide-hairline-soft border-y border-hairline-soft">
        {items.map((s) => (
          <ServiceRow key={s.key} s={s} />
        ))}
      </div>
    </section>
  )
}

function ServiceRow({ s }: { s: Service }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-3 py-2.5 text-left">
        <span className="flex min-w-0 items-center gap-2">
          <svg viewBox="0 0 24 24" className={`h-3.5 w-3.5 shrink-0 text-muted transition ${open ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M9 6l6 6-6 6" />
          </svg>
          <span className="truncate text-[14px] text-ink">{s.name}</span>
          {s.status?.tone === 'warn' && <span className="h-2 w-2 shrink-0 rounded-full bg-warn" title={s.status.label} />}
        </span>
        <span className="shrink-0 text-[14px] font-semibold text-ink tabular-nums">{fmtMetric(s.unit.cost_chf, 'cost_chf')}</span>
      </button>
      {open && (
        <div className="pb-3 pl-5.5 text-[13px] text-body">
          <p>{s.what}</p>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            {METRICS.map((m) => (
              <div key={m.key} className="rounded-[8px] bg-surface-soft px-2.5 py-1.5">
                <div className="text-[11px] text-muted">{m.label}</div>
                <div className="text-[13px] font-semibold text-ink tabular-nums">{fmtMetric(s.unit[m.key], m.key)}</div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[12px] text-muted">{s.basis}</p>
          <p className="mt-0.5 text-[12px] text-muted">
            Department total: {fmtMetric(s.deptTotal.cost_chf, 'cost_chf')} · {fmtMetric(s.deptTotal.kwh, 'kwh')} · {fmtMetric(s.deptTotal.co2_kg, 'co2_kg')}
          </p>
          {s.status && (
            <div className="mt-2">
              <Chip tone={s.status.tone}>{s.status.label}</Chip>
            </div>
          )}
          {s.sources.length > 0 && <p className="mt-2 text-[11px] text-muted-soft">Sources: {s.sources.join(' · ')}</p>}
        </div>
      )}
    </div>
  )
}
