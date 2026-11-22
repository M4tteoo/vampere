import { useMemo } from 'react'
import { useApp } from '../store'
import { DEPARTMENTS, DEPT_LABEL, labelOf, makeCtx } from '../data/twin'
import { useScreen } from '../scene/twin/screen'
import { allocRegistry, cloudResourcesOf, ISLAND_LABEL, ISLAND_ORDER, islandsOf } from '../scene/twin/Allocation'
import { MARK_COLOR, deptMark, useHeat } from '../scene/twin/heat'
import { GOAL_LABEL, ISLAND_LOC, deptUnits } from '../data/usage'
import { forecastPlan, goalOf } from '../data/plan'
import { useCo2 } from '../data/co2'
import { BEHAVIOUR_TEXT, BehaviourIcon, behaviourOf } from './Behaviour'
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
  const step = useApp((s) => s.step)
  const ctx = useMemo(() => makeCtx(data, []), [data])

  // Passo 4: anche senza reparto; «L:» = lo stesso oggetto nel lato baseline.
  const hovered = hoverId?.replace(/^L:/, '') ?? null
  const tip = (room || step === 'forecast') && hovered && hovered !== selectedId ? allocRegistry.get(hovered) : undefined
  const seats = room ? data.layout.filter((i) => i.id.startsWith(`seat:${room}:`)).length : 0
  const cloud = room ? cloudResourcesOf(ctx, room) : new Set<string>()
  const islands = room ? islandsOf(ctx, room) : []
  const heat = useHeat()
  const heatOn = heat.on

  return (
    <>
      {!room &&
        step !== 'forecast' &&
        DEPARTMENTS.map((r) => {
          const p = points[`room:${r}`]
          if (!p) return null
          const on = hoverId === `room:${r}`
          const tint = heat.step // passi 2–4: la pillola resta bianca, il pavimento si colora
          return (
            <button
              key={r}
              onClick={() => setRoom(r)}
              onPointerEnter={() => hover(`room:${r}`)}
              onPointerLeave={() => hover(null)}
              style={{ left: p[0], top: p[1] }}
              className={`pointer-events-auto absolute mt-3 ml-3 rounded-full px-3 py-1 text-[13px] font-semibold whitespace-nowrap backdrop-blur-sm transition ${
                on ? (tint ? 'bg-white text-ink' : 'bg-primary/90 text-white') : 'bg-white/70 text-ink'
              }`}
            >
              {DEPT_LABEL[r]}
              {step !== 'allocation' && <DeptBadge room={r} />}
            </button>
          )
        })}

      {room && (
        <>
          <StageTitle
            at={points['stage:office']}
            active={heatOn || stage === 'office'}
            hovered={hoverId === 'stage:office'}
            title="Software & services"
            left
            sub={`${seats} computers · licences, SaaS and AI`}
            onClick={() => setStage('office')}
          />
          {islands.length > 0 && (
            <StageTitle
              at={points['stage:cloud']}
              active={heatOn || stage === 'cloud'}
              hovered={hoverId === 'stage:cloud'}
              title="Cloud infrastructure"
              sub={`${cloud.size} resource${cloud.size > 1 ? 's' : ''} · ${islands.map((i) => ISLAND_LABEL[i.name]).join(', ')}`}
              onClick={() => setStage('cloud')}
            />
          )}
          {stage === 'cloud' &&
            !heatOn &&
            islands.map(({ name, items }) => {
              const below = points[`islandb:${name}`]
              const p = below ?? points[`island:${name}`]
              if (!p) return null
              return (
                <div key={name} style={{ left: p[0], top: p[1] }} className={`absolute whitespace-nowrap ${below ? '-translate-x-1/2 pt-2 text-center' : '-translate-y-1/2 pl-4'}`}>
                  <div className="text-[14px] font-semibold text-ink">{ISLAND_LABEL[name]}</div>
                  <div className="text-[12px] text-muted">
                    {items.length} item{items.length > 1 ? 's' : ''} used
                  </div>
                </div>
              )
            })}
        </>
      )}

      <HeatLabels />
      <ForecastSides />
      {/* Nome dell'oggetto sotto il mouse: sopra tutto e più in alto dei simboli (▼, comportamento), così non li copre. */}
      {tip && points.hover && (
        <div
          style={{ left: points.hover[0], top: points.hover[1] - (heatOn ? 30 : 0) }}
          className="pill-shadow absolute z-20 -translate-x-1/2 -translate-y-full rounded-full bg-white px-3 py-1.5 text-[13px] font-semibold whitespace-nowrap text-ink"
        >
          {tip.item.id.startsWith('seat:') ? `${DEPT_LABEL[tip.item.room ?? '']} computers · ${seats}` : labelOf(ctx, tip.item)}
        </div>
      )}
    </>
  )
}

