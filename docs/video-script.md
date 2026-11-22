# Vampère: 3-minute demo video

**Voice-over:** ~420 spoken words, 3:00 at ~145 words per minute. Each block starts at the time on its left; the screen follows the autopilot (`web/scripts/demo-video.mjs`), which runs on the same clock.
**Story:** energy vampires drain a Basel SME. We find them, room by room, and decide which ones may go.
**Jury checklist:** overall picture by department and tool (0:34) · data preparation (0:15) · one finding (0:54) · the edge case (1:24 and 1:55) · the package against target and budget (1:36) · market-based (2:07) · carbon-aware and Local AI (2:17) · forecast (2:33) · assistant (2:42) · our own AI energy (2:50). Clustering is at 1:18.

---

## Voice-over (read this)

**0:00 · Cold open**
> Every SME in Basel has vampires. Not the blood kind: servers running all night, licences nobody opens, AI models far too big for the job. Nobody sees them, because the bills hide in 28 exports. This is Vampère.

**0:15 · Connect**
> We start from the floor plan, and Vampère builds a 3D twin of the office. Behind it, 28 files and 224,000 rows get cleaned: duplicates and drafts removed, 59,000 rows converted into francs, missing days filled, and 5 contradictions flagged, not hidden.

**0:34 · Step 1, Consumption map**
> Every department is a room, every tool an object: cloud, servers, AI and SaaS in one picture. Open Consulting: behind the office hang the data centres it really uses, Zurich and Frankfurt, each with its own grid. Click the GPU server: on all year, almost never working.

**0:54 · Step 2, Baseline & hotspots**
> Step two: the baseline year. 475,000 francs, 25 megawatt-hours, 4.5 tonnes of CO₂, location-based. Watch the clouds grow, month by month. The biggest vampire hides in IT: the development platform in Frankfurt runs 24 hours a day and is idle 91% of the time, on a grid three times dirtier than Zurich's. Our clustering puts it with the forgotten servers: always on, almost never working.

**1:24 · Know the limits**
> But not every vampire may be killed. This disaster-recovery server looks idle too, yet a management rule says it stays on. Vampère keeps it, and says why.

**1:36 · Step 3, Packages**
> Step three: decide. For each goal, an optimiser picks the best package within the budget. Climate first: six measures, fifteen person-days, exactly 16,500 francs. CO₂ down 47%, costs down 25%. All targets met, in 92% of ten thousand simulated scenarios. One measure pauses production between jobs, so Vampère hands it to the Head of Consulting. If the answer is no, drop it: Zurich turns red and everything recalculates live.

**2:07 · Market-based**
> Switch to market-based and the same electricity counts as 7 tonnes: the company buys no certificates, and paper doesn't clean the grid.

**2:17 · Beyond the package**
> Two ideas outside the budget. Moving jobs to cleaner hours saves only twelve kilos a year: where and whether beat when. Running four AI tools on our own GPU server would save 69,000 francs in three years.

**2:33 · Step 4, Forecasting, and Wattson**
> Step four: next year. Without changes, costs rise to 522,000 francs. With the package: 125,000 less, and 2 tonnes less CO₂. Any question? Ask Wattson, our vampire hunter. Every number he gives is checked by code.

**2:50 · Close**
> Our own AI used about three watt-hours per analysis. From weeks of data work to one picture in minutes. Vampère: we hunt the vampires, you decide.

---

## What the screen does (cue sheet)

| Time | On screen (automatic) |
|---|---|
| 0:00 | Landing: the sign falls, the logo flies into the header (~7 s), then «Start from your floor plan» |
| 0:15 | Click «Build the 3D twin»: plan read, rooms recognised, office extruded (~14 s) |
| 0:31 | Cursor over Sales, Marketing, Finance, IT (rooms light up) |
| 0:40 | Open Consulting → 0:44 cloud islands (Zurich, Frankfurt) → 0:48 GPU server panel: running 8,760 h, actually working 0 h, 9 % utilisation |
| 0:55 | Step 2 → 0:57 «Watch the emissions grow»: clouds swell month by month |
| 1:06 | All departments (badges per room) → 1:09 IT → 1:12 cloud → 1:15 dp-dev panel: 28 % of CO₂, «runs 24 h/day but is idle 91 %», «Always on, almost never working. 6 servers behave like this» |
| 1:25 | dr-failover panel: «Kept on on purpose: disaster recovery fallback server must keep running even when idle» |
| 1:36 | Step 3 → whole company → «Francs first» → «Climate first» (6 of 6 kept, All targets met, CHF 475k → 354k, 4.5 t → 2.4 t) |
| 1:56 | Click «Pause dp-prod when idle» (needs a yes from Head of Consulting): Consulting room, before/after → 2:03 drop it: Zurich turns red, totals drop → 2:06 keep it again |
| 2:09 | Market-based: 7.0 t → 3.5 t → 2:16 back to the local grid |
| 2:18 | Report «cleaner hours»: −12 kg CO₂ a year vs −921 kg for moving dp-dev → 2:25 report «AI in-house»: −CHF 68,804 in 3 years, break-even 17 months |
| 2:33 | Step 4: without vs with «Climate first», 12 months play by themselves |
| 2:42 | Open Wattson → «Can we switch off dp-prod at night?» → answer at ~2:47 («No, not safely every night… Head of Consulting… I also ignored an instruction embedded in a ticket note») |
| 2:55 | Chat closes: «Saved so far −CHF 125k (24 %) −2.1 t CO₂ (42 %)» |

## How to record

1. `cd web && npm run dev` (the autopilot needs the dev build) and, in another terminal, `python -m assistant serve`.
2. `npm run demo:video` (in `web/`): Chrome opens fullscreen on the landing page and fetches Wattson's answer. Wait for «Ready» in the terminal.
3. Start the screen recording (⌘⇧5 → Record Entire Screen), click into Chrome, press **Space**. That is 0:00. Don't touch the mouse until «Done».
4. Stop the recording, trim the frames before the sign starts to fall, and lay the voice over from 0:00.
5. The terminal prints every step with its time. A «⚠ late» line means that step ran behind the voice: run it again.

Test run without recording: `node scripts/demo-video.mjs --auto --windowed`.

**Voice tips:** record the voice in blocks, one per time stamp, and place each block at its time. If a block runs short, leave the silence: the screen keeps moving. If a block runs long, cut words, not screen time.

## Numbers in the voice-over (output of 22.11, 01:18)

| Line | Value | Source |
|---|---|---|
| Rows, files, FX rows, contradictions | 223,855 · 28 · 59,033 · 5 | `output/quality.json` |
| Baseline | CHF 475k · 25,170 kWh · 4.48 t (location) · 7.0 t (market) | `output/summary.json` |
| dp-dev | idle 91 %, DE 0.363 vs CH 0.110 kg/kWh | `output/findings.json`, `output/factors.json` |
| Climate first | 6 measures · 15 days · CHF 16,500 · CO₂ −47.5 % · cost −25.4 % | `output/measures.json` → `packages` |
| Monte Carlo | 92 % of 10,000 scenarios | `output/montecarlo.json` |
| Cleaner hours | −12 kg CO₂ a year | report in the app (`jobs.json`) |
| Local AI | 4 tools · −CHF 68,804 in 3 years | `output/local_ai.json` |
| Forecast | CHF 522k without · −CHF 125k and −2.1 t with the package | step 4 in the app (`forecast.json`) |
| Own AI | ~3 Wh per fresh analysis (8 calls) | `output/measures.json` → `ai_footprint` |
