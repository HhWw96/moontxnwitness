"""Real-file journal tests; no PostgreSQL or performance benchmark is run.

Set MTW_JOURNAL_TEST_ROOT to keep every test, including fault artifacts, on a
chosen scratch disk. The receipt explicitly describes IO-only execution.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
import journal_v3 as j

BASE = Path(os.environ.get("MTW_JOURNAL_TEST_ROOT", tempfile.gettempdir()))
BASE.mkdir(parents=True, exist_ok=True)
RUN = BASE / ("run-" + uuid.uuid4().hex)
RUN.mkdir()


def event(seq, kind="statement", **fields):
    return {"seq": seq, "time": seq, "kind": kind, **fields}


def snapshot():
    return event(1, "snapshot", consistent=True, initial={"k": "v0"})


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.path = RUN / self._testMethodName
        self.closed = []

    def tearDown(self):
        for writer in self.closed:
            if not writer._closed:
                try:
                    writer.close()
                except j.JournalIOError:
                    pass

    def writer(self, **options):
        writer = j.SegmentedJournal(self.path, **options)
        self.closed.append(writer)
        return writer

    def complete(self, **options):
        writer = self.writer(**options)
        self.assertTrue(writer.append(snapshot()).accepted)
        self.assertTrue(writer.close(source_closed=True).complete)
        return writer

    def reindex(self, change):
        path = self.path / j.INDEX
        index = json.loads(path.read_bytes())
        change(index)
        index.pop("indexSha256")
        index["indexSha256"] = hashlib.sha256(j._json(index)).hexdigest()
        path.write_bytes(j._json(index) + b"\n")

    def test_roundtrip_lifecycle(self):
        w = self.writer()
        events = [snapshot(), event(2, "begin", tx="t", connection="c"),
                  event(3, "read", tx="t", key="k", version="v0"),
                  event(4, "write", tx="t", key="k", version="v1", predecessor="v0"),
                  event(5, "commit_request", tx="t"), event(6, "commit_ok", tx="t")]
        for item in events:
            self.assertTrue(w.append(item).accepted)
        self.assertEqual(w.flush(), 6)
        status = w.close(source_closed=True)
        self.assertTrue(status.complete)
        self.assertEqual(list(j.JournalReader(self.path).iter_events()), events)
        self.assertFalse(hasattr(w, "_events"))
        self.assertEqual(status.as_dict()["actualDatabaseExecution"], False)

    def test_rotation_exact_bindings(self):
        w = self.writer(max_queue_bytes=512, max_record_bytes=256, segment_bytes=256, flush_bytes=128)
        w.append(snapshot())
        for seq in range(2, 30):
            w.append(event(seq, sql="x" * 50))
        status = w.close(source_closed=True)
        self.assertTrue(status.complete)
        self.assertGreater(status.segment_count, 3)
        self.assertEqual(sum(1 for _ in j.JournalReader(self.path).iter_events()), 29)
        self.assertLessEqual(w.stats["maxQueueBytes"], 512)

    def test_timed_flush_below_threshold(self):
        w = self.writer(flush_interval=.02, flush_bytes=4096)
        w.append(snapshot())
        deadline = time.monotonic() + 3
        while w.stats["durableSeq"] < 1 and time.monotonic() < deadline:
            threading.Event().wait(.005)
        self.assertEqual(w.stats["durableSeq"], 1)
        self.assertFalse(j.JournalReader(self.path).verify().complete)
        self.assertTrue(w.close(source_closed=True).complete)

    def test_size_flush_below_interval(self):
        w = self.writer(flush_interval=60, flush_bytes=128)
        w.append(snapshot())
        w.append(event(2, sql="x" * 128))
        deadline = time.monotonic() + 3
        while w.stats["durableSeq"] < 2 and time.monotonic() < deadline:
            threading.Event().wait(.005)
        self.assertEqual(w.stats["durableSeq"], 2)

    def test_bounded_backpressure_includes_inflight(self):
        w = self.writer(max_queue_bytes=256, max_record_bytes=256, segment_bytes=512, flush_bytes=128)
        entered, release = threading.Event(), threading.Event()
        original = w._write_line
        def blocked(line):
            entered.set()
            if not release.wait(3):
                raise OSError("test gate timeout")
            original(line)
        w._write_line = blocked
        w.append(snapshot())
        self.assertTrue(entered.wait(3))
        results = []
        worker = threading.Thread(target=lambda: results.append(w.append(event(2))))
        worker.start()
        try:
            worker.join(.03)
            self.assertTrue(worker.is_alive())
            self.assertLessEqual(w.stats["queueBytes"], 256)
        finally:
            release.set()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertTrue(results[0].accepted)
        self.assertGreater(results[0].blocked_ns, 0)
        self.assertEqual(w.stats["backpressureCount"], 1)
        self.assertLessEqual(w.stats["maxQueueBytes"], 256)

    def test_large_value_rejected_before_json_encoding(self):
        w = self.writer(max_queue_bytes=512, max_record_bytes=256, segment_bytes=512, flush_bytes=128)
        w.append(snapshot())
        with mock.patch.object(j, "_json", side_effect=AssertionError("must not encode oversized tree")):
            result = w.append(event(2, rows=["a" * 5000]))
        self.assertFalse(result.accepted)
        self.assertEqual(result.gap["code"], "record_rejected")
        self.assertFalse(w.close(source_closed=True).complete)
        self.assertEqual(w.stats["queueBytes"], 0)

    def test_aggregate_short_containers_rejected(self):
        w = self.writer(max_queue_bytes=1024, max_record_bytes=1024, segment_bytes=1024, flush_bytes=128)
        result = w.append(event(1, rows=[["ab", "cd"] for _ in range(1000)]))
        self.assertFalse(result.accepted)

    def test_cycle_rejected(self):
        w = self.writer()
        cyclic = []
        cyclic.append(cyclic)
        self.assertFalse(w.append(event(1, rows=cyclic)).accepted)

    def test_nonfinite_and_unsafe_integer_rejected(self):
        w = self.writer()
        self.assertFalse(w.append(event(1, value=float("nan"))).accepted)
        self.assertFalse(w.append(event(1, value=2**54)).accepted)
        self.assertFalse(w.append(event(1, value="\ud800")).accepted)

    def test_total_bytes_limit_is_explicit(self):
        w = self.writer(max_queue_bytes=256, max_record_bytes=256, segment_bytes=256,
                        flush_bytes=128, max_total_bytes=128)
        w.append(snapshot())
        self.assertFalse(w.append(event(2, sql="x" * 100)).accepted)
        self.assertFalse(w.close(source_closed=True).complete)

    def test_missing_sequence_retained_but_incomplete(self):
        w = self.writer()
        w.append(snapshot())
        self.assertTrue(w.append(event(3)).accepted)
        status = w.close(source_closed=True)
        self.assertTrue(status.valid)
        self.assertFalse(status.complete)
        self.assertIn("missing_sequence", {g["code"] for g in status.gaps})
        self.assertEqual(sum(1 for _ in j.JournalReader(self.path).iter_events(require_complete=False)), 2)

    def test_duplicate_and_time_regression_rejected(self):
        w = self.writer()
        w.append(snapshot())
        self.assertFalse(w.append(snapshot()).accepted)
        self.assertFalse(w.append({"seq": 2, "time": 0, "kind": "statement"}).accepted)

    def test_commit_request_then_rollback_remains_unknown(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "commit_request", tx="t"), event(4, "rollback_ok", tx="t")):
            w.append(item)
        status = w.close(source_closed=True)
        self.assertFalse(status.complete)
        self.assertIn("transaction_outcome_unknown", {g["code"] for g in status.gaps})
        self.assertEqual(json.loads((self.path / j.INDEX).read_bytes())["activeTransactions"], ["t"])

    def test_disconnect_cannot_be_cleared_by_later_idle_rollback(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "commit_request", tx="t"), event(4, "disconnect", tx="t"), event(5, "rollback_ok", tx="t")):
            w.append(item)
        self.assertFalse(w.close(source_closed=True).complete)

    def test_plain_rollback_can_close_source(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "rollback_ok", tx="t")):
            w.append(item)
        self.assertTrue(w.close(source_closed=True).complete)

    def test_missing_commit_request_is_gap(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "commit_ok", tx="t")):
            w.append(item)
        self.assertFalse(w.close(source_closed=True).complete)

    def test_duplicate_transaction_identity_is_gap(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "rollback_ok", tx="t"), event(4, "begin", tx="t")):
            w.append(item)
        self.assertFalse(w.close(source_closed=True).complete)

    def test_active_sources_prevent_seal(self):
        w = self.writer()
        w.append(snapshot())
        w.set_references(unread_results=["cursor:1"])
        self.assertFalse(w.close(source_closed=True).complete)

    def test_source_closure_requires_explicit_declaration(self):
        w = self.writer()
        w.append(snapshot())
        self.assertFalse(w.close().complete)

    def test_checkpoint_does_not_close_storage(self):
        w = self.writer()
        w.append(snapshot())
        status = w.checkpoint(source_closed=True)
        self.assertTrue(status.source_closed)
        self.assertFalse(status.complete)
        self.assertTrue(w.close(source_closed=True).complete)
        with self.assertRaises(j.JournalError):
            w.checkpoint(source_closed=True)

    def test_retention_never_deletes_referenced_versions(self):
        w = self.writer()
        w.append(snapshot())
        w.set_references(version_sources=["k:v0"])
        self.assertTrue(w.close(source_closed=True).complete)
        before = {f.name for f in self.path.iterdir()}
        result = w.prune(before_seq=2)
        self.assertFalse(result["implemented"])
        self.assertEqual(result["deleted"], [])
        self.assertEqual({f.name for f in self.path.iterdir()}, before)

    def test_reference_aggregate_budget(self):
        w = self.writer()
        with self.assertRaises(ValueError):
            w.set_references(version_sources=("v" + str(n) + "x" * 250 for n in range(4096)))

    def test_actual_segment_creation_failure(self):
        w = self.writer()
        (self.path / "segment-000001.jsonl").mkdir()
        w.append(snapshot())
        with self.assertRaises(j.JournalIOError):
            w.flush()
        self.assertFalse(w.append(event(2)).accepted)
        with self.assertRaises(j.JournalIOError):
            w.close(source_closed=True)
        self.assertFalse(j.JournalReader(self.path).verify().complete)
        self.assertTrue((self.path / "journal-failure.json").exists())

    def test_actual_index_replace_failure(self):
        w = self.writer(flush_interval=60)
        (self.path / j.INDEX).unlink()
        (self.path / j.INDEX).mkdir()
        w.append(snapshot())
        with self.assertRaises(j.JournalIOError):
            w.flush()
        with self.assertRaises(j.JournalIOError):
            w.close(source_closed=True)
        self.assertFalse(j.JournalReader(self.path).verify().complete)

    def test_fsync_failure_not_acknowledged(self):
        w = self.writer(flush_interval=60)
        with mock.patch.object(j.os, "fsync", side_effect=OSError("injected device sync failure")):
            w.append(snapshot())
            with self.assertRaises(j.JournalIOError):
                w.flush()
            with self.assertRaises(j.JournalIOError):
                w.close(source_closed=True)
        self.assertEqual(w.stats["durableSeq"], 0)
        self.assertFalse(j.JournalReader(self.path).verify().complete)

    def test_short_writes_are_completed(self):
        target = self.path.with_suffix(".bin")
        with target.open("wb", buffering=0) as raw:
            class Short:
                def write(self, value):
                    return raw.write(value[:3])
            writer = object.__new__(j.SegmentedJournal)
            writer._file = Short()
            writer._write_line(b"abcdefghijklmnopqrstuvwxyz\n")
        self.assertEqual(target.read_bytes(), b"abcdefghijklmnopqrstuvwxyz\n")

    def test_truncated_segment_invalid(self):
        self.complete()
        p = self.path / "segment-000001.jsonl"
        p.write_bytes(p.read_bytes()[:-1])
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_same_size_tamper_invalid(self):
        self.complete()
        p = self.path / "segment-000001.jsonl"
        p.write_bytes(p.read_bytes().replace(b"v0", b"v1"))
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_missing_segment_invalid(self):
        self.complete()
        (self.path / "segment-000001.jsonl").unlink()
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_extra_segment_invalid(self):
        self.complete()
        (self.path / "segment-000002.jsonl").write_bytes(b"{}\n")
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_index_checksum_tamper_invalid(self):
        self.complete()
        p = self.path / j.INDEX
        data = json.loads(p.read_bytes())
        data["eventCount"] = 99
        p.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_index_recomputed_wrong_tail_time_invalid(self):
        self.complete()
        self.reindex(lambda data: data.update(lastTime=99))
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_index_recomputed_lifecycle_cannot_hide_active_tx(self):
        w = self.writer()
        w.append(snapshot())
        w.append(event(2, "begin", tx="t"))
        w.close(source_closed=True)
        self.reindex(lambda data: data.update(activeTransactions=[], gaps=[], sourceClosed=True))
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_index_missing_reference_proof_invalid(self):
        self.complete()
        self.reindex(lambda data: data.pop("references"))
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_reopen_requires_explicit_source_continuation(self):
        self.complete()
        with self.assertRaises(j.JournalError):
            j.SegmentedJournal.reopen(self.path)
        w = j.SegmentedJournal.reopen(self.path, exclusive_continuation=True)
        self.closed.append(w)
        w.append(event(2))
        self.assertTrue(w.close(source_closed=True).complete)
        self.assertEqual(len(list(j.JournalReader(self.path).iter_events())), 2)

    def test_reopen_with_prior_transactions(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "rollback_ok", tx="t")):
            w.append(item)
        w.close(source_closed=True)
        w2 = j.SegmentedJournal.reopen(self.path, exclusive_continuation=True)
        self.closed.append(w2)
        w2.append(event(4, "begin", tx="t2"))
        w2.append(event(5, "rollback_ok", tx="t2"))
        self.assertTrue(w2.close(source_closed=True).complete)

    def test_more_than_4096_finished_transactions_use_disk_index(self):
        w = self.writer()
        w.append(snapshot())
        for n in range(4100):
            w.append(event(2 + n * 2, "begin", tx="t" + str(n)))
            w.append(event(3 + n * 2, "rollback_ok", tx="t" + str(n)))
        status = w.close(source_closed=True)
        self.assertTrue(status.complete, status.as_dict())
        index = json.loads((self.path / j.INDEX).read_bytes())
        self.assertNotIn("seenTransactions", index)
        self.assertEqual(index["transactionIndex"]["entries"], 4100)
        self.assertLess((self.path / j.INDEX).stat().st_size, 20_000)

    def test_disk_identity_cache_tamper_rejected_from_raw_facts(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "rollback_ok", tx="t")):
            w.append(item)
        w.close(source_closed=True)
        with j.sqlite3.connect(self.path / j.TRANSACTIONS) as database:
            database.execute("UPDATE transactions SET begin_seq=99 WHERE tx='t'")
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_missing_identity_cache_rejected(self):
        self.complete()
        (self.path / j.TRANSACTIONS).unlink()
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_partial_append_error_during_encoding_releases_reservation(self):
        w = self.writer()
        original = j._bounded_copy
        def fail_while_encoding(value, limit, *args, **kwargs):
            with w._cv:
                w._error = OSError("concurrent writer failure")
                w._queue.clear()
                w._queued_bytes = 0
                w._cv.notify_all()
            return original(value, limit, *args, **kwargs)
        with mock.patch.object(j, "_bounded_copy", side_effect=fail_while_encoding):
            result = w.append(snapshot())
        self.assertFalse(result.accepted)
        self.assertEqual(w.stats["queueBytes"], 0)
        with self.assertRaises(j.JournalIOError):
            w.close(source_closed=True)

    def test_original_input_mutation_after_append_does_not_change_bytes(self):
        w = self.writer()
        value = snapshot()
        w.append(value)
        value["initial"]["k"] = "tampered-after-append"
        w.close(source_closed=True)
        self.assertEqual(next(j.JournalReader(self.path).iter_events())["initial"], {"k": "v0"})

    def test_reader_does_not_follow_segment_symlink(self):
        self.complete()
        p = self.path / "segment-000001.jsonl"
        original = p.read_bytes()
        outside = self.path.with_suffix(".outside")
        outside.write_bytes(original)
        p.unlink()
        try:
            p.symlink_to(outside)
        except OSError:
            self.skipTest("OS does not permit symlink creation for this account")
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_final_handle_close_failure_cannot_publish_sealed_index(self):
        w = self.writer()
        w.append(snapshot())
        w.flush()
        original = w._file
        class FailingClose:
            def flush(self):
                return original.flush()
            def fileno(self):
                return original.fileno()
            def close(self):
                original.close()
                raise OSError("injected final close failure")
        w._file = FailingClose()
        with self.assertRaises(j.JournalIOError):
            w.close(source_closed=True)
        status = j.JournalReader(self.path).verify()
        self.assertFalse(status.complete)
        self.assertFalse(status.closed)

    def test_sealed_replace_then_directory_sync_and_marker_failure_keeps_lock(self):
        w = self.writer()
        w.append(snapshot())
        w.flush()
        original_sync, original_open = j._sync_directory, Path.open
        def fail_after_sealed_replace(folder):
            if json.loads((Path(folder) / j.INDEX).read_bytes())["closed"]:
                raise OSError("injected directory sync failure after sealed replacement")
            return original_sync(folder)
        def marker_unwritable(path, *args, **kwargs):
            if path.name == "journal-failure.json":
                raise PermissionError("injected unwritable failure marker")
            return original_open(path, *args, **kwargs)
        with mock.patch.object(j, "_sync_directory", side_effect=fail_after_sealed_replace), mock.patch.object(Path, "open", marker_unwritable):
            with self.assertRaises(j.JournalIOError):
                w.close(source_closed=True)
        self.assertTrue(json.loads((self.path / j.INDEX).read_bytes())["closed"])
        self.assertFalse((self.path / "journal-failure.json").exists())
        self.assertTrue((self.path / j.LOCK).exists())
        self.assertFalse(j.JournalReader(self.path).verify().complete)
        with self.assertRaises(j.JournalVerificationError):
            j.JournalReader(self.path).export(self.path.with_suffix(".json"), clock_domain="c")
        with self.assertRaises(j.JournalError):
            j.SegmentedJournal.reopen(self.path, exclusive_continuation=True)

    def test_real_wal_cache_cannot_make_omitted_archive_rows_complete(self):
        w = self.writer()
        for item in (snapshot(), event(2, "begin", tx="t"), event(3, "rollback_ok", tx="t")):
            w.append(item)
        w.close(source_closed=True)
        cache = j.sqlite3.connect(self.path / j.TRANSACTIONS)
        try:
            cache.execute("UPDATE transactions SET begin_seq=99")
            cache.commit()
            self.assertEqual(cache.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            cache.execute("UPDATE transactions SET begin_seq=2")
            cache.commit()
            self.assertTrue((self.path / (j.TRANSACTIONS + "-wal")).exists())
            self.assertEqual(cache.execute("SELECT begin_seq FROM transactions").fetchone()[0], 2)
            self.assertFalse(j.JournalReader(self.path).verify().valid)
            with self.assertRaises(j.JournalVerificationError):
                j.JournalReader(self.path).archive(self.path.with_suffix(".zip"))
        finally:
            cache.close()

    def test_wal_header_without_sidecars_is_rejected(self):
        self.complete()
        with j.sqlite3.connect(self.path / j.TRANSACTIONS) as cache:
            cache.execute("PRAGMA journal_mode=WAL")
        cache.close()
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_unsealed_sqlite_rollback_journal_is_rejected(self):
        self.complete()
        (self.path / (j.TRANSACTIONS + "-journal")).write_bytes(b"incomplete")
        self.assertFalse(j.JournalReader(self.path).verify().valid)

    def test_writer_lock_appearing_during_iteration_is_rejected(self):
        self.complete()
        iterator = j.JournalReader(self.path).iter_events()
        self.assertEqual(next(iterator), snapshot())
        (self.path / j.LOCK).write_bytes(b"a-new-writer-began")
        with self.assertRaises(j.JournalVerificationError):
            next(iterator)

    def test_interrupted_subprocess_not_complete_or_recoverable(self):
        code = ("import sys,os;sys.path.insert(0,sys.argv[1]);import journal_v3 as j;"
                "w=j.SegmentedJournal(sys.argv[2]);w.append({'seq':1,'time':1,'kind':'snapshot','initial':{},'consistent':True});"
                "w.flush();os._exit(0)")
        result = subprocess.run([sys.executable, "-B", "-c", code, str(Path(j.__file__).parent), str(self.path)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        status = j.JournalReader(self.path).verify()
        self.assertTrue(status.valid)
        self.assertFalse(status.complete)
        with self.assertRaises(j.JournalError):
            j.SegmentedJournal.reopen(self.path, exclusive_continuation=True)

    def test_archive_verifies_bindings_and_preserves_source(self):
        self.complete()
        destination = self.path.with_suffix(".zip")
        result = j.JournalReader(self.path).archive(destination)
        self.assertTrue(result["verified"])
        self.assertTrue(result["archiveReconstructionVerified"])
        self.assertFalse(result["sourceFilesDeleted"])
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(archive.read("segment-000001.jsonl"), (self.path / "segment-000001.jsonl").read_bytes())
        with self.assertRaises(FileExistsError):
            j.JournalReader(self.path).archive(destination)
        with self.assertRaises(ValueError):
            j.JournalReader(self.path).archive(self.path / "bad.zip")

    def test_archive_refuses_incomplete_source(self):
        w = self.writer()
        w.append(snapshot())
        w.close()
        with self.assertRaises(j.JournalVerificationError):
            w.archive(self.path.with_suffix(".zip"))

    def test_export_streaming_scope_and_no_overwrite(self):
        self.complete()
        destination = self.path.with_suffix(".json")
        result = j.JournalReader(self.path).export(destination, clock_domain="test-clock", exclusive_writers=True)
        data = json.loads(destination.read_bytes())
        self.assertEqual(data["traceSchema"], 3)
        self.assertEqual(data["events"], [snapshot()])
        self.assertTrue(data["scope"]["exclusiveWriters"])
        self.assertEqual(result["sha256"], hashlib.sha256(destination.read_bytes()).hexdigest())
        with self.assertRaises(FileExistsError):
            j.JournalReader(self.path).export(destination, clock_domain="test-clock")

    def test_export_over_budget_has_no_partial_output(self):
        self.complete()
        destination = self.path.with_suffix(".json")
        with self.assertRaises(j.JournalVerificationError):
            j.JournalReader(self.path).export(destination, clock_domain="test-clock", max_bytes=128)
        self.assertFalse(destination.exists())
        self.assertEqual(list(destination.parent.glob("." + destination.name + ".mtw-*.tmp")), [])
        self.assertTrue(j.JournalReader(self.path).verify().complete)

    def test_export_incomplete_refused(self):
        w = self.writer()
        w.append(snapshot())
        w.close()
        with self.assertRaises(j.JournalVerificationError):
            j.JournalReader(self.path).export(self.path.with_suffix(".json"), clock_domain="c")

    def test_cli_verify_and_export(self):
        self.complete()
        command = [sys.executable, "-B", j.__file__]
        result = subprocess.run(command + ["verify", str(self.path)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["complete"])
        target = self.path.with_suffix(".json")
        result = subprocess.run(command + ["export", str(self.path), "--output", str(target), "--clock-domain", "c"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(json.loads(target.read_bytes())["scope"]["exclusiveWriters"])


if __name__ == "__main__":
    program = unittest.main(exit=False)
    result = program.result
    receipt = {"schema": 1, "suite": "v3-segmented-journal-io", "testsRun": result.testsRun,
               "failures": [name.id() for name, _ in result.failures],
               "errors": [name.id() for name, _ in result.errors],
               "skipped": [{"test": name.id(), "reason": reason} for name, reason in result.skipped],
               "passed": result.wasSuccessful(), "actualDatabaseExecution": False,
               "sourceSha256": hashlib.sha256(Path(j.__file__).read_bytes()).hexdigest(),
               "artifacts": "Per-test directories retained alongside this receipt"}
    (RUN / "journal-unit-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Journal IO artifacts: " + str(RUN))
    sys.exit(0 if result.wasSuccessful() else 1)
