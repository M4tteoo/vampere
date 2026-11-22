import { useEffect, useRef, useState } from 'react'
import { useApp } from '../store'
import { makeCtx } from '../data/twin'
import { unitOf } from '../data/usage'
import { PANEL_W } from '../scene/Scene'
import { SPINNER_INTERVAL_MS, randomVerb } from './spinnerVerbs'

/** Indirizzo dell'assistente: in sviluppo il proxy di Vite (/api → 127.0.0.1:8787), altrimenti VITE_ASSISTANT_URL. */
const API = (import.meta.env.VITE_ASSISTANT_URL as string | undefined) ?? ''

interface Msg {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  focus?: string[]
  error?: boolean
}

/** Una conversazione salvata nella cronologia. */
interface Conversation {
  id: string
  title: string
  updated: number
  msgs: Msg[]
}

/** Cronologia nel localStorage di questo browser (solo comodità: se non c'è o è bloccato, la chat funziona lo stesso). */
const STORE = 'vampere.chats.v1'
const MAX_CHATS = 30
const loadChats = (): Conversation[] => {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) ?? '[]')
    return Array.isArray(v) ? v.filter((c) => c && typeof c.id === 'string' && Array.isArray(c.msgs)) : []
  } catch {
    return []
  }
}
const saveChats = (chats: Conversation[]) => {
  try {
    localStorage.setItem(STORE, JSON.stringify(chats.slice(0, MAX_CHATS)))
  } catch {
    /* storage pieno o bloccato: la cronologia resta solo in memoria */
  }
}
const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
const when = (t: number) => {
  const d = new Date(t)
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString([], { day: 'numeric', month: 'short' })
}

const EXAMPLES = [
  'How many AI seats were unused in August 2026, and what do they cost per month?',
  'What would running the GPU server on demand save?',
  'Can we switch off dp-prod at night?',
]

/** Ritratti del vampiro (render di Vampire.png, PNG trasparenti). */
const V = `${import.meta.env.BASE_URL}vampire/`

/** Ritratto piccolo e rotondo di Wattson, accanto alle sue risposte. */
export function Mascot({ className = '' }: { className?: string }) {
  return (
    <span className={`block overflow-hidden rounded-full bg-vampire ${className}`} aria-hidden>
      <img src={`${V}avatar.png`} alt="" draggable={false} className="h-full w-full object-cover" />
    </span>
  )
}

/** Pose di Wattson (Pose_PNG/, ritagliate in public/vampire/pose-*.png):
 *  hello saluta · think pensa · search cerca nei dati · talk risponde · scared i dati hanno provato a dargli ordini ·
 *  hide si copre col mantello quando l'assistente non risponde. `rest` è il ritratto di Vampire.png. */
type Pose = 'rest' | 'hello' | 'think' | 'search' | 'talk' | 'scared' | 'hide'
const POSES: Pose[] = ['rest', 'hello', 'think', 'search', 'talk', 'scared', 'hide']
const poseSrc = (p: Pose) => `${V}${p === 'rest' ? 'pop' : `pose-${p}`}.png`

/** Wattson che esce dal cerchio: il cerchio è il quadrato in basso (size × size), la testa sporge sopra.
 *  Una maschera lascia visibile tutto ciò che sta sopra il centro del cerchio (con margine `pad` in alto e ai lati,
 *  così il rimbalzo di vamp-pop non taglia testa e mani) e sotto segue il bordo del cerchio, dove finisce il mantello. */
export function PopAvatar({ size, pose = 'rest', className = '' }: { size: number; pose?: Pose; className?: string }) {
  const r = size / 2
  // Le immagini (390×426) hanno già questo margine del 15% per lato, così sono larghe quanto la maschera,
  // e continuano per `bleed` sotto il cerchio: quando vamp-pop le alza, sotto il corpo non si vede il bordo.
  const pad = size * 0.15
  const bleed = size * 0.12
  const mask = `linear-gradient(#000, #000) top / 100% calc(100% - ${r}px) no-repeat, radial-gradient(circle at 50% calc(100% - ${r}px), #000 ${r - 0.5}px, transparent ${r}px) no-repeat`
  return (
    <span className={`relative block shrink-0 ${className}`} style={{ width: size, height: size * 1.3 }} aria-hidden>
      <span className="pill-shadow absolute inset-x-0 bottom-0 rounded-full bg-vampire" style={{ height: size }} />
      <span className="absolute bottom-0" style={{ left: -pad, right: -pad, top: -pad, mask, WebkitMask: mask }}>
        <img key={pose} src={poseSrc(pose)} alt="" draggable={false} className="vamp-pop absolute left-0 object-cover" style={{ bottom: -bleed, width: size + 2 * pad, height: size * 1.3 + bleed }} />
      </span>
    </span>
  )
}

