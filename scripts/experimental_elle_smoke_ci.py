"""First real upstream Elle smoke: frozen inputs, isolated runtime, original failures."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from experimental_orm_ci import ROOT, SOURCE_BASELINE, fingerprint, relative

BUNDLE = ROOT / "verification/experimental-candidates/elle-smoke-r2-2026-10-21"
INDEX_FILE = "candidate-index-static-v2.json"
INDEX_SHA = "79181c62e4499b14a420810758d68c31df70d93bd3f950692f71c9b1ca0acf80"
ELLE_SHA = "4e359e597c52938b0afebb8bc42273914d68a424"


def binding(path):
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
            count += len(block)
    return {"bytes": count, "sha256": digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    evidence = work / "evidence"
    evidence.mkdir()
    result = {"schema": 1, "kind": "actual-fixed-Elle-first-smoke-execution", "passed": False,
              "workflowCommit": os.environ.get("GITHUB_SHA"), "fixedElleCommit": ELLE_SHA,
              "started": datetime.now(timezone.utc).isoformat(), "stages": [], "failures": [],
              "formalPerformanceMeasurement": False, "actualDatabaseExecution": False,
              "independentAcceptance": False, "sixModelParity": False, "stableAcceptance": False}
    private = ("TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "PRIVATE_KEY")
    env = {key: value for key, value in os.environ.items() if not any(word in key.upper() for word in private)}
    env.pop("PYTHONPATH", None)
    owned_home = work / "runtime-home"
    owned_home.mkdir()
    jvm_temp = evidence / "jvm-temp"
    jvm_temp.mkdir()
    env.update(LEIN_HOME=str(work / "lein-home"), HOME=str(owned_home),
               LEIN_JVM_OPTS=f"-Xmx1024m -Duser.home={owned_home} -Djava.io.tmpdir={jvm_temp}",
               JVM_OPTS=f"-Xmx1024m -Duser.home={owned_home} -Djava.io.tmpdir={jvm_temp}",
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    # Retain the installed pinned MoonBit location after isolating the Java HOME.
    env["MOON_HOME"] = str(Path(os.environ["HOME"]) / ".moon")
    before = {}

    def stage(name, command, cwd, timeout=300, tolerate_failure=False):
        row = {"name": name, "status": "running", "timeoutSeconds": timeout}
        result["stages"].append(row)
        log = evidence / (name + ".log")
        try:
            with log.open("xb") as stream:
                process = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=timeout)
            row.update(exitCode=process.returncode, status="passed" if process.returncode == 0 else "failed")
        except Exception as error:
            row.update(status="failed", errorClass=type(error).__name__, error=str(error))
            raise
        finally:
            if log.exists():
                row.update(log=log.name, logBinding=binding(log))
        if process.returncode and not tolerate_failure:
            raise RuntimeError("Actual stage failed: " + name)
        return process.returncode

    try:
        java = Path(env["JAVA_HOME_21_X64"])
        env.update(JAVA_HOME=str(java), PATH=str(java / "bin") + os.pathsep + env["PATH"])
        assert fingerprint(ROOT) == SOURCE_BASELINE
        assert binding(BUNDLE / INDEX_FILE)["sha256"] == INDEX_SHA
        index = json.loads((BUNDLE / INDEX_FILE).read_bytes())
        assert index["fileCount"] == 39 and len(index["files"]) == 39
        for name, expected in index["files"].items():
            path = BUNDLE / relative(name)
            assert not path.is_symlink() and binding(path) == expected, name
            before[name] = binding(path)
        result.update(sourceSha256=SOURCE_BASELINE, candidateIndexSha256=INDEX_SHA,
                      candidateFiles=before)
        stage("adapter-identity-boundaries", [sys.executable, "-B", str(BUNDLE / "identity-boundary-check.py"),
              "--output", str(evidence / "identity-boundaries.json")], ROOT)
        boundaries = json.loads((evidence / "identity-boundaries.json").read_bytes())
        assert boundaries["passed"] and boundaries["checks"] == 69
        stage("prepare-original-facts", [sys.executable, "-B", str(BUNDLE / "prepare.py"),
              "--input", str(BUNDLE / "smoke-inputs-v1.json"), "--output", str(evidence / "prepared")], ROOT)
        adapter = json.loads((evidence / "prepared/adapter-receipt.json").read_bytes())
        assert adapter["passed"] and len(adapter["cases"]) == 15
        assert {kind: sum(row["disposition"] == kind for row in adapter["cases"])
                for kind in ("eligible", "outside", "invalid")} == {"eligible": 8, "outside": 5, "invalid": 2}
        shutil.copyfile(BUNDLE / "smoke-inputs-v1.json", evidence / "original-inputs.json")
        stage("clone-upstream", ["git", "clone", "--filter=blob:none", "--no-checkout",
              "https://github.com/jepsen-io/elle", str(work / "elle")], work)
        upstream = work / "elle"
        stage("fetch-fixed-upstream", ["git", "fetch", "--depth", "1", "origin", ELLE_SHA], upstream)
        stage("checkout-fixed-upstream", ["git", "checkout", "--detach", ELLE_SHA], upstream)
        stage("identify-fixed-upstream", ["git", "rev-parse", "HEAD"], upstream)
        assert (evidence / "identify-fixed-upstream.log").read_text().strip() == ELLE_SHA
        pins = json.loads((BUNDLE / "source-pins.json").read_bytes())
        actual_sources = {}
        for name, expected in pins["files"].items():
            path = upstream / relative(name)
            assert not path.is_symlink() and binding(path) == expected, name
            actual_sources[name] = binding(path)
        result["actualUpstreamSources"] = actual_sources
        shutil.copyfile(upstream / "LICENSE", evidence / "ELLE-UPSTREAM-LICENSE")
        shutil.copyfile(BUNDLE / "primary-references/LEININGEN-COPYING", evidence / "LEININGEN-UPSTREAM-COPYING")
        launcher = BUNDLE / "primary-references/lein"
        stage("actual-java-version", ["java", "-version"], upstream)
        stage("actual-lein-version", ["bash", str(launcher), "version"], upstream)
        standalone = Path(env["LEIN_HOME"]) / "self-installs/leiningen-2.11.2-standalone.jar"
        assert binding(standalone)["sha256"] == "7d31ae23ae769e927438b0cd55d15a93e7dabab09fd4fc15877979161e108774"
        result["actualLeinStandaloneBinding"] = binding(standalone)
        stage("actual-dependency-tree", ["bash", str(launcher), "with-profile", "-dev", "deps", ":tree"], upstream, 600)
        xvfb = shutil.which("xvfb-run", path=env["PATH"])
        if not xvfb:
            raise RuntimeError("Missing Xvfb required by the fixed upstream's AWT initialization")
        result["actualXvfbLauncher"] = binding(Path(xvfb))
        # A failed checker still leaves its full result available for the comparison.
        stage("actual-elle-checkers", [xvfb, "-a", "-e", str(evidence / "xvfb.log"),
              "bash", str(launcher), "with-profile", "-dev", "run", "-m", "clojure.main",
              str(BUNDLE / "elle_smoke.clj"), str(evidence / "prepared/requests.edn"),
              str(evidence / "elle-result.json"), str(evidence / "elle-raw-results")], upstream, 300, True)
        stage("build-current-sdk", ["node", "scripts/build.mjs"], ROOT, 600)
        runtime = evidence / "actual-sdk"
        runtime.mkdir()
        for name in ("sdk.mjs", "evidence.mjs", "core.mjs", "capture-core.mjs", "build-manifest.json", "THIRD_PARTY_NOTICES.txt"):
            shutil.copyfile(ROOT / "dist" / name, runtime / name)
        result["actualSdkBindings"] = {path.name: binding(path) for path in runtime.iterdir() if path.is_file()}
        stage("compare-actual-tools", ["node", str(BUNDLE / "compare-tool.mjs"), str(runtime / "sdk.mjs"),
              str(BUNDLE / "smoke-inputs-v1.json"), str(evidence / "prepared/adapter-receipt.json"),
              str(evidence / "elle-result.json"), str(evidence / "comparison-first.json")], ROOT, 300)
        actual = json.loads((evidence / "comparison-first.json").read_bytes())
        result["actualComparisonBinding"] = binding(evidence / "comparison-first.json")
        assert actual["passed"] and actual["actualDualCheckerCases"] == 8 and len(actual["cases"]) == 15
        assert actual["actualBuildManifest"]["sourceSha256"] == SOURCE_BASELINE
        assert all(row["status"] == "passed" for row in result["stages"])
        result["passed"] = True
    except Exception as error:
        result["failures"].append({"class": type(error).__name__, "message": str(error)})
    finally:
        roots = [work / "lein-home", owned_home / ".m2"]
        dependencies = {}
        for base in roots:
            if not base.exists():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file() and path.suffix in (".jar", ".pom"):
                    dependencies[path.relative_to(work).as_posix()] = binding(path)
        result["actualRuntimeDependencyBindings"] = dependencies
        if result["passed"] and not any(name.endswith("/org/clojure/clojure/1.12.6/clojure-1.12.6.jar")
                                        for name in dependencies):
            result["passed"] = False
            result["failures"].append({"class": "MissingDependencyBinding", "message": "Actual pinned Clojure JAR was not found in the new isolated runtime home"})
        result["sourceBindingsUnchanged"] = bool(before) and before == {
            name: binding(BUNDLE / relative(name)) for name in before} and fingerprint(ROOT) == SOURCE_BASELINE
        result["passed"] = result["passed"] and result["sourceBindingsUnchanged"]
        result["finished"] = datetime.now(timezone.utc).isoformat()
        with (evidence / "execution-receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
    print(json.dumps({"passed": result["passed"], "stages": len(result["stages"])}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
