# Bonus plan · GreenOps Basel

Two people build the bonus features while the rest of the team works on the UI and on Steps 5–8 (findings, measures, limits, optimizer). Each bonus is its own module, so we can work in parallel without editing the same files.

## Scope

| Feature | Module | Status |
|---|---|---|
| A3 · Market-based CO₂ | `pipeline/bonus/market.py` | in |
| B2 · Swiss mix switch (production vs consumption) | `pipeline/bonus/scenarios.py` | in |
| A5 · Carbon-aware load shifting | `pipeline/bonus/carbon_aware.py` | in (lowest priority) |
| A4 · Clustering | `pipeline/bonus/clusters.py` | in |
| A2 · Forecast | `pipeline/bonus/forecast.py` | in |
| A1 · Chat assistant | `assistant/` (separate package) | in |
| B1 · Monte Carlo | `pipeline/bonus/montecarlo.py` (+ `pipeline/energy/linear.py`) | in |
| B3 · Every number opens / B8 · Intake log | already in place | keep: every bonus number carries a `calc` |
| A6 · CI pipelines | – | out |
| B5 · Approval queue | – | out |
| B4 · Savings calendar | – | out as its own module. The forecast uses `Measure.start_date` from Step 6 anyway |

## Ground rules

1. **One module = one file = one output.** Each module lives in `pipeline/bonus/<name>.py`, exposes `run(ctx)` and writes its own JSON to `output/`. Modules never write `findings.json`, `measures.json` or `limits.json`. Those belong to the Steps 5–8 owners.
2. **Stay out of the Step 5–8 files.** We don't edit `pipeline/export/frontend.py`, `pipeline/harmonize/*` or the Step 5–8 modules, except for the few hooks listed under "Files we touch outside our modules".
3. **Contract first.** Before coding a module, add its TypeScript type to `contract/types.ts` (section "bonus") and a sample file to `contract/examples/`. The UI team builds on the sample while we build the real file.
4. **Every number opens (B3).** Every figure in a bonus file is a `Range` and carries a `Calc` (formula, inputs, factor ids, source files, row count).
5. **No AI inside calculations.** The forecast, the clusters, the Monte Carlo and the market-based CO₂ are plain code. The LLM appears in the assistant, in the free-text classifier and in the advisor (`pipeline/advisor/`: findings, measures, limits), which reasons and designs but never computes a number: savings are computed by code.
6. **Candidates, not edits.** When a bonus produces a finding or a measure (clustering outliers, carbon-aware shifting), it writes it to `output/bonus/candidates.json` in contract `Finding` / `Measure` format. The Step 5/6 owner decides whether to merge it.

## 0 · Shared foundation (first, one person, before splitting)

**Status: done.** In practice:

- New module: create `pipeline/bonus/<name>.py` with `run(ctx)` (and/or `after_energy(ctx)`), then add `<name>` to `bonus.enabled` in `pipeline/config.yaml`.
- Iterate: `.venv/bin/python -m pipeline.bonus.dev <name>`. It loads the last run from DuckDB in about 2 s and raises errors. The full run (`python -m pipeline.run`) takes about 10 s and skips a failing module with a loud message (unless `bonus.fail_fast: true`).
- Helpers in `pipeline/bonus/common.py`:
  - `write_json`
  - `write_table` (DuckDB)
  - `write_candidates`
  - `fill_baseline_row` / `patch_template`
  - `read_output_or_example` (real `measures.json` or the contract mock)
  - `rng`
  - re-exported `metrics` / `Calc`
