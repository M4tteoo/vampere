import { useEffect, useMemo, useRef } from 'react'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import { Box3, Color, Group, Mesh, MeshStandardMaterial, Object3D, Vector3 } from 'three'
import { useApp } from '../../store'
import { DEPARTMENTS, DEPT_ACCENT, effectiveOf, makeCtx, resourceOf, statusOf, type Ctx } from '../../data/twin'
import type { LayoutItem } from '../../data/types'
import { MODELS, preloadKits } from './kit'
import { KitInstances, type Inst } from './KitInstances'
import { focusPlanes, islandGhostMaterial, setClipBox, type Box2 } from './clip'
import { GLOW, LED, PROVIDER, SCREEN } from './colors'
import { useAnchors } from './Environment'
import { useScreen } from './screen'

const OFFICE = `${MODELS}/env_office_v1.glb`
const ISLANDS = `${MODELS}/env_islands_v1.glb`
useGLTF.preload(OFFICE)
preloadKits(['desk_bench', 'chair_task', 'monitor_27', 'monitor_dual', 'pc_tower', 'hw_compute', 'hw_cluster', 'hw_database', 'hw_storage', 'hw_gpu'])

const ROOMS = DEPARTMENTS as readonly string[]
/** Margine del ritaglio oltre il pavimento: include metà dei muri della stanza. */
const MARGIN = 0.14
const HOVER = new Color('#DCEFE3')
const CLOUD_LOCATIONS = ['CH', 'DE', 'IE']
/** Isole in ordine fisso (dall'alto in basso quando sono impilate). */
export const ISLAND_ORDER = ['zurich', 'frankfurt', 'dublin'] as const
export const ISLAND_LABEL: Record<string, string> = { zurich: 'Zurich', frankfurt: 'Frankfurt', dublin: 'Dublin' }

/** Altezza del palco laterale rispetto a quello principale, e spazio fra i due (in larghezze del principale). */
const SIDE = 0.36
const GAP = 0.16
/** Altezza dei muri e dell'hardware, per l'ingombro. */
const WALL_H = 2.6

const HEIGHT: Record<string, number> = { desk_bench: 1.2, hw_compute: 2, hw_cluster: 2.1, hw_database: 1.9, hw_storage: 0.8, hw_gpu: 1.1 }

/** Angolo fisso della camera nei reparti (da sud-est). Si girano gli oggetti, non la camera. */
export const ISO = new Vector3(1, 0.95, 1).normalize()
/** Assi dello schermo in coordinate mondo per quell'angolo: destra e su. */
const RIGHT = new Vector3(1, 0, -1).normalize()
const UP = new Vector3().crossVectors(RIGHT, ISO.clone().negate()).normalize()

export type Space = 'office' | 'islands'

export interface OfficeInfo {
  rooms: Record<string, { center: Vector3; size: Vector3; box: Box2 }>
  office: { center: Vector3; size: Vector3; box: Box2 }
}

/** Stanze e ingombro dell'ufficio, letti dai pavimenti del modello di Blender. */
export function useOffice(): OfficeInfo {
  const office = useGLTF(OFFICE).scene
  return useMemo(() => {
    office.updateMatrixWorld(true)
    const rooms: OfficeInfo['rooms'] = {}
    office.traverse((o) => {
      if (!o.name.startsWith('floor_')) return
      const b = new Box3().setFromObject(o)
      rooms[o.name.slice(6)] = {
        center: b.getCenter(new Vector3()),
        size: b.getSize(new Vector3()),
        box: { minX: b.min.x - MARGIN, maxX: b.max.x + MARGIN, minZ: b.min.z - MARGIN, maxZ: b.max.z + MARGIN },
      }
    })
    const b = new Box3().setFromObject(office)
    return {
      rooms,
      office: { center: b.getCenter(new Vector3()), size: b.getSize(new Vector3()), box: { minX: b.min.x - 1, maxX: b.max.x + 1, minZ: b.min.z - 1, maxZ: b.max.z + 1 } },
    }
  }, [office])
}

interface IslandInfo {
  object: Object3D
  /** Ingombro nelle coordinate del modello, hardware compreso. */
  box: Box3
  center: Vector3
}

