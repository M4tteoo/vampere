"""Optimiser (code): picks the optimal package for a goal, exactly (mixed-integer programme).

Goals (the user chooses what gets priority):
  climate_first  maximise CO2 saved        · budget ≤ max · cost ≥ −25 % · CO2 ≥ −40 %
  best_value     minimise implementation   · CO2 ≥ −40 % · cost ≥ −25 % · budget ≤ max
  francs_first   maximise francs saved/yr  · budget ≤ max · CO2 ≥ −40 %
Safety margin (always on, every goal): the CO2 threshold must hold with the pessimistic
factor set too (every factor level, not just the middle one). If no package within the
budget can do that, the goal is reported as not feasible.

Rules always applied: blocked measures are never chosen; alternatives of the same
measure (same group) and measures acting on the same resource are mutually exclusive
(no double counting). Solves in milliseconds, so the goal can be switched live.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

GOALS = ("climate_first", "best_value", "francs_first")
LEVELS = ("low", "mid", "high")


def _conflicts(measures: list[dict], resource_of) -> list[tuple[int, int]]:
    def touch(m):
        out = set()
        for e in m["effects"]:
            s = e["scope"]
            out.add(("scope", s))
            if s.startswith("res:"):
                out.add(("res", s[4:]))
            elif s.startswith(("srv:", "ai:")):
                out.add(("child", resource_of(s), s))
        return out
    pairs = []
    for i in range(len(measures)):
        ti = touch(measures[i])
        for j in range(i + 1, len(measures)):
            if measures[i]["group"] == measures[j]["group"]:
                pairs.append((i, j))
                continue
            tj = touch(measures[j])
            if {x for x in ti if x[0] == "scope"} & {x for x in tj if x[0] == "scope"}:
                pairs.append((i, j))
                continue
            res_i = {x[1] for x in ti if x[0] == "res"}
            res_j = {x[1] for x in tj if x[0] == "res"}
            child_i = {x[1] for x in ti if x[0] == "child"}
            child_j = {x[1] for x in tj if x[0] == "child"}
            if res_i & (res_j | child_j) or res_j & child_i:
                pairs.append((i, j))
    return pairs


def optimise(measures: list[dict], baseline: dict, goal: str, safety: bool, budget_chf: float,
             thresholds: dict, resource_of, chf_per_day: float = 1100) -> dict:
    """measures: dicts with key, group, status, effort_days, effects and _savings (cost_chf, co2_kg_low/mid/high)."""
    elig = [m for m in measures if m["status"] != "blocked"]
    n = len(elig)
    if n == 0:
        return {"goal": goal, "safety": safety, "feasible": False, "measure_keys": [], "note": "no eligible measures"}
    eff = np.array([m["effort_days"] for m in elig], float)
    cost = np.array([m["_savings"]["cost_chf"] for m in elig], float)
    co2 = {l: np.array([m["_savings"][f"co2_kg_{l}"] for m in elig], float) for l in LEVELS}
    budget_days = budget_chf / chf_per_day
    A, lo, hi = [], [], []

    def add(row, l=-np.inf, h=np.inf):
        A.append(row); lo.append(l); hi.append(h)

    add(eff, h=budget_days)                                            # budget
    for i, j in _conflicts(elig, resource_of):                          # no double counting
        row = np.zeros(n); row[i] = row[j] = 1
        add(row, h=1)
    co2_levels = LEVELS if safety else ("mid",)
    if goal in ("climate_first", "best_value"):
        add(cost, l=thresholds["cost"] * baseline["cost_chf"])
    if goal in ("best_value", "francs_first"):
        for l in co2_levels:
            add(co2[l], l=thresholds["co2"] * baseline[f"co2_kg_{l}"])
    if goal == "climate_first" and safety:
        for l in LEVELS:
            add(co2[l], l=thresholds["co2"] * baseline[f"co2_kg_{l}"])
    # objective (milp minimises); tiny tie-breakers keep the result stable and sensible
    if goal == "climate_first":
        c = -(co2["mid"] / baseline["co2_kg_mid"] + 1e-3 * cost / baseline["cost_chf"])
    elif goal == "francs_first":
        c = -(cost / baseline["cost_chf"] + 1e-3 * co2["mid"] / baseline["co2_kg_mid"])
    else:
        c = eff / budget_days - 1e-3 * co2["mid"] / baseline["co2_kg_mid"]
    res = milp(c, constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(n), bounds=Bounds(0, 1))
    if res.status != 0:
        return {"goal": goal, "safety": safety, "feasible": False, "measure_keys": [],
                "note": "no package satisfies these rules" + (" (try without the safety margin)" if safety else "")}
    x = np.round(res.x).astype(bool)
    chosen = [m["key"] for m, k in zip(elig, x) if k]
    return {"goal": goal, "safety": safety, "feasible": True, "measure_keys": chosen,
            "effort_days": float(eff[x].sum()), "effort_chf": float(eff[x].sum() * chf_per_day),
            "co2_reduction": {l: float(co2[l][x].sum() / baseline[f"co2_kg_{l}"]) for l in LEVELS},
            "cost_reduction": float(cost[x].sum() / baseline["cost_chf"])}


def all_goals(measures, baseline, budget_chf, thresholds, resource_of) -> dict:
    """Every goal ALWAYS with the safety margin: the CO2 threshold must hold with the pessimistic factors too.
    Never returns an empty package: if no package meets the rules, it falls back (and says so) to
    1) the thresholds with the middle factors only, 2) the most CO2 within the budget."""
    out = {}
    for g in GOALS:
        r = optimise(measures, baseline, g, True, budget_chf, thresholds, resource_of)
        r["safety_met"] = r["feasible"]
        if not r["feasible"]:
            r = optimise(measures, baseline, g, False, budget_chf, thresholds, resource_of)
            r["safety_met"] = False
            r["note"] = ("no package within the budget reaches the thresholds with pessimistic factors: "
                         "this package meets them with the middle factors only")
            if not r["feasible"]:
                r = optimise(measures, baseline, "climate_first", False, budget_chf, {"co2": 0.0, "cost": 0.0}, resource_of)
                r["goal"], r["safety_met"] = g, False
                r["note"] = "no package within the budget reaches the thresholds: this is the most CO2 the budget allows"
            r["feasible"] = True
        out[g] = r
    return out