/** Passi 2–4: CO₂ di ogni nuvola, nomi delle isole nella pianta, punti critici. */
function HeatLabels() {
  const points = useScreen((s) => s.points)
  const heat = useHeat()
  const reduced = useApp((s) => s.step === 'baseline' && s.showMeasures && s.month === null)
  const room = useApp((s) => s.room)
  const pkg = useApp((s) => s.step === 'packages')
  if (!heat.on || !heat.x) return null
  const x = heat.x
  const office = points['stage:office']
  // Passo 3: segno «▼» sugli oggetti toccati dalla misura aperta (i colori cambiano fra «Before» e «After»).
  const Hit = () => (
    <span className="grid h-5 w-5 animate-bounce place-items-center rounded-full bg-ink text-[9px] text-white shadow-sm" title="Changed by this measure">
      ▼
    </span>
  )
  return (
    <>
      {placeClouds(
        ISLAND_ORDER.filter((n) => points[`cloud:${n}`]).map((name) => ({
          name,
          at: points[`cloud:${name}`],
          text: `${ISLAND_LABEL[name]} · ${fmtMetric(heat.cloudKg(ISLAND_LOC[name]), 'co2_kg')}${heat.cumulative ? ' so far' : ''}`,
        })),
      ).map(({ name, at: c }) => {
        return (
          <div
            key={name}
            style={{ left: c[0], top: c[1] }}
            className="absolute -translate-x-1/2 -translate-y-full rounded-full bg-white/85 px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap text-ink backdrop-blur-sm tabular-nums"
          >
            {/* Con le misure attive il numero è verde (una parola in più sovrapponeva le etichette vicine). */}
            {ISLAND_LABEL[name]} · <span className={reduced || (pkg && heat.active.length > 0) ? 'text-primary' : ''}>{fmtMetric(heat.cloudKg(ISLAND_LOC[name]), 'co2_kg')}</span>
            {heat.cumulative && <span className="font-normal text-muted"> so far</span>}
          </div>
        )
      })}
      {/* Sopra ogni risorsa: «!» se ha punti critici aperti, e il simbolo del suo comportamento. */}
      {Object.entries(points)
        .filter(([k]) => k.startsWith('unit:'))
        .map(([k, p]) => {
          const unit = k.slice(5)
          const b = behaviourOf(x, heat.behaviourOf(unit))
          const hit = heat.focusUnits.has(unit)
          if (!b && !hit) return null
          return (
            <div key={k} style={{ left: p[0], top: p[1] }} className="absolute flex -translate-x-1/2 -translate-y-full items-center gap-1">
              {hit && <Hit />}
              {b && (
                <span title={BEHAVIOUR_TEXT[b.kind]} className="grid h-5 w-5 place-items-center rounded-full bg-white text-ink shadow-sm ring-1 ring-hairline">
                  <BehaviourIcon kind={b.kind} className="h-3 w-3" />
                </span>
              )}
            </div>
          )
        })}
      {office && room && heat.focusUnits.has(`pcs:${room}`) && (
        <div style={{ left: office[0], top: office[1] + 52 }} className="absolute flex -translate-x-1/2 items-center gap-1.5 text-[12px] font-semibold text-ink">
          <Hit /> All computers of the department
        </div>
      )}
    </>
  )
}

/**
 * Passo 4: i due lati dello schermo. Sopra ciascuno il titolo e quanto si è speso ed emesso finora nella simulazione;
 * sopra le nuvole della baseline la loro etichetta (quelle del lato con il pacchetto le disegna HeatLabels).
 */
