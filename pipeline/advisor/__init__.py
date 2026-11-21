"""Steps 5–8: code-driven advisor with small parallel agents.

    python -m pipeline.run              # agents run only if their input changed (fingerprint), else reuse
    python -m pipeline.run --advisor    # force a fresh analysis (ticket reader + agents)
    python -m pipeline.run --offline    # never call an LLM (reuse the saved answers, even if outdated)

Flow (code runs the show; the LLM is called only where judgement is needed):
  facts.py      code  fact sheet: numbers with ids, no free text
  reader.py     LLM   ticket text → typed restrictions; parallel batches; quarantined (small model)
  toolbox.py    code  candidate measures from generic levers + «deliberately kept on»
  agents.py     LLM   one small agent per area, in parallel: calibrate candidates, add ideas
  plan.py       code  merge, savings, safety gate
  optimizer.py  code  optimal package per goal (climate first / best value / francs first, ± safety margin)
  apply.py      code  contract files, submission table, entity states

Same input ⇒ same answer: the agents' input is fingerprinted; while it does not change, the saved
answers (output/advisor/*.json, committed) are reused and no AI energy is spent.
planner.py is the previous single-call advisor, kept only for assistant/energy.py --advisor-estimate.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from types import SimpleNamespace

from ..energy.ai_footprint import footprint, usage_row
from ..harmonize.context import ROOT, Context
from . import agents as _agents
from . import apply as _apply
from . import facts as _facts
from . import plan as _plan
from . import reader

ADVISOR_DIR = ROOT / "output" / "advisor"
PIPELINE_VERSION = "fast-1"


class Metered:
    """Wraps the LLM client and records the token usage of every call of this run, so the energy of
    the tool's own AI use is reported with the results (list.append is thread-safe)."""

    def __init__(self, llm, model: str):
        self.llm, self.model, self.calls = llm, model, []

    def respond(self, **kw):
        t0 = time.time()
        resp = self.llm.respond(**kw)
        if getattr(resp, "usage", None) is not None:
            row = usage_row(kw.get("model") or self.model, kw.get("purpose", "advisor"), resp.usage)
            row["seconds"] = round(time.time() - t0, 1)
            self.calls.append(row)
        return resp


def _llm(ctx: Context) -> Metered:
    from assistant.llm import LLM               # shared OpenAI client (also logs tokens to usage_log)
    cfg = ctx.config["advisor"]
    return Metered(LLM(SimpleNamespace(chat_model=cfg["agent_model"], reasoning_effort=cfg["reasoning_effort"],
                                       usage_log=ROOT / cfg["usage_log"])), cfg["agent_model"])


def _have_key() -> bool:
    from assistant.settings import load_env
    load_env()
    return bool(os.environ.get("OPENAI_API_KEY"))


def _save(name: str, obj, directory=None) -> None:
    directory = ADVISOR_DIR if directory is None else directory
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / name, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, default=str)


def _load(name: str):
    p = ADVISOR_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _fp(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:16]


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