/** Le tre isole come oggetti separati (copie che condividono le geometrie), così si possono impilare e girare una per una. */
function useIslands(): Record<string, IslandInfo> {
  useAnchors() // toglie l'isola «UE mista»
  const islands = useGLTF(ISLANDS).scene
  return useMemo(() => {
    islands.updateMatrixWorld(true)
    const out: Record<string, IslandInfo> = {}
    for (const name of ISLAND_ORDER) {
      const node = islands.getObjectByName(`island_${name}`)
      if (!node) continue
      const box = new Box3().setFromObject(node)
      box.max.y = Math.max(box.max.y, box.min.y + 5)
      const object = node.clone(true)
      if (node.parent) object.applyMatrix4(node.parent.matrixWorld)
      object.traverse((o) => {
        const mesh = o as Mesh
        if (!mesh.isMesh) return
        mesh.castShadow = true
        mesh.receiveShadow = true
      })
      out[name] = { object, box, center: box.getCenter(new Vector3()) }
    }
    return out
  }, [islands])
}

/** Gruppi animati: l'ufficio, il palco delle isole e, dentro, ogni isola (già centrata). Servono a ritaglio e scritte. */
export const stageGroups: Record<Space, Group | null> = { office: null, islands: null }
export const islandGroups: Record<string, Group | null> = {}

/** Posizioni locali (dentro il proprio gruppo) degli oggetti cliccabili. */
export const allocRegistry = new Map<string, { pos: Vector3; h: number; item: LayoutItem; space: Space }>()

/** Gruppo in cui vivono le coordinate di un oggetto registrato. */
function groupOf(entry: { space: Space; item: LayoutItem }): Group | null {
  return entry.space === 'islands' ? (islandGroups[entry.item.island ?? ''] ?? null) : stageGroups.office
}

/** Risorse cloud (con un luogo fisico) usate da un reparto: proprietario oppure quota nella ripartizione. */
export function cloudResourcesOf(ctx: Ctx, room: string): Set<string> {
  const out = new Set<string>()
  for (const { entity: e } of ctx.entities.values()) {
    if (!CLOUD_LOCATIONS.includes(e.location) || e.id.startsWith('lic:')) continue
    if (e.department === room || e.allocation?.some((a) => a.department === room)) out.add(e.id)
  }
  return out
}

/** Isole su cui il reparto usa almeno un oggetto, con gli oggetti usati. */
export function islandsOf(ctx: Ctx, room: string): { name: string; items: LayoutItem[] }[] {
  const used = cloudResourcesOf(ctx, room)
  const by: Record<string, LayoutItem[]> = {}
  for (const item of ctx.data.layout) {
    if (item.view !== 'island' || !item.island) continue
    const eff = effectiveOf(ctx, resourceOf(item))
    if (eff && used.has(eff.entity.id)) (by[item.island] ??= []).push(item)
  }
  return ISLAND_ORDER.filter((n) => by[n]).map((name) => ({ name, items: by[name] }))
}

function ancestor(o: Object3D | null, prefix: string): string | null {
  for (let x = o; x; x = x.parent) if (x.name.startsWith(prefix)) return x.name.slice(prefix.length)
  return null
}

function rotate(x: number, z: number, a: number): [number, number] {
  const c = Math.cos(a)
  const s = Math.sin(a)
  return [x * c + z * s, -x * s + z * c]
}

/** Mezza larghezza e mezza altezza sullo schermo di un insieme di punti attorno al loro centro. */
function extent(pts: Vector3[]) {
  let w = 0
  let h = 0
  for (const p of pts) {
    w = Math.max(w, Math.abs(p.dot(RIGHT)))
    h = Math.max(h, Math.abs(p.dot(UP)))
  }
  return { w, h }
}

/** Isole tondeggianti: un'ellisse in basso e una in alto descrive l'ingombro meglio degli angoli del riquadro. */
function ellipse(min: Vector3, max: Vector3, c: Vector3) {
  const out: Vector3[] = []
  const rx = (max.x - min.x) / 2
  const rz = (max.z - min.z) / 2
  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * Math.PI * 2
    for (const y of [min.y, max.y]) out.push(new Vector3(Math.cos(a) * rx, y - c.y, Math.sin(a) * rz))
  }
  return out
}

function corners(min: Vector3, max: Vector3, c: Vector3) {
  const out: Vector3[] = []
  for (const x of [min.x, max.x]) for (const y of [min.y, max.y]) for (const z of [min.z, max.z]) out.push(new Vector3(x - c.x, y - c.y, z - c.z))
  return out
}