- B2 flags already exist: `python -m pipeline.run --scenario ch_production --out output/ch_production`.
- Contract: a `BONUS` section at the end of `contract/types.ts` (add your file's type there) and the `CandidatesFile` type.

Original design notes:

- `pipeline/bonus/__init__.py`: a registry with two hook points:
  - `after_energy(ctx)`: runs right after `energy.compute` (used only by A3, which adds columns to `fact_cost`)
  - `after_export(ctx)`: runs at the end of `pipeline.run` (all other modules)
- `pipeline/config.yaml`: a `bonus.enabled: [market, scenarios, clusters, forecast, montecarlo, carbon_aware]` list, so a broken module can be switched off without touching code.
- `pipeline/bonus/common.py`:
  - `write_json(ctx, name, payload)`: adds the standard `meta` block (reuses `store._meta`)
  - reuses `metrics()` / `Calc` from `pipeline/export/frontend.py` (import only, no edit)
  - `fill_template_row(param, low, mid, high, unit, source, calc)`: patches one row of `output/submission/template_baseline_and_assumptions.csv` after `submission.write_baseline` has run. This is how the Bonus rows get filled without editing `submission.py`
- `pipeline/bonus/dev.py`: rebuilds a `Context` from `output/greenops.duckdb` (all `ctx.tables`, with DATE columns converted back to `YYYY-MM-DD` strings), so `python -m pipeline.bonus.<name>` runs a single module in seconds without re-running the 28 connectors.
- One-time local setup: `uv venv -p 3.13 .venv && uv pip install -p .venv -r requirements.txt && .venv/bin/python -m pipeline.run`

## Shared interface with Step 6 (one request, three bonuses depend on it)

Market-based savings (A3), the exact Monte Carlo (B1) and the forecast with the package (A2) all need to know where each measure saves energy. Ask the Step 6 owner to add one optional field to every `Measure`:

```ts
breakdown?: {
  resource_id: string;
  location: LocationCode;
  provider: string;          // "Azure" | "AWS" | "Swiss hoster" | "AI provider" | "SaaS"
  kwh: Range;                // saved energy; NEGATIVE for energy added elsewhere (relocation)
  cost_chf: Range;
  co2_kg: Range;
}[];
```

Example: moving dp-dev to Zurich is `{dp-dev, DE, +X kWh}` plus `{dp-dev, CH, −Y kWh}`.

**Fallback if it doesn't arrive:** use the measure's `entity_ids` → resource → location/provider and the measure's total `savings`. That's good enough for single-location measures, but wrong for relocations.

## Track 1 · Numbers (factors, scenarios, uncertainty, future)

### A3 · Market-based CO₂ (`market.py`)

**Goal:** CO₂ with energy certificates, shown next to the real location-based figure with a critical comment ("on paper yes, on the grid no").

- **Already there:** the contract has `Metrics.co2_kg_market` and the template has the Bonus rows `grid_mix_market_based`, `total_co2_market_based_baseline_year_kg` and the column `savings_co2_kg_market_based`. Every `fact_cost` row has `provider`, `location` and `kwh_low/mid/high`.
- **Research** (write to `pipeline/bonus/market_factors.yaml`, with low/mid/high, source, date and calculation, in the same format as `factors.yaml`). Follow the GHG Protocol Scope 2 market-based method: if a contractual instrument exists, use the supplier factor; otherwise use the residual mix.
  - Azure (Zurich, Frankfurt) and AWS (Dublin): the providers' renewable-matching claims from their latest sustainability reports. What share is matched, annually or hourly, and does it apply to these regions?
  - Swiss hoster: no claim in the data → Swiss supplier mix (Swiss electricity label) or residual mix. State the choice.
  - AI providers and SaaS ("EU mixed"): the AIB European Residual Mix, unless a provider claim applies.
- **Build:**
  - `after_energy` hook: `co2_kg_market_{low,mid,high} = kwh × factor[provider, location]` on `fact_cost`.
  - Baseline totals and the template rows via `fill_template_row`.
  - Once measures exist, market-based savings per measure from `breakdown` (if `breakdown` never arrives, use the resource fallback above). Patch the `savings_co2_kg_market_based` column in the measures template.
- **Output:** columns in `fact_cost` (so also in DuckDB), `co2_kg_market` in summary and entities (needs the 3-line hook in `frontend.metrics`, see below), and `market.json` with the totals per provider plus the critical note.
- **Pitch point:** relocating dp-dev from Frankfurt to Zurich saves a lot location-based and close to nothing market-based (Azure claims cover both regions). That shows why we use location-based.
- **Can start now:** yes, fully. Measure savings come later.

### B2 · Swiss mix switch (`scenarios.py`)

**Goal:** the whole picture with the Swiss production mix (~0.030) as well as the consumption mix (0.110), and proof that the package holds in both.

- **Already there:** `config.yaml: scenario`, and `factors.yaml` grid CH `variants` used by the engine. `Meta.scenario` is in every file.
- **Build:**
  - `pipeline/run.py` accepts `--scenario ch_production --out output/ch_production` (CLI overrides of `config.scenario` and `output_dir`; small hook).
  - Run the pipeline twice. The frontend's toggle just switches data folders, because the files are identical in format.
  - `scenarios.py` reads both `measures.json` files and writes `output/scenarios.json`: baseline CO₂ in both scenarios, and the consumption package re-evaluated with production-scenario savings. Measures are additive by contract rule 10, so this is a sum over the same measure ids. It reports whether the targets are met in each scenario. If the optimizer picks a different package under production, show both.
- **Can start now:** the CLI flags, the double run and the baseline comparison, yes. The package check waits for Step 8.
- **Note:** with the production mix, Zurich weighs much less, so −40% CO₂ leans even more on Frankfurt (dp-dev, GPU) and Dublin (vm-test). That is a good robustness argument if it holds.

### B1 · Monte Carlo (`montecarlo.py` + `pipeline/energy/linear.py`)

**Goal:** "the package meets −40% CO₂ in X% of scenarios", plus a histogram.

- **Key idea:** given each line's observed utilisation, the engine's kWh is linear in every factor. Even the GPU term is linear in `idle_w`: `idle·(1−u) + 300·u`. So the engine can be rewritten as a coefficient table: for each (location, PUE group, factor), the sum of that factor's coefficient over the rows. One draw is then a small dot product instead of a re-run over all rows.
  - `pipeline/energy/linear.py` builds the coefficients from `fact_cost` + `factors.yaml`. It's a new file and does not modify `engine.py`.
  - **Test:** with all factors at mid, the linear model must reproduce `SUM(kwh_mid)` and `SUM(co2_kg_mid)` of the engine exactly (same for low and high).
- **Sampling:** a triangular distribution (low, mid, high) for each factor. Sample independently by default, with an option to correlate the grid factors. Use 10,000 draws and a fixed seed.
- **Package:**
  - v1, works with any `measures.json`: sample each measure's savings triangularly, co-monotonic with the draw (same quantile), costs included.
  - v2, exact, needs `breakdown`: savings per draw = coefficients of the saved kWh per location × the drawn factors.
  - Baseline and savings use the same draw, so the reduction % accounts for common factors cancelling out.
- **Output `montecarlo.json`:** `p_meet_co2`, `p_meet_cost`, `p_meet_both`, percentiles of the reduction %, histogram bins, plus a sensitivity table (which factor drives the spread) for a tornado chart.
- **Can start now:** the linear model, the sampler and the baseline distribution, yes, fully. The package part uses `contract/examples/measures.json` as a mock until Step 8 delivers.

### A2 · Forecast (`forecast.py`)

**Goal:** monthly costs, energy and CO₂ from Sep 2026 to Dec 2030, with and without the package, always as a range. This feeds the year slider in the UI.

- **Start point:** a run-rate per resource from the last complete months of the recurring baseline (Jun–Aug 2026, without one-offs), then deseasonalized.
- **Drivers**, each with source and range, listed in the file's `assumptions[]`:
  - Known changes:
    - dp-prod 20 → 24 nodes from 01.10.2026 (T-1261; the 16 → 20 step on 01.01.2026, T-1172, is already in the run-rate)
    - M365 14 USD per seat from 01.07.2026 (already in the run-rate for Jul–Aug)
    - Copilot Business 18 → 21 USD after the promotion ends on 31.12.2026 (README «Real and synthetic data»)
  - Growth: headcount trend from `headcount.csv` → per-seat items (M365, SaaS, AI subscriptions). AI token trend from `ai_usage` (log-linear fit, low/mid/high).
  - Seasonality: calendar-month factors from the 22 months of data (quarterly training, month-end close).
  - Grid: mid keeps today's factors, low applies the decarbonisation trend (DE, IE). This is a stated assumption.
  - FX: baseline-average rates (stated).
- **With the package:** each measure's yearly savings, spread over the months from its `start_date` (and per resource via `breakdown` when available). Use the mock measures until Step 8 delivers.
- **Template:** fill `growth_per_year` (Bonus) via `fill_template_row`.
- **Output `forecast.json`:** monthly series of total and category values (`without` / `with` as `Metrics`), events (e.g. "dp-prod 24 nodes"), and the assumptions.
- **Can start now:** yes, everything except the real package.

## Track 2 · Behaviour and assistant

### A4 · Clustering (`clusters.py`)

**Status: done.** k = 4 (silhouette 0.71): on demand (24 sandboxes) · always on, almost idle (dp-dev, gpu-ml-01, dr-failover, 3 orphans: 54 % of the clustered CO₂) · always on, lightly used (test / UAT / QA) · steady workload (app servers + dp-prod). No outliers at robust z > 3; `differs_by` explains every member.

**Goal:** group servers and clusters by behaviour, name the groups, and explain the outliers.

- **Inputs** (all already clean): `stg_server_metrics_weekly` (53 servers, about 97 weeks: CPU avg/max, RAM, network, uptime_h, GPU), `stg_server_inventory` (type, owner, last_login, environment, project), `stg_data_platform_usage` (runtime vs active hours for dp-prod and dp-dev).
- **Features per entity:**
  - mean and p95 CPU
  - uptime share (uptime_h / 168)
  - week-to-week variability (CV) and trend of CPU
  - RAM
  - network
  - days since last login
  - idle ratio (clusters)
  - GPU (gpu-ml-01)
- **Method:** standardize the features, then k-means with k = 3…6 chosen by silhouette. scikit-learn can go in `requirements.txt`, or a 30-line k-means in numpy. Name the groups with simple rules on the centroids ("always on and idle", "steady production", "scheduled / part-time", "bursty"). Outliers = distance to their centroid above the p95, each with a one-line reason built from its features.
- **Output `clusters.json`:** groups (id, name, rule, centroid, member `srv:*` / `res:*` ids matching `entities.json`) and members (features, distance, outlier flag, reason). Outliers worth acting on go to `candidates.json` for the Step 5 owner.
- **Can start now:** yes, fully.

### A5 · Carbon-aware shifting (`carbon_aware.py`), lowest priority

**Status: done.** Hourly profiles from Energy-Charts (Fraunhofer ISE, CC BY 4.0) for the baseline year, IPCC life-cycle factors, Switzerland as a consumption mix with physical imports. 7 flexible jobs moved inside their windows, never over fixed runs (incl. month-end close). Saving: 13.2 kg CO₂/yr after auto-pause, 5.7 kg today, so timing is the last lever, after idle time and location. Pitch text: `docs/pitch-notes.md`.

**Goal:** move the flexible jobs to cleaner hours and leave the fixed ones alone.

- **Already there:** `stg_data_platform_jobs` with `window_type` (fixed/flexible) and `window_rule` parsed. The windows found: "within 24 h", "working day 08:00 to 18:00", "within the week", "within the month", "before the next working day", "first week of the quarter". The fixed ones are the ETL by 06:00, Power BI by 07:30, the export by 08:00, month-end and year-end close, and the backup window 22:00–06:00.
- **Research:** an hourly intensity profile per location (CH: UniGe; DE and IE: ENTSO-E or Electricity Maps), stored in `pipeline/bonus/data/hourly_intensity.csv` as location × month × weekday/weekend × hour. Scale each profile so its yearly mean equals the location-based mid in `factors.yaml`, so the two views stay consistent.
- **Energy per job:** duration × the cluster's nodes × the marginal power of an active node (active minus idle). State honestly that shifting only saves energy when the cluster isn't on 24/7 anyway, so the saving is real only together with the auto-pause measures.
- **Simulation:** for each flexible job, the start hour with the lowest intensity inside its window that doesn't collide with a protection window. Use the Step 7 `limits.json` once it exists, the fixed jobs until then.
- **Output `jobs.json`:** jobs with original and suggested start, kWh, CO₂ before and after, `locked` for fixed jobs, plus the 24-hour profiles for the timeline. The measure goes to `candidates.json` (expect a small saving; that's fine to say in the pitch).
- **Can start now:** yes, fully.

### A1 · Chat assistant (`assistant/`)

**Status: done (v1).** OpenAI Responses API (`gpt-5.4`, classifier `gpt-5.4-mini`). 16 read-only tools, number verifier, HTTP API, attack suite 23/23 (example 3/3, injections in the data 5/5, planted 5/5, user attacks 10/10). The classifier flags exactly the 4 injections in the data. Answers get richer automatically once findings, measures and limits exist (`analysis` tool).

**Goal:** answers questions about the data and the measures, and every answer shows its number, formula and source.

It's a separate package (`assistant/`) because it's a server, not a pipeline step, with its own `requirements-assistant.txt`.

| Sub-module | What | Can start now? |
|---|---|---|
| `assistant/llm.py` | Adapter around the LLM access sprintd provides (provider still to confirm: **ask the organisers now**). Logs tokens per call to `output/ai_usage_log.jsonl`, which also gives us the "energy of our own AI" sentence. | yes, once we have access |
| `assistant/tools.py` | **Read-only** tools over DuckDB (`read_only=True`) and the JSON files. No free SQL. Tools: `query_metrics(scope, metric, period)`, `get_entity(id)`, `explain_calculation(id)`, `get_finding(id)`, `get_measure(id)`, `get_limit(id)`, `list_issues(filter)`, `get_factor(id)`, `get_forecast(year)`, `calculate(expression)`. The safe arithmetic tool means derived numbers also come from a tool. Each tool returns `{value, unit, formula, source_files, ids}`. | yes, on today's DuckDB and JSON |
| `assistant/classify_text.py` | LLM classifier over the `free_text` table → `text_risk` (ok / flagged + reason). The text goes in strictly as data, the output is structured, and results are cached in `assistant/text_risk_cache.json` (hash → label, model, date) and committed, so the pipeline stays offline and deterministic. The Step 7 owner reads it for `Limit.quote_risk`. | yes |
| `assistant/server.py` | A small HTTP API: `POST /chat` → tool loop. The system prompt holds the only authority. Free text returned by tools is wrapped as untrusted data, and flagged texts are redacted with a link to the issue. There is no tool that changes or switches off anything. The response returns `focus_entity_ids` so the camera can move. | yes |
| `assistant/verify.py` | Answer check: every number in the answer must match a tool result (allowing for rounding); every recommendation must match a measure status from the Step 7 checks. If it fails, regenerate once, otherwise answer with a warning. | yes |
| `assistant/tests/` | Attack suite: the injections already in the data plus about 20 of our own (in data fields and in user messages), and the 3 example questions as regression tests. One command runs them and prints the pass rate for the pitch. | yes. The example answers improve once Steps 5–7 land |

- **Contract:** add the `ChatRequest` / `ChatResponse` types (`answer`, `numbers[] {value, unit, tool, ref}`, `sources[]`, `focus_entity_ids[]`, `warnings[]`) to `types.ts` so the UI can build the panel on a mock.
- **Demo safety:** cache the answers to the 3 example questions, so the pitch works without a network connection.

## Who does what

| | Person 1 · Numbers track | Person 2 · Behaviour and assistant track |
|---|---|---|
| first | 0 · Shared foundation (together) | 0 · Shared foundation (together) + ask sprintd for AI access |
| 1 | A3 Market-based | A1 tools + text classifier |
| 2 | B2 Swiss mix switch (CLI + double run) | A4 Clustering |
| 3 | B1 linear model + sampler (baseline) | A1 server + verify + attack suite |
| 4 | A2 Forecast (without package) | A5 Carbon-aware |
| when Step 6/8 land | A3 market savings, B2 package check, B1 package, A2 with package | A1: answers to the 3 example questions, recommendations checked against measure statuses |

**Cut line if time runs out**, in this order: A5 → B1 v2 (keep v1) → A2 seasonality → A1 verify (keep the read-only tools and the redaction).

## Files we touch outside our modules (tell the team)

| File | Change | Why |
|---|---|---|
| `pipeline/run.py` | 2 hook calls (`bonus.after_energy`, `bonus.after_export`) + `--scenario` / `--out` flags | registry, B2 |
| `pipeline/config.yaml` | `bonus:` section | toggles |
| `pipeline/export/frontend.py` | `metrics()` / `SUMS`: include `co2_kg_market_*` when the columns exist (about 3 lines) | A3 in summary and entities |
| `contract/types.ts` + `contract/examples/` | bonus section: `ForecastFile`, `MonteCarloFile`, `ClustersFile`, `JobsFile`, `ScenariosFile`, `MarketFile`, chat types; optional `Measure.breakdown` | the UI builds in parallel |
| `requirements.txt` | scikit-learn (if used) | A4 |

## What we can do right now, without waiting for anyone

- The foundation, plus the contract types and example files for every bonus file (this unblocks the UI)
- A3 completely, except measure savings
- B2: the double run and the baseline comparison
- B1: the linear model, verified against the engine, and the baseline distribution
- A2: the forecast without the package
- A4 and A5 completely
- A1: tools, classifier, server, attack suite

**What waits for Steps 6–8:** the package-dependent parts (market-based savings, package in both Swiss scenarios, Monte Carlo of the package, forecast with the package, assistant recommendations). All of them build on the contract's `measures.json` example first, so switching to the real file is a swap.
