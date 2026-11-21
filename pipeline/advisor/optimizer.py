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
             thresholds: dict, resource_of, chf_per_day: float = 1100, mc: dict | None = None) -> dict:
    """safety + mc: Monte Carlo rule. mc = {"S": CO2 savings per measure and scenario (n_measures × n_draws, same
    order as `measures`), "B": baseline CO2 per scenario, "share": 0.9, "sample": 400}. The CO2 threshold must hold
    in at least `share` of the scenarios: decided on a sample (chance constraint, one binary per sampled scenario),
    then verified on all draws; if the check falls short the required share on the sample is raised and re-solved."""
    """measures: dicts with key, group, status, effort_days, effects and _savings (cost_chf, co2_kg_low/mid/high)."""
    elig = [m for m in measures if m["status"] != "blocked"]
    n = len(elig)
    if n == 0:
        return {"goal": goal, "safety": safety, "feasible": False, "measure_keys": [], "note": "no eligible measures"}
    idx = [i for i, m in enumerate(measures) if m["status"] != "blocked"]
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
    use_mc = safety and mc is not None
    co2_levels = LEVELS if (safety and not use_mc) else ("mid",)        # corner rule only without Monte Carlo
    if goal in ("climate_first", "best_value"):
        add(cost, l=thresholds["cost"] * baseline["cost_chf"])
    if goal in ("best_value", "francs_first"):
        for l in co2_levels:
            add(co2[l], l=thresholds["co2"] * baseline[f"co2_kg_{l}"])
    if goal == "climate_first" and safety and not use_mc:
        for l in LEVELS:
            add(co2[l], l=thresholds["co2"] * baseline[f"co2_kg_{l}"])
    # objective (milp minimises); tiny tie-breakers keep the result stable and sensible
    if goal == "climate_first":
        c = -(co2["mid"] / baseline["co2_kg_mid"] + 1e-3 * cost / baseline["cost_chf"])
    elif goal == "francs_first":
        c = -(cost / baseline["cost_chf"] + 1e-3 * co2["mid"] / baseline["co2_kg_mid"])
    else:
        c = eff / budget_days - 1e-3 * co2["mid"] / baseline["co2_kg_mid"]
    p_meet = None
    if not use_mc:
        res = milp(c, constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(n), bounds=Bounds(0, 1))
        if res.status != 0:
            return {"goal": goal, "safety": safety, "feasible": False, "measure_keys": [], "note": "no package satisfies these rules"}
        x = np.round(res.x[:n]).astype(bool)
    else:
        S = np.asarray(mc["S"])[idx]                                     # (n, draws)
        Bc = np.asarray(mc["B"])
        k = min(int(mc.get("sample", 400)), Bc.size)
        sample = np.random.default_rng(7).choice(Bc.size, k, replace=False)
        x, required = None, float(mc["share"])
        for _ in range(4):
            # x (n binaries) + z (k binaries): Σ S_ij x_i − thr·B_j z_j ≥ 0 ; Σ z_j ≥ required·k
            A2 = [np.concatenate([r, np.zeros(k)]) for r in A]
            lo2, hi2 = list(lo), list(hi)
            for jj, j in enumerate(sample):
                row = np.concatenate([S[:, j], np.zeros(k)]); row[n + jj] = -thresholds["co2"] * Bc[j]
                A2.append(row); lo2.append(0.0); hi2.append(np.inf)
            A2.append(np.concatenate([np.zeros(n), np.ones(k)])); lo2.append(np.ceil(required * k)); hi2.append(np.inf)
            res = milp(np.concatenate([c, np.zeros(k)]), constraints=LinearConstraint(np.array(A2), lo2, hi2),
                       integrality=np.ones(n + k), bounds=Bounds(0, 1), options={"time_limit": 20})
            if res.x is None:
                break
            cand = np.round(res.x[:n]).astype(bool)
            p = float(((S[cand].sum(0)) >= thresholds["co2"] * Bc).mean())
            if p >= mc["share"]:
                x, p_meet = cand, p
                break
            required = min(1.0, required + 0.02)                        # sampling error: tighten and re-solve
        if x is None:
            return {"goal": goal, "safety": safety, "feasible": False, "measure_keys": [],
                    "note": f"no package within the budget reaches the CO2 threshold in {mc['share']:.0%} of scenarios"}
    chosen = [m["key"] for m, k_ in zip(elig, x) if k_]
    out = {"goal": goal, "safety": safety, "feasible": True, "measure_keys": chosen,
           "effort_days": float(eff[x].sum()), "effort_chf": float(eff[x].sum() * chf_per_day),
           "co2_reduction": {l: float(co2[l][x].sum() / baseline[f"co2_kg_{l}"]) for l in LEVELS},
           "cost_reduction": float(cost[x].sum() / baseline["cost_chf"])}
    if mc is not None:
        S_all = np.asarray(mc["S"])[idx]
        out["p_meet_co2"] = round(float((S_all[x].sum(0) >= thresholds["co2"] * np.asarray(mc["B"])).mean()), 4) \
            if p_meet is None else round(p_meet, 4)
    return out


