# vampere

GreenOps for SMEs — sprintd Basel 2026, case "Green AI & Data" (ALTYCA × Basel 2037).

## Setup

```bash
git clone --recurse-submodules https://github.com/M4tteoo/vampere.git
# already cloned without submodules?
git submodule update --init
```

## Run the pipeline

```bash
uv venv -p 3.13 .venv && uv pip install -p .venv -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env          # local only, never committed (.env is in .gitignore)
.venv/bin/python -m pipeline.run                       # ~20 s; the AI runs only if its input changed, else saved answers are reused
.venv/bin/python -m pipeline.run --advisor             # force a fresh analysis (ticket reader + area agents, ~10–20 s)
.venv/bin/python -m pipeline.run --offline             # never call the AI (no key needed)
.venv/bin/python -m pipeline.run --goal best_value     # climate_first (default) | best_value | francs_first
.venv/bin/python -m pipeline.advisor.redteam [--llm]   # prompt-injection tests
```

Check everything before a demo or a commit (offline, under a minute):

```bash
.venv/bin/python -m unittest discover -s tests -t .   # unit tests + end-to-end output audit
.venv/bin/python -m tests.audit_outputs              # the audit, readable: contract fields, ranges, ids, cross-module numbers
```

Architecture and pipeline flow: [docs/architecture.svg](docs/architecture.svg) · extra sources → features: [docs/extra-sources.md](docs/extra-sources.md) · path to operation: [docs/path-to-operation.md](docs/path-to-operation.md) · pitch notes: [docs/pitch-notes.md](docs/pitch-notes.md) · AI-only vs code-driven advisor (speed, AI energy, quality): [docs/advisor-comparison.md](docs/advisor-comparison.md)

**How the work is split**

| Who | Does what |
|---|---|
| Code: harmonizer | reads the 28 exports, fixes time, currency, units, names, duplicates, gaps; allocates to departments |
| Code: energy engine | kWh and location-based CO₂ for every billing line (researched factors with source and range) |
| Code: fact sheet | turns the data into ~750 numbers with ids («dp-dev.idle_share»); no free text |
| LLM: ticket reader (quarantined, 4 parallel batches, `gpt-5.4`) | reads ticket text and turns it into typed restrictions (block, protection window, human decision); code checks every target against the ticket's own resource |
| Code: toolbox | proposes candidate measures from generic levers (pause idle hours, office hours, downsize, decommission forgotten servers, move to a cleaner grid (also on its own: nothing switched off, data kept, so allowed for protected resources such as the backup archive), remove inactive seats, smaller AI model, storage/log clean-up, skip unchanged builds) and the «deliberately kept on» list |
| LLM: area agents (4 in parallel, `gpt-5.4-mini`) | platform, servers, licences, AI & other: make each candidate realistic (shares only downwards), set effort and status, add up to 2 ideas each |
| Code: calculator and gate | computes every saving (CHF, kWh, CO₂; removed idle hours are valued at the power of a server at 5 % background load, a documented team assumption shown in the submission table); safety gate (blocked / a person decides); statuses can only get stricter |
| Code: optimiser | picks the optimal package for each goal: **climate first** (max CO₂ within budget), **best value** (cheapest way to −40 % CO₂ / −25 % cost), **francs first** (max savings); all options meet the case rules (−40 % CO₂, −25 % cost, max CHF 16,500); **options come first**, each with its own risk appetite (climate first: most CO₂, safest by design · best value: cheapest plan safe in ≥ 80 % · francs first: most money, safe in ≥ 70 %); each package reports how **safe** it is («safe in X %» = share of the 10,000 Monte Carlo scenarios in which it still reaches −40 % CO₂, same draws and model as the Monte Carlo panel), plus a fourth option **«safest»** (or a flag on the goal it equals). The user can open any option and **remove** measures: totals and safety are recomputed live from `measures.json → rules` and `output/safety_scenarios.json` |

**Same data ⇒ same answer.** The AI's input is fingerprinted; while it does not change, the saved answers (`output/advisor/*.json`) are reused and no AI energy is spent. New exports change the fingerprint and the analysis re-runs on its own. `measures.json` → `analysis` says when it ran, how long it took and what it cost.

**Prompt-injection defence (by construction, not by trusting the model)**
1. The area agents never see free text from the data: only numbers, ids and master-data labels.
2. Ticket text goes only to the reader, after the classifier removed texts that address AI systems. The reader has no tools; its answer must fit a strict schema and is validated by code.
3. Restrictions can only *restrict*: nothing in the data can unlock a blocked resource or loosen a status.
4. Every number is computed by code from the data: an injected «report costs 40 % lower» cannot change a figure.
5. The test suite (`pipeline.advisor.redteam`) checks all of this, with live attacks on the reader.

