import { useEffect } from 'react'
import { useApp, type View } from '../store'
import { fmtChf, fmtMetric, packageTotals } from '../data/compute'
import type { Dataset } from '../data/types'
import { Card } from './primitives'

// --- Viste della camera (in basso a sinistra) --------------------------------------------------------------

const VIEWS: { id: View; label: string }[] = [
  { id: 'overview', label: 'Tutto' },
  { id: 'office', label: 'Ufficio' },
  { id: 'islands', label: 'Data center' },
]

export function ViewControls() {
  const view = useApp((s) => s.view)
  const setView = useApp((s) => s.setView)
  return (
    <div className="pill-shadow pointer-events-auto flex rounded-full bg-white p-1">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          onClick={() => setView(v.id)}
          className={`rounded-full px-4 py-2 text-[14px] font-medium transition ${view === v.id ? 'bg-ink text-white' : 'text-ink hover:bg-surface-soft'}`}
        >
          {v.label}
        </button>
      ))}
    </div>
  )
}

// --- Legenda dei colori (in basso a destra) ----------------------------------------------------------------

export function Legend() {
  const rows: [string, string][] = [
    ['#CFEBDB', 'in uso'],
    ['#F5B65E', 'pagato ma poco usato'],
    ['#2C3036', 'spento o disdetto'],
    ['#B4C3DA', 'protetto'],
    ['#AFC9F3', 'decide una persona'],
  ]
  return (
    <Card className="px-4 py-3">
      <div className="mb-1.5 text-[12px] font-semibold text-ink">Schermi e luci</div>
      <ul className="space-y-1">
        {rows.map(([c, t]) => (
          <li key={t} className="flex items-center gap-2 text-[12px] text-body">
            <span className="h-2.5 w-4 rounded-[3px] ring-1 ring-black/5" style={{ background: c }} />
            {t}
          </li>
        ))}
        <li className="flex items-center gap-2 pt-1 text-[12px] text-body">
          <span className="h-2.5 w-4 rounded-[3px] bg-gradient-to-r from-[#EAD9C2] to-[#E39A6F]" />
          pavimento: peso del reparto
        </li>
      </ul>
    </Card>
  )
}

// --- Avvisi (misura bloccata o da decidere) ---------------------------------------------------------------

export function Notice() {
  const notice = useApp((s) => s.notice)
  const dismiss = useApp((s) => s.dismissNotice)
  if (!notice) return null
  const tone = notice.tone === 'blocked' ? 'bg-error-soft' : notice.tone === 'human' ? 'bg-human-soft' : 'bg-white'
  return (
    <div className={`pill-shadow pointer-events-auto flex max-w-xl items-start gap-3 rounded-[14px] px-5 py-4 ${tone}`}>
      <span className="text-[20px] leading-none">{notice.tone === 'blocked' ? '⛔' : notice.tone === 'human' ? '👤' : 'ℹ️'}</span>
      <div className="flex-1">
        <div className="text-[15px] font-semibold text-ink">{notice.title}</div>
        <div className="mt-0.5 text-[14px] text-body">{notice.text}</div>
      </div>
      <button onClick={dismiss} aria-label="Chiudi" className="text-[18px] leading-none text-muted hover:text-ink">
        ×
      </button>
    </div>
  )
}

// --- Tour guidato per il pitch (B10) ----------------------------------------------------------------------

type S = ReturnType<typeof useApp.getState>

interface Step {
  kicker: string
  title: string
  text: (d: Dataset, s: S) => string
  run: (s: S) => void
}

