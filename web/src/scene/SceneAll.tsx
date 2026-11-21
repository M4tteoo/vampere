import { Suspense, useEffect, useRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { CameraControls, ContactShadows, Html, useProgress } from '@react-three/drei'
import { Vector3 } from 'three'
import { useApp, type View } from '../store'
import { Twin, registry } from './twin/TwinAll'

/** Direzione da cui guarda la camera (3/4 da sud-est, come le immagini di Blender). */
const DIR = new Vector3(0.5, 1.05, 1.2).normalize()

export const VIEWS: Record<View, { target: [number, number, number]; dist: number }> = {
  overview: { target: [-13, 0, -13], dist: 122 },
  office: { target: [0, 0, 2], dist: 66 },
  islands: { target: [-32, 3, -29], dist: 54 },
}

export function SceneAll() {
  const select = useApp((s) => s.select)
  const { target, dist } = VIEWS.overview
  const start = new Vector3(...target).addScaledVector(DIR, dist)
  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: start.toArray(), fov: 28, near: 0.5, far: 600 }}
      onPointerMissed={() => select(null)}
      gl={{ antialias: true }}
    >
      <color attach="background" args={['#F3F0EA']} />
      <fog attach="fog" args={['#F3F0EA', 150, 300]} />

      {/* Luce di tarda mattina: emisfera calda + sole morbido da nord-est (come nei render di Blender). */}
      <hemisphereLight args={['#FFF9F0', '#E6DCCB', 1.35]} />
      <directionalLight
        position={[30, 60, 22]}
        intensity={1.7}
        castShadow
        shadow-mapSize={[4096, 4096]}
        shadow-camera-left={-60}
        shadow-camera-right={45}
        shadow-camera-top={45}
        shadow-camera-bottom={-60}
        shadow-bias={-0.0003}
        shadow-normalBias={0.03}
      />
      <ambientLight intensity={0.2} />

      <Suspense fallback={<Loading />}>
        <Twin />
        <ContactShadows position={[0, -0.62, 0]} scale={120} blur={2.8} opacity={0.3} far={20} />
      </Suspense>
      <CameraRig />
    </Canvas>
  )
}

function Loading() {
  const { progress } = useProgress()
  return (
    <Html center>
      <div className="pill-shadow whitespace-nowrap rounded-full bg-white px-4 py-2 text-sm font-semibold text-ink">
        Carico il plastico… {Math.round(progress)}%
      </div>
    </Html>
  )
}

/** Controlli della camera: viste d'insieme, volo verso stanza / isola / oggetto selezionato. */
function CameraRig() {
  const ref = useRef<CameraControls>(null)
  const selectedId = useApp((s) => s.selectedId)
  const view = useApp((s) => s.view)
  const viewNonce = useApp((s) => s.viewNonce)

  const look = (target: Vector3, dist: number) => {
    const pos = target.clone().addScaledVector(DIR, dist)
    ref.current?.setLookAt(pos.x, pos.y, pos.z, target.x, target.y, target.z, true)
  }

  useEffect(() => {
    const v = VIEWS[view]
    look(new Vector3(...v.target), v.dist)
  }, [view, viewNonce])

  useEffect(() => {
    if (!selectedId) return
    const a = registry.anchors
    if (selectedId.startsWith('room:')) {
      const room = a?.rooms[selectedId.slice(5)]
      if (room) look(room.center.clone(), Math.max(room.size.x, room.size.z) * 1.75 + 8)
      return
    }
    if (selectedId.startsWith('loc:')) {
      const isl = a?.islands[selectedId.slice(4)]
      if (isl) look(isl.clone().add(new Vector3(0, 1, 0)), 30)
      return
    }
    // L'oggetto può non essere ancora registrato (prima apertura): riprova al frame dopo.
    let tries = 0
    const go = () => {
      const r = registry.items.get(selectedId)
      if (!r) {
        if (tries++ < 30) requestAnimationFrame(go)
        return
      }
      look(r.pos.clone().add(new Vector3(0, r.h * 0.5, 0)), Math.min(45, Math.max(14, r.h * 9)))
    }
    go()
  }, [selectedId])

  return (
    <CameraControls
      ref={ref}
      makeDefault
      minDistance={4}
      maxDistance={170}
      maxPolarAngle={Math.PI / 2.3}
      smoothTime={0.55}
      dollyToCursor
    />
  )
}
