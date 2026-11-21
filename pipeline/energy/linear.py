"""The energy engine as a linear model: kWh and CO2 for ANY set of factor values.

Given the utilisation already observed on each billing line, the engine's kWh is
linear in every factor (engine.py):

    kWh_row = PUE_group × Σ_k a_k θ_k  +  Σ_j b_j φ_j
    CO2_row = kWh_row × grid[location]

  θ (infrastructure, × PUE): cpu_w_min, cpu_w_max, mem_w_per_gb, gpu_idle_w, storage, network, one
  φ (fully loaded, no PUE):  ai_token_wh, ai_message_wh, saas_kwh
  ("one" carries the GPU's 300-W × utilisation term, which has no uncertain factor)

The coefficients a, b are computed once from fact_cost. Any factor set, e.g. 10,000
Monte Carlo draws, is then a few matrix products. `check()` proves the model equals
the engine at low / mid / high.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import LEVELS, load_factors

PUE_PARAMS = ["cpu_w_min", "cpu_w_max", "mem_w_per_gb", "gpu_idle_w", "storage", "network", "one"]
FULL_PARAMS = ["ai_token_wh", "ai_message_wh", "saas_kwh"]
PUE_GROUPS = ["hyperscaler", "hoster", "none"]
LOCATIONS = ["CH", "DE", "IE", "EU"]
GRID_PARAMS = [f"grid_{l}" for l in LOCATIONS]
UNCERTAIN = [p for p in PUE_PARAMS if p != "one"] + FULL_PARAMS + ["pue_hyperscaler", "pue_hoster"] + GRID_PARAMS

LABELS = {
    "cpu_w_min": "CPU power at idle (W per vCPU)", "cpu_w_max": "CPU power at full load (W per vCPU)",
    "mem_w_per_gb": "Memory power (W per GB)", "gpu_idle_w": "GPU idle power (W)",
    "storage": "Storage energy (kWh per GB-day)", "network": "Network energy (kWh per GB)",
    "ai_token_wh": "AI energy (Wh per 1000 output tokens)", "ai_message_wh": "AI subscription energy (Wh per message)",
    "saas_kwh": "SaaS energy (kWh per active licence-month)", "pue_hyperscaler": "PUE Azure / AWS",
    "pue_hoster": "PUE Swiss hoster", "grid_CH": "Grid Zurich (kg CO2 per kWh)",
    "grid_DE": "Grid Frankfurt (kg CO2 per kWh)", "grid_IE": "Grid Dublin (kg CO2 per kWh)",
    "grid_EU": "Grid EU (AI and SaaS, kg CO2 per kWh)",
}


def factor_ranges(scenario: str, F: dict | None = None) -> dict[str, dict[str, float]]:
    """low / mid / high of every uncertain factor, from factors.yaml (Swiss grid of the scenario)."""
    F = F or load_factors()
    c, g = F["compute"], F["grid"]
    r = {"cpu_w_min": c["cpu_w_min"], "cpu_w_max": c["cpu_w_max"], "mem_w_per_gb": c["mem_w_per_gb"],
         "gpu_idle_w": F["gpu"]["idle_w"], "storage": F["storage"]["kwh_per_gb_day"],
         "network": F["network"]["kwh_per_gb"], "ai_token_wh": F["ai_tokens"]["wh_per_1000_output_tokens"],
         "ai_message_wh": F["ai_messages"]["wh_per_message"], "saas_kwh": F["saas"]["kwh_per_active_licence_month"],
         "pue_hyperscaler": F["pue"]["hyperscaler"], "pue_hoster": F["pue"]["hoster"]}
    for loc in LOCATIONS:
        r[f"grid_{loc}"] = g[loc]["variants"][scenario] if "variants" in g[loc] else g[loc]
    return {k: {lvl: float(v[lvl]) for lvl in LEVELS} for k, v in r.items()}


def at_level(ranges: dict, level: str) -> dict[str, float]:
    return {k: v[level] for k, v in ranges.items()}


class LinearEnergy:
    """Per-row coefficients of fact_cost; evaluate subsets of rows for any factor values."""

    def __init__(self, fc: pd.DataFrame, F: dict | None = None):
        F = F or load_factors()
        self.fc = fc
        sh, c = F["shapes"], F["compute"]
        q = fc["quantity"].fillna(0).astype(float).to_numpy()
        unit = fc["unit"].fillna("").to_numpy()
        u = fc["utilisation_cpu"].astype(float).to_numpy()
        ug = fc["utilisation_gpu"].astype(float).to_numpy()
        n = len(fc)
        A = np.zeros((n, len(PUE_PARAMS)))
        B = np.zeros((n, len(FULL_PARAMS)))
        P = {p: i for i, p in enumerate(PUE_PARAMS)}
        Q = {p: i for i, p in enumerate(FULL_PARAMS)}

        def cpu(mask, vcpu, util, mem_gb, per=1000.0):
            """vcpu × (Wmin (1 − u) + Wmax u) + mem × W/GB, in kWh per unit of q."""
            A[mask, P["cpu_w_min"]] += q[mask] * vcpu * (1 - util) / per
            A[mask, P["cpu_w_max"]] += q[mask] * vcpu * util / per
            A[mask, P["mem_w_per_gb"]] += q[mask] * mem_gb / per

        m = unit == "vCPU-hour"
        cpu(m, 1, u[m], sh["vcpu_mem_gb"])
        m = unit == "vCore-hour"
        cpu(m, 1, u[m], sh["vcore_mem_gb"])
        m = unit == "node-hour"
        cpu(m, sh["node"]["vcpu"], u[m], sh["node"]["ram_gb"])
        m = unit == "GPU-hour"
        g = F["gpu"]
        A[m, P["gpu_idle_w"]] += q[m] * (1 - ug[m]) / 1000
        A[m, P["one"]] += q[m] * g["tdp_w"] * ug[m] / 1000
        cpu(m, g["host"]["vcpu"], u[m], g["host"]["ram_gb"])
        m = unit == "capacity-day"
        pb = sh["powerbi_capacity"]
        cpu(m, pb["vcpu"] * 24, c["default_utilisation"], pb["ram_gb"] * 24)
        m = unit == "GB-day"
        A[m, P["storage"]] += q[m]
        m = unit == "GB"
        A[m, P["network"]] += q[m]
        m = unit == "runner-minute"
        cpu(m, sh["runner_vcpu"] / 60, sh["runner_utilisation"], sh["runner_vcpu"] / 60 * sh["vcpu_mem_gb"])

        # Fully loaded units: kWh is one factor × a row constant, so the constant = kWh_mid / factor_mid
        # (exact: the engine's token weights, small-model factor and message counts do not depend on the level).
        mid = at_level(factor_ranges("ch_consumption", F), "mid")
        kwh_mid = fc["kwh_mid"].fillna(0).to_numpy()
        tokens = (unit == "tokens") | (fc["charge_category"] == "Adjustment").to_numpy()
        B[tokens, Q["ai_token_wh"]] = kwh_mid[tokens] / mid["ai_token_wh"]
        m = unit == "seat-month"
        B[m, Q["ai_message_wh"]] = kwh_mid[m] / mid["ai_message_wh"]
        m = unit == "licence-month"
        B[m, Q["saas_kwh"]] = kwh_mid[m] / mid["saas_kwh"]

        credit = (fc["charge_category"] == "Credit").to_numpy()
        A[credit] = 0
        B[credit] = 0
        A[tokens] = 0                                  # adjustments: only the token factor (engine overwrites)
        self.A, self.B = A, B
        prov = fc["provider"].to_numpy()
        self.pue_group = np.where(np.isin(prov, ["Azure", "AWS"]), 0, np.where(prov == "Swiss hoster", 1, 2))
        loc = fc["location"].where(fc["location"].isin(LOCATIONS), "EU").to_numpy()   # engine: unknown → EU
        self.loc = np.array([LOCATIONS.index(x) for x in loc])

    # ------------------------------------------------------------ subsets
    def aggregate(self, mask) -> tuple[np.ndarray, np.ndarray]:
        """Coefficients of a row subset, summed per (PUE group, location): A (3, 4, K), B (4, J)."""
        mask = np.asarray(mask, dtype=bool)
        A = np.zeros((len(PUE_GROUPS), len(LOCATIONS), len(PUE_PARAMS)))
        B = np.zeros((len(LOCATIONS), len(FULL_PARAMS)))
        np.add.at(A, (self.pue_group[mask], self.loc[mask]), self.A[mask])
        np.add.at(B, self.loc[mask], self.B[mask])
        return A, B

    @staticmethod
    def evaluate(agg: tuple[np.ndarray, np.ndarray], theta: dict) -> tuple[np.ndarray, np.ndarray]:
        """kWh and CO2 per location for factor values theta (scalars or arrays of draws).
        Returns arrays shaped (..., 4 locations)."""
        A, B = agg
        # scalars (one factor set) and arrays (N draws) can be mixed: broadcast to a common shape
        names = PUE_PARAMS + FULL_PARAMS + ["pue_hyperscaler", "pue_hoster"] + [f"grid_{l}" for l in LOCATIONS]
        vals = dict(zip(names, np.broadcast_arrays(*[np.asarray(theta.get(p, 1.0), dtype=float) for p in names])))
        th = np.stack([vals[p] for p in PUE_PARAMS], axis=-1)
        ph = np.stack([vals[p] for p in FULL_PARAMS], axis=-1)
        pue = np.stack([vals["pue_hyperscaler"], vals["pue_hoster"], np.ones_like(vals["pue_hoster"])], axis=-1)
        it = np.einsum("glk,...k->...gl", A, th)                                          # (..., 3, 4)
        kwh = np.einsum("...gl,...g->...l", it, pue) + np.einsum("lj,...j->...l", B, ph)
        grid = np.stack([vals[f"grid_{l}"] for l in LOCATIONS], axis=-1)
        return kwh, kwh * grid


def check(fc: pd.DataFrame, scenario: str, tol: float = 1e-3) -> dict[str, float]:
    """Relative difference between the linear model and the engine's columns, per level (must be ~0)."""
    lin = LinearEnergy(fc)
    agg = lin.aggregate(np.ones(len(fc), bool))
    ranges = factor_ranges(scenario)
    out = {}
    for lvl in LEVELS:
        kwh, co2 = LinearEnergy.evaluate(agg, at_level(ranges, lvl))
        out[f"kwh_{lvl}"] = abs(kwh.sum() / fc[f"kwh_{lvl}"].sum() - 1)
        out[f"co2_{lvl}"] = abs(co2.sum() / fc[f"co2_kg_{lvl}"].sum() - 1)
    bad = {k: v for k, v in out.items() if v > tol}
    if bad:
        raise AssertionError(f"linear model differs from the energy engine: {bad}")
    return out
