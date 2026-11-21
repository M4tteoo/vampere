import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { QuadraticBezierLine } from '@react-three/drei'
import { Group, Vector3 } from 'three'
import type { QuadraticBezierLineRef } from '@react-three/drei'
import { useApp } from '../store'
import { effectiveEntity } from '../data/compute'
import type { LocationId, Metrics } from '../data/types'
import { CABLE_ORIGIN, ISLANDS } from './layout'
import { P, gridColor } from './palette'

const LOCS: LocationId[] = ['CH', 'DE', 'IE', 'EU']

export function useLocationTotals() {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  return useMemo(() => {
    const now: Record<LocationId, Metrics> = {
      CH: { cost_chf: 0, kwh: 0, co2_kg: 0 },
      DE: { cost_chf: 0, kwh: 0, co2_kg: 0 },
      IE: { cost_chf: 0, kwh: 0, co2_kg: 0 },
      EU: { cost_chf: 0, kwh: 0, co2_kg: 0 },
    }
    const base: Record<LocationId, number> = { CH: 0, DE: 0, IE: 0, EU: 0 }
    for (const e of data.entities) {
      base[e.location] += e.metrics.co2_kg
      const eff = effectiveEntity(e, data, active)
      // Se un'entità si sposta, la sua CO₂ si ricalcola con la rete della nuova sede.
      const gridFrom = data.summary.locations.find((l) => l.id === e.location)!.grid_kg_per_kwh.mid
      const gridTo = data.summary.locations.find((l) => l.id === eff.location)!.grid_kg_per_kwh.mid
      const m = now[eff.location]
      m.cost_chf += eff.metrics.cost_chf
      m.kwh += eff.metrics.kwh
      m.co2_kg += eff.moved ? (eff.metrics.co2_kg * gridTo) / gridFrom : eff.metrics.co2_kg
    }
    const maxBase = Math.max(...Object.values(base))
    const maxKwh = Math.max(...data.entities.map((e) => e.metrics.kwh)) * 2
    return { now, maxBase, maxKwh }
  }, [data, active])
}

/** Cavi di energia da Basilea ai data center + nuvole di CO₂ sopra ogni isola. */
export function Flows() {
  const data = useApp((s) => s.data)!
  const { now, maxBase, maxKwh } = useLocationTotals()
  return (
    <>
      {LOCS.map((id) => {
        const grid = data.summary.locations.find((l) => l.id === id)!.grid_kg_per_kwh.mid
        return (
          <group key={id}>
            <Cable to={id} kwh={now[id].kwh} maxKwh={maxKwh} color={gridColor(grid)} />
            <Co2Cloud at={id} co2={now[id].co2_kg} maxCo2={maxBase} />
          </group>
        )
      })}
    </>
  )
}

function Cable({ to, kwh, maxKwh, color }: { to: LocationId; kwh: number; maxKwh: number; color: string }) {
  const ref = useRef<QuadraticBezierLineRef>(null)
  const isl = ISLANDS[to]
  const end = useMemo(() => new Vector3(isl.pos[0], isl.pos[1] + 0.3, isl.pos[2]), [isl])
  const start = useMemo(() => new Vector3(...CABLE_ORIGIN), [])
  const mid = useMemo(() => start.clone().lerp(end, 0.5).add(new Vector3(0, 6, 0)), [start, end])
  const width = 1.5 + 9 * Math.sqrt(kwh / maxKwh)
  useFrame((_, dt) => {
    const mat = ref.current?.material
    if (mat) mat.dashOffset -= dt * (0.4 + (kwh / maxKwh) * 3)
  })
  return (
    <QuadraticBezierLine
      ref={ref}
      start={start}
      end={end}
      mid={mid}
      color={color}
      lineWidth={width}
      dashed
      dashScale={2}
      dashSize={0.6}
      gapSize={0.35}
      transparent
      opacity={0.95}
    />
  )
}

const PUFFS: [number, number, number, number][] = [
  [0, 0, 0, 1],
  [0.9, -0.15, 0.2, 0.75],
  [-0.85, -0.1, -0.1, 0.8],
  [0.3, 0.45, -0.3, 0.7],
  [-0.3, 0.35, 0.45, 0.6],
]

function Co2Cloud({ at, co2, maxCo2 }: { at: LocationId; co2: number; maxCo2: number }) {
  const ref = useRef<Group>(null)
  const isl = ISLANDS[at]
  const target = 0.25 + 1.6 * Math.sqrt(co2 / maxCo2)
  useFrame(({ clock }, dt) => {
    const g = ref.current
    if (!g) return
    const s = g.scale.x + (target - g.scale.x) * Math.min(1, dt * 2.5)
    g.scale.setScalar(s)
    g.position.y = isl.pos[1] + 4.2 + s * 0.6 + Math.sin(clock.elapsedTime * 0.8 + isl.pos[0]) * 0.15
  })
  return (
    <group>
      <group ref={ref} position={[isl.pos[0], isl.pos[1] + 5, isl.pos[2]]}>
        {PUFFS.map(([x, y, z, r], i) => (
          <mesh key={i} position={[x, y, z]}>
            <sphereGeometry args={[r, 20, 16]} />
            <meshStandardMaterial color={P.cloud} roughness={1} transparent opacity={0.92} />
          </mesh>
        ))}
      </group>
    </group>
  )
}
