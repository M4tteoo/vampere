import { useId, type CSSProperties } from 'react'

/** Larghezza e altezza del viewBox (design/logo/vampere-meter.svg). */
export const LOGO_W = 934
export const LOGO_H = 230

const LETTERS = [
  { x: 64.6, d: 'M0,0 L38,100 L76,0' },
  { x: 188.6, d: 'M0,100 L38,0 L76,100 M17,62 L59,62' },
  { x: 308.6, d: 'M0,100 L0,0 L43,66 L86,0 L86,100' },
  { x: 443.8, d: 'M0,100 L0,0 L32,0 A26,26 0 0 1 32,52 L0,52' },
  { x: 569.4, d: 'M54,0 L0,0 L0,100 L54,100 M0,50 L46,50 M16,-36 L34,-18' },
  { x: 691, d: 'M0,100 L0,0 L32,0 A26,26 0 0 1 32,52 L0,52 M30,52 L60,100' },
]
const E = 'M54,0 L0,0 L0,100 L54,100 M0,50 L46,50'

/**
 * Logo «contatore» Vampère, inline (stesso disegno di design/logo/vampere-meter-animated.svg).
 * Con `roll` la rotella rossa scatta una volta di una cifra (.vl-roll in index.css), come il contatore animato.
 */
export function VampereLogo({ roll = false, className, style }: { roll?: boolean; className?: string; style?: CSSProperties }) {
  const clip = useId()
  return (
    <svg viewBox={`0 0 ${LOGO_W} ${LOGO_H}`} className={className} style={style} role="img" aria-label="Vampère">
      <defs>
        <clipPath id={clip}>
          <rect x="784" y="40" width="110" height="150" rx="14" />
        </clipPath>
      </defs>
      <g fill="none" strokeWidth="10" strokeLinecap="round">
        <path stroke="#121314" d="M760,22 L42,22 A20,20 0 0 0 22,42 L22,188 A20,20 0 0 0 42,208 L752,208" />
        <path stroke="#D7263D" d="M790,22 L892,22 A20,20 0 0 1 912,42 L912,188 A20,20 0 0 1 892,208 L790,208" />
      </g>
      {[40, 164, 288, 412, 536, 660].map((x) => (
        <rect key={x} x={x} y="40" width="110" height="150" rx="14" fill="#121314" />
      ))}
      <rect x="784" y="40" width="110" height="150" rx="14" fill="#D7263D" />
      <g fill="none" stroke="#FFFFFF" strokeWidth="16" strokeLinecap="round" strokeLinejoin="round">
        {LETTERS.map((l) => (
          <path key={l.x} transform={`translate(${l.x},84) scale(0.8)`} d={l.d} />
        ))}
      </g>
      <g clipPath={`url(#${clip})`}>
        <g className={roll ? 'vl-roll' : undefined} fill="none" stroke="#FFFFFF" strokeWidth="16" strokeLinecap="round" strokeLinejoin="round">
          {[32, 161, 290].map((y) => (
            <path key={y} transform={`translate(817.4,${y}) scale(0.8)`} d={E} />
          ))}
        </g>
      </g>
    </svg>
  )
}
