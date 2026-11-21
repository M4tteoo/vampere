"""Extra-source insights (pipeline/insights) and the advisor's region rule.

    .venv/bin/python -m unittest tests.test_insights
Uses the last pipeline run (skipped without it).
"""
import unittest

from pipeline.harmonize.context import ROOT


@unittest.skipUnless((ROOT / "output" / "greenops.duckdb").exists(), "needs a pipeline run (python -m pipeline.run)")
class InsightsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pipeline.bonus.dev import load_context
        from pipeline.insights import compute_all
        cls.ctx = load_context()
        cls.ins = compute_all(cls.ctx)

    def test_every_extra_source_is_used(self):
        from pipeline.insights import SOURCES
        files = {f"extra/{p.name}" for p in (ROOT / "data" / "case" / "extra").iterdir() if p.suffix in (".csv", ".jsonl")}
        self.assertEqual(files, set(SOURCES), "every extra file must be mapped to at least one feature")
        self.assertTrue(all(SOURCES[f] for f in files))

    def test_cards_are_complete(self):
        for name, i in self.ins.items():
            c = i.card
            self.assertEqual(c["id"], name)
            for key in ("title", "source_files", "headline", "numbers", "protected", "entity_ids", "calc"):
                self.assertIn(key, c, f"{name}: {key}")
            if c["potential"]:
                self.assertIn(c["potential"]["status"], ("ok", "human", "blocked"))
                m = c["potential"]["metrics"]["co2_kg"]
                self.assertLessEqual(m["low"], m["mid"] + 1e-9)
                self.assertLessEqual(m["mid"], m["high"] + 1e-9)

    def test_powerbi_classes_and_protection(self):
        reports = self.ins["powerbi"].extra["reports"]
        self.assertEqual(len(reports), 60)
        cls = {r["report_id"]: r["class"] for r in reports}
        self.assertEqual(cls["pbi-07"], "protected")                       # internal audit (T-1167), regulatory
        self.assertTrue(all(r["class"] == "duplicate" for r in reports if "(copy)" in r["report"]))
        removable = next(f[1] for f in self.ins["powerbi"].facts if f[0] == "pbi-kap.refresh_load_removable_share")
        self.assertTrue(0 < removable < 1)

    def test_region_rule_in_the_calculator(self):
        from pipeline.advisor import facts as advisor_facts
        from pipeline.advisor.calculator import Calculator
        calc = Calculator(self.ctx, advisor_facts.build(self.ctx), [])
        _, problems, _ = calc.savings([{"scope": "res:logs", "cost_share": 0.1, "energy_share": 0.1, "relocate_to": "DE"}])
        self.assertTrue(problems and "offers no region in DE" in problems[0])   # Swiss hoster: Zurich only
        s, problems, _ = calc.savings([{"scope": "res:dp-dev", "cost_share": 0, "energy_share": 0, "relocate_to": "CH"}])
        self.assertEqual(problems, [])
        option = next(o for o in self.ins["regions"].extra["options"] if o["resource_id"] == "dp-dev" and o["to"] == "CH")
        self.assertAlmostEqual(s["co2_kg_mid"], option["co2_kg_saved"]["mid"], delta=0.1)   # two computations agree

    def test_project_allocation_never_exceeds_untagged_costs(self):
        from pipeline.insights.common import baseline
        b = baseline(self.ctx)
        projects = self.ins["project_footprint"].extra["projects"]
        allocated = sum(p["allocated_by_hours"]["cost_chf"]["mid"] for p in projects)
        direct = sum(p["direct"]["cost_chf"]["mid"] for p in projects)
        self.assertLessEqual(allocated, b.loc[b["project_id"].isna(), "cost_chf"].sum() + 1)
        self.assertAlmostEqual(direct, b.loc[b["project_id"].notna(), "cost_chf"].sum(), delta=1)

    def test_m365_is_a_check_only(self):
        check = self.ins["m365"].card["energy_check"]
        self.assertFalse(check["baseline_changed"])
        self.assertLess(check["bottom_up_kwh"]["low"], check["bottom_up_kwh"]["high"])


if __name__ == "__main__":
    unittest.main()
