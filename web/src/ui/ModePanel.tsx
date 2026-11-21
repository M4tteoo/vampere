import { useMemo } from 'react'
import { useApp } from '../store'
import { fmtChf, fmtMetric, locationTotals, packageTotals } from '../data/compute'
import { DEPT_ACCENT, DEPT_LABEL, makeCtx, sceneIdFor } from '../data/twin'
import type { Limit, LocationId, Measure } from '../data/types'
import { Bar, Card, Chip, Kicker, Toggle } from './primitives'

/** Pannello sinistro: cambia contenuto secondo la fase scelta nella barra in alto. */
export function ModePanel() {
  const mode = useApp((s) => s.mode)
  return (
    <Card className="flex max-h-full w-[360px] flex-col overflow-hidden">
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-6">
        {mode === 'connect' && <ConnectPanel />}
        {mode === 'find' && <FindPanel />}
        {mode === 'decide' && <DecidePanel />}
        {mode === 'limits' && <LimitsPanel />}
      </div>
    </Card>
  )
}

/** Seleziona nella scena l'oggetto che rappresenta un'entità e ci porta la camera. */
function useFocus() {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  const select = useApp((s) => s.select)
  const ctx = useMemo(() => makeCtx(data, active), [data, active])
  return (entityId: string) => {
    const id = sceneIdFor(ctx, data.layout, entityId)
    if (id) select(id)
  }
}

// --- Connetti --------------------------------------------------------------------------------------------

const ISLAND_OF: Record<LocationId, string> = { CH: 'zurich', DE: 'frankfurt', IE: 'dublin', EU: 'eu-mixed' }

