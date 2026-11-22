"""B1 · Monte Carlo: how sure is it that the package reaches −40 % CO2 and −25 % cost?

Each uncertain factor of factors.yaml (CPU / memory / GPU power, storage, network,
AI tokens and messages, SaaS, PUE, grid per location) is drawn from a triangular
distribution (low, mode = mid, high), independently, N times. For every draw the
baseline AND the package savings are recomputed with the same factors (linear model
+ package model, both checked against the engine and measures.json), so factors that
scale both cancel out in the reduction. Cost does not depend on energy factors: its
small range (estimated invoice lines) is drawn triangularly as well.

Also reported:
  tornado     reduction with one factor at low / high, all others at mid (what drives the spread)
  stress      all factors move together (one random quantile for all): the «all low / all high» extreme
  production  the same simulation with the Swiss production mix (B2)
  by_goal     the same draws for every goal package of the optimiser (climate first / best value /
              francs first), so the UI can show the certainty of the goal the manager picks

Output: output/montecarlo.json (contract MonteCarloFile).
"""
from __future__ import annotations

import numpy as np

from ..energy.engine import LEVELS
from ..energy.linear import LABELS, UNCERTAIN, at_level, factor_ranges
from ..harmonize.context import Context
from .common import rng, write_json
from .package_eval import PackageModel

N_DRAWS = 10_000
SEED = 2037                       # fixed: the published numbers are reproducible
TARGET = {"co2": 0.40, "cost": 0.25}
BINS = 30
PCT = (5, 25, 50, 75, 95)


def _triangular(gen: np.random.Generator, r: dict, n: int) -> np.ndarray:
    lo, mid, hi = r["low"], r["mid"], r["high"]
    return np.full(n, mid) if hi == lo else gen.triangular(lo, mid, hi, n)


def _quantile_triangular(u: np.ndarray, r: dict) -> np.ndarray:
    """Inverse CDF of the triangular distribution (for the stress case: one quantile for all factors)."""
    a, c, b = r["low"], r["mid"], r["high"]
    if b == a:
        return np.full_like(u, c)
    fc = (c - a) / (b - a)
    return np.where(u < fc, a + np.sqrt(u * (b - a) * (c - a)), b - np.sqrt((1 - u) * (b - a) * (b - c)))


def _cost_draws(gen: np.random.Generator, pm: PackageModel, n: int) -> np.ndarray:
    red = {lvl: float(pm.evaluate(at_level(factor_ranges(pm.scenario), lvl), lvl)["reduction"]["cost"]) for lvl in LEVELS}
    lo, hi = min(red.values()), max(red.values())
    return np.full(n, red["mid"]) if hi == lo else gen.triangular(lo, red["mid"], hi, n)


def _pct(x: float) -> str:
    """Share for the headline: never round 99.9 % up to «100 %»."""
    return f"{x:.0%}" if x in (0.0, 1.0) or 0.01 <= x <= 0.99 else f"{x:.1%}"


def _summary(red: np.ndarray, target: float) -> dict:
    return {"p_meet": round(float((red >= target).mean()), 4),
            "percentiles": {f"p{p}": round(float(np.percentile(red, p)), 4) for p in PCT},
            "mean": round(float(red.mean()), 4)}


def _simulate(pm: PackageModel, scenario: str, gen: np.random.Generator) -> tuple[dict, dict]:
    ranges = factor_ranges(scenario)
    theta = {p: _triangular(gen, ranges[p], N_DRAWS) for p in UNCERTAIN}
    out = pm.evaluate(theta)
    return out, theta


def _tornado(pm: PackageModel, scenario: str) -> list[dict]:
    ranges = factor_ranges(scenario)
    mid = at_level(ranges, "mid")
    base = float(pm.evaluate(mid)["reduction"]["co2"])
    rows = []
    for p in UNCERTAIN:
        lo = float(pm.evaluate({**mid, p: ranges[p]["low"]})["reduction"]["co2"])
        hi = float(pm.evaluate({**mid, p: ranges[p]["high"]})["reduction"]["co2"])
        rows.append({"factor": p, "label": LABELS[p], "range": rng(*ranges[p].values(), nd=6),
                     "reduction_at_low": round(lo, 4), "reduction_at_high": round(hi, 4),
                     "swing": round(abs(hi - lo), 4)})
    rows.sort(key=lambda r: -r["swing"])
    return [{**r, "reduction_at_mid": round(base, 4)} for r in rows]


