import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, QuadraticBezierLine } from '@react-three/drei'
import type { QuadraticBezierLineRef } from '@react-three/drei'
import { Group, Mesh, Vector3 } from 'three'
import { useApp } from '../../store'
import { fmtMetric, locationTotals } from '../../data/compute'
import {
  DEPARTMENTS,
  DEPT_ACCENT,
  DEPT_LABEL,
  ISLAND_LOCATION,
  labelOf,
  makeCtx,
  resourceOf,
  sceneIdFor,
  statusOf,
  type Ctx,
  type ItemStatus,
  type Visual,
} from '../../data/twin'
import type { LayoutItem, LocationId } from '../../data/types'
import { Environment, useAnchors, type Anchors } from './Environment'
import { KitInstances, type Inst } from './KitInstances'
import { preloadKits } from './kit'
import { DAYS, GLOW, LED, SCREEN, gridColor } from './colors'

/** Altezza approssimativa (m) di ogni asset: serve per etichette, badge e inquadrature. */
export const HEIGHT: Record<string, number> = {
  desk_bench: 1.2,
  licence_puck: 0.1,
  wall_screen: 1.6,
  wall_screen_large: 2.2,
  saas_terminal: 0.4,
  rack_compact: 1.2,
  ai_orb: 0.5,
  agent_robot: 0.5,
  console_kiosk: 1.4,
  wall_calendar: 1.6,
  tablet_stand: 1.1,
  storage_cabinet: 1.2,
  text_machine: 1.3,
  approval_desk: 1.1,
  m365_totem: 1.8,
  quote_device: 0.3,
  server_rack_42u: 2.0,
  storage_array: 1.2,
  gpu_server: 1.1,
}

const ASSETS = [...Object.keys(HEIGHT), 'chair_task', 'monitor_27', 'monitor_dual']
preloadKits(ASSETS)

const BLINKING: Visual[] = ['waste', 'human', 'contradiction']


/** Posizioni attuali degli oggetti cliccabili: le usa la camera per inquadrarli. */
export const registry = {
  items: new Map<string, { pos: Vector3; h: number; item: LayoutItem }>(),
  anchors: null as Anchors | null,
}

function rotate(x: number, z: number, a: number): [number, number] {
  const c = Math.cos(a)
  const s = Math.sin(a)
  return [x * c + z * s, -x * s + z * c]
}

/** Il gemello digitale: edificio + isole (GLB statici) e tutti gli oggetti interattivi (in istanze). */
export function Twin() {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  const metric = useApp((s) => s.metric)
  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)
  const anchors = useAnchors()
  const ctx = useMemo(() => makeCtx(data, active), [data, active])

  // Oggetti della «UE mista» (non è un luogo reale) restano solo in ufficio.
  const items = useMemo<LayoutItem[]>(() => data.layout.filter((i) => i.island !== 'eu-mixed'), [data.layout])

  const statuses = useMemo(() => new Map(items.map((i) => [i.id, statusOf(ctx, i)])), [items, ctx])

  const byAsset = useMemo(() => {
    const out: Record<string, Inst[]> = {}
    const push = (asset: string, inst: Inst) => (out[asset] ??= []).push(inst)
    registry.items.clear()
    for (const item of items) {
      const st = statuses.get(item.id)!
      const pos = currentPos(item, st, anchors)
      const accent = DEPT_ACCENT[item.room ?? ''] ?? DEPT_ACCENT[st.info?.department ?? ''] ?? '#E9E4DA'
      const seat = item.id.startsWith('seat:')
      push(item.asset, {
        key: item.id,
        itemId: item.id,
        pos,
        rotY: item.rotY,
        scale: st.hidden ? 0 : 1,
        colors: {
          screen: SCREEN[st.visual],
          led: LED[st.visual],
          glow: GLOW[st.visual],
          accent,
          days: DAYS,
        },
        blink: !seat && !item.id.startsWith('lic:') && !item.id.startsWith('pbi-') && BLINKING.includes(st.visual),
        activity: st.activity,
        pickable: true,
      })
      registry.items.set(item.id, { pos: new Vector3(...pos), h: HEIGHT[item.asset] ?? 1, item })
      for (const [ci, child] of (item.children ?? []).entries()) {
        const [dx, dz] = rotate(child.pos[0], child.pos[2], item.rotY)
        push(child.asset, {
          key: `${item.id}/${ci}`,
          itemId: item.id,
          pos: [pos[0] + dx, pos[1] + child.pos[1], pos[2] + dz],
          rotY: item.rotY + child.rotY,
          scale: 1,
          colors: { screen: SCREEN[st.visual], accent },
          blink: false,
          activity: 0,
          pickable: true,
        })
      }
    }
    registry.anchors = anchors
    return out
  }, [items, statuses, anchors])

  // Quota di ogni reparto sulla metrica scelta → colore del pavimento.
  const shares = useMemo(() => {
    const total = data.summary.departments.reduce((a, d) => a + d.metrics[metric], 0) || 1
    return Object.fromEntries(data.summary.departments.map((d) => [d.id, d.metrics[metric] / total]))
  }, [data, metric])

  return (
    <group>
      <Environment shares={shares} />
      {Object.entries(byAsset).map(([asset, list]) => (
        <KitInstances key={asset} asset={asset} instances={list} onHover={hover} onSelect={select} />
      ))}
      <Cables items={items} statuses={statuses} ctx={ctx} />
      <Co2Clouds anchors={anchors} />
      <RoomLabels anchors={anchors} />
      <IslandCards anchors={anchors} />
      <Badges ctx={ctx} />
      <Hover ctx={ctx} statuses={statuses} />
      <SelectionRing />
    </group>
  )
}

