"""Actual small-file/native-lock tests with explicitly synthetic DB responses."""
from __future__ import annotations
import contextlib
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import epoch_coordinator as coordinator
import epoch_sources as sources
from point_epoch import EpochCapture
from psycopg.rows import tuple_row
from moontxnwitness_capture.journal_v3 import JournalReader


def version(n):return str(uuid.UUID(int=n))


class OriginalError(Exception):pass


class RawCursor:
    def __init__(self,connection):
        self.connection=connection;self.row_factory=tuple_row;self.closed=False;self.description=None
        self.rowcount=-1;self.position=0;self.statusmessage=None;self.rows=[];self.pgresult=SimpleNamespace(status=1)
        self.closed_error=OriginalError("original cursor closed")
    @property
    def rownumber(self):return self.position if self.description is not None else None
    def configure(self,rows,columns=(),tag=None):
        self.rows=list(rows);self.position=0;self.rowcount=len(rows)
        self.description=tuple(SimpleNamespace(name=n,type_code=t) for n,t in columns) or None
        self.statusmessage=tag or "SELECT "+str(len(rows));self.pgresult=SimpleNamespace(status=2 if columns else 1);return self
    def execute(self,sql,params=None,**kwargs):
        if self.connection.closed:raise self.connection.closed_error
        self.connection.info.transaction_status=2;self.connection.last_sql=sql
        response=self.connection.responses.pop(0)
        if "error" in response:raise response["error"]
        return self.configure(response.get("rows",[]),response.get("columns",()),response.get("tag"))
    def fetchone(self):
        if self.closed or self.connection.closed:raise self.closed_error
        if self.position==len(self.rows):return None
        row=self.rows[self.position];self.position+=1;return row
    def fetchmany(self,size=1):
        result=[]
        for _ in range(size):
            row=self.fetchone()
            if row is None:break
            result.append(row)
        return result
    def fetchall(self):return self.fetchmany(max(1,len(self.rows)))
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class RawConnection:
    def __init__(self,responses=()):
        self.responses=list(responses);self.info=SimpleNamespace(transaction_status=0)
        self.autocommit=False;self.closed=False;self.row_factory=tuple_row;self.closed_error=OriginalError("original connection closed")
        self.close_error=None
    def cursor(self,*args,**kwargs):return RawCursor(self)
    def commit(self):self.info.transaction_status=0
    def rollback(self):self.info.transaction_status=0
    def close(self):
        if self.close_error:raise self.close_error
        self.closed=True;self.info.transaction_status=4


class ServerCursor(RawCursor):
    def execute(self,sql,params=None,**kwargs):
        self.connection.queries.append((sql,params));self.configure(self.connection.ledger,[("field",25)]*7,"FETCH 0");return self
    def fetchmany(self,size=1):
        rows=super().fetchmany(size);self.statusmessage="FETCH "+str(len(rows));return rows


class Setup:
    """Synthetic SQL/PGresult responses. Never an actual PostgreSQL connection."""
    def __init__(self):
        self.autocommit=True;self.closed=False;self.row_factory=tuple_row
        self.info=SimpleNamespace(transaction_status=0,backend_pid=5678,server_version=180006)
        self.rows=[("k",1,version(1))];self.ledger=[(version(1),"k","initial",True,None,None,1)]
        self.queries=[];self.snapshots=0;self.change_next=False;self.commit_error=None;self.commit_tag="COMMIT";self.before_commit=None
    def cursor(self,name=None):return ServerCursor(self)
    def execute(self,sql,params=None):
        self.queries.append((sql,params));cursor=RawCursor(self)
        if sql.startswith("BEGIN"):
            self.info.transaction_status=2;return cursor.configure([],tag="BEGIN")
        if sql=="COMMIT":
            if self.before_commit:self.before_commit()
            if self.commit_error:raise self.commit_error
            self.info.transaction_status=0;return cursor.configure([],tag=self.commit_tag)
        if sql=="ROLLBACK":self.info.transaction_status=0;return cursor.configure([],tag="ROLLBACK")
        if sql.startswith("LOCK TABLE"):return cursor.configure([],tag="LOCK TABLE")
        if sql=="SELECT pg_backend_pid(),pg_current_xact_id()::text":return cursor.configure([(5678,"777")],[("pid",23),("xid",25)])
        if sql=="SELECT mock_nonce,mock_oid FROM epoch_mock_identity WHERE nonce=%s":return cursor.configure([(params[0],123456)],[("nonce",25),("oid",26)])
        if sql=="SELECT mock_catalog FROM epoch_mock_catalog WHERE oid=%s":return cursor.configure([("fixed-catalog",)],[("catalog",25)])
        if sql.startswith('SELECT "id","value",') and sql.endswith(" LIMIT 65"):
            self.snapshots+=1;rows=self.rows
            if self.change_next and self.snapshots%2==0:rows=[("k",2,version(2))]
            return cursor.configure(rows,[("id",25),("value",23),("token",25)])
        raise AssertionError("Unexpected mock setup SQL "+sql)


