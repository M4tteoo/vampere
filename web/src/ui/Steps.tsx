import { useEffect, useMemo, useState } from 'react'
import { useApp, type ColorBy } from '../store'
import { fmtMetric } from '../data/compute'
import type { Extra } from '../data/extra'
import type { MetricKey, Metrics } from '../data/types'
import { CLUSTER_COLORS, GOAL_HINT, GOAL_LABEL, HEAT, NEUTRAL } from '../data/usage'
import { useHeat } from '../scene/twin/heat'
import { PANEL_W } from '../scene/Scene'
import { Chip } from './primitives'

const MONTH = (iso: string, opts: Intl.DateTimeFormatOptions = { month: 'short' }) => new Date(iso).toLocaleDateString('en-GB', opts)
const heatStep = (step: string) => step === 'baseline' || step === 'packages' || step === 'forecast'

/** Fa avanzare la simulazione di un mese ogni 0,65 s (12 mesi ≈ 8 s). */
export function Ticker() {
  const playing = useApp((s) => s.playing)
  const tick = useApp((s) => s.tick)
  useEffect(() => {
    if (!playing) return
    const t = setInterval(tick, 650)
    return () => clearInterval(t)
  }, [playing, tick])
  return null
}

/** Tutti i comandi dei passi 2–4 sopra la scena. */
export function StepUi() {
  const step = useApp((s) => s.step)
  const x = useApp((s) => s.data?.extra)
  const room = useApp((s) => s.room)
  const selected = useApp((s) => !!s.selectedId)
  const [charts, setCharts] = useState(false)
  if (!x || !heatStep(step)) return null
  return (
    <>
      <div className="pointer-events-auto absolute top-3 left-1/2 -translate-x-1/2">
        {step === 'baseline' && <Timeline months={x.months} />}
        {step === 'packages' && <GoalPicker x={x} />}
        {step === 'forecast' && <ForecastBar x={x} />}
      </div>
      {!selected && !charts && (
        <div className="pointer-events-auto absolute top-3 right-6 flex items-center gap-2">
          {step === 'baseline' && <MeasuresToggle />}
          {(step === 'baseline' || step === 'packages') && <ExportButton x={x} />}
          {step === 'forecast' && <PillButton onClick={() => setCharts(true)}>Show the charts</PillButton>}
        </div>
      )}
      {step === 'forecast' && charts && <ForecastCharts x={x} onClose={() => setCharts(false)} />}
      <Legend compact={!!room} />
      {!room && <ResultPill x={x} />}
    </>
  )
}

function PillButton({ children, onClick, disabled, title }: { children: React.ReactNode; onClick: () => void; disabled?: boolean; title?: string }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="pill-shadow rounded-full bg-white px-4 py-2.5 text-[14px] font-medium whitespace-nowrap text-ink transition hover:bg-surface-soft disabled:text-muted-soft"
    >
      {children}
    </button>
  )
}

/** Barra dei mesi: play / rigioca, un segmento per mese, «Year» = l'anno intero. */
function Timeline({ months }: { months: string[] }) {
  const month = useApp((s) => s.month)
  const playing = useApp((s) => s.playing)
  const play = useApp((s) => s.play)
  const setMonth = useApp((s) => s.setMonth)
  const year = month === null
  return (
    <div className="pill-shadow flex items-center gap-3 rounded-full bg-white py-2 pr-2 pl-2">
      <button
        onClick={play}
        aria-label={playing ? 'Playing' : 'Play the year'}
        className="grid h-9 w-9 place-items-center rounded-full bg-ink text-white transition hover:bg-black"
      >
        {playing ? (
          <span className="h-2.5 w-2.5 rounded-full bg-white" />
        ) : (
          <svg viewBox="0 0 24 24" className="ml-0.5 h-3.5 w-3.5" fill="currentColor">
            <path d="M7 5l12 7-12 7z" />
          </svg>
        )}
      </button>
      <div className="flex items-center gap-0.5">
        {months.map((m, i) => {
          const on = month === i
          const past = year || (month !== null && i <= month)
          return (
            <button
              key={m}
              onClick={() => setMonth(i)}
              className={`flex w-9 flex-col items-center rounded-full py-1 text-[11px] transition ${on ? 'bg-surface-strong font-semibold text-ink' : 'text-muted hover:text-ink'}`}
            >
              <span className={`mb-1 h-1 w-6 rounded-full ${past ? 'bg-primary' : 'bg-hairline'}`} />
              {MONTH(m)}
            </button>
          )
        })}
      </div>
      <button
        onClick={() => {
          setMonth(null)
          useApp.setState({ simDone: true })
        }}
        className={`rounded-full px-4 py-2 text-[13px] font-semibold transition ${year ? 'bg-ink text-white' : 'text-ink hover:bg-surface-soft'}`}
      >
        Whole year
      </button>
    </div>
  )
}

