"""Answers to the case's example questions (data/case/example_questions.md),
computed from the harmonized tables. Written to output/answers.json."""
from __future__ import annotations

import json

import pandas as pd

from ..harmonize.context import Context
from ..harmonize.store import _meta


def q1_ai_seats(ctx: Context, month: str = "2026-08-01") -> dict:
    """How many AI subscription seats were purchased but not active in August
    2026, and what do they cost per month?"""
    s = ctx.tables["stg_ai_subscriptions"]
    s = s[s["month"] == month]   # Final versions only (Drafts dropped by the harmonizer)
    rate = ctx.tables["fx_monthly"].set_index("month").loc[month, "usd_chf"]
    rows = []
    for product, g in s.groupby("product"):
        purchased, active = int(g["licences_purchased"].sum()), int(g["licences_active_30d"].sum())
        price = float(g["price_per_seat"].iat[0])
        inactive = purchased - active
        rows.append({"product": product, "purchased": purchased, "active": active, "inactive": inactive,
                     "price_per_seat_usd": price, "inactive_cost_usd_per_month": inactive * price,
                     "inactive_cost_chf_per_month": round(inactive * price * rate, 2),
                     "by_cost_center": {int(r.cost_center): {"purchased": int(r.licences_purchased),
                                        "active": int(r.licences_active_30d)} for r in g.itertuples()}})
    tot = pd.DataFrame(rows)[["purchased", "active", "inactive", "inactive_cost_chf_per_month"]].sum()
    drafts = int(ctx.tables["stg_ai_subscriptions"].pipe(lambda d: (d["month"] == month) & d["is_draft"]).sum())
    return {
        "question": "How many AI subscription seats were purchased but not active in August 2026, and what do they cost per month?",
        "answer": (f"{int(tot.inactive)} of {int(tot.purchased)} AI seats were not active in August 2026, costing "
                   f"CHF {tot.inactive_cost_chf_per_month:,.2f} per month (USD → CHF at {rate}, the August 2026 ECB average)."),
        "table": rows,
        "sources": ["ai_subscriptions.csv (contract_status = Final; Draft rows next to Final versions dropped)",
                    "exchange_rates.csv (usd_chf, 2026-08)"],
        "calc": "inactive = licences_purchased − licences_active_30d; cost = inactive × price_per_seat (USD) × usd_chf of the month",
        "note": f"Draft rows for the same month and cost center ignored ({drafts} kept as Draft-only: none expected).",
    }


def _read(ctx: Context, name: str) -> dict | None:
    p = ctx.output_dir / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _fmt_range(r: dict, unit: str, nd: int = 0) -> str:
    return f"{r['mid']:,.{nd}f} {unit} (range {r['low']:,.{nd}f}–{r['high']:,.{nd}f})"


def q2_gpu_on_demand(ctx: Context) -> dict:
    """What does it bring to start the GPU server only when needed? Effort and savings in CHF and CO2 per year."""
    b0, b1 = ctx.baseline
    m = ctx.tables["stg_server_metrics_weekly"]
    g = m[(m["server_id"] == "gpu-ml-01") & m["week_start"].between(b0, b1)]
    util, uptime = float(g["gpu_avg_pct"].mean()), float(g["uptime_h"].mean())
    measures = (_read(ctx, "measures.json") or {}).get("measures", [])
    gm = next((x for x in measures if any(e["scope"] in ("res:gpu-ml", "srv:gpu-ml-01") for e in x.get("effects", []))), None)
    factors = {f["id"]: f for f in (_read(ctx, "factors.json") or {}).get("factors", [])}
    gpu_f, grid_f = factors.get("energy_per_gpu_hour"), factors.get("grid_mix_location_based_germany")
    limits = {l["id"]: l for l in (_read(ctx, "limits.json") or {}).get("limits", [])}
    out = {"question": "What does it bring to start the GPU server only when needed? State the effort and the savings "
                       "in CHF and CO2 (location-based) per year.",
           "utilisation": {"gpu_avg_pct": round(util, 1), "uptime_h_per_week": round(uptime, 1), "weeks": int(len(g))},
           "sources": ["azure_costs.csv (gpu-ml)", "server_inventory.csv", "server_metrics_weekly.csv", "it_tickets.csv",
                       "pipeline/energy/factors.yaml"]}
    if gm is None:
        out["answer"] = (f"The GPU server runs {uptime:.0f} h a week at {util:.1f} % GPU utilisation; no measure for it "
                         "exists yet (run the advisor).")
        return out
    s = gm["savings"]
    windows = [limits[i]["title"].rstrip(". ") for i in gm.get("limit_ids", []) if i in limits]
    out.update({
        "answer": (f"Today gpu-ml-01 (Frankfurt) runs {uptime:.0f} of 168 h a week at {util:.1f} % average GPU utilisation. "
                   f"Measure {gm['id']} «{gm['title']}»: effort {gm['effort_days']} person-days (CHF {gm['effort_chf']:,.0f}); "
                   f"savings per year {_fmt_range(s['cost_chf'], 'CHF')}, {_fmt_range(s['kwh'], 'kWh')} and "
                   f"{_fmt_range(s['co2_kg'], 'kg CO2', 1)} location-based. Status: {gm['status']} (decides: {gm['owner_role']})."
                   + (f" It respects: {'; '.join(windows)}." if windows else "")),
        "measure_id": gm["id"], "effort_days": gm["effort_days"], "effort_chf": gm["effort_chf"], "savings": s,
        "status": gm["status"], "owner_role": gm["owner_role"], "limit_ids": gm.get("limit_ids", []),
        "calc": gm["calc"]["formula"],
        "assumptions": [{k: f[k] for k in ("id", "label", "unit", "low", "mid", "high", "source")} for f in (gpu_f, grid_f) if f],
    })
    return out


