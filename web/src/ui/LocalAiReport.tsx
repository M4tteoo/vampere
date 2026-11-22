import { useEffect } from 'react'
import { useApp } from '../store'
import { fmtChf, fmtMetric } from '../data/compute'
import type { LocalAiPanel } from '../data/types'
import { Chip } from './primitives'

// Report «AI in casa» (bonus del backend, solo consultivo): i testi e i numeri arrivano già pronti da local_ai.json → panel.
// Sta nel passo 3 perché è un'opzione da decidere come le misure, ma fuori dal budget del pacchetto.

const SERIES_COLOR: Record<string, string> = { api_only: '#8A8A8A', best_value: '#1F7A57', lowest_co2: '#6E9FD6' }

const fig = (unit: 'CHF' | 'kg' | 'months', v: number | null) => (v == null ? 'not within 3 years' : unit === 'CHF' ? fmtChf(v) : unit === 'kg' ? fmtMetric(v, 'co2_kg') : `${Math.round(v)} months`)
const short = (unit: string, v: number) => (unit === 'CHF' ? fmtChf(v) : unit === 'kg' ? fmtMetric(v, 'co2_kg') : fmtMetric(v, 'kwh'))

/** Scheda in fondo all'elenco dei pacchetti: la conclusione in una riga e il bottone per il report. */
export function LocalAiCard() {
  const panel = useApp((s) => s.data?.localAi?.panel)
  const open = useApp((s) => s.setLocalAiOpen)
  if (!panel) return null
  const best = panel.options.find((o) => o.id === 'best_value') ?? panel.options[0]
  const get = (k: string) => best?.figures.find((f) => f.key === k)
  const saving = get('saving')
  const be = get('breakeven')
  return (
    <section className="rounded-[12px] border border-dashed border-hairline px-3.5 py-3">
      <div className="text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">Beyond the package</div>
      <div className="mt-0.5 text-[15px] font-semibold text-ink">Run our AI tools in-house?</div>
      <p className="mt-1 text-[12px] leading-[17px] text-body">{panel.tools.headline}</p>
      {saving?.mid != null && (
        <p className="mt-1 text-[12px] text-muted">
          <span className="font-semibold text-primary">−{fmtChf(saving.mid)}</span> in 3 years · setup paid back after {fig('months', be?.mid ?? null)}
        </p>
      )}
      <button onClick={() => open(true)} className="mt-2 rounded-full bg-ink px-3.5 py-1.5 text-[13px] font-semibold text-white">
        Open the report
      </button>
    </section>
  )
}

/** Report a tutta pagina: le due opzioni, tre grafici, quali strumenti e perché, come abbiamo calcolato. */
export function LocalAiReport() {
  const panel = useApp((s) => s.data?.localAi?.panel)
  const isOpen = useApp((s) => s.localAiOpen)
  const setOpen = useApp((s) => s.setLocalAiOpen)
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, setOpen])
  if (!panel || !isOpen) return null
  return (
    <div className="step-in pointer-events-auto absolute inset-0 z-50 grid place-items-center bg-ink/25 p-6" onClick={() => setOpen(false)}>
      <article className="pill-shadow flex max-h-full w-full max-w-[1040px] flex-col overflow-hidden rounded-[18px] bg-white" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start justify-between gap-6 border-b border-hairline-soft px-8 pt-7 pb-5">
          <div>
            <div className="text-[13px] text-muted">Advisory · a person decides · not part of the package budget</div>
            <h2 className="mt-1 text-[26px] leading-tight font-semibold tracking-[-0.5px] text-ink">Running our AI tools in-house</h2>
            <p className="mt-1.5 max-w-[720px] text-[14px] text-body">{panel.tools.intro.replace(/\s*\(agreed with [^)]*\)/i, '')}</p>
          </div>
          <button onClick={() => setOpen(false)} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-8 py-6">
          <Options panel={panel} />
          <section className="mt-8 grid grid-cols-3 gap-5">
            {panel.charts.map((c) => (
              <Chart key={c.id} c={c} />
            ))}
          </section>
          <Tools panel={panel} />
          <Method panel={panel} />
        </div>
      </article>
    </div>
  )
}

