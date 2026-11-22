import { useEffect, useState } from 'react'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'
import type { XHours } from '../data/extra'
import { Chip } from './primitives'

// «Fasce del giorno» (bonus carbon-aware del caso): la CO₂ della rete cambia ora per ora; alcuni job della piattaforma dati
// si possono spostare nelle ore più pulite. Sta nel passo 3 accanto all'AI locale: un'opzione oltre il pacchetto.

const SITE: Record<string, { label: string; color: string }> = {
  CH: { label: 'Zurich', color: '#3B7DD8' },
  DE: { label: 'Frankfurt', color: '#8A5CC8' },
  IE: { label: 'Dublin', color: '#D08A2E' },
}
const hourOf = (t: string | null) => (t ? Number(t.slice(0, 2)) + Number(t.slice(3, 5)) / 60 : 0)

/** Scheda in fondo all'elenco dei pacchetti: il senso in due righe e il bottone per il report. */
export function HoursCard() {
  const h = useApp((s) => s.data?.extra?.hours)
  const open = useApp((s) => s.setHoursOpen)
  if (!h) return null
  const ch = h.stats.CH
  const moved = h.jobs.filter((j) => j.suggested && j.saving != null).length
  return (
    <section className="rounded-[12px] border border-dashed border-hairline px-3.5 py-3">
      <div className="text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">Beyond the package</div>
      <div className="mt-0.5 text-[15px] font-semibold text-ink">Run jobs in cleaner hours?</div>
      <p className="mt-1 text-[12px] leading-[17px] text-body">
        {ch ? `Zurich's grid goes from ${Math.round(ch.min)} to ${Math.round(ch.max)} g CO₂/kWh over a day. ` : ''}
        Moving {moved} flexible jobs saves about <span className="font-semibold text-primary">{fmtMetric(h.saving.mid, 'co2_kg')}</span> a year.
      </p>
      <button onClick={() => open(true)} className="mt-2 rounded-full bg-ink px-3.5 py-1.5 text-[13px] font-semibold text-white">
        Open the report
      </button>
    </section>
  )
}

/** Report: la curva della rete nelle 24 ore, i job spostabili (ora di oggi → ora consigliata) e quanto vale davvero. */
export function HoursReport() {
  const h = useApp((s) => s.data?.extra?.hours)
  const m01 = useApp((s) => s.data?.extra?.cleanHours?.m01)
  const isOpen = useApp((s) => s.hoursOpen)
  const setOpen = useApp((s) => s.setHoursOpen)
  const [season, setSeason] = useState<'year' | 'winter' | 'summer'>('year')
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, setOpen])
  if (!h || !isOpen) return null
  const share = h.baselineCo2 > 0 ? (h.saving.mid / h.baselineCo2) * 100 : 0
  return (
    <div className="step-in pointer-events-auto absolute inset-0 z-50 grid place-items-center bg-ink/25 p-6" onClick={() => setOpen(false)}>
      <article className="pill-shadow flex max-h-full w-full max-w-[1040px] flex-col overflow-hidden rounded-[18px] bg-white" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start justify-between gap-6 border-b border-hairline-soft px-8 pt-7 pb-5">
          <div>
            <div className="text-[13px] text-muted">Advisory · carbon-aware scheduling · not part of the package budget</div>
            <h2 className="mt-1 text-[26px] leading-tight font-semibold tracking-[-0.5px] text-ink">When it runs: cleaner hours of the day</h2>
            <p className="mt-1.5 max-w-[760px] text-[14px] text-body">
              The CO₂ of each kWh changes hour by hour with the power mix. Jobs that may run at any time can wait for a cleaner hour; the others keep their slot.
            </p>
          </div>
          <button onClick={() => setOpen(false)} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-8 py-6">
          <section className="grid grid-cols-3 gap-4">
            <Big label="Saving with the package, per year" value={`−${fmtMetric(h.saving.mid, 'co2_kg')}`} sub={`range ${fmtMetric(h.saving.low, 'co2_kg')} – ${fmtMetric(h.saving.high, 'co2_kg')}`} />
            <Big label="Share of the footprint" value={`${share.toFixed(1)}%`} sub={`of ${fmtMetric(h.baselineCo2, 'co2_kg')} a year`} />
            {m01 ? <Big label="Compare: moving dp-dev to Zurich" value={`−${fmtMetric(m01, 'co2_kg')}`} sub="already in the package (M-01)" /> : <div />}
          </section>
          <p className="mt-3 text-[13px] text-body">
            <span className="font-semibold text-ink">Where and whether matter more than when.</span> Shifting hours helps a little, mostly on the German grid; switching off and moving to a cleaner
            grid do far more. {h.note}
          </p>

          <section className="mt-7">
            <div className="flex items-center justify-between">
              <h3 className="text-[18px] font-semibold text-ink">CO₂ of the grid over a workday</h3>
              <div className="flex rounded-full bg-surface-soft p-0.5 text-[12px]">
                {(['year', 'winter', 'summer'] as const).map((s) => (
                  <button key={s} onClick={() => setSeason(s)} className={`rounded-full px-3 py-1 font-semibold capitalize ${season === s ? 'bg-white text-ink shadow-sm' : 'text-muted'}`}>
                    {s === 'year' ? 'Whole year' : s}
                  </button>
                ))}
              </div>
            </div>
            <DayChart h={h} season={season} />
            <p className="mt-1 text-[11px] text-muted">Source: {h.source}</p>
          </section>

          <Jobs h={h} />
        </div>
      </article>
    </div>
  )
}

