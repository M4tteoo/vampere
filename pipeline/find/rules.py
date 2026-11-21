"""Step 5 · Find: the biggest drivers and the waste, each backed by numbers.

Every rule is generic (thresholds in config.yaml «find») and reads structured
data only: utilisation, uptime, logins, project end dates, seats, catalogue
metadata. Ticket text is never interpreted: tickets are linked by resource and
date as context for a human.

impact = yearly amount at stake in the baseline year (not a saving: the
measures in Step 6 compute what can actually be saved, and Step 7 decides
what may be touched). Impacts of different findings can overlap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..export.frontend import SUMS, Calc, metrics, scale
from ..harmonize.context import Context


class Finder:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.cfg = ctx.config["find"]
        fc = ctx.tables["fact_cost"]
        self.fc = fc
        self.b = fc[fc["in_baseline"]]
        self.tot = self.b[SUMS].sum()
        self.calc = Calc(ctx, fc)
        b0, b1 = ctx.baseline
        act = ctx.tables["fact_activity"]
        self.act = act[(act["date"] >= b0) & (act["date"] <= b1)]
        self.findings: list[dict] = []
        self.flags: dict[str, set] = {}
        self.links: dict[str, set] = {}

    # ---------------------------------------------------------------- helpers
    def res_sums(self, rid):
        return self.b[self.b["resource_id"] == rid][SUMS].sum()

    def severity(self, s: pd.Series) -> str:
        share = max(s["cost_chf"] / self.tot["cost_chf"], s["co2_kg_mid"] / self.tot["co2_kg_mid"])
        sv = self.cfg["severity"]
        return "high" if share >= sv["high"] else "medium" if share >= sv["medium"] else "low"

    def tickets(self, rid, around=None, days=30):
        t = self.ctx.tables["stg_it_tickets"]
        t = t[t["resource_id"] == rid]
        if around:
            t = t[abs(pd.to_datetime(t["date"]) - pd.Timestamp(around)) <= pd.Timedelta(days=days)]
        return t["ticket_id"].tolist()

    def add(self, kind, title, entity_ids, evidence, impact_sums, rows, formula, note=None, flag=None, extra=None):
        fid = f"F-{len(self.findings) + 1:02d}"
        f = {"id": fid, "kind": kind, "title": title, "entity_ids": entity_ids, "evidence": evidence,
             "severity": self.severity(impact_sums), "impact": metrics(impact_sums), "measure_ids": [],
             "calc": self.calc(rows, formula, note=note)}
        if extra:
            f.update(extra)
        self.findings.append(f)
        for e in entity_ids:
            self.links.setdefault(e, set()).add(fid)
            if flag:
                self.flags.setdefault(e, set()).add(flag)
        return f

    @staticmethod
    def ev(statement, value, unit, *files):
        v = float(value) if value is not None else None
        return {"statement": statement, "value": None if v is None else round(v, 3), "unit": unit,
                "source_files": list(files)}

    # ----------------------------------------------------------------- drivers
    def drivers(self):
        g = self.b.groupby("resource_id")[SUMS].sum()
        top = set(g.nlargest(self.cfg["drivers_top_n"], "co2_kg_mid").index) | \
            set(g.nlargest(self.cfg["drivers_top_n"], "cost_chf").index)
        dim = self.ctx.tables["dim_resource"].set_index("resource_id")
        for rid in g.loc[list(top)].sort_values("co2_kg_mid", ascending=False).index:
            s = g.loc[rid]
            rows = self.b[self.b["resource_id"] == rid]
            loc = rows["location"].mode().iat[0]
            self.add("driver", f"{dim.loc[rid, 'tool']}: {s.co2_kg_mid / self.tot.co2_kg_mid:.0%} of CO₂, "
                     f"{s.cost_chf / self.tot.cost_chf:.0%} of cost", [f"res:{rid}", f"loc:{loc}"],
                     [self.ev("share of baseline CO₂ (location-based)", 100 * s.co2_kg_mid / self.tot.co2_kg_mid, "%", *rows.source_file.unique()),
                      self.ev("share of baseline cost", 100 * s.cost_chf / self.tot.cost_chf, "%", *rows.source_file.unique()),
                      self.ev("energy per year", s.kwh_mid, "kWh", *rows.source_file.unique())],
                     s, rows, "resource total in the baseline year (cost as billed; kWh × grid mix of "
                     f"{loc})", flag="driver")

    # ------------------------------------------------------------- waste rules
    def idle_clusters(self):
        a = self.act[self.act["metric"].isin(["runtime_h", "active_use_h"])]
        p = a.pivot_table(index="resource_id", columns="metric", values="value", aggfunc="sum")
        wd = a[pd.to_datetime(a["date"]).dt.dayofweek < 5].pivot_table(index="resource_id", columns="metric", values="value", aggfunc="mean")
        we = a[pd.to_datetime(a["date"]).dt.dayofweek >= 5].pivot_table(index="resource_id", columns="metric", values="value", aggfunc="mean")
        for rid, r in p.iterrows():
            idle = 1 - r["active_use_h"] / r["runtime_h"]
            if idle < self.cfg["idle_cluster_min_idle_ratio"]:
                continue
            s = self.res_sums(rid)
            rows = self.b[self.b["resource_id"] == rid]
            loc = rows["location"].mode().iat[0]
            nodes = self.act[(self.act["resource_id"] == rid) & (self.act["metric"] == "node_count")]["value"].mean()
            self.add("waste", f"{rid} runs {r.runtime_h / len(a.date.unique()):.0f} h a day but works "
                     f"{wd.loc[rid, 'active_use_h']:.1f} h on weekdays and {we.loc[rid, 'active_use_h']:.1f} h at weekends",
                     [f"res:{rid}"],
                     [self.ev("idle share of running hours", 100 * idle, "%", "data_platform_usage.csv"),
                      self.ev("average active use on weekdays", wd.loc[rid, "active_use_h"], "h/day", "data_platform_usage.csv"),
                      self.ev("average active use at weekends", we.loc[rid, "active_use_h"], "h/day", "data_platform_usage.csv"),
                      self.ev("running hours per day", r.runtime_h / len(a.date.unique()), "h/day", "data_platform_usage.csv"),
                      self.ev("average nodes", nodes, "nodes", "data_platform_usage.csv"),
                      self.ev("average CPU of the billed node-hours", 100 * rows["utilisation_cpu"].mean(), "%", "azure_costs.csv")],
                     s * idle, rows, "at stake = resource total × idle share (1 − active_use_h / runtime_h)",
                     note="Upper bound: idle hours still draw idle power and some windows may be protected (Step 7).",
                     flag="waste", extra={"rule": "idle_cluster", "location": loc})

    def low_gpu(self):
        g = self.b[self.b["unit"] == "GPU-hour"]
        hours_in_year = len(pd.date_range(*self.ctx.baseline)) * 24
        for rid, rows in g.groupby("resource_id"):
            u = np.average(rows["utilisation_gpu"], weights=rows["quantity"].clip(lower=1e-9))
            up = rows["quantity"].sum() / hours_in_year
            if u >= self.cfg["low_gpu_max_utilisation"] or up < self.cfg["always_on_min_uptime_share"]:
                continue
            srv = self.ctx.tables["dim_server"]
            srv = srv[srv["resource_id"] == rid].iloc[0]
            proj = self.ctx.tables["dim_project"].set_index("project_id")
            p = srv["project_id"]
            ev = [self.ev("average GPU utilisation", 100 * u, "%", "server_metrics_weekly.csv"),
                  self.ev("share of hours running", 100 * up, "%", "azure_costs.csv"),
                  self.ev("days since last human login (as of data date)",
                          (pd.Timestamp(self.cfg["data_as_of"]) - pd.Timestamp(srv["last_login"])).days, "days", "server_inventory.csv")]
            if isinstance(p, str) and p in proj.index and proj.loc[p, "status"] == "completed":
                ev.append(self.ev(f"tagged project {p} «{proj.loc[p, 'project_name']}» completed on {proj.loc[p, 'end']}: "
                                  "days running since", (pd.Timestamp(self.cfg["data_as_of"]) - pd.Timestamp(proj.loc[p, "end"])).days,
                                  "days", "projects.csv", "server_inventory.csv"))
            dd = pd.to_datetime(rows["charge_period_start"])
            train = (dd.dt.month.isin([1, 4, 7, 10]) & (dd.dt.day <= 3))
            share_outside = rows.loc[~train, "kwh_mid"].sum() / rows["kwh_mid"].sum()
            self.add("waste", f"GPU server runs around the clock at {100 * u:.0f} % GPU utilisation",
                     [f"res:{rid}", f"srv:{srv['server_id']}"], ev, rows[SUMS].sum() * share_outside, rows,
                     "at stake = resource total outside the quarterly training days (days 1–3 of Jan/Apr/Jul/Oct)",
                     note=f"related tickets (context only): {', '.join(self.tickets(rid)) or 'none'}",
                     flag="waste", extra={"rule": "low_gpu"})

    def low_cpu_servers(self):
        srv = self.ctx.tables["dim_server"]
        met = self.ctx.tables["stg_server_metrics_weekly"]
        b0, b1 = self.ctx.baseline
        w = met[(met["week_start"] >= b0) & (met["week_start"] <= b1)].copy()
        w["idle_week"] = w["cpu_avg_pct"] / 100 < self.cfg["low_cpu_max_utilisation"]
        m = w.groupby("server_id").agg(
            cpu=("cpu_avg_pct", "mean"), peak=("cpu_avg_pct", "max"), up=("uptime_h", "sum"),
            weeks=("uptime_h", "size"), idle_weeks=("idle_week", "sum"))
        m["uptime_share"] = m["up"] / (m["weeks"] * 168)
        m["idle_week_share"] = m["idle_weeks"] / m["weeks"]
        s = srv.set_index("server_id").join(m)
        s = s[s["resource_id"] != "gpu-ml"]
        # idle = under the CPU threshold in most weeks (not on the yearly average)
        low = s[(s["idle_week_share"] >= self.cfg["low_cpu_min_idle_week_share"])
                & (s["uptime_share"] >= self.cfg["always_on_min_uptime_share"])]
        for rid, grp in low.groupby("resource_id"):
            allsrv = s[s["resource_id"] == rid]
            share = (grp["vcpu"] * grp["up"]).sum() / (allsrv["vcpu"] * allsrv["up"]).sum()
            rows = self.b[self.b["resource_id"] == rid]
            q = rows.groupby("charge_period_start")["quantity"].sum()
            ev = [self.ev("servers always on and under 10 % CPU in at least 3 of 4 weeks", len(grp), "servers", "server_metrics_weekly.csv", "server_inventory.csv"),
                  self.ev("their weeks under 10 % CPU", grp["idle_weeks"].sum(), f"of {int(grp['weeks'].sum())} weeks", "server_metrics_weekly.csv"),
                  self.ev("their average CPU over the year (incl. busy weeks)", grp["cpu"].mean(), "%", "server_metrics_weekly.csv"),
                  self.ev("their highest weekly CPU (busy period)", grp["peak"].max(), "%", "server_metrics_weekly.csv"),
                  self.ev("their vCPU", grp["vcpu"].sum(), "vCPU", "server_inventory.csv"),
                  self.ev("billed vCPU-hours per day (baseline year)", q.mean(), "vCPU-h/day", rows.source_file.iat[0])]
            shift = self.ctx.tables["anomaly_candidates"]
            shift = shift[(shift["resource_id"] == rid) & (shift["kind"] == "level_shift")]
            for sh in shift.itertuples():
                before = self.fc[(self.fc["resource_id"] == rid) & (self.fc["charge_period_start"] < sh.start)].groupby("charge_period_start")["quantity"].sum().tail(30).mean()
                ev.append(self.ev(f"level shift on {sh.start}: billed vCPU-h/day before", before, "vCPU-h/day", rows.source_file.iat[0]))
            proj = self.ctx.tables["dim_project"]
            done = proj[(proj["status"] == "completed") & proj["end"].notna()]
            note = f"related tickets (context only): {', '.join(self.tickets(rid)) or 'none'}. "
            note += "Completed projects for context: " + ", ".join(f"{r.project_id} «{r.project_name}» ended {r.end}" for r in done.itertuples())
            self.add("waste", f"{len(grp)} {rid} servers run 24/7 but are nearly idle in "
                     f"{grp['idle_weeks'].sum() / grp['weeks'].sum():.0%} of weeks",
                     [f"res:{rid}"] + [f"srv:{x}" for x in grp.index], ev, rows[SUMS].sum() * share, rows,
                     "at stake = resource total × share of the low-CPU servers (vCPU × uptime hours)",
                     note=note, flag="waste", extra={"rule": "low_cpu_always_on", "servers": grp.index.tolist()})

    def zombies(self):
        srv = self.ctx.tables["dim_server"].copy()
        asof = pd.Timestamp(self.cfg["data_as_of"])
        srv["days"] = (asof - pd.to_datetime(srv["last_login"])).dt.days
        z = srv[(srv["days"] > self.cfg["zombie_min_days_since_login"])
                & (srv["cpu_utilisation_30d_pct"] / 100 <= self.cfg["zombie_max_cpu"])]
        if z.empty:
            return
        ents = {e["id"]: e for e in self._server_entities()}
        tot = pd.Series(0.0, index=SUMS)
        for sid in z["server_id"]:
            m = ents[f"srv:{sid}"]["metrics"]
            for col, (k, l) in _COLMAP.items():
                tot[col] += m[k][l] or 0
        rows = self.b[self.b["resource_id"].isin(z["resource_id"].unique())]
        proj = self.ctx.tables["dim_project"].set_index("project_id")
        ev = [self.ev(f"{r.server_id}: days since last human login", r.days, "days", "server_inventory.csv") for r in z.itertuples()]
        ev += [self.ev(f"{r.server_id}: CPU (30 days)", r.cpu_utilisation_30d_pct, "%", "server_inventory.csv") for r in z.itertuples()]
        ev += [self.ev(f"{r.server_id}: no owner cost center", 1, "flag", "server_inventory.csv") for r in z.itertuples() if pd.isna(r.owner_cost_center)]
        for r in z.itertuples():
            if isinstance(r.project_id, str) and r.project_id in proj.index and proj.loc[r.project_id, "status"] == "completed":
                ev.append(self.ev(f"{r.server_id}: project {r.project_id} completed on {proj.loc[r.project_id, 'end']}", 1, "flag", "projects.csv"))
        self.add("waste", f"{len(z)} forgotten servers: no login for over {self.cfg['zombie_min_days_since_login']} days, no load",
                 [f"srv:{s}" for s in z["server_id"]], ev, tot, rows,
                 "at stake = sum of the servers' shares of their resource (vCPU × uptime hours)",
                 flag="waste", extra={"rule": "zombie_server", "servers": z["server_id"].tolist()})

    def unused_licences(self):
        lic = self.b[self.b["source_file"].isin(["ai_subscriptions.csv", "saas_contracts.csv"])].copy()
        stg = pd.concat([self.ctx.tables["stg_ai_subscriptions"].assign(source_file="ai_subscriptions.csv"),
                         self.ctx.tables["stg_saas_contracts"].assign(source_file="saas_contracts.csv")])
        act = stg.set_index(["source_file", "source_row"])["licences_active_30d"]
        lic["active"] = [act.get((f, r), np.nan) for f, r in zip(lic["source_file"], lic["source_row"])]
        lic["inactive_share"] = (1 - lic["active"] / lic["quantity"]).clip(lower=0)
        for tool, rows in lic.groupby("tool"):
            share = rows["active"].sum() / rows["quantity"].sum()
            if share >= self.cfg["licence_max_active_share"]:
                continue
            at_stake = pd.Series({c: (rows[c] * rows["inactive_share"]).sum() if c.startswith("cost") else 0.0 for c in SUMS})
            last = rows[rows["month"] == rows["month"].max()]
            groups = rows.groupby("department").apply(lambda g: g["active"].sum() / g["quantity"].sum(), include_groups=False)
            src = rows["source_file"].iat[0]
            stg_t = stg[(stg["source_file"] == src) & (stg[("product" if src == "ai_subscriptions.csv" else "contract")] == tool)]
            self.add("waste", f"{tool}: {share:.0%} of paid seats active",
                     [f"lic:{tool}@{d}" for d, u in groups.items() if u < self.cfg["licence_max_active_share"]],
                     [self.ev("active / purchased seats (baseline-year average)", 100 * share, "%", src),
                      self.ev("seats purchased (last month)", last["quantity"].sum(), "seats", src),
                      self.ev("seats active in the last 30 days (last month)", last["active"].sum(), "seats", src),
                      self.ev("cost of inactive seats per year", at_stake["cost_chf"], "CHF", src, "exchange_rates.csv"),
                      self.ev("days until contract end (as of data date)",
                              (pd.Timestamp(stg_t["contract_end"].max()) - pd.Timestamp(self.cfg["data_as_of"])).days, "days", src),
                      self.ev("notice period", stg_t["notice_period_days"].max(), "days", src)],
                     at_stake, rows, "at stake = Σ monthly cost × (1 − active / purchased seats)",
                     note="Inactive seats cost money but use almost no energy (energy counts active use), so CO₂ at stake ≈ 0.",
                     flag="waste", extra={"rule": "unused_licences", "billing": stg_t["billing"].iat[0]})

    def oversized_model(self):
        ai = self.ctx.tables["stg_ai_usage"]
        b0, b1 = self.ctx.baseline
        g = self.b[(self.b["source_file"] == "ai_usage.csv")].merge(
            ai[["source_row", "task_type", "model_class"]], on="source_row")
        sel = g[g["task_type"].isin(self.cfg["simple_tasks"]) & (g["model_class"] == "large")]
        for (rid, task), rows in sel.groupby(["resource_id", "task_type"]):
            r = 1 - self.cfg["small_large_cost_ratio"]
            e = 1 - self.ctx_factor("small_model_factor")
            s = rows[SUMS].sum()
            at = pd.Series({c: s[c] * (r if c.startswith("cost") else e) for c in SUMS})
            self.add("waste", f"{rid}: «{task}» runs on a large model ({rows['service'].iat[0]})", [f"res:{rid}"],
                     [self.ev(f"cost of «{task}» on the large model per year", s["cost_chf"], "CHF", "ai_usage.csv"),
                      self.ev("requests per year", ai[(ai.resource_id == rid) & (ai.task_type == task) & ai.date.between(b0, b1)]["requests"].sum(), "requests", "ai_usage.csv"),
                      self.ev("share of this tool's AI cost", 100 * s["cost_chf"] / self.res_sums(rid)["cost_chf"], "%", "ai_usage.csv"),
                      self.ev("small / large model list price", 100 * self.cfg["small_large_cost_ratio"], "%", "reference.yaml")],
                     at, rows, "at stake = cost × (1 − small/large price ratio); energy × (1 − small model factor)",
                     flag="waste", extra={"rule": "oversized_model"})

    def ctx_factor(self, key):
        from ..energy.engine import load_factors
        return load_factors()["ai_tokens"][key]

    def anomalies(self):
        an = self.ctx.tables["anomaly_candidates"]
        for a in an[an["kind"].isin(["one_off_or_peak", "spike"])].itertuples():
            if isinstance(a.explained_by, str) and a.explained_by.startswith("expected peak"):
                continue
            rows = self.fc[(self.fc["resource_id"] == a.resource_id) & self.fc["charge_period_start"].between(a.start, a.end)]
            ratio = a.excess_chf / rows["cost_chf"].sum() if rows["cost_chf"].sum() else 0
            title = (f"{a.resource_id}: spike {a.start} … {a.end}, CHF {a.excess_chf:,.0f} above normal"
                     + (f" ({a.explained_by})" if isinstance(a.explained_by, str) else " (unexplained)"))
            self.add("anomaly", title, [f"res:{a.resource_id}"],
                     [self.ev("cost above the rolling median", a.excess_chf, "CHF", *rows.source_file.unique()),
                      self.ev("days", a.days, "days", *rows.source_file.unique())],
                     rows[SUMS].sum() * ratio, rows, "excess = daily cost − rolling 28-day median, summed over the spike",
                     note=("one-off, already fixed according to the ticket: no recurring saving; a budget alert / loop "
                           "guard prevents recurrence" if isinstance(a.explained_by, str) else
                           "unexplained: a human should check it") + f"; related tickets: {a.related_tickets or 'none'}",
                     flag=None, extra={"rule": "anomaly", "one_off": isinstance(a.explained_by, str)})

    # ----------------------------------------------------------- extra sources
    def ci_nightly(self):
        ci = self.ctx.tables["stg_ci_pipeline_runs"]
        b0, b1 = self.ctx.baseline
        c = ci[ci["date"].between(b0, b1)]
        n = c[c["pipeline"] == "nightly-full"]
        empty = n["commits_since_last_nightly"] == 0
        share_min = n.loc[empty, "duration_seconds"].sum() / c["duration_seconds"].sum()
        reruns = (c["trigger"] == "rerun").sum()
        rows = self.b[self.b["resource_id"] == "cicd"]
        self.add("waste", f"{empty.mean():.0%} of nightly builds run without any change", ["res:cicd"],
                 [self.ev("nightly builds with 0 commits since the last one", empty.sum(), "runs", "extra/ci_pipeline_runs.jsonl"),
                  self.ev("share of nightly builds", 100 * empty.mean(), "%", "extra/ci_pipeline_runs.jsonl"),
                  self.ev("share of all build minutes", 100 * share_min, "%", "extra/ci_pipeline_runs.jsonl"),
                  self.ev("re-runs (repeats) in the baseline year", reruns, "runs", "extra/ci_pipeline_runs.jsonl"),
                  self.ev("runner location: Dublin (IE grid 0.226 vs CH 0.110 kg/kWh)", 1, "flag", "extra/ci_pipeline_runs.jsonl")],
                 rows[SUMS].sum() * share_min, rows, "at stake = cicd total × share of build minutes spent on unchanged nightly builds",
                 flag="waste", extra={"rule": "ci_nightly_unchanged"})

    def stale_tables(self):
        dc = self.ctx.tables["stg_data_catalog_tables"].copy()
        asof = pd.Timestamp(self.cfg["data_as_of"])
        dc["days"] = (asof - pd.to_datetime(dc["last_read"])).dt.days
        stale = dc["last_read"].isna() | (dc["days"] > self.cfg["stale_table_min_days_since_read"])
        retained = dc["retention_required"] == "yes"
        cand = stale & ~retained
        share = dc.loc[cand, "size_gb"].sum() / dc["size_gb"].sum()
        rows = self.b[self.b["resource_id"] == "dp-storage"]
        self.add("waste", f"{dc.loc[cand, 'size_gb'].sum() / 1000:.1f} TB of tables not read for over a year", ["res:dp-storage"],
                 [self.ev("tables not read for > 1 year (or never) and not under retention", cand.sum(), "tables", "extra/data_catalog_tables.csv"),
                  self.ev("their size", dc.loc[cand, "size_gb"].sum(), "GB", "extra/data_catalog_tables.csv"),
                  self.ev("share of the platform storage", 100 * share, "%", "extra/data_catalog_tables.csv"),
                  self.ev("stale but under retention obligation (excluded)", dc.loc[stale & retained, "size_gb"].sum(), "GB", "extra/data_catalog_tables.csv"),
                  self.ev("of the candidates: retention flag empty (owner must confirm)", dc.loc[cand & dc["retention_required"].isna(), "size_gb"].sum(), "GB", "extra/data_catalog_tables.csv"),
                  self.ev("of the candidates: personal data", dc.loc[cand & (dc["data_class"] == "personal data"), "size_gb"].sum(), "GB", "extra/data_catalog_tables.csv")],
                 rows[SUMS].sum() * share, rows, "at stake = dp-storage total × stale (non-retained) share of catalogue GB",
                 flag="waste", extra={"rule": "stale_tables"})

    def triple_backups(self):
        bc = self.ctx.tables["stg_backup_chains"]
        n = bc.groupby("source")["backup_tool"].nunique()
        triple = n[n == 3].index
        t = bc[bc["source"].isin(triple)]
        # the largest copy per source is kept; beyond two copies per source is redundancy
        extra = t.sort_values("size_gb", ascending=False).groupby("source").nth(2)
        share = extra["size_gb"].sum() / bc["size_gb"].sum()
        rows = self.b[self.b["resource_id"] == "st-backup"]
        self.add("waste", f"{len(triple)} of {n.size} sources are backed up by all three backup tools", ["res:st-backup"],
                 [self.ev("sources backed up by three tools", len(triple), "sources", "extra/backup_chains.csv"),
                  self.ev("third copies (smallest of three)", extra["size_gb"].sum(), "GB", "extra/backup_chains.csv"),
                  self.ev("share of the backup archive", 100 * share, "%", "extra/backup_chains.csv"),
                  self.ev("copies without any restore test", bc["last_restore_test"].isna().sum(), "copies", "extra/backup_chains.csv"),
                  self.ev("copies with 10-year retention", (bc["retention_days"] >= 3650).sum(), "copies", "extra/backup_chains.csv")],
                 rows[SUMS].sum() * share, rows, "at stake = st-backup total × share of GB in third copies",
                 note="Retention obligations apply to the archive (Step 7 decides what may be touched).",
                 flag="waste", extra={"rule": "triple_backup"})

    def unviewed_reports(self):
        pb = self.ctx.tables["stg_powerbi_usage"]
        b0, b1 = self.ctx.baseline
        p = pb[pb["date"].between(b0, b1)].groupby(["report_id", "report"]).agg(
            refresh_min=("refresh_duration_min", "sum"), views=("view_count", "sum"),
            report_type=("report_type", lambda s: s.mode().iat[0] if s.notna().any() else None)).reset_index()
        low = p[(p["views"] < self.cfg["pbi_max_views_per_year"]) & (p["refresh_min"] > 0)]
        share = low["refresh_min"].sum() / p["refresh_min"].sum()
        rows = self.b[self.b["resource_id"] == "pbi-kap"]
        self.add("waste", f"{len(low)} reports are refreshed daily but opened fewer than {self.cfg['pbi_max_views_per_year']} times a year",
                 ["res:pbi-kap"],
                 [self.ev("reports with refreshes and < 20 views in the baseline year", len(low), "reports", "extra/powerbi_usage.csv"),
                  self.ev("their share of refresh time on the capacity", 100 * share, "%", "extra/powerbi_usage.csv"),
                  self.ev("of them regulatory reports (keep)", (low["report_type"] == "regulatory").sum(), "reports", "extra/powerbi_usage.csv")],
                 rows[SUMS].sum() * share, rows, "at stake = capacity total × share of refresh minutes of unviewed reports",
                 note="The capacity is a fixed price: money is saved only if the capacity can be downsized.",
                 flag="waste", extra={"rule": "unviewed_reports", "reports": low["report_id"].tolist()})

    def unopened_agent_reports(self):
        ag = self.ctx.tables["stg_ai_agent_runs"]
        b0, b1 = self.ctx.baseline
        r = ag[(ag["agent"] == "report-agent") & ag["date"].between(b0, b1)]
        unopened = (r["report_opened"] == 0).mean()
        rows = self.b[self.b["resource_id"] == "ai-report"]
        self.add("waste", f"{unopened:.0%} of the reports generated by the report agent are never opened", ["res:ai-report"],
                 [self.ev("report-agent runs in the baseline year", len(r), "runs", "extra/ai_agent_runs.jsonl"),
                  self.ev("share never opened", 100 * unopened, "%", "extra/ai_agent_runs.jsonl")],
                 rows[SUMS].sum() * unopened, rows, "at stake = ai-report total × share of unopened reports",
                 flag="waste", extra={"rule": "unopened_agent_reports"})

    def bot_traffic(self):
        wt = self.ctx.tables["stg_web_traffic"]
        b0, b1 = self.ctx.baseline
        w = wt[wt["date"].between(b0, b1)]
        bot = (w["bot_share_pct"] / 100 * w["gb_out_scaled"]).sum() / w["gb_out_scaled"].sum()
        rows = self.b[self.b["resource_id"] == "web-cdn"]
        self.add("waste", f"{bot:.0%} of web traffic comes from bots", ["res:web-cdn"],
                 [self.ev("bot share of delivered GB (weighted)", 100 * bot, "%", "extra/web_traffic.csv")],
                 rows[SUMS].sum() * bot, rows, "at stake = web-cdn total × bot share of delivered GB",
                 note="Not all bots are unwanted (search engines); a human decides what to block.",
                 flag=None, extra={"rule": "bot_traffic"})

    def dirty_location(self):
        from ..energy.engine import load_factors
        F = load_factors()
        ch = F["grid"]["CH"]["mid"]
        for loc in ("DE", "IE"):
            rows = self.b[(self.b["location"] == loc) & self.b["provider"].isin(["Azure", "AWS"])]
            if rows.empty:
                continue
            g = F["grid"][loc]["mid"]
            share = 1 - ch / g
            s = rows[SUMS].sum()
            at = pd.Series({c: s[c] * share if c.startswith("co2") else 0.0 for c in SUMS})
            res = rows.groupby("resource_id")["co2_kg_mid"].sum().sort_values(ascending=False)
            self.add("driver", f"{LOC[loc]}: {s.co2_kg_mid / self.tot.co2_kg_mid:.0%} of CO₂ from {s.cost_chf / self.tot.cost_chf:.0%} of cost "
                     f"(grid {g:.3f} vs Zurich {ch:.3f} kg/kWh)", [f"loc:{loc}"] + [f"res:{r}" for r in res.index[:3]],
                     [self.ev(f"grid mix {loc}", g, "kg CO2/kWh", "pipeline/energy/factors.yaml"),
                      self.ev("grid mix CH (consumption mix)", ch, "kg CO2/kWh", "pipeline/energy/factors.yaml"),
                      self.ev("CO₂ of the location in the baseline year", s.co2_kg_mid, "kg", *rows.source_file.unique())]
                     + [self.ev(f"{r}: CO₂ per year", v, "kg", *rows.source_file.unique()) for r, v in res.head(3).items()],
                     at, rows, f"at stake = CO₂ at {loc} × (1 − grid CH / grid {loc}): what the same load would emit less in Zurich",
                     note="Location is a decision made in Basel; moving needs a technical check (Step 6/7).",
                     flag="driver", extra={"rule": "dirty_location"})

    # ------------------------------------------------------------------- run
    def _server_entities(self):
        from ..export.frontend import build_entities
        if not hasattr(self, "_ents"):
            self._ents = build_entities(self.ctx, self.calc)[0]["entities"]
        return [e for e in self._ents if e["kind"] == "server"]

    def run(self):
        self.drivers()
        self.dirty_location()
        for rule in (self.idle_clusters, self.low_gpu, self.low_cpu_servers, self.zombies, self.unused_licences,
                     self.oversized_model, self.anomalies, self.ci_nightly, self.stale_tables, self.triple_backups,
                     self.unviewed_reports, self.unopened_agent_reports, self.bot_traffic):
            rule()
        return self.findings


LOC = {"CH": "Zurich", "DE": "Frankfurt", "IE": "Dublin", "EU": "EU"}
_COLMAP = {"cost_chf_low": ("cost_chf", "low"), "cost_chf": ("cost_chf", "mid"), "cost_chf_high": ("cost_chf", "high"),
           "cost_eur": ("cost_eur", "mid"), "cost_usd": ("cost_usd", "mid"), "kwh_low": ("kwh", "low"),
           "kwh_mid": ("kwh", "mid"), "kwh_high": ("kwh", "high"), "co2_kg_low": ("co2_kg", "low"),
           "co2_kg_mid": ("co2_kg", "mid"), "co2_kg_high": ("co2_kg", "high")}


def find(ctx: Context) -> None:
    f = Finder(ctx)
    ctx.findings = f.run()
    ctx.finding_flags = f.flags
    ctx.finding_links = f.links
    ctx.tables["findings"] = pd.DataFrame([{
        "finding_id": x["id"], "kind": x["kind"], "rule": x.get("rule"), "title": x["title"], "severity": x["severity"],
        "entity_ids": ", ".join(x["entity_ids"]), "impact_cost_chf": x["impact"]["cost_chf"]["mid"],
        "impact_kwh": x["impact"]["kwh"]["mid"], "impact_co2_kg": x["impact"]["co2_kg"]["mid"],
        "evidence": " · ".join(f"{e['statement']}: {e['value']} {e['unit']}" for e in x["evidence"]),
        "formula": x["calc"]["formula"], "note": x["calc"].get("note")} for x in ctx.findings])
