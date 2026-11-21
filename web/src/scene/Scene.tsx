import { Suspense, useEffect, useRef } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { CameraControls } from '@react-three/drei'
import { MathUtils, PerspectiveCamera, Vector3 } from 'three'
import { useApp } from '../store'
import { useIntro } from '../intro/store'
import { AllocationScene, ISO, TOP, useStageLayout } from './twin/Allocation'

/** Obiettivo «lungo» (FOV piccolo): la vista sembra un'assonometria, come un plastico. */
const FOV = 22
/** Spazio occupato dalla UI (px): scheda a destra e titolo in basso. */
export const PANEL_W = 420
const TITLE_H = 130
/** Spazio in alto per i titoli dei palchi. */
const TOP_H = 110
/** Pianta dei passi 2–4: spazio in basso per la barra del tempo. */
const PLAN_BOTTOM = 90
/** Pianta dei passi 2–4: spazio a sinistra per la legenda. */
const LEGEND_W = 300

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

/** Camera guidata, nessun movimento libero: pianta dall'alto oppure reparto in isometria, sempre dallo stesso angolo. */
function CameraRig() {
  const ref = useRef<CameraControls>(null)
  const room = useApp((s) => s.room)
  const panel = useApp((s) => !!s.selectedId)
  const step = useApp((s) => s.step)
  const size = useThree((s) => s.size)
  const layout = useStageLayout()
  // Durante l'estrusione la camera la guida l'intro; alla fine si torna alla pianta.
  const building = useIntro((s) => s.phase === 'build')

  useEffect(() => {
    const c = ref.current
    if (!c || !layout || building) return
    const vf = MathUtils.degToRad(FOV)
    const aspect = size.width / size.height
    const plan = layout.view === 'plan'
    const dir = plan ? TOP : ISO
    // Spazio libero (px): nel reparto sotto i titoli dei palchi, sopra il nome del reparto e a sinistra della scheda;
    // nella pianta dei passi 2–4 sopra la barra del tempo e la legenda.
    const bottom = plan ? (step === 'allocation' ? 24 : PLAN_BOTTOM) : TITLE_H
    const heatPlan = plan && step !== 'allocation'
    const free = { l: heatPlan ? LEGEND_W : 24, r: size.width - 24 - (panel ? PANEL_W + 48 : 0), t: heatPlan ? 76 : plan ? 24 : TOP_H, b: size.height - bottom }
    const fx = [(free.l / size.width) * 2 - 1, (free.r / size.width) * 2 - 1]
    const fy = [1 - (free.b / size.height) * 2, 1 - (free.t / size.height) * 2]
    // Inquadratura con la prospettiva vera: si proiettano i punti, poi si ricentra e si regola la distanza (poche iterazioni).
    const cam = new PerspectiveCamera(FOV, aspect, 0.1, 2000)
    const target = layout.center.clone()
    const t = Math.tan(vf / 2)
    let dist = 120
    const camUp = new Vector3()
    const camRight = new Vector3()
    const p = new Vector3()
    for (let i = 0; i < 8; i++) {
      cam.position.copy(target).addScaledVector(dir, dist)
      cam.lookAt(target)
      cam.updateMatrixWorld()
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
      for (const q of layout.points) {
        p.copy(q).project(cam)
        x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y)
      }
      const halfH = dist * t
      camRight.setFromMatrixColumn(cam.matrixWorld, 0)
      camUp.setFromMatrixColumn(cam.matrixWorld, 1)
      // Sposta il punto guardato in modo che il centro del riquadro cada al centro dello spazio libero.
      target.addScaledVector(camRight, (((x0 + x1) - (fx[0] + fx[1])) / 2) * halfH * aspect)
      target.addScaledVector(camUp, (((y0 + y1) - (fy[0] + fy[1])) / 2) * halfH)
      dist *= Math.max((x1 - x0) / (fx[1] - fx[0]), (y1 - y0) / (fy[1] - fy[0])) * 1.04
    }
    const pos = target.clone().addScaledVector(dir, dist)
    c.normalizeRotations()
    c.setFocalOffset(0, 0, 0, true)
    c.setLookAt(pos.x, pos.y, pos.z, target.x, target.y, target.z, true)
  }, [room, panel, size, layout, step, building])

  return <CameraControls ref={ref} makeDefault enabled={false} smoothTime={0.45} minPolarAngle={0} maxPolarAngle={Math.PI / 2} />
}
