"""Bounded FS/mock checks; these never count as actual PostgreSQL evidence."""
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import profile as draft
from source_log import SourceLog,SourceLogReader,SourceLogError
from moontxnwitness_capture.journal_v3 import JournalReader
from psycopg.rows import tuple_row


class BusinessError(Exception):pass


class RawCursor:
    def __init__(self,connection):
        self.connection=connection;self.row_factory=connection.row_factory;self.closed=False
        self.description=None;self.rowcount=-1;self.position=0;self.statusmessage=None;self.rows=[];self.fetch_error=None
        self.closed_error=BusinessError("actual closed cursor")
    @property
    def rownumber(self):return self.position if self.description is not None else None
    def execute(self,query,params=None,**kwargs):
        self.connection.last_query=query;self.connection.last_params=params;self.connection.info.transaction_status=2
        item=self.connection.responses.pop(0)
        if "error" in item:raise item["error"]
        self.rows=list(item.get("rows",[]));self.position=0
        self.description=tuple(SimpleNamespace(name=name,type_code=code) for name,code in item.get("columns",[])) or None
        self.rowcount=item.get("rowcount",len(self.rows));self.statusmessage=item.get("status","SELECT "+str(self.rowcount))
        self.fetch_error=item.get("fetch_error");return self
    def fetchone(self):
        if self.closed:raise self.closed_error
        if self.fetch_error:raise self.fetch_error
        if self.position>=len(self.rows):return None
        value=self.rows[self.position];self.position+=1;return value
    def fetchmany(self,size=None):
        if size==0:return []
        size=1 if size is None else size
        result=[]
        for _ in range(size):
            value=self.fetchone()
            if value is None:break
            result.append(value)
        return result
    def fetchall(self):return self.fetchmany(max(1,len(self.rows)-self.position))
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class RawConnection:
    def __init__(self,responses=()):
        self.responses=list(responses);self.info=SimpleNamespace(transaction_status=0)
        self.autocommit=False;self.closed=False;self.row_factory=tuple_row
    def cursor(self,*args,**kwargs):return RawCursor(self)
    def commit(self):self.info.transaction_status=0
    def rollback(self):self.info.transaction_status=0
    def close(self):self.closed=True;self.info.transaction_status=4