function Options({ panel }: { panel: LocalAiPanel }) {
  // Il primo punto della curva dei costi cumulati è la spesa iniziale (setup) dell'opzione.
  const setup = panel.charts.find((c) => c.id === 'cost')?.series.find((x) => x.id !== 'api_only')?.values[0]
  // Numeri del pareggio (opzione «Best value»): costo in casa al mese e quanto costano oggi, al mese, gli stessi strumenti sull'API.
  const ai = useApp((s) => s.data?.localAi)
  const sc = ai?.scenarios.find((x) => x.id === panel.options[0]?.scenario_id)
  const localMonth = sc?.yearly_chf ? sc.yearly_chf.mid / 12 : null
  const apiMonth = sc && ai ? sc.workload_ids.reduce((a, id) => a + (ai.workloads.find((w) => w.id === id)?.api.cost_chf.mid ?? 0), 0) / 12 : null
  return (
    <>
      {setup != null && setup > 0 && (
        <p className="mb-4 text-[13px] text-body">
          <span className="font-semibold text-ink">Why it is not paid back at once:</span> going in-house costs about {fmtChf(setup)} up front (setup of the server and the models). After that, every
          month costs less than the API
          {localMonth && apiMonth ? ` (in «${panel.options[0].title}»: about ${fmtChf(localMonth)} a month in-house against ${fmtChf(apiMonth)} today on the API, a gap that grows as AI use grows)` : ''}: «paid back after» is
          when those monthly savings have covered the setup.
        </p>
      )}
      <section className={`grid gap-5 ${panel.options.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}>
        {panel.options.map((o) => {
          const f = (k: string) => o.figures.find((x) => x.key === k)
          const saving = f('saving')
          const be = f('breakeven')
          return (
            <div key={o.id} className="rounded-[14px] border border-hairline-soft p-5">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: SERIES_COLOR[o.id] }} />
                <h3 className="text-[18px] font-semibold text-ink">{o.title}</h3>
                {o.owned && <Chip tone="primary">Server we already have</Chip>}
              </div>
              <p className="mt-1 text-[13px] text-body">{o.summary}</p>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <Big
                  label="Saving in 3 years"
                  value={fig('CHF', saving?.mid ?? null)}
                  range={saving && saving.low != null && saving.high != null ? `${fmtChf(saving.low)} – ${fmtChf(saving.high)}` : undefined}
                />
                <Big label="Paid back after" value={fig('months', be?.mid ?? null)} range={be && be.low != null && be.high != null ? `${be.low} – ${be.high} months` : undefined} />
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
                {(['api_3y', 'local_3y', 'co2_api', 'co2_local'] as const).map((k) => {
                  const x = f(k)
                  return x ? (
                    <div key={k} className="flex justify-between gap-2 border-b border-hairline-soft py-1">
                      <dt className="text-muted">{x.label}</dt>
                      <dd className="font-semibold text-ink tabular-nums">{fig(x.unit, x.mid)}</dd>
                    </div>
                  ) : null
                })}
              </dl>
              <p className="mt-3 text-[12px] text-muted">
                <span className="font-semibold text-ink">In-house:</span> {o.tools_local.join(', ')}. <span className="font-semibold text-ink">Stay on the API:</span> {o.tools_api.join(', ')}.
              </p>
            </div>
          )
        })}
      </section>
    </>
  )
}

function Big({ label, value, range }: { label: string; value: string; range?: string }) {
  return (
    <div className="rounded-[10px] bg-surface-soft px-3.5 py-2.5">
      <div className="text-[12px] text-muted">{label}</div>
      <div className="text-[22px] font-semibold tracking-[-0.4px] text-ink tabular-nums">{value}</div>
      {range && <div className="text-[11px] text-muted tabular-nums">range {range}</div>}
    </div>
  )
}

function Chart({ c }: { c: LocalAiPanel['charts'][number] }) {
  const W = 300
  const H = 150
  const max = Math.max(1, ...c.series.flatMap((s) => s.values)) * 1.08
  // Margini per le etichette: a sinistra il valore massimo, ai lati il primo e l'ultimo anno.
  const px = (i: number) => 58 + (i / Math.max(1, c.x.length - 1)) * (W - 86)
  const py = (v: number) => H - 22 - (v / max) * (H - 34)
  return (
    <figure>
      <figcaption className="text-[14px] font-semibold text-ink">{c.title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full">
        <line x1="50" x2={W - 20} y1={H - 22} y2={H - 22} stroke="#DDDDDD" />
        <text x="50" y={py(max / 1.08) + 4} textAnchor="end" fontSize="9" fill="#8A8A8A">
          {short(c.unit, max / 1.08)}
        </text>
        {c.series.map((s) => (
          <g key={s.id}>
            <path
              d={s.values.map((v, i) => `${i ? 'L' : 'M'}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(' ')}
              fill="none"
              stroke={SERIES_COLOR[s.id]}
              strokeWidth={s.id === 'api_only' ? 2 : 2.5}
              strokeDasharray={s.id === 'api_only' ? '5 4' : undefined}
            />
            {s.values.map((v, i) => (
              <circle key={i} cx={px(i)} cy={py(v)} r="2.5" fill={SERIES_COLOR[s.id]} />
            ))}
          </g>
        ))}
        {c.x_labels.map((l, i) => (
          <text key={l} x={px(i)} y={H - 6} textAnchor="middle" fontSize="10" fill="#6A6A6A">
            {l}
          </text>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted">
        {c.series.map((s) => (
          <span key={s.id} className="flex items-center gap-1">
            <span className="h-0.5 w-3.5" style={{ background: SERIES_COLOR[s.id] }} />
            {s.label}
          </span>
        ))}
      </div>
      <p className="mt-1 text-[11px] text-muted">{c.caption}</p>
    </figure>
  )
}

function Tools({ panel }: { panel: LocalAiPanel }) {
  const t = panel.tools
  return (
    <section className="mt-8">
      <h3 className="text-[18px] font-semibold text-ink">{t.title}</h3>
      <p className="mt-0.5 text-[13px] text-body">{t.headline}</p>
      <table className="mt-3 w-full text-left text-[13px]">
        <thead className="text-[12px] text-muted">
          <tr className="border-b border-hairline-soft">
            <th className="py-2 font-medium">Tool</th>
            <th className="py-2 font-medium">Private data it handles</th>
            <th className="py-2 text-right font-medium">API today, per year</th>
            <th className="py-2 pl-4 font-medium">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {t.items.map((i) => (
            <tr key={i.workload_id} className="border-b border-hairline-soft align-top">
              <td className="py-2 font-semibold text-ink">{i.label}</td>
              <td className="py-2 text-body">
                {i.private_data}
                {i.notes.map((n) => (
                  <div key={n} className="text-[12px] text-muted">
                    {n}
                  </div>
                ))}
              </td>
              <td className="py-2 text-right text-ink tabular-nums">
                {fmtChf(i.api_chf_per_year)}
                <div className="text-[12px] text-muted">{fmtMetric(i.api_co2_kg_per_year, 'co2_kg')}</div>
              </td>
              <td className="py-2 pl-4">
                <Chip tone={i.local_in.length ? 'primary' : 'neutral'}>{i.status}</Chip>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Method({ panel }: { panel: LocalAiPanel }) {
  const m = panel.model
  return (
    <section className="mt-8 grid grid-cols-[1fr_1.2fr] gap-8">
      <div>
        <h3 className="text-[18px] font-semibold text-ink">{m.title}</h3>
        <ol className="mt-2 space-y-2">
          {m.steps.map((s, i) => (
            <li key={s.label} className="flex gap-3 text-[13px]">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface-strong text-[12px] font-semibold text-ink">{i + 1}</span>
              <span>
                <span className="font-semibold text-ink">{s.label}.</span> <span className="text-body">{s.text}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>
      <div>
        <h3 className="text-[18px] font-semibold text-ink">{m.servers_title}</h3>
        <ul className="mt-2 divide-y divide-hairline-soft text-[13px]">
          {m.servers.map((s) => (
            <li key={s.hardware_id} className="py-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink">{s.label}</span>
                {s.owned && <Chip tone="primary">Ours</Chip>}
              </div>
              <div className="text-[12px] text-muted">
                {s.gpu} · <span className="text-body">{s.price.text}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
