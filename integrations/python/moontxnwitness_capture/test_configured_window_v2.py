"""Bounded V2 snapshot/window producer checks with explicit fake control buffers."""
import copy
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from . import configured_window_v2 as m
from . import test_configured_source_v2 as f


class Connection(f.Connection):
    effect_change=None
    def execute(self,sql,params=None):
        if sql.startswith('BEGIN ISOLATION'):
            self.calls.append((sql,params));self.info.transaction_status=2;return f.Cursor(tag='BEGIN')
        if sql=='ROLLBACK':
            self.calls.append((sql,params));self.info.transaction_status=0;return f.Cursor(tag='ROLLBACK')
        if sql==m.SNAPSHOT_SQL:return f.Cursor([dict(isolation='repeatable read',readOnly='on',snapshot='1:3:')])
        if sql=='SELECT '+m.PEER_SQL+'::text':return f.Cursor([dict(databaseOid=123,postmasterStartMicros='10',serverAddress='127.0.0.1',serverPort=5432)])
        if "'kind','effect'" in sql:
            self.calls.append((sql,params));rows=[]
            for effect in self.effects:
                value=copy.deepcopy(effect);value['kind']='effect';value['version']=str(value['version'])
                if value['baseVersion'] is not None:value['baseVersion']=str(value['baseVersion'])
                rows.append(value)
            if self.effect_change:self.effect_change(rows)
            return f.Cursor([r for r in rows if int(r['version'])>int(params[0])][:1])
        return super().execute(sql,params)


