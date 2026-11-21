"""Small normalisers shared by all sources."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

_PROJECT_RX = re.compile(r"^\s*[Pp]\s*-?\s*0*(\d{1,3})\s*$")


def normalize_project_id(value) -> str | None:
    """P001 / p-001 / P-1 → P-001. Unparseable values stay as they are."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _PROJECT_RX.match(s)
    return f"P-{int(m.group(1)):03d}" if m else s


def month_start(dates: pd.Series) -> pd.Series:
    """'YYYY-MM-DD…' (string or datetime) → 'YYYY-MM-01'."""
    d = pd.to_datetime(dates)
    return d.dt.strftime("%Y-%m-01")


def nonempty(s: pd.Series) -> pd.Series:
    """Treat empty strings as missing (empty = «not recorded», never zero)."""
    return s.replace(r"^\s*$", np.nan, regex=True)