function MeasuresToggle() {
  const on = useApp((s) => s.showMeasures)
  const set = useApp((s) => s.setShowMeasures)
  const simDone = useApp((s) => s.simDone)
  return (
    <button
      onClick={() => set(!on)}
      disabled={!simDone}
      title={simDone ? undefined : 'Available after the baseline year has played'}
      className="pill-shadow flex items-center gap-3 rounded-full bg-white py-2 pr-2 pl-4 text-[14px] font-medium text-ink disabled:text-muted-soft"
    >
      Show proposed measures
      <span className={`relative h-6 w-10 rounded-full transition ${on ? 'bg-primary' : 'bg-hairline'}`}>
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
      </span>
    </button>
  )
}

/** Tre obiettivi del backend: cambio istantaneo, nessuna AI. */
function GoalPicker({ x }: { x: Extra }) {
  const goalSel = useApp((s) => s.goal)
  const setGoal = useApp((s) => s.setGoal)
  const goal = goalSel && x.packages[goalSel] ? goalSel : x.defaultGoal
  return (
    <div className="pill-shadow flex items-center gap-1 rounded-full bg-white p-1.5">
      <span className="px-3 text-[13px] font-medium text-muted">Optimise for</span>
      {x.goals.map((g) => (
        <button
          key={g}
          onClick={() => setGoal(g)}
          title={GOAL_HINT[g]}
          className={`rounded-full px-4 py-2 text-left transition ${g === goal ? 'bg-ink text-white' : 'text-ink hover:bg-surface-soft'}`}
        >
          <div className="text-[14px] font-semibold">{GOAL_LABEL[g] ?? g}</div>
          <div className={`text-[11px] ${g === goal ? 'text-white/75' : 'text-muted'}`}>{GOAL_HINT[g] ?? ''}</div>
        </button>
      ))}
    </div>
  )
}