function ForecastSides() {
  const points = useScreen((s) => s.points)
  const step = useApp((s) => s.step)
  const month = useApp((s) => s.month)
  const goalSel = useApp((s) => s.goal)
  const dropped = useApp((s) => s.dropped)
  const data = useApp((s) => s.data)!
  const x = data.extra
  const base = useHeat({ withPackage: false })
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const cv = useCo2(ctx)
  const goal = x ? goalOf(x, goalSel) : ''
  const fm = useMemo(() => (x && step === 'forecast' ? forecastPlan(ctx, x, goal, dropped) : []), [ctx, x, goal, dropped, step])
  if (step !== 'forecast' || !x || !fm.length) return null
  const upTo = month === null ? fm.length : month + 1
  const so = (k: 'with' | 'without') => fm.slice(0, upTo).reduce((a, m) => ({ cost: a.cost + m[k].cost_chf, co2: a.co2 + m[k].co2_kg * cv.company }), { cost: 0, co2: 0 })
  const sides = [
    { key: 'L', title: 'Without changes', sub: 'their baseline', v: so('without'), tone: 'text-ink' },
    { key: 'R', title: `With «${GOAL_LABEL[goal] ?? goal}»`, sub: 'our package', v: so('with'), tone: 'text-primary' },
  ]
  return (
    <>
      {sides.map((sd) => {
        const p = points[`side:${sd.key}`]
        if (!p) return null
        return (
          <div key={sd.key} style={{ left: p[0], top: p[1] - 10 }} className="absolute -translate-x-1/2 -translate-y-full text-center whitespace-nowrap">
            <div className={`text-[20px] font-semibold tracking-[-0.3px] ${sd.tone}`}>{sd.title}</div>
            <div className="text-[13px] text-muted">
              {sd.sub} · so far <span className="font-semibold text-ink tabular-nums">{fmtMetric(sd.v.cost, 'cost_chf')}</span> ·{' '}
              <span className="font-semibold text-ink tabular-nums">{fmtMetric(sd.v.co2, 'co2_kg')}</span>
            </div>
          </div>
        )
      })}
      {placeClouds(
        ISLAND_ORDER.filter((n) => points[`cloudL:${n}`]).map((name) => ({
          name,
          at: points[`cloudL:${name}`],
          text: `${ISLAND_LABEL[name]} · ${fmtMetric(base.cloudKg(ISLAND_LOC[name]), 'co2_kg')}`,
        })),
      ).map(({ name, at, text }) => (
        <div key={name} style={{ left: at[0], top: at[1] }} className="absolute -translate-x-1/2 -translate-y-full rounded-full bg-white/85 px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap text-ink backdrop-blur-sm tabular-nums">
          {text}
          {base.cumulative && <span className="font-normal text-muted"> so far</span>}
        </div>
      ))}
    </>
  )
}

/**
 * Etichette delle nuvole senza sovrapposizioni: larghezza stimata dal testo; se un'etichetta tocca una già piazzata
 * sale di una riga finché è libera (le nuvole vicine, viste di lato, possono avere le etichette alla stessa altezza).
 */
function placeClouds<T extends { at: [number, number]; text: string }>(list: T[]): T[] {
  const placed: { x0: number; x1: number; y0: number; y1: number }[] = []
  return [...list]
    .sort((a, b) => b.at[1] - a.at[1])
    .map((l) => {
      const w = l.text.length * 6.6 + 24
      let y = l.at[1]
      const box = () => ({ x0: l.at[0] - w / 2, x1: l.at[0] + w / 2, y0: y - 24, y1: y })
      const hits = (b: { x0: number; x1: number; y0: number; y1: number }) => placed.some((p) => b.x0 < p.x1 + 6 && b.x1 > p.x0 - 6 && b.y0 < p.y1 && b.y1 > p.y0)
      for (let i = 0; i < 6 && hits(box()); i++) y -= 26
      placed.push(box())
      return { ...l, at: [l.at[0], y] as [number, number] }
    })
}

/** Pianta dei passi 2–4: quanti punti critici ha il reparto (i suoi computer e le risorse cloud che usa). */
function DeptBadge({ room }: { room: string }) {
  const heat = useHeat()
  const step = useApp((s) => s.step)
  if (!heat.step) return null
  const units = new Set(deptUnits(heat.ctx, room))
  const n = [...heat.pains].filter(([u]) => units.has(u)).reduce((a, [, k]) => a + k, 0)
  if (!n) return null
  // Stesso colore della tinta del reparto: rosso se c'è una grande fonte, arancio se solo sprechi.
  const color = MARK_COLOR[deptMark(heat, [...units])]
  return (
    // Baseline: un piccolo «!» dentro il pallino, accanto al numero.
    <span className="ml-1.5 rounded-full px-1.5 text-[11px] font-bold text-white" style={{ background: color }}>
      {n}
      {step === 'baseline' && <span className="ml-0.5">!</span>}
    </span>
  )
}

/** Titolo di un palco: grande e scuro quando è in primo piano, piccolo e cliccabile quando è di lato. */
function StageTitle(props: { at?: [number, number]; active: boolean; hovered: boolean; title: string; sub: string; onClick: () => void; left?: boolean }) {
  const { at, active, hovered, title, sub, onClick, left } = props
  if (!at) return null
  return (
    <button
      onClick={onClick}
      disabled={active}
      style={{ left: at[0], top: at[1] - 26 }}
      className={`pointer-events-auto absolute -translate-x-1/2 -translate-y-full text-center whitespace-nowrap transition ${active ? 'cursor-default' : 'opacity-80 hover:opacity-100'}`}
    >
      <div className={`font-semibold tracking-[-0.3px] ${active ? 'text-[18px] text-ink' : `text-[14px] ${hovered ? 'text-primary' : 'text-body'}`}`}>
        {/* La freccia indica dove sta il palco laterale: a sinistra l'ufficio, a destra le isole. */}
        {!active && left && <span className="mr-1">←</span>}
        {title}
        {!active && !left && <span className="ml-1">→</span>}
      </div>
      <div className={`text-muted ${active ? 'text-[13px]' : 'text-[12px]'}`}>{sub}</div>
    </button>
  )
}