def mock_verify(connection,installation):
    row=connection.execute("SELECT mock_nonce,mock_oid FROM epoch_mock_identity WHERE nonce=%s",(installation.nonce,)).fetchone()
    sources.require(row==(installation.nonce,installation.table_oid),"Synthetic marker mismatch")
    rows=connection.execute("SELECT mock_catalog FROM epoch_mock_catalog WHERE oid=%s",(installation.table_oid,)).fetchall()
    sources.require(rows==[("fixed-catalog",)],"Synthetic catalog mismatch")


def mock_initialize(self,setup):
    # The production initializer is not changed. This test-only monkeypatch
    # marks its source record explicitly synthetic, not catalog/DB proof.
    self.installation=sources.Installation(self.profile.names,version(100),123456,{})
    self.sources.append({"kind":"synthetic-test-installation","actualDatabaseExecution":False})
    self.publish_snapshot({key:version(1+i) for i,key in enumerate(sorted(self.keys))},consistent=True)


@contextlib.contextmanager
def synthetic():
    with patch.object(EpochCapture,"initialize",mock_initialize),patch.object(sources,"verify_installation",mock_verify):yield


def read():return {"rows":[(1,version(1))],"columns":[("value",23),("token",25)]}
def write(old,new):return {"rows":[(version(old),version(new))],"columns":[("old",25),("new",25)],"tag":"UPDATE 1"}


class EpochTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(os.environ["MTW_EPOCH_TEST_RUN"])/self._testMethodName;self.root.mkdir()
        self.synthetic=synthetic();self.synthetic.__enter__();self.created=[]
    def tearDown(self):
        for c in self.created:
            for capture in c._captures:
                for connection in list(capture._live.values()):
                    try:connection._raw.close_error=None;connection.rollback();connection.close()
                    except Exception:pass
                try:capture.close(source_closed=False)
                except Exception:pass
        self.synthetic.__exit__(None,None,None)
    def create(self,**kwargs):
        setup=Setup();c=coordinator.EpochCoordinator.create(self.root/("store-"+uuid.uuid4().hex),setup,
            schema="mtw_provenance_epoch_mock",keys=kwargs.pop("keys",("k",)),exclusive_writers=True,**kwargs)
        self.created.append(c);return c,setup
    def barrier(self,c):return c.quiesce(expected_generation=c.manifest["generation"])
    def handoff(self,c,setup):return c.handoff(setup,caller=self.barrier(c),expected_generation=c.manifest["generation"])
    def finish(self,c,setup):return c.finish(setup,caller=self.barrier(c),expected_generation=c.manifest["generation"])
    def assertFailed(self,c):
        self.assertTrue((c.path/"operation.lock").is_file());self.assertTrue(c._poisoned)
        fresh=coordinator.EpochCoordinator(c.path).verify_chain();self.assertFalse(fresh["valid"]);self.assertFalse(fresh["rawEpochChainComplete"])
    def connect(self,c,responses=()):
        raw=RawConnection(responses);return c.current.wrap(raw),raw

    def test_01_commit_before_old_seal_and_new_snapshot(self):
        c,s=self.create();old=c.current;observed=[]
        def stage(name):
            observed.append(name)
            if name=="boundary_prepared":self.assertFalse(old._closed);self.assertEqual(len(c._captures),1)
            if name=="new_published":self.assertFalse(c._captures[-1]._released)
        c._stage=stage;new=self.handoff(c,s)
        self.assertLess(observed.index("database_acknowledged"),observed.index("old_sealed"))
        self.assertLess(observed.index("old_sealed"),observed.index("new_published"));self.assertTrue(new._released)
        self.assertEqual(new._seq,1)
    def test_02_dropped_wrapper_strong_registry_blocks(self):
        c,s=self.create();connection,raw=self.connect(c);identity=connection._identity;del connection;gc.collect()
        self.assertIn(identity,c.current._live)
        with self.assertRaises(sources.EpochError):self.handoff(c,s)
        self.assertFalse((c.path/"operation.lock").exists())
    def test_03_idle_close_ack_persisted(self):
        c,s=self.create();connection,raw=self.connect(c);identity=connection._identity;connection.close()
        self.assertNotIn(identity,c.current._live);self.assertTrue(c.registry.closed(c.current.epoch));self.assertFalse(c.current.gaps)
    def test_04_external_close_is_not_observed_ack(self):
        c,s=self.create();connection,raw=self.connect(c);raw.close();connection.close()
        self.assertTrue(c.current._live);self.assertIn("close_unobserved",[g["code"] for g in c.current.gaps])
    def test_05_close_exception_identity_retained(self):
        c,s=self.create();connection,raw=self.connect(c);original=OriginalError("actual close failure");raw.close_error=original
        with self.assertRaises(OriginalError) as caught:connection.close()
        self.assertIs(caught.exception,original);self.assertTrue(c.current._live)
    def test_06_connection_registry_bounded(self):
        c,s=self.create(max_live=1);first,_=self.connect(c)
        with self.assertRaises(sources.EpochError):self.connect(c)
        first.close();second,_=self.connect(c);self.assertEqual(len(c.current._live),1);second.close()
    def test_07_active_transaction_refused_before_intent(self):
        c,s=self.create();connection,raw=self.connect(c,[read()]);connection.execute(c.current.profile.read_sql,("k",)).fetchone()
        with self.assertRaises(sources.EpochError):self.handoff(c,s)
        self.assertFalse((c.path/"intent.json").exists());self.assertFalse((c.path/"operation.lock").exists())
    def test_08_unread_discarded_result_blocks(self):
        c,s=self.create();connection,raw=self.connect(c,[read()]);cursor=connection.execute(c.current.profile.read_sql,("k",));del cursor;gc.collect()
        connection.commit();connection.close()
        self.assertTrue(c.current._pending_results)
        with self.assertRaises(sources.EpochError):self.handoff(c,s)
    def test_09_unknown_not_healed_by_idle_rollback(self):
        c,s=self.create();connection,raw=self.connect(c,[read()]);connection.execute(c.current.profile.read_sql,("k",)).fetchone();connection._unknown("synthetic-unknown")
        connection.rollback();connection.close()
        with self.assertRaises(sources.EpochError):self.handoff(c,s)
    def test_10_stale_generation_no_guard_or_mutation(self):
        c,s=self.create();caller=self.barrier(c);before=(c.path/"manifest.json").read_bytes()
        with self.assertRaises(sources.EpochError):c.handoff(s,caller=caller,expected_generation=1)
        self.assertEqual(before,(c.path/"manifest.json").read_bytes());self.assertFalse((c.path/"operation.lock").exists());self.assertFalse((c.path/"intent.json").exists());self.assertFalse(c._poisoned)
    def test_11_wrong_caller_no_poison(self):
        c,s=self.create();caller=self.barrier(c);wrong={**caller,"token":"wrong"}
        with self.assertRaises(sources.EpochError):c.handoff(s,caller=wrong,expected_generation=0)
        self.assertFalse(c._poisoned);self.assertFalse((c.path/"operation.lock").exists())
        self.assertIsNotNone(c.handoff(s,caller=caller,expected_generation=0))
    def test_12_quiesce_stops_new_wrapper_admission(self):
        c,s=self.create();token=self.barrier(c);self.assertEqual(token,self.barrier(c))
        with self.assertRaises(sources.EpochError):self.connect(c)
    def test_13_shared_transaction_all_owned_locks(self):
        c,s=self.create();self.handoff(c,s);queries=[q for q,p in s.queries]
        self.assertEqual(sum(q.startswith("BEGIN") for q in queries),1);self.assertEqual(queries.count("COMMIT"),1)
        lock=next(q for q in queries if q.startswith("LOCK TABLE"));n=c.current.profile.names
        for relation in (n.business,n.object("installation"),n.object("audit"),n.object("state")):self.assertIn(relation,lock)
    def test_14_changed_boundary_refuses_old_seal(self):
        c,s=self.create();old=c.current;s.change_next=True
        with self.assertRaises(sources.EpochError):self.handoff(c,s)
        self.assertFalse(old._closed);self.assertFailed(c)
    def test_15_catalog_replayed_not_trusted_flag(self):
        c,s=self.create();calls=[]
        def verify(connection,installation):calls.append(type(connection).__name__);return mock_verify(connection,installation)
        with patch.object(sources,"verify_installation",verify):self.handoff(c,s)
        self.assertEqual(calls.count("Control"),2);self.assertGreaterEqual(calls.count("Replay"),4)
    def test_16_unacknowledged_commit_preserves_error_and_guard(self):
        c,s=self.create();original=OriginalError("setup COMMIT disconnected");s.commit_error=original
        with self.assertRaises(OriginalError) as caught:self.handoff(c,s)
        self.assertIs(caught.exception,original);self.assertFalse(c.current._closed);self.assertFailed(c)
    def test_17_commit_and_marker_double_fault_guard(self):
        c,s=self.create();s.commit_error=OriginalError("no ACK")
        with patch.object(c,"_failure_marker",side_effect=OSError("marker denied")):
            with self.assertRaises(OriginalError):self.handoff(c,s)
        self.assertFalse((c.path/"failed.json").exists());self.assertFailed(c)
    def test_18_old_source_close_io_failure(self):
        c,s=self.create()
        with patch.object(c.current.sources,"close",side_effect=OSError("source close IO")):
            with self.assertRaises(sources.EpochError):self.handoff(c,s)
        self.assertFailed(c)
    def test_19_new_publication_io_failure_keeps_old(self):
        c,s=self.create();old=c.current
        with patch.object(EpochCapture,"initialize_from_boundary",side_effect=OSError("new publish IO")):
            with self.assertRaises(OSError):self.handoff(c,s)
        self.assertTrue(old._closed);self.assertTrue(JournalReader(old.journal.path).verify().complete);self.assertFailed(c)
    def protected_fault(self,c):
        actual=coordinator._sync_directory
        def sync(path):
            if path==c.path and (c.path/"operation.lock").exists() and not (c.path/"intent.json").exists() and coordinator.read_json(c.path/"manifest.json")["generation"]==1:raise OSError("protected final sync")
            return actual(path)
        return patch.object(coordinator,"_sync_directory",sync)
    def test_20_final_protected_sync_failure(self):
        c,s=self.create()
        with self.protected_fault(c):
            with self.assertRaises(OSError):self.handoff(c,s)
        self.assertFailed(c)
    def test_21_protected_sync_marker_double_failure(self):
        c,s=self.create()
        with self.protected_fault(c),patch.object(c,"_failure_marker",side_effect=OSError("secondary marker failure")):
            with self.assertRaises(OSError):self.handoff(c,s)
        self.assertFalse((c.path/"failed.json").exists());self.assertFailed(c)
    def child(self,mode,path,nonce=""):
        return subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),"--child",mode,str(path),nonce],capture_output=True,text=True,timeout=20)
    def test_22_permanent_native_mutex_actual_child_exclusion(self):
        c,s=self.create();before=coordinator.file_binding(c.path/"coordination.lock")
        with coordinator.NativeMutex(c.path/"coordination.lock",c.nonce):result=self.child("native",c.path,c.nonce)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('"blocked": true',result.stdout)
        self.assertEqual(before,coordinator.file_binding(c.path/"coordination.lock"))
    def crash(self,stage):
        path=self.root/"crashed";result=self.child(stage,path);self.assertEqual(result.returncode,73,result.stdout+result.stderr)
        fresh=coordinator.EpochCoordinator(path);self.assertFalse(fresh.verify_chain()["rawEpochChainComplete"])
        owner=coordinator.read_json(path/"operation.lock");outcome=fresh.recover(owner=owner)
        self.assertEqual(outcome["mode"],"inspect-only");self.assertFalse(outcome["canResume"]);self.assertTrue((path/"operation.lock").exists());return path
    def test_23_real_child_crash_after_durable_intent(self):self.crash("intent_durable")
    def test_24_real_child_crash_after_old_seal(self):
        path=self.crash("old_sealed");self.assertTrue(JournalReader(path/"epochs/epoch-0000/journal").verify().complete)
    def test_25_real_child_crash_after_new_publication(self):
        path=self.crash("new_published");self.assertTrue((path/"epochs/epoch-0001").is_dir())
    def test_26_late_old_fetch_invalidates_continuity(self):
        c,s=self.create();connection,raw=self.connect(c,[read()]);cursor=connection.execute(c.current.profile.read_sql,("k",));cursor.fetchone();connection.commit();connection.close()
        self.handoff(c,s)
        with self.assertRaises(OriginalError):cursor.fetchone()
        self.assertTrue(c._poisoned);self.assertFalse(c.verify_chain()["valid"])
    def test_27_late_marker_io_failure_live_still_invalid(self):
        c,s=self.create();old=c.current;self.handoff(c,s)
        with patch.object(c,"_failure_marker",side_effect=OSError("no marker")):old.activity("fetch")
        self.assertTrue(c._poisoned);self.assertFalse(c.verify_chain()["valid"])
    def test_28_idempotent_old_close_cleanup_harmless(self):
        c,s=self.create();connection,raw=self.connect(c);connection.close();self.handoff(c,s);connection.close()
        self.assertFalse(c._poisoned);self.assertTrue(self.finish(c,s)["rawEpochChainComplete"])
    def test_29_two_epochs_complete_raw_not_sql_or_prune(self):
        c,s=self.create();old=c.current;new=self.handoff(c,s);result=self.finish(c,s)
        self.assertTrue(result["valid"]);self.assertTrue(result["rawEpochChainComplete"])
        self.assertFalse(result["sourceClosureVerified"]);self.assertFalse(result["coreProofImplemented"])
        self.assertEqual(c.prune()["deleted"],0);self.assertFalse(c.prune()["allowed"])
        self.assertEqual(len(c.manifest["sealed"]),2);self.assertNotEqual(old.clock_domain,new.clock_domain)
    def test_30_changed_or_missing_sealed_source_invalid(self):
        c,s=self.create();self.handoff(c,s);self.finish(c,s);path=c.path/"epochs/epoch-0000/sources/records.jsonl"
        raw=path.read_bytes();path.write_bytes(raw.replace(b"synthetic-test",b"synthetic-tesz"))
        result=coordinator.EpochCoordinator(c.path).verify_chain();self.assertFalse(result["valid"]);self.assertFalse(result["rawEpochChainComplete"])
        path.write_bytes(raw);path.unlink();self.assertFalse(coordinator.EpochCoordinator(c.path).verify_chain()["valid"])
    def test_31_third_handoff_refused_without_poison(self):
        c,s=self.create();self.handoff(c,s);caller=self.barrier(c)
        with self.assertRaises(sources.EpochError):c.handoff(s,caller=caller,expected_generation=1)
        self.assertFalse((c.path/"operation.lock").exists());self.assertFalse(c._poisoned)
        self.assertTrue(c.finish(s,caller=caller,expected_generation=1)["rawEpochChainComplete"])
    def test_32_ledger_overflow_no_complete_footer(self):
        c,s=self.create();s.ledger*=2
        with self.assertRaises(sources.EpochError):c.handoff(s,caller=self.barrier(c),expected_generation=0,max_ledger=1)
        self.assertFailed(c);reader=sources.SourceLogReader(c.path/"boundaries/boundary-0000");self.assertFalse(reader.verify()["complete"])
    def test_33_disk_cross_epoch_version_origin_no_synthetic_read(self):
        c,s=self.create();connection,raw=self.connect(c,[write(1,2)]);connection.execute(c.current.profile.write_sql,(1,"k"));connection.commit();connection.close()
        s.rows=[("k",1,version(2))];s.ledger.append((version(2),"k","UPDATE",True,version(1),1,1))
        self.handoff(c,s);self.finish(c,s)
        with c.registry.open() as db:
            row=db.execute("SELECT origin_epoch,origin_seq FROM versions WHERE epoch='epoch-0001' AND version=?",(version(2),)).fetchone()
            self.assertEqual(row[0],"epoch-0000");self.assertIsInstance(row[1],int);self.assertEqual(db.execute("SELECT count(*) FROM reads").fetchone()[0],0)
    def test_34_two_real_threads_only_one_handoff(self):
        c,s=self.create();caller=self.barrier(c);entered=threading.Event();release=threading.Event();outcomes=[]
        def stage(name):
            if name=="intent_durable":entered.set();self.assertTrue(release.wait(5))
        c._stage=stage
        def worker():
            try:c.handoff(s,caller=caller,expected_generation=0);outcomes.append("ok")
            except sources.EpochError:outcomes.append("stale")
        a=threading.Thread(target=worker);b=threading.Thread(target=worker);a.start();self.assertTrue(entered.wait(5));b.start();release.set();a.join(10);b.join(10)
        self.assertFalse(a.is_alive() or b.is_alive());self.assertCountEqual(outcomes,["ok","stale"])
        self.assertEqual(c.manifest["generation"],1);self.assertFalse(c._poisoned);self.assertFalse((c.path/"operation.lock").exists())
    def test_35_metadata_same_size_change_during_read_refused(self):
        path=self.root/"metadata.json";path.write_bytes(b'{"a":1}')
        original=Path.open
        class Changed:
            def __init__(self,file):self.file=file
            def __enter__(self):return self
            def __exit__(self,*args):self.file.close()
            def fileno(self):return self.file.fileno()
            def read(self,size):
                raw=self.file.read(size)
                with original(path,"r+b") as writer:writer.write(b'{"a":2}');writer.flush();os.fsync(writer.fileno())
                os.utime(path,ns=(path.stat().st_atime_ns,path.stat().st_mtime_ns+10000000));return raw
        calls=[]
        def instrument(target,*args,**kwargs):
            file=original(target,*args,**kwargs)
            if target==path and args and args[0]=="rb" and not calls:calls.append(True);return Changed(file)
            return file
        with patch.object(Path,"open",instrument):
            with self.assertRaises(sources.EpochError):coordinator.read_json(path)
    def test_36_file_binding_same_size_rewrite_refused(self):
        path=self.root/"source.bin";path.write_bytes(b"aaaa");original=Path.open;calls=[]
        class Changed:
            def __init__(self,file):self.file=file
            def __enter__(self):return self
            def __exit__(self,*args):self.file.close()
            def fileno(self):return self.file.fileno()
            def read(self,size):
                value=self.file.read(size)
                if value:
                    with original(path,"r+b") as writer:writer.write(b"bbbb");writer.flush();os.fsync(writer.fileno())
                    os.utime(path,ns=(path.stat().st_atime_ns,path.stat().st_mtime_ns+10000000))
                return value
        def instrument(target,*args,**kwargs):
            file=original(target,*args,**kwargs)
            if target==path and args and args[0]=="rb" and not calls:calls.append(True);return Changed(file)
            return file
        with patch.object(Path,"open",instrument):
            with self.assertRaises(sources.EpochError):coordinator.file_binding(path)
    def test_37_generator_keys_preserved_once(self):
        c,s=self.create(keys=(k for k in ("k",)));self.assertEqual(c.current.keys,frozenset(("k",)));self.assertIsNotNone(self.handoff(c,s))
    def test_38_manifest_guard_or_poison_never_valid(self):
        c,s=self.create();(c.path/"intent.json").write_text("{}")
        self.assertFalse(c.verify_chain()["valid"]);(c.path/"intent.json").unlink();c.invalidate("explicit")
        self.assertFalse(c.verify_chain()["valid"]);self.assertFalse(coordinator.EpochCoordinator(c.path).verify_chain()["valid"])
    def test_39_rollback_tag_does_not_confirm_commit(self):
        c,s=self.create();s.commit_tag="ROLLBACK"
        with self.assertRaises(sources.EpochError):self.handoff(c,s)
        self.assertFailed(c);self.assertFalse(c.current._closed)
    def test_40_boundary_new_initialization_binds_exact_bytes(self):
        c,s=self.create();new=self.handoff(c,s)
        records=list(sources.SourceLogReader(new.sources.path).iter_records()) if new.sources.closed else []
        self.assertEqual(records,[])
        self.finish(c,s);records=list(sources.SourceLogReader(new.sources.path).iter_records())
        first=records[0]["payload"];self.assertEqual(first["kind"],"boundary-initialization")
        boundary=c.path/"boundaries"/first["boundaryId"]
        self.assertEqual(first["boundaryBindings"],{name:coordinator.file_binding(boundary/name) for name in ("index.json","records.jsonl")})