interface Pose {
  /** Dove sta il centro dell'oggetto, in coordinate mondo. */
  pos: Vector3
  s: number
}

export interface StageLayout {
  /** Centro di rotazione dell'ufficio (centro della stanza a mezza altezza). */
  pivot: Vector3
  office: Pose
  islands: Pose | null
  /** Isole mostrate (dall'alto in basso) e loro posto nel palco delle isole. */
  shown: string[]
  offsets: Record<string, Vector3>
  /** Palco effettivo: senza isole si vede solo l'ufficio. */
  stage: 'office' | 'cloud'
  /** Riquadro da inquadrare: centro in mondo e mezze misure sullo schermo (in metri). */
  frame: { center: Vector3; w: number; h: number }
  /** Angoli di tutto ciò che si vede, in coordinate mondo: la camera li fa entrare con la prospettiva vera. */
  points: Vector3[]
}

/**
 * Disposizione «scelta del personaggio»: l'oggetto in primo piano al centro, l'altro piccolo di lato
 * (isole a destra, oppure ufficio a sinistra), senza sovrapporsi. Le isole usate sono impilate in colonna.
 */
function layoutFor(info: OfficeInfo, isl: Record<string, IslandInfo>, room: string, wanted: 'office' | 'cloud', shown: string[]): StageLayout | null {
  const r = info.rooms[room]
  if (!r) return null
  const b = r.box
  const pivot = new Vector3(r.center.x, WALL_H / 2, r.center.z)
  const office = extent(corners(new Vector3(b.minX, 0, b.minZ), new Vector3(b.maxX, WALL_H, b.maxZ), pivot))

  // Colonna di isole: centri allineati sullo schermo, una sotto l'altra.
  const offsets: Record<string, Vector3> = {}
  let stack: { w: number; h: number } | null = null
  const list = shown.filter((n) => isl[n])
  if (list.length) {
    const exts = list.map((n) => extent(ellipse(isl[n].box.min, isl[n].box.max, isl[n].center)))
    const gap = 0.12 * Math.max(...exts.map((e) => e.h))
    const ys: number[] = []
    exts.forEach((e, i) => ys.push(i ? ys[i - 1] - exts[i - 1].h - gap - e.h : 0))
    const top = ys[0] + exts[0].h
    const bottom = ys[ys.length - 1] - exts[exts.length - 1].h
    const mid = (top + bottom) / 2
    // Spostate lungo l'asse «su» della camera: cambia solo l'altezza sullo schermo, non la distanza (niente prospettiva diversa).
    list.forEach((n, i) => (offsets[n] = UP.clone().multiplyScalar(ys[i] - mid)))
    stack = { w: Math.max(...exts.map((e) => e.w)), h: (top - bottom) / 2 }
  }

  const stage = wanted === 'cloud' && stack ? 'cloud' : 'office'
  const main = stage === 'cloud' ? stack! : office
  const side = stage === 'cloud' ? office : stack
  const M = pivot.clone()
  const mainPose: Pose = { pos: M.clone(), s: 1 }
  let sidePose: Pose | null = null
  let minX = -main.w
  let maxX = main.w
  let h = main.h
  if (side) {
    const s = Math.min((SIDE * main.h) / side.h, (0.5 * main.w) / side.w)
    const dir = stage === 'cloud' ? -1 : 1
    const x = dir * (main.w * (1 + GAP) + side.w * s)
    sidePose = { pos: M.clone().addScaledVector(RIGHT, x), s }
    minX = Math.min(minX, x - side.w * s)
    maxX = Math.max(maxX, x + side.w * s)
    h = Math.max(h, side.h * s)
  }
  const officePose = stage === 'office' ? mainPose : sidePose!
  const islandsPose = stack ? (stage === 'cloud' ? mainPose : sidePose) : null
  const points = corners(new Vector3(b.minX, -0.64, b.minZ), new Vector3(b.maxX, WALL_H, b.maxZ), pivot).map((p) => p.multiplyScalar(officePose.s).add(officePose.pos))
  if (islandsPose)
    for (const n of list)
      for (const p of ellipse(isl[n].box.min, isl[n].box.max, isl[n].center)) points.push(p.add(offsets[n]).multiplyScalar(islandsPose.s).add(islandsPose.pos))
  return {
    pivot,
    office: officePose,
    islands: islandsPose,
    shown: list,
    offsets,
    stage,
    frame: { center: M.clone().addScaledVector(RIGHT, (minX + maxX) / 2), w: (maxX - minX) / 2, h },
    points,
  }
}

