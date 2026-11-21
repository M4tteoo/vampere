import { useApp, type Mode } from '../store'
import { METRIC_LABEL } from '../data/compute'
import type { MetricKey } from '../data/types'
import { exportCsvs } from './exportCsv'

/** Le quattro fasi del caso, come le «schede prodotto» di Airbnb (Homes / Experiences / Services). */
export const MODES: { id: Mode; label: string; icon: string; hint: string }[] = [
  { id: 'connect', label: 'Connetti', icon: '📥', hint: 'Dati unificati e quadro d’insieme' },
  { id: 'find', label: 'Scopri', icon: '🔎', hint: 'Driver e sprechi' },
  { id: 'decide', label: 'Decidi', icon: '🎚️', hint: 'Misure e pacchetto' },
  { id: 'limits', label: 'Limiti', icon: '🛡️', hint: 'Finestre, blocchi, decisioni umane' },
]

export function Nav() {
  const data = useApp((s) => s.data)!
  const mode = useApp((s) => s.mode)
  const setMode = useApp((s) => s.setMode)
  const metric = useApp((s) => s.metric)
  const setMetric = useApp((s) => s.setMetric)
  const active = useApp((s) => s.active)
  const tour = useApp((s) => s.tour)
  const setTour = useApp((s) => s.setTour)

  return (
    <header className="relative z-40 flex h-20 shrink-0 items-center justify-between border-b border-hairline bg-white px-6">
      <div className="flex min-w-56 items-center gap-2.5">
        <Leaf />
        <div className="leading-tight">
          <div className="text-[18px] font-semibold tracking-tight text-primary">greenops</div>
          <div className="text-[12px] text-muted">Basel · {data.summary.baseline_period}</div>
        </div>
        {data.summary.is_mock && (
          <span className="ml-1 rounded-full border border-hairline px-1.5 py-0.5 text-[8px] font-bold tracking-[0.32px] text-ink uppercase">Demo</span>
        )}
      </div>

      <nav className="flex h-full items-stretch gap-1">
        {MODES.map((m) => {
          const on = m.id === mode
          return (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              title={m.hint}
              className={`group flex flex-col items-center justify-center gap-0.5 border-b-2 px-4 text-[14px] font-semibold transition ${
                on ? 'border-ink text-ink' : 'border-transparent text-muted hover:text-ink'
              }`}
            >
              <span className={`text-[22px] leading-none transition ${on ? '' : 'opacity-80 grayscale-[35%] group-hover:scale-110'}`}>{m.icon}</span>
              {m.label}
            </button>
          )
        })}
      </nav>

      <div className="flex min-w-56 items-center justify-end gap-2">
        <div className="flex rounded-full border border-hairline p-1">
          {(['co2_kg', 'cost_chf', 'kwh'] as MetricKey[]).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={`rounded-full px-3 py-1.5 text-[13px] font-medium transition ${metric === m ? 'bg-ink text-white' : 'text-body hover:bg-surface-soft'}`}
            >
              {METRIC_LABEL[m]}
            </button>
          ))}
        </div>
        <button
          onClick={() => setTour(tour === null ? 0 : null)}
          className={`rounded-full border px-4 py-2 text-[14px] font-medium transition ${
            tour !== null ? 'border-ink bg-ink text-white' : 'border-hairline text-ink hover:bg-surface-soft'
          }`}
        >
          {tour !== null ? 'Chiudi tour' : '▶ Tour'}
        </button>
        <button
          onClick={() => exportCsvs(data, active)}
          title="Scarica i due CSV di consegna"
          className="grid h-10 w-10 place-items-center rounded-full border border-hairline text-ink transition hover:bg-surface-soft"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14" />
          </svg>
        </button>
      </div>
    </header>
  )
}

function Leaf() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8 text-primary" fill="currentColor" aria-hidden>
      <path d="M27 5c-9.5-.4-17.6 2.6-20.4 9.3-1.6 3.8-.8 7.4 1.2 9.9-1.3 1.3-2.3 2.6-3 3.8l1.7 1c.7-1.2 1.7-2.5 3-3.8 2.5 1.6 6.1 2 9.6.2C25.5 22.3 27.8 13.8 27 5zm-6 6.4c-3.6 2.2-7.4 5.4-10.4 8.7l-1.4-1.4c3.1-3.4 7-6.7 10.8-9z" />
    </svg>
  )
}
