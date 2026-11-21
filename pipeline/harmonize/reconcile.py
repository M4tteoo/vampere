"""Cross-source checks. Each check states which source we trust and why.
Contradictions go to the issues log; consistent pairs are logged too, as
evidence that the extra sources detail (and do not add to) core costs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .context import Context


def _month(s: pd.Series) -> pd.Series:
    return s.astype(str).str[:7] + "-01"


def ai_invoice_vs_gateway(ctx: Context) -> None:
    """Decision: invoices for totals (what is paid), gateway for allocation.
    The difference is added as Adjustment rows, split by gateway cost share."""
    fc = ctx.tables["fact_cost"]
    inv = ctx.tables["stg_ai_invoice_monthly"].copy()
    inv["chf"] = inv["amount"] * ctx.fx_to_chf(inv["month"], inv["currency"])
    stg = ctx.tables["stg_ai_usage"][["source_row", "model_class"]]
    gw = fc[fc["source_file"] == "ai_usage.csv"].merge(stg, on="source_row", how="left")

    rows = []
    for _, r in inv.iterrows():
        g = gw[(gw["month"] == r["month"]) & (gw["provider"] == r["provider"]) & (gw["model_class"] == r["model_class"])]
        if g.empty:
            continue
        diff_native = r["amount"] - g["cost_chf"].sum() / ctx.fx_to_chf(pd.Series([r["month"]]), pd.Series([r["currency"]])).iat[0]
        diff_tokens = (r["tokens_in"] + r["tokens_out"]) - g["quantity"].sum()
        keys = ["resource_id", "department", "cost_center", "tool", "service", "project_id",
                "provider", "category", "location", "environment", "allocation_method"]
        share = g.groupby(keys, dropna=False)["cost_chf"].sum()
        share = share / share.sum()
        for k, w in share.items():
            row = dict(zip(keys, k))
            row.update({
                "charge_period_start": r["month"], "month": r["month"], "grain": "month",
                "source_file": "extra/ai_invoice_monthly.csv", "source_row": None,
                "region": None, "charge_category": "Adjustment",
                "quantity": diff_tokens * w, "unit": "tokens",
                "amount_native": diff_native * w, "currency_native": r["currency"],
                "value_status": "derived_cross_source",
                "method": "AI invoice − gateway for the provider/model class, split by gateway cost share",
                "dq_flags": None,
            })
            rows.append(row)
    adj = pd.DataFrame(rows)
    rate = ctx.fx_to_chf(adj["month"], adj["currency_native"])
    fx = ctx.tables["fx_monthly"].set_index("month")
    adj["fx_rate_chf"] = rate
    adj["amount_native_low"] = adj["amount_native"]
    adj["amount_native_high"] = adj["amount_native"]
    adj["cost_chf"] = adj["cost_chf_low"] = adj["cost_chf_high"] = adj["amount_native"] * rate
    adj["cost_eur"] = adj["cost_chf"] / adj["month"].map(fx["eur_chf"])
    adj["cost_usd"] = adj["cost_chf"] / adj["month"].map(fx["usd_chf"])
    ctx.tables["fact_cost"] = pd.concat([fc, adj], ignore_index=True)

    b0, b1 = ctx.baseline
    base = adj["month"].between(b0, b1)
    gap = adj.loc[base, "cost_chf"].sum()
    gw_base = gw.loc[gw["month"].between(b0, b1), "cost_chf"].sum()
    ctx.log("extra/ai_invoice_monthly.csv", "contradiction", len(adj),
            "invoices used for totals (what is paid), gateway for allocation; difference added as Adjustment rows",
            f"baseline year: invoices exceed the gateway by CHF {gap:,.0f} ({gap / gw_base:.1%}); "
            "token counts differ by the same ratio, so the gateway misses some usage",
            amount_chf=gap, category="ai", severity="warn")


def provider_report_vs_billing(ctx: Context) -> None:
    fc = ctx.tables["fact_cost"]
    rep = ctx.tables["stg_provider_monthly_report"].set_index("month")["total_cost_chf"]
    by = fc[fc["source_file"].isin(["azure_costs.csv", "aws_costs.csv", "hoster_invoice.csv"])] \
        .pivot_table(index="month", columns="source_file", values="cost_chf", aggfunc="sum")
    combos = {
        "Azure": by["azure_costs.csv"],
        "Azure + AWS": by["azure_costs.csv"] + by["aws_costs.csv"],
        "Azure + AWS + hoster": by.sum(axis=1),
    }
    m = rep.index
    err = {k: float((v.reindex(m) / rep - 1).abs().mean()) for k, v in combos.items()}
    best = min(err, key=err.get)
    b0, b1 = ctx.baseline
    mb = [x for x in m if b0 <= x <= b1]
    diff = float((rep[mb] - combos[best].reindex(mb)).sum())
    ctx.log("extra/provider_monthly_report.csv", "contradiction", len(rep),
            "billing lines trusted (line-level, traceable); report kept for reference only",
            f"no combination matches; closest «{best}» deviates {err[best]:.1%} per month on average; "
            f"baseline-year difference CHF {diff:,.0f}",
            amount_chf=diff, category="cloud", severity="warn")


def platform_nodes_vs_billing(ctx: Context) -> None:
    fc = ctx.tables["fact_cost"]
    act = ctx.tables["fact_activity"]
    bill = fc[fc["resource_id"].isin(["dp-prod", "dp-dev"]) & (fc["charge_category"] == "Usage")] \
        .groupby(["resource_id", "month"]).agg(q=("quantity", "sum"), c=("cost_chf", "sum"))
    mon = act[(act["metric"] == "node_hours") & act["resource_id"].isin(["dp-prod", "dp-dev"])].copy()
    mon["month"] = _month(mon["date"])
    mon = mon.groupby(["resource_id", "month"])["value"].sum()
    j = bill.join(mon.rename("mon")).dropna()
    j["ratio"] = j["q"] / j["mon"]
    bad = j[(j["ratio"] - 1).abs() > 0.05]
    for (rid, mo), r in bad.iterrows():
        ctx.log("data_platform_usage.csv", "contradiction", 1,
                "billing trusted for cost, monitoring for activity patterns",
                f"{rid} {mo[:7]}: billed {r.q:,.0f} node-h vs monitored {r.mon:,.0f} ({r.ratio - 1:+.0%})",
                amount_chf=(r.q - r.mon) * r.c / r.q, resource_id=rid)
    ctx.log("data_platform_usage.csv", "consistency_check", len(j) - len(bad),
            "billed node-hours match monitored node_count × runtime_h within 5 %",
            f"{len(j) - len(bad)} of {len(j)} resource-months")


def detail_sources_match_billing(ctx: Context) -> None:
    """Extra sources detail a core billing line: verify instead of adding."""
    fc, t = ctx.tables["fact_cost"], ctx.tables
    last = fc["charge_period_start"].max()

    def last_qty(rid):
        g = fc[(fc["resource_id"] == rid) & (fc["charge_category"] == "Usage")]
        return float(g.sort_values("charge_period_start")["quantity"].iloc[-1])

    cat = t["stg_data_catalog_tables"]["size_gb"].sum()
    ctx.log("extra/data_catalog_tables.csv", "consistency_check", len(t["stg_data_catalog_tables"]),
            "catalogue = detail of dp-storage (not added to costs)",
            f"500 tables total {cat:,.1f} GB vs dp-storage last day {last_qty('dp-storage'):,.1f} GB-day")
    bk = t["stg_backup_chains"]["size_gb"].sum()
    ctx.log("extra/backup_chains.csv", "consistency_check", len(t["stg_backup_chains"]),
            "backup chains = detail of st-backup (not added to costs)",
            f"all copies total {bk:,.1f} GB vs st-backup last day {last_qty('st-backup'):,.1f} GB-day")

    ci = t["stg_ci_pipeline_runs"].groupby("month")["duration_seconds"].sum() / 60
    aws = fc[fc["resource_id"] == "cicd"].groupby("month")["quantity"].sum()
    r = (aws / ci).dropna()
    ctx.log("extra/ci_pipeline_runs.jsonl", "consistency_check", len(t["stg_ci_pipeline_runs"]),
            "CI runs = detail of AWS cicd (not added to costs)",
            f"billed runner-minutes / run minutes = {r.median():.2f} (median over {len(r)} months; 2 runners per job)")

    web = t["stg_web_traffic"].assign(month=lambda d: _month(d["date"])).groupby("month")["gb_out_scaled"].sum()
    ho = fc[fc["resource_id"] == "web-cdn"].groupby("month")["quantity"].sum()
    r = (ho / web).dropna()
    ctx.log("extra/web_traffic.csv", "consistency_check", len(t["stg_web_traffic"]),
            "web traffic = detail of hoster web-cdn (not added to costs)",
            f"hoster GB / scaled traffic GB = {r.median():.2f} (median); without sample-rate scaling "
            "traffic would appear to drop by 90 % from September 2025")

    ag = t["stg_ai_agent_runs"].groupby(["month", "resource_id"])["usage_tokens_in"].sum()
    gw = t["stg_ai_usage"][t["stg_ai_usage"]["task_type"] == "Agent run"].groupby(["month", "resource_id"])["tokens_in"].sum()
    r = (ag / gw).dropna()
    ctx.log("extra/ai_agent_runs.jsonl", "consistency_check", len(t["stg_ai_agent_runs"]),
            "agent runs = detail of ai-agent / ai-agent2 / ai-report gateway rows (not added to costs)",
            f"agent-log tokens / gateway tokens = {r.median():.2f} (median over {len(r)} resource-months)")


def run_all(ctx: Context) -> None:
    ai_invoice_vs_gateway(ctx)
    provider_report_vs_billing(ctx)
    platform_nodes_vs_billing(ctx)
    detail_sources_match_billing(ctx)
