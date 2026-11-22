import { useEffect, useMemo } from 'react'
import { makeCtx } from '../data/twin'
import type { MetricKey } from '../data/types'
import { deptSaved, savedByRaw } from '../data/plan'
import { useHeat } from '../scene/twin/heat'
import { useCo2 } from '../data/co2'
import { CompareToggle } from './PackagesPanel'
import { Co2Switch } from './Co2Switch'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'

/** Reparto isolato: nome in basso al centro (frecce per ruotare, Esc per tornare) (la spesa totale è in RoomTotals). */
export function RoomTitle() {
  // Passo 3: il pannello dei pacchetti occupa la sinistra, il bottone si sposta alla sua destra.
  const pkg = useApp((s) => s.step === 'packages' && !!s.data?.extra)
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
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
  return (
    <>
      {/* In alto a sinistra: torna alla pianta. Passo 3: accanto, sulla stessa riga, il confronto senza/con la misura aperta. */}
      <div className={`pointer-events-none absolute top-6 flex items-center gap-3 ${pkg ? 'left-[408px]' : 'left-8'}`}>
        <button
          onClick={() => setRoom(null)}
          className="pill-shadow pointer-events-auto flex h-11 items-center gap-2 rounded-full bg-white px-4 text-[14px] font-medium text-ink transition hover:bg-surface-soft"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 5l-7 7 7 7" />
          </svg>
          All departments
        </button>
        {pkg && data.extra && <CompareToggle x={data.extra} />}
      </div>

      {/* Nome del reparto e, sotto, solo il comando per girare. */}
      <div className="pointer-events-none absolute right-0 bottom-8 left-0 flex flex-col items-center">
        <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.5px] text-ink">{d.label}</h1>
        <p className="mt-1 text-[13px] text-muted">← → rotate</p>
      </div>
    </>
  )
}

/** Spesa totale del reparto: in basso a sinistra, sopra la legenda (si sposta da solo quando la legenda si apre o si chiude). */
export function RoomTotals() {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const heat = useHeat()
  const ctx = useMemo(() => makeCtx(data, []), [data])
  // Con le misure attive (interruttore del passo 2, piano del passo 4) i totali scendono di quanto fanno risparmiare.
  const co2 = useCo2(ctx)
  const cut = useMemo(() => (room && heat.x && heat.active.length ? deptSaved(ctx, co2.saved(savedByRaw(ctx, heat.x, heat.active)), room) : null), [ctx, heat.x, heat.active, room, co2])
  const d = room ? data.summary.departments.find((x) => x.id === room) : undefined
  if (!room || !d) return null
  // Quota di questo reparto sulle risorse condivise (già inclusa nei totali).
  const shared = data.entities.reduce((a, e) => a + (e.allocation?.find((x) => x.department === room)?.share ?? 0) * e.metrics.cost_chf, 0)
  // CO₂ nella vista scelta (location- o market-based).
  const m = { ...d.metrics, co2_kg: d.metrics.co2_kg * co2.dept(room) }
  const val = (k: MetricKey) => fmtMetric(Math.max(0, m[k] - (cut?.[k] ?? 0)), k)
  const drop = (k: MetricKey) => (cut && cut[k] > 0 && m[k] > 0 ? `−${Math.round((cut[k] / m[k]) * 100)}%` : undefined)
  return (
    <div className="pill-shadow pointer-events-auto w-[260px] rounded-[14px] bg-white px-4 py-3">
      <div className="text-[12px] font-medium text-muted">
        {cut ? `${d.label} with the measures, per year` : `Total spend of ${d.label}, per year`}
      </div>
      <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1">
        <Stat label="Cost" value={val('cost_chf')} drop={drop('cost_chf')} />
        <Stat label={co2.market ? "CO₂ · market-based" : "CO₂"} value={val("co2_kg")} drop={drop("co2_kg")} />
        <Stat label="Energy" value={val('kwh')} drop={drop('kwh')} />
        <Stat label="People" value={`${d.fte} FTE`} />
      </div>
      {shared > 0 && <div className="mt-1.5 text-[11px] text-muted">incl. {fmtMetric(Math.min(shared, d.metrics.cost_chf), 'cost_chf')} of shared services</div>}
      {/* Passi 2–4: come si conta la CO₂ (location- o market-based). */}
      {heat.step && (
        <div className="mt-2 border-t border-hairline-soft pt-2">
          <Co2Switch />
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, drop }: { label: string; value: string; drop?: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="text-[15px] font-semibold whitespace-nowrap text-ink tabular-nums">
        {value}
        {drop && <span className="ml-1 text-[11px] font-semibold text-primary">{drop}</span>}
      </div>
    </div>
  )
}