def safest(measures: list[dict], baseline: dict, budget_chf: float, thresholds: dict, resource_of, mc: dict,
           chf_per_day: float = 1100) -> dict:
    """The package with the highest share of Monte Carlo scenarios reaching the CO2 threshold, within the case
    rules (budget, cost ≥ threshold, CO2 ≥ threshold with the middle factors, no conflicts). Decided on a sample
    of scenarios (one binary per sampled scenario), reported on all draws; tie-break: more CO2."""
    elig = [m for m in measures if m["status"] != "blocked"]
    idx = [i for i, m in enumerate(measures) if m["status"] != "blocked"]
    n = len(elig)
    eff = np.array([m["effort_days"] for m in elig], float)
    cost = np.array([m["_savings"]["cost_chf"] for m in elig], float)
    co2 = {l: np.array([m["_savings"][f"co2_kg_{l}"] for m in elig], float) for l in LEVELS}
    S, Bc = np.asarray(mc["S"])[idx], np.asarray(mc["B"])
    k = min(int(mc.get("sample", 400)), Bc.size)
    sample = np.random.default_rng(7).choice(Bc.size, k, replace=False)
    A, lo, hi = [], [], []

    def add(row, l=-np.inf, h=np.inf):
        A.append(row); lo.append(l); hi.append(h)
    add(np.concatenate([eff, np.zeros(k)]), h=budget_chf / chf_per_day)
    for i, j in _conflicts(elig, resource_of):
        row = np.zeros(n + k); row[i] = row[j] = 1
        add(row, h=1)
    add(np.concatenate([cost, np.zeros(k)]), l=thresholds["cost"] * baseline["cost_chf"])
    add(np.concatenate([co2["mid"], np.zeros(k)]), l=thresholds["co2"] * baseline["co2_kg_mid"])
    for jj, j in enumerate(sample):
        row = np.concatenate([S[:, j], np.zeros(k)]); row[n + jj] = -thresholds["co2"] * Bc[j]
        add(row, l=0.0)
    c = np.concatenate([-1e-3 * co2["mid"] / baseline["co2_kg_mid"], -np.ones(k) / k])
    res = milp(c, constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(n + k), bounds=Bounds(0, 1),
               options={"time_limit": 20})
    if res.x is None:
        return {"goal": "safest", "safety": True, "feasible": False, "measure_keys": [], "note": "no package meets the case rules"}
    x = np.round(res.x[:n]).astype(bool)
    return {"goal": "safest", "safety": True, "feasible": True, "measure_keys": [m["key"] for m, kk in zip(elig, x) if kk],
            "effort_days": float(eff[x].sum()), "effort_chf": float(eff[x].sum() * chf_per_day),
            "co2_reduction": {l: float(co2[l][x].sum() / baseline[f"co2_kg_{l}"]) for l in LEVELS},
            "cost_reduction": float(cost[x].sum() / baseline["cost_chf"]),
            "p_meet_co2": round(float((S[x].sum(0) >= thresholds["co2"] * Bc).mean()), 4)}


def all_goals(measures, baseline, budget_chf, thresholds, resource_of, mc: dict | None = None) -> dict:
    """One optimal package per goal under the CASE rules (budget, CO2 and cost thresholds with the middle factors).
    Safety is REPORTED for every package (share of Monte Carlo scenarios reaching the CO2 threshold), not required,
    unless mc["share"] sets a minimum. Adds «safest» (highest share) and flags it: if it equals a goal's package,
    `same_as` names that goal and both carry is_safest. Never returns an empty package (falls back, with a note)."""
    n_draws = np.asarray(mc["B"]).size if mc else 0
    out = {}
    for g in GOALS:
        # risk appetite per option: a goal-specific minimum safety (e.g. best value ≥ 80 %), else the general one
        min_share = ((mc.get("share_by_goal") or {}).get(g, mc.get("share"))) if mc else None
        mc_g = {**mc, "share": min_share} if mc else None
        rule = (f"case rules; safety = share of {n_draws:,} Monte Carlo scenarios reaching −{thresholds['co2']:.0%} CO2"
                + (f" (minimum {min_share:.0%})" if min_share else " (reported, not required)")) if mc else "case rules"
        r = optimise(measures, baseline, g, bool(min_share), budget_chf, thresholds, resource_of, mc=mc_g)
        r["safety_met"] = r["feasible"] if min_share else None
        if not r["feasible"]:
            r = optimise(measures, baseline, g, False, budget_chf, thresholds, resource_of, mc=mc_g)
            if min_share:
                r["safety_met"] = False
                r["note"] = f"no package within the budget is safe in {min_share:.0%} of scenarios: this one meets the case rules"
            if not r["feasible"]:
                r = optimise(measures, baseline, "climate_first", False, budget_chf, {"co2": 0.0, "cost": 0.0}, resource_of, mc=mc_g)
                r["goal"] = g
                r["note"] = "no package within the budget reaches the thresholds: this is the most CO2 the budget allows"
            r["feasible"] = True
        r["safety_rule"] = rule
        out[g] = r
    if mc:
        sf = safest(measures, baseline, budget_chf, thresholds, resource_of, mc)
        if sf["feasible"]:
            sf["safety_rule"] = f"the highest share of {n_draws:,} Monte Carlo scenarios reaching −{thresholds['co2']:.0%} CO2"
            out["safest"] = sf
        best = max((v.get("p_meet_co2") or 0) for v in out.values())
        for gk, v in out.items():
            v["is_safest"] = bool(v.get("p_meet_co2") is not None and v["p_meet_co2"] >= best - 1e-9)
        if "safest" in out:
            same = [g for g in GOALS if set(out[g]["measure_keys"]) == set(out["safest"]["measure_keys"])]
            if same:
                out["safest"]["same_as"] = same[0]
            elif not out["safest"]["is_safest"]:     # sampling: a goal's package turned out safer on all draws
                top = max(GOALS, key=lambda g: out[g].get("p_meet_co2") or 0)
                out["safest"] = {**out[top], "goal": "safest", "same_as": top}
    return out
