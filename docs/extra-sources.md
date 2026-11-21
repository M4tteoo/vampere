# Extra sources → features

All 15 files in `data/case/extra/` are now used by at least one feature that reaches the user. They used to be loaded and cleaned, with several of them reaching only the advisor's reasoning or nothing at all. This note is for the **UI team** (what's new in the data and how to show it) and the **advisor owner** (what changed in the fact sheet and the safety gate).

Code: `pipeline/insights/` (one module per topic, code only) → `output/insights.json` (bonus module `extras`) and new advisor facts. Contract: `InsightsFile` in `contract/types.ts`, sample in `contract/examples/insights.json`.

## 1. Every extra source and where it goes

| Extra file | Feature | Output |
|---|---|---|
| `powerbi_usage.csv` | **Power BI report hygiene**: classify the 60 reports, clean-up, capacity downsizing | card `powerbi`, `insights.powerbi.reports`, advisor facts `pbi-kap.*` |
| `data_center_locations.csv` | **Where else could it run**: relocation options per resource, unused regions, **safety rule** for the advisor | card `regions`, `insights.regions`, facts `<resource>.co2_saved_if_moved_to_<LOC>`, `regions_offered` |
| `m365_usage.csv` | **M365 cross-check**: real active users vs licences; energy check of our SaaS factor (baseline unchanged) | card `m365`, facts `saas-m365.*` |
| `project_hours_monthly.csv` | **CO₂ per client project** (hours as allocation key), rechargeable share | card `project_footprint`, `insights.projects` |
| `projects.csv` | **Closed projects still billing** (e.g. P-004 AI pilot ended 30.06.2025, GPU still running) | card `closed_projects`, `insights.closed_projects`, facts `project.*` |
| `data_catalog_tables.csv` | unread and temporary tables (retention-bound tables locked) | card `data_catalog`, facts `dp-storage.*` |
| `log_volume.csv` | log retention (365 → 90 days) | card `logs`, facts `logs.*` |
| `ci_pipeline_runs.jsonl` | nightly builds without changes, re-runs, runner location | card `ci_builds`, facts `cicd.*` |
| `ai_agent_runs.jsonl` | report-agent outputs never opened, research-agent retries | card `ai_agents`, facts `ai-report.*`, `ai-agent2.*` |
| `web_traffic.csv` | bot share of the web volume | card `web_traffic`, fact `web-cdn.bot_share` |
| `backup_chains.csv` | three backup tools, missing restore tests, legal retention (**blocked**) | card `backups`, facts `st-backup.*` |
| `data_platform_jobs.csv` | carbon-aware timing; protection windows for the advisor; example Q3 | `jobs.json`, limits |
| `headcount.csv` | FTE allocation key, forecast growth, project footprint | `summary.json`, `forecast.json`, card `project_footprint` |
| `ai_invoice_monthly.csv` | invoice vs gateway contradiction, invoice adjustment in the totals | `quality.json`, limits |
| `provider_monthly_report.csv` | provider report vs invoices contradiction | `quality.json`, limits |

The same table, machine-readable: `insights.sources`.

## 2. Key results (baseline year)

| Card | Finding | Upper-bound potential per year | Status |
|---|---|---|---|
| Power BI | 21 of 60 reports refreshed daily but opened < 30 times a year; with 4 copies and 4 quarterly reports they make up **79 % of the refresh load** | clean-up: ≈ 10 kg CO₂ (the bill stays the same: billed per day) · + one tier down: **≈ CHF 12,000**, ≈ 19 kg CO₂ | clean-up ok · downsizing 🧑 IT + Finance |
| Closed projects | 4 completed projects still billing after their end: **CHF 27,095 and 735 kg CO₂** (P-004 AI pilot = the GPU server) | same | 🧑 project owner |
| Logs | 68 % of logs kept 365 days; 90 days by default cuts stored logs by 69 % | ≈ CHF 9,600, 106 kg CO₂ | 🧑 (compliance) |
| Regions | dp-dev → Zurich 863 kg, **GPU → Zurich 293 kg**, AWS test servers → Zurich 142 kg (compute +18 %, README list prices) | per option | — |
| Data catalogue | 9.2 TB of 27.6 TB unread or temporary, no retention; 3.9 TB with unknown retention | ≈ CHF 2,100, 18 kg CO₂ | 🧑 |
| Backups | 21 of 36 sources in 3 tools, 29 copies never restore-tested | locked: 10-year retention (T-1039, T-1195) | ⛔ |
| CI builds | 21 % of nightly builds without changes (3 % of build minutes) | small | ok |
| AI agents | 91 % of report-agent outputs never opened; research-agent 1.6 retries per run | small | ok |
| Web | 36 % of web volume to bots | small | 🧑 (keep useful bots) |
| Client projects | 531 kg CO₂ caused by client projects, ≈ 423 kg rechargeable | — | — |
| M365 | admin data: 104 active users vs 102 active licences (+2 %): licence data confirmed; 11 % of seats unused; our SaaS energy assumption is inside the bottom-up range | — | check only |

**Potentials are not measures:** they are upper bounds and are **not additive** with the package (they may overlap, e.g. closed project P-004 = the GPU measure). The advisor decides what becomes a measure; the Calculator computes its savings.

## 3. For the UI team

