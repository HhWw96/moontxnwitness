"""New revision fault cases only. Written while host tests are paused."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid
import zipfile
import managed
from managed import ManagedSource, Incomplete, Budget
from protocol import canonical, digest
from test_managed import ManagedTests


class GapTests(ManagedTests):
    def write_manifest(self,state):
        state={key:value for key,value in state.items() if key!="manifestSha256"}
        state["manifestSha256"]=digest(canonical(state));(self.store/"manifest.json").write_bytes(canonical(state))

    def rebind_archive(self,s,path,*,cache=None):
        state,index=s._state();state["archive"]={"path":str(path),"bytes":path.stat().st_size,"sha256":digest(path.read_bytes())}
        for checkpoint in state["checkpoints"].values():checkpoint["archiveSha256"]=state["archive"]["sha256"]
        if cache is not None:state["transactionBinding"]={"bytes":len(cache),"sha256":digest(cache)}
        self.write_manifest(state)

    def bad_zip(self,s,name,change):
        path=self.root/name
        with zipfile.ZipFile(self.zip) as old,zipfile.ZipFile(path,"w") as new:
            for number,member in enumerate(old.infolist()):
                info,raw=change(number,member,old.read(member));new.writestr(info,raw)
        self.rebind_archive(s,path);return path

    def no_original_deletion(self,before):self.assertEqual(before,{p.name for p in self.source.glob("segment-*.jsonl")})

    def test_r2_01_active_transaction_source_refused(self):
        def active(events):events.append({"seq":19,"time":18,"kind":"begin","tx":"active","connection":"active"})
        with self.assertRaises(Exception):self.make(mutate=active)
        self.assertFalse(self.store.exists());self.assertFalse(managed.JournalReader(self.source).verify().complete)

    def test_r2_02_actual_unread_reference_source_refused(self):
        with self.assertRaises(Exception):self.make(references={"unread_results":["result-not-delivered"]})
        self.assertFalse(self.store.exists());self.assertFalse(managed.JournalReader(self.source).verify().complete)

    def test_r2_03_actual_active_reference_source_refused(self):
        with self.assertRaises(Exception):self.make(references={"active_transactions":["external-source-holder"]})
        self.assertFalse(self.store.exists())

    def test_r2_04_unknown_commit_source_refused(self):
        def unknown(events):
            events.extend([{"seq":19,"time":18,"kind":"begin","tx":"unknown","connection":"unknown"},
                {"seq":20,"time":19,"kind":"commit_request","tx":"unknown"},
                {"seq":21,"time":20,"kind":"disconnect","tx":"unknown"}])
        with self.assertRaises(Exception):self.make(mutate=unknown)
        self.assertFalse(self.store.exists());self.assertFalse(managed.JournalReader(self.source).verify().complete)

    def test_r2_05_actual_version_sources_keep_full_writer_chain_hot(self):
        s=self.make(references={"version_sources":["x1"]});state,index=s._state()
        self.zip=self.root/"source.zip";s.archive_checkpoint("checkpoint",self.zip)
        result=s.prune(before_seq=999);self.assertTrue(result["originalSegmentsDeleted"])
        for segment in index["segments"]:
            if set(range(segment["firstSeq"],segment["lastSeq"]+1)).intersection({1,2,3,4,5}):
                self.assertTrue((self.source/segment["name"]).is_file())
        self.assertEqual(list(s.iter_events()),self.events)

    def test_r2_06_read_window_lease_prevents_original_segment_deletion(self):
        s=self.archived(True);reader=s.read_window("reader");self.assertEqual(next(reader)["seq"],1)
        before={p.name for p in self.source.glob("segment-*.jsonl")}
        try:
            with self.assertRaises(Exception):ManagedSource(self.store).prune(before_seq=999)
            self.no_original_deletion(before)
        finally:reader.close()

    def test_r2_07_foreign_regular_fence_refused_before_delete(self):
        s=self.archived();path=self.source/"writer.lock";original=path.read_bytes();(self.root/"original-fence.json").write_bytes(original)
        value=json.loads(original);value["nonce"]="0"*32;path.write_bytes(canonical(value))
        before={p.name for p in self.source.glob("segment-*.jsonl")}
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.no_original_deletion(before);self.assertFalse(s.verify()["complete"])

    def test_r2_08_actual_archive_truncation_refused(self):
        s=self.archived();before={p.name for p in self.source.glob("segment-*.jsonl")}
        with self.zip.open("r+b") as file:file.truncate(self.zip.stat().st_size-7)
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.no_original_deletion(before);self.assertFalse(s.verify()["complete"])

    def test_r2_09_zip_traversal_member_refused_without_extraction(self):
        s=self.archived()
        def change(number,info,raw):
            if number==0:info.filename="../escaped-evidence"
            return info,raw
        self.bad_zip(s,"traversal.zip",change)
        status=s.verify();self.assertFalse(status["complete"]);self.assertIn("Unsafe archive member",status["gap"])
        self.assertFalse((self.root/"escaped-evidence").exists())

    def test_r2_10_zip_symlink_member_refused_without_fs_symlink_privilege(self):
        s=self.archived()
        def change(number,info,raw):
            if number==0:info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
            return info,raw
        self.bad_zip(s,"member-symlink.zip",change)
        status=s.verify();self.assertFalse(status["complete"]);self.assertIn("Unsafe archive member",status["gap"])

    def test_r2_11_zip_encryption_flags_refused_before_password_or_decompression(self):
        s=self.archived();raw=bytearray(self.zip.read_bytes())
        local=raw.find(b"PK\x03\x04");central=raw.find(b"PK\x01\x02");self.assertGreaterEqual(min(local,central),0)
        for offset in (local+6,central+8):struct.pack_into("<H",raw,offset,struct.unpack_from("<H",raw,offset)[0]|1)
        path=self.root/"encrypted-flag.zip";path.write_bytes(raw);self.rebind_archive(s,path)
        status=s.verify();self.assertFalse(status["complete"]);self.assertIn("Unsafe archive member",status["gap"])

    def test_r2_12_zip_wrong_expanded_member_size_refused(self):
        s=self.archived();raw=bytearray(self.zip.read_bytes());central=raw.find(b"PK\x01\x02")
        struct.pack_into("<L",raw,central+24,struct.unpack_from("<L",raw,central+24)[0]+1)
        path=self.root/"wrong-expanded-size.zip";path.write_bytes(raw);self.rebind_archive(s,path)
        status=s.verify();self.assertFalse(status["complete"]);self.assertIn("Unsafe archive member",status["gap"])

    def test_r2_13_manifest_location_contradiction_with_fresh_checksum_refused(self):
        s=self.archived();state,index=s._state();state["locations"][0]["name"]="segment-999999.jsonl";self.write_manifest(state)
        self.assertFalse(s.verify()["complete"])

    def test_r2_14_checkpoint_archive_contradiction_with_fresh_checksum_refused(self):
        s=self.archived();state,index=s._state();state["checkpoints"]["checkpoint"]["archiveSha256"]="0"*64;self.write_manifest(state)
        self.assertFalse(s.verify()["complete"])

    def test_r2_15_unknown_retained_root_not_ignored(self):
        s=self.archived();state,index=s._state();state["pins"]["missing"]={"transactions":["not-recorded"],"versions":[],"sequences":[]};self.write_manifest(state)
        before={p.name for p in self.source.glob("segment-*.jsonl")}
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.no_original_deletion(before)

    def test_r2_16_manifest_roots_changed_after_publication_prevent_deletion(self):
        s=self.archived();before={p.name for p in self.source.glob("segment-*.jsonl")}
        def change(stage):
            if stage=="after-manifest":
                path=self.store/"manifest.json";raw=path.read_bytes();(self.root/"before-root-change.json").write_bytes(raw)
                state=json.loads(raw);state["pins"]["new-holder"]={"transactions":["B"],"versions":[],"sequences":[]};state["generation"]+=1;self.write_manifest(state)
        s.fault=change
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.no_original_deletion(before);self.assertTrue((self.store/"operation.lock").exists())

    def test_r2_17_rebound_sqlite_schema_still_checked_against_raw(self):
        s=self.archived();db=sqlite3.connect(self.source/"transactions.sqlite3")
        db.execute("CREATE TABLE substituted(x TEXT)");db.commit();db.close();cache=(self.source/"transactions.sqlite3").read_bytes()
        def change(number,info,raw):return info,cache if info.filename=="transactions.sqlite3" else raw
        path=self.bad_zip(s,"cache-schema.zip",change);self.rebind_archive(s,path,cache=cache)
        status=s.verify();self.assertFalse(status["complete"]);self.assertIn("Reconstructed raw journal failed",status["gap"])

    def test_r2_18_rebound_sqlite_identity_still_checked_against_raw(self):
        s=self.archived();db=sqlite3.connect(self.source/"transactions.sqlite3")
        db.execute("UPDATE transactions SET begin_seq=999 WHERE tx='A'");db.commit();db.close();cache=(self.source/"transactions.sqlite3").read_bytes()
        def change(number,info,raw):return info,cache if info.filename=="transactions.sqlite3" else raw
        path=self.bad_zip(s,"cache-identity.zip",change);self.rebind_archive(s,path,cache=cache)
        status=s.verify();self.assertFalse(status["complete"]);self.assertIn("Reconstructed raw journal failed",status["gap"])

    def test_r2_19_publication_sync_and_failure_marker_io_both_fail_closed(self):
        s=self.archived();before={p.name for p in self.source.glob("segment-*.jsonl")};sync=managed.point.sync_directory;opened=Path.open
        count={"sync":0,"marker":0}
        def broken_sync(path):
            if Path(path)==self.store and (self.store/"prune-intent.json").exists():
                count["sync"]+=1
                if count["sync"]==2:raise OSError("Injected post-replace directory sync failure")
            return sync(path)
        def broken_open(path,*args,**kwargs):
            mode=args[0] if args else kwargs.get("mode","r")
            if path.name=="operation-failed.json" and "x" in mode:count["marker"]+=1;raise PermissionError("Injected failure marker IO denial")
            return opened(path,*args,**kwargs)
        with patch.object(managed.point,"sync_directory",side_effect=broken_sync),patch.object(Path,"open",new=broken_open):
            with self.assertRaises(OSError):s.prune(before_seq=999)
        self.assertEqual(count,{"sync":2,"marker":1});self.assertTrue((self.store/"operation.lock").exists());self.assertFalse((self.store/"operation-failed.json").exists())
        self.no_original_deletion(before);self.assertFalse(s.verify()["complete"]);self.assertFalse(ManagedSource(self.store).verify()["complete"])
        plan=json.loads((self.store/"prune-intent.json").read_text())["plan"]
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"]);self.assertFalse(s.verify()["complete"])

    def test_r2_20_actual_process_crash_between_manifest_replace_and_sync(self):
        s=self.archived();plan=self.crash(s,"manifest-replaced-before-sync")
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertEqual(list(ManagedSource(self.store).iter_events()),self.events)

    def test_r2_21_actual_process_crash_after_intent_clear_can_recover(self):
        s=self.archived();plan=self.crash(s,"after-intent-clear")
        self.assertFalse((self.store/"prune-intent.json").exists())
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertEqual(list(ManagedSource(self.store).iter_events()),self.events)

    def test_r2_22_foreign_failed_operation_marker_refused_before_recovery_delete(self):
        s=self.archived()
        def stop(stage):
            if stage=="after-intent":raise OSError("Injected prepared-plan failure")
        s.fault=stop
        with self.assertRaises(OSError):s.prune(before_seq=999)
        marker=self.store/"operation-failed.json";raw=marker.read_bytes();(self.root/"original-failure-marker.json").write_bytes(raw)
        value=json.loads(raw);value["nonce"]="0"*32;marker.write_bytes(canonical(value));before={p.name for p in self.source.glob("segment-*.jsonl")}
        plan=json.loads((self.store/"prune-intent.json").read_text())["plan"]
        with self.assertRaises(Exception):ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.no_original_deletion(before);self.assertTrue((self.store/"operation.lock").exists())

    def test_r2_23_archive_changes_after_intent_refused_then_original_restore_recover(self):
        s=self.archived();original=self.zip.read_bytes();(self.root/"verified-original.zip").write_bytes(original)
        def change(stage):
            if stage=="after-intent":
                with self.zip.open("ab") as file:file.write(b"changed-after-intent")
        s.fault=change;before={p.name for p in self.source.glob("segment-*.jsonl")}
        with self.assertRaises(Exception):s.prune(before_seq=999)
        self.no_original_deletion(before);self.assertFalse(ManagedSource(self.store).verify()["complete"])
        self.zip.rename(self.root/"failed-changed-archive.zip")
        with self.zip.open("xb") as file:file.write(original)
        plan=json.loads((self.store/"prune-intent.json").read_text())["plan"]
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"])

    def test_r2_24_published_manifest_actual_bytes_changed_no_complete_receipt(self):
        s=self.archived();replace=managed.os.replace;before={p.name for p in self.source.glob("segment-*.jsonl")}
        def changed(source,target):
            result=replace(source,target)
            if Path(target)==self.store/"manifest.json" and (self.store/"prune-intent.json").exists():
                with Path(target).open("ab") as file:file.write(b" ")
            return result
        with patch.object(managed.os,"replace",side_effect=changed):
            with self.assertRaises(Exception):s.prune(before_seq=999)
        self.no_original_deletion(before);self.assertFalse(ManagedSource(self.store).verify()["complete"])
        (self.root/"failed-published-manifest.json").write_bytes((self.store/"manifest.json").read_bytes())

    def test_r2_25_archive_actual_bytes_change_during_delivery_prevents_eof(self):
        s=self.archived();s.prune(before_seq=999);reader=s.iter_events();self.assertEqual(next(reader)["seq"],1)
        with self.zip.open("ab") as file:file.write(b"changed-during-delivery")
        with self.assertRaises(Exception):list(reader)

    def test_r2_26_manifest_generation_change_during_delivery_prevents_eof(self):
        s=self.archived();reader=s.iter_events();self.assertEqual(next(reader)["seq"],1)
        state=json.loads((self.store/"manifest.json").read_text());state["generation"]+=1;self.write_manifest(state)
        with self.assertRaises(Exception):list(reader)

    def test_r2_27_actual_expanded_zip_sum_over_scaled_cap_refused(self):
        s=self.archived()
        with zipfile.ZipFile(self.zip) as archive:expanded=sum(member.file_size for member in archive.infolist())
        with patch.dict(managed.LIMITS,{"archiveUncompressedBytes":expanded-1}):
            status=s.verify();self.assertFalse(status["complete"]);self.assertIn("Archive expanded bound",status["gap"])

    def test_r2_28_actual_temp_growth_over_reserved_cap_prevents_publication(self):
        s=self.make();state,index=s._state()
        original=managed.LIMITS["temporaryBytes"]
        try:
            with self.assertRaises(Exception) as caught:
                with s._operation() as budget:
                    with s._view(state,index,budget) as view:
                        occupied=sum(p.stat().st_size for p in view.rglob("*") if p.is_file())
                        managed.LIMITS["temporaryBytes"]=occupied+1024
                        with (view/"unexpected-growth").open("xb") as file:file.write(b"x"*2048)
                        (self.root/"temp-cap-observation.json").write_text(json.dumps({"actualBytesBefore":occupied,"configuredScaledCap":occupied+1024,"addedBytes":2048})+"\n")
                        # Normal exit invokes the actual occupancy check. The
                        # test itself never throws a synthetic budget error.
            self.assertIn("Actual temporary bound",str(caught.exception))
        finally:managed.LIMITS["temporaryBytes"]=original

    def test_r2_29_same_instance_competing_reader_cannot_clear_dirty_owner(self):
        s=self.archived();observed=[]
        def nested(stage):
            if stage=="after-manifest":
                self.assertTrue(s.dirty);self.assertFalse(s.verify()["complete"]);self.assertTrue(s.dirty);self.assertFalse(s.poisoned);observed.append(True)
        s.fault=nested;self.assertTrue(s.prune(before_seq=999)["originalSegmentsDeleted"]);self.assertEqual(observed,[True])

    def test_r2_30_sqlite_work_counter_rejects_without_server(self):
        budget=Budget();budget.steps=4_999_500;db=sqlite3.connect(":memory:");db.set_progress_handler(budget.progress,1000)
        try:
            with self.assertRaises(sqlite3.OperationalError):db.execute("WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<10000) SELECT sum(x) FROM n").fetchone()
        finally:db.close()

    def test_r2_31_source_bounds_reject_before_reader_decode(self):
        # These are configured-limit fault injections on real small files;
        # they are not claims of a 32MiB or 16k-event stress measurement.
        original_adopt=ManagedSource.adopt
        with patch.object(ManagedSource,"adopt",side_effect=RuntimeError("Keep prepared original source")):
            with self.assertRaises(RuntimeError):self.make()
        for limits in ({"sourceEvents":4},{"segmentCount":1},{"transactionCacheBytes":1}):
            with self.subTest(limits=limits),patch.dict(managed.LIMITS,limits),self.assertRaises(Exception):
                original_adopt(self.store,self.source,exclusive_source_ownership=True)
        self.assertFalse(self.store.exists())

    def test_r2_32_physical_event_count_preflight_before_raw_decode(self):
        original_adopt=ManagedSource.adopt
        with patch.object(ManagedSource,"adopt",side_effect=RuntimeError("Keep prepared source")):
            with self.assertRaises(RuntimeError):self.make()
        path=self.source/"journal-index.json";index=json.loads(path.read_text());item=next(item for item in index["segments"] if item["eventCount"]>1)
        item["eventCount"]-=1;index["eventCount"]-=1
        index["indexSha256"]=digest(canonical({k:v for k,v in index.items() if k!="indexSha256"}));path.write_bytes(canonical(index))
        with patch.object(managed.JournalReader,"verify",side_effect=AssertionError("Raw decoder must not be reached")):
            with self.assertRaises(Incomplete) as caught:original_adopt(self.store,self.source,exclusive_source_ownership=True)
        self.assertIn("Segment event count exceeded",str(caught.exception));self.assertFalse(self.store.exists())

    def test_r2_33_cutoff_integer_limit_checked_before_json_or_lock(self):
        s=self.archived();before={p.name for p in self.source.glob("segment-*.jsonl")}
        with self.assertRaises(Exception):s.prune(before_seq=2**10000)
        self.assertFalse((self.store/"operation.lock").exists());self.no_original_deletion(before)

    def persistent_bytes(self):
        """Small fixture bindings, excluding only independent test receipts."""
        paths=[*self.source.rglob("*"),*self.store.rglob("*"),self.zip]
        return {str(path.relative_to(self.root)):digest(path.read_bytes())
            for path in paths if path.is_file()}

    def test_r3_34_wrong_lock_token_refusal_cannot_poison_prepared_recovery(self):
        s=self.archived();plan=self.crash(s,"after-manifest")
        path=self.store/"operation.lock";original=path.read_bytes()
        wrong=json.loads(original);wrong["token"]="0"*32 if wrong["token"]!="0"*32 else "1"*32
        path.write_bytes(canonical(wrong));before=self.persistent_bytes()
        recovery=ManagedSource(self.store)
        with self.assertRaises(Exception) as caught:recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertIn("token differs",str(caught.exception))
        self.assertEqual(self.persistent_bytes(),before)
        self.assertFalse((self.store/"operation-failed.json").exists())
        self.assertFalse(recovery.poisoned);self.assertFalse(recovery.dirty)
        path.write_bytes(original)
        recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"])
        self.assertEqual(list(ManagedSource(self.store).iter_events()),self.events)

    def test_r3_35_wrong_plan_preserves_existing_genuine_failure_marker(self):
        s=self.archived()
        def stop(stage):
            if stage=="after-intent":raise OSError("Injected original prepared-plan failure")
        s.fault=stop
        with self.assertRaises(OSError):s.prune(before_seq=999)
        plan=json.loads((self.store/"prune-intent.json").read_text())["plan"]
        marker=self.store/"operation-failed.json";self.assertTrue(marker.is_file())
        before=self.persistent_bytes();recovery=ManagedSource(self.store)
        wrong="0"*32 if plan!="0"*32 else "1"*32
        with self.assertRaises(Exception) as caught:recovery.recover(expected_plan=wrong,exclusive_recovery=True)
        self.assertIn("Unexpected recovery plan",str(caught.exception))
        self.assertEqual(self.persistent_bytes(),before);self.assertFalse(recovery.poisoned)
        recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertFalse(marker.exists());self.assertTrue(ManagedSource(self.store).verify()["complete"])

    def test_r3_36_malformed_intent_refusal_is_read_only_and_correctable(self):
        s=self.archived();plan=self.crash(s,"after-manifest")
        path=self.store/"prune-intent.json";original=path.read_bytes()
        wrong=json.loads(original);wrong["targets"]=[];path.write_bytes(canonical(wrong))
        before=self.persistent_bytes();recovery=ManagedSource(self.store)
        with self.assertRaises(Exception) as caught:recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertIn("targets bound",str(caught.exception))
        self.assertEqual(self.persistent_bytes(),before)
        self.assertFalse((self.store/"operation-failed.json").exists());self.assertFalse(recovery.poisoned)
        path.write_bytes(original);recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"])

    def test_r3_37_root_digest_refusal_is_read_only_and_correctable(self):
        s=self.archived();plan=self.crash(s,"after-manifest")
        path=self.store/"prune-intent.json";original=path.read_bytes()
        wrong=json.loads(original);wrong["rootsSha256"]="0"*64;path.write_bytes(canonical(wrong))
        before=self.persistent_bytes();recovery=ManagedSource(self.store)
        with self.assertRaises(Exception) as caught:recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertIn("Retained roots changed",str(caught.exception))
        self.assertEqual(self.persistent_bytes(),before)
        self.assertFalse((self.store/"operation-failed.json").exists());self.assertFalse(recovery.poisoned)
        path.write_bytes(original);recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(ManagedSource(self.store).verify()["complete"])

    def test_r3_38_real_recovery_mutation_failure_still_persists_owner_guard(self):
        s=self.archived();plan=self.crash(s,"after-intent")
        original=json.loads((self.store/"operation.lock").read_bytes())
        recovery=ManagedSource(self.store)
        def stop(stage):
            if stage=="after-manifest":raise OSError("Injected failure after actual recovery publication")
        recovery.fault=stop
        with self.assertRaises(OSError):recovery.recover(expected_plan=plan,exclusive_recovery=True)
        self.assertTrue(recovery.poisoned);self.assertTrue((self.store/"operation.lock").exists())
        marker=self.store/"operation-failed.json"
        self.assertEqual(json.loads(marker.read_bytes()),{"kind":"archive-operation-failed/1","nonce":original["nonce"],"operationToken":original["token"]})
        self.assertFalse(ManagedSource(self.store).verify()["complete"])
        ManagedSource(self.store).recover(expected_plan=plan,exclusive_recovery=True)
        self.assertFalse(marker.exists());self.assertTrue(ManagedSource(self.store).verify()["complete"])
        self.assertEqual(list(ManagedSource(self.store).iter_events()),self.events)


def main():
    root=Path(os.environ["MTW_JOURNAL_SCRATCH"])/("archive-r3-gap-run-"+uuid.uuid4().hex);root.mkdir()
    os.environ["MTW_MANAGED_TEST_RUN"]=str(root);here=Path(__file__).resolve().parent
    files=[*here.glob("*.py"),here/"contract-v1.json",here/"test-plan.json",here/"contract-r2-amendment.json",here/"contract-r3-amendment.json",managed.OLD,
        managed.ROOT/"integrations/python/moontxnwitness_capture/journal_v3.py"]
    def bindings():return {str(p.relative_to(managed.ROOT)).replace("\\","/"):{"bytes":p.stat().st_size,"sha256":digest(p.read_bytes())} for p in files}
    before=bindings();names=[name for name in unittest.defaultTestLoader.getTestCaseNames(GapTests) if name.startswith(("test_r2_","test_r3_"))]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(GapTests(name) for name in names));after=bindings()
    payload={"schema":1,"passed":result.wasSuccessful() and before==after,"tests":result.testsRun,"testNames":names,
        "actualFilesystemExecution":True,"actualDatabaseExecution":False,"formalPerformanceMeasurement":False,
        "original32TestsRerun":False,"retainedR2Cases":33,"newR3Cases":5,"independentAcceptance":False,"sourceBindingsBefore":before,"sourceBindingsAfter":after,
        "sourceBindingsUnchanged":before==after,"failures":[{"test":str(test),"trace":trace} for test,trace in result.failures+result.errors],
        "skipped":[{"test":str(test),"reason":reason} for test,reason in result.skipped],"planFullyCovered":False,
        "limits":"Scaled-limit branches, not large-limit stress or OS quotas; separate r3 baseline regression must actually execute dangling symlink cases."}
    (root/"test-receipt.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print("Archive r3 incremental receipt: "+str(root/"test-receipt.json"));return 0 if payload["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
