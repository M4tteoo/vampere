"""End-to-end audit of the pipeline outputs (run after `python -m pipeline.run`).

    .venv/bin/python -m tests.audit_outputs          # prints every check
    .venv/bin/python -m unittest tests.test_outputs  # same checks as a test

1. contract: every file in output/ has the fields of its interface in contract/types.ts,
   every {low, mid, high} is ordered, every cross-reference resolves;
2. numbers: the same quantity agrees across modules (e.g. summary = fact_cost = entities =
   timeseries = submission template; package = Σ measures = templates = Monte Carlo mid).
"""
import csv
import json
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def contract_problems(R: Path) -> list[str]:
    """Every output file has the required fields of its contract interface, every Range is ordered,
    every id reference (entity, finding, measure, limit, factor, quality issue) resolves."""
    O = R / "output"
    ts = (R / "contract/types.ts").read_text()
    # --- parse interfaces: name -> {field: optional}
    ifaces = {}
    for m in re.finditer(r"export interface (\w+)\s*(?:extends [\w, ]+)?\{(.*?)\n\}", ts, re.S):
        body = re.sub(r"/\*.*?\*/", "", m.group(2), flags=re.S)
        depth, fields = 0, {}
        for line in body.split("\n"):
            line = re.sub(r"//.*", "", line)
            if depth == 0:
                mm = re.match(r"\s*(\w+)(\?)?\s*:", line)
                if mm: fields[mm.group(1)] = bool(mm.group(2))
            depth += line.count("{") - line.count("}")
        ifaces[m.group(1)] = fields
    FILES = {"summary.json": "SummaryFile", "entities.json": "EntitiesFile", "timeseries.json": "TimeseriesFile",
             "findings.json": "FindingsFile", "measures.json": "MeasuresFile", "limits.json": "LimitsFile",
             "factors.json": "FactorsFile", "quality.json": "QualityFile", "fx.json": "FxFile",
             "clusters.json": "ClustersFile", "jobs.json": "JobsFile", "scenarios.json": "ScenariosFile",
             "montecarlo.json": "MonteCarloFile", "forecast.json": "ForecastFile", "market.json": None, "insights.json": "InsightsFile",
             "bonus/candidates.json": "CandidatesFile"}
    ITEMS = {"entities.json": ("entities", "Entity"), "findings.json": ("findings", "Finding"),
             "measures.json": ("measures", "Measure"), "limits.json": ("limits", "Limit"), "factors.json": ("factors", "Factor"),
             "quality.json": ("issues", "QualityIssue"), "clusters.json": ("members", "ClusterMember"), "jobs.json": ("jobs", "CarbonJob")}
    problems = []
    data = {}
    for f, iface in FILES.items():
        p = O / f
        if not p.exists(): problems.append(f"MISSING FILE {f}"); continue
        d = data[f] = json.loads(p.read_text())
        if iface is None:
            if not any(k == "MarketFile" for k in ifaces): problems.append(f"{f}: no contract type in types.ts")
            continue
        if iface not in ifaces: problems.append(f"{f}: interface {iface} not in types.ts"); continue
        miss = [k for k, opt in ifaces[iface].items() if not opt and k not in d]
        if miss: problems.append(f"{f}: missing required {miss}")
        if f in ITEMS:
            key, it = ITEMS[f]
            for x in d.get(key, []):
                miss = [k for k, opt in ifaces[it].items() if not opt and k not in x]
                if miss: problems.append(f"{f} {x.get('id', x.get('issue_id', x.get('entity_id', x.get('job_name'))))}: missing {miss}"); break
    # --- ranges ordered low <= mid <= high
    def walk(o, path):
        if isinstance(o, dict):
            if {"low", "mid", "high"} <= set(o) and all(isinstance(o[k], (int, float)) for k in ("low", "mid", "high")):
                if not (o["low"] - 1e-9 <= o["mid"] <= o["high"] + 1e-9): yield path, o
            for k, v in o.items(): yield from walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o[:5000]): yield from walk(v, f"{path}[{i}]")
    inverted = {}
    for f, d in data.items():
        for path, o in walk(d, f):
            key = re.sub(r"\[\d+\]", "[]", path); inverted.setdefault(key, []).append(o)
    for k, v in inverted.items(): problems.append(f"RANGE not ordered ({len(v)}x): {k} e.g. {v[0]}")
    # --- cross references
    ents = {e["id"] for e in data["entities.json"]["entities"]}
    F = {x["id"] for x in data["findings.json"]["findings"]}; M = {x["id"] for x in data["measures.json"]["measures"]}
    L = {x["id"] for x in data["limits.json"]["limits"]}; Q = {x["issue_id"] for x in data["quality.json"]["issues"]}
    FA = {x["id"] for x in data["factors.json"]["factors"]}
    def refs(where, ids, pool, kind):
        bad = sorted(set(ids) - pool)
        if bad: problems.append(f"{where}: unknown {kind} {bad[:5]}")
    for e in data["entities.json"]["entities"]:
        refs(f"entity {e['id']}", e["finding_ids"], F, "finding"); refs(f"entity {e['id']}", e["measure_ids"], M, "measure")
        refs(f"entity {e['id']}", e["limit_ids"], L, "limit")
        if e["parent_id"] and e["parent_id"] not in ents: problems.append(f"entity {e['id']}: parent {e['parent_id']} unknown")
    for x in data["findings.json"]["findings"]: refs(f"finding {x['id']}", x["entity_ids"], ents, "entity"); refs(f"finding {x['id']}", x["measure_ids"], M, "measure")
    for x in data["measures.json"]["measures"]:
        refs(f"measure {x['id']}", x["entity_ids"], ents, "entity"); refs(f"measure {x['id']}", x["finding_ids"], F, "finding"); refs(f"measure {x['id']}", x["limit_ids"], L, "limit")
    for x in data["limits.json"]["limits"]: refs(f"limit {x['id']}", x["entity_ids"], ents, "entity")
    refs("package", data["measures.json"]["package"]["measure_ids"], M, "measure")
    for g in data["clusters.json"]["groups"]: refs(f"cluster {g['id']}", g["entity_ids"], ents, "entity")
    for j in data["jobs.json"]["jobs"]: refs(f"job {j['job_name']}", [j["entity_id"]], ents, "entity")
    refs("scenarios entities", data["scenarios.json"]["entities_co2_kg_production"], ents, "entity")
    for s in data["timeseries.json"]["series"]: refs("timeseries", [s["entity_id"]], ents, "entity")
    # calc factor ids and issue ids everywhere
    calc_f, calc_q = set(), set()
    def calcs(o):
        if isinstance(o, dict):
            if "formula" in o and "factor_ids" in o:
                calc_f.update(o.get("factor_ids") or []); calc_q.update(o.get("issue_ids") or [])
            for v in o.values(): calcs(v)
        elif isinstance(o, list):
            for v in o: calcs(v)
    for f in ("summary.json", "entities.json", "findings.json", "measures.json"): calcs(data[f])
    refs("calc.factor_ids (summary/entities/findings/measures)", calc_f, FA, "factor")
    refs("calc.issue_ids", calc_q, Q, "quality issue")
    return problems


