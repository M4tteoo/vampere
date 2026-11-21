"""Deterministic assembly: toolbox candidates + agent reviews → measures → savings,
safety gate → optimal package for every goal. Pure code (re-run any time, instant)."""
from __future__ import annotations

from .agents import merge
from .calculator import Calculator
from .optimizer import GOALS, all_goals
from .toolbox import Toolbox

LEVER_TYPE = {"schedule": "schedule", "relocate": "relocate", "rightsize": "rightsize", "decommission": "decommission",
              "licence": "licence", "model_switch": "model_switch", "storage": "storage", "pipeline": "pipeline",
              "other": "other", "agent_idea": "other"}
WITHHELD_SUMMARY = "(summary withheld: source text not verified clean; use type, targets and schedule)"


def typed_constraints(constraints: list[dict]) -> list[dict]:
    """What the agents see of each constraint. The reader's one-line summary is included only when
    the source text was verified clean (or comes from a structured source); otherwise only the typed
    fields, so there is no text channel for injections."""
    return [{**{k: c[k] for k in ("id", "type", "applies_to", "schedule", "decided_by")},
             "summary": c["summary"] if c.get("source_risk") in ("ok", "system") else WITHHELD_SUMMARY}
            for c in constraints]


def toolbox(ctx, facts: dict, constraints: list[dict]) -> dict:
    return Toolbox(facts, constraints, str(ctx.config["advisor"]["data_as_of"])).run()


def evaluate(calc: Calculator, measures: list[dict]) -> tuple[list[dict], list[str]]:
    problems, out = [], []
    for m in measures:
        sav, probs, lines = calc.savings(m["effects"])
        status, reasons, limit_ids = calc.gate(m)
        problems += [f"{m['key']}: {p}" for p in probs]
        out.append({**m, "_savings": sav, "_lines": lines, "status": status, "gate_reasons": reasons, "limit_ids": limit_ids})
    return out, problems


def assemble(ctx, facts: dict, constraints: list[dict], reviews: dict) -> dict:
    cfg = ctx.config["advisor"]
    calc = Calculator(ctx, facts, constraints)
    tb = toolbox(ctx, facts, constraints)
    merged, notes = merge(tb["candidates"], reviews, None)
    # old «plan» schema expected by apply.build
    measures = [{**m, "type": LEVER_TYPE.get(m["lever"], "other"), "finding_keys": [m["finding"]] if m.get("finding") else [],
                 "effort_reasoning": "", "status_reason": "", "respects_constraints": m.get("respects_constraints", [])}
                for m in merged]
    evaluated, problems = evaluate(calc, measures)
    baseline = {"cost_chf": calc.tot["cost_chf"], **{f"co2_kg_{l}": calc.tot[f"co2_kg_{l}"] for l in ("low", "mid", "high")}}
    thresholds = {"co2": float(cfg["thresholds"]["co2"]), "cost": float(cfg["thresholds"]["cost"])}
    mc = None
    safety = cfg.get("safety") or {}
    if safety.get("method", "monte_carlo") == "monte_carlo":
        from .scenarios import Scenarios
        sc = Scenarios(ctx, facts)
        ms = safety.get("min_share_of_scenarios")
        mc = {"S": [sc.co2_savings(m["_lines"]) for m in evaluated], "B": sc.baseline_co2,
              "share": float(ms) if ms else None, "sample": int(safety.get("sample", 400))}
    packages = all_goals(evaluated, baseline, float(cfg["budget_chf"]), thresholds, calc.resource_of, mc=mc)
    default = cfg["goal"]
    chosen = packages[default]
    if chosen.get("safety_met") is False:
        notes.append(f"goal {default}: no package within the budget meets the safety rule ({chosen.get('safety_rule')})")
    plan = {"findings": tb["findings"], "measures": measures,
            "package": {"measure_keys": chosen["measure_keys"],
                        "reasoning": f"Optimal package for goal «{default}» chosen by the optimiser (code) among "
                                     f"{sum(1 for m in evaluated if m['status'] != 'blocked')} eligible measures."},
            "edge_cases": [{"measure_key": m["key"], "explanation": "; ".join(m["gate_reasons"]) or m["risks"]}
                           for m in evaluated if m["status"] == "blocked"]}
    live = None
    if mc is not None:                         # per-measure CO2 savings in the first N scenarios, for live safety in the UI
        nl = int(safety.get("live_scenarios", 1000))
        live = {"baseline_co2": [round(float(v), 1) for v in sc.baseline_co2[:nl]],
                "measures": {m["key"]: [round(float(v), 1) for v in sv[:nl]]
                             for m, sv in zip(evaluated, mc["S"]) if m["status"] != "blocked"}}
    return {"plan": plan, "packages": packages, "default_goal": default, "kept_on": tb["kept_on"],
            "notes": notes + problems, "goals": list(GOALS) + (["safest"] if "safest" in packages else []), "live": live}
