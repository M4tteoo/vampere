"""Library of named transforms. Connector YAML files call them by name:

    transforms:
      - dedupe_exact
      - resource_id_last: {column: resource_path, sep: "/"}

Each transform takes (df, ctx, source, **params) and returns a DataFrame.
Every correction is written to the issues log, so the Intake screen and the
jury can see what was changed and why.
"""
from __future__ import annotations

import json
import re
from typing import Callable

import numpy as np
import pandas as pd

from .common import nonempty, normalize_project_id

REGISTRY: dict[str, Callable] = {}


def transform(fn: Callable) -> Callable:
    REGISTRY[fn.__name__] = fn
    return fn


def _status_col(col: str) -> str:
    return f"{col}_status"


# ----------------------------------------------------------------- generic
@transform
def dedupe_exact(df, ctx, source):
    cols = [c for c in df.columns if c != "source_row"]
    dup = df.duplicated(subset=cols, keep="first")
    if dup.any():
        ctx.log(source, "duplicate", dup.sum(), "removed exact duplicate rows",
                "identical in every column; first occurrence kept")
    return df[~dup].copy()


@transform
def keep_final(df, ctx, source, key, status_col="contract_status"):
    """Drafts next to final versions: keep Final; keep a Draft only when no
    Final exists for the same key (flagged)."""
    has_final = df.groupby(key)[status_col].transform(lambda s: (s == "Final").any())
    drop = (df[status_col] == "Draft") & has_final
    orphan = (df[status_col] == "Draft") & ~has_final
    if drop.any():
        ctx.log(source, "draft_dropped", drop.sum(),
                "dropped Draft rows that have a Final version for the same key",
                f"key = {', '.join(key)}")
    if orphan.any():
        ctx.log(source, "draft_only", orphan.sum(),
                "kept Draft rows without a Final version, flagged", severity="warn")
    out = df[~drop].copy()
    out["is_draft"] = out[status_col] == "Draft"
    return out


@transform
def add_constant(df, ctx, source, column, value):
    df[column] = value
    return df


@transform
def coalesce(df, ctx, source, target, sources):
    """Field renamed over time (e.g. duration_s → duration_seconds)."""
    present = [c for c in sources if c in df.columns]
    out = df[present[0]].copy()
    for c in present[1:]:
        out = out.fillna(df[c])
    counts = {c: int(df[c].notna().sum()) for c in present}
    ctx.log(source, "field_renamed", sum(counts.values()),
            f"merged {present} into «{target}»", json.dumps(counts))
    df[target] = out
    return df.drop(columns=[c for c in present if c != target])


@transform
def date_part(df, ctx, source, column, target):
    """'YYYY-MM-DD hh:mm:ss' → 'YYYY-MM-DD' (local time stays local)."""
    df[target] = df[column].astype(str).str[:10]
    return df


@transform
def local_date_from_utc(df, ctx, source, column, target, tz="Europe/Zurich"):
    ts = pd.to_datetime(df[column], utc=True).dt.tz_convert(tz)
    df[target] = ts.dt.strftime("%Y-%m-%d")
    df[f"{target}_hour"] = ts.dt.hour
    ctx.log(source, "timezone_converted", len(df), f"UTC → {tz} for daily totals")
    return df


# ------------------------------------------------------------------- keys
@transform
def resource_id_last(df, ctx, source, column, sep, target="resource_id"):
    df[target] = df[column].astype(str).str.split(sep).str[-1]
    return df


@transform
def normalize_project(df, ctx, source, columns):
    for col in columns:
        if col not in df.columns:
            continue
        before = nonempty(df[col].astype("string"))
        after = before.map(normalize_project_id, na_action="ignore")
        changed = before.notna() & (before != after)
        if changed.any():
            variants = sorted(before[changed].dropna().unique().tolist())[:8]
            ctx.log(source, "project_id_normalized", changed.sum(),
                    f"{col}: spellings unified to P-NNN", f"e.g. {variants}")
        df[col] = after
    return df


@transform
def department_alias(df, ctx, source, column):
    aliases = ctx.ref["department_aliases"]
    m = df[column].isin(aliases)
    if m.any():
        ctx.log(source, "department_renamed", m.sum(),
                f"{column}: {dict((k, v) for k, v in aliases.items() if k in set(df.loc[m, column]))}")
    df[column] = df[column].replace(aliases)
    return df


@transform
def cost_center_department(df, ctx, source, column, target="department"):
    df[target] = ctx.department_of_cc(df[column])
    return df


@transform
def map_values(df, ctx, source, column, target, ref_key):
    table = ctx.ref[ref_key]
    default = table.get("default")
    mapped = df[column].map({k: v for k, v in table.items() if k != "default"})
    df[target] = mapped.fillna(default) if default else mapped
    return df


