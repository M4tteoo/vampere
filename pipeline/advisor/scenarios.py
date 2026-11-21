"""Monte Carlo scenarios for the optimiser's safety rule: «−40 % CO2 in at least 90 % of scenarios».

Uses the SAME building blocks and the SAME draws as the Monte Carlo panel (pipeline/bonus/montecarlo.py):
the linear energy model (pipeline/energy/linear.py), the scope resolution (pipeline/bonus/scope_rows.py),
triangular draws of every uncertain factor with the same seed. So the probability the optimiser
guarantees is the one the panel reports for the chosen package.
"""
from __future__ import annotations

import numpy as np

from ..bonus.montecarlo import N_DRAWS, SEED, _triangular
from ..bonus.scope_rows import ScopeRows
from ..energy.linear import LOCATIONS, UNCERTAIN, LinearEnergy, factor_ranges
from ..harmonize.context import Context


class Scenarios:
    def __init__(self, ctx: Context, facts: dict, n: int = N_DRAWS, seed: int = SEED):
        fc = ctx.tables["fact_cost"]
        self.base = fc[fc["in_baseline"]].reset_index(drop=True)
        self.lin = LinearEnergy(self.base)
        self.rows = ScopeRows(self.base, facts, ctx.tables["stg_ai_usage"])
        self.rec = self.rows.recurring.to_numpy()
        ranges = factor_ranges(ctx.config.get("scenario", "ch_consumption"))
        gen = np.random.default_rng(seed)
        self.theta = {p: _triangular(gen, ranges[p], n) for p in UNCERTAIN}      # identical to the panel's draws
        _, co2 = LinearEnergy.evaluate(self.lin.aggregate(np.ones(len(self.base), bool)), self.theta)
        self.baseline_co2 = co2.sum(-1)                                          # (n,)
        self._cache: dict[str, tuple] = {}

    def _scope(self, scope: str):
        if scope not in self._cache:
            rows, k = self.rows.resolve(scope)
            mask = rows.to_numpy()
            A, B = self.lin.aggregate(mask)
            _, co2 = LinearEnergy.evaluate((A * k, B * k), self.theta)
            rid = self.rows.servers.get(scope) if scope.startswith("srv:") else scope.partition(":")[2].split(":")[0]
            locs = self.base.loc[self.rec & (self.base["resource_id"] == rid).to_numpy(), "location"].dropna()
            self._cache[scope] = (co2.sum(-1), locs.mode().iat[0] if len(locs) else None)
        return self._cache[scope]

    def co2_savings(self, lines: list[dict]) -> np.ndarray:
        """CO2 saved by a measure in every scenario (same rule as the Calculator and the panel)."""
        s = np.zeros_like(self.baseline_co2)
        for e in lines:
            co2, frm = self._scope(e["scope"])
            es = float(e["energy_share"])
            s = s + co2 * es
            to = e.get("relocate_to")
            if to and frm and to != frm and frm in LOCATIONS and to in LOCATIONS:
                s = s + co2 * (1 - es) * (1 - self.theta[f"grid_{to}"] / self.theta[f"grid_{frm}"])
        return s
