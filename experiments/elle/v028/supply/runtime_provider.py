"""Opt-in Linux runtime supply; prepares no checker inputs and runs no checker."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import sys

ELLE = "4e359e597c52938b0afebb8bc42273914d68a424"
INDEX = "79181c62e4499b14a420810758d68c31df70d93bd3f950692f71c9b1ca0acf80"
OLD_EXECUTION = "27a941374d6fe8ced62ad084a5812b7dadbb84c6997e41b6756e4273d272b5cb"
CORE = "4f9a73a5fe82478d913cb751ab68714d4ba0558c85b45a3933c6eb9a6c3078ef"
STANDALONE = "7d31ae23ae769e927438b0cd55d15a93e7dabab09fd4fc15877979161e108774"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def binding(path):
    size, digest = 0, hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(65536):
            size += len(block)
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def pinned(path, digest, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Pinned regular bounded file required")
    raw = path.read_bytes()
    if len(raw) > limit or sha(raw) != digest:
        raise ValueError("Frozen input SHA differs")
    return raw


def write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def compare_dependencies(actual, expected):
    return {"missing": sorted(set(expected) - set(actual)),
            "extra": sorted(set(actual) - set(expected)),
            "changed": sorted(name for name in set(actual) & set(expected)
                              if actual[name] != expected[name])}


def tree(path):
    files = {}
    for p in sorted(Path(path).rglob("*")):
        if p.is_symlink():
            raise ValueError("Symlink in frozen runtime closure")
        if p.is_file():
            files[p.relative_to(path).as_posix()] = binding(p)
    return files


def classpath_entries(raw, upstream, work, create_empty=False):
    text = raw.decode("utf-8").strip()
    if not text or "\n" in text or "\r" in text:
        raise ValueError("One original classpath stdout line required")
    entries, created = [], []
    for name in text.split(os.pathsep):
        p = Path(name)
        if not p.is_absolute() or p.is_symlink() or not p.resolve().is_relative_to(work):
            raise ValueError("Classpath must remain in fresh owned runtime")
        if not p.exists():
            if not create_empty or p not in (upstream / "resources", upstream / "dev-resources"):
                raise ValueError("Unresolved classpath entry")
            p.mkdir(exist_ok=False)
            created.append(str(p))
        if p.is_file():
            entries.append(dict(path=str(p), **binding(p)))
        elif p.is_dir():
            entries.append({"path": str(p), "files": tree(p)})
        else:
            raise ValueError("Unsupported classpath entry")
    return entries, created


def prepare(args, ownership):
    if os.name != "posix":
        raise RuntimeError("Linux runtime supply only")
    core_raw = pinned(args.controller, CORE, 1024 * 1024)
    core = {"__name__": "verified_r4_runtime_supply", "__file__": args.controller,
            "__verified_source_sha256__": CORE}
    exec(compile(core_raw, args.controller, "exec"), core)
    project = Path(args.project_root).resolve()
    bundle = project / "verification/experimental-candidates/elle-smoke-r2-2026-10-21"
    old = json.loads(pinned(bundle / "actual-ci-39599513353/actual/execution-receipt.json",
                            OLD_EXECUTION, 1024 * 1024))
    static = json.loads(pinned(bundle / "candidate-index-static-v2.json", INDEX, 1024 * 1024))
    def bundle_file(name):
        expected = static["files"][name]
        raw = pinned(bundle / name, expected["sha256"], expected["bytes"])
        if len(raw) != expected["bytes"]:
            raise ValueError("Original source artifact size differs")
        return raw
    source_pins = json.loads(bundle_file("source-pins.json"))
    launcher_raw = bundle_file("primary-references/lein")
    work = Path(args.work).absolute()
    if work.resolve() != work or work.is_symlink() or work.exists():
        raise ValueError("Fresh literal owned Linux runtime root required")
    gate = core["linux_resources"](work.parent)
    if not gate["passed"]:
        raise RuntimeError("Runtime preparation resource gate failed: " + json.dumps(gate))
    work.mkdir(exist_ok=False)
    ownership["newWork"] = work
    for name in ("evidence", "runtime-home", "lein-home", "tmp"):
        (work / name).mkdir()
    java_home = Path(os.environ["JAVA_HOME_21_X64"]).resolve()
    java = (java_home / "bin/java").resolve()
    javac = (java_home / "bin/javac").resolve()
    xvfb_name, xserver_name, xauth_name = (shutil.which(n) for n in ("xvfb-run", "Xvfb", "xauth"))
    if not all((java.is_file(), javac.is_file(), xvfb_name, xserver_name, xauth_name)):
        raise RuntimeError("Actual Java21/Javac/Xvfb/xauth prerequisites missing")
    xvfb, xserver, xauth = (Path(n).resolve() for n in (xvfb_name, xserver_name, xauth_name))
    private = ("TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "PRIVATE_KEY")
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in private)}
    for key in ("CLASSPATH", "PYTHONPATH", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
        env.pop(key, None)
    env.update(JAVA_HOME=str(java_home), PATH=str(java_home / "bin") + os.pathsep + env["PATH"],
               HOME=str(work / "runtime-home"), LEIN_HOME=str(work / "lein-home"),
               LEIN_JVM_OPTS="-Xmx1024m -Djava.io.tmpdir=" + str(work / "tmp"),
               JVM_OPTS="-Xmx1024m -Djava.io.tmpdir=" + str(work / "tmp"),
               TMPDIR=str(work / "tmp"), TMP=str(work / "tmp"), TEMP=str(work / "tmp"),
               GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=str(work / "empty-gitconfig"))
    (work / "empty-gitconfig").write_bytes(b"")
    (work / "lein").write_bytes(launcher_raw)
    receipt = {"schema": 1, "kind": "actual-runtime-only-supply", "passed": False,
               "startedUtc": datetime.now(timezone.utc).isoformat(),
               "fixedElleCommit": ELLE, "historicalReferenceReceiptSha256": OLD_EXECUTION,
               "actualCheckerInputs": 0, "actualSDKExecuted": False,
               "sourceInputGeneratedOrChanged": False, "automaticRetry": False,
               "resourceGate": gate, "stages": [], "sourceControllerSha256": CORE,
               "runtimeManifestExternallyApproved": False}
    def stage(name, argv, cwd, timeout=300):
        out = work / "evidence" / name
        out.mkdir()
        before_gate = core["linux_resources"](work)
        if not before_gate["passed"]:
            raise RuntimeError("Runtime stage resource stop before " + name)
        process = core["run_process"](argv, cwd, env, b"", out, timeout=timeout)
        write(out / "process.json", process)
        receipt["stages"].append({"name": name, "process": process, "beforeResourceGate": before_gate,
                                   "afterResourceGate": core["linux_resources"](work)})
        if (process["exitCode"] != 0 or process["stopReason"] is not None
                or process["controllerErrors"] or process["rawStreamsMayBeTruncated"]):
            raise RuntimeError("First runtime stage failed: " + name)
        return (out / "stdout.raw").read_bytes(), out
    try:
        _, java_log = stage("java-version", [str(java), "-version"], work)
        java_text = (java_log / "stderr.raw").read_text() + (java_log / "stdout.raw").read_text()
        if 'version "21.' not in java_text:
            raise ValueError("Actual Java major21 required")
        upstream = work / "upstream"
        git = shutil.which("git")
        bash = shutil.which("bash")
        if not git or not bash:
            raise RuntimeError("Git/bash unavailable")
        git_prefix = [git, "-c", "credential.helper="]
        stage("clone-fixed-elle", git_prefix + ["clone", "--filter=blob:none", "--no-checkout",
              "https://github.com/jepsen-io/elle", str(upstream)], work)
        stage("fetch-fixed-elle", git_prefix + ["fetch", "--depth", "1", "origin", ELLE], upstream)
        stage("checkout-fixed-elle", git_prefix + ["checkout", "--detach", ELLE], upstream)
        head, _ = stage("identify-fixed-elle", git_prefix + ["rev-parse", "HEAD"], upstream)
        if head.decode().strip() != ELLE:
            raise ValueError("Actual fixed Elle checkout differs")
        for name, expected in source_pins["files"].items():
            if binding(upstream / name) != expected:
                raise ValueError("Actual upstream raw source differs: " + name)
        tracked, _ = stage("tracked-source-files", git_prefix + ["ls-files", "-z"], upstream)
        source_before = {}
        for raw_name in tracked.split(b"\0"):
            if not raw_name:
                continue
            name = raw_name.decode("utf-8")
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe tracked source path")
            source_before[name] = binding(upstream / relative)
        lein = [bash, str(work / "lein"), "with-profile", "+dev"]
        stage("lein-version", lein + ["version"], upstream)
        standalone = work / "lein-home/self-installs/leiningen-2.11.2-standalone.jar"
        if binding(standalone)["sha256"] != STANDALONE:
            raise ValueError("Original pinned Lein standalone differs")
        stage("dependencies", lein + ["deps", ":tree"], upstream, 900)
        # The original lein run invokes Java preparation. Direct java needs this
        # explicit equivalent step and frozen target/classes before classpath use.
        stage("javac-release21", lein + ["javac"], upstream, 600)
        cp_raw, cp_out = stage("effective-classpath", lein + ["classpath"], upstream)
        effective, created = classpath_entries(cp_raw, upstream, work, create_empty=True)
        actual_dependencies = {}
        for sub in ("lein-home", "runtime-home/.m2"):
            for p in sorted((work / sub).rglob("*")):
                if p.is_file() and p.suffix in (".jar", ".pom"):
                    actual_dependencies[p.relative_to(work).as_posix()] = binding(p)
        differences = compare_dependencies(actual_dependencies, old["actualRuntimeDependencyBindings"])
        receipt["dependencyDifferences"] = differences
        receipt["actualRuntimeDependencyBindings"] = actual_dependencies
        if any(differences.values()):
            raise ValueError("Actual dependency bytes differ from original141; amendment/review required")
        if source_before != {name: binding(upstream / name) for name in source_before}:
            raise ValueError("Actual tracked upstream source changed during runtime preparation")
        receipt["actualTrackedSourceClosure"] = source_before
        provenance = {"schema":1, "fixedElleCommit":ELLE, "exitCode":0,
                      "argvSuffix":["with-profile","+dev","classpath"],
                      "effectiveClasspath":[entry["path"] for entry in effective],
                      "stdout":{"path":str(cp_out / "stdout.raw"), **binding(cp_out / "stdout.raw")},
                      "process":{"path":str(cp_out / "process.json"), **binding(cp_out / "process.json")}}
        write(work / "classpath-provenance.json", provenance)
        runtime = {"schema":1, "kind":"actual-prepared-runtime-awaiting-independent-admission",
                   "fixedElleCommit":ELLE, "java":21, "clojure":"1.12.6",
                   "leinProfile":"+dev", "additionalGraphs":[],
                   "classpathFromActualLein":True, "classpath":effective,
                   "javaExecutable":{"path":str(java), **binding(java)},
                   "xvfbExecutable":{"path":str(xvfb), **binding(xvfb)},
                   "leinClasspathProvenance":{"path":str(work / "classpath-provenance.json"),
                                               **binding(work / "classpath-provenance.json")},
                   "upstreamRoot":str(upstream),
                   "auxiliaryExecutableBindings":{str(p):binding(p) for p in (javac,xserver,xauth,Path(bash),Path(git))},
                   "original141DependencyBindings":actual_dependencies,
                   "actualJavaVersionText":java_text,
                   "referenceJavaVersionText":'Temurin21.0.12.1+1; compare actual log before admission',
                   "materializedEmptyResourceDirectories":created,
                   "actualCheckerInputs":0, "runtimeIndependentlyApproved":False}
        # Recheck via the exact frozen r4 validator. Still no checker invocation.
        runtime_raw = (json.dumps(runtime, sort_keys=True, indent=2) + "\n").encode()
        core["validate_runtime"](runtime_raw)
        write(work / "runtime-manifest.json", runtime)
        receipt.update(passed=True, actualRuntimeManifest=binding(work / "runtime-manifest.json"),
                       actualCompiledClasses=tree(upstream / "target/classes"),
                       allClasspathInputsBound=True, actualJavaVersionText=java_text)
    except Exception as error:
        receipt["firstFailure"] = {"class":type(error).__name__, "message":str(error)}
    finally:
        receipt["finishedUtc"] = datetime.now(timezone.utc).isoformat()
        write(work / "runtime-supply-receipt.json", receipt)
        files = tree(work)
        write(work / "RUNTIME-ARTIFACT-INDEX.json", {"schema":1, "files":files,
              "sourceRuntimeReceipt":binding(work / "runtime-supply-receipt.json"),
              "actualCheckerInputs":0, "sourceRoot":str(work),
              "restoreRequiresSameLiteralRootAndExternallyPinnedIndex":True,
              "runtimePassed":receipt["passed"]})
    return 0 if receipt["passed"] else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepare-runtime", action="store_true")
    p.add_argument("--allow-network-provisioning", action="store_true")
    for name in ("project-root", "controller", "work"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    if not a.prepare_runtime or not a.allow_network_provisioning:
        p.error("Explicit runtime-only execution and network-provisioning flags required")
    ownership = {}
    try:
        return prepare(a, ownership)
    except Exception as error:
        # A failure before the inner runtime receipt still gets retained, but
        # never write to a caller path that this invocation did not create.
        work = ownership.get("newWork")
        if work is not None:
            target = work / "EARLY-FIRST-FAILURE.json"
            if not target.exists():
                write(target, {"kind":"runtime-supply-early-first-failure",
                      "passed":False, "actualCheckerInputs":0,
                      "errorClass":type(error).__name__, "error":str(error)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
