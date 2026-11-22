import type { Extra } from '../data/extra'

/** Come si comporta un server durante l'anno (clustering del backend): un simbolo piccolo, non un colore. */
type Kind = 'demand' | 'idle' | 'light' | 'steady'

export function behaviourKind(name: string): Kind {
  const n = name.toLowerCase()
  if (n.includes('demand')) return 'demand'
  if (n.includes('idle')) return 'idle'
  if (n.includes('light')) return 'light'
  return 'steady'
}

/** Frase breve per la scheda e per la legenda. */
export const BEHAVIOUR_TEXT: Record<Kind, string> = {
  demand: 'Switched on only when needed',
  idle: 'Always on, almost never working',
  light: 'Always on, lightly used',
  steady: 'Always on, steady workload',
}

export function BehaviourIcon({ kind, className = 'h-3.5 w-3.5' }: { kind: Kind; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {kind === 'demand' && <path d="M12 3v8M6.5 7a7 7 0 1 0 11 0" />}
      {kind === 'idle' && <path d="M5 8h5l-5 6h5M14 4h5l-5 6h5" />}
      {kind === 'light' && <path d="M3 17h4l3-4 3 2 3-6 5 8" />}
      {kind === 'steady' && <path d="M3 12c2-4 4-4 6 0s4 4 6 0 4-4 6 0" />}
    </svg>
  )
}

/** Gruppo di un'unità: nome, tipo di simbolo e quanti server ne fanno parte. */
export function behaviourOf(x: Extra, groupId: string | null) {
  const g = groupId ? x.clusters?.groups.find((c) => c.id === groupId) : undefined
  return g ? { ...g, kind: behaviourKind(g.name) } : null
}
