import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useGLTF, type CameraControls } from '@react-three/drei'
import { CanvasTexture, DoubleSide, Group, MeshBasicMaterial, Object3D, SRGBColorSpace, Vector3 } from 'three'
import {
  BLUEPRINT_META_URL,
  BLUEPRINT_URL,
  BUILD_S,
  easeInOut,
  easeOutBack,
  ramp,
  useIntro,
  type BlueprintMeta,
} from '../../intro/store'
import { MODELS } from './kit'

const OFFICE = `${MODELS}/env_office_v1.glb`
/** Il foglio sta appena sopra i pavimenti: i muri «crescono» attraverso le linee della pianta. */
const PAPER_Y = 0.05
/** Strati della «stampa» delle postazioni e altezza di una postazione (scrivania + monitor). */
const LAYERS = 14
const SEAT_H = 1.25
/** Piano di costruzione: velo luminoso all'altezza dello strato in corso. */
const slabMaterial = new MeshBasicMaterial({ color: '#7dffbf', transparent: true, opacity: 0.1, depthWrite: false, toneMapped: false, side: DoubleSide })
const slabEdge = new MeshBasicMaterial({ color: '#2fd88a', transparent: true, opacity: 0.9, depthWrite: false, toneMapped: false, side: DoubleSide })

/** Ordine di costruzione dei reparti: da ovest verso est, come una passata di stampante. */
export const BUILD_ORDER = ['it', 'consulting', 'finance', 'corridor', 'sales', 'management', 'marketing', 'hr', 'reception']

/** Gruppi animati dall'intro: l'edificio e le postazioni di ogni reparto (li registra AllocationScene). */
export const buildGroups: { walls: Group | null; rooms: Record<string, Group | null> } = { walls: null, rooms: {} }

let metaPromise: Promise<BlueprintMeta> | null = null
export function loadBlueprintMeta() {
  return (metaPromise ??= fetch(BLUEPRINT_META_URL).then((r) => r.json() as Promise<BlueprintMeta>))
}

export function useBlueprintMeta(): BlueprintMeta | null {
  const [meta, setMeta] = useState<BlueprintMeta | null>(null)
  useEffect(() => {
    loadBlueprintMeta().then(setMeta).catch(() => setMeta(null))
  }, [])
  return meta
}

/** La pianta SVG rasterizzata in una texture grande (le linee restano nitide anche da vicino). */
function useBlueprintTexture(): CanvasTexture | null {
  const [tex, setTex] = useState<CanvasTexture | null>(null)
  useEffect(() => {
    let alive = true
    const img = new Image()
    img.onload = () => {
      if (!alive) return
      const W = 4096
      const H = Math.round((W * 42) / 59.4)
      const c = document.createElement('canvas')
      c.width = W
      c.height = H
      c.getContext('2d')!.drawImage(img, 0, 0, W, H)
      const t = new CanvasTexture(c)
      t.colorSpace = SRGBColorSpace
      t.anisotropy = 8
      setTex(t)
    }
    img.src = BLUEPRINT_URL
    return () => {
      alive = false
    }
  }, [])
  return tex
}

/**
 * Regia 3D dell'intro: foglio della pianta a terra, proiezione del foglio sullo schermo (per l'overlay HTML),
 * estrusione dei muri, arredi che «spuntano» reparto per reparto, postazioni che atterrano, giro di camera.
 */
