#!/usr/bin/env node
/**
 * Demo video autopilot: drives the app click by click, on the same clock as the voice-over (docs/video-script.md).
 *
 *   cd web && npm run dev                      # app on :5173 (dev build: exposes window.__vampere)
 *   python -m assistant serve                  # Wattson on :8787 (optional: the answer is fetched once, before the start)
 *   node scripts/demo-video.mjs                # Chrome fullscreen; press SPACE in Chrome to start (t = 0)
 *
 * Options:
 *   --auto        start by itself 3 s after loading (for test runs)
 *   --windowed    normal window instead of fullscreen (for test runs)
 *   --url <u>     app address (default http://localhost:5173/)
 *   --shots <dir> save a screenshot ~1 s after each step (to check a run without watching it)
 *
 * The OS pointer is hidden on the page; a drawn cursor follows the (real, trusted) mouse events, with a click ripple.
 * Objects in the 3D scene are found by asking the scene itself (hover hit test), so the clicks land on any screen size.
 */
import { chromium } from 'playwright-core'

const args = process.argv.slice(2)
const flag = (f) => args.includes(f)
const opt = (f, d) => (args.includes(f) ? args[args.indexOf(f) + 1] : d)
const URL_APP = opt('--url', 'http://localhost:5173/')
const ASSISTANT = 'http://localhost:8787/api/chat'
const CHAT_Q = 'Can we switch off dp-prod at night?'
const CHAT_DELAY_MS = 2800
const SHOTS = opt('--shots', null)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ---------------------------------------------------------------- page-side helpers (cursor, hit test)
const INIT = () => {
  const css = `
    html, body, * { cursor: none !important; }
    #demo-cursor { position: fixed; left: 0; top: 0; z-index: 2147483647; pointer-events: none; will-change: transform;
      filter: drop-shadow(0 2px 3px rgba(0,0,0,.35)); }
    .demo-ripple { position: fixed; z-index: 2147483646; pointer-events: none; width: 44px; height: 44px; margin: -22px 0 0 -22px;
      border-radius: 50%; border: 3px solid rgba(232,60,60,.85); animation: demo-ripple .5s ease-out forwards; }
    @keyframes demo-ripple { from { transform: scale(.3); opacity: 1 } to { transform: scale(1.4); opacity: 0 } }`
  const mount = () => {
    if (document.getElementById('demo-cursor')) return
    const s = document.createElement('style')
    s.textContent = css
    document.head.appendChild(s)
    const c = document.createElement('div')
    c.id = 'demo-cursor'
    c.innerHTML =
      '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2.5l15.5 9.2-6.6 1.6 3.9 7.1-2.9 1.6-3.9-7.2L5 19.7z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>'
    c.style.transform = `translate(${innerWidth / 2}px, ${innerHeight / 2}px)`
    document.body.appendChild(c)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount)
  else mount()

  window.__demoMouse = [innerWidth / 2, innerHeight / 2]
  const move = (e) => {
    if (!e.isTrusted) return // the hit test below sends synthetic events: the cursor must not jump
    window.__demoMouse = [e.clientX, e.clientY]
    const c = document.getElementById('demo-cursor')
    if (c) c.style.transform = `translate(${e.clientX - 3}px, ${e.clientY - 2}px)`
  }
  addEventListener('pointermove', move, true)
  addEventListener('mousemove', move, true)
  addEventListener(
    'pointerdown',
    (e) => {
      if (!e.isTrusted) return
      const r = document.createElement('div')
      r.className = 'demo-ripple'
      r.style.left = `${e.clientX}px`
      r.style.top = `${e.clientY}px`
      document.body.appendChild(r)
      setTimeout(() => r.remove(), 600)
    },
    true,
  )

  /**
   * Where is a 3D object on screen? Sweep synthetic pointer moves over the canvas and read the scene's hover id.
   * Runs in small chunks, each ending back at the real mouse position, so no hover highlight ever reaches a frame.
   */
  window.__demoLocate = async (id, stepPx = 7) => {
    const app = window.__vampere?.app
    const cv = document.querySelector('canvas')
    if (!app || !cv) return null
    const r = cv.getBoundingClientRect()
    const ev = (x, y) => new PointerEvent('pointermove', { clientX: x, clientY: y, bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, view: window })
    const pts = []
    for (let y = r.top + 40; y < r.bottom - 10; y += stepPx) for (let x = r.left + 10; x < r.right - 10; x += stepPx) pts.push([x, y])
    const hits = []
    for (let i = 0; i < pts.length; i += 350) {
      for (const [x, y] of pts.slice(i, i + 350)) {
        cv.dispatchEvent(ev(x, y))
        if (app.getState().hoverId === id) hits.push([x, y])
      }
      cv.dispatchEvent(ev(...window.__demoMouse))
      await new Promise((res) => requestAnimationFrame(res))
    }
    if (!hits.length) return null
    // Centre of the hits, snapped to the hit nearest to it (objects are not always convex).
    const cx = hits.reduce((a, h) => a + h[0], 0) / hits.length
    const cy = hits.reduce((a, h) => a + h[1], 0) / hits.length
    return hits.reduce((b, h) => (Math.hypot(h[0] - cx, h[1] - cy) < Math.hypot(b[0] - cx, b[1] - cy) ? h : b))
  }
}

