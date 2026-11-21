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

Rent, setup and maintenance are fixed costs shared by every workload on a GPU. So feasibility and energy are computed per **fit** (workload × model × hardware), while cost and break-even are computed per **scenario** (hardware × model × set of workloads).

### Fits (workload × model × hardware)

1. **Feasibility.**
   - The model's weight memory × 1.2 (runtime and KV-cache headroom) must fit the hardware VRAM.
   - The batched throughput (mid) must be at least the workload's peak tokens/s in year 3, after token growth.
   - The model tier must be at least the workload tier.
   - The model must have a throughput figure for the hardware's GPU class.

   Every rejection keeps a reason string, e.g. "Llama 3.3 70B (4-bit) needs 48 GB with headroom; gpu-ml-01 has 48 GB".
2. **GPU hours per year** = output-equivalent tokens / batched throughput / 3600. Output-equivalent tokens use the same formula as the energy engine: output + 0.1 × uncached input + 0.01 × cached input.

### Scenarios (hardware × model × workload set)

- **Workload sets:**
  - `all`: all 7 workloads.
  - `hybrid`: every workload except `advanced` ones, which stay on the API.
  - `single`: one per workload, to see if it pays off on its own.
- **Model choice:** for each hardware and set, the feasible model with the lowest energy. Ties go to the lowest weight memory.
- **On-hours per year:**
  - Hourly-billed cloud hardware runs in office hours only: baseline workdays (`dim_date.workday`) × 10 h.
  - Monthly hardware (hoster) is on 8,760 h per year.
- **3-year local cost (CHF):**
  - rent: on-hours × hourly price, or 12 × monthly price, per year;
  - setup, once: `setup_days` × CHF 1,100;
  - maintenance: `maint_days_per_year` × CHF 1,100 per year.

  Electricity is included in cloud and hoster prices.
- **`gpu-ml-01` (owned) and measure M-04.** The package already contains M-04 "Run gpu-ml on demand", which stops the GPU outside quarter days. Running inference there in office hours gives back part of that saving. This is recorded in `interacts_with` (measure id, title, CHF per year) and counted as the rent of `gpu-ml-01`, at the hourly rate derived from `azure_costs.csv` (baseline cost / baseline hours). A second figure, "vs today (24/7, without M-04)", is shown only in `calc.inputs`. M-04 itself is not changed.
- **3-year API cost** = baseline API cost of the moved workloads, from `fact_cost`, year y × (1 + token growth)^y for y = 1, 2, 3. Token growth comes from `forecast.json` (`assumptions[id=token_growth]`). It is read, not recomputed.
- **Break-even month**: the first month m (1…36) where cumulative local cost (setup + m × monthly cost) ≤ cumulative API cost, or `null`.
- **Energy and CO₂:**
  - kWh = (on-hours × idle W + GPU hours × (TDP − idle W)) / 1000 × PUE, plus host W × on-hours;
  - CO₂ = kWh × location grid factor.

  The factor ids (`pue`, `pue_hoster`, `grid_mix_location_based_*`) and the GPU idle range come from `pipeline/energy/factors.yaml`, the same factors used by the rest of the product.
- **Ranges:**
  - `low` = cheap prices, high throughput, low factors, few person-days;
  - `high` = the opposite.

  Break-even uses local high against API low for its pessimistic bound.
- **Pros and cons** come from rules, each backed by a number:
  - **pros:** private data stays in CH or DE under company control; API cost avoided; energy and CO₂ change; GPU utilisation goes up; no per-token price risk.
  - **cons:** quality gap on `advanced` tasks; setup person-days against the CHF 16,500 budget; maintenance per year; single point of failure; quarterly training weeks share `gpu-ml-01` (ticket T-1101); M-04 saving given back; capacity or quota not guaranteed in CH regions; estimated prices.
- **Best:**
  - `by_cost`: the feasible scenario with the highest 3-year saving (mid);
  - `by_co2`: the feasible scenario with the lowest CO₂ (mid);
  - for each workload, the fit with the lowest energy.

**Read-only guarantee:** the module only reads the existing outputs. It writes only `output/local_ai.json`.

## Output and contract

New type `LocalAiFile` in `contract/types.ts`, mirrored in `web/src/data/types.ts`. It is additive only.

```ts
interface LocalAiFile {
  meta: Meta;
  advisory: true;                 // information only, a human decides
  horizon_years: 3;
  note: string;
  workloads: LocalAiWorkload[];   // tier, tasks[], tokens, out_eq_tokens, peak_tps, api (Metrics, baseline year), calc
  models: LocalAiModel[];         // catalogue entries with source, source_date, estimate
  hardware: LocalAiHardware[];    // vram, tdp, idle, price, location, owned, entity_id, factor ids
  fits: LocalAiFit[];             // workload × model × hardware: feasible, reasons[], tps, gpu_hours_per_year
  scenarios: LocalAiScenario[];   // hardware × model × set: api_3y, local_3y, savings_3y, breakeven_month, interacts_with, pros, cons, calc
  best: { by_cost: string | null; by_co2: string | null; by_workload: { workload_id: string; fit: string | null }[] };
  assumptions: LocalAiAssumption[];
}
```

- Add `contract/examples/local_ai.json` and a row in the `contract/README.md` file table.
- Enable the module through `bonus.enabled` in `pipeline/config.yaml`; it runs in `bonus.after_export`. When the module fails, only this file is missing and the pipeline still succeeds.
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