const STEPS: Step[] = [
  {
    kicker: '1 · Connetti',
    title: '28 file, un solo quadro',
    text: (d) =>
      `Fatture cloud, SaaS, AI, ticket e metriche in un formato unico: ${fmtChf(d.summary.baseline.cost_chf)}, ${fmtMetric(d.summary.baseline.kwh, 'kwh')} e ${fmtMetric(d.summary.baseline.co2_kg, 'co2_kg')} all’anno. Si decide a Basilea, si consuma nei data center.`,
    run: (s) => {
      s.reset()
      s.setMode('connect')
      s.setView('overview')
    },
  },
  {
    kicker: '2 · Scopri',
    title: 'Acceso 24 ore, lavora 2',
    text: (d) => d.findings.find((f) => f.entity_id === 'dp-dev')?.evidence ?? '',
    run: (s) => {
      s.setMode('find')
      s.select('island:dp-dev')
    },
  },
  {
    kicker: '2 · Scopri',
    title: 'Licenze pagate, schermi color ambra',
    text: (d) => {
      const c = d.items.find((i) => i.id === 'lic:chatgpt:sales')
      return `${c ? `ChatGPT Team in Sales: ${c.headline}. ` : ''}Ogni scrivania è un posto Microsoft 365, ogni dischetto un posto AI: ambra = pagato ma non usato.`
    },
    run: (s) => {
      s.setMode('find')
      s.select('room:sales')
    },
  },
  {
    kicker: '3 · Decidi',
    title: 'Il pacchetto consigliato',
    text: (d, s) => {
      const t = packageTotals(d, s.active)
      return `${s.active.length} misure: −${Math.round(t.co2Pct * 100)}% CO₂ e −${Math.round(t.costPct * 100)}% costi per ${fmtChf(t.effortChf)} (${t.effortDays} giornate). Il cluster di sviluppo vola da Francoforte a Zurigo, la GPU si spegne, i posti inutilizzati spariscono.`
    },
    run: (s) => {
      s.setMode('decide')
      s.applyRecommended()
      s.setView('overview')
    },
  },
  {
    kicker: '4 · Limiti',
    title: 'Quello che il sistema non fa da solo',
    text: (d) => d.measures.find((m) => m.id === 'X1')?.reason ?? '',
    run: (s) => {
      s.setMode('limits')
      s.select('dp-prod')
      s.toggleMeasure('X1')
    },
  },
  {
    kicker: 'Fine',
    title: 'Ogni numero si apre',
    text: () => 'Clicca qualsiasi oggetto: formula, fattori, fonti e ticket dietro ogni cifra. I due CSV di consegna si scaricano dalla barra in alto.',
    run: (s) => {
      s.dismissNotice()
      s.setMode('decide')
      s.setView('overview')
    },
  },
]

export function Tour() {
  const tour = useApp((s) => s.tour)
  const setTour = useApp((s) => s.setTour)
  const data = useApp((s) => s.data)!
  const state = useApp()

  useEffect(() => {
    if (tour === null) return
    STEPS[tour].run(useApp.getState())
  }, [tour])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = useApp.getState().tour
      if (t === null) return
      if (e.key === 'ArrowRight') setTour(Math.min(STEPS.length - 1, t + 1))
      if (e.key === 'ArrowLeft') setTour(Math.max(0, t - 1))
      if (e.key === 'Escape') setTour(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setTour])

  if (tour === null) return null
  const step = STEPS[tour]
  return (
    <Card className="w-[560px] p-5">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-semibold tracking-wide text-primary uppercase">{step.kicker}</span>
        <div className="flex gap-1.5">
          {STEPS.map((_, i) => (
            <button key={i} onClick={() => setTour(i)} aria-label={`Passo ${i + 1}`} className={`h-2 rounded-full transition-all ${i === tour ? 'w-5 bg-ink' : 'w-2 bg-hairline'}`} />
          ))}
        </div>
      </div>
      <div className="mt-1 text-[20px] font-semibold tracking-[-0.18px]">{step.title}</div>
      <p className="mt-1 text-[14px] leading-relaxed text-body">{step.text(data, state)}</p>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-[12px] text-muted">← → per muoverti · Esc per uscire</span>
        <div className="flex gap-2">
          <button
            onClick={() => setTour(Math.max(0, tour - 1))}
            disabled={tour === 0}
            className="rounded-[8px] border border-hairline px-4 py-2 text-[14px] font-medium disabled:opacity-40"
          >
            Indietro
          </button>
          {tour < STEPS.length - 1 ? (
            <button onClick={() => setTour(tour + 1)} className="rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-white hover:bg-primary-active">
              Avanti
            </button>
          ) : (
            <button onClick={() => setTour(null)} className="rounded-[8px] bg-ink px-4 py-2 text-[14px] font-medium text-white">
              Fine
            </button>
          )}
        </div>
      </div>
    </Card>
  )
}
