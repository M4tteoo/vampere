import { Color } from 'three'

/** Palette «clay» pastello, stile Airbnb. */
export const P = {
  ground: '#efe6da',
  floor: '#f6efe6',
  wall: '#fbf8f4',
  wallTop: '#e9dccb',
  desk: '#e8d2b8',
  deskSide: '#d6bd9f',
  chair: '#8fb8a8',
  monitorOn: '#bfe3ff',
  monitorGhost: '#ffb37c',
  skin: ['#f2c7a5', '#d9a07b', '#a86f4c', '#f5d5bd'],
  shirt: ['#7fa7d9', '#f28b82', '#a7d7c5', '#f7c873', '#b39ddb', '#90caf9'],
  rack: '#5d6472',
  rackLight: '#79808e',
  ledOk: '#7ee0b5',
  ledWaste: '#ff9f5a',
  ledOff: '#8f949c',
  gpu: '#9b87f5',
  storage: '#c9d3df',
  ai: '#c3b5ff',
  card: '#ffffff',
  rock: '#c9b59c',
  rockDark: '#b39d82',
  cloud: '#a8b0ba',
  coral: '#ff5a5f',
  select: '#ff5a5f',
} as const

const LOW = new Color('#8fdcbf') // rete pulita
const MID = new Color('#ffd08a')
const HIGH = new Color('#ff8a80') // rete sporca

/** Colore dell'isola in base ai kg CO₂/kWh della rete (0,03 → menta, 0,4 → corallo). */
export function gridColor(kgPerKwh: number): string {
  const t = Math.min(1, Math.max(0, (kgPerKwh - 0.03) / (0.4 - 0.03)))
  const c = t < 0.5 ? LOW.clone().lerp(MID, t * 2) : MID.clone().lerp(HIGH, (t - 0.5) * 2)
  return `#${c.getHexString()}`
}

/** Tinta di una stanza in base alla quota della metrica (0–1). */
export function heatColor(share: number): string {
  const base = new Color(P.floor)
  const hot = new Color('#ffc2a8')
  return `#${base.lerp(hot, Math.min(1, share * 1.6)).getHexString()}`
}
