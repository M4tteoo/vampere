"""Local AI option (advisory only): could the company's own AI workloads run on open-weight
models on hardware it has or could rent from its current providers?

Reads the harmonized data and the existing outputs; writes only output/local_ai.json.
Every number is computed here from the data and pipeline/bonus/local_ai_catalog.yaml; no LLM.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ..energy.engine import load_factors
from ..export.frontend import SUMS, Calc, metrics
from ..harmonize.context import Context
from .common import read_output, rng, write_json

CATALOG = Path(__file__).with_name("local_ai_catalog.yaml")
LEVELS = ("low", "mid", "high")
FLIP = {"low": "high", "mid": "mid", "high": "low"}
TIERS = ["basic", "standard", "advanced"]
HORIZON_YEARS = 3
TIER_SHARE_MIN = 0.20

WORKLOADS = {
    "ai-assistant": ("wl:office-assistant", "Office AI assistant", "contracts, tables, summaries of internal documents"),
    "ai-marketing": ("wl:marketing-classify", "Marketing text analysis", "customer texts"),
    "ai-agent2": ("wl:other-agents", "Other agents (research, sales)", "internal data read by agents"),
    "ai-agent": ("wl:support-agent", "Support-Agent", "support tickets"),
    "ai-quote": ("wl:quote-generator", "Quote generator", "prices and customer data"),
    "ai-chatbot": ("wl:knowledge-chatbot", "Knowledge chatbot", "internal knowledge base"),
    "ai-report": ("wl:report-agent", "Report-Agent", "internal reports"),
}
TASK_TIER = {
    "Classify": "basic", "Translate": "basic", "Manual question": "basic",
    "Summarise": "standard", "Draft texts": "standard", "Analyse table": "standard",
    "Review contract": "advanced", "Agent run": "advanced",
}
# Coding stays on the API (agreed with the case owner, ALTYCA): local models are for tasks on private business data.
# The code agent shares the resource «ai-agent2» with other agents; its share is removed using the agent-run logs.
CODING_AGENTS = {"ai-agent2": ["code-agent"]}

TASK_LABEL = {"Review contract": "contract review", "Agent run": "agent runs", "Analyse table": "table analysis",
              "Draft texts": "drafting", "Manual question": "manual questions"}
GRID_ID = {"CH": "grid_mix_location_based_switzerland", "DE": "grid_mix_location_based_germany",
           "IE": "grid_mix_location_based_ireland", "EU": "grid_mix_location_based_eu"}


# ------------------------------------------------------------------ pure helpers
def out_eq(tokens_in: float, tokens_in_cache: float, tokens_out: float, input_w: float, cached_w: float) -> float:
    """Output-equivalent tokens, the same formula as the energy engine."""
    return tokens_out + input_w * max(tokens_in - tokens_in_cache, 0.0) + cached_w * tokens_in_cache


def vram_check(weights_gb: float, vram_gb: float, headroom: float) -> str | None:
    need = weights_gb * headroom
    if need > vram_gb + 1e-9:
        return f"needs {need:.0f} GB with headroom, hardware has {vram_gb:.0f} GB"
    return None


def breakeven_month(setup_chf: float, local_monthly_chf: float, api_year0_chf: float, growth: float,
                    months: int = HORIZON_YEARS * 12) -> int | None:
    """First month m where setup + m × local ≤ cumulative API cost (API grows by `growth` per year)."""
    api = 0.0
    for m in range(1, months + 1):
        api += api_year0_chf / 12 * (1 + growth) ** (m / 12)
        if setup_chf + m * local_monthly_chf <= api + 1e-6:
            return m
    return None


def energy_kwh(on_hours: float, gpu_hours: float, idle_w: float, tdp_w: float, host_w: float, pue: float) -> float:
    """Idle power (+ host) whenever on, plus the dynamic part while generating."""
    return (on_hours * (idle_w + host_w) + gpu_hours * (tdp_w - idle_w)) / 1000 * pue


# ------------------------------------------------------------------ inputs
def _catalog() -> dict:
    with CATALOG.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _lvl(v) -> dict:
    """Scalar or {low, mid, high} → {low, mid, high}."""
    return {k: float(v[k]) for k in LEVELS} if isinstance(v, dict) else {k: float(v) for k in LEVELS}


def _factor_ranges(ctx: Context) -> dict[str, dict]:
    f = read_output(ctx, "factors.json") or {"factors": []}
    return {x["id"]: {k: float(x[k]) for k in LEVELS} for x in f["factors"]}


def _fx(ctx: Context) -> dict[str, float]:
    """CHF per unit of currency, baseline-year average (as the savings in measures.json)."""
    fx = ctx.tables["fx_monthly"].copy()
    b0, b1 = ctx.baseline
    m = fx["month"].astype(str)
    fx = fx[(m >= b0[:7]) & (m <= b1)]
    return {"CHF": 1.0, "EUR": float(fx["eur_chf"].mean()), "USD": float(fx["usd_chf"].mean())}


def _token_growth(ctx: Context) -> tuple[dict, str]:
    fc = read_output(ctx, "forecast.json") or {}
    for a in fc.get("assumptions", []):
        if a.get("id") == "token_growth":
            return {k: a["value"][k] / 100 for k in LEVELS}, "output/forecast.json (assumptions.token_growth)"
    return {k: 0.0 for k in LEVELS}, "forecast.json missing: no growth assumed"


def _metrics(chf: dict, kwh: dict, co2: dict, fx: dict) -> dict:
    s = {"cost_chf_low": chf["low"], "cost_chf": chf["mid"], "cost_chf_high": chf["high"],
         "cost_eur": chf["mid"] / fx["EUR"], "cost_usd": chf["mid"] / fx["USD"],
         "kwh_low": kwh["low"], "kwh_mid": kwh["mid"], "kwh_high": kwh["high"],
         "co2_kg_low": co2["low"], "co2_kg_mid": co2["mid"], "co2_kg_high": co2["high"]}
    return metrics(pd.Series(s))


def _host_w(host: dict, F: dict, u: float) -> dict:
    c = F["compute"]
    return {lv: host["vcpu"] * (c["cpu_w_min"][lv] + u * (c["cpu_w_max"][lv] - c["cpu_w_min"][lv]))
            + host["ram_gb"] * c["mem_w_per_gb"][lv] for lv in LEVELS}


# ------------------------------------------------------------------ workloads
def _workloads(ctx: Context, F: dict, cat: dict, growth: dict, fx: dict) -> list[dict]:
    b0, b1 = ctx.baseline
    a = F["ai_tokens"]
    u = ctx.tables["stg_ai_usage"].copy()
    u["date"] = u["date"].astype(str)
    u = u[(u["date"] >= b0) & (u["date"] <= b1) & u["resource_id"].isin(WORKLOADS)]
    # One-off events (e.g. OO-1, a script stuck in a loop) are not recurring demand: drop them from tokens and cost.
    oo = ctx.tables["one_off_events"]
    for e in oo[oo["resource_id"].isin(WORKLOADS)].itertuples():
        u = u[~((u["resource_id"] == e.resource_id) & (u["date"] >= str(e.start)) & (u["date"] <= str(e.end)))]
    u["out_eq"] = (u["tokens_out"].fillna(0) + a["input_weight"] * (u["tokens_in"].fillna(0) - u["tokens_in_cache"].fillna(0)).clip(lower=0)
                   + a["cached_weight"] * u["tokens_in_cache"].fillna(0))
    fc = ctx.tables["fact_cost"]
    base = fc[fc["in_baseline"] & ~fc["is_one_off"].fillna(False).astype(bool) & fc["resource_id"].isin(WORKLOADS)]
    calc = Calc(ctx, fc)
    hours_day = float(cat["assumptions"]["office_hours_per_workday"]["value"])
    out = []
    for rid, (wid, label, why) in WORKLOADS.items():
        rows = u[u["resource_id"] == rid]
        cost_rows = base[base["resource_id"] == rid]
        if rows.empty or cost_rows.empty:
            continue
        excluded = None
        if rid in CODING_AGENTS:
            share = _coding_share(ctx, rid, CODING_AGENTS[rid], a)
            keep = 1 - share
            rows = rows.assign(**{c: rows[c] * keep for c in ("tokens_in", "tokens_in_cache", "tokens_out", "requests", "cost_chf", "out_eq")})
            cost_rows = cost_rows.assign(**{c: cost_rows[c] * keep for c in SUMS})
            excluded = {"what": ", ".join(CODING_AGENTS[rid]), "share": round(share, 4),
                        "reason": "coding stays on the API (agreed with ALTYCA); share of output-equivalent tokens in "
                                  "ai_agent_runs.jsonl, baseline year"}
        by_task = rows.groupby("task_type").agg(cost=("cost_chf", "sum"), out_eq=("out_eq", "sum"))
        total = by_task["cost"].sum() or 1.0
        tasks = [{"task_type": t, "tier": TASK_TIER.get(t, "standard"), "cost_share": round(r.cost / total, 4),
                  "out_eq_tokens": round(r.out_eq)} for t, r in by_task.sort_values("cost", ascending=False).iterrows()]
        major = [t for t in tasks if t["cost_share"] >= TIER_SHARE_MIN] or tasks[:1]
        tier = max((t["tier"] for t in major), key=TIERS.index)
        day = rows.groupby("date")["out_eq"].sum()
        peak = float(day.max()) / (hours_day * 3600)
        m = metrics(cost_rows[SUMS].sum())
        eq = float(rows["out_eq"].sum())
        out.append({
            "id": wid, "label": label, "resource_id": rid, "tool": str(rows["tool"].mode().iat[0]),
            "why_private": why, "tier": tier, "tasks": tasks, "excluded": excluded,
            "models_today": sorted(rows["model"].dropna().unique().tolist()),
            "tokens_in": round(float(rows["tokens_in"].sum())), "tokens_in_cache": round(float(rows["tokens_in_cache"].sum())),
            "tokens_out": round(float(rows["tokens_out"].sum())), "out_eq_tokens": round(eq),
            "requests": int(rows["requests"].sum()),
            "peak_tps": round(peak, 1),
            "peak_tps_year3": round(peak * (1 + growth["mid"]) ** HORIZON_YEARS, 1),
            "api": m,
            "_daily": day,
            "calc": calc(cost_rows, "API cost, kWh and CO2 of the baseline year without one-off events (fact_cost); tokens from ai_usage.csv",
                         note=f"tier = highest tier among task types with ≥ {TIER_SHARE_MIN:.0%} of the API cost; "
                              f"peak = busiest day's output-equivalent tokens / ({hours_day:.0f} h × 3600 s)",
                         inputs=[{"name": "output-equivalent tokens", "value": round(eq), "unit": "tokens",
                                  "source": "ai_usage.csv"},
                                 {"name": "peak tokens/s", "value": round(peak, 1), "unit": "tokens/s",
                                  "source": "ai_usage.csv"}]),
        })
    return out


def _coding_share(ctx: Context, rid: str, agents: list[str], a: dict) -> float:
    """Share of the resource's output-equivalent tokens used by coding agents (agent-run logs, baseline year)."""
    r = ctx.tables.get("stg_ai_agent_runs")
    if r is None or r.empty:
        return 0.0
    b0, b1 = ctx.baseline
    d = r["date"].astype(str)
    r = r[(r["resource_id"] == rid) & (d >= b0) & (d <= b1)]
    tin, cache, tout = (r[c].fillna(0) for c in ("usage_tokens_in", "usage_cache_read_tokens", "usage_tokens_out"))
    eq = tout + a["input_weight"] * (tin - cache).clip(lower=0) + a["cached_weight"] * cache
    total = float(eq.sum())
    return float(eq[r["agent"].isin(agents)].sum()) / total if total else 0.0


