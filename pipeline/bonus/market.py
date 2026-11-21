"""A3: a parallel market-based estimate, without unverified supplier credits."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ..energy.engine import load_factors
from ..export.frontend import MARKET_SUMS
from ..harmonize.context import Context
from .common import MEASURES_TEMPLATE, fill_baseline_row, patch_template, read_output, rng, write_json

LEVELS = ("low", "mid", "high")
NOTE = (
    "Same estimated kWh as location-based; no verified supplier instruments credited. "
    "AIB 2025 factors are used across the full baseline period. DE/IE use residual mixes, "
    "EU is an attribute-mix proxy, and CH uses the Swiss consumption mix regardless of the location-based scenario. "
    "AIB measures direct generation CO2; the location-based factors and CH proxy use life-cycle estimates. "
    "The figures are not strictly comparable and their difference is not a physical emission saving."
)


def _factors() -> dict:
    with Path(__file__).with_name("market_factors.yaml").open(encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    swiss = load_factors()["grid"]["CH"]
    aib = config["aib"]
    factors = {}
    for location, entry in config["locations"].items():
        if "g_co2_per_kwh" in entry:
            point = entry["g_co2_per_kwh"] / 1000
            value = rng(point, point, point, nd=5)
            source = aib
        else:
            value = swiss["variants"]["ch_consumption"]
            source = {"source": swiss["source"], "factor_id": swiss["template"], "aib_residual_mix": aib["source"]}
        factors[location] = {"basis": entry["basis"], "kg_per_kwh": value,
                             "calculation": entry["calculation"], "source": source}
    return factors


def _enrich(facts: pd.DataFrame, factors: dict) -> pd.DataFrame:
    unknown = ~facts["location"].isin(factors)
    if unknown.any():
        locations = facts.loc[unknown, "location"].fillna("(missing)").unique()
        raise ValueError(f"No A3 factor for location(s): {', '.join(map(str, locations))}")
    columns = {
        column: facts[f"kwh_{level}"] * facts["location"].map({loc: f["kg_per_kwh"][level] for loc, f in factors.items()})
        for column, level in zip(MARKET_SUMS, LEVELS)
    }
    return facts.assign(**columns)


def after_energy(ctx: Context) -> None:
    ctx.tables["fact_cost"] = _enrich(ctx.tables["fact_cost"], _factors())


def _totals(rows: pd.DataFrame, factors: dict) -> dict:
    def total(metric: str, data: pd.DataFrame = rows) -> dict:
        return rng(*(data[f"{metric}_{level}"].sum() for level in LEVELS))

    basis = rows["location"].map({loc: f["basis"] for loc, f in factors.items()})
    locations = sorted(rows["location"].unique().tolist())
    return {
        "kwh": total("kwh"), "co2_kg": total("co2_kg"), "co2_kg_market": total("co2_kg_market"),
        "market_basis_kwh": {key: total("kwh", rows.loc[idx]) for key, idx in basis.groupby(basis).groups.items()},
        "calc": {"formula": "sum(kWh × factor by location)", "inputs": [], "factor_ids": locations,
                 "source_files": sorted(rows["source_file"].dropna().unique().tolist()), "row_count": len(rows),
                 "value_status": "estimated", "issue_ids": []},
    }


def _measure_savings(measure: dict, recurring: pd.DataFrame, factors: dict) -> dict:
    def unavailable(reason: str) -> dict:
        return {"co2_kg_market": None, "reason": reason}

    if measure["status"] not in ("ok", "human"):
        return unavailable(f"Measure status is {measure['status']}")
    if not measure.get("effects"):
        return unavailable("No structured effects")

    low = mid = high = 0.0
    seen = set()
    locations = set()
    selected_rows = []
    for effect in measure["effects"]:
        scope = effect["scope"]
        kind, _, resource = scope.partition(":")
        if kind != "res":
            return unavailable(f"Unsupported scope: {scope}")
        if resource in seen:
            return unavailable(f"Overlapping effects: {scope}")
        seen.add(resource)
        rows = recurring[recurring["resource_id"].eq(resource)]
        if rows.empty:
            return unavailable(f"No recurring baseline rows for {scope}")
        selected_rows.append(rows)
        energy, to = float(effect["energy_share"]), effect.get("relocate_to")
        if not 0 <= energy <= 1 or (to and to not in factors):
            return unavailable(f"Invalid energy share or destination for {scope}")

        for origin, group in rows.groupby("location"):
            locations.update((origin, to or origin))
            before = factors[origin]["kg_per_kwh"]
            if not to or to == origin:
                delta_lo, delta_mid, delta_hi = (before[key] * energy for key in LEVELS)
            else:
                after = factors[to]["kg_per_kwh"]
                delta_lo = before["low"] - (1 - energy) * after["high"]
                delta_mid = before["mid"] - (1 - energy) * after["mid"]
                delta_hi = before["high"] - (1 - energy) * after["low"]
            kwh_lo, kwh_mid, kwh_hi = (group[f"kwh_{key}"].sum() for key in LEVELS)
            low += min(kwh_lo * delta_lo, kwh_hi * delta_lo)
            mid += kwh_mid * delta_mid
            high += max(kwh_lo * delta_hi, kwh_hi * delta_hi)
    return {
        "co2_kg_market": rng(low, mid, high), "reason": None,
        "calc": {"formula": "recurring kWh × (origin factor − remaining energy share × destination factor)",
                 "inputs": [], "factor_ids": sorted(locations), "value_status": "estimated", "issue_ids": [],
                 "source_files": sorted({src for rows in selected_rows for src in rows["source_file"].dropna()}),
                 "row_count": sum(map(len, selected_rows))},
    }


def run(ctx: Context) -> None:
    factors = _factors()
    facts = ctx.tables["fact_cost"]
    baseline = _enrich(facts[facts["in_baseline"]], factors)
    recurring = baseline[~baseline["is_one_off"].eq(True)]
    measures = (read_output(ctx, "measures.json") or {}).get("measures", [])
    savings = {m["id"]: _measure_savings(m, recurring, factors) for m in measures}
    totals = _totals(baseline, factors)
    source = "AIB 2025 (DE/IE residual mix, EU attribute proxy); Swiss consumption mix proxy (CH)"
    co2 = totals["co2_kg_market"]
    fill_baseline_row(ctx, "total_co2_market_based_baseline_year_kg", **co2, source=source,
                      calculation="Sum of kWh × factor by location (same kWh as location-based). " + NOTE)
    intensity = {}
    for key in LEVELS:
        kwh = baseline[f"kwh_{key}"].sum()
        intensity[key] = baseline[f"co2_kg_market_{key}"].sum() / kwh if kwh else None
    available = [value for value in intensity.values() if value is not None]
    fill_baseline_row(ctx, "grid_mix_market_based", low=min(available, default=None), mid=intensity["mid"],
                      high=max(available, default=None), source=source,
                      calculation="Baseline kWh-weighted portfolio factor; range spans the three baseline cases.")
    if any(m["in_package"] for m in measures):
        patch_template(ctx, MEASURES_TEMPLATE, "measure_id", {
            m["id"]: {"savings_co2_kg_market_based": (savings[m["id"]]["co2_kg_market"] or {}).get("mid")}
            for m in measures if m["in_package"]
        })
    write_json(ctx, "market.json", {
        "note": NOTE, "scope2_guidance": "https://ghgprotocol.org/scope-2-guidance",
        "factors": factors, "baseline": totals, "measure_savings": savings,
        "by_provider": [{"provider": None if pd.isna(provider) else provider, **_totals(rows, factors)}
                        for provider, rows in baseline.groupby("provider", dropna=False)],
    })
