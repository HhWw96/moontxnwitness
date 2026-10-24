"""Experimental-branch runtime producer only. No import-time provisioning."""
from pathlib import Path
import argparse
import contextlib
import signal
import traceback
import hashlib
import json
import os
import re
import subprocess
import sys

REPOSITORY = "HhWw96/moontxnwitness"
BRANCH = "experiment/elle-v028-hosted"
WORKFLOW = ".github/workflows/elle-v028-hosted.yml"
APP = "experiments/elle/v028"
CORE = "4f9a73a5fe82478d913cb751ab68714d4ba0558c85b45a3933c6eb9a6c3078ef"
PROVIDER = "c5cfdc2f690faf62900936badcdbbd4e832966e19c917886034d3496578ff2a3"
SOURCE_CLOSURE = "a27f9d17dc41a9c90d1bc851d3fdbb710ead594ce212edf5f86ce5d8f7744b0a"
LOADER = "import hashlib,sys;from pathlib import Path;p,h=sys.argv[1:3];b=Path(p).read_bytes();assert hashlib.sha256(b).hexdigest()==h;sys.argv=[p,*sys.argv[3:]];exec(compile(b,p,'exec'),{'__name__':'__main__','__file__':p,'__verified_source_sha256__':h})"


class HostedProducerCancelled(Exception):
    """Route cancellation through the approved run_process Exception cleanup."""


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def binding(path):
    size, digest = 0, hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(65536):
            size += len(block)
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def write_new(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def safe_relative(name):
    need(type(name) is str and name and "\\" not in name and ":" not in name, "Unsafe relative member")
    p = Path(name)
    need(not p.is_absolute() and all(x not in ("", ".", "..") for x in name.split("/")), "Unsafe relative member")
    return p


def validate_context(env, head, config):
    need(env.get("GITHUB_REPOSITORY") == REPOSITORY, "Exact repository required")
    need(env.get("GITHUB_EVENT_NAME") == "push", "Experimental push required")
    need(env.get("GITHUB_REF") == "refs/heads/" + BRANCH, "Main/tag/foreign branch refused")
    need(re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", "")) is not None, "Full workflow commit required")
    need(head == env["GITHUB_SHA"], "Checkout differs from actual event commit")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        need(re.fullmatch(r"[1-9][0-9]*", env.get(key, "")) is not None, "Actual run identity required")
    need(type(config) is dict and type(config.get("schema")) is int and config.get("schema") == 1, "Stage object required")
    need(config.get("experimentBranch") == BRANCH and config.get("stage") == "runtime", "Producer only; consumers require later admitted workflow")
    need(config.get("networkProvisioningAuthorized") is True, "Explicit runtime-only network authorization required")
    need(config.get("runtimeAdmission") is None and config.get("smokeAdmission") is None, "Producer cannot manufacture or consume its own admission")


def validate_manifest(root, raw, pin):
    need(type(pin) is str and re.fullmatch(r"[0-9a-f]{64}", pin), "External source manifest pin required")
    need(sha(raw) == pin, "Frozen execution source manifest differs")
    doc = json.loads(raw)
    need(type(doc.get("schema")) is int and doc.get("schema") == 1 and type(doc.get("files")) is dict and doc["files"], "Bound source list required")
    for name, expected in doc["files"].items():
        p = root / safe_relative(name)
        need(not p.is_symlink() and p.is_file() and p.resolve().is_relative_to(root.resolve()), "Bound source path escapes checkout")
        need(binding(p) == expected, "Bound source bytes differ: " + name)
    return doc


def closure(root):
    files, directories = {}, []
    for p in sorted(root.rglob("*")):
        need(not p.is_symlink(), "Symlink in owned producer output")
        if p.is_dir():
            directories.append(p.relative_to(root).as_posix())
        elif p.is_file():
            if p.name != "OUTPUT-INDEX.json" or p.parent != root:
                files[p.relative_to(root).as_posix()] = binding(p)
        else:
            raise ValueError("Unsupported producer member")
    return {"files": files, "directories": directories}


def verified_module(path, pin, name):
    need(not path.is_symlink() and path.is_file(), "Verified regular source required")
    raw = path.read_bytes()
    need(len(raw) <= 1024 * 1024 and sha(raw) == pin, "Execution source SHA differs")
    ns = {"__name__": name, "__file__": str(path), "__verified_source_sha256__": pin}
    exec(compile(raw, str(path), "exec"), ns)
    return ns


def producer(project, output, manifest_pin, env):
    need(os.name == "posix", "Hosted Linux execution only")
    head = subprocess.run(["git", "-c", "gc.auto=0", "rev-parse", "HEAD"], cwd=project,
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
    config = json.loads((project / APP / "stage.json").read_bytes())
    validate_context(env, head, config)
    clean = subprocess.run(["git", "-c", "gc.auto=0", "status", "--porcelain", "--untracked-files=all"],
                           cwd=project, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    need(not clean.stdout, "Execution checkout must be clean")
    manifest_raw = (project / APP / "execution-source-manifest.json").read_bytes()
    validate_manifest(project, manifest_raw, manifest_pin)
    r4 = project / APP / "r4"
    need(sha((r4 / "SOURCE-CLOSURE.json").read_bytes()) == SOURCE_CLOSURE, "Approved r4 closure differs")
    core = verified_module(r4 / "r4_controller.py", CORE, "verified_hosted_producer_core")
    resource = core["linux_resources"](output)
    need(resource["passed"], "Original1.2GiB RAM/2GiB output reserve unavailable")
    argv = [sys.executable, "-B", "-c", LOADER, str(project / APP / "supply/runtime_provider.py"), PROVIDER,
            "--prepare-runtime", "--allow-network-provisioning", "--project-root", str(project),
            "--controller", str(r4 / "r4_controller.py"), "--work", str(output / "runtime")]
    attempt = {"schema": 1, "kind": "runtime-producer-attempt-before-invocation", "repository": REPOSITORY,
               "branch": BRANCH, "workflow": WORKFLOW, "sourceCommit": head,
               "runId": int(env["GITHUB_RUN_ID"]), "runAttempt": int(env["GITHUB_RUN_ATTEMPT"]),
               "executionSourceManifestSha256": manifest_pin, "r4SourceClosureSha256": SOURCE_CLOSURE,
               "providerSha256": PROVIDER, "controllerSha256": CORE, "argv": argv,
               "literalOutputRoot": str(output), "resourceGate": resource,
               "actualCheckerInputs": 0, "runtimeIndependentlyApproved": False, "automaticRetry": False}
    write_new(output / "ATTEMPT-BEFORE-INVOCATION.json", attempt)
    write_new(output / "EXECUTION-SOURCE-MANIFEST.json", json.loads(manifest_raw))
    logs = output / "provider-process"
    logs.mkdir()
    # Execute the approved provider bytes in this process. Its own run_process
    # owns each Java/git process group; an extra outer timeout could strand an
    # inner group when terminating only the provider Python process.
    provider = verified_module(project / APP / "supply/runtime_provider.py", PROVIDER,
                               "verified_hosted_runtime_provider")
    previous_argv = sys.argv
    previous_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    def cancel_owned_provider(signum, frame):
        raise HostedProducerCancelled("Hosted producer cancelled; unwind approved owned-process cleanup")
    rc = None
    try:
        for sig in previous_signals:
            signal.signal(sig, cancel_owned_provider)
        sys.argv = [str(project / APP / "supply/runtime_provider.py"), *argv[6:]]
        with (logs / "stdout.raw").open("x", encoding="utf-8") as stdout, (logs / "stderr.raw").open("x", encoding="utf-8") as stderr:
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    rc = provider["main"]()
            except BaseException:
                traceback.print_exc(file=stderr)
                raise
            finally:
                stdout.flush()
                stderr.flush()
                os.fsync(stdout.fileno())
                os.fsync(stderr.fileno())
    finally:
        sys.argv = previous_argv
        for sig, handler in previous_signals.items():
            signal.signal(sig, handler)
        write_new(logs / "process.json", {"inProcessSameByteProviderExecution": True,
                  "exitCode": rc, "sourceSha256": PROVIDER,
                  "ownedChildCleanupDelegatedToApprovedProviderRunProcess": True,
                  "nestedOuterProcessGroupCreated": False})
    need(rc == 0, "Runtime provider failed; preserve original outputs, do not retry automatically")
    runtime = output / "runtime"
    result = json.loads((runtime / "runtime-supply-receipt.json").read_bytes())
    need(result.get("passed") is True and result.get("actualCheckerInputs") == 0 and
         result.get("sourceControllerSha256") == CORE, "Actual provider receipt did not pass")
    runtime_raw = (runtime / "runtime-manifest.json").read_bytes()
    core["validate_runtime"](runtime_raw)
    validate_manifest(project, manifest_raw, manifest_pin)
    return {"schema": 1, "kind": "actual-runtime-producer-receipt", "passed": True,
            "sourceCommit": head, "repository": REPOSITORY, "branch": BRANCH,
            "runId": attempt["runId"], "runAttempt": attempt["runAttempt"],
            "executionSourceManifestSha256": manifest_pin,
            "runtimeManifest": binding(runtime / "runtime-manifest.json"),
            "runtimeArtifactIndex": binding(runtime / "RUNTIME-ARTIFACT-INDEX.json"),
            "runtimeReceipt": binding(runtime / "runtime-supply-receipt.json"),
            "literalOutputRoot": str(output), "literalRuntimeRoot": str(runtime),
            "actualCheckerInputs": 0, "actualSDKExecuted": False,
            "runtimeIndependentlyApproved": False, "nextGate": "independent-actual-runtime-review",
            "sourceFilesUnchanged": True, "automaticRetry": False,
            "emptyDirectoriesRecordedForExactRestore": True,
            "sameLiteralRootAndHostExecutableHashesRequiredForFutureRestore": True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-manifest-sha256", required=True)
    a = p.parse_args()
    project = Path.cwd().resolve()
    need(bool(os.environ.get("RUNNER_TEMP")) and Path(os.environ["RUNNER_TEMP"]).is_absolute(), "Explicit absolute RUNNER_TEMP required")
    parent = Path(os.environ["RUNNER_TEMP"]).absolute()
    need(os.name == "posix" and parent.is_dir() and parent.resolve() == parent and not parent.is_symlink(), "Actual literal Linux RUNNER_TEMP required")
    output = parent / "mtw-elle-v028-runtime-first"
    need(not output.exists(), "Fresh exclusive producer output required; keep earlier attempts")
    output.mkdir()
    passed = False
    try:
        result = producer(project, output, a.source_manifest_sha256, dict(os.environ))
        write_new(output / "STAGE-RECEIPT.json", result)
        passed = True
    except BaseException as error:
        write_new(output / "FIRST-FAILURE.json", {"passed": False, "type": type(error).__name__,
                  "reason": str(error), "actualCheckerInputs": 0, "automaticRetry": False})
        raise
    finally:
        members = closure(output)
        write_new(output / "OUTPUT-INDEX.json", {"schema": 1, "kind": "runtime-producer-owned-output-index",
                  "sourceRoot": str(output), "runtimePassed": passed, **members,
                  "rawArtifactZipSha256StillRequiresIndependentDownload": True,
                  "runtimeIndependentlyApproved": False, "actualCheckerInputs": 0})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())