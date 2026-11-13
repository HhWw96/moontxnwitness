"""Execute the pinned Elle source in an isolated Linux/JDK21 environment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ELLE_COMMIT = "4e359e597c52938b0afebb8bc42273914d68a424"
LEIN_VERSION = "2.11.2"
LEIN_SHA = "f83e3de252cb09d301f18f1912acffa807b54c1c9a96772ae63847a946032bd4"
LEIN_LICENSE_SHA = "721fc8dd7fb2419c5360287b591b918084f350cd17d71130a942bc0f81546ea3"
LEIN_JAR_SHA = "7d31ae23ae769e927438b0cd55d15a93e7dabab09fd4fc15877979161e108774"
PINS = {
    "project.clj": "d4608919c02b20de53cb017467e54c4b8267c4f146619a612a1a585f42f7c89f",
    "LICENSE": "721c2da257578bace3332b14d8ea06643d7d26753e7ef25a837b4e904edc0bf5",
    "src/elle/graph.clj": "9cbe589d740593671cd02ee48300a929b9bb863ffe4da506b906eebbb222ea3f",
    "src/elle/core.clj": "396fcbd5683787366f3bf111f512aa4f7976e0d48414f8939e3e71edeeddff98",
    "src/elle/rw_register.clj": "9ad17da5b86e6e25fe66b77e0deab9000265901a1bedd5045dbba98c7dddd1ce",
    "src/elle/list_append.clj": "f4bfeee8afef994e662a4f5e2d36219ddd714254a9590f6bc36ca0b52bf3d2e7",
    "src/elle/txn.clj": "8c3c87062d518cc7ba9cee49408fe552e8057a59e5b2068f4f8aa0bf6421a5a6",
    "src/elle/consistency_model.clj": "f909f517351081001054bef461fcdec709f6bd2d2c058955777e68033d4fb10b",
}


def binding(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
            size += len(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def download(url: str, path: Path, expected: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "MoonTxnWitness-fixed-Elle-runner"})
    with urllib.request.urlopen(request, timeout=60) as response, path.open("xb") as target:
        shutil.copyfileobj(response, target)
    actual = binding(path)
    if actual["sha256"] != expected:
        raise ValueError("Pinned download differs: " + path.name)
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requests = args.requests.resolve(strict=True)
    if requests.is_symlink() or not requests.is_file() or requests.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Requests must be a regular file of at most 32 MiB")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    logs = output / "logs"
    logs.mkdir()
    licenses = output / "licenses"
    licenses.mkdir()
    shutil.copyfile(requests, output / "requests.edn")
    request_binding = binding(requests)
    checker = Path(__file__).with_name("upstream.clj").resolve(strict=True)
    checker_binding = binding(checker)
    record = {"format": "moontxnwitness-actual-fixed-elle-execution/v1", "passed": False,
              "fixedElleCommit": ELLE_COMMIT, "jdkMajor": 21, "leinVersion": LEIN_VERSION,
              "clojureVersion": "1.12.6", "workflowCommit": os.environ.get("GITHUB_SHA"),
              "startedAt": datetime.now(timezone.utc).isoformat(), "stages": [],
              "requests": request_binding, "checker": checker_binding,
              "formalPerformanceMeasurement": False, "actualDatabaseExecution": False}
    (output / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    parent = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    work = Path(tempfile.mkdtemp(prefix="mtw-fixed-elle-", dir=parent))
    hidden = ("TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "PRIVATE_KEY")
    env = {k: v for k, v in os.environ.items() if not any(part in k.upper() for part in hidden)}
    env.pop("PYTHONPATH", None)
    home = work / "home"
    home.mkdir()
    java = Path(env.get("JAVA_HOME_21_X64") or env.get("JAVA_HOME") or "")
    env.update(HOME=str(home), LEIN_HOME=str(work / "lein-home"),
               JAVA_HOME=str(java), PATH=str(java / "bin") + os.pathsep + env.get("PATH", ""),
               LEIN_JVM_OPTS=f"-Xmx2048m -Duser.home={home} -Djava.io.tmpdir={work}",
               JVM_OPTS=f"-Xmx2048m -Duser.home={home} -Djava.io.tmpdir={work}",
               PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

    def stage(name, command, cwd=work, timeout=300, tolerate_failure=False):
        row = {"name": name, "timeoutSeconds": timeout, "status": "running"}
        record["stages"].append(row)
        log = logs / (name + ".log")
        try:
            with log.open("xb") as stream:
                result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=timeout)
            row.update(exitCode=result.returncode, status="passed" if result.returncode == 0 else "failed")
        except Exception as error:
            row.update(status="failed", errorClass=type(error).__name__, error=str(error))
            raise
        finally:
            if log.exists():
                row.update(log="logs/" + log.name, logBinding=binding(log))
            (output / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
        if result.returncode and not tolerate_failure:
            raise RuntimeError("Actual upstream stage failed: " + name)
        return result.returncode

    try:
        if os.name != "posix":
            raise RuntimeError("Actual fixed upstream execution requires the isolated Linux workflow")
        stage("java-version", ["java", "-version"])
        if not re.search(r'(?:openjdk|java) version "21(?:\.|\")', (logs / "java-version.log").read_text("utf8")):
            raise RuntimeError("An actual JDK21 runtime is required")
        upstream = work / "elle"
        stage("git-init", ["git", "init", str(upstream)])
        stage("git-remote", ["git", "remote", "add", "origin", "https://github.com/jepsen-io/elle"], upstream)
        stage("git-fetch", ["git", "fetch", "--depth", "1", "origin", ELLE_COMMIT], upstream)
        stage("git-checkout", ["git", "checkout", "--detach", "FETCH_HEAD"], upstream)
        stage("git-identify", ["git", "rev-parse", "HEAD"], upstream)
        if (logs / "git-identify.log").read_text("utf8").strip() != ELLE_COMMIT:
            raise ValueError("Actual upstream commit differs")
        actual_sources = {}
        for name, expected in PINS.items():
            path = upstream / name
            if path.is_symlink() or binding(path)["sha256"] != expected:
                raise ValueError("Actual upstream source differs: " + name)
            actual_sources[name] = binding(path)
        record["actualSources"] = actual_sources
        (output / "source-bindings.json").write_text(json.dumps(actual_sources, indent=2) + "\n", encoding="utf8")
        shutil.copyfile(upstream / "LICENSE", licenses / "ELLE-LICENSE")
        launcher = work / "lein"
        record["leinLauncher"] = download(
            "https://raw.githubusercontent.com/technomancy/leiningen/2.11.2/bin/lein", launcher, LEIN_SHA)
        record["leinLicense"] = download(
            "https://raw.githubusercontent.com/technomancy/leiningen/2.11.2/COPYING",
            licenses / "LEININGEN-COPYING", LEIN_LICENSE_SHA)
        stage("lein-version", ["bash", str(launcher), "with-profile", "+dev", "version"], upstream)
        jar = Path(env["LEIN_HOME"]) / "self-installs" / f"leiningen-{LEIN_VERSION}-standalone.jar"
        if binding(jar)["sha256"] != LEIN_JAR_SHA:
            raise ValueError("Actual Leiningen standalone differs")
        record["leinStandalone"] = binding(jar)
        stage("dependency-tree", ["bash", str(launcher), "with-profile", "+dev", "deps", ":tree"], upstream, 900)
        xvfb = shutil.which("xvfb-run", path=env["PATH"])
        if not xvfb:
            raise RuntimeError("The fixed upstream AWT initialization requires Xvfb")
        record["xvfb"] = binding(Path(xvfb))
        exit_code = stage("actual-model-checkers", [xvfb, "-a", "-e", str(logs / "xvfb.log"),
                          "bash", str(launcher), "with-profile", "+dev", "run", "-m", "clojure.main",
                          str(checker), str(requests), str(output)], upstream, 1200, True)
        deps = home / ".m2" / "repository"
        inventory = {p.relative_to(deps).as_posix(): binding(p) for p in sorted(deps.rglob("*.jar"))}
        if "org/clojure/clojure/1.12.6/clojure-1.12.6.jar" not in inventory:
            raise RuntimeError("The fixed Clojure runtime was not actually resolved")
        (output / "dependency-bindings.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf8")
        result = json.loads((output / "results.json").read_text("utf8"))
        if (result["fixedElleCommit"] != ELLE_COMMIT
                or result["requestsSha256"] != request_binding["sha256"]
                or result["requestCount"] != len(result["results"])):
            raise ValueError("Upstream result envelope differs")
        record.update(requestCount=result["requestCount"], executionErrors=result["executionErrors"],
                      timeouts=result["timeouts"], resultBinding=binding(output / "results.json"))
        record["passed"] = exit_code == 0 and result["passed"] is True
        stage("upstream-source-status", ["git", "status", "--porcelain"], upstream)
        if (logs / "upstream-source-status.log").read_text("utf8").strip():
            raise RuntimeError("Tracked upstream source changed during execution")
    except Exception as error:
        record.update(passed=False, error={"class": type(error).__name__, "message": str(error)})
    finally:
        if binding(requests) != request_binding or binding(checker) != checker_binding:
            record.update(passed=False, inputChanged=True)
        record["finishedAt"] = datetime.now(timezone.utc).isoformat()
        (output / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"passed": record["passed"], "fixedElleCommit": ELLE_COMMIT,
                      "requestCount": record.get("requestCount"), "executionErrors": record.get("executionErrors"),
                      "timeouts": record.get("timeouts"), "error": record.get("error")}))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
