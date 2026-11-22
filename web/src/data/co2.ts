// Due modi di contare la CO₂ (bonus del caso): location-based (rete del luogo, il numero di riferimento) e market-based
// (stessi kWh, fattore del «residual mix» AIB: nessun certificato verde comprato). Qui il rapporto fra i due per sede,
// così ogni numero di CO₂ della UI si converte allo stesso modo.
import { useMemo } from 'react'
import { useApp } from '../store'
import type { Ctx } from './twin'
import type { Extra, XMeasure } from './extra'
import type { Metrics } from './types'
import { deptUnits, sum, unitDiv, unitMonthly } from './usage'

const LOCS = ['CH', 'DE', 'IE', 'EU']

/** Rapporto market / location per sede: fattore market × kWh ÷ CO₂ location dell'anno di baseline. */
export function marketRatios(x: Extra): Record<string, number> {
  const out: Record<string, number> = {}
  for (const l of LOCS) {
    const s = x.series.get(`loc:${l}`)
    const f = x.market?.factor[l]
    const co2 = s ? sum(s.co2_kg) : 0
    out[l] = s && f !== undefined && co2 > 0 ? (f * sum(s.kwh)) / co2 : 1
  }
  return out
}

export function locOfRaw(x: Extra, raw: string): string {
  const r = x.raw.get(raw)
  return r?.location ?? (r?.parent ? (x.raw.get(r.parent)?.location ?? 'EU') : 'EU')
}

/** Sede di un'unità della scena: i computer usano software e AI nel cloud europeo; una risorsa ha la sua sede. */
export function locOfUnit(ctx: Ctx, unit: string): string {
  if (unit.startsWith('pcs:')) return 'EU'
  const l = ctx.entities.get(unit)?.entity.location
  return l && LOCS.includes(l) ? l : 'EU'
}

export interface Co2View {
  market: boolean
  /** Fattore da applicare alla CO₂ location-based di una sede, di un id del backend, di un'unità, dell'azienda. */
  loc: (l: string) => number
  raw: (id: string) => number
  unit: (u: string) => number
  company: number
  /** Fattore di un reparto (media dei suoi computer e delle risorse che usa, pesata sulla CO₂). */
  dept: (room: string) => number
  /** Risparmio di CO₂ di una misura in questa vista (market-based: valore del backend, se c'è). */
  measure: (m: XMeasure) => number
  /** Risparmi per id del backend con la CO₂ convertita. */
  saved: (s: Map<string, Metrics>) => Map<string, Metrics>
}

export function useCo2(ctx: Ctx): Co2View {
  const x = useApp((s) => s.data?.extra ?? null)
  const on = useApp((s) => s.co2Basis === 'market' && (s.step === 'baseline' || s.step === 'packages' || s.step === 'forecast'))
  return useMemo<Co2View>(() => {
    const market = on && !!x?.market
    const r = x && market ? marketRatios(x) : {}
    const loc = (l: string) => (market ? (r[l] ?? 1) : 1)
    const unit = (u: string) => loc(locOfUnit(ctx, u))
    let company = 1
    if (x && market) {
      let a = 0
      let b = 0
      for (const l of LOCS) {
        const c = sum(x.series.get(`loc:${l}`)?.co2_kg ?? [])
        a += c * loc(l)
        b += c
      }
      company = b > 0 ? a / b : 1
    }
    const dept = (room: string) => {
      if (!market || !x) return 1
      let a = 0
      let b = 0
      for (const u of deptUnits(ctx, room)) {
        const c = sum(unitMonthly(ctx, x, u, 'co2_kg')) * unitDiv(ctx, u)
        a += c * unit(u)
        b += c
      }
      return b > 0 ? a / b : 1
    }
    return {
      market,
      loc,
      raw: (id) => (x ? loc(locOfRaw(x, id)) : 1),
      unit,
      company,
      dept,
      measure: (m) => (market ? (x?.market?.measureCo2[m.id] ?? m.savings.co2_kg * company) : m.savings.co2_kg),
      saved: (s) => {
        if (!market || !x) return s
        const out = new Map<string, Metrics>()
        for (const [id, m] of s) out.set(id, { ...m, co2_kg: m.co2_kg * loc(locOfRaw(x, id)) })
        return out
      },
    }
  }, [on, x, ctx])
}
