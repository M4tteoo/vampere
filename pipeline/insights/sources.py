"""Insight cards for the extra sources whose numbers so far only reached the advisor:
data catalogue, logs, CI builds, AI agents, web traffic, backups.

Same thresholds as the advisor's fact sheet (pipeline/advisor/facts.py), so a card and
the advisor never disagree. Potentials are upper bounds on the resource each source
details (catalogue → dp-storage, logs → logs, CI → cicd, agents → ai-report / ai-agent2,
web → web-cdn, backups → st-backup), as share of its recurring baseline.
"""
from __future__ import annotations

import pandas as pd

from ..harmonize.context import Context
from .common import Insight, card, potential, resource_sums, role

SHORT_RETENTION_DAYS = 90


def _asof(ctx: Context) -> pd.Timestamp:
    return pd.Timestamp(str(ctx.config["advisor"]["data_as_of"]))


def catalog(ctx: Context) -> Insight:
    src, rid = "extra/data_catalog_tables.csv", "dp-storage"
    dc = ctx.tables["stg_data_catalog_tables"]
    days = (_asof(ctx) - pd.to_datetime(dc["last_read"])).dt.days
    stale = dc["last_read"].isna() | (days > 365)
    keep = dc["retention_required"] == "yes"
    removable = (stale | (dc["schema"] == "tmp")) & ~keep & dc["retention_required"].notna()
    unknown = stale & dc["retention_required"].isna()
    total = dc["size_gb"].sum()
    share = dc.loc[removable, "size_gb"].sum() / total
    base = resource_sums(ctx, rid)
    c = card("data_catalog", "Data platform: tables nobody reads", [src, "azure_costs.csv"],
             f"{dc.loc[removable, 'size_gb'].sum() / 1000:,.1f} TB of {total / 1000:,.1f} TB are unread for a year or "
             f"temporary and not under retention ({share:.0%} of the stored volume); "
             f"{dc.loc[unknown, 'size_gb'].sum() / 1000:,.1f} TB need an owner's answer on retention.",
             [("tables", len(dc), "tables"), ("catalogue volume", total, "GB"),
              ("unread > 1 year, no retention", dc.loc[stale & (dc["retention_required"] == "no"), "size_gb"].sum(), "GB"),
              ("schema tmp", dc.loc[dc["schema"] == "tmp", "size_gb"].sum(), "GB"),
              ("unread, retention unknown", dc.loc[unknown, "size_gb"].sum(), "GB"),
              ("unread but retention required (keep)", dc.loc[stale & keep, "size_gb"].sum(), "GB")],
             potential_=potential(base, share, share), action="archive or delete unread and temporary tables",
             status="human", decided_by=role(ctx, rid),
             protected=["tables with retention_required = yes stay, even if never read"],
             entity_ids=[f"res:{rid}"], row_count=len(dc),
             formula="share = GB of (unread > 1 year or schema tmp) without retention / catalogue GB; "
                     "catalogue GB = dp-storage GB-days / 365 (checked in reconcile); potential = share × dp-storage",
             fact_ids=["dp-storage.stale_gb_no_retention", "dp-storage.tmp_schema_gb", "dp-storage.removable_share"])
    return Insight(c, [("dp-storage.removable_share", share, "share",
                        "share of stored GB that is unread > 1 year or temporary and not under retention", src),
                       ("dp-storage.stale_gb_retention_unknown_share", dc.loc[unknown, "size_gb"].sum() / total, "share",
                        "share of stored GB unread > 1 year with an empty retention flag (owner must answer)", src)])


