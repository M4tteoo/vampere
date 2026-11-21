"""Run the pipeline:  python -m pipeline.run

Step 1–2 (Connect): read all 28 exports through their connectors, harmonize
time, currency, units and names, allocate to departments, reconcile sources
and write everything to output/greenops.duckdb + output/quality.json.
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from .harmonize import post, reconcile, store
from .harmonize.context import Context
from .harmonize.engine import run_connector


def main() -> int:
    t0 = time.time()
    ctx = Context.load()
    for name in ctx.config["connectors_order"]:
        run_connector(name, ctx)
    post.build_tables(ctx)
    post.fill_gaps(ctx)
    reconcile.run_all(ctx)
    post.finalize_fact_cost(ctx)
    post.tag_one_offs(ctx)
    post.detect_anomalies(ctx)
    post.apply_materiality(ctx)
    store.write(ctx)
    _summary(ctx, time.time() - t0)
    return 0


def _summary(ctx: Context, secs: float) -> None:
    fc = ctx.tables["fact_cost"]
    b = fc[fc["in_baseline"]]
    print(f"\nHarmonized {len(ctx.sources)} sources in {secs:.1f}s → {ctx.config['duckdb_file']}")
    print(f"fact_cost {len(fc):,} rows · fact_activity {len(ctx.tables['fact_activity']):,} rows · "
          f"issues {len(ctx.issues)}")
    tot = b.groupby("category")[["cost_chf", "cost_chf_low", "cost_chf_high"]].sum()
    tot.loc["TOTAL"] = tot.sum()
    print(f"\nBaseline {ctx.baseline[0]} … {ctx.baseline[1]} (CHF, actual):")
    print(tot.round(0).to_string())
    oo = ctx.tables["one_off_events"]
    print(f"Recurring baseline (actual − one-off excess CHF {oo['excess_chf'].sum():,.0f}): "
          f"CHF {b['cost_chf'].sum() - oo['excess_chf'].sum():,.0f}")
    iss = pd.DataFrame(ctx.issues)
    print("\nIssues by severity:", iss["severity"].value_counts().to_dict())


if __name__ == "__main__":
    sys.exit(main())
