# Checklist · after Step 6 (and 7–8) are done

The bonus modules were built before measures, limits and the package existed. Some of them work on placeholders or rough estimates until then. When `output/measures.json` (Step 6), `output/limits.json` (Step 7) and the package (Step 8) exist, go through this list and tick each item.

Order: **0 → 1 → 2 → 3 → 4 → 5**, then the final run in **6**.

## Status · re-checked on 2026-11-21 after commit 667c261 ("fast advisor: toolbox, parallel agents, optimiser")

The advisor is now code-driven: a toolbox of levers, 4 area agents and an exact optimiser with 3 goals. It is still checked by the same calculator and gate. Our modules were adapted to it, and its code was not changed (details: `docs/extra-sources.md`, section 4).

| Check | Result |
|---|---|
| Offline run reproduces the committed analysis | ✅ reused answers, 0 AI calls; 29 findings, 33 measures, 16 limits; «climate first» CO₂ −50.4 %, cost −25.4 %, 15.0 d |
| Package model (B1 + B2) | ✅ reproduces all 3 goal packages of the Calculator at low / mid / high |
| Monte Carlo | ✅ 99.9 % (median −47.9 %), `by_goal` for all goals on the same draws |
| Swiss switch | ✅ every goal meets the target under both mixes, also at the least favourable factors |
| Carbon-aware after the package | ✅ 13.2 kg CO₂/yr (dp-dev and dp-prod paused by M-01 / M-03); budget read from `advisor.budget_chf` |
| Assistant | ✅ sees the goals, «kept on» and analysis info; attack suite 31/31 |
| Tests | ✅ unit tests 35/35, audit 0 contract problems and 62/62 number checks, red-team 8 structural checks |
| Open point (for the advisor owner) | Power BI hygiene, closed projects and M365 facts reach no agent: no toolbox lever touches those resources. Shown as insight cards; a Power BI lever is a suggestion |

The table below is the earlier check (AI-only advisor), kept for the record; its figures are superseded.

## Status · checked on 2026-11-21 after commit f423146 ("switch steps 5–8 to LLM advisor")

Steps 5–8 now come from the LLM advisor (`pipeline/advisor/`). Result of this checklist:

| § | Check | Result |
|---|---|---|
| 0 | Pipeline runs offline, all bonus modules ok, files follow the contract | ✅ 6 findings, 8 measures, 17 limits; package CO₂ −40.1%, cost −27.1%, 15.0 d (CHF 16,500) |
| 1 | Clustering candidate F-CL-C-2 | ✅ not merged: covered by the advisor's F-03 (dp-dev) and F-04 (non-production compute) |
| 1 | Carbon-aware candidate M-CA | ✅ recomputed **on top of the package** (`jobs.json` → `after_package`): dp-dev paused and moved to Zurich by M-01, dp-prod still 24/7 → **8.2 kg CO₂/yr (2.2–21.0)**. Not in the package: the budget is fully used (15.0 of 15 d) |
| 2 | Carbon-aware vs limits | ✅ now also reads the time-bounded windows of the advisor constraints (finance closing 00:00–04:00 on the last 3 working days, C-01 / L-01); no job lands in them |
| 3 | Pitch notes | ✅ updated: M-01 1,182 kg, M-02 345 kg, carbon-aware 8.2 kg (≈140× smaller), clustering 54%, attack suite 26/26, AI energy so far |
| 4 | Assistant | ✅ reads measures / package / limits; measures overview made compact (55k → 9k chars); **26/26** (new: package target, blocked backup deletion, planted fake approval of the blocked DR shutdown) |
| 4 | Advisor red-team (`python -m pipeline.advisor.redteam --llm`) | ✅ 6 structural + 3 live attacks passed |
| 4 | Limit quotes | ✅ fixed in `pipeline/advisor/apply.py`: `quote_risk` now takes the **worst** verdict of title and description (before: the first one, so a clean title could vouch for an injected description), and `ambiguous` → `ok` (contract enum) |
| 5 | Energy of our AI | ⏳ one laptop so far: 499 calls ≈ 96 Wh (19–385), ≈ 20 g CO₂. **Missing: the advisor runs (on the machine that ran `--advisor`) and the coding assistants** |

**Open points for the Steps 5–8 owner:**
1. **The CO₂ target is met only at mid:** −40.1% (target 40%). With pessimistic factors it's −34.7% (`package.meets_at_low.co2 = false`). The Monte Carlo (track 1) should show how likely −40% is. A little more CO₂ margin would make the pitch safer.
2. **`package.reduction` ranges are stored inverted** (`co2`: low 0.56 > mid 0.40 > high 0.35). The contract expects low ≤ mid ≤ high (or document that «low» = low factors).
3. **L-06** (pbi-07 audit block) points to `res:pbi-07`, which is not in `entities.json`, so the scene can't draw that lock.
4. **dr-failover owner mismatch:** L-04 says `decided_by: Head of Management`, M-08 says `owner_role: Head of IT`. The assistant reports both.
5. **`answers.json` only has question 1.** Questions 2 and 3 are answered by the assistant (verified) but not exported.
6. Cosmetic: some licence `energy_share` values are 1e-16 instead of 0 (floating-point noise) in `measures.json` → `effects`.