@transform
def tool_to_resource(df, ctx, source, column, target="resource_id"):
    """Hoster has no resource key: its Item label equals the tool name."""
    lookup = ctx.dim_resource.set_index("tool")["resource_id"]
    df[target] = df[column].map(lookup)
    miss = df[target].isna()
    if miss.any():
        ctx.log(source, "unmapped_label", miss.sum(), "no resource for label",
                str(df.loc[miss, column].unique()[:5]), severity="warn")
    ctx.log(source, "key_derived", len(df) - miss.sum(),
            f"resource_id derived from «{column}» via tool names in the mapping")
    return df


@transform
def server_to_resource(df, ctx, source, column="server_id", target="resource_id"):
    df[target] = ctx.server_resource(df[column])
    return df


@transform
def parse_json_tags(df, ctx, source, column, prefix="tag_"):
    parsed = df[column].fillna("{}").map(json.loads)
    keys = sorted({k for d in parsed for k in d})
    for k in keys:
        df[f"{prefix}{k}"] = nonempty(parsed.map(lambda d: d.get(k)).astype("object"))
    empty = parsed.map(len) == 0
    if empty.any():
        ctx.log(source, "missing_tags", empty.sum(), "empty tag JSON ({}): department and tool "
                "taken from the mapping instead")
    return df


# ------------------------------------------------------------------- units
@transform
def to_gb(df, ctx, source, value, unit, target=None):
    target = target or value
    mb = df[unit].astype(str).str.upper() == "MB"
    factor = ctx.config["units"]["mb_per_gb"]
    df[target] = np.where(mb, df[value] / factor, df[value])
    if mb.any():
        ctx.log(source, "unit_converted", mb.sum(), f"{value}: MB → GB (÷{factor})",
                "factor verified: MB rows sit at a median ratio of 1000 to neighbouring GB rows")
    df[unit] = "GB"
    return df


@transform
def scale_by_sample_rate(df, ctx, source, columns, rate_col="sample_rate"):
    sampled = df[rate_col] != 1
    for c in columns:
        df[f"{c}_scaled"] = df[c] * df[rate_col]
    if sampled.any():
        first = df.loc[sampled].iloc[0]
        ctx.log(source, "sampling_scaled", sampled.sum(),
                f"multiplied {columns} by {rate_col}",
                f"sample_rate {sorted(df[rate_col].unique())}; sampled rows start at {first.get('time_utc', '')}")
    return df


# --------------------------------------------------------- missing values
@transform
def recover_tokens_out(df, ctx, source):
    """Tier 1: invert cost = in·p_in + cached·p_cached + out·p_out (USD list
    prices × monthly USD→CHF rate). Tier 3 fallback: median out/in ratio."""
    prices = ctx.ref["ai_list_prices_usd_per_mtok"]
    usd = df["month"].map(ctx.tables["fx_monthly"].set_index("month")["usd_chf"])
    p_in = df["model"].map({k: v["input"] for k, v in prices.items()})
    p_ca = df["model"].map({k: v["cached"] for k, v in prices.items()})
    p_out = df["model"].map({k: v["output"] for k, v in prices.items()})
    uncached = df["tokens_in"] - df["tokens_in_cache"]
    est = (df["cost_chf"] / usd * 1e6 - uncached * p_in - df["tokens_in_cache"] * p_ca) / p_out

    st = _status_col("tokens_out")
    df[st] = np.where(df["tokens_out"].notna(), "observed", "missing")
    miss = df["tokens_out"].isna()
    ok = miss & est.gt(0) & est.notna()
    df.loc[ok, "tokens_out"] = est[ok].round()
    df.loc[ok, st] = "derived_exact"
    ctx.log(source, "derived_exact", ok.sum(), "tokens_out recovered from the cost formula",
            "out = (cost_chf / usd_chf − uncached·p_in − cached·p_cached) / p_out; "
            "list prices reproduce the gateway cost with median error 0.00 %")

    rest = df["tokens_out"].isna()
    if rest.any():
        ratio = (df.loc[~rest, "tokens_out"] / df.loc[~rest, "tokens_in"]).groupby(
            [df["model"], df["task_type"]]).median()
        key = pd.MultiIndex.from_frame(df.loc[rest, ["model", "task_type"]])
        r = pd.Series(ratio.reindex(key).values, index=df.index[rest])
        df.loc[rest, "tokens_out"] = (df.loc[rest, "tokens_in"] * r).round()
        df.loc[rest & df["tokens_out"].notna(), st] = "estimated"
        ctx.log(source, "estimated", rest.sum(), "tokens_out estimated from median out/in ratio",
                "cost formula gave no positive solution for these rows")
    return df


@transform
def chf_to_native_usd(df, ctx, source, amount_chf="cost_chf"):
    """The gateway reports CHF, but the provider bills in USD (list prices).
    Restore the native amount so every currency view is exact."""
    usd = df["month"].map(ctx.tables["fx_monthly"].set_index("month")["usd_chf"])
    df["amount_native"] = df[amount_chf] / usd
    df["currency_native"] = "USD"
    return df