function ForecastBar({ x }: { x: Extra }) {
  const withPackage = useApp((s) => s.withPackage)
  const setWith = useApp((s) => s.setWithPackage)
  const month = useApp((s) => s.month)
  const playing = useApp((s) => s.playing)
  const play = useApp((s) => s.play)
  const setMonth = useApp((s) => s.setMonth)
  const fm = x.forecast?.months ?? []
  return (
    <div className="flex items-center gap-2">
      <div className="pill-shadow flex items-center gap-1 rounded-full bg-white p-1.5">
        {[false, true].map((w) => (
          <button
            key={String(w)}
            onClick={() => setWith(w)}
            className={`rounded-full px-4 py-2 text-[14px] font-semibold whitespace-nowrap transition ${withPackage === w ? 'bg-ink text-white' : 'text-ink hover:bg-surface-soft'}`}
          >
            {w ? 'With the package' : 'Without changes'}
          </button>
        ))}
      </div>
      <div className="pill-shadow flex items-center gap-3 rounded-full bg-white py-2 pr-3 pl-2">
        <button onClick={play} aria-label="Play" className="grid h-9 w-9 place-items-center rounded-full bg-ink text-white">
          {playing ? (
            <span className="h-2.5 w-2.5 rounded-full bg-white" />
          ) : (
            <svg viewBox="0 0 24 24" className="ml-0.5 h-3.5 w-3.5" fill="currentColor">
              <path d="M7 5l12 7-12 7z" />
            </svg>
          )}
        </button>
        <div className="flex items-center gap-0.5">
          {fm.map((m, i) => {
            const ev = x.forecast?.events.find((e) => e.date.slice(0, 7) === m.month.slice(0, 7))
            return (
              <button
                key={m.month}
                onClick={() => setMonth(i)}
                title={ev?.label}
                className={`relative flex w-9 flex-col items-center rounded-full py-1 text-[11px] ${month === i ? 'bg-surface-strong font-semibold text-ink' : 'text-muted hover:text-ink'}`}
              >
                <span className={`mb-1 h-1 w-6 rounded-full ${month !== null && i <= month ? 'bg-primary' : 'bg-hairline'}`} />
                {MONTH(m.month)}
                {ev && <span className="absolute -top-0.5 right-1 h-1.5 w-1.5 rounded-full bg-human" />}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** Totali in basso al centro: mese della simulazione o anno; pacchetto; previsione. */
function ResultPill({ x }: { x: Extra }) {
  const step = useApp((s) => s.step)
  const month = useApp((s) => s.month)
  const goalSel = useApp((s) => s.goal)
  const withPackage = useApp((s) => s.withPackage)
  const monthly = useMemo(() => {
    const out = x.months.map(() => ({ cost_chf: 0, kwh: 0, co2_kg: 0 }) as Metrics)
    for (const loc of ['CH', 'DE', 'IE', 'EU']) {
      const s = x.series.get(`loc:${loc}`)
      if (!s) continue
      for (const k of ['cost_chf', 'kwh', 'co2_kg'] as MetricKey[]) s[k].forEach((v, i) => (out[i][k] += v))
    }
    return out
  }, [x])
  const goal = goalSel && x.packages[goalSel] ? goalSel : x.defaultGoal
  const pkg = x.packages[goal]
  const line = (m: Metrics) => `${fmtMetric(m.cost_chf, 'cost_chf')} · ${fmtMetric(m.kwh, 'kwh')} · ${fmtMetric(m.co2_kg, 'co2_kg')}`

  let body: React.ReactNode = null
  if (step === 'baseline') {
    body =
      month === null ? (
        <>
          <span className="text-muted">Baseline year</span> <span className="font-semibold text-ink">{line(x.baseline)}</span>
        </>
      ) : (
        <>
          <span className="text-muted">{MONTH(x.months[month], { month: 'long', year: 'numeric' })}</span>{' '}
          <span className="font-semibold text-ink">{line(monthly[month])}</span>
        </>
      )
  } else if (step === 'packages' && pkg) {
    const conf = x.confidence?.byGoal[goal]
    body = (
      <span className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
        <span className="font-semibold text-ink">CO₂ −{Math.round(pkg.co2 * 100)}%</span>
        <span className="text-muted">(at worst −{Math.round(pkg.co2_low * 100)}%)</span>
        <span className="font-semibold text-ink">Cost −{Math.round(pkg.cost * 100)}%</span>
        <span className="text-muted">
          {pkg.measure_ids.length} measures · {pkg.effort_days} days = {fmtMetric(pkg.effort_chf, 'cost_chf')}
        </span>
        {pkg.meets.co2 && pkg.meets.cost && pkg.meets.budget && <Chip tone="primary">All targets met</Chip>}
        {Number.isFinite(conf) && <Chip>{(conf! * 100).toFixed(1)}% of 10,000 scenarios reach both targets</Chip>}
      </span>
    )
  } else if (step === 'forecast' && x.forecast) {
    const tot = (k: 'with' | 'without') =>
      x.forecast!.months.reduce((a, m) => ({ cost_chf: a.cost_chf + m[k].cost_chf, kwh: a.kwh + m[k].kwh, co2_kg: a.co2_kg + m[k].co2_kg }), { cost_chf: 0, kwh: 0, co2_kg: 0 })
    body = (
      <>
        <span className="text-muted">Sep 2026 – Aug 2027</span>{' '}
        <span className={withPackage ? 'text-muted line-through' : 'font-semibold text-ink'}>{line(tot('without'))}</span>
        <span className="text-muted"> → </span>
        <span className={withPackage ? 'font-semibold text-primary' : 'text-muted'}>{line(tot('with'))}</span>
      </>
    )
  }
  if (!body) return null
  return (
    <div className="pill-shadow pointer-events-auto absolute bottom-6 left-1/2 max-w-[62%] -translate-x-1/2 rounded-[22px] bg-white px-5 py-3 text-center text-[14px]">
      {body}
    </div>
  )
}

/** Come leggere la mappa: colori, nuvole, punti critici. Nella vista del reparto si chiude in una pillola. */
function Legend({ compact }: { compact: boolean }) {
  const step = useApp((s) => s.step)
  const colorBy = useApp((s) => s.colorBy)
  const setColorBy = useApp((s) => s.setColorBy)
  const month = useApp((s) => s.month)
  const x = useApp((s) => s.data?.extra)!
  // Aperta nella pianta, chiusa nel reparto; si può aprire e chiudere a mano in entrambi.
  const [toggled, setToggled] = useState<{ compact: boolean; open: boolean } | null>(null)
  const open = toggled && toggled.compact === compact ? toggled.open : !compact
  const setOpen = (v: boolean) => setToggled({ compact, open: v })
  const heat = useHeat()
  const scale = heat.scale ? { lo: heat.scale.lo, hi: heat.scale.hi, metric: heat.metric } : null
  if (!open)
    return (
      <div className={`pointer-events-auto absolute left-6 ${compact ? 'bottom-[150px]' : 'bottom-6'}`}>
        <PillButton onClick={() => setOpen(true)}>How to read the map</PillButton>
      </div>
    )
  const opts: { id: ColorBy; label: string }[] = [
    { id: 'co2_kg', label: 'CO₂' },
    { id: 'cost_chf', label: 'Cost' },
    ...(x.clusters && step === 'baseline' ? [{ id: 'cluster' as ColorBy, label: 'Server groups' }] : []),
  ]
  const eu = x.series.get('loc:EU')?.co2_kg.reduce((a, v) => a + v, 0) ?? 0
  return (
    <div className={`pill-shadow pointer-events-auto absolute left-6 w-[264px] rounded-[14px] bg-white p-4 text-[12px] text-body ${compact ? 'bottom-[150px]' : 'bottom-6'}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-[14px] font-semibold text-ink">How to read the map</h3>
        <button onClick={() => setOpen(false)} aria-label="Close" className="text-muted hover:text-ink">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      <div className="mt-2 flex gap-1 rounded-full bg-surface-strong p-1">
        {opts.map((o) => (
          <button
            key={o.id}
            onClick={() => setColorBy(o.id)}
            className={`flex-1 rounded-full px-2 py-1 text-[12px] font-semibold transition ${colorBy === o.id ? 'bg-white text-ink shadow-sm' : 'text-muted'}`}
          >
            {o.label}
          </button>
        ))}
      </div>
      {colorBy === 'cluster' && x.clusters ? (
        <div className="mt-3 space-y-1.5">
          <p className="text-muted">Servers grouped by how they behave over the year (k-means on usage):</p>
          {x.clusters.groups.map((g, i) => (
            <div key={g.id} className="flex items-start gap-2">
              <span className="mt-1 h-3 w-3 shrink-0 rounded-[3px]" style={{ background: CLUSTER_COLORS[i % CLUSTER_COLORS.length] }} />
              <span>
                <span className="font-semibold text-ink">{g.name}</span> · {g.size} servers · {g.share_co2 < 0.01 ? '<1' : Math.round(g.share_co2 * 100)}% of their CO₂
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3">
          <p className="text-muted">
            Colour = {colorBy === 'cost_chf' ? 'cost' : 'CO₂'} per year{step === 'baseline' && month !== null ? ' at this month’s rate' : ''}. Computers: one computer.
          </p>
          <div className="mt-1.5 flex h-3 overflow-hidden rounded-full">
            {HEAT.map((c) => (
              <span key={c} className="flex-1" style={{ background: c }} />
            ))}
          </div>
          {scale && (
            <div className="mt-1 flex justify-between text-[11px] text-muted tabular-nums">
              <span>{fmtMetric(scale.lo, scale.metric)}</span>
              <span>{fmtMetric(scale.hi, scale.metric)}</span>
            </div>
          )}
        </div>
      )}
      <div className="mt-3 flex items-center gap-2">
        <span className="h-3 w-3 rounded-[3px]" style={{ background: NEUTRAL }} />
        <span className="text-muted">Neutral: building and landscape, no cost of their own</span>
      </div>
      <div className="mt-2 flex items-start gap-2">
        <svg viewBox="0 0 24 16" className="mt-0.5 h-3 w-4 shrink-0 text-muted" fill="currentColor">
          <path d="M6 15a5 5 0 01-.5-10A6 6 0 0117 4a4.5 4.5 0 011 11z" />
        </svg>
        <span className="text-muted">
          Cloud = CO₂ of each data centre, bigger and darker = more. Another {fmtMetric(eu, 'co2_kg')} comes from AI and SaaS providers with no stated location.
        </span>
      </div>
      {step === 'baseline' && (
        <div className="mt-2 flex items-center gap-2">
          <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-error text-[10px] font-bold text-white">!</span>
          <span className="text-muted">Pain point found in the data (after the year has played)</span>
        </div>
      )}
      {step === 'forecast' && <p className="mt-2 text-[12px] text-muted">Map: each object follows the forecast trend. Exact numbers in the charts.</p>}
      {(step === 'packages' || step === 'baseline') && <Notes x={x} />}
    </div>
  )
}

/** Due note brevi dei bonus: market-based e ore pulite. */
function Notes({ x }: { x: Extra }) {
  const [open, setOpen] = useState(false)
  if (!x.market && !x.cleanHours) return null
  return (
    <div className="mt-3 border-t border-hairline-soft pt-2">
      <button onClick={() => setOpen(!open)} className="text-[12px] font-semibold text-ink">
        {open ? '−' : '+'} Good to know
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1.5 text-[12px] text-muted">
          {x.market && (
            <li>
              <span className="font-semibold text-ink">On paper vs. on the grid.</span> With supplier mixes (market-based) the same energy counts{' '}
              {fmtMetric(x.market.market_co2, 'co2_kg')} instead of {fmtMetric(x.market.location_co2, 'co2_kg')}. Buying certificates changes the paper, not the grid.
            </li>
          )}
          {x.cleanHours && (
            <li>
              <span className="font-semibold text-ink">Clean hours.</span> Moving flexible jobs to greener hours saves only {fmtMetric(x.cleanHours.saving, 'co2_kg')} a year, against{' '}
              {fmtMetric(x.cleanHours.m01, 'co2_kg')} for pausing dp-dev: where and whether matter more than when.
            </li>
          )}
        </ul>
      )}
    </div>
  )
}

// --- Export ------------------------------------------------------------------------------------------------------

const SUB = `${import.meta.env.BASE_URL}data/real/submission`
const BASELINE_CSV = 'template_baseline_and_assumptions.csv'
const PACKAGE_CSV = 'template_measures_package.csv'

function save(text: string, name: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }))
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let q = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (q) {
      if (c === '"' && text[i + 1] === '"') {
        cell += '"'
        i++
      } else if (c === '"') q = false
      else cell += c
    } else if (c === '"') q = true
    else if (c === ',') {
      row.push(cell)
      cell = ''
    } else if (c === '\n') {
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else if (c !== '\r') cell += c
  }
  if (cell || row.length) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}
const toCsv = (rows: string[][]) => rows.map((r) => r.map((c) => (/[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(',')).join('\n') + '\n'

/** Il file del pacchetto del backend vale per l'obiettivo predefinito; per gli altri si ricompone con le stesse colonne. */
async function packageCsv(x: Extra, goal: string): Promise<string> {
  const text = await (await fetch(`${SUB}/${PACKAGE_CSV}`)).text()
  if (goal === x.defaultGoal) return text
  const rows = parseCsv(text.replace(/^﻿/, ''))
  const [head, ...body] = rows
  const byId = new Map(body.map((r) => [r[0], r]))
  const ids = x.packages[goal]?.measure_ids ?? []
  const out = ids.map((id) => {
    const known = byId.get(id)
    if (known) return known
    const m = x.measures.find((y) => y.id === id)!
    const cells: Record<string, string> = {
      measure_id: m.id,
      description: m.title,
      resource_or_source: m.entity_ids.join('; '),
      change: m.description,
      effort_person_days: String(m.effort_days),
      savings_cost_chf_per_year: String(Math.round(m.savings.cost_chf)),
      savings_energy_kwh_per_year: String(Math.round(m.savings.kwh)),
      savings_co2_kg_location_based: String(Math.round(m.savings.co2_kg)),
      savings_co2_kg_market_based: '',
      risks_and_exceptions: m.risks,
      assumptions_and_sources: 'Pipeline output: output/measures.json',
    }
    return head.map((h) => cells[h] ?? '')
  })
  return '﻿' + toCsv([head, ...out])
}

function ExportButton({ x }: { x: Extra }) {
  const step = useApp((s) => s.step)
  const goalSel = useApp((s) => s.goal)
  const goal = goalSel && x.packages[goalSel] ? goalSel : x.defaultGoal
  const [open, setOpen] = useState(false)
  const baseline = async () => save(await (await fetch(`${SUB}/${BASELINE_CSV}`)).text(), BASELINE_CSV)
  const pkg = async () => save(await packageCsv(x, goal), goal === x.defaultGoal ? PACKAGE_CSV : `template_measures_package_${goal}.csv`)
  if (step === 'baseline') return <PillButton onClick={baseline}>Export baseline (CSV)</PillButton>
  return (
    <div className="relative">
      <PillButton onClick={() => setOpen(!open)}>Export (CSV)</PillButton>
      {open && (
        <div className="pill-shadow absolute top-12 right-0 w-72 rounded-[14px] bg-white p-2 text-[14px]">
          <button onClick={baseline} className="w-full rounded-[8px] px-3 py-2 text-left hover:bg-surface-soft">
            Baseline and assumptions
          </button>
          <button onClick={pkg} className="w-full rounded-[8px] px-3 py-2 text-left hover:bg-surface-soft">
            Measures package · {GOAL_LABEL[goal] ?? goal}
          </button>
          <p className="px-3 pt-1 pb-1 text-[11px] text-muted">The two submission templates of the case, filled in.</p>
        </div>
      )}
    </div>
  )
}

// --- Grafici della previsione --------------------------------------------------------------------------------------

function ForecastCharts({ x, onClose }: { x: Extra; onClose: () => void }) {
  const fc = x.forecast
  if (!fc) return null
  const pkgGoal = GOAL_LABEL[fc.goal] ?? fc.goal
  return (
    <aside className="pill-shadow pointer-events-auto absolute top-6 right-6 flex max-h-[calc(100%-48px)] flex-col overflow-hidden rounded-[14px] bg-white" style={{ width: PANEL_W }}>
      <div className="flex items-start justify-between gap-4 px-6 pt-6">
        <div>
          <div className="text-[13px] text-muted">Sep 2026 – Aug 2027 · forecast</div>
          <h2 className="mt-1 text-[22px] leading-tight font-medium tracking-[-0.44px] text-ink">Without vs. with the package</h2>
        </div>
        <button onClick={onClose} aria-label="Close" className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 pt-3 pb-6 text-[13px] text-body">
        <p className="text-muted">Package «{pkgGoal}» from its start dates; prices and growth already announced are included.</p>
        <LineChart title="CO₂ per month" k="co2_kg" x={x} />
        <LineChart title="Cost per month" k="cost_chf" x={x} />
        <h3 className="mt-6 text-[14px] font-semibold text-ink">Known changes</h3>
        <ul className="mt-1 space-y-1.5">
          {fc.events.map((e) => (
            <li key={e.date + e.label} className="flex gap-2">
              <span className="w-16 shrink-0 text-muted">{MONTH(e.date, { month: 'short', year: '2-digit' })}</span>
              <span>
                {e.label} <span className="text-muted">({e.source})</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}

function LineChart({ title, k, x }: { title: string; k: MetricKey; x: Extra }) {
  const fm = x.forecast!.months
  const W = 360
  const H = 120
  const max = Math.max(...fm.flatMap((m) => [m.without[k], m.with[k]])) * 1.1
  const px = (i: number) => 8 + (i / (fm.length - 1)) * (W - 16)
  const py = (v: number) => H - 16 - (v / max) * (H - 28)
  const path = (key: 'with' | 'without') => fm.map((m, i) => `${i ? 'L' : 'M'}${px(i).toFixed(1)},${py(m[key][k]).toFixed(1)}`).join(' ')
  const sum = (key: 'with' | 'without') => fm.reduce((a, m) => a + m[key][k], 0)
  return (
    <section className="mt-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
        <span className="text-[12px] text-muted">
          year: <span className="line-through">{fmtMetric(sum('without'), k)}</span> → <span className="font-semibold text-primary">{fmtMetric(sum('with'), k)}</span>
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full">
        <line x1="8" x2={W - 8} y1={H - 16} y2={H - 16} stroke="#DDDDDD" />
        <path d={path('without')} fill="none" stroke="#CF4F45" strokeWidth="2" strokeDasharray="4 3" />
        <path d={path('with')} fill="none" stroke="#1F7A57" strokeWidth="2.5" />
        {fm.map((m, i) => (
          <text key={m.month} x={px(i)} y={H - 3} textAnchor="middle" fontSize="9" fill="#6a6a6a">
            {MONTH(m.month)[0]}
          </text>
        ))}
      </svg>
      <div className="mt-1 flex gap-4 text-[11px] text-muted">
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-4 bg-[#CF4F45]" /> without changes
        </span>
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-4 bg-primary" /> with the package
        </span>
      </div>
    </section>
  )
}
