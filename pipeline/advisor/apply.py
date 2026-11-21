"""Turn the saved LLM answers into the contract files (all numbers by code)."""
from __future__ import annotations

import csv
import json

import numpy as np
import pandas as pd

from ..export.frontend import SUMS, Calc, metrics
from ..harmonize.context import Context
from ..harmonize.store import _meta
from .calculator import PERSON_DAY_CHF, Calculator
from .plan import evaluate as _eval_measures

TZ = "Europe/Zurich"


# ------------------------------------------------------------- helpers
def _entity_ids(ctx: Context, scope: str) -> list[str]:
    kind, _, rest = scope.partition(":")
    if kind == "res" and not ctx.tables["fact_cost"]["resource_id"].eq(rest).any():
        # not billed itself (e.g. Power BI report pbi-07): point to the billed resource it runs on
        pbi = ctx.tables.get("stg_powerbi_usage")
        host = pbi.loc[pbi["report_id"] == rest, "resource_id"].dropna() if pbi is not None else []
        return [f"res:{host.iat[0]}"] if len(host) else []
    if kind in ("res", "srv"):
        return [scope]
    if kind == "ai":
        return [f"res:{rest.split(':')[0]}"]
    if kind == "lic":
        fc = ctx.tables["fact_cost"]
        deps = fc[(fc["tool"] == rest) & fc["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"])]["department"].dropna().unique()
        return [f"lic:{rest}@{d}" for d in sorted(deps)]
    return []


def _occurrences(schedule: dict, start: pd.Timestamp, months: int = 12) -> list[dict]:
    end = start + pd.DateOffset(months=months)
    k = schedule.get("kind")
    out = []
    iso = lambda t: t.tz_localize(TZ).isoformat()

    def hm(v, default):
        v = v or default
        h, m = v.split(":")
        return pd.Timedelta(hours=int(h), minutes=int(m))
    if k == "monthly_last_workdays":
        n = schedule.get("days") or 3
        for m0 in pd.date_range(start.replace(day=1), end, freq="MS"):
            wd = pd.bdate_range(m0, m0 + pd.offsets.MonthEnd(0))
            if len(wd) < n:
                continue
            a = wd[-n]
            b = wd[-1] + pd.Timedelta(days=1) + hm(schedule.get("until_time"), "00:00")
            if a >= start:
                out.append({"start": iso(a), "end": iso(b)})
    elif k == "quarter_days":
        n = schedule.get("days") or 3
        for y in (start.year, start.year + 1):
            for mo in (1, 4, 7, 10):
                a = pd.Timestamp(year=y, month=mo, day=1)
                if start <= a <= end:
                    out.append({"start": iso(a), "end": iso(a + pd.Timedelta(days=n))})
    elif k == "date_range" and schedule.get("start_date"):
        a = pd.Timestamp(schedule["start_date"])
        b = pd.Timestamp(schedule.get("end_date") or schedule["start_date"]) + pd.Timedelta(days=1)
        out.append({"start": iso(a), "end": iso(b)})
    elif k == "daily" and schedule.get("from_time"):
        for d in pd.date_range(start, periods=7, freq="D"):
            a = d + hm(schedule["from_time"], "00:00")
            b = d + hm(schedule.get("until_time"), "23:59")
            if b <= a:
                b += pd.Timedelta(days=1)
            out.append({"start": iso(a), "end": iso(b)})
    return out


def _period_text(s: dict) -> str:
    k = s.get("kind")
    t = (f" from {s['from_time']}" if s.get("from_time") else "") + (f" until {s['until_time']}" if s.get("until_time") else "")
    return {"always": "always", "monthly_last_workdays": f"last {s.get('days') or 3} working days of every month{t}",
            "quarter_days": f"days 1–{s.get('days') or 3} of January, April, July and October",
            "date_range": f"{s.get('start_date')} – {s.get('end_date') or s.get('start_date')}",
            "daily": f"every day{t} (next 7 days shown)", "none": "see summary"}.get(k, "see summary")


