"""Step 9: replay selected, structured advisor effects on a copy of fact_cost."""
from __future__ import annotations

import duckdb
import pandas as pd

from ..energy.engine import load_factors
from ..harmonize.context import ROOT, Context
from ..harmonize.store import DATE_COLUMNS
from .common import read_output, write_json, write_table

TABLE = "fact_cost_optimized"
REPORT = "optimized_history.json"
LEVELS = ("low", "mid", "high")
COST_COLUMNS = ("amount_native", "amount_native_low", "amount_native_high",
                "cost_chf_low", "cost_chf", "cost_chf_high", "cost_eur", "cost_usd")


def replay(facts: pd.DataFrame, payload: dict | None, scenario: str) -> tuple[pd.DataFrame | None, dict]:
    report = {"status": "missing_package", "applied_measure_ids": [], "requires_confirmation": [], "skipped": []}
    if payload is None:
        return None, report

    grid = load_factors()["grid"]
    measures = {m["id"]: m for m in payload["measures"]}
    selected = list(dict.fromkeys(payload["package"]["measure_ids"]))
    recurring = ~facts["is_one_off"].eq(True)
    cost_columns = [column for column in COST_COLUMNS if column in facts]
    claimed = set()
    optimized = None

    # Open: replay srv:/lic:/ai: scopes when their row allocation is shared with the
    # advisor. Don't infer row effects from annual savings or measure descriptions.
    # Open: calendar windows and activation dates need a separate rollout simulation.
    # This history assumes supported measures were already in force.
    for measure_id in selected:
        measure = measures.get(measure_id)
        planned = []
        seen = set()
        if measure is None:
            reason = "Selected measure not found"
        elif measure["status"] not in ("ok", "human"):
            reason = f"Measure status is {measure['status']}"
        elif not measure.get("effects"):
            reason = "No structured effects"
        else:
            reason = None
            for effect in measure["effects"]:
                scope = effect["scope"]
                kind, _, resource = scope.partition(":")
                if kind != "res":
                    reason = f"Unsupported scope: {scope}"
                    break
                if resource in claimed or resource in seen:
                    reason = f"Overlapping resource effects: {scope}"
                    break
                rows = recurring & facts["resource_id"].eq(resource)
                if not rows.any():
                    reason = f"No recurring rows for {scope}"
                    break
                cost, energy = float(effect["cost_share"]), float(effect["energy_share"])
                destination = effect.get("relocate_to")
                if not (0 <= cost <= 1 and 0 <= energy <= 1):
                    reason = f"Invalid effect shares for {scope}"
                    break
                if destination and destination not in grid:
                    reason = f"Unknown grid location: {destination}"
                    break
                seen.add(resource)
                planned.append((rows, cost, energy, destination))
        if reason is not None:
            report["skipped"].append({"id": measure_id, "reason": reason})
            continue

        # A measure is applied atomically: a supported effect never masks an
        # unsupported effect from the same measure.
        if optimized is None:
            optimized = facts.copy()
            scaled = cost_columns + [f"{metric}_{level}" for level in LEVELS for metric in ("kwh", "co2_kg")]
            optimized[scaled] = optimized[scaled].astype(float)
        for rows, cost, energy, destination in planned:
            optimized.loc[rows, cost_columns] *= 1 - cost
            if destination:
                moved = rows & ~optimized["location"].eq(destination)
                optimized.loc[moved, "location"] = destination
                if "region" in optimized:
                    optimized.loc[moved, "region"] = None
            for level in LEVELS:
                kwh, co2 = f"kwh_{level}", f"co2_kg_{level}"
                optimized.loc[rows, kwh] *= 1 - energy
                if destination:
                    factors = grid[destination]
                    factor = factors["variants"][scenario][level] if "variants" in factors else factors[level]
                    optimized.loc[rows, co2] = optimized.loc[rows, kwh] * factor
                else:
                    optimized.loc[rows, co2] *= 1 - energy
        claimed.update(seen)
        report["applied_measure_ids"].append(measure_id)
        if measure["status"] == "human":
            report["requires_confirmation"].append(measure_id)

    report["status"] = ("no_supported_measures" if optimized is None else
                        "partial" if report["skipped"] else "complete")
    return optimized, report


def run(ctx: Context) -> None:
    payload = read_output(ctx, "measures.json")
    previous = read_output(ctx, REPORT)
    history, report = replay(ctx.tables["fact_cost"], payload, ctx.config["scenario"])
    if history is not None:
        for column in DATE_COLUMNS.intersection(history.columns):
            history[column] = pd.to_datetime(history[column]).dt.date
        write_table(ctx, TABLE, history)
    elif previous and previous["applied_measure_ids"] and TABLE in ctx.tables:
        # Standalone reruns load DuckDB before replay. Don't keep an obsolete
        # Step 9 output if its package has since been removed or replaced.
        with duckdb.connect(str(ROOT / ctx.config["duckdb_file"])) as con:
            con.execute(f'DROP TABLE IF EXISTS "{TABLE}"')
        ctx.tables.pop(TABLE, None)
    write_json(ctx, REPORT, report)