def child(mode,path,nonce):
    if mode=="native":
        try:
            with coordinator.NativeMutex(path/"coordination.lock",nonce):print(json.dumps({"blocked":False}))
        except OSError:print(json.dumps({"blocked":True}));return 0
        return 2
    with synthetic():
        c=coordinator.EpochCoordinator.create(path,Setup(),schema="mtw_provenance_epoch_mock",keys=("k",),exclusive_writers=True)
        c._stage=lambda stage:os._exit(73) if stage==mode else None
        c.handoff(Setup(),caller=c.quiesce(expected_generation=0),expected_generation=0)
    return 3


def main():
    if len(sys.argv)>1 and sys.argv[1]=="--child":return child(sys.argv[2],Path(sys.argv[3]),sys.argv[4])
    root=Path(os.environ["MTW_JOURNAL_SCRATCH"])/("epoch-r1-unit-"+uuid.uuid4().hex);root.mkdir();os.environ["MTW_EPOCH_TEST_RUN"]=str(root)
    here=Path(__file__).resolve().parent
    def bindings():
        files=[p for p in here.iterdir() if p.is_file() and p.suffix in (".py",".json") and p.name!="candidate-index.json"]
        files.extend(sources.BASE/name for name in ("profile.py","source_log.py"))
        files.extend(sources.ROOT/name for name in ("integrations/python/moontxnwitness_capture/capture.py","integrations/python/moontxnwitness_capture/capture_v3.py","integrations/python/moontxnwitness_capture/journal_v3.py","experiments/provenance/prototype.py","experiments/provenance/capture_profile.py"))
        return {p.relative_to(sources.ROOT).as_posix():{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
    before=bindings();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EpochTests));after=bindings()
    receipt={"schema":1,"passed":result.wasSuccessful() and before==after,"tests":result.testsRun,"actualMockExecution":True,
        "actualFilesystemExecution":True,"actualNativeChildExecution":True,"actualDatabaseExecution":False,"formalPerformanceMeasurement":False,
        "sourceClosureVerified":False,"coreProofImplemented":False,"formalEligible":False,"independentAcceptance":False,
        "sourceBindingsBefore":before,"sourceBindingsAfter":after,"sourceBindingsUnchanged":before==after,
        "failures":[{"test":str(test),"trace":trace} for test,trace in result.failures+result.errors],"skipped":[{"test":str(test),"reason":reason} for test,reason in result.skipped]}
    (root/"test-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8");print("Epoch receipt: "+str(root/"test-receipt.json"))
    return 0 if receipt["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
