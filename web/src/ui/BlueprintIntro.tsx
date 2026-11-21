import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { DEPT_ACCENT } from '../data/twin'
import { BLUEPRINT_URL, BUILD_S, LAND_S, SCAN_S, useIntro, type BlueprintMeta, type PaperRect } from '../intro/store'
import { loadBlueprintMeta, BUILD_ORDER } from '../scene/twin/BlueprintBuild'

const LOG_W = 360
const ASPECT = 59.4 / 42
const SAMPLE_NAME = 'A-101_Floor-plan_Level-01.svg'

/** Passi della «lettura» della pianta: [inizio, fine] in secondi dall'inizio della scansione. */
const STEPS: { at: [number, number]; title: string; detail: (m: BlueprintMeta) => string }[] = [
  { at: [0.2, 2.7], title: 'Vectorising linework', detail: (m) => `${(m.counts.wall_segments + m.counts.glass_segments).toLocaleString('en')} edges traced` },
  { at: [0.9, 1.6], title: 'Reading scale bar & north', detail: () => '1:100 on A2 · north up' },
  { at: [1.6, 2.9], title: 'Walls & glazing', detail: (m) => `cut at +${m.cut.toFixed(2)} m · ${m.counts.wall_segments} wall, ${m.counts.glass_segments} glass edges` },
  {
    at: [2.9, 4.3],
    title: 'Rooms recognised',
    detail: (m) => `${Object.keys(m.rooms).length} spaces · ${Math.round(Object.values(m.rooms).reduce((a, r) => a + r.area, 0)).toLocaleString('en')} m²`,
  },
  { at: [4.3, 5.4], title: 'Matching module library', detail: (m) => `${m.counts.workstations} workstations → desk_bench · ${m.counts.furniture} fixtures` },
  { at: [5.4, SCAN_S], title: 'Extruding to 3D', detail: () => 'walls 2.6 m · floors · plinth' },
]

function fitRect(w: number, h: number): PaperRect {
  const aw = w - LOG_W - 96
  const ah = h - 96
  const width = Math.min(aw, ah * ASPECT)
  const height = width / ASPECT
  return { left: 48 + (aw - width) / 2, top: 48 + (ah - height) / 2, width, height }
}

/** Intro scenica «planimetria → gemello 3D». La pianta è ricavata dal modello (web/scripts/make-floorplan.py). */
export function BlueprintIntro() {
  const phase = useIntro((s) => s.phase)
  if (phase === 'done') return null
  return phase === 'upload' ? <Upload /> : <Reading />
}

