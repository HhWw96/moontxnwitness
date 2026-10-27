"""Original native control SQL for the fixed ORM sourceSchema2 protocol.

Only the explicitly owned installation/finalization connection is consumed.
Business cursors are never passed through this eager control-result recorder.
"""
from __future__ import annotations
import json
import uuid
from ..capture import _status
from ..orm import CoverageRequired

STATES = {0:'IDLE', 1:'ACTIVE', 2:'INTRANS', 3:'INERROR', 4:'UNKNOWN'}


def append_source(sink, record):
    result = sink.append(record)
    if type(result) is int:
        return result
    if not getattr(result, 'accepted', False):
        raise CoverageRequired('Source record was not admitted: '+str(getattr(result, 'gap', None)))
    return result.source_seq


def source_parameters(value):
    """Observe the actual parameter object without changing driver arguments."""
    from psycopg.types.json import Jsonb
    if type(value) is Jsonb:
        if value.dumps is not json.dumps:
            raise CoverageRequired('Owned setup Jsonb must use the explicit stdlib serializer')
        return {'captureType':'psycopg-jsonb','objectDumps':'stdlib-json-dumps','value':value.obj}
    if type(value) in (list, tuple):
        return [source_parameters(item) for item in value]
    if type(value) is dict:
        return {key:source_parameters(item) for key,item in value.items()}
    return value


def native_result(result, *, max_rows=512, max_columns=64, max_bytes=96*1024):
    if result is None or not 0 <= result.nfields <= max_columns or not 0 <= result.ntuples <= max_rows:
        raise CoverageRequired('Original native control result exceeds fixed bounds')
    rows=[]; remaining=max_bytes
    fields=[{'oid':result.ftype(i),'format':result.fformat(i),'typmod':result.fmod(i)}
            for i in range(result.nfields)]
    for i in range(result.ntuples):
        row=[]
        for column in range(result.nfields):
            raw=result.get_value(i,column)
            if raw is not None:
                remaining-=len(raw)
                if remaining < 0:raise CoverageRequired('Control result raw-cell budget exhausted')
            row.append(raw)
        rows.append(row)
    return {'status':int(result.status),'commandTag':result.command_status,
            'commandTuples':result.command_tuples,'nfields':result.nfields,
            'ntuples':result.ntuples,'fields':fields,'rawRows':rows}


class ControlCursor:
    def __init__(self, raw, rows, source_seq):
        self.raw, self.rows, self.control_query_seq = raw, rows, source_seq
        self.position=0
    def fetchone(self):
        if self.position >= len(self.rows):return None
        row=self.rows[self.position];self.position+=1;return row
    def fetchall(self):
        rows=self.rows[self.position:];self.position=len(self.rows);return rows
    def __getattr__(self,name):return getattr(self.raw,name)


class ControlConnection:
    def __init__(self, raw, sink):
        import psycopg
        if psycopg.__version__!='3.3.6' or not isinstance(raw,psycopg.Connection):
            raise CoverageRequired('Native pinned synchronous psycopg setup connection required')
        if not raw.autocommit or _status(raw)!=0:
            raise CoverageRequired('Fresh idle autocommit control connection required')
        self.raw,self.sink=raw,sink
        self.identity='setup-'+uuid.uuid4().hex
        self.query_sequences=[];self._transaction=None;self._counter=0
    def references_since(self,start):return list(self.query_sequences[start:])
    def execute(self,sql,parameters=None):
        if type(sql) is not str or not 0 < len(sql.encode('utf8')) <= 65536:
            raise CoverageRequired('Owned control SQL must be bounded native text')
        before=STATES.get(_status(self.raw),'UNKNOWN')
        if self._transaction is None:
            self._counter+=1;self._transaction=self.identity+'-tx-'+str(self._counter)
        transaction=self._transaction
        try:
            cursor=self.raw.execute(sql,parameters)
        except BaseException as error:
            try:
                append_source(self.sink,{'kind':'source-gap','phase':'control-error','sql':sql,
                    'connection':self.identity,'transaction':transaction,
                    'errorClass':type(error).__name__,'sqlstate':getattr(error,'sqlstate',None)})
            except BaseException:pass
            raise
        after=STATES.get(_status(self.raw),'UNKNOWN')
        original=native_result(cursor.pgresult)
        # This is an owned control query, never a business fetch. The same
        # immutable PGresult is kept alongside the driver's actual decoded rows.
        rows=cursor.fetchall() if cursor.description is not None else []
        columns=None if cursor.description is None else [
            {'name':column.name,'typeCode':column.type_code} for column in cursor.description]
        seq=append_source(self.sink,{'kind':'control-query','connection':self.identity,
            'backendPid':self.raw.info.backend_pid,'transaction':transaction,'sql':sql,
            'parameters':source_parameters(parameters),
            'transactionStatusBefore':before,'transactionStatusAfter':after,
            'result':{'status':int(cursor.pgresult.status),'commandTag':cursor.statusmessage,
                'rowcount':cursor.rowcount,'columns':columns,'rows':rows,'complete':True,
                'actualPGresult':original}})
        self.query_sequences.append(seq)
        if after=='IDLE':self._transaction=None
        return ControlCursor(cursor,rows,seq)
    def __getattr__(self,name):return getattr(self.raw,name)
