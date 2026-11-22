import { useMemo, useState } from 'react'
import { useApp } from '../store'
import { DEPARTMENTS, DEPT_LABEL, makeCtx } from '../data/twin'
import { fmtMetric } from '../data/compute'
import type { Extra, XMeasure } from '../data/extra'
import type { Metrics } from '../data/types'
import { GOAL_HINT, GOAL_LABEL, deptUnits } from '../data/usage'
import { deptSaved, goalOf, goalOrder, planIds, savedByRaw, totalSaved } from '../data/plan'
import { useCo2 } from '../data/co2'
import { LocalAiCard } from './LocalAiReport'
import { HoursCard } from './HoursReport'
import { Co2Switch } from './Co2Switch'
import { MARK_COLOR, MARK_LABEL, useHeat, type Mark } from '../scene/twin/heat'
import { measureTag } from './UnitPanel'
import { Chip } from './primitives'

/** Larghezza del pannello dei pacchetti (a sinistra, passo 3): la scena lascia questo spazio libero. */
export const PKG_W = 360

const TYPE_LABEL: Record<string, string> = {
  schedule: 'Schedule',
  rightsize: 'Right-size',
  decommission: 'Switch off',
  licence: 'Licences',
  relocate: 'Move region',
  model_switch: 'Smaller AI model',
  pipeline: 'Pipeline',
  storage: 'Storage',
  other: 'Other',
}

const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0)
// Il risparmio che conta di più: CO₂ se c'è, altrimenti franchi.
const saving = (m: Metrics) => (m.co2_kg >= 1 ? `−${fmtMetric(m.co2_kg, 'co2_kg')}` : `−${fmtMetric(m.cost_chf, 'cost_chf')}`)

/**
 * Passo 3, a sinistra: le strategie del backend in colonna. Quella scelta si apre con le sue misure:
 * tipo, stato, due righe di spiegazione e un interruttore per tenerla o toglierla (human in the loop).
 * Cliccando una misura la scena mostra il reparto o l'isola che tocca.
 */