// ---------------------------------------------------------------------------------------------------------
function Upload() {
  const start = useIntro((s) => s.start)
  const skip = useIntro((s) => s.skip)
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  return (
    <div
      className="pointer-events-auto absolute inset-0 z-50 grid place-items-center bg-white"
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const f = e.dataTransfer.files[0]
        if (f) start(f.name)
      }}
    >
      <button onClick={skip} className="absolute top-5 right-8 text-[14px] font-medium text-muted hover:text-ink">
        Skip intro
      </button>

      <div className="flex w-[min(880px,92vw)] flex-col items-center text-center">
        <p className="text-[13px] font-semibold tracking-[0.12em] text-primary uppercase">Digital twin setup</p>
        <h1 className="mt-3 text-[36px] leading-tight font-semibold tracking-[-0.6px] text-ink">Start from your floor plan</h1>
        <p className="mt-3 max-w-[560px] text-[16px] text-muted">
          Upload an architectural plan. GreenOps reads walls, rooms and workstations and builds the 3D office from its module library.
        </p>

        <div
          onClick={() => input.current?.click()}
          className={`mt-9 flex w-full cursor-pointer flex-col items-center rounded-[var(--radius-lg)] border-2 border-dashed px-8 py-10 transition ${
            over ? 'border-primary bg-primary-soft' : 'border-hairline hover:border-muted-soft hover:bg-surface-soft'
          }`}
        >
          <svg viewBox="0 0 48 48" className={`h-12 w-12 ${over ? 'text-primary' : 'text-muted-soft'}`} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M8 34v6h32v-6" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M24 30V8m0 0-8 8m8-8 8 8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <p className="mt-4 text-[18px] font-semibold text-ink">{over ? 'Release to import' : 'Drop a floor plan here'}</p>
          <p className="mt-1 text-[14px] text-muted">DWG · DXF · PDF · SVG · PNG — or click to browse</p>
          <input
            ref={input}
            type="file"
            accept=".dwg,.dxf,.pdf,.svg,.png,.jpg,.jpeg"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) start(f.name)
            }}
          />
        </div>

        <div className="mt-6 flex w-full items-center gap-4 text-[13px] text-muted-soft">
          <span className="h-px flex-1 bg-hairline" />
          or try the sample
          <span className="h-px flex-1 bg-hairline" />
        </div>

        <div className="pill-shadow mt-6 flex w-full items-center gap-5 rounded-[var(--radius-md)] bg-white p-3 text-left">
          <img src={BLUEPRINT_URL} alt="Sample floor plan A-101" className="h-[92px] w-[130px] rounded-[var(--radius-sm)] border border-hairline-soft object-cover" />
          <div className="min-w-0 flex-1">
            <p className="text-[16px] font-semibold text-ink">A-101 · Floor plan · Level 01</p>
            <p className="mt-0.5 text-[14px] text-muted">Basel head office · 1:100 on A2 · as built</p>
          </div>
          <a
            href={BLUEPRINT_URL}
            download={SAMPLE_NAME}
            onClick={(e) => e.stopPropagation()}
            className="rounded-full border border-hairline px-4 py-2.5 text-[14px] font-medium text-ink hover:bg-surface-soft"
          >
            Download
          </a>
          <button onClick={() => start(SAMPLE_NAME)} className="rounded-full bg-primary px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-primary-active">
            Use sample plan
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------------
function Reading() {
  const phase = useIntro((s) => s.phase)
  const t0 = useIntro((s) => s.t0)
  const fileName = useIntro((s) => s.fileName)
  const paper = useIntro((s) => s.paper)
  const next = useIntro((s) => s.next)
  const skip = useIntro((s) => s.skip)
  const root = useRef<HTMLDivElement>(null)
  const [meta, setMeta] = useState<BlueprintMeta | null>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [t, setT] = useState(0)
  const [size, setSize] = useState({ w: 1200, h: 800 })

  useEffect(() => {
    loadBlueprintMeta().then(setMeta)
    fetch(BLUEPRINT_URL)
      .then((r) => r.text())
      .then((s) => setSvg(s.replace(/width="594mm" height="420mm"/, 'width="100%" height="100%" preserveAspectRatio="none"')))
  }, [])

  useEffect(() => {
    const el = root.current
    if (!el) return
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Orologio della scena: avanza le fasi (scan → land → build) e alimenta le animazioni.
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const s = (performance.now() - t0) / 1000
      setT(s)
      if (phase === 'scan' && s > SCAN_S && meta) next('land')
      else if (phase === 'land' && s > LAND_S) next('build')
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [phase, t0, next, meta])

  const scanT = phase === 'scan' ? t : SCAN_S
  // Vettorizzazione: la scansione morbida si dissolve nella versione nitida (nessuna barra di scansione).
  const sweep = Math.min(1, Math.max(0, (scanT - 0.2) / 2.5))
  const detect = phase === 'scan' ? Math.min(1, Math.max(0, (SCAN_S - 0.5 - scanT) / 0.5)) : 0
  const fit = fitRect(size.w, size.h)
  const rect = phase === 'scan' || !paper ? fit : paper
  const html = useMemo(() => (svg ? { __html: svg } : null), [svg])

  const style: CSSProperties = {
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
    transition: phase === 'land' ? `all ${LAND_S}s cubic-bezier(0.65, 0, 0.35, 1), box-shadow ${LAND_S}s` : 'none',
    boxShadow: phase === 'scan' ? '0 24px 60px rgba(0,0,0,0.14), 0 2px 8px rgba(0,0,0,0.06)' : '0 0 0 rgba(0,0,0,0)',
  }

  return (
    <div
      ref={root}
      className="absolute inset-0 z-50 overflow-hidden"
      style={{
        background: phase === 'scan' ? '#EEF1F5' : phase === 'land' ? '#FFFFFF' : 'transparent',
        transition: `background ${LAND_S}s, opacity 0.6s`,
        opacity: phase === 'build' ? 0 : 1,
        pointerEvents: phase === 'build' ? 'none' : 'auto',
      }}
    >
      <div className="absolute" style={style}>
        {/* Scansione originale (morbida, leggermente ingiallita) e, sopra, la versione vettoriale rivelata dalla passata. */}
        <img src={BLUEPRINT_URL} alt="" className="absolute inset-0 h-full w-full" style={{ filter: 'blur(0.8px) saturate(0.55) contrast(0.75) brightness(0.92)', opacity: 1 - sweep }} />
        <img src={BLUEPRINT_URL} alt="Floor plan" className="absolute inset-0 h-full w-full" style={{ opacity: sweep }} />
        {html && (
          <div
            className="bp-detect absolute inset-0"
            style={{ opacity: detect * Math.min(1, Math.max(0, (scanT - 1.4) / 0.8)), ['--furn' as string]: Math.min(1, Math.max(0, (scanT - 4.3) / 0.4)) }}
            dangerouslySetInnerHTML={html}
          />
        )}
        {meta && <RoomsOverlay meta={meta} t={scanT} fade={detect} />}
      </div>

      {phase === 'scan' && meta && <Log meta={meta} t={t} fileName={fileName} />}

      {phase !== 'build' && (
        <button onClick={skip} className="absolute top-5 right-8 z-10 text-[14px] font-medium text-muted hover:text-ink">
          Skip
        </button>
      )}
    </div>
  )
}

/** Locali riconosciuti: riquadri colorati con nome e superficie, uno dopo l'altro. */
function RoomsOverlay({ meta, t, fade }: { meta: BlueprintMeta; t: number; fade: number }) {
  const p = meta.paper
  const order = [...BUILD_ORDER, 'entry_gallery'].filter((r) => meta.rooms[r])
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox={`${p.x} ${p.z} ${p.w} ${p.h}`} preserveAspectRatio="none" style={{ opacity: fade }}>
      {order.map((r, i) => {
        const room = meta.rooms[r]
        const k = Math.min(1, Math.max(0, (t - 2.9 - i * 0.13) / 0.35))
        if (k <= 0) return null
        const color = DEPT_ACCENT[r] ?? '#8C9AA6'
        const [x0, z0] = room.min
        const [x1, z1] = room.max
        const label = `${room.name} · ${Math.round(room.area)} m²`
        const w = 0.27 * label.length + 0.6
        return (
          <g key={r} style={{ opacity: k }}>
            <rect x={x0 + 0.12} y={z0 + 0.12} width={x1 - x0 - 0.24} height={z1 - z0 - 0.24} fill={color} fillOpacity={0.16} stroke={color} strokeWidth={0.14} rx={0.25} />
            <g transform={`translate(${x0 + 0.45} ${z0 + 0.45})`}>
              <rect width={w} height={0.95} rx={0.47} fill={color} />
              <text x={w / 2} y={0.64} fontSize={0.46} textAnchor="middle" fill="#fff" fontWeight={700} fontFamily="Inter Variable, Inter, sans-serif">
                {label}
              </text>
            </g>
          </g>
        )
      })}
    </svg>
  )
}

