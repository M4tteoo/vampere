"""Answers to the case's example questions (data/case/example_questions.md),
computed from the harmonized tables. Written to output/answers.json."""
from __future__ import annotations

import json

import pandas as pd

from ..harmonize.context import Context
from ..harmonize.store import _meta


def q1_ai_seats(ctx: Context, month: str = "2026-08-01") -> dict:
    """How many AI subscription seats were purchased but not active in August
    2026, and what do they cost per month?"""
    s = ctx.tables["stg_ai_subscriptions"]
    s = s[s["month"] == month]   # Final versions only (Drafts dropped by the harmonizer)
    rate = ctx.tables["fx_monthly"].set_index("month").loc[month, "usd_chf"]
    rows = []
    for product, g in s.groupby("product"):
        purchased, active = int(g["licences_purchased"].sum()), int(g["licences_active_30d"].sum())
        price = float(g["price_per_seat"].iat[0])
        inactive = purchased - active
        rows.append({"product": product, "purchased": purchased, "active": active, "inactive": inactive,
                     "price_per_seat_usd": price, "inactive_cost_usd_per_month": inactive * price,
                     "inactive_cost_chf_per_month": round(inactive * price * rate, 2),
                     "by_cost_center": {int(r.cost_center): {"purchased": int(r.licences_purchased),
                                        "active": int(r.licences_active_30d)} for r in g.itertuples()}})
    tot = pd.DataFrame(rows)[["purchased", "active", "inactive", "inactive_cost_chf_per_month"]].sum()
    drafts = int(ctx.tables["stg_ai_subscriptions"].pipe(lambda d: (d["month"] == month) & d["is_draft"]).sum())
    return {
        "question": "How many AI subscription seats were purchased but not active in August 2026, and what do they cost per month?",
        "answer": (f"{int(tot.inactive)} of {int(tot.purchased)} AI seats were not active in August 2026, costing "
                   f"CHF {tot.inactive_cost_chf_per_month:,.2f} per month (USD → CHF at {rate}, the August 2026 ECB average)."),
        "table": rows,
        "sources": ["ai_subscriptions.csv (contract_status = Final; Draft rows next to Final versions dropped)",
                    "exchange_rates.csv (usd_chf, 2026-08)"],
        "calc": "inactive = licences_purchased − licences_active_30d; cost = inactive × price_per_seat (USD) × usd_chf of the month",
        "note": f"Draft rows for the same month and cost center ignored ({drafts} kept as Draft-only: none expected).",
    }


def write(ctx: Context) -> None:
    out = {"meta": _meta(ctx), "answers": {"q1_find": q1_ai_seats(ctx)}}
    with open(ctx.output_dir / "answers.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
