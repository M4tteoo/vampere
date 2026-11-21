import { useApp } from '../store'
import { fmtChf, packageTotals } from '../data/compute'

/** La «barra di ricerca» di Airbnb diventa il riepilogo del pacchetto: CO₂ · costi · budget + pulsante tondo. */
export function SummaryPill() {
  const data = useApp((s) => s.data)!
  const active = useApp((s) => s.active)
  const apply = useApp((s) => s.applyRecommended)
  const reset = useApp((s) => s.reset)
  const setMode = useApp((s) => s.setMode)
  const t = packageTotals(data, active)
  const { target } = data.summary
  const any = active.length > 0

  return (
    <div className="pill-shadow pointer-events-auto flex h-16 items-center rounded-full bg-white pr-2 pl-2">
      <Segment
        label="CO₂ location-based"
        value={any ? `−${Math.round(t.co2Pct * 100)}%` : '—'}
        target={`target −${Math.round(target.co2_reduction * 100)}%`}
        ok={t.co2Ok}
        onClick={() => setMode('decide')}
      />
      <Sep />
      <Segment
        label="Costi"
        value={any ? `−${Math.round(t.costPct * 100)}%` : '—'}
        target={`target −${Math.round(target.cost_reduction * 100)}%`}
        ok={t.costOk}
        onClick={() => setMode('decide')}
      />
      <Sep />
      <Segment
        label="Budget"
        value={any ? fmtChf(t.effortChf) : 'CHF 0'}
        target={`${t.effortDays} di ${target.budget_chf / target.day_rate_chf} giornate`}
        ok={any && t.budgetOk}
        bad={!t.budgetOk}
        onClick={() => setMode('decide')}
      />
      <button
        onClick={() => {
          if (any) reset()
          else {
            apply()
            setMode('decide')
          }
        }}
        title={any ? 'Azzera le misure' : 'Applica il pacchetto consigliato'}
        className="ml-2 flex h-12 items-center gap-2 rounded-full bg-primary px-4 text-[14px] font-medium text-white transition hover:bg-primary-active active:scale-95"
      >
        {any ? (
          <>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" />
            </svg>
            Azzera
          </>
        ) : (
          <>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
              <path d="M5 12.5l4.5 4.5L19 7.5" />
            </svg>
            Pacchetto consigliato
          </>
        )}
      </button>
    </div>
  )
}

function Segment({ label, value, target, ok, bad, onClick }: { label: string; value: string; target: string; ok: boolean; bad?: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex h-full flex-col justify-center rounded-full px-6 text-left transition hover:bg-surface-soft">
      <span className="text-[12px] font-semibold text-ink">{label}</span>
      <span className="flex items-baseline gap-2">
        <span className={`text-[18px] font-semibold tabular-nums ${bad ? 'text-error' : ok ? 'text-primary' : 'text-ink'}`}>{value}</span>
        <span className="text-[12px] text-muted">
          {ok && '✓ '}
          {target}
        </span>
      </span>
    </button>
  )
}

function Sep() {
  return <span className="h-8 w-px bg-hairline" />
}
