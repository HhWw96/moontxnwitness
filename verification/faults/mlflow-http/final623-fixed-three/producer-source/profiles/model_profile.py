"""Explicit installed list/relation driver profile, separate from diagnostics.

The producer stores observations only. It does not create semantic histories or
grant complete model coverage; the independent MoonBit projection entry does.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import uuid
from ..instrumentation import Instrumentation,DiagnosticConnection,DiagnosticCursor,_diagnostic_call,_error
from ..capture_v3 import CapturedV3Cursor
from ..orm import CoverageRequired
from ..source_sink import GroupedSourceSink,verify_grouped_source
from .orm_control import ControlConnection,append_source,native_result,source_parameters
from .model_sql import ModelScope,PROFILE,FORMAT,plans,ddl,control_sql,validate_parameters


def _bounded(path,limit):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise CoverageRequired('Original model profile exceeds the explicit export budget')
    return raw.decode('utf8',errors='strict')


def _window(control,scope,phase):
    sql=control_sql(scope);start=len(control.query_sequences)
    control.execute('BEGIN')
    try:
        control.execute(sql['lock'])
        snapshot=control.execute(sql['snapshot']);snapshot_rows=snapshot.fetchall()
        ledger=control.execute(sql['ledger']);ledger_rows=ledger.fetchall()
        state=control.execute(sql['state']);state_rows=state.fetchall()
        functions=control.execute(sql['catalog'],(scope.schema,));function_rows=functions.fetchall()
        triggers=control.execute(sql['triggers'],(scope.target,));trigger_rows=triggers.fetchall()
        locale=control.execute(sql['locale']);locale_rows=locale.fetchall()
        control.execute('COMMIT')
    except BaseException:
        try:control.execute('ROLLBACK')
        except Exception:pass
        raise
    return {'phase':phase,'queries':control.references_since(start),
        'snapshot':snapshot.control_query_seq,'ledger':ledger.control_query_seq,'state':state.control_query_seq,
        'catalog':functions.control_query_seq,'triggers':triggers.control_query_seq,'locale':locale.control_query_seq,
        'snapshotRows':snapshot_rows,'ledgerRows':ledger_rows,'stateRows':state_rows,
        'catalogRows':function_rows,'triggerRows':trigger_rows,'localeRows':locale_rows}


class ModelResultView:
    """Keep same-statement metadata outside the original business PGresult."""
    def __init__(self,raw,columns):self._raw,self.nfields=raw,columns
    def _column(self,column):
        if type(column) is not int or not 0<=column<self.nfields:raise IndexError('column out of range')
        return column
    def get_value(self,row,column):return self._raw.get_value(row,self._column(column))
    def fname(self,column):return self._raw.fname(self._column(column))
    def ftype(self,column):return self._raw.ftype(self._column(column))
    def fformat(self,column):return self._raw.fformat(self._column(column))
    def fmod(self,column):return self._raw.fmod(self._column(column))
    def fsize(self,column):return self._raw.fsize(self._column(column))
    def ftable(self,column):return self._raw.ftable(self._column(column))
    def ftablecol(self,column):return self._raw.ftablecol(self._column(column))
    def __getattr__(self,name):return getattr(self._raw,name)


class ModelCursor(DiagnosticCursor):
    def __init__(self,connection,raw):
        super().__init__(connection,raw)
        self._model_plan=None;self._source=None;self._row_events=[];self._business_position=0

    @property
    def description(self):
        value=self._raw.description
        return value[:self._model_plan.columns] if value is not None and self._model_plan else value

    @property
    def connection(self):return self._connection

    @property
    def pgresult(self):
        actual=self._raw.pgresult
        return ModelResultView(actual,self._model_plan.columns) if actual is not None and self._model_plan else actual

    @property
    def rownumber(self):return self._business_position if self._model_plan else self._raw.rownumber

    def _known(self,query,params,kwargs):
        self._model_plan=None;self._source=None;self._row_events=[];self._business_position=0
        plan=self._session.plans.get(query) if type(query) is str else None
        try:
            if plan is None or kwargs:raise ValueError('Exact plain text/default execution required')
            factory=getattr(self._raw,'row_factory',None)
            if factory is not None and (getattr(factory,'__module__',None),getattr(factory,'__name__',None))!=('psycopg.rows','tuple_row'):
                raise ValueError('Default tuple row decoder required')
            validate_parameters(self._session.scope,plan,params)
            if self._session._quiescing:raise ValueError('Business SQL after source window quiescence')
            self._model_plan=plan
            return plan
        except Exception:
            self._session.gap('model_statement_unproven','Original SQL or parameters are outside the explicit installed model profile.')
            return None

    @_diagnostic_call
    def execute(self,query,params=None,**kwargs):
        if not self._session._enabled:return super().execute(query,params,**kwargs)
        plan=self._known(query,params,kwargs)
        if plan is None:return CapturedV3Cursor.execute(self,query,params,**kwargs)
        with self._connection._operation_lock:
            self._session.activity('execute')
            if self._pending:self._session.gap('model_result_replaced','Original business rows were replaced before delivery completed.')
            self._connection._begin();self._complete=self._result_complete=False;self._mapping=None
            self._statement=self._session.emit('statement',tx=self._connection._tx,sql=query,
                executedSql=plan.executed_sql,mappingId='configured-model/'+plan.operation,
                parameters=self._session.encode(params))
            try:self._raw.execute(plan.executed_sql,params)
            except BaseException as error:
                self._pending=False
                self._session.emit('rows',tx=self._connection._tx,statement=self._statement,rows=[],complete=False,
                    error={'class':type(error).__name__,'sqlstate':getattr(error,'sqlstate',None)})
                self._session.gap('model_statement_failed','Original database error is retained without inventing a model effect.')
                raise
            self._pending=self._raw.description is not None
            try:
                self._source={'kind':'source-batch','statement':self._statement,'tx':self._connection._tx,
                    'operation':plan.operation,'originalSql':query,'executedSql':plan.executed_sql,
                    'parameters':source_parameters(params),'actualPGresult':native_result(self._raw.pgresult),
                    'businessColumns':[{'name':column.name,'typeCode':column.type_code} for column in self.description],
                    'commandTag':self._raw.statusmessage,'rowcount':self._raw.rowcount}
                if not self._pending:raise ValueError('Supported model SQL always has a result set')
                if plan.operation not in ('row-read','list-read') and self._raw.rowcount != 1:
                    self._session.gap('model_zero_or_multiple_write','A zero or multirow write is an unproved condition, never a negative SELECT fact.')
            except Exception:
                self._session.gap('model_native_source_missing','Original bounded PGresult could not be retained.')
        return self

    def _fetch(self,method,*args):
        if self._model_plan is None:return DiagnosticCursor._fetch(self,method,*args)
        with self._connection._operation_lock:
            try:actual=getattr(self._raw,method)(*args)
            except BaseException as error:
                _error(self,method,error);self._session.gap('model_fetch_failed','Original delivery failed; no complete read is invented.');raise
            native=([] if actual is None else [actual]) if method=='fetchone' else actual
            business=[tuple(row[:self._model_plan.columns]) for row in native]
            eof=method=='fetchall' or not native or self._raw.rownumber>=self._raw.rowcount
            self._business_position+=len(business)
            if self._complete:
                if business:self._session.gap('model_rows_after_complete','Unexpected result rows followed the original completion boundary.')
                return (business[0] if business else None) if method=='fetchone' else business
            try:
                event=self._session.emit('rows',tx=self._connection._tx,statement=self._statement,
                    rows=self._session.encode(business),columns=[{'name':c.name,'typeCode':c.type_code} for c in self.description],complete=eof)
                self._row_events.append(event)
                if eof and self._source is not None:
                    append_source(self._session.sink,{**self._source,'businessRowsEvents':list(self._row_events),
                        'deliveredRows':self._business_position,'resultComplete':True})
                    self._source=None
            except Exception:self._session.gap('model_delivery_source_missing','Actual business delivery could not be bound to its original source.')
            self._pending=not eof;self._complete=self._result_complete=eof
            return (business[0] if business else None) if method=='fetchone' else business

    def executemany(self,*args,**kwargs):
        self._model_plan=None
        self._session.gap('model_batch_unproven','Batch execution stays raw diagnostic evidence.')
        return super().executemany(*args,**kwargs)


class ModelConnection(DiagnosticConnection):
    def cursor(self,*args,**kwargs):
        if args or kwargs:return super().cursor(*args,**kwargs)
        raw=self._raw.cursor()
        if not self._session._enabled:return raw
        if len(self._session._cursors)>=self._session._max_cursors:
            self._session.gap('cursor_budget','Cursor runs without model observation.');return raw
        cursor=ModelCursor(self,raw);self._cursors.add(cursor);self._session._cursors.add(cursor)
        return cursor


class ModelProfileCapture(Instrumentation):
    def __init__(self,path,scope,sink,installation,**options):
        self.scope,self.sink,self.installation=scope,sink,installation
        self.plans={plan.sql:plan for plan in plans(scope)}
        self._quiescing=self._profile_finalized=self._factory_attached=False
        super().__init__(path,**options)
        self.note('model-window-open',profile=PROFILE,installationNonce=installation['nonce'],
            initialSourceSeq=installation['sourceSeq'])

    def psycopg_factory(self,factory,*,asynchronous=False):
        if asynchronous or self._factory_attached or not callable(factory):
            raise CoverageRequired('One startup synchronous local factory per source window')
        self._factory_attached=True;self.note('model-factory-attached',asynchronous=False)
        def connect(*args,**kwargs):
            self.activity('connect')
            if self._quiescing:raise CoverageRequired('The installed model source window is quiescing')
            raw=factory(*args,**kwargs)
            if len(self._connections)>=self._max_connections:
                self.gap('connection_budget','Connection runs without configured model observation.')
                return raw
            if getattr(raw,'autocommit',True):
                self.gap('model_autocommit_unproven','Autocommit business connections lack an observed atomic transaction boundary.')
            wrapped=ModelConnection(self,raw)
            self._connections.add(wrapped);self.note('connect',connection=wrapped._identity,asynchronous=False)
            return wrapped
        return connect

    def finalize(self,control):
        if self._closed or self._profile_finalized:raise CoverageRequired('One finalization per installed source window')
        if type(control) is not ControlConnection or control.sink is not self.sink:raise CoverageRequired('Original source control connection required')
        with self._lock:
            self._quiescing=True
            if not self._factory_attached or any(c._tx is not None or not c._raw.closed for c in self._connections):
                self.gap('model_window_active','Stop workers and close all model business connections first.')
                raise CoverageRequired('Model source window still has live business connections')
            self.note('model-window-quiesced',profile=PROFILE,installationNonce=self.installation['nonce'])
        final=_window(control,self.scope,'final')
        seq=append_source(self.sink,{'kind':'final-effect-ledger','profile':PROFILE,'nonce':self.installation['nonce'],'window':final})
        self.note('model-window-close',profile=PROFILE,installationNonce=self.installation['nonce'],finalSourceSeq=seq)
        storage=self.sink.close()
        if not storage['storageSealed']:raise CoverageRequired('Original model source storage is incomplete')
        self._profile_finalized=True
        return self.close()

    def close(self,*,source_closed=False):
        if not self._closed and not self._profile_finalized:
            self.gap('model_window_unclosed','No original locked final source window was observed.')
            try:self.sink.close()
            except Exception:self.gap('model_source_storage_failed','Original source journal did not seal.')
        return super().close(source_closed=False)

    def export_profile(self,destination):
        if not self._closed:raise CoverageRequired('Close original diagnostic before packaging')
        verify_grouped_source(self.sink.path)
        trace_path=self.output/'trace.json'
        if not trace_path.exists():self.export_diagnostic(trace_path)
        trace=_bounded(trace_path,8*1024*1024)
        if self._last_exported_trace!=(trace_path.resolve(),hashlib.sha256(trace.encode()).hexdigest()):
            raise CoverageRequired('Original diagnostic bytes changed')
        package={'format':FORMAT,'profile':PROFILE,'traceText':trace,
            'sourceJournalText':_bounded(self.sink.path,16*1024*1024),
            'lifecycleText':_bounded(self.output/'lifecycle.jsonl',8*1024*1024),
            'journalIndexText':_bounded(self.journal.path/'journal-index.json',2*1024*1024)}
        raw=(json.dumps(package,ensure_ascii=False,separators=(',',':'))+'\n').encode()
        with Path(destination).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        return {'format':FORMAT,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'analysisCoverageAccepted':False,'reason':'raw producer only; independent model projection required'}


def install_model_profile(setup,scope,output,*,initial=(),**options):
    """Explicit fresh-schema installation; diagnostics never call this migration."""
    if type(scope) is not ModelScope:raise CoverageRequired('Explicit immutable ModelScope required')
    from psycopg.types.json import Jsonb
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    sink=GroupedSourceSink(output/'sources.jsonl');control=ControlConnection(setup,sink)
    start=len(control.query_sequences);statements=ddl(scope)
    try:
        control.execute('BEGIN')
        for sql in statements[:-2]:control.execute(sql)
        if scope.model=='append-list-v1':
            if initial:raise CoverageRequired('First list profile starts with empty installed lists')
            for key in scope.keys:control.execute('INSERT INTO '+scope.target+' VALUES(%s,%s::jsonb)',(key,'[]'))
        else:
            seen=set()
            for values in initial:
                validate_parameters(scope,plans(scope)[1],values)
                key=values[0]
                if key in seen:raise CoverageRequired('Duplicate initial row')
                seen.add(key)
                control.execute('INSERT INTO '+scope.target+' VALUES(%s,%s,%s,%s,gen_random_uuid())',tuple(values))
            for key in scope.keys:
                control.execute('INSERT INTO '+scope.owned('state')+' SELECT %s,version,true FROM '+scope.target+' WHERE id=%s',(key,key))
                control.execute('INSERT INTO '+scope.owned('state')+' VALUES(%s,NULL,false) ON CONFLICT DO NOTHING',(key,))
        for sql in statements[-2:]:control.execute(sql)
        control.execute('COMMIT')
        install_queries=control.references_since(start)
        window=_window(control,scope,'initial')
        installation={'kind':'installation','profile':PROFILE,'nonce':uuid.uuid4().hex,
            'config':scope.config(),'installationQueries':install_queries,'window':window}
        seq=append_source(sink,installation);installation={**installation,'sourceSeq':seq}
        return ModelProfileCapture(output/'capture',scope,sink,installation,**options),control
    except BaseException:
        try:control.execute('ROLLBACK')
        except Exception:pass
        try:sink.close()
        except Exception:pass
        raise
