import { useState } from 'react'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'
import type { Ctx } from '../data/twin'
import type { Extra, XFinding, XMeasure } from '../data/extra'
import type { MetricKey, Metrics } from '../data/types'
import { GOAL_LABEL, findingsOf, keptOnOf, limitsOf, measuresOf, unitDiv, unitMonthly, unitSaved, savedByRaw, sum } from '../data/usage'
import { Chip, type Tone } from './primitives'
import { MetricGrid } from './WorkstationPanel'

const short = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { month: 'short' })

/** Stato di una misura detto in chiaro: si può fare subito, serve un sì, oppure non si può. */
export function measureTag(m: XMeasure): { label: string; tone: Tone } {
  if (m.status === 'ok') return { label: 'No risk · ready to apply', tone: 'primary' }
  if (m.status === 'blocked') return { label: 'Not possible', tone: 'lock' }
  return { label: `Needs approval · ${m.owner_role || 'a person'}`, tone: 'human' }
}

/**
 * Scheda dei passi 2–4 per un'unità (i computer di un reparto, oppure una risorsa cloud):
 * consumo dell'anno mese per mese, punti critici con le prove, e (se attivo) le misure proposte e i limiti da rispettare.
 */
export function UnitBody({ ctx, x, unit }: { ctx: Ctx; x: Extra; unit: string }) {
  const step = useApp((s) => s.step)
  const month = useApp((s) => s.month)
  const showMeasures = useApp((s) => s.showMeasures)
  const goalSel = useApp((s) => s.goal)
  const colorBy = useApp((s) => s.colorBy)
  const metric: MetricKey = colorBy === 'cost_chf' ? 'cost_chf' : 'co2_kg'
  const goal = goalSel && x.packages[goalSel] ? goalSel : x.defaultGoal
  const pkg = x.packages[goal]
  const div = unitDiv(ctx, unit)
  const isPcs = unit.startsWith('pcs:')

  // Totali dell'unità (per i computer: tutto il reparto).
  const annual = (k: MetricKey) => sum(unitMonthly(ctx, x, unit, k)) * div
  const base: Metrics = { cost_chf: annual('cost_chf'), kwh: annual('kwh'), co2_kg: annual('co2_kg') }
  const monthly = unitMonthly(ctx, x, unit, metric).map((v) => v * div)
  const findings = findingsOf(ctx, x, unit).filter((f) => f.kind === 'waste' || f.kind === 'driver')
  const measures = measuresOf(ctx, x, unit)
  const limits = limitsOf(ctx, x, unit)
  const keptOn = keptOnOf(ctx, x, unit)
  const showM = (step === 'baseline' && showMeasures) || step === 'packages'

  let after: Metrics | null = null
  if (step === 'packages' && pkg) {
    const sv = savedByRaw(ctx, x, pkg.measure_ids)
    const k = (m: MetricKey) => Math.max(0, base[m] - unitSaved(ctx, sv, unit, m) * div)
    after = { cost_chf: k('cost_chf'), kwh: k('kwh'), co2_kg: k('co2_kg') }
  }

  return (
    <>
      {after ? (
        <section>
          <h3 className="text-[16px] font-semibold text-ink">With «{GOAL_LABEL[goal] ?? goal}», per year</h3>
          <BeforeAfter before={base} after={after} />
        </section>
      ) : (
        <section>
          <h3 className="text-[16px] font-semibold text-ink">Baseline year{isPcs ? ', whole department' : ''}</h3>
          <MetricGrid m={base} />
          {isPcs && (
            <p className="mt-1.5 text-[12px] text-muted">
              {div} computers, same services each: one computer {fmtMetric(base.cost_chf / div, 'cost_chf')} · {fmtMetric(base.co2_kg / div, 'co2_kg')}.
            </p>
          )}
        </section>
      )}

      <section className="mt-5">
        <h3 className="text-[14px] font-semibold text-ink">{metric === 'cost_chf' ? 'Cost' : 'CO₂'} month by month</h3>
        <MonthBars values={monthly} labels={x.months.map(short)} current={step === 'baseline' ? month : null} metric={metric} />
      </section>

      {findings.length > 0 && (
        <section className="mt-6">
          <h3 className="mb-1 text-[14px] font-semibold text-ink">Pain points</h3>
          <div className="divide-y divide-hairline-soft border-y border-hairline-soft">
            {findings.map((f) => (
              <FindingRow key={f.id} f={f} />
            ))}
          </div>
        </section>
      )}
      {!findings.length && <p className="mt-6 text-[13px] text-muted">No waste found here: it is used as paid for.</p>}

      {showM && (
        <section className="mt-6">
          <h3 className="mb-1 text-[14px] font-semibold text-ink">Proposed measures</h3>
          {measures.length ? (
            <div className="divide-y divide-hairline-soft border-y border-hairline-soft">
              {measures.map((m) => (
                <MeasureRow key={m.id} m={m} inPackage={step === 'packages' ? pkg?.measure_ids.includes(m.id) : undefined} />
              ))}
            </div>
          ) : (
            <p className="text-[13px] text-muted">Nothing to change here.</p>
          )}
        </section>
      )}

      {showM && (limits.length > 0 || keptOn.length > 0) && (
        <section className="mt-6">
          <h3 className="mb-1 text-[14px] font-semibold text-ink">What we must respect</h3>
          <ul className="space-y-2">
            {keptOn.map((k) => (
              <li key={k.target} className="rounded-[8px] bg-surface-soft px-3 py-2 text-[13px] text-body">
                <span className="font-semibold text-ink">Kept on on purpose.</span> {k.reason} <span className="text-muted">({k.ref})</span>
              </li>
            ))}
            {limits.map((l) => (
              <li key={l.id} className="rounded-[8px] bg-surface-soft px-3 py-2 text-[13px] text-body">
                <span className="font-semibold text-ink">{l.type === 'window' ? 'Time window' : l.type === 'block' ? 'Must not change' : 'Sources disagree'}.</span> {l.title}
                {l.period_text && <span className="text-muted"> · {l.period_text}</span>}
                {l.source && <span className="text-muted"> ({l.source})</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

function BeforeAfter({ before, after }: { before: Metrics; after: Metrics }) {
  const rows: { key: MetricKey; label: string }[] = [
    { key: 'cost_chf', label: 'Cost' },
    { key: 'kwh', label: 'Energy' },
    { key: 'co2_kg', label: 'CO₂' },
  ]
  return (
    <div className="mt-2 grid grid-cols-3 gap-2">
      {rows.map((r) => {
        const d = before[r.key] > 0 ? 1 - after[r.key] / before[r.key] : 0
        return (
          <div key={r.key} className="rounded-[8px] bg-surface-soft px-3 py-2.5">
            <div className="text-[12px] font-medium text-muted">{r.label}</div>
            <div className="text-[16px] font-semibold text-ink tabular-nums">{fmtMetric(after[r.key], r.key)}</div>
            <div className="text-[11px] text-muted tabular-nums">
              was {fmtMetric(before[r.key], r.key)}
              {d > 0.005 && <span className="font-semibold text-primary"> · −{Math.round(d * 100)}%</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** Dodici barre (una per mese), neutre: il mese della simulazione è evidenziato. */
function MonthBars({ values, labels, current, metric }: { values: number[]; labels: string[]; current: number | null; metric: MetricKey }) {
  const max = Math.max(...values, 1e-9)
  return (
    <div className="mt-2">
      <div className="flex h-16 items-end gap-1">
        {values.map((v, i) => (
          <div
            key={i}
            title={`${labels[i]}: ${fmtMetric(v, metric)}`}
            className="flex-1 rounded-t-[3px] transition-all"
            style={{ height: `${Math.max(3, (v / max) * 100)}%`, background: current === i ? '#222222' : current === null ? '#9C978F' : '#D9D6D0' }}
          />
        ))}
      </div>
      <div className="mt-1 flex gap-1 text-[10px] text-muted">
        {labels.map((l, i) => (
          <span key={i} className={`flex-1 text-center ${current === i ? 'font-semibold text-ink' : ''}`}>
            {l[0]}
          </span>
        ))}
      </div>
    </div>
  )
}

function FindingRow({ f }: { f: XFinding }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start justify-between gap-3 py-2.5 text-left">
        <span className="flex min-w-0 items-start gap-2">
          <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${f.severity === 'high' ? 'bg-error' : f.severity === 'medium' ? 'bg-warn' : 'bg-muted-soft'}`} />
          <span className="text-[14px] leading-snug text-ink">{f.title}</span>
        </span>
        <span className="shrink-0 text-[12px] text-muted">{f.kind === 'driver' ? 'Big source' : 'Waste'}</span>
      </button>
      {open && (
        <div className="pb-3 pl-4 text-[13px] text-body">
          <ul className="space-y-0.5">
            {f.evidence.slice(0, 4).map((e, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span className="text-muted">{e.statement}</span>
                <span className="shrink-0 font-semibold tabular-nums">
                  {Number.isFinite(e.value) ? (Math.abs(e.value) >= 100 ? Math.round(e.value).toLocaleString('de-CH') : +e.value.toFixed(2)) : '–'} {e.unit}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[12px] text-muted">
            At stake per year: {fmtMetric(f.impact.cost_chf, 'cost_chf')} · {fmtMetric(f.impact.co2_kg, 'co2_kg')}
          </p>
        </div>
      )}
    </div>
  )
}

function MeasureRow({ m, inPackage }: { m: XMeasure; inPackage?: boolean }) {
  const [open, setOpen] = useState(false)
  const tag = measureTag(m)
  return (
    <div className={inPackage === false ? 'opacity-60' : ''}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start justify-between gap-3 py-2.5 text-left">
        <span className="min-w-0">
          <span className="block text-[14px] leading-snug text-ink">{m.title}</span>
          <span className="mt-1 flex flex-wrap gap-1">
            <Chip tone={tag.tone}>{tag.label}</Chip>
            {inPackage === true && <Chip tone="primary">In the package</Chip>}
            {inPackage === false && <Chip>Not chosen</Chip>}
          </span>
        </span>
        <span className="shrink-0 text-right text-[12px] text-muted tabular-nums">
          {m.status === 'blocked' ? '–' : `−${fmtMetric(m.savings.co2_kg, 'co2_kg')}`}
          <br />
          {m.status === 'blocked' ? '' : `−${fmtMetric(m.savings.cost_chf, 'cost_chf')}`}
        </span>
      </button>
      {open && (
        <div className="pb-3 text-[13px] text-body">
          <p>{m.description}</p>
          {m.status === 'blocked' && m.reason && <p className="mt-1.5 text-[12px] text-muted">Why not: {m.reason.replace(/^Safety gate:\s*/i, '')}</p>}
          {m.risks && m.status !== 'blocked' && <p className="mt-1.5 text-[12px] text-muted">Risk: {m.risks}</p>}
          <p className="mt-1 text-[12px] text-muted">
            Effort {m.effort_days} day{m.effort_days === 1 ? '' : 's'}
            {m.start_date && ` · from ${new Date(m.start_date).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })}`}
          </p>
        </div>
      )}
    </div>
  )
}
