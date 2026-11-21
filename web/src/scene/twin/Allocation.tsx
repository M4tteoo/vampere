import { useEffect, useMemo, useRef } from 'react'
import { useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import { Box3, BufferGeometry, Color, Group, Material, Mesh, MeshBasicMaterial, MeshStandardMaterial, Object3D, Vector3 } from 'three'
import { useApp } from '../../store'
import { DEPARTMENTS, DEPT_ACCENT, effectiveOf, makeCtx, resourceOf, statusOf, type Ctx } from '../../data/twin'
import type { LayoutItem } from '../../data/types'
import { ISLAND_LOC, unitOf } from '../../data/usage'
import { MODELS, kitUrl, preloadKits } from './kit'
import { KitInstances, type Inst } from './KitInstances'
import { focusPlanes, islandGhostMaterial, setClipBox, type Box2 } from './clip'
import { GLOW, LED, PROVIDER, SCREEN } from './colors'
import { useAnchors } from './Environment'
import { useScreen } from './screen'
import { useHeat, type HeatView } from './heat'
import { BlueprintBuild, buildGroups } from './BlueprintBuild'

const OFFICE = `${MODELS}/env_office_v1.glb`
const ISLANDS = `${MODELS}/env_islands_v1.glb`
const CLOUD = kitUrl('co2_cloud')
useGLTF.preload(OFFICE)
useGLTF.preload(CLOUD)
preloadKits(['desk_bench', 'chair_task', 'monitor_27', 'monitor_dual', 'pc_tower', 'hw_compute', 'hw_cluster', 'hw_database', 'hw_storage', 'hw_gpu'])

const ROOMS = DEPARTMENTS as readonly string[]
/** Margine del ritaglio oltre il pavimento: include metà dei muri della stanza. */
const MARGIN = 0.14
const HOVER = new Color('#DCEFE3')
const CLOUD_LOCATIONS = ['CH', 'DE', 'IE']
/** Isole in ordine fisso (dall'alto in basso / da sinistra a destra). */
export const ISLAND_ORDER = ['zurich', 'frankfurt', 'dublin'] as const
export const ISLAND_LABEL: Record<string, string> = { zurich: 'Zurich', frankfurt: 'Frankfurt', dublin: 'Dublin' }

/** Altezza del palco laterale rispetto a quello principale, e spazio fra i due (in larghezze del principale). */
const SIDE = 0.36
const GAP = 0.16
/** Aria intorno alle isole al centro (1 = toccano i bordi): più alto = isole più piccole. */
const ISLAND_ROOM = 1.35
/** Altezza dei muri, per l'ingombro. */
const WALL_H = 2.6
/** Spazio occupato dalla UI (px), per scegliere la disposizione delle isole. */
const UI_W = 48
const UI_H = 220

const HEIGHT: Record<string, number> = { desk_bench: 1.2, hw_compute: 2, hw_cluster: 2.1, hw_database: 1.9, hw_storage: 0.8, hw_gpu: 1.1 }

/** Angolo fisso della camera nei reparti (da sud-est). Si girano gli oggetti, non la camera. */
export const ISO = new Vector3(1, 0.95, 1).normalize()
/** Camera della pianta: dall'alto, nord in alto. */
export const TOP = new Vector3(0, 1, 0.001).normalize()
/** Assi dello schermo in coordinate mondo nella vista isometrica: destra e su. */
const RIGHT = new Vector3(1, 0, -1).normalize()
const UP = new Vector3().crossVectors(RIGHT, ISO.clone().negate()).normalize()

/** Colori «neutri» della mappa a colori (passi 2–4): ufficio e isole diventano un plastico bianco. */
const NEUTRAL_WALL = '#ECE9E3'
const NEUTRAL_FLOOR = new Color('#F5F3EF')
const NEUTRAL_ISLAND = '#E6E2DA'

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
      office: { center: b.getCenter(new Vector3()), size: b.getSize(new Vector3()), box: { minX: b.min.x, maxX: b.max.x, minZ: b.min.z, maxZ: b.max.z } },
    }
  }, [office])
}

interface IslandInfo {
  object: Object3D
  /** Ingombro nelle coordinate del modello, hardware compreso. */
  box: Box3
  center: Vector3
}

/** Le tre isole come oggetti separati (copie che condividono le geometrie), così si possono disporre e girare una per una. */
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

/** Materiali neutri al posto di quelli di Blender (stessa trasparenza e stesso ritaglio), uno per materiale originale. */
const neutralCache = new WeakMap<Material, Material>()
function neutralOf(m: Material, color: string): Material {
  let n = neutralCache.get(m)
  if (!n) {
    n = new MeshStandardMaterial({ color, roughness: 0.92, transparent: m.transparent, opacity: m.opacity, depthWrite: m.depthWrite })
    n.clippingPlanes = m.clippingPlanes
    neutralCache.set(m, n)
  }
  return n
}

