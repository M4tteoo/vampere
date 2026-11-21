# Checklist · after Step 6 (and 7–8) are done

The bonus modules were built before measures, limits and the package existed. Some of them work on placeholders or rough estimates until then. When `output/measures.json` (Step 6), `output/limits.json` (Step 7) and the package (Step 8) exist, go through this list and tick each item.

Order: **0 → 1 → 2 → 3 → 4 → 5**, then the final run in **6**.

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
