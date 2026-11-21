import { useState } from 'react'
import { fmtMetric } from '../data/compute'
import { DEPT_LABEL, type Ctx } from '../data/twin'
import type { Entity, MetricKey, Metrics } from '../data/types'
import { Chip, type Tone } from './primitives'

/** Un servizio usato dai computer di un reparto. */
export interface Service {
  key: string
  name: string
  what: string
  /** Totale del reparto e quota di un computer. */
  dept: Metrics
  unit: Metrics
  basis: string
  status?: { label: string; tone: Tone }
  sources: string[]
}

const AI_SEAT = ['Microsoft Copilot', 'Claude Team', 'ChatGPT Team']

/** Cosa fa ogni servizio, in una riga. */
const WHAT: Record<string, string> = {
  'Microsoft 365': 'Mail, Teams, Office and file storage, one seat per person.',
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

/**
 * Tutti i servizi usati dai computer di un reparto. I dati sono per reparto, non per persona:
 * ogni computer dello stesso reparto ha gli stessi servizi; cambia solo se il posto Microsoft 365 è attivo.
 */
export function servicesOf(ctx: Ctx, room: string) {
  const dept = DEPT_LABEL[room] ?? room
  const seats = ctx.data.layout.filter((i) => i.id.startsWith(`seat:${room}:`))
  const n = seats.length || 1
  const active = seats.filter((s) => s.active).length
  const ents = [...ctx.entities.values()].map((x) => x.entity)
  const sources = (e: Entity) => e.calc?.sources ?? []
  const lic = ents.filter((e) => e.id.startsWith('lic:') && e.department === room && e.tool)

  const seatRow = (e: Entity): Service => {
    const use = e.seats ? e.seats.active / Math.max(1, e.seats.purchased) : 1
    return {
      key: e.id,
      name: e.tool,
      what: WHAT[e.tool] ?? 'Software bought per seat.',
      dept: e.metrics,
      unit: scale(e.metrics, 1 / n),
      basis: e.seats ? `${e.seats.purchased} seats paid, ${e.seats.active} used in the last 30 days.` : 'Paid per seat.',
      status: use < 0.6 ? { label: `Only ${pct(use)} of seats used`, tone: 'warn' } : undefined,
      sources: sources(e),
    }
  }
  const personal = lic.filter((e) => e.tool === 'Microsoft 365' || AI_SEAT.includes(e.tool)).map(seatRow)
  const software = lic.filter((e) => e.tool !== 'Microsoft 365' && !AI_SEAT.includes(e.tool)).map(seatRow)
  const ai: Service[] = ents
    .filter((e) => e.id.startsWith('ai-') && (e.department === room || e.allocation?.some((a) => a.department === room)))
    .map((e) => {
      const share = e.allocation ? (e.allocation.find((a) => a.department === room)?.share ?? 0) : 1
      return {
        key: e.id,
        name: e.label,
        what: WHAT[e.id] ?? 'AI application used through an API.',
        dept: scale(e.metrics, share),
        unit: scale(e.metrics, share / n),
        basis: e.allocation ? `Shared by ${e.allocation.length} departments; ${dept} pays ${pct(share)}, by usage.` : `Used by ${dept} only.`,
        sources: sources(e),
      }
    })
  const byCost = (a: Service, b: Service) => b.dept.cost_chf - a.dept.cost_chf
  software.sort(byCost)
  ai.sort(byCost)
  const total = [...personal, ...software, ...ai].reduce((t, s) => add(t, s.dept), { cost_chf: 0, kwh: 0, co2_kg: 0 })
  return { personal, software, ai, total, n, active, dept }
}

const METRICS: { key: MetricKey; label: string }[] = [
  { key: 'cost_chf', label: 'Cost' },
  { key: 'kwh', label: 'Energy' },
  { key: 'co2_kg', label: 'CO₂' },
]

/** Scheda dei computer di un reparto (tutti insieme): totale del reparto, quota di un computer e i servizi, chiusi e apribili. */
export function ComputersBody({ ctx, room }: { ctx: Ctx; room: string }) {
  const { personal, software, ai, total, n, active, dept } = servicesOf(ctx, room)
  return (
    <>
      <div className="flex flex-wrap gap-2">
        <BigTag tone="primary">{active} in use</BigTag>
        {n - active > 0 && <BigTag tone="warn">{n - active} without sign-in for 30 days</BigTag>}
        <BigTag tone="neutral">{personal.length + software.length + ai.length} services</BigTag>
      </div>

      <section className="mt-5">
        <h3 className="text-[16px] font-semibold text-ink">{dept} computers, per year</h3>
        <MetricGrid m={total} />
        <p className="mt-1.5 text-[13px] text-muted">
          One computer: {fmtMetric(total.cost_chf / n, 'cost_chf')} · {fmtMetric(total.kwh / n, 'kwh')} · {fmtMetric(total.co2_kg / n, 'co2_kg')}
        </p>
      </section>

      <Group title="Licences per person" items={personal} />
      <Group title={`${dept} software`} items={software} />
      <Group title="AI applications" items={ai} />
    </>
  )
}

const BIG_TONE: Record<'primary' | 'warn' | 'neutral', string> = {
  primary: 'bg-primary-soft text-primary',
  warn: 'bg-warn-soft text-warn',
  neutral: 'bg-surface-strong text-ink',
}

function BigTag({ tone, children }: { tone: keyof typeof BIG_TONE; children: React.ReactNode }) {
  return <span className={`rounded-full px-3 py-1.5 text-[14px] font-semibold ${BIG_TONE[tone]}`}>{children}</span>
}

/** Segnale di spreco: lo stesso «!» rosso dei punti critici nei passi successivi. */
function WastePin({ title }: { title: string }) {
  return (
    <span title={title} className="grid h-4.5 w-4.5 shrink-0 place-items-center rounded-full bg-error text-[11px] leading-none font-bold text-white">
      !
    </span>
  )
}

export function MetricGrid({ m, small }: { m: Metrics; small?: boolean }) {
  return (
    <div className="mt-2 grid grid-cols-3 gap-2">
      {METRICS.map((x) => (
        <div key={x.key} className={`rounded-[8px] bg-surface-soft ${small ? 'px-2.5 py-1.5' : 'px-3 py-2.5'}`}>
          <div className={`${small ? 'text-[11px]' : 'text-[12px]'} font-medium text-muted`}>{x.label}</div>
          <div className={`${small ? 'text-[13px]' : 'text-[16px]'} font-semibold text-ink tabular-nums`}>{fmtMetric(m[x.key], x.key)}</div>
        </div>
      ))}
    </div>
  )
}

function Group({ title, items }: { title: string; items: Service[] }) {
  if (!items.length) return null
  return (
    <section className="mt-6">
      <h3 className="mb-1 flex items-baseline justify-between text-[14px] font-semibold text-ink">
        {title}
        <span className="text-[12px] font-normal text-muted">department · per year</span>
      </h3>
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
          {s.status?.tone === 'warn' && <WastePin title={s.status.label} />}
        </span>
        <span className="shrink-0 text-[14px] font-semibold text-ink tabular-nums">{fmtMetric(s.dept.cost_chf, 'cost_chf')}</span>
      </button>
      {open && (
        <div className="pb-3 pl-5.5 text-[13px] text-body">
          <MetricGrid m={s.dept} small />
          <p className="mt-2 text-[12px] text-muted">{s.basis}</p>
          {s.status && (
            <div className="mt-2">
              <Chip tone={s.status.tone}>{s.status.label}</Chip>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
