import { useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, RoundedBox } from '@react-three/drei'
import { Vector3, type Group, type Mesh, type MeshStandardMaterial } from 'three'
import { useApp } from '../store'
import { effectiveEntity, type EffectiveEntity } from '../data/compute'
import type { EntityKind, LocationId } from '../data/types'
import { slotPosition } from './layout'
import { P } from './palette'

type LedMode = 'ok' | 'waste' | 'off'

/** Tutte le risorse (server, cluster, storage, AI, SaaS) sulle isole, nello stato dato dalle misure attive. */
export function Entities() {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)

  const placed = useMemo(() => {
    const eff = data.entities.map((e) => effectiveEntity(e, data, active))
    const counters: Record<LocationId, number> = { CH: 0, DE: 0, IE: 0, EU: 0 }
    // Prima le entità originarie del luogo, poi quelle spostate (così prendono gli slot liberi).
    const ordered = [...eff.filter((x) => !x.moved), ...eff.filter((x) => x.moved)]
    return ordered.map((x) => ({ eff: x, pos: slotPosition(x.location, counters[x.location]++) }))
  }, [data, active])

  return (
    <>
      {placed.map(({ eff, pos }) => (
        <EntityNode key={eff.entity.id} eff={eff} target={pos} />
      ))}
    </>
  )
}

function EntityNode({ eff, target }: { eff: EffectiveEntity; target: [number, number, number] }) {
  const ref = useRef<Group>(null)
  const select = useApp((s) => s.select)
  const selectedId = useApp((s) => s.selectedId)
  const [hover, setHover] = useState(false)
  const { entity, visual } = eff
  const isWaste = entity.tags.includes('waste') && visual === 'normal'
  const led: LedMode = visual === 'off' || visual === 'removed' ? 'off' : isWaste ? 'waste' : 'ok'
  const selected = selectedId === entity.id
  const targetScale = visual === 'removed' ? 0.001 : visual === 'reduced' ? 1 - eff.reduction * 0.35 : 1
  const tv = useMemo(() => new Vector3(...target), [target])

  useFrame((_, dt) => {
    const g = ref.current
    if (!g) return
    const k = Math.min(1, dt * 2.2)
    // Movimento ad arco: più è lontano dalla meta, più sale.
    const dist = g.position.distanceTo(tv)
    g.position.x += (tv.x - g.position.x) * k
    g.position.z += (tv.z - g.position.z) * k
    const arc = Math.min(4, dist * 0.25)
    g.position.y += (tv.y + arc - g.position.y) * Math.min(1, dt * 4)
    const s = g.scale.x + (targetScale - g.scale.x) * Math.min(1, dt * 4)
    g.scale.setScalar(s)
    g.visible = s > 0.01
  })

  return (
    <group
      ref={ref}
      position={target}
      onClick={(e) => {
        e.stopPropagation()
        select(entity.id)
      }}
      onPointerOver={(e) => {
        e.stopPropagation()
        setHover(true)
        document.body.style.cursor = 'pointer'
      }}
      onPointerOut={() => {
        setHover(false)
        document.body.style.cursor = 'auto'
      }}
    >
      <Model kind={entity.kind} count={entity.count ?? 1} led={led} />

      {(selected || hover) && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
          <ringGeometry args={[1.05, 1.2, 48]} />
          <meshBasicMaterial color={P.select} transparent opacity={selected ? 0.9 : 0.45} />
        </mesh>
      )}

      <Html position={[0, 2.25, 0]} center zIndexRange={[20, 0]}>
        <div className="pointer-events-none flex flex-col items-center gap-0.5">
          <div className="flex gap-1">
            {entity.tags.includes('locked') && <Badge>🔒</Badge>}
            {entity.tags.includes('human') && <Badge>🧑‍💼</Badge>}
            {entity.tags.includes('contradiction') && <Badge>⚠️</Badge>}
            {isWaste && <span className="rounded-full bg-orange-400 px-2 py-0.5 text-[10px] font-extrabold text-white shadow">spreco</span>}
            {eff.moved && <span className="rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-extrabold text-white shadow">spostato</span>}
          </div>
          {(hover || selected) && (
            <div className="whitespace-nowrap rounded-lg bg-white/95 px-2 py-0.5 text-[11px] font-bold shadow">{entity.label}</div>
          )}
        </div>
      </Html>
    </group>
  )
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-white px-1.5 py-0.5 text-xs shadow">{children}</span>
}

