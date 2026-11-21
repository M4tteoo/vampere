"""Step 4 + contract export: baseline and the scene files for the frontend.

Writes (format: contract/types.ts):
  output/summary.json     baseline, recurring baseline, target, breakdowns, flows, coverage
  output/entities.json    rooms, islands, resources, servers, licence groups with metrics
  output/timeseries.json  monthly series per entity, daily for dp-prod / dp-dev / gpu-ml
States are preliminary (driver / contradiction) until findings, measures and
limits exist (Steps 5–7).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..harmonize.context import Context
from ..harmonize.store import _meta

SUMS = ["cost_chf_low", "cost_chf", "cost_chf_high", "cost_eur", "cost_usd",
        "kwh_low", "kwh_mid", "kwh_high", "co2_kg_low", "co2_kg_mid", "co2_kg_high"]
STATUS_RANK = {"observed": 0, "derived_exact": 1, "derived_cross_source": 2, "estimated": 3, "missing": 4}
GRID_IDS = {"CH": "grid_mix_location_based_switzerland", "DE": "grid_mix_location_based_germany",
            "IE": "grid_mix_location_based_ireland", "EU": "grid_mix_location_based_eu"}
UNIT_FACTORS = {"vCPU-hour": ["energy_per_vcpu_hour"], "vCore-hour": ["energy_per_vcpu_hour"],
                "runner-minute": ["energy_per_vcpu_hour"], "node-hour": ["energy_per_node_hour"],
                "GPU-hour": ["energy_per_gpu_hour"], "capacity-day": ["energy_per_vcpu_hour"],
                "GB-day": ["energy_per_gb_storage_day"], "GB": ["energy_per_gb_network"],
                "tokens": ["energy_per_1000_tokens"], "seat-month": ["energy_per_subscription_message"],
                "licence-month": ["energy_per_active_saas_licence_month"]}
LOC_LABELS = {"CH": "Zurich", "DE": "Frankfurt", "IE": "Dublin", "EU": "EU cloud (AI & SaaS)"}


# ------------------------------------------------------------------ helpers
def _r(v, nd):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), nd)


def metrics(s: pd.Series | dict) -> dict:
    """Group sums → contract Metrics (ranges, three currencies)."""
    s = pd.Series(s)
    mid = s["cost_chf"]
    k_eur = s["cost_eur"] / mid if mid else 1.0
    k_usd = s["cost_usd"] / mid if mid else 1.0

    def rng(lo, m, hi, nd):
        return {"low": _r(lo, nd), "mid": _r(m, nd), "high": _r(hi, nd)}
    return {
        "cost_chf": rng(s["cost_chf_low"], mid, s["cost_chf_high"], 2),
        "cost_eur": rng(s["cost_chf_low"] * k_eur, s["cost_eur"], s["cost_chf_high"] * k_eur, 2),
        "cost_usd": rng(s["cost_chf_low"] * k_usd, s["cost_usd"], s["cost_chf_high"] * k_usd, 2),
        "kwh": rng(s["kwh_low"], s["kwh_mid"], s["kwh_high"], 1),
        "co2_kg": rng(s["co2_kg_low"], s["co2_kg_mid"], s["co2_kg_high"], 1),
    }


def zero_metrics() -> dict:
    return metrics(pd.Series(0.0, index=SUMS))


def scale(m: dict, k: float) -> dict:
    return {key: {lvl: _r(v * k, 2) for lvl, v in r.items()} if r else r for key, r in m.items()}


class Calc:
    def __init__(self, ctx: Context, fc: pd.DataFrame):
        iss = pd.DataFrame(ctx.issues)
        self.issues = iss[iss["resource_id"].notna()].groupby("resource_id")["issue_id"].apply(list).to_dict()
        self.fc = fc

    def __call__(self, rows: pd.DataFrame, formula: str, note: str | None = None, inputs=()) -> dict:
        units = rows["unit"].dropna().unique()
        factors = sorted({f for u in units for f in UNIT_FACTORS.get(u, [])}
                         | {GRID_IDS[l] for l in rows["location"].dropna().unique() if l in GRID_IDS}
                         | ({"pue"} if rows["provider"].isin(["Azure", "AWS"]).any() else set())
                         | ({"pue_hoster"} if (rows["provider"] == "Swiss hoster").any() else set()))
        rank = rows["value_status"].map(STATUS_RANK).max()
        status = {v: k for k, v in STATUS_RANK.items()}.get(rank, "observed")
        issue_ids = sorted({i for r in rows["resource_id"].dropna().unique() for i in self.issues.get(r, [])})
        out = {"formula": formula, "inputs": list(inputs), "factor_ids": factors,
               "source_files": sorted(rows["source_file"].dropna().unique().tolist()),
               "row_count": int(len(rows)), "value_status": status, "issue_ids": issue_ids[:20]}
        if note:
            out["note"] = note
        return out


# ------------------------------------------------------------------ summary
def _one_off_excess(fc: pd.DataFrame, events: pd.DataFrame) -> list[dict]:
    out = []
    for e in events.itertuples():
        if e.resource_id is None or pd.isna(e.resource_id):
            rows = fc[(fc["one_off_id"] == e.one_off_id) & fc["in_baseline"]]
            ex = rows[SUMS].sum()
        else:
            res = fc[(fc["resource_id"] == e.resource_id) & (fc["charge_category"] != "Credit")]
            daily = res.groupby("charge_period_start")[SUMS].sum()
            d = pd.to_datetime(daily.index)
            inside = daily.index.to_series().between(e.start, e.end).values
            near = daily[(abs((d - pd.Timestamp(e.start)).days) <= 30) & ~inside]
            ex = daily[inside].sum() - near.median() * inside.sum()
        out.append({"id": e.one_off_id, "resource_id": None if pd.isna(e.resource_id) else e.resource_id,
                    "ticket": e.ticket if isinstance(e.ticket, str) else None, "reason": e.reason,
                    "excess": metrics(ex)})
    return out


def build_summary(ctx: Context, calc: Calc) -> dict:
    fc = ctx.tables["fact_cost"]
    b = fc[fc["in_baseline"]]
    tot = b[SUMS].sum()
    one_offs = _one_off_excess(fc, ctx.tables["one_off_events"])
    rec = tot.copy()
    for o in one_offs:
        for col, (key, lvl) in {"cost_chf_low": ("cost_chf", "low"), "cost_chf": ("cost_chf", "mid"),
                                "cost_chf_high": ("cost_chf", "high"), "cost_eur": ("cost_eur", "mid"),
                                "cost_usd": ("cost_usd", "mid"), "kwh_low": ("kwh", "low"),
                                "kwh_mid": ("kwh", "mid"), "kwh_high": ("kwh", "high"),
                                "co2_kg_low": ("co2_kg", "low"), "co2_kg_mid": ("co2_kg", "mid"),
                                "co2_kg_high": ("co2_kg", "high")}.items():
            rec[col] -= o["excess"][key][lvl] or 0

    def breakdown(col, ent_prefix=None, label=None):
        g = b.groupby(col, dropna=False)[SUMS].sum().sort_values("cost_chf", ascending=False)
        rows = []
        for key, s in g.iterrows():
            key = "unassigned" if pd.isna(key) else key
            rows.append({"key": key, "label": (label or {}).get(key, key),
                         "entity_id": f"{ent_prefix}{key}" if ent_prefix else None, "metrics": metrics(s),
                         "share": {"cost": _r(s["cost_chf"] / tot["cost_chf"], 4),
                                   "co2": _r(s["co2_kg_mid"] / tot["co2_kg_mid"], 4)}})
        return rows

    tool_res = b.groupby("tool")["resource_id"].agg(lambda s: s.iat[0] if s.nunique() == 1 else None)
    by_tool = breakdown("tool")
    for r in by_tool:
        rid = tool_res.get(r["key"])
        r["entity_id"] = f"res:{rid}" if rid else None

    flows = [{"from": f"dept:{d}", "to": f"loc:{l}", "metrics": metrics(s)}
             for (d, l), s in b.groupby(["department", "location"])[SUMS].sum().iterrows()]
    cov = (b.groupby("value_status")["cost_chf"].sum() / tot["cost_chf"]).round(4).to_dict()
    return {
        "meta": _meta(ctx),
        "baseline": metrics(tot),
        "baseline_recurring": metrics(rec),
        "one_offs": one_offs,
        "target": {"co2_reduction": 0.40, "cost_reduction": 0.25, "budget_chf": 16500, "chf_per_person_day": 1100},
        "breakdown": {"by_category": breakdown("category"), "by_department": breakdown("department", "dept:"),
                      "by_location": breakdown("location", "loc:", LOC_LABELS), "by_tool": by_tool},
        "flows": flows,
        "coverage": cov,
        "calc": calc(b, "baseline = sum of all billing lines Sep 2025 – Aug 2026 (cloud, servers, AI, SaaS); "
                     "kWh = usage × energy per unit × PUE; CO2 = kWh × grid mix at the location",
                     note="Actual baseline (what happened). Recurring baseline = actual − excess of curated one-off events."),
    }


# ----------------------------------------------------------------- entities
def _utilisation(ctx: Context) -> dict[str, dict]:
    """Per resource: utilisation (0..1) and idle ratio over the baseline year."""
    b0, b1 = ctx.baseline
    act = ctx.tables["fact_activity"]
    a = act[(act["date"] >= b0) & (act["date"] <= b1)]
    out = {}
    dp = a[a["metric"].isin(["runtime_h", "active_use_h"])].pivot_table(index="resource_id", columns="metric", values="value", aggfunc="sum")
    for rid, r in dp.iterrows():
        u = r["active_use_h"] / r["runtime_h"]
        out[rid] = {"utilisation": u, "idle_ratio": 1 - u, "basis": "active_use_h / runtime_h"}
    fc = ctx.tables["fact_cost"]
    b = fc[fc["in_baseline"] & fc["utilisation_cpu"].notna()]
    for rid, g in b.groupby("resource_id"):
        if rid in out:
            continue
        w = g["quantity"].clip(lower=0)
        col = "utilisation_gpu" if g["unit"].iat[0] == "GPU-hour" else "utilisation_cpu"
        u = float(np.average(g[col], weights=w)) if w.sum() else float(g[col].mean())
        out[rid] = {"utilisation": u, "idle_ratio": None, "basis": "GPU utilisation (weekly)" if col == "utilisation_gpu"
                    else "CPU utilisation weighted by usage"}
    return out


def build_entities(ctx: Context, calc: Calc) -> tuple[dict, dict]:
    fc = ctx.tables["fact_cost"]
    b = fc[fc["in_baseline"]]
    dim = ctx.tables["dim_resource"].set_index("resource_id")
    util = _utilisation(ctx)
    iss = pd.DataFrame(ctx.issues)
    # Every contradiction is listed in flags (always visible). It becomes the primary
    # state only when material (severity warn/handover, i.e. above the materiality
    # threshold in config.yaml): the same rule that decides hand-overs.
    is_contra = iss["issue_type"].eq("contradiction") & iss["resource_id"].notna()
    contra = set(iss.loc[is_contra, "resource_id"])
    contra_material = set(iss.loc[is_contra & iss["severity"].isin(["warn", "handover"]), "resource_id"])
    top = set(b.groupby("resource_id")["co2_kg_mid"].sum().nlargest(5).index)
    ents, members = [], {}

    def base(eid, kind, label, parent, rows, formula, **kw):
        s = rows[SUMS].sum()
        e = {"id": eid, "kind": kind, "label": label, "parent_id": parent, "department": None, "tool": None,
             "category": None, "location": None, "metrics": metrics(s), "utilisation": None, "idle_ratio": None,
             "state": "normal", "flags": [], "finding_ids": [], "measure_ids": [], "limit_ids": [],
             "calc": calc(rows, formula, note=kw.pop("note", None))}
        e.update(kw)
        ents.append(e)
        return e

    hc = ctx.tables["alloc_headcount"]
    fte = hc[hc["month"] == hc["month"].max()].set_index("department")["fte"]
    for d in sorted(b["department"].dropna().unique()):
        rows = b[b["department"] == d]
        base(f"dept:{d}", "room", d, None, rows, "sum of baseline lines allocated to the department "
             "(row tag → row cost center → mapping)", department=d, fte=_r(fte.get(d), 1))
        members[f"dept:{d}"] = ("department", d)
    for loc in ["CH", "DE", "IE", "EU"]:
        rows = b[b["location"] == loc]
        base(f"loc:{loc}", "island", LOC_LABELS[loc], None, rows, "sum of baseline lines at the location",
             location=loc)
        members[f"loc:{loc}"] = ("location", loc)

    for rid, rows in b.groupby("resource_id"):
        d = dim.loc[rid] if rid in dim.index else None
        loc = rows["location"].mode().iat[0] if rows["location"].notna().any() else None
        u = util.get(rid, {})
        flags = (["driver"] if rid in top else []) + (["contradiction"] if rid in contra else [])
        e = base(f"res:{rid}", "resource", d["tool"] if d is not None else rid, f"loc:{loc}" if loc else None, rows,
                 f"{rows['energy_method'].mode().iat[0]}; cost as billed",
                 note=f"utilisation basis: {u['basis']}" if u else None,
                 department=rows["department"].mode().iat[0], tool=d["tool"] if d is not None else None,
                 category=rows["category"].iat[0], location=loc,
                 utilisation=_r(u.get("utilisation"), 3), idle_ratio=_r(u.get("idle_ratio"), 3))
        e["flags"] = flags
        e["state"] = ("contradiction" if rid in contra_material
                      else "driver" if "driver" in flags
                      else "contradiction" if "contradiction" in flags   # immaterial, but the only flag
                      else "normal")
        members[f"res:{rid}"] = ("resource_id", rid)

    # servers: share of their billed resource by vCPU × uptime hours (baseline year)
    srv = ctx.tables["dim_server"].copy()
    met = ctx.tables["stg_server_metrics_weekly"]
    b0, b1 = ctx.baseline
    up = met[(met["week_start"] >= b0) & (met["week_start"] <= b1)].groupby("server_id")
    srv["uptime_h"] = srv["server_id"].map(up["uptime_h"].sum()).fillna(0)
    srv["cpu"] = srv["server_id"].map(up["cpu_avg_pct"].mean()) / 100
    srv["gpu"] = srv["server_id"].map(up["gpu_avg_pct"].mean()) / 100
    srv["w"] = srv["vcpu"] * srv["uptime_h"]
    srv["share"] = srv["w"] / srv.groupby("resource_id")["w"].transform("sum")
    res_metrics = {e["id"]: e for e in ents if e["kind"] == "resource"}
    for s in srv.itertuples():
        parent = res_metrics.get(f"res:{s.resource_id}")
        if parent is None:
            continue
        rows = b[b["resource_id"] == s.resource_id]
        e = base(f"srv:{s.server_id}", "server", s.server_id, f"res:{s.resource_id}", rows,
                 f"share of res:{s.resource_id} by vCPU × uptime hours ({s.share:.1%})",
                 department=s.owner_department if isinstance(s.owner_department, str) else None,
                 tool=parent["tool"], category=parent["category"], location=parent["location"],
                 utilisation=_r(s.gpu if s.resource_id == "gpu-ml" else s.cpu, 3))
        e["metrics"] = scale(parent["metrics"], s.share)
        e["calc"]["inputs"] = [{"name": "vCPU", "value": float(s.vcpu), "unit": "vCPU", "source": "server_inventory.csv"},
                               {"name": "uptime in baseline year", "value": float(s.uptime_h), "unit": "h",
                                "source": "server_metrics_weekly.csv"}]
        members[f"srv:{s.server_id}"] = ("server", (s.resource_id, s.share))

    # licence groups: one product in one room; seats from the last full month
    lic = b[b["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"])]
    act = ctx.tables["fact_activity"]
    last = lic["month"].max()
    seats = act[(act["date"] == last) & act["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"])] \
        .pivot_table(index=["entity_id", "department"], columns="metric", values="value", aggfunc="sum")
    for (tool, dept), rows in lic.groupby(["tool", "department"]):
        sp = seats.loc[(tool, dept)] if (tool, dept) in seats.index else None
        purchased = int(sp["licences_purchased"]) if sp is not None else None
        active = int(sp["licences_active_30d"]) if sp is not None else None
        base(f"lic:{tool}@{dept}", "license_group", f"{tool} · {dept}", f"dept:{dept}", rows,
             "seats × price per seat × monthly FX; energy from messages (AI) or active licences (SaaS)",
             department=dept, tool=tool, category=rows["category"].iat[0], location=rows["location"].iat[0],
             seats={"purchased": purchased, "active": active} if sp is not None else None,
             utilisation=_r(active / purchased, 3) if purchased else None)
        members[f"lic:{tool}@{dept}"] = ("license", (tool, dept))
    return {"meta": _meta(ctx), "entities": ents}, members


# --------------------------------------------------------------- timeseries
def build_timeseries(ctx: Context, members: dict) -> dict:
    fc = ctx.tables["fact_cost"]
    cols = ["cost_chf", "cost_eur", "cost_usd", "kwh_mid", "co2_kg_mid"]
    last_full = ctx.baseline[1][:7] + "-01"
    act = ctx.tables["fact_activity"]
    dpm = act[act["metric"].isin(["runtime_h", "active_use_h"])].copy()
    dpm["month"] = dpm["date"].str[:7] + "-01"
    run_m = dpm.pivot_table(index=["resource_id", "month"], columns="metric", values="value", aggfunc="sum")
    run_d = dpm.pivot_table(index=["resource_id", "date"], columns="metric", values="value", aggfunc="sum")

    def points(df, key, share=1.0, rid=None, daily=False):
        g = df.groupby(key)[cols].sum().sort_index() * share
        out = []
        for t, r in g.iterrows():
            p = {"t": t, "cost_chf": _r(r.cost_chf, 2), "cost_eur": _r(r.cost_eur, 2), "cost_usd": _r(r.cost_usd, 2),
                 "kwh": _r(r.kwh_mid, 2), "co2_kg": _r(r.co2_kg_mid, 2)}
            idx = run_d if daily else run_m
            if rid and (rid, t) in idx.index:
                p["runtime_h"] = _r(idx.loc[(rid, t), "runtime_h"], 2)
                p["active_h"] = _r(idx.loc[(rid, t), "active_use_h"], 2)
            elif rid == "gpu-ml":
                p["runtime_h"] = _r(df[df[key] == t]["quantity"].sum(), 1)
            if not daily and t > last_full:
                p["partial"] = True
            out.append(p)
        return out

    series = []
    for eid, (kind, val) in members.items():
        if kind == "server":
            rid, share = val
            rows = fc[fc["resource_id"] == rid]
            series.append({"entity_id": eid, "granularity": "month", "points": points(rows, "month", share)})
            continue
        if kind == "license":
            rows = fc[(fc["tool"] == val[0]) & (fc["department"] == val[1])
                      & fc["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"])]
        else:
            rows = fc[fc[kind] == val]
        rid = val if kind == "resource_id" else None
        series.append({"entity_id": eid, "granularity": "month", "points": points(rows, "month", rid=rid)})
        if rid in ("dp-prod", "dp-dev", "gpu-ml"):
            d = rows[rows["grain"] == "day"]
            series.append({"entity_id": eid, "granularity": "day",
                           "points": points(d, "charge_period_start", rid=rid, daily=True)})
    return {"meta": _meta(ctx), "series": series}


# ---------------------------------------------------------------------- run
def export(ctx: Context) -> None:
    fc = ctx.tables["fact_cost"]
    calc = Calc(ctx, fc)
    summary = build_summary(ctx, calc)
    entities, members = build_entities(ctx, calc)
    ts = build_timeseries(ctx, members)
    for name, obj in (("summary.json", summary), ("entities.json", entities), ("timeseries.json", ts)):
        with open(ctx.output_dir / name, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
    ctx.export_summary = summary
