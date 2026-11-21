import csv
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.bonus import call
from pipeline.bonus.common import BASELINE_TEMPLATE, MEASURES_TEMPLATE
from pipeline.bonus.optimized_history import replay
from pipeline.export.frontend import SUMS, metrics
from pipeline.harmonize.context import Context


class MarketTest(unittest.TestCase):
    def setUp(self):
        self.ctx = Context.load()
        self.ctx.config["scenario"] = "ch_production"
        self.ctx.config["bonus"]["enabled"] = [
            name for name in self.ctx.config["bonus"]["enabled"] if name == "market"
        ]
        self.facts = pd.DataFrame([
            dict.fromkeys(SUMS, 0.0) | {
                "provider": "Azure", "location": location, "resource_id": "dp-dev",
                "in_baseline": baseline, "is_one_off": one_off, "source_file": "fixture.csv",
                "kwh_low": energy, "kwh_mid": energy, "kwh_high": energy,
                "co2_kg_low": energy * 0.02, "co2_kg_mid": energy * 0.03, "co2_kg_high": energy * 0.04,
            }
            for location, energy, baseline, one_off in [
                ("DE", 100, True, False), ("CH", 100, True, True), ("IE", 50, False, False)
            ]
        ])
        self.ctx.tables["fact_cost"] = self.facts.copy()

    def test_baseline_preserves_kwh_and_swiss_proxy_is_independent_of_b2(self):
        self.assertIn("market", call(self.ctx, "after_energy", fail_fast=True))
        enriched = self.ctx.tables["fact_cost"]
        pd.testing.assert_frame_equal(enriched[self.facts.columns], self.facts)
        baseline = enriched[enriched["in_baseline"]].sum(numeric_only=True)
        self.assertEqual(metrics(baseline)["co2_kg_market"], {"low": 75.8, "mid": 81.1, "high": 82.9})

    def test_unknown_location_is_not_assumed_to_be_eu(self):
        self.assertIn("market", self.ctx.config["bonus"]["enabled"])
        self.ctx.tables["fact_cost"].loc[0, "location"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "UNKNOWN"):
            call(self.ctx, "after_energy", fail_fast=True)

    def test_exports_relocation_savings_without_one_offs_or_out_of_period_rows(self):
        effect = {"scope": "res:dp-dev", "energy_share": 0.2, "cost_share": 0.2, "relocate_to": "CH"}
        measures = [{"id": "M-01", "status": "human", "in_package": True, "effects": [effect]},
                    {"id": "M-02", "status": "ok", "in_package": True, "effects": [effect | {"scope": "srv:dp-dev"}]}]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.ctx.config["output_dir"] = directory
            (out / "submission").mkdir()
            for name in (BASELINE_TEMPLATE, MEASURES_TEMPLATE):
                source = self.ctx.data_dir / name
                header = source.read_text(encoding="utf-8-sig").splitlines()[0]
                with (out / "submission" / name).open("w", encoding="utf-8-sig", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=next(csv.reader([header])))
                    writer.writeheader()
                    if name == MEASURES_TEMPLATE:
                        writer.writerows({"measure_id": m["id"]} for m in measures)
            (out / "measures.json").write_text(json.dumps({"measures": measures}), encoding="utf-8")
            self.assertIn("market", call(self.ctx, "run", fail_fast=True))
            report = json.loads((out / "market.json").read_text(encoding="utf-8"))
            self.assertEqual(report["baseline"]["kwh"]["mid"], 200)
            self.assertEqual(report["baseline"]["co2_kg_market"]["mid"], 81.15)
            self.assertEqual(report["by_provider"][0]["market_basis_kwh"]["location_proxy"]["mid"], 100)
            self.assertEqual(report["measure_savings"]["M-01"]["co2_kg_market"]["mid"], 61.35)
            self.assertIsNone(report["measure_savings"]["M-02"]["co2_kg_market"])
            with (out / "submission" / MEASURES_TEMPLATE).open(encoding="utf-8-sig", newline="") as fh:
                supported, unsupported = csv.DictReader(fh)
            self.assertAlmostEqual(float(supported["savings_co2_kg_market_based"]), 61.35)
            self.assertEqual(unsupported["savings_co2_kg_market_based"], "")

    def test_step_nine_does_not_copy_stale_market_emissions(self):
        enriched = self.facts.assign(co2_kg_market_low=1, co2_kg_market_mid=2, co2_kg_market_high=3)
        measures = {"package": {"measure_ids": ["M-01"]}, "measures": [
            {"id": "M-01", "status": "ok", "effects": [
                {"scope": "res:dp-dev", "energy_share": 0.2, "cost_share": 0.2}
            ]}
        ]}
        result, _ = replay(enriched, measures, "ch_consumption")
        self.assertFalse(any(c.startswith("co2_kg_market_") for c in result))
