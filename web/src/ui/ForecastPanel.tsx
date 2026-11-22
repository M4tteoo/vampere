import { useMemo, useState } from 'react'
import { useApp } from '../store'
import { fmtMetric } from '../data/compute'
import type { Ctx } from '../data/twin'
import type { Extra } from '../data/extra'
import type { MetricKey } from '../data/types'
import { GOAL_LABEL, measuresOf, unitParts } from '../data/usage'
import { forecastParts, forecastPlan, goalOf, planIds } from '../data/plan'
import { useCo2 } from '../data/co2'

const MON = (iso: string, opts: Intl.DateTimeFormatOptions = { month: 'short' }) => new Date(iso).toLocaleDateString('en-GB', opts)

/**
 * Passo 4, scheda di un oggetto: come cambia mese per mese. Grafico senza/con il pacchetto (il mese della simulazione
 * evidenziato), poi in ordine di tempo cosa lo fa cambiare: misure che partono ed eventi già noti.
 */
export function ForecastUnitBody({ ctx, x, unit }: { ctx: Ctx; x: Extra; unit: string }) {
  const goalSel = useApp((s) => s.goal)
  const dropped = useApp((s) => s.dropped)
  const month = useApp((s) => s.month)
  const withPackage = useApp((s) => s.withPackage)
  const setMonth = useApp((s) => s.setMonth)
  const [k, setK] = useState<MetricKey>('co2_kg')
  const cv = useCo2(ctx)
  const goal = goalOf(x, goalSel)
  const fm = useMemo(() => forecastPlan(ctx, x, goal, dropped), [ctx, x, goal, dropped])

  // Risorse della previsione che compongono l'unità (id senza «res:») e fattore della CO₂ nella vista scelta.
  const ids = useMemo(() => forecastParts(x, unitParts(ctx, unit)), [ctx, x, unit])
  const r = k === 'co2_kg' ? cv.unit(unit) : 1
  const series = fm.map((m) => {
    let wo = 0
    let w = 0
    for (const { id, w: f } of ids) {
      wo += (m.res[id]?.without[k] ?? 0) * f
      w += (m.res[id]?.with[k] ?? 0) * f
    }
    return { month: m.month, without: wo * r, with: w * r }
  })
  if (!ids.length || !series.some((s) => s.without > 0)) return <p className="text-[13px] text-muted">This item has no forecast of its own: it is part of a shared service.</p>

  // Cosa cambia e quando: misure del piano che toccano l'oggetto (dal mese in cui partono) ed eventi noti.
  const plan = new Set(planIds(x, goal, dropped))
  const starts = measuresOf(ctx, x, unit)
    .filter((m) => plan.has(m.id))
    .map((m) => {
      const i = Math.max(
        0,
        series.findIndex((s) => s.month >= (m.start_date || '')),
      )
      const cut = series[i] ? series[i].without - series[i].with : 0
      return { date: series[i]?.month ?? m.start_date, text: `«${m.title}» starts`, detail: cut > 0 ? `−${fmtMetric(cut, k)} a month from here` : 'Takes effect from here', kind: 'measure' as const }
    })
  const events = (x.forecast?.events ?? [])
    .filter((e) => ids.some(({ id }) => id === e.resource_id))
    .map((e) => ({ date: e.date, text: e.label, detail: `Known change (${e.source})`, kind: 'event' as const }))
  const timeline = [...starts, ...events].sort((a, b) => a.date.localeCompare(b.date))

  const max = Math.max(...series.map((s) => Math.max(s.without, s.with))) * 1.1 || 1
  const sum = (key: 'with' | 'without') => series.reduce((a, s) => a + s[key], 0)
  const W = 360
  const H = 170
  const L = 40
  const bw = (W - L - 4) / series.length
  const py = (v: number) => H - 18 - (v / max) * (H - 44)
  // Mese di cui si scrivono i valori sopra le barre: quello della simulazione (a fine anno, l'ultimo).
  const at = month ?? series.length - 1
  const short = (v: number) => fmtMetric(v, k).replace(/\s?(CO₂|kWh)$/, '')

  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex items-center justify-between">
          <h3 className="text-[14px] font-semibold text-ink">Month by month</h3>
          <div className="flex rounded-full bg-surface-soft p-0.5 text-[11px]">
            {(['co2_kg', 'cost_chf'] as MetricKey[]).map((m) => (
              <button key={m} onClick={() => setK(m)} className={`rounded-full px-2.5 py-0.5 font-semibold ${k === m ? 'bg-white text-ink shadow-sm' : 'text-muted'}`}>
                {m === 'co2_kg' ? 'CO₂' : 'Cost'}
              </button>
            ))}
          </div>
        </div>
        {/* Due barre per mese: grigia senza cambiamenti, verde con il pacchetto. Clic su un mese: la simulazione salta lì. */}
        <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full">
          {/* Asse dei valori: zero e il massimo, così le barre si leggono anche senza numeri su ognuna. */}
          <line x1={L} x2={W - 4} y1={py(max / 1.1)} y2={py(max / 1.1)} stroke="#EBEBEB" strokeDasharray="3 3" />
          <text x={L - 4} y={py(max / 1.1) + 3} textAnchor="end" fontSize="9" fill="#8A8A8A">
            {short(max / 1.1)}
          </text>
          <text x={L - 4} y={H - 18} textAnchor="end" fontSize="9" fill="#8A8A8A">
            0
          </text>
          {series.map((s, i) => {
            const x0 = L + i * bw
            const on = at === i
            return (
              <g key={s.month} onClick={() => setMonth(i)} className="cursor-pointer">
                {on && <rect x={x0} y={4} width={bw} height={H - 8} rx={4} fill="#F2F2F2" />}
                <rect x={x0 + bw * 0.16} y={py(s.without)} width={bw * 0.32} height={H - 18 - py(s.without)} rx={1.5} fill="#C9C4BB" />
                <rect x={x0 + bw * 0.52} y={py(s.with)} width={bw * 0.32} height={H - 18 - py(s.with)} rx={1.5} fill={withPackage ? '#1F7A57' : '#9FC8B2'} />
                <text x={x0 + bw / 2} y={H - 5} textAnchor="middle" fontSize="9" fill={on ? '#222222' : '#6A6A6A'} fontWeight={on ? 700 : 400}>
                  {MON(s.month)[0]}
                </text>
                {timeline.some((t) => t.date.slice(0, 7) === s.month.slice(0, 7)) && <circle cx={x0 + bw / 2} cy={8} r={2.5} fill="#222222" />}
                {on && (
                  <>
                    {/* Due righe sopra la barra più alta: grigio senza, verde con (non si sovrappongono mai). */}
                    <text x={x0 + bw / 2} y={Math.min(py(s.without), py(s.with)) - 15} textAnchor="middle" fontSize="9" fontWeight="600" fill="#6A6A6A">
                      {short(s.without)}
                    </text>
                    <text x={x0 + bw / 2} y={Math.min(py(s.without), py(s.with)) - 5} textAnchor="middle" fontSize="9" fontWeight="700" fill="#1F7A57">
                      {short(s.with)}
                    </text>
                  </>
                )}
              </g>
            )
          })}
        </svg>
        <div className="mt-1 flex gap-4 text-[11px] text-muted">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-[2px] bg-[#C9C4BB]" /> without changes
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-[2px] bg-primary" /> with «{GOAL_LABEL[goal] ?? goal}»
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-ink" /> something changes
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-[8px] bg-surface-soft px-2.5 py-1.5">
          <div className="text-[11px] font-medium text-muted">12 months, without changes</div>
          <div className="text-[14px] font-semibold text-ink tabular-nums">{fmtMetric(sum('without'), k)}</div>
        </div>
        <div className="rounded-[8px] bg-surface-soft px-2.5 py-1.5">
          <div className="text-[11px] font-medium text-muted">12 months, with the package</div>
          <div className="text-[14px] font-semibold text-primary tabular-nums">{fmtMetric(sum('with'), k)}</div>
        </div>
        <div className="rounded-[8px] bg-primary/10 px-2.5 py-1.5">
          <div className="text-[11px] font-medium text-muted">Saved by the package</div>
          <div className="text-[14px] font-semibold text-primary tabular-nums">−{fmtMetric(Math.max(0, sum('without') - sum('with')), k)}</div>
        </div>
      </div>

      <section>
        <h3 className="text-[14px] font-semibold text-ink">What changes, and when</h3>
        {!timeline.length && <p className="mt-1 text-[13px] text-muted">No measure or known event: it follows the recent months, with the usual seasonality.</p>}
        <ol className="mt-2 space-y-2.5 border-l border-hairline pl-4">
          {timeline.map((t) => (
            <li key={t.date + t.text} className="relative text-[13px]">
              <span className={`absolute top-1.5 -left-[21px] h-2.5 w-2.5 rounded-full ring-2 ring-white ${t.kind === 'measure' ? 'bg-primary' : 'bg-ink'}`} />
              <div className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">{MON(t.date, { month: 'short', year: 'numeric' })}</div>
              <div className="text-ink">{t.text}</div>
              <div className="text-[12px] text-muted">{t.detail}</div>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-[12px] text-muted">Every other month follows the last three months of use, with growth and seasonality already in the forecast.</p>
      </section>
    </div>
  )
}
