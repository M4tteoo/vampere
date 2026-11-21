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
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..energy.engine import LEVELS
from ..energy.linear import LOCATIONS, LinearEnergy, at_level, factor_ranges
from ..harmonize.context import Context
from .common import read_output

COST = {"low": "cost_chf_low", "mid": "cost_chf", "high": "cost_chf_high"}


class PackageModel:
    def __init__(self, ctx: Context):
        mf = read_output(ctx, "measures.json")
        facts = read_output(ctx, "advisor/facts.json")
        if not mf or not facts:
            raise FileNotFoundError("measures.json / advisor/facts.json missing: run the pipeline with the advisor answers")
        fc = ctx.tables["fact_cost"]
        self.base = fc[fc["in_baseline"]].reset_index(drop=True)
        self.lin = LinearEnergy(self.base)
        self.rec = ~self.base["is_one_off"].fillna(False).astype(bool).to_numpy()
        self.total = self.lin.aggregate(np.ones(len(self.base), bool))
        self.total_cost = {lvl: float(self.base[COST[lvl]].sum()) for lvl in LEVELS}

        srv = pd.DataFrame(facts["servers"]).set_index("id")
        self.srv_res = srv["resource"].to_dict()
        self.srv_share = {s: facts["facts"].get(f"{s}.share_of_resource", {}).get("value", 0) for s in srv.index}
        ai = ctx.tables["stg_ai_usage"].set_index("source_row")[["task_type", "model_class"]]
        gw = (self.base["source_file"] == "ai_usage.csv").to_numpy()
        self.task = np.where(gw, self.base["source_row"].map(ai["task_type"]).to_numpy(), None)
        self.mclass = np.where(gw, self.base["source_row"].map(ai["model_class"]).to_numpy(), None)

        self.measures = [m for m in mf["measures"] if m["in_package"] and m["status"] != "blocked"]
        self.all_measures = mf["measures"]
        self.package = mf["package"]
        self.scenario = mf["meta"]["scenario"]
        self._scopes: dict[str, dict] = {}

    # ----------------------------------------------------------- scopes
    def _rows(self, scope: str) -> tuple[np.ndarray, float]:
        """(mask over baseline rows, scale) of a scope's recurring baseline, as Calculator.base()."""
        kind, _, rest = scope.partition(":")
        b = self.base
        if kind == "res":
            return self.rec & (b["resource_id"] == rest).to_numpy(), 1.0
        if kind == "srv":
            return self.rec & (b["resource_id"] == self.srv_res[scope]).to_numpy(), float(self.srv_share.get(scope, 0))
        if kind == "lic":
            return self.rec & b["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"]).to_numpy() \
                & (b["tool"] == rest).to_numpy(), 1.0
        if kind == "ai":
            rid, task, mc = rest.split(":")
            return self.rec & (b["resource_id"] == rid).to_numpy() & (self.task == task) & (self.mclass == mc), 1.0
        return np.zeros(len(b), bool), 0.0

    def scope(self, scope: str) -> dict:
        if scope not in self._scopes:
            mask, k = self._rows(scope)
            A, B = self.lin.aggregate(mask)
            rid = self.srv_res.get(scope) if scope.startswith("srv:") else scope.partition(":")[2].split(":")[0]
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
        for lvl in LEVELS:
            for key, want in (("co2", self.package["reduction"]["co2"][lvl]), ("cost", self.package["reduction"]["cost"][lvl])):
                if abs(float(got[lvl]["reduction"][key]) - want) > tol:
                    bad.append(f"{key} {lvl}: {float(got[lvl]['reduction'][key]):.4f} vs measures.json {want:.4f}")
            want = self.package["savings"]["co2_kg"][lvl]
            if abs(float(got[lvl]["savings"]["co2_kg"]) / want - 1) > tol:
                bad.append(f"co2 savings {lvl}: {float(got[lvl]['savings']['co2_kg']):.1f} vs {want:.1f}")
        if bad:
            raise AssertionError("package model differs from the advisor's Calculator: " + "; ".join(bad))
