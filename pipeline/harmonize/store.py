"""Write the harmonized tables to DuckDB, create the analysis views and
export the files the frontend reads (quality.json, fx.json)."""
from __future__ import annotations

import json
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

from .context import ROOT, Context

DATE_COLUMNS = {"date", "month", "charge_period_start", "week_start"}

FACT_COST_ORDER = [
    "cost_id", "charge_period_start", "month", "grain", "in_baseline", "category", "provider",
    "service", "region", "location", "resource_id", "tool", "department", "cost_center",
    "project_id", "environment", "allocation_method", "charge_category", "quantity", "unit",
    "amount_native", "currency_native", "fx_rate_chf", "cost_chf", "cost_chf_low", "cost_chf_high",
    "cost_eur", "cost_usd", "value_status", "method", "is_one_off", "one_off_id", "dq_flags",
    "source_file", "source_row",
]


def _fx_pairs(ctx: Context) -> pd.DataFrame:
    fx = ctx.tables["fx_monthly"]
    rows = []
    b0, b1 = ctx.baseline
    base = fx[fx["month"].between(b0, b1)][["eur_chf", "usd_chf"]].mean()
    for basis, frame in (("monthly", fx), ("baseline_avg", pd.DataFrame([{"month": None, **base}]))):
        for _, r in frame.iterrows():
            chf = {"CHF": 1.0, "EUR": r["eur_chf"], "USD": r["usd_chf"]}  # CHF per unit
            for a in chf:
                for b in chf:
                    rows.append({"basis": basis, "month": r["month"], "from_ccy": a, "to_ccy": b,
                                 "rate": chf[a] / chf[b]})
    return pd.DataFrame(rows)


def write(ctx: Context) -> None:
    out = ctx.output_dir
    out.mkdir(parents=True, exist_ok=True)
    path = ROOT / ctx.config["duckdb_file"]
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))

    fc = ctx.tables["fact_cost"]
    ctx.tables["fact_cost"] = fc[FACT_COST_ORDER + [c for c in fc.columns if c not in FACT_COST_ORDER]]
    ctx.tables["fx_pairs"] = _fx_pairs(ctx)
    ctx.tables["issues"] = pd.DataFrame(ctx.issues)
    ctx.tables["sources"] = pd.DataFrame(ctx.sources)

    for name, df in ctx.tables.items():
        df = df.copy()
        for c in df.columns:
            if df[c].dtype == object and df[c].map(type).isin([list, dict]).any():
                df[c] = df[c].map(lambda v: json.dumps(v) if isinstance(v, (list, dict)) else v)
        con.register("_df", df)
        sel = ", ".join(f'TRY_CAST("{c}" AS DATE) AS "{c}"' if c in DATE_COLUMNS else f'"{c}"'
                        for c in df.columns)
        con.execute(f'CREATE TABLE "{name}" AS SELECT {sel} FROM _df')
        con.unregister("_df")

    _views(con, ctx)
    con.close()
    _export_json(ctx)


def _views(con, ctx: Context) -> None:
    con.execute("""
    CREATE VIEW v_cost_baseline AS
      SELECT * FROM fact_cost WHERE in_baseline;

    -- Recurring baseline: actual minus the excess of curated one-off events
    CREATE VIEW v_baseline_totals AS
      SELECT category,
             SUM(cost_chf) AS actual_chf,
             SUM(cost_chf_low) AS actual_chf_low,
             SUM(cost_chf_high) AS actual_chf_high
      FROM fact_cost WHERE in_baseline GROUP BY category;

    -- Shared costs (department Overhead) split by FTE share of the month
    CREATE VIEW v_cost_allocated AS
      WITH fte AS (
        SELECT month, department, fte / SUM(fte) OVER (PARTITION BY month) AS share FROM alloc_headcount),
      last_fte AS (SELECT department, share FROM fte WHERE month = (SELECT MAX(month) FROM fte))
      SELECT c.* EXCLUDE (department, cost_chf, cost_chf_low, cost_chf_high, cost_eur, cost_usd),
             COALESCE(f.department, l.department) AS department,
             'shared: FTE share' AS shared_rule,
             c.cost_chf * COALESCE(f.share, l.share) AS cost_chf,
             c.cost_chf_low * COALESCE(f.share, l.share) AS cost_chf_low,
             c.cost_chf_high * COALESCE(f.share, l.share) AS cost_chf_high,
             c.cost_eur * COALESCE(f.share, l.share) AS cost_eur,
             c.cost_usd * COALESCE(f.share, l.share) AS cost_usd
      FROM fact_cost c
      LEFT JOIN fte f ON c.department = 'Overhead' AND f.month = c.month
      LEFT JOIN last_fte l ON c.department = 'Overhead' AND f.month IS NULL
      WHERE c.department = 'Overhead'
      UNION ALL BY NAME
      SELECT *, NULL AS shared_rule FROM fact_cost WHERE department IS DISTINCT FROM 'Overhead';

    -- FOCUS-style column names (https://focus.finops.org) for interoperability
    CREATE VIEW v_focus_cost AS
      SELECT charge_period_start AS ChargePeriodStart, provider AS ProviderName,
             service AS ServiceName, resource_id AS ResourceId, region AS RegionName,
             charge_category AS ChargeCategory, quantity AS ConsumedQuantity, unit AS ConsumedUnit,
             amount_native AS BilledCost, currency_native AS BillingCurrency,
             cost_chf AS x_CostCHF, category AS x_Category, department AS x_Department,
             cost_center AS x_CostCenter, project_id AS x_ProjectId, location AS x_Location,
             value_status AS x_ValueStatus, method AS x_Method, source_file AS x_SourceFile,
             source_row AS x_SourceRow
      FROM fact_cost;

    -- Share of baseline cost per value status (coverage)
    CREATE VIEW v_coverage AS
      SELECT category, value_status, COUNT(*) AS rows, SUM(cost_chf) AS cost_chf,
             SUM(cost_chf) / SUM(SUM(cost_chf)) OVER (PARTITION BY category) AS share
      FROM fact_cost WHERE in_baseline GROUP BY category, value_status ORDER BY category, value_status;
    """)


