import { useMemo } from 'react'
import { useGLTF } from '@react-three/drei'
import { focusPlanes } from './clip'
import {
  Box3,
  BufferGeometry,
  Material,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  Vector3,
} from 'three'

export const MODELS = `${import.meta.env.BASE_URL}models`
export const kitUrl = (asset: string) => `${MODELS}/kit_${asset}_v1.glb`

/** Ruolo di una parte del modello (nomi dei nodi definiti in design/office-spec.md §6). */
export type Role = 'body' | 'screen' | 'led' | 'glow' | 'accent' | 'days' | 'fan' | 'belt'

const ROLE: Record<string, Role> = {
  screen: 'screen',
  screen_2: 'screen',
  face_screen: 'screen',
  status_led: 'led',
  glow: 'glow',
  accent: 'accent',
  days: 'days',
  fan: 'fan',
  belt: 'belt',
}

export interface KitPart {
  role: Role
  geometry: BufferGeometry
  material: Material
  /** Trasformazione della mesh rispetto all'origine del modello. */
  matrix: Matrix4
  /** Centro di rotazione per le parti che si muovono (ventola, nastro). */
  pivot: Vector3
}

export interface Kit {
  parts: KitPart[]
  size: Vector3
}

/** Materiali «a colori per istanza»: bianco × colore dell'istanza. Schermi e LED non sono illuminati (sembrano accesi). */
function partMaterial(role: Role, original: Material): Material {
  let m: Material = original
  if (role === 'screen' || role === 'led' || role === 'glow' || role === 'days') {
    m = new MeshBasicMaterial({ color: '#ffffff', toneMapped: false })
  } else if (role === 'accent') {
    m = (original as MeshStandardMaterial).clone()
    ;(m as MeshStandardMaterial).color.set('#ffffff')
  }
  // Tutti i materiali rispettano il ritaglio del reparto selezionato.
  m.clippingPlanes = focusPlanes
  return m
}

export function useKit(asset: string): Kit {
  const { scene } = useGLTF(kitUrl(asset))
  return useMemo(() => {
    scene.updateMatrixWorld(true)
    const parts: KitPart[] = []
    for (const node of scene.children) {
      const role = ROLE[node.name] ?? 'body'
      const pivot = node.getWorldPosition(new Vector3())
      node.traverse((o: Object3D) => {
        const mesh = o as Mesh
        if (!mesh.isMesh) return
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        parts.push({ role, geometry: mesh.geometry, material: partMaterial(role, mats[0]), matrix: mesh.matrixWorld.clone(), pivot })
      })
    }
    const size = new Box3().setFromObject(scene).getSize(new Vector3())
    return { parts, size }
  }, [scene])
}

export function preloadKits(assets: string[]) {
  for (const a of assets) useGLTF.preload(kitUrl(a))
}
