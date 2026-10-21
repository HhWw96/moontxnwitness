"""Restore frozen r4 bytes and execute the independent protected-sync audit."""
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

INDEPENDENT = ROOT / "verification/experimental-candidates/storage-independent-r4-2026-10-21"
INDEX_SHA = "33636dba9e1a3bb4c3f26a50c7f47b79db7d15185a4fddab8f2a27cea228a6f6"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    evidence = work / "evidence"
    evidence.mkdir()
    result = {"schema": 1, "kind": "independent-storage-r4-protected-sync-execution",
              "passed": False, "executed": False, "workflowCommit": os.environ.get("GITHUB_SHA"),
              "failures": [], "independentExpectationChanged": False, "stableAcceptance": False,
              "started": datetime.now(timezone.utc).isoformat()}
    try:
        bundle = ROOT / "verification/experimental-candidates/storage-r4-2026-10-21"
        bundle_sha, candidate_sha, _ = PROFILES["r4"]
        assert binding(bundle / "bundle-index.json")["sha256"] == bundle_sha
        index = json.loads((bundle / "bundle-index.json").read_bytes())
        assert index["candidateIndexSha256"] == candidate_sha
        clone = work / "isolated-checkout"
        clone.mkdir()
        # The independent locator requires the real module marker as well as
        # integrations/python. The frozen author bundle deliberately omits it.
        shutil.copyfile(ROOT / "moon.mod", clone / "moon.mod")
        before = {"moon.mod": binding(clone / "moon.mod")}
        for name, item in index["files"].items():
            original = bundle / relative(item["bundleFile"])
            assert not original.is_symlink() and binding(original) == {key: item[key] for key in ("bytes", "sha256")}
            target = clone / relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with original.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, 65536)
            before[name] = binding(target)
        assert binding(INDEPENDENT / "candidate-index.json")["sha256"] == INDEX_SHA
        independent_index = json.loads((INDEPENDENT / "candidate-index.json").read_bytes())
        independent_path = clone / "artifacts/storage-r4-independent-draft"
        independent_path.mkdir()
        independent_before = {}
        for item in independent_index["files"]:
            name = item["file"]
            original = INDEPENDENT / relative(name)
            expected = {key: item[key] for key in ("bytes", "sha256")}
            assert not original.is_symlink() and binding(original) == expected
            target = independent_path / relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with original.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, 65536)
            independent_before[name] = binding(target)
        shutil.copyfile(INDEPENDENT / "candidate-index.json", independent_path / "candidate-index.json")
        scratch = evidence / "scratch"
        scratch.mkdir()
        command = [sys.executable, "-B", str(independent_path / "counterexample.py"),
                   "--candidate", str(clone / "artifacts/source-window-v3-archive-r4-draft"),
                   "--work", str(evidence / "scenario")]
        with (evidence / "independent-process.log").open("xb") as stream:
            process = subprocess.run(command, cwd=clone, env=public_environment(scratch),
                                     stdout=stream, stderr=subprocess.STDOUT, timeout=300)
        result.update(executed=True, exitCode=process.returncode,
                      logBinding=binding(evidence / "independent-process.log"))
        actual_path = evidence / "scenario/independent-r4-receipt.json"
        actual = json.loads(actual_path.read_bytes())
        result.update(actualReceiptBinding=binding(actual_path),
                      actualFilesystemExecution=actual["actualFilesystemExecution"],
                      checksCount=actual["checksCount"],
                      oldR3FaultTarget=actual["oldR3FaultTarget"],
                      postCommitNativeAllDiagnosticIOFailure=actual["postCommitNativeAllDiagnosticIOFailure"],
                      sourceBindingsUnchanged=before == {name: binding(clone / relative(name)) for name in before},
                      independentBindingsUnchanged=independent_before == {
                          name: binding(independent_path / relative(name)) for name in independent_before})
        assert actual["complete"] is True and len(actual["cases"]) == 2 and actual["checksCount"] == 24
        assert actual["actualFilesystemExecution"] is True
        assert result["sourceBindingsUnchanged"] and result["independentBindingsUnchanged"]
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
