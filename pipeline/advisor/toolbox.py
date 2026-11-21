"""Toolbox (code): turns the fact sheet into candidate measures, findings and the
«deliberately kept on» list. Instant, deterministic, no LLM.

The levers are GENERIC actions that work for any SME, not rules for this case:
pause idle hours, run in office hours, downsize, decommission forgotten servers,
move load to a cleaner grid, remove inactive seats, use a smaller AI model for
routine tasks, clean up storage, skip unchanged builds, shorten retention.
Numbers come from the data; every share has a CAP (the physical maximum, e.g.
the idle share) that the agents may lower but never exceed.

Conscious optimisation («not everything unused may be switched off»):
  - resources that are idle BY DESIGN (emergency fallback, backups and data under
    retention, audit/regulatory reports) are never proposed for reduction: they go
    to the «kept on» list with the reason;
  - regular peaks in the usage data (e.g. every quarter) count as needed time;
  - production / critical resources start as «a person decides».
"""
from __future__ import annotations

import pandas as pd

ROUTINE_TASKS = ["Classify", "Translate", "Summarise", "Draft texts"]   # a small model handles most of these
BLOCK_TYPES = ("block",)


class Toolbox:
    def __init__(self, facts: dict, constraints: list[dict], data_as_of: str):
        self.F = facts["facts"]
        clean = lambda d: {k: (None if v is pd.NA or (isinstance(v, float) and v != v) else v) for k, v in d.items()}  # noqa: E731
        self.res = {r["id"]: clean(r) for r in facts["resources"]}
        self.srv = {s["id"]: clean(s) for s in facts["servers"]}
        self.lic = {l["id"]: l for l in facts["licences"]}
        self.ai = facts["ai_tasks"]
        self.constraints = constraints
        self.asof = pd.Timestamp(data_as_of)
        self.candidates: list[dict] = []
        self.findings: list[dict] = []
        self.kept_on: list[dict] = []
        self.blocked_targets = {t for c in constraints if c["type"] in BLOCK_TYPES for t in c["applies_to"]}
        self.offered = {p: set(v) for p, v in facts.get("regions_offered", {}).items()}

    def can_move(self, rid, to="CH") -> bool:
        """Relocation rule (data_center_locations.csv): only to a location the resource's provider offers."""
        from ..insights.regions import provider_key
        prov = provider_key((self.res.get(rid) or {}).get("provider"))
        return bool(self.offered) and prov in self.offered and to in self.offered[prov]

    # -------------------------------------------------------------- helpers
    def f(self, fid, default=None):
        x = self.F.get(fid)
        return x["value"] if x else default

    def owner(self, rid):
        return (self.res.get(rid) or {}).get("decides") or "Head of IT"

    def is_prod(self, rid):
        r = self.res.get(rid) or {}
        return r.get("environment") == "prod" or r.get("criticality_masterdata") == "high"

    def add(self, key, area, lever, title, description, effects, effort, rid, basis, finding=None,
            status=None, start="2026-10-01", group=None, risks="", assumptions=""):
        self.candidates.append({
            "key": key, "area": area, "lever": lever, "title": title, "description": description,
            "effects": effects, "effort_days": effort, "owner_role": self.owner(rid),
            "proposed_status": status or ("human" if self.is_prod(rid) else "ok"),
            "start_date": start, "group": group or rid, "basis_fact_ids": basis, "finding": finding,
            "risks": risks, "assumptions": assumptions})

    def finding(self, key, kind, title, scopes, evidence, explanation):
        self.findings.append({"key": key, "kind": kind, "title": title, "scopes": scopes,
                              "evidence_fact_ids": [e for e in evidence if e in self.F], "explanation": explanation})
        return key

    @staticmethod
    def eff(scope, share, energy=None, relocate=None, removes=None):
        """removes="idle_hours": the effect removes hours (or capacity) WITHOUT work, so the calculator values the
        energy saved at idle power (energy model), not at the average power of the scope."""
        e = share if energy is None else energy
        out = {"scope": scope, "cost_share": round(share, 4), "energy_share": round(e, 4),
               "cost_cap": round(share, 4), "energy_cap": round(e, 4), "relocate_to": relocate}
        if removes:
            out["removes"] = removes
        return out

    # -------------------------------------------------------------- levers
    def idle_clusters(self):
        for rid in self.res:
            idle = self.f(f"{rid}.idle_share")
            if idle is None or idle < 0.3:
                continue
            loc = self.res[rid]["location"]
            fk = self.finding(f"W-{rid}", "waste", f"{rid} runs {self.f(f'{rid}.running_h_per_day', 24):.0f} h/day but is idle "
                              f"{idle:.0%} of that time", [f"res:{rid}"],
                              [f"{rid}.idle_share", f"{rid}.active_h_weekday", f"{rid}.active_h_weekend", f"{rid}.running_h_per_day",
                               f"{rid}.nodes_avg", f"{rid}.co2", f"{rid}.cost"],
                              "Running hours without work: the cluster could pause when idle.")
            share = idle * 0.85               # start-up times and safety margin
            self.add(f"C-{rid}-pause", "platform", "schedule", f"Auto-pause {rid} when idle",
                     f"{rid} pauses after 30 min without work and starts on demand; protection windows stay covered by "
                     "scheduled starts.", [self.eff(f"res:{rid}", share, removes="idle_hours")], 3 if not self.is_prod(rid) else 4, rid,
                     [f"{rid}.idle_share"], fk, group=f"res:{rid}",
                     risks="start-up delay for the first query; scheduled jobs must trigger a start",
                     assumptions=f"{share:.0%} of running hours removed (idle share × 0.85 safety margin)")
            if loc in ("DE", "IE") and self.can_move(rid):
                self.add(f"C-{rid}-pause-ch", "platform", "relocate", f"Auto-pause {rid} and move it to Zurich",
                         f"As auto-pause, plus migrate {rid} from {loc} to the Zurich region (cleaner grid).",
                         [self.eff(f"res:{rid}", share, relocate="CH", removes="idle_hours")], (3 if not self.is_prod(rid) else 4) + 3, rid,
                         [f"{rid}.idle_share", f"grid.{loc}", "grid.CH"], fk, group=f"res:{rid}",
                         status="human", risks="migration of data and jobs; latency and price of the Zurich region to check",
                         assumptions=f"{share:.0%} of hours removed; remaining load runs on the Zurich grid")

    def gpu(self):
        for rid, r in self.res.items():
            u = self.f(f"{rid}.gpu_utilisation")
            run = self.f(f"{rid}.hours_running_share")
            if u is None or u > 0.2 or (run is not None and run < 0.9):
                continue
            needed = 12 / 365 + u              # quarterly training days + current average use as on-demand time
            share = max(0.0, 1 - needed) * 0.95
            fk = self.finding(f"W-{rid}", "waste", f"{rid} runs around the clock at {u:.0%} GPU utilisation", [f"res:{rid}"],
                              [f"{rid}.gpu_utilisation", f"{rid}.hours_running_share", f"{rid}.gpu_util_weekly_median",
                               f"{rid}.gpu_util_weekly_max", f"{rid}.cost_on_quarter_days_1_3", f"{rid}.co2"],
                              "The GPU is needed for the quarterly training (peaks) and occasional use, not 24/7.")
            self.add(f"C-{rid}-ondemand", "platform", "schedule", f"Run {rid} only for training and on demand",
                     "Stopped by default; started automatically for days 1–3 of each quarter and on request.",
                     [self.eff(f"res:{rid}", share, removes="idle_hours")], 1.5, rid, [f"{rid}.gpu_utilisation"], fk, group=f"res:{rid}",
                     risks="on-demand start takes minutes", assumptions=f"keeps quarterly training days and current usage time; removes {share:.0%}")
            if r["location"] in ("DE", "IE") and self.can_move(rid):
                self.add(f"C-{rid}-ondemand-ch", "platform", "relocate", f"Run {rid} on demand and move it to Zurich",
                         f"As on-demand, plus move the GPU server from {r['location']} to Zurich.",
                         [self.eff(f"res:{rid}", share, relocate="CH", removes="idle_hours")], 3.5, rid, [f"{rid}.gpu_utilisation", "grid.CH"], fk,
                         group=f"res:{rid}", status="human", risks="GPU availability and price in Zurich to check")

    def servers(self):
        zombies, office = [], []
        for sid, s in self.srv.items():
            if sid in self.blocked_targets or s["type"] == "dr":
                continue
            days = self.f(f"{sid}.days_since_login", 0)
            cpu = self.f(f"{sid}.cpu_avg", 1)
            idle_w = self.f(f"{sid}.weeks_under_10pct_cpu", 0)
            up = self.f(f"{sid}.uptime_share", 0)
            if days > 180 and cpu < 0.01:
                zombies.append(sid)
            elif s["environment"] in ("test", "dev") and idle_w >= 0.5 and up >= 0.95:
                office.append(sid)
        if zombies:
            rid = self.srv[zombies[0]]["resource"]
            fk = self.finding("W-zombies", "waste", f"{len(zombies)} servers without a login for over 180 days and without load",
                              zombies, [f"{z}.days_since_login" for z in zombies] + [f"{z}.cpu_avg" for z in zombies],
                              "Forgotten servers: no human login and no load, some without owner or for completed projects.")
            self.add("C-zombies", "servers", "decommission", f"Decommission {len(zombies)} forgotten servers",
                     f"Snapshot, then delete {', '.join(z[4:] for z in zombies)} after the owner confirms.",
                     [self.eff(z, 1.0) for z in zombies], 1, rid, [f"{z}.days_since_login" for z in zombies], fk,
                     group="servers:zombies", status="human", risks="hidden dependency; keep a snapshot for 90 days")
        if office:
            rid = self.srv[office[0]]["resource"]
            share = (1 - 60 / 168) * 0.85      # office hours Mon–Fri 07–19 = 60 of 168 h
            fk = self.finding("W-always-on-test", "waste", f"{len(office)} test/QA servers run 24/7 but are mostly idle",
                              office, [f"{s}.weeks_under_10pct_cpu" for s in office] + [f"{s}.cpu_peak_week" for s in office],
                              "Test servers are needed during working hours and test campaigns, not at night and weekends.")
            self.add("C-test-office-hours", "servers", "schedule", f"Run {len(office)} test/QA servers in office hours only",
                     "Automatic stop at 19:00 and on weekends, start at 07:00; kept on during announced test campaigns.",
                     [self.eff(s, share, removes="idle_hours") for s in office], max(1, 0.15 * len(office)), rid,
                     [f"{s}.weeks_under_10pct_cpu" for s in office], fk, group="servers:office",
                     risks="night-time test jobs must be rescheduled", assumptions="60 of 168 h kept, × 0.85 margin")
            # alternative on the whole resource: downsize to the capacity actually used
            u = self.f(f"{rid}.cpu_utilisation", 0.1)
            keep = max(u / 0.5, 0.25)          # target 50 % utilisation, keep at least a quarter
            self.add(f"C-{rid}-rightsize", "servers", "rightsize", f"Downsize {rid} to the capacity actually used",
                     f"Shrink {rid} to {keep:.0%} of its vCPU (target 50 % CPU); scale up for test campaigns.",
                     [self.eff(f"res:{rid}", 1 - keep, removes="idle_hours")], 2, rid, [f"{rid}.cpu_utilisation", f"{rid}.usage_vCPU-hour"],
                     fk, group="servers:office", status="human",
                     risks="protected servers in the resource (e.g. emergency fallback) must keep their size")

    def licences(self):
        for lid, l in self.lic.items():
            act = self.f(f"{lid}.active_share", 1)
            if act >= 0.8:
                continue
            share = (1 - act) * 0.9            # keep 10 % of the inactive seats as buffer
            notice = self.f(f"{lid}.notice_days", 30)
            to_end = self.f(f"{lid}.days_to_contract_end", 0)
            if l["billing"] == "monthly":
                start = (self.asof + pd.Timedelta(days=notice + 25)).strftime("%Y-%m-01")
            else:
                start = l["contract_end"] if to_end >= notice else (pd.Timestamp(l["contract_end"]) + pd.DateOffset(years=1)).strftime("%Y-%m-%d")
            fk = self.finding(f"W-{lid}", "waste", f"{l['tool']}: {act:.0%} of paid seats active", [lid],
                              [f"{lid}.active_share", f"{lid}.seats_purchased", f"{lid}.seats_active", f"{lid}.cost_inactive_seats",
                               f"{lid}.days_to_contract_end", f"{lid}.notice_days"], "Seats paid but not used in the last 30 days.")
            self.add(f"C-{lid[4:]}", "licences", "licence", f"Remove inactive {l['tool']} seats",
                     f"Reduce {l['tool']} seats to the active users plus a small buffer at the next possible date ({start}).",
                     [self.eff(lid, share, energy=0.0)], 0.5 if l["billing"] == "monthly" else 0.75, None,
                     [f"{lid}.active_share"], fk, group=lid, status="human", start=start,
                     risks="department heads confirm the seat list", assumptions=f"{share:.0%} of seats removed; annual contracts change at renewal")
            self.candidates[-1]["owner_role"] = "Head of Finance"

    def ai_models(self):
        for a in self.ai:
            if a["model_class"] != "large" or a["task"] not in ROUTINE_TASKS:
                continue
            cost = self.f(f"{a['id']}.cost", 0)
            if cost < 1000:
                continue
            moved = 0.6                        # quality-critical requests stay on the large model
            fk = self.finding(f"W-{a['id']}", "waste", f"{a['resource']}: «{a['task']}» runs on a large model", [a["id"]],
                              [f"{a['id']}.cost", f"{a['id']}.energy", "ai.small_to_large_price_ratio"],
                              "Routine tasks a small model handles at ~30 % of the price.")
            self.add(f"C-{a['resource']}-{a['task'].replace(' ', '')}", "ai_other", "model_switch",
                     f"{a['resource']}: «{a['task']}» on a small model by default",
                     "Route the task to the small model; the large model stays available for complex cases.",
                     [self.eff(a["id"], moved * 0.70, energy=moved * 0.75)], 1, a["resource"],
                     [f"{a['id']}.cost", "ai.small_to_large_price_ratio"], fk, group=a["id"], status="human",
                     risks="quality pilot with users first", assumptions="60 % of requests moved; 70 % cost and 75 % energy saved on them")

    def extras(self):
        st = self.f("dp-storage.stale_gb_no_retention", 0)
        cat = self.f("dp-storage.catalog_gb", 0)
        if st and cat:
            share = st / cat * 0.8
            fk = self.finding("W-stale-tables", "waste", f"{st / 1000:.1f} TB of tables not read for over a year (no retention)",
                              ["res:dp-storage"], ["dp-storage.stale_gb_no_retention", "dp-storage.stale_gb_retention_unknown",
                                                   "dp-storage.stale_gb_retention_required", "dp-storage.catalog_gb"],
                              "Old tables nobody reads; tables under retention are excluded.")
            self.add("C-stale-tables", "ai_other", "storage", "Archive or delete unread tables without retention",
                     "Owners review the list; unread tables without retention are archived to cold storage or deleted.",
                     [self.eff("res:dp-storage", share)], 2, "dp-storage", ["dp-storage.stale_gb_no_retention"], fk,
                     group="res:dp-storage", status="human", risks="owners must confirm; personal data rules apply")
        nightly = self.f("cicd.minutes_share_unchanged_nightly")
        if nightly:
            fk = self.finding("W-ci-nightly", "waste", f"{self.f('cicd.nightly_without_changes_share', 0):.0%} of nightly builds run without changes",
                              ["res:cicd"], ["cicd.nightly_without_changes_share", "cicd.minutes_share_unchanged_nightly", "cicd.rerun_share"],
                              "Builds that repeat the same result.")
            self.add("C-ci-skip", "ai_other", "pipeline", "Skip nightly builds when nothing changed",
                     "The nightly build runs only if there were commits since the last one.",
                     [self.eff("res:cicd", nightly)], 0.5, "cicd", ["cicd.minutes_share_unchanged_nightly"], fk, group="res:cicd")
        unopened = self.f("ai-report.unopened_share")
        if unopened and unopened > 0.5:
            fk = self.finding("W-report-agent", "waste", f"{unopened:.0%} of the report agent's reports are never opened",
                              ["res:ai-report"], ["ai-report.unopened_share"], "Reports produced for nobody.")
            self.add("C-report-agent", "ai_other", "other", "Generate agent reports on request only",
                     "The report agent runs when someone asks for a report instead of on a schedule.",
                     [self.eff("res:ai-report", unopened * 0.8)], 0.5, "ai-report", ["ai-report.unopened_share"], fk,
                     group="res:ai-report", status="human")
        long_logs = self.f("logs.volume_share_retention_365d")
        if long_logs:
            share = long_logs * (1 - 90 / 365) * 0.7
            fk = self.finding("W-log-retention", "waste", f"{long_logs:.0%} of new logs are kept 365 days", ["res:logs"],
                              ["logs.volume_share_retention_365d", "logs.volume_share_retention_90d"], "Long log retention multiplies stored volume.")
            self.add("C-log-retention", "ai_other", "storage", "Shorten log retention from 365 to 90 days where allowed",
                     "Services without a retention obligation keep logs 90 days; older logs go to cheap archive.",
                     [self.eff("res:logs", share)], 1, "logs", ["logs.volume_share_retention_365d"], fk, group="res:logs",
                     status="human", risks="compliance check per service")

    # ------------------------------------------------- kept on deliberately
    def kept(self):
        seen = set()
        for c in self.constraints:
            if c["type"] in BLOCK_TYPES:
                for t in c["applies_to"]:
                    if t not in seen:
                        seen.add(t)
                        self.kept_on.append({"target": t, "reason": c["summary"], "constraint_id": c["id"], "source": c["source"]})
        # edge-case candidates the gate will block (shown to the jury as «not recommended»)
        for t in sorted(seen):
            scope = t if t.startswith("srv:") else f"res:{t}"
            if scope.startswith("res:") and t not in self.res:
                continue
            self.add(f"X-{t.replace(':', '-')}", "edge", "decommission" if scope.startswith("srv:") else "storage",
                     f"Reduce or switch off {t}", f"{t} looks underused, but it is protected.",
                     [self.eff(scope, 0.5)], 0.5, t if not t.startswith("srv:") else self.srv.get(t, {}).get("resource"),
                     [], None, group=f"edge:{t}", status="blocked",
                     risks="protected: see «deliberately kept on»")

    def drivers(self):
        top = sorted(self.res, key=lambda r: -(self.f(f"{r}.co2", 0) or 0))[:3]
        for r in top:
            self.finding(f"D-{r}", "driver", f"{r}: {self.f(f'{r}.share_co2', 0):.0%} of CO₂, {self.f(f'{r}.share_cost', 0):.0%} of cost",
                         [f"res:{r}"], [f"{r}.co2", f"{r}.share_co2", f"{r}.share_cost", f"{r}.energy", f"grid.{self.res[r]['location']}"],
                         "One of the biggest CO₂ sources.")

    def run(self) -> dict:
        for lever in (self.drivers, self.idle_clusters, self.gpu, self.servers, self.licences, self.ai_models,
                      self.extras, self.kept):
            lever()
        return {"candidates": self.candidates, "findings": self.findings, "kept_on": self.kept_on}
