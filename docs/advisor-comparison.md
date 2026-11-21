# Advisor: AI-only vs code-driven (Steps 5–8)

How the advisor changed between the first LLM version (`main`, 21 Nov morning) and the optimised version (branch `fast-advisor`, 21 Nov afternoon). All figures are measured on the case data, with the same harmonizer, the same energy factors and the same savings method in both versions. Sources: `output/advisor/plan_raw.json` (per-call token usage returned by the API), `output/measures.json`, `output/montecarlo.json`.

## The two designs in one picture

| | Before: AI-only advisor | After: code-driven advisor |
|---|---|---|
| Who finds the waste | one large LLM call | code (toolbox of generic levers) |
| Who designs the measures | the same LLM call | code proposes candidates; **4 small agents in parallel** make them realistic and add ideas |
| Who picks the package | the LLM (revised until the target is met) | **an exact optimiser** (code) |
| Ticket reading | 1 call, large model | 4 parallel batches, large model; runs **only when the tickets change** |
| Same data, second run | the whole analysis again | **saved answers reused** (fingerprint) |

## Speed

| | Before | After |
|---|---:|---:|
| Fresh analysis (tickets + measures) | **379 s** (6 min 19 s) | **21.7 s**, about 17× faster |
| Data changed, tickets unchanged | 379 s | **11–14 s**, about 30× faster |
| Same data again | 379 s | **0 s** (reused) |
| Whole pipeline incl. 28 files and bonus modules | ~6.5 min | **~10 s** reused · ~20–30 s fresh |

Where the old time went: one call wrote 24,630 tokens, 17,454 of them invisible "reasoning", in 267 s. The new design splits the work into small calls that run at the same time, so the wait is the slowest call, not the sum of all calls.

## AI energy of the tool itself

Same conversion as for the company's own AI use: output-equivalent tokens × 0.5 Wh per 1,000 (range 0.1–2.0), EU grid 0.213 kg CO₂/kWh.

| | Before | After: fresh | After: data changed | After: same data |
|---|---:|---:|---:|---:|
| AI calls | 3 | 8 | 4 | 0 |
| Output-equivalent tokens | 42,912 | 5,726 | 1,619 | 0 |
| Energy (mid, range) | **21.5 Wh** (4.3–85.8) | **2.9 Wh** (0.6–11.4) | **0.8 Wh** (0.2–3.2) | **0 Wh** |
| CO₂ | 4.6 g | 0.6 g | 0.2 g | 0 g |
| Saving vs before | – | about 7× less | about 27× less | 100 % |

## Quality of the result

| | Before | After (default goal «climate first») |
|---|---|---|
| CO₂ reduction, middle estimate | −40.1 % | **−50.4 %** |
| CO₂ reduction, pessimistic factors | −34.7 % (**misses 40 %**) | **−41.9 %** (meets 40 %) |
| Monte Carlo: share of 10,000 factor scenarios reaching −40 % | 54 % | **100 %** (median −47.9 %) |
| Cost reduction | −27.1 % | −25.4 % |
| Implementation effort | 15 days (CHF 16,500) | 15 days (CHF 16,500) |
| Measures considered | 8 | 33 (incl. alternatives and protected edge cases) |
| Findings | 6 | 29 |
| Package choice | the LLM's best attempt (round 1 missed the target: −39.9 %) | **mathematically optimal** for the goal, within budget, no double counting |
| Goal options | one package | **3, switchable instantly**: climate first · best value (13 days, −49.6 %) · francs first (−29.5 % cost) |
| Safety margin | not checked | every goal must reach −40 % CO₂ **even with pessimistic factors** |

The higher CO₂ reduction comes from the optimiser being able to compare 33 options and pick the best combination, including one the AI-only version never proposed: auto-pausing the production platform between its scheduled jobs. That measure is marked «a person decides» (production).

## Safety (unchanged or stronger)

| | Before | After |
|---|---|---|
| The reasoning LLM sees free text from the data | no | no (the agents see only numbers and ids) |
| Texts aimed at AI systems reach the ticket reader | no (withheld) | no (withheld) |
| Restrictions can unlock a protected resource | no | no |
| Every number computed by code | yes | yes |
| Code checks the reader's targets against the ticket's own resource | no | **yes** (fixed one wrong target automatically) |
| «Deliberately kept on» list (emergency server, backups, audit report) | implicit (2 blocked measures) | **explicit**, with the reason for each |
| Injection tests | 6 structural + 3 live | **8 structural** + 3 live (new: agents get no data text; the optimiser never picks a blocked measure) |

## Figures for the pitch

- «The analysis used to take **6 minutes**. Now it takes **20 seconds**, and zero when the data hasn't changed.»
- «Our tool's own AI uses **7 to 27 times less energy**: about **3 Wh** for a full analysis, about as much as a laptop in a few minutes, and **0 Wh** when nothing changed. We don't run AI that isn't needed, which is exactly what we recommend to the SME.»
- «The AI does the judgement, the code does the maths: the package is **provably the best combination** within CHF 16,500, not a guess.»
- «It reaches **−50 % CO₂** and **−25 % cost**, and still **−42 %** with the most pessimistic factors. It meets the target in **100 % of 10,000** Monte Carlo scenarios, up from 54 %.»
- «The manager chooses what matters: **climate first, best value or francs first**, and gets the optimal package instantly.»

## Honest caveats

- **Run-to-run variation.** Each fresh run of the agents calibrates slightly differently. Two fresh runs gave −44 % and −53 % for «climate first». Once saved, the result is stable: same data, same answer.
- **Idle-hour energy.** Valuing removed idle hours at idle power, which is more accurate because an idle server draws less, is implemented but switched off for now (`advisor.value_idle_hours_at_idle_power`). With it on, the CO₂ savings of the pause measures drop, and with the current budget no goal reaches −40 % in the pessimistic case. It is under review.
- **The production pause.** The biggest CO₂ lever in the new package (auto-pausing the production platform between jobs) needs the owner's decision. A realistic share for production may be lower than the one the agent kept.
- **What is compared.** Both versions use the same data, harmonizer, energy factors and savings method. The AI-only figures are from its final saved run, the code-driven figures from the runs of 21 Nov at 14:35 (full fresh) and 15:04 (agents only).
