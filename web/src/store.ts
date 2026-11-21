import { create } from 'zustand'
import type { Dataset, MetricKey } from './data/types'

interface Notice {
  title: string
  text: string
  tone: 'blocked' | 'human' | 'info'
}

/** Le quattro fasi richieste dal caso: Connect → Find → Decide → Know the limits. */
export type Mode = 'connect' | 'find' | 'decide' | 'limits'
export type View = 'overview' | 'office' | 'islands'
export type Decision = 'approved' | 'rejected'

/** Passi della pipeline mostrati nella barra in alto (per ora è attivo solo «allocation»). */
export type Step = 'allocation' | 'footprint' | 'baseline' | 'hotspots' | 'measures' | 'limits' | 'package' | 'export' | 'local_ai'

interface AppState {
  step: Step
  setStep: (step: Step) => void
  /** Reparto isolato nella vista isometrica (null = pianta dall'alto). */
  room: string | null
  /** Mezzi giri della vista isometrica (frecce ← →): +1 = 180° in senso orario, -1 = antiorario. Si accumulano. */
  turns: number
  setRoom: (room: string | null) => void
  turn: (dir: 1 | -1) => void
  data: Dataset | null
  metric: MetricKey
  active: string[]
  /** id di un oggetto della scena, oppure room:<reparto> / loc:<CH|DE|IE|EU>. */
  selectedId: string | null
  hoverId: string | null
  mode: Mode
  view: View
  /** Cambia a ogni richiesta di vista, così la camera si muove anche se la vista è la stessa. */
  viewNonce: number
  tour: number | null
  decisions: Record<string, Decision>
  notice: Notice | null
  setData: (d: Dataset) => void
  setMetric: (m: MetricKey) => void
  setMode: (m: Mode) => void
  setView: (v: View) => void
  toggleMeasure: (id: string) => void
  setActive: (ids: string[]) => void
  applyRecommended: () => void
  reset: () => void
  select: (id: string | null) => void
  hover: (id: string | null) => void
  setTour: (step: number | null) => void
  decide: (measureId: string, d: Decision | null) => void
  dismissNotice: () => void
}

export const useApp = create<AppState>((set, get) => ({
  step: 'allocation',
  setStep: (step) => set({ step }),
  room: null,
  turns: 0,
  setRoom: (room) => set({ room, turns: 0, selectedId: null, hoverId: null }),
  turn: (dir) => set((s) => ({ turns: s.turns + dir })),
  data: null,
  metric: 'co2_kg',
  active: [],
  selectedId: null,
  hoverId: null,
  mode: 'connect',
  view: 'overview',
  viewNonce: 0,
  tour: null,
  decisions: {},
  notice: null,
  setData: (data) => set({ data }),
  setMetric: (metric) => set({ metric }),
  setMode: (mode) => set({ mode }),
  setView: (view) => set((s) => ({ view, selectedId: null, viewNonce: s.viewNonce + 1 })),
  toggleMeasure: (id) => {
    const { data, active } = get()
    const m = data?.measures.find((x) => x.id === id)
    if (!m) return
    if (m.status === 'blocked') {
      // Caso limite: la misura non si applica, il sistema spiega perché e chi decide.
      set({ notice: { title: `Non consigliato: ${m.title}`, text: m.reason ?? 'Misura bloccata.', tone: 'blocked' } })
      return
    }
    const on = active.includes(id)
    set({
      active: on ? active.filter((x) => x !== id) : [...active, id],
      notice:
        !on && m.status === 'human'
          ? { title: `Decide: ${m.owner_role ?? 'una persona'}`, text: m.reason ?? '', tone: 'human' }
          : get().notice,
    })
  },
  setActive: (active) => set({ active }),
  applyRecommended: () => {
    const { data } = get()
    if (!data) return
    set({ active: data.measures.filter((m) => m.recommended && m.status !== 'blocked').map((m) => m.id) })
  },
  reset: () => set({ active: [], notice: null, decisions: {} }),
  select: (selectedId) => set({ selectedId }),
  hover: (hoverId) => (get().hoverId === hoverId ? undefined : set({ hoverId })),
  setTour: (tour) => set({ tour }),
  decide: (measureId, d) =>
    set((s) => {
      const decisions = { ...s.decisions }
      if (d) decisions[measureId] = d
      else delete decisions[measureId]
      // Respinta = la misura esce dal pacchetto.
      const active = d === 'rejected' ? s.active.filter((x) => x !== measureId) : s.active
      return { decisions, active }
    }),
  dismissNotice: () => set({ notice: null }),
}))