# ------------------------------------------------------------------ hardware
def _hardware(ctx: Context, cat: dict, F: dict, FR: dict, fx: dict) -> tuple[list[dict], dict]:
    fc = ctx.tables["fact_cost"]
    gpu = fc[fc["in_baseline"] & (fc["resource_id"] == "gpu-ml") & (fc["unit"] == "GPU-hour")]
    gpu_h = float(gpu["quantity"].sum()) or 1.0
    derived = {"low": gpu["cost_chf_low"].sum() / gpu_h, "mid": gpu["cost_chf"].sum() / gpu_h,
               "high": gpu["cost_chf_high"].sum() / gpu_h}
    dd = ctx.tables["dim_date"]
    workdays = int(dd[dd["in_baseline"].astype(bool) & (dd["workday"] == 1)].shape[0])
    office_h = workdays * float(cat["assumptions"]["office_hours_per_workday"]["value"])
    u_host = float(cat["assumptions"]["host_cpu_utilisation"]["value"])
    out = []
    for h in cat["hardware"]:
        price = h["price"]
        if price == "derived":
            k = _lvl(h.get("price_factor", 1.0))
            per_h = {lv: derived[lv] * k[lv] for lv in LEVELS}
            per_m = None
        else:
            rate = fx[price["currency"]]
            vals = {lv: float(price[lv]) * rate for lv in LEVELS}
            per_h, per_m = (vals, None) if h["billing"] == "hourly" else (None, vals)
        on_h = office_h if h["billing"] == "hourly" else 8760.0
        pue_id = h["pue"]
        out.append({
            **{k: h[k] for k in ("id", "label", "provider", "location", "gpu", "gpu_class", "vram_gb", "tdp_w",
                                 "billing", "owned", "entity_id", "measure_roles", "note", "source", "estimate")},
            "idle_w": rng(*_lvl(h["idle_w"]).values(), nd=1),
            "host_w": rng(*_host_w(h["host"], F, u_host).values(), nd=1),
            "price_chf_per_hour": rng(*per_h.values(), nd=3) if per_h else None,
            "price_chf_per_month": rng(*per_m.values(), nd=0) if per_m else None,
            "on_hours_per_year": round(on_h),
            "extra_setup_days": float(h.get("extra_setup_days", 0)),
            "pue_factor_id": pue_id, "grid_factor_id": GRID_ID[h["location"]],
            "_pue": FR[pue_id], "_grid": FR[GRID_ID[h["location"]]],
            "_idle": _lvl(h["idle_w"]), "_host": _host_w(h["host"], F, u_host),
            "_per_h": per_h, "_per_m": per_m,
        })
    return out, {"gpu_ml_hourly_chf": derived, "gpu_ml_billed_hours": gpu_h, "workdays": workdays,
                 "office_hours": office_h, "gpu_rows": int(len(gpu))}


