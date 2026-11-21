import unittest
from types import SimpleNamespace

import pandas as pd


def row(month, resource, category, cost, kwh=100, location="CH", one_off=False):
    return {
        "month": month, "resource_id": resource, "category": category, "location": location,
        "is_one_off": one_off, "currency_native": "CHF", "fx_rate_chf": 1,
        "cost_chf_low": cost, "cost_chf": cost, "cost_chf_high": cost,
        "kwh_low": kwh, "kwh_mid": kwh, "kwh_high": kwh,
        "co2_kg_low": kwh / 2, "co2_kg_mid": kwh / 2, "co2_kg_high": kwh / 2,
        "provider": "Azure", "unit": "node-hour", "source_file": "baseline.csv",
        "value_status": "observed",
    }


def context(rows):
    months = pd.date_range("2024-11-01", "2026-08-01", freq="MS")
    return SimpleNamespace(
        config={"baseline": {"start": "2025-09-01", "end": "2026-08-31"}},
        tables={
            "fact_cost": pd.DataFrame(rows),
            "fx_monthly": pd.DataFrame({"month": months, "eur_chf": 0.9, "usd_chf": 0.8}),
            "alloc_headcount": pd.DataFrame({"month": months, "fte": 100}),
            "stg_ai_usage": pd.DataFrame({"month": months, "tokens_total": 100}),
        },
        issues=[{"resource_id": "dp-dev", "issue_id": "Q-1"}],
    )


