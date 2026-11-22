import { useMemo, useState } from 'react'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'
import type { Ctx } from '../data/twin'
import type { Extra, XFinding, XMeasure } from '../data/extra'
import type { MetricKey, Metrics } from '../data/types'
import { GOAL_LABEL, clusterOf, findingsOf, keptOnOf, measuresOf, savedByRaw, sum, unitDiv, unitMonthly, unitParts, unitSaved } from '../data/usage'
import { forecastPlan, goalOf, unitForecast } from '../data/plan'
import { useCo2, type Co2View } from '../data/co2'
import { MARK_COLOR, useHeat } from '../scene/twin/heat'
import { BEHAVIOUR_TEXT, BehaviourIcon, behaviourOf } from './Behaviour'
import { Chip, type Tone } from './primitives'
import { MetricGrid } from './WorkstationPanel'

/** Stato di una misura detto in chiaro: si può fare subito, serve un sì, oppure non si può. */
export function measureTag(m: XMeasure): { label: string; tone: Tone } {
  if (m.status === 'ok') return { label: 'Ready, no risk', tone: 'primary' }
  if (m.status === 'blocked') return { label: 'Not possible', tone: 'lock' }
  return {
    label: `Needs a yes from ${m.owner_role || 'a person'}`,
    tone: 'human',
  }
}

// La CO₂ delle licenze è quasi zero: in quel caso si mostrano solo i franchi.
const money = (m: Metrics) => (m.co2_kg >= 1 ? `${fmtMetric(m.cost_chf, 'cost_chf')} · ${fmtMetric(m.co2_kg, 'co2_kg')}` : fmtMetric(m.cost_chf, 'cost_chf'))
/** Il risparmio che conta di più: CO₂ se c'è, altrimenti franchi. */
const saving = (m: Metrics) => (m.co2_kg >= 1 ? `−${fmtMetric(m.co2_kg, 'co2_kg')}` : `−${fmtMetric(m.cost_chf, 'cost_chf')}`)

/**
 * Scheda dei passi 2–4 per un'unità (i computer di un reparto, oppure una risorsa cloud).
 * In alto i numeri dell'anno; poi ogni punto critico come una scheda, con sotto le misure che lo risolvono.
 */
