"""Instance-local raw SQL/result delivery observation; never grants source facts.

No SQL rewrite, result consumption, DDL, catalogue query or late provenance read.
The optional recognizer is only a candidate producer. MoonBit verifies separately.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import threading
import uuid
import weakref
from dataclasses import dataclass
from .configured_sql import ConfiguredSQLParser, SQLCaptureConfig
from .instrumentation import (Instrumentation, DiagnosticConnection,
    DiagnosticAsyncConnection, DiagnosticCursor, DiagnosticAsyncCursor)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True, slots=True)
class StoredColumnObservation:
    """Identify an original projected column, NOT an installation/source proof."""
    schema: str
    table: str
    column: str


class ConfiguredInstrumentation(Instrumentation):
    def __init__(self, path, config: SQLCaptureConfig, *, stored_columns=(), **options):
        if type(config) is not SQLCaptureConfig: raise ValueError('Immutable SQLCaptureConfig required')
        if type(stored_columns) is not tuple or any(type(item) is not StoredColumnObservation for item in stored_columns):
            raise ValueError('Stored-column declarations must be an immutable tuple')
        available={(table.schema,table.table,column.name) for table in config.tables for column in table.columns}
        if any((item.schema,item.table,item.column) not in available for item in stored_columns):
            raise ValueError('Stored-column declaration is not in the independent configuration')
        if len(set(stored_columns)) != len(stored_columns): raise ValueError('Duplicate stored-column declaration')
        self.config, self.stored_columns = config, stored_columns
        self.parser=ConfiguredSQLParser(config)
        self._configured_registry={}
        super().__init__(path, **options)
        self.gap('configured_source_window_unproven', 'No installation, catalogue or complete writer-window proof is granted by configuration.')

    def _wrap(self, raw, *, asynchronous):
        if not self._enabled: return raw
        with self._lock:
            if isinstance(raw,(DiagnosticConnection,DiagnosticAsyncConnection)):
                if raw._session is not self: self.gap('foreign_observer','Connection belongs to another observer.')
                return raw
            key=id(raw)
            entry=self._configured_registry.get(key)
            existing=entry[1]() if entry and entry[0]() is raw else None
            if existing is not None:
                if isinstance(existing,ConfiguredAsyncConnection) != asynchronous:
                    self.gap('connection_mode_conflict','Connection reused in a different sync/async mode.')
                    return raw
                return existing
            owner_ref=weakref.ref(self)
            def remove(reference):
                owner=owner_ref()
                if owner is not None:
                    with owner._lock:
                        current=owner._configured_registry.get(key)
                        if current and any(item is reference for item in current):owner._configured_registry.pop(key,None)
            try:raw_ref=weakref.ref(raw,remove)
            except TypeError:
                self.gap('connection_identity_unproven','Non-weak-referenceable connection is returned unchanged.')
                return raw
            if len(self._connections)>=self._max_connections:
                self.gap('connection_budget','Connection returned without observation.');return raw
            cls=ConfiguredAsyncConnection if asynchronous else ConfiguredConnection
            wrapped=cls(self,raw)
            self._configured_registry[key]=(raw_ref,weakref.ref(wrapped,remove))
            self._connections.add(wrapped)
            self.note('connect',connection=wrapped._identity,asynchronous=asynchronous)
            return wrapped

    def frame(self, kind, payload):
        """Small bounded text avoids raw-value coercion and retains exact int64 JSON."""
        try:
            text=_canonical(payload)
            if len(text.encode('utf8'))>60*1024: raise ValueError('frame limit')
            with self.lifecycle.lock:
                before=self.lifecycle.count
                self.note(kind,frameText=text)
                return self.lifecycle.count if self.lifecycle.count==before+1 and not self.lifecycle.failed else None
        except Exception:
            self.gap('configured_observation_missing','An observation exceeded the bounded sink or could not be encoded.')
            return None


class ConfiguredConnection(DiagnosticConnection):
    def cursor(self,*args,**kwargs):
        raw=self._raw.cursor(*args,**kwargs)
        return _cursor(self,raw,args,kwargs,False)


class ConfiguredAsyncConnection(DiagnosticAsyncConnection):
    def cursor(self,*args,**kwargs):
        raw=self._raw.cursor(*args,**kwargs)
        return _cursor(self,raw,args,kwargs,True)


def _cursor(connection,raw,args,kwargs,asynchronous):
    session=connection._session
    if not session._enabled:return raw
    if len(session._cursors)>=session._max_cursors:
        session.gap('cursor_budget','Cursor returned without observation.');return raw
    cls=ConfiguredAsyncCursor if asynchronous else ConfiguredCursor
    cursor=cls(connection,raw)
    cursor._configured_mode_supported=not args and not any(kwargs.get(name) for name in ('name','row_factory','withhold','binary','scrollable'))
    if not cursor._configured_mode_supported:
        session.gap('configured_cursor_mode_unsupported','Non-default cursor mode has no result verification claim.')
    connection._cursors.add(cursor);session._cursors.add(cursor)
    return cursor


class _ConfiguredState:
    def _configured_init(self):
        self._configured_native=None
        self._configured_native_object=None
        self._configured_position=0
        self._configured_done=False
        self._configured_method='unobserved'
        self._configured_mode_supported=True

    def _configured_clear(self, reason):
        if self._configured_native and not self._configured_done:
            self._session.gap('configured_result_incomplete',reason)
            self._session.frame('configured-result-incomplete',{'resultId':self._configured_native['resultId'],'reason':reason})
        self._configured_native=None;self._configured_native_object=None;self._configured_position=0;self._configured_done=False

    def _configured_prepare(self, query, params):
        self._configured_clear('Result replaced before observed exhaustion.')
        if not self._session._enabled or not self._configured_mode_supported:return None
        try:
            if type(query) is not str:raise ValueError('Only original immutable SQL strings are in this grammar')
            plan=self._session.parser.recognize(query)
            bound=plan.bind(params)
            bindings=[{'reference':reference.to_dict(),'value':{'type':reference.type,'value':str(value) if reference.type=='int64' else value}} for reference,value in bound]
            candidate={'format':'moontxnwitness-sql-binding-candidate/v1','descriptor':plan.to_dict(),'bindings':bindings,
                'configSha256':self._session.config.sha256,'sqlSha256':hashlib.sha256(query.encode('utf8')).hexdigest(),
                'parametersSha256':hashlib.sha256(_canonical(params).encode('utf8')).hexdigest()}
            return {'sql':query,'parameters':params,'candidate':candidate}
        except Exception as error:
            self._session.gap('configured_sql_unrecognized','Original execution continues unchanged; recognition failed: '+type(error).__name__)
            return None

    def _configured_executed(self, prepared):
        if prepared is None:return
        try:
            record={'format':'moontxnwitness-configured-execution/v1','connection':self._connection._identity,
                'cursor':self._identity,'tx':self._connection._tx,'statementSeq':self._statement,**prepared,
                'sourceFactsProduced':False}
            statement_note=self._session.frame('configured-execution',record)
            if statement_note is None:raise ValueError('statement not retained')
            result=self._raw.pgresult
            # libpq inspection accesses the immutable completed native buffer, never fetches.
            if result is None or int(result.status)!=2:raise ValueError('No ordinary TUPLES_OK result')
            columns,rows=int(result.nfields),int(result.ntuples)
            if columns<1 or columns>128 or rows<0 or rows>256 or rows*columns>2048:raise ValueError('native dimensions')
            fields=[]
            for index in range(columns):
                name=result.fname(index)
                if type(name) is not bytes:raise ValueError('native field name')
                fields.append({'name':name.decode('utf8'),'oid':int(result.ftype(index)),
                    'format':int(result.fformat(index)),'typmod':int(result.fmod(index)),
                    'tableOid':int(result.ftable(index)),'tableColumn':int(result.ftablecol(index))})
            raw_rows=[];size=0
            for row in range(rows):
                cells=[]
                for column in range(columns):
                    cell=result.get_value(row,column)
                    if cell is not None and type(cell) is not bytes:raise ValueError('native cell')
                    size+=len(cell) if cell is not None else 0
                    if size>32*1024:raise ValueError('native byte budget')
                    cells.append(None if cell is None else base64.b64encode(cell).decode('ascii'))
                raw_rows.append(cells)
            table=prepared['candidate']['descriptor']['table']
            declarations=[item.column for item in self._session.stored_columns if item.schema==table['schema'] and item.table==table['table']]
            frame={'format':'moontxnwitness-native-result/v1','resultId':'result-'+uuid.uuid4().hex,
                'connection':self._connection._identity,'cursor':self._identity,'tx':self._connection._tx,
                'statementSeq':self._statement,'executionNoteSeq':statement_note,'sqlSha256':prepared['candidate']['sqlSha256'],
                'parametersSha256':prepared['candidate']['parametersSha256'],'status':2,'fields':fields,'rows':raw_rows,
                'storedColumnDeclarations':declarations,'sourceFactsProduced':False}
            native_note=self._session.frame('configured-native-result',frame)
            if native_note is None:raise ValueError('native not retained')
            # No full result or supplied parameters retained after the bounded note is written.
            self._configured_native={key:frame[key] for key in ('resultId','statementSeq','connection','cursor','tx')}
            self._configured_native['nativeNoteSeq']=native_note
            self._configured_native_object=result
            self._session.gap('read_version_unproven','Returned stored columns are observations only; installation/catalogue/writer-window proof is absent.')
        except Exception:
            self._session.gap('configured_native_result_unproven','No independent native-result claim is available for this statement.')

    def _configured_rows(self, rows, complete):
        native=self._configured_native
        if native is None:return
        try:
            if self._raw.pgresult is not self._configured_native_object:raise ValueError('native result replaced outside wrapper')
            if type(rows) not in (list,tuple):raise ValueError('row collection')
            typed=[]
            for row in rows:
                if type(row) not in (list,tuple):raise ValueError('custom row factory')
                values=[]
                for value in row:
                    if type(value) is bool:kind='bool'
                    elif type(value) is int and -(2**63)<=value<2**63:kind='int64'
                    elif type(value) is str:kind='text'
                    elif value is None:kind='null'
                    else:raise ValueError('custom scalar decoder')
                    values.append({'type':kind,'value':str(value) if kind=='int64' else value})
                typed.append(values)
            note=self._session.frame('configured-delivery',{'format':'moontxnwitness-actual-delivery/v1',**native,
                'method':self._configured_method,'start':self._configured_position,'rows':typed,'complete':bool(complete),
                'sourceFactsProduced':False})
            if note is None:raise ValueError('delivery not retained')
            self._configured_position+=len(rows)
            self._configured_done=bool(complete)
        except Exception:
            self._session.gap('configured_delivery_unproven','Actual delivered shape could not be retained in the bounded default-scalar contract.')
            self._configured_native=None


class ConfiguredCursor(_ConfiguredState,DiagnosticCursor):
    def __init__(self,connection,raw):
        super().__init__(connection,raw);self._configured_init();self._configured_lock=threading.RLock()

    def execute(self,query,params=None,**kwargs):
        with self._configured_lock:
            prepared=self._configured_prepare(query,params)
            result=super().execute(query,params,**kwargs)
            self._configured_executed(prepared)
            return result

    def executemany(self,*args,**kwargs):
        with self._configured_lock:
            self._configured_clear('Batch execution has no generic single-statement mapping.')
            return super().executemany(*args,**kwargs)

    def _rows(self,rows,complete):
        self._configured_rows(rows,complete)
        return super()._rows(rows,complete)

    def _fetch(self,method,*args):
        with self._configured_lock:
            self._configured_method=method
            return super()._fetch(method,*args)

    def close(self):
        with self._configured_lock:
            self._configured_clear('Cursor closed before observed exhaustion.')
            return super().close()


class ConfiguredAsyncCursor(_ConfiguredState,DiagnosticAsyncCursor):
    def __init__(self,connection,raw):
        super().__init__(connection,raw);self._configured_init();self._configured_lock=asyncio.Lock()

    async def execute(self,query,params=None,**kwargs):
        async with self._configured_lock:
            prepared=self._configured_prepare(query,params)
            result=await super().execute(query,params,**kwargs)
            self._configured_executed(prepared)
            return result

    async def executemany(self,*args,**kwargs):
        async with self._configured_lock:
            self._configured_clear('Batch execution has no generic single-statement mapping.')
            return await super().executemany(*args,**kwargs)

    def _rows(self,rows,complete):
        if not self._adapter_delivery:self._configured_rows(rows,complete)
        return super()._rows(rows,complete)

    def delivered(self,rows,complete):
        previous=self._configured_method;self._configured_method='adapter-delivered'
        try:return super().delivered(rows,complete)
        finally:self._configured_method=previous

    async def _fetch(self,method,*args):
        async with self._configured_lock:
            self._configured_method=method
            return await super()._fetch(method,*args)

    async def close(self):
        async with self._configured_lock:
            self._configured_clear('Cursor closed before observed exhaustion.')
            return await super().close()

    def _close(self):
        self._configured_clear('Adapter closed before observed exhaustion.')
        return super()._close()


def instrument_configured_psycopg(factory,path,config,*,asynchronous=False,**options):
    """Return observer and local factory; never replace the module/global driver."""
    if not callable(factory) or type(asynchronous) is not bool:raise ValueError('Local callable and explicit async boolean required')
    observer=ConfiguredInstrumentation(path,config,**options)
    return observer,observer.psycopg_factory(factory,asynchronous=asynchronous)


def instrument_configured_engine(engine,path,config,**options):
    """Attach once to an unused supported engine; inherited late-attach gaps remain."""
    observer=ConfiguredInstrumentation(path,config,**options)
    try:return observer.attach_engine(engine)
    except BaseException:
        observer.close()
        raise
