"""Mock of web/public/data/items.json: quick per-object facts for the 3D scene, read straight from the case CSVs.

The backend pipeline will produce the same file with cleaned data. Until then this script gives every clickable
object (seat, licence, report screen, SaaS terminal, AI device, agent) real numbers for the baseline year.

Run: python3 web/scripts/items_mock.py   (from the repo root)
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "data/case"
OUT = ROOT / "web/public/data/items.json"
LAYOUT = ROOT / "web/public/models/layout.json"
START, END = "2025-09-01", "2026-08-31"

CC = {4000: "consulting", 4100: "sales", 4200: "finance", 4300: "marketing", 4400: "hr", 4500: "it", 4900: "management"}
DEPT = {"Consulting": "consulting", "Sales": "sales", "Finance": "finance", "Marketing": "marketing",
        "HR": "hr", "IT": "it", "Management": "management"}
LOCKED_REPORTS = {"pbi-07": "Required by internal audit: must be kept."}


def csv(name):
    return pd.read_csv(CASE / name, encoding="utf-8-sig")


def in_year(df, col):
    d = pd.to_datetime(df[col])
    return df[(d >= START) & (d <= END)]


def chf(v):
    return f"CHF {round(v):,}".replace(",", "'")


def num(v):
    return f"{round(v):,}".replace(",", "'")


def slug(s):
    return s.lower().replace(" ", "-")


items = {}
layout = json.load(open(LAYOUT))
ids = {i["id"] for i in layout}

# Power BI reports ---------------------------------------------------------------
pbi = in_year(csv("extra/powerbi_usage.csv"), "date")
for rid, g in pbi.groupby("resource_id"):
    views, refresh = g.view_count.fillna(0).sum(), g.refresh_count.fillna(0).sum()
    minutes = (g.refresh_count.fillna(0) * g.refresh_duration_min.fillna(0)).sum()
    months = max(1, g.date.str[:7].nunique())
    rare = views / months < 5
    state = "locked" if rid in LOCKED_REPORTS else ("waste" if rare and refresh > 0 else "ok")
    items[rid] = {
        "id": rid, "entity_id": "pbi-kap", "label": g.report.iloc[0], "kind": "report",
        "department": DEPT.get(g.department.iloc[0], "it"), "state": state,
        "headline": LOCKED_REPORTS.get(rid) or (f"Opened {num(views / months)} times a month, but refreshed {num(refresh / months)} times"
                                                 if rare else f"{num(views / months)} views a month"),
        "facts": [{"label": "Views per year", "value": num(views)},
                  {"label": "Refreshes per year", "value": num(refresh)},
                  {"label": "Refresh minutes per year", "value": num(minutes)}],
        "source": "extra/powerbi_usage.csv",
    }

# SaaS contracts per department ----------------------------------------------------
saas = in_year(csv("saas_contracts.csv"), "month")
saas = saas[saas.contract_status == "Final"]
fx = csv("exchange_rates.csv") if (CASE / "exchange_rates.csv").exists() else None
for (contract, cc), g in saas.groupby(["contract", "cost_center"]):
    dept = CC.get(cc)
    last = g.sort_values("month").iloc[-1]
    rid = f"saas:{slug(contract)}:{dept}"
    bought, active = int(last.licences_purchased), int(last.licences_active_30d)
    share = active / bought if bought else 1
    amount = g.amount.sum() * (0.9 if last.currency == "EUR" else 1)  # rough EUR→CHF for the mock
    entry = {
        "id": rid, "entity_id": "saas", "label": contract, "kind": "saas", "department": dept,
        "state": "waste" if share < 0.6 else "ok",
        "headline": f"{active} of {bought} licences used in the last 30 days",
        "facts": [{"label": "Cost per year", "value": chf(amount)},
                  {"label": "Active licences", "value": f"{active} / {bought}"},
                  {"label": "Contract end", "value": f"{last.contract_end} · notice {last.notice_period_days} days"}],
        "source": "saas_contracts.csv (Final rows only)",
    }
    if contract == "Microsoft 365":
        items[f"m365:{dept}"] = {**entry, "id": f"m365:{dept}", "kind": "m365"}
    else:
        items[rid] = entry

# AI subscriptions (licence pucks are grouped per product and department) ------------
subs = in_year(csv("ai_subscriptions.csv"), "month")
subs = subs[subs.contract_status == "Final"]
PRODUCT = {"ChatGPT Team": "chatgpt", "Microsoft Copilot": "copilot", "Claude Team": "claude"}
for (product, cc), g in subs.groupby(["product", "cost_center"]):
    key = PRODUCT.get(product, slug(product))
    last = g.sort_values("month").iloc[-1]
    rate = 0.8 if last.currency == "USD" else 1
    items[f"lic:{key}:{CC.get(cc)}"] = {
        "id": f"lic:{key}:{CC.get(cc)}", "entity_id": "ai-subs", "label": product, "kind": "licence",
        "department": CC.get(cc), "state": "waste" if last.licences_active_30d / last.licences_purchased < 0.6 else "ok",
        "headline": f"{int(last.licences_active_30d)} of {int(last.licences_purchased)} seats active",
        "facts": [{"label": "Cost per year", "value": chf(g.amount.sum() * rate)},
                  {"label": "Messages (30 days)", "value": num(last.messages_30d)},
                  {"label": "Contract end", "value": f"{last.contract_end} · notice {last.notice_period_days} days"}],
        "source": "ai_subscriptions.csv",
    }

# AI applications and agents ------------------------------------------------------------
ai = in_year(csv("ai_usage.csv"), "date")
AI_ITEM = {"ai-marketing": "ai-marketing", "ai-quote": "ai-quote", "ai-chatbot": "ai-chatbot"}
for (rid, dept), g in ai.groupby(["resource_id", "department"]):
    d = DEPT.get(dept)
    if rid == "ai-assistant":
        key = f"ai-assistant:{d}"
    elif f"{rid}:{d}" in ids:
        key = f"{rid}:{d}"  # shared AI app with one device per department (e.g. ai-chatbot:consulting)
    elif rid in AI_ITEM and rid not in items:
        key = AI_ITEM[rid]
        if not any(i.startswith(rid + ":") for i in ids):
            g = ai[ai.resource_id == rid]
    else:
        continue
    big = g[g.model_class == "large"].requests.sum() / max(1, g.requests.sum())
    tasks = g.groupby("task_type").requests.sum().sort_values(ascending=False)
    items[key] = {
        "id": key, "entity_id": "ai-api", "label": g.tool.iloc[0], "kind": "ai_app", "department": d,
        "state": "waste" if rid == "ai-marketing" else "ok",
        "headline": f"{num(g.requests.sum())} requests per year · {round(big * 100)}% on a large model",
        "facts": [{"label": "Cost per year", "value": chf(g.cost_chf.sum())},
                  {"label": "Tokens (in + out)", "value": num(g.tokens_in.sum() + g.tokens_out.sum())},
                  {"label": "Main task", "value": f"{tasks.index[0]} ({round(tasks.iloc[0] / tasks.sum() * 100)}%)"}],
        "source": "ai_usage.csv",
    }

runs = pd.read_json(CASE / "extra/ai_agent_runs.jsonl", lines=True)
runs = runs[(runs.start >= START) & (runs.start <= END + " 23:59")]
for agent, g in runs.groupby("agent"):
    key = f"agent:{agent}"
    if key not in ids:
        continue
    retries = g.retries.fillna(0).sum()
    outcomes = g.outcome.value_counts(normalize=True)
    top = outcomes.index[0]
    items[key] = {
        "id": key, "entity_id": "ai-api", "label": agent.replace("-", " ").capitalize(), "kind": "agent",
        "department": DEPT.get(g.department.mode().iloc[0]),
        "state": "waste" if agent == "report-agent" else "ok",
        "headline": f"{num(len(g))} runs per year · most frequent outcome: {top} ({round(outcomes.iloc[0] * 100)}%)",
        "facts": [{"label": "Retries", "value": num(retries)},
                  {"label": "Average steps", "value": f"{g.steps.mean():.1f}"},
                  {"label": "Trigger", "value": ", ".join(g.trigger.value_counts().index[:2])}],
        "source": "extra/ai_agent_runs.jsonl",
    }

OUT.write_text(json.dumps(sorted(items.values(), key=lambda x: x["id"]), ensure_ascii=False, indent=1))
missing = sorted(i for i in ids if i.startswith(("pbi-", "saas:", "agent:", "ai-")) and i not in items)
print(f"{len(items)} items → {OUT.relative_to(ROOT)}; layout ids without facts: {missing}")
