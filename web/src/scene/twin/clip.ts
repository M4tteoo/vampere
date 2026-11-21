import { FrontSide, Matrix4, MeshStandardMaterial, Plane, Vector3 } from 'three'

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

const local = [new Plane(new Vector3(1, 0, 0), 0), new Plane(new Vector3(-1, 0, 0), 0), new Plane(new Vector3(0, 0, 1), 0), new Plane(new Vector3(0, 0, -1), 0)]

/** Riquadro del reparto in coordinate dell'ufficio; `matrix` = trasformazione del gruppo ufficio (che può spostarsi e rimpicciolirsi). */
export function setClipBox(b: Box2, matrix?: Matrix4) {
  local[0].constant = -b.minX
  local[1].constant = b.maxX
  local[2].constant = -b.minZ
  local[3].constant = b.maxZ
  local.forEach((p, i) => {
    focusPlanes[i].copy(p)
    if (matrix) focusPlanes[i].applyMatrix4(matrix)
    ghostPlanes[i].copy(focusPlanes[i]).negate()
  })
}

/** Fantasma per l'hardware delle isole non usato dal reparto (senza ritaglio). */
export const islandGhostMaterial = new MeshStandardMaterial({ color: '#D9D6D0', roughness: 1, transparent: true, opacity: 0.35, depthWrite: false })

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