/** Passa un modello fra i colori di Blender e il plastico neutro. I pavimenti dei reparti si gestiscono a parte. */
function useNeutral(root: Object3D, on: boolean, color: string) {
  useEffect(() => {
    root.traverse((o) => {
      const mesh = o as Mesh
      if (!mesh.isMesh || mesh.userData.ownMaterial) return
      const orig = (mesh.userData.orig ??= mesh.material) as Material
      mesh.material = on ? neutralOf(orig, color) : orig
    })
  }, [root, on, color])
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

/** Mezza larghezza e mezza altezza sullo schermo (assi `right`, `up`) di un insieme di punti attorno al loro centro. */
function extent(pts: Vector3[], right = RIGHT, up = UP) {
  let w = 0
  let h = 0
  for (const p of pts) {
    w = Math.max(w, Math.abs(p.dot(right)))
    h = Math.max(h, Math.abs(p.dot(up)))
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

/** Divisioni di n isole in righe consecutive (1 → [1]; 2 → [2], [1,1]; 3 → [3], [1,2], [2,1], [1,1,1]). */
function rowings(n: number): number[][] {
  if (n === 0) return [[]]
  const out: number[][] = []
  for (let first = 1; first <= n; first++) for (const rest of rowings(n - first)) out.push([first, ...rest])
  return out
}

/** Dispone le isole in righe (centri sullo schermo, mezze misure) e restituisce l'ingombro totale. */
function arrange(exts: { w: number; h: number }[], rows: number[]) {
  const gap = 0.14 * Math.max(...exts.map((e) => Math.max(e.w, e.h)))
  const pos: [number, number][] = []
  let i = 0
  const rowData = rows.map((n) => {
    const items = exts.slice(i, i + n)
    i += n
    return { items, w: items.reduce((a, e) => a + 2 * e.w, 0) + gap * (n - 1), h: Math.max(...items.map((e) => 2 * e.h)) }
  })
  const H = rowData.reduce((a, r) => a + r.h, 0) + gap * (rows.length - 1)
  const W = Math.max(...rowData.map((r) => r.w))
  let y = H / 2
  for (const r of rowData) {
    let x = -r.w / 2
    for (const e of r.items) {
      pos.push([x + e.w, y - r.h / 2])
      x += 2 * e.w + gap
    }
    y -= r.h + gap
  }
  return { pos, w: W / 2, h: H / 2 }
}

interface Pose {
  /** Dove sta il centro dell'oggetto, in coordinate mondo. */
  pos: Vector3
  s: number
}

export interface StageLayout {
  view: 'plan' | 'iso'
  /** Centro di rotazione dell'ufficio (centro della stanza a mezza altezza; nella pianta l'origine). */
  pivot: Vector3
  office: Pose
  islands: Pose | null
  /** Isole mostrate e loro posto nel palco delle isole. */
  shown: string[]
  offsets: Record<string, Vector3>
  /** Palco effettivo: senza isole si vede solo l'ufficio. */
  stage: 'office' | 'cloud'
  /** Punti di tutto ciò che si vede, in coordinate mondo: la camera li fa entrare con la prospettiva vera. */
  points: Vector3[]
  /** Centro approssimativo dell'inquadratura (punto di partenza della camera). */
  center: Vector3
  /** Isole affiancate in una riga: i nomi vanno sotto, non a destra. */
  labelBelow: boolean
}

/** Pianta: tutto l'ufficio dall'alto; nei passi 2–4 le tre isole in colonna alla sua destra. */
function planLayout(info: OfficeInfo, isl: Record<string, IslandInfo>, withIslands: boolean): StageLayout {
  const o = info.office
  const pivot = new Vector3()
  const ob = new Box3(new Vector3(o.box.minX, 0, o.box.minZ), new Vector3(o.box.maxX, WALL_H, o.box.maxZ))
  const points = corners(ob.min, ob.max, pivot)
  const offsets: Record<string, Vector3> = {}
  let islands: Pose | null = null
  const list = withIslands ? ISLAND_ORDER.filter((n) => isl[n]) : []
  if (list.length) {
    // Dall'alto: destra = +x, su = −z. Colonna centrata, alta quanto l'ufficio.
    const exts = list.map((n) => extent(ellipse(isl[n].box.min, isl[n].box.max, isl[n].center), new Vector3(1, 0, 0), new Vector3(0, 0, -1)))
    const a = arrange(exts, list.map(() => 1))
    const s = Math.min(1, (0.98 * (o.box.maxZ - o.box.minZ)) / (2 * a.h))
    list.forEach((n, i) => (offsets[n] = new Vector3(a.pos[i][0], 0, -a.pos[i][1])))
    const pos = new Vector3(o.box.maxX + 3 + a.w * s, 0, (o.box.minZ + o.box.maxZ) / 2)
    islands = { pos, s }
    for (const n of list)
      for (const p of ellipse(isl[n].box.min, isl[n].box.max, isl[n].center)) points.push(p.add(offsets[n]).multiplyScalar(s).add(pos))
  }
  const bb = new Box3().setFromPoints(points)
  return { view: 'plan', pivot, office: { pos: pivot.clone(), s: 1 }, islands, shown: list, offsets, stage: 'office', points, center: bb.getCenter(new Vector3()), labelBelow: false }
}

/**
 * Reparto, disposizione «scelta del personaggio»: l'oggetto in primo piano al centro, l'altro piccolo di lato
 * (isole a destra, oppure ufficio a sinistra), senza sovrapporsi. Le isole usate si dispongono nelle righe che le fanno più grandi.
 */
function roomLayout(info: OfficeInfo, isl: Record<string, IslandInfo>, room: string, wanted: 'office' | 'cloud', shown: string[], aspect: number): StageLayout | null {
  const r = info.rooms[room]
  if (!r) return null
  const b = r.box
  const pivot = new Vector3(r.center.x, WALL_H / 2, r.center.z)
  const office = extent(corners(new Vector3(b.minX, 0, b.minZ), new Vector3(b.maxX, WALL_H, b.maxZ), pivot))

  // Migliore disposizione in righe (per le isole date) e ingombro sullo schermo.
  const bestArrange = (names: string[]) => {
    const exts = names.map((n) => extent(ellipse(isl[n].box.min, isl[n].box.max, isl[n].center)))
    let best: (ReturnType<typeof arrange> & { below: boolean }) | null = null
    let bestFit = 0
    for (const rows of rowings(names.length)) {
      const a = arrange(exts, rows)
      const sOff = Math.min((SIDE * a.h) / office.h, (0.5 * a.w) / office.w)
      const fit = Math.min(aspect / (2 * a.w * (1 + GAP) + 2 * office.w * sOff), 1 / (2 * a.h))
      if (fit > bestFit) {
        bestFit = fit
        best = { ...a, below: rows.some((n) => n > 1) }
      }
    }
    return best!
  }

  const offsets: Record<string, Vector3> = {}
  let stack: { w: number; h: number } | null = null
  let labelBelow = false
  const list = shown.filter((n) => isl[n])
  // Riferimento fisso: tutte e tre le isole, con un po' d'aria. Le isole hanno sempre la stessa grandezza,
  // qualunque sia il numero mostrato (con una sola, il palco è semplicemente più vuoto).
  const all = ISLAND_ORDER.filter((n) => isl[n])
  const refA = all.length ? bestArrange(all) : null
  const ref = refA ? { w: refA.w * ISLAND_ROOM, h: refA.h * ISLAND_ROOM } : null
  if (list.length) {
    const best = bestArrange(list)
    list.forEach((n, i) => (offsets[n] = RIGHT.clone().multiplyScalar(best.pos[i][0]).addScaledVector(UP, best.pos[i][1])))
    stack = { w: best.w, h: best.h }
    labelBelow = best.below
  }

  const stage = wanted === 'cloud' && stack ? 'cloud' : 'office'
  // Per la disposizione dei palchi le isole contano sempre con l'ingombro di riferimento.
  const islandsBox = ref ?? stack
  const main = stage === 'cloud' ? islandsBox! : office
  const side = stage === 'cloud' ? office : stack ? islandsBox : null
  const M = pivot.clone()
  const mainPose: Pose = { pos: M.clone(), s: 1 }
  let sidePose: Pose | null = null
  if (side) {
    const s = Math.min((SIDE * main.h) / side.h, (0.5 * main.w) / side.w)
    const dir = stage === 'cloud' ? -1 : 1
    sidePose = { pos: M.clone().addScaledVector(RIGHT, dir * (main.w * (1 + GAP) + side.w * s)), s }
  }
  const officePose = stage === 'office' ? mainPose : sidePose!
  const islandsPose = stack ? (stage === 'cloud' ? mainPose : sidePose) : null
  const points = corners(new Vector3(b.minX, -0.64, b.minZ), new Vector3(b.maxX, WALL_H, b.maxZ), pivot).map((p) => p.multiplyScalar(officePose.s).add(officePose.pos))
  if (islandsPose) {
    for (const n of list)
      for (const p of ellipse(isl[n].box.min, isl[n].box.max, isl[n].center)) points.push(p.add(offsets[n]).multiplyScalar(islandsPose.s).add(islandsPose.pos))
    // Il riquadro di riferimento entra sempre nell'inquadratura: è quello che fissa la grandezza delle isole.
    if (ref)
      for (const sx of [-1, 1]) for (const sy of [-1, 1]) points.push(islandsPose.pos.clone().addScaledVector(RIGHT, sx * ref.w * islandsPose.s).addScaledVector(UP, sy * ref.h * islandsPose.s))
  }
  const bb = new Box3().setFromPoints(points)
  return { view: 'iso', pivot, office: officePose, islands: islandsPose, shown: list, offsets, stage, points, center: bb.getCenter(new Vector3()), labelBelow }
}

/** Disposizione dei palchi per il passo, il reparto e il palco scelti (usata dalla scena e dalla camera). */
export function useStageLayout(): StageLayout | null {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const stage = useApp((s) => s.stage)
  const heatOn = useHeatOn()
  const size = useThree((s) => s.size)
  const info = useOffice()
  const isl = useIslands()
  const ctx = useMemo(() => makeCtx(data, []), [data])
  const key = useMemo(() => (room ? islandsOf(ctx, room).map((x) => x.name) : []).join(','), [ctx, room])
  const aspect = Math.max(0.5, (size.width - UI_W) / Math.max(1, size.height - UI_H))
  return useMemo(
    () => (room ? roomLayout(info, isl, room, stage, key ? key.split(',') : [], aspect) : planLayout(info, isl, heatOn)),
    [info, isl, room, stage, key, aspect, heatOn],
  )
}

/** Passi 2–4: la mappa «a colori» (plastico neutro, oggetti colorati per consumo, nuvole di CO₂). */
function useHeatOn() {
  const step = useApp((s) => s.step)
  const has = useApp((s) => !!s.data?.extra)
  return has && (step === 'baseline' || step === 'packages' || step === 'forecast')
}

/** Velature per evidenziare un'unità intera (tutti i computer di un reparto, tutti i rack di una risorsa). */
// Senza ritaglio: gli oggetti di un'unità stanno tutti dentro la stanza scelta (o su un'isola).
// Verde nel passo 1; blu nella mappa a colori, per non confonderlo con il verde «consuma poco».
function veil(opacity: number, color: string) {
  return new MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 })
}
const VEIL = { select: veil(0.42, '#1F7A57'), hover: veil(0.2, '#1F7A57') }
const VEIL_HEAT = { select: veil(0.5, '#2F66C8'), hover: veil(0.25, '#2F66C8') }

/**
 * Pianta dall'alto → clic su un reparto → due «palchi» come nella scelta del personaggio dei videogiochi:
 * l'ufficio da solo (software e servizi, si clicca sui computer) e le isole che il reparto usa davvero (hardware cloud).
 * Nei passi 2–4 la stessa scena diventa un plastico neutro con gli oggetti colorati per consumo e le nuvole di CO₂.
 */
export function AllocationScene() {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const setRoom = useApp((s) => s.setRoom)
  const setStage = useApp((s) => s.setStage)
  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)
  const selectedId = useApp((s) => s.selectedId)
  const hoverId = useApp((s) => s.hoverId)
  const info = useOffice()
  const isl = useIslands()
  const layout = useStageLayout()
  const heat = useHeat()
  const stage = layout?.stage ?? 'office'
  const ctx = useMemo(() => makeCtx(data, []), [data])

  // Ufficio: solo i computer (postazione = scrivania + sedia + monitor + case).
  const seats = useMemo(() => data.layout.filter((i) => i.id.startsWith('seat:') && i.room && ROOMS.includes(i.room)), [data.layout])
  const used = useMemo(() => (room ? cloudResourcesOf(ctx, room) : new Set<string>()), [ctx, room])

  // Raggruppate per reparto: nell'intro «planimetria → 3D» atterrano un reparto alla volta.
  const officeAssets = useMemo(() => {
    const byRoom: Record<string, Record<string, Inst[]>> = {}
    for (const item of seats) {
      const out = (byRoom[item.room!] ??= {})
      const push = (asset: string, inst: Inst) => (out[asset] ??= []).push(inst)
      const st = statusOf(ctx, item)
      const accent = DEPT_ACCENT[item.room ?? ''] ?? '#E9E4DA'
      const unit = unitOf(ctx, item) ?? undefined
      const paint = unit ? heat.colorOf(unit) : undefined
      const base = { itemId: item.id, rotY: item.rotY, scale: 1, blink: false, activity: st.activity, pickable: true, room: item.room, unit }
      push(item.asset, { ...base, key: item.id, pos: item.pos, colors: { screen: SCREEN[st.visual], accent, paint } })
      allocRegistry.set(item.id, { pos: new Vector3(...item.pos), h: HEIGHT[item.asset] ?? 1, item, space: 'office' })
      for (const [ci, child] of (item.children ?? []).entries()) {
        const [dx, dz] = rotate(child.pos[0], child.pos[2], item.rotY)
        push(child.asset, {
          ...base,
          key: `${item.id}/${ci}`,
          pos: [item.pos[0] + dx, item.pos[1] + child.pos[1], item.pos[2] + dz],
          rotY: item.rotY + child.rotY,
          colors: { screen: SCREEN[st.visual], accent, led: LED[st.visual], paint },
        })
      }
    }
    return byRoom
  }, [seats, ctx, heat])

  // Hardware di ogni isola: a colori (e cliccabile) se il reparto lo usa, fantasma altrimenti. Nella pianta: tutto, non cliccabile.
  const islandAssets = useMemo(() => {
    const out: Record<string, { on: Record<string, Inst[]>; off: Record<string, Inst[]> }> = {}
    for (const item of data.layout) {
      if (item.view !== 'island' || !item.island) continue
      const eff = effectiveOf(ctx, resourceOf(item))
      const isUsed = !room || (!!eff && used.has(eff.entity.id))
      const st = statusOf(ctx, item)
      const unit = unitOf(ctx, item) ?? undefined
      const inst: Inst = {
        itemId: item.id,
        key: item.id,
        pos: item.pos,
        rotY: item.rotY,
        scale: 1,
        blink: false,
        activity: st.activity,
        pickable: !!room && isUsed,
        unit,
        colors: {
          led: LED[st.visual],
          screen: SCREEN[st.visual],
          glow: GLOW[st.visual],
          provider: PROVIDER[eff?.entity.provider ?? ''] ?? '#B9B4AC',
          paint: unit ? heat.colorOf(unit) : undefined,
        },
      }
      const g = (out[item.island] ??= { on: {}, off: {} })
      ;((isUsed ? g.on : g.off)[item.asset] ??= []).push(inst)
      allocRegistry.set(item.id, { pos: new Vector3(...item.pos), h: HEIGHT[item.asset] ?? 1.5, item, space: 'islands' })
    }
    return out
  }, [data.layout, ctx, used, room, heat])

  // Unità evidenziate: quella selezionata e quella sotto il mouse (tutti gli oggetti con gli stessi dati).
  const unitAt = (id: string | null) => {
    const r = id ? allocRegistry.get(id) : undefined
    return r ? unitOf(ctx, r.item) : null
  }
  const selUnit = room ? unitAt(selectedId) : null
  const hovUnit = room ? unitAt(hoverId) : null
  const pick = (list: Inst[], unit: string | null) => (unit ? list.filter((i) => i.unit === unit) : [])
  const V = heat.on ? VEIL_HEAT : VEIL

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
  const onIslandHover = (id: string | null) => (room ? hover(id ? (stage === 'cloud' ? id : 'stage:cloud') : null) : undefined)
  const onIslandSelect = (id: string) => (room ? (stage === 'office' ? setStage('cloud') : select(id)) : undefined)

  return (
    <group>
      <group ref={(g) => void (stageGroups.office = g)}>
        <group ref={(g) => void (buildGroups.walls = g)}>
          <OfficeModel info={info} stage={stage} heatOn={heat.on} />
        </group>
        {/* Raggruppate per reparto: nell'intro «planimetria → 3D» atterrano un reparto alla volta. */}
        {Object.entries(officeAssets).map(([r, assets]) => (
          <group key={r} ref={(g) => void (buildGroups.rooms[r] = g)}>
            {Object.entries(assets).map(([asset, list]) => (
              <group key={asset}>
                <KitInstances asset={asset} instances={list} onHover={onOfficeHover} onSelect={onOfficeSelect} pickRoom={room} paint={heat.on} />
                {selUnit && <Veil key={`s-${selUnit}`} asset={asset} list={pick(list, selUnit)} material={V.select} />}
                {hovUnit && hovUnit !== selUnit && <Veil key={`h-${hovUnit}`} asset={asset} list={pick(list, hovUnit)} material={V.hover} />}
              </group>
            ))}
          </group>
        ))}
        <BlueprintBuild />
      </group>

      {layout?.islands && (
        <group key={room ?? 'plan'} ref={(g) => void (stageGroups.islands = g)}>
          {layout.shown.map((name) => (
            <group key={name} position={layout.offsets[name]}>
              <group position={isl[name].center.clone().negate()} ref={(g) => void (islandGroups[name] = g)}>
                <IslandModel object={isl[name].object} stage={stage} heatOn={heat.on} interactive={!!room} />
                {Object.entries(islandAssets[name]?.on ?? {}).map(([asset, list]) => (
                  <group key={`on-${asset}`}>
                    <KitInstances asset={asset} instances={list} onHover={onIslandHover} onSelect={onIslandSelect} unclipped paint={heat.on} />
                    {selUnit && <Veil key={`s-${selUnit}`} asset={asset} list={pick(list, selUnit)} material={V.select} />}
                    {hovUnit && hovUnit !== selUnit && <Veil key={`h-${hovUnit}`} asset={asset} list={pick(list, hovUnit)} material={V.hover} />}
                  </group>
                ))}
                {Object.entries(islandAssets[name]?.off ?? {}).map(([asset, list]) => (
                  <KitInstances key={`off-${asset}`} asset={asset} instances={list} onHover={() => {}} onSelect={() => {}} ghost={islandGhostMaterial} />
                ))}
                {heat.on && <Co2Cloud island={name} info={isl[name]} heat={heat} />}
              </group>
            </group>
          ))}
        </group>
      )}

      <StageController info={info} layout={layout} />
      <Projector info={info} isl={isl} layout={layout} heat={heat} />
    </group>
  )
}

