"""Mock-only HTTP/archive/output checks; no network, SDK or Java execution."""
import copy
import gzip
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
import hosted_public_validation as h


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class Temporary(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent
        self.tmp = tempfile.TemporaryDirectory(prefix=".hosted-unit-", dir=base)
        self.root = Path(self.tmp.name).resolve()
        assert self.root.parent == base and self.root.name.startswith(".hosted-unit-")

    def tearDown(self):
        assert self.root.parent == Path(__file__).resolve().parent and self.root.name.startswith(".hosted-unit-")
        self.tmp.cleanup()

    def archive(self, files, prefix="root/", **limits):
        path = self.root / (str(len(list(self.root.glob("*.zip")))) + ".zip")
        with zipfile.ZipFile(path, "w") as z:
            for name, data in files:
                z.writestr(name, data)
        return h.SafeZip(path, path.stat().st_size, h.file_digest(path), prefix, **limits)


class HttpTests(Temporary):
    class Response(io.BytesIO):
        status = 200
        headers = {}

        def geturl(self):
            return "https://release-assets.githubusercontent.com/path?temporary-public-ticket=not-recorded"

    class Opener:
        def __init__(self, data, headers=None):
            self.data, self.headers, self.requests = data, headers or {}, []

        def open(self, request, **_kwargs):
            self.requests.append(request)
            value = HttpTests.Response(self.data)
            value.headers = self.headers
            return value

    def test_anonymous_asset_and_metadata_headers(self):
        opener = self.Opener(b"abc", {"Content-Length": "3"})
        receipt = h.download(h.DATA_URL, self.root / "download", 3, h.digest(b"abc"), opener)
        self.assertTrue(receipt["anonymous"])
        headers = {k.lower(): v for k, v in opener.requests[0].header_items()}
        self.assertEqual(headers["accept"], "application/octet-stream")
        self.assertFalse(set(headers) & {"authorization", "cookie", "proxy-authorization"})
        metadata = self.Opener(b'{"ok":true}')
        self.assertEqual(h.public_json("https://api.github.com/repos/HhWw96/moontxnwitness/git/ref/tags/v0.5.0", metadata), {"ok": True})
        headers = {k.lower(): v for k, v in metadata.requests[0].header_items()}
        self.assertEqual(headers["accept"], "application/vnd.github+json")
        self.assertFalse(set(headers) & {"authorization", "cookie", "proxy-authorization"})

    def test_download_hash_length_and_body_overrun_rejected(self):
        for index, (data, size, digest, headers) in enumerate([
            (b"abc", 3, "0" * 64, {}), (b"ab", 3, h.digest(b"abc"), {}),
            (b"abcd", 3, h.digest(b"abc"), {}), (b"abc", 3, h.digest(b"abc"), {"Content-Length": "4"}),
            (b"abc", 3, h.digest(b"abc"), {"Content-Encoding": "gzip"})]):
            with self.subTest(index=index), self.assertRaises(ValueError):
                h.download(h.DATA_URL, self.root / str(index), size, digest, self.Opener(data, headers))

    def test_redirect_destination_must_stay_public_https(self):
        for url in ["http://github.com/a", "https://github.com.evil.invalid/a", "https://evil.invalid/a",
                    "https://user:secret@github.com/a", "https://github.com:444/a", "file:///etc/passwd"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                h.checked_url(url)

    def test_library_tag_and_data_tag_targets_are_separate(self):
        direct = {"ref": "refs/tags/v0.5.0", "object": {"type": "commit", "sha": h.LIBRARY_SOURCE}}
        with patch.object(h, "public_json", return_value=direct):
            self.assertFalse(h.verify_library_tag()["dataReleaseTargetRequiredToEqualLibrarySource"])
        direct["object"]["sha"] = "0" * 40
        with patch.object(h, "public_json", return_value=direct), self.assertRaises(ValueError):
            h.verify_library_tag()

    def test_subprocess_does_not_receive_ambient_auth_or_loader_override(self):
        with patch.dict(h.os.environ, {"GH_TOKEN": "synthetic", "COOKIE": "synthetic", "NODE_OPTIONS": "--bad", "PUBLIC_TEST_KEEP": "kept"}):
            env = h.subprocess_environment()
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("COOKIE", env)
            self.assertNotIn("NODE_OPTIONS", env)
            self.assertEqual(env["PUBLIC_TEST_KEEP"], "kept")


class ZipTests(Temporary):
    def test_inventory_crc_hash_and_selected_extraction(self):
        archive = self.archive([("root/a.txt", "a"), ("root/deep/b.txt", "b")])
        self.assertEqual(archive.inventory["root/a.txt"], {"bytes": 1, "sha256": h.digest(b"a")})
        archive.extract(["root/deep/b.txt"], self.root / "out")
        self.assertEqual((self.root / "out/deep/b.txt").read_bytes(), b"b")
        self.assertFalse((self.root / "out/a.txt").exists())

    def test_unsafe_paths_and_wrong_root(self):
        for name in ["../a", "root/../a", "/root/a", "root//a", "root/./a", "C:/a", "root/NUL.txt", "other/a", "root/trailing."]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.archive([(name, "x")])

    def test_real_duplicate_and_case_collision(self):
        for names in [["root/same", "root/same"], ["root/same", "root/SAME"]]:
            with warnings.catch_warnings(record=True), self.assertRaises(ValueError):
                warnings.simplefilter("always")
                self.archive([(name, "x") for name in names])

    def test_links_and_member_or_expansion_budgets(self):
        path = self.root / "link.zip"
        with zipfile.ZipFile(path, "w") as z:
            info = zipfile.ZipInfo("root/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "../target")
        with self.assertRaises(ValueError):
            h.SafeZip(path, path.stat().st_size, h.file_digest(path), "root/")
        with self.assertRaises(ValueError):
            self.archive([("root/big", "x" * 10)], max_member=9)
        with self.assertRaises(ValueError):
            self.archive([("root/a", "x" * 6), ("root/b", "x" * 6)], max_expanded=10)

    def test_pinned_zip_hash_and_length_are_mandatory(self):
        archive = self.archive([("root/a", "x")])
        path = Path(archive.zip.filename)
        with self.assertRaises(ValueError):
            h.SafeZip(path, path.stat().st_size, "0" * 64, "root/")
        with self.assertRaises(ValueError):
            h.SafeZip(path, path.stat().st_size + 1, h.file_digest(path), "root/")

    def test_manifest_core_and_package_version_are_independently_bound(self):
        prefix = "MoonTxnWitness-v0.5.0/"
        core, capture, configured = b"actual core", b"capture", b"configured"
        manifest = {"version": "0.5.0", "sourceSha256": "a" * 64, "toolchain": {"compiler": "v0.10.16+b1a0e846e"},
                    "coreSha256": h.digest(core), "captureCoreSha256": h.digest(capture),
                    "configuredCoreSha256": {"configured-core.mjs": h.digest(configured)}}
        def candidate(value, version="0.5.0", actual_core=core):
            return self.archive([(prefix + "package.json", raw({"version": version})),
                (prefix + "dist/build-manifest.json", raw(value)), (prefix + "dist/core.mjs", actual_core),
                (prefix + "dist/models-v4.mjs", b"host"), (prefix + "dist/capture-core.mjs", capture),
                (prefix + "dist/configured-core.mjs", configured)], prefix)
        self.assertEqual(h.validate_portable(candidate(manifest))["coreSha256"], h.digest(core))
        for value, version, actual in [(manifest, "0.4.5", core), (manifest, "0.5.0", b"changed"),
                                       ({**manifest, "coreSha256": "0" * 64}, "0.5.0", core)]:
            with self.subTest(version=version, actual=actual), self.assertRaises(ValueError):
                h.validate_portable(candidate(value, version, actual))

    def test_sealed_data_manifest_mismatch_is_not_accepted(self):
        class Fake:
            prefix = "sealed-reference/"
            @staticmethod
            def read(_): return b"{}"
        with self.assertRaisesRegex(ValueError, "manifest pin"):
            h.validate_data(Fake())


class ResultTests(Temporary):
    def write_result(self, target, mutate=None):
        target.mkdir()
        job, refs, items, entries = [], [], [], []
        empty = {key: 0 for key in ["match", "difference", "sdkUnknown", "upstreamNotComparable", "timeout", "failure"]}
        totals = {**empty, "match": 1997, "upstreamNotComparable": 3}
        report_text = raw({"format": "moontxnwitness-model-composition/v4", "schemaVersion": 4,
            "sourceProfile": "captured-register-full-program/v2", "models": [{"model": "serializable", "status": "refuted"}]}).decode()
        for i in range(2000):
            source = {"dataModel": "point-register-v1", "events": []}
            source_text = raw(source).decode()
            row = {"id": str(i), "input": source, "inputSha256": h.digest(source_text.encode())}
            eligible = i < 1997
            ref = {"id": str(i), "inputSha256": row["inputSha256"], "comparisonEligible": eligible,
                   "validity": False if eligible else None, "cycleSearchTimeout": False,
                   "raw": {"sha256": h.digest(b"upstream")}, "summary": {"sha256": h.digest(b"summary")}}
            item = {"id": str(i), "dataModel": "point-register-v1", "inputSha256": row["inputSha256"], "referenceEligible": eligible,
                "upstreamValidity": ref["validity"], "upstreamCycleSearchTimeout": False,
                "classificationAttempted": True, "verificationAttempted": True,
                "callerOptions": {"models": ["serializable"], "maxSourceChecks": 1000000, "maxStates": 100000, "maxEdgeChecks": 1000000},
                "reportSha256": h.digest(report_text.encode()), "sdkStatus": "refuted",
                "sourceProfile": "captured-register-full-program/v2", "sdkDisposition": "complete",
                "outcome": "match" if eligible else "upstreamNotComparable"}
            entry = {"item": item, "input": source, "sourceText": source_text, "upstreamReference": ref,
                     "upstreamRawEdn": "upstream", "upstreamSummaryText": "summary",
                     "sdkReportText": report_text, "sdkVerification": {"valid": True}}
            job.append(row); refs.append(ref); items.append(item); entries.append(entry)
        runtime_files = {"core.mjs": "a" * 64}
        summary = {"version": "0.5.0", "runtimeOrigin": "public-download", "runtimeFilesUnchanged": True,
            "runtime": {"files": runtime_files}, "referenceSha256": h.REFERENCE_SHA, "jobSha256": h.JOB_SHA,
            "models": ["serializable"], "listProfile": "captured-list-original-serial/v1",
            "completed": 2000, "classifications": 2000, "verifications": 2000,
            "upstreamEligible": 1997, "upstreamNotComparable": 3, "totals": totals,
            "eligibleOutcomes": {**empty, "match": 1997},
            "byDataModel": {"point-register-v1": totals.copy(), "append-list-v1": empty.copy()},
            "sdkDispositions": {"complete": 2000, "unknown": 0, "timeout": 0, "failure": 0}, "passed": True, "fatal": None}
        if mutate:
            mutate(items, entries, summary)
        item_bytes = b"\n".join(raw(item) for item in items) + b"\n"
        report_bytes = b"\n".join(raw(entry) for entry in entries) + b"\n"
        (target / "items.jsonl").write_bytes(item_bytes)
        (target / "reports.jsonl.gz").write_bytes(gzip.compress(report_bytes))
        summary.update(itemSha256=h.digest(item_bytes), reportsGzipSha256=h.file_digest(target / "reports.jsonl.gz"),
                       reportStreamSha256=h.digest(report_bytes), reportUncompressedBytes=len(report_bytes))
        (target / "summary.json").write_bytes(raw(summary))
        return runtime_files, job, {"cases": refs}

    def test_full_pure_data_recount_accepts_consistent_mock(self):
        path = self.root / "consistent"
        values = self.write_result(path)
        self.assertTrue(h.validate_comparison(path, *values)["passed"])

    def test_rehashed_outcome_or_counter_tampering_rejected(self):
        def changed_outcome(items, entries, summary):
            items[0]["outcome"] = "difference"
        def changed_counter(items, entries, summary):
            summary["eligibleOutcomes"]["match"] -= 1
        def changed_eligibility(items, entries, summary):
            items[0]["referenceEligible"] = False
        def changed_raw(items, entries, summary):
            entries[0]["upstreamRawEdn"] = "changed raw"
        def changed_data_model(items, entries, summary):
            items[0]["dataModel"] = "append-list-v1"
        def changed_fatal(items, entries, summary):
            summary["fatal"] = "execution did not complete"
        for index, mutate in enumerate([changed_outcome, changed_counter, changed_eligibility, changed_raw, changed_data_model, changed_fatal]):
            path = self.root / str(index)
            values = self.write_result(path, mutate)
            with self.subTest(index=index), self.assertRaises(ValueError):
                h.validate_comparison(path, *values)

    def test_coherent_rehashed_difference_cannot_inherit_passed_true(self):
        def changed(items, entries, summary):
            report = h.strict_json(entries[0]["sdkReportText"])
            report["models"][0]["status"] = "checked-compatible"
            entries[0]["sdkReportText"] = raw(report).decode()
            items[0].update(reportSha256=h.digest(entries[0]["sdkReportText"].encode()), sdkStatus="checked-compatible", outcome="difference")
            for counts in [summary["totals"], summary["eligibleOutcomes"], summary["byDataModel"]["point-register-v1"]]:
                counts["match"] -= 1
                counts["difference"] += 1
        path = self.root / "coherent-difference"
        values = self.write_result(path, changed)
        with self.assertRaisesRegex(ValueError, "recounted SDK differences"):
            h.validate_comparison(path, *values)

    def test_upstream_unknown_position_still_requires_valid_sdk_status(self):
        def changed(items, entries, summary):
            report = h.strict_json(entries[-1]["sdkReportText"])
            report["models"][0]["status"] = "invented-status"
            entries[-1]["sdkReportText"] = raw(report).decode()
            items[-1].update(reportSha256=h.digest(entries[-1]["sdkReportText"].encode()), sdkStatus="invented-status")
        path = self.root / "ineligible-still-validated"
        values = self.write_result(path, changed)
        with self.assertRaisesRegex(ValueError, "SDK model status outside contract"):
            h.validate_comparison(path, *values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