# --------------------------------------------------------------- build
def _package(calc, measures, keys, mkey, reasoning, edge_cases) -> dict:
    pkg = calc.evaluate(measures, keys)
    return {"measure_ids": [mkey[k] for k in pkg["measure_keys"]], "effort_days": pkg["effort_days"],
            "effort_chf": pkg["effort_chf"], "savings": metrics(pkg["savings"]),
            # contract Range: low ≤ mid ≤ high (low factors give the HIGHER reduction, so sort)
            "reduction": {k: {"low": round(min(r.values()), 4), "mid": round(r["mid"], 4), "high": round(max(r.values()), 4)}
                          for k, r in pkg["reduction"].items()},
            "meets": pkg["meets"], "meets_at_low": pkg["meets_at_low"], "reasoning": reasoning,
            "edge_cases": edge_cases}, pkg


def build(ctx: Context, facts: dict, constraints: list[dict], raw_c: dict, assembled: dict, analysis: dict) -> dict:
    plan = assembled["plan"]
    calc = Calculator(ctx, facts, constraints)
    measures, problems = _eval_measures(calc, plan["measures"])
    problems += assembled["notes"]
    pkg = calc.evaluate(measures, plan["package"]["measure_keys"])
    cfacts = facts["facts"]
    tot = calc.tot
    calcf = Calc(ctx, ctx.tables["fact_cost"])
    sev = ctx.config["advisor"]["severity"]
    asof = pd.Timestamp(str(ctx.config["advisor"]["data_as_of"])) + pd.Timedelta(days=1)

    # limits from constraints (block / window / human) + material contradictions
    limit_of: dict[str, str] = {}
    limits = []
    tickets = ctx.tables["stg_it_tickets"].set_index("ticket_id")
    # A ticket has two texts (title, description): take the WORST verdict, so a clean title can never
    # vouch for an injected description. Contract quote_risk knows unchecked / ok / flagged only:
    # «ambiguous» (a human-directed note, shown but never followed) is displayed as ok.
    def _worst(s: pd.Series) -> str:
        v = set(s.dropna())
        return "flagged" if "flagged" in v else "unchecked" if "unchecked" in v or not v else "ok"
    risk = ctx.tables["free_text"].groupby("record_key")["text_risk"].agg(_worst)
    for c in constraints:
        if c["type"] not in ("block", "window", "human_decision"):
            continue
        lid = f"L-{len(limits) + 1:02d}"
        limit_of[c["id"]] = lid
        ref = c["source"]["ref"]
        quote, qrisk = None, "unchecked"
        if c["source"]["kind"] == "ticket" and ref in tickets.index:
            t = tickets.loc[ref]
            quote = f"{t['title']}: {t['description']}"
            qrisk = risk.get(ref) or "unchecked"
        limits.append({"id": lid, "type": {"human_decision": "human"}.get(c["type"], c["type"]), "title": c["summary"],
                       "entity_ids": sorted({e for s in c["applies_to"] for e in _entity_ids(ctx, s if ":" in s else f"res:{s}")}),
                       "period_text": _period_text(c["schedule"]), "occurrences": _occurrences(c["schedule"], asof),
                       "decided_by": c.get("decided_by"), "source": c["source"],
                       "quote": None if qrisk == "flagged" else quote, "quote_risk": qrisk, "constraint_id": c["id"]})
    iss = pd.DataFrame(ctx.issues)
    for it in iss[(iss["issue_type"] == "contradiction") & iss["severity"].isin(["warn", "handover"])].itertuples():
        limits.append({"id": f"L-{len(limits) + 1:02d}", "type": "contradiction", "title": it.action,
                       "entity_ids": [f"res:{it.resource_id}"] if isinstance(it.resource_id, str) else [],
                       "period_text": "baseline year", "occurrences": [], "decided_by": None,
                       "source": {"kind": "file", "ref": it.issue_id}, "quote": it.detail, "quote_risk": "ok"})

    # measures
    mkey = {m["key"]: f"M-{i + 1:02d}" for i, m in enumerate(measures)}
    fkey = {f["key"]: f"F-{i + 1:02d}" for i, f in enumerate(plan["findings"])}
    in_pkg = set(pkg["measure_keys"])
    out_m = []
    for m in measures:
        ents = sorted({e for ef in m["effects"] for e in _entity_ids(ctx, ef["scope"])})
        rows = ctx.tables["fact_cost"][ctx.tables["fact_cost"]["resource_id"].isin({calc.resource_of(ef["scope"]) for ef in m["effects"]})]
        formula = " + ".join(f"{l['scope']}: cost × {l['cost_share']:.2f}, energy × {l['energy_share']:.2f}"
                             + (f", rest moved to {l['relocate_to']}" if l["relocate_to"] else "") for l in m["_lines"])
        c = calcf(rows[rows["in_baseline"]], "savings = recurring baseline of each scope × shares chosen by the advisor; "
                  "CO2 of relocated load × (1 − grid target / grid origin). " + formula,
                  note=f"Assumptions: {m['assumptions']} Risks: {m['risks']}")
        c["inputs"] = [{"name": f"{l['scope']} baseline cost", "value": l["base_cost_chf"], "unit": "CHF", "source": "fact_cost"}
                       for l in m["_lines"]] + [{"name": f"{l['scope']} cost share removed", "value": l["cost_share"], "unit": "share",
                                                  "source": ", ".join(l["basis_fact_ids"]) or "advisor"} for l in m["_lines"]]
        reason = m["status_reason"] if m["status"] != "ok" else ""
        if m["gate_reasons"]:
            reason = (reason + " · " if reason else "") + "Safety gate: " + "; ".join(m["gate_reasons"])
        out_m.append({
            "id": mkey[m["key"]], "title": m["title"], "description": m["description"], "type": m["type"],
            "entity_ids": ents, "finding_ids": [fkey[k] for k in m["finding_keys"] if k in fkey],
            "limit_ids": [limit_of[c_] for c_ in m["limit_ids"] if c_ in limit_of],
            "effort_days": m["effort_days"], "effort_chf": m["effort_days"] * PERSON_DAY_CHF,
            "savings": metrics(m["_savings"]), "status": m["status"], "owner_role": m["owner_role"],
            "reason": reason, "start_date": m["start_date"], "in_package": m["key"] in in_pkg and m["status"] != "blocked",
            "calc": c, "effects": m["_lines"], "proposed_status": m["proposed_status"],
            "effort_reasoning": m["effort_reasoning"], "risks": m["risks"], "assumptions": m["assumptions"],
            "generated_by": ("candidate from the toolbox (code), calibrated by an area agent "
                             f"({ctx.config['advisor']['agent_model']})" if m.get("agent_reviewed") else "toolbox (code)")
                            + "; numbers, status gate and package choice by code"})

    # findings: evidence values filled by code from fact ids
    unknown = set()
    out_f = []
    for f in plan["findings"]:
        ev = []
        for fid in f["evidence_fact_ids"]:
            x = cfacts.get(fid)
            if x is None:
                unknown.add(fid)
                continue
            ev.append({"statement": x["statement"], "value": x["value"] if isinstance(x["value"], (int, float)) else None,
                       "unit": x["unit"], "source_files": x["sources"], "fact_id": fid})
        linked = [m for m in measures if f["key"] in m["finding_keys"] and m["status"] != "blocked"]
        if f["kind"] == "waste" and linked:
            imp = sum((m["_savings"] for m in linked), pd.Series(0.0, index=SUMS))
            basis = "savings of the linked measures"
        else:
            imp = sum((calc.base(s) for s in f["scopes"]), pd.Series(0.0, index=SUMS))
            basis = "baseline of the scopes"
        share = max(imp["cost_chf"] / tot["cost_chf"], imp["co2_kg_mid"] / tot["co2_kg_mid"])
        rows = ctx.tables["fact_cost"][ctx.tables["fact_cost"]["resource_id"].isin({calc.resource_of(s) for s in f["scopes"]})]
        out_f.append({"id": fkey[f["key"]], "kind": f["kind"], "title": f["title"],
                      "entity_ids": sorted({e for s in f["scopes"] for e in _entity_ids(ctx, s)}), "evidence": ev,
                      "severity": "high" if share >= sev["high"] else "medium" if share >= sev["medium"] else "low",
                      "impact": metrics(imp), "measure_ids": [mkey[m["key"]] for m in measures if f["key"] in m["finding_keys"]],
                      "calc": calcf(rows[rows["in_baseline"]], f"impact = {basis}", note=f["explanation"]),
                      "generated_by": "found by code (toolbox) from the fact sheet; evidence values from fact ids"})
    if unknown:
        ctx.log("advisor", "advisor_unknown_fact", len(unknown), "evidence fact ids not in the fact sheet were dropped",
                ", ".join(sorted(unknown)[:10]), severity="warn")

    edge = [{"measure_id": mkey.get(e["measure_key"]), "explanation": e["explanation"]} for e in plan["edge_cases"]]
    package, _ = _package(calc, measures, plan["package"]["measure_keys"], mkey, plan["package"]["reasoning"], edge)
    package["goal"] = assembled["default_goal"]
    # optimal package for every goal option (switchable live in the UI: no AI involved)
    packages = {}
    for goal, opt in assembled["packages"].items():
        if not opt["feasible"]:
            packages[goal] = {"goal": goal, "feasible": False, "note": opt.get("note", "")}
            continue
        p_, _ = _package(calc, measures, opt["measure_keys"], mkey,
                         f"Optimal package for «{goal}» (optimiser, code)", edge)
        packages[goal] = {"goal": goal, "feasible": True, **p_, "safety_met": opt.get("safety_met"),
                          "safety_rule": opt.get("safety_rule"), "p_meet_co2": opt.get("p_meet_co2"),
                          "is_safest": bool(opt.get("is_safest")),
                          **({"same_as": opt["same_as"]} if opt.get("same_as") else {}),
                          **({"note": opt["note"]} if opt.get("note") else {})}
    dp = assembled["packages"].get(assembled["default_goal"], {})
    package.update({"p_meet_co2": dp.get("p_meet_co2"), "is_safest": bool(dp.get("is_safest")), "safety_rule": dp.get("safety_rule")})
    cfg_a = ctx.config["advisor"]
    rules = {"co2_min": float(cfg_a["thresholds"]["co2"]), "cost_min": float(cfg_a["thresholds"]["cost"]),
             "budget_chf": float(cfg_a["budget_chf"]), "chf_per_person_day": PERSON_DAY_CHF,
             "baseline": {"cost_chf": round(float(calc.tot["cost_chf"]), 2), "kwh": round(float(calc.tot["kwh_mid"]), 1),
                          "co2_kg": round(float(calc.tot["co2_kg_mid"]), 1)},
             "how_to_recompute": "a package's measures do not overlap: totals = sum of the remaining measures' savings and "
                                 "effort; reduction = savings / baseline; meets = reductions ≥ co2_min / cost_min and "
                                 "effort_chf ≤ budget_chf; safety: see safety_scenarios.json"}
    live = None
    if assembled.get("live"):
        live = {"baseline_co2_kg": assembled["live"]["baseline_co2"],
                "measures": {mkey[k]: v for k, v in assembled["live"]["measures"].items() if k in mkey}}
    in_pkg_ids = set(package["measure_ids"])
    for m in out_m:
        m["in_package"] = m["id"] in in_pkg_ids

    # entity flags and links for the scene
    flags, links = {}, {"finding_ids": {}, "measure_ids": {}, "limit_ids": {}}
    for f in out_f:
        for e in f["entity_ids"]:
            flags.setdefault(e, set()).add("waste" if f["kind"] in ("waste", "anomaly") else "driver")
            links["finding_ids"].setdefault(e, set()).add(f["id"])
    for m in out_m:
        for e in m["entity_ids"]:
            links["measure_ids"].setdefault(e, set()).add(m["id"])
            if m["status"] == "human":
                flags.setdefault(e, set()).add("handover")
    for l in limits:
        for e in l["entity_ids"]:
            links["limit_ids"].setdefault(e, set()).add(l["id"])
            if l["type"] == "block":
                flags.setdefault(e, set()).add("locked")
    ctx.entity_flags, ctx.entity_links = flags, links

    for p in problems:
        ctx.log("advisor", "advisor_check", 1, "plan check", p, severity="warn")
    rej = getattr(ctx, "advisor_rejected_constraints", [])
    if rej:
        ctx.log("advisor", "constraint_rejected", len(rej), "reader constraints failing code validation were dropped",
                "; ".join(f"{r['ticket_id']}: {r['problems']}" for r in rej), severity="warn")
    ctx.log("advisor", "advisor_applied", len(out_m),
            f"{len(out_f)} findings, {len(out_m)} measures, {len(limits)} limits; package CO2 −{pkg['reduction']['co2']['mid']:.1%}, "
            f"cost −{pkg['reduction']['cost']['mid']:.1%}, effort {pkg['effort_days']} d",
            f"tickets withheld from the reader: {len(raw_c.get('withheld', []))}; ignored by the reader: {len(raw_c.get('ignored', []))}")
    kept = [{**k, "entity_ids": _entity_ids(ctx, k["target"] if ":" in k["target"] else f"res:{k['target']}")}
            for k in assembled["kept_on"]]
    return {"findings": out_f, "measures": out_m, "package": package, "packages": packages, "goals": assembled["goals"],
            "kept_on": kept, "limits": limits, "constraints": constraints, "analysis": analysis, "rules": rules, "live": live,
            "ignored": raw_c.get("ignored", []), "withheld": raw_c.get("withheld", []),
            "ai_footprint": analysis.get("ai_footprint")}


