import { useMemo } from 'react'
import { useApp } from '../store'
import { DEPARTMENTS, DEPT_LABEL, labelOf, makeCtx } from '../data/twin'
import { useScreen } from '../scene/twin/screen'
import { allocRegistry, cloudResourcesOf, ISLAND_LABEL, ISLAND_ORDER, islandsOf } from '../scene/twin/Allocation'
import { useHeat } from '../scene/twin/heat'
import { ISLAND_LOC } from '../data/usage'
import { fmtMetric } from '../data/compute'

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
              const below = points[`islandb:${name}`]
              const p = below ?? points[`island:${name}`]
              if (!p) return null
              return (
                <div
                  key={name}
                  style={{ left: p[0], top: p[1] }}
                  className={`absolute whitespace-nowrap ${below ? '-translate-x-1/2 pt-2 text-center' : '-translate-y-1/2 pl-4'}`}
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
          {tip.item.id.startsWith('seat:') ? `${DEPT_LABEL[tip.item.room ?? '']} computers · ${seats}` : labelOf(ctx, tip.item)}
        </div>
      )}
      <HeatLabels />
    </>
  )
}

/** Passi 2–4: CO₂ di ogni nuvola, nomi delle isole nella pianta, punti critici. */
function HeatLabels() {
  const points = useScreen((s) => s.points)
  const room = useApp((s) => s.room)
  const setRoom = useApp((s) => s.setRoom)
  const heat = useHeat()
  if (!heat.on) return null
  return (
    <>
      {ISLAND_ORDER.map((name) => {
        const c = points[`cloud:${name}`]
        const kg = heat.cloudKg(ISLAND_LOC[name])
        return (
          <div key={name}>
            {c && (
              <div
                style={{ left: c[0], top: c[1] }}
                className="absolute -translate-x-1/2 -translate-y-full rounded-full bg-white/85 px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap text-ink backdrop-blur-sm tabular-nums"
              >
                {fmtMetric(kg, 'co2_kg')}
              </div>
            )}
            {!room && points[`island:${name}`] && (
              <div style={{ left: points[`island:${name}`][0], top: points[`island:${name}`][1] }} className="absolute -translate-y-1/2 pl-3 whitespace-nowrap">
                <div className="text-[13px] font-semibold text-ink">{ISLAND_LABEL[name]}</div>
              </div>
            )}
          </div>
        )
      })}
      {[...heat.pains].map(([unit, n]) => {
        const p = points[`pain:${unit}`]
        if (!p || (room && unit.startsWith('pcs:'))) return null
        const pcs = unit.startsWith('pcs:')
        return (
          <button
            key={unit}
            onClick={() => pcs && !room && setRoom(unit.slice(4))}
            title={`${n} pain point${n > 1 ? 's' : ''}`}
            style={{ left: p[0], top: p[1] }}
            className={`absolute grid h-6 min-w-6 -translate-x-1/2 -translate-y-full place-items-center rounded-full bg-error px-1.5 text-[12px] font-bold text-white shadow ${pcs && !room ? 'pointer-events-auto' : ''}`}
          >
            {n > 1 ? `! ${n}` : '!'}
          </button>
        )
      })}
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
      style={{ left: at[0], top: at[1] - 26 }}
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