# ------------------------------------------------------------------ fits
def _fits(workloads: list[dict], models: list[dict], hardware: list[dict], headroom: float, growth: dict) -> list[dict]:
    out = []
    for w in workloads:
        for m in models:
            for h in hardware:
                tps = m["throughput"].get(h["gpu_class"])
                if tps is None and ("cpu4" in m["throughput"]) != (h["gpu_class"] == "cpu4"):
                    continue  # CPU build on a GPU host or GPU build on a CPU host: not a real option
                if tps is None:
                    r = vram_check(m["weights_gb"], h["vram_gb"], headroom)
                    out.append({
                        "id": f"{w['id']}|{m['id']}|{h['id']}", "workload_id": w["id"], "model_id": m["id"],
                        "hardware_id": h["id"], "feasible": False,
                        "reasons": [f"{m['label']} {r}" if r else f"no throughput figure for {h['gpu']}"],
                        "tps": None, "gpu_hours_per_year": None, "kwh_per_year": None, "co2_kg_per_year": None,
                    })
                    continue
                reasons = []
                r = vram_check(m["weights_gb"], h["vram_gb"], headroom)
                if r:
                    reasons.append(f"{m['label']} {r}")
                if TIERS.index(m["tier"]) < TIERS.index(w["tier"]):
                    reasons.append(f"quality tier {m['tier']} below the required {w['tier']}")
                if tps["mid"] < w["peak_tps_year3"]:
                    reasons.append(f"throughput {tps['mid']:.0f} tokens/s below the year-3 peak {w['peak_tps_year3']:.0f}")
                hours = {lv: w["out_eq_tokens"] / tps[FLIP[lv]] / 3600 for lv in LEVELS}
                kwh = {lv: hours[lv] * (h["tdp_w"] - h["_idle"][FLIP[lv]]) / 1000 * h["_pue"][lv] for lv in LEVELS}
                out.append({
                    "id": f"{w['id']}|{m['id']}|{h['id']}", "workload_id": w["id"], "model_id": m["id"],
                    "hardware_id": h["id"], "feasible": not reasons, "reasons": reasons,
                    "tps": rng(tps["low"], tps["mid"], tps["high"], 0),
                    "gpu_hours_per_year": rng(*hours.values(), nd=1),
                    "kwh_per_year": rng(*kwh.values(), nd=1),
                    "co2_kg_per_year": rng(*(kwh[lv] * h["_grid"][lv] for lv in LEVELS), nd=2),
                })
    return out