// ---------------------------------------------------------------- browser
const browser = await chromium.launch({
  channel: 'chrome',
  headless: false,
  ignoreDefaultArgs: ['--enable-automation'],
  args: [flag('--windowed') ? '--window-size=1512,945' : '--start-fullscreen', '--hide-scrollbars', '--autoplay-policy=no-user-gesture-required', '--disable-features=Translate'],
})
const context = await browser.newContext({ viewport: null, deviceScaleFactor: undefined })
await context.addInitScript(INIT)
const page = await context.newPage()

// Wattson: the real answer, fetched once now, then served after a fixed delay so the timing never depends on the model.
let chatAnswer = null
try {
  const r = await fetch(ASSISTANT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: CHAT_Q, history: [] }) })
  if (r.ok) chatAnswer = await r.json()
  console.log(chatAnswer ? '✓ Wattson answer ready' : `! Wattson answered ${r.status}: the live answer will be used`)
} catch {
  console.log('! Wattson is not running (python -m assistant serve): the chat will show the offline message')
}
await page.route('**/api/chat', async (route) => {
  if (!chatAnswer) return route.continue()
  await sleep(CHAT_DELAY_MS)
  await route.fulfill({ json: chatAnswer })
})

await page.goto(URL_APP)
await page.waitForFunction(() => window.__vampere?.app.getState().data, null, { timeout: 60000 })
// Let the 3D models load under the landing page.
await page.waitForFunction(() => !document.body.innerText.includes('Loading the office'), null, { timeout: 60000 }).catch(() => {})
await sleep(1500)

// ---------------------------------------------------------------- mouse
let mouse = [0, 0]
mouse = await page.evaluate(() => window.__demoMouse)
await page.mouse.move(...mouse)

