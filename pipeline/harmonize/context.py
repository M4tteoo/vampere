"""Shared state of one pipeline run: config, reference data, loaded tables,
lookups and the issues log (the «quality register»)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = ROOT / "pipeline"


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class Context:
    config: dict
    ref: dict
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    cost_parts: list[pd.DataFrame] = field(default_factory=list)
    activity_parts: list[pd.DataFrame] = field(default_factory=list)
    free_text_parts: list[pd.DataFrame] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------ setup
    @classmethod
    def load(cls, config_path: Path | None = None) -> "Context":
        config = load_yaml(config_path or PIPELINE_DIR / "config.yaml")
        ref = load_yaml(PIPELINE_DIR / "reference.yaml")
        return cls(config=config, ref=ref)

    @property
    def data_dir(self) -> Path:
        return ROOT / self.config["data_dir"]

    @property
    def output_dir(self) -> Path:
        return ROOT / self.config["output_dir"]

    @property
    def baseline(self) -> tuple[str, str]:
        b = self.config["baseline"]
        return str(b["start"]), str(b["end"])

    # ------------------------------------------------------------ issues log
    def log(self, source: str, issue_type: str, rows: int, action: str,
            detail: str = "", amount_chf: float | None = None,
            resource_id: str | None = None, severity: str = "info",
            evidence: str = "", category: str | None = None) -> None:
        """Record one fix, imputation, contradiction or observation."""
        self.issues.append({
            "issue_id": f"Q-{len(self.issues) + 1:04d}",
            "category": category,
            "source_file": source,
            "issue_type": issue_type,
            "rows_affected": int(rows),
            "action": action,
            "detail": detail,
            "amount_chf": None if amount_chf is None else round(float(amount_chf), 2),
            "resource_id": resource_id,
            "severity": severity,
            "evidence": evidence,
        })

    # --------------------------------------------------------------- lookups
    def fx_to_chf(self, months: pd.Series, currencies: pd.Series) -> pd.Series:
        """CHF per 1 unit of currency, for the usage month."""
        fx = self.tables["fx_monthly"].set_index("month")
        out = pd.Series(1.0, index=months.index)
        for cur, col in (("EUR", "eur_chf"), ("USD", "usd_chf")):
            m = currencies == cur
            out[m] = months[m].map(fx[col]).astype(float)
        return out

    def department_of_cc(self, cc: pd.Series) -> pd.Series:
        names = {int(k): v for k, v in self.ref["cost_centers"].items()}
        return pd.to_numeric(cc, errors="coerce").map(names)

    def location_of_region(self, region: pd.Series) -> pd.Series:
        return region.map(self.ref["regions"])

    def category_of_resource(self, rid: pd.Series) -> pd.Series:
        cats = self.ref["resource_categories"]
        lookup = {r: c for c, rs in cats.items() if c != "default" for r in rs}
        return rid.map(lookup).fillna(cats["default"])

    def server_resource(self, server_id: pd.Series) -> pd.Series:
        rules = [(re.compile(r["pattern"]), r["resource_id"]) for r in self.ref["server_resource_rules"]]

        def one(s: str) -> str | None:
            for rx, rid in rules:
                if rx.search(s):
                    return rid
            return None
        return server_id.map(one)

    @property
    def dim_resource(self) -> pd.DataFrame:
        return self.tables["dim_resource"]
