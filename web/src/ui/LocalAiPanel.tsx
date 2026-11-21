import { useState } from 'react'
import { useApp } from '../store'
import { fmtChf, fmtMetric } from '../data/compute'
import type { LocalAiFile, LocalAiScenario, LocalAiTier, Range } from '../data/types'
import { Chip, type Tone } from './primitives'

const TIER: Record<LocalAiTier, { label: string; tone: Tone }> = {
  basic: { label: 'basic', tone: 'neutral' },
  standard: { label: 'standard', tone: 'primary' },
  advanced: { label: 'advanced', tone: 'human' },
}

const months = (m: number | null | undefined) => (m == null ? 'over 36 months' : `${m} months`)
const rangeChf = (r: Range) => `${fmtChf(r.low)} – ${fmtChf(r.high)}`

/** Advisory view: the company's own AI tools on open-weight models vs today's APIs. Changes no other number. */
export function LocalAiPanel() {
  const ai = useApp((s) => s.data?.localAi)
  const setStep = useApp((s) => s.setStep)
  if (!ai) return null
  const sc = (id: string | null) => ai.scenarios.find((s) => s.id === id) ?? null
  const byCost = sc(ai.best.by_cost)
  const byCo2 = sc(ai.best.by_co2)
  const main = ai.scenarios.filter((s) => s.id.startsWith('sc:all@') || s.id.startsWith('sc:hybrid@'))
  const singles = ai.scenarios.filter((s) => s.feasible && !main.includes(s) && (s.savings_3y?.cost_chf.mid ?? 0) > 0)
  const apiYear = ai.workloads.reduce((a, w) => a + w.api.cost_chf.mid, 0)

  return (
    <aside className="pill-shadow pointer-events-auto absolute top-6 bottom-6 left-6 flex w-[420px] flex-col overflow-hidden rounded-[14px] bg-white">
      <div className="flex items-start justify-between gap-4 px-6 pt-6">
        <div>
          <div className="text-[13px] text-muted">Advisory · a human decides</div>
          <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px] text-ink">What if the AI ran in-house?</h2>
        </div>
        <button
          onClick={() => setStep('allocation')}
          aria-label="Close"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline"
        >
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 pt-3 pb-6">
        <Chip tone="human">Information only · no number changed</Chip>
        <p className="mt-2 text-[14px] text-body">
          {ai.workloads.length} AI tools read private company data and cost <b className="font-semibold text-ink">{fmtChf(apiYear)}/year</b> in API fees today.
          This view compares open-weight models on servers the company has or can rent from its current providers, over {ai.horizon_years} years.
        </p>

        {byCost && <BestCard title="Best value" s={byCost} ai={ai} />}
        {byCo2 && byCo2.id !== byCost?.id && <BestCard title="Lowest CO₂" s={byCo2} ai={ai} />}

        <h3 className="mt-6 mb-2 text-[16px] font-semibold">Scenarios: all in-house or hybrid</h3>
        <div className="space-y-2">
          {main.map((s) => (
            <ScenarioRow key={s.id} s={s} ai={ai} />
          ))}
        </div>

        {singles.length > 0 && (
          <>
            <h3 className="mt-6 mb-1 text-[16px] font-semibold">Pays off on its own</h3>
            <p className="mb-2 text-[13px] text-muted">A single tool that covers the fixed costs by itself.</p>
            <div className="space-y-2">
              {singles.map((s) => (
                <ScenarioRow key={s.id} s={s} ai={ai} />
              ))}
            </div>
          </>
        )}

        <h3 className="mt-6 mb-2 text-[16px] font-semibold">Tools analysed</h3>
        <ul className="divide-y divide-hairline-soft">
          {ai.workloads.map((w) => (
            <li key={w.id} className="py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[14px] font-medium">{w.label}</span>
                <span className="text-[14px] font-semibold tabular-nums">{fmtChf(w.api.cost_chf.mid)}/year</span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                <Chip tone={TIER[w.tier].tone}>{TIER[w.tier].label}</Chip>
                <span>{w.why_private}</span>
                <span>· today {w.models_today.join(', ')}</span>
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-[12px] text-muted">
          Models and prices as of {ai.catalog_date}; sources and estimates in pipeline/bonus/local_ai_catalog.yaml. {ai.note}
        </p>
      </div>
    </aside>
  )
}

function BestCard({ title, s, ai }: { title: string; s: LocalAiScenario; ai: LocalAiFile }) {
  const model = ai.models.find((m) => m.id === s.model_id)
  return (
    <div className="mt-4 rounded-[14px] border border-ink p-4">
      <div className="text-[12px] font-semibold tracking-wide text-muted uppercase">{title}</div>
      <div className="mt-1 text-[15px] leading-snug font-semibold">{s.label}</div>
      <div className="mt-0.5 text-[13px] text-body">{model?.label}</div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[13px]">
        <Figure label={`API, ${ai.horizon_years} years`} value={fmtChf(s.api_3y!.cost_chf.mid)} />
        <Figure label={`In-house, ${ai.horizon_years} years`} value={fmtChf(s.local_3y!.cost_chf.mid)} />
        <Figure label="Saving" value={fmtChf(s.savings_3y!.cost_chf.mid)} sub={rangeChf(s.savings_3y!.cost_chf)} />
        <Figure label="Break-even" value={months(s.breakeven_month?.mid)} sub={`${months(s.breakeven_month?.low)} to ${months(s.breakeven_month?.high)}`} />
        <Figure label="CO₂ via API" value={fmtMetric(s.api_3y!.co2_kg?.mid ?? NaN, 'co2_kg')} />
        <Figure label="CO₂ in-house" value={fmtMetric(s.local_3y!.co2_kg?.mid ?? NaN, 'co2_kg')} />
      </div>
    </div>
  )
}

function Figure({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-[8px] bg-surface-soft px-3 py-2">
      <div className="text-[12px] text-muted">{label}</div>
      <div className="font-semibold text-ink tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-muted">{sub}</div>}
    </div>
  )
}

function ScenarioRow({ s, ai }: { s: LocalAiScenario; ai: LocalAiFile }) {
  const [open, setOpen] = useState(false)
  const hw = ai.hardware.find((h) => h.id === s.hardware_id)
  const model = ai.models.find((m) => m.id === s.model_id)
  const saving = s.savings_3y?.cost_chf.mid ?? 0
  const label = (id: string) => ai.workloads.find((w) => w.id === id)?.label ?? id
  return (
    <div className="rounded-[14px] border border-hairline">
      <button onClick={() => setOpen(!open)} className="block w-full p-4 text-left transition hover:bg-surface-soft">
        <div className="flex items-start justify-between gap-2">
          <span className="text-[14px] leading-snug font-semibold">{s.label}</span>
          {s.feasible ? (
            <Chip tone={saving > 0 ? 'primary' : 'error'}>{saving > 0 ? `+${fmtChf(saving)}` : fmtChf(saving)}</Chip>
          ) : (
            <Chip tone="lock">not feasible</Chip>
          )}
        </div>
        <p className="mt-1 text-[12px] text-muted">
          {hw?.gpu}
          {hw?.owned ? ' · already owned' : ''}
          {model ? ` · ${model.label}` : ''}
        </p>
      </button>
      {open && (
        <div className="border-t border-hairline-soft px-4 pt-2 pb-4 text-[13px] text-body">
          {!s.feasible && (
            <ul className="list-disc pl-4">
              {s.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {s.feasible && (
            <>
              <p>
                Break-even in {months(s.breakeven_month?.mid)} · setup {fmtChf(s.setup_chf!.mid)} · then {fmtChf(s.yearly_chf!.mid)}/year · GPU busy{' '}
                {Math.round((s.utilisation ?? 0) * 100)}% of its on-hours
              </p>
              {s.kept_on_api.length > 0 && <p className="mt-1">Stay on the API: {s.kept_on_api.map(label).join(', ')}.</p>}
              {s.interacts_with?.map((i) => (
                <div key={i.measure_id} className="mt-2 rounded-[8px] bg-human-soft px-3 py-2">
                  <b className="font-semibold text-human">
                    {i.measure_id} · {i.title}
                    {i.in_package ? ' (in the package)' : ''}
                  </b>
                  <div>{i.note}</div>
                  {i.cost_chf_per_year && <div className="mt-0.5 font-semibold">{fmtChf(i.cost_chf_per_year.mid)}/year</div>}
                </div>
              ))}
              <div className="mt-2 font-semibold text-primary">Pros</div>
              <ul className="list-disc pl-4">
                {s.pros?.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
              <div className="mt-2 font-semibold text-error">Cons</div>
              <ul className="list-disc pl-4">
                {s.cons?.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
              {s.alternatives.length > 0 && (
                <p className="mt-2 text-[12px] text-muted">Other suitable models: {s.alternatives.map((id) => ai.models.find((m) => m.id === id)?.label ?? id).join(', ')}</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
