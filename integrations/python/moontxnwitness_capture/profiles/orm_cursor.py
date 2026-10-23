"""Fixed base-user same-statement source projection, preserving business rows.

The eight-cell observation protocol is the existing independently checked ORM
sourceSchema2 contract. No source fact is inserted into the raw event journal.
"""
from __future__ import annotations
from ..capture_v3 import CapturedV3Cursor
from .._orm_raw_async import DraftAsyncCursor
from ..instrumentation import (DiagnosticConnection, DiagnosticAsyncConnection,
    DiagnosticCursor, DiagnosticAsyncCursor, _diagnostic_call, _error)
from ..orm import CoverageRequired, FIELDS
from .._orm_policy import (observe_get, observe_command,
    SyncCommandCursorView, AsyncCommandCursorView)
from .._orm_async import SourceResult, ReadResultFacade
from .orm_control import append_source


class ProfileCursorState:
    def _reset_profile(self):
        self._plan=self._command=self._read=self._source_result=None
        self._present_hint=None;self._business_position=0;self._params=None;self._point_key=None
    @property
    def pgresult(self):
        if self._command:return self._command.pgresult
        if self._present_hint is not None:return ReadResultFacade(self._raw.pgresult,self._present_hint)
        return self._raw.pgresult
    @property
    def description(self):
        if self._command:return None
        value=self._raw.description
        return value[:6] if value is not None and self._present_hint is not None else value
    @property
    def rowcount(self):return int(self._present_hint) if self._present_hint is not None else self._raw.rowcount
    @property
    def rownumber(self):
        return None if self._command else self._business_position if self._present_hint is not None else self._raw.rownumber
    @property
    def statusmessage(self):
        return 'SELECT '+str(int(self._present_hint)) if self._present_hint is not None else self._raw.statusmessage
    def _prepare(self,query,params,kwargs):
        self._reset_profile()
        plan=self._session.plans.get(query) if type(query) is str else None
        try:
            if plan is None:raise CoverageRequired('SQL is outside the exact registered profile')
            if kwargs.get('binary') or kwargs.get('returning'):
                raise CoverageRequired('Non-default binary/returning execution is unsupported')
            factory=getattr(self._raw,'row_factory',None)
            if factory is not None and (getattr(factory,'__module__',None),getattr(factory,'__name__',None))!=('psycopg.rows','tuple_row'):
                raise CoverageRequired('Only the original default tuple row adapter is supported')
            if type(params) is not dict:raise CoverageRequired('Pinned named parameters required')
            self._point_key=self._session.scope.key(params[plan.key.pk_bind])
            required=set(FIELDS) if plan.key.operation=='create' else set(plan.key.fields)|{plan.key.pk_bind}
            if set(params)!=required:raise CoverageRequired('Exact original parameter layout required')
            plan=self._session.cache.match(self._session.scope,query,plan.key.operation,plan.key.fields,plan.key.pk_bind)
            self._params=self._session.encode(params)
        except Exception:
            self._session.gap('profile_statement_unproven','Original SQL/parameters run unchanged outside the fixed base-user source profile.')
            return None
        if self._session._quiescing:
            self._session.gap('profile_activity_after_quiesce','Business SQL arrived after the declared stop boundary.')
        self._plan=plan
        return plan
    def _before_known(self,query):
        self._session.activity('execute')
        if self._pending:self._session.gap('profile_result_replaced','A known statement replaced undelivered business rows.')
        self._connection._begin()
        self._result_complete=False;self._complete=False;self._mapping=None
        self._statement=self._session.emit('statement',tx=self._connection._tx,sql=query,
            executedSql=self._plan.observed_sql,mappingId=self._plan.mapping_id,parameters=self._params)
    def _failed_known(self,error):
        self._pending=False
        self._session.emit('rows',tx=self._connection._tx,statement=self._statement,rows=[],complete=False,
            error={'class':type(error).__name__,'sqlstate':getattr(error,'sqlstate',None)})
        self._session.gap('profile_statement_failed','The original database exception is preserved; no source fact is invented.')
    def _after_known(self,command_view):
        self._source_result=SourceResult(self._raw.pgresult)
        self._pending=self._raw.description is not None
        try:
            if self._plan.result_mode=='command':
                self._command=command_view(self._raw)
                self._pending=False;self._complete=self._result_complete=True
                rows_event=self._session.emit('rows',tx=self._connection._tx,statement=self._statement,rows=[],complete=True)
                observed=observe_command(self._session.scope,self._plan,self._source_result)
                self._retain(observed,rows_event)
            else:
                self._present_hint=self._raw.pgresult.ntuples>0 and self._raw.pgresult.get_value(0,0) is not None
                self._read=observe_get(self._session.scope,self._plan,self._source_result,self._point_key)
                self._pending=True
        except Exception as error:
            self._session.gap('profile_source_missing','Missing or invalid same-statement source remains unknown.')
            try:
                append_source(self._session.sink,{'kind':'source-gap','statement':self._statement,
                    'tx':self._connection._tx,'errorClass':type(error).__name__,'operation':self._plan.key.operation,
                    'actualPGresult':self._source_result.snapshot(),'businessCommand':{
                        'tag':self.statusmessage,'rowcount':self.rowcount,
                        'description':None if self.description is None else 'six-business-columns','rownumber':self.rownumber}})
            except Exception:self._session.gap('profile_source_sink_failed','Source gap could not be retained.')
    def _retain(self,observed,rows_event):
        try:
            append_source(self._session.sink,{'kind':'source-batch','statement':self._statement,
                'businessRowsEvent':rows_event,'tx':self._connection._tx,'mappingId':self._plan.mapping_id,
                'operation':self._plan.key.operation,'originalSql':self._plan.original_sql,
                'executedSql':self._plan.observed_sql,'parameters':self._params,
                'businessCommand':{'tag':self.statusmessage,'rowcount':self.rowcount,'rownumber':self.rownumber,
                    'description':None if self.description is None else [
                        {'name':column.name,'typeCode':column.type_code} for column in self.description]},
                'actualPGresult':self._source_result.snapshot(),'observation':observed})
        except Exception:self._session.gap('profile_source_sink_failed','Business result is preserved after source-record failure.')
    def _deliver_business(self,business,complete):
        if not self._session._enabled:
            self._business_position+=len(business)
            self._pending=not complete;self._complete=self._result_complete=complete
            return
        if self._complete:
            if business:self._session.gap('profile_rows_after_complete','Repeated rows after point result completion.')
            return
        self._business_position+=len(business)
        try:
            fields={'tx':self._connection._tx,'statement':self._statement,
                'rows':self._session.encode(business),'complete':complete,
                'columns':[{'name':column.name,'typeCode':column.type_code} for column in self.description]}
            if business and self._read is not None:fields['serverRows']=self._session.encode([self._read.cells])
            rows_event=self._session.emit('rows',**fields)
            observed=self._read.deliver(business,eof=complete) if self._read is not None else None
            if observed is not None:self._retain(observed,rows_event)
        except Exception:self._session.gap('profile_read_delivery_unproven','Actual delivery does not validate the same-statement source.')
        self._pending=not complete;self._complete=self._result_complete=complete
    def _business_result(self,method,result):
        source_rows=([] if result is None else [result]) if method=='fetchone' else result
        business=[tuple(row[:6]) for row in source_rows if row[0] is not None]
        complete=method=='fetchall' or not source_rows or self._raw.rownumber>=self._raw.rowcount
        return business,complete


