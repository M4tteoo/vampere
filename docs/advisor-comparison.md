# Advisor: AI-only vs code-driven (Steps 5–8)

How the advisor changed between the first LLM version (21 Nov morning) and the current version on `main` (21 Nov evening: the code-driven advisor plus idle-power energy, safety per option and option-specific safety levels). Every figure comes from the case data, with the same harmonizer and the same energy factors in both versions. Sources: `output/advisor/plan_raw.json` (per-call token usage returned by the API), `output/measures.json`, `output/montecarlo.json`, `output/safety_scenarios.json`.

## The two designs in one picture

| | Before: AI-only advisor | Now: code-driven advisor |
|---|---|---|
| Who finds the waste | one large LLM call | code (toolbox of generic levers) |
| Who designs the measures | the same LLM call | code proposes candidates; **4 small agents in parallel** make them realistic and add ideas |
| Who picks the package | the LLM (revised until the target is met) | **an exact optimiser** (code), one package per goal |
| How safety is checked | not checked | **10,000 Monte Carlo scenarios** of the uncertain factors, for every option |
| Ticket reading | 1 call, large model | 4 parallel batches, large model; runs **only when the tickets change** |
| Same data, second run | the whole analysis again | **saved answers reused** (fingerprint) |
| What the manager can do | accept one package | **choose between 4 options**, see each one's safety, **remove measures** with live recalculation |

## Speed

| | Before | Now |
|---|---:|---:|
| Fresh analysis (tickets + measures) | **379 s** (6 min 19 s) | **~22 s**, about 17× faster |
| Data changed, tickets unchanged | 379 s | **13–14 s**, about 27× faster |
| Same data again | 379 s | **0 s** (reused) |
| Whole pipeline incl. 28 files and bonus modules | ~6.5 min | **~10 s** reused · ~25–35 s fresh |

Where the old time went: one call wrote 24,630 tokens, 17,454 of them invisible "reasoning", in 267 s. The new design splits the work into small calls that run at the same time, so the wait is only as long as the slowest call, not the sum of all calls.

## AI energy of the tool itself

The tool's own AI use is converted the same way as the company's AI use: output-equivalent tokens × 0.5 Wh per 1,000 tokens (range 0.1–2.0), EU grid 0.213 kg CO₂/kWh.

| | Before | Now: fresh | Now: data changed | Now: same data |
|---|---:|---:|---:|---:|
| AI calls | 3 | 8 | 4 | 0 |
| Output-equivalent tokens | 42,912 | ~6,230 | 2,123 | 0 |
| Energy (mid, range) | **21.5 Wh** (4.3–85.8) | **3.1 Wh** (0.6–12.5) | **1.1 Wh** (0.2–4.2) | **0 Wh** |
| CO₂ | 4.6 g | 0.7 g | 0.2 g | 0 g |
| Saving vs before | – | about 7× less | about 20× less | 100 % |

"Fresh" adds the ticket reader (measured at 14:35; the reader and the tickets have not changed since) to the four agents (measured at 16:07).

## Quality of the result

**The four options** (the manager picks one; all stay within the CHF 16,500 budget and reach −40 % CO₂ and −25 % cost with the middle estimate):

| Option | CO₂ (mid) | Cost | Effort | Safe in | Minimum required |
|---|---:|---:|---:|---:|---:|
| Climate first *(default)* | **−48.5 %** | −25.7 % (CHF 121,900/yr) | 15 days · 6 measures | **95 %** ★ safest | 70 % |
| Best value | −45.3 % | −25.5 % (CHF 121,300/yr) | **13.5 days** · 7 measures | 84 % | 80 % |
| Francs first | −44.8 % | **−30.1 %** (CHF 142,900/yr) | 15 days · 10 measures | 75 % | 70 % |
| Safest | same package as climate first | | | 95 % | – |

"Safe in X %" is the share of 10,000 Monte Carlo scenarios in which the option still reaches −40 % CO₂. Each scenario draws every uncertain factor (grid mix, PUE, power per vCPU, memory, GPU idle power, storage, network, AI energy) from its range. The background load (below) is held at 5 % in every scenario. The draws use the same seed and model as the Monte Carlo panel, so the panel and the options always show the same number.

**Before vs now** (default option):

