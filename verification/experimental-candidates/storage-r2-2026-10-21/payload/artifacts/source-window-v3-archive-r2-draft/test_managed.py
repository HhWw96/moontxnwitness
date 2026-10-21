"""Preregistered actual filesystem checks; no database or performance samples."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid
import zipfile
import managed
from managed import ManagedSource, Incomplete, Budget
from protocol import canonical, digest
from moontxnwitness_capture.journal_v3 import SegmentedJournal, JournalReader, INVALIDATED


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(os.environ["MTW_MANAGED_TEST_RUN"])/self._testMethodName;self.root.mkdir()
        self.source=self.root/"journal";self.store=self.root/"store"
        raw=[{"kind":"snapshot","initial":{"x":"x0","y":"y0","z":"z0"},"consistent":True},
            {"kind":"begin","tx":"A","connection":"A"},{"kind":"write","tx":"A","key":"x","version":"x1","predecessor":"x0"},
            {"kind":"commit_request","tx":"A"},{"kind":"commit_ok","tx":"A"},
            {"kind":"begin","tx":"B","connection":"B"},{"kind":"write","tx":"B","key":"y","version":"y1","predecessor":"y0"},
            {"kind":"commit_request","tx":"B"},{"kind":"commit_ok","tx":"B"},
            {"kind":"begin","tx":"C","connection":"C"},{"kind":"read","tx":"C","key":"x","version":"x1"},
            {"kind":"write","tx":"C","key":"x","version":"x2","predecessor":"x1"},
            {"kind":"commit_request","tx":"C"},{"kind":"commit_ok","tx":"C"},
            {"kind":"begin","tx":"D","connection":"D"},{"kind":"read","tx":"D","key":"z","version":"z0"},
            {"kind":"commit_request","tx":"D"},{"kind":"commit_ok","tx":"D"}]
        self.events=[{"seq":i,"time":i-1,**event} for i,event in enumerate(raw,1)]

    def make(self,*,mutate=None,sealed=True,references=None):
        if mutate:mutate(self.events)
        self.journal=SegmentedJournal(self.source,segment_bytes=256,max_record_bytes=256,flush_bytes=128,max_queue_bytes=4096)
        for event in self.events:self.journal.append(event)
        if references:self.journal.set_references(**references)
        self.journal.close(source_closed=sealed)
        return ManagedSource.adopt(self.store,self.source,exclusive_source_ownership=True)

    def archived(self,pin=False):
        s=self.make()
        if pin:s.pin("reader",transactions=["C"])
        self.zip=self.root/"source.zip";s.archive_checkpoint("checkpoint",self.zip)
        return s

    def crash(self,s,stage):
        with (self.root/("crash-"+stage+".log")).open("xb") as log:
            result=subprocess.run([sys.executable,"-B",__file__,"--crash",str(self.store),stage],
                stdout=log,stderr=subprocess.STDOUT,timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        self.assertEqual(result.returncode,73)
        self.assertFalse(ManagedSource(self.store).verify()["complete"])
        path=self.store/"prune-intent.json"
        intent=json.loads(path.read_text()) if path.exists() else json.loads((self.store/"manifest.json").read_text())["completedIntent"]
        return intent["plan"]

    def test_01_actual_original_prune_archive_only_full_read(self):
        s=self.archived();before={p.name:digest(p.read_bytes()) for p in self.source.iterdir() if p.is_file()}
        archive=digest(self.zip.read_bytes());result=s.prune(before_seq=999)
        self.assertTrue(result["originalSegmentsDeleted"])
        self.assertTrue(all(not (self.source/name).exists() for name in result["originalSegmentsDeleted"]))
        self.assertEqual(list(s.iter_events()),self.events);self.assertTrue(s.verify()["complete"])
        self.assertEqual(digest(self.zip.read_bytes()),archive)
        for name in ("journal-index.json","transactions.sqlite3"):self.assertEqual(digest((self.source/name).read_bytes()),before[name])
        self.assertFalse(JournalReader(self.source).verify().complete)

    def test_02_recursive_pinned_closure_stays_hot(self):
        s=self.archived(True);state,index=s._state();result=s.prune(before_seq=999)
        keep={1,*range(2,6),*range(10,15)}
        for item in index["segments"]:
            if keep.intersection(range(item["firstSeq"],item["lastSeq"]+1)):
                self.assertNotIn(item["name"],result["originalSegmentsDeleted"]);self.assertTrue((self.source/item["name"]).is_file())
        self.assertTrue(result["originalSegmentsDeleted"]);self.assertEqual(list(s.iter_events()),self.events)

    def test_03_checkpoint_required(self):
        s=self.make();before=set(self.source.glob("segment-*.jsonl"))
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.assertEqual(before,set(self.source.glob("segment-*.jsonl")));self.assertTrue(s.verify()["complete"])

    def test_04_missing_version_root_refused(self):
        s=self.make()
        with self.assertRaises(Exception):s.pin("bad",versions=["future"])
        self.assertTrue(s.verify()["complete"])

    def test_05_future_source_not_backfilled(self):
        with self.assertRaises(Exception):self.make(mutate=lambda events:events[10].update(version="x2"))
        self.assertTrue((self.source/"writer.lock").exists())

    def test_06_unsealed_source_refused(self):
        with self.assertRaises(Exception):self.make(sealed=False)
        self.assertFalse(self.store.exists())

    def test_07_unsupported_models_refused(self):
        self.make()
        for model in ("relation-set-v1","append-list-v1"):
            with self.subTest(model=model),self.assertRaises(Exception):
                ManagedSource.adopt(self.root/model,self.source,model=model,exclusive_source_ownership=True)

    def test_08_actual_late_producer_invalidates_original(self):
        s=self.archived();s.prune(before_seq=999)
        result=self.journal.append({"seq":19,"time":19,"kind":"begin","tx":"late"})
        self.assertFalse(result.accepted)
        self.assertTrue((self.source/INVALIDATED).exists());self.assertFalse(s.verify()["complete"])

    def test_09_missing_fence_refused(self):
        s=self.make();(self.source/"writer.lock").unlink();self.assertFalse(s.verify()["complete"])

    def test_10_original_failure_marker_not_bypassed_by_archive(self):
        s=self.archived();s.prune(before_seq=999);(self.source/"journal-failure.json").write_text("failure")
        self.assertFalse(s.verify()["complete"])

    def test_11_tampered_archive_refused_before_prune(self):
        s=self.archived()
        with self.zip.open("ab") as file:file.write(b"tamper")
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.assertFalse(s.verify()["complete"])

    def test_12_missing_archive_after_prune_incomplete(self):
        s=self.archived();s.prune(before_seq=999);self.zip.rename(self.root/"preserved-source.zip")
        self.assertFalse(ManagedSource(self.store).verify()["complete"])

    def test_13_zip_extra_member_even_with_rebound_container_refused(self):
        s=self.archived();state,index=s._state()
        bad=self.root/"duplicate.zip"
        with zipfile.ZipFile(self.zip) as old,zipfile.ZipFile(bad,"w") as new:
            for member in old.infolist():new.writestr(member,old.read(member))
            new.writestr("unexpected",b"not original")
        state["archive"]={"path":str(bad),"bytes":bad.stat().st_size,"sha256":digest(bad.read_bytes())}
        for checkpoint in state["checkpoints"].values():checkpoint["archiveSha256"]=state["archive"]["sha256"]
        s._publish(state);s.dirty=False
        self.assertFalse(s.verify()["complete"])

    def test_14_manifest_checksum_tamper_refused(self):
        s=self.make();state,index=s._state();state["generation"]+=1
        (self.store/"manifest.json").write_bytes(canonical(state));self.assertFalse(s.verify()["complete"])

    def test_15_real_sqlite_wal_refused(self):
        s=self.archived();db=sqlite3.connect(self.source/"transactions.sqlite3")
        try:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(),("wal",))
            db.execute("INSERT INTO transactions VALUES('forged',999)");db.commit()
            self.assertTrue((self.source/"transactions.sqlite3-wal").exists());self.assertFalse(s.verify()["complete"])
        finally:db.close()

    def test_16_live_reader_lease_prevents_prune_and_recovery(self):
        s=self.archived();reader=s.iter_events();self.assertEqual(next(reader)["seq"],1)
        try:
            other=ManagedSource(self.store)
            with self.assertRaises(Exception):other.prune(before_seq=999)
            with self.assertRaises(Exception):other.recover(expected_plan="0"*32,exclusive_recovery=True)
            self.assertTrue((self.store/"operation.lock").exists())
        finally:reader.close()
        self.assertTrue(s.verify()["complete"])

    def test_17_process_crash_after_intent_explicit_recover(self):
        s=self.archived();plan=self.crash(s,"after-intent")
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertEqual(list(ManagedSource(self.store).iter_events()),self.events)

    def test_18_process_crash_after_manifest_explicit_recover(self):
        s=self.archived();plan=self.crash(s,"after-manifest")
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"])

    def test_19_process_crash_mid_unlink_explicit_recover(self):
        s=self.archived();state,index=s._state();plan=self.crash(s,"after-unlink")
        self.assertLess(len(list(self.source.glob("segment-*.jsonl"))),len(index["segments"]))
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertEqual(list(ManagedSource(self.store).iter_events()),self.events)

    def test_20_wrong_recovery_keeps_abandoned_lock(self):
        s=self.archived();plan=self.crash(s,"after-manifest")
        with self.assertRaises(Exception):ManagedSource(self.store).recover(expected_plan="wrong",exclusive_recovery=True)
        self.assertTrue((self.store/"operation.lock").is_file())
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)

    def test_21_sync_failure_keeps_intent_lock_then_can_recover(self):
        s=self.archived()
        with patch.object(managed.point,"sync_directory",side_effect=OSError("injected sync failure")):
            with self.assertRaises(OSError):s.prune(before_seq=999)
        self.assertTrue((self.store/"operation.lock").is_file());self.assertFalse(s.verify()["complete"])
        plan=json.loads((self.store/"prune-intent.json").read_text())["plan"]
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"])

    def test_22_io_and_cooperative_cpu_budget_fail_closed(self):
        s=self.make();original=Budget
        with patch.object(managed,"Budget",side_effect=lambda:original(max_io=8)):
            self.assertFalse(s.verify()["complete"])
        b=Budget(seconds=.01)
        with patch.object(managed.time,"monotonic",return_value=b.started+1):
            with self.assertRaises(Incomplete):b.check()
        self.assertTrue(s.verify()["complete"])

    def test_23_archive_deletion_refused(self):
        s=self.archived();before=digest(self.zip.read_bytes())
        with self.assertRaises(Incomplete):s.delete_archive()
        self.assertEqual(digest(self.zip.read_bytes()),before)

    def test_24_marker_appears_during_actual_delivery(self):
        s=self.archived();s.prune(before_seq=999);reader=s.iter_events();self.assertEqual(next(reader)["seq"],1)
        (self.source/INVALIDATED).write_text("late activity")
        with self.assertRaises(Exception):list(reader)
        self.assertFalse(s.verify()["complete"])

    def test_25_archive_disappears_after_first_actual_unlink(self):
        s=self.archived()
        def fault(stage):
            if stage=="after-unlink" and self.zip.exists():self.zip.rename(self.root/"preserved-during-prune.zip")
        s.fault=fault
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.assertTrue((self.store/"operation.lock").exists());self.assertFalse(s.verify()["complete"])

    def test_26_dangling_original_marker_refused(self):
        s=self.archived();target=self.source/INVALIDATED
        try:os.symlink(str(self.root/"missing-target"),target)
        except OSError as error:self.skipTest("Windows symlink privilege unavailable: "+type(error).__name__)
        self.assertTrue(target.is_symlink());self.assertFalse(target.exists());self.assertFalse(s.verify()["complete"])

    def test_27_dangling_source_fence_refused(self):
        s=self.make();target=self.source/"writer.lock";original=target.read_bytes();target.unlink()
        try:os.symlink(str(self.root/"missing-fence-target"),target)
        except OSError as error:
            target.write_bytes(original);self.skipTest("Windows symlink privilege unavailable: "+type(error).__name__)
        self.assertTrue(target.is_symlink());self.assertFalse(s.verify()["complete"])

    def test_28_duplicate_zip_member_even_with_rebound_hash_refused(self):
        s=self.archived();state,index=s._state();bad=self.root/"duplicate-members.zip"
        with zipfile.ZipFile(self.zip) as old,zipfile.ZipFile(bad,"w") as new:
            for member in old.infolist():new.writestr(member,old.read(member))
            first=old.infolist()[0];new.writestr(first,old.read(first))
        state["archive"]={"path":str(bad),"bytes":bad.stat().st_size,"sha256":digest(bad.read_bytes())}
        for checkpoint in state["checkpoints"].values():checkpoint["archiveSha256"]=state["archive"]["sha256"]
        s._publish(state);s.dirty=False
        self.assertFalse(s.verify()["complete"])

    def test_29_actual_window_delivery_and_explicit_release(self):
        s=self.archived(True);s.prune(before_seq=999)
        window=list(s.read_window("reader"));self.assertEqual([e["seq"] for e in window],[1,*range(2,6),*range(10,15)])
        s.release("reader");self.assertTrue(s.prune(before_seq=999)["originalSegmentsDeleted"])
        self.assertEqual(list(s.iter_events()),self.events)

    def test_30_root_generators_and_massive_labels_rejected_before_copy(self):
        s=self.make()
        for params in ({"transactions":(str(i) for i in range(1000000))},{"versions":["x"*1000000]}):
            with self.assertRaises(Exception):s.pin("bad",**params)
        self.assertTrue(s.verify()["complete"])

    def test_31_statement_source_gap_blocks_adoption(self):
        def mutate(events):
            events.insert(3,{"kind":"statement","tx":"A","sql":"SELECT arbitrary()"})
            for i,event in enumerate(events,1):event.update(seq=i,time=i-1)
        with self.assertRaises(Exception):self.make(mutate=mutate)

    def test_32_abandoned_lock_token_must_match_prepared_intent(self):
        s=self.archived();plan=self.crash(s,"after-manifest")
        path=self.store/"operation.lock";original=path.read_bytes();(self.root/"original-abandoned.lock").write_bytes(original)
        token=json.loads(original);token["token"]="0"*32 if token["token"]!="0"*32 else "1"*32
        path.write_bytes(canonical(token))
        with self.assertRaises(Exception):ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(path.is_file());self.assertFalse(ManagedSource(self.store).verify()["complete"])
        path.write_bytes(original);ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"])


def main():
    if len(sys.argv)==4 and sys.argv[1]=="--crash":
        source=ManagedSource(sys.argv[2]);stage=sys.argv[3]
        source.fault=lambda actual:os._exit(73) if actual==stage else None
        source.prune(before_seq=999);raise SystemExit("Expected process fault was not reached")
    root=Path(os.environ["MTW_JOURNAL_SCRATCH"])/("archive-run-"+uuid.uuid4().hex);root.mkdir()
    os.environ["MTW_MANAGED_TEST_RUN"]=str(root)
    here=Path(__file__).resolve().parent
    files=[*here.glob("*.py"),here/"contract-v1.json",here/"test-plan.json",managed.OLD,
        managed.ROOT/"integrations/python/moontxnwitness_capture/journal_v3.py"]
    def bindings():return {str(p.relative_to(managed.ROOT)).replace("\\","/"):{"bytes":p.stat().st_size,"sha256":digest(p.read_bytes())} for p in files}
    before=bindings();suite=unittest.defaultTestLoader.loadTestsFromTestCase(ManagedTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite);after=bindings()
    payload={"schema":1,"passed":result.wasSuccessful() and before==after,"tests":result.testsRun,
        "actualFilesystemExecution":True,"actualDatabaseExecution":False,"formalPerformanceMeasurement":False,
        "independentAcceptance":False,"sourceBindingsBefore":before,"sourceBindingsAfter":after,"sourceBindingsUnchanged":before==after,
        "failures":[{"test":str(test),"trace":trace} for test,trace in result.failures+result.errors],
        "skipped":[{"test":str(test),"reason":reason} for test,reason in result.skipped],
        "preregisteredPlanCases":24,"planFullyCovered":False,
        "remaining":"Separate exact mapping of each preregistered scenario, extra ZIP/symlink/IO failure/retention cases and independent audit remain; passing these tests is not complete plan acceptance."}
    (root/"test-receipt.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print("Archive-backed receipt: "+str(root/"test-receipt.json"))
    return 0 if payload["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
