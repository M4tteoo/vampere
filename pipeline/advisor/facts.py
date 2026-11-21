"""System support for the advisor: the fact sheet.

Plain code turns the harmonized tables into a compact list of numbers, each with
an id («dp-dev.idle_share»), a unit, a statement and its source files. The LLM
reasons on these facts and cites them by id; it never types a number itself, so
every figure in a finding stays traceable to the data.

The fact sheet contains NO free text from the data (no ticket text, notes or
remarks): only ids, master-data labels and numbers. Free text is handled by the
quarantined reader (reader.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..energy.engine import load_factors
from ..export.frontend import SUMS
from ..harmonize.context import Context


class Facts:
    def __init__(self):
        self.items: dict[str, dict] = {}

    def add(self, fid: str, value, unit: str, statement: str, *sources: str) -> None:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return
        v = float(value) if isinstance(value, (int, float, np.integer, np.floating)) else value
        if isinstance(v, float):
            v = round(v, 4) if abs(v) < 10 else round(v, 1)
        self.items[fid] = {"value": v, "unit": unit, "statement": statement, "sources": list(sources)}


def build(ctx: Context) -> dict:
    """Return {"facts": {...}, "resources": [...], "servers": [...], ...} for the advisor."""
    F = Facts()
    fc = ctx.tables["fact_cost"]
    b = fc[fc["in_baseline"]]
    rec = b[~b["is_one_off"].fillna(False)]          # savings are claimed on recurring usage only
    tot = b[SUMS].sum()
    b0, b1 = ctx.baseline
    asof = pd.Timestamp(str(ctx.config["advisor"]["data_as_of"]))
    act = ctx.tables["fact_activity"]
    act = act[(act["date"] >= b0) & (act["date"] <= b1)]
    dim = ctx.tables["dim_resource"].set_index("resource_id")
    proj = ctx.tables["dim_project"].set_index("project_id")
    G = load_factors()["grid"]

    # ------------------------------------------------------------ baseline
    for k, col, unit in (("cost", "cost_chf", "CHF"), ("energy", "kwh_mid", "kWh"), ("co2", "co2_kg_mid", "kg CO2")):
        F.add(f"baseline.{k}", tot[col], unit, f"baseline year total {k} (actual, location-based CO2)", "fact_cost")
    F.add("baseline.cost_recurring", rec["cost_chf"].sum(), "CHF", "baseline cost without one-off events", "fact_cost")
    F.add("target.co2_reduction", 0.40, "share", "required CO2 reduction (location-based)", "case.md")
    F.add("target.cost_reduction", 0.25, "share", "required cost reduction", "case.md")
    F.add("target.budget_chf", 16500, "CHF", "max implementation effort (15 person-days × CHF 1,100)", "case.md")
    for loc, g in G.items():
        F.add(f"grid.{loc}", g["mid"], "kg CO2/kWh", f"grid mix {loc} (location-based)", "pipeline/energy/factors.yaml")

    # ------------------------------------------------------------ resources
    resources = []
    for rid, rows in b.groupby("resource_id"):
        s = rows[SUMS].sum()
        d = dim.loc[rid] if rid in dim.index else pd.Series(dtype=object)
        loc = rows["location"].mode().iat[0] if rows["location"].notna().any() else None
        src = sorted(rows["source_file"].dropna().unique())
        p = f"{rid}"
        F.add(f"{p}.cost", s["cost_chf"], "CHF/year", f"{rid} baseline cost", *src)
        F.add(f"{p}.energy", s["kwh_mid"], "kWh/year", f"{rid} baseline energy", *src)
        F.add(f"{p}.co2", s["co2_kg_mid"], "kg CO2/year", f"{rid} baseline CO2", *src)
        F.add(f"{p}.share_cost", s["cost_chf"] / tot["cost_chf"], "share", f"{rid} share of baseline cost", *src)
        F.add(f"{p}.share_co2", s["co2_kg_mid"] / tot["co2_kg_mid"], "share", f"{rid} share of baseline CO2", *src)
        q = rows.groupby("unit")["quantity"].sum()
        for u, v in q.items():
            F.add(f"{p}.usage_{u}", v, f"{u}/year", f"{rid} billed usage", *src)
        if rows["utilisation_cpu"].notna().any():
            w = rows["quantity"].clip(lower=1e-9)
            F.add(f"{p}.cpu_utilisation", np.average(rows["utilisation_cpu"].fillna(0), weights=w), "share",
                  f"{rid} average CPU utilisation of billed hours", *src)
        if rows["utilisation_gpu"].notna().any():
            F.add(f"{p}.gpu_utilisation", rows["utilisation_gpu"].mean(), "share", f"{rid} average GPU utilisation", "server_metrics_weekly.csv")
        dp = d.get("default_project")
        resources.append({
            "id": rid, "label": d.get("tool"), "category": rows["category"].iat[0], "location": loc,
            "provider": rows["provider"].mode().iat[0] if rows["provider"].notna().any() else None,
            "owner_department": d.get("department"), "decides": d.get("responsible_role"),
            "environment": d.get("environment"), "criticality_masterdata": d.get("criticality"),
            "project": dp if isinstance(dp, str) else None,
            "project_status": proj.loc[dp, "status"] if isinstance(dp, str) and dp in proj.index else None,
            "facts": sorted(k for k in F.items if k.startswith(p + "."))})

    # ------------------------------------------------- data platform patterns
    a = act[act["metric"].isin(["runtime_h", "active_use_h", "node_count"])].copy()
    a["dow"] = pd.to_datetime(a["date"]).dt.dayofweek
    days = a["date"].nunique()
    for rid, g in a.groupby("resource_id"):
        p = g.pivot_table(index="date", columns="metric", values="value", aggfunc="sum")
        p["dow"] = pd.to_datetime(p.index).dayofweek
        F.add(f"{rid}.running_h_per_day", p["runtime_h"].mean(), "h/day", f"{rid} running hours per day", "data_platform_usage.csv")
        F.add(f"{rid}.active_h_weekday", p.loc[p.dow < 5, "active_use_h"].mean(), "h/day", f"{rid} active hours on weekdays", "data_platform_usage.csv")
        F.add(f"{rid}.active_h_weekend", p.loc[p.dow >= 5, "active_use_h"].mean(), "h/day", f"{rid} active hours at weekends", "data_platform_usage.csv")
        F.add(f"{rid}.idle_share", 1 - p["active_use_h"].sum() / p["runtime_h"].sum(), "share",
              f"{rid} share of running hours without work", "data_platform_usage.csv")
        F.add(f"{rid}.nodes_avg", p["node_count"].mean(), "nodes", f"{rid} average nodes (16 vCPU, 64 GB each)", "data_platform_usage.csv")
        F.add(f"{rid}.nodes_last", p["node_count"].iloc[-1], "nodes", f"{rid} nodes at the end of the baseline year", "data_platform_usage.csv")

    # ---------------------------------------------------------------- GPU
    g = b[b["unit"] == "GPU-hour"]
    if not g.empty:
        dd = pd.to_datetime(g["charge_period_start"])
        train = dd.dt.month.isin([1, 4, 7, 10]) & (dd.dt.day <= 3)
        met = ctx.tables["stg_server_metrics_weekly"]
        gm = met[met["gpu_avg_pct"].notna() & met["week_start"].between(b0, b1)]
        F.add("gpu-ml.hours_running_share", g["quantity"].sum() / (len(pd.date_range(b0, b1)) * 24), "share",
              "GPU server share of hours running", "azure_costs.csv")
        F.add("gpu-ml.gpu_util_weekly_max", gm["gpu_avg_pct"].max() / 100, "share", "highest weekly GPU utilisation", "server_metrics_weekly.csv")
        F.add("gpu-ml.gpu_util_weekly_median", gm["gpu_avg_pct"].median() / 100, "share", "median weekly GPU utilisation", "server_metrics_weekly.csv")
        F.add("gpu-ml.cost_on_quarter_days_1_3", g.loc[train, "cost_chf"].sum(), "CHF/year",
              "GPU cost on days 1–3 of Jan/Apr/Jul/Oct", "azure_costs.csv")

    # -------------------------------------------------------------- servers
    srv = ctx.tables["dim_server"].copy()
    met = ctx.tables["stg_server_metrics_weekly"]
    w = met[met["week_start"].between(b0, b1)].copy()
    w["idle"] = w["cpu_avg_pct"] < 10
    m = w.groupby("server_id").agg(cpu=("cpu_avg_pct", "mean"), peak=("cpu_avg_pct", "max"),
                                   idle_weeks=("idle", "sum"), weeks=("idle", "size"), up=("uptime_h", "sum"))
    srv = srv.set_index("server_id").join(m)
    srv["w"] = srv["vcpu"] * srv["up"]
    srv["share_of_resource"] = srv["w"] / srv.groupby("resource_id")["w"].transform("sum")
    servers = []
    for sid, r in srv.iterrows():
        p = f"srv:{sid}"
        F.add(f"{p}.cpu_avg", r["cpu"] / 100 if pd.notna(r["cpu"]) else None, "share", f"{sid} average weekly CPU", "server_metrics_weekly.csv")
        F.add(f"{p}.cpu_peak_week", r["peak"] / 100 if pd.notna(r["peak"]) else None, "share", f"{sid} busiest week CPU", "server_metrics_weekly.csv")
        F.add(f"{p}.weeks_under_10pct_cpu", r["idle_weeks"] / r["weeks"] if r["weeks"] else None, "share",
              f"{sid} share of weeks under 10 % CPU", "server_metrics_weekly.csv")
        F.add(f"{p}.uptime_share", r["up"] / (r["weeks"] * 168) if r["weeks"] else None, "share", f"{sid} share of hours running", "server_metrics_weekly.csv")
        F.add(f"{p}.days_since_login", (asof - pd.Timestamp(r["last_login"])).days, "days", f"{sid} days since last human login", "server_inventory.csv")
        F.add(f"{p}.share_of_resource", r["share_of_resource"], "share", f"{sid} share of {r['resource_id']} (vCPU × uptime)", "server_inventory.csv")
        pj = r["project_id"]
        servers.append({"id": f"srv:{sid}", "resource": r["resource_id"], "type": r["type"], "environment": r["environment"],
                        "vcpu": r["vcpu"], "has_owner": pd.notna(r["owner_cost_center"]),
                        "criticality_inventory": r["criticality"] if isinstance(r["criticality"], str) else None,
                        "project": pj if isinstance(pj, str) else None,
                        "project_status": proj.loc[pj, "status"] if isinstance(pj, str) and pj in proj.index else None,
                        "project_end": proj.loc[pj, "end"] if isinstance(pj, str) and pj in proj.index else None})

    # ------------------------------------------------------------- licences
    stg = pd.concat([ctx.tables["stg_ai_subscriptions"].rename(columns={"product": "tool", "price_per_seat": "price"}),
                     ctx.tables["stg_saas_contracts"].rename(columns={"contract": "tool", "price_per_licence": "price"})])
    stg = stg[stg["month"].between(b0, b1)]
    licences = []
    lic_rows = b[b["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"])]
    for tool, s in stg.groupby("tool"):
        p = f"lic:{tool}"
        last = s[s["month"] == s["month"].max()]
        cost = lic_rows[lic_rows["tool"] == tool]["cost_chf"].sum()
        share = s["licences_active_30d"].sum() / s["licences_purchased"].sum()
        F.add(f"{p}.cost", cost, "CHF/year", f"{tool} cost", "ai_subscriptions.csv / saas_contracts.csv")
        F.add(f"{p}.active_share", share, "share", f"{tool} active / purchased seats (year average)", "ai_subscriptions.csv / saas_contracts.csv")
        F.add(f"{p}.seats_purchased", last["licences_purchased"].sum(), "seats", f"{tool} seats purchased (last month)", "ai_subscriptions.csv / saas_contracts.csv")
        F.add(f"{p}.seats_active", last["licences_active_30d"].sum(), "seats", f"{tool} seats active in 30 days (last month)", "ai_subscriptions.csv / saas_contracts.csv")
        F.add(f"{p}.cost_inactive_seats", cost * (1 - share), "CHF/year", f"{tool} cost of inactive seats", "ai_subscriptions.csv / saas_contracts.csv")
        F.add(f"{p}.days_to_contract_end", (pd.Timestamp(s["contract_end"].max()) - asof).days, "days", f"{tool} days until contract end", "contracts")
        F.add(f"{p}.notice_days", s["notice_period_days"].max(), "days", f"{tool} notice period", "contracts")
        licences.append({"id": p, "tool": tool, "billing": s["billing"].iat[0], "currency": s["currency"].iat[0],
                         "price_per_seat": float(s["price"].iloc[-1]), "contract_end": s["contract_end"].max(),
                         "departments": {dep: {"purchased": int(g2["licences_purchased"].sum()), "active": int(g2["licences_active_30d"].sum())}
                                         for dep, g2 in last.groupby("department")}})

    # -------------------------------------------------------------- AI tasks
    ai = ctx.tables["stg_ai_usage"]
    gw = b[b["source_file"] == "ai_usage.csv"].merge(ai[["source_row", "task_type", "model_class"]], on="source_row")
    ai_tasks = []
    for (rid, task, mc), g in gw.groupby(["resource_id", "task_type", "model_class"]):
        p = f"ai:{rid}:{task}:{mc}"
        F.add(f"{p}.cost", g["cost_chf"].sum(), "CHF/year", f"{rid} «{task}» on {mc} models", "ai_usage.csv")
        F.add(f"{p}.energy", g["kwh_mid"].sum(), "kWh/year", f"{rid} «{task}» on {mc} models", "ai_usage.csv")
        ai_tasks.append({"id": p, "resource": rid, "task": task, "model_class": mc, "models": sorted(g["service"].unique())})
    F.add("ai.small_to_large_price_ratio", 0.30, "share", "list price small / large model", "reference.yaml")

    # -------------------------------------------------------- extra sources
    dc = ctx.tables["stg_data_catalog_tables"]
    days_read = (asof - pd.to_datetime(dc["last_read"])).dt.days
    stale = dc["last_read"].isna() | (days_read > 365)
    F.add("dp-storage.catalog_gb", dc["size_gb"].sum(), "GB", "data catalogue total", "extra/data_catalog_tables.csv")
    F.add("dp-storage.stale_gb_no_retention", dc.loc[stale & (dc["retention_required"] == "no"), "size_gb"].sum(), "GB",
          "tables not read > 1 year, retention_required = no", "extra/data_catalog_tables.csv")
    F.add("dp-storage.stale_gb_retention_unknown", dc.loc[stale & dc["retention_required"].isna(), "size_gb"].sum(), "GB",
          "tables not read > 1 year, retention flag empty", "extra/data_catalog_tables.csv")
    F.add("dp-storage.stale_gb_retention_required", dc.loc[stale & (dc["retention_required"] == "yes"), "size_gb"].sum(), "GB",
          "tables not read > 1 year but under retention obligation", "extra/data_catalog_tables.csv")
    F.add("dp-storage.tmp_schema_gb", dc.loc[dc["schema"] == "tmp", "size_gb"].sum(), "GB", "tables in schema tmp", "extra/data_catalog_tables.csv")

    bc = ctx.tables["stg_backup_chains"]
    n = bc.groupby("source")["backup_tool"].nunique()
    trip = bc[bc["source"].isin(n[n == 3].index)]
    third = trip.sort_values("size_gb", ascending=False).groupby("source").nth(2)
    F.add("st-backup.sources_in_3_tools", int((n == 3).sum()), "sources", "backup sources copied by all three tools", "extra/backup_chains.csv")
    F.add("st-backup.third_copy_share", third["size_gb"].sum() / bc["size_gb"].sum(), "share", "share of backup GB in third copies", "extra/backup_chains.csv")
    F.add("st-backup.copies_10y_retention_share", bc.loc[bc["retention_days"] >= 3650, "size_gb"].sum() / bc["size_gb"].sum(), "share",
          "share of backup GB with 10-year retention", "extra/backup_chains.csv")

    ci = ctx.tables["stg_ci_pipeline_runs"]
    c = ci[ci["date"].between(b0, b1)]
    nf = c[c["pipeline"] == "nightly-full"]
    F.add("cicd.nightly_without_changes_share", (nf["commits_since_last_nightly"] == 0).mean(), "share",
          "nightly builds with 0 commits since the last one", "extra/ci_pipeline_runs.jsonl")
    F.add("cicd.minutes_share_unchanged_nightly", nf.loc[nf["commits_since_last_nightly"] == 0, "duration_seconds"].sum() / c["duration_seconds"].sum(),
          "share", "share of build minutes spent on unchanged nightly builds", "extra/ci_pipeline_runs.jsonl")
    F.add("cicd.rerun_share", (c["trigger"] == "rerun").mean(), "share", "share of runs that are re-runs", "extra/ci_pipeline_runs.jsonl")

    pb = ctx.tables["stg_powerbi_usage"]
    pp = pb[pb["date"].between(b0, b1)].groupby("report_id").agg(refresh=("refresh_duration_min", "sum"), views=("view_count", "sum"),
                                                                 rtype=("report_type", lambda s: s.mode().iat[0] if s.notna().any() else None))
    low = pp[(pp["views"] < 20) & (pp["refresh"] > 0)]
    F.add("pbi-kap.reports_refreshed_rarely_viewed", len(low), "reports", "reports refreshed but < 20 views per year", "extra/powerbi_usage.csv")
    F.add("pbi-kap.refresh_share_rarely_viewed", low["refresh"].sum() / pp["refresh"].sum(), "share",
          "their share of refresh minutes on the capacity", "extra/powerbi_usage.csv")
    F.add("pbi-kap.regulatory_among_them", int((low["rtype"] == "regulatory").sum()), "reports", "regulatory reports among them", "extra/powerbi_usage.csv")

    ag = ctx.tables["stg_ai_agent_runs"]
    r = ag[(ag["agent"] == "report-agent") & ag["date"].between(b0, b1)]
    F.add("ai-report.unopened_share", (r["report_opened"] == 0).mean(), "share", "report-agent outputs never opened", "extra/ai_agent_runs.jsonl")
    wt = ctx.tables["stg_web_traffic"]
    ww = wt[wt["date"].between(b0, b1)]
    F.add("web-cdn.bot_share", (ww["bot_share_pct"] / 100 * ww["gb_out_scaled"]).sum() / ww["gb_out_scaled"].sum(), "share",
          "bot share of delivered GB", "extra/web_traffic.csv")
    lv = ctx.tables["stg_log_volume"]
    l = lv[lv["date"].between(b0, b1)]
    for ret, g2 in l.groupby("retention_days"):
        F.add(f"logs.volume_share_retention_{int(ret)}d", g2["log_gb"].sum() / l["log_gb"].sum(), "share",
              f"share of new log volume kept {int(ret)} days", "extra/log_volume.csv")

    # ------------------------------------------------ one-offs and anomalies
    oo = ctx.tables["one_off_events"]
    for e in oo.itertuples():
        F.add(f"one_off.{e.one_off_id}.excess", e.excess_chf, "CHF", f"one-off {e.reason} (not recurring, no savings may be claimed)", "fact_cost")
    an = ctx.tables["anomaly_candidates"]
    anomalies = [{"resource": x.resource_id, "start": x.start, "end": x.end, "kind": x.kind,
                  "excess_chf": round(float(x.excess_chf), 2), "explained_by": x.explained_by if isinstance(x.explained_by, str) else None}
                 for x in an.itertuples()]

    return {"facts": F.items, "resources": resources, "servers": servers, "licences": licences,
            "ai_tasks": ai_tasks, "anomalies": anomalies,
            "calendar": {"baseline": [b0, b1], "data_as_of": str(asof.date()),
                         "note": "quarter days 1–3 = Jan/Apr/Jul/Oct; month-end = last 3 working days (business_calendar.csv)"}}
