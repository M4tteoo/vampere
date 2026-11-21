# Data contract · backend → frontend (v0.1, draft)

The pipeline writes JSON files; the 3D frontend reads them. This folder fixes their format so both sides can work in parallel: the frontend builds on the examples, and switches to the real files by replacing the folder.

- `types.ts`: the types, field by field. **Single source of truth.** Copy it into `web/src/`.
- `examples/`: one sample per file. Numbers are illustrative (costs are close to the real baseline, kWh and CO₂ are placeholders until Step 3).
- Real files: `python -m pipeline.run` writes them to `output/`; the frontend serves them from `web/public/data/`.

## Rules

Findings, measures and limits are written by an LLM (the advisor and the ticket reader, `pipeline/advisor/`); every number in them is computed by code. Extra fields the advisor adds (`effects`, `proposed_status`, `risks`, `assumptions`, `generated_by`) are optional for the frontend.


1. **Every file** has a `meta` block: `schema_version`, `generated_at`, `baseline` (2025-09-01 … 2026-08-31), `scenario`.
2. **Every figure is a range** `{low, mid, high}`. Show `mid`; the range goes in the calc panel.
3. **Metrics** always carry `cost_chf`, `cost_eur`, `cost_usd`, `kwh`, `co2_kg`. The currency selector just picks a field. **The frontend never converts currencies.** The backend has already converted each month at that month's rate, and values measure savings at the baseline-average rate, so exchange-rate moves never look like savings.
4. **`kwh` / `co2_kg` may be `null`** while not computed yet, or where not applicable. Show "–", never 0.
5. **Every number opens** (B3): entities, findings, measures and summary carry a `calc` object with the formula, inputs, factor ids, source files, row count, value status and quality issue ids.
6. **IDs** are prefixed and stable:
   - `dept:IT`: a department (room)
   - `loc:DE`: a location (island)
   - `res:dp-dev`: a billed resource (rack)
   - `srv:gpu-ml-01`: a server
   - `lic:ChatGPT Team@Sales`: one product's seats in one room
   - `F-01`, `M-01`, `L-01`, `Q-0001`: findings, measures, limits, quality issues
   - `Q-…` IDs are numbered in log order. They are stable across runs of the same code, but can shift when the pipeline changes. Always take them from the files and never hard-code them in the frontend.
7. **Dates** are ISO. Months are the first day of the month. Times are local Europe/Zurich with offset.
8. **Text from the data is untrusted** (some of it contains prompt injections). Fields such as `Limit.quote` must be rendered as **plain text only**, never as HTML or markdown. If `quote_risk = "flagged"`, show "[withheld]" with a link to the quality issue.
9. **Entity state.** The backend decides it; the frontend only paints it. `flags` lists every state that applies; `state` is the primary one, with precedence `locked > handover > contradiction > waste > driver > normal`. A contradiction takes that precedence only when it is **material**, meaning above the materiality threshold in `pipeline/config.yaml` (the same rule as hand-overs). An immaterial contradiction ranks below the other states but **always stays in `flags`** and in the calc panel (`issue_ids`), so the scene must show it, for example as a small ⚠️ badge. Nothing is hidden.
10. **Measures can be summed.** The backend defines them without overlap, so the frontend may add up the savings of any selection to update the indicators. Blocked measures are never in `package`.

## Files

| File | Content | Produced by | Status |
|---|---|---|---|
| `quality.json` | Intake screen: counters, sources, every fix / estimate / contradiction | harmonizer | **available now** |
| `fx.json` | exchange rates, for calc panels only | harmonizer | **available now** |
| `summary.json` | baseline, target, breakdowns, flows (cables), one-offs, coverage | Step 4 | **available now** |
| `entities.json` | every object in the scene with metrics, state and links | Steps 4–7 | **available now** (states preliminary: driver / contradiction until Steps 5–7) |
| `timeseries.json` | monthly series for every entity, daily for dp-prod, dp-dev, gpu-ml | Step 4 | **available now** |
| `factors.json` | conversion factors with low / mid / high + source | Step 3 | **available now** |
| `findings.json` | drivers and waste, each with its numerical evidence | LLM advisor (evidence values by code) | **available now** |
| `measures.json` | measures + recommended package + target check | LLM advisor (savings, status gate, target check by code) | **available now** |
| `limits.json` | protection windows, blocks, hand-overs, contradictions, with concrete dates | LLM ticket reader + scheduler (code) | **available now** |
| forecast | `forecast.json` | A2 | 52 weeks in monthly buckets; `without` uses original history and `with` uses already-optimized history (`null` if absent); final month is prorated |
| optimized history | `optimized_history.json` | Step 9 | Replay coverage: applied, skipped, and human-confirmation measures; optimized history itself is in DuckDB |
| bonus | `montecarlo.json`, `jobs.json`, `clusters.json` | bonus steps | defined when built |

## Changes from the first list in frontend-3d.todo

- `metrics` values are ranges, and cost comes in three currencies (no conversion in the frontend).
- Each entity has a `parent_id` (server → resource → island, seats → room) and a `flags` array next to the primary `state`.
- New entity kinds `server` and `license_group`, so desks in rooms map to seats.
- `summary.flows` gives the department → location cables, with their kWh and CO₂.
- `measures.json` also contains the `package` chosen by the optimizer, with `meets` and `meets_at_low` for the robustness check.
- `limits.json` has ready-to-draw `occurrences`, so the frontend needs no calendar logic.
- `quality.json` follows the harmonizer's richer structure (`issues` with `severity`, `amount_chf`, `at_risk_chf`).

## Open questions for the frontend

1. **Server granularity.** 53 servers individually (`srv:*` under their resource), or only the 15 billed resources? Proposal: all servers, since 24 tiny sandboxes can be instanced.
2. **Seats.** Is one `license_group` per product × department (about 30 objects) right for the desks?
3. **Daily series.** Is daily data for dp-prod, dp-dev and gpu-ml enough for the day/night slider (B11), or do you need hourly?
4. **State precedence.** Is it OK?
