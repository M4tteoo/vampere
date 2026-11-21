"""Projects: closed projects that still cost money, and CO2 per client project
(extra/projects.csv, extra/project_hours_monthly.csv).

Closed projects: billing lines tagged with a project after its end date.

Footprint per project:
  direct    lines tagged with the project (tags, project ids in the exports)
  allocated untagged lines of a department, split by the share of the department's
            working hours booked on the project that month
            (hours / (FTE × 182 h); FTE from headcount.csv, Swiss 42-h week)
  the rest (time not booked on a project) stays «unassigned».
Rechargeable flags come from the project master data (yes / partly / no). This is the
case's alternative allocation key (hours): we use it for projects; departments are
allocated directly by tags / cost centers, so FTE vs hours changes nothing there.
"""
from __future__ import annotations

import pandas as pd

from ..export.frontend import SUMS, metrics
from ..harmonize.context import Context
from .common import Insight, baseline, card, fte_hours_month


def closed(ctx: Context) -> Insight:
    src = "extra/projects.csv"
    b = baseline(ctx)
    pr = ctx.tables["dim_project"]
    done = pr[pr["status"] == "completed"].set_index("project_id")
    rows = b[b["project_id"].isin(done.index)].copy()
    rows["end"] = rows["project_id"].map(done["end"])
    after = rows[rows["charge_period_start"] > rows["end"]]
    out, facts = [], []
    for pid, g in after.groupby("project_id"):
        s = g[SUMS].sum()
        out.append({"project_id": pid, "project": done.at[pid, "project_name"], "ended": str(done.at[pid, "end"]),
                    "resources": sorted(g["resource_id"].dropna().unique().tolist()), "metrics": metrics(s)})
        facts.append((f"project.{pid}.cost_after_end", s["cost_chf"], "CHF/year",
                      f"{pid} ({done.at[pid, 'project_name']}) ended {done.at[pid, 'end']}: cost still billed in the baseline year", src))
        facts.append((f"project.{pid}.co2_after_end", s["co2_kg_mid"], "kg CO2/year",
                      f"{pid}: CO2 of resources still running after the project end", src))
    out.sort(key=lambda x: -x["metrics"]["cost_chf"]["mid"])
    tot = after[SUMS].sum()
    top = out[0] if out else None
    c = card("closed_projects", "Closed projects still running", [src, "azure_costs.csv", "aws_costs.csv"],
             (f"{len(out)} completed projects still have resources billing after their end: CHF {tot['cost_chf']:,.0f} and "
              f"{tot['co2_kg_mid']:,.0f} kg CO2 in the baseline year"
              + (f" (largest: {top['project_id']} {top['project']}, ended {top['ended']})." if top else ".")),
             [("completed projects with costs after the end", len(out), "projects"),
              ("cost after the end", tot["cost_chf"], "CHF/year"), ("CO2 after the end", tot["co2_kg_mid"], "kg/year")],
             potential_=metrics(tot), action="confirm with the project owner, then switch off or re-assign",
             status="human", decided_by="project owner",
             entity_ids=sorted({f"res:{r}" for x in out for r in x["resources"]}), row_count=len(after),
             formula="Σ baseline lines tagged with a completed project and dated after its end",
             fact_ids=[f[0] for f in facts])
    return Insight(c, facts, {"closed_projects": out})


def footprint(ctx: Context) -> Insight:
    src = "extra/project_hours_monthly.csv"
    b = baseline(ctx)
    pr = ctx.tables["dim_project"].set_index("project_id")
    hours = ctx.tables["alloc_project_hours"]
    fte = ctx.tables["alloc_headcount"]
    cols = SUMS
    direct = b[b["project_id"].notna()].groupby("project_id")[cols].sum()
    untagged = b[b["project_id"].isna()].groupby(["month", "department"])[cols].sum()
    capacity = fte.set_index(["month", "department"])["fte"] * fte_hours_month()
    h = hours.groupby(["month", "department", "project_id"])["hours"].sum().reset_index()
    h["share"] = h.apply(lambda r: min(1.0, r["hours"] / capacity.get((r["month"], r["department"]), float("nan"))), axis=1)
    alloc = pd.DataFrame(0.0, index=sorted(set(direct.index) | set(h["project_id"])), columns=cols)
    used = 0
    for r in h.itertuples():
        key = (r.month, r.department)
        if key in untagged.index and pd.notna(r.share):
            alloc.loc[r.project_id] += untagged.loc[key] * r.share
            used += 1
    total = direct.reindex(alloc.index, fill_value=0) + alloc
    projects = []
    for pid, s in total.iterrows():
        meta = pr.loc[pid] if pid in pr.index else pd.Series(dtype=object)
        projects.append({"project_id": pid, "project": meta.get("project_name"), "type": meta.get("type"),
                         "customer": meta.get("customer") if isinstance(meta.get("customer"), str) else None,
                         "status": meta.get("status"), "rechargeable": meta.get("rechargeable"),
                         "direct": metrics(direct.loc[pid] if pid in direct.index else pd.Series(0.0, index=cols)),
                         "allocated_by_hours": metrics(alloc.loc[pid]), "total": metrics(s)})
    projects.sort(key=lambda x: -x["total"]["co2_kg"]["mid"])
    cust = [p for p in projects if p["type"] == "customer"]
    rech = [p for p in cust if p["rechargeable"] in ("yes", "partly")]
    co2_cust = sum(p["total"]["co2_kg"]["mid"] for p in cust)
    co2_rech = sum(p["total"]["co2_kg"]["mid"] * (1 if p["rechargeable"] == "yes" else 0.5) for p in rech)
    c = card("project_footprint", "CO2 per client project", [src, "extra/projects.csv", "extra/headcount.csv"],
             f"Client projects caused {co2_cust:,.0f} kg CO2 in the baseline year; about {co2_rech:,.0f} kg belong to "
             "rechargeable work and can be reported to the clients (Scope 3 for them).",
             [("projects", len(projects), "projects"), ("client projects", len(cust), "projects"),
              ("client project CO2", co2_cust, "kg/year"), ("rechargeable CO2 (partly = 50 %)", co2_rech, "kg/year")],
             formula="project = tagged lines + Σ months, departments: untagged department lines × project hours / "
                     "(FTE × 182 h); time not booked on projects stays unassigned",
             row_count=used, fact_ids=[])
    c["allocation_note"] = ("Departments are allocated directly (tags, cost centers, mapping); no shared Overhead remains, "
                            "so FTE vs hours makes no difference there. Hours are used for the project view.")
    return Insight(c, [], {"projects": projects})