def _by_goal(pm: PackageModel, theta: dict, theta_stress: dict) -> dict:
    """Every feasible goal on the SAME factor draws as the main simulation (common random numbers: a fair
    comparison, and the recommended goal gives exactly the top-level figures)."""
    out = {}
    for g in pm.goals():
        pm.use(g).check()
        co2 = np.asarray(pm.evaluate(theta)["reduction"]["co2"])
        cost = _cost_draws(np.random.default_rng(SEED + 1), pm, N_DRAWS)
        budget = bool(pm.package["meets"]["budget"])
        out[g] = {"measure_ids": pm.package["measure_ids"], "effort_days": pm.package["effort_days"],
                  "co2_reduction": _summary(co2, TARGET["co2"]), "cost_reduction": _summary(cost, TARGET["cost"]),
                  "p_meet_both": round(float(((co2 >= TARGET["co2"]) & (cost >= TARGET["cost"]) & budget).mean()), 4),
                  "stress_all_factors_together": _summary(np.asarray(pm.evaluate(theta_stress)["reduction"]["co2"]), TARGET["co2"])}
    pm.use(None)
    return out


def run(ctx: Context) -> None:
    TARGET.update(ctx.config.get("advisor", {}).get("thresholds", {}))   # same thresholds as the advisor's optimiser
    pm = PackageModel(ctx)
    pm.check()
    gen = np.random.default_rng(SEED)

    scenario = pm.scenario                                          # the run's Swiss mix (config / --scenario)
    out, theta = _simulate(pm, scenario, gen)
    co2 = np.asarray(out["reduction"]["co2"])
    cost = _cost_draws(gen, pm, N_DRAWS)
    budget = bool(pm.package["meets"]["budget"])
    both = (co2 >= TARGET["co2"]) & (cost >= TARGET["cost"]) & budget

    u = gen.random(N_DRAWS)                                         # stress: all factors at the same quantile
    ranges = factor_ranges(scenario)
    theta_stress = {p: _quantile_triangular(u, ranges[p]) for p in UNCERTAIN}
    stress = np.asarray(pm.evaluate(theta_stress)["reduction"]["co2"])

    prod, _ = _simulate(pm, "ch_production", gen)
    prod_co2 = np.asarray(prod["reduction"]["co2"])

    by_goal = _by_goal(pm, theta, theta_stress)
    # the recommended goal: same cost draws as the top level, so both views show the same figures
    by_goal[pm.goal].update(cost_reduction=_summary(cost, TARGET["cost"]), p_meet_both=round(float(both.mean()), 4))
    counts, edges = np.histogram(co2, bins=BINS)
    co2_sum = _summary(co2, TARGET["co2"])
    payload = {
        "n_draws": N_DRAWS, "seed": SEED, "scenario": scenario, "goal": pm.goal,
        "package": {"measure_ids": pm.package["measure_ids"], "effort_days": pm.package["effort_days"],
                    "deterministic_mid": {"co2": round(float(pm.evaluate(at_level(ranges, "mid"))["reduction"]["co2"]), 4),
                                          "cost": round(float(pm.package["reduction"]["cost"]["mid"]), 4)}},
        "target": TARGET, "budget_met": budget,
        "co2_reduction": co2_sum,
        "cost_reduction": _summary(cost, TARGET["cost"]),
        "p_meet_both": round(float(both.mean()), 4),
        "baseline_co2_kg": {f"p{p}": round(float(np.percentile(out["baseline"]["co2_kg"], p)), 1) for p in PCT},
        "package_savings_co2_kg": {f"p{p}": round(float(np.percentile(out["savings"]["co2_kg"], p)), 1) for p in PCT},
        "histogram": {"metric": "co2_reduction", "edges": [round(float(e), 4) for e in edges],
                      "counts": [int(c) for c in counts], "target": TARGET["co2"]},
        "tornado": _tornado(pm, scenario),
        "stress_all_factors_together": _summary(stress, TARGET["co2"]),
        "production_mix": _summary(prod_co2, TARGET["co2"]),
        "by_goal": by_goal,
        "headline": f"The package reaches −40 % CO2 in {_pct(co2_sum['p_meet'])} of {N_DRAWS:,} factor scenarios "
                    f"(median −{co2_sum['percentiles']['p50']:.1%}); −25 % cost in {_pct(float((cost >= TARGET['cost']).mean()))}.",
        "calc": {
            "formula": "for each of N draws: factors ~ triangular(low, mid, high) independently; reduction = package CO2 "
                       "savings / baseline CO2, both recomputed with the drawn factors (linear energy model + package model)",
            "inputs": [{"name": "draws", "value": N_DRAWS, "unit": "scenarios", "source": "montecarlo.py"},
                       {"name": "seed", "value": SEED, "unit": "", "source": "montecarlo.py"}],
            "factor_ids": sorted(UNCERTAIN), "source_files": ["pipeline/energy/factors.yaml", "fact_cost", "measures.json"],
            "row_count": int(len(pm.base)), "value_status": "estimated", "issue_ids": [],
            "note": "Independent factors are the default; the stress case (all factors together) shows the extreme.",
        },
    }
    write_json(ctx, "montecarlo.json", payload)