def number_checks(R: Path) -> list[tuple]:
    """The same quantity agrees wherever it appears (summary, entities, timeseries, templates, package,
    market, scenarios, Monte Carlo, forecast, jobs, answers). Returns (ok, name, a, b) per check."""
    O = R / "output"
    J = lambda n: json.loads((O / n).read_text())
    S, E, T, M, MK, SC, MC, FC, JB, CL, A, Q = (J(n) for n in ("summary.json", "entities.json", "timeseries.json", "measures.json",
        "market.json", "scenarios.json", "montecarlo.json", "forecast.json", "jobs.json", "clusters.json", "answers.json", "quality.json"))
    con = duckdb.connect(str(O / "greenops.duckdb"), read_only=True)
    fc = con.execute("select sum(cost_chf), sum(kwh_mid), sum(co2_kg_mid), sum(co2_kg_market_mid) from fact_cost where in_baseline").fetchone()
    res = []
    def eq(name, a, b, rel=1e-3):
        ok = abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)
        res.append((ok, name, a, b)); return ok
    B = S["baseline"]
    eq("summary cost = fact_cost", B["cost_chf"]["mid"], fc[0]); eq("summary kWh = fact_cost", B["kwh"]["mid"], fc[1]); eq("summary CO2 = fact_cost", B["co2_kg"]["mid"], fc[2])
    eq("summary market CO2 = fact_cost", B["co2_kg_market"]["mid"], fc[3])
    for dim in ("by_category", "by_department", "by_location", "by_tool"):
        eq(f"summary {dim} CO2 sums to baseline", sum(x["metrics"]["co2_kg"]["mid"] for x in S["breakdown"][dim]), B["co2_kg"]["mid"])
        eq(f"summary {dim} cost sums to baseline", sum(x["metrics"]["cost_chf"]["mid"] for x in S["breakdown"][dim]), B["cost_chf"]["mid"])
    eq("flows (cables) CO2 = baseline", sum(f["metrics"]["co2_kg"]["mid"] for f in S["flows"]), B["co2_kg"]["mid"])
    ents = E["entities"]; byk = lambda k: [e for e in ents if e["kind"] == k]
    eq("islands CO2 = baseline", sum(e["metrics"]["co2_kg"]["mid"] for e in byk("island")), B["co2_kg"]["mid"])
    eq("rooms cost = baseline", sum(e["metrics"]["cost_chf"]["mid"] for e in byk("room")), B["cost_chf"]["mid"])
    eq("resources cost (billed racks) = cloud+server+ai+saas", sum(e["metrics"]["cost_chf"]["mid"] for e in byk("resource")), B["cost_chf"]["mid"], 0.25)
    # timeseries: monthly island points over baseline months
    bm = {f"2025-{m:02d}-01" for m in range(9, 13)} | {f"2026-{m:02d}-01" for m in range(1, 9)}
    ts_co2 = sum(p["co2_kg"] or 0 for s in T["series"] if s["entity_id"].startswith("loc:") and s["granularity"] == "month" for p in s["points"] if p["t"] in bm)
    eq("timeseries islands (12 baseline months) CO2 = baseline", ts_co2, B["co2_kg"]["mid"])
    # submission baseline template
    rows = {r["parameter"]: r for r in csv.DictReader(open(O / "submission/template_baseline_and_assumptions.csv", encoding="utf-8-sig"))}
    eq("template total cost = summary", float(rows["total_cost_baseline_year_chf"]["value_mid"]), B["cost_chf"]["mid"])
    eq("template total kWh = summary", float(rows["total_energy_baseline_year_kwh"]["value_mid"]), B["kwh"]["mid"])
    eq("template total CO2 = summary", float(rows["total_co2_location_based_baseline_year_kg"]["value_mid"]), B["co2_kg"]["mid"])
    eq("template market CO2 = market.json", float(rows["total_co2_market_based_baseline_year_kg"]["value_mid"]), MK["baseline"]["co2_kg_market"]["mid"])
    must_empty = [p for p, r in rows.items() if r["must_or_bonus"] == "Must" and not r["value_mid"]]
    bonus_empty = [p for p, r in rows.items() if r["must_or_bonus"] == "Bonus" and not r["value_mid"]]
    res.append((not must_empty, "template: every Must row filled", must_empty, "")); res.append((True, "template: Bonus rows still empty (info)", bonus_empty, ""))
    # package
    P = M["package"]; inpk = [m for m in M["measures"] if m["in_package"]]
    eq("package CO2 savings = Σ package measures", P["savings"]["co2_kg"]["mid"], sum(m["savings"]["co2_kg"]["mid"] for m in inpk))
    eq("package cost savings = Σ package measures", P["savings"]["cost_chf"]["mid"], sum(m["savings"]["cost_chf"]["mid"] for m in inpk))
    eq("package CO2 reduction = savings / baseline", P["reduction"]["co2"]["mid"], P["savings"]["co2_kg"]["mid"] / B["co2_kg"]["mid"], 2e-3)
    eq("package cost reduction = savings / baseline", P["reduction"]["cost"]["mid"], P["savings"]["cost_chf"]["mid"] / B["cost_chf"]["mid"], 2e-3)
    eq("package effort days = Σ", P["effort_days"], sum(m["effort_days"] for m in inpk)); eq("package effort CHF = days × 1100", P["effort_chf"], P["effort_days"] * 1100)
    res.append((P["effort_chf"] <= 16500 and P["reduction"]["co2"]["mid"] >= .40 and P["reduction"]["cost"]["mid"] >= .25, "package meets −40 % / −25 % / CHF 16,500 (mid)", P["reduction"]["co2"]["mid"], P["reduction"]["cost"]["mid"]))
    mt = list(csv.DictReader(open(O / "submission/template_measures_package.csv", encoding="utf-8-sig")))
    res.append(({r["measure_id"] for r in mt} == set(P["measure_ids"]), "measures template rows = package measures", sorted(r["measure_id"] for r in mt), P["measure_ids"]))
    eq("measures template Σ CO2 = package", sum(float(r["savings_co2_kg_location_based"]) for r in mt), P["savings"]["co2_kg"]["mid"], 2e-3)
    eq("measures template Σ CHF = package", sum(float(r["savings_cost_chf_per_year"]) for r in mt), P["savings"]["cost_chf"]["mid"], 2e-3)
    mk_cols = [r["savings_co2_kg_market_based"] for r in mt]; res.append((all(mk_cols), "measures template market column filled", mk_cols, ""))
    # bonus modules vs core
    eq("market kWh = location kWh", MK["baseline"]["kwh"]["mid"], B["kwh"]["mid"]); eq("market location CO2 = summary", MK["baseline"]["co2_kg"]["mid"], B["co2_kg"]["mid"])
    c = SC["scenarios"]["ch_consumption"]
    eq("scenarios consumption baseline CO2 = summary", c["baseline"]["co2_kg"]["mid"], B["co2_kg"]["mid"]); eq("scenarios consumption reduction = package", c["package"]["reduction"]["co2"]["mid"], P["reduction"]["co2"]["mid"])
    eq("scenarios production entities: islands sum = production baseline", sum(v["mid"] for k, v in SC["entities_co2_kg_production"].items() if k.startswith("loc:")), SC["scenarios"]["ch_production"]["baseline"]["co2_kg"]["mid"])
    eq("montecarlo deterministic mid = package", MC["package"]["deterministic_mid"]["co2"], P["reduction"]["co2"]["mid"])
    res.append((MC["package"]["measure_ids"] == P["measure_ids"], "montecarlo uses the package measures", MC["package"]["measure_ids"], ""))
    for g, gp in M.get("packages", {}).items():       # the optimiser's goal packages (advisor) → B1 / B2 per goal
        if not gp.get("feasible"):
            continue
        eq(f"scenarios {g} reduction = measures.json packages", c["packages_by_goal"][g]["reduction"]["co2"]["mid"], gp["reduction"]["co2"]["mid"])
        res.append((MC["by_goal"][g]["measure_ids"] == gp["measure_ids"], f"montecarlo {g} uses that goal's measures", g, ""))
    eq("montecarlo by_goal[recommended] = top level", MC["by_goal"][P["goal"]]["co2_reduction"]["p_meet"], MC["co2_reduction"]["p_meet"])
    eq("jobs: baseline CO2 = summary", JB["totals"]["baseline_co2_kg"], B["co2_kg"]["mid"])
    reloc = {e["scope"].split(":")[1]: e["relocate_to"] for m in inpk for e in m["effects"] if e.get("relocate_to")}
    res.append((JB["after_package"]["relocated"] == {k: v for k, v in reloc.items() if k in ("dp-prod", "dp-dev")}, "jobs after_package relocations = package", JB["after_package"]["relocated"], reloc))
    # forecast: first month 'without' vs recurring baseline/12; 'with' lower by roughly the package
    f0 = FC["months"][0]; yr_wo = sum(m["without"]["co2_kg"]["mid"] for m in FC["months"]); yr_w = sum(m["with"]["co2_kg"]["mid"] for m in FC["months"]) if f0["with"] else None
    res.append((True, "forecast 12-month CO2 without / with (info)", round(yr_wo), round(yr_w) if yr_w else None))
    res.append((yr_w is not None and yr_w < yr_wo, "forecast: with package < without", round(1 - yr_w / yr_wo, 3) if yr_w else None, f"package {P['reduction']['co2']['mid']}"))
    res.append((True, "forecast first month cost without vs baseline/12 (info)", f0["without"]["cost_chf"]["mid"], round(S["baseline_recurring"]["cost_chf"]["mid"] / 12, 1)))
    # extra-source insights
    IN = J("insights.json")
    extra_files = {f"extra/{p.name}" for p in (R / "data/case/extra").iterdir() if p.suffix in (".csv", ".jsonl")}
    res.append(({s_["file"] for s_ in IN["sources"]} == extra_files and all(s_["used_for"] for s_ in IN["sources"]),
                "insights: every extra source is used by a feature", len(IN["sources"]), len(extra_files)))
    pbi = next(c for c in IN["cards"] if c["id"] == "powerbi")
    cap = con.execute("select sum(cost_chf) from fact_cost where in_baseline and not coalesce(is_one_off, false) and resource_id='pbi-kap'").fetchone()[0]
    eq("insights: Power BI capacity cost = fact_cost", next(n["value"] for n in pbi["numbers"] if n["label"] == "capacity cost"), cap)
    res.append((len(IN["powerbi"]["reports"]) == con.execute("select count(distinct report_id) from stg_powerbi_usage").fetchone()[0],
                "insights: every Power BI report classified", len(IN["powerbi"]["reports"]), ""))
    reloc_ok = all(o["to"] in IN["regions"]["offered"][o["provider"]]["locations"] for o in IN["regions"]["options"])
    res.append((reloc_ok, "insights: relocation options only to offered regions", "", ""))
    pkg_moves = [(e["scope"], e["relocate_to"]) for m in inpk for e in m["effects"] if e.get("relocate_to")]
    res.append((all(any(o["resource_id"] == s_.split(":")[1] and o["to"] == t for o in IN["regions"]["options"]) for s_, t in pkg_moves),
                "package relocations are offered by the provider", pkg_moves, ""))

    # answers & quality
    q1 = A["answers"]["q1_find"]["answer"]; res.append(("67" in q1 and "1,223.51" in q1, "answers.json Q1 = 67 seats, CHF 1,223.51", q1[:60], ""))
    res.append((len(A["answers"]) >= 3, "answers.json has the 3 example questions", list(A["answers"]), ""))
    risk = dict(con.execute("select text_risk, count(distinct text) from free_text group by 1").fetchall())
    res.append((risk.get("flagged") == 4, "4 injected texts flagged (text_risk)", risk, ""))
    fp = J("advisor/report.json").get("ai_footprint") or json.loads((O / "advisor/plan_raw.json").read_text()).get("ai_footprint")
    res.append((bool(fp), "per-run AI footprint present", (fp or {}).get("kwh"), (fp or {}).get("source")))
    return res


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    problems = contract_problems(root)
    print(f"contract: {len(problems)} problem(s)")
    for p in problems:
        print("  -", p)
    res = number_checks(root)
    for ok, name, a, b in res:
        print(("PASS " if ok else "FAIL ") + name + (f"   [{a} | {b}]" if not ok or "info" in name else ""))
    passed = sum(r[0] for r in res)
    print(f"numbers: {passed}/{len(res)} passed")
    return 0 if not problems and passed == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
