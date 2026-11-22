"""A4 · Clustering: group servers and data-platform clusters by how they behave,
name the groups and explain the outliers.

Entities: the 53 virtual servers (srv:*) and the two data-platform clusters
(res:dp-prod, res:dp-dev). Features over the baseline year, on one scale for both:

    utilisation   servers: weekly CPU avg (GPU server: GPU avg) · clusters: active_use_h / runtime_h
    peak          95th percentile of weekly CPU max (clusters: of daily active share)
    uptime        servers: uptime_h / 168 · clusters: runtime_h / 24
    variability   coefficient of variation of the weekly utilisation
    memory        weekly RAM avg (clusters: not measured → median of all entities)

Method: z-scores → k-means (numpy, deterministic seeds), k chosen by silhouette;
groups named by rules on the centroids; outliers = distance to the own centroid
far above the group's usual spread. Plain code, no AI.

Outputs: output/clusters.json (contract ClustersFile) · DuckDB table cluster_members
· candidate findings (idle groups, outliers) in output/bonus/candidates.json.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ..harmonize.context import Context
from .common import read_output, rng, write_candidates, write_json, write_table

DATA_DATE = date(2026, 9, 6)          # README: «Data as of 06.09.2026»
K_RANGE = range(3, 8)
SEEDS = range(20)
OUTLIER_Z = 3.0                       # robust z of the distance within the group

FEATURES = [  # key, label, unit, scale for display
    ("utilisation", "Average utilisation", "%", 100),
    ("peak", "Peak utilisation (p95 of weekly max)", "%", 100),
    ("uptime", "Share of time switched on", "%", 100),
    ("variability", "Week-to-week variability (CV)", "ratio", 1),
    ("memory", "Average memory use", "%", 100),
]
KEYS = [f[0] for f in FEATURES]


# ---------------------------------------------------------------- features
def _server_features(ctx: Context) -> pd.DataFrame:
    b0, b1 = ctx.baseline
    m = ctx.tables["stg_server_metrics_weekly"]
    m = m[m["week_start"].between(b0, b1)].copy()
    # The GPU server works on its GPU: its utilisation is the GPU's, not the host CPU's
    m["util"] = np.where(m["gpu_avg_pct"].notna(), m["gpu_avg_pct"], m["cpu_avg_pct"]) / 100
    g = m.groupby("server_id")
    out = pd.DataFrame({
        "utilisation": g["util"].mean(),
        "peak": g["cpu_max_pct"].quantile(0.95) / 100,
        "uptime": (g["uptime_h"].mean() / 168).clip(upper=1),
        "variability": g["util"].std() / g["util"].mean().replace(0, np.nan),
        "memory": g["ram_avg_pct"].mean() / 100,
        "weeks": g.size(),
    })
    out["variability"] = out["variability"].fillna(0)
    out.index = "srv:" + out.index
    return out


def _platform_features(ctx: Context) -> pd.DataFrame:
    b0, b1 = ctx.baseline
    u = ctx.tables["stg_data_platform_usage"]
    u = u[u["date"].between(b0, b1)].copy()
    u["share"] = (u["active_use_h"] / u["runtime_h"].replace(0, np.nan)).clip(0, 1)
    u["week"] = pd.to_datetime(u["date"]).dt.to_period("W").astype(str)
    weekly = u.groupby(["resource_id", "week"])["share"].mean()
    g = u.groupby("resource_id")
    out = pd.DataFrame({
        "utilisation": g["share"].mean(),
        "peak": g["share"].quantile(0.95),
        "uptime": (g["runtime_h"].mean() / 24).clip(upper=1),
        "variability": weekly.groupby(level=0).std() / weekly.groupby(level=0).mean(),
        "memory": np.nan,
        "weeks": weekly.groupby(level=0).size(),
    })
    out.index = "res:" + out.index
    return out


def _context(ctx: Context) -> dict[str, dict]:
    """Facts shown next to a member (not used for clustering)."""
    inv = ctx.tables["dim_server"]
    out = {}
    for r in inv.itertuples():
        login = pd.to_datetime(r.last_login, errors="coerce")
        out[f"srv:{r.server_id}"] = {
            "type": r.type, "environment": r.environment, "provider": r.provider, "region": r.region,
            "vcpu": None if pd.isna(r.vcpu) else float(r.vcpu),
            "owner_department": None if pd.isna(r.owner_department) else r.owner_department,
            "days_since_login": None if pd.isna(login) else int((pd.Timestamp(DATA_DATE) - login).days),
            "project_id": None if pd.isna(r.project_id) else r.project_id,
        }
    return out


# ------------------------------------------------------------------ k-means
def _kmeans(X: np.ndarray, k: int, seed: int, iters: int = 100) -> tuple[np.ndarray, np.ndarray, float]:
    rs = np.random.default_rng(seed)
    C = X[rs.choice(len(X), 1)]
    while len(C) < k:  # k-means++ initialisation
        d = ((X[:, None] - C[None]) ** 2).sum(-1).min(1)
        C = np.vstack([C, X[rs.choice(len(X), p=d / d.sum())]])
    for _ in range(iters):
        lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
        new = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(new, C):
            break
        C = new
    inertia = float(((X - C[lab]) ** 2).sum())
    return lab, C, inertia


def _silhouette(X: np.ndarray, lab: np.ndarray) -> float:
    D = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1))
    s = []
    for i in range(len(X)):
        own = lab == lab[i]
        if own.sum() <= 1:
            s.append(0.0)
            continue
        a = D[i, own].sum() / (own.sum() - 1)
        b = min(D[i, lab == j].mean() for j in set(lab) if j != lab[i])
        s.append((b - a) / max(a, b))
    return float(np.mean(s))


def _best_partition(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, float, dict]:
    scores, best = {}, None
    for k in K_RANGE:
        lab, C, _ = min((_kmeans(X, k, s) for s in SEEDS), key=lambda r: r[2])
        sil = _silhouette(X, lab)
        scores[k] = round(sil, 3)
        if best is None or sil > best[3] + 1e-9:
            best = (lab, C, k, sil)
    return (*best, scores)


# ------------------------------------------------------------------- naming
def _name(c: pd.Series) -> tuple[str, str, str]:
    """(name, description, rule) from a centroid in raw units."""
    if c["uptime"] < 0.5:
        return ("On demand", "Switched on only for short sessions; little to gain.",
                "uptime < 50 %")
    if c["utilisation"] < 0.02:
        return ("Always on, almost idle", "Running around the clock with almost no load: candidates "
                "for switch-off or decommissioning (check owner, protection and DR first).",
                "uptime ≥ 50 % and utilisation < 2 %")
    if c["utilisation"] < 0.20:
        return ("Always on, lightly used", "Running around the clock at low average load with short "
                "peaks: candidates for schedules (nights, weekends) and smaller sizes.",
                "uptime ≥ 50 % and utilisation 2–20 %")
    return ("Steady workload", "Running around the clock with a steady, real load: production.",
            "uptime ≥ 50 % and utilisation ≥ 20 %")


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


def _fmt(key: str, v: float) -> str:
    scale = dict((f[0], f[3]) for f in FEATURES)[key]
    unit = dict((f[0], f[2]) for f in FEATURES)[key]
    return f"{v * scale:.1f} %" if unit == "%" else f"{v:.2f}"


# ---------------------------------------------------------------- metrics
def _sum_metrics(ms: list[dict]) -> dict | None:
    if not ms:
        return None
    out = {}
    for key in ms[0]:
        vals = [m[key] for m in ms if m.get(key)]
        out[key] = None if not vals else {lvl: round(sum(v[lvl] or 0 for v in vals), 2) for lvl in ("low", "mid", "high")}
    return out


# ---------------------------------------------------------------------- run
def run(ctx: Context) -> None:
    raw = pd.concat([_server_features(ctx), _platform_features(ctx)])
    measured = raw[KEYS].notna()                 # memory is not measured for the clusters
    Z = ((raw[KEYS] - raw[KEYS].mean()) / raw[KEYS].std(ddof=0)).fillna(0)  # not measured → average (z = 0)
    lab, C, k, sil, scores = _best_partition(Z.to_numpy())

    # order groups by utilisation (stable ids from run to run)
    order = raw.groupby(lab)["utilisation"].mean().sort_values().index.tolist()
    gid = {old: f"C-{i + 1}" for i, old in enumerate(order)}
    raw["group_id"] = [gid[x] for x in lab]
    # distance to the own centroid on MEASURED features only (an imputed value never makes an outlier)
    diff = np.where(measured.to_numpy(), Z.to_numpy() - C[lab], 0.0)
    raw["distance"] = np.sqrt((diff ** 2).sum(1) * len(KEYS) / measured.sum(1).to_numpy())

    # outliers: distance far above the group's usual spread (robust z), or a group of one
    raw["outlier"] = False
    for g, idx in raw.groupby("group_id").groups.items():
        d = raw.loc[idx, "distance"]
        if len(d) == 1:
            raw.loc[idx, "outlier"] = True
            continue
        mad = (d - d.median()).abs().median() or 1e-9
        raw.loc[idx, "outlier"] = ((d - d.median()) / (1.4826 * mad) > OUTLIER_Z) & (d > 1.0)

    entities = {e["id"]: e for e in (read_output(ctx, "entities.json") or {}).get("entities", [])}
    context = _context(ctx)
    group_median = raw[~raw["outlier"]].groupby("group_id")[KEYS].median()

    def reason(eid: str) -> str:
        r, g = raw.loc[eid], raw.loc[eid, "group_id"]
        ref = group_median.loc[g] if g in group_median.index else raw[KEYS].median()
        keys = [k for k in KEYS if measured.loc[eid, k]]
        z = ((r[keys] - ref[keys]) / raw[keys].std(ddof=0)).abs().sort_values(ascending=False)
        parts = [f"{_lower_first(dict((f[0], f[1]) for f in FEATURES)[k])} {_fmt(k, r[k])} vs {_fmt(k, ref[k])} in its group"
                 for k in z.index[:2]]
        return "; ".join(parts)

    def util_range(ids: list[str]) -> str:
        u = raw.loc[ids, "utilisation"] * 100
        return f"{u.min():.1f}–{u.max():.1f} %"

    members = []
    for eid, r in raw.sort_values(["group_id", "utilisation"]).iterrows():
        e = entities.get(eid, {})
        members.append({
            "entity_id": eid, "label": e.get("label", eid.split(":", 1)[1]), "group_id": r["group_id"],
            "features": {k: None if pd.isna(r[k]) else round(float(r[k]), 4) for k in KEYS},
            "distance": round(float(r["distance"]), 3), "outlier": bool(r["outlier"]),
            "differs_by": reason(eid),     # how it differs from its group (shown for every member)
            "outlier_reason": reason(eid) if r["outlier"] else None,
            "context": context.get(eid, {"type": "data platform cluster"}),
        })

    total_co2 = sum((entities.get(eid, {}).get("metrics", {}).get("co2_kg") or {}).get("mid") or 0 for eid in raw.index)
    groups = []
    for g in sorted(raw["group_id"].unique()):
        ids = raw.index[raw["group_id"] == g].tolist()
        core = raw.loc[ids][~raw.loc[ids, "outlier"]]
        cen = (core if len(core) else raw.loc[ids])[KEYS].median()
        name, desc, rule = _name(cen)
        mets = _sum_metrics([entities[i]["metrics"] for i in ids if i in entities])
        co2 = (mets or {}).get("co2_kg") or {}
        groups.append({"id": g, "name": name, "description": desc, "rule": rule, "size": len(ids),
                       "centroid": {k: round(float(cen[k]), 4) for k in KEYS}, "entity_ids": ids,
                       "metrics": mets, "share_co2": round(co2.get("mid", 0) / total_co2, 4) if total_co2 else None})
        groups[-1]["utilisation_range"] = util_range(ids)
    _disambiguate(groups)

    weeks = int(raw["weeks"].sum())
    calc = {
        "formula": "z-scores of 5 behaviour features → k-means (k by silhouette) → groups named by rules on "
                   "the group medians; outlier = robust z of the distance to the own centroid > 3",
        "inputs": [{"name": "k", "value": int(k), "unit": "groups", "source": "silhouette"},
                   {"name": "silhouette", "value": round(sil, 3), "unit": "−1…1", "source": "clusters.py"},
                   {"name": "entities", "value": int(len(raw)), "unit": "servers + clusters", "source": "server_inventory.csv"}],
        "factor_ids": [], "row_count": weeks, "value_status": "observed", "issue_ids": [],
        "source_files": ["server_metrics_weekly.csv", "data_platform_usage.csv", "server_inventory.csv"],
        "note": "Group costs and CO2 are the sums of the members' baseline metrics from entities.json.",
    }
    write_json(ctx, "clusters.json", {
        "method": {"algorithm": "k-means (k-means++ init, 20 seeds, numpy)", "k": int(k),
                   "silhouette": round(sil, 3), "silhouette_by_k": scores,
                   "features": [{"key": k_, "label": l, "unit": u} for k_, l, u, _ in FEATURES],
                   "period": {"start": ctx.baseline[0], "end": ctx.baseline[1]},
                   "note": "GPU server: utilisation = GPU utilisation. Clusters: utilisation = active_use_h / "
                           "runtime_h; memory not measured → neutral (average) for the grouping, ignored for "
                           "distances and outliers, null in the output."},
        "groups": groups, "members": members, "calc": calc,
    })
    write_table(ctx, "cluster_members", pd.DataFrame([{**{k: v for k, v in m.items() if k not in ("features", "context")},
                                                         **m["features"], **m["context"]} for m in members]))
    write_candidates(ctx, "clusters", findings=_candidates(groups, members, raw, calc))


def _disambiguate(groups: list[dict]) -> None:
    seen: dict[str, int] = {}
    for g in groups:
        n = seen.get(g["name"], 0)
        seen[g["name"]] = n + 1
        if n:
            g["name"] += f" ({'higher' if n == 1 else 'highest'} load)"


def _candidates(groups: list[dict], members: list[dict], raw: pd.DataFrame, calc: dict) -> list[dict]:
    """Findings for the Step 5 owner: idle groups (waste) and outliers (anomaly)."""
    out = []
    for g in groups:
        if not g["name"].startswith("Always on, almost idle") or not g["metrics"]:
            continue
        c = g["centroid"]
        out.append({
            "id": f"F-CL-{g['id']}", "kind": "waste",
            "title": f"{g['size']} machines always on at {g['utilisation_range']} average load",
            "entity_ids": g["entity_ids"],
            "evidence": [
                {"statement": f"median utilisation in the group (members: {g['utilisation_range']})",
                 "value": round(c["utilisation"] * 100, 2), "unit": "%",
                 "source_files": ["server_metrics_weekly.csv"]},
                {"statement": "median share of time switched on", "value": round(c["uptime"] * 100, 1), "unit": "%",
                 "source_files": ["server_metrics_weekly.csv"]}],
            "severity": "high" if (g["share_co2"] or 0) > 0.05 else "medium",
            "impact": g["metrics"], "measure_ids": [], "calc": calc})
    for m in members:
        if not m["outlier"]:
            continue
        out.append({
            "id": f"F-CL-{m['entity_id'].split(':', 1)[1]}", "kind": "anomaly",
            "title": f"{m['label']} behaves unlike any other machine",
            "entity_ids": [m["entity_id"]],
            "evidence": [{"statement": m["outlier_reason"], "value": m["distance"], "unit": "z-distance",
                          "source_files": calc["source_files"]}],
            "severity": "medium", "impact": None, "measure_ids": [], "calc": calc})
    return out
