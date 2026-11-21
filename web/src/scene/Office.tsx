import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, RoundedBox } from '@react-three/drei'
import type { Group } from 'three'
import { useApp } from '../store'
import { fmtMetric, seatsHidden } from '../data/compute'
import type { Department } from '../data/types'
import { CABLE_ORIGIN, OFFICE_SIZE, ROOMS } from './layout'
import { P, heatColor } from './palette'

const WALL_H = 0.9
const WALL_T = 0.14

/** Plastico dell'ufficio di Basilea: una stanza per reparto, scrivanie = posti di licenza. */
export function Office() {
  const data = useApp((s) => s.data)!
  const metric = useApp((s) => s.metric)
  const active = useApp((s) => s.active)
  const hideGhosts = seatsHidden(data, active)
  const total = data.summary.departments.reduce((a, d) => a + d.metrics[metric], 0)

  return (
    <group>
      {/* Basamento */}
      <RoundedBox args={[OFFICE_SIZE.w + 1.2, 0.5, OFFICE_SIZE.d + 1.2]} radius={0.22} position={[0, -0.25, 0]} receiveShadow>
        <meshStandardMaterial color={P.ground} roughness={0.95} />
      </RoundedBox>
      {/* Muri esterni alti (spaccato da plastico: solo retro e lato sinistro) */}
      <RoundedBox args={[OFFICE_SIZE.w, 1.6, WALL_T * 1.6]} radius={0.06} position={[0, 0.8, -OFFICE_SIZE.d / 2]} castShadow receiveShadow>
        <meshStandardMaterial color={P.wall} roughness={0.9} />
      </RoundedBox>
      <RoundedBox args={[WALL_T * 1.6, 1.6, OFFICE_SIZE.d]} radius={0.06} position={[-OFFICE_SIZE.w / 2, 0.8, 0]} castShadow receiveShadow>
        <meshStandardMaterial color={P.wall} roughness={0.9} />
      </RoundedBox>

      {data.summary.departments.map((d) => (
        <Room key={d.id} dept={d} share={total ? d.metrics[metric] / total : 0} hideGhosts={hideGhosts} />
      ))}

      <ServerCabinet />

      <Html position={[0, 0.1, OFFICE_SIZE.d / 2 + 1.1]} center zIndexRange={[10, 0]}>
        <div className="whitespace-nowrap rounded-full bg-white/90 px-4 py-1.5 text-sm font-extrabold shadow-md">
          🏢 Sede di Basilea · qui si decide
        </div>
      </Html>
    </group>
  )
}

function Room({ dept, share, hideGhosts }: { dept: Department; share: number; hideGhosts: boolean }) {
  const r = ROOMS[dept.id]
  const metric = useApp((s) => s.metric)
  if (!r) return null
  const x0 = r.x - r.w / 2
  const z0 = r.z - r.d / 2

  // Griglia di scrivanie dentro la stanza
  const cols = Math.max(1, Math.floor((r.w - 0.8) / 1.45))
  const rows = Math.max(1, Math.floor((r.d - 1.4) / 1.55))
  const seats = Math.min(dept.seats_total, cols * rows)
  const desks = Array.from({ length: seats }, (_, i) => {
    const c = i % cols
    const row = Math.floor(i / cols)
    const x = x0 + 0.4 + (c + 0.5) * ((r.w - 0.8) / cols)
    const z = z0 + 1.0 + (row + 0.5) * ((r.d - 1.4) / rows)
    return { x, z, active: i < dept.seats_active, i }
  })

  return (
    <group>
      {/* Pavimento colorato secondo la metrica */}
      <RoundedBox args={[r.w - 0.12, 0.08, r.d - 0.12]} radius={0.03} position={[r.x, 0.04, r.z]} receiveShadow>
        <meshStandardMaterial color={heatColor(share)} roughness={0.95} />
      </RoundedBox>
      {/* Muri bassi interni: retro e lato sinistro della stanza */}
      <RoundedBox args={[r.w, WALL_H, WALL_T]} radius={0.05} position={[r.x, WALL_H / 2, z0]} castShadow receiveShadow>
        <meshStandardMaterial color={P.wall} roughness={0.9} />
      </RoundedBox>
      <RoundedBox args={[WALL_T, WALL_H, r.d]} radius={0.05} position={[x0, WALL_H / 2, r.z]} castShadow receiveShadow>
        <meshStandardMaterial color={P.wall} roughness={0.9} />
      </RoundedBox>

      {desks.map((d) => (
        <Desk key={d.i} x={d.x} z={d.z} active={d.active} hidden={!d.active && hideGhosts} seed={d.i + dept.id.length} />
      ))}

      <Html position={[r.x, 1.25, z0 + 0.35]} center zIndexRange={[10, 0]}>
        <div className="pointer-events-none whitespace-nowrap rounded-full bg-white/90 px-3 py-1 text-xs font-bold shadow">
          {dept.label} <span className="font-semibold text-neutral-500">· {fmtMetric(dept.metrics[metric], metric)}</span>
        </div>
      </Html>
    </group>
  )
}

