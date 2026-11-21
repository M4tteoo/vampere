"""A5 · Carbon-aware load shifting: move flexible jobs to cleaner hours inside
their allowed window; fixed jobs (protection windows) are never moved.

Inputs
  stg_data_platform_jobs        every scheduled run with its window (fixed / flexible + rule)
  stg_data_platform_usage       nodes of the cluster on the day of the run
  data/hourly_intensity.csv     relative hourly CO2 profile per location × month × day type × hour
                                (Energy-Charts, baseline year; see hourly_intensity.py)
  pipeline/energy/factors.yaml  power model, PUE and the location-based grid factor (absolute level)

Energy of one run (data-platform clusters, 16 vCPU / 64 GB per node, CCF power model):
  full      nodes × h × (16 × (Wmin + u_job × (Wmax − Wmin)) + 64 GB × W/GB) × PUE
            → what the run costs when the cluster pauses when idle (after the auto-pause measures)
  marginal  nodes × h × 16 × (u_job − u_idle) × (Wmax − Wmin) × PUE
            → what moving the run changes TODAY, while the cluster runs 24/7 anyway
CO2 of a placement = energy × location factor (factors.yaml) × mean relative intensity of the hours it covers.

Two policies per job: «static» = one new fixed start (what a cron change achieves);
«dynamic» = best placement per run on the monthly profile (a carbon-aware scheduler).
Protected hours: a flexible run must not overlap any fixed run of the same resource on that date
(daily deadlines such as the ETL, and month-end / year-end close on their days, incl. past midnight).

Outputs: output/jobs.json (contract JobsFile) · DuckDB table carbon_aware_jobs ·
candidate measure in output/bonus/candidates.json.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from ..energy.engine import LEVELS, load_factors
from ..harmonize.context import Context
from .common import rng, write_candidates, write_json, write_table

PROFILE_FILE = Path(__file__).with_name("data") / "hourly_intensity.csv"
META_FILE = Path(__file__).with_name("data") / "hourly_intensity_meta.json"

U_JOB = {"low": 0.5, "mid": 0.7, "high": 0.9}   # CPU utilisation of the nodes while a batch job runs (assumption)
U_IDLE = 0.05                                    # CPU of an idle but running cluster (assumption)
DAILY_FIXED_MIN_RUNS = 100                       # fixed jobs running (almost) daily block their hours
CLUSTERS = ("dp-prod", "dp-dev")                 # node-hour resources: energy per run is quantifiable
EFFORT_DAYS = 1.0                                # re-schedule flexible jobs + test (assumption)

# Constraints from tickets that are stricter than the job's window in the scheduler (curated, like the
# one-offs in reference.yaml): the job keeps its days, only the hour may move, and a human confirms.
TICKET_CONSTRAINTS = {
    "Quarterly model training": ("T-1053, T-1101: training needs dp-dev continuously on days 1–3 of the quarter, "
                                 "together with the GPU server → keep the days, move only the start hour; "
                                 "confirm with the responsible role"),
}


# ------------------------------------------------------------- windows
def _candidates(rule: str, hour: int, day_type: str, dur: float) -> list[tuple[str, int]]:
    """Allowed (day_type, start hour) placements for a flexible job."""
    r = (rule or "").lower()
    both = ["workday", "weekend"]
    if "within 24 h" in r:
        return [(day_type, h) for h in range(24)]
    if any(k in r for k in ("within the week", "within the month", "first week of the quarter")):
        return [(d, h) for d in both for h in range(24)]
    if "working day 08:00 to 18:00" in r:
        return [("workday", h) for h in range(8, 24) if h + dur <= 18]
    if "before the next working day" in r:
        return [(day_type, h) for h in [*range(hour, 24), *range(0, 24)] if h >= hour or h + dur <= 8]
    return []


def _covered(start: int, dur: float) -> list[tuple[int, float]]:
    """(hour of day, weight) covered by a run starting at `start` for `dur` hours."""
    out, t = [], 0.0
    while t < dur - 1e-9:
        w = min(1.0, dur - t)
        out.append(((start + int(t)) % 24, w))
        t += 1.0
    return out


def _blocked(jobs: pd.DataFrame) -> dict[tuple[str, str], set[int]]:
    """Hours taken by fixed runs, per (resource, date); runs past midnight block the next date too."""
    out: dict[tuple[str, str], set[int]] = {}
    for r in jobs[jobs["window_type"] == "fixed"].itertuples():
        start = int(r.start_time[:2]) + int(r.start_time[3:5]) / 60
        day = pd.Timestamp(r.date)
        for h in range(int(start), math.ceil(start + r.duration_h)):
            key = (r.resource_id, (day + pd.Timedelta(days=h // 24)).strftime("%Y-%m-%d"))
            out.setdefault(key, set()).add(h % 24)
    return out


def _daily_protected(blocked: dict[tuple[str, str], set[int]], n_days: int) -> dict[str, list[int]]:
    """Hours blocked on most days (for display): the daily deadlines."""
    count: dict[tuple[str, int], int] = {}
    for (res, _), hours in blocked.items():
        for h in hours:
            count[(res, h)] = count.get((res, h), 0) + 1
    out: dict[str, list[int]] = {}
    for (res, h), n in sorted(count.items()):
        if n >= DAILY_FIXED_MIN_RUNS:
            out.setdefault(res, []).append(h)
    return out


# ------------------------------------------------------------- energy
def _energy_per_node_hour(F: dict, lvl: str, kind: str) -> float:
    c, node = F["compute"], F["shapes"]["node"]
    span = c["cpu_w_max"][lvl] - c["cpu_w_min"][lvl]
    if kind == "full":
        w = node["vcpu"] * (c["cpu_w_min"][lvl] + U_JOB[lvl] * span) + node["ram_gb"] * c["mem_w_per_gb"][lvl]
    else:
        w = node["vcpu"] * (U_JOB[lvl] - U_IDLE) * span
    return w / 1000 * F["pue"]["hyperscaler"][lvl]


def _grid(F: dict, loc: str, lvl: str, scenario: str) -> float:
    g = F["grid"][loc]
    return g["variants"][scenario][lvl] if loc == "CH" and "variants" in g else g[lvl]


# ---------------------------------------------------------------- run
def run(ctx: Context) -> None:
    if not PROFILE_FILE.exists():
        raise FileNotFoundError(f"{PROFILE_FILE} missing: run `python -m pipeline.bonus.hourly_intensity build`")
    F = load_factors()
    scenario = ctx.config.get("scenario", "ch_consumption")
    b0, b1 = ctx.baseline
    prof = pd.read_csv(PROFILE_FILE)
    rel = {(r.location, r.month, r.day_type, r.hour): r.relative for r in prof.itertuples()}

    jobs = ctx.tables["stg_data_platform_jobs"]
    jobs = jobs[jobs["date"].between(b0, b1)].copy()
    res = ctx.tables["dim_resource"].set_index("resource_id")
    jobs["location"] = jobs["resource_id"].map(res["location"])
    d = pd.to_datetime(jobs["date"])
    jobs["month"] = d.dt.month
    jobs["day_type"] = np.where(d.dt.dayofweek >= 5, "weekend", "workday")
    jobs["hour"] = jobs["start_time"].str[:2].astype(int)
    usage = ctx.tables["stg_data_platform_usage"].set_index(["resource_id", "date"])["node_count"]
    jobs["nodes"] = [usage.get((r, dt), np.nan) for r, dt in zip(jobs["resource_id"], jobs["date"])]
    blocked = _blocked(jobs)
    for key, hours in _limit_blocks(ctx, set(jobs["date"])).items():   # Step 7 windows with a time range
        blocked.setdefault(key, set()).update(hours)

    def simulate(loc_of: dict[str, str]) -> tuple[list[dict], list[dict]]:
        """All jobs with locations `loc_of` (resource → grid). Returns (all jobs, shiftable jobs)."""
        def placement_rel(loc, month, day_type, start, dur):
            cov = _covered(start, dur)
            return sum(rel[(loc, month, day_type, h)] * w for h, w in cov) / sum(w for _, w in cov)

        out_jobs, rows = [], []
        for (res_id, name), g in jobs.groupby(["resource_id", "job_name"], sort=False):
            first = g.iloc[0]
            loc = loc_of.get(res_id, first["location"])
            wtype, rule = first["window_type"], first["window_rule"] or first["time_window"]
            dur = float(g["duration_h"].mean())
            usual = int(g["hour"].mode()[0])
            base = {"job_name": name, "resource_id": res_id, "entity_id": f"res:{res_id}", "location": loc,
                    "window_type": wtype if isinstance(wtype, str) else "other", "window_rule": rule,
                    "runs": int(len(g)), "usual_start": f"{usual:02d}:00", "avg_duration_h": round(dur, 2)}
            reason = _not_shiftable(wtype, loc, res_id)
            if reason:
                out_jobs.append({**base, "shiftable": False, "locked": wtype == "fixed", "reason": reason,
                                 "suggested_start": None, "kwh_per_run": None, "co2_kg_year": None})
                continue

            ticket_note = TICKET_CONSTRAINTS.get(name)
            cands = _candidates("within 24 h" if ticket_note else rule, usual, "workday", dur)

            def free(r, cand):  # no overlap with a fixed run of this resource on the run's date
                return not ({h for h, _ in _covered(cand[1], dur)} & blocked.get((res_id, r.date), set()))

            runs = list(g.itertuples())
            cands = [c for c in cands if any(free(r, c) for r in runs)]
            if not cands:
                out_jobs.append({**base, "shiftable": False, "locked": False, "reason": "no allowed hour outside the "
                                 "protected hours of the resource", "suggested_start": None, "kwh_per_run": None,
                                 "co2_kg_year": None})
                continue

            # A rule that allows other days (week / month / quarter) may also change the day type;
            # otherwise the run keeps the day type of its date and only the hour moves.
            multi_day = len({dt for dt, _ in cands}) > 1

            def rel_of(r, cand):
                return placement_rel(loc, r.month, cand[0] if multi_day else r.day_type, cand[1], dur)

            cur = np.array([placement_rel(loc, r.month, r.day_type, r.hour, dur) for r in runs])
            # static: one start for all runs, so it must be free on every run date (e.g. not 18:00 on dp-prod,
            # which collides with the month-end close); dynamic: best free placement per run
            static = {c: np.array([rel_of(r, c) for r in runs]) for c in cands if all(free(r, c) for r in runs)}
            if not static:
                static = {(runs[0].day_type, usual): cur}
            best_static = min(static, key=lambda c: static[c].sum())
            dyn = np.array([min([rel_of(r, c) for c in cands if free(r, c)] or [rel_of(r, (r.day_type, r.hour))])
                            for r in runs])
            nodes = g["nodes"].fillna(g["nodes"].median()).to_numpy()

            res_lv = {}
            for kind in ("marginal", "full"):
                for lvl in LEVELS:
                    e_run = nodes * dur * _energy_per_node_hour(F, lvl, kind)   # kWh per run
                    f = _grid(F, loc, lvl, scenario)
                    res_lv[(kind, lvl)] = {
                        "kwh_run": float(e_run.mean()),
                        "now": float((e_run * f * cur).sum()),
                        "static": float((e_run * f * static[best_static]).sum()),
                        "dynamic": float((e_run * f * dyn).sum())}

            def metric(kind, key):
                return rng(*(res_lv[(kind, l)][key] for l in LEVELS), nd=2)

            def saving(kind, pol):
                return rng(*(res_lv[(kind, l)]["now"] - res_lv[(kind, l)][pol] for l in LEVELS), nd=2)

            day_label = best_static[0] if multi_day else "same day"
            out_jobs.append({**base, "shiftable": True, "locked": False, "reason": None,
                             "needs_human": ticket_note,
                             "suggested_start": f"{best_static[1]:02d}:00", "suggested_day_type": day_label,
                             "relative_intensity": {"now": round(float(cur.mean()), 3),
                                                    "static": round(float(static[best_static].mean()), 3),
                                                    "dynamic": round(float(dyn.mean()), 3)},
                             "kwh_per_run": {"marginal": metric("marginal", "kwh_run"), "full": metric("full", "kwh_run")},
                             "co2_kg_year": {k: {"now": metric(k, "now"), "saving_static": saving(k, "static"),
                                                 "saving_dynamic": saving(k, "dynamic")} for k in ("marginal", "full")}})
            rows.append(out_jobs[-1])
        return out_jobs, rows

    out_jobs, rows = simulate({})
    totals = _totals(rows)
    after = _after_package(ctx, simulate)

    baseline_co2 = float(ctx.tables["fact_cost"].loc[ctx.tables["fact_cost"]["in_baseline"], "co2_kg_mid"].sum())
    meta = _profile_meta()
    calc = {
        "formula": "saving = Σ runs energy per run × location factor × (relative intensity now − at the new hours); "
                   "energy per run = nodes × hours × node power (CCF) × PUE; relative intensity from the hourly "
                   "profile (Energy-Charts, baseline year), scaled to the location-based factor",
        "inputs": [{"name": "job utilisation", "value": U_JOB["mid"], "unit": "CPU share", "source": "assumption"},
                   {"name": "idle utilisation", "value": U_IDLE, "unit": "CPU share", "source": "assumption"}],
        "factor_ids": ["energy_per_node_hour", "pue", "grid_mix_location_based_switzerland",
                       "grid_mix_location_based_germany"],
        "source_files": ["extra/data_platform_jobs.csv", "data_platform_usage.csv", "Energy-Charts (CC BY 4.0)"],
        "row_count": int(len(jobs)), "value_status": "estimated", "issue_ids": [],
        "note": "Profiles are monthly averages per hour: a scheduler using live grid forecasts would gain more on "
                "windy / sunny days.",
    }
    payload = {
        "method": {"policies": {"static": "one new fixed start per job (cron change)",
                                "dynamic": "best placement per run on the monthly profile (carbon-aware scheduler)"},
                   "energy_bases": {"marginal": "today: cluster runs 24/7, only the job's extra power moves",
                                    "full": "after auto-pause: the run's whole energy depends on the hour"},
                   "protected_hours": _daily_protected(blocked, len(jobs["date"].unique())),
                   "ticket_constraints": TICKET_CONSTRAINTS,
                   "assumptions": {"u_job": U_JOB, "u_idle": U_IDLE, "effort_days": EFFORT_DAYS}},
        "profiles": _profiles(prof, F, scenario),
        "profile_source": meta.get("source"), "profile_stats": meta.get("stats"),
        "jobs": out_jobs,
        "totals": {**totals, "baseline_co2_kg": round(baseline_co2, 1),
                   "share_of_baseline_full_dynamic": round(totals["full"]["saving_dynamic"]["mid"] / baseline_co2, 4)},
        "after_package": after,
        "calc": calc,
    }
    write_json(ctx, "jobs.json", payload)
    write_table(ctx, "carbon_aware_jobs", pd.DataFrame([{k: v for k, v in j.items() if not isinstance(v, dict)}
                                                         | {"saving_full_dynamic_kg": (j["co2_kg_year"] or {}).get("full", {}).get("saving_dynamic", {}).get("mid")}
                                                         for j in out_jobs]))
    write_candidates(ctx, "carbon_aware", measures=[_measure(rows, totals, calc, after)])


def _totals(rows: list[dict]) -> dict:
    return {k: {pol: rng(*(sum(j["co2_kg_year"][k][pol][l] for j in rows) for l in LEVELS), nd=1)
                for pol in ("now", "saving_static", "saving_dynamic")} for k in ("marginal", "full")}


def _limit_blocks(ctx: Context, dates: set[str]) -> dict[tuple[str, str], set[int]]:
    """Protection windows of the advisor constraints (Step 7) that have a time range, e.g. finance closing
    00:00–04:00 on the last 3 working days (T-1029). Whole-day «must be available» windows (quarter days,
    test freeze) do not stop a job from running and are not blocked here."""
    from .common import read_output
    rep = read_output(ctx, "advisor/report.json") or {}
    cal = ctx.tables["dim_date"].set_index("date")
    out: dict[tuple[str, str], set[int]] = {}
    for c in rep.get("constraints", []):
        sch = c.get("schedule") or {}
        if c.get("type") != "window" or not sch.get("from_time") or not sch.get("until_time"):
            continue
        h0, h1 = int(sch["from_time"][:2]), int(sch["until_time"][:2]) + (sch["until_time"][3:] != "00")
        hours = set(range(h0, h1)) if h1 > h0 else set(range(h0, 24)) | set(range(0, h1))
        if sch.get("kind") == "monthly_last_workdays":
            days = [d for d in dates if d in cal.index and bool(cal.at[d, "is_last3_workdays_of_month"])]
        elif sch.get("kind") == "daily":
            days = list(dates)
        else:
            continue
        for rid in c.get("applies_to", []):
            for d in days:
                out.setdefault((rid, d), set()).update(hours)
    return out


def _after_package(ctx: Context, simulate) -> dict | None:
    """Carbon-aware ON TOP of the recommended package (additive, contract rule 10): jobs of relocated
    clusters run on the new grid; clusters paused by a package «schedule» measure count with their
    full run energy, the others only with the marginal energy (they still run 24/7)."""
    from .common import read_output
    mf = read_output(ctx, "measures.json")
    if not mf:
        return None
    pkg = [m for m in mf["measures"] if m.get("in_package")]
    loc_of, paused, by = {}, set(), {}
    for m in pkg:
        for e in m.get("effects", []):
            rid = e["scope"].partition(":")[2]
            if e["scope"].startswith("res:") and rid in CLUSTERS:
                if e.get("relocate_to"):
                    loc_of[rid] = e["relocate_to"]
                if m["type"] == "schedule" and e.get("energy_share", 0) > 0:
                    paused.add(rid)
                by.setdefault(rid, []).append(m["id"])
    _, rows = simulate(loc_of)
    basis = {rid: "full" if rid in paused else "marginal" for rid in CLUSTERS}
    saving = {pol: rng(*(sum(j["co2_kg_year"][basis[j["resource_id"]]][pol][l] for j in rows) for l in LEVELS), nd=1)
              for pol in ("saving_static", "saving_dynamic")}
    effort_used = mf["package"]["effort_days"]
    return {"package_measures": mf["package"]["measure_ids"], "relocated": loc_of, "energy_basis": basis,
            "because_of": by, "saving": saving,
            "jobs": [{"job_name": j["job_name"], "resource_id": j["resource_id"], "location": j["location"],
                      "basis": basis[j["resource_id"]], "suggested_start": j["suggested_start"],
                      "saving_dynamic": j["co2_kg_year"][basis[j["resource_id"]]]["saving_dynamic"]} for j in rows],
            "fits_budget": effort_used + EFFORT_DAYS <= 15,
            "note": f"The package already uses {effort_used} of 15 person-days: adding {EFFORT_DAYS} d for carbon-aware "
                    "scheduling exceeds the budget unless another measure is trimmed."}


def _not_shiftable(wtype, loc, res_id) -> str | None:
    if wtype == "fixed":
        return "fixed time window (protection window / deadline): never moved"
    if not isinstance(wtype, str):
        return "scheduled by arrangement with the project: a human decides"
    if res_id not in CLUSTERS:
        if loc == "EU":
            return "runs at an AI provider in «EU (mixed)»: no hourly profile for an unknown location"
        return "billed per GB stored / transferred, not per run: no energy per run to move"
    return None


def _profiles(prof: pd.DataFrame, F: dict, scenario: str) -> list[dict]:
    """24-hour curves (g CO2/kWh at the location-based level) for the timeline."""
    out = []
    for loc in ("CH", "DE", "IE"):
        f = _grid(F, loc, "mid", scenario) * 1000
        for label, months in (("winter", [12, 1, 2]), ("summer", [6, 7, 8]), ("year", list(range(1, 13)))):
            p = prof[(prof["location"] == loc) & prof["month"].isin(months) & (prof["day_type"] == "workday")]
            curve = p.groupby("hour")["relative"].mean().reindex(range(24))
            out.append({"location": loc, "season": label, "day_type": "workday",
                        "g_per_kwh": [round(float(v * f), 1) for v in curve]})
    return out


def _profile_meta() -> dict:
    import json
    if not META_FILE.exists():
        return {}
    with open(META_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _measure(rows: list[dict], totals: dict, calc: dict, after: dict | None) -> dict:
    s = after["saving"]["saving_dynamic"] if after else totals["full"]["saving_dynamic"]
    return {
        "id": "M-CA", "title": "Carbon-aware scheduling of flexible data-platform jobs",
        "description": "Move the flexible jobs of dp-dev and dp-prod to the cleanest allowed hours ("
                       + "; ".join(f"{j['job_name']} → {j['suggested_start']}" for j in rows)
                       + "). Fixed jobs and protected hours are untouched. Pays off fully only together with "
                         "auto-pause of the clusters.",
        "type": "schedule", "entity_ids": sorted({j["entity_id"] for j in rows}), "finding_ids": [],
        "limit_ids": [], "effort_days": EFFORT_DAYS, "effort_chf": EFFORT_DAYS * 1100,
        "savings": {"cost_chf": rng(0, 0, 0), "cost_eur": rng(0, 0, 0), "cost_usd": rng(0, 0, 0),
                    "kwh": rng(0, 0, 0), "co2_kg": s},
        "status": "ok", "owner_role": "Head of Consulting", "reason": "",
        "start_date": "2026-10-01", "in_package": False, "calc": calc,
        "note": ("Same kWh and CHF, less CO2: the energy is used at cleaner hours. "
                 + ("Savings computed ON TOP of the package (relocations and auto-pause applied, no overlap). "
                    + after["note"] if after else "Savings assume auto-pause (energy basis «full»).")),
    }