const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
async function glide(x, y, ms = 550) {
  const [x0, y0] = mouse
  const n = Math.max(1, Math.round(ms / 16))
  const start = Date.now()
  for (let i = 1; i <= n; i++) {
    const k = ease(i / n)
    await page.mouse.move(x0 + (x - x0) * k, y0 + (y - y0) * k)
    const due = start + (ms * i) / n - Date.now()
    if (due > 0) await sleep(due)
  }
  mouse = [x, y]
}
async function clickAt(x, y, ms) {
  await glide(x, y, ms)
  await sleep(70)
  await page.mouse.down()
  await sleep(60)
  await page.mouse.up()
}
async function box(locator) {
  const l = locator.first()
  await l.waitFor({ state: 'visible', timeout: 8000 })
  // Hidden inside a scrolling panel (e.g. the package list)? Scroll it into view, smoothly, before pointing at it.
  const hidden = await l.evaluate((el) => {
    const r = el.getBoundingClientRect()
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
    if (hit && (el === hit || el.contains(hit))) return false
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    return true
  })
  if (hidden) await sleep(550)
  const b = await l.boundingBox()
  return [b.x + b.width / 2, b.y + b.height / 2]
}
async function click(locator, ms) {
  const [x, y] = await box(locator)
  await clickAt(x, y, ms)
}
async function hover(locator, ms = 700) {
  const [x, y] = await box(locator)
  await glide(x, y, ms)
}
/** Click an object of the 3D scene by its id (e.g. island:dp-dev); if the hit test misses, select it through the store. */
async function clickObject(id) {
  const p = await page.evaluate((i) => window.__demoLocate(i), id)
  if (p) {
    await glide(p[0], p[1], 650)
    const ok = await page.evaluate((i) => window.__vampere.app.getState().hoverId === i, id)
    if (ok) {
      await sleep(70)
      await page.mouse.down()
      await sleep(60)
      await page.mouse.up()
      return
    }
  }
  console.log(`  ! ${id}: not hit on screen, selected through the store`)
  await page.evaluate((i) => window.__vampere.app.getState().select(i), id)
}
const btn = (name) => page.getByRole('button', { name })
const visible = (l) => l.filter({ visible: true })
const scrollPanel = (where) =>
  page.evaluate((w) => {
    const el = document.querySelector('.scroll-thin.overflow-y-auto')
    el?.scrollTo({ top: w === 'top' ? 0 : el.scrollHeight, behavior: 'smooth' })
  }, where)
const closeReport = (title) =>
  click(
    page
      .locator('div')
      .filter({ has: page.locator('h2', { hasText: title }) })
      .filter({ has: btn('Close') })
      .last()
      .getByRole('button', { name: 'Close', exact: true }),
  )

// ---------------------------------------------------------------- timeline (seconds from the start, = voice-over clock)
const T = [
  // 0:00 · Cold open (landing animation, ~7 s, then the floor-plan screen)
  [13.4, 'move to «Build the 3D twin»', () => hover(btn(/Build the 3D twin/), 1000)],
  // 0:15 · Connect
  [15.0, 'build the twin', () => click(btn(/Build the 3D twin/), 200)],
  [29.0, 'wait for the 3D office', () => page.waitForFunction(() => window.__vampere.intro.getState().phase === 'done', null, { timeout: 30000 })],
  [31.0, 'hover Sales', () => hover(btn(/^Sales/), 900)],
  [33.0, 'hover Marketing', () => hover(btn(/^Marketing/), 800)],
  [35.0, 'hover Finance', () => hover(btn(/^Finance/), 900)],
  [37.2, 'hover IT', () => hover(btn(/^IT/), 800)],
  // 0:34 · Step 1, Consumption map
  [40.5, 'open Consulting', () => click(btn(/^Consulting/), 800)],
  [43.6, 'cloud stage', () => click(btn(/Cloud infrastructure/), 700)],
  [48.3, 'click the GPU server', () => clickObject('island:gpu-ml')],
  [53.6, 'close the panel', () => click(visible(page.getByRole('button', { name: 'Close', exact: true })), 500)],
  // 0:54 · Step 2, Baseline & hotspots
  [54.6, 'step 2', () => click(btn(/Baseline & hotspots/), 600)],
  [56.6, 'watch the year', () => click(btn(/Watch the emissions grow/), 600)],
  [66.0, 'all departments', () => click(btn(/All departments/), 700)],
  [69.0, 'open IT', () => click(btn(/^IT/), 800)],
  [72.0, 'cloud stage', () => click(btn(/Cloud infrastructure/), 700)],
  [74.6, 'click dp-dev', () => clickObject('island:dp-dev')],
  // 1:24 · Know the limits: the disaster-recovery server
  [85.0, 'click dr-failover', () => clickObject('island:dr-failover')],
  // 1:36 · Step 3, Packages
  [96.2, 'step 3', () => click(btn(/^3\s*Packages/), 600)],
  [98.0, 'all departments', () => click(btn(/All departments/), 700)],
  [100.0, 'open «Francs first»', () => click(page.locator('button', { hasText: 'Most money saved within the budget' }), 700)],
  [103.5, 'open «Climate first»', () => click(page.locator('button', { hasText: 'Most CO₂ cut within the budget' }), 700)],
  [104.6, 'panel to the top', () => scrollPanel('top')],
  [109.0, 'point at «All targets met»', () => hover(page.getByText('All targets met'), 700)],
  [116.0, 'focus the dp-prod measure', () => click(page.locator('button', { hasText: 'Pause dp-prod when idle' }), 700)],
  [122.6, 'drop it', () => click(page.locator('li', { hasText: 'Pause dp-prod when idle' }).getByRole('button', { name: 'Drop this measure' }), 600)],
  [126.0, 'keep it again', () => click(page.locator('li', { hasText: 'Pause dp-prod when idle' }).getByRole('button', { name: 'Keep this measure' }), 400)],
  // 2:07 · market-based
  [127.6, 'all departments', () => click(btn(/All departments/), 600)],
  [129.2, 'market-based', () => click(visible(btn(/^Market-based$/)), 700)],
  [135.6, 'back to the local grid', () => click(visible(btn(/^Local grid$/)), 500)],
  // 2:17 · Beyond the package
  [136.6, 'panel to the bottom', () => scrollPanel('bottom')],
  [138.0, 'open «cleaner hours»', () => click(page.locator('section', { hasText: 'Run jobs in cleaner hours?' }).getByRole('button', { name: 'Open the report' }), 600)],
  [144.4, 'close it', () => closeReport('When it runs')],
  [145.4, 'open «AI in-house»', () => click(page.locator('section', { hasText: 'Run our AI tools in-house?' }).getByRole('button', { name: 'Open the report' }), 600)],
  [152.0, 'close it', () => closeReport('Running our AI tools in-house')],
  // 2:33 · Step 4, Forecasting (plays by itself, ~8 s)
  [153.2, 'step 4', () => click(btn(/Forecasting/), 600)],
  [157.0, 'point at the package side', () => hover(page.getByText(/With «/), 900)],
  // 2:42 · Wattson
  [161.6, 'open Wattson', () => click(btn('Ask Wattson'), 800)],
  [163.6, 'ask about dp-prod', () => click(page.locator('button', { hasText: CHAT_Q }), 600)],
  // 2:50 · Close
  [175.0, 'close the chat', () => click(page.locator('div.h-\\[540px\\]').getByRole('button', { name: 'Close', exact: true }), 600)],
  [176.5, 'point at «Saved so far»', () => hover(page.getByText('Saved so far'), 900)],
  [180.0, 'end', async () => {}],
]

