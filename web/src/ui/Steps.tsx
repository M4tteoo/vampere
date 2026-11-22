import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import { makeCtx } from '../data/twin'
import { islandsOf } from '../scene/twin/Allocation'
import { fmtMetric } from '../data/compute'
import type { Extra } from '../data/extra'
import type { MetricKey, Metrics } from '../data/types'
import { GOAL_LABEL } from '../data/usage'
import { forecastPlan, goalOf, planIds, savedByRaw, totalSaved, type ForecastMonth } from '../data/plan'
import { PackagesPanel } from './PackagesPanel'
import { useCo2 } from '../data/co2'
import { MARK_COLOR, MARK_LABEL, type Mark } from '../scene/twin/heat'
import { BEHAVIOUR_TEXT, BehaviourIcon } from './Behaviour'
import { PANEL_W } from '../scene/Scene'

const MONTH = (iso: string, opts: Intl.DateTimeFormatOptions = { month: 'short' }) => new Date(iso).toLocaleDateString('en-GB', opts)
export const heatStep = (step: string) => step === 'baseline' || step === 'packages' || step === 'forecast'

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
  const charts = useApp((s) => s.chartsOpen)
  const setCharts = useApp((s) => s.setChartsOpen)
  // Il bottone dell'anno fa crescere le nuvole: senza isole (es. HR) non ha senso.
  const data = useApp((s) => s.data)!
  const hasIslands = useMemo(() => !!room && islandsOf(makeCtx(data, []), room).length > 0, [data, room])
  if (!x || !heatStep(step)) return null
  // Cambiando passo i comandi compaiono con una breve dissolvenza (la scena intanto cambia colori e posizione).
  return (
    <div key={step} className="step-in pointer-events-none absolute inset-0">
      {step === 'packages' && <PackagesPanel x={x} />}
      <div className="pointer-events-auto absolute top-3 left-1/2 -translate-x-1/2">
        {step === 'baseline' && hasIslands && <YearButton months={x.months} />}
        {step === 'forecast' && <ForecastBar x={x} />}
      </div>
      {/* L'export sta nella barra in alto (Header). Subito sotto, dentro un reparto: le misure proposte (riducono le nuvole). */}
      {step === 'baseline' && room && (
        <div className="pointer-events-auto absolute top-3 right-6">
          <MeasuresToggle />
        </div>
      )}
      {/* Sempre visibile, allineato alla barra dei mesi: apre i grafici al posto della scheda di un oggetto (e li richiude). */}
      {step === 'forecast' && (
        <div className="pointer-events-auto absolute top-3 right-6">
          <PillButton onClick={() => setCharts(!charts)}>{charts ? 'Hide the charts' : 'Show the charts'}</PillButton>
        </div>
      )}
      {step === 'forecast' && charts && <ForecastCharts x={x} onClose={() => setCharts(false)} />}
      {/* Passo 3: i totali del piano in un blocco proprio in alto a destra (niente schede a destra: sarebbero ripetizioni). */}
      {!room && step === 'forecast' && <ResultPill x={x} />}
    </div>
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

/** Un bottone: le nuvole si riempiono mese per mese con la CO₂ dell'anno di baseline. */
function YearButton({ months }: { months: string[] }) {
  const month = useApp((s) => s.month)
  const playing = useApp((s) => s.playing)
  const play = useApp((s) => s.play)
  return (
    <button onClick={play} disabled={playing} className="pill-shadow flex items-center gap-3 rounded-full bg-white py-2 pr-5 pl-2 text-[14px] font-medium text-ink">
      <span className="grid h-8 w-8 place-items-center rounded-full bg-ink text-white">
        {playing ? (
          <span className="h-2 w-2 rounded-full bg-white" />
        ) : (
          <svg viewBox="0 0 24 24" className="ml-0.5 h-3.5 w-3.5" fill="currentColor">
            <path d="M7 5l12 7-12 7z" />
          </svg>
        )}
      </span>
      {playing && month !== null ? (
        <span className="tabular-nums">
          {MONTH(months[month], { month: 'long', year: 'numeric' })} <span className="text-muted">· emissions so far</span>
        </span>
      ) : (
        'Watch the emissions grow over the year'
      )}
    </button>
  )
}

function MeasuresToggle() {
  const on = useApp((s) => s.showMeasures)
  const set = useApp((s) => s.setShowMeasures)
  return (
    <button
      onClick={() => set(!on)}
      className="pill-shadow flex items-center gap-3 rounded-full bg-white py-2 pr-2 pl-4 text-[14px] font-medium text-ink disabled:text-muted-soft"
    >
      Show proposed measures
      <span className={`relative h-6 w-10 rounded-full transition ${on ? 'bg-primary' : 'bg-hairline'}`}>
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
      </span>
    </button>
  )
}

function ForecastBar({ x }: { x: Extra }) {
  const month = useApp((s) => s.month)
  const playing = useApp((s) => s.playing)
  const pause = useApp((s) => s.pause)
  const resume = useApp((s) => s.resume)
  const setMonth = useApp((s) => s.setMonth)
  const fm = x.forecast?.months ?? []
  return (
    <div className="flex items-center gap-2">
      <div className="pill-shadow flex items-center gap-3 rounded-full bg-white py-2 pr-3 pl-2">
        {/* Play / pausa: si ferma sul mese mostrato e riparte da lì (dall'inizio se l'anno è finito). */}
        <button onClick={playing ? pause : resume} aria-label={playing ? 'Pause' : 'Play'} className="grid h-9 w-9 place-items-center rounded-full bg-ink text-white">
          {playing ? (
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor">
              <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" />
            </svg>
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
  const monthly = useMemo(() => {
    const out = x.months.map(() => ({ cost_chf: 0, kwh: 0, co2_kg: 0 }) as Metrics)
    for (const loc of ['CH', 'DE', 'IE', 'EU']) {
      const s = x.series.get(`loc:${loc}`)
      if (!s) continue
      for (const k of ['cost_chf', 'kwh', 'co2_kg'] as MetricKey[]) s[k].forEach((v, i) => (out[i][k] += v))
    }
    return out
  }, [x])
  const dropped = useApp((s) => s.dropped)
  const data = useApp((s) => s.data)!
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const goal = goalOf(x, goalSel)
  const pkg = x.packages[goal]
  const cv = useCo2(ctx)
  // Previsione con la CO₂ nella vista scelta (market-based: fattore medio dell'azienda).
  const fm = useMemo(() => (step === 'forecast' ? scaleCo2(forecastPlan(ctx, x, goal, dropped), cv.company) : []), [step, ctx, x, goal, dropped, cv])
  const cut = useMemo(() => (step === 'packages' ? totalSaved(savedByRaw(ctx, x, planIds(x, goal, dropped))) : null), [step, ctx, x, goal, dropped])
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
          <span className="text-muted">
            So far, {MONTH(x.months[0], { month: 'short', year: 'numeric' })} – {MONTH(x.months[month], { month: 'short', year: 'numeric' })}
          </span>{' '}
          <span className="font-semibold text-ink tabular-nums">
            {line(monthly.slice(0, month + 1).reduce((a, m) => ({ cost_chf: a.cost_chf + m.cost_chf, kwh: a.kwh + m.kwh, co2_kg: a.co2_kg + m.co2_kg }), { cost_chf: 0, kwh: 0, co2_kg: 0 }))}
          </span>
        </>
      )
  } else if (step === 'packages' && pkg && cut) {
    // Totali con le scelte del pannello: cambiano a ogni misura tolta o rimessa.
    const after: Metrics = { cost_chf: x.baseline.cost_chf - cut.cost_chf, kwh: x.baseline.kwh - cut.kwh, co2_kg: x.baseline.co2_kg - cut.co2_kg }
    const pair = (k: MetricKey) => (
      <span className="whitespace-nowrap">
        <span className="text-muted line-through">{fmtMetric(x.baseline[k], k)}</span> → <span className="font-semibold text-primary">{fmtMetric(after[k], k)}</span>
      </span>
    )
    body = (
      <span className="flex flex-wrap items-center justify-center gap-x-4">
        <span className="font-semibold text-ink">{GOAL_LABEL[goal] ?? goal}, per year</span>
        {pair('cost_chf')}
        {pair('co2_kg')}
      </span>
    )
  } else if (step === 'forecast' && x.forecast && fm.length) {
    // Differenza fra i due lati dall'inizio della simulazione al mese mostrato: quanto fa risparmiare il pacchetto.
    const upTo = month === null ? fm.length : month + 1
    const tot = (k: 'with' | 'without') =>
      fm.slice(0, upTo).reduce((a, m) => ({ cost_chf: a.cost_chf + m[k].cost_chf, kwh: a.kwh + m[k].kwh, co2_kg: a.co2_kg + m[k].co2_kg }), { cost_chf: 0, kwh: 0, co2_kg: 0 })
    const w = tot('with')
    const wo = tot('without')
    const cut = (k: MetricKey) => (
      <span className="whitespace-nowrap">
        <span className="font-semibold text-primary tabular-nums">−{fmtMetric(Math.max(0, wo[k] - w[k]), k)}</span>
        <span className="text-muted"> ({wo[k] > 0 ? Math.round(((wo[k] - w[k]) / wo[k]) * 100) : 0}%)</span>
      </span>
    )
    body = (
      <span className="flex flex-wrap items-center justify-center gap-x-4">
        <span className="font-semibold text-ink">
          Saved so far
          <span className="font-normal text-muted">
            {' · '}
            {upTo > 1 && `${MONTH(fm[0].month, { month: 'short', year: 'numeric' })} – `}
            {MONTH(fm[upTo - 1].month, { month: 'short', year: 'numeric' })}
          </span>
        </span>
        {cut('cost_chf')}
        {cut('co2_kg')}
      </span>
    )
  }
  if (!body) return null
  return (
    <div
      className="pill-shadow pointer-events-auto absolute bottom-6 left-1/2 max-w-[56%] -translate-x-1/2 rounded-[22px] bg-white px-5 py-3 text-center text-[14px]"
      // Passo 3: centrata nello spazio a destra del pannello dei pacchetti.
      style={step === 'packages' ? { left: 'calc(50% + 192px)' } : undefined}
    >
      {body}
    </div>
  )
}

/** Legenda, sempre in basso a sinistra. Nella pianta solo rosso e arancio (il senso dei colori); nel reparto completa. */
export function Legend({ compact, marks: only }: { compact: boolean; marks?: Mark[] }) {
  const x = useApp((s) => s.data?.extra)!
  const [open, setOpen] = useState(true)
  if (compact)
    return (
      <ul className="pill-shadow pointer-events-none space-y-0.5 rounded-[14px] bg-white px-4 py-3 text-[11px] leading-[16px] text-body">
        {(only ?? (['driver', 'waste'] as Mark[])).map((m) => (
          <li key={m} className="flex items-center gap-2 whitespace-nowrap">
            <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: MARK_COLOR[m] }} />
            {MARK_LABEL[m]}
          </li>
        ))}
      </ul>
    )
  if (!open)
    return (
      <div className="pointer-events-auto">
        <PillButton onClick={() => setOpen(true)}>How to read the map</PillButton>
      </div>
    )
  const marks: Mark[] = ['driver', 'waste', 'none', 'kept']
  return (
    <div className="pill-shadow pointer-events-auto relative flex w-[260px] flex-col gap-2 rounded-[14px] bg-white py-3 pr-9 pl-4 text-[11px] leading-[16px] text-body">
      <button onClick={() => setOpen(false)} aria-label="Close" className="absolute top-2.5 right-3 text-muted hover:text-ink">
        <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
      <ul className="space-y-0.5">
        {marks.map((m) => (
          <li key={m} className="flex items-center gap-2 whitespace-nowrap">
            <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: MARK_COLOR[m] }} />
            {MARK_LABEL[m]}
          </li>
        ))}
      </ul>
      <ul className="space-y-0.5 border-t border-hairline-soft pt-2">
        <li className="flex items-center gap-2 whitespace-nowrap">
          <svg viewBox="0 0 24 16" className="h-2.5 w-3.5 shrink-0 text-muted" fill="currentColor">
            <path d="M6 15a5 5 0 01-.5-10A6 6 0 0117 4a4.5 4.5 0 011 11z" />
          </svg>
          Cloud: CO₂ of the data centre
        </li>
        {x.clusters &&
          (['idle', 'light', 'steady', 'demand'] as const).map((k) => (
            <li key={k} className="flex items-center gap-2 whitespace-nowrap text-muted">
              <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full bg-white text-ink ring-1 ring-hairline">
                <BehaviourIcon kind={k} className="h-2.5 w-2.5" />
              </span>
              {BEHAVIOUR_TEXT[k]}
            </li>
          ))}
      </ul>
    </div>
  )
}

