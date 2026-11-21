"""Energy and CO2 of our own AI use («Teams that use AI also estimate its energy use», case.md).

    .venv/bin/python -m assistant energy                          # this machine's log
    .venv/bin/python -m assistant energy other/usage.jsonl ...    # + logs copied from teammates
    .venv/bin/python -m assistant energy --advisor-estimate       # + the saved advisor run, rebuilt from output/advisor/

Same factors as the case (pipeline/energy/factors.yaml → ai_tokens):
  output-equivalent tokens = output + 0.1 × (input − cached) + 0.01 × cached   (× 0.25 for small models)
  kWh = eq / 1000 × Wh per 1000 (low / mid / high) / 1000 ;  CO2 = kWh × 0.213 kg/kWh (EU mix, provider location unknown)
Coding assistants used while building are not logged here: add them from each tool's usage page.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .settings import ROOT

FACTORS = ROOT / "pipeline" / "energy" / "factors.yaml"
GRID_EU = {"low": 0.150, "mid": 0.213, "high": 0.300}     # factors.yaml grid EU
LEVELS = ("low", "mid", "high")
# Reasoning tokens are billed as output but not saved with the answer: assumed range × visible output.
REASONING_FACTOR = {"low": 0.5, "mid": 1.5, "high": 3.0}
CACHE_SHARE = {"low": 0.5, "mid": 0.3, "high": 0.0}       # share of repeated input served from cache


def _ai() -> dict:
    with open(FACTORS, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["ai_tokens"]


def _eq(inp: float, cached: float, out: float, small: bool, F: dict) -> float:
    return (out + F["input_weight"] * (inp - cached) + F["cached_weight"] * cached) * (F["small_model_factor"] if small else 1)


def from_logs(paths: list[Path]) -> dict:
    """Sum logged calls (one JSON line per call, as written by assistant/llm.py)."""
    F = _ai()
    rows = []
    for p in paths:
        rows += [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    eq = sum(_eq(r["input_tokens"], r.get("cached_input_tokens", 0), r["output_tokens"],
                 "mini" in r["model"] or "nano" in r["model"], F) for r in rows)
    by = {}
    for r in rows:
        by[r["purpose"].split(".")[0]] = by.get(r["purpose"].split(".")[0], 0) + 1
    return {"source": [str(p) for p in paths], "calls": len(rows), "calls_by_purpose": by,
            "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
            "eq_tokens": {l: eq for l in LEVELS}}


def advisor_estimate() -> dict:
    """Rebuild the prompts of the saved advisor run (reader + planning rounds) and count tokens."""
    import tiktoken

    from pipeline.advisor import ADVISOR_DIR, _constraints, facts as Fm, planner, reader
    from pipeline.advisor.calculator import Calculator
    from pipeline.bonus.dev import load_context

    enc = tiktoken.get_encoding("o200k_base")
    n = lambda s: len(enc.encode(s))  # noqa: E731
    ctx = load_context()
    raw_c = json.loads((ADVISOR_DIR / "reader_raw.json").read_text(encoding="utf-8"))
    raw_p = json.loads((ADVISOR_DIR / "plan_raw.json").read_text(encoding="utf-8"))

    tickets, _ = reader.select_tickets(ctx)
    allowed = sorted(ctx.tables["dim_resource"]["resource_id"].tolist()
                     + [f"srv:{s}" for s in ctx.tables["dim_server"]["server_id"]])
    roles = sorted(ctx.tables["dim_resource"]["responsible_role"].dropna().unique().tolist())
    body = "\n".join(json.dumps({"ticket_id": r.ticket_id, "date": r.date, "type": r.type, "status": r.status,
                                 "resource_id": r.resource_id if isinstance(r.resource_id, str) else None,
                                 "text_risk": r.text_risk, "untrusted_title": r.title,
                                 "untrusted_description": r.description}, ensure_ascii=False)
                     for r in tickets.itertuples())
    calls = [(n(reader.INSTRUCTIONS) + n(json.dumps(reader._schema(allowed, roles)))
              + n(f"Allowed ids for applies_to: {', '.join(allowed)}\n\n<tickets>\n{body}\n</tickets>"),
              n(json.dumps({k: raw_c[k] for k in ("constraints", "ignored")}, ensure_ascii=False)))]

    facts = Fm.build(ctx)
    cons = _constraints(ctx, raw_c)
    calc = Calculator(ctx, facts, cons)
    lines = "\n".join(f"{k} = {v['value']} {v['unit']} · {v['statement']}" for k, v in facts["facts"].items())
    rest = {k: v for k, v in facts.items() if k != "facts"}
    for r in rest["resources"]:
        r.pop("facts", None)
    content = ("FACTS (id = value unit · meaning)\n" + lines + "\n\nENTITIES\n" + json.dumps(rest, ensure_ascii=False, default=str)
               + "\n\nCONSTRAINTS\n" + json.dumps(planner.typed_constraints(cons), ensure_ascii=False)
               + "\n\nSCOPES\n" + ", ".join(calc.scopes))
    schema = planner._schema(calc.scopes, roles, [c["id"] for c in cons], [r["id"] for r in facts["resources"]])
    fixed = n(planner.INSTRUCTIONS) + n(content) + n(json.dumps(schema))
    out = n(json.dumps(raw_p["plan"], ensure_ascii=False))
    feedback = 1200  # tokens of one feedback message (code's results per measure)
    calls += [(fixed + k * (out + feedback), out) for k in range(len(raw_p["rounds"]))]

    F = _ai()
    tin, tout = sum(i for i, _ in calls), sum(o for _, o in calls)
    eq = {l: _eq(tin, tin * CACHE_SHARE[l], tout * (1 + REASONING_FACTOR[l]), False, F) for l in LEVELS}
    return {"source": "output/advisor/ (saved final run, prompts rebuilt by code, tokenizer o200k_base)",
            "calls": len(calls), "calls_by_purpose": {"advisor": len(calls)}, "input_tokens": tin,
            "output_tokens": tout, "eq_tokens": eq,
            "note": "Only the saved final run; reasoning tokens assumed 0.5–3× the visible output. "
                    "Development runs of the advisor are in the log of the machine that ran them."}


def energy(parts: list[dict]) -> dict:
    F = _ai()
    eq = {l: sum(p["eq_tokens"][l] for p in parts) for l in LEVELS}
    kwh = {l: eq[l] / 1000 * F["wh_per_1000_output_tokens"][l] / 1000 for l in LEVELS}
    return {"parts": parts, "eq_tokens": {l: round(v) for l, v in eq.items()},
            "wh": {l: round(kwh[l] * 1000, 1) for l in LEVELS},
            "co2_g": {l: round(kwh[l] * GRID_EU[l] * 1000, 1) for l in LEVELS},
            "formula": "eq = output + 0.1 × (input − cached) + 0.01 × cached (× 0.25 small models); "
                       "Wh = eq / 1000 × Wh per 1000 tokens (factors.yaml ai_tokens); CO2 = kWh × EU grid (0.150–0.300)",
            "not_included": "coding assistants used while building (add from each tool's usage page)"}