export function UnitBody({ ctx, x, unit }: { ctx: Ctx; x: Extra; unit: string }) {
  const step = useApp((s) => s.step)
  const showMeasures = useApp((s) => s.showMeasures)
  const goalSel = useApp((s) => s.goal)
  const dropped = useApp((s) => s.dropped)
  const heat = useHeat()
  const goal = goalOf(x, goalSel)
  const pkg = x.packages[goal]
  const div = unitDiv(ctx, unit)
  const showM = (step === 'baseline' && showMeasures) || step === 'packages'
  const inPkg = step === 'packages' && pkg ? (id: string) => (!pkg.measure_ids.includes(id) ? false : dropped.includes(id) ? 'dropped' : true) : undefined
  // Prossimi 12 mesi: costo e CO₂ previsti per le risorse con una previsione propria (non per i computer).
  const fm = useMemo(() => (step === 'forecast' ? forecastPlan(ctx, x, goal, dropped) : []), [step, ctx, x, goal, dropped])
  // Vista della CO₂ (location- o market-based): fattore della sede di questa unità.
  const cv = useCo2(ctx)
  const r = cv.unit(unit)
  const nextLoc = step === 'forecast' ? unitForecast(x, unitParts(ctx, unit), fm) : null
  const next = nextLoc && { without: { ...nextLoc.without, co2_kg: nextLoc.without.co2_kg * r }, with: { ...nextLoc.with, co2_kg: nextLoc.with.co2_kg * r } }

  const annual = (k: MetricKey) => sum(unitMonthly(ctx, x, unit, k)) * div
  const base: Metrics = {
    cost_chf: annual('cost_chf'),
    kwh: annual('kwh'),
    co2_kg: annual('co2_kg') * r,
  }
  let after: Metrics | null = null
  // Con le misure attive (passo 2 con l'interruttore, passo 3) i numeri dell'anno diventano «prima → dopo».
  if (step !== 'forecast' && heat.active.length) {
    const sv = cv.saved(savedByRaw(ctx, x, heat.active))
    const k = (m: MetricKey) => Math.max(0, base[m] - unitSaved(ctx, sv, unit, m) * div)
    after = { cost_chf: k('cost_chf'), kwh: k('kwh'), co2_kg: k('co2_kg') }
  }

  const findings = findingsOf(ctx, x, unit).filter((f) => f.kind === 'waste' || f.kind === 'driver')
  // Le grandi fonti prima, poi gli sprechi dal più costoso.
  findings.sort((a, b) => (a.kind === b.kind ? b.impact.cost_chf - a.impact.cost_chf : a.kind === 'driver' ? -1 : 1))
  const linked = new Set(findings.flatMap((f) => f.measure_ids))
  const others = showM ? measuresOf(ctx, x, unit).filter((m) => !linked.has(m.id)) : []
  const keptOn = keptOnOf(ctx, x, unit)
  const behaviour = behaviourOf(x, clusterOf(ctx, x, unit))
  const keepOnly = !findings.length && !others.length && keptOn.length > 0

  return (
    <>
      <section>
        <h3 className="text-[14px] font-semibold text-ink">{after ? (step === 'packages' ? `With «${GOAL_LABEL[goal] ?? goal}», per year` : 'With the proposed measures, per year') : 'Baseline year'}</h3>
        {after ? <BeforeAfter before={base} after={after} /> : <MetricGrid m={base} small />}
        {div > 1 && (
          <p className="mt-1.5 text-[12px] text-muted">
            One computer:{' '}
            {money({
              cost_chf: base.cost_chf / div,
              kwh: 0,
              co2_kg: base.co2_kg / div,
            })}
          </p>
        )}
      </section>

      {next && (
        <section className="mt-4">
          <h3 className="text-[14px] font-semibold text-ink">Next 12 months</h3>
          <div className="mt-1.5 grid grid-cols-2 gap-2 text-[12px]">
            {(['cost_chf', 'co2_kg'] as const).map((k) => (
              <div key={k} className="rounded-[8px] bg-surface-soft px-2.5 py-1.5">
                <div className="text-[11px] font-medium text-muted">{k === 'cost_chf' ? 'Cost' : 'CO₂'}</div>
                <div className="text-[13px] font-semibold text-ink tabular-nums">
                  <span className="font-normal text-muted line-through">{fmtMetric(next.without[k], k)}</span> → <span className="text-primary">{fmtMetric(next.with[k], k)}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-muted">Without changes → with «{GOAL_LABEL[goal] ?? goal}»{dropped.length ? ', your version' : ''}.</p>
        </section>
      )}

      {behaviour && (
        <div className="mt-4 flex items-center gap-2.5 rounded-[10px] bg-surface-soft px-3 py-2 text-[13px] text-body">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white text-ink shadow-sm ring-1 ring-hairline">
            <BehaviourIcon kind={behaviour.kind} className="h-3.5 w-3.5" />
          </span>
          <span>
            <span className="font-semibold text-ink">{BEHAVIOUR_TEXT[behaviour.kind]}.</span> {behaviour.size} servers behave like this.
          </span>
        </div>
      )}

      {/* Tenuto così di proposito e nient'altro da dire: solo il motivo. */}
      {keepOnly ? (
        keptOn.map((k) => (
          <p key={k.target} className="mt-5 text-[13px] text-muted">
            <span className="font-semibold text-ink">Kept on on purpose:</span> {k.reason}
          </p>
        ))
      ) : (
        <section className="mt-5">
          <h3 className="mb-2 text-[14px] font-semibold text-ink">{findings.length ? `Pain points (${findings.length})` : 'No pain points'}</h3>
          {!findings.length && <p className="text-[13px] text-muted">Used as paid for: nothing to fix here.</p>}
          <div className="space-y-2.5">
            {findings.map((f) => (
              <PainCard key={f.id} f={f} measures={showM ? f.measure_ids.map((id) => x.measures.find((m) => m.id === id)).filter((m): m is XMeasure => !!m) : []} x={x} inPkg={inPkg} cv={cv} r={r} />
            ))}
          </div>
        </section>
      )}

      {!keepOnly && (others.length > 0 || (showM && keptOn.length > 0)) && (
        <section className="mt-5">
          <h3 className="mb-1 text-[14px] font-semibold text-ink">Other options</h3>
          <div className="divide-y divide-hairline-soft">
            {others.map((m) => (
              <MeasureRow key={m.id} m={m} x={x} inPackage={inPkg?.(m.id)} cv={cv} />
            ))}
          </div>
          {keptOn.map((k) => (
            <p key={k.target} className="mt-2 text-[12px] text-muted">
              <span className="font-semibold text-ink">Kept on on purpose:</span> {k.reason}
            </p>
          ))}
        </section>
      )}
    </>
  )
}

/** Un punto critico: cosa succede, quanto vale all'anno, le prove (apribili) e, sotto, le misure che lo risolvono. */
function PainCard({ f, measures, x, inPkg, cv, r }: { f: XFinding; measures: XMeasure[]; x: Extra; inPkg?: (id: string) => boolean | 'dropped'; cv: Co2View; r: number }) {
  const [open, setOpen] = useState(false)
  const driver = f.kind === 'driver'
  return (
    <div className="rounded-[12px] border border-hairline-soft p-3">
      <div className="flex items-start gap-2">
        <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: MARK_COLOR[driver ? 'driver' : 'waste'] }} />
        <div className="min-w-0 flex-1">
          <div className="text-[14px] leading-snug font-semibold text-ink">{f.title}</div>
          <div className="mt-0.5 text-[12px] text-muted">
            {driver ? 'Big source' : 'Waste'} · {money({ ...f.impact, co2_kg: f.impact.co2_kg * r })} a year
          </div>
        </div>
      </div>
      <button onClick={() => setOpen(!open)} className="mt-1.5 ml-4.5 text-[12px] font-semibold text-ink underline-offset-2 hover:underline">
        {open ? 'Hide the evidence' : 'Show the evidence'}
      </button>
      {open && (
        <ul className="mt-1 ml-4.5 space-y-0.5 text-[12px]">
          {f.evidence.slice(0, 3).map((e, i) => (
            <li key={i} className="flex justify-between gap-3">
              <span className="text-muted">{e.statement}</span>
              <span className="shrink-0 font-semibold text-ink tabular-nums">
                {Number.isFinite(e.value) ? (Math.abs(e.value) >= 100 ? Math.round(e.value).toLocaleString('de-CH') : +e.value.toFixed(2)) : '–'} {e.unit}
              </span>
            </li>
          ))}
        </ul>
      )}
      {measures.length > 0 && (
        <div className="mt-2.5 ml-4.5 border-t border-hairline-soft pt-1">
          <div className="pt-1 text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">How to fix it</div>
          <div className="divide-y divide-hairline-soft">
            {measures.map((m) => (
              <MeasureRow key={m.id} m={m} x={x} inPackage={inPkg?.(m.id)} cv={cv} />
            ))}
          </div>
        </div>
      )}
    </div>
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
          <div key={r.key} className="rounded-[8px] bg-surface-soft px-2.5 py-1.5">
            <div className="text-[11px] font-medium text-muted">{r.label}</div>
            <div className="text-[13px] font-semibold text-ink tabular-nums">{fmtMetric(after[r.key], r.key)}</div>
            {d > 0.005 && <div className="text-[11px] font-semibold text-primary">−{Math.round(d * 100)}%</div>}
          </div>
        )
      })}
    </div>
  )
}

