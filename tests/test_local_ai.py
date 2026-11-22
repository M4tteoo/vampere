import hashlib
import unittest

from pipeline.bonus.local_ai import breakeven_month, energy_kwh, vram_check
from pipeline.harmonize.context import ROOT, Context


class HelpersTest(unittest.TestCase):
    def test_vram_check_rejects_with_reason_and_accepts_small_model(self):
        reason = vram_check(40, 24, 1.2)
        self.assertIsNotNone(reason)
        self.assertIn("48", reason)
        self.assertIsNone(vram_check(16, 48, 1.2))

    def test_breakeven_month(self):
        # Setup 1200 + 100/month against an API at 1200/year (100/month): never cheaper.
        self.assertIsNone(breakeven_month(1200, 100, 1200, 0.0))
        # Setup 1200 + 0/month against 100/month: cumulative API reaches 1200 in month 12.
        self.assertEqual(breakeven_month(1200, 0, 1200, 0.0), 12)
        # Growth makes the API dearer, so break-even comes earlier.
        self.assertLess(breakeven_month(1200, 0, 1200, 0.5), 12)

    def test_energy_idle_only_when_no_gpu_work(self):
        self.assertAlmostEqual(energy_kwh(1000, 0, 60, 300, 0, 1.0), 60.0)
        self.assertAlmostEqual(energy_kwh(1000, 100, 60, 300, 10, 1.5), (60 + 10) * 1.5 + 100 * 240 / 1000 * 1.5)


def _db_ready() -> bool:
    return (ROOT / Context.load().config["duckdb_file"]).exists()


@unittest.skipUnless(_db_ready(), "run `python -m pipeline.run` first")
class ModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.bonus.dev import load_context
        from pipeline.bonus.local_ai import build
        cls.ctx = load_context()
        cls.out = build(cls.ctx)

    def test_workloads_and_tiers(self):
        wl = {w["id"]: w for w in self.out["workloads"]}
        self.assertEqual(len(wl), 7)
        self.assertEqual(wl["wl:marketing-classify"]["tier"], "basic")
        self.assertEqual(wl["wl:support-agent"]["tier"], "advanced")

    def test_large_model_does_not_fit_gpu_ml_01(self):
        fits = [f for f in self.out["fits"] if f["model_id"] == "gpt-oss-120b" and f["hardware_id"] == "hw:gpu-ml-01"]
        self.assertTrue(fits)
        self.assertTrue(all(not f["feasible"] and any("GB" in r for r in f["reasons"]) for f in fits))

    def test_gpu_ml_01_scenarios_give_back_part_of_m04(self):
        hw = next(h for h in self.out["hardware"] if h["id"] == "hw:gpu-ml-01")
        scen = [s for s in self.out["scenarios"] if s["hardware_id"] == "hw:gpu-ml-01" and s["feasible"]]
        self.assertTrue(scen)
        for s in scen:
            # the on-demand measure (found by role, its id can change between analyses) carries the rent given back
            m04 = next(i for i in s["interacts_with"] if i["cost_chf_per_year"] is not None)
            self.assertAlmostEqual(m04["cost_chf_per_year"]["mid"],
                                   hw["on_hours_per_year"] * hw["price_chf_per_hour"]["mid"], delta=1.0)

    def test_coding_stays_on_the_api(self):
        w = next(x for x in self.out["workloads"] if x["resource_id"] == "ai-agent2")
        self.assertIsNotNone(w["excluded"])
        self.assertIn("code-agent", w["excluded"]["what"])
        self.assertTrue(0 < w["excluded"]["share"] < 1)

    def test_panel_cost_chart_matches_the_option_saving(self):
        p = self.out["panel"]
        self.assertTrue(p["model"]["servers"] and p["options"] and p["tools"]["items"])
        cost = next(c for c in p["charts"] if c["id"] == "cost")
        api = next(x for x in cost["series"] if x["id"] == "api_only")["values"][-1]
        for o in p["options"]:
            local = next(x for x in cost["series"] if x["id"] == o["id"])["values"][-1]
            saving = next(f for f in o["figures"] if f["key"] == "saving")["mid"]
            self.assertAlmostEqual(api - local, saving, delta=5.0)

    def test_ranges_are_ordered(self):
        def walk(v):
            if isinstance(v, dict):
                if set(v) == {"low", "mid", "high"} and all(isinstance(x, (int, float)) for x in v.values()):
                    self.assertLessEqual(v["low"], v["mid"] + 1e-6, v)
                    self.assertLessEqual(v["mid"], v["high"] + 1e-6, v)
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(self.out["scenarios"])
        walk(self.out["workloads"])

    def test_run_leaves_other_outputs_untouched(self):
        from pipeline.bonus import call
        names = ["measures.json", "summary.json", "forecast.json"]

        def digest():
            return {n: hashlib.sha256((self.ctx.output_dir / n).read_bytes()).hexdigest()
                    for n in names if (self.ctx.output_dir / n).exists()}
        before = digest()
        self.assertTrue(call(self.ctx, "run", ["local_ai"], fail_fast=True)["local_ai"].startswith("ok"))
        self.assertEqual(digest(), before)
        self.assertTrue((self.ctx.output_dir / "local_ai.json").exists())


if __name__ == "__main__":
    unittest.main()