function ConnectPanel() {
  const data = useApp((s) => s.data)!
  const metric = useApp((s) => s.metric)
  const active = useApp((s) => s.active)
  const select = useApp((s) => s.select)
  const rows = data.quality.reduce((a, q) => a + q.rows, 0)
  const depts = [...data.summary.departments].sort((a, b) => b.metrics[metric] - a.metrics[metric])
  const maxD = depts[0]?.metrics[metric] ?? 1
  const { now } = locationTotals(data, active)
  const locs = data.summary.locations.map((l) => ({ ...l, v: now[l.id][metric] })).sort((a, b) => b.v - a.v)
  const maxL = locs[0]?.v ?? 1

  return (
    <>
      <Kicker>Connetti</Kicker>
      <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px]">28 file, un solo quadro</h2>
      <p className="mt-2 text-[14px] text-body">
        Fatture cloud, SaaS, AI, ticket e metriche armonizzati in un unico formato.{' '}
        <b className="font-semibold text-ink">{rows.toLocaleString('de-CH')}</b> righe sistemate dalla pipeline.
      </p>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {(['co2_kg', 'cost_chf', 'kwh'] as const).map((k) => (
          <div key={k} className={`rounded-[8px] px-3 py-2 ${k === metric ? 'bg-ink text-white' : 'bg-surface-soft'}`}>
            <div className={`text-[11px] font-semibold ${k === metric ? 'text-white/70' : 'text-muted'}`}>{k === 'co2_kg' ? 'CO₂ / anno' : k === 'cost_chf' ? 'Costi / anno' : 'Energia / anno'}</div>
            <div className="text-[15px] font-semibold tabular-nums">{fmtMetric(data.summary.baseline[k], k)}</div>
          </div>
        ))}
      </div>

      <h3 className="mt-6 mb-2 text-[16px] font-semibold">Per reparto</h3>
      {depts.map((d) => (
        <button key={d.id} onClick={() => select(`room:${d.id}`)} className="-mx-2 block w-[calc(100%+16px)] rounded-[8px] px-2 py-1.5 text-left hover:bg-surface-soft">
          <div className="mb-1 flex justify-between text-[14px]">
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: DEPT_ACCENT[d.id] }} />
              {d.label}
              <span className="text-[12px] text-muted">{d.fte} FTE</span>
            </span>
            <span className="font-semibold tabular-nums">{fmtMetric(d.metrics[metric], metric)}</span>
          </div>
          <Bar value={d.metrics[metric]} max={maxD} color="bg-ink" />
        </button>
      ))}

      <h3 className="mt-6 mb-2 text-[16px] font-semibold">Per sede (dove si consuma)</h3>
      {locs.map((l) => (
        <button
          key={l.id}
          onClick={() => l.id !== 'EU' && select(`loc:${ISLAND_OF[l.id]}`)}
          title={l.id === 'EU' ? 'AI e SaaS: i dati non dicono in quale data center girano' : undefined}
          className={`-mx-2 block w-[calc(100%+16px)] rounded-[8px] px-2 py-1.5 text-left ${l.id === 'EU' ? 'cursor-default' : 'hover:bg-surface-soft'}`}
        >
          <div className="mb-1 flex justify-between text-[14px]">
            <span>
              {l.label} <span className="text-[12px] text-muted">{l.grid_kg_per_kwh.mid} kg/kWh</span>
            </span>
            <span className="font-semibold tabular-nums">{fmtMetric(l.v, metric)}</span>
          </div>
          <Bar value={l.v} max={maxL} color="bg-primary" />
        </button>
      ))}

      <h3 className="mt-6 mb-1 text-[16px] font-semibold">Pulizia dei dati</h3>
      <ul className="divide-y divide-hairline-soft">
        {data.quality.map((q, i) => (
          <li key={i} className="py-2 text-[13px]">
            <div className="flex justify-between gap-3">
              <span className="font-medium text-ink">{q.issue}</span>
              {q.rows > 0 && <span className="shrink-0 text-muted tabular-nums">{q.rows.toLocaleString('de-CH')}</span>}
            </div>
            <div className="text-[12px] text-muted">
              {q.source_file} · {q.action}
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}

// --- Scopri ----------------------------------------------------------------------------------------------

const SEVERITY: Record<string, { label: string; tone: 'error' | 'warn' | 'neutral' }> = {
  high: { label: 'Alta', tone: 'error' },
  medium: { label: 'Media', tone: 'warn' },
  low: { label: 'Bassa', tone: 'neutral' },
}

function FindPanel() {
  const data = useApp((s) => s.data)!
  const metric = useApp((s) => s.metric)
  const select = useApp((s) => s.select)
  const focus = useFocus()
  const order = { high: 0, medium: 1, low: 2 }
  const findings = [...data.findings].sort((a, b) => order[a.severity] - order[b.severity])
  const drivers = [...data.entities].sort((a, b) => b.metrics[metric] - a.metrics[metric]).slice(0, 5)
  const wasteReports = data.items.filter((i) => i.kind === 'report' && i.state === 'waste')
  const wasteLic = data.items.filter((i) => (i.kind === 'licence' || i.kind === 'saas') && i.state === 'waste')

  return (
    <>
      <Kicker>Scopri</Kicker>
      <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px]">Dove va l’energia, e dove si spreca</h2>

      <h3 className="mt-5 mb-2 text-[16px] font-semibold">I 5 driver principali · {metric === 'co2_kg' ? 'CO₂' : metric === 'kwh' ? 'kWh' : 'CHF'}</h3>
      <ol className="space-y-1">
        {drivers.map((e, i) => (
          <li key={e.id}>
            <button onClick={() => focus(e.id)} className="-mx-2 flex w-[calc(100%+16px)] items-center gap-3 rounded-[8px] px-2 py-1.5 text-left hover:bg-surface-soft">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface-strong text-[12px] font-semibold">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate text-[14px]">{e.label}</span>
              <span className="text-[14px] font-semibold tabular-nums">{fmtMetric(e.metrics[metric], metric)}</span>
            </button>
          </li>
        ))}
      </ol>

      <h3 className="mt-6 mb-2 text-[16px] font-semibold">Scoperte</h3>
      <div className="space-y-2">
        {findings.map((f) => (
          <button key={f.id} onClick={() => focus(f.entity_id)} className="block w-full rounded-[14px] border border-hairline p-4 text-left transition hover:border-ink">
            <div className="flex items-start justify-between gap-2">
              <span className="text-[15px] leading-snug font-semibold">{f.title}</span>
              <Chip tone={SEVERITY[f.severity].tone}>{SEVERITY[f.severity].label}</Chip>
            </div>
            <p className="mt-1 text-[13px] text-body">{f.evidence}</p>
            <p className="mt-1.5 text-[12px] text-muted">{f.source}</p>
          </button>
        ))}
      </div>

      <h3 className="mt-6 mb-1 text-[16px] font-semibold">Piccoli sprechi, tanti oggetti</h3>
      <p className="mb-2 text-[13px] text-muted">Nella scena: schermi e luci color ambra.</p>
      <div className="grid grid-cols-2 gap-2">
        <Stat value={wasteLic.length} label="contratti e licenze sotto il 60% d’uso" />
        <Stat value={wasteReports.length} label="report Power BI aggiornati ma quasi mai aperti" />
      </div>
      <ul className="mt-3 divide-y divide-hairline-soft">
        {wasteLic.map((i) => (
          <li key={i.id}>
            <button
              onClick={() => {
                const sid = data.layout.find((l) => l.id === i.id || l.id.startsWith(i.id + ':'))?.id
                if (sid) select(sid)
              }}
              className="flex w-full justify-between gap-3 py-2 text-left text-[13px] hover:underline"
            >
              <span>
                {i.label} <span className="text-muted">· {DEPT_LABEL[i.department ?? ''] ?? ''}</span>
              </span>
              <span className="shrink-0 text-warn">{i.headline.split(' licenze')[0].split(' posti')[0]}</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

function Stat({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="rounded-[8px] bg-warn-soft px-3 py-2">
      <div className="text-[20px] font-semibold text-warn tabular-nums">{value}</div>
      <div className="text-[12px] leading-snug text-body">{label}</div>
    </div>
  )
}

// --- Decidi ----------------------------------------------------------------------------------------------

function DecidePanel() {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  const apply = useApp((s) => s.applyRecommended)
  const reset = useApp((s) => s.reset)
  const t = packageTotals(data, active)
  const doable = data.measures.filter((m) => m.status !== 'blocked')
  const blocked = data.measures.filter((m) => m.status === 'blocked')
  const { target } = data.summary

  return (
    <>
      <Kicker>Decidi</Kicker>
      <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px]">Misure e pacchetto</h2>
      <p className="mt-2 text-[14px] text-body">
        Accendi una misura e guarda cosa cambia nel plastico. Il pacchetto consigliato è la combinazione migliore entro {fmtChf(target.budget_chf)}.
      </p>
      <div className="mt-4 flex gap-2">
        <button onClick={apply} className="flex-1 rounded-[8px] bg-primary py-2.5 text-[14px] font-medium text-white hover:bg-primary-active">
          Applica il consigliato
        </button>
        <button onClick={reset} className="rounded-[8px] border border-ink px-4 py-2.5 text-[14px] font-medium hover:bg-surface-soft">
          Azzera
        </button>
      </div>
      <div className="mt-3 rounded-[8px] bg-surface-soft px-3 py-2 text-[13px] text-body">
        <b className="font-semibold text-ink">{t.effortDays} giornate</b> · {fmtChf(t.effortChf)} su {fmtChf(target.budget_chf)}
        <div className="mt-1.5">
          <Bar value={t.effortChf} max={target.budget_chf} color={t.budgetOk ? 'bg-primary' : 'bg-error'} />
        </div>
      </div>

      <div className="mt-4 divide-y divide-hairline-soft">
        {doable.map((m) => (
          <MeasureRow key={m.id} m={m} />
        ))}
      </div>

      <h3 className="mt-6 mb-1 text-[16px] font-semibold">Sembrano risparmi, ma no</h3>
      <p className="mb-2 text-[13px] text-muted">Il sistema le riconosce e spiega perché non si fanno.</p>
      <div className="divide-y divide-hairline-soft">
        {blocked.map((m) => (
          <MeasureRow key={m.id} m={m} />
        ))}
      </div>
    </>
  )
}

export function MeasureRow({ m, compact }: { m: Measure; compact?: boolean }) {
  const active = useApp((s) => s.active)
  const toggle = useApp((s) => s.toggleMeasure)
  const decisions = useApp((s) => s.decisions)
  const focus = useFocus()
  const on = active.includes(m.id)
  const blocked = m.status === 'blocked'
  const decision = decisions[m.id]
  return (
    <div className="flex items-start gap-3 py-3">
      <button
        onClick={() => {
          const first = m.effects[0]?.entity_id
          if (first && first !== 'seats') focus(first)
        }}
        className="min-w-0 flex-1 text-left"
      >
        <div className={`text-[14px] leading-snug font-semibold ${blocked ? 'text-muted line-through' : 'text-ink'}`}>{m.title}</div>
        {!compact && (
          <div className="mt-0.5 text-[12px] text-muted tabular-nums">
            {m.effort_days} gg · −{fmtMetric(m.savings.co2_kg, 'co2_kg')} · −{fmtMetric(m.savings.cost_chf, 'cost_chf')}
          </div>
        )}
        <div className="mt-1 flex flex-wrap gap-1">
          {m.status === 'human' && <Chip tone="human">👤 {m.owner_role}</Chip>}
          {blocked && <Chip tone="error">⛔ bloccata</Chip>}
          {decision === 'approved' && <Chip tone="primary">✓ approvata</Chip>}
          {decision === 'rejected' && <Chip tone="error">respinta</Chip>}
        </div>
      </button>
      <button onClick={() => toggle(m.id)} aria-label={on ? 'Disattiva' : 'Attiva'} className="mt-0.5">
        <Toggle on={on} disabled={blocked} />
      </button>
    </div>
  )
}

// --- Limiti ----------------------------------------------------------------------------------------------

const LIMIT_GROUP: { type: Limit['type']; title: string; icon: string; tone: 'lock' | 'error' | 'human' | 'warn' }[] = [
  { type: 'window', title: 'Finestre protette', icon: '🕒', tone: 'lock' },
  { type: 'block', title: 'Da non toccare', icon: '🔒', tone: 'error' },
  { type: 'human', title: 'Decide una persona', icon: '👤', tone: 'human' },
  { type: 'contradiction', title: 'Dati in conflitto', icon: '⚠️', tone: 'warn' },
]

function LimitsPanel() {
  const data = useApp((s) => s.data)!
  const select = useApp((s) => s.select)
  const focus = useFocus()
  const human = data.measures.filter((m) => m.status === 'human')
  return (
    <>
      <Kicker>Limiti</Kicker>
      <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px]">Cosa il sistema non decide da solo</h2>
      <p className="mt-2 text-[14px] text-body">Ogni limite viene dai ticket e dai calendari. Clicca per vederlo nel plastico.</p>

      {LIMIT_GROUP.map((g) => {
        const list = data.limits.filter((l) => l.type === g.type)
        if (!list.length) return null
        return (
          <div key={g.type} className="mt-5">
            <h3 className="mb-2 text-[16px] font-semibold">
              {g.icon} {g.title}
            </h3>
            <div className="space-y-2">
              {list.map((l) => (
                <button key={l.id} onClick={() => focus(l.entity_id)} className="block w-full rounded-[14px] border border-hairline p-3.5 text-left transition hover:border-ink">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[14px] font-semibold">{l.title}</span>
                    <Chip tone={g.tone}>{l.entity_id}</Chip>
                  </div>
                  <p className="mt-1 text-[13px] text-body">{l.text}</p>
                  <p className="mt-1 text-[12px] text-muted">{l.source}</p>
                </button>
              ))}
            </div>
          </div>
        )
      })}

      <div className="mt-6 rounded-[14px] bg-human-soft p-4">
        <div className="text-[15px] font-semibold text-ink">👤 {human.length} misure aspettano una decisione</div>
        <p className="mt-1 text-[13px] text-body">Sono sulla scrivania delle approvazioni in Management.</p>
        <button onClick={() => select('handover:queue')} className="mt-3 rounded-[8px] bg-ink px-4 py-2 text-[14px] font-medium text-white hover:bg-black">
          Apri la coda
        </button>
      </div>
    </>
  )
}
