"""Run the pipeline:  python -m pipeline.run [--advisor] [--scenario ch_production] [--out output/ch_production]

Step 1–2 (Connect): read all 28 exports through their connectors, harmonize
time, currency, units and names, allocate to departments, reconcile sources
and write everything to output/greenops.duckdb + output/quality.json.
Bonus modules (pipeline/bonus/, enabled in config.yaml) hook in after the
energy engine and at the end.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from . import bonus
from .harmonize import post, reconcile, store
from .harmonize.context import Context
from .harmonize.engine import run_connector
from .energy import engine as energy
from .export import answers, frontend, submission
from . import advisor


def _args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m pipeline.run")
    p.add_argument("--scenario", choices=["ch_consumption", "ch_production"],
                   help="Swiss grid mix scenario (overrides config.yaml scenario)")
    p.add_argument("--out", help="output folder (overrides config.yaml output_dir; DuckDB goes inside it)")
    p.add_argument("--advisor", action="store_true",
                   help="call the LLMs (ticket reader + advisor) and save their answers; without it the last saved answers are re-applied")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    t0 = time.time()
    args = _args(argv)
    ctx = Context.load()
    if args.scenario:
        ctx.config["scenario"] = args.scenario
    if args.out:
        ctx.config["output_dir"] = args.out
        ctx.config["duckdb_file"] = str(Path(args.out) / "greenops.duckdb")
    for name in ctx.config["connectors_order"]:
        run_connector(name, ctx)
    post.build_tables(ctx)
    post.fill_gaps(ctx)
    reconcile.run_all(ctx)
    post.finalize_fact_cost(ctx)
    post.tag_one_offs(ctx)
    post.detect_anomalies(ctx)
    energy.compute(ctx)
    status = bonus.after_energy(ctx)    # bonus modules that add columns to fact_cost (e.g. market-based CO2)
    post.apply_materiality(ctx)
    if args.advisor:
        advisor.run_llm(ctx)  # LLM: reads tickets, finds waste, designs measures (answers saved in output/advisor/)
    advisor.apply(ctx)        # code: validates the answers, computes savings, safety gate, target check
    submission.write_baseline(ctx)
    store.write(ctx)
    frontend.export(ctx)
    advisor.export(ctx)
    answers.write(ctx)
    status |= bonus.after_export(ctx)   # bonus modules that write their own outputs
    _summary(ctx, time.time() - t0)
    if status:
        print("\nBonus modules:", status)
    return 0


def _summary(ctx: Context, secs: float) -> None:
    fc = ctx.tables["fact_cost"]
    b = fc[fc["in_baseline"]]
    print(f"\nHarmonized {len(ctx.sources)} sources in {secs:.1f}s → {ctx.config['duckdb_file']}")
    print(f"fact_cost {len(fc):,} rows · fact_activity {len(ctx.tables['fact_activity']):,} rows · "
          f"issues {len(ctx.issues)}")
    tot = b.groupby("category")[["cost_chf", "kwh_low", "kwh_mid", "kwh_high", "co2_kg_low", "co2_kg_mid", "co2_kg_high"]].sum()
    tot.loc["TOTAL"] = tot.sum()
    print(f"\nBaseline {ctx.baseline[0]} … {ctx.baseline[1]} (actual; scenario {ctx.config.get('scenario')}):")
    print(tot.round(0).to_string())
    oo = ctx.tables["one_off_events"]
    print(f"Recurring baseline (actual − one-off excess CHF {oo['excess_chf'].sum():,.0f}): "
          f"CHF {b['cost_chf'].sum() - oo['excess_chf'].sum():,.0f}")
    iss = pd.DataFrame(ctx.issues)
    print("\nIssues by severity:", iss["severity"].value_counts().to_dict())
    a = getattr(ctx, "advisor", None)
    if not a:
        print("\nAdvisor: no saved LLM answers (run with --advisor)")
        return
    p = a["package"]
    print(f"\nAdvisor: {len(a['findings'])} findings · {len(a['measures'])} measures · {len(a['limits'])} limits")
    for m in a["measures"]:
        s = m["savings"]
        print(f"  {m['id']} [{m['status']:7s}]{' *' if m['in_package'] else '  '} {m['title'][:60]:60s} "
              f"CHF {s['cost_chf']['mid']:>8,.0f} · {s['co2_kg']['mid']:>6,.0f} kg CO2 · {m['effort_days']} d")
    r = p["reduction"]
    print(f"Package (*): CO2 −{r['co2']['mid']:.1%} · cost −{r['cost']['mid']:.1%} · effort {p['effort_days']} d "
          f"(CHF {p['effort_chf']:,.0f}) · meets {p['meets']}")
    fp = a.get("ai_footprint")
    if fp:
        print(f"AI used by this analysis: {fp['calls']} LLM calls · {fp['output_equivalent_tokens']:,} eq. tokens · "
              f"{fp['kwh']['mid'] * 1000:.1f} Wh ({fp['kwh']['low'] * 1000:.1f}–{fp['kwh']['high'] * 1000:.1f}) · "
              f"{fp['co2_kg']['mid'] * 1000:.1f} g CO2")


if __name__ == "__main__":
    sys.exit(main())