# ------------------------------------------------------------------ scenarios
def _peak_year3(ws: list[dict], hours_day: float, growth: dict) -> float:
    """Busiest day of the combined daily series (not the sum of each workload's own peak)."""
    day = pd.concat([w["_daily"] for w in ws], axis=1).fillna(0).sum(axis=1)
    return float(day.max()) / (hours_day * 3600) * (1 + growth["mid"]) ** HORIZON_YEARS


def _choose_model(ws: list[dict], models: list[dict], h: dict, headroom: float, peak: float) -> tuple[dict | None, list[str]]:
    tier = max((w["tier"] for w in ws), key=TIERS.index)
    ok, why = [], []
    for m in models:
        tps = m["throughput"].get(h["gpu_class"])
        if tps is None:
            continue
        if vram_check(m["weights_gb"], h["vram_gb"], headroom) or TIERS.index(m["tier"]) < TIERS.index(tier):
            continue
        if tps["mid"] < peak:
            why.append(f"{m['label']}: {tps['mid']:.0f} tokens/s < peak {peak:.0f}")
            continue
        ok.append(m)
    if not ok:
        return None, why or [f"no catalogue model reaches tier «{tier}» and fits {h['vram_gb']} GB on {h['label']}"]
    ok.sort(key=lambda m: (-m["throughput"][h["gpu_class"]]["mid"], m["weights_gb"]))
    return ok[0], [m["id"] for m in ok[1:]]


