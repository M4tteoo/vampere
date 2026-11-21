"""Assistant tools that read the advisor's output (no LLM).

    .venv/bin/python -m unittest tests.test_assistant_tools
Uses the last pipeline run (skipped without it).
"""
import unittest

from pipeline.harmonize.context import ROOT


@unittest.skipUnless((ROOT / "output" / "measures.json").exists(), "needs a pipeline run (python -m pipeline.run)")
class AnalysisToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from assistant.data import DataStore
        from assistant.settings import load_settings
        cls.store = DataStore(load_settings())

    def run_tool(self, name, **args):
        from assistant.tools import run_tool
        return run_tool(self.store, name, args)

    def test_entity_filter_includes_parent_and_children(self):
        """A server question also finds the measures on its resource, and the other way round."""
        mf = self.store.output("measures.json")
        for m in mf["measures"]:
            for eid in m["entity_ids"]:
                for asked in self.store.related_ids(eid):
                    r = self.run_tool("analysis", kind="measures", item_id=None, entity_id=asked)
                    self.assertIn(m["id"], [i["id"] for i in r["items"]] if not r.get("truncated") else [m["id"]],
                                  f"{asked} must find {m['id']}")

    def test_locations_are_not_expanded(self):
        self.assertEqual(self.store.related_ids("loc:DE"), {"loc:DE"})

    def test_package_exposes_goals_and_kept_on(self):
        mf = self.store.output("measures.json")
        r = self.run_tool("analysis", kind="package", item_id=None, entity_id=None)
        self.assertEqual(r["recommended_goal"], mf["package"].get("goal"))
        self.assertEqual(set(r["packages_by_goal"]), set(mf.get("packages", {})))
        self.assertEqual(r["kept_on"], mf.get("kept_on"))
        self.assertNotIn("calls", r["analysis"])           # per-call details stay out of the model's context


if __name__ == "__main__":
    unittest.main()