class ProfileSyncCursor(ProfileCursorState,DiagnosticCursor):
    def __init__(self,connection,raw):super().__init__(connection,raw);self._reset_profile()
    @_diagnostic_call
    def execute(self,query,params=None,**kwargs):
        if not self._session._enabled:
            self._reset_profile()
            return DiagnosticCursor.execute(self,query,params,**kwargs)
        plan=self._prepare(query,params,kwargs)
        if plan is None:return CapturedV3Cursor.execute(self,query,params,**kwargs)
        with self._connection._operation_lock:
            self._before_known(query)
            try:self._raw.execute(plan.observed_sql,params,**kwargs)
            except BaseException as error:self._failed_known(error);raise
            self._after_known(SyncCommandCursorView)
        return self
    def _fetch(self,method,*args):
        if self._command:return getattr(self._command,method)(*args)
        if self._present_hint is None:return DiagnosticCursor._fetch(self,method,*args)
        with self._connection._operation_lock:
            try:result=getattr(self._raw,method)(*args)
            except BaseException as error:
                _error(self,method,error)
                self._session.gap('profile_fetch_failed','Original driver fetch failed; no delivered source is invented.')
                raise
            business,complete=self._business_result(method,result)
            self._deliver_business(business,complete)
            return (business[0] if business else None) if method=='fetchone' else business
    def executemany(self,*args,**kwargs):
        self._reset_profile()
        if self._session._enabled:self._session.gap('profile_batch_unproven','Batch SQL is retained as raw diagnostics only.')
        return super().executemany(*args,**kwargs)


