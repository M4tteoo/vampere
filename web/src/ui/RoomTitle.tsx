import { useEffect } from 'react'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'
import { PANEL_W } from '../scene/Scene'

/** Sotto il reparto isolato: nome e consumi annui, senza riquadro. Frecce per ruotare di 180°, Esc per tornare. */
export function RoomTitle() {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const panel = useApp((s) => !!s.selectedId)
  const turn = useApp((s) => s.turn)
  const setRoom = useApp((s) => s.setRoom)

  useEffect(() => {
    // Tenendo premuta una freccia si continua a girare nello stesso verso (un mezzo giro ogni 0,4 s al massimo).
    let lastTurn = 0
    const onKey = (e: KeyboardEvent) => {
      const s = useApp.getState()
      if (!s.room) return
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault()
        if (performance.now() - lastTurn < 400) return
        lastTurn = performance.now()
        s.turn(e.key === 'ArrowRight' ? 1 : -1)
      }
      if (e.key === 'Escape') {
        if (s.selectedId) s.select(null)
        else s.setRoom(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!room) return null
  const d = data.summary.departments.find((x) => x.id === room)
  if (!d) return null
  // Quota di questo reparto sulle risorse condivise (già inclusa nei totali).
  const shared = data.entities.reduce((a, e) => a + (e.allocation?.find((x) => x.department === room)?.share ?? 0) * e.metrics.cost_chf, 0)

  return (
    <>
      <button
        onClick={() => setRoom(null)}
        className="pill-shadow pointer-events-auto absolute top-6 left-8 flex items-center gap-2 rounded-full bg-white px-4 py-2.5 text-[14px] font-medium text-ink transition hover:bg-surface-soft"
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 5l-7 7 7 7" />
        </svg>
        All departments
      </button>

      <div
        className="pointer-events-none absolute bottom-8 left-0 flex flex-col items-center transition-[right] duration-700"
        style={{ right: panel ? PANEL_W + 48 : 0 }}
      >
        <div className="flex items-center gap-5">
          <span className="w-10" />
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.5px] text-ink">{d.label}</h1>
          <RotateButton onClick={() => turn(1)} label="Rotate the view" />
        </div>
        <p className="mt-1 text-[15px] text-muted">
          {d.fte} FTE · {fmtMetric(d.metrics.cost_chf, 'cost_chf')} · {fmtMetric(d.metrics.kwh, 'kwh')} · {fmtMetric(d.metrics.co2_kg, 'co2_kg')} per year
          {shared > 0 && <span className="text-muted-soft"> · incl. {fmtMetric(shared, 'cost_chf')} of shared services</span>}
        </p>
        <p className="mt-2 text-[12px] text-muted-soft">Click an object to see what it consumes · ← → rotate · Esc back</p>
      </div>
    </>
  )
}

function RotateButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="pointer-events-auto grid h-10 w-10 place-items-center rounded-full border border-hairline bg-white text-ink transition hover:border-ink"
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4" />
      </svg>
    </button>
  )
}