def _scenario(sid: str, label: str, ws: list[dict], kept: list[dict], h: dict, models: list[dict], cat: dict,
              growth: dict, fx: dict, measures: dict, info: dict) -> dict:
    A = cat["assumptions"]
    headroom = float(A["vram_headroom"]["value"])
    pd_chf = float(A["person_day_chf"]["value"])
    peak = _peak_year3(ws, float(A["office_hours_per_workday"]["value"]), growth)
    m, why = _choose_model(ws, models, h, headroom, peak)
    base = {"id": sid, "label": label, "hardware_id": h["id"], "workload_ids": [w["id"] for w in ws],
            "kept_on_api": [w["id"] for w in kept], "peak_tps_year3": round(peak, 1)}
    if m is None:
        return base | {"model_id": None, "alternatives": [], "feasible": False, "reasons": why}
    alternatives = why

    tps = m["throughput"][h["gpu_class"]]
    on_h = float(h["on_hours_per_year"])
    eq = sum(w["out_eq_tokens"] for w in ws)
    setup_days = {lv: _lvl(A["setup_platform_days"]["value"])[lv] + _lvl(A["setup_per_workload_days"]["value"])[lv] * len(ws)
                  + h["extra_setup_days"] for lv in LEVELS}
    setup = {lv: setup_days[lv] * pd_chf for lv in LEVELS}
    maint = {lv: _lvl(A["maint_days_per_year"]["value"])[lv] * pd_chf for lv in LEVELS}
    rent = {lv: (on_h * h["_per_h"][lv]) if h["_per_h"] else 12 * h["_per_m"][lv] for lv in LEVELS}
    yearly = {lv: rent[lv] + maint[lv] for lv in LEVELS}

    api0 = {k: {lv: sum(w["api"][k][lv] for w in ws) for lv in LEVELS} for k in ("cost_chf", "kwh", "co2_kg")}
    api3 = {k: {lv: sum(api0[k][lv] * (1 + growth[lv]) ** y for y in range(1, HORIZON_YEARS + 1)) for lv in LEVELS}
            for k in api0}

    kwh3, co23, hours_y1, kwh_y = {}, {}, {}, {}
    for lv in LEVELS:
        e, per = 0.0, []
        for y in range(1, HORIZON_YEARS + 1):
            gh = min(eq * (1 + growth["mid"]) ** y / tps[FLIP[lv]] / 3600, on_h)
            if y == 1:
                hours_y1[lv] = gh
            ey = energy_kwh(on_h, gh, h["_idle"][lv], h["tdp_w"], h["_host"][lv], h["_pue"][lv])
            per.append(ey)
            e += ey
        kwh3[lv], co23[lv], kwh_y[lv] = e, e * h["_grid"][lv], per
    local3 = {lv: setup[lv] + HORIZON_YEARS * yearly[lv] for lv in LEVELS}

    # Year by year for the charts (mid): all 7 tools on the API vs this option (moved tools local + the rest on the API).
    every = ws + kept
    api_all = {k: sum(w["api"][k]["mid"] for w in every) for k in ("cost_chf", "kwh", "co2_kg")}
    api_kept = {k: sum(w["api"][k]["mid"] for w in kept) for k in ("cost_chf", "kwh", "co2_kg")}
    by_year = [{"year": 0, "api_only": {"cost_chf": 0.0, "kwh": 0.0, "co2_kg": 0.0},
                "with_option": {"cost_chf": round(setup["mid"], 2), "kwh": 0.0, "co2_kg": 0.0}}]
    for y in range(1, HORIZON_YEARS + 1):
        g = (1 + growth["mid"]) ** y
        by_year.append({"year": y,
                        "api_only": {k: round(api_all[k] * g, 2) for k in api_all},
                        "with_option": {"cost_chf": round(yearly["mid"] + api_kept["cost_chf"] * g, 2),
                                        "kwh": round(kwh_y["mid"][y - 1] + api_kept["kwh"] * g, 2),
                                        "co2_kg": round(kwh_y["mid"][y - 1] * h["_grid"]["mid"] + api_kept["co2_kg"] * g, 2)}})

    def diff(api: dict, loc: dict) -> dict:
        return {"low": api["low"] - loc["high"], "mid": api["mid"] - loc["mid"], "high": api["high"] - loc["low"]}

    sav_cost, sav_kwh, sav_co2 = diff(api3["cost_chf"], local3), diff(api3["kwh"], kwh3), diff(api3["co2_kg"], co23)
    be = {"low": breakeven_month(setup["low"], yearly["low"] / 12, api0["cost_chf"]["high"], growth["high"]),
          "mid": breakeven_month(setup["mid"], yearly["mid"] / 12, api0["cost_chf"]["mid"], growth["mid"]),
          "high": breakeven_month(setup["high"], yearly["high"] / 12, api0["cost_chf"]["low"], growth["low"])}
    util = hours_y1["mid"] / on_h if on_h else 0.0

    interacts = []
    for role in h["measure_roles"]:
        meas = measures.get(f"_role:{role}", {})
        mid_ = meas.get("id")
        if not mid_:
            continue
        in_pkg = mid_ in measures.get("_package", [])
        if role == "on_demand":
            interacts.append({"measure_id": mid_, "title": meas.get("title", mid_), "in_package": in_pkg,
                              "cost_chf_per_year": rng(*rent.values(), nd=0),
                              "note": f"{mid_} stops gpu-ml-01 outside quarter days. Inference in office hours keeps it on "
                                      f"{on_h:.0f} h/year: this rent is the part of the {mid_} saving given back "
                                      f"(counted in the local cost). {mid_} itself is not changed."})
        elif role == "move":
            interacts.append({"measure_id": mid_, "title": meas.get("title", mid_), "in_package": in_pkg,
                              "cost_chf_per_year": None,
                              "note": f"Same move as {mid_}; its {h['extra_setup_days']:.1f} person-days are in the setup."})

    max_tier = max((w["tier"] for w in ws), key=TIERS.index)
    pros = [
        f"Private data of {len(ws)} workload(s) stays on {h['provider']} in {h['location']} under company control "
        f"instead of an external AI API (EU, location not stated).",
        f"API cost avoided over {HORIZON_YEARS} years: CHF {api3['cost_chf']['mid']:,.0f} (growing {growth['mid']:.0%}/year).",
        f"{HORIZON_YEARS}-year CO2: {co23['mid']:,.0f} kg local vs {api3['co2_kg']['mid']:,.0f} kg via API.",
        "No per-token price risk: cost is fixed and known in advance.",
    ]
    if h["owned"]:
        pros.append(f"Uses hardware the company already has ({h['entity_id']}); GPU busy {util:.0%} of on-hours instead of ≈ 5 %.")
    cons = [
        f"Setup {setup_days['mid']:.0f} person-days (CHF {setup['mid']:,.0f}), "
        f"{setup['mid'] / float(info['budget_chf']):.0%} of this round's CHF {info['budget_chf']:,.0f} budget.",
        f"Operations {_lvl(A['maint_days_per_year']['value'])['mid']:.0f} person-days/year "
        f"(CHF {maint['mid']:,.0f}): model updates, patching, incidents.",
        f"Quality: {m['label']} ({m['quality_note']}) instead of {', '.join(sorted({x for w in ws for x in w['models_today']}))}.",
        "Single GPU = single point of failure; no provider SLA on model quality.",
    ]
    if max_tier == "advanced":
        cons.append("Includes advanced tasks (agents, contracts): the open-weight gap is largest there.")
    if m["languages"].startswith("partial"):
        multi = [x for x in models if x["id"] in alternatives and not x["languages"].startswith("partial")]
        alt = f" Alternative with full DE / FR / IT support: {multi[0]['label']}." if multi else ""
        cons.append(f"Languages: {m['label']} is {m['languages']}; texts in Basel are mostly German, test quality first.{alt}")
    if kept:
        cons.append(f"{len(kept)} advanced workload(s) stay on the API: two AI stacks to run.")
    if h["id"].startswith("hw:gpu-ml-01"):
        cons.append("Quarterly training (ticket T-1101) shares gpu-ml-01 on quarter days: inference slows down then.")
    if sav_cost["mid"] < 0:
        cons.append(f"Dearer than the API over {HORIZON_YEARS} years: CHF {-sav_cost['mid']:,.0f} more.")
    if h["estimate"]:
        cons.append(f"Price or capacity is an estimate: {h['note']}")
    if be["mid"] is None:
        cons.append(f"No break-even within {HORIZON_YEARS * 12} months.")

    calc = {
        "formula": (f"local = setup + {HORIZON_YEARS} × (rent + operations); rent = on-hours × CHF/h (or 12 × CHF/month); "
                    f"API = Σ_y baseline API × (1 + token growth)^y; kWh = (on-h × (idle W + host W) + GPU-h × (TDP − idle W)) "
                    f"/ 1000 × PUE; GPU-h = output-equivalent tokens / tokens/s / 3600; CO2 = kWh × grid"),
        "inputs": [
            {"name": "output-equivalent tokens (baseline year)", "value": round(eq), "unit": "tokens", "source": "ai_usage.csv"},
            {"name": "tokens/s (mid)", "value": tps["mid"], "unit": "tokens/s", "source": "local_ai_catalog.yaml"},
            {"name": "on-hours per year", "value": round(on_h), "unit": "h", "source": "dim_date (workdays) / catalogue"},
            {"name": "rent per year (mid)", "value": round(rent["mid"], 2), "unit": "CHF", "source": "local_ai_catalog.yaml / azure_costs.csv"},
            {"name": "setup person-days (mid)", "value": setup_days["mid"], "unit": "person-days", "source": "local_ai_catalog.yaml"},
            {"name": "token growth (mid)", "value": round(growth["mid"] * 100, 2), "unit": "%/year", "source": "forecast.json"},
            {"name": "API baseline cost (mid)", "value": round(api0["cost_chf"]["mid"], 2), "unit": "CHF/year", "source": "fact_cost"},
        ],
        "factor_ids": sorted({h["pue_factor_id"], h["grid_factor_id"], "energy_per_1000_tokens"}),
        "source_files": ["ai_usage.csv", "azure_costs.csv", "server_inventory.csv", "local_ai_catalog.yaml"],
        "row_count": int(sum(w["calc"]["row_count"] for w in ws)),
        "value_status": "estimated",
        "issue_ids": sorted({i for w in ws for i in w["calc"]["issue_ids"]})[:20],
        "note": "Advisory only: no number in measures, summary or forecast is changed.",
    }
    if h["id"] == "hw:gpu-ml-01":
        calc["inputs"].append({"name": "vs today (24/7, without the on-demand measure): extra rent", "value": 0, "unit": "CHF/year",
                               "source": "gpu-ml-01 already billed 24/7 in the baseline"})

    return base | {
        "model_id": m["id"], "alternatives": alternatives, "feasible": True, "reasons": [],
        "utilisation": round(util, 4),
        "api_3y": _metrics(api3["cost_chf"], api3["kwh"], api3["co2_kg"], fx),
        "local_3y": _metrics(local3, kwh3, co23, fx),
        "savings_3y": _metrics(sav_cost, sav_kwh, sav_co2, fx),
        "setup_chf": rng(*setup.values(), nd=0), "yearly_chf": rng(*yearly.values(), nd=0),
        "breakeven_month": be,
        "interacts_with": interacts, "pros": pros, "cons": cons, "calc": calc, "by_year": by_year,
    }


