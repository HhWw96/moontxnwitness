"""Bounded Linux Elle batch transport. No import-time execution or source imports."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid

ELLE = "4e359e597c52938b0afebb8bc42273914d68a424"
R3_SUMMARY = "28cc491ea897d7191ea6305219abdd1009d53b822a79cfccbac3d79dfdf1709c"
R3_TRANSPORT = "0664577c850598ac683f2c31f33c86e8da27a2011f694a8b147f1f91632964f0"
ZERO = "0" * 64
PHASES = ("preparing", "invocation-intent", "returned", "completed")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_pinned(path, digest, maximum):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Pinned regular file required")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum or sha(raw) != digest:
        raise ValueError("Pinned raw bytes differ")
    return raw


def binding(path):
    raw = Path(path).read_bytes()
    return {"bytes": len(raw), "sha256": sha(raw)}


def write_new(path, raw):
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")) + "\n").encode()


def source_module(path, digest, name):
    """Execute exactly the checked byte snapshot, never cached bytecode."""
    raw = read_pinned(path, digest, 1024 * 1024)
    namespace = {"__name__": name, "__file__": str(Path(path).resolve())}
    exec(compile(raw, str(path), "exec"), namespace)
    return namespace


def expected_cases(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError("One bounded batch required")
    seen = set()
    for row in rows:
        if set(row) != {"id", "inputSha256"}:
            raise ValueError("Exact original identity fields required")
        name, digest = row["id"], row["inputSha256"]
        if not isinstance(name, str) or not 1 <= len(name) <= 128:
            raise ValueError("Invalid original ID")
        if any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in name):
            raise ValueError("Unsafe original ID")
        if name in seen or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Duplicate identity or digest")
        if any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Lowercase original digest required")
        seen.add(name)
    return rows


def ledger_records(path, cases, run_id):
    """Require complete fsynced frames and an exact per-input state machine."""
    ids = {row["id"]: i for i, row in enumerate(cases)}
    states = {row["id"]: [] for row in cases}
    previous = ZERO
    bodies = []
    with Path(path).open("rb") as stream:
        for sequence, raw in enumerate(stream, 1):
            if len(raw) > 1024 * 1024 or not raw.endswith(b"\n"):
                raise ValueError("Truncated or oversized ledger frame")
            envelope = decode(raw)
            if set(envelope) != {"body", "bodySha256", "previousSha256"}:
                raise ValueError("Invalid ledger envelope")
            body_raw = envelope["body"].encode("utf-8")
            if sha(body_raw) != envelope["bodySha256"] or previous != envelope["previousSha256"]:
                raise ValueError("Ledger digest or chain mismatch")
            previous = envelope["bodySha256"]
            body = decode(body_raw)
            if body["sequence"] != sequence or body["runId"] != run_id:
                raise ValueError("Ledger sequence or run mismatch")
            name = body["id"]
            if name not in ids:
                raise ValueError("Unexpected input ID")
            ordinal = ids[name]
            if body["ordinal"] != ordinal or body["inputSha256"] != cases[ordinal]["inputSha256"]:
                raise ValueError("Original input identity mismatch")
            phase, prior = body["phase"], states[name]
            wanted = PHASES[len(prior)] if len(prior) < len(PHASES) else None
            if phase == "completed" and prior == ["preparing"]:
                if body.get("result", {}).get("actualElleInvocationAttempted") is not False:
                    raise ValueError("Unproven preparation failure")
            elif phase == "completed" and prior == ["preparing", "invocation-intent"]:
                if body.get("result", {}).get("actualElleResultReturned") is not False:
                    raise ValueError("Unproven checker exception")
            elif phase == "reader-error" and not prior:
                pass
            elif phase != wanted:
                raise ValueError("Duplicate, reordered or invalid phase")
            if any("reader-error" in states[cases[i]["id"]] for i in range(ordinal)):
                raise ValueError("Execution continued after reader failure")
            if any(states[cases[i]["id"]][-1:] not in (["completed"], ["reader-error"])
                   for i in range(ordinal)):
                raise ValueError("Non-sequential input execution")
            if any(states[cases[i]["id"]] for i in range(ordinal + 1, len(cases))):
                raise ValueError("Execution moved backwards")
            prior.append(phase)
            bodies.append(body)
    return bodies, states


def account(cases, ledger, summaries, raw_root, run_id, process):
    expected_cases(cases)
    try:
        bodies, states = ledger_records(ledger, cases, run_id)
        by_id, rows = {}, []
        for body in bodies:
            by_id.setdefault(body["id"], []).append(body)
        allowed = {row["id"] + ".json" for row in cases}
        if any(path.name not in allowed or path.is_symlink() for path in Path(summaries).iterdir()):
            raise ValueError("Unexpected summary artifact")
        raw_allowed = {r["id"] + suffix for r in cases for suffix in (".edn", ".exception.edn")}
        if any(p.name not in raw_allowed or p.is_symlink() for p in Path(raw_root).iterdir()):
            raise ValueError("Unexpected raw artifact")
        for original in cases:
            name, phases = original["id"], states[original["id"]]
            row = dict(original, phases=phases, actualCheckerReturned=False,
                       actualCheckerInvocationAttempted=False,
                       comparisonEligible=False, originalValidity=None,
                       cycleSearchTimeout=False)
            events = by_id.get(name, [])
            complete = events[-1] if phases[-1:] == ["completed"] else None
            if complete is not None:
                path = Path(summaries) / (name + ".json")
                raw_summary = read_pinned(path, complete["summary"]["sha256"], 1024 * 1024)
                value = decode(raw_summary)
                if len(raw_summary) != complete["summary"]["bytes"] or value != complete["result"]:
                    raise ValueError("Summary bytes or content differ")
                if value.get("id") != name or value.get("inputSha256") != original["inputSha256"]:
                    raise ValueError("Summary original identity mismatch")
                returned = "returned" in phases
                if value.get("actualElleResultReturned") is not returned:
                    raise ValueError("Returned result lacks matching durable marker")
                attempted = value.get("actualElleInvocationAttempted")
                retained = value.get("rawResultRetained")
                if type(attempted) is not bool or type(retained) is not bool:
                    raise ValueError("Actual invocation/retention state must be boolean")
                if attempted is not ("invocation-intent" in phases):
                    raise ValueError("Attempted state contradicts original durable phases")
                if returned and not attempted:
                    raise ValueError("Returned result requires an attempted invocation")
                if retained and not returned:
                    raise ValueError("Retained result requires a returned invocation")
                row["actualCheckerReturned"] = returned
                row["actualCheckerInvocationAttempted"] = value.get("actualElleInvocationAttempted") is True
                if value.get("rawResultRetained"):
                    original_raw = read_pinned(Path(raw_root) / (name + ".edn"),
                                               complete["raw"]["sha256"], 8 * 1024 * 1024)
                    if len(original_raw) != complete["raw"]["bytes"]:
                        raise ValueError("Raw evidence size mismatch")
                if returned and value.get("rawResultRetained"):
                    validity, verdict = value.get("originalValidity"), value.get("valid")
                    timeout = value.get("cycleSearchTimeout") is True
                    row.update(originalValidity=validity, cycleSearchTimeout=timeout)
                    if type(verdict) is bool:
                        if validity != {"kind": "boolean", "value": verdict}:
                            raise ValueError("Typed original verdict changed")
                        row["status"] = "returned-" + ("true" if verdict else "false") + (
                            "-with-cycle-timeout" if timeout else "")
                        row["comparisonEligible"] = not timeout
                    elif verdict == "unknown" and validity == {"kind": "keyword", "value": "unknown"}:
                        row["status"] = "returned-unknown"
                    elif verdict == "execution-error":
                        row["status"] = "result-transport-error"
                    else:
                        raise ValueError("Unsupported or changed original verdict")
                else:
                    row["status"] = "execution-error-" + value.get("failureStage", "unclassified")
            elif "returned" in phases:
                row.update(status="returned-unretained-or-untransported",
                           actualCheckerReturned=True, actualCheckerInvocationAttempted=True)
            elif "invocation-intent" in phases:
                row["status"] = "interrupted-after-intent"
            elif phases == ["preparing"]:
                row["status"] = "preparation-interrupted"
            elif phases == ["reader-error"]:
                row["status"] = "reader-failure"
            else:
                row["status"] = "not-invoked"
            rows.append(row)
        integrity, issue = True, None
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as error:
        integrity, issue = False, {"class": type(error).__name__, "message": str(error)}
        rows = [dict(row, status="protocol-error", actualCheckerReturned=False,
                     actualCheckerInvocationAttempted=False, comparisonEligible=False)
                for row in cases]
    if (process.get("exitCode") != 0 or process.get("stopReason") is not None
            or process.get("rawStreamsMayBeTruncated") or process.get("controllerErrors")):
        for row in rows:
            row["comparisonEligible"] = False
    return {"schema": 1, "transportIntegrity": integrity, "issue": issue,
            "inputsAccounted": len(rows), "cases": rows, "process": process,
            "actualElleReturnedInputs": sum(row["actualCheckerReturned"] for row in rows),
            "actualAgreementCount": 0, "SDKExecutedByController": False}


def comparison_counts(accounting, sdk):
    counts = {"agree": 0, "different": 0, "notCompared": 0}
    for row in accounting["cases"]:
        other = sdk.get(row["id"])
        if not row["comparisonEligible"] or type(other) is not bool:
            counts["notCompared"] += 1
        elif other == row["originalValidity"]["value"]:
            counts["agree"] += 1
        else:
            counts["different"] += 1
    return counts



def campaign_account(groups, results, total=2000):
    """Pure aggregation of already revalidated batch accounting; no invented verdict."""
    all_rows, seen, batches = [], set(), []
    if len(groups) > 40 or set(results) - set(groups):
        raise ValueError("Unexpected campaign batch")
    for name, cases in groups.items():
        expected_cases(cases)
        for original in cases:
            if original["id"] in seen:
                raise ValueError("Duplicate original campaign ID")
            seen.add(original["id"])
        result = results.get(name)
        if result is None:
            rows = [dict(row, status="not-invoked", actualCheckerReturned=False,
                         actualCheckerInvocationAttempted=False, comparisonEligible=False)
                    for row in cases]
            batch_status = "not-invoked"
        else:
            rows = result["cases"]
            if len(rows) != len(cases) or any(
                row.get("id") != original["id"] or row.get("inputSha256") != original["inputSha256"]
                for row, original in zip(rows, cases)):
                raise ValueError("Campaign result identities differ")
            if not result["transportIntegrity"]:
                if any(row.get("comparisonEligible") or row.get("actualCheckerReturned") for row in rows):
                    raise ValueError("Failed integrity cannot claim actual/comparable results")
            batch_status = "accounted"
        all_rows.extend(rows)
        batches.append({"batch": name, "status": batch_status, "inputs": len(cases)})
    if len(all_rows) != total:
        raise ValueError("Entire original campaign must be accounted")
    return {"cases": all_rows, "batches": batches, "inputsAccounted": total,
            "actualElleReturnedInputs": sum(r["actualCheckerReturned"] for r in all_rows),
            "actualAgreementCount": 0, "actualSDKExecuted": False}


def resource_gate(memory, disk):
    minimum_memory, minimum_disk = 1288490189, 2147483648
    return {"profile": "elle-r4-functional-linux-1.2gib-v1",
            "availableMemoryBytes": memory, "availableOutputDiskBytes": disk,
            "minimumMemoryBytes": minimum_memory, "minimumOutputDiskBytes": minimum_disk,
            "passed": memory >= minimum_memory and disk >= minimum_disk}


def linux_resources(parent):
    if os.name != "posix" or not Path("/proc/meminfo").is_file():
        return resource_gate(0, 0)
    values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    memory = int(values["MemAvailable"].split()[0]) * 1024
    return resource_gate(memory, shutil.disk_usage(parent).free)


def run_process(argv, cwd, env, stdin, output, timeout=300, log_limit=8 * 1024 * 1024,
                artifact_limit=64 * 1024 * 1024):
    """Own only this Linux process group; preserve first bounded log prefixes."""
    if os.name != "posix":
        raise RuntimeError("Reviewed Linux process-group execution required")
    output = Path(output)
    stdout, stderr = output / "stdout.raw", output / "stderr.raw"
    stop, totals, errors = threading.Event(), {}, []
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    def drain(name, source, target):
        total = retained = 0
        try:
            with target.open("xb") as stream:
                while chunk := source.read(65536):
                    total += len(chunk)
                    allowed = min(len(chunk), max(0, log_limit - retained))
                    if allowed:
                        stream.write(chunk[:allowed])
                        retained += allowed
                    if total > log_limit:
                        stop.set()
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as error:
            errors.append({"stage": name, "class": type(error).__name__, "message": str(error)})
            stop.set()
        finally:
            totals[name] = {"observedBytes": total, "retainedBytes": retained,
                            "complete": total == retained}
    threads = [threading.Thread(target=drain, args=(name, pipe, path), daemon=True)
               for name, pipe, path in (("stdout", proc.stdout, stdout), ("stderr", proc.stderr, stderr))]
    delivery = {"bytes": len(stdin), "sha256": sha(stdin), "writtenBytes": 0,
                "fullyDelivered": False}
    def feed():
        try:
            delivery["writtenBytes"] = proc.stdin.write(stdin)
            proc.stdin.flush()
            proc.stdin.close()
            delivery["fullyDelivered"] = delivery["writtenBytes"] == len(stdin)
        except Exception as error:
            errors.append({"stage": "stdin", "class": type(error).__name__, "message": str(error)})
            stop.set()
            try:
                proc.stdin.close()
            except Exception:
                pass
    threads.append(threading.Thread(target=feed, daemon=True))
    for thread in threads:
        thread.start()
    reason = None
    try:
        while proc.poll() is None:
            used = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
            if stop.is_set():
                reason = "log-budget-or-write-failure"
            elif used > artifact_limit:
                reason = "artifact-budget"
            elif time.monotonic() - started >= timeout:
                reason = "process-timeout"
            if reason:
                os.killpg(proc.pid, signal.SIGKILL)
                break
            time.sleep(0.025)
        proc.wait(timeout=10)
    except Exception as error:
        errors.append({"stage": "process", "class": type(error).__name__, "message": str(error)})
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
        reason = reason or "process-controller-failure"
    finally:
        for thread in threads:
            thread.join(2)
        if any(thread.is_alive() for thread in threads):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for thread in threads:
                thread.join(2)
            reason = reason or "owned-descendant-pipe-retention"
    if stop.is_set():
        reason = reason or "log-budget-or-write-failure"
    if sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) > artifact_limit:
        reason = reason or "artifact-budget"
    return {"stdinDelivery": delivery, "argv": argv, "exitCode": proc.returncode, "stopReason": reason,
            "timedOut": reason == "process-timeout", "logBindings": {
                p.name: binding(p) for p in (stdout, stderr) if p.exists()},
            "streams": totals, "controllerErrors": errors,
            "rawStreamsMayBeTruncated": any(not row["complete"] for row in totals.values())}


def validate_runtime(raw):
    value = decode(raw)
    if type(value) is not dict:
        raise ValueError("Runtime manifest object required")
    if value.get("fixedElleCommit") != ELLE or value.get("java") != 21 or value.get("clojure") != "1.12.6":
        raise ValueError("Fixed upstream/runtime required")
    if value.get("leinProfile") != "+dev" or value.get("additionalGraphs") != []:
        raise ValueError("Original dev profile and graph options required")
    if value.get("classpathFromActualLein") is not True:
        raise ValueError("Actual retained Lein +dev classpath provenance required")
    if not value["classpath"]:
        raise ValueError("Nonempty effective classpath required")
    for entry in value["classpath"]:
        path = Path(entry["path"])
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("Pinned absolute classpath required")
        if path.is_file():
            read_pinned(path, entry["sha256"], entry["bytes"])
            if path.stat().st_size != entry["bytes"]:
                raise ValueError("Classpath size changed")
        elif path.is_dir():
            files = {}
            for p in sorted(path.rglob("*")):
                if p.is_symlink():
                    raise ValueError("Symlink in classpath")
                if p.is_file():
                    files[p.relative_to(path).as_posix()] = binding(p)
            if files != entry["files"]:
                raise ValueError("Classpath directory closure differs")
        else:
            raise ValueError("Missing classpath entry")
    for name in ("javaExecutable", "xvfbExecutable"):
        entry = value[name]
        read_pinned(entry["path"], entry["sha256"], entry["bytes"])
        if Path(entry["path"]).stat().st_size != entry["bytes"]:
            raise ValueError("Runtime executable size differs")
    p = value["leinClasspathProvenance"]
    proof_raw = read_pinned(p["path"], p["sha256"], p["bytes"])
    if len(proof_raw) != p["bytes"]:
        raise ValueError("Classpath provenance size differs")
    proof = decode(proof_raw)
    if (proof.get("exitCode") != 0 or proof.get("fixedElleCommit") != ELLE
            or proof.get("argvSuffix") != ["with-profile", "+dev", "classpath"]
            or proof.get("effectiveClasspath") != [e["path"] for e in value["classpath"]]):
        raise ValueError("Classpath provenance contract differs")
    stdout = proof["stdout"]
    raw_stdout = read_pinned(stdout["path"], stdout["sha256"], 1048576)
    if len(raw_stdout) != stdout["bytes"]:
        raise ValueError("Classpath stdout size differs")
    if raw_stdout.decode().strip() != os.pathsep.join(proof["effectiveClasspath"]):
        raise ValueError("Actual retained classpath stdout differs")
    return value


def execute(args):
    plan_raw = read_pinned(args.plan, args.plan_sha256, 1024 * 1024)
    plan, work = decode(plan_raw), Path(args.output).resolve()
    if globals().get("__verified_source_sha256__") != plan["controllerSha256"]:
        raise ValueError("Externally pinned same-byte controller loader required")
    cases = expected_cases(plan["cases"])
    wrapper = read_pinned(args.wrapper, plan["wrapperSha256"], 1024 * 1024)
    summary = read_pinned(args.summary, R3_SUMMARY, 1024 * 1024)
    transport = read_pinned(args.transport, R3_TRANSPORT, 1024 * 1024)
    batch = read_pinned(plan["batchPath"], plan["batchSha256"], 8 * 1024 * 1024)
    if len(batch) != plan["batchBytes"]:
        raise ValueError("Original batch size differs")
    runtime = validate_runtime(read_pinned(args.runtime, args.runtime_sha256, 4 * 1024 * 1024))
    work.mkdir(parents=False, exist_ok=False)
    run_id = uuid.uuid4().hex
    for directory in ("raw", "summaries", "tmp"):
        (work / directory).mkdir()
    for name, raw in (("input.edn", batch), ("summary.clj", summary),
                      ("transport.clj", transport), ("wrapper.stdin.clj", wrapper)):
        write_new(work / name, raw)
    write_new(work / "control.edn", json.dumps([[r["id"], r["inputSha256"]] for r in cases]).encode())
    write_new(work / "ledger.jsonl", b"")
    prefix = [runtime["xvfbExecutable"]["path"], "-a", "-e", str(work / "xvfb.raw"),
              runtime["javaExecutable"]["path"], "-Xmx1024m",
              "-Djava.io.tmpdir=" + str(work / "tmp"),
              "-cp", os.pathsep.join(r["path"] for r in runtime["classpath"]), "clojure.main", "-"]
    argv = prefix + [str(work / p) for p in ("input.edn", "summaries", "raw", "ledger.jsonl", "control.edn",
                                            "summary.clj")] + [R3_SUMMARY, str(work / "transport.clj"),
                                                                R3_TRANSPORT, run_id]
    safe = {k: v for k, v in os.environ.items()
            if not any(s in k.upper() for s in ("TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "PRIVATE_KEY"))}
    for key in ("CLASSPATH", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "PYTHONPATH"):
        safe.pop(key, None)
    safe.update(HOME=str(work), TMPDIR=str(work / "tmp"), TMP=str(work / "tmp"),
                TEMP=str(work / "tmp"), PYTHONDONTWRITEBYTECODE="1")
    registration = {"controllerSha256": globals()["__verified_source_sha256__"],
                    "schema": 1, "planSha256": sha(plan_raw), "runtimeManifestSha256": args.runtime_sha256,
                    "wrapperStdin": {"bytes": len(wrapper), "sha256": sha(wrapper)}, "runId": run_id,
                    "fixedElleCommit": ELLE, "cases": cases, "argv": argv,
                    "timeoutSeconds": 300, "actualStarted": False}
    write_new(work / "registration.json", json_bytes(registration))
    resources = linux_resources(work)
    write_new(work / "resource-gate.json", json_bytes(resources))
    try:
        if not resources["passed"]:
            process = {"exitCode": None, "stopReason": "resource-gate", "timedOut": False}
        else:
            process = run_process(argv, runtime["upstreamRoot"], safe, wrapper, work)
    except Exception as error:
        process = {"exitCode": None, "stopReason": "controller-start-failure", "timedOut": False,
                   "errorClass": type(error).__name__, "error": str(error)}
    result = account(cases, work / "ledger.jsonl", work / "summaries", work / "raw", run_id, process)
    result["registrationSha256"] = binding(work / "registration.json")["sha256"]
    result["sourceBytesUnchanged"] = sha(Path(args.wrapper).read_bytes()) == sha(wrapper)
    write_new(work / "accounting.json", json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    for name in ("plan", "plan-sha256", "runtime", "runtime-sha256", "wrapper", "summary", "transport", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if not args.execute:
        parser.error("Explicit --execute and external plan/runtime pins required")
    result = execute(args)
    print(json.dumps({"output": args.output, "transportIntegrity": result["transportIntegrity"],
                      "inputsAccounted": result["inputsAccounted"],
                      "actualElleReturnedInputs": result["actualElleReturnedInputs"]}))
    process = result["process"]
    terminal = {"returned-true", "returned-false", "returned-unknown",
                "returned-true-with-cycle-timeout", "returned-false-with-cycle-timeout"}
    return 0 if (result["transportIntegrity"] and process["exitCode"] == 0
                 and process["stopReason"] is None
                 and all(r["status"] in terminal for r in result["cases"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
