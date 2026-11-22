"""Power BI report hygiene (extra/powerbi_usage.csv).

The capacity (res:pbi-kap, Azure, Zurich) is billed per day, whatever runs on it.
Code classifies every report and estimates two steps:

  1. clean-up: stop refreshing reports nobody opens, retire copies, refresh quarterly
     reports only in closing months → less load → less energy (the bill stays the same);
  2. downsize: if the remaining load fits half the capacity, move one tier down →
     about half the cost (Fabric / Power BI capacities are sized in capacity units;
     ASSUMPTION: price proportional to capacity units, verify on the Azure price page).
     A decision for people (Head of IT + Finance), with the load data attached.

Energy follows the engine's capacity model (factors.yaml: 8 v-cores + 25 GB,
utilisation 50 %), with utilisation proportional to the refresh load.
"""
from __future__ import annotations

import re

import pandas as pd

from ..energy.engine import load_factors
from ..harmonize.context import Context
from .common import Insight, card, potential, resource_sums, role

RESOURCE = "pbi-kap"
UNUSED_VIEWS_PER_YEAR = 30          # fewer views a year = nobody really uses it
QUARTERLY_KEEP = 1 / 3              # quarterly reports: refresh only in closing months
HEADROOM = 0.8                      # downsize only if the load fits 80 % of half the capacity
SOURCE = "extra/powerbi_usage.csv"


def _reports(ctx: Context) -> pd.DataFrame:
    b0, b1 = ctx.baseline
    pb = ctx.tables["stg_powerbi_usage"]
    pb = pb[pb["date"].between(b0, b1)]
    r = pb.groupby("report_id").agg(
        report=("report", "first"), department=("department", "first"),
        report_type=("report_type", lambda s: s.mode().iat[0] if s.notna().any() else None),
        refreshes=("refresh_count", "sum"), refresh_min=("refresh_duration_min", "sum"),
        views=("view_count", "sum"), active_users=("active_user_count", "mean"))
    tickets = ctx.tables["stg_it_tickets"]
    by_ticket = tickets[tickets["resource_id"].isin(r.index)].groupby("resource_id")["ticket_id"].apply(list)
    r["tickets"] = r.index.map(lambda i: by_ticket.get(i, []))

    def cls(row) -> tuple[str, str, float]:
        """(class, action, share of its refresh load removed)"""
        if row["report_type"] == "regulatory" or row["tickets"]:
            return "protected", "keep as is (regulatory / ticket)", 0.0
        if re.search(r"\(copy\)", row["report"], re.I):
            return "duplicate", "retire the copy", 1.0
        if re.search(r"\(quarterly\)", row["report"], re.I):
            return "quarterly", "refresh only in closing months", 1 - QUARTERLY_KEEP
        if row["views"] < UNUSED_VIEWS_PER_YEAR:
            return "unused", "stop scheduled refresh (on demand) or retire", 1.0
        return "in_use", "keep", 0.0

    c = r.apply(cls, axis=1, result_type="expand")
    r[["class", "action", "load_removed_share"]] = c
    r["refresh_min_saved"] = r["refresh_min"] * r["load_removed_share"]
    return r.reset_index()


def _capacity_energy_shares(load_after: float) -> tuple[float, float]:
    """(energy share saved by the clean-up, energy share saved by clean-up + one tier down)."""
    F = load_factors()
    c, cap = F["compute"], F["shapes"]["powerbi_capacity"]
    wmin, wmax, wmem = c["cpu_w_min"]["mid"], c["cpu_w_max"]["mid"], c["mem_w_per_gb"]["mid"]
    u = c["default_utilisation"]

    def watts(vcores, ram, util):
        return vcores * (wmin + min(util, 1.0) * (wmax - wmin)) + ram * wmem
    now = watts(cap["vcpu"], cap["ram_gb"], u)
    clean = watts(cap["vcpu"], cap["ram_gb"], u * load_after)
    half = watts(cap["vcpu"] / 2, cap["ram_gb"] / 2, u * load_after * 2)   # same work on half the cores
    return 1 - clean / now, 1 - half / now


