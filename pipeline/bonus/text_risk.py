"""Free-text risk (A1 defence, layer 2): copy the LLM classifier's verdicts into
free_text.text_risk, so the assistant, the limits (Limit.quote_risk) and the
Intake screen can withhold texts that try to instruct AI systems.

The verdicts live in pipeline/bonus/text_risk.json, written by
`python -m assistant classify` and committed: the pipeline itself never calls
an LLM and stays offline and deterministic. Texts not in the file stay
«unchecked» (shown as data, never followed).

Labels: ok · ambiguous (directive aimed at humans, e.g. «please exclude from
analyses»: shown, never followed) · flagged (instruction aimed at AI systems:
withheld) · unchecked.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from ..harmonize.context import Context

CACHE_FILE = Path(__file__).with_name("text_risk.json")
LABELS = ("ok", "ambiguous", "flagged")


def text_key(text: str) -> str:
    """Stable id of a text (same text in many rows → one verdict)."""
    return hashlib.sha256(str(text).strip().encode("utf-8")).hexdigest()[:16]


def load_cache() -> dict[str, dict]:
    if not CACHE_FILE.exists():
        return {}
    with open(CACHE_FILE, encoding="utf-8") as fh:
        return json.load(fh).get("verdicts", {})


def risk_of(text: str | None, cache: dict[str, dict] | None = None) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return "ok"
    v = (cache if cache is not None else load_cache()).get(text_key(text))
    return v["risk"] if v else "unchecked"


def after_energy(ctx: Context) -> None:
    ft = ctx.tables["free_text"]
    cache = load_cache()
    ft["text_risk"] = ft["text"].map(lambda t: risk_of(t, cache))
    ctx.tables["free_text"] = ft
    counts = ft.drop_duplicates("text")["text_risk"].value_counts().to_dict()
    flagged = ft[ft["text_risk"] == "flagged"]
    ctx.log("free text", "free_text_classified", len(ft),
            "LLM verdicts applied (pipeline/bonus/text_risk.json); flagged texts are withheld from the "
            "assistant and from displays, every row stays in the calculations",
            f"distinct texts by risk: {counts}",
            evidence="; ".join(f"{r.source_file} {r.field} {r.record_key or ''}".strip()
                               for r in flagged.drop_duplicates("text").itertuples()))
