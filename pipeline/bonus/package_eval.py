"""The recommended package, evaluated for ANY factor values (shared by B1 and B2).

Same rules as the advisor's Calculator (pipeline/advisor/calculator.py), on the
linear energy model, so savings can be recomputed for another Swiss mix (B2) or
for 10,000 random factor draws (B1) without re-running anything:
  - an effect removes cost_share of the scope's recurring baseline cost and
    energy_share of its energy / CO2 (licence energy shares are already adjusted
    by the Calculator and saved in measures.json → effects);
  - a relocation also cuts the CO2 of the remaining energy by (1 − grid_to / grid_from);
  - reduction = package savings / actual baseline (incl. one-off events), as in the Calculator.
`check()` proves it reproduces measures.json at low / mid / high.

The advisor's optimiser gives one package per goal (measures.json → packages:
climate_first / best_value / francs_first); `PackageModel(ctx, goal)` evaluates
any of them (default: the recommended `package`), `goals()` lists the feasible ones.
"""
from __future__ import annotations

import numpy as np

from ..energy.engine import LEVELS
from ..energy.linear import LOCATIONS, LinearEnergy, at_level, factor_ranges
from ..harmonize.context import Context
from .common import read_output
from .scope_rows import ScopeRows

COST = {"low": "cost_chf_low", "mid": "cost_chf", "high": "cost_chf_high"}


class PackageModel:
    def __init__(self, ctx: Context, goal: str | None = None):
        mf = read_output(ctx, "measures.json")
        facts = read_output(ctx, "advisor/facts.json")
        if not mf or not facts:
            raise FileNotFoundError("measures.json / advisor/facts.json missing: run the pipeline with the advisor answers")
        fc = ctx.tables["fact_cost"]
        self.base = fc[fc["in_baseline"]].reset_index(drop=True)
        self.lin = LinearEnergy(self.base)
        self.rows = ScopeRows(self.base, facts, ctx.tables["stg_ai_usage"])
        self.rec = self.rows.recurring.to_numpy()
        self._default = mf["package"]
        self.total = self.lin.aggregate(np.ones(len(self.base), bool))
        self.total_cost = {lvl: float(self.base[COST[lvl]].sum()) for lvl in LEVELS}

        self.all_measures = mf["measures"]
        self.packages = {g: p for g, p in (mf.get("packages") or {}).items() if p.get("feasible")}
        self.default_goal = mf["package"].get("goal")
        self.scenario = mf["meta"]["scenario"]
        self._scopes: dict[str, dict] = {}
        self.use(goal)

    def use(self, goal: str | None = None) -> "PackageModel":
        """Switch to the package of a goal (None = the recommended package); scope caches are kept."""
        mf_pkg = self.packages[goal] if goal else None
        if goal and mf_pkg is None:
            raise KeyError(f"goal {goal} has no feasible package in measures.json")
        self.goal = goal or self.default_goal
        self.package = mf_pkg or self._default
        ids = set(self.package["measure_ids"])
        self.measures = [m for m in self.all_measures if m["id"] in ids and m["status"] != "blocked"]
        return self

    def goals(self) -> list[str]:
        """Feasible goals of the optimiser, the recommended one first."""
        return sorted(self.packages, key=lambda g: g != self.default_goal)

    # ----------------------------------------------------------- scopes
    def scope(self, scope: str) -> dict:
        if scope not in self._scopes:
            rows, k = self.rows.resolve(scope)
            mask = rows.to_numpy()
            A, B = self.lin.aggregate(mask)
            rid = self.rows.servers.get(scope) if scope.startswith("srv:") else scope.partition(":")[2].split(":")[0]
            locs = self.base.loc[self.rec & (self.base["resource_id"] == rid).to_numpy(), "location"].dropna()
            self._scopes[scope] = {"agg": (A * k, B * k), "cost": {l: float(self.base.loc[mask, COST[l]].sum()) * k for l in LEVELS},
                                   "from": locs.mode().iat[0] if len(locs) else None}
        return self._scopes[scope]

    # ---------------------------------------------------------- evaluate
    def measure_savings(self, m: dict, theta: dict, cost_level: str = "mid") -> dict:
        kwh_s, co2_s, cost_s = 0.0, 0.0, 0.0
        for e in m["effects"]:
            sc = self.scope(e["scope"])
            kwh, co2 = LinearEnergy.evaluate(sc["agg"], theta)
            kwh, co2 = kwh.sum(-1), co2.sum(-1)
            es, cs = float(e["energy_share"]), float(e["cost_share"])
            kwh_s = kwh_s + kwh * es
            co2_s = co2_s + co2 * es
            to, frm = e.get("relocate_to"), sc["from"]
            if to and frm and to != frm and frm in LOCATIONS and to in LOCATIONS:
                co2_s = co2_s + co2 * (1 - es) * (1 - np.asarray(theta[f"grid_{to}"]) / np.asarray(theta[f"grid_{frm}"]))
            cost_s += sc["cost"][cost_level] * cs
        return {"kwh": kwh_s, "co2_kg": co2_s, "cost_chf": cost_s}

    def evaluate(self, theta: dict, cost_level: str = "mid") -> dict:
        """Baseline, package savings and reductions for factor values (scalars or arrays of draws)."""
        kwh_b, co2_b = LinearEnergy.evaluate(self.total, theta)
        sav = [self.measure_savings(m, theta, cost_level) for m in self.measures]
        s = {k: sum(x[k] for x in sav) for k in ("kwh", "co2_kg", "cost_chf")}
        return {"baseline": {"kwh": kwh_b.sum(-1), "co2_kg": co2_b.sum(-1), "cost_chf": self.total_cost[cost_level],
                             "co2_by_location": {l: co2_b[..., i] for i, l in enumerate(LOCATIONS)}},
                "savings": s,
                # cost: the Calculator divides every level by the mid baseline cost
                "reduction": {"co2": s["co2_kg"] / co2_b.sum(-1), "cost": s["cost_chf"] / self.total_cost["mid"]}}

    def levels(self, scenario: str) -> dict[str, dict]:
        r = factor_ranges(scenario)
        return {lvl: self.evaluate(at_level(r, lvl), lvl) for lvl in LEVELS}

    def check(self, tol: float = 5e-4) -> None:
        """Must reproduce the package in measures.json for its recorded mix."""
        got = self.levels(self.scenario)
        bad = []
        # measures.json stores reductions as a contract Range (sorted low ≤ mid ≤ high); compare like with like
        for key in ("co2", "cost"):
            red = {lvl: float(got[lvl]["reduction"][key]) for lvl in LEVELS}
            mine = {"low": min(red.values()), "mid": red["mid"], "high": max(red.values())}
            for lvl in LEVELS:
                want = self.package["reduction"][key][lvl]
                if abs(mine[lvl] - want) > tol:
                    bad.append(f"{key} {lvl}: {mine[lvl]:.4f} vs measures.json {want:.4f}")
        for lvl in LEVELS:
            want = self.package["savings"]["co2_kg"][lvl]
            if abs(float(got[lvl]["savings"]["co2_kg"]) / want - 1) > tol:
                bad.append(f"co2 savings {lvl}: {float(got[lvl]['savings']['co2_kg']):.1f} vs {want:.1f}")
        if bad:
            raise AssertionError("package model differs from the advisor's Calculator: " + "; ".join(bad))
