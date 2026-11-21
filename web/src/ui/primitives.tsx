import type { ReactNode } from 'react'

/** Superfici e piccoli componenti condivisi (stile DESIGN.md: bianco, raggio 14 px, un solo livello d'ombra). */
export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`pill-shadow pointer-events-auto rounded-[14px] bg-white ${className}`}>{children}</div>
}

export function Kicker({ children }: { children: ReactNode }) {
  return <div className="text-[12px] font-semibold tracking-wide text-muted uppercase">{children}</div>
}

export function Toggle({ on, disabled }: { on: boolean; disabled?: boolean }) {
  return (
    <span
      aria-hidden
      className={`relative inline-block h-6 w-10 shrink-0 rounded-full transition ${disabled ? 'bg-surface-strong' : on ? 'bg-primary' : 'bg-hairline'}`}
    >
      <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition ${on ? 'translate-x-4' : ''}`} />
    </span>
  )
}

export type Tone = 'neutral' | 'primary' | 'warn' | 'error' | 'human' | 'lock'

const TONE: Record<Tone, string> = {
  neutral: 'bg-surface-strong text-ink',
  primary: 'bg-primary-soft text-primary',
  warn: 'bg-warn-soft text-warn',
  error: 'bg-error-soft text-error',
  human: 'bg-human-soft text-human',
  lock: 'bg-lock-soft text-lock',
}

export function Chip({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${TONE[tone]}`}>{children}</span>
}

/** Riga «amenity» di Airbnb: etichetta a sinistra, valore a destra. */
export function Row({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5">
      <span className="text-[14px] text-body">{label}</span>
      <span className="text-right text-[14px] font-semibold text-ink">
        {value}
        {sub && <span className="block text-[12px] font-normal text-muted">{sub}</span>}
      </span>
    </div>
  )
}

export function Divider() {
  return <div className="my-4 h-px bg-hairline-soft" />
}

export function PrimaryButton({ children, onClick, className = '' }: { children: ReactNode; onClick?: () => void; className?: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-[8px] bg-primary px-4 py-2.5 text-[14px] font-medium text-white transition hover:bg-primary-active active:scale-[0.98] ${className}`}
    >
      {children}
    </button>
  )
}

export function SecondaryButton({ children, onClick, className = '' }: { children: ReactNode; onClick?: () => void; className?: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-[8px] border border-ink bg-white px-4 py-2.5 text-[14px] font-medium text-ink transition hover:bg-surface-soft active:scale-[0.98] ${className}`}
    >
      {children}
    </button>
  )
}

export function Bar({ value, max, color = 'bg-primary' }: { value: number; max: number; color?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-strong">
      <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${Math.min(100, (value / (max || 1)) * 100)}%` }} />
    </div>
  )
}
