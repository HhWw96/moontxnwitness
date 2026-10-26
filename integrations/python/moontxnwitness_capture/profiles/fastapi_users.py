"""Explicit fixed base-user profile; raw diagnostics remain partial.

Installation changes an explicitly configured controlled table. Unknown SQL is
left unchanged. Only the independent MoonBit promotion entry may accept mapping
coverage from the complete original source package.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from ..capture_v3 import CaptureV3Session
from ..instrumentation import Instrumentation,DiagnosticConnection,DiagnosticAsyncConnection
from ..orm import UserScope,StructuredSQLCache,CoverageRequired,FIELDS,VALUES,PROFILE
from ..source_sink import GroupedSourceSink,verify_grouped_source,_validate_write_buffer_bytes
from .orm_control import ControlConnection,append_source
from . import orm_install
from .orm_cursor import ProfileSyncConnection,ProfileAsyncConnection

FORMAT='moontxnwitness-orm-profile-source/v1'


def _bounded_text(path,bound):
    with Path(path).open('rb') as file:raw=file.read(bound+1)
    if len(raw)>bound:raise CoverageRequired('Original profile source exceeds its analysis/export bound')
    return raw.decode('utf8',errors='strict')


class UserProfileCapture(Instrumentation):
    def __init__(self,path,installation,sink,**options):
        if type(installation.scope) is not UserScope:
            raise CoverageRequired('Explicit immutable UserScope required')
        self.installation,self.scope,self.sink=installation,installation.scope,sink
        self._quiescing=self._profile_finalized=False
        self.source_storage=None
        self.cache=StructuredSQLCache()
        plans=[self.cache.prepare(self.scope,'get',pk_bind=name) for name in ('id_1','pk_1')]
        plans += [self.cache.prepare(self.scope,'create',pk_bind='id'),self.cache.prepare(self.scope,'delete',pk_bind='id')]
        for mask in range(1,32):
            fields=tuple(name for i,name in enumerate(VALUES) if mask & (1<<i))
            # The existing independent source verifier accepts this pinned
            # schema-qualified ORM identity-map bind only. Other cache shapes
            # are useful compiler assets but do not grant this profile proof.
            bind=self.scope.schema+'_'+self.scope.table+'_id'
            plans.append(self.cache.prepare(self.scope,'update',fields,bind))
        self.plans={plan.original_sql:plan for plan in plans}
        super().__init__(path,**options)
        append_source(sink,{'kind':'installation','metadata':installation.metadata,
            'knownIds':self.scope.known_ids,'schema':self.scope.schema,'table':self.scope.table})
        window=installation.metadata['initializationWindow']
        self.note('profile-window-open',profile=PROFILE,installationNonce=installation.nonce,
            initialCommitSourceSeq=window[-1]['querySeq'],
            initialSnapshotSourceSeq=installation.metadata['initialSnapshotQuerySeq'])
    def publish_snapshot(self,initial,*,consistent):
        # Instrumentation calls this once during construction. Its explicitly
        # installed subtype publishes the real locked, acknowledged initial
        # state directly; no existing event is edited or replaced afterward.
        metadata=self.installation.metadata
        window=metadata.get('initializationWindow',())
        if not window or window[-1].get('commandTag')!='COMMIT':
            raise CoverageRequired('Initial source transaction lacks its observed COMMIT')
        actual=self.installation.initial
        if set(actual)!=set(self.scope.known_ids):raise CoverageRequired('Incomplete fixed-domain initial source')
        self.exclusive_writers=True
        return CaptureV3Session.publish_snapshot(self,{key:row['version'] for key,row in actual.items()},consistent=True)
    def _wrap(self,raw,*,asynchronous):
        self.activity('connect')
        if not self._enabled:return raw
        with self._lock:
            if isinstance(raw,(DiagnosticConnection,DiagnosticAsyncConnection)):
                if raw._session is not self:self.gap('foreign_observer','Connection already belongs to another observer.')
                return raw
            if len(self._connections)>=self._max_connections:
                self.gap('connection_budget','Connection runs without fixed-profile observation.');return raw
            cls=ProfileAsyncConnection if asynchronous else ProfileSyncConnection
            wrapped=cls(self,raw);self._connections.add(wrapped)
            self.note('connect',connection=wrapped._identity,asynchronous=asynchronous)
            return wrapped
    def finalize(self,control):
        """Call after stopping application workers; the core verifies closure."""
        if self._profile_finalized or self._closed:raise CoverageRequired('One finalization attempt per profile window')
        if type(control) is not ControlConnection or control.sink is not self.sink:
            raise CoverageRequired('Finalization must record original SQL into the same source journal')
        with self._lock:
            self._quiescing=True
            if self._borrowed or any(connection._tx is not None for connection in self._connections):
                self.gap('profile_window_active','Stop workers, return borrowed connections and acknowledge transaction outcomes first.')
                raise CoverageRequired('The application window is not quiescent')
            self.note('profile-window-quiesced',profile=PROFILE,installationNonce=self.installation.nonce)
        record=orm_install.finalize(control,self.installation)
        append_source(self.sink,record)
        self.note('profile-window-close',profile=PROFILE,installationNonce=self.installation.nonce,
            finalCommitSourceSeq=record['finalizationWindow'][-1]['querySeq'],
            finalSnapshotSourceSeq=record['finalSnapshotQuerySeq'],finalLedgerSourceSeq=record['ledgerQuerySeq'])
        self.source_storage=self.sink.close()
        if not self.source_storage['storageSealed']:raise CoverageRequired('Original source journal is incomplete')
        self._profile_finalized=True
        return self.close()
    def close(self,*,source_closed=False):
        if not self._closed and not self._profile_finalized:
            self.gap('profile_window_unclosed','No complete locked finalization window was observed.')
            try:self.source_storage=self.sink.close()
            except Exception:self.gap('profile_source_storage_failed','Source storage could not be sealed.')
        # Raw index sourceClosed intentionally remains false. New independent
        # promotion consumes the separate source/window evidence.
        return super().close(source_closed=False)
    def export_profile(self,destination):
        if not self._closed:raise CoverageRequired('Close the raw diagnostic before exporting the source package')
        verify_grouped_source(self.sink.path)
        trace_path=self.output/'trace.json'
        if not trace_path.exists():self.export_diagnostic(trace_path)
        if self._last_exported_trace is None or self._last_exported_trace[0]!=trace_path.resolve():
            raise CoverageRequired('Only this observer original diagnostic may be packaged')
        trace=_bounded_text(trace_path,8*1024*1024)
        if hashlib.sha256(trace.encode('utf8')).hexdigest()!=self._last_exported_trace[1]:
            raise CoverageRequired('Original raw trace changed')
        package={'format':FORMAT,'profile':PROFILE,'traceText':trace,
            'sourceJournalText':_bounded_text(self.sink.path,16*1024*1024),
            'lifecycleText':_bounded_text(self.output/'lifecycle.jsonl',8*1024*1024),
            'journalIndexText':_bounded_text(self.journal.path/'journal-index.json',2*1024*1024)}
        raw=(json.dumps(package,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8')
        if len(raw)>64*1024*1024:raise CoverageRequired('Combined source envelope exceeds 64 MiB')
        with Path(destination).open('xb') as file:
            if file.write(raw)!=len(raw):raise OSError('Short profile source write')
            file.flush();os.fsync(file.fileno())
        return {'format':FORMAT,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'analysisCoverageAccepted':False,'reason':'producer package only; independent MoonBit promotion must run'}


def install_user_profile(setup,scope,output,*,source_write_buffer_bytes=0,**capture_options):
    """Explicit opt-in migration, never called by diagnostic instrumentation."""
    if type(scope) is not UserScope:raise CoverageRequired('Explicit fixed UserScope required')
    _validate_write_buffer_bytes(source_write_buffer_bytes)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    sink=GroupedSourceSink(output/'sources.jsonl',write_buffer_bytes=source_write_buffer_bytes)
    control=ControlConnection(setup,sink)
    try:
        installation=orm_install.install(control,scope,diagnostic_path=output/'initial-relation.json')
        capture=UserProfileCapture(output/'capture',installation,sink,**capture_options)
        return capture,control
    except BaseException:
        try:sink.close()
        except BaseException:pass
        raise