function currentPos(item: LayoutItem, st: ItemStatus, a: Anchors): [number, number, number] {
  if (st.moved && item.alternateSlotM1 && a.slots[item.alternateSlotM1.replace(/^slot_/, '')]) {
    const p = a.slots[item.alternateSlotM1.replace(/^slot_/, '')]
    const zurichY = a.islands.zurich ? a.islands.zurich.y + 0.18 : p.y
    return [p.x, Math.max(p.y, zurichY), p.z]
  }
  return item.pos
}

// ---------------------------------------------------------------------------------------------------------
// Cavi: dalla «console» del reparto proprietario all'oggetto fisico sull'isola (o sulla nuvola EU).

function Cables({ items, statuses, ctx }: { items: LayoutItem[]; statuses: Map<string, ItemStatus>; ctx: Ctx }) {
  const metric = useApp((s) => s.metric)
  const selectedId = useApp((s) => s.selectedId)
  const hoverId = useApp((s) => s.hoverId)
  const cables = useMemo(() => {
    const office = new Map(items.filter((i) => i.view !== 'island').map((i) => [i.id, i]))
    const out: { key: string; from: string; to: string; loc: LocationId; value: number; st: ItemStatus }[] = []
    for (const it of items) {
      if (it.view !== 'island') continue
      const src = office.get(resourceOf(it))
      if (!src) continue
      const st = statuses.get(it.id)!
      const loc = st.entity?.location ?? ISLAND_LOCATION[it.island ?? ''] ?? 'EU'
      out.push({ key: it.id, from: src.id, to: it.id, loc, value: st.entity?.metrics[metric] ?? 0, st })
    }
    return out
  }, [items, statuses, metric])
  const max = Math.max(1, ...cables.map((c) => c.value))
  return (
    <>
      {cables.map((c) => {
        const a = registry.items.get(c.from)
        const b = registry.items.get(c.to)
        if (!a || !b) return null
        const focus = [selectedId, hoverId].some((x) => x && (x === c.from || x === c.to || resourceOf(b.item) === x))
        const grid = ctx.data.summary.locations.find((l) => l.id === c.loc)?.grid_kg_per_kwh.mid ?? 0.2
        return (
          <Cable
            key={c.key}
            from={a.pos.clone().setY(a.pos.y + a.h)}
            to={b.pos.clone().setY(b.pos.y + b.h)}
            color={c.st.visual === 'off' ? '#9AA3AD' : gridColor(grid)}
            width={(c.value ? 1 + 3.5 * Math.sqrt(c.value / max) : 0.8) + (focus ? 1.5 : 0)}
            speed={c.st.activity}
            opacity={c.st.hidden ? 0 : focus ? 1 : 0.4}
          />
        )
      })}
    </>
  )
}

function Cable({ from, to, color, width, speed, opacity }: { from: Vector3; to: Vector3; color: string; width: number; speed: number; opacity: number }) {
  const ref = useRef<QuadraticBezierLineRef>(null)
  const mid = useMemo(() => from.clone().lerp(to, 0.5).add(new Vector3(0, 4 + from.distanceTo(to) * 0.25, 0)), [from, to])
  useFrame((_, dt) => {
    const mat = ref.current?.material
    if (mat) mat.dashOffset -= dt * (0.3 + speed * 2.5)
  })
  if (opacity === 0) return null
  return (
    <QuadraticBezierLine
      ref={ref}
      start={from}
      end={to}
      mid={mid}
      color={color}
      lineWidth={width}
      dashed
      dashScale={1.4}
      dashSize={0.7}
      gapSize={0.4}
      transparent
      opacity={opacity}
      raycast={() => null}
    />
  )
}

