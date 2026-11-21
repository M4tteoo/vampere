import { useApp, type Step } from '../store'

/** Passi della pipeline, nell'ordine in cui li racconta la demo. Per ora è pronto solo «Allocation». */
export const STEPS: { id: Step; label: string; ready: boolean }[] = [
  { id: 'allocation', label: 'Allocation', ready: true },
  { id: 'footprint', label: 'Footprint', ready: false },
  { id: 'baseline', label: 'Baseline', ready: false },
  { id: 'hotspots', label: 'Hotspots', ready: false },
  { id: 'measures', label: 'Measures', ready: false },
  { id: 'limits', label: 'Limits', ready: false },
  { id: 'package', label: 'Package', ready: false },
  { id: 'export', label: 'Export', ready: false },
]

/** Barra in alto: logo a sinistra, i passi in una pillola al centro (stile ricerca di Airbnb, senza icone). */
export function Header() {
  const step = useApp((s) => s.step)
  const setRoom = useApp((s) => s.setRoom)
  const isMock = useApp((s) => s.data?.summary.is_mock)

  return (
    <header className="relative z-40 flex h-[88px] shrink-0 items-center justify-between bg-white px-8">
      <button onClick={() => setRoom(null)} className="flex w-48 items-center gap-2" aria-label="Back to the floor plan">
        <svg viewBox="0 0 32 32" className="h-7 w-7 text-primary" fill="currentColor" aria-hidden>
          <path d="M27 5c-9.5-.4-17.6 2.6-20.4 9.3-1.6 3.8-.8 7.4 1.2 9.9-1.3 1.3-2.3 2.6-3 3.8l1.7 1c.7-1.2 1.7-2.5 3-3.8 2.5 1.6 6.1 2 9.6.2C25.5 22.3 27.8 13.8 27 5zm-6 6.4c-3.6 2.2-7.4 5.4-10.4 8.7l-1.4-1.4c3.1-3.4 7-6.7 10.8-9z" />
        </svg>
        <span className="text-[20px] font-semibold tracking-[-0.4px] text-primary">greenops</span>
      </button>

      <nav className="pill-shadow flex h-16 items-center rounded-full border border-hairline bg-white px-3">
        {STEPS.map((s, i) => {
          const on = s.id === step
          return (
            <div key={s.id} className="flex items-center">
              {i > 0 && <span className="h-7 w-px bg-hairline" />}
              <button
                disabled={!s.ready}
                title={s.ready ? undefined : 'Coming next'}
                className={`rounded-full px-5 py-3 text-[16px] font-medium whitespace-nowrap transition ${
                  on ? 'font-semibold text-ink' : s.ready ? 'text-ink hover:bg-surface-soft' : 'text-muted-soft'
                }`}
              >
                {s.label}
              </button>
            </div>
          )
        })}
      </nav>

      <div className="flex w-48 justify-end">
        {isMock && <span className="rounded-full border border-hairline px-2.5 py-1 text-[12px] font-medium text-muted">Demo data</span>}
      </div>
    </header>
  )
}