function Veil({ asset, list, material }: { asset: string; list: Inst[]; material: Material }) {
  if (!list.length) return null
  return <KitInstances asset={asset} instances={list} onHover={() => {}} onSelect={() => {}} ghost={material} />
}

/** Edificio (un solo modello): pavimenti cliccabili nella pianta; nel reparto resta solo la stanza scelta. */
function OfficeModel({ info, stage, heatOn }: { info: OfficeInfo; stage: 'office' | 'cloud'; heatOn: boolean }) {
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
  useNeutral(office, heatOn, NEUTRAL_WALL)

  // Evidenzia il reparto sotto il mouse (solo nella pianta). Nella mappa a colori i pavimenti sono neutri.
  useEffect(() => {
    const hovered = !room && hoverId?.startsWith('room:') ? hoverId.slice(5) : null
    for (const [r, f] of Object.entries(floors)) f.mat.color.copy(heatOn ? NEUTRAL_FLOOR : f.base).lerp(HOVER, r === hovered ? 0.85 : 0)
    document.body.style.cursor = hovered || (room && hoverId) ? 'pointer' : 'auto'
  }, [hoverId, room, floors, heatOn])

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
          <meshStandardMaterial color={heatOn ? '#D9D4CB' : '#C7A27C'} roughness={0.9} />
        </mesh>
      )}
    </>
  )
}

