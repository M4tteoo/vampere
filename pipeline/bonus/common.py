"""Shared helpers for the bonus modules: JSON and DuckDB output, candidate
findings / measures for the Step 5–6 owners, and patching the Bonus rows of the
submission templates (without editing pipeline/export/submission.py)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb
import pandas as pd

from ..export.frontend import SUMS, Calc, metrics, scale, zero_metrics  # noqa: F401 (re-exported)
from ..harmonize.context import ROOT, Context
from ..harmonize.store import _jsonable, _meta

BASELINE_TEMPLATE = "template_baseline_and_assumptions.csv"
MEASURES_TEMPLATE = "template_measures_package.csv"
CANDIDATES_FILE = "bonus/candidates.json"


# ------------------------------------------------------------------ ranges
def rng(low, mid, high, nd: int = 2) -> dict:
    """A contract Range {low, mid, high}."""
    def r(v):
        return None if v is None or pd.isna(v) else round(float(v), nd)
    return {"low": r(low), "mid": r(mid), "high": r(high)}


# -------------------------------------------------------------------- JSON
def write_json(ctx: Context, name: str, payload: dict) -> Path:
    """Write output/<name> with the standard contract `meta` block first."""
    path = ctx.output_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"meta": _meta(ctx), **{k: v for k, v in payload.items() if k != "meta"}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, ensure_ascii=False, indent=1, default=_jsonable)
    return path


def read_output(ctx: Context, name: str) -> dict | None:
    """Read an output file of another step (e.g. measures.json) if it exists yet."""
    path = ctx.output_dir / name
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_example(name: str) -> dict:
    """Contract sample (contract/examples/<name>): the mock to build on until the real file exists."""
    with open(ROOT / "contract" / "examples" / name, encoding="utf-8") as fh:
        return json.load(fh)


def read_output_or_example(ctx: Context, name: str) -> tuple[dict, bool]:
    """(data, is_mock): the real output file if present, otherwise the contract sample."""
    real = read_output(ctx, name)
    return (real, False) if real is not None else (read_example(name), True)


# ------------------------------------------------------------------ DuckDB
def write_table(ctx: Context, name: str, df: pd.DataFrame) -> None:
    """Store a table in ctx and (create or replace) in output/greenops.duckdb,
    so the assistant and SQL users can query bonus results too. Call from run()."""
    ctx.tables[name] = df
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object and df[c].map(type).isin([list, dict]).any():
            df[c] = df[c].map(lambda v: json.dumps(v, default=_jsonable) if isinstance(v, (list, dict)) else v)
    con = duckdb.connect(str(ROOT / ctx.config["duckdb_file"]))
    try:
        con.register("_df", df)
        con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _df')
        con.unregister("_df")
    finally:
        con.close()


# -------------------------------------------------------------- candidates
def write_candidates(ctx: Context, module: str, findings: list[dict] = (), measures: list[dict] = ()) -> Path:
    """Propose findings / measures (contract Finding / Measure format) to the Step 5–6
    owners in output/bonus/candidates.json. Each module replaces only its own entry;
    the owners decide what to merge into findings.json / measures.json."""
    path = ctx.output_dir / CANDIDATES_FILE
    data = {}
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh).get("by_module", {})
    data[module] = {"findings": list(findings), "measures": list(measures)}
    return write_json(ctx, CANDIDATES_FILE, {"by_module": data})


# --------------------------------------------------------------- templates
def patch_template(ctx: Context, template: str, key_column: str, updates: dict[str, dict]) -> None:
    """Update cells of an already written output/submission/<template>.

    updates = {row key: {column: value}}; unknown keys are appended as new rows.
    Keeps the column order and the UTF-8 BOM of the original."""
    path = ctx.output_dir / "submission" / template
    if not path.exists():
        raise FileNotFoundError(f"{path} not written yet (the template export must run first)")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    for key, values in updates.items():
        bad = set(values) - set(columns)
        if bad:
            raise KeyError(f"{template}: unknown columns {sorted(bad)}")
        row = next((r for r in rows if r[key_column] == key), None)
        if row is None:
            row = {c: "" for c in columns} | {key_column: key}
            rows.append(row)
        row.update({k: "" if v is None else str(v) for k, v in values.items()})
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)


def _fmt(v, nd: int = 6) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    v = float(v)
    return f"{v:.0f}" if abs(v) >= 100 else f"{v:.{nd}g}"


def fill_baseline_row(ctx: Context, parameter: str, *, low, mid, high, source: str, calculation: str,
                      unit: str | None = None) -> None:
    """Fill one row (e.g. a «Bonus» row such as growth_per_year) of
    output/submission/template_baseline_and_assumptions.csv."""
    values = {"value_low": _fmt(low), "value_mid": _fmt(mid), "value_high": _fmt(high),
              "source": source, "calculation_or_assumption": calculation}
    if unit is not None:
        values["unit"] = unit
    patch_template(ctx, BASELINE_TEMPLATE, "parameter", {parameter: values})
