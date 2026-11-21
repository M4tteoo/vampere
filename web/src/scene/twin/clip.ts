import { FrontSide, MeshStandardMaterial, Plane, Vector3 } from 'three'

/** Ritaglio del reparto selezionato: i piani tengono DENTRO il riquadro (oggetti a colori)… */
export const focusPlanes = [new Plane(new Vector3(1, 0, 0), 1e4), new Plane(new Vector3(-1, 0, 0), 1e4), new Plane(new Vector3(0, 0, 1), 1e4), new Plane(new Vector3(0, 0, -1), 1e4)]
/** …e questi tengono FUORI dal riquadro (il resto dell'ufficio, come fantasma). */
export const ghostPlanes = focusPlanes.map((p) => p.clone().negate())

export interface Box2 {
  minX: number
  maxX: number
  minZ: number
  maxZ: number
}

export function setClipBox(b: Box2) {
  focusPlanes[0].constant = -b.minX
  focusPlanes[1].constant = b.maxX
  focusPlanes[2].constant = -b.minZ
  focusPlanes[3].constant = b.maxZ
  focusPlanes.forEach((p, i) => ghostPlanes[i].copy(p).negate())
}

/** Materiale unico del «fantasma»: bianco semitrasparente, senza ombre, non cliccabile. */
export const ghostMaterial = new MeshStandardMaterial({
  color: '#E9E5DE',
  roughness: 1,
  transparent: true,
  opacity: 0,
  depthWrite: false,
  clippingPlanes: ghostPlanes,
  clipIntersection: true,
  side: FrontSide,
})