/** Un'isola: nel palco laterale un clic porta le isole al centro. Nella pianta non si clicca. */
function IslandModel({ object, stage, heatOn, interactive }: { object: Object3D; stage: 'office' | 'cloud'; heatOn: boolean; interactive: boolean }) {
  const setStage = useApp((s) => s.setStage)
  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)
  useNeutral(object, heatOn, NEUTRAL_ISLAND)
  return (
    <primitive
      object={object}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        if (!interactive) return
        e.stopPropagation()
        if (stage === 'office') setStage('cloud')
        else select(null)
      }}
      onPointerMove={(e: ThreeEvent<PointerEvent>) => {
        if (!interactive || stage !== 'office') return
        e.stopPropagation()
        hover('stage:cloud')
      }}
      onPointerOut={() => interactive && hover(null)}
    />
  )
}

/** Nuvola di CO₂ sopra un'isola: grandezza = CO₂ all'anno della sede (o del mese, annualizzato), più scura se è più grande. */
const LIGHT_CLOUD = new Color('#F1EFEB')
const DARK_CLOUD = new Color('#9C978F')
function Co2Cloud({ island, info, heat }: { island: string; info: IslandInfo; heat: HeatView }) {
  const { scene } = useGLTF(CLOUD)
  const geo = useMemo(() => {
    let g: BufferGeometry | null = null
    scene.traverse((o) => {
      const m = o as Mesh
      if (m.isMesh && !g) {
        g = m.geometry.clone()
        g.morphAttributes = {}
      }
    })
    return g
  }, [scene])
  const mat = useMemo(() => new MeshStandardMaterial({ color: '#D9D6D0', roughness: 1, transparent: true, opacity: 0.82, depthWrite: false }), [])
  const ref = useRef<Mesh>(null)
  const kg = heat.cloudKg(ISLAND_LOC[island])
  const t = Math.sqrt(Math.max(0, kg) / heat.cloudMax)
  const target = 0.25 + 0.7 * t
  useFrame((_, dt) => {
    const m = ref.current
    if (!m) return
    const s = m.scale.x + (target - m.scale.x) * Math.min(1, dt * 4)
    m.scale.setScalar(s)
    mat.color.copy(LIGHT_CLOUD).lerp(DARK_CLOUD, Math.min(1, t))
  })
  if (!geo) return null
  const b = info.box
  return <mesh ref={ref} geometry={geo} material={mat} position={[info.center.x, b.max.y + 0.6, b.min.z - 0.6]} scale={target} raycast={() => null} />
}