---

## 0 · Regenerate everything first

- [ ] `git pull`, then `.venv/bin/python -m pipeline.run`. All bonus modules must print `ok`: `text_risk`, `clusters`, `carbon_aware` (plus track 1: `market`, `scenarios`, `forecast`, `montecarlo`).
- [ ] `output/measures.json` and `output/limits.json` exist and follow `contract/types.ts` (`MeasuresFile`, `LimitsFile`).

## 1 · Merge the bonus candidates into Steps 5–6

Bonus modules only *propose* findings and measures, in `output/bonus/candidates.json`. The Step 5/6 owner decides what to merge.

- [ ] **Clustering finding `F-CL-C-2`** ("6 machines always on at 0.1–9.2 % average load"). It overlaps F-10 (dp-dev idle) and F-12 (GPU 9%). Either drop it, or keep it as the summary finding that links them. Never count its impact on top of theirs.
- [ ] **Carbon-aware measure `M-CA`** (1 person-day, CO₂ only, CHF 0). Merge it into `measures.json` or leave it out. If it's merged, check all of the following, because **measures must be additive** (contract rule 10):
  - [ ] **Relocation:** if the package moves **dp-dev to Zurich**, the dp-dev jobs no longer run on the Frankfurt grid. Recompute M-CA with dp-dev on CH, i.e. change its location before `carbon_aware.run`. Otherwise M-CA claims savings that the relocation already took.
  - [ ] **Energy basis:** M-CA uses the **"full"** basis (13.2 kg), which assumes the clusters auto-pause. If the auto-pause measures (M1 dp-dev, M7 dp-prod) are **not** in the package, use the **"marginal"** basis (5.7 kg) instead: `totals.marginal.saving_dynamic` in `output/jobs.json`.
  - [ ] Fill in the real `finding_ids`, `limit_ids`, `owner_role` and `start_date` (currently placeholders in `pipeline/bonus/carbon_aware.py`, `_measure`).
  - [ ] The quarterly model training stays **"needs human"** (T-1053, T-1101). If Step 7 makes it a limit, link that limit id.

## 2 · Carbon-aware: use the Step 7 limits instead of our own list

- [ ] `carbon_aware.py` derives protected hours from the **fixed jobs** in `data_platform_jobs.csv`. Compare with `limits.json` (`type: window`, `occurrences`):
  - [ ] Finance closing **until 04:00 on the last 3 working days** (T-1029). Our job-based blocking only covers the month-end close job (18:00, about 10 h). Make sure flexible dp-prod jobs don't land in 00:00–04:00 on those days. Today they move to 17:00, which is fine, but check again if the logic changes.
  - [ ] Quarter days 1–3 for dp-dev and the GPU (T-1053, T-1101).
  - [ ] vm-test change freeze in March 2026 (T-1204). It doesn't affect our jobs today, but it should appear if a vm-test job ever becomes flexible.
- [ ] If they differ, read `limits.json` in `carbon_aware.py` (`_blocked`) so both use one source of truth.

## 3 · Pitch notes: replace estimates with the final figures

File: `docs/pitch-notes.md`

- [ ] **"dp-dev in Zurich ≈ 860 kg CO₂/yr"**: my rough estimate (3,411 kWh × (0.363 − 0.110)). Replace it with the CO₂ savings of the Step 6 relocation measure.
- [ ] **"dp-dev idle time ≈ 1,130 kg/yr"** comes from finding F-10. Replace it with the savings of the auto-pause measure (M1) if they differ, and update the **"≈ 85×"** ratio (= measure savings ÷ M-CA savings).
- [ ] **Carbon-aware numbers** (13.2 / 5.7 kg, the table): re-copy from `output/jobs.json` after the final run, and after any change from item 1.
- [ ] **Clustering:** "54% of the clustered CO₂" is `output/clusters.json` → group C-2 `share_co2`. Re-copy it.
- [ ] **Assistant:** the attack-suite score. Re-copy from `output/assistant/eval_report.json` after section 4.

## 4 · Assistant: re-test with measures and limits

- [ ] `.venv/bin/python -m assistant eval`: all cases pass (currently 23/23).
- [ ] **The `analysis` tool reads the real files.** Run these and check there are no errors and no empty `items`:
  ```bash
  .venv/bin/python -c "from assistant.settings import load_settings; from assistant.data import DataStore; from assistant.tools import run_tool; s=DataStore(load_settings())
  for k in ('measures','package','limits'): print(k, str(run_tool(s,'analysis',dict(kind=k,item_id=None,entity_id=None)))[:300])"
  ```
  If the field names differ from the contract (`measures`, `package`, `limits`, `entity_ids`, `quote`), adapt `analysis()` in `assistant/tools.py`.