# --------------------------------------------------------------- export
def export(ctx: Context) -> None:
    a = ctx.advisor
    out = ctx.output_dir
    meta = _meta(ctx)
    files = {
        "measures.json": {"meta": meta, "measures": a["measures"], "package": a["package"],
                          "packages": a["packages"], "goals": a["goals"], "kept_on": a["kept_on"], "rules": a["rules"],
                          "analysis": {k: v for k, v in a["analysis"].items() if k != "calls"},
                          "ai_footprint": a["ai_footprint"],
                          "additivity_note": "Measures are checked by code for overlap: savings of the package can be summed. "
                                             "Blocked measures are never part of the package."},
        "limits.json": {"meta": meta, "limits": a["limits"]},
        **({"safety_scenarios.json": {
            "meta": meta, "n_scenarios": len(a["live"]["baseline_co2_kg"]), "threshold_co2": a["rules"]["co2_min"],
            "baseline_co2_kg": a["live"]["baseline_co2_kg"], "measures": a["live"]["measures"],
            "how_to": "safe in X % (approx.) = share of scenarios j where Σ measures[m][j] over the package's remaining "
                      "measures ≥ threshold_co2 × baseline_co2_kg[j]. The first N of the Monte Carlo panel's 10,000 draws "
                      "(same seed): can differ from the panel's figure by about one point."}} if a.get("live") else {}),
        "advisor/report.json": {"meta": meta, "analysis": a["analysis"], "ai_footprint": a["ai_footprint"],
                                "constraints": a["constraints"],
                                "reader_ignored": a["ignored"], "reader_withheld": a["withheld"]},
    }
    for name, obj in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        with open(out / name, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1, default=str)

    tpl = pd.read_csv(ctx.data_dir / "template_measures_package.csv", encoding="utf-8-sig", dtype=str, nrows=0)
    sub = out / "submission"
    sub.mkdir(parents=True, exist_ok=True)
    with open(sub / "template_measures_package.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(tpl.columns))
        w.writeheader()
        for m in a["measures"]:
            if not m["in_package"]:
                continue
            s = m["savings"]
            w.writerow({
                "measure_id": m["id"], "description": m["title"],
                "resource_or_source": ", ".join(e["scope"] for e in m["effects"]),
                "change": m["description"] + f" (from {m['start_date']})",
                "effort_person_days": m["effort_days"],
                "savings_cost_chf_per_year": round(s["cost_chf"]["mid"]),
                "savings_energy_kwh_per_year": round(s["kwh"]["mid"]),
                "savings_co2_kg_location_based": round(s["co2_kg"]["mid"]),
                "savings_co2_kg_market_based": "",
                "risks_and_exceptions": f"Status: {m['status']} (decides: {m['owner_role']}). {m['reason']} {m['risks']}".strip(),
                "assumptions_and_sources": f"{m['assumptions']} Calculation: {m['calc']['formula']} "
                                           f"Ranges CHF {s['cost_chf']['low']:,.0f}–{s['cost_chf']['high']:,.0f}, "
                                           f"CO2 {s['co2_kg']['low']:,.0f}–{s['co2_kg']['high']:,.0f} kg. "
                                           f"Factors: pipeline/energy/factors.yaml; data: fact_cost (baseline year, without one-offs)."})