def version(number):return "00000000-0000-0000-0000-"+str(number).zfill(12)
def read(value=1,number=1,**extra):return {"rows":[(value,version(number))],"columns":[("value",23),("version",25)],**extra}
def command(old=1,new=2):return {"rows":[(version(old),version(new))],"columns":[("old",25),("new",25)],"rowcount":1,"status":"UPDATE 1"}


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(os.environ["MTW_PLAIN_TEST_RUN"])/self._testMethodName;self.root.mkdir();self.captures=[]
    def capture(self,responses=()):
        session=draft.PlainJournalCapture(self.root/("capture-"+uuid.uuid4().hex),schema="mtw_provenance_mock",keys=("k",),exclusive_writers=True)
        # Explicit synthetic fixture only: no database installation or proof is
        # claimed by this mock. Production users must call initialize(setup).
        session.installation=SimpleNamespace();session.publish_snapshot({"k":version(1)},consistent=True)
        raw=RawConnection(responses);connection=session.wrap(raw);self.captures.append((session,connection));return session,connection,raw
    def events(self,session):
        for captured,connection in self.captures:
            if captured is session and not connection._raw.closed:
                if connection._tx:connection.rollback()
                connection.close()
        session.close(source_closed=True)
        return list(JournalReader(session.journal.path).iter_events(require_complete=False))
    def tearDown(self):
        for session,connection in self.captures:
            try:
                if not connection._raw.closed:
                    if connection._tx:connection.rollback()
                    connection.close()
                session.close(source_closed=False)
            except Exception:pass

    def test_01_source_roundtrip_is_bounded_stream(self):
        log=SourceLog(self.root/"source");log.append({"value":1});log.append({"value":2});log.close()
        self.assertEqual([r["payload"]["value"] for r in SourceLogReader(log.path).iter_records()],[1,2])
        self.assertTrue(SourceLogReader(log.path).verify()["complete"]);self.assertFalse(hasattr(log,"events"))
    def test_02_source_tamper_and_missing_index_refused(self):
        log=SourceLog(self.root/"source");log.append({"value":1});log.close();path=log.path/"records.jsonl"
        raw=path.read_bytes();path.write_bytes(raw.replace(b'"value":1',b'"value":2'))
        self.assertFalse(SourceLogReader(log.path).verify()["complete"])
        path.write_bytes(raw);(log.path/"index.json").unlink();self.assertFalse(SourceLogReader(log.path).verify()["complete"])
    def test_03_source_budget_failure_cannot_close_complete(self):
        log=SourceLog(self.root/"source",record_bytes=1024,total_bytes=1024,max_records=1);log.append({"value":1})
        with self.assertRaises(Exception):log.append({"value":2})
        log.close();self.assertTrue((log.path/"writer.lock").exists());self.assertFalse(SourceLogReader(log.path).verify()["complete"])
    def test_04_postclose_source_activity_invalidates(self):
        log=SourceLog(self.root/"source");log.append({"value":1});log.close()
        with self.assertRaises(SourceLogError):log.append({"value":2})
        self.assertFalse(SourceLogReader(log.path).verify()["complete"])
    def test_05_source_marker_during_actual_iteration_blocks_eof(self):
        log=SourceLog(self.root/"source");log.append({"value":1});log.append({"value":2});log.close()
        reader=SourceLogReader(log.path).iter_records();self.assertEqual(next(reader)["seq"],1)
        with self.assertRaises(SourceLogError):log.append({"value":3})
        with self.assertRaises(SourceLogError):list(reader)
    def test_06_concurrent_source_writers_keep_unique_chain(self):
        log=SourceLog(self.root/"source")
        workers=[threading.Thread(target=lambda number=n:[log.append({"worker":number,"n":i}) for i in range(20)]) for n in range(4)]
        for worker in workers:worker.start()
        for worker in workers:worker.join()
        log.close();self.assertEqual(SourceLogReader(log.path).verify()["records"],80)
    def test_07_reads_emit_on_delivery_and_do_not_repeat_at_eof(self):
        s,c,raw=self.capture([read()]);cursor=c.execute(s.profile.read_sql,("k",));self.assertIn(cursor._identity,s._pending_results)
        self.assertEqual(cursor.fetchone(),(1,));self.assertIsNone(cursor.fetchone());self.assertIsNone(cursor.fetchone())
        events=self.events(s);self.assertEqual(len([e for e in events if e["kind"]=="read"]),1)
        self.assertEqual(raw.last_query,s.profile.observed_read_sql)
    def test_08_fetchmany0_does_not_fabricate_eof(self):
        s,c,_=self.capture([read()]);cursor=c.execute(s.profile.read_sql,("k",))
        self.assertEqual(cursor.fetchmany(0),[]);self.assertTrue(cursor._pending);self.assertIn(cursor._identity,s._pending_results)
        self.assertEqual(cursor.fetchone(),(1,));self.assertFalse(cursor._pending)
    def test_09_discarded_cursor_pending_identity_is_retained(self):
        s,c,_=self.capture([read()]);cursor=c.execute(s.profile.read_sql,("k",));identity=cursor._identity
        del cursor;gc.collect();self.assertIn(identity,s._pending_results)
        self.assertIn("undelivered-result-identities",s.quiescence_report()["reasons"])
    def test_10_command_surface_and_no_result_errors_preserved(self):
        import psycopg
        s,c,_=self.capture([command()]);cursor=c.execute(s.profile.write_sql,(1,"k"))
        self.assertIsNone(cursor.description);self.assertIsNone(cursor.rownumber);self.assertEqual(cursor.rowcount,1);self.assertEqual(cursor.statusmessage,"UPDATE 1")
        with self.assertRaises(psycopg.ProgrammingError) as error:cursor.fetchone()
        self.assertEqual(str(error.exception),"the last operation didn't produce records (command status: UPDATE 1)")
        cursor.close()
        with self.assertRaises(psycopg.InterfaceError):cursor.fetchone()
        events=self.events(s);self.assertEqual(len([e for e in events if e["kind"]=="write"]),1)
        self.assertFalse(any(e["kind"]=="read" for e in events))
        rows=[e for e in events if e["kind"]=="rows"];self.assertTrue(all(e["rows"]==[] for e in rows))
    def test_11_original_returning_value_hides_only_metadata(self):
        response={"rows":[(7,version(1),version(2))],"columns":[("value",23),("old",25),("new",25)],"status":"UPDATE 1"}
        s,c,_=self.capture([response]);cursor=c.execute(s.returning_sql,(7,"k"))
        self.assertEqual(len(cursor.description),1);self.assertEqual(cursor.fetchall(),[(7,)])
        self.assertEqual(len([e for e in self.events(s) if e["kind"]=="write"]),1)
    def test_12_same_value_intermediate_writes_are_retained(self):
        s,c,_=self.capture([command(1,2),command(2,3)])
        c.execute(s.profile.write_sql,(1,"k"));c.execute(s.profile.write_sql,(1,"k"))
        writes=[e for e in self.events(s) if e["kind"]=="write"]
        self.assertEqual([(e["predecessor"],e["version"]) for e in writes],[(version(1),version(2)),(version(2),version(3))])
    def test_13_original_execute_error_identity(self):
        original=BusinessError("original execute");s,c,_=self.capture([{"error":original}])
        with self.assertRaises(BusinessError) as caught:c.execute(s.profile.write_sql,(1,"k"))
        self.assertIs(caught.exception,original)
    def test_14_original_fetch_error_identity(self):
        original=BusinessError("original fetch");s,c,_=self.capture([read(fetch_error=original)])
        cursor=c.execute(s.profile.read_sql,("k",))
        with self.assertRaises(BusinessError) as caught:cursor.fetchone()
        self.assertIs(caught.exception,original)
    def test_15_source_observer_failure_does_not_change_business_result(self):
        s,c,_=self.capture([command()])
        with patch.object(s.sources,"append",side_effect=OSError("source IO")):cursor=c.execute(s.profile.write_sql,(1,"k"))
        self.assertIsNone(cursor.description);self.assertEqual(cursor.rowcount,1)
        self.assertIn("write_source_unavailable",[g["code"] for g in s.gaps])
        self.assertFalse(any(e["kind"]=="write" for e in self.events(s)))
    def test_16_invalid_parameters_execute_original_query(self):
        s,c,raw=self.capture([{"rows":[],"rowcount":0,"status":"UPDATE 0"}]);params=(1,"outside")
        c.execute(s.profile.write_sql,params);self.assertEqual(raw.last_query,s.profile.write_sql);self.assertIs(raw.last_params,params)
        self.assertIn("point_profile_unsupported",[g["code"] for g in s.gaps])
    def test_17_custom_factory_executes_original_projection(self):
        s,c,raw=self.capture([{"rows":[{"value":3}],"columns":[("value",23)]}]);cursor=c.cursor();cursor._raw.row_factory=lambda row:row
        cursor.execute(s.profile.read_sql,("k",));self.assertEqual(raw.last_query,s.profile.read_sql);self.assertEqual(cursor.fetchone(),{"value":3})
        self.assertIn("point_profile_unsupported",[g["code"] for g in s.gaps])
    def test_18_unknown_sql_original_and_gap(self):
        s,c,raw=self.capture([{"rows":[(1,)],"columns":[("x",23)]}]);cursor=c.execute("SELECT 1")
        self.assertEqual(cursor.fetchone(),(1,));self.assertEqual(raw.last_query,"SELECT 1")
        self.assertIn("unknown_sql",[g["code"] for g in s.gaps])
    def test_19_zero_update_rows_do_not_invent_token(self):
        s,c,_=self.capture([{"rows":[],"columns":[("old",25),("new",25)],"rowcount":0,"status":"UPDATE 0"}])
        cursor=c.execute(s.profile.write_sql,(1,"k"));self.assertEqual(cursor.rowcount,0)
        self.assertIn("write_source_unavailable",[g["code"] for g in s.gaps]);self.assertFalse(any(e["kind"]=="write" for e in self.events(s)))
    def test_20_no_event_or_fact_history_lists(self):
        s,c,_=self.capture([command(1,2),command(2,3)])
        for _ in range(2):c.execute(s.profile.write_sql,(1,"k"))
        self.assertFalse(hasattr(s,"_events"));self.assertFalse(hasattr(s,"_presence_writes"));self.assertEqual(s._pending_results,set())
        self.assertFalse(s.core_proof_implemented);self.assertFalse(s.formal_eligible)
    def test_21_quiescence_reports_actual_state_not_handoff_completion(self):
        s,c,_=self.capture();self.assertIn("business-connections-not-closed",s.quiescence_report()["reasons"])
        c.close();report=s.quiescence_report();self.assertTrue(report["eligible"]);self.assertFalse(report["handoffImplemented"])
    def test_22_unknown_outcome_not_healed_by_idle_rollback(self):
        s,c,_=self.capture([read()]);cursor=c.execute(s.profile.read_sql,("k",));cursor.fetchone();c._unknown("injected_mock_disconnect");c.rollback();c.close()
        self.assertFalse(s.quiescence_report()["eligible"]);self.assertIn("prior-coverage-gap",s.quiescence_report()["reasons"])
    def test_23_close_without_final_ledger_is_not_complete(self):
        s,c,_=self.capture();c.close();status=s.close(source_closed=True)
        self.assertFalse(status.complete);self.assertIn("ledger_not_finalized",[g["code"] for g in s.gaps])
    def test_24_parameter_encoding_budget_does_not_change_original_call(self):
        s,c,raw=self.capture([{"rows":[],"rowcount":0,"status":"UPDATE 0"}]);params=(["x"]*20000,"k")
        c.execute(s.profile.write_sql,params);self.assertIs(raw.last_params,params)
        self.assertIn("parameter_encoding_failed",[g["code"] for g in s.gaps])
    def test_25_existing_cursor_postclose_preserves_business_row_and_invalidates(self):
        s,c,_=self.capture([read()]);cursor=c.execute(s.profile.read_sql,("k",));s.close(source_closed=False)
        self.assertEqual(cursor.fetchone(),(1,));self.assertTrue(s._invalidated)
        self.assertFalse(JournalReader(s.journal.path).verify().complete)

    def test_26_discarded_pending_identities_have_actual_hard_cap(self):
        s,c,_=self.capture([read() for _ in range(draft.PENDING_RESULT_LIMIT+2)])
        for _ in range(draft.PENDING_RESULT_LIMIT+2):
            cursor=c.execute(s.profile.read_sql,("k",));del cursor
        self.assertEqual(len(s._pending_results),draft.PENDING_RESULT_LIMIT)
        self.assertIn("pending_result_budget",[g["code"] for g in s.gaps])
        self.assertFalse(s.quiescence_report()["eligible"])

    def test_27_hidden_command_fetch_after_close_invalidates(self):
        import psycopg
        s,c,_=self.capture([command()]);cursor=c.execute(s.profile.write_sql,(1,"k"));c.commit();c.close()
        s._ledger_complete=True  # Mock storage case, never actual SQL proof.
        self.assertTrue(s.close(source_closed=True).complete)
        with self.assertRaises(psycopg.ProgrammingError):cursor.fetchone()
        self.assertTrue(s._invalidated);self.assertFalse(JournalReader(s.journal.path).verify().complete)

    def test_28_name_spoofed_factory_runs_original_sql(self):
        s,c,raw=self.capture([{"rows":[(3,)],"columns":[("value",23)]}]);cursor=c.cursor()
        def impostor(*args):pass
        impostor.__module__="psycopg.rows";impostor.__name__="tuple_row";cursor._raw.row_factory=impostor
        cursor.execute(s.profile.read_sql,("k",));self.assertEqual(raw.last_query,s.profile.read_sql)
        self.assertEqual(cursor.fetchone(),(3,));self.assertIn("point_profile_unsupported",[g["code"] for g in s.gaps])

    def test_29_failed_source_footer_adds_capture_gap(self):
        s,c,_=self.capture();c.close();s._ledger_complete=True
        s.sources.failed=True;status=s.close(source_closed=True)
        self.assertFalse(status.complete);self.assertIn("source_log_failed",[g["code"] for g in s.gaps])

    def test_30_index_growth_after_fstat_read_is_bounded(self):
        log=SourceLog(self.root/"source");log.append({"value":1});log.close()
        index=log.path/"index.json";original_open=Path.open;requests=[]
        class GrowingReader:
            def __init__(self,file):self.file=file
            def __enter__(self):return self
            def __exit__(self,*args):return self.file.__exit__(*args)
            def fileno(self):return self.file.fileno()
            def read(self,size=-1):
                requests.append(size)
                with original_open(index,"ab") as growing:growing.write(b" "*5000);growing.flush();os.fsync(growing.fileno())
                return self.file.read(size)
        def instrument(path,*args,**kwargs):
            file=original_open(path,*args,**kwargs)
            mode=args[0] if args else kwargs.get("mode","r")
            return GrowingReader(file) if path==index and mode=="rb" else file
        with patch.object(Path,"open",instrument):result=SourceLogReader(log.path).verify()
        self.assertFalse(result["complete"]);self.assertEqual(requests,[4097])


