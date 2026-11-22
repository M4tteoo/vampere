"""Read-only access to the pipeline results: DuckDB (opened read-only per query)
and the JSON files in output/. Nothing here can write or change data."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.bonus.text_risk import load_cache, risk_of

from .settings import Settings


class DataStore:
    def __init__(self, settings: Settings):
        self.s = settings
        self._json: dict[str, tuple[float, dict]] = {}
        self._risk = load_cache()

    # -------------------------------------------------------------- DuckDB
    def sql(self, query: str, params: list | None = None) -> pd.DataFrame:
        """Parameterised read-only query. Tools build queries from whitelisted
        identifiers only; values always go through params."""
        if not self.s.duckdb_file.exists():
            raise FileNotFoundError("output/greenops.duckdb missing: run `python -m pipeline.run`")
        con = duckdb.connect(str(self.s.duckdb_file), read_only=True)
        try:
            return con.execute(query, params or []).df()
        finally:
            con.close()

    # ------------------------------------------------------------ JSON files
    def output(self, name: str) -> dict | None:
        """output/<name> (cached until the file changes), None if not produced yet."""
        path: Path = self.s.output_dir / name
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        hit = self._json.get(name)
        if hit is None or hit[0] != mtime:
            with open(path, encoding="utf-8") as fh:
                hit = (mtime, json.load(fh))
            self._json[name] = hit
        return hit[1]

    def entity_ids(self) -> set[str]:
        return {e["id"] for e in (self.output("entities.json") or {}).get("entities", [])}

    def related_ids(self, entity_id: str) -> set[str]:
        """The entity, its parent resource and its children (a server ↔ its resource): measures may act on
        either level (e.g. M-04 on res:gpu-ml, M-07 on srv:gpu-ml-01). Rooms, locations and the company are
        not expanded (their «children» are half the scene)."""
        ents = (self.output("entities.json") or {}).get("entities", [])
        by_id = {e["id"]: e for e in ents}
        out = {entity_id}
        if not entity_id.startswith(("res:", "srv:", "lic:", "ai:")):
            return out
        parent = (by_id.get(entity_id) or {}).get("parent_id")
        if parent and parent.startswith("res:"):
            out.add(parent)
        out |= {e["id"] for e in ents if e.get("parent_id") == entity_id}
        return out

    # ------------------------------------------------------------- free text
    def text_risk(self, text: str | None) -> str:
        return risk_of(text, self._risk)
