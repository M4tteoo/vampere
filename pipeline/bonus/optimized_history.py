"""Step 9: replay selected, structured advisor effects on a copy of fact_cost."""
from __future__ import annotations

import duckdb
import pandas as pd

from ..energy.engine import load_factors
from ..export.frontend import MARKET_SUMS
from ..harmonize.context import ROOT, Context
from ..harmonize.store import DATE_COLUMNS
from .common import read_output, write_json, write_table
from .scope_rows import ScopeRows

TABLE = "fact_cost_optimized"
REPORT = "optimized_history.json"
LEVELS = ("low", "mid", "high")
COST_COLUMNS = ("amount_native", "amount_native_low", "amount_native_high",
                "cost_chf_low", "cost_chf", "cost_chf_high", "cost_eur", "cost_usd")


def replay(facts: pd.DataFrame, payload: dict | None, scenario: str, *,
           advisor_facts: dict | None = None, ai_usage: pd.DataFrame | None = None) -> tuple[pd.DataFrame | None, dict]:
    report = {"status": "missing_package", "applied_measure_ids": [], "requires_confirmation": [], "skipped": []}
    if payload is None:
        return None, report

    grid = load_factors()["grid"]
    measures = {m["id"]: m for m in payload["measures"]}
    selected = list(dict.fromkeys(payload["package"]["measure_ids"]))
    allocations = ScopeRows(facts, advisor_facts, ai_usage)
    cost_columns = [column for column in COST_COLUMNS if column in facts]
    claimed: set[str] = set()
    allocated = pd.Series(0.0, index=facts.index)
    optimized = None

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
            proposed = allocated.copy()
            for effect in measure["effects"]:
                scope = effect["scope"]
                try:
                    rows, share = allocations.resolve(scope)
                except ValueError as exc:
                    reason = str(exc)
                    break
                if not rows.any():
                    reason = f"No recurring rows for {scope}"
                    break
                if scope in claimed or scope in seen or (proposed.loc[rows] + share > 1 + 1e-9).any():
                    reason = f"Overlapping effects: {scope}"
                    break
                cost, energy = float(effect["cost_share"]), float(effect["energy_share"])
                destination = effect.get("relocate_to")
                if not (0 <= cost <= 1 and 0 <= energy <= 1):
                    reason = f"Invalid effect shares for {scope}"
                    break
                if destination and destination not in grid:
                    reason = f"Unknown grid location: {destination}"
                    break
                if destination and not scope.startswith("res:"):
                    reason = f"Relocation requires a whole resource: {scope}"
                    break
                seen.add(scope)
                proposed.loc[rows] += share
                planned.append((rows, cost * share, energy * share, destination))
        if reason is not None:
            report["skipped"].append({"id": measure_id, "reason": reason})
            continue

        # A measure is applied atomically: a supported effect never masks an
        # unsupported effect from the same measure.
        if optimized is None:
            # A2 replays location-based emissions only; don't carry stale A3 values.
            optimized = facts.drop(columns=MARKET_SUMS, errors="ignore")
            scaled = cost_columns + [f"{metric}_{level}" for level in LEVELS for metric in ("kwh", "co2_kg")]
            optimized[scaled] = optimized[scaled].astype(float)
        # Distinct servers on a shared bill each remove a share of the original rows.
        for rows, cost, energy, destination in planned:
            optimized.loc[rows, cost_columns] -= facts.loc[rows, cost_columns] * cost
            if destination:
                moved = rows & ~optimized["location"].eq(destination)
                optimized.loc[moved, "location"] = destination
                if "region" in optimized:
                    optimized.loc[moved, "region"] = None
            for level in LEVELS:
                kwh, co2 = f"kwh_{level}", f"co2_kg_{level}"
                optimized.loc[rows, kwh] -= facts.loc[rows, kwh] * energy
                if destination:
                    factors = grid[destination]
                    factor = factors["variants"][scenario][level] if "variants" in factors else factors[level]
                    optimized.loc[rows, co2] = optimized.loc[rows, kwh] * factor
                else:
                    optimized.loc[rows, co2] -= facts.loc[rows, co2] * energy
        claimed.update(seen)
        allocated = proposed
        report["applied_measure_ids"].append(measure_id)
        if measure["status"] == "human":
            report["requires_confirmation"].append(measure_id)

    report["status"] = ("no_supported_measures" if optimized is None else
                        "partial" if report["skipped"] else "complete")
    return optimized, report


def replay_packages(ctx: Context, payload: dict | None) -> dict[str, dict]:
    """Replay every goal package of measures.json (climate_first, best_value, francs_first, safest).

    Returns {goal: {"feasible", "history", "report", "measure_ids", "same_as"}}. Goals whose package holds
    the same measures share one replay; `same_as` names the first goal with that exact measure set."""
    results: dict[str, dict] = {}
    if not payload or not payload.get("packages"):
        return results
    default = payload["package"].get("goal")
    goals = sorted(payload["packages"], key=lambda goal: goal != default)
    solved: dict[tuple, tuple[str, pd.DataFrame | None, dict]] = {}
    for goal in goals:
        package = payload["packages"][goal]
        if package.get("feasible") is False:
            results[goal] = {"feasible": False, "note": package.get("note", ""), "measure_ids": []}
            continue
        ids = list(dict.fromkeys(package["measure_ids"]))
        key = tuple(sorted(ids))
        same_as = solved[key][0] if key in solved else None
        if same_as is None:
            history, report = replay(ctx.tables["fact_cost"], {**payload, "package": {**package, "measure_ids": ids}},
                                     ctx.config["scenario"], advisor_facts=read_output(ctx, "advisor/facts.json"),
                                     ai_usage=ctx.tables.get("stg_ai_usage"))
            solved[key] = (goal, history, report)
        _, history, report = solved[key]
        results[goal] = {"feasible": True, "history": history, "report": report, "measure_ids": ids,
                         "same_as": same_as}
    return results


def run(ctx: Context) -> None:
    payload = read_output(ctx, "measures.json")
    previous = read_output(ctx, REPORT)
    history, report = replay(ctx.tables["fact_cost"], payload, ctx.config["scenario"],
                             advisor_facts=read_output(ctx, "advisor/facts.json"),
                             ai_usage=ctx.tables.get("stg_ai_usage"))
    if payload is not None:
        report["goal"] = payload["package"].get("goal")
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
