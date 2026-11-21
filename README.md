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
.venv/bin/python -m pipeline.run
```

Reads all 28 exports and writes `output/greenops.duckdb` (harmonized tables), `output/quality.json` (Intake screen: everything fixed, estimated or flagged), `output/fx.json` (currency selector), `output/factors.json` (energy and CO₂ factors with low/mid/high and sources), the scene files `output/summary.json`, `output/entities.json`, `output/timeseries.json` (format: `contract/`) and the filled submission table `output/submission/template_baseline_and_assumptions.csv`.

- `pipeline/config.yaml`: tunable parameters (materiality threshold, baseline year, FX mode, imputation)
- `pipeline/reference.yaml`: reference facts with sources (cost centers, regions, AI list prices, curated one-offs)
- `pipeline/connectors/*.yaml`: one mapping file per export (for another SME, write new ones)
- `pipeline/harmonize/`: generic engine, transform library, gap filling, reconciliation, DuckDB store
- `pipeline/export/`: frontend files (contract format) and submission templates, generated from the engine, never by hand
- `pipeline/energy/`: `factors.yaml` (researched factors, each with source, date, range and calculation) and the engine that adds kWh and location-based CO₂ (low/mid/high) to every billing line

Main tables: `fact_cost` (every franc, with native amount, CHF/EUR/USD, value status and range, department, source row), `fact_activity` (physical quantities), `issues`, `free_text` (inert text, `text_risk` for a later LLM classifier), `dim_*`, `stg_*` (one cleaned table per source). Views: `v_cost_baseline`, `v_cost_allocated`, `v_focus_cost`, `v_coverage`.

## Structure

- `case.md` — case description
- `data/case/` — case data (git submodule, read-only): https://github.com/Fa-Bee/sprintd-basel-green-ai-data

Update the case data if the organisers push fixes:

```bash
git submodule update --remote data/case
```

Data: «Sample data ALTYCA, sprintd Basel 2026» (synthetic).
