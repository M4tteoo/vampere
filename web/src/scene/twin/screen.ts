import { create } from 'zustand'

/** Posizioni sullo schermo (px) dei punti che hanno una scritta HTML: aggiornate dalla scena a ogni frame. */
interface ScreenState {
  points: Record<string, [number, number]>
  set: (p: Record<string, [number, number]>) => void
}

export const useScreen = create<ScreenState>((set, get) => ({
  points: {},
  set: (points) => {
    const old = get().points
    const keys = Object.keys(points)
    // Aggiorna solo se qualcosa si è mosso di almeno 1 px, per non ridisegnare la UI a vuoto.
    const same = keys.length === Object.keys(old).length && keys.every((k) => old[k] && Math.abs(old[k][0] - points[k][0]) < 1 && Math.abs(old[k][1] - points[k][1]) < 1)
    if (!same) set({ points })
  },
}))
