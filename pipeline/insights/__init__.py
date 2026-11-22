"""Insights from the extra sources: one card per topic for the dashboard and the
assistant, plus facts for the advisor. Pure code, computed from the harmonized
tables before the advisor runs (so the advisor can use them) and exported after.

    build(ctx)          → {"cards": [...], "powerbi": {...}, "regions": {...}, ...}
    advisor_facts(ctx)  → [(id, value, unit, statement, source), ...]
    offered(ctx)        → regions each provider offers (advisor safety rule)

Which source feeds which card: see SOURCES and docs/extra-sources.md.
"""
from __future__ import annotations

from ..harmonize.context import Context
from . import m365, powerbi, projects, regions, sources
from .common import Insight
from .regions import offered, provider_key  # noqa: F401 (re-exported for the advisor)

TOPICS = {
    "powerbi": powerbi.compute,
    "regions": regions.compute,
    "data_catalog": sources.catalog,
    "logs": sources.logs,
    "ci_builds": sources.cicd,
    "ai_agents": sources.agents,
    "web_traffic": sources.web,
    "backups": sources.backups,
    "closed_projects": projects.closed,
    "project_footprint": projects.footprint,
    "m365": m365.compute,
}

# extra source → where it is used (everything that reaches the user, beyond loading)
SOURCES = {
    "extra/data_platform_jobs.csv": ["carbon-aware timing (jobs.json)", "protection windows for the advisor", "example Q3"],
    "extra/data_catalog_tables.csv": ["card data_catalog", "advisor facts dp-storage.*", "consistency check (reconcile)"],
    "extra/powerbi_usage.csv": ["card powerbi (report hygiene, capacity downsizing)", "advisor facts pbi-kap.*", "pbi-07 lock"],
    "extra/ai_agent_runs.jsonl": ["card ai_agents", "advisor facts ai-report.*, ai-agent2.*", "consistency check (reconcile)"],
    "extra/ai_invoice_monthly.csv": ["AI invoice vs gateway contradiction", "invoice adjustment in the totals"],
    "extra/m365_usage.csv": ["card m365 (licence cross-check, energy check)", "advisor facts saas-m365.*"],
    "extra/web_traffic.csv": ["card web_traffic", "advisor fact web-cdn.bot_share", "consistency check (reconcile)"],
    "extra/ci_pipeline_runs.jsonl": ["card ci_builds", "advisor facts cicd.*", "relocation option (regions)"],
    "extra/log_volume.csv": ["card logs", "advisor facts logs.*"],
    "extra/backup_chains.csv": ["card backups (blocked edge case)", "advisor facts st-backup.*"],
    "extra/data_center_locations.csv": ["card regions (relocation options, unused regions)", "advisor safety rule: only offered regions"],
    "extra/provider_monthly_report.csv": ["provider report vs invoices contradiction (limits)"],
    "extra/headcount.csv": ["FTE allocation key", "forecast seat growth", "card project_footprint"],
    "extra/projects.csv": ["card closed_projects", "card project_footprint", "advisor facts (project status)"],
    "extra/project_hours_monthly.csv": ["card project_footprint (CO2 per client project, hours as allocation key)"],
}


def compute_all(ctx: Context) -> dict[str, Insight]:
    if not hasattr(ctx, "_insights"):
        ctx._insights = {name: fn(ctx) for name, fn in TOPICS.items()}
    return ctx._insights


def advisor_facts(ctx: Context) -> list[tuple]:
    return [f for ins in compute_all(ctx).values() for f in ins.facts]


def build(ctx: Context) -> dict:
    ins = compute_all(ctx)
    out = {"cards": [i.card for i in ins.values()], "sources": [{"file": f, "used_for": u} for f, u in SOURCES.items()]}
    out["powerbi"] = ins["powerbi"].extra
    out["regions"] = ins["regions"].extra
    out["closed_projects"] = ins["closed_projects"].extra["closed_projects"]
    out["projects"] = ins["project_footprint"].extra["projects"]
    return out
