import type { LocationId } from '../data/types'

export type Vec3 = [number, number, number]

/** Stanze dell'ufficio di Basilea: centro (x, z) e dimensioni (w, d). Pianta 16 × 10. */
export const ROOMS: Record<string, { x: number; z: number; w: number; d: number }> = {
  consulting: { x: -4.5, z: 2.5, w: 7, d: 5 },
  sales: { x: 1.25, z: 2.5, w: 4.5, d: 5 },
  management: { x: 5.75, z: 2.5, w: 4.5, d: 5 },
  finance: { x: -6, z: -2.5, w: 4, d: 5 },
  marketing: { x: -2, z: -2.5, w: 4, d: 5 },
  hr: { x: 1.5, z: -2.5, w: 3, d: 5 },
  it: { x: 5.5, z: -2.5, w: 5, d: 5 },
}

export const OFFICE_SIZE = { w: 16, d: 10 }

/** Punto da cui partono i cavi: l'armadio rack nella stanza IT. */
export const CABLE_ORIGIN: Vec3 = [7.2, 2.2, -4.3]

/** Isole dei data center, ad arco dietro l'ufficio (leggibili con la camera isometrica e i pannelli laterali). */
export const ISLANDS: Record<LocationId, { pos: Vec3; radius: number; flag: string; city: string }> = {
  IE: { pos: [-15.5, 1.6, 2.5], radius: 4.2, flag: '🇮🇪', city: 'Dublino' },
  DE: { pos: [-14.5, 2.4, -8.5], radius: 3.4, flag: '🇩🇪', city: 'Francoforte' },
  CH: { pos: [-6.5, 1.4, -15], radius: 4.6, flag: '🇨🇭', city: 'Zurigo' },
  EU: { pos: [4, 4.2, -16], radius: 3.8, flag: '🇪🇺', city: 'UE (mista)' },
}

/** Posizioni libere su un'isola (offset x, z dal centro). */
const SLOTS: [number, number][] = [
  [-1.6, -1.1],
  [1.6, -1.1],
  [-1.6, 1.5],
  [1.6, 1.5],
  [0, 0.2],
  [0, -2.6],
  [-3, 0.2],
  [3, 0.2],
]

export function slotPosition(loc: LocationId, index: number, islandTop = 0.35): Vec3 {
  const isl = ISLANDS[loc]
  const [ox, oz] = SLOTS[index % SLOTS.length]
  const k = Math.min(1, isl.radius / 4.4)
  return [isl.pos[0] + ox * k, isl.pos[1] + islandTop, isl.pos[2] + oz * k]
}