export function PackagesPanel({ x }: { x: Extra }) {
  const data = useApp((s) => s.data)!
  const goalSel = useApp((s) => s.goal)
  const setGoal = useApp((s) => s.setGoal)
  const dropped = useApp((s) => s.dropped)
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const goal = goalOf(x, goalSel)
  // Le misure della strategia scelta si possono chiudere, così si vedono tutte le strategie insieme.
  const [open, setOpen] = useState(true)
  const co2 = useCo2(ctx)
  const reduction = (ids: string[]) => {
    const t = totalSaved(co2.saved(savedByRaw(ctx, x, ids)))
    return { co2: pct(t.co2_kg, x.baseline.co2_kg * co2.company), cost: pct(t.cost_chf, x.baseline.cost_chf) }
  }

  // Colonna di sinistra: il pannello (alto quanto il suo contenuto) e, in fondo, i totali del piano.
  // Così la scena non si sposta né si rimpicciolisce per far posto ai numeri.
  return (
    <div className="step-in pointer-events-none absolute top-3 bottom-6 left-6 flex flex-col gap-3" style={{ width: PKG_W }}>
    <aside className="pill-shadow pointer-events-auto flex min-h-0 shrink flex-col overflow-hidden rounded-[14px] bg-white">
      <div className="px-5 pt-5 pb-2">
        <h2 className="text-[20px] leading-tight font-semibold tracking-[-0.3px] text-ink">Packages</h2>
        <p className="mt-1 text-[13px] text-muted">Pick a strategy, then keep or drop each measure.</p>
      </div>
      <div className="scroll-thin min-h-0 space-y-2 overflow-y-auto px-3 pb-3">
        {goalOrder(x).map((g) => {
          const on = g === goal
          const r = reduction(planIds(x, g, on ? dropped : []))
          return (
            <section key={g} className={`rounded-[12px] border transition ${on ? 'border-ink' : 'border-hairline-soft hover:border-hairline'}`}>
              <button
                onClick={() => {
                  if (on) setOpen(!open)
                  else {
                    setGoal(g)
                    setOpen(true)
                  }
                }}
                aria-expanded={on && open}
                className="flex w-full items-start justify-between gap-3 px-3.5 py-3 text-left"
              >
                <span className="flex min-w-0 items-start gap-2">
                  <svg viewBox="0 0 24 24" className={`mt-1 h-3.5 w-3.5 shrink-0 text-muted transition ${on && open ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                    <path d="M9 6l6 6-6 6" />
                  </svg>
                  <span className="min-w-0">
                  <span className="block text-[15px] font-semibold text-ink">{GOAL_LABEL[g] ?? g}</span>
                  <span className="block text-[12px] text-muted">{GOAL_HINT[g] ?? ''}</span>
                  </span>
                </span>
                <span className="shrink-0 text-right text-[12px] leading-[17px] tabular-nums">
                  <span className="block font-semibold text-primary">CO₂ −{r.co2}%</span>
                  <span className="block text-muted">cost −{r.cost}%</span>
                </span>
              </button>
              {on && open && <MeasureList x={x} goal={g} />}
            </section>
          )
        })}
        <LocalAiCard />
        <HoursCard />
      </div>
      <MapColors />
    </aside>
      <div className="mt-auto shrink-0">
        <PlanTotals x={x} />
      </div>
    </div>
  )
}

function MeasureList({ x, goal }: { x: Extra; goal: string }) {
  const data = useApp((s) => s.data)!
  const dropped = useApp((s) => s.dropped)
  const toggle = useApp((s) => s.toggleDropped)
  const focus = useApp((s) => s.focus)
  const setFocus = useApp((s) => s.setFocus)
  const heat = useHeat()
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const co2 = useCo2(ctx)
  const pkg = x.packages[goal]
  const ms = (pkg?.measure_ids ?? []).map((id) => x.measures.find((m) => m.id === id)).filter((m): m is XMeasure => !!m)
  const kept = ms.filter((m) => !dropped.includes(m.id)).length

  // Reparto da mostrare per una misura: quello con più unità toccate (i computer contano di più).
  const roomFor = (id: string): string | null | undefined => {
    const hit = new Set(heat.unitsOfMeasure(id))
    if (!hit.size) return undefined
    let best: string | null = null
    let score = 0
    for (const r of DEPARTMENTS) {
      const s = deptUnits(ctx, r).reduce((a, u) => a + (hit.has(u) ? (u.startsWith('pcs:') ? 3 : 1) : 0), 0)
      if (s > score) [best, score] = [r, s]
    }
    return best ?? undefined
  }

  return (
    <div className="border-t border-hairline-soft px-2 pt-1 pb-2">
      <div className="flex flex-wrap items-center gap-1.5 px-1.5 py-1.5 text-[12px] text-muted">
        {kept} of {ms.length} measures kept
        {!dropped.length && pkg?.meets.co2 && pkg.meets.cost && pkg.meets.budget && <Chip tone="primary">All targets met</Chip>}
      </div>
      <ul className="space-y-1">
        {ms.map((m) => {
          const off = dropped.includes(m.id)
          const open = focus === m.id
          const tag = measureTag(m)
          return (
            <li key={m.id} className={`rounded-[10px] transition ${open ? 'bg-surface-soft ring-1 ring-ink/15' : 'hover:bg-surface-soft'}`}>
              <div className="flex items-start gap-2.5 px-2 py-2">
                <button
                  onClick={() => toggle(m.id)}
                  aria-label={off ? 'Keep this measure' : 'Drop this measure'}
                  title={off ? 'Keep this measure' : 'Drop this measure'}
                  className={`relative mt-0.5 h-5 w-8 shrink-0 rounded-full transition ${off ? 'bg-hairline' : 'bg-primary'}`}
                >
                  <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${off ? 'left-0.5' : 'left-[14px]'}`} />
                </button>
                <button onClick={() => setFocus(open ? null : m.id, open ? undefined : roomFor(m.id))} className={`min-w-0 flex-1 text-left ${off ? 'opacity-55' : ''}`}>
                  <span className="flex items-start justify-between gap-2">
                    <span className="text-[13px] leading-snug font-semibold text-ink">{m.title}</span>
                    <span className={`shrink-0 text-[12px] font-semibold tabular-nums ${off ? 'text-muted line-through' : 'text-primary'}`}>{saving({ ...m.savings, co2_kg: co2.measure(m) })}</span>
                  </span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    <Chip>{TYPE_LABEL[m.type] ?? m.type}</Chip>
                    <Chip tone={tag.tone}>{tag.label}</Chip>
                  </span>
                  <span className="mt-1 line-clamp-2 block text-[12px] leading-[17px] text-body">{m.description}</span>
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** In fondo al pannello: i colori della mappa. */
function MapColors() {
  const marks: Mark[] = ['driver', 'waste', 'none', 'kept']
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-hairline-soft px-5 py-3 text-[11px] text-body">
      {marks.map((m) => (
        <span key={m} className="flex items-center gap-1.5 whitespace-nowrap">
          <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: MARK_COLOR[m] }} />
          {m === 'kept' ? 'Kept on purpose' : MARK_LABEL[m]}
        </span>
      ))}
    </div>
  )
}

/**
 * In alto a destra, passo 3: quanto costa l'anno con il pacchetto e le scelte fatte (azienda, oppure il reparto aperto).
 * Cambia a ogni misura tolta o rimessa e a ogni cambio di strategia.
 */
export function PlanTotals({ x }: { x: Extra }) {
  const room = useApp((s) => s.room)
  const data = useApp((s) => s.data)!
  const goalSel = useApp((s) => s.goal)
  const heat = useHeat()
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const co2 = useCo2(ctx)
  const saved = useMemo(() => co2.saved(savedByRaw(ctx, x, heat.active)), [ctx, x, heat.active, co2])
  const d = room ? data.summary.departments.find((y) => y.id === room) : undefined
  // CO₂ nella vista scelta (location- o market-based).
  const before: Metrics = d ? { ...d.metrics, co2_kg: d.metrics.co2_kg * co2.dept(room!) } : { ...x.baseline, co2_kg: x.baseline.co2_kg * co2.company }
  const cut = d && room ? deptSaved(ctx, saved, room) : totalSaved(saved)
  const goal = goalOf(x, goalSel)
  const rows = [
    { k: 'cost_chf' as const, label: 'Cost' },
    { k: 'kwh' as const, label: 'Energy' },
    { k: 'co2_kg' as const, label: 'CO₂' },
  ]
  return (
    <div className="pill-shadow pointer-events-auto w-full rounded-[14px] bg-white px-5 py-4">
      <div className="text-[13px] text-muted">
        <span className="font-semibold text-ink">{GOAL_LABEL[goal] ?? goal}</span> · {d ? (DEPT_LABEL[room!] ?? d.label) : 'whole company'}, per year
        {co2.market && ' · CO₂ market-based'}
      </div>
      <div className="mt-2 space-y-1.5">
        {rows.map(({ k, label }) => {
          const after = Math.max(0, before[k] - cut[k])
          return (
            <div key={k} className="grid grid-cols-[56px_1fr_auto] items-baseline gap-2">
              <span className="text-[13px] text-muted">{label}</span>
              <span className="whitespace-nowrap tabular-nums">
                <span className="text-[12px] text-muted line-through">{fmtMetric(before[k], k)}</span>{' '}
                <span className="text-[20px] font-semibold tracking-[-0.3px] text-ink">{fmtMetric(after, k)}</span>
              </span>
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[12px] font-semibold text-primary tabular-nums">{cut[k] > 0 ? `−${pct(cut[k], before[k])}%` : '0%'}</span>
            </div>
          )
        })}
      </div>
      <div className="mt-2.5 border-t border-hairline-soft pt-2">
        <Co2Switch />
      </div>
    </div>
  )
}

/** In alto al centro, con una misura aperta: la scena senza o con quella misura. */
export function CompareToggle({ x }: { x: Extra }) {
  const focus = useApp((s) => s.focus)
  const dropped = useApp((s) => s.dropped)
  const before = useApp((s) => s.compareBefore)
  const set = useApp((s) => s.setCompareBefore)
  if (!focus) return null
  const m = x.measures.find((y) => y.id === focus)
  if (!m) return null
  if (dropped.includes(focus))
    return <div className="pill-shadow flex h-11 items-center rounded-full bg-white px-4 text-[13px] text-muted">«{m.title}» is dropped: turn it back on to see its effect</div>
  return (
    <div className="pill-shadow pointer-events-auto flex h-11 items-center gap-1 rounded-full bg-white p-1">
      <span className="max-w-[260px] truncate px-3 text-[13px] font-medium text-muted">{m.title}</span>
      {[true, false].map((b) => (
        <button
          key={String(b)}
          onClick={() => set(b)}
          className={`h-9 rounded-full px-4 text-[13px] font-semibold whitespace-nowrap transition ${before === b ? 'bg-ink text-white' : 'text-ink hover:bg-surface-soft'}`}
        >
          {b ? 'Before' : 'After'}
        </button>
      ))}
    </div>
  )
}