/** Movimento di un palco: da dove parte, dove arriva, a che punto è (0–1). */
interface Live {
  pos: Vector3
  s: number
  from: Vector3
  fromS: number
  to: Vector3
  toS: number
  t: number
}

/** Verso il fondo della scena (lontano dalla camera), sul pavimento: il «giro» del carosello passa di qui. */
const BACK = new Vector3(-1, 0, -1).normalize()
const SWAP_S = 0.7
// Morbido ma deciso: parte svelta e rallenta solo alla fine.
const ease = (x: number) => 1 - Math.pow(1 - x, 3)

/** Porta un palco verso la sua posa lungo un arco: scivola di lato e passa dietro, come un carosello. */
function follow(l: Live, pos: Vector3, s: number, depth: number, dt: number) {
  if (l.to.distanceTo(pos) > 0.01 || Math.abs(l.toS - s) > 1e-4) {
    l.from.copy(l.pos)
    l.fromS = l.s
    l.to.copy(pos)
    l.toS = s
    l.t = 0
  }
  l.t = Math.min(1, l.t + dt / SWAP_S)
  const e = ease(l.t)
  l.pos.lerpVectors(l.from, l.to, e).addScaledVector(BACK, depth * Math.sin(Math.PI * e))
  l.s = l.fromS + (l.toS - l.fromS) * e
}

