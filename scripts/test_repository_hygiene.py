"""Exercise staged versus untracked files and real Git blob identities."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from repository_hygiene import inventory, check


class IndexBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mtw-hygiene-")
        self.root = Path(self.temp.name)
        self.git("init", "--quiet")
        self.git("config", "core.autocrlf", "false")
        self.policy = {"maxTrackedFiles": 10, "maxTrackedBytes": 1000, "maxNewFileBytes": 100,
                       "frozenLargeFiles": {}, "frozenExternalMoonbit": {}, "frozenSourceDuplicateGroups": []}

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args])

    def add(self, name, text="test source"):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        self.git("add", "--", name)

    def audit(self):
        return check(inventory(self.root), self.policy)

    def test_untracked_outputs_do_not_expand_audit(self):
        self.add("src/main.mbt")
        (self.root / "output.bin").write_bytes(b"x" * 2000)
        self.assertTrue(self.audit()["passed"])
        self.assertEqual(self.audit()["trackedFiles"], 1)

    def test_source_copy_and_nested_project_are_rejected(self):
        self.add("src/main.mbt")
        self.add("verification/old/source/main.mbt")
        self.add("verification/old/source/moon.mod", 'name = "old"')
        failures = self.audit()["failures"]
        self.assertTrue(any("duplicated MoonBit" in e for e in failures))
        self.assertTrue(any("nested complete" in e for e in failures))

    def test_frozen_proof_is_bound_to_original_blob(self):
        self.add("verification/proof/oracle.mbt")
        self.policy["frozenExternalMoonbit"] = {r["path"]: r["oid"] for r in inventory(self.root)}
        self.assertTrue(self.audit()["passed"])
        self.add("verification/proof/oracle.mbt", "changed interpretation")
        self.assertFalse(self.audit()["passed"])

    def test_deletion_removes_file_from_index_inventory(self):
        self.add("src/main.mbt")
        self.add("verification/archive/data.json", "x" * 101)
        self.assertFalse(self.audit()["passed"])
        self.git("rm", "--cached", "--force", "verification/archive/data.json")
        self.assertTrue((self.root / "verification/archive/data.json").is_file())
        self.assertTrue(self.audit()["passed"])

    def test_frozen_large_input_does_not_allow_arbitrary_replacement(self):
        self.add("fixtures/oracle.json", "x" * 101)
        self.policy["frozenLargeFiles"] = {r["path"]: r["oid"] for r in inventory(self.root)}
        self.assertTrue(self.audit()["passed"])
        self.add("fixtures/oracle.json", "y" * 101)
        self.assertFalse(self.audit()["passed"])

    def test_combined_size_and_cache_are_rejected(self):
        self.add("node_modules/a.js", "x" * 60)
        self.add("fixtures/a.json", "x" * 60)
        self.policy["maxTrackedBytes"] = 100
        self.assertFalse(self.audit()["passed"])
        self.assertEqual(len(self.audit()["failures"]), 2)


if __name__ == "__main__":
    unittest.main()
