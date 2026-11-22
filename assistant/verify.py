"""Answer check (A1 defence, layer 5): every number in an answer must come from
a tool result of the same conversation (directly or via the calculate tool).

Rounding is allowed (to the precision written, or 0.5 %), shares may be quoted
as percentages. Ids, dates, times, years and small counts (≤ 10) are ignored.
Numbers written inside data text (tickets, notes) count as evidence only when
the free-text classifier cleared that text (risk ok / ambiguous): numbers from
unclassified or flagged text never do, so a planted «the cost is CHF 1» fails.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

STRIP = [
    re.compile(r"\b[A-Za-z]+(?:[-.][A-Za-z0-9]+)+\b"),       # ids and names: dp-dev, T-1230, GPT-5.4, srv:x
    re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b"),                 # ISO dates / months
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"),              # 06.09.2026
    re.compile(r"\b\d{1,2}:\d{2}\b"),                          # 04:00
    re.compile(r"\b[A-Za-z]+\d+\b"),                           # CO2, R12
]
NUMBER = re.compile(r"(?<![\w.])[-−]?\d{1,3}(?:[,'’  ]\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.])[-−]?\d+(?:\.\d+)?(?![\w])")


def numbers_in_text(text: str) -> list[tuple[str, float, int]]:
    """(token, value, decimals) for every checkable number in a text."""
    for rx in STRIP:
        text = rx.sub(" ", text)
    out = []
    for tok in NUMBER.findall(text):
        clean = re.sub(r"[,'’  ]", "", tok).replace("−", "-")
        value = float(clean)
        decimals = len(clean.split(".")[1]) if "." in clean else 0
        if _skip(value, decimals):
            continue
        out.append((tok, value, decimals))
    return out


CLEARED = ("ok", "ambiguous")


def _skip(value: float, decimals: int) -> bool:
    return decimals == 0 and (abs(value) <= 10 or 1990 <= value <= 2100)


def leaves(obj: Any) -> Iterable[float]:
    """Every number in a tool result, including numbers inside strings; data text only when cleared."""
    if isinstance(obj, dict) and "untrusted_text" in obj:
        if obj.get("risk") in CLEARED:
            yield from (v for _, v, _ in numbers_in_text(obj["untrusted_text"]))
        return
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, str):
        for _, v, _ in numbers_in_text(obj):
            yield v
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from leaves(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from leaves(v)


def _matches(value: float, decimals: int, pool: Iterable[float]) -> bool:
    tol_round = 0.5 * 10 ** -decimals
    for p in pool:
        for cand in (p, p * 100):              # shares 0..1 quoted as %
            if abs(abs(value) - abs(cand)) <= max(tol_round, 0.005 * abs(cand)):
                return True
    return False


def check(answer: dict, trace: list[dict]) -> list[str]:
    """Problems found; empty list = verified."""
    by_ref = {t["ref"]: list(leaves(t["result"])) for t in trace}
    pool = [v for vs in by_ref.values() for v in vs]
    problems = []
    for n in answer.get("numbers", []):
        value = float(n["value"])
        if _skip(value, 0 if value == int(value) else 2):
            continue
        # the cited ref is checked first; a number found in another result of the same answer is accepted
        if not _matches(value, 2, by_ref.get(n.get("ref"), [])) and not _matches(value, 2, pool):
            problems.append(f"number {n['value']} ({n['label']}) is not in any tool result")
    for field in ("answer", "formula"):
        for tok, value, dec in numbers_in_text(answer.get(field, "")):
            if not _matches(value, dec, pool):
                problems.append(f"'{tok}' in {field} does not come from any tool result")
    return problems