/** Chat con l'assistente del backend: risposte con numeri verificati e fonti; gli oggetti citati si aprono nella scena. */
export function Chat() {
  const open = useApp((s) => s.chatOpen)
  const setOpen = useApp((s) => s.setChatOpen)
  const panel = useApp((s) => !!s.selectedId)
  const [chats, setChats] = useState<Conversation[]>(loadChats)
  /** Conversazione aperta; null = chat nuova, che entra in cronologia alla prima domanda. */
  const [cur, setCur] = useState<string | null>(null)
  /** Conversazioni che aspettano una risposta (una risposta arriva sempre nella sua, anche se nel frattempo ne apri un'altra). */
  const [pending, setPending] = useState<string[]>([])
  const [view, setView] = useState<'chat' | 'history'>('chat')
  const [text, setText] = useState('')
  const [pose, setPose] = useState<Pose>('talk')
  const [tick, setTick] = useState(0)
  const [hover, setHover] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const curRef = useRef<string | null>(null)
  const msgs = chats.find((c) => c.id === cur)?.msgs ?? []
  const busy = cur !== null && pending.includes(cur)

  useEffect(() => saveChats(chats), [chats])
  useEffect(() => end.current?.scrollIntoView({ behavior: 'smooth' }), [msgs.length, busy, view])

  const show = (id: string | null) => {
    curRef.current = id
    setCur(id)
    setView('chat')
  }
  const newChat = () => (show(null), setText(''), setPose('hello'))
  const openChat = (id: string) => (show(id), setPose(pending.includes(id) ? 'think' : 'talk'))
  const deleteChat = (id: string) => {
    setChats((cs) => cs.filter((c) => c.id !== id))
    if (cur === id) show(null)
    setView('history')
  }
  /** Aggiunge un messaggio a una conversazione (la crea se serve) e la porta in cima alla cronologia. */
  const push = (id: string, title: string, m: Msg) =>
    setChats((cs) => {
      const c = cs.find((x) => x.id === id)
      const next = c ? { ...c, msgs: [...c.msgs, m], updated: Date.now() } : { id, title, updated: Date.now(), msgs: [m] }
      return [next, ...cs.filter((x) => x.id !== id)].slice(0, MAX_CHATS)
    })
  // Carica subito tutte le pose, così i cambi sono istantanei.
  useEffect(() => POSES.forEach((p) => (new Image().src = poseSrc(p))), [])
  // Mentre lavora alterna «pensa» e «cerca», allo stesso ritmo dei verbi dello spinner.
  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => setTick((t) => t + 1), SPINNER_INTERVAL_MS)
    return () => clearInterval(id)
  }, [busy])
  const shown: Pose = busy ? (tick % 2 ? 'search' : 'think') : pose

  const ask = async (q: string) => {
    if (!q.trim() || busy) return
    const history = msgs.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content }))
    const id = cur ?? newId()
    if (!cur) show(id)
    push(id, q.trim().slice(0, 80), { role: 'user', content: q })
    setText('')
    setTick(0)
    setPending((p) => [...p, id])
    // La posa cambia solo se quella conversazione è ancora aperta quando arriva la risposta.
    const mine = () => curRef.current === id
    try {
      const r = await fetch(`${API}/api/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: q, history: history.slice(-20) }) })
      if (!r.ok) throw new Error(String(r.status))
      const a = await r.json()
      push(id, '', { role: 'assistant', content: String(a.answer ?? ''), sources: a.sources ?? [], focus: a.focus_entity_ids ?? [] })
      if (mine()) setPose(a.ignored_data_instructions ? 'scared' : 'talk')
    } catch {
      push(id, '', { role: 'assistant', content: 'Wattson is still asleep in his coffin. Start the assistant with: python -m assistant serve', error: true })
      if (mine()) setPose('hide')
    } finally {
      setPending((p) => p.filter((x) => x !== id))
    }
  }

  const right = panel ? PANEL_W + 48 : 24
  return (
    <div className="pointer-events-auto absolute bottom-6 z-50 flex flex-col items-end gap-3 transition-[right] duration-500" style={{ right }}>
      {open && (
        <div className="pill-shadow flex h-[540px] w-[380px] flex-col overflow-hidden rounded-[14px] bg-white">
          <div className="flex items-center gap-3 border-b border-hairline-soft px-4 pt-2 pb-3">
            <button onClick={() => !busy && setPose('hello')} aria-label="Wave at Wattson" className="shrink-0">
              <PopAvatar size={60} pose={shown} />
            </button>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold text-ink">Wattson</div>
              <div className="text-[12px] text-muted">Hunter of energy vampires · every number checked by code</div>
            </div>
            <button
              onClick={() => setView(view === 'history' ? 'chat' : 'history')}
              aria-label="Chat history"
              aria-pressed={view === 'history'}
              title="Chat history"
              className={`grid h-8 w-8 place-items-center rounded-full hover:bg-hairline ${view === 'history' ? 'bg-ink text-white hover:bg-ink' : 'bg-surface-strong text-ink'}`}
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
            </button>
            {(msgs.length > 0 || view === 'history') && (
              <button onClick={newChat} aria-label="New chat" title="New chat" className="grid h-8 w-8 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
              </button>
            )}
            <button onClick={() => setOpen(false)} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-full bg-surface-strong text-ink hover:bg-hairline">
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
          {view === 'history' ? (
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 py-2 text-[14px]">
              <div className="px-2 pt-1 pb-2 text-[13px] font-semibold text-ink">Past chats</div>
              {!chats.length && <p className="px-2 text-[13px] text-muted">No chats yet. Ask Wattson something and it will appear here.</p>}
              {chats.map((c) => (
                <div key={c.id} className={`group flex items-center gap-1 rounded-[10px] hover:bg-surface-soft ${c.id === cur ? 'bg-surface-soft' : ''}`}>
                  <button onClick={() => openChat(c.id)} className="min-w-0 flex-1 px-2 py-2 text-left">
                    <div className="truncate text-[13px] text-ink">{c.title}</div>
                    <div className="text-[11px] text-muted">
                      {when(c.updated)} · {c.msgs.length} messages{pending.includes(c.id) ? ' · answering…' : ''}
                    </div>
                  </button>
                  <button
                    onClick={() => deleteChat(c.id)}
                    aria-label={`Delete chat: ${c.title}`}
                    title="Delete chat"
                    className="mr-1 grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted opacity-0 group-hover:opacity-100 hover:bg-hairline hover:text-ink focus-visible:opacity-100"
                  >
                    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          ) : (
          <div className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 text-[14px]">
            {!msgs.length && (
              <div className="space-y-2">
                {EXAMPLES.map((q) => (
                  <button key={q} onClick={() => ask(q)} className="block w-full rounded-[10px] border border-hairline px-3 py-2 text-left text-[13px] text-ink hover:bg-surface-soft">
                    {q}
                  </button>
                ))}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex items-end gap-2'}>
                {m.role === 'assistant' && <Mascot className="h-7 w-7 shrink-0" />}
                <div className={`max-w-[88%] rounded-[12px] px-3 py-2 whitespace-pre-wrap ${m.role === 'user' ? 'bg-ink text-white' : m.error ? 'bg-warn-soft text-warn' : 'bg-surface-soft text-body'}`}>
                  {m.content}
                  {!!m.focus?.length && <Focus ids={m.focus} />}
                  {!!m.sources?.length && <div className="mt-1.5 text-[11px] text-muted">Sources: {m.sources.slice(0, 4).join(' · ')}</div>}
                </div>
              </div>
            ))}
            {busy && <SpinnerVerb />}
            <div ref={end} />
          </div>
          )}
          {view === 'chat' && (
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
          )}
        </div>
      )}
      {/* Il cerchio in basso c'è solo a chat chiusa: aperta, Wattson sta nell'intestazione e la X la richiude. */}
      {!open && (
        <button
          onClick={() => (!busy && setPose(msgs.length ? 'hello' : 'talk'), setHover(false), setOpen(true))}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          aria-label="Ask Wattson"
          className="origin-bottom transition hover:scale-105"
        >
          <PopAvatar size={80} pose={hover ? 'hello' : busy ? shown : 'rest'} />
        </button>
      )}
    </div>
  )
}

/** Verbo casuale che cambia a intervalli mentre l'assistente lavora. */
function SpinnerVerb() {
  const [verb, setVerb] = useState(() => randomVerb())
  useEffect(() => {
    const id = setInterval(() => setVerb((v) => randomVerb(v)), SPINNER_INTERVAL_MS)
    return () => clearInterval(id)
  }, [])
  return <div className="text-[13px] text-muted">{verb}…</div>
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
