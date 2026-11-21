import { useEffect, useMemo, useRef } from 'react'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import { useScreen } from './screen'
import { Box3, Color, Group, Mesh, MeshStandardMaterial, Object3D, Vector3 } from 'three'
import { useApp } from '../../store'
import { DEPARTMENTS, DEPT_ACCENT, makeCtx, statusOf } from '../../data/twin'
import type { LayoutItem } from '../../data/types'
import { MODELS, preloadKits } from './kit'
import { KitInstances, type Inst } from './KitInstances'
import { focusPlanes, ghostMaterial, setClipBox, type Box2 } from './clip'
import { DAYS, GLOW, LED, SCREEN } from './colors'
import { HEIGHT } from './TwinAll'

const OFFICE = `${MODELS}/env_office_v1.glb`
useGLTF.preload(OFFICE)
preloadKits([...Object.keys(HEIGHT), 'chair_task', 'monitor_27', 'monitor_dual'])

const ROOMS = DEPARTMENTS as readonly string[]
/** Margine del ritaglio oltre il pavimento: include metà dei muri della stanza. */
const MARGIN = 0.14
const HOVER = new Color('#DCEFE3')

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

/** Registro delle posizioni degli oggetti (per la camera e il tooltip). */
export const allocRegistry = new Map<string, { pos: Vector3; h: number; item: LayoutItem }>()

function ancestor(o: Object3D | null, prefix: string): string | null {
  for (let x = o; x; x = x.parent) if (x.name.startsWith(prefix)) return x.name.slice(prefix.length)
  return null
}

function rotate(x: number, z: number, a: number): [number, number] {
  const c = Math.cos(a)
  const s = Math.sin(a)
  return [x * c + z * s, -x * s + z * c]
}

/** Passo 1 · Allocation: pianta dall'alto → clic su un reparto → il reparto isolato, il resto come fantasma. */
export function AllocationScene() {
  const data = useApp((s) => s.data)!
  const room = useApp((s) => s.room)
  const setRoom = useApp((s) => s.setRoom)
  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)
  const info = useOffice()
  const ctx = useMemo(() => makeCtx(data, []), [data])

  // Solo l'ufficio: le isole arrivano nei passi successivi.
  const items = useMemo(() => data.layout.filter((i) => i.view !== 'island' && i.room && ROOMS.includes(i.room)), [data.layout])

  const byAsset = useMemo(() => {
    const out: Record<string, Inst[]> = {}
    const push = (asset: string, inst: Inst) => (out[asset] ??= []).push(inst)
    allocRegistry.clear()
    for (const item of items) {
      const st = statusOf(ctx, item)
      const accent = DEPT_ACCENT[item.room ?? ''] ?? '#E9E4DA'
      const base = { itemId: item.id, rotY: item.rotY, scale: 1, blink: false, activity: st.activity, pickable: true, room: item.room }
      push(item.asset, {
        ...base,
        key: item.id,
        pos: item.pos,
        colors: { screen: SCREEN[st.visual], led: LED[st.visual], glow: GLOW[st.visual], accent, days: DAYS },
      })
      allocRegistry.set(item.id, { pos: new Vector3(...item.pos), h: HEIGHT[item.asset] ?? 1, item })
      for (const [ci, child] of (item.children ?? []).entries()) {
        const [dx, dz] = rotate(child.pos[0], child.pos[2], item.rotY)
        push(child.asset, {
          ...base,
          key: `${item.id}/${ci}`,
          pos: [item.pos[0] + dx, item.pos[1] + child.pos[1], item.pos[2] + dz],
          rotY: item.rotY + child.rotY,
          colors: { screen: SCREEN[st.visual], accent },
        })
      }
    }
    return out
  }, [items, ctx])

  // Nella pianta un clic su qualsiasi oggetto apre il suo reparto; nel reparto apre la scheda dell'oggetto.
  const roomOf = (id: string) => allocRegistry.get(id)?.item.room ?? null
  const onHover = (id: string | null) => {
    if (!id) return hover(null)
    hover(room ? id : `room:${roomOf(id)}`)
  }
  const onSelect = (id: string) => {
    if (room) select(id)
    else {
      const r = roomOf(id)
      if (r) setRoom(r)
    }
  }

  return (
    <group>
      <OfficeModel info={info} />
      {Object.entries(byAsset).map(([asset, list]) => (
        <group key={asset}>
          <KitInstances asset={asset} instances={list} onHover={onHover} onSelect={onSelect} pickRoom={room} />
          {room && <KitInstances asset={asset} instances={list} onHover={onHover} onSelect={onSelect} ghost={ghostMaterial} />}
        </group>
      ))}
      <ClipController info={info} />
      <Projector info={info} />
      {room && <SelectionRing />}
    </group>
  )
}

