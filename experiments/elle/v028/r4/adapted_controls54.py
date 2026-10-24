"""Offline first controls: synthetic protocol/files only, no JVM/SDK/network/DB."""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import marshal
import os
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
SOURCE_PIN = "4f9a73a5fe82478d913cb751ab68714d4ba0558c85b45a3933c6eb9a6c3078ef"
raw = (ROOT / "r4_controller.py").read_bytes()
assert hashlib.sha256(raw).hexdigest() == SOURCE_PIN
M = {"__name__": "independent_offline_r4", "__file__": str(ROOT / "r4_controller.py")}
exec(compile(raw, M["__file__"], "exec"), M)
OUT = ROOT / "offline-fourth"
OUT.mkdir(exist_ok=False)
COUNT = 0


class FakeProcess:
    def __init__(self, stdout=b"raw-out\x00", stderr=b"raw-error", code=7):
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(stdout), io.BytesIO(stderr)
        self.returncode, self.pid = code, 123456
    def poll(self):
        return self.returncode
    def wait(self, timeout=None):
        return self.returncode


class Controls(unittest.TestCase):
    def setUp(self):
        global COUNT
        COUNT += 1
        self.work = OUT / ("%03d-" % COUNT + self._testMethodName)
        self.work.mkdir()
        self.raw, self.summaries = self.work / "raw", self.work / "summaries"
        self.raw.mkdir()
        self.summaries.mkdir()
        self.ledger = self.work / "ledger.jsonl"
        self.ledger.write_bytes(b"")
        self.cases = [{"id": "A", "inputSha256": "a" * 64},
                      {"id": "B", "inputSha256": "b" * 64}]
        self.sequence, self.previous = 0, "0" * 64
        self.run_id = "r4-synthetic-controls"
        self.process = {"exitCode": 0, "stopReason": None, "timedOut": False}

    def mark(self, phase, ordinal=0, **extra):
        self.sequence += 1
        body = dict(sequence=self.sequence, runId=self.run_id, ordinal=ordinal,
                    phase=phase, **self.cases[ordinal])
        body.update(extra)
        text = json.dumps(body, ensure_ascii=True, separators=(",", ":"))
        digest = hashlib.sha256(text.encode()).hexdigest()
        envelope = dict(body=text, bodySha256=digest, previousSha256=self.previous)
        with self.ledger.open("ab") as file:
            file.write(json.dumps(envelope).encode() + b"\n")
            file.flush()
            os.fsync(file.fileno())
        self.previous = digest

    def payload(self, verdict=True, timeout=False):
        typed = ({"kind": "boolean", "value": verdict} if type(verdict) is bool
                 else {"kind": "keyword", "value": "unknown"})
        return dict(self.cases[0], valid=verdict, originalValidity=typed,
                    cycleSearchTimeout=timeout, anomalyTypes=[],
                    actualElleInvocationAttempted=True, actualElleResultReturned=True,
                    rawResultRetained=True, rawResultFile="A.edn")

    def complete(self, value=None, phases=("preparing", "invocation-intent", "returned")):
        value = value or self.payload()
        for phase in phases:
            self.mark(phase)
        if value.get("rawResultRetained"):
            (self.raw / "A.edn").write_bytes(b"{:valid? :synthetic-only}\n")
        summary = self.summaries / "A.json"
        summary.write_bytes(json.dumps(value).encode() + b"\n")
        self.mark("completed", result=value, summary=M["binding"](summary),
                  raw=M["binding"](self.raw / "A.edn") if (self.raw / "A.edn").exists() else None)

    def result(self):
        return M["account"](self.cases, self.ledger, self.summaries, self.raw,
                            self.run_id, self.process)

    def status(self):
        return self.result()["cases"][0]["status"]

    def reject(self):
        result = self.result()
        self.assertFalse(result["transportIntegrity"])
        self.assertTrue(all(not r["comparisonEligible"] for r in result["cases"]))

    def test_01_empty_not_invoked(self):
        self.assertEqual(["not-invoked", "not-invoked"], [r["status"] for r in self.result()["cases"]])

    def test_02_preparation_interrupt(self):
        self.mark("preparing")
        self.assertEqual("preparation-interrupted", self.status())

    def test_03_intent_is_not_actual_call(self):
        self.mark("preparing")
        self.mark("invocation-intent")
        row = self.result()["cases"][0]
        self.assertEqual("interrupted-after-intent", row["status"])
        self.assertFalse(row["actualCheckerInvocationAttempted"])
        self.assertFalse(row["actualCheckerReturned"])

    def test_04_return_without_transport(self):
        for phase in ("preparing", "invocation-intent", "returned"):
            self.mark(phase)
        row = self.result()["cases"][0]
        self.assertTrue(row["actualCheckerReturned"])
        self.assertFalse(row["comparisonEligible"])

    def test_05_true_complete(self):
        self.complete()
        self.assertEqual("returned-true", self.status())
        self.assertEqual({"agree": 1, "different": 0, "notCompared": 1},
                         M["comparison_counts"](self.result(), {"A": True, "B": True}))

    def test_06_false_complete(self):
        self.complete(self.payload(False))
        self.assertEqual("returned-false", self.status())
        self.assertEqual(1, M["comparison_counts"](self.result(), {"A": True})["different"])

    def test_07_false_with_timeout_preserved_not_agreement(self):
        self.complete(self.payload(False, True))
        row = self.result()["cases"][0]
        self.assertEqual({"kind": "boolean", "value": False}, row["originalValidity"])
        self.assertEqual("returned-false-with-cycle-timeout", row["status"])
        self.assertEqual(0, M["comparison_counts"](self.result(), {"A": False})["agree"])

    def test_08_unknown_never_agreement(self):
        self.complete(self.payload("unknown"))
        self.assertEqual("returned-unknown", self.status())
        self.assertEqual(0, M["comparison_counts"](self.result(), {"A": "unknown"})["agree"])

    def test_09_checker_failure(self):
        p = dict(self.cases[0], valid="execution-error", failureStage="checker",
                 actualElleInvocationAttempted=True, actualElleResultReturned=False,
                 rawResultRetained=False)
        self.complete(p, ("preparing", "invocation-intent"))
        self.assertEqual("execution-error-checker", self.status())

    def test_10_preparation_failure(self):
        p = dict(self.cases[0], valid="execution-error", failureStage="preparation",
                 actualElleInvocationAttempted=False, actualElleResultReturned=False,
                 rawResultRetained=False)
        self.complete(p, ("preparing",))
        self.assertEqual("execution-error-preparation", self.status())

    def test_11_summary_failure_preserves_returned_raw(self):
        p = dict(self.cases[0], valid="execution-error", failureStage="result-transport",
                 actualElleInvocationAttempted=True, actualElleResultReturned=True,
                 rawResultRetained=True)
        self.complete(p)
        self.assertEqual("result-transport-error", self.status())
        self.assertTrue(self.result()["cases"][0]["actualCheckerReturned"])
        self.assertTrue((self.raw / "A.edn").exists())

    def test_12_reader_failure_other_not_invoked(self):
        self.mark("reader-error", errorClass="synthetic.ReaderFailure")
        self.assertEqual(["reader-failure", "not-invoked"], [r["status"] for r in self.result()["cases"]])

    def test_13_reader_failure_cannot_continue(self):
        self.mark("reader-error")
        self.mark("preparing", ordinal=1)
        self.reject()

    def test_14_duplicate_phase(self):
        self.mark("preparing")
        self.mark("preparing")
        self.reject()

    def test_15_unexpected_id(self):
        self.mark("preparing", id="other")
        self.reject()

    def test_16_original_digest_mismatch(self):
        self.mark("preparing", inputSha256="c" * 64)
        self.reject()

    def test_17_run_identity(self):
        self.mark("preparing", runId="other-run")
        self.reject()

    def test_18_truncated_ledger(self):
        self.mark("preparing")
        self.ledger.write_bytes(self.ledger.read_bytes()[:-1])
        self.reject()

    def test_19_ledger_body_tamper(self):
        self.mark("preparing")
        self.ledger.write_bytes(self.ledger.read_bytes().replace(b"preparing", b"returning"))
        self.reject()

    def test_20_raw_tamper(self):
        self.complete()
        (self.raw / "A.edn").write_bytes(b"changed")
        self.reject()

    def test_21_summary_tamper(self):
        self.complete()
        (self.summaries / "A.json").write_bytes(b"{}")
        self.reject()

    def test_22_unknown_summary(self):
        (self.summaries / "outside.json").write_bytes(b"{}")
        self.reject()

    def test_23_unknown_raw(self):
        (self.raw / "outside.edn").write_bytes(b"{}")
        self.reject()

    def test_24_typed_original_mismatch(self):
        p = self.payload(False)
        p["originalValidity"]["value"] = True
        self.complete(p)
        self.reject()

    def test_25_numeric_verdict_is_not_boolean(self):
        p = self.payload()
        p["valid"] = 1
        self.complete(p)
        self.reject()

    def test_26_unproved_actual_return(self):
        self.complete(self.payload(), ("preparing",))
        self.reject()

    def test_27_out_of_order_input(self):
        self.mark("preparing", ordinal=1)
        self.reject()

    def test_28_chain_reorder(self):
        self.mark("preparing")
        self.mark("invocation-intent")
        self.ledger.write_bytes(b"".join(reversed(self.ledger.read_bytes().splitlines(keepends=True))))
        self.reject()

    def test_29_duplicate_case(self):
        with self.assertRaises(ValueError):
            M["expected_cases"]([self.cases[0], self.cases[0]])

    def test_30_unsafe_id(self):
        with self.assertRaises(ValueError):
            M["expected_cases"]([dict(self.cases[0], id="../escape")])

    def test_31_wrong_source_digest_before_execute(self):
        path = self.work / "helper.py"
        marker = self.work / "must-not-exist"
        path.write_text("open(%r, 'w').write('bad')\n" % str(marker), encoding="utf-8")
        with self.assertRaises(ValueError):
            M["source_module"](path, "0" * 64, "guarded_helper")
        self.assertFalse(marker.exists())

    def test_32_valid_cached_bytecode_is_ignored(self):
        source = self.work / "cached_helper.py"
        source.write_bytes(b"VALUE = 'raw'\n")
        cached = Path(importlib.util.cache_from_source(str(source)))
        cached.parent.mkdir()
        evil = compile("VALUE = 'cached'\n", str(source), "exec")
        cached.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack(
            "<III", 0, int(source.stat().st_mtime), source.stat().st_size) + marshal.dumps(evil))
        namespace = M["source_module"](source, hashlib.sha256(source.read_bytes()).hexdigest(), "pinned_helper")
        self.assertEqual("raw", namespace["VALUE"])

    def test_33_duplicate_json_key(self):
        with self.assertRaises(ValueError):
            M["decode"](b'{"id":1,"id":2}')

    def test_34_number_sdk_is_not_comparable(self):
        self.complete()
        self.assertEqual(0, M["comparison_counts"](self.result(), {"A": 1})["agree"])

    def fake_process(self, process, **options):
        fake_os = SimpleNamespace(name="posix", fsync=os.fsync,
                                  killpg=lambda pid, sig: setattr(process, "returncode", -9))
        with mock.patch.dict(M, {"os": fake_os, "signal": SimpleNamespace(SIGKILL=9)}), mock.patch.object(
                M["subprocess"], "Popen", return_value=process):
            return M["run_process"](["synthetic-child-no-execution"], self.work, {},
                                     b"synthetic stdin", self.work, **options)

    def test_35_raw_stdout_stderr_and_exit(self):
        p = self.fake_process(FakeProcess())
        self.assertEqual(7, p["exitCode"])
        self.assertEqual(b"raw-out\x00", (self.work / "stdout.raw").read_bytes())
        self.assertEqual(b"raw-error", (self.work / "stderr.raw").read_bytes())

    def test_36_fast_exit_log_budget_still_fails(self):
        p = self.fake_process(FakeProcess(stdout=b"0123456789", code=0), log_limit=4)
        self.assertEqual("log-budget-or-write-failure", p["stopReason"])
        self.assertTrue(p["rawStreamsMayBeTruncated"])
        self.assertEqual(b"0123", (self.work / "stdout.raw").read_bytes())

    def test_37_timeout_owns_only_mock_child_group(self):
        p = self.fake_process(FakeProcess(code=None), timeout=0)
        self.assertTrue(p["timedOut"])
        self.assertEqual(-9, p["exitCode"])

    def test_38_fast_exit_artifact_budget(self):
        p = self.fake_process(FakeProcess(code=0), artifact_limit=1)
        self.assertEqual("artifact-budget", p["stopReason"])

    def test_39_log_write_failure(self):
        (self.work / "stdout.raw").write_bytes(b"first-evidence")
        p = self.fake_process(FakeProcess(code=0))
        self.assertEqual("log-budget-or-write-failure", p["stopReason"])
        self.assertTrue(p["controllerErrors"])
        self.assertEqual(b"first-evidence", (self.work / "stdout.raw").read_bytes())

    def test_40_process_timeout_does_not_label_uninvoked_ids_timeout(self):
        self.process.update(exitCode=-9, timedOut=True, stopReason="process-timeout")
        self.mark("preparing")
        self.mark("invocation-intent")
        self.assertEqual(["interrupted-after-intent", "not-invoked"],
                         [r["status"] for r in self.result()["cases"]])


    def test_41_full_campaign_missing_batches_accounted(self):
        groups = {}
        for batch in range(40):
            groups["batch-%03d" % batch] = [
                {"id": "original-%d" % (batch * 50 + item), "inputSha256": "c" * 64}
                for item in range(50)]
        report = M["campaign_account"](groups, {})
        self.assertEqual(2000, report["inputsAccounted"])
        self.assertEqual(2000, sum(r["status"] == "not-invoked" for r in report["cases"]))
        self.assertEqual(0, report["actualAgreementCount"])

    def test_42_campaign_duplicate_original_id_rejected(self):
        with self.assertRaises(ValueError):
            M["campaign_account"]({"batch-a": self.cases, "batch-b": self.cases}, {}, total=4)

    def test_43_campaign_unknown_batch_rejected(self):
        with self.assertRaises(ValueError):
            M["campaign_account"]({"batch-a": self.cases}, {"other": {}}, total=2)

    def test_44_campaign_missing_original_id_rejected(self):
        with self.assertRaises(ValueError):
            M["campaign_account"]({"batch-a": self.cases}, {}, total=2000)

    def test_45_campaign_wrong_result_identity_rejected(self):
        self.complete()
        result = self.result()
        result["cases"][0]["inputSha256"] = "d" * 64
        with self.assertRaises(ValueError):
            M["campaign_account"]({"batch-a": self.cases}, {"batch-a": result}, total=2)

    def test_46_resource_gate_exact_boundaries(self):
        gate = M["resource_gate"]
        self.assertFalse(gate(1288490188, 2147483648)["passed"])
        self.assertFalse(gate(1288490189, 2147483647)["passed"])
        self.assertTrue(gate(1288490189, 2147483648)["passed"])

    def test_47_runtime_null_manifest_rejected(self):
        with self.assertRaises((ValueError, TypeError)):
            M["validate_runtime"](b"null")

    def test_48_digest_uppercase_rejected(self):
        with self.assertRaises(ValueError):
            M["expected_cases"]([dict(self.cases[0], inputSha256="A" * 64)])


    def test_49_completed_false_kept_but_batch_timeout_not_agreement(self):
        self.complete(self.payload(False))
        self.process.update(exitCode=-9, stopReason="process-timeout", timedOut=True)
        result = self.result()
        self.assertEqual("returned-false", result["cases"][0]["status"])
        self.assertTrue(result["cases"][0]["actualCheckerReturned"])
        self.assertEqual(0, M["comparison_counts"](result, {"A": False})["agree"])

    def test_50_truncated_raw_log_not_agreement(self):
        self.complete()
        self.process["rawStreamsMayBeTruncated"] = True
        self.assertEqual(0, M["comparison_counts"](self.result(), {"A": True})["agree"])

    def test_51_nonzero_batch_exit_not_agreement(self):
        self.complete()
        self.process["exitCode"] = 1
        self.assertEqual(0, M["comparison_counts"](self.result(), {"A": True})["agree"])

    def test_52_unbound_controller_loader_refused_before_start(self):
        plan = self.work / "plan.json"
        plan.write_bytes(json.dumps({"controllerSha256": SOURCE_PIN}).encode())
        args = SimpleNamespace(plan=plan, plan_sha256=hashlib.sha256(plan.read_bytes()).hexdigest(),
                               output=str(self.work / "must-not-be-created"))
        with self.assertRaisesRegex(ValueError, "same-byte controller"):
            M["execute"](args)
        self.assertFalse(Path(args.output).exists())


    def test_53_blocked_stdin_does_not_block_timeout(self):
        import threading
        release = threading.Event()
        class BlockedStdin:
            def write(self, raw):
                if not release.wait(2):
                    raise RuntimeError("Synthetic feed did not receive owned-group termination")
                raise BrokenPipeError("Synthetic child stopped reading")
            def flush(self):
                pass
            def close(self):
                pass
        p = FakeProcess(code=None)
        p.stdin = BlockedStdin()
        def stop_owned(pid, sig):
            self.assertEqual(123456, pid)
            p.returncode = -9
            release.set()
        fake_os = SimpleNamespace(name="posix", fsync=os.fsync, killpg=stop_owned)
        with mock.patch.dict(M, {"os": fake_os, "signal": SimpleNamespace(SIGKILL=9)}), mock.patch.object(
                M["subprocess"], "Popen", return_value=p):
            result = M["run_process"](["synthetic-child-no-execution"], self.work, {},
                                       b"source larger than synthetic blocked pipe", self.work, timeout=0)
        self.assertTrue(result["timedOut"])
        self.assertFalse(result["stdinDelivery"]["fullyDelivered"])
        self.assertTrue(any(e["stage"] == "stdin" for e in result["controllerErrors"]))

    def test_54_exact_source_delivery_bytes_retained(self):
        result = self.fake_process(FakeProcess(code=0))
        self.assertEqual(len(b"synthetic stdin"), result["stdinDelivery"]["writtenBytes"])
        self.assertEqual(hashlib.sha256(b"synthetic stdin").hexdigest(),
                         result["stdinDelivery"]["sha256"])
        self.assertTrue(result["stdinDelivery"]["fullyDelivered"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    with (OUT / "unittest.stdout-stderr.txt").open("x", encoding="utf-8") as stream:
        run = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    result = dict(schema=1, kind="offline-synthetic-r4-stdin-final-controls",
                  passed=run.wasSuccessful(), testsRun=run.testsRun, failures=len(run.failures),
                  errors=len(run.errors), skipped=len(run.skipped), sourceSha256=SOURCE_PIN,
                  actualJVMLaunched=False, actualOSChildGroupLaunched=False,
                  actualElleExecuted=False, actualSDKExecuted=False, network=False,
                  actualDatabaseExecuted=False, processControlTestsAreMocked=True,
                  rawLogsAndFsyncUseRealExclusiveSmallFiles=True)
    (OUT / "receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