def logs(ctx: Context) -> Insight:
    src, rid = "extra/log_volume.csv", "logs"
    b0, b1 = ctx.baseline
    lv = ctx.tables["stg_log_volume"]
    lv = lv[lv["date"].between(b0, b1)]
    stored = (lv["log_gb"] * lv["retention_days"]).sum()            # steady state: GB kept ∝ volume × days
    shorter = (lv["log_gb"] * lv["retention_days"].clip(upper=SHORT_RETENTION_DAYS)).sum()
    share = 1 - shorter / stored
    by_ret = lv.groupby("retention_days")["log_gb"].sum() / lv["log_gb"].sum()
    base = resource_sums(ctx, rid)
    c = card("logs", "Logs kept for a year", [src, "hoster_invoice.csv"],
             f"{by_ret.get(365, 0):.0%} of the log volume is kept 365 days. Keeping {SHORT_RETENTION_DAYS} days unless "
             f"a service needs more would cut the stored log volume by {share:.0%}.",
             [("services", lv["service"].nunique(), "services"), ("log volume per year", lv["log_gb"].sum(), "GB"),
              ("kept 365 days", by_ret.get(365, 0), "share"), ("kept 180 days", by_ret.get(180, 0), "share"),
              ("kept 90 days", by_ret.get(90, 0), "share")],
             potential_=potential(base, share, share), action=f"default retention {SHORT_RETENTION_DAYS} days, longer only where required",
             status="human", decided_by=role(ctx, rid), entity_ids=[f"res:{rid}"], row_count=len(lv),
             protected=["services with a legal or security retention need keep theirs (to be confirmed per service)"],
             formula=f"stored GB ∝ Σ volume × retention days; share = 1 − Σ volume × min(retention, {SHORT_RETENTION_DAYS}) / Σ volume × retention",
             fact_ids=["logs.volume_share_retention_365d", "logs.retention_90d_stored_share_saved"])
    return Insight(c, [("logs.retention_90d_stored_share_saved", share, "share",
                        f"share of stored log GB saved if every service kept logs at most {SHORT_RETENTION_DAYS} days", src)])


def cicd(ctx: Context) -> Insight:
    src, rid = "extra/ci_pipeline_runs.jsonl", "cicd"
    b0, b1 = ctx.baseline
    ci = ctx.tables["stg_ci_pipeline_runs"]
    c_ = ci[ci["date"].between(b0, b1)]
    nf = c_[c_["pipeline"] == "nightly-full"]
    unchanged = nf["commits_since_last_nightly"] == 0
    minutes_share = nf.loc[unchanged, "duration_seconds"].sum() / c_["duration_seconds"].sum()
    base = resource_sums(ctx, rid)
    runners = c_["runner"].value_counts()
    c = card("ci_builds", "Builds that change nothing", [src, "aws_costs.csv"],
             f"{unchanged.mean():.0%} of the nightly builds run with no new commit; skipping them saves "
             f"{minutes_share:.1%} of all build minutes. All builds run in {runners.index[0]}.",
             [("runs", len(c_), "runs"), ("nightly builds without changes", unchanged.mean(), "share"),
              ("build minutes on unchanged nightlies", minutes_share, "share"),
              ("re-runs", (c_["trigger"] == "rerun").mean(), "share"),
              ("runs in Dublin", runners.iloc[0] / len(c_), "share")],
             potential_=potential(base, minutes_share, minutes_share), action="skip the nightly build when nothing changed",
             status="ok", decided_by=role(ctx, rid), entity_ids=[f"res:{rid}"], row_count=len(c_),
             formula="share = build seconds of nightly builds with 0 commits since the last one / all build seconds; "
                     "runner minutes are billed (2 × build time, checked in reconcile)",
             fact_ids=["cicd.nightly_without_changes_share", "cicd.minutes_share_unchanged_nightly", "cicd.rerun_share"])
    return Insight(c, [])


def agents(ctx: Context) -> Insight:
    src = "extra/ai_agent_runs.jsonl"
    b0, b1 = ctx.baseline
    ag = ctx.tables["stg_ai_agent_runs"]
    ag = ag[ag["date"].between(b0, b1)]
    rep = ag[ag["agent"] == "report-agent"]
    unopened = (rep["report_opened"] == 0).mean()
    res = ag[ag["agent"] == "research-agent"]
    retries = res["retries"].fillna(0)
    by_agent = ag.groupby("agent").agg(runs=("run_id", "count"), retries=("retries", "mean"),
                                       tokens=("usage_tokens_out", "sum"))
    base = resource_sums(ctx, "ai-report")
    c = card("ai_agents", "AI agents: reports nobody opens", [src, "ai_usage.csv"],
             f"{unopened:.0%} of the report-agent's reports are never opened; generating them on request would remove "
             f"most of its usage. The research-agent retries {retries.mean():.1f} times per run on average.",
             [("agent runs", len(ag), "runs"), ("report-agent outputs never opened", unopened, "share"),
              ("research-agent retries per run", retries.mean(), "retries"),
              ("research-agent runs with retries", (retries > 0).mean(), "share")],
             potential_=potential(base, unopened, unopened), action="report-agent on request instead of on schedule",
             status="ok", decided_by=role(ctx, "ai-report"), entity_ids=["res:ai-report", "res:ai-agent2"], row_count=len(ag),
             formula="share of report-agent runs whose report was never opened × ai-report recurring baseline",
             fact_ids=["ai-report.unopened_share", "ai-agent2.research_retries_per_run"])
    c["by_agent"] = [{"agent": a, "runs": int(x.runs), "retries_per_run": round(float(x.retries), 2),
                      "output_tokens": int(x.tokens)} for a, x in by_agent.iterrows()]
    return Insight(c, [("ai-agent2.research_retries_per_run", retries.mean(), "retries",
                        "average retries per research-agent run (part of ai-agent2)", src)])