/** Scrivania con monitor, sedia e persona. Monitor arancione = licenza pagata ma non usata. */
function Desk({ x, z, active, hidden, seed }: { x: number; z: number; active: boolean; hidden: boolean; seed: number }) {
  const ref = useRef<Group>(null)
  useFrame((_, dt) => {
    if (!ref.current) return
    const target = hidden ? 0.001 : 1
    const s = ref.current.scale.x + (target - ref.current.scale.x) * Math.min(1, dt * 6)
    ref.current.scale.setScalar(s)
    ref.current.visible = s > 0.01
  })
  const shirt = P.shirt[seed % P.shirt.length]
  const skin = P.skin[seed % P.skin.length]
  return (
    <group ref={ref} position={[x, 0.08, z]}>
      {/* Piano e fianchi */}
      <RoundedBox args={[1.05, 0.08, 0.6]} radius={0.03} position={[0, 0.52, 0]} castShadow receiveShadow>
        <meshStandardMaterial color={P.desk} roughness={0.85} />
      </RoundedBox>
      <RoundedBox args={[0.08, 0.5, 0.52]} radius={0.02} position={[-0.45, 0.25, 0]} castShadow>
        <meshStandardMaterial color={P.deskSide} roughness={0.9} />
      </RoundedBox>
      <RoundedBox args={[0.08, 0.5, 0.52]} radius={0.02} position={[0.45, 0.25, 0]} castShadow>
        <meshStandardMaterial color={P.deskSide} roughness={0.9} />
      </RoundedBox>
      {/* Monitor */}
      <RoundedBox args={[0.52, 0.34, 0.05]} radius={0.025} position={[0, 0.8, -0.18]} castShadow>
        <meshStandardMaterial
          color={active ? P.monitorOn : P.monitorGhost}
          emissive={active ? P.monitorOn : P.monitorGhost}
          emissiveIntensity={active ? 0.35 : 0.55}
          roughness={0.5}
        />
      </RoundedBox>
      <mesh position={[0, 0.6, -0.18]} castShadow>
        <cylinderGeometry args={[0.025, 0.025, 0.12, 8]} />
        <meshStandardMaterial color={P.rackLight} />
      </mesh>
      {/* Sedia */}
      <mesh position={[0, 0.32, 0.5]} castShadow>
        <cylinderGeometry args={[0.2, 0.2, 0.08, 16]} />
        <meshStandardMaterial color={P.chair} roughness={0.8} />
      </mesh>
      {/* Persona (solo se la licenza è usata) */}
      {active && (
        <group position={[0, 0.36, 0.5]}>
          <mesh position={[0, 0.27, 0]} castShadow>
            <capsuleGeometry args={[0.15, 0.22, 4, 12]} />
            <meshStandardMaterial color={shirt} roughness={0.8} />
          </mesh>
          <mesh position={[0, 0.62, 0]} castShadow>
            <sphereGeometry args={[0.13, 16, 16]} />
            <meshStandardMaterial color={skin} roughness={0.7} />
          </mesh>
        </group>
      )}
    </group>
  )
}

/** Armadio rack nella stanza IT: da qui partono i cavi verso i data center. */
function ServerCabinet() {
  const [x, , z] = CABLE_ORIGIN
  return (
    <group position={[x, 0, z + 0.2]}>
      <RoundedBox args={[0.9, 1.9, 0.7]} radius={0.08} position={[0, 0.95, 0]} castShadow receiveShadow>
        <meshStandardMaterial color={P.rack} roughness={0.7} />
      </RoundedBox>
      {[0.5, 0.85, 1.2, 1.55].map((y) => (
        <mesh key={y} position={[0, y, 0.36]}>
          <boxGeometry args={[0.6, 0.05, 0.02]} />
          <meshStandardMaterial color={P.ledOk} emissive={P.ledOk} emissiveIntensity={1.2} />
        </mesh>
      ))}
    </group>
  )
}
