"""Energy and CO2 of the tool's own LLM calls, reported with the results of each run.

When a user runs the analysis (ticket reader + advisor rounds), every call's token
usage is recorded and converted with the SAME factors we apply to the company's AI
use (factors.yaml → ai_tokens, EU grid):

    output-equivalent tokens = output (incl. reasoning) + 0.1 × uncached input + 0.01 × cached input
                               (× 0.25 for small models)
    kWh = eq / 1000 × Wh per 1000 tokens / 1000      CO2 = kWh × EU grid

Shared by the advisor and the chat assistant (any list of usage rows works).
"""
from __future__ import annotations

from .engine import load_factors

LEVELS = ("low", "mid", "high")


def usage_row(model: str, purpose: str, usage) -> dict:
    """Usage of one OpenAI Responses call (output_tokens already include reasoning tokens)."""
    cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    return {"model": model, "purpose": purpose, "input_tokens": int(usage.input_tokens),
            "cached_input_tokens": int(cached), "output_tokens": int(usage.output_tokens),
            "reasoning_tokens": int(reasoning)}


def footprint(calls: list[dict], source: str) -> dict:
    F = load_factors()
    a, grid = F["ai_tokens"], F["grid"]["EU"]
    eq = 0.0
    for c in calls:
        small = any(s in c["model"] for s in ("mini", "nano"))
        e = (c["output_tokens"] + a["input_weight"] * (c["input_tokens"] - c.get("cached_input_tokens", 0))
             + a["cached_weight"] * c.get("cached_input_tokens", 0))
        eq += e * (a["small_model_factor"] if small else 1)
    kwh = {l: eq / 1000 * a["wh_per_1000_output_tokens"][l] / 1000 for l in LEVELS}
    return {
        "calls": len(calls),
        "calls_by_purpose": {p: sum(1 for c in calls if c["purpose"] == p) for p in sorted({c["purpose"] for c in calls})},
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "cached_input_tokens": sum(c.get("cached_input_tokens", 0) for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "reasoning_tokens": sum(c.get("reasoning_tokens", 0) for c in calls),
        "output_equivalent_tokens": round(eq),
        "kwh": {l: round(v, 5) for l, v in kwh.items()},
        "co2_kg": {l: round(kwh[l] * grid[l], 6) for l in LEVELS},
        "formula": "eq = output (incl. reasoning) + 0.1 × uncached input + 0.01 × cached input (× 0.25 small models); "
                   "kWh = eq / 1000 × Wh per 1000 tokens (factors.yaml ai_tokens: 0.1 / 0.5 / 2.0); "
                   "CO2 = kWh × EU grid (0.150 / 0.213 / 0.300 kg/kWh)",
        "source": source,
        "models": sorted({c["model"] for c in calls}),
    }
