"""Research tool for A5: hourly CO2 intensity profiles for CH, DE, IE.

NOT a pipeline step (the pipeline stays offline). Run once; the derived, small
profile is committed and read by pipeline/bonus/carbon_aware.py:

    .venv/bin/python -m pipeline.bonus.hourly_intensity fetch   # ~4 min (API limit: 2 requests/min)
    .venv/bin/python -m pipeline.bonus.hourly_intensity build   # → data/hourly_intensity.csv + _meta.json

Source: Energy-Charts API (Fraunhofer ISE), public net electricity production per
technology, 15-min, baseline year Sep 2025 – Aug 2026, licence CC BY 4.0
(attribution: energy-charts.info). Raw downloads are cached in data/.cache/ (git-ignored).

Method
  1. Production intensity per country and quarter-hour:
       I(t) = Σ_tech generation(t) × EF_tech / Σ_tech generation(t)
     EF = IPCC AR5 WG III Annex III life-cycle medians (the default of Electricity Maps);
     storage discharge is left out (its energy was counted when it was generated).
  2. Switzerland: consumption mix incl. imports (our factors.yaml choice). Physical
     imports per border (cbpf) carry the neighbour's production intensity:
       I_CH(t) = (Σ gen_CH × EF + Σ_n import_n(t) × I_n(t)) / (Σ gen_CH + Σ_n import_n(t))
  3. Hourly means in Basel local time (Europe/Zurich: the scheduler's clock), then a
     profile per location × month × day type (workday / weekend) × hour.
  4. SHAPE ONLY: each profile is divided by its load-weighted yearly mean. The
     carbon-aware module multiplies this relative factor by the location-based factor
     of factors.yaml, so hourly results add up to the same yearly CO2 as the engine.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA = HERE / "data"
CACHE = DATA / ".cache"
PROFILE_FILE = DATA / "hourly_intensity.csv"
META_FILE = DATA / "hourly_intensity_meta.json"

API = "https://api.energy-charts.info/v2"
START, END = "2025-09-01", "2026-08-31"          # baseline year
LOCAL_TZ = "Europe/Zurich"
TARGETS = {"CH": "ch", "DE": "de", "IE": "ie"}  # our locations → Energy-Charts country
NEIGHBOURS = {"de": "germany", "fr": "france", "at": "austria", "it": "italy"}  # Swiss borders (cbpf ids)

# g CO2eq per kWh, life-cycle medians, IPCC AR5 WG III Annex III (2014), Table A.III.2.
# Not in the IPCC table (assumptions): oil 650 (Electricity Maps default), peat 1100 (above coal:
# peat emits more CO2 per kWh than hard coal), others / waste 700 (unknown, fossil-heavy).
EF = {
    "fossil_brown_coal_lignite": 820, "fossil_hard_coal": 820, "fossil_coal_derived_gas": 820,
    "fossil_gas": 490, "fossil_oil": 650, "fossil_peat": 1100, "others": 700, "waste": 700,
    "biomass": 230, "geothermal": 38, "nuclear": 12, "solar": 48,
    "wind_onshore": 11, "wind_offshore": 12,
    "hydro_run_of_river": 24, "hydro_water_reservoir": 24,
}
SKIP = ("storage", "battery", "load", "share", "cross_border", "residual")  # not generation (storage = re-delivered)


# ------------------------------------------------------------------- fetch
def _get(endpoint: str, country: str) -> Path:
    path = CACHE / f"{endpoint}_{country}_{START}_{END}.json"
    if path.exists():
        return path
    url = f"{API}/{endpoint}?country={country}&start={START}&end={END}"
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                path.write_bytes(r.read())
            print(f"  fetched {endpoint} {country}")
            time.sleep(31)                       # API limit: 2 requests / minute
            return path
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            wait = int(e.headers.get("Retry-After", 60))
            print(f"  429, waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}")


def fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for c in sorted(set(TARGETS.values()) | set(NEIGHBOURS)):
        _get("public_power", c)          # NEIGHBOURS: dict → its country codes
    _get("cbpf", "ch")


# ------------------------------------------------------------------- build
def _frame(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    df = pd.DataFrame([r["values"] for r in d["data"]],
                      index=pd.to_datetime([r["timestamp"] for r in d["data"]], utc=True))
    return df.apply(pd.to_numeric, errors="coerce")


def _production(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, list[str]]:
    """(generation MW, emissions g/h-equivalent, unknown techs) per quarter-hour."""
    gen_cols = [c for c in df.columns if not any(s in c for s in SKIP)]
    unknown = [c for c in gen_cols if c not in EF]
    g = df[gen_cols].clip(lower=0).fillna(0)
    ef = pd.Series({c: EF.get(c, EF["others"]) for c in gen_cols})
    return g.sum(1), (g * ef).sum(1), unknown


def build() -> dict:
    prod = {c: _frame(CACHE / f"public_power_{c}_{START}_{END}.json")
            for c in sorted(set(TARGETS.values()) | set(NEIGHBOURS))}
    gen, emis, intensity, unknown = {}, {}, {}, {}
    for c, df in prod.items():
        gen[c], emis[c], unknown[c] = _production(df)
        intensity[c] = emis[c] / gen[c].replace(0, np.nan)

    # Switzerland: consumption mix with physical imports at the neighbour's intensity.
    # cbpf: GW, positive = import (attributes.sign_convention); generation is in MW.
    flows = _frame(CACHE / f"cbpf_ch_{START}_{END}.json").resample("1h").mean()
    gen_ch, emis_ch = gen["ch"].resample("1h").mean(), emis["ch"].resample("1h").mean()
    imp_g, imp_e = pd.Series(0.0, index=gen_ch.index), pd.Series(0.0, index=gen_ch.index)
    for code, border in NEIGHBOURS.items():
        imports = flows[border].reindex(gen_ch.index).fillna(0).clip(lower=0) * 1000   # GW → MW
        imp_g += imports
        imp_e += imports * intensity[code].resample("1h").mean().reindex(gen_ch.index).ffill()
    ch_cons = (emis_ch + imp_e) / (gen_ch + imp_g)
    import_share = float(imp_g.sum() / (gen_ch.sum() + imp_g.sum()))

    series = {"CH": (ch_cons, gen_ch + imp_g),
              "DE": (intensity["de"], prod["de"].get("load", gen["de"])),
              "IE": (intensity["ie"], prod["ie"].get("load", gen["ie"]))}
    rows, stats = [], {}
    for loc, (i_q, load_q) in series.items():
        h = pd.DataFrame({"i": i_q, "load": load_q}).resample("1h").mean().dropna()
        h.index = h.index.tz_convert(LOCAL_TZ)
        annual = float((h["i"] * h["load"]).sum() / h["load"].sum())
        h["month"], h["hour"] = h.index.month, h.index.hour
        h["day_type"] = np.where(h.index.dayofweek >= 5, "weekend", "workday")
        prof = h.groupby(["month", "day_type", "hour"])["i"].mean().reset_index()
        prof["location"] = loc
        prof["relative"] = prof["i"] / annual
        rows.append(prof.rename(columns={"i": "g_per_kwh"}))
        daily = h.groupby(h.index.date)["i"]
        by_hour = h.groupby("hour")["i"].mean()
        winter = h[h["month"].isin([12, 1, 2])].groupby("hour")["i"].mean()
        summer = h[h["month"].isin([6, 7, 8])].groupby("hour")["i"].mean()
        stats[loc] = {
            "annual_load_weighted_g_per_kwh": round(annual, 1),
            "hourly_min_max_g_per_kwh": [round(float(h["i"].min()), 1), round(float(h["i"].max()), 1)],
            "median_daily_spread_pct": round(float(((daily.max() - daily.min()) / daily.mean()).median() * 100), 1),
            "cleanest_hour_year": int(by_hour.idxmin()), "dirtiest_hour_year": int(by_hour.idxmax()),
            "winter_cleanest_dirtiest_hour": [int(winter.idxmin()), int(winter.idxmax())],
            "summer_cleanest_dirtiest_hour": [int(summer.idxmin()), int(summer.idxmax())],
            "hourly_profile_year_rel": [round(float(v / annual), 3) for v in by_hour.values],
            "hours": int(len(h)),
        }
    out = pd.concat(rows)[["location", "month", "day_type", "hour", "g_per_kwh", "relative"]]
    out = out.round({"g_per_kwh": 1, "relative": 4}).sort_values(["location", "month", "day_type", "hour"])
    DATA.mkdir(exist_ok=True)
    out.to_csv(PROFILE_FILE, index=False)
    meta = {
        "source": "Energy-Charts API (Fraunhofer ISE), /v2/public_power and /v2/cbpf, 15-min, "
                  f"{START} … {END}; licence CC BY 4.0, attribution: energy-charts.info; retrieved 2026-11-21",
        "emission_factors_g_per_kwh": EF,
        "emission_factors_source": "IPCC AR5 WG III (2014) Annex III, life-cycle medians (Electricity Maps default "
                                   "method); oil 650, peat 1100 and unknown/waste 700 are assumptions",
        "switzerland": "consumption mix incl. physical imports from " + ", ".join(NEIGHBOURS.values())
                       + f" at the neighbour's production intensity; imports = {import_share:.1%} of supply",
        "use": "relative = hourly intensity / load-weighted yearly mean (shape only); absolute level comes from "
               "pipeline/energy/factors.yaml (location-based factor)",
        "time": f"hours in {LOCAL_TZ} (scheduler clock in Basel)",
        "unknown_technologies_mapped_to_others": {c: u for c, u in unknown.items() if u},
        "stats": stats,
    }
    with open(META_FILE, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta



if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "fetch":
        fetch()
    else:
        print(json.dumps(build()["stats"], indent=1))