| | Before | Now (climate first) |
|---|---|---|
| CO₂ reduction, middle estimate | −40.1 % | **−48.5 %** |
| Monte Carlo: share of 10,000 scenarios reaching −40 % | 54 % | **95 %** (median −46.2 %, 5th percentile −39.9 %) |
| CO₂ reduction, all factors pessimistic at once | −34.7 % | −38.2 % (see caveats) |
| Cost reduction | −27.1 % | −25.7 % |
| Implementation effort | 15 days (CHF 16,500) | 15 days (CHF 16,500) |
| Measures considered | 8 | 38 (incl. alternatives, combined variants and protected edge cases) |
| Findings | 6 | 31 |
| Package choice | the LLM's best attempt (round 1 missed the target: −39.9 %) | **mathematically optimal** for the goal, within budget, no double counting |
| Options | one package | **4, switchable instantly**, each with its safety |
| Manager control | none | remove any measure → totals and safety recalculated live |

Why the options differ: climate first buys the most CO₂, best value buys the target with the fewest days, and francs first adds licence clean-ups, which save money but almost no energy. Each option has a minimum safety level matching its risk appetite. Best value is the "sensible compromise", so it must be safe in at least 80 % of scenarios; the others need at least 70 %.

## Energy model change: idle hours at idle power

The first code-driven version valued every removed server hour at the server's *average* power. In reality, a server that sits idle draws much less than one doing work. The current version values hours **without work** at idle power: CPU minimum power plus a small **background load**, because monitoring agents, the operating system and cluster services keep running. The background load is a **team assumption** of 5 % CPU (range 0–10 %), shown in the submission table as an «Additional» row (`factors.yaml` → `compute.idle_background_utilisation`).

Effect: pausing idle servers saves less CO₂ than before. It is more realistic. It is one reason the default option went from −50.4 % to −48.5 % (fresh agent runs also vary a little), and it is why safety is now reported as a probability instead of a yes/no.

## Safety against manipulation (unchanged or stronger)

| | Before | Now |
|---|---|---|
| The reasoning LLM sees free text from the data | no | no (the agents see only numbers and ids) |
| Texts aimed at AI systems reach the ticket reader | no (withheld) | no (withheld) |
| Restrictions can unlock a protected resource | no | no |
| Every number computed by code | yes | yes |
| Code checks the reader's targets against the ticket's own resource | no | **yes** (fixed one wrong target automatically) |
| «Deliberately kept on» list (emergency server, backups, audit report) | implicit (2 blocked measures) | **explicit**, with the reason for each |
| Injection tests | 6 structural + 3 live | **8 structural** + 3 live (new: agents get no data text; the optimiser never picks a blocked measure, for all 4 options) |

## Figures for the pitch

- «The analysis used to take **6 minutes**. Now it takes **20 seconds**, and zero when the data hasn't changed.»
- «Our tool's own AI uses **7 to 20 times less energy**: about **3 Wh** for a full analysis, about what a laptop uses in a few minutes, and **0 Wh** when nothing has changed. We don't run AI that isn't needed, which is exactly what we recommend to the SME.»
- «The AI does the judgement, the code does the maths: each option is **provably the best combination** for its goal within CHF 16,500, not a guess.»
- «The manager chooses what matters: **climate first, best value, francs first or safest**. Every option shows how likely it is to hit the target, and any measure can be removed with the numbers updating instantly.»
- «The default option cuts **−48.5 % CO₂** and **−26 % cost**, and reaches the −40 % target in **95 % of 10,000** Monte Carlo scenarios, up from 54 %.»

## Honest caveats

- **Background load is an assumption.** The 5 % CPU during idle hours is not in the case data and comes from no single source. It is a team estimate, used only to value removed idle hours. The Monte Carlo keeps it fixed at 5 % and does not vary it over its 0–10 % range. With 0 %, the pause measures would save somewhat more. With 10 %, they would save somewhat less.
- **The "everything pessimistic at once" corner misses the target.** If every factor sits at its worst value *at the same time*, no option reaches −40 % within the budget (climate first: −38.2 %). That combination is very unlikely, because the factors are independent. This is why safety is reported as the Monte Carlo share instead of this corner case. The corner is still in the outputs (`meets_at_low`) and is not hidden.
- **Run-to-run variation.** Each fresh run of the agents calibrates slightly differently. Once saved, the result is stable: same data, same answer.
- **Production decisions.** Several CO₂ levers (pausing or retiring idle servers, the GPU server) are marked «a person decides». A realistic share for production may be lower than the one the agent kept.
- **What is compared.** Both versions use the same data, harmonizer and energy factors. The AI-only figures are from its final saved run. The current figures are from `main` after the merge of 21 Nov evening.
