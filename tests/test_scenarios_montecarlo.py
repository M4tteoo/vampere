"""B1 Monte Carlo and B2 Swiss mix switch: the linear energy model, the package model, the sampler.

    .venv/bin/python -m unittest tests.test_scenarios_montecarlo

The integration tests use the last pipeline run, or GREENOPS_TEST_OUTPUT when set.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from pipeline.energy.engine import load_factors
from pipeline.energy.linear import LinearEnergy, at_level, factor_ranges
from pipeline.harmonize.context import ROOT, Context


def line(unit, quantity, provider="Azure", location="DE", cpu=None, gpu=None, kwh_mid=0.0, charge="Usage"):
    return {"unit": unit, "quantity": quantity, "provider": provider, "location": location,
            "utilisation_cpu": cpu, "utilisation_gpu": gpu, "kwh_mid": kwh_mid, "charge_category": charge}


class LinearModelTest(unittest.TestCase):
    def test_node_hour_matches_the_engine_formula(self):
        F = load_factors()
        fc = pd.DataFrame([line("node-hour", 10, cpu=0.25)])
        mid = at_level(factor_ranges("ch_consumption", F), "mid")
        kwh, co2 = LinearEnergy.evaluate(LinearEnergy(fc, F).aggregate([True]), mid)
        c, node = F["compute"], F["shapes"]["node"]
        w = node["vcpu"] * (c["cpu_w_min"]["mid"] + 0.25 * (c["cpu_w_max"]["mid"] - c["cpu_w_min"]["mid"])) \
            + node["ram_gb"] * c["mem_w_per_gb"]["mid"]
        expected = 10 * w / 1000 * F["pue"]["hyperscaler"]["mid"]
        self.assertAlmostEqual(kwh.sum(), expected, places=9)
        self.assertAlmostEqual(co2.sum(), expected * F["grid"]["DE"]["mid"], places=9)

    def test_fully_loaded_units_scale_with_their_factor_only(self):
        fc = pd.DataFrame([line("tokens", 1e6, provider="OpenAI", location="EU", kwh_mid=2.0)])
        r = factor_ranges("ch_consumption")
        lin = LinearEnergy(fc).aggregate([True])
        kwh_mid, _ = LinearEnergy.evaluate(lin, at_level(r, "mid"))
        kwh_high, _ = LinearEnergy.evaluate(lin, at_level(r, "high"))
        self.assertAlmostEqual(kwh_mid.sum(), 2.0)
        self.assertAlmostEqual(kwh_high.sum(), 2.0 * r["ai_token_wh"]["high"] / r["ai_token_wh"]["mid"])

    def test_credits_have_no_energy_and_unknown_location_uses_eu(self):
        fc = pd.DataFrame([line("vCPU-hour", 100, cpu=0.5, charge="Credit"),
                           line("GB-day", 1000, provider="AWS", location=None)])
        kwh, co2 = LinearEnergy.evaluate(LinearEnergy(fc).aggregate([True, True]), at_level(factor_ranges("ch_consumption"), "mid"))
        self.assertEqual(kwh[0], 0)                       # CH column: nothing
        self.assertGreater(kwh[3], 0)                     # EU column: the storage line
        self.assertAlmostEqual(co2[3] / kwh[3], factor_ranges("ch_consumption")["grid_EU"]["mid"])

    def test_draws_and_scalars_can_be_mixed(self):
        fc = pd.DataFrame([line("GPU-hour", 24, gpu=0.1, cpu=0.05)])
        r = factor_ranges("ch_consumption")
        theta = {**at_level(r, "mid"), "gpu_idle_w": np.array([30.0, 60.0, 90.0])}
        kwh, _ = LinearEnergy.evaluate(LinearEnergy(fc).aggregate([True]), theta)
        self.assertEqual(kwh.shape, (3, 4))
        self.assertTrue(np.all(np.diff(kwh.sum(-1)) > 0))  # more idle power → more energy


class SamplerTest(unittest.TestCase):
    def test_triangular_quantile_hits_low_mode_high(self):
        from pipeline.bonus.montecarlo import _quantile_triangular
        r = {"low": 1.0, "mid": 2.0, "high": 5.0}
        q = _quantile_triangular(np.array([0.0, 0.25, 1.0]), r)  # F(mode) = (2 − 1) / (5 − 1) = 0.25
        np.testing.assert_allclose(q, [1.0, 2.0, 5.0])

    def test_degenerate_range_is_constant(self):
        from pipeline.bonus.montecarlo import _triangular
        x = _triangular(np.random.default_rng(1), {"low": 3.0, "mid": 3.0, "high": 3.0}, 5)
        np.testing.assert_array_equal(x, np.full(5, 3.0))


class AdvisorOutputTest(unittest.TestCase):
    def test_facts_follow_custom_output(self):
        from pipeline import advisor
        with tempfile.TemporaryDirectory() as directory:
            ctx = Context.load()
            ctx.config["output_dir"] = str(Path(directory) / "run")
            with patch.object(advisor, "ADVISOR_DIR", Path(directory) / "default"), \
                    patch.object(advisor._facts, "build", return_value={"servers": []}), \
                    patch.object(advisor, "_load", return_value=None):
                advisor.apply(ctx)
            self.assertTrue((ctx.output_dir / "advisor" / "facts.json").is_file())


TEST_OUTPUT = Path(os.environ.get("GREENOPS_TEST_OUTPUT", str(ROOT / "output")))


@unittest.skipUnless((TEST_OUTPUT / "greenops.duckdb").exists() and (TEST_OUTPUT / "measures.json").exists(),
                     "needs a pipeline run (python -m pipeline.run)")
class RealDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.bonus.dev import load_context
        from pipeline.bonus.package_eval import PackageModel
        from pipeline.bonus.common import read_output
        cls.ctx = load_context(str(TEST_OUTPUT))
        cls.ctx.config["scenario"] = read_output(cls.ctx, "measures.json")["meta"]["scenario"]
        cls.pm = PackageModel(cls.ctx)

    def test_linear_model_equals_the_engine(self):
        from pipeline.energy.linear import check
        fc = self.ctx.tables["fact_cost"]
        check(fc[fc["in_baseline"]].reset_index(drop=True), self.ctx.config["scenario"])

    def test_package_model_equals_measures_json(self):
        self.pm.check()

    def test_every_goal_package_equals_measures_json(self):
        """The optimiser's packages (climate first / best value / francs first) are reproduced too."""
        from pipeline.bonus.package_eval import PackageModel
        pm = PackageModel(self.ctx)
        self.assertEqual(pm.goals()[0], pm.default_goal)              # the recommended goal first
        for g in pm.goals():
            pm.use(g).check()
            self.assertEqual({m["id"] for m in pm.measures}, set(pm.packages[g]["measure_ids"]))
        pm.use(None)
        self.assertEqual(pm.package["measure_ids"], self.pm.package["measure_ids"])

    def test_entity_production_totals_match_production_scenario(self):
        from pipeline.bonus.common import read_output
        from pipeline.bonus.scenarios import _entities_production
        if self.ctx.config["scenario"] == "ch_production":
            entities = read_output(self.ctx, "entities.json")["entities"]
            original = {e["id"]: e["metrics"]["co2_kg"] for e in entities if e["metrics"]["co2_kg"]}
            self.assertEqual(_entities_production(self.ctx), original)
        else:
            expected = self.pm.levels("ch_production")["mid"]["baseline"]["co2_by_location"]["CH"]
            self.assertAlmostEqual(_entities_production(self.ctx)["loc:CH"]["mid"], float(expected), delta=0.1)

    def test_production_mix_changes_only_swiss_co2(self):
        cons, prod = self.pm.levels("ch_consumption")["mid"], self.pm.levels("ch_production")["mid"]
        for loc in ("DE", "IE", "EU"):
            self.assertAlmostEqual(float(cons["baseline"]["co2_by_location"][loc]),
                                   float(prod["baseline"]["co2_by_location"][loc]), places=6)
        self.assertLess(float(prod["baseline"]["co2_by_location"]["CH"]), float(cons["baseline"]["co2_by_location"]["CH"]))
        self.assertAlmostEqual(float(cons["baseline"]["kwh"]), float(prod["baseline"]["kwh"]), places=6)

    def test_monte_carlo_is_reproducible(self):
        from pipeline.bonus.montecarlo import _simulate
        a, _ = _simulate(self.pm, "ch_consumption", np.random.default_rng(7))
        b, _ = _simulate(self.pm, "ch_consumption", np.random.default_rng(7))
        np.testing.assert_array_equal(a["reduction"]["co2"], b["reduction"]["co2"])


if __name__ == "__main__":
    unittest.main()
