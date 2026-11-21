import { useMemo } from 'react'
import { useApp } from '../store'
import { DEPARTMENTS, DEPT_LABEL, labelOf, makeCtx } from '../data/twin'
import { useScreen } from '../scene/twin/screen'
import { allocRegistry, cloudResourcesOf, ISLAND_LABEL, islandsOf } from '../scene/twin/Allocation'

/** Scritte sopra la scena: nella pianta i nomi dei reparti; nel reparto i titoli dei due palchi e il tooltip. */
export function SceneLabels() {
  const points = useScreen((s) => s.points)
  const room = useApp((s) => s.room)
  const stage = useApp((s) => s.stage)
  const setStage = useApp((s) => s.setStage)
  const hoverId = useApp((s) => s.hoverId)
  const selectedId = useApp((s) => s.selectedId)
  const setRoom = useApp((s) => s.setRoom)
  const hover = useApp((s) => s.hover)
  const data = useApp((s) => s.data)!
  const ctx = useMemo(() => makeCtx(data, []), [data])

  const tip = room && hoverId && hoverId !== selectedId ? allocRegistry.get(hoverId) : undefined
  const seats = room ? data.layout.filter((i) => i.id.startsWith(`seat:${room}:`)).length : 0
  const cloud = room ? cloudResourcesOf(ctx, room) : new Set<string>()
  const islands = room ? islandsOf(ctx, room) : []

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
              className={`pointer-events-auto absolute mt-3 ml-3 rounded-full px-3 py-1 text-[13px] font-semibold whitespace-nowrap backdrop-blur-sm transition ${
                on ? 'bg-primary/90 text-white' : 'bg-white/70 text-ink'
              }`}
            >
              {DEPT_LABEL[r]}
            </button>
          )
        })}

      {room && (
        <>
          <StageTitle
            at={points['stage:office']}
            active={stage === 'office'}
            hovered={hoverId === 'stage:office'}
            title="Software & services"
            sub={`${seats} computers · licences, SaaS and AI`}
            onClick={() => setStage('office')}
          />
          {islands.length > 0 && (
            <StageTitle
              at={points['stage:cloud']}
              active={stage === 'cloud'}
              hovered={hoverId === 'stage:cloud'}
              title="Cloud infrastructure"
              sub={`${cloud.size} resource${cloud.size > 1 ? 's' : ''} · ${islands.map((i) => ISLAND_LABEL[i.name]).join(', ')}`}
              onClick={() => setStage('cloud')}
            />
          )}
          {stage === 'cloud' &&
            islands.map(({ name, items }) => {
              const p = points[`island:${name}`]
              if (!p) return null
              return (
                <div
                  key={name}
                  style={{ left: p[0], top: p[1] }}
                  className="absolute -translate-y-1/2 pl-4 whitespace-nowrap"
                >
                  <div className="text-[14px] font-semibold text-ink">{ISLAND_LABEL[name]}</div>
                  <div className="text-[12px] text-muted">
                    {items.length} item{items.length > 1 ? 's' : ''} used
                  </div>
                </div>
              )
            })}
        </>
      )}

      {tip && points.hover && (
        <div
          style={{ left: points.hover[0], top: points.hover[1] }}
          className="pill-shadow absolute -translate-x-1/2 -translate-y-full rounded-full bg-white px-3 py-1.5 text-[13px] font-semibold whitespace-nowrap text-ink"
        >
          {labelOf(ctx, tip.item)}
        </div>
      )}
    </>
  )
}

/** Titolo di un palco: grande e scuro quando è in primo piano, piccolo e cliccabile quando è di lato. */
function StageTitle(props: { at?: [number, number]; active: boolean; hovered: boolean; title: string; sub: string; onClick: () => void }) {
  const { at, active, hovered, title, sub, onClick } = props
  if (!at) return null
  return (
    <button
      onClick={onClick}
      disabled={active}
      style={{ left: at[0], top: at[1] - 14 }}
      className={`pointer-events-auto absolute -translate-x-1/2 -translate-y-full text-center whitespace-nowrap transition ${active ? 'cursor-default' : 'opacity-80 hover:opacity-100'}`}
    >
      <div className={`font-semibold tracking-[-0.3px] ${active ? 'text-[18px] text-ink' : `text-[14px] ${hovered ? 'text-primary' : 'text-body'}`}`}>
        {title}
        {!active && <span className="ml-1">→</span>}
      </div>
      <div className={`text-muted ${active ? 'text-[13px]' : 'text-[12px]'}`}>{sub}</div>
    </button>
  )
}