def _jsonable(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if v is pd.NA or (isinstance(v, float) and np.isnan(v)):
        return None
    return v


SCHEMA_VERSION = "0.1"  # contract/types.ts


def _meta(ctx: Context) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline": {"start": ctx.baseline[0], "end": ctx.baseline[1]},
        "scenario": ctx.config.get("scenario", "ch_consumption"),
    }


def _export_json(ctx: Context) -> None:
    issues = pd.DataFrame(ctx.issues)
    fc = ctx.tables["fact_cost"]

    def count(t):
        return int(issues.loc[issues["issue_type"] == t, "rows_affected"].sum())

    counters = {
        "files_loaded": len(ctx.sources),
        "rows_read": int(sum(s["rows_in"] for s in ctx.sources)),
        "duplicates_removed": count("duplicate"),
        "drafts_dropped": count("draft_dropped"),
        "rows_currency_converted": count("currency_converted"),
        "rows_unit_converted": count("unit_converted"),
        "project_ids_normalized": count("project_id_normalized"),
        "values_derived_exact": count("derived_exact"),
        "values_derived_cross_source": count("derived_cross_source"),
        "values_estimated": count("estimated"),
        "gap_days_filled": count("gap_filled"),
        "contradictions": int((issues["issue_type"] == "contradiction").sum()),
        "consistency_checks_passed": int((issues["issue_type"] == "consistency_check").sum()),
        "free_text_fields_isolated": count("free_text_isolated"),
        "handovers": int((issues["severity"] == "handover").sum()),
    }
    b = fc[fc["in_baseline"]]
    coverage = (b.groupby("value_status")["cost_chf"].sum() / b["cost_chf"].sum()).round(4).to_dict()
    quality = {
        "meta": _meta(ctx),
        "materiality_pct_of_category": ctx.config["handover"]["materiality_pct_of_category"],
        "counters": counters,
        "baseline_cost_coverage_by_status": coverage,
        "sources": ctx.sources,
        "issues": [{k: _jsonable(v) for k, v in it.items()} for it in ctx.issues],
    }
    with open(ctx.output_dir / "quality.json", "w", encoding="utf-8") as fh:
        json.dump(quality, fh, ensure_ascii=False, indent=2, default=_jsonable)

    fxp = ctx.tables["fx_pairs"]
    fxj = {
        "meta": _meta(ctx),
        "source": "ECB reference rates via Deutsche Bundesbank (exchange_rates.csv); EUR↔USD as cross rate",
        "baseline_avg": {f"{r.from_ccy}_{r.to_ccy}": round(r.rate, 6)
                         for r in fxp[fxp["basis"] == "baseline_avg"].itertuples()},
        "monthly": {m: {f"{r.from_ccy}_{r.to_ccy}": round(r.rate, 6) for r in g.itertuples()}
                    for m, g in fxp[fxp["basis"] == "monthly"].groupby("month")},
    }
    with open(ctx.output_dir / "fx.json", "w", encoding="utf-8") as fh:
        json.dump(fxj, fh, indent=2)
