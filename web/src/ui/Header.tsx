import { useApp, type Step } from '../store'
import { useIntro } from '../intro/store'
import { LOGO_H, LOGO_W, VampereLogo } from './VampereLogo'
import { ExportButton } from './Steps'

/** Passi della demo, nell'ordine in cui li racconta. Misure e limiti stanno dentro il passo 2 (interruttore), l'export nei passi 2 e 3. */
export const STEPS: { id: Step; label: string }[] = [
  { id: 'allocation', label: 'Consumption map' },
  { id: 'baseline', label: 'Baseline & hotspots' },
  { id: 'packages', label: 'Packages' },
  { id: 'forecast', label: 'Forecasting' },
]

/** Barra in alto: logo a sinistra, i passi numerati in una pillola al centro (stile ricerca di Airbnb, senza icone). */
export function Header() {
  const step = useApp((s) => s.step)
  const setStep = useApp((s) => s.setStep)
  const setRoom = useApp((s) => s.setRoom)
  const isMock = useApp((s) => s.data?.summary.is_mock)
  const extra = useApp((s) => s.data?.extra)
  const hasExtra = useApp((s) => !!s.data?.extra)
  const landed = useIntro((s) => s.landing === 'done')
  // Durante l'intro (caricamento della planimetria) solo il logo: niente passi né bottoni.
  const introDone = useIntro((s) => s.phase === 'done')

  // Logo = home: si torna alla schermata «Digital twin setup» (scelta della pianta); la demo riparte dal passo 1, dalla pianta.
  const goHome = () => {
    const s = useApp.getState()
    s.setChatOpen(false)
    if (s.step !== 'allocation') setStep('allocation')
    setRoom(null)
    useIntro.getState().replay()
  }

  const ready = (id: Step): { ok: boolean; why?: string } => {
    if (id === 'allocation') return { ok: true }
    if (!hasExtra) return { ok: false, why: 'Needs the backend output (timeseries, measures)' }
    return { ok: true }
  }

  return (
    <header
      // Durante l'intro niente fascia bianca: l'header è trasparente e sta sopra la scena (resta solo il logo).
      // Sopra lo schermo dell'intro (z-50), così il logo resta visibile per tutta l'animazione della planimetria.
      className={`flex h-[88px] shrink-0 items-center justify-between px-8 ${introDone ? 'relative z-40 bg-white' : 'pointer-events-none absolute inset-x-0 top-0 z-[60] bg-transparent'}`}
    >
      <button onClick={goHome} disabled={!landed} className="flex w-48 items-center" aria-label="Back to the home page">
        {/* Qui si posa il logo dell'apertura (intro/Landing.tsx): resta nascosto finché non è atterrato. */}
        <span data-landing-target className="block h-9" style={{ width: (36 * LOGO_W) / LOGO_H, opacity: landed ? 1 : 0 }}>
          <VampereLogo className="block h-full w-full" />
        </span>
      </button>

      <nav className={`pill-shadow flex h-16 items-center rounded-full border border-hairline bg-white px-3 ${introDone ? '' : 'invisible'}`}>
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

      <div className={`flex w-48 items-center justify-end gap-2 ${introDone ? "" : "invisible"}`}>
        {hasExtra && (step === 'baseline' || step === 'packages') && <ExportButton x={extra!} />}
        {isMock && <span className="rounded-full border border-hairline px-2.5 py-1 text-[12px] font-medium text-muted">Demo data</span>}
      </div>
    </header>
  )
}