- [ ] **Example question 2 (GPU on demand)** must now give effort and savings in CHF and CO₂. Today it correctly says "measures not available yet". In `assistant/evals/cases.yaml`, case `EX2-gpu-on-demand`, add an `expect:` on the GPU measure's savings (tool `analysis`, `kind: measures`, path to `savings.co2_kg.mid`).
- [ ] **Example question 3 (dp-prod at night)** should now cite the limits (L-xx ids) and the measure status (🧑 human). Add `must: ['L-']` or similar to `EX3-dp-prod-night`.
- [ ] Add test cases for the new data:
  - [ ] a **blocked** measure, e.g. "Can we delete the backup archive?" → must say blocked (T-1039 / T-1195) and must not recommend it.
  - [ ] the **package**: "Does the package reach −40% CO₂ and −25% cost within budget?" → `expect` on `package.reduction.co2.mid`.
  - [ ] an injection planted into a measure or limit field (`inject:`) → the measure status must not change in the answer.
- [ ] **`answers.json` vs assistant:** the Step 5 export (`output/answers.json`) and the assistant must agree on the 3 example questions. Q1 matches today (67 seats, CHF 1,223.51). Check Q2 and Q3 once they're filled.
- [ ] **Limit quotes:** Step 7 must set `Limit.quote_risk` from `free_text.text_risk` (filled by the `text_risk` module with `ok` / `ambiguous` / `flagged` / `unchecked`; the contract only knows `unchecked` / `ok` / `flagged`, so map `ambiguous` → `ok`; `flagged` → the frontend shows "[withheld]"). Check that T-1230 is never quoted as is.

## 5 · Energy of our own AI (case requirement: "Teams that use AI also estimate its energy use")

The sentence in `docs/pitch-notes.md` currently counts **only the chat assistant** (about 65 Wh, about 14 g CO₂ so far). Before the pitch, add **every** AI use:

- [ ] **One command for the total:** `.venv/bin/python -m assistant energy <every usage.jsonl you collected> [--advisor-estimate]` sums the logs with the factors below. `--advisor-estimate` adds the saved final advisor run, rebuilt from `output/advisor/`. Leave it out if the advisor runs are already in a log you pass, otherwise they are counted twice.
- [ ] **Chat assistant (A1):** `output/assistant/usage.jsonl` logs every call (development, tests, demo). It's local and git-ignored, so **each person who ran the assistant** must sum their own file.
- [ ] **The other LLM my teammate is building:** it must log its calls in the **same format**, one JSON line per call:
  ```json
  {"at": "2026-11-22T10:00:00+01:00", "model": "…", "purpose": "…", "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
  ```
  Write it to its own file (e.g. `output/<component>/usage.jsonl`) or reuse `assistant/llm.py` (class `LLM`), which already logs. **Add its total to the sentence once it's done.**
- [ ] **Free-text classifier:** included in `usage.jsonl` (purpose `classify`, 118 calls, small model).
- [ ] **AI used while building** (coding assistants, chat tools): take token counts from each tool's usage page or dashboard, per team member, and add them. This is probably the largest part.
- [ ] **Formula** (the same factors as the case, `pipeline/energy/factors.yaml` → `ai_tokens`):
  - output-equivalent tokens = output + 0.1 × (input − cached) + 0.01 × cached (× 0.25 for small models)
  - kWh = output-equivalent tokens ÷ 1000 × 0.5 Wh ÷ 1000 (range 0.1–2.0 Wh per 1,000)
  - CO₂ = kWh × 0.213 kg/kWh (EU mix; providers' data centres in the EU or the US, location unknown)
- [ ] Put the final total (range low–high) in `docs/pitch-notes.md`, the submission and the last slide.

## 6 · Final run and commit

- [ ] `.venv/bin/python -m pipeline.run` and `.venv/bin/python -m assistant eval` once more, on the final code.
- [ ] Commit only outputs that really changed (not only `generated_at`).
- [ ] Never commit `.env` (the API key): `git check-ignore .env` must print `.env`.
- [ ] No Co-Authored-By / Claude signature lines in commit messages.

---

### For track 1 (reference, owned by my teammate)
These bonuses also wait for Step 6/8. Listed so nothing is forgotten:
- market-based savings per measure → `savings_co2_kg_market_based` column of the measures template
- Swiss mix switch: package re-checked with the production mix (`output/ch_production/`)
- Monte Carlo of the package
- forecast "with package" (uses `Measure.start_date`)
- all of these are much more precise if Step 6 adds the optional `Measure.breakdown` (see `bonus-plan.md`)
