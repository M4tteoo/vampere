import { useApp } from '../store'
import { useScreen } from '../scene/twin/screen'
import { RoomTotals } from './RoomTitle'
import { Legend, heatStep } from './Steps'

/**
 * Angolo in basso a sinistra. Nel reparto: spesa totale sopra la legenda, in colonna (se la legenda si chiude, i totali scendono).
 * Nella pianta dei passi 2–4: solo la legenda ridotta, con la base allineata alla base della mappa.
 */
export function BottomLeft() {
  const room = useApp((s) => s.room)
  const step = useApp((s) => s.step)
  const hasExtra = useApp((s) => !!s.data?.extra)
  const base = useScreen((s) => s.points['map:base'])
  const legend = hasExtra && heatStep(step)
  // Passo 3: totali e colori stanno in fondo al pannello dei pacchetti.
  if (step === 'packages' && hasExtra) return null

  // Passo 4: solo isole; legenda in basso a sinistra con tutti i colori (si vede il passaggio rosso/arancio → verde).
  if (step === 'forecast' && legend)
    return (
      <div key={step} className="step-in absolute bottom-6 left-6">
        <Legend compact marks={['driver', 'waste', 'none', 'kept']} />
      </div>
    )
  if (!room) {
    if (!legend || !base) return null
    return (
      <div key={step} className="step-in absolute left-6" style={{ top: base[1], translate: '0 -100%' }}>
        <Legend compact />
      </div>
    )
  }
  return (
    <div key={step} className="step-in absolute bottom-6 left-6 flex flex-col items-start gap-3">
      <RoomTotals />
      {legend && <Legend compact={false} />}
    </div>
  )
}
