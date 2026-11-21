# Local AI option — design

**Date:** 2026-11-21 · **Status:** approved, ready for implementation plan

## Goal

A new, **advisory-only** feature that reads the company's architecture (servers, GPU, cloud providers, AI API usage) and suggests whether some AI workloads that read private company data could run on **open-weight models on hardware the company already has or could use with its current providers**. For each option it shows 3-year cost, energy and CO₂ against "API as today", with pros and cons. It **never changes** any existing number (baseline, measures, package, forecast). A human decides.

## Scope

**In scope: 7 company workloads** (baseline 2025-09-01 … 2026-08-31, from `ai_usage.csv`):

| id | Source `resource_id` | Why private data |
|---|---|---|
| `wl:office-assistant` | `ai-assistant` (all task types) | contracts, tables, summaries |
| `wl:knowledge-chatbot` | `ai-chatbot` | internal knowledge base |
| `wl:support-agent` | `ai-agent` | tickets |
| `wl:report-agent` | `ai-report` | internal reports |
| `wl:other-agents` | `ai-agent2` | internal data |
| `wl:quote-generator` | `ai-quote` | prices, customers |
| `wl:marketing-classify` | `ai-marketing` | customer texts |

**Out of scope:** our own GreenOps chatbot and advisor, per-seat subscriptions (ChatGPT Team, Claude Team), Microsoft Copilot, development or coding AI use, and any change to the measures package.

## Inputs

### Workload demand (computed from the data)

For each workload:
- tokens in, cached and out per year, plus requests;
- API cost in CHF, kWh and CO₂ as today, reusing the existing energy engine and `factors.json`;
- **peak tokens/s**: output-equivalent tokens on the busiest day, spread over 8 working hours;
- **required quality tier**, mapped from `task_type`:
  - `basic`: Classify, Translate, Manual question;
  - `standard`: Summarise, Draft texts, Analyse table;
  - `advanced`: Review contract, Agent run.

  A workload's required tier is the highest tier among the task types that make up at least 20 % of its API cost. The per-task-type split (tier, tokens, cost) is kept in `tasks[]`, so the UI can show which part drives the tier.

### Catalogue `pipeline/bonus/local_ai_catalog.yaml` (researched online; every entry has `source` and `source_date`)

**Models** (about 10–12 open-weight models, e.g. Llama 3.x 8B/70B, Qwen 2.5/3 7B–72B, Mistral Small, Mixtral, Gemma 3, gpt-oss-20b/120b, Phi-4, DeepSeek-R1-distill). Fields:
- `params_b`, `licence`, `context_k`;
- `vram_gb` for `fp16`, `q8` and `q4`;
- `quality_tier` (with the benchmark cited);
- `tokens_per_s` per GPU class (low, mid, high).

**Hardware.** Only options with providers the company already uses, plus one CPU-only option:
1. `hw:gpu-ml-01-fra`: the existing `gpu-ml-01` as it is (Azure Frankfurt, one GPU of the 300-W class, about 5 % used, already paid). `owned: true`.
2. `hw:gpu-azure-zrh`: the same GPU class in Azure Switzerland North (Zurich).
3. `hw:gpu-azure-80gb`: a larger Azure GPU VM (80-GB class) for 70B+ models.
4. `hw:gpu-aws-zrh`: an AWS GPU instance in Zurich.
5. `hw:gpu-hoster-ch`: a GPU at the Swiss hoster.
6. `hw:cpu-test-servers`: CPU-only inference on the under-used test servers (small models only).

Fields:
- `vram_gb`, `tdp_w`, `idle_w`;
- `price` (per hour or per month, with currency and source) and `energy_included`;
- `location`, used for the grid factor and the PUE id;
- `setup_days` and `maint_days_per_year`;
- `entity_id` where one exists (e.g. `srv:gpu-ml-01`).

## Calculation (`pipeline/bonus/local_ai.py`, deterministic, no LLM)

For each workload × model × hardware:

1. **Feasibility.**
   - Model VRAM at the chosen quantisation, plus KV-cache for the typical context, fits the hardware VRAM.
   - Throughput is at least the peak tokens/s.
   - Model tier is at least the required tier.

   Every rejection keeps a reason string, e.g. "70B Q4 needs 42 GB, gpu-ml-01 has 24 GB".
2. **GPU hours** = yearly output-equivalent tokens / throughput, plus idle time.
   - Owned and already always on (`gpu-ml-01`): count only the **incremental** energy and cost of the active hours.
   - New hardware: take the cheaper of always-on and office-hours-only.
3. **3-year cost in CHF.**
   - Local = rent or lease + electricity (when not included) + one-off setup (`setup_days` × CHF 1,100) + maintenance (`maint_days_per_year` × CHF 1,100 × 3).
   - API = baseline API cost × 3, scaled by the growth assumptions already in `forecast.json`. They are read, not recomputed.
   - **Break-even month**: the first month when cumulative local cost falls below cumulative API cost, or `null`.
4. **Energy and CO₂.** kWh = hours × W × PUE. CO₂ uses the location grid factor. The factor ids come from `factors.json` (same factors as the rest of the product). `co2_kg_market` is optional.
5. **Ranges.** Every figure is `{low, mid, high}`, from the low/high bounds of throughput, prices and factors.
6. **Selection.**
   - Per workload: the best option by cost and the best option by CO₂.
   - **Consolidated** options: several workloads on one GPU, first of all "all feasible workloads on `gpu-ml-01`".
7. **Pros and cons** come from rules, each backed by a number. Examples:
   - pros: private data stays in CH or DE under company control, no per-token price risk, fixed cost, uses idle GPU;
   - cons: lower quality on `advanced` tasks, ops skills needed, single point of failure, model updates, and peak throughput margin when it is low.

**Read-only guarantee:** the module only reads the existing outputs. It writes only `output/local_ai.json`.

## Output and contract

New type `LocalAiFile` in `contract/types.ts`, mirrored in `web/src/data/types.ts`. It is additive only.

```ts
interface LocalAiFile {
  meta: Meta;
  advisory: true;
  horizon_years: 3;
  workloads: LocalAiWorkload[];   // id, label, resource_id, tool, quality_tier, tasks[], tokens per year, peak_tps, api: Metrics, calc
  models: LocalAiModel[];         // catalogue entries with source and source_date
  hardware: LocalAiHardware[];    // id, label, provider, location, vram_gb, tdp_w, price, owned, entity_id
  options: LocalAiOption[];       // workload × model × hw: feasible, reasons[], tco_3y: Range, kwh/co2_kg: Range, breakeven_month, pros[], cons[], calc
  best: { workload_id: string; by_cost: string | null; by_co2: string | null }[];
  consolidated: LocalAiOption[];  // workload_ids[] instead of workload_id
  totals: { api_3y: Metrics; local_best_3y: Metrics };
}
```

- Add `contract/examples/local_ai.json` and a row in the `contract/README.md` file table.
- Wire the module into `bonus.after_export`, like the other bonus modules. When the module fails, only this file is missing and the pipeline still succeeds.

## UI

- Add a fifth mode, **"Local AI"**, in `web/src/ui/Nav.tsx`, `web/src/ui/ModePanel.tsx` and `web/src/store.ts`. It carries the badge "Advisory, no numbers changed".
- The panel shows a table of the 7 workloads: API vs best local option (3-year cost, kWh, CO₂, break-even). Each row expands to all options, with feasibility reasons, pros and cons, and the calc panel.
- In the scene, while the mode is on, the `gpu-ml-01` rack is highlighted with the label "GPU at X %: could host N workloads".
- Load it with `get(base, 'local_ai').catch(() => null)`. When the file is missing, the mode shows "not available" and nothing else changes.

## Tests (`tests/`)

- Feasibility rejects a model when VRAM is too small, and records the reason.
- Break-even month is correct on a small hand-built case.
- Owned `gpu-ml-01` counts only incremental energy and cost.
- Running the module leaves `measures.json`, `summary.json` and `forecast.json` byte-identical (hash before and after).