class WindowTests(unittest.TestCase):
    def setUp(self):
        base=Path(os.environ['MTW_WINDOW_V2_TEST_ROOT']);base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def prepared(self):
        c=Connection()
        m.source.install_configured_source_v2(c,self.root/'install',c.config,f.POLICY,opt_in=True)
        return c,m.SourceInputsV2.from_directory(self.root/'install')
    def observe(self,c,inputs,**kwargs):
        with patch.object(m,'_pinned_connection',return_value=True):
            return m.observe_source_snapshot_v2(c,self.root/'snapshot',c.config,f.POLICY,inputs,opt_in=True,**kwargs)
    def test_original_inputs_are_byte_and_config_bound(self):
        c,inputs=self.prepared();self.assertEqual(inputs.validate(c.config,f.POLICY)['status'],'installed-components-only')
        with self.assertRaises(ValueError):inputs.validate(f.config('text'),f.POLICY)
        changed=m.SourceInputsV2(inputs.installation_log_text+'\n',inputs.installation_receipt_text)
        with self.assertRaises((ValueError,TypeError)):changed.validate(c.config,f.POLICY)
    def test_sequence_boolean_cannot_impersonate_one(self):
        c,inputs=self.prepared();lines=inputs.installation_log_text.splitlines(keepends=True)
        header=json.loads(lines[0]);header['seq']=True;lines[0]=m.canonical(header)+'\n'
        with self.assertRaises(ValueError):m._sealed(''.join(lines),json.loads(inputs.installation_receipt_text)['log'],m.source.LOG_FORMAT)
    def test_sealed_log_checks_record_structure_after_rehash(self):
        header = m.canonical({'kind': 'header', 'seq': 1, 'format': m.SNAPSHOT_LOG}) + '\r\n'
        valid = m.canonical({'kind': 'test', 'seq': 2, 'value': '行🙂'}) + '\r\n'

        def check(line):
            prefix = header + line
            text = prefix + m.canonical({'kind': 'seal', 'seq': 3, 'records': 2,
                                         'prefixSha256': m.digest(prefix)}) + '\n'
            receipt = {'sealed': True, 'records': 3, 'bytes': len(text.encode('utf8')), 'sha256': m.digest(text)}
            m._sealed(text, receipt, m.SNAPSHOT_LOG)

        check(valid)
        with self.assertRaisesRegex(ValueError, 'sequence'):
            check(valid.replace('"seq":2', '"seq":true'))
        with self.assertRaisesRegex(ValueError, 'newline-terminated'):
            check(valid.replace('"seq":2', '"seq":\r2'))
    def test_snapshot_uses_own_header_and_preserves_original_files(self):
        c,inputs=self.prepared();before=inputs.installation_log_text
        receipt=json.loads(self.observe(c,inputs).read_text('utf8'))
        self.assertEqual(receipt['status'],'observed-components-only');self.assertEqual(receipt['effectVersions'],['1'])
        self.assertFalse(receipt['completeWindow']);self.assertFalse(receipt['modelCoverageAccepted'])
        raw=(self.root/'snapshot/snapshot.jsonl').read_text('utf8')
        self.assertEqual(json.loads(raw.splitlines()[0])['format'],m.SNAPSHOT_LOG)
        m._sealed(raw,receipt['log'],m.SNAPSHOT_LOG)
        self.assertEqual(inputs.installation_log_text,before);self.assertEqual(c.info.transaction_status,0)
    def test_row_budget_has_no_partial_success(self):
        c,inputs=self.prepared()
        with self.assertRaisesRegex(m.source.SourceInstallError,'row budget'):self.observe(c,inputs,max_rows=0)
        r=json.loads((self.root/'snapshot/snapshot-receipt.json').read_text('utf8'))
        self.assertEqual(r['status'],'failed');self.assertFalse(r['completeWindow'])
    def test_effect_budget_has_no_partial_success(self):
        c,inputs=self.prepared()
        with self.assertRaisesRegex(m.source.SourceInstallError,'effect budget'):self.observe(c,inputs,max_effects=0)
    def test_missing_visible_source_is_rejected(self):
        c,inputs=self.prepared();c.effect_change=lambda rows:rows.clear()
        with self.assertRaisesRegex(m.source.SourceInstallError,'source is absent'):self.observe(c,inputs)
    def test_changed_visible_row_value_is_rejected(self):
        c,inputs=self.prepared()
        def alter(rows):rows[0]['rowValues']['flag']=False
        c.effect_change=alter
        with self.assertRaisesRegex(m.source.SourceInstallError,'differs'):self.observe(c,inputs)
    def test_retained_snapshot_starts_from_zero_not_prior_watermark(self):
        c,inputs=self.prepared();self.observe(c,inputs)
        requests=[p for sql,p in c.calls if "'kind','effect'" in sql]
        self.assertEqual(requests[0],('0',));self.assertEqual(requests[-1],('1',))
        self.assertTrue(any(sql.startswith('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY') for sql,_ in c.calls))
    def test_new_snapshot_rescans_low_identity_committed_later(self):
        c,inputs=self.prepared();original=copy.deepcopy(c.effects[0]);high=copy.deepcopy(original)
        high.update(version=5,operation='INSERT',rowKey='00000000-0000-0000-0000-000000000005',writerLogin='writer')
        high['rowValues']['Key ID']=high['rowKey'];c.effects.append(high)
        first=json.loads(self.observe(c,inputs).read_text('utf8'));self.assertEqual(first['effectVersions'],['1','5'])
        low=copy.deepcopy(high);low.update(version=3,rowKey='00000000-0000-0000-0000-000000000003');low['rowValues']['Key ID']=low['rowKey']
        c.effects.insert(1,low)
        with patch.object(m,'_pinned_connection',return_value=True):
            second=m.observe_source_snapshot_v2(c,self.root/'second',c.config,f.POLICY,inputs,opt_in=True)
        self.assertEqual(json.loads(second.read_text('utf8'))['effectVersions'],['1','3','5'])
    def test_unsealed_installation_refused_before_snapshot_output(self):
        c,inputs=self.prepared();r=json.loads(inputs.installation_receipt_text);r['log']['sealed']=False
        bad=m.SourceInputsV2(inputs.installation_log_text,m.canonical(r))
        with self.assertRaises(ValueError):self.observe(c,bad)
        self.assertFalse((self.root/'snapshot').exists())
    def test_invalid_opt_in_does_not_access_connection(self):
        class Bomb:
            def __getattr__(self,key):raise AssertionError(key)
        with self.assertRaises(ValueError):m.observe_source_snapshot_v2(Bomb(),self.root/'x',None,None,None)
        self.assertFalse((self.root/'x').exists())
    def test_bad_limits_refused_before_output(self):
        c,inputs=self.prepared()
        for value in [True,-1,16385]:
            with self.assertRaises(ValueError):self.observe(c,inputs,max_rows=value)
        self.assertFalse((self.root/'snapshot').exists())
    def test_exact_native_control_exception_is_retained(self):
        c,inputs=self.prepared();c.fail_sql='pg_catalog.jsonb_build_object';error=c.error
        with self.assertRaises(RuntimeError) as caught:self.observe(c,inputs)
        self.assertIs(caught.exception,error)
    def test_duplicate_visible_key_cannot_be_hidden_by_version_identity(self):
        c,inputs=self.prepared();row=copy.deepcopy(c.values[0]);row[m.source.VERSION_COLUMN]=2;c.values.append(row)
        with self.assertRaisesRegex(m.source.SourceInstallError,'Duplicate visible'):self.observe(c,inputs)
    def test_missing_retained_predecessor_is_rejected(self):
        c,inputs=self.prepared()
        def alter(rows):
            r=copy.deepcopy(rows[0]);r.update(version='3',baseVersion='2',oldKey=r['rowKey'],operation='UPDATE',writerLogin='writer');rows.append(r)
        c.effect_change=alter
        with self.assertRaisesRegex(m.source.SourceInstallError,'predecessor source'):self.observe(c,inputs)
    def test_out_of_scope_retained_writer_is_rejected(self):
        c,inputs=self.prepared()
        def alter(rows):
            r=copy.deepcopy(rows[0]);r.update(version='3',operation='INSERT',writerLogin='unmanaged');rows.append(r)
        c.effect_change=alter
        with self.assertRaisesRegex(m.source.SourceInstallError,'writer is outside'):self.observe(c,inputs)
    def test_failed_seal_does_not_return_snapshot_success(self):
        c,inputs=self.prepared();error=OSError('sync failed');original=m.source._LogV2.close
        def fail(log):original(log);raise error
        with patch.object(m.source._LogV2,'close',fail),self.assertRaises(OSError) as caught:self.observe(c,inputs)
        self.assertIs(caught.exception,error)
        self.assertEqual(json.loads((self.root/'snapshot/snapshot-receipt.json').read_text('utf8'))['status'],'recording-failed')
    def test_window_seal_refuses_live_participants_before_reading_database(self):
        window=object.__new__(m.ConfiguredCaptureWindowV2)
        window._lock=m.threading.RLock();window._state='open'
        window._participants=[types.SimpleNamespace(_raw=types.SimpleNamespace(closed=False))]
        with self.assertRaises(ValueError):window.seal()
        self.assertEqual(window._state,'open')
    def test_repeated_enrollment_returns_same_participant_at_capacity(self):
        window=object.__new__(m.ConfiguredCaptureWindowV2);window._lock=m.threading.RLock();window._state='open';window.control=object()
        original=object();p=types.SimpleNamespace(_raw=original);window._participants=[p]*32
        self.assertIs(window.wrap_connection(original),p);self.assertIs(window.wrap_connection(p),p)
        with self.assertRaises(ValueError):window.wrap_connection(object())
    def test_snapshot_log_is_rechecked_before_binding_envelope(self):
        c,inputs=self.prepared();window=object.__new__(m.ConfiguredCaptureWindowV2)
        window.output=self.root/'window';window.output.mkdir();window.control=c;window.config=c.config
        window.policy=f.POLICY;window.installation=inputs;window._max_rows=window._max_effects=4096
        window._snapshot_profile='row-v2'
        original=m.observe_source_snapshot_v2
        def corrupt(*args,**kwargs):
            path=original(*args,**kwargs)
            with (path.parent/'snapshot.jsonl').open('ab') as file:file.write(b'\n')
            return path
        with patch.object(m,'_pinned_connection',return_value=True),patch.object(m,'observe_source_snapshot_v2',corrupt),self.assertRaises(ValueError):
            window._snapshot('start')
        self.assertFalse((window.output/'start-input.json').exists())
    def test_snapshot_receipt_status_is_rechecked_before_binding_envelope(self):
        c,inputs=self.prepared();window=object.__new__(m.ConfiguredCaptureWindowV2)
        window.output=self.root/'window';window.output.mkdir();window.control=c;window.config=c.config
        window.policy=f.POLICY;window.installation=inputs;window._max_rows=window._max_effects=4096
        window._snapshot_profile='row-v2'
        original=m.observe_source_snapshot_v2
        def corrupt(*args,**kwargs):
            path=original(*args,**kwargs);r=json.loads(path.read_text('utf8'));r['status']='failed';path.write_text(json.dumps(r),encoding='utf8');return path
        with patch.object(m,'_pinned_connection',return_value=True),patch.object(m,'observe_source_snapshot_v2',corrupt),self.assertRaises(ValueError):
            window._snapshot('start')
    def test_failed_receipt_file_sync_cannot_publish_success_filename(self):
        window=object.__new__(m.ConfiguredCaptureWindowV2);window.output=self.root
        original=m.write_new;error=OSError('receipt fsync failed')
        def fail(path,raw):original(path,raw);raise error
        with patch.object(m,'write_new',fail),self.assertRaises(OSError) as caught:window._publish_receipt({'status':'sealed-original-inputs'})
        self.assertIs(caught.exception,error)
        self.assertFalse((self.root/'window-receipt.json').exists())
        self.assertTrue((self.root/'window-receipt.pending.json').exists())
    def test_failed_receipt_directory_sync_removes_new_success_link(self):
        window=object.__new__(m.ConfiguredCaptureWindowV2);window.output=self.root
        with patch.object(m,'_sync_directory',side_effect=OSError('directory fsync failed')),self.assertRaises(OSError):
            window._publish_receipt({'status':'sealed-original-inputs'})
        self.assertFalse((self.root/'window-receipt.json').exists())
    def test_success_receipt_publication_never_overwrites_existing_target(self):
        window=object.__new__(m.ConfiguredCaptureWindowV2);window.output=self.root
        (self.root/'window-receipt.json').write_bytes(b'existing')
        with self.assertRaises(FileExistsError):window._publish_receipt({'status':'sealed-original-inputs'})
        self.assertEqual((self.root/'window-receipt.json').read_bytes(),b'existing')
    def seal_fixture(self,*,tamper_trace=False):
        window=object.__new__(m.ConfiguredCaptureWindowV2)
        window.output=self.root/'seal';window.output.mkdir();(window.output/'capture').mkdir()
        window._lock=m.threading.RLock();window._state='open';window._participants=[types.SimpleNamespace(_raw=types.SimpleNamespace(closed=True))]
        window.config=f.config();window.policy=f.POLICY;window.installation=m.SourceInputsV2('original-log','original-receipt')
        start='{}\n';m.write_new(window.output/'start-input.json',start);window._start_digest=m.digest(start)
        log=m.source._LogV2(window.output/'capture/lifecycle.jsonl',1024*1024,log_format='moontxnwitness-instrumentation/v1')
        metadata=log.close();m.write_new(window.output/'capture/instrumentation.json',m.canonical({'lifecycle':metadata}))
        def end(side):
            raw='{"end":true}\n';m.write_new(window.output/'end-input.json',raw);window._end_digest=m.digest(raw)
        window._snapshot=end
        class Observer:
            def frame(self,*args):return 1
            def close(self):pass
            def export_diagnostic(self,path):
                raw='{}\n';m.write_new(path,'[]\n' if tamper_trace else raw)
                return {'sha256':m.digest(raw),'bytes':len(raw)}
        window.observer=Observer()
        return window
    def test_trace_export_digest_is_checked_before_packaging(self):
        window=self.seal_fixture(tamper_trace=True)
        with self.assertRaisesRegex(ValueError,'trace changed'):window.seal()
        self.assertFalse((window.output/'window-receipt.json').exists())
        self.assertTrue((window.output/'window-failure.json').exists())
        self.assertEqual(window._state,'failed')
    def test_sealed_original_bundle_and_success_receipt_are_byte_bound(self):
        window=self.seal_fixture();path=window.seal();r=json.loads((window.output/'window-receipt.json').read_text('utf8'))
        self.assertEqual(r['bundleSha256'],m.digest(path.read_text('utf8')))
        self.assertFalse(r['completeWindow']);self.assertFalse(r['modelCoverageAccepted']);self.assertEqual(window._state,'sealed')
        with self.assertRaises(ValueError):window.seal()

    def test_streamed_bundle_preserves_canonical_bytes_and_exact_limit(self):
        path = self.root / 'bundle.json'
        bundle = {'z': '月光🌙\r\n"\\', 'a': '{}\n'}
        expected = (m.canonical(bundle) + '\n').encode('utf-8')
        with self.assertRaisesRegex(ValueError, 'byte budget'):
            m._write_window_bundle(path, bundle, maximum=len(expected) - 1)
        self.assertFalse(path.exists())
        self.assertFalse(path.with_suffix('.pending.json').exists())
        checksum = m._write_window_bundle(path, bundle, maximum=len(expected))
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(checksum, m.hashlib.sha256(expected).hexdigest())
        with self.assertRaises(FileExistsError):
            m._write_window_bundle(path, {'other': 'bundle'})
        self.assertEqual(path.read_bytes(), expected)

    def test_bundle_sync_failure_cannot_publish_bundle_or_receipt(self):
        window = self.seal_fixture()
        original = m._write_window_bundle
        def fail_sync(*args, **kwargs):
            with patch.object(m.os, 'fsync', side_effect=OSError('bundle sync failed')):
                return original(*args, **kwargs)
        with patch.object(m, '_write_window_bundle', fail_sync), self.assertRaisesRegex(OSError, 'bundle sync'):
            window.seal()
        self.assertFalse((window.output/'configured-window-input.json').exists())
        self.assertFalse((window.output/'window-receipt.json').exists())
        self.assertTrue((window.output/'window-failure.json').exists())


if __name__=='__main__':unittest.main(verbosity=2)
