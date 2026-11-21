"""End-to-end consistency of the outputs (needs a pipeline run)."""
import unittest

from tests.audit_outputs import ROOT, contract_problems, number_checks


@unittest.skipUnless((ROOT / "output" / "greenops.duckdb").exists(), "needs a pipeline run (python -m pipeline.run)")
class OutputsTest(unittest.TestCase):
    def test_contract_fields_ranges_and_references(self):
        self.assertEqual(contract_problems(ROOT), [])

    def test_numbers_agree_across_modules(self):
        failed = [(name, a, b) for ok, name, a, b in number_checks(ROOT) if not ok]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