// ---------------------------------------------------------------------------------------------------------
// Nuvole di CO₂: una sopra ogni isola, il volume segue i kg di CO₂ della sede.

function Co2Clouds({ anchors }: { anchors: Anchors }) {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  const { now, base } = useMemo(() => locationTotals(data, active), [data, active])
  const maxBase = Math.max(...Object.entries(base).filter(([k]) => k !== 'EU').map(([, m]) => m.co2_kg))
  if (!anchors.cloud) return null
  return (
    <>
      {Object.entries(anchors.islands).map(([name, p]) => {
        const loc = ISLAND_LOCATION[name]
        if (!loc) return null
        return <Co2Cloud key={name} at={p} target={0.15 + 1.05 * Math.sqrt(now[loc].co2_kg / maxBase)} anchors={anchors} />
      })}
    </>
  )
}

/** Nuvola di Blender, grigia e semitrasparente: la grandezza segue i kg di CO₂ della sede. */
function Co2Cloud({ at, target, anchors }: { at: Vector3; target: number; anchors: Anchors }) {
  const ref = useRef<Group>(null)
  useFrame(({ clock }, dt) => {
    const g = ref.current
    if (!g) return
    const s = g.scale.x + (target - g.scale.x) * Math.min(1, dt * 2.5)
    g.scale.setScalar(s)
    g.position.y = at.y + 5.2 + Math.sin(clock.elapsedTime * 0.7 + at.x) * 0.2
    g.rotation.y = Math.sin(clock.elapsedTime * 0.15 + at.z) * 0.15
  })
  return (
    <group ref={ref} position={[at.x, at.y + 5.2, at.z]} scale={0.01}>
      <mesh geometry={anchors.cloud!} raycast={() => null} castShadow>
        <meshStandardMaterial color="#9AA1A8" roughness={1} transparent opacity={0.82} />
      </mesh>
    </group>
  )
}

// ---------------------------------------------------------------------------------------------------------
// Etichette HTML (testo nitido, stile delle pillole della UI).

function RoomLabels({ anchors }: { anchors: Anchors }) {
  const data = useApp((s) => s.data)!
  const metric = useApp((s) => s.metric)
  const select = useApp((s) => s.select)
  const selectedId = useApp((s) => s.selectedId)
  return (
    <>
      {DEPARTMENTS.map((d) => {
        const p = anchors.labels[d]
        const dept = data.summary.departments.find((x) => x.id === d)
        if (!p || !dept) return null
        const on = selectedId === `room:${d}`
        return (
          <Html key={d} position={[p.x, p.y + 0.6, p.z]} center zIndexRange={[20, 0]}>
            <button
              onClick={() => select(`room:${d}`)}
              className={`pill-shadow flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-[13px] font-semibold transition ${
                on ? 'bg-ink text-white' : 'bg-white text-ink hover:scale-105'
              }`}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: DEPT_ACCENT[d] }} />
              {DEPT_LABEL[d]}
              <span className={on ? 'text-white/70' : 'text-muted'}>{fmtMetric(dept.metrics[metric], metric)}</span>
            </button>
          </Html>
        )
      })}
    </>
  )
}

const FLAG: Record<LocationId, string> = { CH: '🇨🇭', DE: '🇩🇪', IE: '🇮🇪', EU: '🇪🇺' }

function IslandCards({ anchors }: { anchors: Anchors }) {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  const select = useApp((s) => s.select)
  const { now, base } = useMemo(() => locationTotals(data, active), [data, active])
  return (
    <>
      {Object.entries(anchors.islands).map(([name, p]) => {
        const loc = ISLAND_LOCATION[name]
        const l = data.summary.locations.find((x) => x.id === loc)
        if (!loc || !l) return null
        const delta = base[loc].co2_kg ? now[loc].co2_kg / base[loc].co2_kg - 1 : 0
        return (
          <Html key={name} position={[p.x, p.y - 2.6, p.z]} center zIndexRange={[20, 0]}>
            <button
              onClick={() => select(`loc:${name}`)}
              title={`Rete ${l.grid_kg_per_kwh.mid} kg CO₂/kWh`}
              className="pill-shadow flex items-center gap-1.5 whitespace-nowrap rounded-full bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:scale-105"
            >
              <span className="h-2 w-2 rounded-full" style={{ background: gridColor(l.grid_kg_per_kwh.mid) }} />
              {FLAG[loc]} {l.label}
              <span className="font-normal text-muted">{fmtMetric(now[loc].co2_kg, 'co2_kg')}</span>
              {delta < -0.005 && <span className="text-primary">{Math.round(delta * 100)}%</span>}
            </button>
          </Html>
        )
      })}
    </>
  )
}

