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
# Swiss production mix instead of consumption mix, into its own folder (B2)
.venv/bin/python -m pipeline.run --scenario ch_production --out output/ch_production
# run one bonus module against the last run, without the 28 connectors (~2 s)
.venv/bin/python -m pipeline.bonus.dev <module>
```

Reads all 28 exports and writes `output/greenops.duckdb` (harmonized tables), `output/quality.json` (Intake screen: everything fixed, estimated or flagged), `output/fx.json` (currency selector), `output/factors.json` (energy and CO₂ factors with low/mid/high and sources), the scene files `output/summary.json`, `output/entities.json`, `output/timeseries.json`, `output/findings.json` (format: `contract/`), `output/answers.json` (example questions) and the filled submission table `output/submission/template_baseline_and_assumptions.csv`.

- `pipeline/config.yaml`: tunable parameters (materiality threshold, baseline year, FX mode, imputation)
- `pipeline/reference.yaml`: reference facts with sources (cost centers, regions, AI list prices, curated one-offs)
- `pipeline/connectors/*.yaml`: one mapping file per export (for another SME, write new ones)
- `pipeline/harmonize/`: generic engine, transform library, gap filling, reconciliation, DuckDB store
- `pipeline/find/`: Step 5 rules for drivers and waste (thresholds in `config.yaml` → `find`)
- `pipeline/export/`: frontend files (contract format) and submission templates, generated from the engine, never by hand
- `pipeline/energy/`: `factors.yaml` (researched factors, each with source, date, range and calculation) and the engine that adds kWh and location-based CO₂ (low/mid/high) to every billing line

Main tables: `fact_cost` (every franc, with native amount, CHF/EUR/USD, value status and range, department, source row), `fact_activity` (physical quantities), `issues`, `free_text` (inert text, `text_risk` for a later LLM classifier), `dim_*`, `stg_*` (one cleaned table per source). Views: `v_cost_baseline`, `v_cost_allocated`, `v_focus_cost`, `v_coverage`.

## Assistant (bonus A1)

A chat assistant on the pipeline results (OpenAI, `assistant/config.yaml`). It only **reads**: 16 read-only tools over DuckDB and `output/*.json`; every number in an answer is checked against the tool results before it is returned.

```bash
uv pip install -p .venv -r requirements-assistant.txt
echo "OPENAI_API_KEY=sk-..." > .env            # never committed
.venv/bin/python -m assistant ask "How many AI seats were unused in August 2026?"
.venv/bin/python -m assistant serve             # POST http://127.0.0.1:8787/api/chat (contract: ChatRequest / ChatResponse)
.venv/bin/python -m assistant eval              # attack suite + the 3 example questions
.venv/bin/python -m assistant classify          # only when free texts change → pipeline/bonus/text_risk.json
```

Defence against the prompt injections hidden in the data:
1. No AI in the calculations: pipeline, formulas and rules are code.
2. Free texts are classified once by an LLM (`text_risk`: ok / ambiguous / flagged). The verdicts are committed, so the pipeline stays offline. Flagged texts are withheld everywhere.
3. Tools are read-only; data text reaches the model only wrapped as untrusted data.
4. Authority comes only from the system prompt and the user; approvals written in the data count for nothing.
5. Verifier: every number must come from a tool result. Numbers from unclassified or flagged text never count.
6. Attack suite (`assistant/evals/cases.yaml`): the injections in the data, injections planted into tool results, and user attacks.

## Structure

- `case.md` — case description
- `data/case/` — case data (git submodule, read-only): https://github.com/Fa-Bee/sprintd-basel-green-ai-data

Update the case data if the organisers push fixes:

```bash
git submodule update --remote data/case
```

Data: «Sample data ALTYCA, sprintd Basel 2026» (synthetic).
