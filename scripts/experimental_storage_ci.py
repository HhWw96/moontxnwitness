"""Restore and test one frozen storage candidate without changing the normal SDK.

This entry point is intentionally limited to a checked-in, content-addressed
profile. It does not install dependencies, invoke a database or measure speed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "verification/experimental-candidates/storage-r2-2026-10-21"
BASE_COMMIT = "78635505e4c189c402ba70600632aeaef71ef206"


def binding(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def relative(name):
    value = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or value.is_absolute() or ".." in value.parts:
        raise ValueError("Unsafe frozen candidate path")
    return value


def public_environment(scratch):
    private = ("TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "PRIVATE_KEY")
    env = {key: value for key, value in os.environ.items()
           if not any(word in key.upper() for word in private)}
    env.update(MTW_JOURNAL_SCRATCH=str(scratch), TEMP=str(scratch), TMP=str(scratch),
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    env.pop("PYTHONPATH", None)
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    output = work / "evidence"
    output.mkdir()
    receipt = {"schema": 1, "kind": "experimental-storage-r2-execution",
               "passed": False, "candidateBaselineCommit": BASE_COMMIT,
               "workflowCommit": os.environ.get("GITHUB_SHA"),
               "platform": platform.platform(), "python": sys.version,
               "sqlite": sqlite3.sqlite_version,
               "started": datetime.now(timezone.utc).isoformat(),
               "independentAcceptance": False, "stableApiChanged": False,
               "actualDatabaseExecution": False, "formalPerformanceMeasurement": False,
               "fullCaptureIntegration": False, "runs": [], "failures": []}
    try:
        profile_path = BUNDLE / "bundle-index.json"
        assert binding(profile_path)["sha256"] == "1caf45ea6b0361c6d703c9e34d69881e4c0ba94a41e36a07ccf87df43a629db5"
        profile = json.loads(profile_path.read_bytes())
        assert profile["candidateIndexSha256"] == "7a0147740c722f6194d98def54e6ad0326934895b84f3c09aa468c3d35918079"
        assert profile["baselineCommit"] == BASE_COMMIT
        receipt["profileBinding"] = binding(profile_path)
        restored = work / "isolated-checkout"
        restored.mkdir()
        before = {}
        for target_name, item in profile["files"].items():
            target = restored / relative(target_name)
            original = BUNDLE / relative(item["bundleFile"])
            assert original.is_file() and not original.is_symlink()
            actual = binding(original)
            assert actual == {key: item[key] for key in ("bytes", "sha256")}, target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            with original.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, 65536)
            assert binding(target) == actual
            before[target_name] = actual
        receipt["restoredFiles"] = before
        candidate = restored / "artifacts/source-window-v3-archive-r2-draft"
        index = json.loads((candidate / "candidate-index.json").read_bytes())
        assert binding(candidate / "candidate-index.json")["sha256"] == profile["candidateIndexSha256"]
        for name, expected in index["fileBindings"].items():
            assert binding(candidate / relative(name)) == expected
        for name, expected in index["runtimeDependencies"].items():
            assert binding(restored / relative(name)) == expected
        # Each run has a new scratch base; failed inputs and child crash logs
        # remain available instead of being removed in test cleanup.
        for label, script, expected_count in (
                ("new-gap-cases", "test_gaps.py", 33),
                ("revision-regression", "test_managed.py", 32)):
            scratch = output / (label + "-scratch")
            scratch.mkdir()
            log = output / (label + ".log")
            run = {"name": label, "expectedTests": expected_count, "executed": False,
                   "passed": False, "log": log.name}
            receipt["runs"].append(run)
            try:
                with log.open("xb") as stream:
                    result = subprocess.run([sys.executable, "-B", str(candidate / script)],
                                            cwd=restored, env=public_environment(scratch),
                                            stdout=stream, stderr=subprocess.STDOUT, timeout=600)
                run.update(executed=True, exitCode=result.returncode)
                paths = list(scratch.glob("*/test-receipt.json"))
                assert len(paths) == 1, "Expected exactly one actual test receipt"
                actual_receipt = json.loads(paths[0].read_bytes())
                run["receipt"] = paths[0].relative_to(output).as_posix()
                run["receiptBinding"] = binding(paths[0])
                run["actualTests"] = actual_receipt["tests"]
                run["skipped"] = actual_receipt["skipped"]
                assert actual_receipt["tests"] == expected_count
                assert actual_receipt["actualFilesystemExecution"] is True
                assert actual_receipt["sourceBindingsUnchanged"] is True
                assert actual_receipt["passed"] is True and result.returncode == 0
                if actual_receipt["skipped"]:
                    assert os.name == "nt" and label == "revision-regression"
                    assert len(actual_receipt["skipped"]) <= 2
                    assert all("symlink" in item["test"] or "dangling" in item["test"]
                               for item in actual_receipt["skipped"])
                    assert all("symlink privilege unavailable" in item["reason"]
                               for item in actual_receipt["skipped"])
                run["passed"] = True
            except Exception as error:
                run["error"] = {"class": type(error).__name__, "message": str(error)}
                receipt["failures"].append({"run": label, **run["error"]})
            finally:
                if log.exists():
                    run["logBinding"] = binding(log)
        after = {name: binding(restored / relative(name)) for name in before}
        receipt["sourceBindingsUnchanged"] = before == after
        receipt["passed"] = all(run["passed"] for run in receipt["runs"]) and before == after
    except Exception as error:
        receipt["failures"].append({"class": type(error).__name__, "message": str(error)})
    finally:
        receipt["finished"] = datetime.now(timezone.utc).isoformat()
        with (output / "execution-receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "runs": len(receipt["runs"]),
                      "receipt": str(output / "execution-receipt.json")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