/** Disposizione dei palchi per il reparto e il palco scelti (usata dalla scena e dalla camera). */
export function useStageLayout(): StageLayout | null {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const stage = useApp((s) => s.stage)
  const info = useOffice()
  const isl = useIslands()
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const key = useMemo(() => (room ? islandsOf(ctx, room).map((x) => x.name) : []).join(','), [ctx, room])
  return useMemo(() => (room ? layoutFor(info, isl, room, stage, key ? key.split(',') : []) : null), [info, isl, room, stage, key])
}

/**
 * Passo 1 · Allocation.
 * Pianta dall'alto → clic su un reparto → due «palchi» come nella scelta del personaggio dei videogiochi:
 * l'ufficio da solo (software e servizi, si clicca sui computer) e le isole che il reparto usa davvero (hardware cloud).
 */
export function AllocationScene() {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const setRoom = useApp((s) => s.setRoom)
  const setStage = useApp((s) => s.setStage)
  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)
  const info = useOffice()
  const isl = useIslands()
  const layout = useStageLayout()
  const stage = layout?.stage ?? 'office'
  const ctx = useMemo(() => makeCtx(data, []), [data])

  // Ufficio: solo i computer (postazione = scrivania + sedia + monitor + case).
  const seats = useMemo(() => data.layout.filter((i) => i.id.startsWith('seat:') && i.room && ROOMS.includes(i.room)), [data.layout])
  const used = useMemo(() => (room ? cloudResourcesOf(ctx, room) : new Set<string>()), [ctx, room])

  const officeAssets = useMemo(() => {
    const out: Record<string, Inst[]> = {}
    const push = (asset: string, inst: Inst) => (out[asset] ??= []).push(inst)
    for (const item of seats) {
      const st = statusOf(ctx, item)
      const accent = DEPT_ACCENT[item.room ?? ''] ?? '#E9E4DA'
      const base = { itemId: item.id, rotY: item.rotY, scale: 1, blink: false, activity: st.activity, pickable: true, room: item.room }
      push(item.asset, { ...base, key: item.id, pos: item.pos, colors: { screen: SCREEN[st.visual], accent } })
      allocRegistry.set(item.id, { pos: new Vector3(...item.pos), h: HEIGHT[item.asset] ?? 1, item, space: 'office' })
      for (const [ci, child] of (item.children ?? []).entries()) {
        const [dx, dz] = rotate(child.pos[0], child.pos[2], item.rotY)
        push(child.asset, {
          ...base,
          key: `${item.id}/${ci}`,
          pos: [item.pos[0] + dx, item.pos[1] + child.pos[1], item.pos[2] + dz],
          rotY: item.rotY + child.rotY,
          colors: { screen: SCREEN[st.visual], accent, led: LED[st.visual] },
        })
      }
    }
    return out
  }, [seats, ctx])

  // Hardware di ogni isola: a colori (e cliccabile) se il reparto lo usa, fantasma altrimenti.
  const islandAssets = useMemo(() => {
    const out: Record<string, { on: Record<string, Inst[]>; off: Record<string, Inst[]> }> = {}
    for (const item of data.layout) {
      if (item.view !== 'island' || !item.island) continue
      const eff = effectiveOf(ctx, resourceOf(item))
      const isUsed = !!eff && used.has(eff.entity.id)
      const st = statusOf(ctx, item)
      const inst: Inst = {
        itemId: item.id,
        key: item.id,
        pos: item.pos,
        rotY: item.rotY,
        scale: 1,
        blink: false,
        activity: st.activity,
        pickable: isUsed,
        colors: { led: LED[st.visual], screen: SCREEN[st.visual], glow: GLOW[st.visual], provider: PROVIDER[eff?.entity.provider ?? ''] ?? '#B9B4AC' },
      }
      const g = (out[item.island] ??= { on: {}, off: {} })
      ;((isUsed ? g.on : g.off)[item.asset] ??= []).push(inst)
      allocRegistry.set(item.id, { pos: new Vector3(...item.pos), h: HEIGHT[item.asset] ?? 1.5, item, space: 'islands' })
    }
    return out
  }, [data.layout, ctx, used])

  const roomOf = (id: string) => allocRegistry.get(id)?.item.room ?? null
  const onOfficeHover = (id: string | null) => {
    if (!id) return hover(null)
    if (!room) hover(`room:${roomOf(id)}`)
    else hover(stage === 'office' ? id : 'stage:office')
  }
  const onOfficeSelect = (id: string) => {
    if (!room) {
      const r = roomOf(id)
      if (r) setRoom(r)
    } else if (stage === 'cloud') setStage('office')
    else select(id)
  }
  const onIslandHover = (id: string | null) => hover(id ? (stage === 'cloud' ? id : 'stage:cloud') : null)
  const onIslandSelect = (id: string) => (stage === 'office' ? setStage('cloud') : select(id))

  return (
    <group>
      <group ref={(g) => void (stageGroups.office = g)}>
        <OfficeModel info={info} stage={stage} />
        {Object.entries(officeAssets).map(([asset, list]) => (
          <KitInstances key={asset} asset={asset} instances={list} onHover={onOfficeHover} onSelect={onOfficeSelect} pickRoom={room} />
        ))}
        {room && <SelectionRing space="office" />}
      </group>

      {room && layout?.islands && (
        <group key={room} ref={(g) => void (stageGroups.islands = g)}>
          {layout.shown.map((name) => (
            <group key={name} position={layout.offsets[name]} name={`turn_${name}`}>
              <group position={isl[name].center.clone().negate()} ref={(g) => void (islandGroups[name] = g)}>
                <IslandModel object={isl[name].object} stage={stage} />
                {Object.entries(islandAssets[name]?.on ?? {}).map(([asset, list]) => (
                  <KitInstances key={`on-${asset}`} asset={asset} instances={list} onHover={onIslandHover} onSelect={onIslandSelect} unclipped />
                ))}
                {Object.entries(islandAssets[name]?.off ?? {}).map(([asset, list]) => (
                  <KitInstances key={`off-${asset}`} asset={asset} instances={list} onHover={() => {}} onSelect={() => {}} ghost={islandGhostMaterial} />
                ))}
                <SelectionRing space="islands" island={name} />
              </group>
            </group>
          ))}
        </group>
      )}

      <StageController info={info} layout={layout} />
      <Projector info={info} isl={isl} layout={layout} />
    </group>
  )
}