function Big({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-[10px] bg-surface-soft px-4 py-3">
      <div className="text-[12px] text-muted">{label}</div>
      <div className="text-[24px] font-semibold tracking-[-0.4px] text-ink tabular-nums">{value}</div>
      <div className="text-[11px] text-muted">{sub}</div>
    </div>
  )
}

/**
 * Curva di ogni sede nelle 24 ore e, sotto, una riga per ogni job spostabile sullo stesso asse delle ore:
 * grigio quando gira oggi, verde quando conviene farlo girare (dopo il pacchetto i job di dp-dev sono a Zurigo).
 */
function DayChart({ h, season }: { h: XHours; season: 'year' | 'winter' | 'summer' }) {
  const lines = h.profiles.filter((p) => p.season === season && SITE[p.loc])
  const moved = h.jobs.filter((j) => j.suggested && j.saving != null)
  const W = 960
  const L = 170
  const CH = 190
  const lane = 22
  const H = CH + 30 + moved.length * lane + 8
  const max = Math.max(...lines.flatMap((l) => l.values)) * 1.08 || 1
  const px = (hr: number) => L + (hr / 24) * (W - L - 12)
  const py = (v: number) => CH - 8 - (v / max) * (CH - 24)
  const bar = (from: number, dur: number, y: number, fill: string) => {
    // Un job che passa la mezzanotte continua dall'inizio dell'asse.
    const a = Math.min(24 - from, dur)
    return (
      <>
        <rect x={px(from)} y={y} width={Math.max(3, px(from + a) - px(from))} height={7} rx={2} fill={fill} />
        {dur > a && <rect x={px(0)} y={y} width={Math.max(3, px(dur - a) - px(0))} height={7} rx={2} fill={fill} />}
      </>
    )
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full">
      {[0, 6, 12, 18, 24].map((t) => (
        <g key={t}>
          <line x1={px(t)} x2={px(t)} y1={8} y2={H - 4} stroke="#EBEBEB" />
          <text x={px(t)} y={CH + 14} textAnchor="middle" fontSize="11" fill="#6A6A6A">
            {String(t).padStart(2, '0')}:00
          </text>
        </g>
      ))}
      <text x={L - 8} y={py(max / 1.08) + 4} textAnchor="end" fontSize="11" fill="#8A8A8A">
        {Math.round(max / 1.08)} g/kWh
      </text>
      <text x={L - 8} y={CH - 8} textAnchor="end" fontSize="11" fill="#8A8A8A">
        0
      </text>
      {lines.map((l) => (
        <g key={l.loc}>
          <path d={l.values.map((v, i) => `${i ? 'L' : 'M'}${px(i + 0.5).toFixed(1)},${py(v).toFixed(1)}`).join(' ')} fill="none" stroke={SITE[l.loc].color} strokeWidth="2.5" />
          <text x={px(23.5) + 4} y={py(l.values[23]) - 6} textAnchor="end" fontSize="12" fontWeight="600" fill={SITE[l.loc].color}>
            {SITE[l.loc].label}
          </text>
        </g>
      ))}
      {moved.map((j, i) => {
        const y = CH + 30 + i * lane
        return (
          <g key={j.name}>
            <text x={L - 8} y={y + 10} textAnchor="end" fontSize="12" fill="#222222">
              {j.name}
            </text>
            {/* Due righe sottili per job: sopra quando gira oggi, sotto l'ora più pulita (così non si coprono). */}
            {bar(hourOf(j.start), j.hours, y, '#C9C4BB')}
            {bar(hourOf(j.suggested), j.hours, y + 8, '#1F7A57')}
          </g>
        )
      })}
    </svg>
  )
}

function Jobs({ h }: { h: XHours }) {
  const moved = h.jobs.filter((j) => j.suggested && j.saving != null)
  const kept = h.jobs.filter((j) => !(j.suggested && j.saving != null))
  return (
    <section className="mt-6 grid grid-cols-[1.1fr_1fr] gap-8">
      <div>
        <h3 className="text-[18px] font-semibold text-ink">Jobs that can move</h3>
        <div className="mt-1 flex gap-4 text-[11px] text-muted">
          <span className="flex items-center gap-1">
            <span className="h-2 w-3 rounded-[2px] bg-[#C9C4BB]" /> today
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-3 rounded-[2px] bg-primary" /> cleaner hour
          </span>
        </div>
        <table className="mt-2 w-full text-left text-[13px]">
          <tbody>
            {moved.map((j) => (
              <tr key={j.name} className="border-b border-hairline-soft">
                <td className="py-1.5 font-semibold text-ink">{j.name}</td>
                <td className="py-1.5 text-muted">{SITE[j.locAfter ?? j.loc]?.label ?? j.loc}</td>
                <td className="py-1.5 text-body tabular-nums">
                  {j.start} → <span className="font-semibold text-primary">{j.suggested}</span>
                </td>
                <td className="py-1.5 text-right font-semibold text-primary tabular-nums">−{fmtMetric(j.saving ?? 0, 'co2_kg')}/yr</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <h3 className="text-[18px] font-semibold text-ink">Jobs that keep their slot</h3>
        <ul className="mt-2 space-y-1.5 text-[13px]">
          {kept.map((j) => (
            <li key={j.name} className="flex items-start justify-between gap-3 border-b border-hairline-soft pb-1.5">
              <span>
                <span className="font-semibold text-ink">{j.name}</span> <span className="text-muted">· {j.start}</span>
                <span className="block text-[12px] text-muted">{j.reason || 'Already in a clean hour.'}</span>
              </span>
              <span className="shrink-0 whitespace-nowrap">
                <Chip tone={j.locked ? 'lock' : 'neutral'}>{j.locked ? 'Fixed' : j.window === 'flexible' ? 'No gain' : 'By arrangement'}</Chip>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
