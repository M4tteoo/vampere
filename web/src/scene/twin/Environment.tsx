import { useEffect, useMemo } from 'react'
import { useGLTF } from '@react-three/drei'
import type { ThreeEvent } from '@react-three/fiber'
import { Box3, BufferGeometry, Color, Mesh, MeshStandardMaterial, Object3D, Vector3 } from 'three'
import { useApp } from '../../store'
import { DEPARTMENTS } from '../../data/twin'
import { MODELS } from './kit'

const OFFICE = `${MODELS}/env_office_v1.glb`
const ISLANDS = `${MODELS}/env_islands_v1.glb`
useGLTF.preload(OFFICE)
useGLTF.preload(ISLANDS)

export interface Anchors {
  labels: Record<string, Vector3>
  rooms: Record<string, { center: Vector3; size: Vector3 }>
  islands: Record<string, Vector3>
  slots: Record<string, Vector3>
  /** Forma della nuvola modellata in Blender: si usa per le nuvole di CO₂ sopra le isole. */
  cloud: BufferGeometry | null
}

/** «UE (mista)» non è un luogo in più ma un mix non specificato: l'isola si toglie e la sua nuvola diventa la forma della CO₂. */
const MIXED = 'island_eu-mixed'

function takeCloud(islands: Object3D): BufferGeometry | null {
  const node = islands.getObjectByName(MIXED)
  let geo: BufferGeometry | null = (islands.userData.cloud as BufferGeometry | undefined) ?? null
  if (node) {
    node.traverse((o) => {
      const mesh = o as Mesh
      if (mesh.isMesh && !geo) {
        geo = mesh.geometry.clone()
        // La nuvola di Blender ha delle shape key (morph target): qui serve solo la forma base.
        geo.morphAttributes = {}
        geo.computeBoundingBox()
        const b = geo.boundingBox!
        const c = b.getCenter(new Vector3())
        geo.translate(-c.x, -b.min.y, -c.z)
        geo.computeBoundingBox()
      }
    })
    node.removeFromParent()
    islands.userData.cloud = geo
  }
  return geo
}

/** Punti notevoli dei modelli d'ambiente (empty creati in Blender): etichette, stanze, isole, slot. */
export function useAnchors(): Anchors {
  const office = useGLTF(OFFICE).scene
  const islands = useGLTF(ISLANDS).scene
  return useMemo(() => {
    const cloud = takeCloud(islands)
    office.updateMatrixWorld(true)
    islands.updateMatrixWorld(true)
    const a: Anchors = { labels: {}, rooms: {}, islands: {}, slots: {}, cloud }
    office.traverse((o) => {
      if (o.name.startsWith('label_')) a.labels[o.name.slice(6)] = o.getWorldPosition(new Vector3())
      if (o.name.startsWith('floor_')) {
        const box = new Box3().setFromObject(o)
        a.rooms[o.name.slice(6)] = { center: box.getCenter(new Vector3()), size: box.getSize(new Vector3()) }
      }
    })
    islands.traverse((o) => {
      if (o.name.startsWith('island_')) a.islands[o.name.slice(7)] = o.getWorldPosition(new Vector3())
      if (o.name.startsWith('slot_')) a.slots[o.name.slice(5)] = o.getWorldPosition(new Vector3())
    })
    return a
  }, [office, islands])
}

const HEAT = new Color('#E39A6F')

function ancestor(o: Object3D | null, prefix: string): string | null {
  for (let x = o; x; x = x.parent) if (x.name.startsWith(prefix)) return x.name.slice(prefix.length)
  return null
}

/** Edificio e isole statici. I pavimenti delle stanze si colorano secondo la metrica scelta («mappa di calore»). */
export function Environment({ shares }: { shares: Record<string, number> }) {
  const office = useGLTF(OFFICE).scene
  const islands = useGLTF(ISLANDS).scene
  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)

  // Materiali dei pavimenti clonati una volta, così si possono ricolorare senza toccare gli altri.
  const floors = useMemo(() => {
    const map: Record<string, { mat: MeshStandardMaterial; base: Color }> = {}
    office.traverse((o) => {
      const mesh = o as Mesh
      if (!mesh.isMesh) return
      mesh.castShadow = true
      mesh.receiveShadow = true
      const room = ancestor(mesh, 'floor_')
      if (room && (DEPARTMENTS as readonly string[]).includes(room)) {
        const mat = (mesh.material as MeshStandardMaterial).clone()
        mesh.material = mat
        map[room] = { mat, base: mat.color.clone() }
      } else {
        // Solo i pavimenti sono cliccabili: il resto non intercetta il mouse (e costa meno).
        mesh.raycast = () => {}
      }
    })
    islands.traverse((o) => {
      const mesh = o as Mesh
      if (!mesh.isMesh) return
      mesh.castShadow = true
      mesh.receiveShadow = true
    })
    return map
  }, [office, islands])

  useEffect(() => {
    const max = Math.max(0.0001, ...Object.values(shares))
    for (const [room, f] of Object.entries(floors)) {
      f.mat.color.copy(f.base).lerp(HEAT, 0.6 * ((shares[room] ?? 0) / max))
    }
  }, [shares, floors])

  const onRoom = (e: ThreeEvent<MouseEvent>) => {
    const room = ancestor(e.object, 'floor_')
    if (!room || !(DEPARTMENTS as readonly string[]).includes(room)) return
    e.stopPropagation()
    select(`room:${room}`)
  }
  const onIsland = (e: ThreeEvent<MouseEvent>) => {
    const isl = ancestor(e.object, 'island_')
    if (!isl) return
    e.stopPropagation()
    select(`loc:${isl}`)
  }

  return (
    <>
      <primitive
        object={office}
        onClick={onRoom}
        onPointerMove={(e: ThreeEvent<PointerEvent>) => {
          const room = ancestor(e.object, 'floor_')
          if (room) {
            e.stopPropagation()
            hover(`room:${room}`)
          }
        }}
        onPointerOut={() => hover(null)}
      />
      <primitive object={islands} onClick={onIsland} />
    </>
  )
}
