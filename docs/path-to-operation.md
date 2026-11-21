# Path to operation

How the prototype becomes a monthly routine for an SME without a data department.

## 1. What runs, and when

| When | What | Who | Effort |
|---|---|---|---|
| Monthly, after invoice close | Drop the month's exports (cloud invoices, licence lists, tickets, monitoring) into the input folder | IT manager | 30 min |
| Automatically | `pipeline.run`: clean and harmonise (28 sources), allocate, kWh and CO₂, bonus analyses, contract files, both submission tables | scheduler | ~10 s |
| Monthly or quarterly | `pipeline.run --advisor`: the LLM reads new tickets, finds waste, redesigns the package; code recomputes every number and checks every rule | scheduler | a few minutes, 3–4 LLM calls (≈ 20 Wh, ≈ 5 g CO₂ per run, measured and reported with the results) |
| After each advisor run | Decisions on 🧑 measures (role named per measure, data attached) | Heads of IT / Finance / business | 1 meeting |
| On demand | Dashboard and chat assistant for management and finance | everyone | none |

The pipeline is deterministic: the same exports give the same numbers on any machine. Without network access and without an API key, it re-applies the last saved advisor answers.

## 2. Where it runs

- **Today:** Python + DuckDB on a laptop, static web app for the 3D view, small HTTP service for the assistant.
- **At an SME with Microsoft 365:** the same code as a scheduled notebook in Microsoft Fabric, or Databricks if already used (ALTYCA's platforms). Exports land in OneLake / a lakehouse, the DuckDB tables become lakehouse tables, the JSON files feed the web app or Power BI. Nothing in the logic changes.
- **Cost:** compute is negligible (seconds per month). The LLM is a few calls per analysis plus the chat. Most of the cost is the first set-up.

## 3. Onboarding a new SME (≈ 5–8 person-days with ALTYCA)

1. Map each export with a connector YAML (`pipeline/connectors/*.yaml`: columns, date format, currency, units). Most transformations are reusable by name. **2–3 d**
2. Master data: resource → department, tool, cost center, responsible role (one CSV), locations of the providers. **1 d**
3. Review the factors (`pipeline/energy/factors.yaml`: grid per location, PUE, energy per unit). Defaults are researched, with source and range. **0.5 d**
4. First run, plausibility check against invoices, first advisor run and decision meeting. **1–2 d**

## 4. Safety and governance

- **No AI in the numbers:** every CHF, kWh and CO₂ value is computed by code from the data, with an open calculation.
- **Text in the data is quarantined.** It is classified first; instructions aimed at AI are withheld. Only an isolated reader sees ticket text, and it can only *add* restrictions. Red-team tests run with every change.
- **Nothing is switched off automatically:** the tool recommends; blocked measures stay blocked; 🧑 measures wait for the named role.
- **Secrets:** the API key lives in the environment (`.env` / a key vault), never in the repository.

## 5. What we would add next

- Hourly carbon data from a live API (carbon-aware scheduling with forecasts instead of yearly profiles).
- Direct connectors (Azure Cost Management, AWS CUR, Microsoft 365 admin APIs) instead of file exports.
- A savings tracker: planned versus measured after each measure goes live (the forecast's «with package» line becomes the target).
- Market-based reporting once suppliers provide verified certificates.