def compute(ctx: Context) -> Insight:
    r = _reports(ctx)
    total_min = r["refresh_min"].sum()
    saved_share = r["refresh_min_saved"].sum() / total_min
    load_after = 1 - saved_share
    fits_half = load_after <= 0.5 * HEADROOM
    e_clean, e_both = _capacity_energy_shares(load_after)
    base = resource_sums(ctx, RESOURCE)
    counts = r["class"].value_counts().to_dict()
    owner = role(ctx, RESOURCE)

    clean_pot = potential(base, 0.0, e_clean)
    both_pot = potential(base, 0.5 if fits_half else 0.0, e_both if fits_half else e_clean)
    protected = [f"{x.report_id} «{x.report}»: {x.action}" + (f" ({', '.join(x.tickets)})" if x.tickets else "")
                 for x in r[r["class"] == "protected"].itertuples()]
    c = card(
        "powerbi", "Power BI: reports refreshed for nobody", [SOURCE, "azure_costs.csv", "it_tickets.csv"],
        f"{counts.get('unused', 0)} of {len(r)} reports are refreshed daily but opened fewer than "
        f"{UNUSED_VIEWS_PER_YEAR} times a year; with {counts.get('duplicate', 0)} copies and "
        f"{counts.get('quarterly', 0)} quarterly reports they use {saved_share:.0%} of the refresh load. "
        f"The capacity costs CHF {base['cost_chf']:,.0f} a year whatever runs on it.",
        [("reports", len(r), "reports"), ("unused (refreshed, < 30 views/year)", counts.get("unused", 0), "reports"),
         ("duplicate copies", counts.get("duplicate", 0), "reports"), ("quarterly", counts.get("quarterly", 0), "reports"),
         ("protected (regulatory / audit)", counts.get("protected", 0), "reports"),
         ("refresh hours per year", total_min / 60, "h"), ("refresh load removable", saved_share, "share"),
         ("capacity load after clean-up", load_after, "share of today"),
         ("capacity cost", base["cost_chf"], "CHF/year")],
        potential_=both_pot,
        action=("clean up the reports, then move the capacity one tier down" if fits_half
                else "clean up the reports (the remaining load does not fit a smaller tier)"),
        status="human", decided_by=f"{owner} + Head of Finance" if owner else "Head of IT + Head of Finance",
        protected=protected, entity_ids=[f"res:{RESOURCE}"],
        formula=("clean-up: refresh minutes of unused reports and copies removed, quarterly reports keep 1/3; "
                 "capacity utilisation ∝ refresh load (engine: 8 v-cores, 25 GB, 50 %); downsizing: half the "
                 "v-cores and memory, cost × 0.5 (ASSUMPTION: capacity price ∝ capacity units)"),
        row_count=int(len(ctx.tables["stg_powerbi_usage"])),
        fact_ids=[f"{RESOURCE}.reports_unused", f"{RESOURCE}.refresh_load_removable_share",
                  f"{RESOURCE}.cleanup_energy_share", f"{RESOURCE}.downsize_fits_half",
                  f"{RESOURCE}.downsize_cost_share", f"{RESOURCE}.cleanup_and_downsize_energy_share"])
    c["steps"] = [
        {"step": "clean-up", "status": "ok", "decided_by": owner, "metrics": clean_pot,
         "note": "less load, same bill: saves energy and CO2 only"},
        {"step": "downsize one tier", "status": "human", "decided_by": "Head of IT + Head of Finance",
         "metrics": both_pot if fits_half else None, "fits": bool(fits_half),
         "note": ("price assumed proportional to capacity units (verify on the Azure price page); a paused "
                  "pay-as-you-go capacity also stops compute billing (Microsoft Learn: pause and resume)")}]
    src = SOURCE
    facts = [
        (f"{RESOURCE}.reports_total", len(r), "reports", "Power BI reports on the capacity", src),
        (f"{RESOURCE}.reports_unused", counts.get("unused", 0), "reports",
         f"reports refreshed but opened < {UNUSED_VIEWS_PER_YEAR} times a year (not copies, not quarterly, not protected)", src),
        (f"{RESOURCE}.reports_duplicate", counts.get("duplicate", 0), "reports", "reports that are «(copy)» duplicates", src),
        (f"{RESOURCE}.reports_quarterly", counts.get("quarterly", 0), "reports", "quarterly reports (needed in closing months only)", src),
        (f"{RESOURCE}.reports_protected", counts.get("protected", 0), "reports", "regulatory or ticket-protected reports (keep)", src),
        (f"{RESOURCE}.refresh_load_removable_share", saved_share, "share",
         "share of refresh minutes removed by the clean-up (unused + copies + quarterly outside closing months)", src),
        (f"{RESOURCE}.cleanup_energy_share", e_clean, "share",
         "energy share of the capacity saved by the clean-up (cost unchanged: billed per day)", "factors.yaml capacity model"),
        (f"{RESOURCE}.downsize_fits_half", 1 if fits_half else 0, "flag",
         "1 if the load after clean-up fits 80 % of half the capacity", src),
        (f"{RESOURCE}.downsize_cost_share", 0.5 if fits_half else 0.0, "share",
         "cost share saved by moving one tier down (ASSUMPTION: price ∝ capacity units; human decision)", "Azure capacity SKUs"),
        (f"{RESOURCE}.cleanup_and_downsize_energy_share", e_both if fits_half else e_clean, "share",
         "energy share saved by clean-up + one tier down", "factors.yaml capacity model"),
    ]
    reports = [{"report_id": x.report_id, "report": x.report, "department": x.department, "type": x.report_type,
                "class": x["class"], "action": x.action, "refreshes": int(x.refreshes), "refresh_hours": round(x.refresh_min / 60, 1),
                "views": int(x.views), "tickets": x.tickets, "parent_id": f"res:{RESOURCE}"}
               for _, x in r.sort_values(["class", "views"]).iterrows()]
    return Insight(c, facts, {"reports": reports})