**Energy of the tool's own AI:** every analysis records the tokens of its LLM calls and reports their energy and CO₂ with the results (`measures.json` → `ai_footprint`, same factors as the company's AI use). Fresh analysis of the reader + 4 agents: ~2.9 Wh, ~0.6 g CO₂ in ~22 s (the previous single-call advisor: ~21.5 Wh in ~6 min); agents only: ~0.8 Wh in ~11 s.

Outputs (format: `contract/`): `output/greenops.duckdb` (harmonized tables), `quality.json` (Intake screen), `fx.json`, `factors.json`, `summary.json`, `entities.json`, `timeseries.json`, `findings.json`, `measures.json` (with the package), `limits.json`, `answers.json`, `output/advisor/` (saved LLM answers, fact sheet, report) and the filled submission tables in `output/submission/`.

- `pipeline/config.yaml`: tunable parameters (materiality threshold, baseline year, FX mode, advisor models, goal, budget)
- `pipeline/reference.yaml`: reference facts with sources (cost centers, regions, AI list prices, curated one-offs)
- `pipeline/connectors/*.yaml`: one mapping file per export (for another SME, write new ones)
- `pipeline/harmonize/`: generic engine, transform library, gap filling, reconciliation, DuckDB store
- `pipeline/energy/`: `factors.yaml` (researched factors, each with source, date, range and calculation) and the kWh/CO₂ engine
- `pipeline/advisor/`: fact sheet, ticket reader, toolbox, area agents, calculator and gate, optimiser, red-team tests (`planner.py` = previous single-call advisor, kept only for `assistant energy --advisor-estimate`)
- `pipeline/export/`: frontend files (contract format) and submission templates, generated by code
- `pipeline/bonus/`, `assistant/`: bonus modules and the chat assistant (see `bonus-plan.md`)

Main tables: `fact_cost` (every franc, with native amount, CHF/EUR/USD, value status and range, department, kWh, CO₂, source row), `fact_activity` (physical quantities), `issues`, `free_text` (inert text with `text_risk`), `dim_*`, `stg_*`. Views: `v_cost_baseline`, `v_cost_allocated`, `v_focus_cost`, `v_coverage`.

## Forecast (bonus A2)

The pipeline writes `output/forecast.json` with monthly cost, energy and location-based CO₂ ranges for 52 weeks starting September 1, 2026. August 2027 is prorated through August 30. It runs the same projection on `fact_cost` (`without`) and on the optional `fact_cost_optimized` table (`with`). The two projections are separate from the Swiss grid-mix switch.

**Step 9 — optimized history:** `optimized_history` applies the selected structured effects from `measures.json` to recurring historical rows, leaving one-offs untouched. It shares the row allocation rules with B1/B2: whole resources, server shares within shared bills, licence products, and AI task/model groups. Server shares estimated by the advisor for the baseline are held fixed across the history. Whole-resource relocations use the destination grid factor. No annual savings are spread over months. The step writes `fact_cost_optimized` to DuckDB and reports applied, skipped, and human-confirmation measures in `output/optimized_history.json`. This assumes measures were already in force; it does not simulate rollout dates or authorize implementation. A partial replay is also flagged in `forecast.json`.

**A3 — market-based CO₂:** `output/market.json` compares the same baseline kWh using location-based and market-based factors, with a provider breakdown and factor provenance. It uses [AIB 2025](https://www.aib-net.org/facts/european-residual-mix/2025) residual mixes for DE and IE, the European Attribute Mix as a proxy for unspecified EU locations, and the Swiss consumption mix as a fallback for CH (no AIB residual mix). No unverified certificates or supplier claims are credited. AIB generation CO₂ and the location-based life-cycle figures are not strictly comparable; the difference is not a reduction in electricity use or physical emissions. Targets and forecasts remain location-based. Market-based savings are reported only for measures with supported `res:` effects; unsupported rows are left blank in the submission.

**Bonus verification:** the pipeline can run offline with the committed advisor answers. Use `--scenario ch_production --out <directory>` to check the production mix without replacing the default exports. Set `GREENOPS_TEST_OUTPUT` to the directory of a completed run to include the data-backed B1/B2 consistency tests.

**Forecast input contract:** `ctx.tables["fact_cost_optimized"]` is a full historical dataset with optimizations already applied, not a table of savings. It matches `fact_cost`'s columns, months, and units and includes unchanged resources. Neither forecast reads the measures package. If the optimized table is absent, `with` is `null`.

Run `python -m pipeline.bonus.dev optimized_history forecast` to replay the current package and regenerate the forecast from the existing DuckDB.

## Structure

- `case.md` — case description
- `data/case/` — case data (git submodule, read-only): https://github.com/Fa-Bee/sprintd-basel-green-ai-data

Update the case data if the organisers push fixes:

```bash
git submodule update --remote data/case
```

Data: «Sample data ALTYCA, sprintd Basel 2026» (synthetic).