def q3_dp_prod_off_hours(ctx: Context) -> dict:
    """May the production platform be switched off at night and at weekends?"""
    b0, b1 = ctx.baseline
    u = ctx.tables["stg_data_platform_usage"]
    d = ctx.tables["dim_date"][["date", "is_weekend", "is_last3_workdays_of_month", "public_holiday", "company_holidays"]]
    x = u[(u["resource_id"] == "dp-prod") & u["date"].between(b0, b1)].merge(d, on="date")
    x["day_type"] = x.apply(lambda r: "holiday" if pd.notna(r["public_holiday"]) or pd.notna(r["company_holidays"])
                            else "weekend" if r["is_weekend"] else "last 3 working days" if r["is_last3_workdays_of_month"]
                            else "other working day", axis=1)
    use = {k: {"days": int(len(g)), "active_h_per_day": round(float(g["active_use_h"].mean()), 2),
               "queries_per_day": round(float(g["query_count"].mean()), 1)} for k, g in x.groupby("day_type")}
    limits = [l for l in (_read(ctx, "limits.json") or {}).get("limits", [])
              if "res:dp-prod" in l["entity_ids"] and l["type"] in ("window", "block", "human")]
    role = ctx.tables["dim_resource"].set_index("resource_id").at["dp-prod", "responsible_role"]
    measures = [m for m in (_read(ctx, "measures.json") or {}).get("measures", [])
                if "res:dp-prod" in m.get("entity_ids", [])]
    we, wd = use.get("weekend", {}), use.get("other working day", {})
    return {
        "question": "May the production platform be switched off at night and at weekends?",
        "answer": ("Not as a general rule, and not without a decision. Nights: fixed jobs need the platform every day ("
                   + "; ".join(l["title"].replace("scheduled job ", "") for l in limits
                               if l["source"]["kind"] == "file" and l["period_text"].startswith("every day"))
                   + "), and finance closing needs it on the last 3 working days until 04:00 (T-1029). "
                   f"Weekends: {we.get('active_h_per_day', 0)} active h/day and {we.get('queries_per_day', 0)} queries/day "
                   f"(working days: {wd.get('active_h_per_day', 0)} h, {wd.get('queries_per_day', 0)} queries), so mostly idle "
                   "but not unused. A narrower switch-off outside these windows can be assessed; "
                   f"the {role} decides before anything changes."),
        "usage_by_day_type": use,
        "protection": [{"id": l["id"], "type": l["type"], "title": l["title"], "period": l["period_text"],
                        "source": l["source"]} for l in limits],
        "decided_by": role,
        "measures_on_dp_prod": [{"id": m["id"], "status": m["status"], "in_package": m["in_package"]} for m in measures],
        "sources": ["data_platform_usage.csv", "it_tickets.csv (T-1029 and others, via the quarantined reader)",
                    "extra/data_platform_jobs.csv", "business_calendar.csv", "mapping_departments_tools.csv"],
    }


def write(ctx: Context) -> None:
    out = {"meta": _meta(ctx), "answers": {"q1_find": q1_ai_seats(ctx), "q2_decide": q2_gpu_on_demand(ctx),
                                           "q3_limits": q3_dp_prod_off_hours(ctx)}}
    with open(ctx.output_dir / "answers.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
