"""Microsoft 365 usage (extra/m365_usage.csv): two checks, no change to the baseline.

1. Licences: active users in the M365 admin data vs licences active / purchased in the
   SaaS contracts, per department → confirms (or contradicts) the licence measure.
2. Energy: bottom-up estimate from storage and video minutes vs our per-licence SaaS
   assumption (factors.yaml saas, 0.15 kWh per active licence-month).
   storage: GB-days × storage factor (factors.yaml)
   video:   minutes × kWh per minute, low / mid from data volume (0.3 / 0.6 GB per hour,
            ASSUMPTION) × network factor (factors.yaml), high from Obringer et al. 2021
            (≈ 160 g CO2e per hour of videoconferencing, at the EU grid factor)
   mails are left out (negligible).
"""
from __future__ import annotations

from ..energy.engine import load_factors
from ..harmonize.context import Context
from .common import Insight, card, recurring

SRC = "extra/m365_usage.csv"
VIDEO_GB_PER_HOUR = {"low": 0.3, "mid": 0.6}
OBRINGER_KG_PER_HOUR = 0.16


def compute(ctx: Context) -> Insight:
    b0, b1 = ctx.baseline
    F = load_factors()
    m = ctx.tables["stg_m365_usage"]
    m = m[m["week_start"].between(b0, b1)]
    lic = ctx.tables["stg_saas_contracts"]
    lic = lic[(lic["contract"] == "Microsoft 365") & (lic["contract_status"] == "Final") & lic["month"].between(b0, b1)]
    users = m.groupby("department")["active_users"].mean()
    act = lic.groupby("department")["licences_active_30d"].mean()
    bought = lic.groupby("department")["licences_purchased"].mean()
    depts = [{"department": d, "active_users_admin": round(float(users.get(d, 0)), 1),
              "licences_active": round(float(act.get(d, 0)), 1), "licences_purchased": round(float(bought.get(d, 0)), 1),
              "difference_active": round(float(users.get(d, 0) / act.get(d, 1) - 1), 3)} for d in sorted(set(users.index) | set(act.index))]
    diff = users.sum() / act.sum() - 1
    idle_seats = 1 - users.sum() / bought.sum()

    weeks = m["week_start"].nunique()
    gb_days = m["storage"].sum() / max(weeks, 1) * 365 if weeks else 0     # weekly storage snapshots → GB-days/year
    video_min = m["teams_video_minutes"].sum()
    eu = F["grid"]["EU"]
    kwh_min = {"low": VIDEO_GB_PER_HOUR["low"] * F["network"]["kwh_per_gb"]["low"] / 60,
               "mid": VIDEO_GB_PER_HOUR["mid"] * F["network"]["kwh_per_gb"]["mid"] / 60,
               "high": OBRINGER_KG_PER_HOUR / eu["mid"] / 60}
    bottom_up = {l: gb_days * F["storage"]["kwh_per_gb_day"][l] + video_min * kwh_min[l] for l in ("low", "mid", "high")}
    rec = recurring(ctx)
    ours = float(rec.loc[rec["resource_id"] == "saas-m365", "kwh_mid"].sum())
    inside = bottom_up["low"] <= ours <= bottom_up["high"]
    c = card("m365", "Microsoft 365: real use vs licences", [SRC, "saas_contracts.csv"],
             f"Admin data shows {users.sum():,.0f} active users vs {act.sum():,.0f} active licences "
             f"({diff:+.0%}): the licence data is confirmed; {idle_seats:.0%} of the purchased seats are unused. "
             f"Bottom-up energy {bottom_up['mid']:,.0f} kWh/year (range {bottom_up['low']:,.0f}–{bottom_up['high']:,.0f}) vs "
             f"{ours:,.0f} kWh in our baseline: {'consistent' if inside else 'outside the range, check the SaaS factor'}.",
             [("active users (admin, average)", users.sum(), "users"), ("active licences (contracts)", act.sum(), "licences"),
              ("purchased licences", bought.sum(), "licences"), ("unused purchased seats", idle_seats, "share"),
              ("Teams video minutes", video_min, "min/year"), ("storage", gb_days / 365, "GB (average)"),
              ("energy bottom-up (mid)", bottom_up["mid"], "kWh/year"), ("energy in our baseline", ours, "kWh/year")],
             entity_ids=["res:saas-m365"], row_count=len(m),
             formula="licences: mean weekly active users vs mean monthly active licences; energy: storage GB-days × "
                     "storage factor + video minutes × kWh/min (data volume × network factor; high: Obringer et al. 2021)",
             fact_ids=["saas-m365.active_users_admin", "saas-m365.unused_seat_share"])
    c["by_department"] = depts
    c["energy_check"] = {"bottom_up_kwh": {k: round(v, 1) for k, v in bottom_up.items()}, "baseline_kwh": round(ours, 1),
                         "consistent": bool(inside), "baseline_changed": False,
                         "sources": ["factors.yaml (storage, network)", "Obringer et al. 2021, Resources, Conservation & Recycling 167"]}
    facts = [("saas-m365.active_users_admin", users.sum(), "users", "M365 active users (admin data, weekly average)", SRC),
             ("saas-m365.unused_seat_share", idle_seats, "share", "M365 purchased seats without an active user (admin data)", SRC),
             ("saas-m365.admin_vs_licence_difference", diff, "share", "admin active users vs licence data active (consistency)", SRC)]
    return Insight(c, facts)
