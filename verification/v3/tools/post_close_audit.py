"""Independent closure regression audit; no production/test fixture imports.

Run against a frozen source in a NEW --output directory. It uses an intentionally
small synchronous driver and real journal IO. This is not a PostgreSQL test.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import types
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "integrations/python"))
from moontxnwitness_capture.capture_v3 import CaptureV3Session
from moontxnwitness_capture.journal_v3 import JournalReader, SegmentedJournal


class RawConnection:
    def __init__(self):
        self.info = types.SimpleNamespace(transaction_status=0)
        self.autocommit, self.closed, self.executions = False, False, []
        self.commit_result = object()

    def cursor(self, *args, **kwargs):
        return RawCursor(self)

    def commit(self):
        self.info.transaction_status = 0
        return self.commit_result

    def close(self):
        self.closed = True


class RawCursor:
    def __init__(self, connection):
        self.connection, self.row_factory = connection, None
        self.description, self.rowcount, self.rownumber = None, -1, 0

    def execute(self, query, params=None, **kwargs):
        self.connection.executions.append([query, params, kwargs])
        self.connection.info.transaction_status = 2
        self.description = [types.SimpleNamespace(name="value", type_code=23)]
        self.rowcount, self.rownumber = 1, 0
        return self

    def fetchall(self):
        self.rownumber = 1
        return [(1,)]

    def close(self):
        pass


def binding(path):
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def refuse(operation):
    try:
        result = operation()
        if isinstance(result, SegmentedJournal):
            # A regression must not leave an unexpected live writer/thread.
            result.close(source_closed=False)
            return {"refused": False, "returnedType": type(result).__name__,
                    "unexpectedWriterClosedByAudit": True}
        try:
            json.dumps(result)
            returned = result
        except TypeError:
            returned = {"type": type(result).__name__}
        return {"refused": False, "returned": returned}
    except Exception as error:
        # Error classes are sufficient here; raw local paths are not published.
        return {"refused": True, "errorClass": type(error).__name__}


@contextmanager
def reject_new_journal_writes(directory):
    """Inject an IO outage at both public Python file-creation entry points.

    Existing sealed bytes remain readable. This does not patch production marker
    helpers and does not assume a marker filename or serialization algorithm.
    """
    directory = directory.resolve()
    original_path_open, original_os_open = Path.open, os.open
    attempts = []

    def inside(value):
        try:
            return Path(value).resolve().is_relative_to(directory)
        except (TypeError, ValueError):
            return False

    def guarded_path_open(path, mode="r", *args, **kwargs):
        if inside(path) and any(flag in mode for flag in "wax+"):
            attempts.append(Path(path).name)
            raise PermissionError("independent injected journal write outage")
        return original_path_open(path, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if inside(path) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            attempts.append(Path(path).name)
            raise PermissionError("independent injected journal write outage")
        return original_os_open(path, flags, *args, **kwargs)

    with patch.object(Path, "open", guarded_path_open), patch.object(os, "open", guarded_os_open):
        yield attempts


def run_case(output, mode):
    output.mkdir(exist_ok=False)
    journal = output / "journal"
    session = CaptureV3Session(journal, exclusive_writers=True)
    session.publish_snapshot({"x": "x0"}, consistent=True)
    raw = RawConnection()
    wrapped = session.wrap(raw)
    assert wrapped.execute("SELECT 1").fetchall() == [(1,)]
    assert wrapped.commit() is raw.commit_result
    closed = session.close(source_closed=True).as_dict()
    original = {p.name: binding(p) for p in journal.iterdir() if p.is_file()}
    checks = {"originalWindowComplete": closed["complete"]}
    details = {"mode": mode, "originalClosedStatus": closed,
               "originalDiskBindings": original}

    def later_activity():
        if mode == "facade-connect":
            another = RawConnection()
            driver = types.SimpleNamespace(connect=lambda: another)
            observed = session.driver(driver).connect()
            checks["businessConnectionIdentityPreserved"] = observed is another
            checks["businessRowsPreserved"] = observed.cursor().execute("SELECT 2").fetchall() == [(1,)]
            checks["businessCommitReturnPreserved"] = observed.commit() is another.commit_result
        elif mode == "journal-append":
            result = session.journal.append({"seq": 7, "time": 10**12, "kind": "begin",
                                             "tx": "later", "connection": "later-connection"})
            checks["appendRejected"] = not result.accepted
        else:
            checks["businessRowsPreserved"] = wrapped.execute("SELECT 2").fetchall() == [(1,)]
            checks["businessCommitReturnPreserved"] = wrapped.commit() is raw.commit_result
            checks["actualSecondBusinessExecution"] = len(raw.executions) == 2

    if mode == "marker-io-outage":
        with reject_new_journal_writes(journal) as attempts:
            later_activity()
        details["injectedWriteAttempts"] = attempts
        checks["outageActuallyInterceptedWrite"] = bool(attempts)
    else:
        later_activity()

    details["sessionGaps"] = list(session.gaps)
    after = {p.name: binding(p) for p in journal.iterdir() if p.is_file()}
    details["afterDiskBindings"] = after
    checks["sealedEvidenceBytesUnchanged"] = all(after.get(name) == value for name, value in original.items())
    instance = refuse(lambda: session.export(output / "instance-export.json"))
    details["instanceExport"] = instance
    checks["instanceExportRefused"] = instance["refused"]
    checks["noInstanceExportPublished"] = not (output / "instance-export.json").exists()
    status = JournalReader(journal).verify().as_dict()
    details["freshReaderStatus"] = status
    if mode != "marker-io-outage":
        checks["freshReaderNotComplete"] = not status["complete"]
        operations = {
            "readerExport": lambda: JournalReader(journal).export(output / "reader-export.json",
                clock_domain=session.clock_domain, exclusive_writers=True),
            "readerArchive": lambda: JournalReader(journal).archive(output / "archive.zip"),
            "readerIteration": lambda: list(JournalReader(journal).iter_events()),
            "reopen": lambda: SegmentedJournal.reopen(journal, exclusive_continuation=True),
        }
        for name, operation in operations.items():
            result = refuse(operation)
            details[name] = result
            checks[name + "Refused"] = result["refused"]
    else:
        details["outageScope"] = ("If every invalidation write fails, another process cannot infer the "
            "unpersisted activity from unchanged bytes. This case requires a permanent live-instance "
            "refusal and records fresh-reader status without claiming durable cross-process detection.")
    details.update(checks=checks, passed=all(checks.values()))
    target = output / "case-receipt.json"
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(details, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    return {"mode": mode, "passed": details["passed"], "checks": checks,
            "receipt": target.relative_to(output.parent).as_posix(), **binding(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = ["integrations/python/moontxnwitness_capture/capture_v3.py",
               "integrations/python/moontxnwitness_capture/journal_v3.py",
               "integrations/python/moontxnwitness_capture/capture.py"]
    before = {name: binding(ROOT / name) for name in sources}
    cases = []
    for mode in ("wrapper-execute", "facade-connect", "journal-append", "marker-io-outage"):
        cases.append(run_case(args.output / mode, mode))
    after = {name: binding(ROOT / name) for name in sources}
    receipt = {"schema": 1, "audit": "independent observed post-close activity audit",
               "createdAt": datetime.now(timezone.utc).isoformat(),
               "actualDatabaseExecution": False, "productionModified": False,
               "sourceBindings": before, "sourceUnchangedDuringRun": before == after,
               "auditImplementation": binding(Path(__file__)), "cases": cases,
               "passed": before == after and all(case["passed"] for case in cases),
               "scope": "Independent minimal synchronous fake driver with actual journal filesystem IO; not a database or application consistency verdict."}
    target = args.output / "receipt.json"
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": receipt["passed"], "cases": len(cases),
                      "checks": sum(len(case["checks"]) for case in cases),
                      "receipt": target.as_posix(), **binding(target)}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
