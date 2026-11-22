import { useApp } from '../store'

/**
 * Come si conta la CO₂ (bonus del caso): «Local grid» = location-based, il mix reale dove girano i server (riferimento);
 * «Market-based» = stessi kWh con il residual mix AIB, perché l'azienda non compra certificati verdi.
 * Cambia tutti i numeri di CO₂ dei passi 2–4: totali, nuvole, risparmi.
 */
export function Co2Switch() {
  const basis = useApp((s) => s.co2Basis)
  const set = useApp((s) => s.setCo2Basis)
  const has = useApp((s) => !!s.data?.extra?.market)
  if (!has) return null
  const opts = [
    { id: 'location' as const, label: 'Local grid', hint: 'Location-based: the real power mix where the servers run (the reference figure).' },
    { id: 'market' as const, label: 'Market-based', hint: 'Same energy with the residual mix: the company buys no green certificates, so it gets the power others did not claim.' },
  ]
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="whitespace-nowrap text-muted">CO₂ on</span>
      <div className="flex rounded-full bg-surface-soft p-0.5">
        {opts.map((o) => (
          <button
            key={o.id}
            title={o.hint}
            onClick={() => set(o.id)}
            className={`rounded-full px-2.5 py-0.5 font-semibold whitespace-nowrap transition ${basis === o.id ? 'bg-white text-ink shadow-sm' : 'text-muted hover:text-ink'}`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}
