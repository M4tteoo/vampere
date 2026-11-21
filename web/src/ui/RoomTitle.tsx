import { useEffect } from 'react'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'
import { PANEL_W } from '../scene/Scene'

/** Reparto isolato: nome in basso al centro (frecce per ruotare, Esc per tornare) e spesa totale in un riquadro in basso a sinistra. */
export function RoomTitle() {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const panel = useApp((s) => !!s.selectedId)
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

      {/* Nome del reparto e, sotto, solo il comando per girare. */}
      <div
        className="pointer-events-none absolute bottom-8 left-0 flex flex-col items-center transition-[right] duration-700"
        style={{ right: panel ? PANEL_W + 48 : 0 }}
      >
        <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.5px] text-ink">{d.label}</h1>
        <p className="mt-1 text-[13px] text-muted">← → rotate</p>
      </div>

      {/* Spesa totale del reparto: riquadro fisso in basso a sinistra. */}
      <div className="pill-shadow pointer-events-auto absolute bottom-6 left-6 w-[244px] rounded-[14px] bg-white px-4 py-3">
        <div className="text-[12px] font-medium text-muted">Total spend of {d.label}, per year</div>
        <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1">
          <Stat label="Cost" value={fmtMetric(d.metrics.cost_chf, 'cost_chf')} />
          <Stat label="CO₂" value={fmtMetric(d.metrics.co2_kg, 'co2_kg')} />
          <Stat label="Energy" value={fmtMetric(d.metrics.kwh, 'kwh')} />
          <Stat label="People" value={`${d.fte} FTE`} />
        </div>
        {shared > 0 && (
          <div className="mt-1.5 text-[11px] text-muted">incl. {fmtMetric(Math.min(shared, d.metrics.cost_chf), 'cost_chf')} of shared services</div>
        )}
      </div>
    </>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="text-[15px] font-semibold text-ink tabular-nums">{value}</div>
    </div>
  )
}