New file `output/insights.json` (contract `InsightsFile`), independent of the advisor's run:

- **`cards[]`**: an "Insights" panel, one card per topic. Show `headline`, `numbers` and `potential` (metrics with status ok / 🧑 / ⛔ and `decided_by`), `protected` (what must not be touched) and the `calc` panel. Highlight `entity_ids` in the scene.
- **Power BI (`powerbi.reports[]`)**: 60 small **screens on the Power BI rack** (`parent_id: res:pbi-kap`), coloured by `class`:
  - `in_use`: normal
  - `unused`: dimmed or "ghost"
  - `duplicate`: crossed out
  - `quarterly`: lit only in closing months
  - `protected`: lock (pbi-07, T-1167)

  The card's `steps` gives the two-step story: clean-up (energy only), then downsizing (francs, 🧑).
- **Regions (`regions`)**: `unused_regions` → **grey islands** (e.g. AWS Zurich: available, not used). `options[]` → relocation arrows with `co2_kg_saved` and `cost_note` (a visible trade-off: AWS Zurich is cleaner but costs +18 % for compute).
- **Projects (`projects[]`, `closed_projects[]`)**: a "CO₂ per client project" list (customer, rechargeable yes / partly / no, direct + allocated by hours); closed projects as "still running" warnings on their resources.
- **Assistant**: new read-only tool `extra_insights` (topic = a card, detail = a table). Questions like "Which Power BI reports does nobody open?" or "Could the GPU server run somewhere cleaner?" are answered from this file, with numbers verified.

## 4. For the advisor owner (Steps 5–8)

Input and output formats are unchanged. What changed:

1. **Fact sheet** (`pipeline/advisor/facts.py`, one block before "one-offs"): adds the facts of `pipeline.insights.advisor_facts(ctx)` (≈ 50 new ids, same `{value, unit, statement, sources}` format, no free text) and a new key **`regions_offered`** (`{provider: [location codes]}`), which reaches the LLM with the other entities. New fact ids:
   - `pbi-kap.reports_*`, `pbi-kap.refresh_load_removable_share`, `pbi-kap.cleanup_energy_share`, `pbi-kap.downsize_fits_half`, `pbi-kap.downsize_cost_share` (0.5, ASSUMPTION: capacity price ∝ capacity units), `pbi-kap.cleanup_and_downsize_energy_share`
   - `<resource>.co2_saved_if_moved_to_<LOC>` (only where the provider offers the location)
   - `dp-storage.removable_share`, `dp-storage.stale_gb_retention_unknown_share`, `logs.retention_90d_stored_share_saved`, `ai-agent2.research_retries_per_run`, `st-backup.copies_without_restore_test`
   - `project.<P-xxx>.cost_after_end`, `project.<P-xxx>.co2_after_end`
   - `saas-m365.active_users_admin`, `saas-m365.unused_seat_share`, `saas-m365.admin_vs_licence_difference`
2. **Safety gate** (`pipeline/advisor/calculator.py`, `savings()`): an effect with `relocate_to` outside the provider's locations is **rejected** with a problem ("Swiss hoster offers no region in DE …"), so the advisor revises. Today's committed package passes (dp-dev Azure Frankfurt → Zurich is offered).
3. **Instructions** (`pipeline/advisor/planner.py`): two lines, one about the region rule and the relocation facts, one telling the advisor that the Power BI capacity is billed per day (clean-up = energy only, francs need downsizing = human decision).
4. **Re-run:** the committed package was produced before these facts existed. A new `--advisor` run can now use them (Power BI downsizing, log retention, GPU to Zurich…). Pick the demo run deliberately; see section 6.

## 5. Assumptions and sources

- **Power BI capacity price ∝ capacity units** (one tier down ≈ half the price): Fabric / Power BI capacities are sized in capacity units (Azure pricing page, SKUs F2…F2048); **verify the price for the actual SKU** before deciding. A paused pay-as-you-go capacity stops compute billing (Microsoft Learn, "Pause and resume your capacity"). Capacity energy: engine model (8 v-cores, 25 GB, 50 % utilisation), utilisation proportional to the refresh load.
- **Regions:** grid factors only for CH, DE, IE, EU (factors.yaml). France, Netherlands and Sweden are listed without a CO₂ value. AWS compute prices from the case README (m6i.large Zurich 0.1265 vs Ireland 0.107 USD/h); other price differences are not in the data.
- **M365 energy check:** storage × factors.yaml; video calls 0.3–0.6 GB/h × network factor (assumption), high end from Obringer et al. 2021 (≈ 160 g CO₂e per hour of videoconferencing). Used as a check only; the baseline is unchanged.
- **Projects:** one FTE = 182 h a month (Swiss 42-hour week); time not booked on projects stays unassigned; "partly" rechargeable counted as 50 %.
- **Logs:** stored volume ∝ daily volume × retention days (steady state).

## 6. How to check

```bash
.venv/bin/python -m pipeline.run                     # writes output/insights.json (bonus module «extras»)
.venv/bin/python -m unittest discover -s tests -t .  # incl. tests/test_insights.py (every extra source used, region rule, Power BI classes…)
.venv/bin/python -m tests.audit_outputs              # incl. 5 checks on insights.json
.venv/bin/python -m assistant eval                   # incl. Power BI, GPU region and a planted «pbi-07 no longer protected» injection
```