// ---------------------------------------------------------------------------------------------------------
// Badge: uno per risorsa, con il testo che conta nella fase scelta (scoperta, effetto della misura, limite).

const LIMIT_ICON = { window: '🕒', block: '🔒', human: '👤', contradiction: '⚠️' } as const

function Badges({ ctx }: { ctx: Ctx }) {
  const mode = useApp((s) => s.mode)
  const select = useApp((s) => s.select)
  const badges = useMemo(() => {
    const out: { id: string; text: string; cls: string }[] = []
    for (const eff of ctx.entities.values()) {
      const e = eff.entity
      let id = sceneIdFor(ctx, ctx.data.layout, e.id)
      if (eff.moved) id = ctx.data.layout.find((i) => i.view === 'island' && i.resourceId === id)?.id ?? id
      if (!id) continue
      if (mode === 'find') {
        const f = ctx.data.findings.find((x) => x.entity_id === e.id)
        if (f) out.push({ id, text: f.title, cls: f.severity === 'high' ? 'bg-ink text-white' : 'bg-warn-soft text-warn' })
      } else if (mode === 'decide') {
        if (eff.reduction > 0)
          out.push({
            id,
            text: `${eff.visual === 'removed' ? 'Dismesso' : eff.visual === 'off' ? 'Spento' : 'Ridotto'} −${Math.round(eff.reduction * 100)}%${eff.moved ? ' · ora a Zurigo' : ''}`,
            cls: 'bg-primary text-white',
          })
      } else if (mode === 'limits') {
        const l = ctx.data.limits.find((x) => x.entity_id === e.id && x.type !== 'window') ?? ctx.data.limits.find((x) => x.entity_id === e.id)
        if (l)
          out.push({
            id,
            text: `${LIMIT_ICON[l.type]} ${l.title}`,
            cls: l.type === 'block' ? 'bg-error-soft text-error' : l.type === 'human' ? 'bg-human-soft text-human' : l.type === 'contradiction' ? 'bg-warn-soft text-warn' : 'bg-lock-soft text-lock',
          })
      }
    }
    return out
  }, [ctx, mode])
  return (
    <>
      {badges.map((b) => {
        const r = registry.items.get(b.id)
        if (!r) return null
        return (
          <Html key={b.id} position={[r.pos.x, r.pos.y + r.h + 0.5, r.pos.z]} center zIndexRange={[19, 0]}>
            <button onClick={() => select(b.id)} className={`pill-shadow whitespace-nowrap rounded-full px-2.5 py-1 text-[12px] font-semibold ${b.cls}`}>
              {b.text}
            </button>
          </Html>
        )
      })}
    </>
  )
}

// ---------------------------------------------------------------------------------------------------------
// Tooltip al passaggio del mouse e anello di selezione.

function Hover({ ctx, statuses }: { ctx: Ctx; statuses: Map<string, ItemStatus> }) {
  const hoverId = useApp((s) => s.hoverId)
  const selectedId = useApp((s) => s.selectedId)
  const metric = useApp((s) => s.metric)
  if (!hoverId || hoverId === selectedId) return null
  if (hoverId.startsWith('room:')) return null
  const r = registry.items.get(hoverId)
  if (!r) return null
  const st = statuses.get(hoverId)
  const line = st?.info?.headline ?? (st?.entity ? fmtMetric(st.entity.metrics[metric], metric) + ' / anno' : '')
  return (
    <Html position={[r.pos.x, r.pos.y + r.h + 0.35, r.pos.z]} center zIndexRange={[30, 0]} style={{ pointerEvents: 'none' }}>
      <div className="pill-shadow max-w-64 rounded-xl bg-white px-3 py-2 text-left">
        <div className="text-[13px] font-semibold leading-tight text-ink">{labelOf(ctx, r.item)}</div>
        {line && <div className="mt-0.5 text-[12px] leading-snug text-muted">{line}</div>}
      </div>
    </Html>
  )
}

function SelectionRing() {
  const selectedId = useApp((s) => s.selectedId)
  const ref = useRef<Mesh>(null)
  const r = selectedId ? registry.items.get(selectedId) : undefined
  useFrame(({ clock }) => {
    if (!ref.current || !r) return
    ref.current.position.set(r.pos.x, r.pos.y + 0.03, r.pos.z)
    const s = 1 + Math.sin(clock.elapsedTime * 3) * 0.06
    ref.current.scale.setScalar(s)
  })
  if (!r) return null
  const radius = Math.max(0.55, r.h * 0.55)
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null}>
      <ringGeometry args={[radius, radius + 0.09, 48]} />
      <meshBasicMaterial color="#1E7A55" toneMapped={false} />
    </mesh>
  )
}