/** Striscia luminosa che segnala lo stato: verde ok, arancione che pulsa = spreco, grigio = spento. */
function Led({ position, size, mode }: { position: [number, number, number]; size: [number, number, number]; mode: LedMode }) {
  const ref = useRef<Mesh>(null)
  const color = mode === 'ok' ? P.ledOk : mode === 'waste' ? P.ledWaste : P.ledOff
  useFrame(({ clock }) => {
    const m = ref.current?.material as MeshStandardMaterial | undefined
    if (!m) return
    m.emissiveIntensity = mode === 'waste' ? 0.8 + Math.sin(clock.elapsedTime * 4) * 0.7 : mode === 'ok' ? 1.1 : 0
  })
  return (
    <mesh ref={ref} position={position}>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1} />
    </mesh>
  )
}

function Model({ kind, count, led }: { kind: EntityKind; count: number; led: LedMode }) {
  switch (kind) {
    case 'cluster':
      return <Cluster count={Math.min(count, 3)} led={led} />
    case 'server_group':
      return <ServerGroup count={Math.min(count, 6)} led={led} />
    case 'gpu':
      return <Gpu led={led} />
    case 'storage':
      return <Storage count={Math.min(count, 4)} led={led} />
    case 'ai_api':
      return <AiBrain led={led} />
    case 'subscriptions':
      return <Cards led={led} />
    case 'saas':
      return <AppTiles led={led} />
    case 'reporting':
      return <Report led={led} />
    case 'build':
      return <Build led={led} />
  }
}

function Cluster({ count, led }: { count: number; led: LedMode }) {
  const off = led === 'off'
  return (
    <group>
      {Array.from({ length: count }, (_, i) => {
        const x = (i - (count - 1) / 2) * 0.56
        return (
          <group key={i} position={[x, 0, 0]}>
            <RoundedBox args={[0.5, 1.5, 0.7]} radius={0.06} position={[0, 0.75, 0]} castShadow receiveShadow>
              <meshStandardMaterial color={off ? P.rackLight : P.rack} roughness={0.7} />
            </RoundedBox>
            {[0.35, 0.65, 0.95, 1.25].map((y) => (
              <Led key={y} position={[0, y, 0.36]} size={[0.34, 0.05, 0.02]} mode={led} />
            ))}
          </group>
        )
      })}
    </group>
  )
}

function ServerGroup({ count, led }: { count: number; led: LedMode }) {
  const cols = Math.min(3, count)
  return (
    <group>
      {Array.from({ length: count }, (_, i) => {
        const c = i % cols
        const r = Math.floor(i / cols)
        const x = (c - (cols - 1) / 2) * 0.52
        return (
          <group key={i} position={[x, r * 0.4, 0]}>
            <RoundedBox args={[0.46, 0.36, 0.6]} radius={0.05} position={[0, 0.18, 0]} castShadow receiveShadow>
              <meshStandardMaterial color={led === 'off' ? P.rackLight : '#e8eef5'} roughness={0.75} />
            </RoundedBox>
            <Led position={[0.12, 0.18, 0.31]} size={[0.12, 0.05, 0.02]} mode={led} />
          </group>
        )
      })}
    </group>
  )
}

function Gpu({ led }: { led: LedMode }) {
  const fan = useRef<Mesh>(null)
  useFrame((_, dt) => {
    if (fan.current && led !== 'off') fan.current.rotation.z += dt * 6
  })
  return (
    <group>
      <RoundedBox args={[0.9, 1.15, 0.8]} radius={0.08} position={[0, 0.575, 0]} castShadow receiveShadow>
        <meshStandardMaterial color={led === 'off' ? P.rackLight : P.gpu} roughness={0.6} />
      </RoundedBox>
      <mesh ref={fan} position={[0, 0.65, 0.41]} rotation={[0, 0, 0]}>
        <cylinderGeometry args={[0.28, 0.28, 0.04, 6]} />
        <meshStandardMaterial color="#ffffff" roughness={0.5} />
      </mesh>
      <mesh position={[0, 0.65, 0.41]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.3, 0.035, 8, 24]} />
        <meshStandardMaterial color={P.rack} />
      </mesh>
      <Led position={[0, 0.18, 0.41]} size={[0.5, 0.05, 0.02]} mode={led} />
    </group>
  )
}

function Storage({ count, led }: { count: number; led: LedMode }) {
  return (
    <group>
      {Array.from({ length: count }, (_, i) => (
        <group key={i} position={[0, 0.12 + i * 0.26, 0]}>
          <mesh castShadow receiveShadow>
            <cylinderGeometry args={[0.55, 0.55, 0.22, 32]} />
            <meshStandardMaterial color={P.storage} roughness={0.7} />
          </mesh>
          <Led position={[0, 0, 0.55]} size={[0.25, 0.04, 0.02]} mode={led} />
        </group>
      ))}
    </group>
  )
}