/** Edificio (un solo modello): pavimenti cliccabili nella pianta; nel reparto resta solo la stanza scelta. */
function OfficeModel({ info, stage }: { info: OfficeInfo; stage: 'office' | 'cloud' }) {
  const office = useGLTF(OFFICE).scene
  const room = useApp((s) => s.room)
  const hoverId = useApp((s) => s.hoverId)
  const setRoom = useApp((s) => s.setRoom)
  const setStage = useApp((s) => s.setStage)
  const hover = useApp((s) => s.hover)
  const select = useApp((s) => s.select)

  const floors = useMemo(() => {
    const map: Record<string, { mat: MeshStandardMaterial; base: Color }> = {}
    office.traverse((o) => {
      const mesh = o as Mesh
      if (!mesh.isMesh) return
      mesh.castShadow = true
      mesh.receiveShadow = true
      const r = ancestor(mesh, 'floor_')
      if (r && ROOMS.includes(r)) {
        if (!mesh.userData.ownMaterial) {
          mesh.material = (mesh.material as MeshStandardMaterial).clone()
          mesh.userData.ownMaterial = true
        }
        const mat = mesh.material as MeshStandardMaterial
        map[r] = { mat, base: (mesh.userData.base as Color | undefined) ?? mat.color.clone() }
        mesh.userData.base = map[r].base
      } else {
        mesh.raycast = () => {}
      }
      for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) m.clippingPlanes = focusPlanes
    })
    return map
  }, [office])

  // Evidenzia il reparto sotto il mouse (solo nella pianta).
  useEffect(() => {
    const hovered = !room && hoverId?.startsWith('room:') ? hoverId.slice(5) : null
    for (const [r, f] of Object.entries(floors)) f.mat.color.copy(f.base).lerp(HOVER, r === hovered ? 0.85 : 0)
    document.body.style.cursor = hovered || (room && hoverId) ? 'pointer' : 'auto'
  }, [hoverId, room, floors])

  const box = room ? info.rooms[room]?.box : null

  return (
    <>
      <primitive
        object={office}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          const r = ancestor(e.object, 'floor_')
          if (!r || !ROOMS.includes(r)) return
          e.stopPropagation()
          if (!room) setRoom(r)
          else if (stage === 'cloud') setStage('office')
          else if (r === room) select(null)
        }}
        onPointerMove={(e: ThreeEvent<PointerEvent>) => {
          const r = ancestor(e.object, 'floor_')
          if (!r || !ROOMS.includes(r)) return
          if (!room) {
            e.stopPropagation()
            hover(`room:${r}`)
          } else if (stage === 'cloud' && r === room) {
            e.stopPropagation()
            hover('stage:office')
          }
        }}
        onPointerOut={() => hover(null)}
      />
      {/* Zoccolo del reparto ritagliato: chiude il taglio del basamento, come un plastico. */}
      {box && (
        <mesh position={[(box.minX + box.maxX) / 2, -0.33, (box.minZ + box.maxZ) / 2]} receiveShadow raycast={() => null}>
          <boxGeometry args={[box.maxX - box.minX, 0.62, box.maxZ - box.minZ]} />
          <meshStandardMaterial color="#C7A27C" roughness={0.9} />
        </mesh>
      )}
    </>
  )
}