def _measures(ctx: Context) -> dict:
    """Measures by id, plus the GPU measures found by what they do (ids can change between analyses):
    «on_demand» = a schedule on gpu-ml without relocation, «move» = a schedule on gpu-ml moved to Zurich."""
    m = read_output(ctx, "measures.json") or {}
    out = {x["id"]: x for x in m.get("measures", [])}
    out["_package"] = (m.get("package") or {}).get("measure_ids", [])
    for x in m.get("measures", []):
        if x.get("type") != "schedule" or x.get("status") == "blocked":
            continue
        eff = x.get("effects") or []
        if not eff or any(e.get("scope") != "res:gpu-ml" for e in eff):
            continue
        role = "move" if any(e.get("relocate_to") == "CH" for e in eff) else "on_demand"
        out.setdefault(f"_role:{role}", x)
    return out


# ------------------------------------------------------------------ build / run
def build(ctx: Context) -> dict:
    cat, F, FR, fx = _catalog(), load_factors(), _factor_ranges(ctx), _fx(ctx)
    growth, growth_src = _token_growth(ctx)
    workloads = _workloads(ctx, F, cat, growth, fx)
    hardware, info = _hardware(ctx, cat, F, FR, fx)
    info["budget_chf"] = float((ctx.config.get("advisor") or {}).get("budget_chf", 16500))
    models = cat["models"]
    headroom = float(cat["assumptions"]["vram_headroom"]["value"])
    fits = _fits(workloads, models, hardware, headroom, growth)
    measures = _measures(ctx)

    scenarios = []
    adv = [w for w in workloads if w["tier"] == "advanced"]
    rest = [w for w in workloads if w["tier"] != "advanced"]
    for h in hardware:
        scenarios.append(_scenario(f"sc:all@{h['id']}", f"All 7 workloads on {h['label']}", workloads, [], h,
                                   models, cat, growth, fx, measures, info))
        if adv and rest:
            scenarios.append(_scenario(f"sc:hybrid@{h['id']}", f"Hybrid: {len(rest)} workloads on {h['label']}, agents stay on the API",
                                       rest, adv, h, models, cat, growth, fx, measures, info))
        for w in workloads:
            s = _scenario(f"sc:{w['id']}@{h['id']}", f"{w['label']} alone on {h['label']}", [w],
                          [x for x in workloads if x is not w], h, models, cat, growth, fx, measures, info)
            if s["feasible"]:
                scenarios.append(s)

    feas = [s for s in scenarios if s["feasible"]]
    by_cost = max(feas, key=lambda s: s["savings_3y"]["cost_chf"]["mid"], default=None)
    by_co2 = max(feas, key=lambda s: s["savings_3y"]["co2_kg"]["mid"], default=None)
    by_wl = []
    for w in workloads:
        cand = [f for f in fits if f["workload_id"] == w["id"] and f["feasible"]]
        best = min(cand, key=lambda f: f["kwh_per_year"]["mid"], default=None)
        by_wl.append({"workload_id": w["id"], "fit": best["id"] if best else None})

    A = cat["assumptions"]
    assumptions = [{"id": k, "label": k.replace("_", " "), "value": v["value"] if not isinstance(v["value"], dict)
                    else rng(v["value"]["low"], v["value"]["mid"], v["value"]["high"]),
                    "unit": v["unit"], "source": v["source"], "estimate": bool(v["estimate"])} for k, v in A.items()]
    assumptions += [
        {"id": "token_growth", "label": "token growth", "value": rng(*(growth[lv] * 100 for lv in LEVELS)),
         "unit": "%/year", "source": growth_src, "estimate": True},
        {"id": "gpu_ml_hourly_chf", "label": "gpu-ml-01 price per GPU-hour",
         "value": rng(*info["gpu_ml_hourly_chf"].values(), nd=3), "unit": "CHF/h",
         "source": f"azure_costs.csv: baseline cost / {info['gpu_ml_billed_hours']:.0f} billed GPU-hours ({info['gpu_rows']} rows)",
         "estimate": False},
        {"id": "office_hours_per_year", "label": "office hours per year", "value": round(info["office_hours"]),
         "unit": "h", "source": f"business_calendar.csv: {info['workdays']} workdays in the baseline × "
                                f"{A['office_hours_per_workday']['value']} h", "estimate": True},
        {"id": "fx_baseline_avg", "label": "exchange rates (baseline average)",
         "value": {"EUR": round(fx["EUR"], 4), "USD": round(fx["USD"], 4)}, "unit": "CHF per unit",
         "source": "exchange_rates.csv", "estimate": False},
    ]

    public_hw = [{k: v for k, v in h.items() if not k.startswith("_")} for h in hardware]
    return {
        "advisory": True,
        "horizon_years": HORIZON_YEARS,
        "note": ("Information only, a human decides. Compares the company's own AI workloads on open-weight models "
                 "with the current APIs; no number in measures, summary or forecast is changed."),
        "catalog_date": cat["source_date"],
        "workloads": [{k: v for k, v in w.items() if not k.startswith("_")} for w in workloads],
        "models": [{k: v for k, v in m.items()} for m in models],
        "hardware": public_hw,
        "fits": fits,
        "scenarios": scenarios,
        "best": {"by_cost": by_cost["id"] if by_cost else None, "by_co2": by_co2["id"] if by_co2 else None,
                 "by_workload": by_wl},
        "assumptions": assumptions,
        "panel": _panel(workloads, public_hw, models, scenarios, by_cost, by_co2, growth),
    }