function AiBrain({ led }: { led: LedMode }) {
  const ring = useRef<Mesh>(null)
  useFrame((_, dt) => {
    if (ring.current) ring.current.rotation.z += dt * (led === 'off' ? 0.2 : 1)
  })
  const glow = led === 'waste' ? P.ledWaste : P.ai
  return (
    <group position={[0, 0.85, 0]}>
      <mesh castShadow>
        <sphereGeometry args={[0.6, 32, 24]} />
        <meshStandardMaterial color={P.ai} emissive={glow} emissiveIntensity={0.25} roughness={0.55} />
      </mesh>
      <mesh ref={ring} rotation={[Math.PI / 2.6, 0, 0]}>
        <torusGeometry args={[0.9, 0.04, 8, 48]} />
        <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.3} />
      </mesh>
      <mesh position={[0, -0.75, 0]} castShadow>
        <cylinderGeometry args={[0.35, 0.45, 0.2, 24]} />
        <meshStandardMaterial color={P.rackLight} roughness={0.8} />
      </mesh>
      <Led position={[0, -0.75, 0.42]} size={[0.3, 0.05, 0.02]} mode={led} />
    </group>
  )
}

function Cards({ led }: { led: LedMode }) {
  const colors = ['#10a37f', '#7fa7d9', '#d97757']
  return (
    <group>
      {colors.map((c, i) => (
        <group key={c} position={[(i - 1) * 0.12, 0.45 + i * 0.12, (i - 1) * 0.1]} rotation={[-0.35, 0.2 * (i - 1), 0]}>
          <RoundedBox args={[1.0, 0.65, 0.06]} radius={0.04} castShadow>
            <meshStandardMaterial color={P.card} roughness={0.6} />
          </RoundedBox>
          <mesh position={[0, 0.2, 0.035]}>
            <boxGeometry args={[0.8, 0.1, 0.01]} />
            <meshStandardMaterial color={c} />
          </mesh>
        </group>
      ))}
      <Led position={[0, 0.06, 0.4]} size={[0.5, 0.05, 0.02]} mode={led} />
    </group>
  )
}

function AppTiles({ led }: { led: LedMode }) {
  const colors = ['#f28b82', '#f7c873', '#a7d7c5', '#7fa7d9', '#b39ddb', '#90caf9']
  return (
    <group>
      {colors.map((c, i) => {
        const x = ((i % 3) - 1) * 0.5
        const z = (Math.floor(i / 3) - 0.5) * 0.5
        return (
          <RoundedBox key={c} args={[0.4, 0.4, 0.4]} radius={0.1} position={[x, 0.22 + (i % 2) * 0.08, z]} castShadow>
            <meshStandardMaterial color={c} roughness={0.6} />
          </RoundedBox>
        )
      })}
      <Led position={[0, 0.05, 0.5]} size={[0.6, 0.05, 0.02]} mode={led} />
    </group>
  )
}

function Report({ led }: { led: LedMode }) {
  return (
    <group>
      <RoundedBox args={[1.3, 0.9, 0.08]} radius={0.05} position={[0, 0.85, 0]} castShadow>
        <meshStandardMaterial color="#ffffff" roughness={0.6} />
      </RoundedBox>
      {[0.25, 0.45, 0.35, 0.6].map((h, i) => (
        <mesh key={i} position={[-0.4 + i * 0.27, 0.5 + h / 2, 0.05]}>
          <boxGeometry args={[0.16, h, 0.02]} />
          <meshStandardMaterial color={['#7fa7d9', '#a7d7c5', '#f7c873', '#f28b82'][i]} />
        </mesh>
      ))}
      <mesh position={[0, 0.2, 0]} castShadow>
        <cylinderGeometry args={[0.05, 0.05, 0.4, 8]} />
        <meshStandardMaterial color={P.rackLight} />
      </mesh>
      <Led position={[0, 0.05, 0.2]} size={[0.4, 0.05, 0.02]} mode={led} />
    </group>
  )
}

function Build({ led }: { led: LedMode }) {
  const gear = useRef<Mesh>(null)
  useFrame((_, dt) => {
    if (gear.current && led !== 'off') gear.current.rotation.z += dt * 1.5
  })
  return (
    <group>
      <RoundedBox args={[1.2, 0.45, 0.7]} radius={0.08} position={[0, 0.22, 0]} castShadow receiveShadow>
        <meshStandardMaterial color="#e8eef5" roughness={0.75} />
      </RoundedBox>
      <mesh ref={gear} position={[0, 0.85, 0]}>
        <torusGeometry args={[0.28, 0.1, 6, 8]} />
        <meshStandardMaterial color={P.chair} roughness={0.6} />
      </mesh>
      <Led position={[0, 0.22, 0.36]} size={[0.5, 0.05, 0.02]} mode={led} />
    </group>
  )
}
