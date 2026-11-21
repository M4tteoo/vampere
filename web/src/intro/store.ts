import { create } from 'zustand'

/**
 * Intro «planimetria → 3D» (puramente scenica): si carica una pianta, il sistema la «legge» e la estrude nel gemello.
 * In realtà la pianta è ricavata dal modello 3D (web/scripts/make-floorplan.py): è reverse engineering della disposizione.
 *
 * upload → scan (vettorizzazione, locali, moduli) → land (il foglio si posa sulla vista dall'alto) → build (estrusione) → done
 */
export type IntroPhase = 'upload' | 'scan' | 'land' | 'build' | 'done'

export const BLUEPRINT_URL = `${import.meta.env.BASE_URL}blueprints/level-01.svg`
export const BLUEPRINT_META_URL = `${import.meta.env.BASE_URL}blueprints/level-01.json`

/** Durate (s) delle fasi animate. */
export const SCAN_S = 6.2
export const LAND_S = 1.1
export const BUILD_S = 5.2

export interface PaperRect {
  left: number
  top: number
  width: number
  height: number
}

export interface BlueprintMeta {
  paper: { x: number; z: number; w: number; h: number }
  building: { minX: number; minZ: number; maxX: number; maxZ: number }
  cut: number
  rooms: Record<string, { min: [number, number]; max: [number, number]; area: number; name: string; no: string }>
  counts: { wall_segments: number; glass_segments: number; workstations: number; furniture: number; axes: number }
}

interface IntroState {
  phase: IntroPhase
  /** performance.now() all'inizio della fase. */
  t0: number
  fileName: string | null
  /** Foglio proiettato sullo schermo dalla camera della pianta (lo scrive la scena 3D). */
  paper: PaperRect | null
  start: (fileName: string) => void
  next: (phase: IntroPhase) => void
  skip: () => void
  replay: () => void
  setPaper: (r: PaperRect) => void
}

const skipped = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('nointro')

export const useIntro = create<IntroState>((set, get) => ({
  phase: skipped ? 'done' : 'upload',
  t0: 0,
  fileName: null,
  paper: null,
  start: (fileName) => set({ phase: 'scan', fileName, t0: performance.now() }),
  next: (phase) => set({ phase, t0: performance.now() }),
  skip: () => set({ phase: 'done', t0: performance.now() }),
  replay: () => set({ phase: 'upload', fileName: null, t0: performance.now() }),
  setPaper: (r) => {
    const p = get().paper
    if (p && Math.abs(p.left - r.left) < 0.5 && Math.abs(p.top - r.top) < 0.5 && Math.abs(p.width - r.width) < 0.5) return
    set({ paper: r })
  },
}))

/** 0→1 fra a e b. */
export const ramp = (t: number, a: number, b: number) => Math.min(1, Math.max(0, (t - a) / (b - a)))
export const easeOut = (x: number) => 1 - Math.pow(1 - x, 3)
export const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
/** Atterraggio con un piccolo rimbalzo. */
export const easeOutBack = (x: number) => {
  const c1 = 1.4
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2)
}
