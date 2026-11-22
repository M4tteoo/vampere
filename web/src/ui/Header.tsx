import { useApp, type Step } from '../store'
import { useIntro } from '../intro/store'
import { LOGO_H, LOGO_W, VampereLogo } from './VampereLogo'

/** Passi della demo, nell'ordine in cui li racconta. Misure e limiti stanno dentro il passo 2 (interruttore), l'export nei passi 2 e 3. */
export const STEPS: { id: Step; label: string }[] = [
  { id: 'allocation', label: 'Who uses what' },
  { id: 'baseline', label: 'Baseline & hotspots' },
  { id: 'packages', label: 'Packages' },
  { id: 'forecast', label: 'Next 12 months' },
]

/** Barra in alto: logo a sinistra, i passi numerati in una pillola al centro (stile ricerca di Airbnb, senza icone). */
export function Header() {
  const step = useApp((s) => s.step)
  const setStep = useApp((s) => s.setStep)
  const setRoom = useApp((s) => s.setRoom)
  const simDone = useApp((s) => s.simDone)
  const isMock = useApp((s) => s.data?.summary.is_mock)
  const hasExtra = useApp((s) => !!s.data?.extra)
  const hasLocalAi = useApp((s) => !!s.data?.localAi)
  const landed = useIntro((s) => s.landing === 'done')

  const ready = (id: Step): { ok: boolean; why?: string } => {
    if (id === 'allocation') return { ok: true }
    if (!hasExtra) return { ok: false, why: 'Needs the backend output (timeseries, measures)' }
    if (id === 'baseline') return { ok: true }
    return simDone ? { ok: true } : { ok: false, why: 'Play the baseline year first' }
  }

  return (
    <header className="relative z-40 flex h-[88px] shrink-0 items-center justify-between bg-white px-8">
      <button onClick={() => setRoom(null)} className="flex w-48 items-center" aria-label="Back to the floor plan">
        {/* Qui si posa il logo dell'apertura (intro/Landing.tsx): resta nascosto finché non è atterrato. */}
        <span data-landing-target className="block h-9" style={{ width: (36 * LOGO_W) / LOGO_H, opacity: landed ? 1 : 0 }}>
          <VampereLogo className="block h-full w-full" />
        </span>
      </button>

      <nav className="pill-shadow flex h-16 items-center rounded-full border border-hairline bg-white px-3">
        {STEPS.map((s, i) => {
          const on = s.id === step
          const r = ready(s.id)
          return (
            <div key={s.id} className="flex items-center">
              {i > 0 && <span className="h-7 w-px bg-hairline" />}
              <button
                disabled={!r.ok}
                title={r.why}
                onClick={() => !on && setStep(s.id)}
                className={`flex items-center gap-2 rounded-full px-4 py-3 text-[16px] whitespace-nowrap transition ${
                  on ? 'font-semibold text-ink' : r.ok ? 'font-medium text-ink hover:bg-surface-soft' : 'font-medium text-muted-soft'
                }`}
              >
                <span
                  className={`grid h-6 w-6 place-items-center rounded-full text-[12px] font-semibold ${on ? 'bg-ink text-white' : r.ok ? 'bg-surface-strong text-ink' : 'bg-surface-soft text-muted-soft'}`}
                >
                  {i + 1}
                </span>
                {s.label}
              </button>
            </div>
          )
        })}
      </nav>

      <div className="flex w-48 items-center justify-end gap-2">
        <button
          onClick={() => {
            // L'intro costruisce l'ufficio «vero»: si torna al passo 1.
            if (step !== 'allocation') setStep('allocation')
            setRoom(null)
            useIntro.getState().replay()
          }}
          title="Replay: build the twin from the floor plan"
          className="rounded-full border border-hairline px-4 py-2 text-[14px] font-medium whitespace-nowrap text-ink transition hover:bg-surface-soft"
        >
          Floor plan
        </button>
        {isMock && <span className="rounded-full border border-hairline px-2.5 py-1 text-[12px] font-medium text-muted">Demo data</span>}
        {hasLocalAi && (
          // Vista consultiva a parte: non è un passo della pipeline e non cambia nessun numero.
          <button
            onClick={() => setStep(step === 'local_ai' ? 'allocation' : 'local_ai')}
            title="Advisory view: open-weight models on available servers"
            className={`rounded-full border px-4 py-2 text-[14px] font-medium whitespace-nowrap transition ${
              step === 'local_ai' ? 'border-ink bg-ink text-white' : 'border-hairline text-ink hover:bg-surface-soft'
            }`}
          >
            Local AI
          </button>
        )}
      </div>
    </header>
  )
}