def main():
    root=Path(os.environ["MTW_JOURNAL_SCRATCH"])/("plain-v3-unit-"+uuid.uuid4().hex);root.mkdir()
    os.environ["MTW_PLAIN_TEST_RUN"]=str(root);here=Path(__file__).resolve().parent
    def bindings():
        paths=[p for p in here.iterdir() if p.is_file() and p.suffix in (".py",".json") and p.name!="candidate-index.json"]
        paths.extend(draft.ROOT/p for p in ("integrations/python/moontxnwitness_capture/__init__.py",
            "integrations/python/moontxnwitness_capture/capture.py","integrations/python/moontxnwitness_capture/capture_v3.py",
            "integrations/python/moontxnwitness_capture/journal_v3.py","experiments/provenance/prototype.py","experiments/provenance/capture_profile.py"))
        return {p.relative_to(draft.ROOT).as_posix():{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths}
    before=bindings();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DraftTests));after=bindings()
    receipt={"schema":1,"passed":result.wasSuccessful() and before==after,"tests":result.testsRun,
        "actualMockExecution":True,"actualFilesystemExecution":True,"actualDatabaseExecution":False,
        "formalPerformanceMeasurement":False,"coreProofImplemented":False,"formalEligible":False,"independentAcceptance":False,
        "sourceBindingsBefore":before,"sourceBindingsAfter":after,"sourceBindingsUnchanged":before==after,
        "failures":[{"test":str(test),"trace":trace} for test,trace in result.failures+result.errors],
        "skipped":[{"test":str(test),"reason":reason} for test,reason in result.skipped]}
    (root/"test-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print("Plain draft receipt: "+str(root/"test-receipt.json"));return 0 if receipt["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
