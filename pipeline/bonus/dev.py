"""Run bonus modules against the last pipeline run, without the 28 connectors.

    .venv/bin/python -m pipeline.bonus.dev clusters            # run(ctx) of one module
    .venv/bin/python -m pipeline.bonus.dev market --hook after_energy
    .venv/bin/python -m pipeline.bonus.dev clusters forecast --out output/ch_production

The context is rebuilt from output/greenops.duckdb (every table, DATE columns
back to "YYYY-MM-DD" strings as in the live pipeline, JSON columns decoded)
plus ctx.issues / ctx.sources / ctx.export_summary. Errors are raised (fail fast).

Note: columns added by an after_energy hook only reach DuckDB in a full run
(python -m pipeline.run); with --hook after_energy they live in memory only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

from ..harmonize.context import ROOT, Context
from . import HOOKS, call


def _decode_json(s: pd.Series) -> pd.Series:
    vals = s.dropna()
    if not vals.empty and vals.isin(["True", "False"]).all():  # mixed bool/None columns stored as text
        return s.map({"True": True, "False": False})
    if vals.empty or not vals.map(lambda v: isinstance(v, str) and v[:1] in "[{").all():
        return s
    try:
        return s.map(lambda v: json.loads(v) if isinstance(v, str) else v)
    except ValueError:
        return s


def load_context(out_dir: str | None = None) -> Context:
    ctx = Context.load()
    if out_dir:
        ctx.config["output_dir"] = out_dir
        ctx.config["duckdb_file"] = str(Path(out_dir) / "greenops.duckdb")
    path = ROOT / ctx.config["duckdb_file"]
    if not path.exists():
        sys.exit(f"{path} not found: run `python -m pipeline.run` first")
    con = duckdb.connect(str(path), read_only=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE'").fetchall()]
        for name in names:
            df = con.execute(f'SELECT * FROM "{name}"').df()
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    df[c] = df[c].dt.strftime("%Y-%m-%d").where(df[c].notna(), None)
                elif pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
                    df[c] = _decode_json(df[c])
            ctx.tables[name] = df
    finally:
        con.close()

    def records(df: pd.DataFrame) -> list[dict]:
        return [{k: (None if not isinstance(v, (list, dict)) and pd.isna(v) else v) for k, v in r.items()}
                for r in df.to_dict("records")]
    ctx.issues = records(ctx.tables.get("issues", pd.DataFrame()))
    ctx.sources = records(ctx.tables.get("sources", pd.DataFrame()))
    summary = ctx.output_dir / "summary.json"
    if summary.exists():
        with open(summary, encoding="utf-8") as fh:
            ctx.export_summary = json.load(fh)
    return ctx


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.bonus.dev", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("modules", nargs="+", help="module names in pipeline/bonus/")
    p.add_argument("--hook", choices=[*HOOKS, "both"], default="run")
    p.add_argument("--out", help="output folder of the run to load (default: config output_dir)")
    a = p.parse_args(argv)
    ctx = load_context(a.out)
    hooks = HOOKS if a.hook == "both" else (a.hook,)
    for hook in hooks:
        call(ctx, hook, names=a.modules, fail_fast=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
