"""A2: project original and already-optimized histories with the same model.

Upstream provides a full counterfactual ``ctx.tables["fact_cost_optimized"]``
with the same schema, historical months and units as ``fact_cost`` (not a
delta table). Include unchanged resources and use explicit zero values if a
whole month becomes zero. Apply interventions and recompute CHF, kWh and
location-based CO2 ranges upstream, as if they were already in force.
Forecast never reads measures or subtracts savings. No table means ``with: null``.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from ..harmonize.context import Context
from .common import Calc, fill_baseline_row, read_output, rng, write_json
from .optimized_history import REPORT, TABLE as OPTIMIZED_HISTORY

METRICS = ("cost_chf", "kwh", "co2_kg")
COLUMNS = ("cost_chf_low", "cost_chf", "cost_chf_high",
           "kwh_low", "kwh_mid", "kwh_high", "co2_kg_low", "co2_kg_mid", "co2_kg_high")
SEAT_UNITS = {"seat-month", "licence-month"}


def _growth(table: pd.DataFrame, column: str, end: pd.Timestamp, cap: float) -> np.ndarray:
    monthly = table.groupby(pd.to_datetime(table["month"]))[column].sum().loc[:end].asfreq("MS")
    yoy = (monthly / monthly.shift(12) - 1).replace([np.inf, -np.inf], np.nan).dropna()
    if yoy.empty:
        raise ValueError(f"Forecast needs year-over-year observations for {column}")
    rates = yoy.quantile([0.25, 0.5, 0.75]).to_numpy()
    return rates * (cap / max(cap, np.abs(rates).max()))


def _format(values: np.ndarray, fx: dict[str, float]) -> dict:
    result = {key: rng(*values[i]) for i, key in enumerate(METRICS)}
    for code, rate in fx.items():
        result[f"cost_{code.lower()}"] = rng(*(values[0] / rate))
    return result


def _seasonality(facts: pd.DataFrame) -> dict[int, float]:
    gpu = facts.loc[facts["resource_id"].eq("gpu-ml")]
    monthly = gpu.groupby("month")["kwh_mid"].sum()
    positive = monthly[monthly.gt(0)]
    if positive.index.month.nunique() != 12:
        return {}
    profile = positive.groupby(positive.index.month).median()
    return (profile / profile.mean()).clip(0.9, 1.1).to_dict()


def _prepare_history(ctx: Context, table: str, first: pd.Timestamp, fx: dict[str, float]) -> tuple[dict, dict, dict]:
    source = ctx.tables[table]
    required = {*COLUMNS, "month", "is_one_off", "currency_native", "fx_rate_chf", "resource_id",
                "category", "location", "provider", "unit", "source_file", "value_status"}
    if missing := required - set(source.columns):
        raise ValueError(f"{table}: missing forecast columns: {', '.join(sorted(missing))}")
    end = first - pd.offsets.MonthBegin()
    start = first - pd.offsets.MonthBegin(3)
    dates = pd.to_datetime(source["month"])
    facts = source.loc[dates.le(end) & ~source["is_one_off"].eq(True)].copy()
    facts["month"] = dates.loc[facts.index]
    recent = facts.loc[facts["month"].ge(start)].copy()
    if table == OPTIMIZED_HISTORY:
        missing_months = pd.date_range(start, end, freq="MS").difference(recent["month"])
        if len(missing_months):
            raise ValueError(f"{table}: missing recurring history for {', '.join(missing_months.strftime('%Y-%m'))}")
    if recent.empty:
        raise ValueError(f"{table}: no recurring cost rows in the three months before the forecast")

    # M365 and Copilot prices changed in July. Use only post-change costs for those seats.
    repriced = recent["resource_id"].isin(["saas-m365", "sub-copilot"])
    recent = recent.loc[~repriced | recent["month"].ge(pd.Timestamp("2026-07-01"))].copy()
    currency_scale = recent["currency_native"].map({"CHF": 1.0, **fx}) / recent["fx_rate_chf"]
    recent[list(COLUMNS[:3])] = recent[list(COLUMNS[:3])].mul(currency_scale.fillna(1), axis=0)
    season = _seasonality(facts)
    seasonal_scale = recent["month"].dt.month.map(season).fillna(1).where(recent["resource_id"].eq("gpu-ml"), 1)
    recent[list(COLUMNS)] = recent[list(COLUMNS)].div(seasonal_scale, axis=0)
    groups = ["resource_id", "category", "location", "provider", "unit"]
    sums = recent.groupby(groups, dropna=False)[list(COLUMNS)].sum()
    rates = {}
    for key, values in sums.iterrows():
        divisor = 2 if key[0] in {"saas-m365", "sub-copilot"} and first == pd.Timestamp("2026-09-01") else 3
        rates[key] = values.to_numpy().reshape(3, 3) / divisor
    calc = Calc(ctx, recent)
    calculations = {
        "total": calc(recent, "Sum of forecast category values before rounding", note=f"Historical input: {table}."),
        "by_category": {category: calc(group, "Recurring monthly run-rate x growth x seasonal factor x dated change",
                                      note=f"Historical input: {table}.")
                        for category, group in recent.groupby("category")},
    }
    return rates, season, calculations


def _project(rates: dict, season: dict, seats: np.ndarray, ai: np.ndarray, month: pd.Timestamp,
             years: float, month_fraction: float) -> tuple[dict, dict]:
    categories = defaultdict(lambda: np.zeros((3, 3)))
    resources = defaultdict(lambda: np.zeros((3, 3)))
    for (resource, category, location, _, unit), run_rate in rates.items():
        growth = seats if unit in SEAT_UNITS else ai if unit == "tokens" else 0
        values = run_rate * (1 + growth) ** years
        if resource == "gpu-ml":
            values *= season.get(month.month, 1)
        if resource == "dp-prod" and month >= pd.Timestamp("2026-10-01"):
            values *= 24 / 20
        if resource == "sub-copilot" and month >= pd.Timestamp("2027-01-01"):
            values[0] *= 21 / 18
        if location in {"DE", "IE"}:
            values[2, 0] *= 0.97 ** years
        categories[category] += values * month_fraction
        resources[(resource, category)] += values * month_fraction
    return categories, resources


def build_forecast(ctx: Context) -> dict:
    baseline = ctx.config["baseline"]
    first = pd.Timestamp(baseline["end"]).to_period("M").to_timestamp() + pd.offsets.MonthBegin()
    end = first - pd.offsets.MonthBegin()
    fx_table = ctx.tables["fx_monthly"]
    fx_months = pd.to_datetime(fx_table["month"])
    fx = {code: float(fx_table.loc[fx_months.between(pd.Timestamp(baseline["start"]), end), f"{code.lower()}_chf"].mean())
          for code in ("EUR", "USD")}
    if any(not np.isfinite(rate) or rate <= 0 for rate in fx.values()):
        raise ValueError("Forecast requires positive baseline-average CHF rates for EUR and USD")

    original_rates, original_season, original_calcs = _prepare_history(ctx, "fact_cost", first, fx)
    optimized = _prepare_history(ctx, OPTIMIZED_HISTORY, first, fx) if OPTIMIZED_HISTORY in ctx.tables else None
    seats = _growth(ctx.tables["alloc_headcount"], "fte", end, 0.15)
    ai = _growth(ctx.tables["stg_ai_usage"], "tokens_total", end, 0.30)
    events = [
        {"date": "2026-07-01", "resource_id": "saas-m365", "label": "Microsoft 365: USD 12.50 to USD 14 (already in run-rate)",
         "source": "data/case/README.md"},
        {"date": "2026-10-01", "resource_id": "dp-prod", "label": "Production data platform: 20 to 24 nodes", "source": "T-1261"},
        {"date": "2027-01-01", "resource_id": "sub-copilot", "label": "Copilot Business: USD 18 to USD 21",
         "source": "data/case/README.md"},
    ]
    months = []
    end_exclusive = first + pd.Timedelta(weeks=52)
    zero = np.zeros((3, 3))
    for step, month in enumerate(pd.date_range(first, end_exclusive, freq="MS", inclusive="left")):
        month_end = min(month + pd.offsets.MonthBegin(), end_exclusive)
        month_fraction = (month_end - month).days / month.days_in_month
        years = step / 12
        without, without_res = _project(original_rates, original_season, seats, ai, month, years, month_fraction)
        with_, with_res = (_project(optimized[0], optimized[1], seats, ai, month, years, month_fraction)
                           if optimized else (None, None))
        categories = without.keys() | (with_.keys() if with_ is not None else set())
        resources = without_res.keys() | (with_res.keys() if with_res is not None else set())
        months.append({
            "month": month.date().isoformat(),
            "without": _format(sum(without.values(), zero), fx),
            "with": _format(sum(with_.values(), zero), fx) if with_ is not None else None,
            "by_category": {cat: {"without": _format(without.get(cat, zero), fx),
                                  "with": _format(with_.get(cat, zero), fx) if with_ is not None else None}
                            for cat in sorted(categories)},
            "by_resource": {resource: {"category": category,
                                       "without": _format(without_res.get((resource, category), zero), fx),
                                       "with": _format(with_res.get((resource, category), zero), fx)
                                       if with_res is not None else None}
                            for resource, category in sorted(resources, key=str)},
        })

    return {
        "horizon": {"start": first.date().isoformat(), "end_exclusive": end_exclusive.date().isoformat()},
        "months": months, "events": events,
        "calculations": {"without": original_calcs, "with": optimized[2] if optimized else None},
        "assumptions": [
            {"id": "run_rate", "source": "fact_cost and fact_cost_optimized (if provided)",
             "method": "Each scenario uses its own last three complete recurring months; M365 and Copilot use July-August post-change rates."},
            {"id": "seat_growth", "source": "extra/headcount.csv", "unit": "percent/year",
             "value": rng(*(100 * seats)), "method": "25th/50th/75th percentiles of monthly year-over-year FTE growth; scaled together if any exceed +/-15%."},
            {"id": "token_growth", "source": "ai_usage.csv", "unit": "percent/year",
             "value": rng(*(100 * ai)), "method": "25th/50th/75th percentiles of monthly year-over-year token growth; scaled together if any exceed +/-30% for a multi-year projection."},
            *({"id": f"seasonality_{scenario}", "source": f"{table} (gpu-ml)", "unit": "multiplier",
               "method": "Positive GPU kWh calendar-month medians normalized by their mean, limited to 0.9-1.1. Other workloads are flat apart from growth and known changes.",
               "by_month": {str(month): rng(value, value, value, nd=4) for month, value in profile.items()}}
              for scenario, table, profile in (
                  ("without", "fact_cost", original_season),
                  ("with", OPTIMIZED_HISTORY, optimized[1] if optimized else None),
              ) if profile is not None),
            {"id": "grid", "source": "pipeline/energy/factors.yaml", "unit": "percent/year",
             "value": rng(-3, 0, 0), "method": "Illustrative DE/IE decarbonisation in the low case only; all other factors held fixed."},
            *({"id": f"fx_{code.lower()}", "source": "exchange_rates.csv", "unit": f"CHF/{code}",
               "value": rng(rate, rate, rate, nd=6), "method": "Fixed average of the baseline-period monthly rates."}
              for code, rate in fx.items()),
        ],
    }


def run(ctx: Context) -> None:
    forecast = build_forecast(ctx)
    if OPTIMIZED_HISTORY in ctx.tables and (report := read_output(ctx, REPORT)) and report["applied_measure_ids"]:
        forecast["optimized_history"] = {key: value for key, value in report.items() if key != "meta"}
    write_json(ctx, "forecast.json", forecast)
    growth = next(a for a in forecast["assumptions"] if a["id"] == "seat_growth")
    if (ctx.output_dir / "submission" / "template_baseline_and_assumptions.csv").exists():
        fill_baseline_row(ctx, "growth_per_year", **growth["value"], source=growth["source"],
                          calculation=f"Seat-based forecast driver. {growth['method']} AI token growth is separate in forecast.json.")