/** CO₂ dei mesi di previsione moltiplicata per un fattore (vista market-based). */
function scaleCo2(fm: ForecastMonth[], k: number): ForecastMonth[] {
  if (k === 1) return fm
  return fm.map((m) => ({ ...m, without: { ...m.without, co2_kg: m.without.co2_kg * k }, with: { ...m.with, co2_kg: m.with.co2_kg * k } }))
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

/** Il file del pacchetto del backend vale per l'obiettivo predefinito intero; altrimenti (altro obiettivo, misure tolte) si ricompone. */
async function packageCsv(x: Extra, goal: string, dropped: string[]): Promise<string> {
  const text = await (await fetch(`${SUB}/${PACKAGE_CSV}`)).text()
  if (goal === x.defaultGoal && !dropped.length) return text
  const rows = parseCsv(text.replace(/^﻿/, ''))
  const [head, ...body] = rows
  const byId = new Map(body.map((r) => [r[0], r]))
  const ids = (x.packages[goal]?.measure_ids ?? []).filter((id) => !dropped.includes(id))
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

export function ExportButton({ x }: { x: Extra }) {
  const step = useApp((s) => s.step)
  const goalSel = useApp((s) => s.goal)
  const dropped = useApp((s) => s.dropped)
  const goal = goalOf(x, goalSel)
  const [open, setOpen] = useState(false)
  const baseline = async () => save(await (await fetch(`${SUB}/${BASELINE_CSV}`)).text(), BASELINE_CSV)
  const pkg = async () => save(await packageCsv(x, goal, dropped), goal === x.defaultGoal && !dropped.length ? PACKAGE_CSV : `template_measures_package_${goal}${dropped.length ? '_edited' : ''}.csv`)
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
            {dropped.length ? ' (your version)' : ''}
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
  const goalSel = useApp((s) => s.goal)
  const dropped = useApp((s) => s.dropped)
  const data = useApp((s) => s.data)!
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const cv = useCo2(ctx)
  const fm = useMemo(() => scaleCo2(forecastPlan(ctx, x, goalOf(x, goalSel), dropped), cv.company), [ctx, x, goalSel, dropped, cv])
  if (!fc) return null
  const pkgGoal = GOAL_LABEL[goalOf(x, goalSel)] ?? goalOf(x, goalSel)
  return (
    <aside className="step-in pill-shadow pointer-events-auto absolute top-[68px] right-6 flex max-h-[calc(100%-92px)] flex-col overflow-hidden rounded-[14px] bg-white" style={{ width: PANEL_W }}>
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
        <p className="text-muted">Package «{pkgGoal}»{dropped.length ? ' with your changes' : ''}, from its start dates; prices and growth already announced are included.</p>
        <LineChart title="CO₂ per month" k="co2_kg" fm={fm} />
        <LineChart title="Cost per month" k="cost_chf" fm={fm} />
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

function LineChart({ title, k, fm }: { title: string; k: MetricKey; fm: ForecastMonth[] }) {
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
