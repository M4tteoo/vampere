import { useMemo } from 'react'
import { useApp } from '../store'
import { DEPARTMENTS, DEPT_LABEL, labelOf, makeCtx } from '../data/twin'
import { useScreen } from '../scene/twin/screen'
import { allocRegistry } from '../scene/twin/Allocation'

/** Scritte sopra la scena: nella pianta i nomi dei reparti (solo testo), nel reparto il nome dell'oggetto sotto il mouse. */
export function SceneLabels() {
  const points = useScreen((s) => s.points)
  const room = useApp((s) => s.room)
  const hoverId = useApp((s) => s.hoverId)
  const selectedId = useApp((s) => s.selectedId)
  const setRoom = useApp((s) => s.setRoom)
  const hover = useApp((s) => s.hover)
  const data = useApp((s) => s.data)!
  const ctx = useMemo(() => makeCtx(data, []), [data])

  const tip = room && hoverId && hoverId !== selectedId ? allocRegistry.get(hoverId) : undefined
  return (
    <>
      {!room &&
        DEPARTMENTS.map((r) => {
          const p = points[`room:${r}`]
          if (!p) return null
          const on = hoverId === `room:${r}`
          return (
            <button
              key={r}
              onClick={() => setRoom(r)}
              onPointerEnter={() => hover(`room:${r}`)}
              onPointerLeave={() => hover(null)}
              style={{ left: p[0], top: p[1] }}
              className={`pointer-events-auto absolute ml-3 mt-3 whitespace-nowrap rounded-full px-3 py-1 text-[13px] font-semibold backdrop-blur-sm transition ${
                on ? 'bg-primary/90 text-white' : 'bg-white/70 text-ink'
              }`}
            >
              {DEPT_LABEL[r]}
            </button>
          )
        })}
      {tip && points.hover && (
        <div
          style={{ left: points.hover[0], top: points.hover[1] }}
          className="pill-shadow absolute -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-full bg-white px-3 py-1.5 text-[13px] font-semibold text-ink"
        >
          {labelOf(ctx, tip.item)}
        </div>
      )}
    </>
  )
}
