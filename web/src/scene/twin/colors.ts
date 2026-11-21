import type { Visual } from '../../data/twin'

/** Colori «di stato» di schermi, LED e luci (sono gli unici elementi che cambiano colore nella scena). */
export const SCREEN: Record<Visual, string> = {
  ok: '#CFEBDB',
  driver: '#CFEBDB',
  idle: '#D4E2EC',
  waste: '#F5B65E',
  reduced: '#A6DDBD',
  off: '#2C3036',
  removed: '#2C3036',
  locked: '#B4C3DA',
  human: '#AFC9F3',
  contradiction: '#F2D274',
}

export const LED: Record<Visual, string> = {
  ok: '#37C27A',
  driver: '#37C27A',
  idle: '#9AA3AD',
  waste: '#F59A2C',
  reduced: '#7FDCA6',
  off: '#4A4F57',
  removed: '#4A4F57',
  locked: '#6F8FBF',
  human: '#4C8DF6',
  contradiction: '#F2C230',
}

export const GLOW: Record<Visual, string> = {
  ok: '#BDEBD2',
  driver: '#BDEBD2',
  idle: '#D9E4EC',
  waste: '#F8B36A',
  reduced: '#A8E6C4',
  off: '#5A6068',
  removed: '#5A6068',
  locked: '#B4C3DA',
  human: '#AFC9F3',
  contradiction: '#F2D274',
}

/** Giorni protetti sui calendari a muro. */
export const DAYS = '#E07A5F'

/** Intensità della rete (kg CO₂/kWh): verde → giallo → terracotta. */
export function gridColor(kg: number): string {
  if (kg < 0.15) return '#4DB37E'
  if (kg < 0.27) return '#E2B53E'
  if (kg < 0.33) return '#E8925A'
  return '#D9674A'
}

/** Colore del fornitore cloud sulle parti «provider» dell'hardware (fascia sul rack, piattaforma sull'isola). */
export const PROVIDER: Record<string, string> = { Azure: '#5B8FC7', AWS: '#E3A445', 'Swiss hoster': '#C9605A' }