class ForecastTest(unittest.TestCase):
    @staticmethod
    def forecast(rows, optimized=None):
        from pipeline.bonus.forecast import build_forecast

        ctx = context(rows)
        if optimized is not None:
            ctx.tables["fact_cost_optimized"] = pd.DataFrame(optimized)
        return build_forecast(ctx)

    def test_baseline_horizon_price_and_capacity_changes(self):
        rows = []
        for month in ("2026-06-01", "2026-07-01", "2026-08-01"):
            rows.extend([
                row(month, "dp-prod", "cloud", 100),
                row(month, "sub-copilot", "ai", 80 if month >= "2026-07" else 140),
                row(month, "saas-m365", "saas", 140 if month >= "2026-07" else 125),
            ])
        rows.extend([row("2026-08-01", "dp-prod", "cloud", 5000, one_off=True),
                     row("2026-09-01", "dp-prod", "cloud", 9999)])
        forecast = self.forecast(rows)
        months = forecast["months"]
        self.assertEqual((len(months), months[0]["month"], months[-1]["month"]),
                         (12, "2026-09-01", "2027-08-01"))
        self.assertEqual(forecast["horizon"], {
            "start": "2026-09-01", "end_exclusive": "2027-08-31",
        })
        self.assertEqual(months[0]["without"]["cost_chf"]["mid"], 320)
        self.assertEqual(months[0]["without"]["cost_usd"]["mid"], 400)
        self.assertEqual(months[1]["by_category"]["cloud"]["without"]["kwh"]["mid"], 120)
        january = next(point for point in months if point["month"] == "2027-01-01")
        self.assertEqual(january["by_category"]["ai"]["without"]["cost_chf"]["mid"], 93.33)
        self.assertEqual(january["by_category"]["ai"]["without"]["kwh"]["mid"], 100)

    def test_without_optimized_history_with_is_unavailable(self):
        rows = [row(f"2026-0{month}-01", "dp-dev", "cloud", 100) for month in (6, 7, 8)]
        forecast = self.forecast(rows)
        self.assertIsNone(forecast["calculations"]["with"])
        for month in forecast["months"]:
            self.assertIsNone(month["with"])
            self.assertIsNone(month["by_category"]["cloud"]["with"])

    def test_both_histories_get_the_same_projection_rules_and_partial_month(self):
        months = ("2026-06-01", "2026-07-01", "2026-08-01")
        original = [row(month, "dp-prod", "cloud", 310, kwh=100) for month in months]
        optimized = [row(month, "dp-prod", "cloud", 155, kwh=50) for month in months]
        optimized.append(row("2026-08-01", "new-server", "server", 30, kwh=30))
        forecast = self.forecast(original, optimized)
        sep, oct_ = forecast["months"][:2]
        self.assertEqual(sep["with"]["cost_chf"]["mid"], 165)
        self.assertEqual(sep["by_category"]["server"]["without"]["kwh"]["mid"], 0)
        self.assertEqual(oct_["by_category"]["cloud"]["without"]["kwh"]["mid"], 120)
        self.assertEqual(oct_["by_category"]["cloud"]["with"]["kwh"]["mid"], 60)
        last_cloud = forecast["months"][-1]["by_category"]["cloud"]
        self.assertEqual(last_cloud["without"]["cost_chf"]["mid"], 360)
        self.assertEqual(last_cloud["with"]["cost_chf"]["mid"], 180)

    def test_rejects_optimized_history_missing_a_baseline_month(self):
        rows = [row(f"2026-0{month}-01", "dp-dev", "cloud", 100) for month in (6, 7, 8)]
        with self.assertRaisesRegex(ValueError, "fact_cost_optimized.*2026-07"):
            self.forecast(rows, [rows[0], rows[2]])

    def test_selected_resource_effect_flows_into_the_forecast(self):
        from pipeline.bonus.forecast import build_forecast
        from pipeline.bonus.optimized_history import replay
        from pipeline.energy.engine import load_factors

        original = [row(f"2026-0{month}-01", "dp-dev", "cloud", 100, location="DE") for month in (6, 7, 8)]
        original.append(row("2026-08-01", "dp-dev", "cloud", 500, location="DE", one_off=True))
        ctx = context(original)
        ctx.config["scenario"] = "ch_production"
        baseline = ctx.tables["fact_cost"]
        effect = {"scope": "res:dp-dev", "cost_share": 0.25, "energy_share": 0.5, "relocate_to": "CH"}
        package = {"package": {"measure_ids": ["selected", "unsupported", "blocked", "overlap"]}, "measures": [
            {"id": "selected", "status": "human", "effects": [effect]},
            {"id": "unsupported", "status": "ok", "effects": [effect, {**effect, "scope": "lic:Tool@IT"}]},
            {"id": "blocked", "status": "blocked", "effects": [effect]},
            {"id": "overlap", "status": "ok", "effects": [effect]},
            {"id": "not-selected", "status": "ok", "effects": [effect]},
        ]}
        optimized, report = replay(baseline, package, ctx.config["scenario"])
        self.assertIsNotNone(optimized)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["applied_measure_ids"], ["selected"])
        self.assertEqual(report["requires_confirmation"], ["selected"])
        self.assertEqual([item["id"] for item in report["skipped"]], ["unsupported", "blocked", "overlap"])
        pd.testing.assert_frame_equal(baseline, pd.DataFrame(original))
        pd.testing.assert_series_equal(optimized.iloc[-1], baseline.iloc[-1], check_dtype=False)
        ctx.tables["fact_cost_optimized"] = optimized
        september = build_forecast(ctx)["months"][0]
        self.assertEqual(september["without"]["cost_chf"]["mid"], 100)
        self.assertEqual(september["with"]["cost_chf"]["mid"], 75)
        self.assertEqual(september["with"]["kwh"]["mid"], 50)
        factor = load_factors()["grid"]["CH"]["variants"]["ch_production"]["mid"]
        self.assertAlmostEqual(september["with"]["co2_kg"]["mid"], 50 * factor, places=2)

    def test_history_replays_server_shares_licences_and_distinct_ai_tasks(self):
        from pipeline.bonus.optimized_history import replay

        base = row("2026-08-01", "shared", "cloud", 100)
        facts = pd.DataFrame([
            base,
            {**base, "is_one_off": True},
            {**base, "resource_id": "suite", "source_file": "saas_contracts.csv", "tool": "Suite"},
            {**base, "resource_id": "gateway", "source_file": "ai_usage.csv", "source_row": 7},
            {**base, "resource_id": "gateway", "source_file": "ai_usage.csv", "source_row": 8},
            {**base, "resource_id": "gateway", "source_file": "ai_usage.csv", "source_row": 9},
        ])
        advisor = {
            "servers": [{"id": f"srv:{s}", "resource": "shared"} for s in ("a", "b")],
            "facts": {f"srv:{s}.share_of_resource": {"value": share} for s, share in (("a", .2), ("b", .3))},
        }
        ai = pd.DataFrame({"source_row": [7, 8, 9], "task_type": ["Draft", "Translate", "Draft"],
                           "model_class": ["large", "large", "small"]})
        ids = ["server", "licence", "draft", "translate", "overlap"]
        effect = lambda scope, cost, energy: {"scope": scope, "cost_share": cost, "energy_share": energy}
        payload = {"package": {"measure_ids": ids}, "measures": [
            {"id": mid, "status": "ok", "effects": effects}
            for mid, effects in zip(ids, [
                [effect("srv:a", 1, 1), effect("srv:b", .5, .5)],
                [effect("lic:Suite", .4, 0)],
                [effect("ai:gateway:Draft:large", .5, .5)],
                [effect("ai:gateway:Translate:large", .25, .25)],
                [effect("res:shared", .1, .1)],
            ])
        ]}
        optimized, report = replay(facts, payload, "ch_consumption", advisor_facts=advisor, ai_usage=ai)
        self.assertEqual(report["applied_measure_ids"], ids[:-1])
        self.assertEqual(report["skipped"][0]["id"], "overlap")
        self.assertIn("Overlapping", report["skipped"][0]["reason"])
        self.assertEqual(optimized["cost_chf"].tolist(), [65, 100, 60, 50, 75, 100])
        self.assertEqual(optimized["kwh_mid"].tolist(), [65, 100, 100, 50, 75, 100])

    def test_no_replayable_measures_does_not_invent_an_optimized_history(self):
        from pipeline.bonus.optimized_history import replay

        rows = [row("2026-08-01", "dp-dev", "cloud", 100)]
        estimates_only = {"package": {"measure_ids": ["M-01"]}, "measures": [
            {"id": "M-01", "status": "ok", "savings": {"cost_chf": {"mid": 50}}},
        ]}
        history, report = replay(pd.DataFrame(rows), estimates_only, "ch_consumption")
        self.assertIsNone(history)
        self.assertEqual(report["status"], "no_supported_measures")
        self.assertEqual(report["skipped"][0]["id"], "M-01")


if __name__ == "__main__":
    unittest.main()
