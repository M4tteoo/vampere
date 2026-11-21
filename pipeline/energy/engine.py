"""Step 3: from usage to energy (kWh) and location-based CO2 (kg).

For every billing line in fact_cost:
    kWh = usage × energy per unit (at the observed utilisation) × PUE
    CO2 = kWh × grid intensity at the line's location
computed three times (low / mid / high factor sets). Lines without a physical
driver (support fee, credits) carry 0 kWh by definition.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..harmonize.context import Context, load_yaml

FACTORS_FILE = Path(__file__).with_name("factors.yaml")
LEVELS = ("low", "mid", "high")


def load_factors() -> dict:
    return load_yaml(FACTORS_FILE)


# ------------------------------------------------------------- utilisation
def _utilisation(ctx: Context, fc: pd.DataFrame, F: dict) -> tuple[pd.Series, pd.Series]:
    """CPU utilisation (0..1) per line from the billing exports, GPU
    utilisation from weekly monitoring. Missing → resource median → 50 %."""
    cpu = pd.Series(np.nan, index=fc.index)
    for src, table in (("azure_costs.csv", "stg_azure_costs"), ("aws_costs.csv", "stg_aws_costs")):
        m = fc["source_file"] == src
        lookup = ctx.tables[table].set_index("source_row")["cpu_avg_pct"]
        cpu[m] = fc.loc[m, "source_row"].map(lookup) / 100
    med = cpu.groupby(fc["resource_id"]).transform("median")
    met = ctx.tables["stg_server_metrics_weekly"]
    srv = fc["resource_id"].map(met.groupby("resource_id")["cpu_avg_pct"].mean() / 100)  # tier 2: server monitoring
    status = np.where(cpu.notna(), "observed", np.where(med.notna(), "resource median",
                      np.where(srv.notna(), "server metrics", "default 50 %")))
    cpu = cpu.fillna(med).fillna(srv).fillna(F["compute"]["default_utilisation"]).clip(0, 1)

    g = met[met["gpu_avg_pct"].notna()].set_index("week_start")["gpu_avg_pct"] / 100
    d = pd.to_datetime(fc["charge_period_start"])
    week = (d - pd.to_timedelta(d.dt.dayofweek, unit="D")).dt.strftime("%Y-%m-%d")
    gpu = week.map(g)
    gpu = gpu.fillna(g.median())
    fc["utilisation_source"] = status
    return cpu, gpu


# ------------------------------------------------------------------ engine
def compute(ctx: Context) -> None:
    F = load_factors()
    fc = ctx.tables["fact_cost"]
    cpu_u, gpu_u = _utilisation(ctx, fc, F)
    q = fc["quantity"].fillna(0).astype(float)
    unit = fc["unit"].fillna("")
    sh = F["shapes"]
    scenario = ctx.config.get("scenario", "ch_consumption")

    # joins to source rows for AI tokens, subscription messages, active SaaS licences
    def from_stg(src, table, col):
        m = fc["source_file"] == src
        return fc["source_row"].where(m).map(ctx.tables[table].set_index("source_row")[col])

    t_in = from_stg("ai_usage.csv", "stg_ai_usage", "tokens_in")
    t_ca = from_stg("ai_usage.csv", "stg_ai_usage", "tokens_in_cache")
    t_out = from_stg("ai_usage.csv", "stg_ai_usage", "tokens_out")
    small = from_stg("ai_usage.csv", "stg_ai_usage", "model_class") == "small"
    msgs = from_stg("ai_subscriptions.csv", "stg_ai_subscriptions", "messages_30d")
    active = from_stg("saas_contracts.csv", "stg_saas_contracts", "licences_active_30d")

    method = pd.Series("no physical driver (fee / credit) → 0 kWh", index=fc.index)
    is_credit = fc["charge_category"].isin(["Credit"])

    for lvl in LEVELS:
        c = F["compute"]
        wmin, wmax, wmem = c["cpu_w_min"][lvl], c["cpu_w_max"][lvl], c["mem_w_per_gb"][lvl]

        def p_cpu(u):
            return wmin + u * (wmax - wmin)

        it = pd.Series(0.0, index=fc.index)   # IT energy, kWh (before PUE)
        full = pd.Series(0.0, index=fc.index)  # fully loaded energy (AI, SaaS), kWh

        m = unit == "vCPU-hour"
        it[m] = q[m] * (p_cpu(cpu_u[m]) + sh["vcpu_mem_gb"] * wmem) / 1000
        method[m] = "vCPU-h × (W per vCPU at observed CPU + 2 GB memory) × PUE"
        m = unit == "vCore-hour"
        it[m] = q[m] * (p_cpu(cpu_u[m]) + sh["vcore_mem_gb"] * wmem) / 1000
        method[m] = "vCore-h × (W per vCore at observed CPU + 5.1 GB memory) × PUE"
        m = unit == "node-hour"
        it[m] = q[m] * (sh["node"]["vcpu"] * p_cpu(cpu_u[m]) + sh["node"]["ram_gb"] * wmem) / 1000
        method[m] = "node-h × (16 vCPU at observed CPU + 64 GB memory) × PUE"
        m = unit == "GPU-hour"
        g = F["gpu"]
        p_gpu = g["idle_w"][lvl] + gpu_u[m] * (g["tdp_w"] - g["idle_w"][lvl])
        it[m] = q[m] * (p_gpu + g["host"]["vcpu"] * p_cpu(cpu_u[m]) + g["host"]["ram_gb"] * wmem) / 1000
        method[m] = "GPU-h × (300-W GPU at observed GPU utilisation + 8 vCPU host + 56 GB) × PUE"
        m = unit == "capacity-day"
        pb = sh["powerbi_capacity"]
        it[m] = q[m] * 24 * (pb["vcpu"] * p_cpu(c["default_utilisation"]) + pb["ram_gb"] * wmem) / 1000
        method[m] = "capacity-day × 24 h × (8 v-cores at 50 % + 25 GB) × PUE"
        m = unit == "GB-day"
        it[m] = q[m] * F["storage"]["kwh_per_gb_day"][lvl]
        method[m] = "GB-day × kWh per GB-day (incl. replication) × PUE"
        m = unit == "GB"
        it[m] = q[m] * F["network"]["kwh_per_gb"][lvl]
        method[m] = "GB transferred × kWh per GB × PUE"
        m = unit == "runner-minute"
        it[m] = q[m] * sh["runner_vcpu"] / 60 * (p_cpu(sh["runner_utilisation"]) + sh["vcpu_mem_gb"] * wmem) / 1000
        method[m] = "runner-min × 2 vCPU / 60 at 90 % CPU × PUE"

        a = F["ai_tokens"]
        m = (unit == "tokens") & t_out.notna()
        eq = t_out[m] + a["input_weight"] * (t_in[m] - t_ca[m]) + a["cached_weight"] * t_ca[m]
        size = np.where(small[m], a["small_model_factor"], 1.0)
        full[m] = eq / 1000 * a["wh_per_1000_output_tokens"][lvl] * size / 1000
        method[m] = "output-equivalent tokens × Wh per 1000 (fully loaded, no extra PUE)"
        m = unit == "seat-month"
        full[m] = msgs[m].fillna(0) * F["ai_messages"]["wh_per_message"][lvl] / 1000
        method[m] = "messages (30 d) × Wh per message (fully loaded)"
        m = unit == "licence-month"
        full[m] = active[m].fillna(0) * F["saas"]["kwh_per_active_licence_month"][lvl]
        method[m] = "active licences × kWh per active licence-month (incl. PUE)"

        pue = np.where(fc["provider"].isin(["Azure", "AWS"]), F["pue"]["hyperscaler"][lvl],
                       np.where(fc["provider"] == "Swiss hoster", F["pue"]["hoster"][lvl], 1.0))
        kwh = it * pue + full
        kwh[is_credit] = 0.0
        fc[f"kwh_{lvl}"] = kwh

    # AI invoice adjustments: extra tokens get the average energy per token of
    # the gateway lines of the same month and model.
    adj = fc["charge_category"] == "Adjustment"
    gw = fc[(fc["source_file"] == "ai_usage.csv")]
    for lvl in LEVELS:
        per_tok = gw.groupby(["month", "service"])[f"kwh_{lvl}"].sum() / gw.groupby(["month", "service"])["quantity"].sum()
        key = pd.MultiIndex.from_frame(fc.loc[adj, ["month", "service"]])
        fc.loc[adj, f"kwh_{lvl}"] = fc.loc[adj, "quantity"].values * per_tok.reindex(key).fillna(0).values
    method[adj] = "extra invoiced tokens × average kWh per token of the gateway lines"

    for lvl in LEVELS:
        grid = pd.Series({loc: (g["variants"][scenario][lvl] if loc == "CH" and "variants" in g else g[lvl])
                          for loc, g in F["grid"].items()})
        fc[f"co2_kg_{lvl}"] = fc[f"kwh_{lvl}"] * fc["location"].map(grid).fillna(grid["EU"])
    fc["utilisation_cpu"] = np.where(unit.isin(["vCPU-hour", "vCore-hour", "node-hour", "GPU-hour"]), cpu_u.round(4), np.nan)
    fc["utilisation_gpu"] = np.where(unit == "GPU-hour", gpu_u.round(4), np.nan)
    fc["energy_method"] = method
    ctx.tables["fact_cost"] = fc

    b = fc[fc["in_baseline"]]
    no_loc = fc["location"].isna() & (fc["kwh_mid"] > 0)
    if no_loc.any():
        ctx.log("energy engine", "missing_value", no_loc.sum(), "no location → EU grid average used", severity="warn")
    defaults = (fc["utilisation_source"] == "default 50 %") & fc["unit"].isin(["vCPU-hour", "vCore-hour", "node-hour", "GPU-hour"])
    ctx.log("energy engine", "energy_computed", len(b),
            f"kWh and location-based CO2 (scenario {scenario}) for every baseline line",
            f"baseline: {b.kwh_mid.sum():,.0f} kWh (range {b.kwh_low.sum():,.0f}–{b.kwh_high.sum():,.0f}), "
            f"{b.co2_kg_mid.sum():,.0f} kg CO2 (range {b.co2_kg_low.sum():,.0f}–{b.co2_kg_high.sum():,.0f}); "
            f"{int(defaults.sum())} compute lines used the 50 % default utilisation")


# -------------------------------------------------------- factor export
def template_rows(F: dict | None = None) -> list[dict]:
    """Factors as reported in factors.json and template_baseline_and_assumptions.csv.
    Per-unit energy values are derived from the coefficients at a stated utilisation."""
    F = F or load_factors()
    c, sh, g = F["compute"], F["shapes"], F["gpu"]

    def lvl3(fn):
        return {lvl: fn(lvl) for lvl in LEVELS}

    def p(lvl, u):
        return c["cpu_w_min"][lvl] + u * (c["cpu_w_max"][lvl] - c["cpu_w_min"][lvl])

    u = c["default_utilisation"]
    rows = []
    for loc, gr in F["grid"].items():
        rows.append({"id": gr["template"] or f"grid_mix_location_based_{loc.lower()}", "label": gr["label"],
                     "unit": "kg CO2 per kWh", **{k: gr[k] for k in LEVELS}, "source": gr["source"],
                     "calculation": gr["calculation"], "applies_to": [loc],
                     "must_or_bonus": "Must" if gr["template"] else "Extra",
                     **({"variants": gr["variants"]} if "variants" in gr else {})})
    for key, pu in F["pue"].items():
        rows.append({"id": pu["template"] or f"pue_{key}", "label": pu["label"], "unit": "ratio",
                     **{k: pu[k] for k in LEVELS}, "source": pu["source"], "calculation": pu["calculation"],
                     "applies_to": ["Azure", "AWS"] if key == "hyperscaler" else ["Swiss hoster"],
                     "must_or_bonus": "Must" if pu["template"] else "Extra"})
    rows += [
        {"id": "energy_per_vcpu_hour", "label": "Energy per vCPU-hour (at 50 % CPU, incl. 2 GB memory)", "unit": "kWh",
         **lvl3(lambda l: round((p(l, u) + sh["vcpu_mem_gb"] * c["mem_w_per_gb"][l]) / 1000, 5)),
         "source": c["source"], "calculation": "(Wmin + u × (Wmax − Wmin) + 2 GB × W/GB) / 1000; the engine uses the "
         "observed CPU utilisation of each line instead of 50 %. " + c["calculation"],
         "applies_to": ["vCPU-hour", "vCore-hour", "runner-minute"], "must_or_bonus": "Must"},
        {"id": "energy_per_node_hour", "label": "Energy per node-hour (16 vCPU, 64 GB, at 50 % CPU)", "unit": "kWh",
         **lvl3(lambda l: round((16 * p(l, u) + 64 * c["mem_w_per_gb"][l]) / 1000, 4)),
         "source": c["source"], "calculation": "(16 × W per vCPU + 64 GB × W/GB) / 1000; observed utilisation per line in the engine",
         "applies_to": ["node-hour"], "must_or_bonus": "Must"},
        {"id": "energy_per_gpu_hour", "label": "Energy per GPU-hour (300-W class at 10 % GPU, incl. host)", "unit": "kWh",
         **lvl3(lambda l: round((g["idle_w"][l] + 0.10 * (g["tdp_w"] - g["idle_w"][l])
                                 + g["host"]["vcpu"] * p(l, 0.05) + g["host"]["ram_gb"] * c["mem_w_per_gb"][l]) / 1000, 4)),
         "source": g["source"], "calculation": g["calculation"] + " Shown at 10 % GPU / 5 % host CPU (observed level); "
         "the engine uses the weekly measured GPU utilisation.", "applies_to": ["GPU-hour"], "must_or_bonus": "Must"},
        {"id": "energy_per_gb_storage_day", "label": "Energy per GB-day of storage", "unit": "kWh",
         **F["storage"]["kwh_per_gb_day"], "source": F["storage"]["source"], "calculation": F["storage"]["calculation"],
         "applies_to": ["GB-day"], "must_or_bonus": "Must"},
        {"id": "energy_per_gb_network", "label": "Energy per GB transferred", "unit": "kWh",
         **F["network"]["kwh_per_gb"], "source": F["network"]["source"], "calculation": F["network"]["calculation"],
         "applies_to": ["GB"], "must_or_bonus": "Extra"},
        {"id": "energy_per_1000_tokens", "label": "Energy per 1000 output-equivalent tokens (large model)", "unit": "kWh",
         **{k: v / 1000 for k, v in F["ai_tokens"]["wh_per_1000_output_tokens"].items()},
         "source": F["ai_tokens"]["source"], "calculation": F["ai_tokens"]["calculation"],
         "applies_to": ["tokens"], "must_or_bonus": "Must"},
        {"id": "energy_per_subscription_message", "label": "Energy per message in an AI subscription", "unit": "kWh",
         **{k: v / 1000 for k, v in F["ai_messages"]["wh_per_message"].items()},
         "source": F["ai_messages"]["source"], "calculation": F["ai_messages"]["calculation"],
         "applies_to": ["seat-month"], "must_or_bonus": "Must"},
        {"id": "energy_per_active_saas_licence_month", "label": "Energy per active SaaS licence-month", "unit": "kWh",
         **F["saas"]["kwh_per_active_licence_month"], "source": F["saas"]["source"],
         "calculation": F["saas"]["calculation"], "applies_to": ["licence-month"], "must_or_bonus": "Extra"},
    ]
    return rows
