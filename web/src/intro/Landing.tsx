import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useIntro } from './store'
import { LOGO_H, LOGO_W, VampereLogo } from '../ui/VampereLogo'

/**
 * Video trasparente, così non c'è nessun bordo fra video e pagina (un H.264 «bianco» esce color crema sugli schermi veri).
 * Safari non gestisce l'alpha in WebM: per lui HEVC con alpha.
 */
const IS_SAFARI = typeof navigator !== 'undefined' && /^((?!chrome|chromium|android|crios|fxios).)*safari/i.test(navigator.userAgent)
const VIDEO_URL = `${import.meta.env.BASE_URL}landing/${IS_SAFARI ? 'caduta-cartello-02-hevc.mov' : 'caduta-cartello-02.webm'}`

/**
 * Dove sta il logo sul cartello nell'ultimo fotogramma di Animazioni/Caduta_Cartello_02.mov (1200×1500).
 * Misurato sulle tessere del contatore: centro, px del video per unità del viewBox del logo, inclinazione.
 * Se si ri-renderizza l'animazione, vanno rimisurati.
 */
const SRC_W = 1200
const SRC_H = 1500
const SIGN = { cx: 599.7, cy: 749.2, unit: 0.769, deg: -2.75 }

/** Tempi (ms) dopo l'ultimo fotogramma. */
const SWAP_MS = 260 // il cartello sfuma, resta il logo
const ROLL_MS = 1000 // scatto del contatore (.vl-roll) e raddrizzamento
const FLY_MS = 1000 // volo in alto a sinistra
const FLY_AT = SWAP_MS + ROLL_MS + 80

/** Dove si posa il logo: lo slot nell'header (data-landing-target). Ripiego se l'header non c'è ancora. */
function targetRect() {
  const el = document.querySelector('[data-landing-target]')
  const r = el?.getBoundingClientRect()
  if (r && r.width > 0) return r
  return { left: 32, top: 26, width: 146, height: 36 }
}

/** 0 video · 1 il logo prende il posto del cartello · 2 contatore + si raddrizza · 3 vola nell'header */
type Stage = 0 | 1 | 2 | 3

export function Landing() {
  const landing = useIntro((s) => s.landing)
  if (landing === 'done') return null
  return <LandingOverlay />
}

function LandingOverlay() {
  const setLanding = useIntro((s) => s.setLanding)
  const video = useRef<HTMLVideoElement>(null)
  const [stage, setStage] = useState<Stage>(0)
  const [view, setView] = useState({ w: window.innerWidth, h: window.innerHeight })
  const [fly, setFly] = useState<{ dx: number; dy: number; s: number } | null>(null)
  /** Il video aspetta fermo sul primo fotogramma finché non si clicca. */
  const [started, setStarted] = useState(false)

  useEffect(() => {
    const onResize = () => setView({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const start = () => {
    const v = video.current
    if (started || !v) return
    setStarted(true)
    // Se il video non parte o non arriva, si salta l'apertura.
    v.play().catch(() => setLanding('done'))
    window.setTimeout(() => v.currentTime === 0 && setLanding('done'), 4000)
  }
  const startRef = useRef(start)
  useEffect(() => {
    startRef.current = start
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLanding('done')
      else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        startRef.current()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setLanding])

  // Geometria: il video occupa l'altezza dello schermo, il logo combacia con quello del cartello.
  const k = Math.min(view.h / SRC_H, view.w / SRC_W)
  const vidW = SRC_W * k
  const vidH = SRC_H * k
  const cx = view.w / 2 + (SIGN.cx - SRC_W / 2) * k
  const cy = view.h / 2 + (SIGN.cy - SRC_H / 2) * k
  const logoW = LOGO_W * SIGN.unit * k
  const logoH = LOGO_H * SIGN.unit * k

  // Sequenza dopo l'ultimo fotogramma.
  const onEnded = () => {
    setStage(1)
    const t = [
      window.setTimeout(() => setStage(2), SWAP_MS),
      window.setTimeout(() => {
        const r = targetRect()
        setFly({ dx: r.left + r.width / 2 - cx, dy: r.top + r.height / 2 - cy, s: r.width / logoW })
        setStage(3)
        setLanding('reveal')
      }, FLY_AT),
      window.setTimeout(() => setLanding('done'), FLY_AT + FLY_MS + 60),
    ]
    timers.current = t
  }
  const timers = useRef<number[]>([])
  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const rotate = stage >= 2 ? 0 : SIGN.deg
  const move = stage === 3 && fly ? `translate(${fly.dx}px, ${fly.dy}px) scale(${fly.s})` : ''
  const logoStyle: CSSProperties = {
    left: cx - logoW / 2,
    top: cy - logoH / 2,
    width: logoW,
    height: logoH,
    opacity: stage >= 1 ? 1 : 0,
    transform: `${move} rotate(${rotate}deg)`,
    transition:
      stage === 1
        ? `opacity ${SWAP_MS}ms linear`
        : stage === 2
          ? `transform ${ROLL_MS * 0.7}ms cubic-bezier(0.65, 0, 0.35, 1)`
          : stage === 3
            ? `transform ${FLY_MS}ms cubic-bezier(0.7, 0, 0.25, 1)`
            : 'none',
  }

  return (
    <div
      className="fixed inset-0 z-[100]"
      onClick={start}
      style={{ pointerEvents: stage === 3 ? 'none' : 'auto', cursor: started ? 'default' : 'pointer' }}
    >
      <div
        className="absolute inset-0 bg-white"
        style={{ opacity: stage === 3 ? 0 : 1, transition: `opacity ${FLY_MS * 0.7}ms ease ${FLY_MS * 0.25}ms` }}
      >
        <video
          ref={video}
          src={VIDEO_URL}
          muted
          playsInline
          preload="auto"
          onEnded={onEnded}
          onError={() => setLanding('done')}
          className="absolute"
          style={{
            left: (view.w - vidW) / 2,
            top: (view.h - vidH) / 2,
            width: vidW,
            height: vidH,
            opacity: stage >= 1 ? 0 : 1,
            transition: `opacity ${SWAP_MS * 1.8}ms ease-out`,
          }}
        />
      </div>

      <div className="absolute" style={logoStyle}>
        <VampereLogo roll={stage >= 2} className="block h-full w-full" />
      </div>

      <p
        className={`${started ? '' : 'landing-hint'} pointer-events-none absolute inset-x-0 bottom-4 text-center text-[13px] font-medium tracking-[0.12em] text-muted uppercase`}
        style={{ opacity: started ? 0 : undefined, transition: 'opacity 0.3s' }}
      >
        Click to start
      </p>
    </div>
  )
}