export function BlueprintBuild() {
  const phase = useIntro((s) => s.phase)
  const meta = useBlueprintMeta()
  const tex = useBlueprintTexture()
  const office = useGLTF(OFFICE).scene
  const controls = useThree((s) => s.controls) as unknown as CameraControls | null
  const mat = useMemo(() => new MeshBasicMaterial({ transparent: true, toneMapped: false, depthWrite: false }), [])
  const v = useMemo(() => new Vector3(), [])
  const cam = useRef({ out: false })
  const slabs = useRef<Record<string, Group | null>>({})

  // Arredi fissi del modello (decor:<reparto>:NN): spuntano con un piccolo rimbalzo.
  const decor = useMemo(() => {
    const out: { node: Object3D; base: Vector3; k: number }[] = []
    office.traverse((o) => {
      const m = /^decor:([a-z_]+):/.exec(o.name)
      if (!m) return
      const k = Math.max(0, BUILD_ORDER.indexOf(m[1]))
      out.push({ node: o, base: (o.userData.baseScale as Vector3 | undefined) ?? o.scale.clone(), k })
      o.userData.baseScale = out[out.length - 1].base
    })
    return out
  }, [office])

  useEffect(() => {
    mat.map = tex
    mat.needsUpdate = true
  }, [tex, mat])

  // Fine dell'intro: tutto al suo posto (anche se si salta).
  useEffect(() => {
    if (phase !== 'done') return
    if (buildGroups.walls) buildGroups.walls.scale.set(1, 1, 1)
    for (const g of Object.values(buildGroups.rooms)) {
      if (!g) continue
      g.position.set(0, 0, 0)
      g.scale.setScalar(1)
    }
    for (const d of decor) d.node.scale.copy(d.base)
    cam.current.out = false
  }, [phase, decor])

  useFrame(({ camera, size }) => {
    const { phase, t0, setPaper, next } = useIntro.getState()
    if (phase === 'done' || !meta) return
    const p = meta.paper

    // Foglio sullo schermo (la camera della pianta guarda dritto in basso).
    if (phase !== 'build') {
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
      for (const [x, z] of [[p.x, p.z], [p.x + p.w, p.z], [p.x, p.z + p.h], [p.x + p.w, p.z + p.h]]) {
        v.set(x, PAPER_Y, z).project(camera)
        const sx = ((v.x + 1) / 2) * size.width
        const sy = ((1 - v.y) / 2) * size.height
        x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy)
      }
      setPaper({ left: x0, top: y0, width: x1 - x0, height: y1 - y0 })
    }

    const t = phase === 'build' ? (performance.now() - t0) / 1000 : 0

    // Muri: estrusione dal foglio (scala in altezza dell'edificio intero, basamento compreso).
    if (buildGroups.walls) buildGroups.walls.scale.y = Math.max(0.002, easeInOut(ramp(t, 0.55, 2.2)))
    mat.opacity = 1 - ramp(t, 1.9, 3.1)

    for (const d of decor) {
      const s = easeOutBack(ramp(t, 1.5 + 0.16 * d.k, 2.05 + 0.16 * d.k))
      d.node.scale.copy(d.base).multiplyScalar(Math.max(0.0001, s))
    }
    // Postazioni: crescono dal pavimento verso l'alto a strati (come una stampa 3D), con il piano di costruzione luminoso.
    BUILD_ORDER.forEach((room, k) => {
      const g = buildGroups.rooms[room]
      if (!g) return
      const r = ramp(t, 2.0 + 0.22 * k, 3.3 + 0.22 * k)
      const s = Math.ceil(r * LAYERS) / LAYERS
      g.position.y = 0
      g.scale.set(1, Math.max(0.0001, s), 1)
      const slab = slabs.current[room]
      if (slab) {
        slab.visible = r > 0 && r < 1
        slab.position.y = s * SEAT_H + 0.01
      }
    })

    // Camera: dalla pianta a un'assonometria dell'intero ufficio e ritorno (lo gestisce CameraRig a fine intro).
    if (phase === 'build' && controls) {
      const b = meta.building
      const cx = (b.minX + b.maxX) / 2
      const cz = (b.minZ + b.maxZ) / 2
      if (!cam.current.out && t > 0.1) {
        cam.current.out = true
        controls.smoothTime = 1.4
        const dir = new Vector3(0.55, 1, 0.95).normalize()
        const d = 96
        controls.setLookAt(cx + dir.x * d, dir.y * d, cz + dir.z * d, cx, 0, cz + 1, true)
      }
      if (t > BUILD_S) {
        controls.smoothTime = 0.9
        next('done')
      }
    }
  })

  if (phase === 'done' || !meta) return null
  const p = meta.paper
  return (
    <>
      <mesh material={mat} position={[p.x + p.w / 2, PAPER_Y, p.z + p.h / 2]} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null} renderOrder={2}>
        <planeGeometry args={[p.w, p.h]} />
      </mesh>
      {BUILD_ORDER.filter((r) => meta.rooms[r]).map((r) => {
        const [x0, z0] = meta.rooms[r].min
        const [x1, z1] = meta.rooms[r].max
        const w = x1 - x0 - 0.3
        const d = z1 - z0 - 0.3
        return (
          <group key={r} ref={(g) => void (slabs.current[r] = g)} position={[(x0 + x1) / 2, 0, (z0 + z1) / 2]} visible={false}>
            <mesh material={slabMaterial} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null} renderOrder={3}>
              <planeGeometry args={[w, d]} />
            </mesh>
            {/* Bordo del piano: quattro listelli sottili. */}
            {[[0, -d / 2, w, 0.06], [0, d / 2, w, 0.06], [-w / 2, 0, 0.06, d], [w / 2, 0, 0.06, d]].map(([x, z, a, b], i) => (
              <mesh key={i} material={slabEdge} position={[x, 0.002, z]} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null} renderOrder={3}>
                <planeGeometry args={[a, b]} />
              </mesh>
            ))}
          </group>
        )
      })}
    </>
  )
}
