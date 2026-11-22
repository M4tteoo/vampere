import { create } from 'zustand'
import type { Dataset, MetricKey } from './data/types'
import { useIntro } from './intro/store'

/** Durante l'intro «planimetria → 3D» la scena non risponde a clic e hover. */
const intro = () => useIntro.getState().phase !== 'done'

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
  /** Passo 4: ferma la simulazione sul mese mostrato, oppure la fa ripartire da lì. */
  pause: () => void
  resume: () => void
  tick: () => void
  setMonth: (m: number | null) => void
  showMeasures: boolean
  setShowMeasures: (v: boolean) => void
  /** Obiettivo del pacchetto (climate_first, best_value, francs_first). null = quello predefinito del backend. */
  goal: string | null
  setGoal: (g: string) => void
  /** Passo 3 (human in the loop): misure del pacchetto tolte a mano. Si azzerano cambiando pacchetto. */
  dropped: string[]
  toggleDropped: (id: string) => void
  /** Passo 3: misura aperta (si vede il reparto o l'isola che tocca) e confronto senza/con lei. */
  focus: string | null
  setFocus: (id: string | null, room?: string | null) => void
  compareBefore: boolean
  /** Passi 2–4: CO₂ della rete del luogo (location-based, quello del caso) oppure market-based (bonus). */
  co2Basis: 'location' | 'market'
  /** Report «AI in casa» (bonus, solo consultivo) aperto sopra la scena. */
  localAiOpen: boolean
  setLocalAiOpen: (v: boolean) => void
  /** Report «fasce del giorno» (bonus carbon-aware) aperto sopra la scena. */
  hoursOpen: boolean
  /** Passo 4: box dei grafici aperto a destra (al posto della scheda di un oggetto). */
  chartsOpen: boolean
  setChartsOpen: (v: boolean) => void
  setHoursOpen: (v: boolean) => void
  setCo2Basis: (b: 'location' | 'market') => void
  setCompareBefore: (v: boolean) => void
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
  // Cambiando passo si resta dove si è (pianta o reparto): cambia solo cosa mostra la scena.
  setStep: (step) =>
    set((s) => ({
      step,
      // Previsione: solo le isole, niente reparto (tornando agli altri passi si riparte dalla pianta).
      room: step === 'forecast' ? null : s.room,
      stage: 'office',
      turns: { office: 0, cloud: 0 },
      selectedId: null,
      focus: null,
      compareBefore: false,
      chartsOpen: false,
      hoverId: null,
      // La previsione parte da sola; la baseline mostra subito l'anno intero (la crescita si guarda con un bottone).
      month: step === 'forecast' ? 0 : null,
      playing: step === 'forecast',
    })),
  month: null,
  playing: false,
  simDone: false,
  play: () => set({ month: 0, playing: true, selectedId: null }),
  pause: () => set({ playing: false }),
  resume: () => set((s) => ({ playing: true, month: s.month === null || s.month >= 11 ? 0 : s.month })),
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
  setGoal: (goal) => set((s) => (s.goal === goal ? s : { goal, dropped: [], focus: null, compareBefore: false })),
  dropped: [],
  toggleDropped: (id) => set((s) => ({ dropped: s.dropped.includes(id) ? s.dropped.filter((x) => x !== id) : [...s.dropped, id] })),
  focus: null,
  // Aprendo una misura si va al reparto che la riguarda (se c'è); richiudendola si resta dove si è.
  setFocus: (focus, room) =>
    set((s) => ({
      focus,
      compareBefore: false,
      selectedId: null,
      ...(focus && room !== undefined && room !== s.room ? { room, turns: { office: 0, cloud: 0 }, stage: 'office' as const, hoverId: null } : {}),
    })),
  chartsOpen: false,
  // Aprendo i grafici si chiude la scheda dell'oggetto (stesso posto a destra), e viceversa.
  setChartsOpen: (chartsOpen) => set(chartsOpen ? { chartsOpen, selectedId: null } : { chartsOpen }),
  hoursOpen: false,
  setHoursOpen: (hoursOpen) => set({ hoursOpen }),
  localAiOpen: false,
  setLocalAiOpen: (localAiOpen) => set({ localAiOpen }),
  co2Basis: 'location',
  setCo2Basis: (co2Basis) => set({ co2Basis }),
  compareBefore: false,
  setCompareBefore: (compareBefore) => set({ compareBefore }),
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
  setRoom: (room) => intro() || set({ room, turns: { office: 0, cloud: 0 }, stage: 'office', selectedId: null, hoverId: null }),
  // Passo 1: gira solo l'oggetto in primo piano. Passi 2–4 (reparto e isole affiancati): girano insieme.
  turn: (dir) =>
    set((s) =>
      s.step === 'allocation' || s.step === 'local_ai'
        ? { turns: { ...s.turns, [s.stage]: s.turns[s.stage] + dir } }
        : { turns: { office: s.turns.office + dir, cloud: s.turns.cloud + dir } },
    ),
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
  // Passo 3: niente schede a destra (le misure sono nel pannello a sinistra), quindi niente selezione.
  select: (selectedId) => intro() || (selectedId && get().step === 'packages' && get().data?.extra ? undefined : set(selectedId ? { selectedId, chartsOpen: false } : { selectedId })),
  hover: (hoverId) => (intro() || get().hoverId === hoverId ? undefined : set({ hoverId })),
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