# ------------------------------------------------------------------ panel (data + short texts for the UI)
def _panel(workloads: list[dict], hardware: list[dict], models: list[dict], scenarios: list[dict],
           by_cost: dict | None, by_co2: dict | None, growth: dict) -> dict:
    """The four sections of the Local AI panel: how we compute and which servers exist, the two options,
    the year-by-year charts, and where local models make a difference. Numbers stay numbers; texts are short."""
    hw = {h["id"]: h for h in hardware}
    md = {m["id"]: m for m in models}
    wl = {w["id"]: w for w in workloads}
    label = lambda wid: wl[wid]["label"]  # noqa: E731

    # 1. computational model + servers
    def price(h):
        v = (h["price_chf_per_hour"] or {}).get("mid", 0)
        if h["owned"] and not v:
            return {"text": f"already running ({h['entity_id'][4:]}), no extra cost", "chf": 0, "per": None}
        if h["owned"]:   # own GPU: office hours cost the part of the on-demand saving given back
            return {"text": f"own server; CHF {v:.2f}/h for office hours (on-demand saving given back)", "chf": round(v, 2), "per": "hour"}
        if h["price_chf_per_hour"]:
            return {"text": f"CHF {v:.2f}/h, office hours", "chf": round(v, 2), "per": "hour"}
        v = h["price_chf_per_month"]["mid"]
        return {"text": f"CHF {v:,.0f}/month, always on", "chf": round(v), "per": "month"}

    servers = [{"hardware_id": h["id"], "label": h["label"], "gpu": h["gpu"], "vram_gb": h["vram_gb"],
                "location": h["location"], "owned": h["owned"], "price": price(h), "estimate": h["estimate"]}
               for h in hardware]
    model = {
        "title": "How we compute",
        "steps": [
            {"label": "Demand", "text": f"Tokens per tool from ai_usage.csv (baseline year), growing {growth['mid']:.0%}/year as in the forecast."},
            {"label": "Fit", "text": "A model qualifies if it fits the GPU memory, reaches the tool's quality level and handles the year-3 peak."},
            {"label": "Energy", "text": "kWh = (idle and host power while on + generation at full power) × PUE; CO₂ = kWh × grid of the site."},
            {"label": "Cost", "text": f"Setup + rent + operations over {HORIZON_YEARS} years, against the API fees the tools pay today."},
        ],
        "servers_title": "Servers that could run local models",
        "servers": servers,
    }

    # 2. options
    picks = [("best_value", "Best value", by_cost), ("lowest_co2", "Lowest CO₂", by_co2)]
    if by_cost and by_co2 and by_cost["id"] == by_co2["id"]:
        picks = [("best_value", "Best value and lowest CO₂", by_cost)]
    options = []
    for oid, title, s in picks:
        if not s:
            continue
        h, m = hw[s["hardware_id"]], md[s["model_id"]]
        r = lambda x: {"low": x["low"], "mid": x["mid"], "high": x["high"]}  # noqa: E731
        options.append({
            "id": oid, "title": title, "scenario_id": s["id"],
            "summary": f"{len(s['workload_ids'])} tools on {m['label']} · {h['label']}; "
                       f"{len(s['kept_on_api'])} stay on the API.",
            "model": m["label"], "hardware": h["label"], "owned": h["owned"],
            "tools_local": [label(w) for w in s["workload_ids"]], "tools_api": [label(w) for w in s["kept_on_api"]],
            "figures": [
                {"key": "api_3y", "label": f"API, {HORIZON_YEARS} years", "unit": "CHF", **r(s["api_3y"]["cost_chf"])},
                {"key": "local_3y", "label": f"In-house, {HORIZON_YEARS} years", "unit": "CHF", **r(s["local_3y"]["cost_chf"])},
                {"key": "saving", "label": "Saving", "unit": "CHF", **r(s["savings_3y"]["cost_chf"])},
                {"key": "breakeven", "label": "Break-even", "unit": "months", **s["breakeven_month"]},
                {"key": "co2_api", "label": "CO₂ via API", "unit": "kg", **r(s["api_3y"]["co2_kg"])},
                {"key": "co2_local", "label": "CO₂ in-house", "unit": "kg", **r(s["local_3y"]["co2_kg"])},
            ],
        })

    # 3. charts (mid values): all tools on the API vs each option
    ref = (by_cost or by_co2 or {}).get("by_year") or []
    def series(key, cumulative, years):
        out = [{"id": "api_only", "label": "All on the API (today)",
                "values": _series([y["api_only"][key] for y in ref], cumulative, years)}]
        for o in options:
            s = next(x for x in scenarios if x["id"] == o["scenario_id"])
            out.append({"id": o["id"], "label": o["title"],
                        "values": _series([y["with_option"][key] for y in s["by_year"]], cumulative, years)})
        return out
    all_x = [y["year"] for y in ref]
    yr_x = [y for y in all_x if y > 0]
    xl = lambda xs: ["Start" if x == 0 else f"Year {x}" for x in xs]  # noqa: E731
    charts = [
        {"id": "cost", "title": "Cost, cumulative", "unit": "CHF", "x": all_x, "x_labels": xl(all_x),
         "series": series("cost_chf", True, all_x), "caption": "Setup first, then rent and operations; the lines cross at break-even."},
        {"id": "kwh", "title": "Electricity per year", "unit": "kWh", "x": yr_x, "x_labels": xl(yr_x),
         "series": series("kwh", False, yr_x), "caption": "API energy is estimated per token (0.1–2 Wh per 1,000 tokens)."},
        {"id": "co2", "title": "CO₂ per year", "unit": "kg", "x": yr_x, "x_labels": xl(yr_x),
         "series": series("co2_kg", False, yr_x), "caption": "Location-based: grid of the server's site vs EU average for the API."},
    ]

    # 4. where local models make a difference (privacy first; coding stays on the API)
    local_in = {w["id"]: [o["id"] for o in options
                          if w["id"] in next(x for x in scenarios if x["id"] == o["scenario_id"])["workload_ids"]]
                for w in workloads}
    tools = []
    for w in sorted(workloads, key=lambda w: -w["api"]["cost_chf"]["mid"]):
        notes = []
        if w.get("excluded"):
            notes.append(f"Code agent ({w['excluded']['share']:.0%} of its use) stays on the API: coding is out of scope.")
        if local_in[w["id"]]:
            for t in w["tasks"]:
                if t["tier"] == "advanced" and t["cost_share"] > 0:
                    task = TASK_LABEL.get(t["task_type"], t["task_type"].lower())
                    notes.append(f"Includes {task} ({t['cost_share']:.0%} of its cost): test quality before moving it.")
        elif w["tier"] == "advanced":
            notes.append("Agent tasks need a frontier model: stays on the API.")
        both = len(local_in[w["id"]]) == len(options) and options
        tools.append({"workload_id": w["id"], "label": w["label"], "private_data": w["why_private"],
                      "api_chf_per_year": round(w["api"]["cost_chf"]["mid"]), "api_co2_kg_per_year": round(w["api"]["co2_kg"]["mid"], 1),
                      "local_in": local_in[w["id"]],
                      "status": ("Local in both options" if both and len(options) > 1 else
                                 "Local" if both else
                                 f"Local in {next(o['title'] for o in options if o['id'] == local_in[w['id']][0])}"
                                 if local_in[w["id"]] else "Stays on the API"),
                      "notes": notes})
    first = options[0] if options else None
    moved = [t for t in tools if first and first["id"] in t["local_in"]]
    spend = sum(t["api_chf_per_year"] for t in tools) or 1
    return {
        "model": model,
        "options": options,
        "charts": charts,
        "tools": {
            "title": "Where local models make a difference",
            "intro": "Local models keep private business data in-house. Coding stays on the API (agreed with ALTYCA).",
            "headline": (f"{len(moved)} of {len(tools)} tools ({sum(t['api_chf_per_year'] for t in moved) / spend:.0%} of today's "
                         f"API spend) can run locally in «{first['title']}».") if first else "",
            "items": tools,
        },
    }


def _series(values: list[float], cumulative: bool, years: list[int]) -> list[float]:
    """Values for the chart's x positions (year 0 = setup); cumulative for cost."""
    out, acc = [], 0.0
    for y, v in enumerate(values):
        acc = acc + v if cumulative else v
        if y in years:
            out.append(round(acc, 1))
    return out


def run(ctx: Context) -> None:
    write_json(ctx, "local_ai.json", build(ctx))