/** Edificio (un solo modello): pavimenti cliccabili, evidenziati al passaggio; copia fantasma per il contesto. */
function OfficeModel({ info }: { info: OfficeInfo }) {
  const office = useGLTF(OFFICE).scene
  const room = useApp((s) => s.room)
  const hoverId = useApp((s) => s.hoverId)
  const setRoom = useApp((s) => s.setRoom)
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

  // Copia fantasma dell'edificio, condivide le geometrie.
  const ghost = useMemo(() => {
    const g = office.clone(true)
    g.traverse((o) => {
      const mesh = o as Mesh
      if (!mesh.isMesh) return
      mesh.material = ghostMaterial
      mesh.castShadow = false
      mesh.receiveShadow = false
      mesh.raycast = () => {}
    })
    return g
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
          else if (r === room) select(null)
        }}
        onPointerMove={(e: ThreeEvent<PointerEvent>) => {
          const r = ancestor(e.object, 'floor_')
          if (!room && r && ROOMS.includes(r)) {
            e.stopPropagation()
            hover(`room:${r}`)
          }
        }}
        onPointerOut={() => hover(null)}
      />
      {room && <primitive object={ghost} />}
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

/** Anima il ritaglio (da tutto l'ufficio al reparto) e la comparsa del fantasma. */
function ClipController({ info }: { info: OfficeInfo }) {
  const room = useApp((s) => s.room)
  // Cambio istantaneo: dalla pianta tutta a colori al solo reparto a colori (nessuna transizione visibile del taglio).
  useFrame(() => {
    setClipBox(room ? info.rooms[room]?.box ?? info.office.box : { minX: -1e4, maxX: 1e4, minZ: -1e4, maxZ: 1e4 })
    ghostMaterial.opacity = room ? 0.12 : 0
  })
  return null
}

/** Proietta sullo schermo i punti delle scritte (nomi dei reparti, tooltip): le scritte sono HTML normale sopra la scena. */
function Projector({ info }: { info: OfficeInfo }) {
  const room = useApp((s) => s.room)
  const hoverId = useApp((s) => s.hoverId)
  const setPoints = useScreen((s) => s.set)
  const v = useMemo(() => new Vector3(), [])
  useFrame(({ camera, size }) => {
    const pts: Record<string, [number, number]> = {}
    const add = (key: string, x: number, y: number, z: number) => {
      v.set(x, y, z).project(camera)
      pts[key] = [Math.round(((v.x + 1) / 2) * size.width), Math.round(((1 - v.y) / 2) * size.height)]
    }
    // Angolo in alto a sinistra di ogni reparto nella pianta (nord in alto = z minima, ovest a sinistra = x minima).
    if (!room) for (const r of ROOMS) { const b = info.rooms[r]?.box; if (b) add(`room:${r}`, b.minX + MARGIN, 1.25, b.minZ + MARGIN) }
    const h = hoverId ? allocRegistry.get(hoverId) : undefined
    if (room && h) add('hover', h.pos.x, h.pos.y + h.h + 0.3, h.pos.z)
    setPoints(pts)
  })
  return null
}

function SelectionRing() {
  const selectedId = useApp((s) => s.selectedId)
  const ref = useRef<Group>(null)
  const r = selectedId ? allocRegistry.get(selectedId) : undefined
  useFrame(({ clock }) => {
    if (!ref.current || !r) return
    ref.current.position.set(r.pos.x, (r.item.asset.startsWith('wall') ? 0 : r.pos.y) + 0.03, r.pos.z)
    ref.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 3) * 0.05)
  })
  if (!r) return null
  const radius = Math.max(0.5, Math.min(1.2, r.h * 0.5))
  return (
    <group ref={ref}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} raycast={() => null}>
        <ringGeometry args={[radius, radius + 0.08, 48]} />
        <meshBasicMaterial color="#1F7A57" toneMapped={false} />
      </mesh>
    </group>
  )
}
