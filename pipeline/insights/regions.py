"""Where else could it run? (extra/data_center_locations.csv)

The catalogue lists every region each provider offers and whether the SME uses it.
Code uses it for:
  - relocation options per resource: CO2 change if the load ran in another region of
    the SAME provider (only locations with a researched grid factor: CH, DE, IE, EU);
  - a safety rule for the advisor: a measure may only relocate a load to a location its
    provider offers (checked in pipeline/advisor/calculator.py);
  - unused regions in the scene (e.g. AWS Zurich: available, not used).
Price differences between regions are only known for AWS compute (README: m6i.large
Zurich 0.1265 vs Ireland 0.107 USD/h); elsewhere they are «not in the data».
"""
from __future__ import annotations

import pandas as pd

from ..energy.linear import factor_ranges
from ..harmonize.context import Context
from .common import Insight, card, recurring

SOURCE = "extra/data_center_locations.csv"
AWS_PRICE_USD_H = {"CH": 0.1265, "IE": 0.107}       # README «Real and synthetic data», m6i.large, as of 07.11.2026
GRID_LOCATIONS = ("CH", "DE", "IE", "EU")


def provider_key(provider: str | None) -> str | None:
    """Billing provider names → catalogue provider names (lower case)."""
    if not isinstance(provider, str):
        return None
    p = provider.lower()
    if p in ("azure", "aws", "swiss hoster"):
        return p
    if p in ("openai", "anthropic", "azure openai", "vendor a1"):
        return "ai provider (api)"
    return p


def offered(ctx: Context) -> dict[str, dict]:
    """{provider: {"locations": [codes], "used": [codes], "regions": [...]}} from the catalogue."""
    reg = ctx.tables["dim_region"]
    out: dict[str, dict] = {}
    for p, g in reg.groupby(reg["provider"].str.lower()):
        out[p] = {"locations": sorted(g["location_code"].dropna().unique().tolist()),
                  "used": sorted(g.loc[g["used_by_sme"] == "yes", "location_code"].dropna().unique().tolist()),
                  "regions": [{"region": x.region, "location": x.location_code, "used": x.used_by_sme == "yes"}
                              for x in g.itertuples()]}
    return out


def compute(ctx: Context) -> Insight:
    off = offered(ctx)
    grid = factor_ranges(ctx.config.get("scenario", "ch_consumption"))
    rec = recurring(ctx)
    rows = rec[rec["kwh_mid"] > 0]
    options, facts = [], []
    for rid, g in rows.groupby("resource_id"):
        prov = provider_key(g["provider"].mode().iat[0] if g["provider"].notna().any() else None)
        here = g["location"].mode().iat[0] if g["location"].notna().any() else None
        if prov not in off or here not in GRID_LOCATIONS:
            continue
        for loc in off[prov]["locations"]:
            if loc == here:
                continue
            if loc not in GRID_LOCATIONS:
                options.append({"resource_id": rid, "provider": prov, "from": here, "to": loc, "co2_kg_saved": None,
                                "note": "no researched grid factor for this location"})
                continue
            saved = {lvl: float((g[f"kwh_{lvl}"] * (grid[f"grid_{here}"][lvl] - grid[f"grid_{loc}"][lvl])).sum())
                     for lvl in ("low", "mid", "high")}
            cost_note = "price difference not in the data"
            compute = g["unit"].isin(["vCPU-hour", "runner-minute"]).any()    # the README price is for compute only
            if prov == "aws" and compute and loc in AWS_PRICE_USD_H and here in AWS_PRICE_USD_H:
                cost_note = (f"AWS compute in {loc} costs {AWS_PRICE_USD_H[loc] / AWS_PRICE_USD_H[here] - 1:+.0%} "
                             f"vs {here} (m6i.large list price, README)")
            lo, hi = min(saved.values()), max(saved.values())
            options.append({"resource_id": rid, "entity_id": f"res:{rid}", "provider": prov, "from": here, "to": loc,
                            "kwh": round(float(g["kwh_mid"].sum()), 1),
                            "co2_kg_saved": {"low": round(lo, 1), "mid": round(saved["mid"], 1), "high": round(hi, 1)},
                            "cost_note": cost_note})
            if saved["mid"] > 1:
                facts.append((f"{rid}.co2_saved_if_moved_to_{loc}", saved["mid"], "kg CO2/year",
                              f"{rid}: CO2 saved per year if its load ran in {loc} ({prov} offers it); {cost_note}",
                              SOURCE))
    options.sort(key=lambda o: -((o["co2_kg_saved"] or {}).get("mid") or 0))
    unused = [{"provider": p, **r} for p, v in off.items() for r in v["regions"] if not r["used"]]
    best = next((o for o in options if o["co2_kg_saved"]), None)
    c = card(
        "regions", "Where else could it run?", [SOURCE, "factors.yaml"],
        (f"{len(unused)} regions of our providers are available but unused (e.g. AWS Zurich). "
         + (f"Largest single gain: {best['resource_id']} {best['from']} → {best['to']}, "
            f"{best['co2_kg_saved']['mid']:,.0f} kg CO2 a year." if best else "")),
        [("regions offered by our providers", sum(len(v["regions"]) for v in off.values()), "regions"),
         ("regions used", sum(len(v["used"]) for v in off.values()), "locations"),
         ("relocation options with a CO2 gain", sum(1 for o in options if (o["co2_kg_saved"] or {}).get("mid", 0) > 0), "options")],
        formula="CO2 saved = recurring kWh × (grid at today's location − grid at the other location of the same provider)",
        row_count=int(len(rows)), entity_ids=sorted({o["entity_id"] for o in options if "entity_id" in o}),
        fact_ids=[f[0] for f in facts[:10]])
    c["safety_rule"] = "The advisor may only relocate a load to a location its provider offers (checked by code)."
    return Insight(c, facts, {"offered": off, "options": options, "unused_regions": unused})
