"""B2 · Swiss mix switch: everything under the Swiss consumption mix (our choice, incl.
imports, 0.110) AND the production mix (0.030), and proof that the package holds in both.

No second pipeline run is needed: CO2 is kWh × the grid factor of each line's location,
so only the Swiss lines change. Baseline and package come from the linear model
(pipeline/energy/linear.py, checked against the engine) and the package model
(package_eval.py, checked against measures.json). The measures are the SAME as in
measures.json (the package is chosen once, under our consumption mix); only their
CO2 is re-valued.

Output: output/scenarios.json (contract ScenariosFile). The scene can recolour
from `entities_co2_kg` (production mix); the consumption values are entities.json.
For the full file set under the production mix: python -m pipeline.run --scenario
ch_production --out output/ch_production.
"""
from __future__ import annotations

from ..energy.engine import LEVELS
from ..energy.linear import LOCATIONS, check as check_linear, factor_ranges
from ..harmonize.context import Context
from .common import read_output, rng, write_json
from .package_eval import PackageModel

SCENARIOS = ("ch_consumption", "ch_production")
TARGET = {"co2": 0.40, "cost": 0.25}


def _sorted(d: dict, nd: int = 4) -> dict:
    """Range with low ≤ mid ≤ high (low factors give the HIGHER reduction, so sort explicitly)."""
    lo, hi = min(d.values()), max(d.values())
    return rng(lo, d["mid"], hi, nd=nd)


def _scenario(pm: PackageModel, sc: str) -> dict:
    L = pm.levels(sc)
    red = {k: {lvl: float(L[lvl]["reduction"][k]) for lvl in LEVELS} for k in ("co2", "cost")}
    r = factor_ranges(sc)
    measures = []
    for m in pm.all_measures:
        co2 = {lvl: float(pm.measure_savings(m, {k: v[lvl] for k, v in r.items()}, lvl)["co2_kg"]) for lvl in LEVELS}
        measures.append({"id": m["id"], "title": m["title"], "status": m["status"], "in_package": m["in_package"],
                         "co2_kg": rng(*co2.values(), nd=1)})
    return {
        "grid_ch": rng(*r["grid_CH"].values(), nd=3),
        "baseline": {"kwh": rng(*(float(L[l]["baseline"]["kwh"]) for l in LEVELS), nd=1),
                     "co2_kg": rng(*(float(L[l]["baseline"]["co2_kg"]) for l in LEVELS), nd=1),
                     "co2_by_location": {loc: rng(*(float(L[l]["baseline"]["co2_by_location"][loc]) for l in LEVELS), nd=1)
                                         for loc in LOCATIONS}},
        "package": {"measure_ids": pm.package["measure_ids"],
                    "savings_co2_kg": rng(*(float(L[l]["savings"]["co2_kg"]) for l in LEVELS), nd=1),
                    "reduction": {k: _sorted(v) for k, v in red.items()},
                    "meets": {"co2": red["co2"]["mid"] >= TARGET["co2"], "cost": red["cost"]["mid"] >= TARGET["cost"],
                              "budget": bool(pm.package["meets"]["budget"])},
                    "meets_at_low": {k: min(v.values()) >= TARGET[k] for k, v in red.items()}},
        "measures": measures,
    }


def _entities_production(ctx: Context) -> dict[str, dict]:
    """CO2 of every scene object under the production mix. Swiss lines scale by the factor ratio;
    rooms are split by their flows to the locations (summary.json); other locations are unchanged."""
    cons, prod = factor_ranges("ch_consumption")["grid_CH"], factor_ranges("ch_production")["grid_CH"]
    ratio = {lvl: prod[lvl] / cons[lvl] for lvl in LEVELS}
    ents = (read_output(ctx, "entities.json") or {}).get("entities", [])
    flows = (read_output(ctx, "summary.json") or {}).get("flows", [])
    out = {}
    for e in ents:
        co2 = e["metrics"].get("co2_kg")
        if not co2:
            continue
        if e["kind"] == "room":
            fl = [f for f in flows if f["from"] == e["id"] and f["metrics"].get("co2_kg")]
            vals = {lvl: sum(f["metrics"]["co2_kg"][lvl] * (ratio[lvl] if f["to"] == "loc:CH" else 1) for f in fl)
                    for lvl in LEVELS} if fl else co2
        else:
            k = ratio if e.get("location") == "CH" else {lvl: 1.0 for lvl in LEVELS}
            vals = {lvl: co2[lvl] * k[lvl] for lvl in LEVELS}
        out[e["id"]] = rng(*vals.values(), nd=1)
    return out


def run(ctx: Context) -> None:
    b = ctx.tables["fact_cost"]
    check_linear(b[b["in_baseline"]].reset_index(drop=True), ctx.config.get("scenario", "ch_consumption"))
    pm = PackageModel(ctx)
    pm.check()
    res = {sc: _scenario(pm, sc) for sc in SCENARIOS}
    c, p = res["ch_consumption"]["package"], res["ch_production"]["package"]
    holds = all(c["meets"].values()) and all(p["meets"].values())
    conclusion = (
        f"The package ({', '.join(pm.package['measure_ids'])}) reaches −{c['reduction']['co2']['mid']:.1%} CO2 with the "
        f"consumption mix and −{p['reduction']['co2']['mid']:.1%} with the production mix; cost −{c['reduction']['cost']['mid']:.1%} "
        f"in both (CO2 factors do not change francs). "
        + ("It meets the target under both Swiss mixes. " if holds else "It does NOT meet the target under both mixes. ")
        + f"Over the full factor range: {'meets' if c['meets_at_low']['co2'] else 'misses'} −40 % at the least favourable "
          f"factors with the consumption mix, {'meets' if p['meets_at_low']['co2'] else 'misses'} with the production mix.")
    calc = {
        "formula": "CO2 = Σ lines kWh × grid factor of the line's location; Swiss lines × (production / consumption factor). "
                   "Package savings re-valued with the advisor's rules (share of each scope + relocation term) on the "
                   "same measures; reduction = savings / actual baseline",
        "inputs": [{"name": "grid CH consumption (mid)", "value": res["ch_consumption"]["grid_ch"]["mid"], "unit": "kg CO2/kWh",
                    "source": "factors.yaml"},
                   {"name": "grid CH production (mid)", "value": res["ch_production"]["grid_ch"]["mid"], "unit": "kg CO2/kWh",
                    "source": "factors.yaml variants"}],
        "factor_ids": ["grid_mix_location_based_switzerland"], "source_files": ["fact_cost", "measures.json"],
        "row_count": int(len(pm.base)), "value_status": "estimated", "issue_ids": [],
        "note": "Checked: linear model = energy engine, package model = measures.json (consumption mix, all levels).",
    }
    write_json(ctx, "scenarios.json", {"default": "ch_consumption", "scenarios": res, "holds_in_both": holds,
                                       "conclusion": conclusion, "entities_co2_kg_production": _entities_production(ctx),
                                       "calc": calc})
