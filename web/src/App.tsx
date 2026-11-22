import { useEffect, useState } from 'react'
import { loadDataset } from './data/load'
import { useApp, type Step } from './store'
import { Scene } from './scene/Scene'
import { Header } from './ui/Header'
import { RoomTitle } from './ui/RoomTitle'
import { ItemPanel } from './ui/ItemPanel'
import { LocalAiPanel } from './ui/LocalAiPanel'
import { SceneLabels } from './ui/SceneLabels'
import { BlueprintIntro } from './ui/BlueprintIntro'
import { useIntro } from './intro/store'
import { useProgress } from '@react-three/drei'
import { StepUi, Ticker } from './ui/Steps'
import { Chat } from './ui/Chat'
import { Landing } from './intro/Landing'

/** Demo passo per passo. Per ora: Allocation (chi consuma cosa). Gli altri passi sono in src/scene/SceneAll.tsx e src/ui/*Panel. */
export default function App() {
  const data = useApp((s) => s.data)
  const step = useApp((s) => s.step)
  const setData = useApp((s) => s.setData)
  const introDone = useIntro((s) => s.phase === 'done')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadDataset()
      .then((d) => {
        setData(d)
        // Parametri URL per test: ?room=it apre un reparto, ?sel=<id> apre la scheda di un oggetto.
        const q = new URLSearchParams(window.location.search)
        const s = useApp.getState()
        const step = q.get('step')
        if (step === 'baseline' || step === 'packages' || step === 'forecast') {
          if (step !== 'baseline' || q.has('year')) useApp.setState({ simDone: true })
          s.setStep(step)
          if (q.has('year')) s.setMonth(null)
        }
        if (q.has('measures')) s.setShowMeasures(true)
        const goal = q.get('goal')
        if (goal) s.setGoal(goal)
        const room = q.get('room')
        if (room) s.setRoom(room)
        if (q.get('stage') === 'cloud') s.setStage('cloud')
        const sel = q.get('sel')
        if (sel) s.select(sel)
        if (q.has('flip')) s.turn(1)
      })
      .catch((e: Error) => setError(e.message))
  }, [setData])

  // L'apertura parte subito, anche mentre i dati e la scena si caricano sotto.
  return (
    <>
      <Main data={!!data} error={error} step={step} introDone={introDone} />
      <Landing />
    </>
  )
}

function Main({ data, error, step, introDone }: { data: boolean; error: string | null; step: Step; introDone: boolean }) {
  if (error) return <div className="grid h-full place-items-center text-error">{error}</div>
  if (!data) return <div className="grid h-full place-items-center text-[14px] font-medium text-muted">Loading data…</div>

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Durante l'intro niente barra: si vede solo la pianta. */}
      {introDone && <Header />}
      <Ticker />
      <main className="relative min-h-0 flex-1">
        <Scene />
        <Loading />
        <BlueprintIntro />
        <div className="pointer-events-none absolute inset-0 z-30">
          {introDone && <SceneLabels />}
          {introDone && <StepUi />}
          {introDone && <RoomTitle />}
          <ItemPanel />
          {introDone && step !== 'local_ai' && <Chat />}
          {step === 'local_ai' && <LocalAiPanel />}
        </div>
      </main>
    </div>
  )
}

function Loading() {
  const { active, progress } = useProgress()
  if (!active) return null
  return (
    <div className="pointer-events-none absolute inset-0 z-40 grid place-items-center bg-white text-[14px] font-medium text-muted">
      Loading the office… {Math.round(progress)}%
    </div>
  )
}