class ProfileAsyncCursor(ProfileCursorState,DiagnosticAsyncCursor):
    def __init__(self,connection,raw):super().__init__(connection,raw);self._reset_profile()
    @_diagnostic_call
    async def execute(self,query,params=None,**kwargs):
        if not self._session._enabled:
            self._reset_profile()
            return await DiagnosticAsyncCursor.execute(self,query,params,**kwargs)
        plan=self._prepare(query,params,kwargs)
        if plan is None:return await DraftAsyncCursor.execute(self,query,params,**kwargs)
        async with self._connection._lock:
            self._before_known(query)
            try:await self._raw.execute(plan.observed_sql,params,**kwargs)
            except BaseException as error:self._failed_known(error);raise
            self._after_known(AsyncCommandCursorView)
        return self
    async def _fetch(self,method,*args):
        if self._command:return await getattr(self._command,method)(*args)
        if self._present_hint is None:return await DiagnosticAsyncCursor._fetch(self,method,*args)
        async with self._connection._lock:
            try:result=await getattr(self._raw,method)(*args)
            except BaseException as error:
                _error(self,method,error)
                self._session.gap('profile_fetch_failed','Original async driver fetch failed; no delivered source is invented.')
                raise
            business,complete=self._business_result(method,result)
            if not self._adapter_delivery:self._deliver_business(business,complete)
            return (business[0] if business else None) if method=='fetchone' else business
    def delivered(self,rows,complete):
        if self._present_hint is None:return super().delivered(rows,complete)
        self._deliver_business(rows,complete)
    async def executemany(self,*args,**kwargs):
        self._reset_profile()
        if self._session._enabled:self._session.gap('profile_batch_unproven','Batch SQL is retained as raw diagnostics only.')
        return await super().executemany(*args,**kwargs)


class ProfileSyncConnection(DiagnosticConnection):
    def cursor(self,*args,**kwargs):
        if args or kwargs:return super().cursor(*args,**kwargs)
        raw=self._raw.cursor()
        if not self._session._enabled:return raw
        if len(self._session._cursors)>=self._session._max_cursors:
            self._session.gap('cursor_budget','Cursor runs without fixed profile observation.');return raw
        cursor=ProfileSyncCursor(self,raw);self._cursors.add(cursor);self._session._cursors.add(cursor)
        return cursor


class ProfileAsyncConnection(DiagnosticAsyncConnection):
    def cursor(self,*args,**kwargs):
        if args or kwargs:return super().cursor(*args,**kwargs)
        raw=self._raw.cursor()
        if not self._session._enabled:return raw
        if len(self._session._cursors)>=self._session._max_cursors:
            self._session.gap('cursor_budget','Async cursor runs without fixed profile observation.');return raw
        cursor=ProfileAsyncCursor(self,raw);self._cursors.add(cursor);self._session._cursors.add(cursor)
        return cursor