def web(ctx: Context) -> Insight:
    src, rid = "extra/web_traffic.csv", "web-cdn"
    b0, b1 = ctx.baseline
    wt = ctx.tables["stg_web_traffic"]
    w = wt[wt["date"].between(b0, b1)]
    gb = w["gb_out_scaled"].sum()
    bots = (w["bot_share_pct"] / 100 * w["gb_out_scaled"]).sum() / gb
    base = resource_sums(ctx, rid)
    c = card("web_traffic", "Web traffic: a third are bots", [src, "hoster_invoice.csv"],
             f"{bots:.0%} of the delivered web volume goes to bots (sampled data scaled ×{int(w['sample_rate'].mode().iat[0])}).",
             [("delivered volume", gb, "GB/year"), ("bot share of volume", bots, "share"),
              ("requests", w["requests_scaled"].sum(), "requests/year")],
             potential_=potential(base, bots, bots), action="block or rate-limit unwanted bots (keep search engines)",
             status="human", decided_by=role(ctx, rid), entity_ids=[f"res:{rid}"], row_count=len(w),
             protected=["useful bots (search engines, monitoring) must keep access"],
             formula="bot share = Σ bot % × GB / Σ GB (sample rate applied); upper bound: all bot traffic removed",
             fact_ids=["web-cdn.bot_share"])
    return Insight(c, [])


def backups(ctx: Context) -> Insight:
    src, rid = "extra/backup_chains.csv", "st-backup"
    bc = ctx.tables["stg_backup_chains"]
    n = bc.groupby("source")["backup_tool"].nunique()
    trip = bc[bc["source"].isin(n[n == 3].index)]
    third = trip.sort_values("size_gb", ascending=False).groupby("source").nth(2)
    share = third["size_gb"].sum() / bc["size_gb"].sum()
    no_test = bc["last_restore_test"].isna().sum()
    base = resource_sums(ctx, rid)
    c = card("backups", "Backups: three tools, legal retention", [src, "aws_costs.csv", "it_tickets.csv"],
             f"{int((n == 3).sum())} of {bc['source'].nunique()} sources are backed up by all three tools "
             f"({share:.0%} of backup volume in third copies), and {no_test} copies have never been restore-tested. "
             "The archive is under a 10-year legal retention: deletion is blocked.",
             [("sources", bc["source"].nunique(), "sources"), ("sources in 3 tools", int((n == 3).sum()), "sources"),
              ("third copies", share, "share of GB"), ("copies without restore test", int(no_test), "copies"),
              ("GB with 10-year retention", bc.loc[bc["retention_days"] >= 3650, "size_gb"].sum() / bc["size_gb"].sum(), "share")],
             potential_=potential(base, share, share), action="drop third copies (only where no retention applies)",
             status="blocked", decided_by=role(ctx, rid), entity_ids=[f"res:{rid}"], row_count=len(bc),
             protected=["10-year legal retention (T-1039); deletion request rejected (T-1195)"],
             formula="share = GB of the third copy of sources in 3 tools / all backup GB",
             fact_ids=["st-backup.sources_in_3_tools", "st-backup.third_copy_share", "st-backup.copies_without_restore_test"])
    return Insight(c, [("st-backup.copies_without_restore_test", int(no_test), "copies",
                        "backup copies never restore-tested (a risk, not a saving)", src)])
