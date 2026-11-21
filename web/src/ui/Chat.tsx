import { useEffect, useRef, useState } from 'react'
import { useApp } from '../store'
import { makeCtx } from '../data/twin'
import { unitOf } from '../data/usage'
import { PANEL_W } from '../scene/Scene'

/** Indirizzo dell'assistente: in sviluppo il proxy di Vite (/api → 127.0.0.1:8787), altrimenti VITE_ASSISTANT_URL. */
const API = (import.meta.env.VITE_ASSISTANT_URL as string | undefined) ?? ''

interface Msg {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  focus?: string[]
  error?: boolean
}

const EXAMPLES = [
  'How many AI seats were unused in August 2026, and what do they cost per month?',
  'What would running the GPU server on demand save?',
  'Can we switch off dp-prod at night?',
]

/** Mascotte provvisoria: un piccolo vampiro (il nome del progetto), verde come il resto dell'interfaccia. */
export function Mascot({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <path d="M8 30 L18 14 L24 24 L32 10 L40 24 L46 14 L56 30 Z" fill="#17603f" />
      <circle cx="32" cy="36" r="18" fill="#F4EFE6" />
      <path d="M14 30 Q32 18 50 30 Q44 24 32 24 Q20 24 14 30Z" fill="#17603f" />
      <path d="M32 24 L28 31 L32 29 L36 31 Z" fill="#17603f" />
      <circle cx="25" cy="36" r="2.6" fill="#222" />
      <circle cx="39" cy="36" r="2.6" fill="#222" />
      <circle cx="21" cy="42" r="2.4" fill="#F2A7A0" opacity="0.7" />
      <circle cx="43" cy="42" r="2.4" fill="#F2A7A0" opacity="0.7" />
      <path d="M26 44 Q32 48 38 44" fill="none" stroke="#222" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M28.5 45 L29.6 49 L30.8 45.6 Z M35.5 45 L34.4 49 L33.2 45.6 Z" fill="#fff" stroke="#222" strokeWidth="0.6" />
      <path d="M12 52 Q32 62 52 52 L50 60 Q32 66 14 60 Z" fill="#1f7a57" />
    </svg>
  )
}

/** Chat con l'assistente del backend: risposte con numeri verificati e fonti; gli oggetti citati si aprono nella scena. */
export function Chat() {
  const open = useApp((s) => s.chatOpen)
  const setOpen = useApp((s) => s.setChatOpen)
  const panel = useApp((s) => !!s.selectedId)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => end.current?.scrollIntoView({ behavior: 'smooth' }), [msgs, busy])

  const ask = async (q: string) => {
    if (!q.trim() || busy) return
    const history = msgs.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content }))
    setMsgs((m) => [...m, { role: 'user', content: q }])
    setText('')
    setBusy(true)
    try {
      const r = await fetch(`${API}/api/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: q, history: history.slice(-20) }) })
      if (!r.ok) throw new Error(String(r.status))
      const a = await r.json()
      setMsgs((m) => [...m, { role: 'assistant', content: String(a.answer ?? ''), sources: a.sources ?? [], focus: a.focus_entity_ids ?? [] }])
    } catch {
      setMsgs((m) => [...m, { role: 'assistant', content: 'The assistant is not running. Start it with: python -m assistant serve', error: true }])
    } finally {
      setBusy(false)
    }
  }

  const right = panel ? PANEL_W + 48 : 24
  return (
    <div className="pointer-events-auto absolute bottom-6 z-50 flex flex-col items-end gap-3 transition-[right] duration-500" style={{ right }}>
      {open && (
        <div className="pill-shadow flex h-[540px] w-[380px] flex-col overflow-hidden rounded-[14px] bg-white">
          <div className="flex items-center gap-3 border-b border-hairline-soft px-4 py-3">
            <Mascot className="h-9 w-9" />
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold text-ink">Ask Vampere</div>
              <div className="text-[12px] text-muted">Answers from our data, numbers checked by code</div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
          <div className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 text-[14px]">
            {!msgs.length && (
              <div className="space-y-2">
                <p className="text-muted">Try one of the questions from the case:</p>
                {EXAMPLES.map((q) => (
                  <button key={q} onClick={() => ask(q)} className="block w-full rounded-[10px] border border-hairline px-3 py-2 text-left text-[13px] text-ink hover:bg-surface-soft">
                    {q}
                  </button>
                ))}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : ''}>
                <div className={`max-w-[88%] rounded-[12px] px-3 py-2 whitespace-pre-wrap ${m.role === 'user' ? 'bg-ink text-white' : m.error ? 'bg-warn-soft text-warn' : 'bg-surface-soft text-body'}`}>
                  {m.content}
                  {!!m.focus?.length && <Focus ids={m.focus} />}
                  {!!m.sources?.length && <div className="mt-1.5 text-[11px] text-muted">Sources: {m.sources.slice(0, 4).join(' · ')}</div>}
                </div>
              </div>
            ))}
            {busy && <div className="text-[13px] text-muted">Thinking…</div>}
            <div ref={end} />
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              ask(text)
            }}
            className="flex gap-2 border-t border-hairline-soft p-3"
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask about costs, CO₂ or a measure…"
              className="min-w-0 flex-1 rounded-full border border-hairline px-4 py-2 text-[14px] outline-none focus:border-ink"
            />
            <button disabled={busy || !text.trim()} className="rounded-full bg-primary px-4 text-[14px] font-semibold text-white disabled:bg-primary-disabled">
              Ask
            </button>
          </form>
        </div>
      )}
      <button onClick={() => setOpen(!open)} aria-label="Ask the assistant" className="pill-shadow grid h-16 w-16 place-items-center rounded-full bg-white transition hover:scale-105">
        <Mascot className="h-12 w-12" />
      </button>
    </div>
  )
}

/** Oggetti citati nella risposta: un clic apre il reparto che li usa e li seleziona. */
function Focus({ ids }: { ids: string[] }) {
  const data = useApp((s) => s.data)!
  const ctx = makeCtx(data, [])
  const targets = ids
    .map((raw) => {
      const e = data.entities.find((x) => x.raw_ids?.includes(raw) || x.raw_ids?.includes(data.extra?.raw.get(raw)?.parent ?? '-'))
      if (!e) return null
      const item = data.layout.find((i) => {
        const u = unitOf(ctx, i)
        return u === e.id || (e.id.startsWith('lic:') && u === `pcs:${e.department}`)
      })
      const room = e.department || [...(e.allocation ?? [])].sort((a, b) => b.share - a.share)[0]?.department
      return item && room ? { label: e.label, item, room } : null
    })
    .filter(Boolean) as { label: string; item: { id: string; view?: string }; room: string }[]
  if (!targets.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {targets.slice(0, 3).map((t) => (
        <button
          key={t.item.id}
          onClick={() => {
            const s = useApp.getState()
            s.setRoom(t.room)
            if (t.item.view === 'island') s.setStage('cloud')
            s.select(t.item.id)
          }}
          className="rounded-full border border-primary px-2.5 py-0.5 text-[12px] font-semibold text-primary hover:bg-primary-soft"
        >
          Show {t.label}
        </button>
      ))}
    </div>
  )
}
