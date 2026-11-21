"""Fill the submission templates from the engine (never by hand).

output/submission/template_baseline_and_assumptions.csv
  - same rows, order, units and columns as data/case/template_baseline_and_assumptions.csv
  - totals from fact_cost (baseline year), factors from pipeline/energy/factors.yaml
  - Bonus rows stay empty until the bonus function is built
  - factors we use beyond the template are appended, marked «Additional»
"""
from __future__ import annotations

import csv

import pandas as pd

from ..energy.engine import template_rows
from ..harmonize.context import Context

TEMPLATE = "template_baseline_and_assumptions.csv"
COLUMNS = ["parameter", "must_or_bonus", "value_low", "value_mid", "value_high", "unit", "source",
           "calculation_or_assumption"]
SOURCE_ENGINE = ("Pipeline output: output/greenops.duckdb, table fact_cost, baseline year {b0} … {b1} "
                 "(python -m pipeline.run, generated {date}); data: «Sample data ALTYCA, sprintd Basel 2026»")


def _fmt(v, nd=6):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    v = float(v)
    return f"{v:.0f}" if abs(v) >= 100 else f"{v:.{nd}g}"


def write_baseline(ctx: Context) -> None:
    tpl = pd.read_csv(ctx.data_dir / TEMPLATE, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    fc = ctx.tables["fact_cost"]
    b = fc[fc["in_baseline"]]
    b0, b1 = ctx.baseline
    src = SOURCE_ENGINE.format(b0=b0, b1=b1, date=pd.Timestamp.now().strftime("%Y-%m-%d"))
    oo = ctx.tables["one_off_events"]
    cov = (b.groupby("value_status")["cost_chf"].sum() / b["cost_chf"].sum())
    by_cat = b.groupby("category")[["cost_chf", "kwh_mid", "co2_kg_mid"]].sum().round(0)

    def cats(col, unit):
        return "; ".join(f"{c} {v:,.0f} {unit}" for c, v in by_cat[col].items())

    totals = {
        "total_cost_baseline_year_chf": (
            b["cost_chf_low"].sum(), b["cost_chf"].sum(), b["cost_chf_high"].sum(),
            "Sum of all billing lines in the baseline year: Azure, AWS, Swiss hoster, AI gateway, AI subscriptions, "
            "SaaS contracts (Final versions only, duplicates removed), plus the AI invoice adjustment "
            "(invoices exceed the gateway by ~5.9 %). EUR/USD converted at the monthly ECB rate of the usage month. "
            f"By category: {cats('cost_chf', 'CHF')}. "
            f"Observed {cov.get('observed', 0):.1%} of the value; estimated {cov.get('estimated', 0):.1%} "
            "(missing costs = quantity × median unit price; missing days = median of neighbouring days) → range. "
            f"Actual baseline incl. one-off events; recurring baseline = CHF {b['cost_chf'].sum() - oo['excess_chf'].sum():,.0f} "
            f"(one-off excess CHF {oo['excess_chf'].sum():,.0f}: loop T-1212, migration egress T-1189, SLA credits)."),
        "total_energy_baseline_year_kwh": (
            b["kwh_low"].sum(), b["kwh_mid"].sum(), b["kwh_high"].sum(),
            "Per billing line: usage × energy per unit at the observed utilisation × PUE (infrastructure); "
            "AI tokens and subscription messages with fully loaded per-token / per-message factors; SaaS per active licence. "
            f"By category: {cats('kwh_mid', 'kWh')}. low/high = all low / all high factors combined."),
        "total_co2_location_based_baseline_year_kg": (
            b["co2_kg_low"].sum(), b["co2_kg_mid"].sum(), b["co2_kg_high"].sum(),
            "kWh of each line × grid mix at the line's location (CH / DE / IE; AI and SaaS: EU average). "
            f"Swiss scenario: {ctx.config.get('scenario')}. By category: {cats('co2_kg_mid', 'kg')}. "
            "low/high = all low / all high factors combined."),
    }

    allocation = (
        "Direct allocation first, in this order: (1) department tag on the billing row (Azure/AWS tags, AI gateway "
        "department); (2) cost center on the row (hoster, subscriptions, SaaS); (3) resource master data "
        "(mapping_departments_tools.csv). Costs that would remain shared (department «Overhead») are split by the "
        "monthly FTE share of each department (headcount.csv): stable, understandable and available every month. "
        f"Result for the baseline year: {1 - (b['allocation_method'] == 'unallocated').mean():.0%} of the lines allocated "
        "directly, no residual Overhead (e.g. the office AI assistant is allocated by the department on each gateway row).")

    factors = {r["id"]: r for r in template_rows()}
    out = []
    for _, row in tpl.iterrows():
        p = row["parameter"]
        r = dict(row)
        if p in totals:
            lo, mid, hi, calc = totals[p]
            r.update(value_low=_fmt(lo), value_mid=_fmt(mid), value_high=_fmt(hi), source=src,
                     calculation_or_assumption=calc)
        elif p == "allocation_rule_shared_costs":
            r.update(value_mid="Row tag → row cost center → mapping; residual shared costs by FTE share",
                     source="mapping_departments_tools.csv, headcount.csv; pipeline/harmonize/engine.py",
                     calculation_or_assumption=allocation)
        elif p in factors:
            f = factors[p]
            r.update(value_low=_fmt(f["low"]), value_mid=_fmt(f["mid"]), value_high=_fmt(f["high"]),
                     source=f["source"], calculation_or_assumption=f["calculation"])
        out.append(r)

    used = set(tpl["parameter"])
    for f in template_rows():
        if f["id"] not in used:
            out.append({"parameter": f["id"], "must_or_bonus": "Additional", "value_low": _fmt(f["low"]),
                        "value_mid": _fmt(f["mid"]), "value_high": _fmt(f["high"]), "unit": f["unit"],
                        "source": f["source"], "calculation_or_assumption": f["label"] + ". " + f["calculation"]})

    path = ctx.output_dir / "submission"
    path.mkdir(parents=True, exist_ok=True)
    with open(path / TEMPLATE, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in COLUMNS})

    missing = [r["parameter"] for r in out if r["must_or_bonus"] == "Must" and not r["value_mid"]]
    ctx.log("submission", "template_written", len(out), f"{TEMPLATE} filled from the engine",
            f"Must rows without value: {missing or 'none'}", severity="warn" if missing else "info")
