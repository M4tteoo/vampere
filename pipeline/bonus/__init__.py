"""Bonus features (see bonus-plan.md). One module per feature.

Module contract
---------------
A bonus module is a file pipeline/bonus/<name>.py that defines one or both of:

    def after_energy(ctx): ...   # right after the energy engine, BEFORE DuckDB and
                                 # the frontend export: may add columns to
                                 # ctx.tables["fact_cost"] (they then reach DuckDB)
    def run(ctx): ...            # at the end of the pipeline, after every export:
                                 # reads ctx / output files, writes its own outputs

Rules:
  - write only your own files (use pipeline.bonus.common: write_json, write_table,
    write_candidates, fill_baseline_row); never findings/measures/limits.json
  - every figure is a Range {low, mid, high} and carries a Calc (B3)
  - no LLM calls inside calculations

Enable a module by adding its name to `bonus.enabled` in pipeline/config.yaml.
Run a single module against the last pipeline run, without the 28 connectors:

    .venv/bin/python -m pipeline.bonus.dev <name> [<name> …]
"""
from __future__ import annotations

import importlib
import sys
import time
import traceback

from ..harmonize.context import Context

HOOKS = ("after_energy", "run")


def enabled(ctx: Context) -> list[str]:
    return list((ctx.config.get("bonus") or {}).get("enabled") or [])


def call(ctx: Context, hook: str, names: list[str] | None = None, fail_fast: bool | None = None) -> dict[str, str]:
    """Call `hook` on every enabled module (in config order). Returns {module: status}.

    A failing module is reported loudly and skipped, so one broken bonus never
    breaks the must-have outputs, unless bonus.fail_fast (or the argument) is true.
    """
    if fail_fast is None:
        fail_fast = bool((ctx.config.get("bonus") or {}).get("fail_fast", False))
    status: dict[str, str] = {}
    for name in names if names is not None else enabled(ctx):
        mod = importlib.import_module(f"{__name__}.{name}")
        fn = getattr(mod, hook, None)
        if fn is None:
            continue
        t0 = time.time()
        try:
            fn(ctx)
        except Exception as exc:  # noqa: BLE001 (isolate bonus failures)
            if fail_fast:
                raise
            status[name] = f"failed: {exc!r}"
            print(f"\n!! bonus {name}.{hook} FAILED, skipped: {exc!r}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        else:
            status[name] = f"ok ({time.time() - t0:.1f}s)"
            print(f"bonus {name}.{hook}: ok ({time.time() - t0:.1f}s)")
    return status


def after_energy(ctx: Context) -> dict[str, str]:
    return call(ctx, "after_energy")


def after_export(ctx: Context) -> dict[str, str]:
    return call(ctx, "run")
