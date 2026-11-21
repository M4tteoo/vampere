"""Steps that need all sources loaded: build the shared tables, fill gaps,
tag one-off events, propose anomaly candidates, apply the materiality rule."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .context import Context


# ------------------------------------------------------------------ tables
def build_tables(ctx: Context) -> None:
    fc = pd.concat(ctx.cost_parts, ignore_index=True)
    ctx.tables["fact_cost"] = fc
    ctx.tables["fact_activity"] = pd.concat(ctx.activity_parts, ignore_index=True)
    ctx.tables["free_text"] = pd.concat(ctx.free_text_parts, ignore_index=True)


def finalize_fact_cost(ctx: Context) -> None:
    fc = ctx.tables["fact_cost"]
    b0, b1 = ctx.baseline
    day = fc["grain"] == "day"
    fc["in_baseline"] = np.where(day, fc["charge_period_start"].between(b0, b1),
                                 fc["month"].between(b0, b1))
    fc.insert(0, "cost_id", np.arange(1, len(fc) + 1))
    ctx.tables["fact_cost"] = fc

    # enrich dim_resource with where/who bills it (most frequent values)
    dim = ctx.tables["dim_resource"]
    mode = fc.groupby("resource_id").agg(
        provider=("provider", lambda s: s.mode().iat[0] if s.notna().any() else None),
        location=("location", lambda s: s.mode().iat[0] if s.notna().any() else None),
        region=("region", lambda s: s.mode().iat[0] if s.notna().any() else None))
    ctx.tables["dim_resource"] = dim.drop(columns=[c for c in mode.columns if c in dim.columns]) \
        .merge(mode, left_on="resource_id", right_index=True, how="left")


# --------------------------------------------------------------- gap fill
def fill_gaps(ctx: Context) -> None:
    cfg = ctx.config["imputation"]
    fc = ctx.tables["fact_cost"]
    cal = ctx.tables["dim_date"][["date", "workday"]]
    win = int(cfg["gap_fill_window_days"])
    new_rows = []
    for (src, rid), g in fc[(fc["grain"] == "day") & fc["source_file"].isin(cfg["gap_fill_sources"])
                            & (fc["charge_category"] != "Credit")].groupby(["source_file", "resource_id"]):
        present = set(g["charge_period_start"])
        span = cal[(cal["date"] >= min(present)) & (cal["date"] <= max(present))]
        weekend_days = set(span.loc[span["workday"] == 0, "date"])
        workday_only = len(present & weekend_days) < 0.2 * max(len(weekend_days), 1)
        expected = set(span.loc[span["workday"] == 1, "date"]) if workday_only else set(span["date"])
        coverage = len(present & expected) / max(len(expected), 1)
        missing = sorted(expected - present)
        if not missing:
            continue
        if coverage < cfg["gap_fill_min_coverage"]:
            ctx.log(src, "periodic_resource", 0, "not gap-filled: bills on few days (periodic charge)",
                    f"coverage {coverage:.0%}", resource_id=rid)
            continue
        daily = g.groupby("charge_period_start").agg(
            cost_chf=("cost_chf", "sum"), amount_native=("amount_native", "sum"),
            quantity=("quantity", "sum")).sort_index()
        template = g.iloc[-1]
        dates = pd.to_datetime(daily.index)
        for d in missing:
            dt = pd.Timestamp(d)
            near = daily[(abs((dates - dt).days) <= win)]
            if near.empty:
                continue
            row = template.copy()
            row["charge_period_start"] = d
            row["month"] = d[:7] + "-01"
            row["source_row"] = None
            for col in ("cost_chf", "amount_native", "quantity"):
                row[col] = near[col].median()
            row["amount_native_low"] = near["amount_native"].min()
            row["amount_native_high"] = near["amount_native"].max()
            rate = ctx.fx_to_chf(pd.Series([row["month"]]), pd.Series([row["currency_native"]])).iat[0]
            fx = ctx.tables["fx_monthly"].set_index("month")
            row["fx_rate_chf"] = rate
            row["cost_chf"] = row["amount_native"] * rate
            row["cost_chf_low"] = row["amount_native_low"] * rate
            row["cost_chf_high"] = row["amount_native_high"] * rate
            row["cost_eur"] = row["cost_chf"] / fx.loc[row["month"], "eur_chf"]
            row["cost_usd"] = row["cost_chf"] / fx.loc[row["month"], "usd_chf"]
            row["value_status"] = "estimated"
            row["method"] = f"missing day filled with median of ±{win} neighbouring days (range min–max)"
            row["dq_flags"] = "gap_filled"
            new_rows.append(row)
        filled = [r for r in new_rows if r["resource_id"] == rid and r["source_file"] == src]
        if filled:
            ctx.log(src, "gap_filled", len(filled), "missing billing days filled",
                    f"days {', '.join(r['charge_period_start'] for r in filled[:6])}{' …' if len(filled) > 6 else ''}",
                    amount_chf=sum(r["cost_chf"] for r in filled), resource_id=rid)
            mid = sum(r["cost_chf"] for r in filled)
            ctx.issues[-1]["uncertainty_chf"] = max(sum(r["cost_chf_high"] for r in filled) - mid,
                                                    mid - sum(r["cost_chf_low"] for r in filled))
    if new_rows:
        ctx.tables["fact_cost"] = pd.concat([fc, pd.DataFrame(new_rows)], ignore_index=True)

    ai = fc[fc["source_file"] == "ai_usage.csv"]
    for rid, g in ai.groupby("resource_id"):
        n = len(ctx.tables["dim_date"]) - g["charge_period_start"].nunique()
        if n > 0:
            ctx.log("ai_usage.csv", "days_without_rows", n, "not filled: usage-driven source, a missing "
                    "day may mean no usage", resource_id=rid)


# ----------------------------------------------------------------- one-offs
def tag_one_offs(ctx: Context) -> None:
    fc = ctx.tables["fact_cost"]
    fc["is_one_off"] = False
    fc["one_off_id"] = None
    events = []
    for oo in ctx.ref["one_offs"]:
        if oo.get("charge_category"):
            m = fc["charge_category"] == oo["charge_category"]
            actual = fc.loc[m & fc["in_baseline"], "cost_chf"].sum()
            normal, excess = 0.0, actual
        else:
            s, e = str(oo["start"]), str(oo["end"])
            m = (fc["resource_id"] == oo["resource_id"]) & fc["charge_period_start"].between(s, e)
            daily = fc[(fc["resource_id"] == oo["resource_id"]) & (fc["charge_category"] != "Credit")] \
                .groupby("charge_period_start")["cost_chf"].sum()
            dts = pd.to_datetime(daily.index)
            around = daily[(abs((dts - pd.Timestamp(s)).days) <= 30) & ~daily.index.to_series().between(s, e).values]
            n_days = (pd.Timestamp(e) - pd.Timestamp(s)).days + 1
            actual = fc.loc[m, "cost_chf"].sum()
            normal = around.median() * n_days
            excess = actual - normal
        fc.loc[m, "is_one_off"] = True
        fc.loc[m, "one_off_id"] = oo["id"]
        events.append({"one_off_id": oo["id"], "resource_id": oo.get("resource_id"),
                       "start": str(oo.get("start", "")), "end": str(oo.get("end", "")),
                       "ticket": oo.get("ticket"), "reason": oo["reason"], "rows": int(m.sum()),
                       "actual_chf": round(actual, 2), "normal_chf": round(normal, 2),
                       "excess_chf": round(excess, 2)})
        ctx.log(oo.get("ticket") or "azure_costs.csv", "one_off", m.sum(),
                "kept in the actual baseline, tagged is_one_off; excluded from the recurring baseline",
                f"{oo['reason']} · actual CHF {actual:,.0f}, normal CHF {normal:,.0f}, excess CHF {excess:,.0f}",
                amount_chf=excess, resource_id=oo.get("resource_id"))
    ctx.tables["one_off_events"] = pd.DataFrame(events)


# ---------------------------------------------------------------- anomalies
def detect_anomalies(ctx: Context) -> None:
    """Propose spikes as candidates; a human-curated list (reference.yaml)
    decides whether they are one-offs, expected peaks or unexplained."""
    a = ctx.config["anomaly"]
    fc = ctx.tables["fact_cost"]
    d = fc[(fc["grain"] == "day") & (fc["charge_category"] == "Usage")] \
        .groupby(["resource_id", "charge_period_start"])["cost_chf"].sum().reset_index()
    known = [(o.get("resource_id"), str(o.get("start")), str(o.get("end")), f"one-off {o.get('ticket')}")
             for o in ctx.ref["one_offs"] if o.get("resource_id")]
    known += [(o["resource_id"], str(o["start"]), str(o["end"]), f"expected peak {o['ticket']}")
              for o in ctx.ref["expected_peaks"]]
    tickets = ctx.tables["stg_it_tickets"]
    win = a["rolling_window_days"]
    tw = pd.Timedelta(days=a["related_ticket_window_days"])
    rows = []
    for rid, g in d.groupby("resource_id"):
        g = g.sort_values("charge_period_start").reset_index(drop=True)
        med = g["cost_chf"].rolling(win, min_periods=7).median().shift(1)
        flag = (g["cost_chf"] > a["daily_cost_ratio_vs_rolling_median"] * med) & (g["cost_chf"] >= a["min_daily_cost_chf"])
        if not flag.any():
            continue
        g["flag"], g["med"] = flag, med
        g["episode"] = (g["flag"] != g["flag"].shift()).cumsum()
        for _, e in g[g["flag"]].groupby("episode"):
            s, en = e["charge_period_start"].min(), e["charge_period_start"].max()
            excess = (e["cost_chf"] - e["med"]).sum()
            if excess < a["min_episode_excess_chf"]:
                continue
            pre = e["med"].iloc[0]
            post_vals = g.loc[e.index[-1] + 1: e.index[-1] + win, "cost_chf"]
            level_shift = len(post_vals) >= 7 and post_vals.median() > a["level_shift_ratio"] * pre
            # Context only: tickets on the same resource near the start (matched by
            # resource and date, never by reading their text). A human confirms.
            near = tickets[(tickets["resource_id"] == rid)
                           & (abs(pd.to_datetime(tickets["date"]) - pd.Timestamp(s)) <= tw)]
            related = ", ".join(near["ticket_id"]) or None
            expl = next((k[3] for k in known if k[0] == rid and not (en < k[1] or s > k[2])), None)
            kind = "one_off_or_peak" if expl else ("level_shift" if level_shift else "spike")
            rows.append({"resource_id": rid, "start": s, "end": en, "days": len(e), "kind": kind,
                         "excess_chf": round(excess, 2), "explained_by": expl, "related_tickets": related})
            if expl:
                action, sev = f"explained: {expl}", "info"
            elif level_shift:
                action, sev = ("level shift: cost stays higher afterwards (new normal, kept in baseline)"
                               + (f"; related tickets to confirm: {related}" if related else "")), "info"
            else:
                action, sev = ("unexplained spike → human to review"
                               + (f"; related tickets: {related}" if related else "")), "warn"
            ctx.log("anomaly detector", "anomaly_candidate", len(e), action,
                    f"{rid} {s}…{en}: CHF {excess:,.0f} above the rolling median",
                    amount_chf=excess, resource_id=rid, severity=sev)
            ctx.issues[-1]["explained"] = bool(expl) or level_shift
    ctx.tables["anomaly_candidates"] = pd.DataFrame(rows)


# ------------------------------------------------------------- materiality
def apply_materiality(ctx: Context) -> None:
    """Issues whose CHF at risk exceeds the configured share of their
    category's baseline cost become hand-overs to a human.

    CHF at risk = the uncertainty for estimates (how far the true value can
    be from our estimate), the full amount for contradictions and unexplained
    anomalies. Explained events (one-offs with a ticket, level shifts) and
    curated one-offs are not escalated."""
    thr = float(ctx.config["handover"]["materiality_pct_of_category"])
    fc = ctx.tables["fact_cost"]
    totals = fc[fc["in_baseline"]].groupby("category")["cost_chf"].sum()
    for it in ctx.issues:
        if it["amount_chf"] is None:
            continue
        cat = it["category"] or (ctx.category_of_resource(pd.Series([it["resource_id"]])).iat[0]
                                 if it["resource_id"] else None)
        it["category"] = cat
        if cat not in totals or totals[cat] == 0:
            continue
        at_risk = it.get("uncertainty_chf")
        at_risk = abs(it["amount_chf"]) if at_risk is None else at_risk
        it["at_risk_chf"] = round(at_risk, 2)
        pct = at_risk / totals[cat] * 100
        it["pct_of_category"] = round(pct, 3)
        if it["issue_type"] == "one_off" or it.get("explained"):
            continue
        if pct > thr and it["severity"] != "handover":
            it["severity"] = "handover"
            it["action"] += f" · above materiality ({pct:.1f}% > {thr}% of {cat}) → human decides"