function Log({ meta, t, fileName }: { meta: BlueprintMeta; t: number; fileName: string | null }) {
  const progress = Math.min(1, t / SCAN_S)
  return (
    <aside className="pill-shadow absolute top-12 right-12 flex flex-col rounded-[var(--radius-lg)] bg-white p-6" style={{ width: LOG_W - 48 }}>
      <p className="text-[12px] font-semibold tracking-[0.12em] text-primary uppercase">Reading floor plan</p>
      <p className="mt-1 truncate text-[15px] font-semibold text-ink" title={fileName ?? ''}>
        {fileName}
      </p>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-strong">
        <div className="h-full rounded-full bg-primary" style={{ width: `${progress * 100}%` }} />
      </div>
      <ol className="mt-5 flex flex-col gap-4">
        {STEPS.map((s) => {
          const state = t < s.at[0] ? 'todo' : t < s.at[1] ? 'doing' : 'done'
          return (
            <li key={s.title} className="flex gap-3" style={{ opacity: state === 'todo' ? 0.4 : 1, transition: 'opacity .3s' }}>
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center">
                {state === 'done' ? (
                  <svg viewBox="0 0 20 20" className="h-5 w-5 text-primary" aria-hidden>
                    <circle cx="10" cy="10" r="10" fill="currentColor" />
                    <path d="m6 10.5 2.6 2.5L14 7.5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : state === 'doing' ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-disabled border-t-primary" />
                ) : (
                  <span className="h-2 w-2 rounded-full bg-muted-soft" />
                )}
              </span>
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-ink">{s.title}</p>
                {state !== 'todo' && <p className="text-[13px] text-muted">{s.detail(meta)}</p>}
              </div>
            </li>
          )
        })}
      </ol>
      <p className="mt-5 text-[12px] text-muted-soft">Build takes ~{Math.round(BUILD_S)} s · modules from the GreenOps asset library</p>
    </aside>
  )
}
