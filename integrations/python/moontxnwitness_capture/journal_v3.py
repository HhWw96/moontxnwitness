"""Bounded, segmented capture journal, independent of the v1/v2 recorder.

The index binds durable NDJSON bytes. It proves storage integrity, not database
truth. Records are streamed; no in-memory list of the complete event history is
retained. Deleting source-chain records is intentionally not implemented yet.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import itertools
import json
import math
import os
import re
import sqlite3
import stat
import threading
import time
import uuid
import zipfile
import sys
import tempfile
from pathlib import Path

if __package__:
    from ._durable_policy import CapacityQueue, sync_due, sync_wait, should_sync, flush_pending
    from ._experimental_budget import PROFILE, LIMITS, profile, authorize, sqlite_limit
else:  # Preserve the documented standalone verify/export command.
    from _durable_policy import CapacityQueue, sync_due, sync_wait, should_sync, flush_pending
    from _experimental_budget import PROFILE, LIMITS, profile, authorize, sqlite_limit

KINDS = frozenset(("snapshot", "begin", "read", "write", "condition", "savepoint",
                   "rollback_to", "release", "commit_request", "commit_ok",
                   "rollback_ok", "disconnect", "statement", "rows"))
SAFE_INTEGER = 9_007_199_254_740_991
INDEX = "journal-index.json"
LOCK = "writer.lock"
INVALIDATED = "journal-invalidated.json"
TRANSACTIONS = "transactions.sqlite3"
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_SEGMENTS = 4096
HARD_RECORD_BYTES = 4 * 1024 * 1024
_SEGMENT = re.compile(r"segment-[0-9]{6}\.jsonl\Z")
_ASCII_JSON_ESCAPES = re.compile(r'["\\\x00-\x1f]')


class JournalError(RuntimeError):
    pass


class JournalIOError(JournalError):
    pass


class JournalVerificationError(JournalError):
    pass


def _integer(value, minimum=0, maximum=SAFE_INTEGER):
    return type(value) is int and minimum <= value <= maximum


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _loads(value):
    return json.loads(value, object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _bounded_copy(value, byte_limit, node_limit=65_536):
    """Copy mutable containers only after charging every visited node/string.

    The caller must not mutate its input concurrently. No complete json.dumps
    allocation is made before the aggregate size check. Strings are immutable
    and are shared; their complete escaped UTF-8 cost is counted incrementally.
    """
    remaining, nodes = byte_limit, node_limit
    ancestors = set()

    def charge(size):
        nonlocal remaining
        remaining -= size
        if remaining < 0:
            raise ValueError("record byte budget")

    def string(text):
        # Exact built-in ASCII text has one UTF-8 byte per character. Reject
        # its minimum cost before scanning escapes; no encoded copy or cache
        # proportional to an untrusted string is allocated. This is JSON byte
        # accounting only, not a parser or a replacement for scalar validation.
        if type(text) is str and text.isascii():
            charge(2 + len(text))
            for escaped in _ASCII_JSON_ESCAPES.finditer(text):
                char = escaped.group()
                charge(1 if char in '\"\\\b\t\n\f\r' else 5)
            return text
        # Keep the original per-scalar path for Unicode and str subclasses,
        # including rejection of every surrogate code point, even paired ones.
        charge(2)
        for char in text:
            code = ord(char)
            if 0xD800 <= code <= 0xDFFF:
                raise ValueError("unpaired Unicode surrogate")
            charge(2 if char in '"\\\b\t\n\f\r' else 6 if code < 32 else
                   1 if code < 128 else 2 if code < 2048 else 3 if code < 65536 else 4)
        return text

    def visit(item, depth):
        nonlocal nodes
        nodes -= 1
        if nodes < 0 or depth > 16:
            raise ValueError("record node/depth budget")
        if item is None:
            charge(4)
        elif type(item) is bool:
            charge(4 if item else 5)
        elif type(item) is int:
            if abs(item) > SAFE_INTEGER:
                raise ValueError("encode large raw integers as typed decimal strings")
            charge(len(str(item)))
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("nonfinite JSON")
            charge(len(repr(item)))
        elif isinstance(item, str):
            return string(item)
        elif isinstance(item, (dict, list, tuple)):
            identity = id(item)
            if identity in ancestors:
                raise ValueError("cyclic record")
            ancestors.add(identity)
            charge(2 + max(0, len(item) - 1))
            try:
                if isinstance(item, dict):
                    result = {}
                    for key, child in item.items():
                        if not isinstance(key, str):
                            raise ValueError("JSON object key must be text")
                        nodes -= 1
                        if nodes < 0:
                            raise ValueError("record node budget")
                        string(key)
                        charge(1)
                        result[key] = visit(child, depth + 1)
                    return result
                return [visit(child, depth + 1) for child in item]
            finally:
                ancestors.remove(identity)
        else:
            raise ValueError("unsupported JSON value")
        return item

    return visit(value, 0)


def _event(value):
    if not isinstance(value, dict) or not _integer(value.get("seq"), 1):
        raise ValueError("event requires a safe positive seq")
    if not _integer(value.get("time")) or value.get("kind") not in KINDS:
        raise ValueError("event requires safe nonnegative time and a v3 kind")
    if "traceSchema" in value and value["traceSchema"] != 3:
        raise ValueError("event traceSchema must be 3")


@dataclasses.dataclass(frozen=True)
class AppendResult:
    accepted: bool
    durable_seq: int
    blocked_ns: int = 0
    gap: dict | None = None


@dataclasses.dataclass(frozen=True)
class Verification:
    valid: bool
    complete: bool
    closed: bool
    source_closed: bool
    durable_seq: int
    event_count: int
    segment_count: int
    bytes_verified: int
    gaps: tuple
    index_sha256: str | None = None

    def as_dict(self):
        return {"schema": 1, "status": "complete" if self.complete else "incomplete" if self.valid else "invalid",
                "valid": self.valid, "complete": self.complete, "closed": self.closed,
                "sourceClosed": self.source_closed, "durableSeq": self.durable_seq,
                "eventCount": self.event_count, "segmentCount": self.segment_count,
                "bytesVerified": self.bytes_verified, "indexSha256": self.index_sha256,
                "gaps": list(self.gaps), "actualDatabaseExecution": False}


def _sync_directory(folder):
    if os.name == "nt":
        return "not-available-in-Windows-stdlib"
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return "fsync"


class _Identities:
    """Rebuildable disk index; transaction facts remain in the raw segments."""
    def __init__(self, path, *, existing=False, byte_limit=None):
        self.path = Path(path)
        if not existing and self.path.exists():
            raise JournalError("Transaction index already exists")
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        if byte_limit is not None:
            if type(byte_limit) is not int or byte_limit<8192 or byte_limit%4096:
                self.connection.close(); raise JournalError("Invalid SQLite page budget")
            self.connection.execute("PRAGMA page_size=4096")
            page_size=self.connection.execute("PRAGMA page_size").fetchone()[0]
            pages=byte_limit//page_size
            actual=self.connection.execute("PRAGMA max_page_count="+str(pages)).fetchone()[0]
            if actual!=pages or actual*page_size>byte_limit:
                self.connection.close(); raise JournalError("Existing SQLite exceeds the requested page budget")
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA trusted_schema=OFF")
        if not existing:
            self.connection.execute("CREATE TABLE transactions(tx TEXT PRIMARY KEY, begin_seq INTEGER NOT NULL) WITHOUT ROWID")
            self.connection.commit()
        self.count = self.connection.execute("SELECT count(*) FROM transactions").fetchone()[0]

    def add(self, tx, seq):
        try:
            self.connection.execute("INSERT INTO transactions VALUES (?,?)", (tx, seq))
            self.count += 1
            return True
        except sqlite3.IntegrityError:
            return False

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def _commit_abort_response(response, request):
    if not isinstance(response, dict) or not _integer(response.get("request"), 1) or response.get("request") != request:
        return False
    if set(response) == {"request", "commandTag"}:
        return response["commandTag"] == "ROLLBACK"
    return (set(response) == {"request", "sqlstate", "diagnosticSqlstate", "transactionStatus"}
            and response["sqlstate"] in ("40001", "40P01")
            and response["diagnosticSqlstate"] == response["sqlstate"]
            and response["transactionStatus"] == "IDLE")


def _lifecycle(kind, tx, active, requested, identities, gap, seq, response=None):
    if kind not in ("begin", "commit_ok", "rollback_ok", "disconnect", "commit_request"):
        return
    if not isinstance(tx, str) or not 1 <= len(tx) <= 256:
        gap("transaction_identity_missing", "A lifecycle event lacked a bounded transaction identity.")
        return
    if kind == "begin":
        if not identities.add(tx, seq):
            gap("transaction_tracking_incomplete", "A transaction identity was reused.")
        elif len(active) >= 4096:
            gap("transaction_tracking_incomplete", "Active transaction tracking budget exhausted.")
        else:
            active.add(tx)
    elif tx not in active:
        gap("transaction_begin_missing", "A lifecycle outcome/request had no recorded active transaction.")
    elif kind == "commit_request":
        if tx in requested:
            gap("duplicate_commit_request", "A transaction has multiple COMMIT requests.")
        requested[tx] = seq
    elif kind == "commit_ok":
        if tx not in requested:
            gap("commit_request_missing", "COMMIT acknowledgement had no recorded request.")
        active.discard(tx)
        requested.pop(tx, None)
    elif kind == "rollback_ok":
        if tx in requested:
            # An idle ROLLBACK after a lost COMMIT acknowledgement cannot tell
            # whether that transaction committed. Keep its source unresolved.
            if _commit_abort_response(response, requested[tx]):
                active.discard(tx)
                requested.pop(tx, None)
            else:
                gap("transaction_outcome_unknown", "ROLLBACK after COMMIT request does not resolve the original COMMIT outcome.")
        else:
            if response is not None:
                gap("commit_response_without_request", "A COMMIT response referenced no preceding request.")
            active.discard(tx)
    elif kind == "disconnect":
        gap("transaction_outcome_unknown", "A connection disappeared while its transaction outcome was unresolved.")


class SegmentedJournal:
    """Single owned writer. append accepted does not mean durable yet.

    flush()/checkpoint()/close() wait for fsync and the bound index. Queue
    accounting includes the record currently being written. Blocking and failure
    remain visible in results/statistics; append never silently drops a record.
    """

    def __init__(self, path, *, max_queue_bytes=4 * 1024 * 1024,
                 segment_bytes=16 * 1024 * 1024, flush_bytes=256 * 1024,
                 flush_interval=0.1, max_record_bytes=512 * 1024,
                 max_total_bytes=1024 * 1024 * 1024, _resume=None,
                 experimental_budget=None, transaction_index_bytes=None):
        self.experimental_budget=profile(experimental_budget)
        self.transaction_index_bytes=sqlite_limit(transaction_index_bytes,self.experimental_budget)
        if self.experimental_budget and max_total_bytes>LIMITS["journalBytes"]:
            raise ValueError("Journal total exceeds experimental ceiling")
        for value in (max_queue_bytes, segment_bytes, flush_bytes, max_record_bytes, max_total_bytes):
            if not _integer(value, 128):
                raise ValueError("journal byte limits must be safe integers >=128")
        if not 0 < flush_interval <= 60 or not max_record_bytes <= min(max_queue_bytes, segment_bytes, HARD_RECORD_BYTES):
            raise ValueError("invalid flush interval or record/queue/segment limits")
        self.path = Path(path).resolve()
        if _resume is None:
            self.path.mkdir(parents=True, exist_ok=False)
        self.max_queue_bytes, self.segment_bytes = max_queue_bytes, segment_bytes
        self.flush_bytes, self.flush_interval = flush_bytes, float(flush_interval)
        self.max_record_bytes, self.max_total_bytes = max_record_bytes, max_total_bytes
        self._cv, self._append_lock = threading.Condition(threading.RLock()), threading.RLock()
        self._capacity = CapacityQueue(max_queue_bytes)
        self._queue, self._error = self._capacity.items, None
        self._closing, self._closed, self._source_closed = False, False, False
        self._invalidated = False
        self._requested_source_closed = False
        self._last_seq = self._written_seq = self._durable_seq = 0
        self._last_time = self._written_time = self._written_count = self._accepted_bytes = 0
        self._segments, self._gaps, self._active = [], [], set()
        self._commit_requested = {}
        self._refs = {"activeTransactions": [], "unreadResults": [], "versionSources": []}
        self._stats = {"acceptedRecords": 0, "durableRecords": 0, "backpressureCount": 0,
                       "backpressureNs": 0, "maxQueueBytes": 0, "fsyncCount": 0, "bytesWritten": 0}
        self._revision = self._flushed_generation = self._flush_generation = self._flush_target_seq = 0
        self._metadata_dirty, self._pending_bytes = True, 0
        self._file, self._current, self._hash = None, None, None
        self._identities_closed = False
        self._nonce = str(uuid.uuid4())
        self._lock_payload = _json({"writer": self._nonce, "pid": os.getpid()})
        if _resume is not None:
            self._segments = [dict(item) for item in _resume["segments"]]
            self._last_seq = self._written_seq = self._durable_seq = _resume["durableSeq"]
            self._last_time = self._written_time = _resume["lastTime"]
            self._written_count = sum(item["eventCount"] for item in self._segments)
            self._accepted_bytes = sum(item["bytes"] for item in self._segments)
            self._stats.update(_resume["stats"])
            self._refs = _resume["references"]
        lock = None
        try:
            lock = (self.path / LOCK).open("xb")
            lock.write(self._lock_payload)
            lock.flush()
            os.fsync(lock.fileno())
            lock.close()
            self._identities = _Identities(self.path / TRANSACTIONS, existing=_resume is not None, byte_limit=self.transaction_index_bytes)
            self._persist_index(False)
        except BaseException:
            if lock is not None and not lock.closed:
                lock.close()
            if hasattr(self, "_identities"):
                self._identities.close()
            # A failed initialization/resume must not erase the only durable
            # indication of interruption when its failure marker cannot be
            # written. Explicit recovery is a separate, unfinished operation.
            raise
        self._last_sync = time.monotonic()
        self._thread = threading.Thread(target=self._worker, name="mtw-journal-v3", daemon=True)
        self._thread.start()

    # Preserve existing fault-injection surfaces while sharing byte accounting.
    @property
    def _queued_bytes(self): return self._capacity.queued_bytes
    @_queued_bytes.setter
    def _queued_bytes(self, value): self._capacity.queued_bytes = value
    @property
    def _reserved_bytes(self): return self._capacity.reserved_bytes
    @_reserved_bytes.setter
    def _reserved_bytes(self, value): self._capacity.reserved_bytes = value

    @classmethod
    def reopen(cls, path, *, exclusive_continuation=False, **options):
        if not exclusive_continuation:
            raise JournalError("Reopening for append requires an explicit uninterrupted exclusive-source continuation assertion")
        reader = JournalReader(path, experimental_budget=options.get("experimental_budget"))
        if not reader.verify().complete:
            raise JournalError("Only a complete sealed source can be reopened; crash recovery is not inferred")
        index, _ = reader._index()
        original = index["limits"]
        if index.get("experimentalBudget"):
            options.setdefault("transaction_index_bytes",index["transactionIndex"]["maxBytes"])
        options = {**{"max_queue_bytes": original["queueBytes"], "segment_bytes": original["segmentBytes"],
                      "flush_bytes": original["flushBytes"], "flush_interval": original["flushIntervalSeconds"],
                      "max_record_bytes": original["recordBytes"], "max_total_bytes": original["totalBytes"]}, **options}
        return cls(path, _resume=index, **options)

    def _release_lock(self):
        try:
            file = self.path / LOCK
            if not file.is_symlink():
                with file.open("rb") as stream:
                    own = stream.read(len(self._lock_payload) + 1) == self._lock_payload
                if own:
                    file.unlink()
        except FileNotFoundError:
            pass

    def _gap(self, code, message):
        with self._cv:
            item = {"code": code, "message": message}
            if item not in self._gaps:
                if len(self._gaps) >= 64:
                    item = {"code": "gap_budget_exhausted", "message": "Additional journal gaps omitted; completeness is unavailable."}
                    if item in self._gaps:
                        return item
                self._gaps.append(item)
                self._revision += 1
                self._metadata_dirty = True
                self._cv.notify_all()
            return item

    def append(self, event):
        started, blocked = None, 0
        with self._append_lock:
            with self._cv:
                if self._closing or self._closed or self._error is not None:
                    if self._closing or self._closed:
                        self.invalidate(code="journal_append_after_close", message="A record append was attempted after this journal window closed.")
                    gap = self._gap("journal_not_writable", "A record arrived after close or an IO failure.")
                    return AppendResult(False, self._durable_seq, gap=gap)
                # Reserve one bounded record before making a mutable-container
                # copy/JSON string. Waiting appenders retain no encoded records.
                while not self._capacity.can_reserve(self.max_record_bytes) and self._error is None:
                    if started is None:
                        started = time.monotonic_ns()
                    self._cv.wait()
                if started is not None:
                    blocked = time.monotonic_ns() - started
                    self._stats["backpressureCount"] += 1
                    self._stats["backpressureNs"] += blocked
                if self._error is not None:
                    return AppendResult(False, self._durable_seq, blocked,
                                        self._gap("journal_write_failed", "Writer IO failed; record was not accepted."))
                self._capacity.reserve(self.max_record_bytes)
                self._stats["maxQueueBytes"] = max(self._stats["maxQueueBytes"], self._queued_bytes + self._reserved_bytes)
            try:
                copied = _bounded_copy(event, self.max_record_bytes - 1)
                _event(copied)
                line = _json(copied) + b"\n"
                if len(line) > self.max_record_bytes:
                    raise ValueError("encoded record budget")
                with self._cv:
                    if self._error is not None:
                        return AppendResult(False, self._durable_seq, blocked,
                            self._gap("journal_write_failed", "Writer IO failed during record encoding; record was not accepted."))
                    if copied["seq"] <= self._last_seq or copied["time"] < self._last_time:
                        raise ValueError("sequence/time regression")
                    if self._accepted_bytes + len(line) > self.max_total_bytes:
                        raise ValueError("total disk evidence budget")
                    if copied["seq"] != self._last_seq + 1:
                        self._gap("missing_sequence", "A capture sequence was skipped before append; no complete conclusion is available.")
                    if self._last_seq == 0 and copied["kind"] != "snapshot":
                        self._gap("missing_snapshot", "The journal does not begin with a snapshot event.")
                    self._last_seq, self._last_time = copied["seq"], copied["time"]
                    self._accepted_bytes += len(line)
                    self._stats["acceptedRecords"] += 1
                    self._source_closed = False
                    self._capacity.enqueue((line, copied["seq"], copied["time"], copied["kind"], copied.get("tx"), copied.get("commitResponse")), len(line))
                    self._revision += 1
                    self._metadata_dirty = True
                    self._cv.notify_all()
                    return AppendResult(True, self._durable_seq, blocked)
            except Exception:
                with self._cv:
                    gap = self._gap("record_rejected", "Record exceeded its budget or violated safe JSON/sequence/time/kind requirements.")
                    return AppendResult(False, self._durable_seq, blocked, gap)
            finally:
                with self._cv:
                    self._capacity.release_reservation(self.max_record_bytes)
                    self._cv.notify_all()

    @property
    def stats(self):
        with self._cv:
            return {**self._stats, "queueBytes": self._queued_bytes + self._reserved_bytes, "durableSeq": self._durable_seq,
                    "lastAcceptedSeq": self._last_seq}

    def set_references(self, *, active_transactions=(), unread_results=(), version_sources=()):
        values = {"activeTransactions": active_transactions, "unreadResults": unread_results, "versionSources": version_sources}
        result, remaining = {}, 256 * 1024
        for name, items in values.items():
            copied = []
            for value in items:
                if len(copied) >= 4096 or not isinstance(value, str) or not 1 <= len(value) <= 256:
                    raise ValueError("Reference labels must be 1..256 characters, at most 4096 per category")
                _bounded_copy(value, remaining)
                remaining -= len(_json(value)) + 1
                if remaining < 0:
                    raise ValueError("Reference aggregate byte budget")
                copied.append(value)
            result[name] = sorted(set(copied))
        with self._cv:
            if self._closing or self._closed:
                raise JournalError("References cannot change after close")
            self._refs = result
            self._revision += 1
            self._metadata_dirty = True
            self._cv.notify_all()

    def flush(self):
        with self._cv:
            self._flush_generation += 1
            generation, target = self._flush_generation, self._last_seq
            self._flush_target_seq = max(self._flush_target_seq, target)
            self._cv.notify_all()
            while self._error is None and (self._durable_seq < target or self._flushed_generation < generation):
                if self._closed:
                    break
                self._cv.wait()
            if self._error is not None:
                raise JournalIOError("Journal persistence failed: " + type(self._error).__name__) from self._error
            return self._durable_seq

    def checkpoint(self, *, source_closed=False):
        with self._append_lock:
            if self._closing or self._closed:
                raise JournalError("A closed journal cannot be checkpointed")
            self.flush()
            with self._cv:
                if source_closed and (self._active or self._refs["activeTransactions"] or self._refs["unreadResults"]):
                    self._gap("source_references_active", "Source closure was requested with active transactions or unread results.")
                    self._source_closed = False
                else:
                    self._source_closed = bool(source_closed)
                self._revision += 1
                self._metadata_dirty = True
            self.flush()
        return self._verified_status()

    def close(self, *, source_closed=False):
        with self._append_lock:
            with self._cv:
                if not self._closing and not self._closed:
                    self._requested_source_closed = bool(source_closed)
                    self._closing = True
                    self._cv.notify_all()
            self._thread.join()
            if self._error is not None:
                # A sealed index replacement may have succeeded just before a
                # directory-sync error, while the disk also rejects the failure
                # marker. Retain the already durable lock on every error path.
                raise JournalIOError("Journal persistence failed: " + type(self._error).__name__) from self._error
            self._release_lock()
        return self._verified_status()

    def _verified_status(self):
        status = JournalReader(self.path, experimental_budget=self.experimental_budget).verify()
        if self._invalidated:
            gaps = list(status.gaps)
            for gap in self._gaps:
                if gap not in gaps:
                    gaps.append(gap)
            status = dataclasses.replace(status, complete=False, gaps=tuple(gaps))
        return status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()  # Never infer that all database sources stopped.

    def _new_segment(self):
        if len(self._segments) >= MAX_SEGMENTS:
            raise JournalIOError("Segment index budget exhausted")
        name = "segment-%06d.jsonl" % (len(self._segments) + 1)
        self._file = (self.path / name).open("xb", buffering=0)
        self._current = {"name": name, "bytes": 0, "sha256": hashlib.sha256().hexdigest(),
                         "firstSeq": None, "lastSeq": None, "eventCount": 0}
        self._hash = hashlib.sha256()
        self._segments.append(self._current)

    def _write_line(self, line):
        # FileIO can legally perform a short write. Charge/ack only a full line.
        view = memoryview(line)
        while view:
            count = self._file.write(view)
            if not count:
                raise OSError("zero-byte journal write")
            view = view[count:]

    def _transaction(self, kind, tx, seq, response):
        _lifecycle(kind, tx, self._active, self._commit_requested, self._identities, self._gap, seq, response)

    def _persist_index(self, closed):
        # SQLite synchronous=FULL commits its DELETE journal before a tail is
        # acknowledged. The DB is a verified cache, never a source of DB facts.
        if not self._identities_closed:
            self._identities.commit()
        with self._cv:
            revision, generation = self._revision, self._flush_generation
            payload = {"indexSchema": 1, "traceSchema": 3, "closed": bool(closed),
                "sourceClosed": self._source_closed, "durableSeq": self._written_seq,
                "lastTime": self._written_time, "eventCount": self._written_count,
                "segments": [dict(item) for item in self._segments], "gaps": list(self._gaps),
                "activeTransactions": sorted(self._active), "references": self._refs,
                "commitRequests": sorted(self._commit_requested),
                "transactionIndex": {"name": TRANSACTIONS, "authoritative": False,
                    "durableThroughSeq": self._written_seq, "entries": self._identities.count,
                    "journalMode": "DELETE", "synchronous": "FULL"},
                "limits": {"queueBytes": self.max_queue_bytes, "segmentBytes": self.segment_bytes,
                    "flushBytes": self.flush_bytes, "flushIntervalSeconds": self.flush_interval,
                    "recordBytes": self.max_record_bytes, "totalBytes": self.max_total_bytes},
                "stats": {**self._stats, "durableRecords": self._written_count},
                "retention": {"deletionImplemented": False, "policy": "retain all source/version-chain records"},
                "directorySync": "not-available-in-Windows-stdlib" if os.name == "nt" else "fsync"}
            if self.experimental_budget:
                payload["experimentalBudget"]=self.experimental_budget
                payload["transactionIndex"]["maxBytes"]=self.transaction_index_bytes
            payload["indexSha256"] = hashlib.sha256(_json(payload)).hexdigest()
            encoded = _json(payload) + b"\n"
            if len(encoded) > MAX_INDEX_BYTES:
                raise JournalIOError("Index byte budget exhausted")
        temporary = self.path / (".journal-index-" + self._nonce + ".tmp")
        with temporary.open("wb") as file:
            remaining = memoryview(encoded)
            while remaining:
                count = file.write(remaining)
                if type(count) is not int or not 0 < count <= len(remaining):
                    raise JournalIOError("Incomplete journal index write")
                remaining = remaining[count:]
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, self.path / INDEX)
        _sync_directory(self.path)
        with self._cv:
            self._durable_seq = self._written_seq
            self._stats["durableRecords"] = self._written_count
            self._metadata_dirty = self._revision != revision
            self._flushed_generation = generation
            self._cv.notify_all()

    def _sync_tail(self, closed=False):
        if self._file is not None:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._stats["fsyncCount"] += 1
        self._persist_index(closed)
        self._pending_bytes = 0
        self._last_sync = time.monotonic()

    def _worker(self):
        try:
            while True:
                with self._cv:
                    while not self._queue:
                        explicit = flush_pending(self._flush_generation, self._flushed_generation, self._durable_seq, self._flush_target_seq)
                        due = sync_due(self._metadata_dirty, self._last_sync, time.monotonic(), self.flush_interval)
                        if self._closing or explicit or due:
                            break
                        wait = sync_wait(self._metadata_dirty, self._last_sync, time.monotonic(), self.flush_interval)
                        self._cv.wait(wait)
                    item = self._capacity.pop()
                if item is not None:
                    line, seq, event_time, kind, tx, response = item
                    if self._current is not None and self._current["bytes"] + len(line) > self.segment_bytes:
                        self._sync_tail()
                        self._file.close()
                        self._file, self._current = None, None
                    if self._file is None:
                        self._new_segment()
                    self._write_line(line)
                    self._hash.update(line)
                    self._current.update(bytes=self._current["bytes"] + len(line), sha256=self._hash.hexdigest(),
                        firstSeq=seq if self._current["firstSeq"] is None else self._current["firstSeq"],
                        lastSeq=seq, eventCount=self._current["eventCount"] + 1)
                    with self._cv:
                        self._transaction(kind, tx, seq, response)
                        self._written_seq, self._written_time, self._written_count = seq, event_time, self._written_count + 1
                        self._capacity.complete(len(line))
                        self._stats["bytesWritten"] += len(line)
                        self._pending_bytes += len(line)
                        self._metadata_dirty = True
                        self._cv.notify_all()
                with self._cv:
                    drained = not self._queue
                    closing = self._closing and drained
                    explicit = flush_pending(self._flush_generation, self._flushed_generation, self._durable_seq, self._flush_target_seq)
                    due = sync_due(self._metadata_dirty, self._last_sync, time.monotonic(), self.flush_interval)
                    sync = should_sync(closing, explicit, self._metadata_dirty, self._pending_bytes, self.flush_bytes, self._last_sync, time.monotonic(), self.flush_interval)
                    if closing:
                        blocked = self._active or self._refs["activeTransactions"] or self._refs["unreadResults"]
                        self._source_closed = self._requested_source_closed and not blocked
                        if self._requested_source_closed and blocked:
                            self._gap("source_references_active", "Source closure refused while transactions or unread results still refer to retained records.")
                if closing:
                    # Do not publish a sealed index until both owned data
                    # handles have closed successfully after synchronous sync.
                    self._sync_tail(False)
                    if self._file is not None:
                        self._file.close()
                        self._file = None
                    self._identities.close()
                    self._identities_closed = True
                    self._persist_index(True)
                    return
                if sync:
                    self._sync_tail()
        except BaseException as error:
            with self._cv:
                self._error = error
                self._gap("journal_write_failed", "Writer IO/index synchronization failed (" + type(error).__name__ + "); durable evidence may be partial.")
                self._queue.clear()
                self._queued_bytes = 0
                self._cv.notify_all()
            # Best effort only. An inability to persist this marker is still
            # fail-closed because the old index remains unsealed or absent.
            try:
                with (self.path / "journal-failure.json").open("xb") as file:
                    file.write(_json({"code": "journal_write_failed", "errorClass": type(error).__name__}))
                    file.flush()
                    os.fsync(file.fileno())
            except Exception:
                pass
        finally:
            try:
                if self._file is not None:
                    self._file.close()
                if not self._identities_closed:
                    self._identities.close()
            except BaseException as close_error:
                with self._cv:
                    self._error = self._error or close_error
                    self._gap("journal_write_failed", "Owned journal handles failed to close; storage remains unsealed.")
            with self._cv:
                self._closed = True
                self._cv.notify_all()

    def prune(self, *, before_seq):
        if not _integer(before_seq):
            raise ValueError("before_seq must be a safe nonnegative integer")
        status = self._verified_status()
        return {"implemented": False, "deleted": [], "beforeSeq": before_seq,
                "reason": "active/unclosed source references" if not status.complete else "version-chain closure deletion proof is not implemented; all records retained",
                "complete": status.complete}

    def archive(self, destination):
        if self._invalidated:
            raise JournalVerificationError("This journal instance was invalidated after closure")
        return JournalReader(self.path, experimental_budget=self.experimental_budget).archive(destination)

    def invalidate(self, *, code="capture_window_invalidated", message="Activity was observed after the capture window was sealed."):
        """Persist a separate fail-closed signal without rewriting sealed bytes.

        False means the marker could not be synchronized. The caller must also
        retain its own permanent invalidation state when storage is unwritable.
        """
        if not isinstance(code, str) or not 1 <= len(code) <= 128 or not isinstance(message, str) or not 1 <= len(message) <= 1024:
            raise ValueError("Invalidation descriptions must be bounded text")
        self._invalidated = True
        self._gap(code, message)
        target = self.path / INVALIDATED
        try:
            with target.open("xb") as file:
                # Open first: even a later index/read/write failure leaves a
                # recognizable fail-closed marker where the filesystem permits.
                binding = JournalReader(self.path, experimental_budget=self.experimental_budget)._index()[1]
                file.write(_json({"schema": 1, "code": code, "message": message, "indexSha256": binding}))
                file.flush()
                os.fsync(file.fileno())
            _sync_directory(self.path)
            return True
        except FileExistsError:
            return True
        except Exception:
            return False


class JournalReader:
    """Two streaming passes: verify bindings first, then bounded event iteration."""

    def __init__(self, path, *, experimental_budget=None):
        self.experimental_budget=profile(experimental_budget)
        self.path = Path(path).resolve()

    def _marker_exists(self, name):
        # lstat sees dangling symlinks without following them. Permission and
        # other inspection errors propagate to fail-closed verification.
        try:
            (self.path / name).lstat()
            return True
        except FileNotFoundError:
            return False

    def _index(self):
        target = self.path / INDEX
        if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_INDEX_BYTES:
            raise JournalVerificationError("Index absent, unsafe or over budget")
        with target.open("rb") as stream:
            raw = stream.read(MAX_INDEX_BYTES + 1)
        if len(raw) > MAX_INDEX_BYTES:
            raise JournalVerificationError("Index grew over its byte budget")
        index = _loads(raw)
        if not isinstance(index, dict):
            raise JournalVerificationError("Index is not an object")
        expected = index.get("indexSha256")
        actual = hashlib.sha256(_json({k: v for k, v in index.items() if k != "indexSha256"})).hexdigest()
        if expected != actual or index.get("indexSchema") != 1 or index.get("traceSchema") != 3:
            raise JournalVerificationError("Index checksum/schema mismatch")
        selected=authorize(index.get("experimentalBudget"),self.experimental_budget)
        segments = index.get("segments")
        if not isinstance(segments, list) or len(segments) > MAX_SEGMENTS:
            raise JournalVerificationError("Index segment budget")
        if not isinstance(index.get("limits"), dict) or not _integer(index["limits"].get("recordBytes"), 128, HARD_RECORD_BYTES):
            raise JournalVerificationError("Record limit missing or unsafe")
        limits = index["limits"]
        if (any(not _integer(limits.get(n), 128) for n in ("queueBytes", "segmentBytes", "flushBytes", "totalBytes"))
                or limits["recordBytes"] > min(limits["queueBytes"], limits["segmentBytes"])
                or type(limits.get("flushIntervalSeconds")) not in (int, float)
                or not 0 < limits["flushIntervalSeconds"] <= 60):
            raise JournalVerificationError("Index limits invalid")
        if selected and limits["totalBytes"]>LIMITS["journalBytes"]:
            raise JournalVerificationError("Journal exceeds experimental reader ceiling")
        if not all(_integer(index.get(name)) for name in ("durableSeq", "lastTime", "eventCount")):
            raise JournalVerificationError("Index tail counters invalid")
        for name in ("activeTransactions", "commitRequests"):
            labels = index.get(name)
            if (not isinstance(labels, list) or len(labels) > 4096
                    or any(not isinstance(v, str) or not 1 <= len(v) <= 256 for v in labels)
                    or labels != sorted(set(labels))):
                raise JournalVerificationError("Index transaction labels invalid")
        txindex = index.get("transactionIndex")
        if (not isinstance(txindex, dict) or txindex.get("name") != TRANSACTIONS
                or txindex.get("authoritative") is not False or txindex.get("journalMode") != "DELETE"
                or txindex.get("synchronous") != "FULL" or not _integer(txindex.get("entries"))
                or txindex.get("durableThroughSeq") != index["durableSeq"]):
            raise JournalVerificationError("Disk transaction index binding invalid")
        if selected:
            if type(txindex.get("maxBytes")) is not int: raise JournalVerificationError("Missing experimental SQLite budget")
            sqlite_limit(txindex["maxBytes"],selected)
        refs = index.get("references")
        if not isinstance(refs, dict) or set(refs) != {"activeTransactions", "unreadResults", "versionSources"}:
            raise JournalVerificationError("Reference tracking missing")
        _bounded_copy(refs, 256 * 1024)
        for labels in refs.values():
            if (not isinstance(labels, list) or len(labels) > 4096
                    or any(not isinstance(v, str) or not 1 <= len(v) <= 256 for v in labels)
                    or labels != sorted(set(labels))):
                raise JournalVerificationError("Index reference labels invalid")
        for number, item in enumerate(segments, 1):
            if (not isinstance(item, dict) or item.get("name") != "segment-%06d.jsonl" % number
                    or not _integer(item.get("bytes"), 1) or not _integer(item.get("eventCount"), 1)
                    or not _integer(item.get("firstSeq"), 1) or not _integer(item.get("lastSeq"), 1)
                    or not isinstance(item.get("sha256"), str) or not re.fullmatch("[0-9a-f]{64}", item["sha256"])):
                raise JournalVerificationError("Invalid segment binding")
            if item["bytes"] > limits["segmentBytes"]:
                raise JournalVerificationError("Segment exceeds the declared byte limit")
        if sum(item["bytes"] for item in segments) > limits["totalBytes"]:
            raise JournalVerificationError("Segments exceed the declared total byte limit")
        return index, hashlib.sha256(raw).hexdigest()

    def _segment_events(self, item, limit):
        path = self.path / item["name"]
        if path.is_symlink() or not path.resolve().is_relative_to(self.path):
            raise JournalVerificationError("Unsafe segment path")
        digest, count, consumed, first, last = hashlib.sha256(), 0, 0, None, None
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size != item["bytes"]:
                raise JournalVerificationError("Missing/truncated/unindexed segment bytes")
            while True:
                line = stream.readline(limit + 1)
                if not line:
                    break
                if len(line) > limit or not line.endswith(b"\n"):
                    raise JournalVerificationError("Partial/over-budget record")
                digest.update(line)
                consumed += len(line)
                event = _loads(line)
                _event(event)
                _bounded_copy(event, limit)
                first = event["seq"] if first is None else first
                last, count = event["seq"], count + 1
                yield event
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise JournalVerificationError("Segment changed during read")
        if (consumed, digest.hexdigest(), count, first, last) != (item["bytes"], item["sha256"], item["eventCount"], item["firstSeq"], item["lastSeq"]):
            raise JournalVerificationError("Segment hash/size/sequence/count mismatch")

    def verify(self):
        gaps, count, consumed, last, last_time, segment_count = [], 0, 0, 0, 0, 0
        active, requested = set(), {}
        scratch = identities = None

        def gap(code, message):
            item = {"code": code, "message": message}
            if item not in gaps:
                if len(gaps) >= 64:
                    item = {"code": "gap_budget_exhausted", "message": "Additional verification gaps omitted; completeness is unavailable."}
                if item not in gaps:
                    gaps.append(item)

        closed = source_closed = False
        index_sha = None
        try:
            index, index_sha = self._index()
            scratch = tempfile.TemporaryDirectory(prefix="mtw-journal-verify-", dir=os.environ.get("MTW_JOURNAL_SCRATCH"))
            identities = _Identities(Path(scratch.name) / TRANSACTIONS, byte_limit=index["transactionIndex"].get("maxBytes") if index.get("experimentalBudget") else None)
            if type(index.get("closed")) is not bool or type(index.get("sourceClosed")) is not bool:
                raise JournalVerificationError("Index closure flags invalid")
            closed, source_closed = index["closed"], index["sourceClosed"]
            raw_gaps = index.get("gaps")
            if not isinstance(raw_gaps, list) or len(raw_gaps) > 65:
                raise JournalVerificationError("Gap budget invalid")
            for original_gap in raw_gaps:
                if not isinstance(original_gap, dict) or set(original_gap) != {"code", "message"} or not all(isinstance(v, str) and v for v in original_gap.values()):
                    raise JournalVerificationError("Invalid gap")
                # Preserve original coverage gaps and bound generated gaps too.
                if original_gap not in gaps:
                    gaps.append(original_gap)
            for item in index["segments"]:
                for event in self._segment_events(item, index["limits"]["recordBytes"]):
                    if event["seq"] != last + 1:
                        gap("missing_sequence", "Verified event sequence is not contiguous.")
                    if event["seq"] <= last or event["time"] < last_time:
                        raise JournalVerificationError("Event sequence/time regressed")
                    if not count and event["kind"] != "snapshot":
                        gap("missing_snapshot", "First verified event is not a snapshot.")
                    _lifecycle(event["kind"], event.get("tx"), active, requested, identities, gap, event["seq"], event.get("commitResponse"))
                    last, last_time, count = event["seq"], event["time"], count + 1
                consumed += item["bytes"]
                segment_count += 1
            if index.get("durableSeq") != last or index.get("eventCount") != count or index.get("lastTime") != last_time:
                raise JournalVerificationError("Index tail/count mismatch")
            if index["activeTransactions"] != sorted(active) or index["commitRequests"] != sorted(requested):
                raise JournalVerificationError("Index lifecycle state does not match actual records")
            self._verify_identities(index, identities)
            expected_names = {item["name"] for item in index["segments"]}
            if {p.name for p in self.path.glob("segment-*.jsonl")} != expected_names:
                raise JournalVerificationError("Unindexed or missing segment")
            if not count:
                gap("missing_snapshot", "Empty evidence has no capture snapshot.")
            if self._marker_exists(LOCK):
                gap("writer_lock_present", "Writer is active or an interrupted writer requires explicit recovery.")
            if self._marker_exists("journal-failure.json"):
                gap("journal_write_failed", "A persisted writer failure marker is present.")
            if self._marker_exists(INVALIDATED):
                gap("capture_window_invalidated", "Post-seal activity or another invalidation signal prevents complete source coverage.")
            if index.get("activeTransactions") or any(index.get("references", {}).get(k) for k in ("activeTransactions", "unreadResults")):
                gap("source_references_active", "Active transactions or unread results still refer to retained evidence.")
            if not closed or not source_closed:
                gap("source_unsealed", "Journal and explicit source window have not both been sealed.")
            return Verification(True, not gaps, closed, source_closed, last, count, segment_count, consumed, tuple(gaps), index_sha)
        except Exception as error:
            gap("journal_integrity_failed", "Journal verification failed (" + type(error).__name__ + ").")
            return Verification(False, False, closed, source_closed, last, count, segment_count, consumed, tuple(gaps), index_sha)
        finally:
            if identities is not None:
                identities.close()
            if scratch is not None:
                scratch.cleanup()

    def _verify_identities(self, index, expected):
        path = self.path / TRANSACTIONS
        maximum=index["transactionIndex"]["maxBytes"] if index.get("experimentalBudget") else 2*1024**3
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            raise JournalVerificationError("Transaction index absent/unsafe/over budget")
        if any((self.path / (TRANSACTIONS + suffix)).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise JournalVerificationError("Transaction cache has an unsealed SQLite sidecar")
        with path.open("rb") as header:
            raw_header = header.read(20)
        if raw_header[:16] != b"SQLite format 3\x00" or raw_header[18:20] != b"\x01\x01":
            raise JournalVerificationError("Transaction cache is not a DELETE-mode SQLite file")
        if expected.count != index["transactionIndex"]["entries"]:
            raise JournalVerificationError("Transaction index count differs from raw facts")
        expected.commit()
        actual = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            actual.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4096)
            actual.execute("PRAGMA trusted_schema=OFF")
            if actual.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                raise JournalVerificationError("Transaction cache journal mode differs from the owned DELETE index")
            # Fixed generated schema; reject a substituted view or triggers.
            schema = actual.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            if schema != [("table", "transactions", "CREATE TABLE transactions(tx TEXT PRIMARY KEY, begin_seq INTEGER NOT NULL) WITHOUT ROWID")]:
                raise JournalVerificationError("Transaction cache schema differs from the owned index")
            expected_rows = expected.connection.execute("SELECT tx,begin_seq FROM transactions ORDER BY tx")
            actual_rows = actual.execute("SELECT tx,begin_seq FROM transactions ORDER BY tx")
            for left, right in itertools.zip_longest(expected_rows, actual_rows):
                if left != right:
                    raise JournalVerificationError("Transaction index row differs from raw segment facts")
        finally:
            actual.close()

    def iter_events(self, *, require_complete=True):
        status = self.verify()
        if not status.valid or require_complete and not status.complete:
            raise JournalVerificationError("Journal is not complete and verified" if require_complete else "Journal integrity failed")
        index, digest = self._index()
        if digest != status.index_sha256:
            raise JournalVerificationError("Index changed after verification")
        for item in index["segments"]:
            # Hash before yielding this segment, then check again during the
            # streaming pass. Already-yielded events must never be treated as a
            # complete history until the generator terminates successfully.
            for _ in self._segment_events(item, index["limits"]["recordBytes"]):
                pass
            yield from self._segment_events(item, index["limits"]["recordBytes"])
        if self._index()[1] != digest:
            raise JournalVerificationError("Index changed during iteration")
        if (self._marker_exists(LOCK) or self._marker_exists("journal-failure.json")
                or self._marker_exists(INVALIDATED)):
            raise JournalVerificationError("Writer/failure marker appeared during iteration")

    def archive(self, destination):
        status = self.verify()
        if not status.complete:
            raise JournalVerificationError("Archive requires complete verified storage and an explicitly sealed source window")
        destination = Path(destination).resolve()
        if destination.is_relative_to(self.path):
            raise ValueError("Archive destination must be outside the journal directory")
        index, digest = self._index()
        transaction_hash = hashlib.sha256()
        cache_size = (self.path / TRANSACTIONS).stat().st_size
        if cache_size > 2 * 1024 * 1024 * 1024:
            raise JournalVerificationError("Transaction cache grew beyond its disk budget")
        with (self.path / TRANSACTIONS).open("rb") as cache:
            remaining = cache_size
            while remaining:
                block = cache.read(min(65_536, remaining))
                if not block:
                    raise JournalVerificationError("Transaction cache changed during archive binding")
                transaction_hash.update(block)
                remaining -= len(block)
            if cache.read(1):
                raise JournalVerificationError("Transaction cache grew during archive binding")

        def put(archive, name, size, expected_hash):
            source, hashed, consumed = self.path / name, hashlib.sha256(), 0
            if source.is_symlink():
                raise JournalVerificationError("Unsafe archive source")
            with source.open("rb") as stream, archive.open(name, "w") as zipped:
                while consumed < size:
                    block = stream.read(min(65_536, size - consumed))
                    if not block:
                        raise JournalVerificationError("Archive source was truncated")
                    zipped.write(block)
                    hashed.update(block)
                    consumed += len(block)
                if stream.read(1) or hashed.hexdigest() != expected_hash:
                    raise JournalVerificationError("Archive source hash/size changed")

        index_size = (self.path / INDEX).stat().st_size
        if index_size > MAX_INDEX_BYTES:
            raise JournalVerificationError("Index grew beyond its byte budget")
        with destination.open("xb") as target:
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                put(archive, INDEX, index_size, digest)
                put(archive, TRANSACTIONS, cache_size, transaction_hash.hexdigest())
                for item in index["segments"]:
                    put(archive, item["name"], item["bytes"], item["sha256"])
            target.flush()
            os.fsync(target.fileno())
        if self._index()[1] != digest:
            raise JournalVerificationError("Source index changed during archive")
        with zipfile.ZipFile(destination) as archived:
            if hashlib.sha256(archived.read(INDEX)).hexdigest() != digest:
                raise JournalVerificationError("Archived index bytes changed")
            for item in index["segments"]:
                hashed, size = hashlib.sha256(), 0
                with archived.open(item["name"]) as stream:
                    for block in iter(lambda: stream.read(65_536), b""):
                        hashed.update(block)
                        size += len(block)
                if size != item["bytes"] or hashed.hexdigest() != item["sha256"]:
                    raise JournalVerificationError("Archived source segment mismatch")
            hashed = hashlib.sha256()
            with archived.open(TRANSACTIONS) as stream:
                for block in iter(lambda: stream.read(65_536), b""):
                    hashed.update(block)
            if hashed.hexdigest() != transaction_hash.hexdigest():
                raise JournalVerificationError("Archived transaction cache changed")
            # Re-run the semantic storage verifier on a bounded extraction of
            # exactly our fixed-name members. Hashing the main SQLite file alone
            # cannot establish that required rows were not left in an omitted WAL.
            expected_sizes = {INDEX: index_size, TRANSACTIONS: cache_size,
                              **{item["name"]: item["bytes"] for item in index["segments"]}}
            if len(archived.infolist()) != len(expected_sizes) or set(archived.namelist()) != set(expected_sizes):
                raise JournalVerificationError("Unexpected or duplicate archived members")
            with tempfile.TemporaryDirectory(prefix="mtw-archive-verify-", dir=os.environ.get("MTW_JOURNAL_SCRATCH")) as scratch:
                for name, size in expected_sizes.items():
                    if archived.getinfo(name).file_size != size:
                        raise JournalVerificationError("Archived member size binding changed")
                    with archived.open(name) as source, (Path(scratch) / name).open("xb") as target:
                        remaining = size
                        while remaining:
                            block = source.read(min(65_536, remaining))
                            if not block:
                                raise JournalVerificationError("Truncated archived member")
                            target.write(block)
                            remaining -= len(block)
                        if source.read(1):
                            raise JournalVerificationError("Over-budget archived member")
                if not JournalReader(scratch, experimental_budget=self.experimental_budget).verify().complete:
                    raise JournalVerificationError("Archived storage failed independent reconstruction")
        if not self.verify().complete:
            raise JournalVerificationError("Source no longer complete after archive")
        return {"path": str(destination), "complete": status.complete, "sourceFilesDeleted": False,
                "segments": len(index["segments"]), "indexSha256": digest, "verified": True,
                "archiveReconstructionVerified": True}

    def export(self, destination, *, clock_domain, exclusive_writers=False, max_bytes=8 * 1024 * 1024, sql_profiles=None):
        """Stream a complete disk journal into a new bounded v3 JSON envelope.

        The final name is atomically created via a no-overwrite hard link. A
        filesystem without hard-link support fails rather than publishing a
        partly written destination. The journal itself is never altered.
        """
        if self.experimental_budget and max_bytes>8*1024*1024:
            raise ValueError("Experimental storage does not extend the 8 MiB export limit")
        if not isinstance(clock_domain, str) or not 1 <= len(clock_domain) <= 256:
            raise ValueError("clock_domain must contain 1..256 characters")
        if type(exclusive_writers) is not bool or not _integer(max_bytes, 128):
            raise ValueError("invalid export scope/byte budget")
        profiles = None
        if sql_profiles is not None:
            if not isinstance(sql_profiles, list) or len(sql_profiles) > 16:
                raise ValueError("sql_profiles must be an array of at most 16 declared profiles")
            profiles = _bounded_copy(sql_profiles, min(max_bytes, 8 * 1024 * 1024), node_limit=200_000)
        if not self.verify().complete:
            raise JournalVerificationError("Only a complete verified journal can be exported")
        destination = Path(destination).resolve()
        if destination.is_relative_to(self.path):
            raise ValueError("Export destination must be outside the journal directory")
        if destination.exists():
            raise FileExistsError("Export destination already exists")
        temporary = destination.parent / ("." + destination.name + ".mtw-" + str(uuid.uuid4()) + ".tmp")
        size, digest = 0, hashlib.sha256()
        try:
            with temporary.open("xb") as target:
                def write(block):
                    nonlocal size
                    if size + len(block) > max_bytes:
                        raise JournalVerificationError("Export byte budget exceeded; select a source-closed window instead of truncating")
                    target.write(block)
                    digest.update(block)
                    size += len(block)

                write(b'{"traceSchema":3,"clockDomain":' + _json(clock_domain)
                      + b',"scope":{"exclusiveWriters":' + (b'true' if exclusive_writers else b'false') + b'}')
                if profiles is not None:
                    write(b',"sqlProfiles":' + _json(profiles))
                write(b',"events":[')
                separator = b""
                for event in self.iter_events():
                    write(separator + _json(event))
                    separator = b","
                write(b'],"gaps":[]}\n')
                target.flush()
                os.fsync(target.fileno())
            os.link(temporary, destination)
            _sync_directory(destination.parent)
            return {"bytes": size, "sha256": digest.hexdigest(), "complete": True,
                    "exclusiveWritersDeclared": exclusive_writers, "actualDatabaseExecution": False}
        finally:
            # Only this operation's uniquely named scratch file is removed.
            # An already published, fully fsynced output is retained on a later
            # directory-sync failure and no successful result is reported.
            if temporary.exists():
                temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify or export a bounded segmented v3 capture journal")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("directory")
    export = sub.add_parser("export")
    export.add_argument("directory")
    export.add_argument("--output", required=True)
    export.add_argument("--clock-domain", required=True)
    export.add_argument("--exclusive-writers", action="store_true")
    export.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    verify.add_argument("--experimental-budget",choices=[PROFILE])
    export.add_argument("--experimental-budget",choices=[PROFILE])
    args = parser.parse_args(argv)
    reader = JournalReader(args.directory, experimental_budget=args.experimental_budget)
    if args.command == "verify":
        status = reader.verify()
        print(json.dumps(status.as_dict(), ensure_ascii=False))
        return 0 if status.complete else 3 if status.valid else 2
    try:
        result = reader.export(args.output, clock_domain=args.clock_domain,
            exclusive_writers=args.exclusive_writers, max_bytes=args.max_bytes)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"status": "refused", "errorClass": type(error).__name__,
                          "message": str(error), "actualDatabaseExecution": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