/** Un'isola: nel palco laterale un clic porta le isole al centro. */
function IslandModel({ object, stage }: { object: Object3D; stage: 'office' | 'cloud' }) {
  const setStage = useApp((s) => s.setStage)
  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)
  return (
    <primitive
      object={object}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation()
        if (stage === 'office') setStage('cloud')
        else select(null)
      }}
      onPointerMove={(e: ThreeEvent<PointerEvent>) => {
        if (stage !== 'office') return
        e.stopPropagation()
        hover('stage:cloud')
      }}
      onPointerOut={() => hover(null)}
    />
  )
}

interface Live {
  pos: Vector3
  s: number
}

/**
 * Anima i palchi verso la disposizione scelta (posizione e scala) e gira solo l'oggetto in primo piano:
 * l'ufficio attorno al centro della stanza, ogni isola attorno al proprio centro.
 * Il ritaglio del reparto segue l'ufficio.
 */
function StageController({ info, layout }: { info: OfficeInfo; layout: StageLayout | null }) {
  const room = useApp((s) => s.room)
  const turns = useApp((s) => s.turns)
  const cur = useRef<{ office: Live | null; islands: Live | null; angle: { office: number; cloud: number } }>({ office: null, islands: null, angle: { office: 0, cloud: 0 } })
  const tmp = useMemo(() => new Vector3(), [])

  useFrame((_, dt) => {
    const og = stageGroups.office
    if (!og) return
    const c = cur.current
    const r = room ? info.rooms[room] : undefined
    if (!r || !layout) {
      // Pianta: ufficio fermo al suo posto.
      og.position.set(0, 0, 0)
      og.rotation.set(0, 0, 0)
      og.scale.setScalar(1)
      c.office = null
      c.islands = null
      c.angle = { office: 0, cloud: 0 }
    } else {
      const k = Math.min(1, dt * 4)
      const ka = Math.min(1, dt * 5)
      c.angle.office += (turns.office * Math.PI - c.angle.office) * ka
      c.angle.cloud += (turns.cloud * Math.PI - c.angle.cloud) * ka

      const o = (c.office ??= { pos: layout.pivot.clone(), s: 1 })
      o.pos.lerp(layout.office.pos, k)
      o.s += (layout.office.s - o.s) * k
      // Gira e scala attorno al centro della stanza: posizione = punto sul palco − scala × (rotazione × centro).
      og.rotation.set(0, c.angle.office, 0)
      og.scale.setScalar(o.s)
      og.position.copy(o.pos).sub(tmp.copy(layout.pivot).applyAxisAngle(og.up, c.angle.office).multiplyScalar(o.s))

      const ig = stageGroups.islands
      if (ig && layout.islands) {
        const i = (c.islands ??= { pos: layout.islands.pos.clone(), s: layout.islands.s })
        i.pos.lerp(layout.islands.pos, k)
        i.s += (layout.islands.s - i.s) * k
        ig.position.copy(i.pos)
        ig.scale.setScalar(i.s)
        for (const child of ig.children) child.rotation.y = c.angle.cloud
      } else c.islands = null
    }
    og.updateMatrixWorld()
    setClipBox(r ? r.box : { minX: -1e4, maxX: 1e4, minZ: -1e4, maxZ: 1e4 }, og.matrixWorld)
  })
  return null
}