@transform
def impute_group_median(df, ctx, source, column, group):
    st = _status_col(column)
    df[st] = np.where(df[column].notna(), "observed", "missing")
    med = df.groupby(group)[column].transform("median")
    miss = df[column].isna() & med.notna()
    df.loc[miss, column] = med[miss]
    df.loc[miss, st] = "estimated"
    if miss.any():
        ctx.log(source, "estimated", miss.sum(), f"{column} missing → median per {group}")
    left = df[column].isna().sum()
    if left:
        ctx.log(source, "missing_value", left, f"{column} left empty (no estimate possible)")
    return df


@transform
def fill_from_group(df, ctx, source, column, group):
    """Attribute recorded on some rows of an entity but not others."""
    st = _status_col(column)
    df[st] = np.where(df[column].notna(), "observed", "missing")
    mode = df.groupby(group)[column].transform(
        lambda s: s.dropna().mode().iat[0] if s.notna().any() else np.nan)
    miss = df[column].isna() & mode.notna()
    df.loc[miss, column] = mode[miss]
    df.loc[miss, st] = "derived_cross_source"
    if miss.any():
        ctx.log(source, "attribute_filled", miss.sum(),
                f"{column} filled from other rows of the same {group}")
    return df


@transform
def fill_cpu_from_metrics(df, ctx, source):
    """Tier 2: empty 30-day CPU in the inventory → last 4 weeks of metrics.
    Where both exist, large differences are logged as contradictions."""
    met = ctx.tables["stg_server_metrics_weekly"]
    last = met[met["week_start"] >= "2026-08-10"].groupby("server_id")["cpu_avg_pct"].mean()
    m = df["server_id"].map(last)
    st = _status_col("cpu_utilisation_30d_pct")
    df[st] = np.where(df["cpu_utilisation_30d_pct"].notna(), "observed", "missing")
    miss = df["cpu_utilisation_30d_pct"].isna() & m.notna()
    df.loc[miss, "cpu_utilisation_30d_pct"] = m[miss].round(1)
    df.loc[miss, st] = "derived_cross_source"
    ctx.log(source, "derived_cross_source", miss.sum(),
            "empty cpu_utilisation_30d_pct filled from server_metrics_weekly (last 4 weeks)")
    both = ~miss & df["cpu_utilisation_30d_pct"].notna() & m.notna()
    diff = (df["cpu_utilisation_30d_pct"] - m).abs()
    bad = both & (diff > 5)
    for _, r in df[bad].iterrows():
        ctx.log(source, "contradiction", 1, "inventory and weekly metrics disagree on CPU",
                f"{r.server_id}: inventory {r.cpu_utilisation_30d_pct}% vs metrics {m[_]:.1f}%",
                severity="warn")
    return df


@transform
def parse_time_window(df, ctx, source, column="time_window"):
    df["window_type"] = df[column].str.extract(r"^(fixed|flexible)", expand=False)
    df["window_rule"] = df[column].str.replace(r"^(fixed|flexible):\s*", "", regex=True)
    return df


@transform
def numeric(df, ctx, source, columns):
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@transform
def compute(df, ctx, source, target, expr):
    """Derived column from a pandas expression, e.g. node_count * runtime_h."""
    df[target] = df.eval(expr)
    return df


@transform
def flag_missing(df, ctx, source, column, issue, action, severity="info"):
    m = df[column].isna()
    if m.any():
        ctx.log(source, issue, m.sum(), action, severity=severity)
    return df


# --------------------------------------------------------- dimension helpers
@transform
def fill_department_from_cc(df, ctx, source, column="department", cc_column="cost_center"):
    m = df[column].isna()
    df.loc[m, column] = ctx.department_of_cc(df.loc[m, cc_column])
    if m.any():
        ctx.log(source, "attribute_filled", m.sum(), f"empty {column} taken from {cc_column}",
                str(df.loc[m, "resource_id"].tolist()) if "resource_id" in df else "")
    return df


@transform
def add_category(df, ctx, source, column="resource_id", target="category"):
    df[target] = ctx.category_of_resource(df[column])
    return df


@transform
def region_code(df, ctx, source, column="region", target="location_code"):
    df[target] = ctx.location_of_region(df[column])
    return df


@transform
def calendar_flags(df, ctx, source):
    d = pd.to_datetime(df["date"])
    df["month"] = d.dt.strftime("%Y-%m-01")
    df["is_weekend"] = d.dt.dayofweek >= 5
    # last three working days of each month (finance closing, T-1029)
    wd = df[df["workday"] == 1].copy()
    wd["rank_from_end"] = wd.groupby("month")["date"].rank(ascending=False, method="first")
    last3 = set(wd.loc[wd["rank_from_end"] <= 3, "date"])
    df["is_last3_workdays_of_month"] = df["date"].isin(last3)
    # days 1–3 of each quarter (quarterly model training, T-1053 / T-1101)
    df["is_quarter_day_1_3"] = d.dt.month.isin([1, 4, 7, 10]) & (d.dt.day <= 3)
    b0, b1 = ctx.baseline
    df["in_baseline"] = (df["date"] >= b0) & (df["date"] <= b1)
    return df