/** Una misura: titolo, stato (subito / serve un sì / non si può), risparmio. Aperta: cosa cambia, il rischio e i limiti da rispettare. */
function MeasureRow({ m, x, inPackage, cv }: { m: XMeasure; x: Extra; inPackage?: boolean | 'dropped'; cv: Co2View }) {
  const sv = { ...m.savings, co2_kg: cv.measure(m) }
  const [open, setOpen] = useState(false)
  const tag = measureTag(m)
  const limits = m.limit_ids.map((id) => x.limits.find((l) => l.id === id)).filter(Boolean)
  return (
    <div className={inPackage === false || inPackage === 'dropped' ? 'opacity-60' : ''}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start justify-between gap-3 py-2 text-left">
        <span className="min-w-0">
          <span className="block text-[13px] leading-snug text-ink">{m.title}</span>
          <span className="mt-1 flex flex-wrap gap-1">
            <Chip tone={tag.tone}>{tag.label}</Chip>
            {m.triggers.map((t) => (
              <Chip key={t}>{t}</Chip>
            ))}
            {inPackage === true && <Chip tone="primary">In the package</Chip>}
            {inPackage === 'dropped' && <Chip>Dropped by you</Chip>}
          </span>
        </span>
        {m.status !== 'blocked' && <span className="shrink-0 text-right text-[12px] font-semibold text-primary tabular-nums">{saving(sv)}</span>}
      </button>
      {open && (
        <div className="pb-2 text-[12px] text-body">
          <p>{m.description}</p>
          {m.status === 'blocked' && m.reason && <p className="mt-1 text-muted">Why not: {m.reason.replace(/^Safety gate:\s*/i, '')}</p>}
          {m.status !== 'blocked' && (
            <p className="mt-1 text-muted">
              Saves {money(sv)} a year · {m.effort_days} day
              {m.effort_days === 1 ? '' : 's'} of work
            </p>
          )}
          {m.risks && m.status !== 'blocked' && <p className="mt-1 text-muted">Risk: {m.risks}</p>}
          {limits.map((l) => (
            <p key={l!.id} className="mt-1 text-muted">
              Respect: {l!.title}
              {l!.period_text && ` (${l!.period_text})`}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
