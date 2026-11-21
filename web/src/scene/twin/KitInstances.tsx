import { useEffect, useMemo, useRef } from 'react'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { Color, InstancedMesh, Matrix4, Object3D, Quaternion, Vector3, type Material } from 'three'
import { useKit, type Role } from './kit'

/** Un'istanza di un asset nella scena: posizione e colori «di stato» calcolati dai dati. */
export interface Inst {
  key: string
  /** Oggetto cliccabile a cui appartiene (le sedie e i monitor appartengono alla scrivania). */
  itemId: string
  pos: [number, number, number]
  rotY: number
  /** 1 = visibile, 0 = sparisce con un'animazione. */
  scale: number
  /** Ingrandimento fisso (es. oggetti sulla nuvola, visti da lontano). */
  size?: number
  colors: Partial<Record<Role, string>>
  /** Lampeggia (spreco, decisione in sospeso). */
  blink: boolean
  /** 0–1: velocità di ventole e nastri. */
  activity: number
  pickable: boolean
  /** Reparto a cui appartiene (per il ritaglio e per i clic). */
  room?: string
}

interface Props {
  asset: string
  instances: Inst[]
  onHover: (itemId: string | null) => void
  onSelect: (itemId: string) => void
  /** Copia «fantasma»: stesso posto, materiale semitrasparente, non cliccabile. */
  ghost?: Material
  /** Se impostato, si possono cliccare solo gli oggetti di questo reparto. */
  pickRoom?: string | null
  /** Materiali senza il ritaglio del reparto (oggetti sulle isole). */
  unclipped?: boolean
}

const TINTED: Role[] = ['screen', 'led', 'glow', 'accent', 'days', 'provider']
const UP = new Vector3(0, 1, 0)

interface Live {
  target: Vector3
  pos: Vector3
  from: Vector3
  t: number
  scale: number
  rotY: number
  spin: number
}

/** Disegna tutte le copie di un asset con poche draw call (una InstancedMesh per parte del modello). */
export function KitInstances({ asset, instances, onHover, onSelect, ghost, pickRoom, unclipped }: Props) {
  const kit = useKit(asset)
  const materials = useMemo(
    () =>
      kit.parts.map((p) => {
        if (ghost) return ghost
        if (!unclipped) return p.material
        const m = p.material.clone()
        m.clippingPlanes = null
        return m
      }),
    [kit, ghost, unclipped],
  )
  const refs = useRef<(InstancedMesh | null)[]>([])
  const live = useRef<Live[]>([])
  const dirty = useRef(true)
  const count = instances.length
  const animated = kit.parts.some((p) => p.role === 'fan' || p.role === 'belt')

  // Stato animato per ogni istanza: segue il «target» calcolato dai dati.
  useMemo(() => {
    live.current = instances.map((inst, i) => {
      const prev = live.current[i]
      const target = new Vector3(...inst.pos)
      if (!prev) return { target, pos: target.clone(), from: target.clone(), t: 1, scale: inst.scale, rotY: inst.rotY, spin: 0 }
      if (prev.target.distanceTo(target) > 0.01) {
        prev.from.copy(prev.pos)
        prev.t = 0
      }
      prev.target = target
      return prev
    })
    dirty.current = true
  }, [instances])

  const colors = useMemo(() => {
    const c = new Color()
    return instances.map((inst) => {
      const out: Partial<Record<Role, Color>> = {}
      for (const r of TINTED) out[r] = c.set(inst.colors[r] ?? '#ffffff').clone()
      return out
    })
  }, [instances])

  useEffect(() => {
    dirty.current = true
  }, [colors])

  const tmp = useMemo(
    () => ({ m: new Matrix4(), q: new Quaternion(), s: new Vector3(), spin: new Matrix4(), piv: new Matrix4(), back: new Matrix4(), c: new Color(), o: new Object3D() }),
    [],
  )

  useFrame(({ clock }, dt) => {
    const time = clock.elapsedTime
    let moving = false
    instances.forEach((inst, i) => {
      const l = live.current[i]
      const target = l.target
      if (l.t < 1) {
        l.t = Math.min(1, l.t + dt / 1.8)
        const e = l.t < 0.5 ? 2 * l.t * l.t : 1 - (-2 * l.t + 2) ** 2 / 2
        l.pos.lerpVectors(l.from, target, e)
        l.pos.y += Math.sin(Math.PI * l.t) * Math.min(14, l.from.distanceTo(target) * 0.5)
        moving = true
      } else if (!l.pos.equals(target)) {
        l.pos.copy(target)
        moving = true
      }
      const ds = inst.scale - l.scale
      if (Math.abs(ds) > 0.001) {
        l.scale += ds * Math.min(1, dt * 5)
        moving = true
      }
      if (animated) l.spin += dt * inst.activity * 7
    })
    if (!dirty.current && !moving && !animated && !instances.some((x) => x.blink)) return

    kit.parts.forEach((part, pi) => {
      const mesh = refs.current[pi]
      if (!mesh) return
      instances.forEach((inst, i) => {
        const l = live.current[i]
        tmp.q.setFromAxisAngle(UP, inst.rotY)
        tmp.s.setScalar(Math.max(0.0001, l.scale) * (inst.size ?? 1))
        tmp.m.compose(l.pos, tmp.q, tmp.s)
        if (part.role === 'fan' || part.role === 'belt') {
          // Ventola: gira sul suo asse (Z); nastro: piccolo movimento avanti e indietro.
          tmp.piv.makeTranslation(part.pivot.x, part.pivot.y, part.pivot.z)
          tmp.back.makeTranslation(-part.pivot.x, -part.pivot.y, -part.pivot.z)
          if (part.role === 'fan') tmp.spin.makeRotationZ(l.spin)
          else tmp.spin.makeTranslation(Math.sin(l.spin) * 0.04 * inst.activity, 0, 0)
          tmp.m.multiply(tmp.piv).multiply(tmp.spin).multiply(tmp.back)
        }
        tmp.m.multiply(part.matrix)
        mesh.setMatrixAt(i, tmp.m)
        if (!ghost && TINTED.includes(part.role)) {
          tmp.c.copy(colors[i][part.role]!)
          if (inst.blink && part.role !== 'accent') tmp.c.multiplyScalar(0.55 + 0.45 * (0.5 + 0.5 * Math.sin(time * 4 + i)))
          mesh.setColorAt(i, tmp.c)
        }
      })
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
      mesh.computeBoundingSphere()
    })
    dirty.current = false
  })

  const pick = (e: ThreeEvent<PointerEvent | MouseEvent>) => {
    const inst = e.instanceId !== undefined ? instances[e.instanceId] : undefined
    if (ghost || !inst?.pickable || inst.scale < 0.5) return undefined
    if (pickRoom && inst.room !== pickRoom) return undefined
    return inst
  }

  return (
    <group>
      {kit.parts.map((part, pi) => (
        <instancedMesh
          key={`${pi}-${count}`}
          ref={(m) => {
            refs.current[pi] = m
          }}
          args={[part.geometry, materials[pi], count]}
          castShadow={!ghost && (part.role === 'body' || part.role === 'accent')}
          receiveShadow={!ghost}
          {...(ghost ? { raycast: () => null } : {})}
          frustumCulled={false}
          onPointerMove={(e) => {
            const inst = pick(e)
            if (!inst) return
            e.stopPropagation()
            onHover(inst.itemId)
          }}
          onPointerOut={() => onHover(null)}
          onClick={(e) => {
            const inst = pick(e)
            if (!inst) return
            e.stopPropagation()
            onSelect(inst.itemId)
          }}
        />
      ))}
    </group>
  )
}