// ---------------------------------------------------------------- start
if (flag('--auto')) {
  console.log('Starting in 3 s…')
  await sleep(3000)
  const [x, y] = await box(page.locator('video'))
  await clickAt(x, y, 500)
} else {
  console.log('\nReady. Start the screen recording, then press SPACE in Chrome (the landing starts and the clock with it).\n')
}
await page.waitForFunction(() => {
  const v = document.querySelector('video')
  return !v || (!v.paused && v.currentTime > 0)
}, null, { timeout: 0, polling: 50 })
const t0 = Date.now()
console.log('▶ t = 0')

const clock = () => (Date.now() - t0) / 1000
const fmt = (s) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`
const late = []
for (const [t, label, fn] of T) {
  const wait = t - clock()
  if (wait > 0) await sleep(wait * 1000)
  const lag = clock() - t
  if (lag > 0.4) late.push(`${label} (+${lag.toFixed(1)} s)`)
  console.log(`${fmt(clock())}  ${label}${lag > 0.4 ? `   ⚠ ${lag.toFixed(1)} s late` : ''}`)
  try {
    await fn()
  } catch (e) {
    console.log(`  ✗ ${label}: ${e.message.split('\n')[0]}`)
  }
  if (SHOTS) {
    const name = `${SHOTS}/${String(Math.round(t * 10)).padStart(4, '0')}-${label.replace(/[^a-z0-9]+/gi, '_')}.png`
    setTimeout(() => page.screenshot({ path: name }).catch(() => {}), 900)
  }
}
console.log(late.length ? `\nDone, with delays: ${late.join(' · ')}` : '\nDone, every step on time.')
console.log('Stop the recording. Ctrl+C closes Chrome.')
await new Promise(() => {})
