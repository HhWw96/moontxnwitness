"""One preregistered real final-sync fault. Never run a database or benchmark."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import traceback
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_INDEX_SHA = "f312fc6d0b6adc6b146954e6b19d0c94ce09d0b5098f5869690d457f8b933962"
FAULT_MESSAGE = "Independent injection: final operation.lock directory synchronization"


def ensure(value, message):
    if not value:
        raise RuntimeError(message)


def binding(path):
    path = Path(path)
    ensure(not path.is_symlink() and path.is_file(), "Regular bound file required")
    size = path.stat().st_size
    ensure(size <= 8 * 1024 * 1024, "Independent small-fixture file limit")
    hashed = hashlib.sha256()
    consumed = 0
    with path.open("rb") as file:
        while block := file.read(65536):
            consumed += len(block)
            ensure(consumed <= 8 * 1024 * 1024, "Independent fixture grew beyond limit")
            hashed.update(block)
    ensure(consumed == size, "Independent fixture changed during binding")
    return {"bytes": size, "sha256": hashed.hexdigest()}


def read_json(path):
    ensure(binding(path)["bytes"] <= 1024 * 1024, "Small JSON metadata required")
    return json.loads(Path(path).read_bytes())


def source_bindings(candidate, expected_sha):
    index_path = candidate / "candidate-index.json"
    ensure(binding(index_path)["sha256"] == expected_sha, "Unexpected author candidate index")
    index = read_json(index_path)
    bound = {"candidate/candidate-index.json": binding(index_path)}
    for group, base, prefix in ((index["fileBindings"], candidate, "candidate/"),
                                (index["runtimeDependencies"], ROOT, "repository/")):
        for name, expected in group.items():
            relative = Path(name)
            ensure(not relative.is_absolute() and ".." not in relative.parts and "\\" not in name,
                   "Unsafe candidate dependency path")
            actual = binding(base / relative)
            ensure(actual == expected, "Author source binding mismatch: " + name)
            bound[prefix + name] = actual
    for name in ("contract-v1.json", "preregistration-before-implementation.json", "events-v1.json", "counterexample.py"):
        bound["independent/" + name] = binding(HERE / name)
    return bound


def tree_bindings(root):
    files = sorted(path for path in root.rglob("*") if path.is_file())
    ensure(len(files) <= 128, "Independent fixture file-count limit")
    return {path.relative_to(root).as_posix(): binding(path) for path in files}


def preserve_original(path, target):
    expected = binding(path)
    ensure(expected["bytes"] <= 1024 * 1024, "Small prepared authority required")
    with path.open("rb") as source, target.open("xb") as destination:
        remaining = expected["bytes"]
        while remaining:
            block = source.read(min(65536, remaining))
            ensure(block, "Actual prepared authority became truncated")
            destination.write(block)
            remaining -= len(block)
        ensure(not source.read(1), "Actual prepared authority grew beyond its original binding")
    ensure(binding(target) == expected, "Prepared authority copy differs from its actual bytes")
    return expected


def load_candidate(candidate):
    ensure(candidate.parent == ROOT / "artifacts", "Restore the candidate in its original repository layout")
    sys.path.insert(0, str(candidate))
    import managed
    ensure(Path(managed.__file__).resolve() == candidate / "managed.py", "Unexpected imported candidate")
    from moontxnwitness_capture.journal_v3 import SegmentedJournal
    return managed, SegmentedJournal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=ROOT / "artifacts/source-window-v3-archive-r3-draft")
    parser.add_argument("--expected-candidate-index", default=DEFAULT_INDEX_SHA)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--child-prune", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    if args.child_prune is not None:
        source_bindings(candidate, args.expected_candidate_index)
        managed, _ = load_candidate(candidate)
        source = managed.ManagedSource(args.child_prune)
        source.fault = lambda stage: os._exit(73) if stage == "after-manifest" else None
        source.prune(before_seq=999)
        raise RuntimeError("The actual prepared-plan crash point was not reached")

    ensure(args.work is not None, "A new task-owned --work directory is required")
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema": 1, "kind": "independent-final-operation-lock-sync-fault", "passed": False,
        "tests": 1, "skipped": [], "checks": [], "failures": [],
        "sourceCandidateIndexSha256": args.expected_candidate_index,
        "actualFilesystemExecution": False, "actualDatabaseExecution": False,
        "formalPerformanceMeasurement": False, "independentAcceptance": False,
        "candidateModified": False, "expectationInvertedForKnownBug": False,
        "platform": platform.platform(), "python": sys.version, "sqlite": sqlite3.sqlite_version,
        "started": datetime.now(timezone.utc).isoformat(),
    }

    def check(name, actual, expected):
        passed = actual == expected
        receipt["checks"].append({"name": name, "actual": actual, "expected": expected, "passed": passed})
        if not passed:
            receipt["failures"].append({"test": name, "actual": actual, "expected": expected})

    before_sources = None
    try:
        before_sources = source_bindings(candidate, args.expected_candidate_index)
        receipt["sourceBindingsBefore"] = before_sources
        managed, SegmentedJournal = load_candidate(candidate)
        journal_path, store, archive = work / "journal", work / "store", work / "source.zip"
        events = read_json(HERE / "events-v1.json")
        ensure(len(events) == 18 and all(event["seq"] == i for i, event in enumerate(events, 1)),
               "Frozen original input sequence changed")
        journal = SegmentedJournal(journal_path, segment_bytes=256, max_record_bytes=256,
                                   flush_bytes=128, max_queue_bytes=4096)
        for event in events:
            journal.append(event)
        journal.close(source_closed=True)
        source = managed.ManagedSource.adopt(store, journal_path, exclusive_source_ownership=True)
        source.archive_checkpoint("checkpoint", archive)
        before_original = {name: binding(path) for name, path in (
            ("journal-index.json", journal_path / "journal-index.json"),
            ("transactions.sqlite3", journal_path / "transactions.sqlite3"),
            ("writer.lock", journal_path / "writer.lock"), ("source.zip", archive))}
        receipt["actualFilesystemExecution"] = True
        with (work / "actual-prepared-plan-child.log").open("xb") as log:
            child = subprocess.run(
                [sys.executable, "-B", str(Path(__file__).resolve()), "--candidate", str(candidate),
                 "--expected-candidate-index", args.expected_candidate_index, "--child-prune", str(store)],
                stdout=log, stderr=subprocess.STDOUT, timeout=90,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        receipt["actualChildExitCode"] = child.returncode
        ensure(child.returncode == 73, "Actual pruning child did not reach the preregistered crash")
        plan_record = read_json(store / "prune-intent.json")
        owner = read_json(store / "operation.lock")
        plan = plan_record["plan"]
        ensure(owner["token"] == plan_record["operationToken"] and owner["nonce"] == plan_record["nonce"],
               "Actual crash did not retain the original prepared authority")
        receipt["preparedAuthority"] = {"plan": plan, "owner": owner, "intent": plan_record,
                                         "intentBinding": binding(store / "prune-intent.json"),
                                         "lockBinding": binding(store / "operation.lock")}
        preserved = work / "prepared-original-bytes"
        preserved.mkdir()
        receipt["preservedActualPreparedBytes"] = {
            name: preserve_original(store / name, preserved / name)
            for name in ("prune-intent.json", "manifest.json", "operation.lock")}
        prepared_status = managed.ManagedSource(store).verify()
        receipt["preparedFreshVerify"] = prepared_status
        ensure(prepared_status["complete"] is False, "Prepared source unexpectedly completed before recovery")
        receipt["preparedFiles"] = tree_bindings(work)

        recovery = managed.ManagedSource(store)
        real_sync = managed.point.sync_directory
        injections = []

        def fail_only_final_lock_sync(path):
            if Path(path).resolve() == store and not (store / "operation.lock").exists():
                ensure(not injections, "Final lock cleanup synchronization unexpectedly repeated")
                manifest = read_json(store / "manifest.json")
                injections.append({"lockPresent": False, "pending": manifest["pending"],
                                   "generation": manifest["generation"],
                                   "completedPlan": manifest.get("completedPlan"),
                                   "intentPresent": (store / "prune-intent.json").exists(),
                                   "failureMarkerPresent": (store / "operation-failed.json").exists()})
                raise OSError(FAULT_MESSAGE)
            return real_sync(path)

        observed_error = None
        with patch.object(managed.point, "sync_directory", side_effect=fail_only_final_lock_sync):
            try:
                recovery.recover(expected_plan=plan, exclusive_recovery=True)
            except BaseException as error:
                observed_error = {"class": type(error).__name__, "message": str(error),
                                  "isOSError": isinstance(error, OSError), "trace": traceback.format_exc()}
        receipt["faultInjections"] = injections
        receipt["actualRecoveryError"] = observed_error
        receipt["afterRecoveryPoisoned"] = recovery.poisoned
        receipt["afterFailureFilesBeforeFreshVerify"] = tree_bindings(work)
        lock_path, marker_path = store / "operation.lock", store / "operation-failed.json"
        lock_value = read_json(lock_path) if lock_path.exists() else None
        marker_value = read_json(marker_path) if marker_path.exists() else None
        expected_marker = {"kind": "archive-operation-failed/1", "nonce": owner["nonce"],
                           "operationToken": owner["token"]}
        guard = lock_value == owner or marker_value == expected_marker
        receipt["afterFailureGuards"] = {"operationLock": lock_value, "failureMarker": marker_value,
                                          "ownerBoundGuardPresent": guard}
        # Observe the real candidate again after removing the sole fault patch.
        # Never alter or repair the source, intent, marker, lock, or outcome.
        fresh = managed.ManagedSource(store).verify()
        receipt["afterFailureFreshVerify"] = fresh
        receipt["afterFreshVerifyFiles"] = tree_bindings(work)
        after_original = {name: binding(path) for name, path in (
            ("journal-index.json", journal_path / "journal-index.json"),
            ("transactions.sqlite3", journal_path / "transactions.sqlite3"),
            ("writer.lock", journal_path / "writer.lock"), ("source.zip", archive))}
        receipt["originalImmutableBindingsBefore"] = before_original
        receipt["originalImmutableBindingsAfter"] = after_original
        check("actual-prepared-plan-child", child.returncode, 73)
        check("prepared-fresh-incomplete", prepared_status["complete"], False)
        check("sole-final-cleanup-fault-reached", len(injections), 1)
        check("actual-recovery-raises-injected-OSError",
              observed_error is not None and observed_error["isOSError"]
              and observed_error["message"] == FAULT_MESSAGE, True)
        check("owner-bound-guard-after-real-failure", guard, True)
        check("live-instance-poisoned-after-real-failure", recovery.poisoned, True)
        check("fresh-verification-must-remain-incomplete", fresh["complete"], False)
        check("original-index-cache-fence-and-archive-unchanged", after_original == before_original, True)
    except BaseException as error:
        receipt["failures"].append({"test": "independent-scenario-execution", "class": type(error).__name__,
                                     "message": str(error), "trace": traceback.format_exc()})
    finally:
        try:
            after_sources = source_bindings(candidate, args.expected_candidate_index)
            receipt["sourceBindingsAfter"] = after_sources
            receipt["sourceBindingsUnchanged"] = before_sources is not None and before_sources == after_sources
            check("candidate-and-independent-source-bytes-unchanged", receipt["sourceBindingsUnchanged"], True)
        except BaseException as error:
            receipt["sourceBindingsUnchanged"] = False
            receipt["failures"].append({"test": "final-source-bindings", "message": str(error)})
        receipt["passed"] = not receipt["failures"] and len(receipt["checks"]) == 9
        receipt["finished"] = datetime.now(timezone.utc).isoformat()
        with (work / "test-receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "tests": receipt["tests"],
                      "checks": len(receipt["checks"]), "receipt": str(work / "test-receipt.json")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
