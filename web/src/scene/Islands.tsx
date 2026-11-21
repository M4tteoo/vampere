import { Html } from '@react-three/drei'
import { useApp } from '../store'
import type { LocationId } from '../data/types'
import { ISLANDS } from './layout'
import { P, gridColor } from './palette'
import { useLocationTotals } from './Flows'
import { fmtMetric } from '../data/compute'

/** Isole fluttuanti dei data center, colorate secondo l'intensità di carbonio della rete locale. */
export function Islands() {
  const data = useApp((s) => s.data)!
  const { now } = useLocationTotals()
  return (
    <>
      {data.summary.locations.map((loc) => (
        <Island key={loc.id} id={loc.id} label={loc.label} grid={loc.grid_kg_per_kwh.mid} co2={now[loc.id].co2_kg} />
      ))}
    </>
  )
}

function Island({ id, label, grid, co2 }: { id: LocationId; label: string; grid: number; co2: number }) {
  const isl = ISLANDS[id]
  const [x, y, z] = isl.pos
  const top = gridColor(grid)
  const isCloud = id === 'EU'
  return (
    <group position={[x, y, z]}>
      <group>
        {/* Prato / piattaforma */}
        <mesh position={[0, 0, 0]} castShadow receiveShadow>
          <cylinderGeometry args={[isl.radius, isl.radius * 0.96, 0.5, 48]} />
          <meshStandardMaterial color={top} roughness={0.95} />
        </mesh>
        {/* Bordo più chiaro */}
        <mesh position={[0, 0.26, 0]} receiveShadow>
          <cylinderGeometry args={[isl.radius * 0.92, isl.radius * 0.92, 0.04, 48]} />
          <meshStandardMaterial color={top} roughness={1} transparent opacity={0.55} />
        </mesh>
        {/* Roccia sotto (o nuvola per la UE) */}
        {isCloud ? (
          [0, 1, 2, 3, 4].map((i) => (
            <mesh key={i} position={[Math.cos(i * 1.3) * isl.radius * 0.55, -0.55, Math.sin(i * 1.3) * isl.radius * 0.55]}>
              <sphereGeometry args={[isl.radius * 0.42, 20, 16]} />
              <meshStandardMaterial color="#ffffff" roughness={1} />
            </mesh>
          ))
        ) : (
          <>
            <mesh position={[0, -1.35, 0]} rotation={[Math.PI, 0, 0]} castShadow>
              <coneGeometry args={[isl.radius * 0.95, 2.3, 7]} />
              <meshStandardMaterial color={P.rock} roughness={1} flatShading />
            </mesh>
            <mesh position={[isl.radius * 0.25, -2.2, 0.3]} rotation={[Math.PI, 0.4, 0]}>
              <coneGeometry args={[isl.radius * 0.4, 1.4, 6]} />
              <meshStandardMaterial color={P.rockDark} roughness={1} flatShading />
            </mesh>
          </>
        )}
      </group>

      <Html position={[0, -0.2, isl.radius + 0.6]} center zIndexRange={[10, 0]}>
        <div className="pointer-events-none flex flex-col items-center whitespace-nowrap rounded-2xl bg-white/95 px-3 py-1.5 shadow-md">
          <span className="text-sm font-extrabold">
            {isl.flag} {label}
          </span>
          <span className="text-[11px] font-semibold text-neutral-500">
            rete: <b style={{ color: '#333' }}>{grid.toFixed(2)}</b> kg CO₂/kWh
          </span>
          <span className="mt-0.5 rounded-full bg-neutral-700 px-2 py-0.5 text-[11px] font-extrabold text-white">☁️ {fmtMetric(co2, 'co2_kg')}</span>
        </div>
      </Html>
    </group>
  )
}
