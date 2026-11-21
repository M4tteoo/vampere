"""Shared helpers for the insight modules: baseline sums per resource, potentials
(share of a resource's recurring baseline), cards and advisor facts.

Every number here is computed by code from the harmonized tables. Potentials are
upper bounds «if acted on»; they are NOT additive with the advisor's package (the
advisor decides which measures to build, the Calculator computes their savings).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..export.frontend import SUMS, metrics
from ..harmonize.context import Context

COST_COLS = ["cost_chf_low", "cost_chf", "cost_chf_high", "cost_eur", "cost_usd"]
ENERGY_COLS = ["kwh_low", "kwh_mid", "kwh_high", "co2_kg_low", "co2_kg_mid", "co2_kg_high"]


def baseline(ctx: Context) -> pd.DataFrame:
    fc = ctx.tables["fact_cost"]
    return fc[fc["in_baseline"]]


def recurring(ctx: Context) -> pd.DataFrame:
    b = baseline(ctx)
    return b[~b["is_one_off"].eq(True)]


def sums(rows: pd.DataFrame) -> pd.Series:
    return rows[SUMS].sum()


def resource_sums(ctx: Context, resource_id: str) -> pd.Series:
    rec = recurring(ctx)
    return sums(rec[rec["resource_id"] == resource_id])


def potential(base: pd.Series, cost_share: float, energy_share: float) -> dict:
    """Contract Metrics of a share of a baseline (costs × cost_share, energy and CO2 × energy_share)."""
    s = base.copy()
    s[COST_COLS] = s[COST_COLS] * cost_share
    s[ENERGY_COLS] = s[ENERGY_COLS] * energy_share
    return metrics(s)


def role(ctx: Context, resource_id: str) -> str | None:
    d = ctx.tables["dim_resource"].set_index("resource_id")
    return d.at[resource_id, "responsible_role"] if resource_id in d.index else None


def fte_hours_month() -> float:
    """Working hours of one FTE per month (Swiss 42-hour week × 52 / 12)."""
    return 42 * 52 / 12


@dataclass
class Insight:
    """One topic: a card for the dashboard / assistant and facts for the advisor."""
    card: dict
    facts: list[tuple] = field(default_factory=list)     # (id, value, unit, statement, source)
    extra: dict = field(default_factory=dict)            # detail tables for the UI (reports, options, projects…)


def card(cid: str, title: str, sources: list[str], headline: str, numbers: list[tuple], *,
         potential_: dict | None = None, action: str | None = None, status: str | None = None,
         decided_by: str | None = None, protected: list[str] = (), entity_ids: list[str] = (),
         formula: str = "", row_count: int = 0, fact_ids: list[str] = ()) -> dict:
    return {
        "id": cid, "title": title, "source_files": sources, "headline": headline,
        "numbers": [{"label": l, "value": (round(float(v), 4) if isinstance(v, float) else v), "unit": u}
                    for l, v, u in numbers],
        "potential": None if potential_ is None else {
            "action": action, "metrics": potential_, "status": status, "decided_by": decided_by,
            "note": "upper bound if acted on; not additive with the package (the advisor decides, code computes)"},
        "protected": list(protected), "entity_ids": list(entity_ids), "advisor_fact_ids": list(fact_ids),
        "calc": {"formula": formula, "inputs": [], "factor_ids": [], "source_files": sources,
                 "row_count": int(row_count), "value_status": "estimated" if potential_ else "observed", "issue_ids": []},
    }
