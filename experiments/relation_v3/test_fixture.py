"""Lightweight producer checks, not the independent relational oracle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import run_postgres as fixture


class FixtureTests(unittest.TestCase):
    def test_plan_frozen_expected(self):
        plan = json.loads((Path(__file__).parent / "plan.json").read_text())
        self.assertEqual(plan["roundsPerScenario"], 20)
        self.assertEqual(len(plan["scenarios"]), 8)
        self.assertEqual(sum(s["expected"] == "violation" for s in plan["scenarios"]), 3)
    def test_int64_and_unicode_projection(self):
        result = fixture.row((-9223372036854775808, 9223372036854775807, True, "\U00010000", "server-token"))
        self.assertEqual(result["key"], "-9223372036854775808")
        self.assertEqual(result["values"]["balance"], "9223372036854775807")
        self.assertLess("\ue000", "\U00010000")
        with self.assertRaises(AssertionError): fixture.row((1, 2, True, "\x00", "token"))
    def test_safe_identifiers(self):
        self.assertEqual(fixture.quoted("safe_1"), '"safe_1"')
        for name in ('bad"x', "bad.x", "a" * 64, "1x", "x;DROP"):
            with self.assertRaises(ValueError): fixture.quoted(name)
    def test_reverted_effects_only_not_observations(self):
        events = [{"kind":"begin","tx":"A"}, {"kind":"row_write","tx":"A","seq":2},
            {"kind":"savepoint","tx":"A","instance":"S1"}, {"kind":"row_write","tx":"A","seq":4},
            {"kind":"row_read","tx":"A","seq":5}, {"kind":"savepoint","tx":"A","instance":"S2"},
            {"kind":"row_write","tx":"A","seq":7}, {"kind":"rollback_to","tx":"A","instance":"S2"},
            {"kind":"release","tx":"A","instance":"S2"}, {"kind":"rollback_to","tx":"A","instance":"S1"},
            {"kind":"commit_ok","tx":"A"}]
        self.assertEqual([e["seq"] for e in fixture.surviving_writes(events)], [2])
        self.assertEqual(events[4]["seq"], 5)
    def test_aborted_effect_not_final_ledger(self):
        events = [{"kind":"begin","tx":"A"},{"kind":"row_write","tx":"A","seq":2},{"kind":"rollback_ok","tx":"A"},
            {"kind":"begin","tx":"retry"},{"kind":"row_write","tx":"retry","seq":5},{"kind":"commit_ok","tx":"retry"}]
        self.assertEqual([e["seq"] for e in fixture.surviving_writes(events)], [5])
    def not_executed(self, no_site):
        with tempfile.TemporaryDirectory(prefix="mtw-relation-unit-") as work:
            output = Path(work) / "output"
            env = {k:v for k,v in os.environ.items() if k not in ("MTW_PG_CONNECTION_FILE", "MTW_PG_DSN")}
            result = subprocess.run([sys.executable, "-B", *(["-S"] if no_site else []),
                str(Path(fixture.__file__)), "--output", str(output)], env=env,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 3, result.stderr)
            receipt = json.loads((output / "database-receipt.json").read_text())
            self.assertFalse(receipt["actualDatabaseExecution"])
            self.assertFalse(receipt["passed"])
            self.assertIn("notExecuted", receipt)
            return receipt
    def test_optional_database_is_not_executed(self):
        self.assertIn("configured", self.not_executed(False)["notExecuted"])
    def test_optional_driver_is_not_executed(self):
        self.assertIn("driver", self.not_executed(True)["notExecuted"])


if __name__ == "__main__": unittest.main()