def run(ctx: Context, force: bool = False, offline: bool = False) -> None:
    """Fact sheet → (reader) → toolbox → (agents) → assemble → outputs. LLM steps only when needed."""
    cfg = ctx.config["advisor"]
    t_all = time.time()
    facts = _facts.build(ctx)
    _save("facts.json", facts, ctx.output_dir / "advisor")
    can_call = not offline and _have_key()
    llm, timings, reused = None, {}, {}

    # nothing saved and no LLM allowed: stop cleanly (the fact sheet is written)
    if not can_call and _load("reader_raw.json") is None:
        ctx.log("advisor", "advisor_missing", 0, "no saved analysis and no API key / --offline: advisor skipped", severity="warn")
        ctx.advisor = None
        return

    # 1. ticket reader (parallel batches): only if the tickets changed
    tickets, _ = reader.select_tickets(ctx)
    fp_reader = _fp(PIPELINE_VERSION, reader.INSTRUCTIONS, cfg["reader_model"], cfg["reader_batches"],
                    tickets[["ticket_id", "date", "type", "status", "resource_id", "title", "description", "text_risk"]]
                    .astype(str).values.tolist())
    raw_c = _load("reader_raw.json")
    if force or raw_c is None or raw_c.get("fingerprint") != fp_reader:
        if can_call:
            llm = _llm(ctx)
            t0 = time.time()
            raw_c = reader.read_tickets(ctx, llm, model=cfg["reader_model"], batches=int(cfg["reader_batches"]),
                                        effort=cfg["reasoning_effort"])
            timings["reader_s"] = round(time.time() - t0, 1)
            raw_c["fingerprint"] = fp_reader
            _save("reader_raw.json", raw_c)
            reused["reader"] = False
        elif raw_c is None:
            ctx.log("advisor", "advisor_missing", 0, "no saved ticket reading and no API key: advisor skipped", severity="warn")
            ctx.advisor = None
            return
        else:
            reused["reader"] = "outdated (no API key or --offline)"
            ctx.log("advisor", "advisor_outdated", 0, "tickets changed since the saved reading; reused it (no API key or --offline)",
                    severity="warn")
    else:
        reused["reader"] = True
    constraints = _constraints(ctx, raw_c)
    typed = _plan.typed_constraints(constraints)

    # 2. toolbox (code) and area agents (parallel): agents only if their input changed
    tb = _plan.toolbox(ctx, facts, constraints)
    from .calculator import Calculator
    calc0 = Calculator(ctx, facts, constraints)
    fp_agents = _fp(PIPELINE_VERSION, _agents.INSTRUCTIONS, cfg["agent_model"], cfg["reasoning_effort"],
                    _agents.inputs(tb["candidates"], facts, typed, calc0.scopes, calc0.resource_of))
    raw_p = _load("plan_raw.json")
    if force or raw_p is None or raw_p.get("fingerprint") != fp_agents or "reviews" not in raw_p:
        if can_call:
            llm = llm or _llm(ctx)
            from .calculator import Calculator
            calc = Calculator(ctx, facts, constraints)
            roles = sorted(ctx.tables["dim_resource"]["responsible_role"].dropna().unique().tolist())
            t0 = time.time()
            reviews = _agents.review(llm, tb["candidates"], facts, typed, calc.scopes, calc.resource_of, roles,
                                     cfg["agent_model"], cfg["reasoning_effort"])
            timings["agents_s"] = round(time.time() - t0, 1)
            raw_p = {"fingerprint": fp_agents, "reviews": reviews}
            reused["agents"] = False
        elif raw_p is None or "reviews" not in raw_p:
            ctx.log("advisor", "advisor_missing", 0, "no saved agent answers and no API key: advisor skipped", severity="warn")
            ctx.advisor = None
            return
        else:
            reused["agents"] = "outdated (no API key or --offline)"
            ctx.log("advisor", "advisor_outdated", 0, "data changed since the saved analysis; reused it (no API key or --offline)",
                    severity="warn")
    else:
        reused["agents"] = True

    if llm is not None and llm.calls:            # fresh analysis: record when, how long, how much AI
        prev = raw_p.get("analysis") or {}
        raw_p["analysis"] = {"analysed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                             "data_as_of": str(cfg["data_as_of"]), "seconds": round(time.time() - t_all, 1),
                             "timings": timings, "model": {"agents": cfg["agent_model"], "reader": cfg["reader_model"]}, "reasoning_effort": cfg["reasoning_effort"],
                             "ai_footprint": footprint(llm.calls, "measured during this run (token usage returned by the API)"),
                             "calls": llm.calls, "previous": {k: prev.get(k) for k in ("analysed_at", "seconds")} if prev else None}
        _save("plan_raw.json", raw_p)
    analysis = dict(raw_p.get("analysis") or {})
    analysis["reused"] = reused
    analysis["fingerprint"] = {"reader": fp_reader, "agents": fp_agents}
    assembled = _plan.assemble(ctx, facts, constraints, raw_p["reviews"])
    ctx.advisor = _apply.build(ctx, facts, constraints, raw_c, assembled, analysis)


def apply(ctx: Context) -> None:
    """Deterministic re-application of the saved answers (no LLM): kept for tests and the dev loader."""
    run(ctx, offline=True)


def export(ctx: Context) -> None:
    if getattr(ctx, "advisor", None):
        _apply.export(ctx)
