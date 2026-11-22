"""Generic connector engine.

A connector is a YAML «dictionary» describing one export:
  - how to read it (csv / jsonl) and rename its columns to our names,
  - which date formats to parse,
  - which named transforms to apply (transforms.py),
  - which rows it contributes to the shared tables:
      cost      → fact_cost      (billing lines, FOCUS-like)
      activity  → fact_activity  (physical quantities, long format)
      free_text → free_text      (inert text, never interpreted)

For another SME you write new YAML files; the engine stays the same.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import month_start, nonempty, normalize_project_id
from .context import PIPELINE_DIR, Context, load_yaml
from .transforms import REGISTRY

CONNECTOR_DIR = PIPELINE_DIR / "connectors"
STATUS_RANK = {"observed": 0, "derived_exact": 1, "derived_cross_source": 2, "estimated": 3, "missing": 4}


# -------------------------------------------------------------------- read
def _read(path: Path, fmt: str) -> pd.DataFrame:
    if fmt == "jsonl":
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        df = pd.json_normalize(rows, sep="_")
    else:
        df = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    df.insert(0, "source_row", np.arange(1, len(df) + 1))  # 1-based data row in the file
    return df


def _value(df: pd.DataFrame, spec, default=None) -> pd.Series:
    """A spec value is a column name, {column: name}, {fixed: value} or None."""
    if spec is None:
        return pd.Series(default, index=df.index, dtype="object")
    if isinstance(spec, dict):
        if "fixed" in spec:
            return pd.Series(spec["fixed"], index=df.index)
        spec = spec["column"]
    return df[spec]


# -------------------------------------------------------------- connector
def run_connector(name: str, ctx: Context) -> None:
    spec = load_yaml(CONNECTOR_DIR / f"{name}.yaml")
    source = spec["source"]
    df = _read(ctx.data_dir / source, spec.get("format", "csv"))
    rows_in = len(df)

    df = df.rename(columns=spec.get("rename", {}))
    for col in spec.get("strings", []):
        df[col] = nonempty(df[col].astype("string")).astype("object")
    for col, fmt in (spec.get("dates") or {}).items():
        df[col] = pd.to_datetime(df[col].astype(str), format=fmt).dt.strftime("%Y-%m-%d")
        if fmt != "%Y-%m-%d":
            ctx.log(source, "date_format", len(df), f"{col}: {fmt} → ISO YYYY-MM-DD")
    if "month_from" in spec and spec["month_from"] in df.columns:
        df["month"] = month_start(df[spec["month_from"]])

    for t in spec.get("transforms", []):
        tname, params = (t, {}) if isinstance(t, str) else next(iter(t.items()))
        df = REGISTRY[tname](df, ctx, source, **(params or {}))
    if "month_from" in spec:  # again: the date column may come from a transform
        df["month"] = month_start(df[spec["month_from"]])

    table = spec["table"]
    ctx.tables[table] = df.reset_index(drop=True)
    ctx.sources.append({
        "connector": name, "source_file": source, "role": "extra" if source.startswith("extra/") else "core",
        "system": spec.get("system", ""), "table": table, "rows_in": rows_in, "rows_out": len(df),
    })

    if spec.get("free_text"):
        _emit_free_text(df, spec["free_text"], ctx, source)
    if spec.get("cost"):
        _emit_cost(df, spec["cost"], ctx, source)
    for block in spec.get("activity", []) or []:
        _emit_activity(df, block, ctx, source)


# --------------------------------------------------------------- free text
def _emit_free_text(df, spec, ctx: Context, source: str) -> None:
    parts = []
    for col in spec["columns"]:
        s = nonempty(df[col].astype("string"))
        m = s.notna()
        parts.append(pd.DataFrame({
            "source_file": source,
            "source_row": df.loc[m, "source_row"].values,
            "record_key": df.loc[m, spec["key"]].values if spec.get("key") else None,
            "resource_id": df.loc[m, spec["resource_id"]].values if spec.get("resource_id") else None,
            "field": col,
            "text": s[m].values,
            "text_risk": None,  # filled later by an LLM classifier, never by regex
        }))
    ft = pd.concat(parts, ignore_index=True)
    ctx.free_text_parts.append(ft)
    ctx.log(source, "free_text_isolated", len(ft),
            f"{spec['columns']} kept as inert data in table free_text",
            "free text never drives calculations; text_risk left empty for the LLM classifier")


# -------------------------------------------------------------------- cost
def _resolve_allocation(df, c, ctx: Context) -> pd.DataFrame:
    """Department priority: row tag → row cost center → mapping → mapping cc."""
    dim = ctx.dim_resource.set_index("resource_id")
    rid = df[c.get("resource_id", "resource_id")]
    out = pd.DataFrame(index=df.index)

    dept = pd.Series(np.nan, index=df.index, dtype="object")
    method = pd.Series(np.nan, index=df.index, dtype="object")
    for col in c.get("department_columns", []):
        m = dept.isna() & df[col].notna()
        dept[m] = df.loc[m, col].replace(ctx.ref["department_aliases"])
        method[m] = f"row:{col}"
    row_cc = pd.to_numeric(df[c["cost_center_column"]], errors="coerce") if c.get("cost_center_column") else pd.Series(np.nan, index=df.index)
    m = dept.isna() & row_cc.notna()
    dept[m] = ctx.department_of_cc(row_cc[m])
    method[m] = f"row:{c.get('cost_center_column')}"
    m = dept.isna()
    dept[m] = rid[m].map(dim["department"])
    method[m & dept.notna()] = "mapping"
    m = dept.isna()
    dept[m] = ctx.department_of_cc(rid[m].map(dim["cost_center"]))
    method[m & dept.notna()] = "mapping:cost_center"

    reverse_cc = {v: int(k) for k, v in ctx.ref["cost_centers"].items()}
    cc = row_cc.copy()
    m = cc.isna() & (dept == rid.map(dim["department"]))
    cc[m] = rid[m].map(dim["cost_center"])
    m = cc.isna()
    cc[m] = dept[m].map(reverse_cc)

    out["department"] = dept
    out["cost_center"] = cc.astype("Int64")
    out["allocation_method"] = method.fillna("unallocated")

    tool = df[c["tool_column"]] if c.get("tool_column") else rid.map(dim["tool"])
    out["tool"] = tool.fillna(rid.map(dim["tool"]))
    proj = df[c["project_column"]] if c.get("project_column") else pd.Series(np.nan, index=df.index)
    out["project_id"] = proj.fillna(rid.map(dim["default_project"]))
    env = df[c["environment_column"]] if c.get("environment_column") else pd.Series(np.nan, index=df.index)
    out["environment"] = env.fillna(rid.map(dim["environment"]))
    return out


def _impute_unit_price(fc: pd.DataFrame, ctx: Context, source: str) -> pd.DataFrame:
    """Tier 3: missing amount = quantity × median unit price of the same
    resource/unit/currency, range from the configured quantiles."""
    lo_q, hi_q = ctx.config["imputation"]["unit_price_range_quantiles"]
    obs = fc[fc["amount_native"].notna() & (fc["quantity"] > 0) & (fc["charge_category"] != "Credit")]
    up = (obs["amount_native"] / obs["quantity"]).groupby(
        [obs["resource_id"], obs["unit"], obs["currency_native"]])
    stats = pd.DataFrame({"mid": up.median(), "lo": up.quantile(lo_q), "hi": up.quantile(hi_q)})

    miss = fc["amount_native"].isna()
    zero = miss & (fc["quantity"] == 0)
    fc.loc[zero, ["amount_native", "amount_native_low", "amount_native_high"]] = 0.0
    fc.loc[zero, "value_status"] = "derived_exact"
    fc.loc[zero, "method"] = "quantity is 0 → cost 0"

    est = miss & ~zero
    key = pd.MultiIndex.from_frame(fc.loc[est, ["resource_id", "unit", "currency_native"]])
    s = stats.reindex(key)
    for col, q in (("amount_native", "mid"), ("amount_native_low", "lo"), ("amount_native_high", "hi")):
        fc.loc[est, col] = fc.loc[est, "quantity"].values * s[q].values
    ok = est & fc["amount_native"].notna()
    fc.loc[ok, "value_status"] = "estimated"
    fc.loc[ok, "method"] = f"quantity × median unit price of the resource (range p{int(lo_q*100):02d}–p{int(hi_q*100)})"
    fc.loc[est & ~ok, "value_status"] = "missing"
    fc["_estimated_now"] = ok
    return fc


def _emit_cost(df, c, ctx: Context, source: str) -> None:
    fc = pd.DataFrame(index=df.index)
    fc["charge_period_start"] = df[c.get("date", "date")]
    fc["month"] = month_start(fc["charge_period_start"])
    fc["grain"] = c.get("grain", "day")
    fc["source_file"] = source
    fc["source_row"] = df["source_row"]
    fc["resource_id"] = df[c.get("resource_id", "resource_id")]
    fc["provider"] = _value(df, c.get("provider"))
    fc["service"] = _value(df, c.get("service"))
    fc["region"] = _value(df, c.get("region"))
    fc["location"] = _value(df, c["location"]) if c.get("location") else ctx.location_of_region(fc["region"])
    fc["charge_category"] = _value(df, c.get("charge_category"), "Usage")
    fc["quantity"] = pd.to_numeric(_value(df, c.get("quantity")), errors="coerce")
    fc["unit"] = _value(df, c.get("unit"))
    fc["amount_native"] = pd.to_numeric(df[c.get("amount", "amount_native")], errors="coerce")
    fc["currency_native"] = _value(df, c.get("currency", "currency_native"))
    fc["amount_native_low"] = fc["amount_native"]
    fc["amount_native_high"] = fc["amount_native"]
    fc["value_status"] = "observed"
    fc["method"] = c.get("method", "as billed")
    fc = pd.concat([fc, _resolve_allocation(df, c, ctx)], axis=1)
    fc["category"] = ctx.category_of_resource(fc["resource_id"])
    if "is_draft" in df.columns:
        fc["dq_flags"] = np.where(df["is_draft"], "draft_without_final", None)
    else:
        fc["dq_flags"] = None

    if c.get("impute") == "unit_price" and fc["amount_native"].isna().any():
        fc = _impute_unit_price(fc, ctx, source)

    rate = ctx.fx_to_chf(fc["month"], fc["currency_native"])
    fc["fx_rate_chf"] = rate
    for a, b in (("amount_native", "cost_chf"), ("amount_native_low", "cost_chf_low"),
                 ("amount_native_high", "cost_chf_high")):
        fc[b] = fc[a] * rate
    fx = ctx.tables["fx_monthly"].set_index("month")
    fc["cost_eur"] = fc["cost_chf"] / fc["month"].map(fx["eur_chf"])
    fc["cost_usd"] = fc["cost_chf"] / fc["month"].map(fx["usd_chf"])

    if "_estimated_now" in fc.columns:
        for rid, g in fc[fc["_estimated_now"]].groupby("resource_id"):
            ctx.log(source, "estimated", len(g), "missing cost estimated from quantity × unit price",
                    f"CHF {g.cost_chf.sum():,.0f} (range {g.cost_chf_low.sum():,.0f}–{g.cost_chf_high.sum():,.0f})",
                    amount_chf=g["cost_chf"].sum(), resource_id=rid)
            ctx.issues[-1]["uncertainty_chf"] = max(g.cost_chf_high.sum() - g.cost_chf.sum(),
                                                    g.cost_chf.sum() - g.cost_chf_low.sum())
        left = fc["value_status"].eq("missing").sum()
        if left:
            ctx.log(source, "missing_value", left, "cost left empty: no quantity or unit price",
                    severity="warn")
        fc = fc.drop(columns="_estimated_now")

    foreign = fc["currency_native"] != "CHF"
    if foreign.any():
        ctx.log(source, "currency_converted", foreign.sum(),
                f"{sorted(fc.loc[foreign, 'currency_native'].unique())} → CHF at the monthly rate of the usage month",
                "native amount and currency kept; EUR and USD views stored too")
    unalloc = fc["allocation_method"].eq("unallocated").sum()
    if unalloc:
        ctx.log(source, "unallocated", unalloc, "no department found", severity="warn")
    ctx.cost_parts.append(fc.reset_index(drop=True))


# ---------------------------------------------------------------- activity
def _emit_activity(df, b, ctx: Context, source: str) -> None:
    date_col = b.get("date", "date")
    ent_col = b["entity"]
    d = df.copy()
    d["_rid"] = _value(d, b.get("resource_id", "resource_id"))
    d["_dept"] = _value(d, b.get("department"))
    metrics: dict = b["metrics"]
    keys = [date_col, ent_col, "_rid", "_dept"]

    status_cols = {m: f"{m}_status" for m in metrics if f"{m}_status" in d.columns}
    for m, sc in status_cols.items():
        d[sc] = d[sc].map(STATUS_RANK)
    if b.get("agg"):
        agg = {m: b["agg"].get(m, "sum") for m in metrics}
        agg.update({sc: "max" for sc in status_cols.values()})
        d = d.groupby(keys, dropna=False).agg(agg).reset_index()

    inv_rank = {v: k for k, v in STATUS_RANK.items()}
    parts = []
    for m, unit in metrics.items():
        vals = pd.to_numeric(d[m], errors="coerce")
        keep = vals.notna()
        status = d.loc[keep, status_cols[m]].map(inv_rank) if m in status_cols else "observed"
        parts.append(pd.DataFrame({
            "date": d.loc[keep, date_col].values,
            "period": b.get("period", "day"),
            "entity_type": b.get("entity_type", ent_col),
            "entity_id": d.loc[keep, ent_col].astype(str).values,
            "resource_id": d.loc[keep, "_rid"].values,
            "department": d.loc[keep, "_dept"].values,
            "metric": b.get("rename_metrics", {}).get(m, m),
            "value": vals[keep].values,
            "unit": unit,
            "source_file": source,
            "value_status": np.asarray(status) if not isinstance(status, str) else status,
        }))
    ctx.activity_parts.append(pd.concat(parts, ignore_index=True))
