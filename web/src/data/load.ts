import type { Dataset } from './types'
import { loadReal } from './real'

/** Dati veri del backend in public/data/real/ (copiati da output/ con scripts/sync-backend.sh); se mancano, i mock in public/data/. */
const BASE = `${import.meta.env.BASE_URL}data`

async function get<T>(name: string): Promise<T> {
  const res = await fetch(`${BASE}/${name}.json`)
  if (!res.ok) throw new Error(`Could not load ${name}.json (${res.status})`)
  return res.json() as Promise<T>
}

export async function loadDataset(): Promise<Dataset> {
  const [items, layout] = await Promise.all([
    get<Dataset['items']>('items').catch(() => []),
    fetch(`${import.meta.env.BASE_URL}models/layout.json`).then((r) => (r.ok ? (r.json() as Promise<Dataset['layout']>) : [])),
  ])
  // ?mock forza i dati finti (utile per confronti).
  if (!new URLSearchParams(window.location.search).has('mock')) {
    const real = await loadReal(`${BASE}/real`, items, layout)
    if (real) return real
  }
  const [summary, entities, measures, limits, findings, quality] = await Promise.all([
    get<Dataset['summary']>('summary'),
    get<Dataset['entities']>('entities'),
    get<Dataset['measures']>('measures'),
    get<Dataset['limits']>('limits'),
    get<Dataset['findings']>('findings'),
    get<Dataset['quality']>('quality'),
  ])
  return { summary, entities, measures, limits, findings, quality, items, layout }
}
