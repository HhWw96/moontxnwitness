"""Prepared FS/mock regression suite. No database, build or benchmark.

Exercises the original full point initializer using explicitly synthetic
catalog/business responses. Only its two catalog-verifier helpers are mocked;
the initializer, ACK proxy and snapshot publication barrier execute normally.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import epoch_coordinator as coordinator
import epoch_sources as sources
from initialization_guard import InitialCommitSetup,bounded_keys
from point_epoch import EpochCapture
import test_epoch as original_tests
from psycopg.rows import tuple_row


class InitSetup:
    def __init__(self):
        self.autocommit=True;self.row_factory=tuple_row;self.closed=False
        self.info=SimpleNamespace(transaction_status=0,server_version=180006,backend_pid=5678)
        self.tag="COMMIT";self.pgstatus=1;self.after=0;self.commit_rows=False
        self.error=None;self.rollback_error=None;self.lost=False
        self.commits=0;self.rollbacks=0;self.queries=[];self.on_commit=None
        self.names=sources.plain.ColumnPointProfile("mtw_provenance_epoch_init_mock","items").names
        self.statements=set(sources.plain.ddl(self.names));self.cursor=None

    def execute(self,sql,params=None):
        self.queries.append((sql,params));cursor=original_tests.RawCursor(self)
        def rows(value):return cursor.configure(value,[("field",25)]*len(value[0]) if value else [("field",25)])
        if sql=="BEGIN ISOLATION LEVEL READ COMMITTED":
            self.info.transaction_status=2;return cursor.configure([],tag="BEGIN")
        if sql.startswith("LOCK TABLE "):return cursor.configure([],tag="LOCK TABLE")
        if sql==sources.plain.table_catalog_sql():return rows([(123456,"r",False,False,True)])
        if sql.startswith("SELECT attname,"):return rows([("id","text",True,"",""),("value","integer",True,"","")])
        if sql.startswith("SELECT am.amname,"):return rows([("btree","pg_catalog","text_ops",True,True)])
        if sql.startswith("SELECT contype,"):return rows([("p",[1],False,False,True,True),("n",[1],False,False,True,True),("n",[2],False,False,True,True)])
        if sql=='SELECT "id" FROM '+self.names.business+' LIMIT 65':return rows([("k",)])
        if sql.startswith('SELECT "id","value",') and sql.endswith(' LIMIT 65'):return rows([("k",1,original_tests.version(1))])
        if sql in self.statements:return cursor.configure([],tag="SYNTHETIC DDL")
        if sql.startswith("INSERT INTO "+self.names.object("installation")):return cursor.configure([],tag="INSERT 0 1")
        if sql=="COMMIT":
            self.commits+=1
            if self.on_commit:self.on_commit()
            if self.error and not self.lost:raise self.error
            self.info.transaction_status=self.after
            if self.error:raise self.error
            cursor.configure([(1,)] if self.commit_rows else [],[("field",23)] if self.commit_rows else (),tag=self.tag)
            cursor.pgresult=SimpleNamespace(status=self.pgstatus);self.cursor=cursor;return cursor
        if sql=="ROLLBACK":
            self.rollbacks+=1
            if self.rollback_error:raise self.rollback_error
            self.info.transaction_status=0;return cursor.configure([],tag="ROLLBACK")
        raise AssertionError("Unexpected synthetic initializer SQL "+sql)


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(os.environ["MTW_EPOCH_HARDENING_RUN"])/self._testMethodName;self.root.mkdir()
        self.captures=[]
    def tearDown(self):
        for capture in self.captures:
            try:capture.close(source_closed=False)
            except BaseException:pass
    def capture(self):
        c=EpochCapture(self.root/("capture-"+uuid.uuid4().hex),epoch="epoch-0000",registry=None,
            schema="mtw_provenance_epoch_init_mock",keys=("k",),exclusive_writers=True)
        self.captures.append(c);return c
    def initialize(self,capture,setup):
        with patch.object(sources.plain,"_check_business_effects"),patch.object(sources.plain,"verify_installation"):
            return capture.initialize(setup)
    def no_snapshot(self,capture):
        self.assertFalse(capture._initialized);self.assertEqual(capture._seq,0);self.assertFalse(capture._released)
        self.assertIn("initialization_unconfirmed",[gap["code"] for gap in capture.gaps])
    def rejected_keys(self,values):
        path=self.root/"must-not-exist";setup=InitSetup()
        with patch.object(Path,"mkdir",side_effect=AssertionError("Filesystem touched before key admission")):
            with self.assertRaises(sources.EpochError):
                coordinator.EpochCoordinator.create(path,setup,schema="mtw_provenance_epoch_init_mock",keys=values,exclusive_writers=True)
        self.assertEqual(setup.queries,[]);self.assertFalse(path.exists())

    def test_01_infinite_keys_stop_at_first_overflow(self):
        calls=[]
        def keys():
            for i in range(1000000):
                calls.append(i)
                if i==65:raise AssertionError("Consumed item66")
                yield str(i)
        self.rejected_keys(keys());self.assertEqual(len(calls),65)
    def test_02_exact64_single_pass_generator(self):
        calls=[]
        def keys():
            for i in range(64):calls.append(i);yield str(i)
        self.assertEqual(bounded_keys(keys()),tuple(str(i) for i in range(64)));self.assertEqual(len(calls),64)
    def test_03_generator_error_identity_before_filesystem(self):
        original=original_tests.OriginalError("key input failed");path=self.root/"never"
        def keys():yield "k";raise original
        with patch.object(Path,"mkdir",side_effect=AssertionError("Filesystem touched")):
            with self.assertRaises(original_tests.OriginalError) as caught:
                coordinator.EpochCoordinator.create(path,InitSetup(),schema="mtw_provenance_epoch_init_mock",keys=keys(),exclusive_writers=True)
        self.assertIs(caught.exception,original);self.assertFalse(path.exists())
    def test_04_empty_keys_rejected_before_filesystem(self):self.rejected_keys(iter(()))
    def test_05_duplicate_keys_rejected_before_filesystem(self):self.rejected_keys(iter(("k","k")))
    def test_06_nontext_unhashable_keys_rejected_before_filesystem(self):self.rejected_keys(iter((["k"],)))
    def test_07_utf8_byte_limit_rejected_before_filesystem(self):self.rejected_keys(iter(("\u4e2d"*171,)))
    def test_08_surrogate_rejected_before_filesystem(self):self.rejected_keys(iter(("\ud800",)))
    def test_09_character_limit_rejected_before_encoding(self):self.rejected_keys(iter(("k"*513,)))
    def test_10_point_constructor_independently_bounds_keys(self):
        calls=[]
        def keys():
            for i in range(1000000):calls.append(i);yield str(i)
        with patch.object(Path,"mkdir",side_effect=AssertionError("Filesystem touched")):
            with self.assertRaises(sources.EpochError):
                EpochCapture(self.root/"never",epoch="epoch-0000",registry=None,schema="mtw_provenance_epoch_init_mock",keys=keys(),exclusive_writers=True)
        self.assertEqual(len(calls),65)
    def test_11_confirmed_initial_commit_precedes_snapshot(self):
        c,s=self.capture(),InitSetup();observed=[];original=c.publish_snapshot
        def publish(initial,**kwargs):
            observed.append((s.commits,s.info.transaction_status,c._initial_commit_guard.confirmed,c.sources.count))
            return original(initial,**kwargs)
        with patch.object(c,"publish_snapshot",publish):self.initialize(c,s)
        self.assertEqual(observed,[(1,0,True,2)]);self.assertTrue(c._initialized);self.assertEqual(c._seq,1)
        self.assertFalse(c.gaps);self.assertFalse(hasattr(c,"_initial_commit_guard"))
    def test_12_rollback_command_tag_never_publishes(self):
        c,s=self.capture(),InitSetup();s.tag="ROLLBACK"
        with self.assertRaises(sources.EpochError):self.initialize(c,s)
        self.no_snapshot(c);self.assertEqual(s.rollbacks,1)
    def test_13_non_command_result_never_publishes(self):
        c,s=self.capture(),InitSetup();s.pgstatus=2
        with self.assertRaises(sources.EpochError):self.initialize(c,s)
        self.no_snapshot(c)
    def test_14_non_idle_ack_never_publishes(self):
        c,s=self.capture(),InitSetup();s.after=2
        with self.assertRaises(sources.EpochError):self.initialize(c,s)
        self.no_snapshot(c)
    def test_15_commit_with_rows_never_publishes(self):
        c,s=self.capture(),InitSetup();s.commit_rows=True
        with self.assertRaises(sources.EpochError):self.initialize(c,s)
        self.no_snapshot(c)
    def test_16_commit_exception_identity_and_unknown_gap(self):
        c,s=self.capture(),InitSetup();s.error=original_tests.OriginalError("setup COMMIT failed")
        with self.assertRaises(original_tests.OriginalError) as caught:self.initialize(c,s)
        self.assertIs(caught.exception,s.error);self.no_snapshot(c);self.assertEqual(s.rollbacks,1)
        self.assertIn("initialization_commit_unknown",[gap["code"] for gap in c.gaps])
    def test_17_lost_ack_after_synthetic_commit_not_healed(self):
        c,s=self.capture(),InitSetup();s.error=original_tests.OriginalError("discarded ACK");s.lost=True
        with self.assertRaises(original_tests.OriginalError) as caught:self.initialize(c,s)
        self.assertIs(caught.exception,s.error);self.no_snapshot(c);self.assertEqual(s.commits,1);self.assertEqual(s.info.transaction_status,0)
    def test_18_secondary_rollback_failure_preserves_primary(self):
        c,s=self.capture(),InitSetup();s.error=original_tests.OriginalError("primary");s.rollback_error=OSError("rollback unavailable")
        with self.assertRaises(original_tests.OriginalError) as caught:self.initialize(c,s)
        self.assertIs(caught.exception,s.error);self.no_snapshot(c)
    def test_19_secondary_error_log_failure_preserves_primary(self):
        c,s=self.capture(),InitSetup();s.error=original_tests.OriginalError("primary")
        with patch.object(c.sources,"append",side_effect=OSError("source unavailable")):
            with self.assertRaises(original_tests.OriginalError) as caught:self.initialize(c,s)
        self.assertIs(caught.exception,s.error);self.no_snapshot(c);self.assertTrue(c.sources.failed)
    def test_20_success_ack_storage_failure_refuses_snapshot(self):
        c,s=self.capture(),InitSetup();original=OSError("ACK disk failure")
        with patch.object(c.sources,"append",side_effect=original):
            with self.assertRaises(OSError) as caught:self.initialize(c,s)
        self.assertIs(caught.exception,original);self.no_snapshot(c)
    def test_21_proxy_preserves_original_cursor_and_parameters(self):
        c,s=self.capture(),InitSetup();s.info.transaction_status=2;guard=InitialCommitSetup(s,c)
        result=guard.execute("COMMIT",None)
        self.assertIs(result,s.cursor);self.assertTrue(guard.confirmed);self.assertEqual(s.queries,[("COMMIT",None)])
    def test_22_proxy_rejects_duplicate_commit_without_second_sql(self):
        c,s=self.capture(),InitSetup();s.info.transaction_status=2;guard=InitialCommitSetup(s,c);guard.execute("COMMIT")
        with self.assertRaises(sources.EpochError):guard.execute("COMMIT")
        self.assertEqual(s.commits,1)
    def test_23_initial_snapshot_barrier_cannot_be_bypassed(self):
        c,s=self.capture(),InitSetup();c._initial_commit_guard=InitialCommitSetup(s,c)
        try:
            with self.assertRaises(sources.EpochError):c.publish_snapshot({"k":original_tests.version(1)},consistent=True)
            self.assertFalse(c._initialized);self.assertEqual(c._seq,0)
        finally:del c._initial_commit_guard
    def test_24_scope_claims_and_prune_stay_unproved(self):
        c,s=self.capture(),InitSetup();self.initialize(c,s)
        self.assertFalse(c.core_proof_implemented);self.assertFalse(c.formal_eligible)
        self.assertIsNone(c._coordinator)
    def test_25_unknown_initialization_cannot_retry_or_heal(self):
        c,s=self.capture(),InitSetup();s.error=original_tests.OriginalError("lost");s.lost=True
        with self.assertRaises(original_tests.OriginalError):self.initialize(c,s)
        before=list(s.queries);s.error=None
        with self.assertRaises(sources.EpochError):self.initialize(c,s)
        self.assertEqual(s.queries,before);self.no_snapshot(c)
    def test_26_initial_commit_requires_active_setup_transaction(self):
        c,s=self.capture(),InitSetup();guard=InitialCommitSetup(s,c)
        with self.assertRaises(sources.EpochError):guard.execute("COMMIT")
        self.assertFalse(guard.confirmed);self.assertFalse(c._initialized)


def main():
    root=Path(os.environ["MTW_JOURNAL_SCRATCH"])/("epoch-r2-unit-"+uuid.uuid4().hex);root.mkdir()
    os.environ["MTW_EPOCH_HARDENING_RUN"]=str(root);os.environ["MTW_EPOCH_TEST_RUN"]=str(root)
    here=Path(__file__).resolve().parent
    def bindings():
        files=[p for p in here.iterdir() if p.is_file() and p.suffix in (".py",".json") and not p.name.startswith("candidate-index")]
        files.extend(sources.ROOT/name for name in json.loads((here/"baseline-r1/candidate-index.json").read_bytes())["dependencies"])
        return {p.relative_to(sources.ROOT).as_posix():{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
    before=bindings()
    for file in sorted(here.glob("*.py")):ast.parse(file.read_text(encoding="utf8"),filename=file.name)
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(original_tests.EpochTests),unittest.defaultTestLoader.loadTestsFromTestCase(HardeningTests)])
    result=unittest.TextTestRunner(verbosity=2).run(suite);after=bindings()
    receipt={"schema":1,"passed":result.wasSuccessful() and before==after,"tests":result.testsRun,"expectedTests":73,
        "actualMockExecution":True,"actualFilesystemExecution":True,"actualNativeChildExecution":True,"actualDatabaseExecution":False,
        "formalPerformanceMeasurement":False,"sourceClosureVerified":False,"coreProofImplemented":False,"formalEligible":False,"independentAcceptance":False,
        "sourceBindingsBefore":before,"sourceBindingsAfter":after,"sourceBindingsUnchanged":before==after,
        "failures":[{"test":str(test),"trace":trace} for test,trace in result.failures+result.errors],"skipped":[{"test":str(test),"reason":reason} for test,reason in result.skipped]}
    receipt["passed"]=receipt["passed"] and result.testsRun==73 and not result.skipped
    path=root/"test-receipt.json"
    with path.open("x",encoding="utf8") as file:json.dump(receipt,file,indent=2);file.write("\n")
    print("Epoch hardening receipt: "+str(path));return 0 if receipt["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
