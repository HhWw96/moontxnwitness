"""Bounded original-input producer for explicitly installed V2 point windows.

Snapshots enumerate the complete retained ledger in each independent database
snapshot. Version allocation order is never used as commit order or as an
incremental visibility watermark. Sealing is durability, not model admission.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import threading

from .capture_v3 import _pinned_connection
from .journal_v3 import _sync_directory
from .configured_session import read_retained_bytes, read_text, write_new
from .configured_point_capture_v2 import PointCaptureV2
from .instrumentation import DiagnosticConnection
from .configured_point_projection_v2 import PointProjectionOptionsV2
from .configured_sql_v2 import SQLCaptureConfigV2, _input_value
from . import configured_source_v2 as source
from .configured_effects import PEER_SQL, SNAPSHOT_SQL
from .configured_factory_v2 import (require_sync_factory_v2, require_sync_result_v2,
    close_rejected_sync_result_v2, record_factory_gap_v2)

CONTRACT = 'postgres18-configured-point-window-observations/v2'
SNAPSHOT_FORMAT = 'moontxnwitness-configured-source-snapshot/v2'
SNAPSHOT_LOG = 'moontxnwitness-source-snapshot-log/v2'
INPUT_FORMAT = 'moontxnwitness-configured-window-input/v2'
PAGED_SNAPSHOT_FORMAT = 'moontxnwitness-configured-source-snapshot-paged/v1'
PAGED_SNAPSHOT_LOG = 'moontxnwitness-source-snapshot-log-paged/v1'
PAGED_SNAPSHOT_CONTRACT = 'postgres18-configured-source-snapshot-pages/v1'


def _snapshot_profile(profile):
    if profile == 'row-v2':
        return SNAPSHOT_FORMAT, SNAPSHOT_LOG, CONTRACT, 1
    if profile == 'paged-v1':
        return PAGED_SNAPSHOT_FORMAT, PAGED_SNAPSHOT_LOG, PAGED_SNAPSHOT_CONTRACT, 128
    raise ValueError('Unknown snapshot profile')


canonical, digest = source.canonical, lambda text: hashlib.sha256(text.encode('utf8')).hexdigest()


def _sealed(text, receipt, log_format):
    _sealed_bytes(text.encode('utf8'), receipt, log_format)


def _sealed_bytes(payload, receipt, log_format):
    if not payload.endswith(b'\n'):
        raise ValueError('Original sealed log requires complete newline-terminated records')
    if (receipt.get('sealed') is not True or type(receipt.get('bytes')) is not int
            or receipt['bytes'] != len(payload) or receipt.get('sha256') != hashlib.sha256(payload).hexdigest()):
        raise ValueError('Original log seal/digest/inventory differs')

    cursor = io.BytesIO(payload)
    count = 0
    for line in cursor:
        count += 1
        cr = line.find(b'\r')
        if cr >= 0 and cr != len(line) - 2:
            raise ValueError('Original sealed log requires complete newline-terminated records')
        record = source._json(line.decode('utf8'))
        if type(record) is not dict or type(record.get('seq')) is not int or record['seq'] != count:
            raise ValueError('Original log sequence differs')
        if count == 1 and (record.get('kind') != 'header' or record.get('format') != log_format):
            raise ValueError('Original log seal/digest/inventory differs')
        if cursor.tell() == len(payload):
            prefix = memoryview(payload)[:len(payload) - len(line)]
            if (record.get('kind') != 'seal' or type(record.get('records')) is not int
                    or record['records'] != count - 1 or type(receipt.get('records')) is not int
                    or receipt['records'] != count
                    or record.get('prefixSha256') != hashlib.sha256(prefix).hexdigest()):
                raise ValueError('Original log seal/digest/inventory differs')


def _checked_text(path, maximum, expected_sha256, message, expected_bytes=None, *, streamed):
    if streamed:
        payload = read_retained_bytes(path, maximum)
        text = None
    else:
        text = read_text(path, maximum)
        payload = text.encode('utf-8')
    if ((expected_bytes is not None and expected_bytes != len(payload))
            or expected_sha256 != hashlib.sha256(payload).hexdigest()):
        raise ValueError(message)
    return payload.decode('utf-8', errors='strict') if streamed else text


def _write_window_bundle(path, bundle, maximum=32 * 1024 * 1024):
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'), allow_nan=False)
    pending = path.with_suffix('.pending.json')
    checksum = hashlib.sha256()
    count = 0
    stream = pending.open('xb')
    try:
        with stream:
            for part in encoder.iterencode(bundle):
                payload = part.encode('utf-8')
                count += len(payload)
                if count >= maximum:
                    raise ValueError('Window bundle byte budget exceeded; original files retained')
                if stream.write(payload) != len(payload):
                    raise OSError('Short window bundle write')
                checksum.update(payload)
            if stream.write(b'\n') != 1:
                raise OSError('Short window bundle write')
            checksum.update(b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, path)
    finally:
        pending.unlink()
    return checksum.hexdigest()


@dataclass(frozen=True,slots=True)
class SourceInputsV2:
    installation_log_text: str
    installation_receipt_text: str

    @classmethod
    def from_directory(cls, directory):
        path=Path(directory)
        return cls(read_text(path/'source-install-v2.jsonl',64*1024*1024),
                   read_text(path/'receipt-v2.json',1024*1024))

    def validate(self,config,policy):
        if type(config) is not SQLCaptureConfigV2 or type(policy) is not source.SourceInstallPolicy:
            raise ValueError('Independent immutable V2 configuration and source policy required')
        receipt=source._json(self.installation_receipt_text)
        if (receipt.get('format')!=source.FORMAT or receipt.get('contract')!=source.CONTRACT
                or receipt.get('status')!='installed-components-only'
                or receipt.get('actualCommitConfirmed') is not True
                or receipt.get('config')!=config.to_dict() or receipt.get('configSha256')!=config.sha256
                or receipt.get('policy')!=policy.to_dict()):
            raise ValueError('Original acknowledged V2 installation with independent config/policy required')
        _sealed(self.installation_log_text,receipt.get('log',{}),source.LOG_FORMAT)
        return receipt  # Component claim only; an independent core must replay the original log.


def ledger_snapshot_sql_v2(policy, page_size=1):
    return ("SELECT CASE WHEN pg_catalog.octet_length(p.payload)>65536 THEN '{\"kind\":\"effect-budget\"}' ELSE p.payload END FROM "
        "(SELECT e.version,pg_catalog.jsonb_build_object('kind','effect','version',e.version::text,"
        "'baseVersion',e.base_version::text,'relationOid',e.relation_oid::bigint,'operation',e.operation,"
        "'writerXid',e.writer_xid,'writerLogin',e.writer_login,'writerPid',e.writer_pid,"
        "'rowKey',e.row_key,'oldKey',e.old_key,'rowValues',e.row_values)::text payload FROM "
        +source._qi(policy.namespace)+".effects e WHERE e.version>%s::bigint ORDER BY e.version LIMIT "
        +str(source._integer(page_size, 1, 128, "Snapshot page size"))+") p"
        +(" ORDER BY p.version" if page_size != 1 else ""))


def _version(value):
    if type(value) is not str or not value.isascii() or not value.isdigit() or not 1<=len(value)<=19:
        raise source.SourceInstallError('Canonical positive decimal source identity required')
    number=int(value)
    if not 1<=number<=2**63-1 or str(number)!=value:
        raise source.SourceInstallError('Source identity exceeds bigint or is not canonical')
    return number


def _business_hash(config,key,values):
    if type(values) is not dict or set(values)!={c.name for c in config.table.columns}:
        raise source.SourceInstallError('Complete configured business row required')
    for column in config.table.columns:
        value=values[column.name]
        identity=_input_value(value,column.type,config.max_text_bytes)
        if column.type=='uuid' and (type(value) is not str or value!=identity):
            raise source.SourceInstallError('Canonical UUID identity required in native JSON')
    if values[config.table.primary_key]!=key:
        raise source.SourceInstallError('Ledger key and full row identity differ')
    return digest(canonical(values))


def observe_source_snapshot_v2(connection,output,config,policy,installation,*,opt_in=False,max_rows=4096,max_effects=4096,snapshot_profile='row-v2'):
    format_name, log_format, contract, page_size = _snapshot_profile(snapshot_profile)
    if opt_in is not True or type(installation) is not SourceInputsV2:
        raise ValueError('Explicit source snapshot opt-in and original installation inputs required')
    original=installation.validate(config,policy)
    if any(type(n) is not int or not 0<=n<=16384 for n in (max_rows,max_effects)):
        raise ValueError('Independent row/effect limits must be 0..16384')
    if not _pinned_connection(connection) or connection.autocommit is not True or int(connection.info.transaction_status)!=0:
        raise ValueError('Dedicated idle autocommit pinned control connection required')
    path=Path(output).resolve();path.mkdir(parents=True,exist_ok=False)
    log=source._LogV2(path/'snapshot.jsonl',policy.max_log_bytes,log_format=log_format,contract=contract)
    control=source._ControlV2(connection,log,terminal_queries=('snapshot-finish',))
    receipt={'format':format_name,'contract':contract,'status':'failed','configSha256':config.sha256,
        'installationLogSha256':digest(installation.installation_log_text),'maxRows':max_rows,'maxEffects':max_effects,
        'sourceFactsProduced':False,'sourceAuthenticated':False,'moonbitSourceVerified':False,
        'completeWindow':False,'modelCoverageAccepted':False,'rowsObserved':0,'effectsObserved':0}
    pending=None
    try:
        source._ack(control,'snapshot-begin','BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY','BEGIN')
        source._ack(control,'snapshot-safe-path','SET LOCAL search_path TO pg_catalog,pg_temp','SET')
        mode=source._one(control,'snapshot-mode',SNAPSHOT_SQL)
        if mode.get('isolation')!='repeatable read' or mode.get('readOnly')!='on' or not mode.get('snapshot'):
            raise source.SourceInstallError('Actual read-only repeatable snapshot required')
        receipt['snapshot']=mode
        receipt['peer']=source._one(control,'snapshot-peer','SELECT '+PEER_SQL+'::text')
        env=source._one(control,'environment',source.ENVIRONMENT_SQL,(list(policy.writers),))
        owner=source.verify_environment_v2(policy,env)
        if any(env.get(k)!=original['environment'].get(k) for k in ('database','databaseOid','owner')):
            raise source.SourceInstallError('Snapshot environment differs from installation')
        source.verify_source_catalog_v2(policy,owner,source._one(control,'source-catalog',source.SOURCE_CATALOG_SQL,(policy.namespace,)))
        actual=source._one(control,'table-catalog',source.TABLE_CATALOG_SQL,(config.table.schema,config.table.table))
        oid=source.verify_table_catalog_v2(config.table,policy,owner,actual,installed=True)
        if canonical(actual)!=canonical(original['afterCatalog']):
            raise source.SourceInstallError('Installed table catalog changed before snapshot')
        receipt['tableOid']=oid
        for writer in policy.writers:
            row=source._one(control,'writer-privileges',source.PERMISSIONS_SQL,
                (writer,source.target(config.table),writer,source.target(config.table),writer,source.target(config.table),writer,owner))
            if any(row.get(k) is not False for k in ('trigger','truncate','ownerMembership')):
                raise source.SourceInstallError('Writer can bypass the installed row-only scope')
        q=source._qi(policy.namespace)
        scopes,_=control.command('source-scope',f"SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint,'relation_schema',s.relation_schema,'relation_table',s.relation_table,'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM {q}.scope s ORDER BY relation_schema,relation_table")
        if scopes!=original.get('sourceScope'):
            raise source.SourceInstallError('Installed source scope changed')
        rows_by_version={};row_keys=set();last=0
        query = 'visible-row' if page_size == 1 else 'visible-row-page'
        sql = source.initial_snapshot_sql_v2(config, page_size)
        while True:
            page,_=control.command(query,sql,(last,),max_rows=page_size)
            if not page:break
            for observed in page:
                if len(rows_by_version)==max_rows:raise source.SourceInstallError('Snapshot row budget exhausted')
                version,row,identity=source._initial_row(config,observed,last)
                if identity in row_keys:raise source.SourceInstallError('Duplicate visible primary-key identity')
                row_keys.add(identity)
                values={k:v for k,v in row.items() if k!=source.VERSION_COLUMN}
                rows_by_version[str(version)]=_business_hash(config,values[config.table.primary_key],values);last=version
        last=0;versions=[];parents={};visible_matches=set()
        query = 'retained-effect' if page_size == 1 else 'retained-effect-page'
        sql = ledger_snapshot_sql_v2(policy, page_size)
        while True:
            page,_=control.command(query,sql,(str(last),),max_rows=page_size)
            if not page:break
            for effect in page:
                if len(versions)==max_effects:raise source.SourceInstallError('Snapshot effect budget exhausted')
                if effect.get('kind')!='effect' or effect.get('relationOid')!=oid:
                    raise source.SourceInstallError('Incomplete or differently scoped retained effect')
                version=_version(effect.get('version'));base=effect.get('baseVersion');operation=effect.get('operation')
                if version<=last or operation not in ('INITIAL','INSERT','UPDATE','DELETE'):
                    raise source.SourceInstallError('Retained effect identity/order differs')
                if operation in ('INITIAL','INSERT'):
                    if base is not None or effect.get('oldKey') is not None:raise source.SourceInstallError('Unexpected initial/insert predecessor')
                else:
                    _version(base)
                    if effect.get('oldKey')!=effect.get('rowKey'):raise source.SourceInstallError('Changed primary key in retained effects')
                xid=effect.get('writerXid')
                if (type(xid) is not str or not xid.isascii() or not xid.isdigit() or len(xid)>20
                        or not 1<=int(xid)<=2**64-1 or str(int(xid))!=xid):
                    raise source.SourceInstallError('Canonical native full transaction identity required')
                source._integer(effect.get('writerPid'),1,2**31-1,'Writer PID')
                source.identifier(effect.get('writerLogin'))
                key=_input_value(effect.get('rowKey'),config.table.key.type,config.max_text_bytes)
                if config.table.key.type=='uuid' and effect['rowKey']!=key:
                    raise source.SourceInstallError('Canonical native UUID key required')
                if operation!='INITIAL' and effect['writerLogin'] not in policy.writers:
                    raise source.SourceInstallError('Retained effect writer is outside the installed scope')
                if base is not None:
                    parent=parents.get(base)
                    if parent is None or parent[0]=='DELETE' or parent[1]!=(config.table.key.type,key):
                        raise source.SourceInstallError('Retained predecessor source is missing or has a different key')
                if operation=='DELETE':
                    if effect.get('rowValues') is not None:raise source.SourceInstallError('DELETE effect has a live row')
                    if str(version) in rows_by_version:raise source.SourceInstallError('Visible row uses a DELETE ledger event identity')
                else:
                    row_hash=_business_hash(config,key,effect.get('rowValues'))
                    if str(version) in rows_by_version:
                        if row_hash!=rows_by_version[str(version)]:raise source.SourceInstallError('Visible row differs from its complete retained effect')
                        visible_matches.add(str(version))
                versions.append(str(version));parents[str(version)]=(operation,(config.table.key.type,key));last=version
        if visible_matches!=set(rows_by_version):raise source.SourceInstallError('Visible row source is absent from the complete ledger')
        source._ack(control,'snapshot-finish','ROLLBACK','ROLLBACK',state=0)
        receipt.update(status='observed-components-only',rowsObserved=len(rows_by_version),effectsObserved=len(versions),
                       visibleRowVersions=sorted(rows_by_version,key=int),effectVersions=versions)
    except BaseException as error:
        pending=error;receipt.update(errorClass=source._python_type(error),error=str(error))
        try:connection.rollback()
        except BaseException:receipt['rollbackUnknown']=True
        raise
    finally:
        error=None
        try:receipt['log']=log.close()
        except BaseException as e:error=e;receipt['log']={'sealed':False}
        if not receipt['log'].get('sealed'):receipt['status']='recording-failed'
        try:write_new(path/'snapshot-receipt.json',canonical(receipt)+'\n')
        except BaseException as e:error=error or e
        if pending is None and error is not None:raise error
    return path/'snapshot-receipt.json'


class ConfiguredCaptureWindowV2:
    """Owned window producer; independent core admission is a separate step."""

    def _make_observer(self, path, config, **options):
        return PointCaptureV2(path, config, **options)

    def _wrap_participant(self, raw):
        return self.observer.wrap(raw)

    def __init__(self,output,config,control,policy,installation,*,opt_in=False,projection_options=None,
                 max_rows=4096,max_effects=4096,snapshot_profile='row-v2',seal_profile='original-v2',
                 **capture_options):
        _snapshot_profile(snapshot_profile)
        if seal_profile not in ('original-v2', 'streamed-v1'):
            raise ValueError('Unknown seal profile')
        self._snapshot_profile = snapshot_profile
        self._seal_profile = seal_profile
        if opt_in is not True or type(installation) is not SourceInputsV2:
            raise ValueError('Explicit window opt-in and original V2 source inputs required')
        original=installation.validate(config,policy)
        if not _pinned_connection(control):raise ValueError('Pinned synchronous control connection required')
        self.output=Path(output).resolve();self.output.mkdir(parents=True,exist_ok=False)
        self.config,self.policy,self.installation,self.control=config,policy,installation,control
        self._max_rows,self._max_effects=max_rows,max_effects
        self._lock=threading.RLock();self._participants=[];self._state='opening'
        self._pending_factories=0;self._factory_observation_failed=False
        self._snapshot('start')
        if projection_options is not None and projection_options.star_contract is not None:
            actual=original['starCatalogComparison']
            if (actual.get('onlyVersionColumnAdded') is not True
                    or actual.get('declaredBusinessViewMatchesBeforeOrder') is not True
                    or list(projection_options.business_star_columns)!=actual['beforePhysicalColumns']):
                raise ValueError('Declared business star view differs from actual installation catalogs')
        self.observer=self._make_observer(self.output/'capture',config,projection_options=projection_options,opt_in=True,**capture_options)
        if self.observer.frame('configured-window-start',{'format':INPUT_FORMAT,'snapshotInputSha256':self._start_digest,
                'installationLogSha256':digest(installation.installation_log_text),'sourceFactsProduced':False}) is None:
            self.observer.close();raise ValueError('Window start boundary was not retained')
        self._state='open'

    def _snapshot(self,side):
        directory=self.output/side
        format_name, log_format, contract, _ = _snapshot_profile(self._snapshot_profile)
        observe_source_snapshot_v2(self.control,directory,self.config,self.policy,self.installation,
            opt_in=True,max_rows=self._max_rows,max_effects=self._max_effects,snapshot_profile=self._snapshot_profile)
        value={'format':format_name,'logText':read_text(directory/'snapshot.jsonl',64*1024*1024),
               'receiptText':read_text(directory/'snapshot-receipt.json',2*1024*1024)}
        receipt=source._json(value['receiptText'])
        if (receipt.get('format')!=format_name or receipt.get('contract')!=contract
                or receipt.get('status')!='observed-components-only' or receipt.get('configSha256')!=self.config.sha256
                or receipt.get('installationLogSha256')!=digest(self.installation.installation_log_text)):
            raise ValueError('Original snapshot receipt binding differs')
        _sealed(value['logText'],receipt.get('log',{}),log_format)
        raw=canonical(value)+'\n';write_new(self.output/(side+'-input.json'),raw)
        setattr(self,'_'+side+'_digest',digest(raw))
        return value

    def wrap_connection(self,raw):
        with self._lock:
            if self._state!='open' or raw is self.control:
                raise ValueError('Window is not open or participant budget exceeded')
            for participant in self._participants:
                if participant is raw or participant._raw is raw:return participant
            if len(self._participants)>=32:raise ValueError('Window participant budget exceeded')
            wrapped=self._wrap_participant(raw)
            self._participants.append(wrapped)
            return wrapped

    def psycopg_factory(self,factory):
        require_sync_factory_v2(factory)
        def connect(*args,**kwargs):
            with self._lock:
                if self._state!='open':
                    raise ValueError('Window must be open before invoking a local factory')
                pending=getattr(self,'_pending_factories',0)
                if pending>=32:raise ValueError('Concurrent window factory budget exceeded')
                self._pending_factories=pending+1
            raw=None
            try:
                raw=factory(*args,**kwargs)
                require_sync_result_v2(raw)
                return self.wrap_connection(raw)
            except BaseException:
                # Never close the dedicated controller or an existing wrapper.
                protected=(self.control,)
                if isinstance(raw,DiagnosticConnection):
                    protected+=(raw,)
                # Enrolled raw/managed identities are already caller-owned.
                with self._lock:
                    for participant in self._participants:
                        if raw is participant or raw is getattr(participant,'_raw',None):
                            protected+=(raw,);break
                close_rejected_sync_result_v2(raw,protected=protected)
                if not record_factory_gap_v2(self.observer):
                    with self._lock:self._factory_observation_failed=True
                raise
            finally:
                with self._lock:self._pending_factories-=1
        return connect

    def _publish_receipt(self,value):
        pending=self.output/'window-receipt.pending.json';final=self.output/'window-receipt.json'
        write_new(pending,canonical(value)+'\n')
        linked=False
        try:
            # The original journal exporter already requires atomic exclusive
            # hard-link publication. A failed file sync leaves only pending data.
            os.link(pending,final);linked=True
            _sync_directory(self.output)
        except BaseException:
            if linked:
                try:
                    if os.path.samefile(pending,final):final.unlink()
                except BaseException:pass
            raise

    def seal(self):
        with self._lock:
            if getattr(self,'_pending_factories',0):
                raise ValueError('Wait for all local factory calls before sealing the window')
            if getattr(self,'_factory_observation_failed',False):
                raise ValueError('Factory failure observation was not retained; window cannot be sealed')
            if self._state!='open' or not self._participants or any(not p._raw.closed for p in self._participants):
                raise ValueError('Close all enrolled connections before sealing an open nonempty window')
            self._state='sealing'
        try:
            self._snapshot('end')
            if self.observer.frame('configured-window-end',{'format':INPUT_FORMAT,'snapshotInputSha256':self._end_digest,'sourceFactsProduced':False}) is None:
                raise ValueError('Window end boundary was not retained')
            self.observer.close()
            streamed = self._seal_profile == 'streamed-v1'
            metadata=source._json(read_text(self.output/'capture/instrumentation.json',65536))
            lifecycle_path = self.output/'capture/lifecycle.jsonl'
            if streamed:
                lifecycle_bytes = read_retained_bytes(lifecycle_path, 8*1024*1024)
                _sealed_bytes(lifecycle_bytes, metadata.get('lifecycle',{}), 'moontxnwitness-instrumentation/v1')
                lifecycle = lifecycle_bytes.decode('utf-8', errors='strict')
                del lifecycle_bytes
            else:
                lifecycle = read_text(lifecycle_path, 8*1024*1024)
                _sealed(lifecycle, metadata.get('lifecycle',{}), 'moontxnwitness-instrumentation/v1')
            trace=self.output/'diagnostic-trace.json';trace_receipt=self.observer.export_diagnostic(trace)
            trace_bytes = trace_receipt.get('bytes')
            if type(trace_bytes) is not int:
                raise ValueError('Original diagnostic trace changed after export')
            trace_text = _checked_text(trace, 8*1024*1024, trace_receipt.get('sha256'),
                'Original diagnostic trace changed after export', trace_bytes, streamed=streamed)
            # Re-read every original file once; no caller-owned dictionaries or
            # accumulated event list is substituted for the retained inputs.
            start = _checked_text(self.output/'start-input.json', 64*1024*1024,
                self._start_digest, 'Retained snapshot input changed', streamed=streamed)
            end = _checked_text(self.output/'end-input.json', 64*1024*1024,
                self._end_digest, 'Retained snapshot input changed', streamed=streamed)
            bundle={'format':INPUT_FORMAT,'contract':CONTRACT,'configText':canonical(self.config.to_dict()),
                'policyText':canonical(self.policy.to_dict()),'installationLogText':self.installation.installation_log_text,
                'installationReceiptText':self.installation.installation_receipt_text,'startInputText':start,'endInputText':end,
                'lifecycleText':lifecycle,'diagnosticTraceText':trace_text}
            target=self.output/'configured-window-input.json'
            if streamed:
                bundle_sha256 = _write_window_bundle(target, bundle)
            else:
                raw = canonical(bundle) + '\n'
                if len(raw.encode('utf-8')) > 32 * 1024 * 1024:
                    raise ValueError('Window bundle byte budget exceeded; original files retained')
                write_new(target, raw)
                bundle_sha256 = digest(raw)
            self._publish_receipt({'format':'moontxnwitness-configured-window-producer-receipt/v2',
                'status':'sealed-original-inputs','bundleSha256':bundle_sha256,'startInputSha256':self._start_digest,
                'endInputSha256':self._end_digest,'diagnosticTraceSha256':digest(trace_text),'participantCount':len(self._participants),
                'sourceFactsProduced':False,'completeWindow':False,'moonbitSourceVerified':False,'modelCoverageAccepted':False})
            self._state='sealed';return target
        except BaseException as error:
            self._state='failed'
            try:self.observer.close()
            except BaseException:pass
            try:write_new(self.output/'window-failure.json',canonical({'format':INPUT_FORMAT,'status':'failed',
                'errorClass':source._python_type(error),'sourceFactsProduced':False,'completeWindow':False,'modelCoverageAccepted':False})+'\n')
            except BaseException:pass
            raise
