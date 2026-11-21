import { Suspense, useEffect, useRef } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { CameraControls } from '@react-three/drei'
import { MathUtils, Vector3 } from 'three'
import { useApp } from '../store'
import { AllocationScene, useOffice } from './twin/Allocation'

/** Obiettivo «lungo» (FOV piccolo): la vista sembra un'assonometria, come un plastico. */
const FOV = 22
/** Angolo isometrico unico per tutti i reparti (da sud-est; ruotato di 180° = da nord-ovest). */
const ISO = new Vector3(1, 0.95, 1).normalize()
/** Spazio occupato dalla UI (px): scheda a destra e titolo in basso. */
export const PANEL_W = 420
const TITLE_H = 130

export function Scene() {
  const select = useApp((s) => s.select)
  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: [0, 120, 0.01], fov: FOV, near: 1, far: 600 }}
      onPointerMissed={() => useApp.getState().room && select(null)}
      onCreated={({ gl }) => {
        gl.localClippingEnabled = true
      }}
      gl={{ antialias: true }}
    >
      <color attach="background" args={['#FFFFFF']} />

      {/* Luce morbida di tarda mattina, come i render di Blender. */}
      <hemisphereLight args={['#FFF9F0', '#E6DCCB', 1.4]} />
      <directionalLight
        position={[22, 50, 30]}
        intensity={1.6}
        castShadow
        shadow-mapSize={[4096, 4096]}
        shadow-camera-left={-30}
        shadow-camera-right={30}
        shadow-camera-top={25}
        shadow-camera-bottom={-25}
        shadow-bias={-0.0003}
        shadow-normalBias={0.03}
      />
      <ambientLight intensity={0.2} />

      <Suspense fallback={null}>
        <AllocationScene />
        <CameraRig />
      </Suspense>
    </Canvas>
  )
}

/** Camera guidata, nessun movimento libero: pianta dall'alto oppure reparto in isometria (ruotabile di 180°). */
function CameraRig() {
  const ref = useRef<CameraControls>(null)
  const room = useApp((s) => s.room)
  const turns = useApp((s) => s.turns)
  const last = useRef({ room: null as string | null, panel: false, turns: 0 })
  const panel = useApp((s) => !!s.selectedId)
  const size = useThree((s) => s.size)
  const info = useOffice()

  useEffect(() => {
    const c = ref.current
    if (!c) return
    const vf = MathUtils.degToRad(FOV)
    const aspect = size.width / size.height
    const hf = 2 * Math.atan(Math.tan(vf / 2) * aspect)

    // Solo un giro in più: si ruota attorno al reparto sempre nello stesso verso (mai avanti e indietro).
    const prev = last.current
    last.current = { room, panel, turns }
    if (room && prev.room === room && prev.panel === panel && prev.turns !== turns) {
      c.rotate(Math.PI * (prev.turns - turns), 0, true)
      return
    }
    // Riporta l'azimut in (-π, π] prima di un nuovo setLookAt, così la camera non fa giri inutili.
    c.normalizeRotations()

    if (!room) {
      // Pianta: tutto l'ufficio, dritto dall'alto, nord in alto.
      const { center, size: s } = info.office
      const dist = Math.max(s.x / 2 / Math.tan(hf / 2), s.z / 2 / Math.tan(vf / 2)) * 1.1 + 2
      c.setFocalOffset(0, 0, 0, true)
      c.setLookAt(center.x, dist, center.z + 0.001, center.x, 0, center.z, true)
      return
    }

    const r = info.rooms[room]
    if (!r) return
    const target = r.center.clone().setY(0.6)
    // La stanza deve stare nello spazio libero: sopra il titolo e, se la scheda è aperta, alla sua sinistra.
    const freeW = size.width - (panel ? PANEL_W + 48 : 0)
    const freeH = size.height - TITLE_H
    const radius = 0.5 * Math.hypot(r.size.x, r.size.z) + 0.5
    const distV = radius / Math.sin(vf / 2) / (freeH / size.height)
    const distH = radius / Math.sin(hf / 2) / (freeW / size.width)
    const dist = Math.max(distV, distH) * 0.8
    const dir = turns % 2 !== 0 ? new Vector3(-ISO.x, ISO.y, -ISO.z) : ISO.clone()
    const pos = target.clone().addScaledVector(dir, dist)
    c.setLookAt(pos.x, pos.y, pos.z, target.x, target.y, target.z, true)
    // Sposta l'inquadratura senza cambiare angolo: in su per il titolo, a sinistra per la scheda.
    const worldPerPx = (2 * dist * Math.tan(vf / 2)) / size.height
    c.setFocalOffset(panel ? ((PANEL_W + 48) / 2) * worldPerPx : 0, (TITLE_H / 2) * worldPerPx, 0, true)
  }, [room, turns, panel, size, info])

  return <CameraControls ref={ref} makeDefault enabled={false} smoothTime={0.7} minPolarAngle={0} maxPolarAngle={Math.PI / 2} />
}