/** Proietta sullo schermo i punti delle scritte HTML: nomi dei reparti, tooltip, titoli dei palchi e nomi delle isole. */
function Projector({ info, isl, layout }: { info: OfficeInfo; isl: Record<string, IslandInfo>; layout: StageLayout | null }) {
  const room = useApp((s) => s.room)
  const hoverId = useApp((s) => s.hoverId)
  const setPoints = useScreen((s) => s.set)
  const v = useMemo(() => new Vector3(), [])
  useFrame(({ camera, size }) => {
    const pts: Record<string, [number, number]> = {}
    const project = (p: Vector3, g: Group | null): [number, number] => {
      v.copy(p)
      if (g) v.applyMatrix4(g.matrixWorld)
      v.project(camera)
      return [Math.round(((v.x + 1) / 2) * size.width), Math.round(((1 - v.y) / 2) * size.height)]
    }
    // Pianta: angolo in alto a sinistra di ogni reparto (nord in alto = z minima, ovest a sinistra = x minima).
    if (!room) for (const r of ROOMS) { const b = info.rooms[r]?.box; if (b) pts[`room:${r}`] = project(new Vector3(b.minX + MARGIN, 1.25, b.minZ + MARGIN), stageGroups.office) }
    const h = hoverId ? allocRegistry.get(hoverId) : undefined
    if (room && h) pts.hover = project(h.pos.clone().setY(h.pos.y + h.h + 0.3), groupOf(h))
    if (room && layout && info.rooms[room]) {
      const b = info.rooms[room].box
      const top = (ps: [number, number][]) => [Math.round(ps.reduce((a, q) => a + q[0], 0) / ps.length), Math.min(...ps.map((q) => q[1]))] as [number, number]
      pts['stage:office'] = top([b.minX, b.maxX].flatMap((x) => [b.minZ, b.maxZ].map((z) => project(new Vector3(x, WALL_H / 2, z), stageGroups.office))))
      const all: [number, number][] = []
      for (const name of layout.shown) {
        const ib = isl[name].box
        const g = islandGroups[name] ?? null
        const ps = [ib.min.x, ib.max.x].flatMap((x) => [ib.min.z, ib.max.z].map((z) => project(new Vector3(x, ib.min.y + 0.4, z), g)))
        all.push(...[ib.min.x, ib.max.x].flatMap((x) => [ib.min.z, ib.max.z].map((z) => project(new Vector3(x, ib.max.y, z), g))))
        // Nome dell'isola: a destra (a sinistra c'è l'ufficio rimpicciolito), a metà altezza.
        pts[`island:${name}`] = [Math.max(...ps.map((q) => q[0])), Math.round(ps.reduce((a, q) => a + q[1], 0) / ps.length)]
      }
      if (all.length) pts['stage:cloud'] = top(all)
    }
    setPoints(pts)
  })
  return null
}

function SelectionRing({ space, island }: { space: Space; island?: string }) {
  const selectedId = useApp((s) => s.selectedId)
  const ref = useRef<Group>(null)
  const r = selectedId ? allocRegistry.get(selectedId) : undefined
  useFrame(({ clock }) => {
    if (!ref.current || !r) return
    ref.current.position.set(r.pos.x, r.pos.y + 0.25, r.pos.z)
    ref.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 3) * 0.05)
  })
  if (!r || r.space !== space || (island && r.item.island !== island)) return null
  const radius = r.item.asset === 'hw_cluster' ? 1.9 : r.item.asset === 'hw_storage' ? 1.1 : Math.max(0.6, Math.min(1.2, r.h * 0.5))
  return (
    <group ref={ref}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} raycast={() => null}>
        <ringGeometry args={[radius, radius + 0.08, 48]} />
        <meshBasicMaterial color="#1F7A57" toneMapped={false} />
      </mesh>
    </group>
  )
}
