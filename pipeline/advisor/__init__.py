"""Steps 5–8 with an LLM advisor and system support.

    python -m pipeline.run --advisor   # calls the LLMs (reader + advisor), then applies
    python -m pipeline.run             # re-applies the last saved LLM answers (offline)

Flow:
  facts.py       code   → fact sheet (numbers with ids, no free text)
  reader.py      LLM    → ticket text → typed constraints (quarantined, can only restrict)
  planner.py     LLM    → findings, measures (as effects), package; revised until target and budget are met
  calculator.py  code   → savings (CHF, kWh, CO2), overlap check, safety gate, target/budget check
  apply.py       code   → findings.json, measures.json, limits.json, template_measures_package.csv, entity states

The raw LLM answers are saved in output/advisor/ (committed), so every later
run is deterministic and works without network or API key.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from ..harmonize.context import ROOT, Context
from . import apply as _apply
from . import facts as _facts
from . import planner, reader

ADVISOR_DIR = ROOT / "output" / "advisor"


def _llm(ctx: Context):
    from assistant.llm import LLM               # shared OpenAI client (logs tokens for «energy of our AI»)
    from assistant.settings import load_env
    load_env()
    cfg = ctx.config["advisor"]
    return LLM(SimpleNamespace(chat_model=cfg["model"], reasoning_effort=cfg["reasoning_effort"],
                               usage_log=ROOT / cfg["usage_log"]))


def _save(name: str, obj) -> None:
    ADVISOR_DIR.mkdir(parents=True, exist_ok=True)
    with open(ADVISOR_DIR / name, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, default=str)


def _load(name: str):
    p = ADVISOR_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def run_llm(ctx: Context) -> None:
    """Call the reader and the advisor; save their raw answers."""
    llm = _llm(ctx)
    raw_c = reader.read_tickets(ctx, llm)
    _save("reader_raw.json", raw_c)
    constraints = _constraints(ctx, raw_c)
    facts = _facts.build(ctx)
    result = planner.plan(ctx, llm, facts, constraints, max_rounds=int(ctx.config["advisor"]["max_rounds"]))
    _save("plan_raw.json", result)


def _constraints(ctx: Context, raw_c: dict) -> list[dict]:
    ok, rejected = reader.validate(ctx, raw_c)
    ctx.advisor_rejected_constraints = rejected
    ft = ctx.tables["free_text"]
    risk = ft[ft["source_file"] == "it_tickets.csv"].groupby("record_key")["text_risk"].agg(
        lambda s: "flagged" if (s == "flagged").any() else "ambiguous" if (s == "ambiguous").any()
        else "ok" if (s == "ok").all() else "unchecked")
    for c in ok:
        c["source_risk"] = risk.get(c["ticket_id"], "unchecked")
    sysc = reader.system_constraints(ctx, start=len(ok) + 1)
    for c in sysc:
        c["source_risk"] = "system"
    return ok + sysc


def apply(ctx: Context) -> None:
    """Deterministic: validate and compute the saved LLM answers, build outputs."""
    facts = _facts.build(ctx)
    _save("facts.json", facts)
    raw_c, raw_p = _load("reader_raw.json"), _load("plan_raw.json")
    if raw_c is None or raw_p is None:
        ctx.log("advisor", "advisor_missing", 0, "no saved LLM answers: run `python -m pipeline.run --advisor`",
                severity="warn")
        ctx.advisor = None
        return
    constraints = _constraints(ctx, raw_c)
    ctx.advisor = _apply.build(ctx, facts, constraints, raw_c, raw_p)


def export(ctx: Context) -> None:
    if getattr(ctx, "advisor", None):
        _apply.export(ctx)
