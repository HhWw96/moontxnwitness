"""Source-closed point-register windows and archived hot-cache retention draft.

The unchanged journal is authoritative. The SQLite graph is rebuilt/compared
against its verified facts before operations. Search/model results are never
inputs. This prototype evicts only owned per-event cache files, never journal
segments, checkpoints, archives or source facts.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "integrations/python"))
from moontxnwitness_capture.journal_v3 import JournalReader, JournalVerificationError

MAX_BYTES, MAX_EVENTS, MAX_ROOTS = 64 * 1024 * 1024, 65536, 4096
TABLES = {"events": "seq,kind,tx,sha,bytes", "versions": "version,key,seq,tx", "refs": "seq,version", "transactions": "tx,status"}


class WindowError(RuntimeError): pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value): return hashlib.sha256(value).hexdigest()


def scalar(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and all(not 0xD800 <= ord(c) <= 0xDFFF for c in value) and len(value.encode("utf-16-le")) <= 512


def sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)


def safe_file(path, max_bytes=MAX_BYTES):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise WindowError("Missing, unsafe or over-budget owned file")
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes: raise WindowError("File grew over budget")
    return raw


def connect(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA trusted_schema=OFF")
    return db


def schema(db):
    db.executescript("""
CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,tx TEXT,sha TEXT NOT NULL,bytes INTEGER NOT NULL);
CREATE TABLE versions(version TEXT PRIMARY KEY,key TEXT NOT NULL,seq INTEGER NOT NULL,tx TEXT) WITHOUT ROWID;
CREATE TABLE refs(seq INTEGER NOT NULL,version TEXT NOT NULL,PRIMARY KEY(seq,version)) WITHOUT ROWID;
CREATE TABLE transactions(tx TEXT PRIMARY KEY,status TEXT NOT NULL) WITHOUT ROWID;
""")


def catalog_digest(db):
    hashed = hashlib.sha256()
    for table, columns in TABLES.items():
        hashed.update(table.encode() + b"\x00")
        for row in db.execute("SELECT " + columns + " FROM " + table + " ORDER BY " + columns):
            hashed.update(canonical(list(row)) + b"\n")
    return hashed.hexdigest()


def build_catalog(db, events, emit=None):
    """Only factual edges known at observation time; later facts cannot fill gaps."""
    schema(db)
    count = size = 0
    gaps = []
    def gap(code):
        if code not in gaps: gaps.append(code)
        if len(gaps) > 64: raise WindowError("Source gap budget")
    for event in events:
        count += 1
        raw, kind, tx, seq = canonical(event), event["kind"], event.get("tx"), event["seq"]
        size += len(raw)
        if count > MAX_EVENTS or size > MAX_BYTES: raise WindowError("Prototype source budget exceeded")
        if seq != count: gap("missing_sequence")
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (seq, kind, tx, digest(raw), len(raw)))
        if emit is not None: emit(seq, raw)
        if kind == "snapshot":
            if count != 1 or event.get("consistent") is not True: gap("inconsistent_snapshot")
            initial = event.get("initial")
            if not isinstance(initial, dict) or len(initial) > 10000: raise WindowError("Unsupported snapshot")
            for key, version in initial.items():
                if not scalar(key) or not scalar(version): raise WindowError("Only point-register scalar snapshots are supported")
                try: db.execute("INSERT INTO versions VALUES(?,?,?,NULL)", (version, key, seq))
                except sqlite3.IntegrityError: gap("duplicate_version")
        elif kind == "begin":
            if not scalar(tx): raise WindowError("Invalid transaction identity")
            db.execute("INSERT INTO transactions VALUES(?,'active')", (tx,))
        elif kind in ("commit_ok", "rollback_ok", "disconnect"):
            db.execute("UPDATE transactions SET status=? WHERE tx=?", ("committed" if kind == "commit_ok" else "aborted" if kind == "rollback_ok" else "unknown", tx))
        elif kind in ("read", "write"):
            key, version = event.get("key"), event.get("version")
            if not scalar(key) or not scalar(version): raise WindowError("Unsupported version/key")
            allowed = {"seq", "time", "kind", "tx", "key", "version", "predecessor"}
            if set(event) - allowed: gap("unproved_fact_transport")
            if kind == "read":
                source = db.execute("SELECT key FROM versions WHERE version=?", (version,)).fetchone()
                if source is None: gap("read_source_missing_at_observation")
                elif source[0] != key: gap("read_source_key_mismatch")
                db.execute("INSERT OR IGNORE INTO refs VALUES(?,?)", (seq, version))
            else:
                predecessor = event.get("predecessor")
                if not scalar(predecessor): gap("write_predecessor_missing")
                else:
                    source = db.execute("SELECT key FROM versions WHERE version=?", (predecessor,)).fetchone()
                    if source is None: gap("write_source_missing_at_observation")
                    elif source[0] != key: gap("write_source_key_mismatch")
                    db.execute("INSERT OR IGNORE INTO refs VALUES(?,?)", (seq, predecessor))
                try: db.execute("INSERT INTO versions VALUES(?,?,?,?)", (version, key, seq, tx))
                except sqlite3.IntegrityError: gap("duplicate_version")
        elif kind in ("statement", "rows", "condition"):
            gap("sql_or_condition_source_proof_unavailable")
        elif kind not in ("savepoint", "rollback_to", "release", "commit_request"):
            gap("unsupported_event_kind")
    db.commit()
    return {"events": count, "bytes": size, "gaps": gaps, "catalogSha256": catalog_digest(db)}


class SourceWindows:
    """Closed immutable journal -> source graph -> pinned windows -> hot eviction.

    Archives and the original journal are retained. Missing archives/source,
    unsealed source, unsupported model/SQL, cache tampering, active readers and
    failed persistence all block eviction/completeness.
    """
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.poisoned = False

    @classmethod
    def create(cls, path, source, *, data_model="point-register-v1", clock_domain, exclusive_writers=False):
        if data_model != "point-register-v1": raise WindowError("List/relation windows are explicitly unsupported; no pruning")
        if not scalar(clock_domain) or exclusive_writers is not True: raise WindowError("Explicit clock/scope declarations required")
        requested, source = Path(path), Path(source).resolve()
        if requested.is_symlink(): raise WindowError("Unsafe managed store")
        path = requested.resolve()
        if path.is_relative_to(source) or source.is_relative_to(path): raise WindowError("Store and journal must be separate")
        path.mkdir(parents=False, exist_ok=False)
        store = cls(path)
        (path / "events").mkdir()
        reader, db = JournalReader(source), connect(path / "catalog.sqlite3")
        status = reader.verify()
        if not status.valid: db.close(); raise WindowError("Source journal integrity failed")
        def emit(seq, raw):
            with store.blob(seq).open("xb") as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            info = build_catalog(db, reader.iter_events(require_complete=False), emit)
        finally: db.close()
        store._write_state({"schema": 1, "source": str(source), "sourceIndexSha256": status.index_sha256,
            "clockDomain": clock_domain, "exclusiveWriters": True, **info,
            "sourceCompleteAtImport": status.complete, "checkpoints": {}, "windows": {}, "pins": {}})
        return store

    def blob(self, seq): return self.path / "events" / ("event-%012d.json" % seq)

    def _state(self):
        if self.poisoned: raise WindowError("This instance failed persistence and is permanently incomplete")
        raw = safe_file(self.path / "state.json", 4 * 1024 * 1024)
        state = json.loads(raw)
        claimed = state.pop("stateSha256", None)
        if claimed != digest(canonical(state)) or state.get("schema") != 1: raise WindowError("State checksum/schema mismatch")
        return state

    def _write_state(self, state):
        roots = [v for w in state.get("windows", {}).values() for v in w["transactions"]]
        roots.extend(v for p in state.get("pins", {}).values() for group in p.values() for v in group)
        if len(roots) > MAX_ROOTS or sum(len(canonical(v)) for v in roots) > 256 * 1024:
            raise WindowError("Aggregate retained-root budget")
        payload = {**state, "stateSha256": digest(canonical(state))}
        temporary = self.path / (".state-" + uuid.uuid4().hex)
        with temporary.open("xb") as stream: stream.write(canonical(payload)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.path / "state.json")
        sync_directory(self.path)

    @contextlib.contextmanager
    def _operation(self):
        if self.poisoned: raise WindowError("Poisoned instance")
        target = self.path / "store.lock"
        if target.is_symlink(): raise WindowError("Unsafe or interrupted store lock")
        try: stream = target.open("xb")
        except FileExistsError: raise WindowError("Active/interrupted store operation; no automatic recovery") from None
        stream.write(b"source-window-operation\n"); stream.flush(); os.fsync(stream.fileno()); stream.close()
        success = False
        try:
            yield
            success = True
        except WindowError:
            success = True  # A rejected validation performed no authoritative deletion.
            raise
        except BaseException:
            self.poisoned = True  # Keep the pre-existing lock even if all later writes fail.
            raise
        finally:
            if success: target.unlink(); sync_directory(self.path)

    def _verify_source(self, state):
        reader = JournalReader(state["source"])
        status = reader.verify()
        if not status.complete or status.index_sha256 != state["sourceIndexSha256"]:
            raise WindowError("Source missing, changed, active, invalidated or unsealed")
        if state["gaps"]: raise WindowError("Source dependencies incomplete: " + ",".join(state["gaps"]))
        with tempfile.TemporaryDirectory(prefix="mtw-window-graph-", dir=os.environ.get("MTW_JOURNAL_SCRATCH")) as scratch:
            rebuilt = connect(Path(scratch) / "graph.sqlite3")
            try:
                actual = build_catalog(rebuilt, reader.iter_events())
                expected_schema = rebuilt.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            finally: rebuilt.close()
        if actual["gaps"] or actual["catalogSha256"] != state["catalogSha256"]: raise WindowError("Source graph changed or factual dependencies are incomplete")
        catalog = self.path / "catalog.sqlite3"
        if catalog.is_symlink() or any((self.path / ("catalog.sqlite3" + suffix)).exists() or (self.path / ("catalog.sqlite3" + suffix)).is_symlink() for suffix in ("-wal", "-shm", "-journal")):
            raise WindowError("Unsafe/unsealed graph cache")
        db = sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True)
        try:
            db.execute("PRAGMA trusted_schema=OFF")
            if db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall() != expected_schema:
                raise WindowError("Graph cache schema differs from fixed factual tables")
            if catalog_digest(db) != state["catalogSha256"]: raise WindowError("Graph cache differs from raw factual graph")
        finally: db.close()
        return reader

    @staticmethod
    def _label(name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name): raise WindowError("Bounded safe reference name required")

    def _open_graph(self, state):
        """Hold a validated read transaction while deriving closure, not a cache TOCTOU."""
        path = self.path / "catalog.sqlite3"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES: raise WindowError("Unsafe/over-budget graph cache")
        with path.open("rb") as header:
            if header.read(20)[18:20] != b"\x01\x01": raise WindowError("Graph cache is not sealed DELETE-mode SQLite")
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            db.execute("PRAGMA trusted_schema=OFF"); db.execute("BEGIN")
            reference = sqlite3.connect(":memory:")
            try:
                schema(reference)
                expected = reference.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            finally: reference.close()
            if db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall() != expected or catalog_digest(db) != state["catalogSha256"]:
                raise WindowError("Graph snapshot differs from verified raw source facts")
            return db
        except BaseException:
            db.close(); raise

    def _closure(self, db, *, transactions=(), versions=(), sequences=()):
        db.execute("DROP TABLE IF EXISTS temp.keep")
        db.execute("CREATE TEMP TABLE keep(seq INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO keep SELECT seq FROM events WHERE kind='snapshot'")
        for group in (transactions, versions, sequences):
            if not isinstance(group, (tuple, list)) or len(group) > MAX_ROOTS: raise WindowError("Root budget")
        for tx in transactions:
            if not scalar(tx): raise WindowError("Invalid transaction root")
            status = db.execute("SELECT status FROM transactions WHERE tx=?", (tx,)).fetchone()
            if status is None or status[0] not in ("committed", "aborted"): raise WindowError("Missing/active/unknown transaction root")
            db.execute("INSERT OR IGNORE INTO keep SELECT seq FROM events WHERE tx=?", (tx,))
        for version in versions:
            if not scalar(version): raise WindowError("Invalid version root")
            if not db.execute("SELECT 1 FROM versions WHERE version=?", (version,)).fetchone(): raise WindowError("Missing pinned version")
            db.execute("INSERT OR IGNORE INTO keep SELECT seq FROM versions WHERE version=?", (version,))
        for seq in sequences:
            if type(seq) is not int or not db.execute("SELECT 1 FROM events WHERE seq=?", (seq,)).fetchone(): raise WindowError("Missing event root")
            db.execute("INSERT OR IGNORE INTO keep VALUES(?)", (seq,))
        while True:
            before = db.total_changes
            db.execute("INSERT OR IGNORE INTO keep SELECT e.seq FROM events e JOIN events root ON root.tx=e.tx JOIN keep k ON k.seq=root.seq WHERE e.tx IS NOT NULL")
            db.execute("INSERT OR IGNORE INTO keep SELECT v.seq FROM versions v JOIN refs r ON r.version=v.version JOIN keep k ON k.seq=r.seq")
            if db.total_changes == before: break
        return db.execute("SELECT count(*) FROM keep").fetchone()[0]

    def checkpoint(self, name):
        self._label(name)
        with self._operation():
            state = self._state(); self._verify_source(state)
            if name in state["checkpoints"] or len(state["checkpoints"]) >= 32: raise WindowError("Checkpoint exists/budget")
            state["checkpoints"][name] = {"sourceIndexSha256": state["sourceIndexSha256"], "catalogSha256": state["catalogSha256"], "archive": None}
            self._write_state(state)
        return {"checkpoint": name, "hotRecordsPinnedUntilArchive": True}

    def _archive_valid(self, record, state):
        archive = Path(record["path"])
        if type(record.get("bytes")) is not int or not 0 < record["bytes"] <= 2 * MAX_BYTES or archive.is_symlink() or not archive.is_file() or archive.stat().st_size != record["bytes"]: raise WindowError("Referenced archive missing/unsafe/size mismatch")
        hashed = hashlib.sha256()
        with archive.open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""): hashed.update(block)
        if hashed.hexdigest() != record["sha256"]: raise WindowError("Referenced archive hash mismatch")
        with zipfile.ZipFile(archive) as zipped, tempfile.TemporaryDirectory(prefix="mtw-window-archive-", dir=os.environ.get("MTW_JOURNAL_SCRATCH")) as scratch:
            names = zipped.namelist()
            if len(names) > 4098 or len(names) != len(set(names)): raise WindowError("Archive member budget/duplicates")
            total = 0
            for info in zipped.infolist():
                if not re.fullmatch(r"journal-index\.json|transactions\.sqlite3|segment-[0-9]{6}\.jsonl", info.filename): raise WindowError("Unsafe archive member")
                total += info.file_size
                if total > 2 * MAX_BYTES or info.file_size > MAX_BYTES: raise WindowError("Archive extraction budget")
                with zipped.open(info) as source, (Path(scratch) / info.filename).open("xb") as target:
                    remaining = info.file_size
                    while remaining:
                        block = source.read(min(65536, remaining))
                        if not block: raise WindowError("Partial archive member")
                        target.write(block); remaining -= len(block)
                    if source.read(1): raise WindowError("Archive member exceeds binding")
            status = JournalReader(scratch).verify()
            if not status.complete or status.index_sha256 != state["sourceIndexSha256"]: raise WindowError("Archive did not reconstruct the same complete journal")

    def archive_checkpoint(self, name, destination):
        self._label(name)
        destination = Path(destination).resolve()
        with self._operation():
            state = self._state(); reader = self._verify_source(state)
            if destination.is_relative_to(self.path) or destination.is_relative_to(Path(state["source"])): raise WindowError("Archive must be outside store/source")
            checkpoint = state["checkpoints"].get(name)
            if checkpoint is None or checkpoint["archive"] is not None: raise WindowError("Missing/already archived checkpoint")
            reader.archive(destination)
            raw_hash = hashlib.sha256()
            with destination.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""): raw_hash.update(block)
            record = {"path": str(destination), "bytes": destination.stat().st_size, "sha256": raw_hash.hexdigest()}
            self._archive_valid(record, state)
            checkpoint["archive"] = record
            self._write_state(state)
            return {"checkpoint": name, "archiveVerified": True, "sourceFilesDeleted": False}

    def _verify_hot(self, db, *, only_keep=False):
        query = "SELECT e.seq,e.sha,e.bytes FROM events e" + (" JOIN keep k ON k.seq=e.seq" if only_keep else "") + " ORDER BY e.seq"
        for seq, claimed, size in db.execute(query):
            raw = safe_file(self.blob(seq), 4 * 1024 * 1024)
            if len(raw) != size or digest(raw) != claimed: raise WindowError("Required hot source missing or tampered")

    def create_window(self, name, *, transactions):
        self._label(name)
        with self._operation():
            state = self._state(); self._verify_source(state)
            if name in state["windows"] or len(state["windows"]) >= 64: raise WindowError("Window exists/budget")
            db = self._open_graph(state)
            try:
                count = self._closure(db, transactions=transactions)
                self._verify_hot(db, only_keep=True)
            finally: db.close()
            state["windows"][name] = {"transactions": list(transactions), "sourceClosureComplete": True, "events": count}
            self._write_state(state)
            return {"window": name, "sourceClosureComplete": True, "retainedEvents": count, "modelVerdict": None}

    def pin(self, name, *, transactions=(), versions=(), sequences=()):
        self._label(name)
        with self._operation():
            state = self._state(); self._verify_source(state)
            if name in state["pins"] or len(state["pins"]) >= 64: raise WindowError("Pin exists/budget")
            db = self._open_graph(state)
            try: self._closure(db, transactions=transactions, versions=versions, sequences=sequences); self._verify_hot(db, only_keep=True)
            finally: db.close()
            state["pins"][name] = {"transactions": list(transactions), "versions": list(versions), "sequences": list(sequences)}
            self._write_state(state)

    def release(self, name, *, kind="window"):
        if kind not in ("window", "pin"): raise WindowError("Only explicit window/pin release is supported")
        with self._operation():
            state = self._state(); self._verify_source(state)
            group = state["windows" if kind == "window" else "pins"]
            if name not in group: raise WindowError("Unknown reference")
            del group[name]; self._write_state(state)

    def prune(self, *, before_seq):
        if type(before_seq) is not int or before_seq < 0: raise WindowError("Safe cutoff required")
        deleted = []
        with self._operation():
            state = self._state(); self._verify_source(state)
            if not state["checkpoints"]: raise WindowError("Checkpoint and verified archive required before eviction")
            for checkpoint in state["checkpoints"].values():
                if checkpoint["archive"] is None: raise WindowError("Unarchived checkpoint retains all hot sources")
                self._archive_valid(checkpoint["archive"], state)
            txs, versions, sequences = [], [], []
            for window in state["windows"].values(): txs.extend(window["transactions"])
            for pin in state["pins"].values():
                txs.extend(pin["transactions"]); versions.extend(pin["versions"]); sequences.extend(pin["sequences"])
            db = self._open_graph(state)
            try:
                self._closure(db, transactions=txs, versions=versions, sequences=sequences)
                self._verify_hot(db, only_keep=True)
                # Verify every present eviction candidate before deleting any.
                for seq, claimed, size in db.execute("SELECT seq,sha,bytes FROM events WHERE seq<? AND seq NOT IN (SELECT seq FROM keep) ORDER BY seq", (before_seq,)):
                    path = self.blob(seq)
                    if path.exists() or path.is_symlink():
                        raw = safe_file(path, 4 * 1024 * 1024)
                        if len(raw) != size or digest(raw) != claimed: raise WindowError("Eviction candidate tampered")
                for (seq,) in db.execute("SELECT seq FROM events WHERE seq<? AND seq NOT IN (SELECT seq FROM keep) ORDER BY seq", (before_seq,)):
                    path = self.blob(seq)
                    if path.exists(): path.unlink(); deleted.append(seq)
                sync_directory(self.path / "events")
            finally: db.close()
            self._verify_source(state)
            for checkpoint in state["checkpoints"].values(): self._archive_valid(checkpoint["archive"], state)
        return {"implemented": True, "managedHotCopiesDeleted": deleted, "originalJournalFilesDeleted": False,
            "archivesDeleted": False, "sourceClosureVerified": True, "modelVerdict": None}

    @contextlib.contextmanager
    def read_window(self, name):
        """Hold a filesystem read lease throughout iteration; pruning is blocked."""
        with self._operation():
            state = self._state(); self._verify_source(state)
            window = state["windows"].get(name)
            if window is None: raise WindowError("Unknown window")
            db = self._open_graph(state)
            try:
                self._closure(db, transactions=window["transactions"]); self._verify_hot(db, only_keep=True)
                def events():
                    for seq, claimed, size in db.execute("SELECT e.seq,e.sha,e.bytes FROM events e JOIN keep k ON k.seq=e.seq ORDER BY e.seq"):
                        raw = safe_file(self.blob(seq), 4 * 1024 * 1024)
                        if len(raw) != size or digest(raw) != claimed: raise WindowError("Source changed at delivery")
                        yield json.loads(raw)
                yield events()
                self._verify_source(state); self._verify_hot(db, only_keep=True)
            finally: db.close()

    def export_window(self, name, destination, *, max_bytes=8 * 1024 * 1024):
        """Never rebase snapshot/search facts; retain original source seq mapping."""
        destination = Path(destination)
        if destination.exists() or destination.is_symlink(): raise WindowError("Refusing overwrite")
        if type(max_bytes) is not int or not 128 <= max_bytes <= MAX_BYTES: raise WindowError("Bounded export required")
        state = self._state()
        if destination.resolve().is_relative_to(self.path) or destination.resolve().is_relative_to(Path(state["source"])):
            raise WindowError("Derived export must be outside store/source")
        temporary = destination.with_name("." + destination.name + "." + uuid.uuid4().hex)
        old_new, total, written_hash = {}, 0, hashlib.sha256()
        try:
            with self.read_window(name) as events, temporary.open("xb") as target:
                def put(raw):
                    nonlocal total
                    total += len(raw)
                    if total > max_bytes: raise WindowError("Export budget exceeded; no silent truncation")
                    target.write(raw); written_hash.update(raw)
                put(b'{"traceSchema":3,"clockDomain":' + canonical(state["clockDomain"]) + b',"scope":{"exclusiveWriters":true},"gaps":[],"events":[')
                for number, original in enumerate(events, 1):
                    event = dict(original); old_new[event["seq"]] = number; event["seq"] = number
                    if event["kind"] == "rollback_ok" and "commitResponse" in event:
                        event["commitResponse"] = {**event["commitResponse"], "request": old_new[event["commitResponse"]["request"]]}
                    put((b"," if number > 1 else b"") + canonical(event))
                put(b"]}"); target.flush(); os.fsync(target.fileno())
            os.link(temporary, destination); sync_directory(destination.parent)
            published = safe_file(destination, max_bytes)
            if len(published) != total or digest(published) != written_hash.hexdigest():
                raise WindowError("Published derived artifact changed; no complete receipt")
            return {"schema": "source-window-draft/1", "sourceClosureComplete": True, "modelVerdict": None,
                "sourceIndexSha256": state["sourceIndexSha256"], "sequenceMap": old_new,
                "traceSha256": written_hash.hexdigest(), "bytes": total, "searchFactsAdded": False}
        finally:
            if temporary.exists(): temporary.unlink()
