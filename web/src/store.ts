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
/** Passi della demo: 1 chi usa cosa (allocazione + impronta), 2 anno di baseline e punti critici (+ misure), 3 pacchetti, 4 previsione. */
export type Step = 'allocation' | 'baseline' | 'packages' | 'forecast' | 'local_ai'
export type ColorBy = 'co2_kg' | 'cost_chf' | 'cluster'

interface AppState {
  step: Step
  setStep: (step: Step) => void
  /** Simulazione mese per mese (passi 2 e 4): mese mostrato (0–11) oppure null = anno intero. */
  month: number | null
  playing: boolean
  /** La simulazione della baseline è finita almeno una volta: si sbloccano le misure e i passi dopo. */
  simDone: boolean
  play: () => void
  tick: () => void
  setMonth: (m: number | null) => void
  showMeasures: boolean
  setShowMeasures: (v: boolean) => void
  /** Obiettivo del pacchetto (climate_first, best_value, francs_first). null = quello predefinito del backend. */
  goal: string | null
  setGoal: (g: string) => void
  colorBy: ColorBy
  setColorBy: (c: ColorBy) => void
  /** Passo 4: la mappa mostra il futuro con il pacchetto (true) o senza. */
  withPackage: boolean
  setWithPackage: (v: boolean) => void
  chatOpen: boolean
  setChatOpen: (v: boolean) => void
  /** Reparto isolato nella vista isometrica (null = pianta dall'alto). */
  room: string | null
  /** Mezzi giri di ciascun palco (frecce ← →): si gira solo l'oggetto in primo piano. Si accumulano. */
  turns: { office: number; cloud: number }
  /** Nel reparto: in primo piano il software e i servizi (ufficio) oppure l'infrastruttura cloud (isole). */
  stage: 'office' | 'cloud'
  setStage: (stage: 'office' | 'cloud') => void
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
  setStep: (step) =>
    set((s) => ({
      step,
      room: null,
      stage: 'office',
      turns: { office: 0, cloud: 0 },
      selectedId: null,
      hoverId: null,
      // La baseline parte da sola la prima volta; la previsione ogni volta.
      month: (step === 'baseline' && !s.simDone) || step === 'forecast' ? 0 : null,
      playing: (step === 'baseline' && !s.simDone) || step === 'forecast',
    })),
  month: null,
  playing: false,
  simDone: false,
  play: () => set({ month: 0, playing: true, selectedId: null }),
  tick: () =>
    set((s) => {
      const m = (s.month ?? -1) + 1
      if (m <= 11) return { month: m }
      return s.step === 'baseline' ? { month: null, playing: false, simDone: true } : { month: 11, playing: false }
    }),
  setMonth: (month) => set({ month, playing: false }),
  showMeasures: false,
  setShowMeasures: (showMeasures) => set({ showMeasures }),
  goal: null,
  setGoal: (goal) => set({ goal }),
  colorBy: 'co2_kg',
  setColorBy: (colorBy) => set({ colorBy }),
  withPackage: true,
  setWithPackage: (withPackage) => set({ withPackage }),
  chatOpen: false,
  setChatOpen: (chatOpen) => set({ chatOpen }),
  room: null,
  turns: { office: 0, cloud: 0 },
  stage: 'office',
  setStage: (stage) => set({ stage, selectedId: null, hoverId: null }),
  setRoom: (room) => set({ room, turns: { office: 0, cloud: 0 }, stage: 'office', selectedId: null, hoverId: null }),
  turn: (dir) => set((s) => ({ turns: { ...s.turns, [s.stage]: s.turns[s.stage] + dir } })),
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
