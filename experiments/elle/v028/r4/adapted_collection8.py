"""Offline collection CLI controls. No real process/service/JVM invocation."""
from pathlib import Path
import hashlib
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "collect_campaign.py"
PIN = "3febadd965e18fd3f653fead261e121ce8bc1a88b34ec659b18dbea0646cbd06"
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == PIN
C = {"__name__": "offline_collector_controls", "__file__": str(SOURCE)}
exec(compile(raw, str(SOURCE), "exec"), C)
OUT = ROOT / "collection-controls-third"
OUT.mkdir(exist_ok=False)
campaign_path = ROOT / "campaign-plan-final2.json"
campaign_raw = campaign_path.read_bytes()
campaign_pin = hashlib.sha256(campaign_raw).hexdigest()
campaign = json.loads(campaign_raw)
controller = ROOT / "r4_controller.py"
count = 0

class Controls(unittest.TestCase):
    def setUp(self):
        global count
        count += 1
        self.work = OUT / ("%02d-" % count + self._testMethodName)
        self.work.mkdir()
        self.outputs = self.work / "outputs"
        self.outputs.mkdir()
        self.report = self.work / "report.json"

    def run_cli(self, *extra):
        argv = ["collect_campaign.py", "--campaign", str(campaign_path),
                "--campaign-sha256", campaign_pin, "--controller", str(controller),
                "--outputs-root", str(self.outputs), "--output", str(self.report), *extra]
        with mock.patch.object(sys, "argv", argv):
            return C["main"]()

    def test_01_absent_campaign_is_all_accounted_not_success(self):
        self.assertEqual(1, self.run_cli())
        result = json.loads(self.report.read_bytes())
        self.assertEqual(2000, result["inputsAccounted"])
        self.assertEqual(0, result["actualElleReturnedInputs"])
        self.assertFalse(result["fullCampaignReturned"])
        self.assertEqual(2000, sum(r["status"] == "not-invoked" for r in result["cases"]))
        self.assertFalse(result["semanticComparisonPerformed"])

    def test_02_existing_unregistered_output_fails_closed(self):
        batch = campaign["batches"][0]
        output = self.outputs / batch["outputDirectory"]
        output.mkdir(parents=True)
        self.assertEqual(1, self.run_cli())
        result = json.loads(self.report.read_bytes())
        self.assertEqual(50, sum(r["status"] == "batch-collection-failure" for r in result["cases"]))
        self.assertEqual(1950, sum(r["status"] == "not-invoked" for r in result["cases"]))
        self.assertEqual(0, result["actualAgreementCount"])

    def test_03_previous_verdict_cannot_replace_original_ledger(self):
        batch = campaign["batches"][0]
        plan = json.loads((ROOT / batch["planPath"]).read_bytes())
        output = self.outputs / batch["outputDirectory"]
        output.mkdir(parents=True)
        for name in ("raw", "summaries"):
            (output / name).mkdir()
        registration = {"planSha256": batch["planSha256"], "cases": plan["cases"],
                        "controllerSha256": campaign["controllerSha256"],
                        "wrapperStdin": {"sha256": campaign["wrapperSha256"]},
                        "runtimeManifestSha256": "e" * 64, "runId": "synthetic-no-checker"}
        registration_raw = json.dumps(registration).encode()
        (output / "registration.json").write_bytes(registration_raw)
        (output / "ledger.jsonl").write_bytes(b"")
        previous = {"registrationSha256": hashlib.sha256(registration_raw).hexdigest(),
                    "process": {"exitCode": 0, "stopReason": None, "logBindings": {}},
                    "cases": [{"id": row["id"], "status": "returned-true",
                               "actualCheckerReturned": True} for row in plan["cases"]]}
        (output / "accounting.json").write_text(json.dumps(previous))
        self.assertEqual(1, self.run_cli("--runtime-sha256", "e" * 64))
        result = json.loads(self.report.read_bytes())
        self.assertEqual(0, result["actualElleReturnedInputs"])
        self.assertEqual(2000, sum(r["status"] == "not-invoked" for r in result["cases"]))

    def test_04_wrong_source_refused_before_import(self):
        fake = self.work / "wrong.py"
        marker = self.work / "must-not-exist"
        fake.write_text("open(%r,'w').write('bad')" % str(marker))
        argv = ["collect_campaign.py", "--campaign", str(campaign_path),
                "--campaign-sha256", campaign_pin, "--controller", str(fake),
                "--outputs-root", str(self.outputs), "--output", str(self.report)]
        with mock.patch.object(sys, "argv", argv), self.assertRaises(ValueError):
            C["main"]()
        self.assertFalse(marker.exists())
        self.assertFalse(self.report.exists())


    def completion(self, status="returned-false", process=None, count=40):
        process = process or {"exitCode": 0, "stopReason": None}
        report = {"actualElleReturnedInputs": 2000, "cases": [{"status": status}] * 2000}
        results = {str(i): {"transportIntegrity": True, "process": process} for i in range(count)}
        return C["completion_flags"](report, results, count, [])

    def test_05_returned_summary_error_cannot_finish_transport(self):
        flags = self.completion(status="result-transport-error")
        self.assertTrue(flags["fullCampaignReturned"])
        self.assertFalse(flags["fullCampaignTransportComplete"])

    def test_06_nonzero_process_cannot_finish_transport(self):
        flags = self.completion(process={"exitCode": 1, "stopReason": None})
        self.assertFalse(flags["fullCampaignTransportComplete"])

    def test_07_unknown_is_retained_transport_not_semantic_agreement(self):
        flags = self.completion(status="returned-unknown")
        self.assertTrue(flags["fullCampaignTransportComplete"])
        self.assertNotIn("agreement", flags)

    def test_08_missing_batch_cannot_finish_transport(self):
        self.assertFalse(self.completion(count=39)["fullCampaignTransportComplete"])


if __name__ == "__main__":
    with (OUT / "unittest.txt").open("x", encoding="utf-8") as stream:
        run = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    receipt = dict(passed=run.wasSuccessful(), testsRun=run.testsRun,
                   failures=len(run.failures), errors=len(run.errors),
                   actualJVMExecuted=False, actualElleExecuted=False,
                   actualSDKExecuted=False, syntheticLedgerOnly=True,
                   actualFrozenCorpusChanged=False, collectorSha256=PIN,
                   controllerSha256=campaign["controllerSha256"])
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    raise SystemExit(0 if receipt["passed"] else 1)
