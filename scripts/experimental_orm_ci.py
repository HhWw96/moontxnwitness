"""Build a frozen sourceSchema2 proof candidate in an isolated temporary tree."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE_BASELINE = "b6638ee56395a14284d1440a92a0d975c4ea4073f42ccab6d8d39e359d928096"
PROFILES = {
    "r1": ("orm-source2-2026-10-21", "3cc3bab0339703acb4f1237ae833d98def66d1aa5c7772c99d5690d864164390", 22, 24),
    "r2": ("orm-source2-r2-2026-10-21", "2ba6e9ad40c99999d3b5c214846b114ed7a646275e3fa8344924bb97d02d144f", 27, 24),
    "r3": ("orm-source2-r3-2026-10-21", "da4d4d06b1d46b7c9e12c648d0509812cbe1672c59d9767aaf106f744ce3f58d", 40, 25),
}


def binding(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def fingerprint(root):
    names = sorted(["moon.mod"] + [path.relative_to(root).as_posix()
                   for path in (root / "src").rglob("*")
                   if path.is_file() and (path.suffix == ".mbt" or path.name == "moon.pkg")])
    hashed = hashlib.sha256()
    for name in names:
        hashed.update(name.encode() + b"\0")
        hashed.update((root / name).read_bytes())
        hashed.update(b"\0")
    return hashed.hexdigest()


def relative(name):
    value = PurePosixPath(name)
    assert name and not value.is_absolute() and ".." not in value.parts
    assert "\\" not in name and ":" not in name
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--candidate", choices=tuple(PROFILES), default="r3")
    args = parser.parse_args()
    bundle_name, candidate_sha, candidate_files, new_units = PROFILES[args.candidate]
    bundle = ROOT / "verification/experimental-candidates" / bundle_name
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    output = work / "evidence"
    output.mkdir()
    receipt = {"schema": 1, "kind": "experimental-orm-source2-execution", "passed": False,
               "workflowCommit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
               "python": sys.version, "started": datetime.now(timezone.utc).isoformat(),
               "candidateIndexSha256": candidate_sha, "stages": [], "failures": [],
               "actualDatabaseExecution": False, "formalPerformanceMeasurement": False,
               "independentAcceptance": False, "stableApiChanged": False,
               "productionModelCoverageAccepted": False, "fullApplicationIntegration": False}
    try:
        assert fingerprint(ROOT) == SOURCE_BASELINE, "Unexpected production source baseline"
        receipt["baselineSourceSha256"] = SOURCE_BASELINE
        raw = (bundle / "candidate-manifest-static-v1.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == candidate_sha
        manifest = json.loads(raw)
        assert len(manifest["files"]) == candidate_files
        before = {}
        for item in manifest["files"]:
            original = bundle / relative(item["path"])
            assert not original.is_symlink()
            actual = binding(original)
            assert actual == {key: item[key] for key in ("bytes", "sha256")}
            before[item["path"]] = actual
        clone = work / "isolated-checkout"
        clone.mkdir()
        shutil.copytree(ROOT / "src", clone / "src")
        for name in ("moon.mod", "package.json"):
            shutil.copyfile(ROOT / name, clone / name)
        (clone / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/moon.mjs", clone / "scripts/moon.mjs")
        assert fingerprint(clone) == SOURCE_BASELINE
        overlays = {}
        for name, item in before.items():
            if name.endswith(".mbt"):
                target_name = ("src/capture_bridge/orm_source2.mbt" if name == "capture_bridge_source2.mbt"
                               else "src/" + PurePosixPath(name).name)
                target = clone / relative(target_name)
                assert not target.exists(), "Do not silently replace an existing source file"
                shutil.copyfile(bundle / relative(name), target)
                overlays[target_name] = binding(target)
        # The old diagnostic had these imports in its private build. Add them
        # explicitly in this clone; never mutate the production package file.
        (clone / "src/moon.pkg").write_text('import {\n  "moonbitlang/core/json",\n  "moonbitlang/core/encoding/base64",\n  "moonbitlang/core/encoding/utf8",\n}\n', encoding="utf-8", newline="\n")
        overlays["src/moon.pkg"] = binding(clone / "src/moon.pkg")
        receipt["overlays"] = overlays
        receipt["experimentalSourceSha256"] = fingerprint(clone)
        expected_count = 563 + 28 + new_units
        actual_count = sum(len(re.findall(r'^test\s+"', path.read_text(encoding="utf-8"), re.M))
                           for path in (clone / "src").rglob("*.mbt"))
        assert actual_count == expected_count
        receipt["declaredCoreTests"] = actual_count
        commands = [("fixed-template-AST", [sys.executable, "-B", str(bundle / "generate_control_templates.py"), "--check"]),
                    ("check-all", ["node", "scripts/moon.mjs", "check", "--target", "all", "--deny-warn", "--jobs", "1"])]
        commands.extend(("test-" + target, ["node", "scripts/moon.mjs", "test", "--target", target, "--deny-warn", "--jobs", "1"])
                        for target in ("js", "wasm-gc", "wasm", "native"))
        commands.extend([
            ("build-js", ["node", "scripts/moon.mjs", "build", "--target", "js", "--release", "--deny-warn", "--jobs", "1"]),
            ("raw-source-and-tamper", ["node", str(bundle / "check-source2.mjs"),
              str(clone / "_build/js/release/build/capture_bridge/capture_bridge.js"),
              str(bundle / "fixtures"), str(output / "source2-functional-first.json")])])
        receipt["stages"] = [{"name": name, "status": "not-executed"} for name, _ in commands]
        env = {key: value for key, value in os.environ.items()
               if not any(word in key.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "PRIVATE_KEY"))}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        for row, (_, command) in zip(receipt["stages"], commands):
            log = output / (row["name"] + ".log")
            row["status"] = "running"
            try:
                with log.open("xb") as stream:
                    result = subprocess.run(command, cwd=clone, env=env, stdout=stream,
                                            stderr=subprocess.STDOUT, timeout=900)
            except Exception as error:
                row.update(status="failed", errorClass=type(error).__name__)
                raise
            finally:
                if log.exists():
                    row.update(log=log.name, logBinding=binding(log))
            row.update(exitCode=result.returncode)
            row["status"] = "passed" if result.returncode == 0 else "failed"
            if result.returncode:
                raise RuntimeError("Experimental stage failed: " + row["name"])
            if row["name"].startswith("test-"):
                text = log.read_text(encoding="utf-8", errors="replace")
                assert f"Total tests: {expected_count}, passed: {expected_count}, failed: 0." in text
                row["actualCoreTestsPassed"] = expected_count
        actual = json.loads((output / "source2-functional-first.json").read_bytes())
        assert actual["passed"] and len(actual["checks"]) == 74
        receipt["rawSourceFunctionalChecks"] = len(actual["checks"])
        runtime = clone / "_build/js/release/build/capture_bridge/capture_bridge.js"
        shutil.copyfile(runtime, output / "experimental-capture-core.mjs")
        receipt["actualRuntimeBinding"] = binding(output / "experimental-capture-core.mjs")
        receipt["sourceBindingsUnchanged"] = (before == {name: binding(bundle / relative(name)) for name in before}
                                               and fingerprint(clone) == receipt["experimentalSourceSha256"])
        assert receipt["sourceBindingsUnchanged"]
        receipt["passed"] = True
    except Exception as error:
        receipt["failures"].append({"class": type(error).__name__, "message": str(error)})
    finally:
        receipt["finished"] = datetime.now(timezone.utc).isoformat()
        with (output / "execution-receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "receipt": str(output / "execution-receipt.json")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