const live = (pos: Vector3, s: number): Live => ({ pos: pos.clone(), s, from: pos.clone(), fromS: s, to: pos.clone(), toS: s, t: 1 })

/**
 * Anima i palchi verso la disposizione scelta e gira solo l'oggetto in primo piano:
 * l'ufficio attorno al centro della stanza, ogni isola attorno al proprio centro. Il ritaglio del reparto segue l'ufficio.
 */
function StageController({ info, layout }: { info: OfficeInfo; layout: StageLayout | null }) {
  const room = useApp((s) => s.room)
  const turns = useApp((s) => s.turns)
  const cur = useRef<{ office: Live | null; islands: Live | null; angle: { office: number; cloud: number } }>({ office: null, islands: null, angle: { office: 0, cloud: 0 } })
  const tmp = useMemo(() => new Vector3(), [])

  useFrame((_, dt) => {
    const og = stageGroups.office
    if (!og || !layout) return
    const c = cur.current
    const r = room ? info.rooms[room] : undefined
    const ig = stageGroups.islands
    if (!r) {
      // Pianta: ufficio fermo al suo posto, isole (se ci sono) in colonna a destra, dritte.
      og.position.set(0, 0, 0)
      og.rotation.set(0, 0, 0)
      og.scale.setScalar(1)
      c.office = null
      c.islands = null
      c.angle = { office: 0, cloud: 0 }
      if (ig && layout.islands) {
        ig.position.copy(layout.islands.pos)
        ig.scale.setScalar(layout.islands.s)
        for (const child of ig.children) child.rotation.y = 0
      }
    } else {
      // Mezzo giro in circa un secondo e mezzo.
      const ka = Math.min(1, dt * 2.4)
      c.angle.office += (turns.office * Math.PI - c.angle.office) * ka
      c.angle.cloud += (turns.cloud * Math.PI - c.angle.cloud) * ka
      // Profondità del giro: un accenno (circa un sesto della distanza fra i due palchi).
      const depth = layout.islands ? 0.18 * layout.office.pos.distanceTo(layout.islands.pos) : 0

      const o = (c.office ??= live(layout.pivot, 1))
      follow(o, layout.office.pos, layout.office.s, depth, dt)
      // Gira e scala attorno al centro della stanza: posizione = punto sul palco − scala × (rotazione × centro).
      og.rotation.set(0, c.angle.office, 0)
      og.scale.setScalar(o.s)
      og.position.copy(o.pos).sub(tmp.copy(layout.pivot).applyAxisAngle(og.up, c.angle.office).multiplyScalar(o.s))

      if (ig && layout.islands) {
        const i = (c.islands ??= live(layout.islands.pos, layout.islands.s))
        follow(i, layout.islands.pos, layout.islands.s, depth, dt)
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

/** Cerchio orizzontale (coordinate locali): non cambia girando l'oggetto, quindi le scritte non si muovono durante la rotazione. */
function ring(cx: number, y: number, cz: number, r: number, rz = r) {
  return Array.from({ length: 24 }, (_, i) => new Vector3(cx + Math.cos((i / 24) * Math.PI * 2) * r, y, cz + Math.sin((i / 24) * Math.PI * 2) * rz))
}

/** Proietta sullo schermo i punti delle scritte HTML: nomi dei reparti, tooltip, titoli dei palchi, isole, nuvole e punti critici. */
function Projector({ info, isl, layout, heat }: { info: OfficeInfo; isl: Record<string, IslandInfo>; layout: StageLayout | null; heat: HeatView }) {
  const room = useApp((s) => s.room)
  const hoverId = useApp((s) => s.hoverId)
  const data = useApp((s) => s.data)!
  const setPoints = useScreen((s) => s.set)
  const v = useMemo(() => new Vector3(), [])
  // Un punto critico per unità: sul primo oggetto che la rappresenta (rack) oppure al centro del reparto (computer).
  const painItems = useMemo(() => {
    const out: { unit: string; item?: LayoutItem; room?: string }[] = []
    for (const unit of heat.pains.keys()) {
      if (unit.startsWith('pcs:')) out.push({ unit, room: unit.slice(4) })
      else {
        const item = data.layout.find((i) => i.view === 'island' && unitOf(heat.ctx, i) === unit)
        if (item) out.push({ unit, item })
      }
    }
    return out
  }, [heat, data.layout])
  useFrame(({ camera, size }) => {
    const pts: Record<string, [number, number]> = {}
    const project = (p: Vector3, g: Group | null): [number, number] => {
      v.copy(p)
      if (g) v.applyMatrix4(g.matrixWorld)
      v.project(camera)
      return [Math.round(((v.x + 1) / 2) * size.width), Math.round(((1 - v.y) / 2) * size.height)]
    }
    // Come project, ma senza la rotazione dell'oggetto: centro e scala dal gruppo, forma dritta.
    // Titoli e nomi così restano fermi mentre il modello gira.
    const cw = new Vector3()
    const still = (p: Vector3, center: Vector3, g: Group | null): [number, number] => {
      if (!g) return project(p, null)
      cw.copy(center).applyMatrix4(g.matrixWorld)
      v.copy(p).sub(center).multiplyScalar(g.matrixWorld.getMaxScaleOnAxis()).add(cw)
      v.project(camera)
      return [Math.round(((v.x + 1) / 2) * size.width), Math.round(((1 - v.y) / 2) * size.height)]
    }
    const top = (ps: [number, number][]) => [Math.round(ps.reduce((a, q) => a + q[0], 0) / ps.length), Math.min(...ps.map((q) => q[1]))] as [number, number]
    // Pianta: angolo in alto a sinistra di ogni reparto (nord in alto = z minima, ovest a sinistra = x minima).
    if (!room) for (const r of ROOMS) { const b = info.rooms[r]?.box; if (b) pts[`room:${r}`] = project(new Vector3(b.minX + MARGIN, 1.25, b.minZ + MARGIN), stageGroups.office) }
    const h = hoverId ? allocRegistry.get(hoverId) : undefined
    if (room && h) pts.hover = project(h.pos.clone().setY(h.pos.y + h.h + 0.3), groupOf(h))
    if (room && layout && info.rooms[room]) {
      const r = info.rooms[room]
      const rc = new Vector3(r.center.x, WALL_H / 2, r.center.z)
      pts['stage:office'] = top(
        corners(new Vector3(r.box.minX, 0, r.box.minZ), new Vector3(r.box.maxX, WALL_H, r.box.maxZ), new Vector3()).map((p) => still(p, rc, stageGroups.office)),
      )
    }
    if (layout) {
      const all: [number, number][] = []
      for (const name of layout.shown) {
        const ib = isl[name].box
        const c = isl[name].center
        const g = islandGroups[name] ?? null
        const rad = 0.5 * Math.max(ib.max.x - ib.min.x, ib.max.z - ib.min.z)
        const topRing = ring(c.x, ib.max.y, c.z, rad).map((p) => still(p, c, g))
        all.push(...topRing)
        // Ellisse dell'isola: anche lei non cambia con il mezzo giro (simmetrica rispetto al centro).
        const rx = 0.5 * (ib.max.x - ib.min.x)
        const rz = 0.5 * (ib.max.z - ib.min.z)
        const mid = ring(c.x, (ib.min.y + ib.max.y) / 2, c.z, rx, rz).map((p) => still(p, c, g))
        // Nome dell'isola: a destra a metà altezza, oppure sotto se le isole sono affiancate.
        if (layout.labelBelow) {
          const low = ring(c.x, ib.min.y + 0.5, c.z, rx * 0.8, rz * 0.8).map((p) => still(p, c, g))
          pts[`islandb:${name}`] = [Math.round(low.reduce((a, q) => a + q[0], 0) / low.length), Math.max(...low.map((q) => q[1]))]
        } else pts[`island:${name}`] = [Math.max(...mid.map((q) => q[0])), Math.round(mid.reduce((a, q) => a + q[1], 0) / mid.length)]
        if (heat.on) pts[`cloud:${name}`] = project(new Vector3(c.x, ib.max.y + 0.8, ib.min.z - 0.6), g)
      }
      if (room && all.length) pts['stage:cloud'] = top(all)
    }
    for (const p of painItems) {
      if (p.item && room) {
        const r = allocRegistry.get(p.item.id)
        if (r && layout?.shown.includes(p.item.island ?? '')) pts[`pain:${p.unit}`] = project(r.pos.clone().setY(r.pos.y + r.h + 0.4), groupOf(r))
      } else if (p.item) {
        const r = allocRegistry.get(p.item.id)
        if (r) pts[`pain:${p.unit}`] = project(r.pos.clone().setY(r.pos.y + r.h + 0.4), groupOf(r))
      } else if (p.room && !room) {
        const c = info.rooms[p.room]?.center
        if (c) pts[`pain:${p.unit}`] = project(new Vector3(c.x, 1.3, c.z), stageGroups.office)
      }
    }
    setPoints(pts)
  })
  return null
}
