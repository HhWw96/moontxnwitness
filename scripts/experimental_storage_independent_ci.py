"""Run the independently frozen final-cleanup fault against a frozen candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from experimental_storage_ci import ROOT, PROFILES, binding, relative, public_environment

INDEPENDENT = ROOT / "verification/experimental-candidates/storage-independent-final-sync-2026-10-21"
INDEX_SHA = "fddf3651801ad0ba096f616793d0de435764d0888dbcad61dcf45736a3f94cfa"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--candidate", choices=[name for name in PROFILES if name in ("r3", "r4")], default="r3")
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    evidence = work / "evidence"
    evidence.mkdir()
    result = {"schema": 1, "kind": "independent-storage-final-cleanup-execution",
              "candidate": args.candidate, "passed": False, "executed": False,
              "workflowCommit": os.environ.get("GITHUB_SHA"), "failures": [],
              "independentExpectationInverted": False, "independentAcceptance": False,
              "started": datetime.now(timezone.utc).isoformat()}
    try:
        bundle = ROOT / ("verification/experimental-candidates/storage-" + args.candidate + "-2026-10-21")
        bundle_sha, candidate_sha, _ = PROFILES[args.candidate]
        assert binding(bundle / "bundle-index.json")["sha256"] == bundle_sha
        index = json.loads((bundle / "bundle-index.json").read_bytes())
        assert index["candidateIndexSha256"] == candidate_sha
        clone = work / "isolated-checkout"
        clone.mkdir()
        before = {}
        for target_name, item in index["files"].items():
            original = bundle / relative(item["bundleFile"])
            assert not original.is_symlink() and binding(original) == {key: item[key] for key in ("bytes", "sha256")}
            target = clone / relative(target_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            before[target_name] = binding(target)
        assert binding(INDEPENDENT / "candidate-index.json")["sha256"] == INDEX_SHA
        independent_index = json.loads((INDEPENDENT / "candidate-index.json").read_bytes())
        independent_path = clone / "artifacts/storage-r3-independent-draft"
        independent_path.mkdir()
        for name, expected in independent_index["files"].items():
            original = INDEPENDENT / relative(name)
            assert not original.is_symlink() and binding(original) == expected
            shutil.copyfile(original, independent_path / relative(name))
        shutil.copyfile(INDEPENDENT / "candidate-index.json", independent_path / "candidate-index.json")
        scratch = evidence / "scratch"
        scratch.mkdir()
        command = [sys.executable, "-B", str(independent_path / "counterexample.py"),
                   "--candidate", str(clone / ("artifacts/source-window-v3-archive-" + args.candidate + "-draft")),
                   "--expected-candidate-index", candidate_sha, "--work", str(evidence / "scenario")]
        with (evidence / "independent-process.log").open("xb") as stream:
            process = subprocess.run(command, cwd=clone, env=public_environment(scratch),
                                     stdout=stream, stderr=subprocess.STDOUT, timeout=300)
        result.update(executed=True, exitCode=process.returncode,
                      logBinding=binding(evidence / "independent-process.log"))
        actual_path = evidence / "scenario/test-receipt.json"
        actual = json.loads(actual_path.read_bytes())
        result["actualReceiptBinding"] = binding(actual_path)
        result["actualFilesystemExecution"] = actual["actualFilesystemExecution"]
        result["actualChecks"] = actual["checks"]
        result["sourceBindingsUnchanged"] = before == {name: binding(clone / relative(name)) for name in before}
        assert actual["tests"] == 1 and len(actual["checks"]) == 9
        assert actual["actualFilesystemExecution"] is True and actual["actualChildExitCode"] == 73
        assert actual["sourceBindingsUnchanged"] is True and result["sourceBindingsUnchanged"]
        assert actual["passed"] is True and process.returncode == 0
        result["passed"] = True
    except Exception as error:
        result["failures"].append({"class": type(error).__name__, "message": str(error)})
    finally:
        result["finished"] = datetime.now(timezone.utc).isoformat()
        with (evidence / "execution-receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
    print(json.dumps({"passed": result["passed"], "executed": result["executed"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
