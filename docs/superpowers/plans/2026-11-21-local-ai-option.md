# Local AI option Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An advisory-only «Local AI» feature: from the company's AI usage and GPU / servers, compare 3-year cost, energy and CO₂ of open-weight models on available hardware against the current APIs, without changing any existing number.

**Architecture:**
- A curated catalogue (`pipeline/bonus/local_ai_catalog.yaml`) and a deterministic bonus module (`pipeline/bonus/local_ai.py`, `run(ctx)` hook) write `output/local_ai.json`.
- The contract type `LocalAiFile` describes the file.
- The frontend adds a fifth mode, «AI locale», that reads the file when present.

**Tech Stack:** Python 3.13, pandas, PyYAML, unittest; React + TypeScript + zustand (web).

**Spec:** `docs/superpowers/specs/2026-11-21-local-ai-option-design.md`

## Global Constraints

- Advisory only: write only `output/local_ai.json`. Never touch `measures.json`, `summary.json`, `forecast.json` or other outputs.
- Every figure is a `{low, mid, high}` range. Metrics carry `cost_chf`, `cost_eur`, `cost_usd`, `kwh`, `co2_kg`.
- No LLM calls. Factors come from `pipeline/energy/factors.yaml`, the same ones used by the rest of the product.
- Scope: the 7 company workloads only (`ai-assistant`, `ai-chatbot`, `ai-agent`, `ai-report`, `ai-agent2`, `ai-quote`, `ai-marketing`). Not our GreenOps assistant or advisor.
- Horizon: 3 years. Person-day: CHF 1,100.

---

### Task 1: Catalogue + pure calculation helpers (TDD)

**Files:**
- Create: `pipeline/bonus/local_ai_catalog.yaml` (models, hardware, assumptions, with sources)
- Create: `pipeline/bonus/local_ai.py` (helpers first)
- Test: `tests/test_local_ai.py`

**Interfaces (produces):**
- `out_eq(tokens_in: float, tokens_in_cache: float, tokens_out: float, input_w: float, cached_w: float) -> float`
- `vram_check(weights_gb: float, vram_gb: float, headroom: float) -> str | None`: returns a reason when the model does not fit
- `breakeven_month(setup_chf: float, local_monthly_chf: float, api_year0_chf: float, growth: float, months: int = 36) -> int | None`
- `energy_kwh(on_hours: float, gpu_hours: float, idle_w: float, tdp_w: float, host_w: float, pue: float) -> float`

- [ ] Write the tests for `vram_check` (70B 4-bit on 24 GB is rejected with a reason; 8B BF16 on 48 GB fits), `breakeven_month` (hand-built case: setup 1200, local 100/month, API 1200/year, growth 0 → month 12; local dearer than the API → `None`) and `energy_kwh` (idle-only when `gpu_hours = 0`).
- [ ] Run `python -m unittest tests.test_local_ai -v`. Expect FAIL (import error).
- [ ] Implement the helpers.
- [ ] Run again. Expect PASS.
- [ ] Commit.

### Task 2: Module `run(ctx)`: workloads, fits, scenarios, best → `output/local_ai.json`

**Files:**
- Modify: `pipeline/bonus/local_ai.py` (add `build(ctx) -> dict` and `run(ctx)`)
- Modify: `pipeline/config.yaml` (append `local_ai` to `bonus.enabled`)
- Test: `tests/test_local_ai.py`

**Interfaces:**
- Consumes: `ctx.tables["fact_cost"]`, `ctx.tables["stg_ai_usage"]`, `ctx.tables["dim_date"]`, `ctx.tables["fx_monthly"]`, `output/forecast.json` (`assumptions[id=token_growth]`), `output/measures.json` (M-04 / M-05 titles), `pipeline/energy/factors.yaml`.
- Produces: `build(ctx) -> dict`, in the `LocalAiFile` shape from the spec.

- [ ] Write the tests on `pipeline.bonus.dev.load_context()`. Skip if `output/greenops.duckdb` is missing.
  - (a) 7 workloads; the tiers of `wl:marketing-classify` and `wl:support-agent` are `basic` and `advanced`.
  - (b) `gpt-oss-120b` on `hw:gpu-ml-01` is not feasible, with a VRAM reason.
  - (c) Every `hw:gpu-ml-01` scenario has `interacts_with` M-04, with CHF per year = office hours × derived hourly rate.
  - (d) Running `call(ctx, "run", ["local_ai"])` leaves `measures.json`, `summary.json` and `forecast.json` byte-identical (sha256).
  - (e) Every metric range satisfies low ≤ mid ≤ high.
- [ ] Run. Expect FAIL.
- [ ] Implement.
- [ ] Run. Expect PASS.
- [ ] Run `python -m pipeline.bonus.dev local_ai` and inspect the output.
- [ ] Commit.

### Task 3: Contract

**Files:**
- Modify: `contract/types.ts` (append the `LocalAi*` types)
- Modify: `contract/README.md` (file table row)
- Create: `contract/examples/local_ai.json` (trimmed real output)

- [ ] Add the types exactly as the module writes them.
- [ ] Generate the example from the real output (first 2 fits, 3 scenarios).
- [ ] Commit.

### Task 4: Frontend mode «AI locale»

**Files:**
- Modify: `web/src/store.ts` (`Mode` gets `'local_ai'`)
- Modify: `web/src/ui/Nav.tsx` (fifth entry in `MODES`)
- Modify: `web/src/ui/ModePanel.tsx` (render `<LocalAiPanel />`)
- Create: `web/src/ui/LocalAiPanel.tsx`
- Modify: `web/src/data/types.ts` (`LocalAiFile` types, `Dataset.localAi?: LocalAiFile | null`)
- Modify: `web/src/data/real.ts` (load `local_ai.json` with `.catch(() => null)`)

- [ ] Implement the panel:
  - an «Advisory, no numbers changed» badge;
  - best scenario cards (by cost, by CO₂) with 3-year API vs local cost, break-even, kWh and CO₂;
  - an expandable list of scenarios with pros, cons and `interacts_with`;
  - a workload table (tier, API cost per year, best fit);
  - a «Show gpu-ml-01» button that focuses the server in the scene.
- [ ] Run `npm run build` (tsc + vite) in `web/`. Expect success.
- [ ] Copy `output/local_ai.json` to `web/public/data/real/` and check it in the browser.
- [ ] Commit.
