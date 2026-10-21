"""Small journal-backed ordinary-table slice, never ready generic SQL proof."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"integrations/python"))
sys.path.insert(0,str(ROOT/"experiments/provenance"))
from moontxnwitness_capture.capture_v3 import (CaptureV3Session, CapturedV3Connection,
    CapturedV3Cursor, SQLMapping)
from moontxnwitness_capture.capture import _status
from moontxnwitness_capture.journal_v3 import JournalError
from capture_profile import ColumnPointProfile, _check_business_effects, verify_installation
from prototype import Installation, Observation, ProvenanceError, ddl, identifier, idle_setup, table_catalog_sql
from source_log import SourceLog, SourceLogReader

PROFILE="plain-existing-column-point-v3-draft/1"
PENDING_RESULT_LIMIT=512


def token(value):
    if type(value) is not str or str(uuid.UUID(value))!=value:raise ValueError("Canonical UUID token required")
    return value


class PlainJournalCapture(CaptureV3Session):
    core_proof_implemented=False
    formal_eligible=False

    def __init__(self,path,*,schema,table="items",keys,exclusive_writers=False,journal_options=None):
        keys=tuple(keys)
        if (not 1<=len(keys)<=64 or len(set(keys))!=len(keys)
                or any(type(k) is not str or not k or len(k.encode("utf-8"))>512 for k in keys)):
            raise ValueError("Declare1..64 bounded distinct existing text keys")
        self.profile=ColumnPointProfile(schema,table)
        self.keys=frozenset(keys);self.installation=None;self._ledger_complete=False
        self._pending_results=set();self.path=Path(path);self.path.mkdir(parents=False,exist_ok=False)
        self.sources=SourceLog(self.path/"sources")
        n=self.profile.names;v=identifier(n.version_column)
        self.returning_sql=self.profile.write_sql+" RETURNING "+identifier(n.value_column)
        mappings=(
            SQLMapping(self.profile.read_sql,PROFILE+"/read",self.profile.observed_read_sql,1,self._read_rows,self._read_parameters),
            SQLMapping(self.profile.write_sql,PROFILE+"/command-update",self.profile.write_sql+" RETURNING OLD."+v+"::text,NEW."+v+"::text",1,None,self._write_parameters),
            SQLMapping(self.returning_sql,PROFILE+"/returning-update",self.returning_sql+",OLD."+v+"::text,NEW."+v+"::text",1,self._write_rows,self._write_parameters))
        try:super().__init__(self.path/"journal",mappings=mappings,exclusive_writers=exclusive_writers,journal_options=journal_options)
        except BaseException:
            self.sources.failed=True
            try:self.sources.close()
            except Exception:pass
            raise

    def _read_parameters(self,params):
        if type(params) not in (tuple,list) or len(params)!=1 or params[0] not in self.keys:
            raise ValueError("One declared key parameter required")
        return {"key":params[0]}

    def _write_parameters(self,params):
        if type(params) not in (tuple,list) or len(params)!=2 or type(params[0]) is not int or params[1] not in self.keys:
            raise ValueError("Integer value and one declared key required")
        return {"key":params[1]}

    def _read_rows(self,cursor,rows,exhausted):
        if len(rows)>1:raise ValueError("Point SELECT returned multiple rows")
        for offset,row in enumerate(rows):
            if type(row) is not tuple or len(row)!=2 or type(row[0]) is not int:raise ValueError("Point read row shape changed")
            cursor.fact("read",key=cursor._bound["key"],version=token(row[1]),
                evidence={"serverRow":cursor._batch_start+offset})
        if exhausted and cursor._server_rows_seen==0:self.gap("existing_row_missing","An existing-key SELECT returned no row; no negative source was invented.")

    def _write_rows(self,cursor,rows,exhausted):
        if len(rows)>1:raise ValueError("Point UPDATE returned multiple rows")
        for offset,row in enumerate(rows):
            if type(row) is not tuple or len(row)!=3 or type(row[0]) is not int:raise ValueError("Returning point row shape changed")
            cursor.fact("write",key=cursor._bound["key"],predecessor=token(row[1]),version=token(row[2]),
                evidence={"serverRow":cursor._batch_start+offset})
        if exhausted and cursor._server_rows_seen==0:self.gap("existing_row_missing","An existing-key UPDATE affected no row.")

    def initialize(self,setup):
        if self._initialized or self._seq or self.installation is not None:raise ProvenanceError("Initialize once before business activity")
        idle_setup(setup)
        import psycopg
        from psycopg.rows import tuple_row
        if psycopg.__version__!="3.3.6" or setup.row_factory is not tuple_row or not 180000<=setup.info.server_version<190000:
            raise ProvenanceError("Require PostgreSQL18, psycopg3.3.6 and standard tuple rows")
        n=self.profile.names;window=[]
        try:
            window.append({"sql":"BEGIN ISOLATION LEVEL READ COMMITTED","tag":setup.execute("BEGIN ISOLATION LEVEL READ COMMITTED").statusmessage})
            lock="LOCK TABLE "+n.business+" IN ACCESS EXCLUSIVE MODE"
            window.append({"sql":lock,"tag":setup.execute(lock).statusmessage})
            catalog=setup.execute(table_catalog_sql(),(n.key_column,n.schema,n.table)).fetchone()
            if catalog is None or tuple(catalog[1:])!=("r",False,False,True):raise ProvenanceError("Unsupported ordinary table identity")
            _check_business_effects(setup,catalog[0])
            columns=setup.execute("SELECT attname,pg_catalog.format_type(atttypid,atttypmod),attnotnull,attgenerated,attidentity FROM pg_catalog.pg_attribute WHERE attrelid=%s AND attnum>0 AND NOT attisdropped ORDER BY attnum",(catalog[0],)).fetchall()
            if columns!=[(n.key_column,"text",True,"",""),(n.value_column,"integer",True,"","")]:raise ProvenanceError("Require exact text/integer NOT NULL point table")
            indexes=setup.execute("SELECT am.amname,ns.nspname,oc.opcname,i.indisprimary,i.indisunique FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid JOIN pg_catalog.pg_am am ON am.oid=c.relam CROSS JOIN LATERAL pg_catalog.unnest(i.indclass::oid[]) x(oid) JOIN pg_catalog.pg_opclass oc ON oc.oid=x.oid JOIN pg_catalog.pg_namespace ns ON ns.oid=oc.opcnamespace WHERE i.indrelid=%s",(catalog[0],)).fetchall()
            if indexes!=[("btree","pg_catalog","text_ops",True,True)]:raise ProvenanceError("Only a native text primary index is supported")
            constraints=setup.execute("SELECT contype,conkey::smallint[],condeferrable,condeferred,convalidated,conenforced FROM pg_catalog.pg_constraint WHERE conrelid=%s",(catalog[0],)).fetchall()
            if (len(constraints)!=3 or {(r[0],tuple(r[1])) for r in constraints}!={("p",(1,)),("n",(1,)),("n",(2,))}
                    or any(tuple(r[2:])!=(False,False,True,True) for r in constraints)):
                raise ProvenanceError("Unexpected business constraints")
            existing=setup.execute("SELECT "+identifier(n.key_column)+" FROM "+n.business+" LIMIT 65").fetchall()
            if len(existing)!=len(self.keys) or {r[0] for r in existing}!=self.keys:raise ProvenanceError("Known key set must exactly match locked rows")
            installation=Installation(n,str(uuid.uuid4()),catalog[0],{})
            for sql in ddl(n):window.append({"sql":sql,"tag":setup.execute(sql).statusmessage})
            setup.execute("INSERT INTO "+n.object("installation")+" VALUES(%s,%s,%s)",(installation.nonce,"column",installation.table_oid))
            verify_installation(setup,installation)
            rows=setup.execute("SELECT "+identifier(n.key_column)+","+identifier(n.value_column)+","+identifier(n.version_column)+"::text FROM "+n.business+" ORDER BY "+identifier(n.key_column)+" LIMIT 65").fetchall()
            if len(rows)!=len(self.keys) or {r[0] for r in rows}!=self.keys:raise ProvenanceError("Incomplete locked token snapshot")
            for key,value,version in rows:
                if type(value) is not int:raise ProvenanceError("Initial business value is not integer")
                token(version)
            window.append({"sql":"COMMIT","tag":setup.execute("COMMIT").statusmessage})
            self.installation=installation
            self.sources.append({"kind":"installation","profile":PROFILE,"coreProofImplemented":False,
                "tableOid":catalog[0],"nonce":installation.nonce,"serverVersion":setup.info.server_version,
                "businessCatalog":self.encode([catalog,columns,indexes,constraints]),"window":self.encode(window),"initialRows":self.encode(rows)})
            self.publish_snapshot({key:version for key,_,version in rows},consistent=True)
        except BaseException:
            self.gap("initialization_failed","The draft locked installation/snapshot did not finish; wrapping remains disabled.")
            try:setup.execute("ROLLBACK")
            except Exception:self.gap("initialization_rollback_unknown","Setup rollback acknowledgement unavailable.")
            raise

    def wrap(self,raw,*,role=None):
        if not self._initialized or self._closed:raise JournalError("Initialize first and never reuse a closed observer")
        with self._lock:
            if any(c._raw is raw for c in self._connections):raise JournalError("Wrap a business connection exactly once")
            if len(self._connections)>=self._max_connections:
                self.gap("connection_budget","Unwrapped connection exceeded bounded draft registry");return raw
            self._ledger_complete=False
            result=PlainConnection(self,raw);self._connections.add(result);return result

    def quiescence_report(self):
        with self._lock:
            reasons=[]
            if not self._initialized or self.installation is None:reasons.append("initialization-unproven")
            if self._closed:reasons.append("observer-already-closed")
            if self._pending_results:reasons.append("undelivered-result-identities")
            if any(c._tx or c._commit_requested or (not c._raw.closed and _status(c._raw)!=0) for c in self._connections):reasons.append("active-or-unresolved-transaction")
            if any(not c._raw.closed for c in self._connections):reasons.append("business-connections-not-closed")
            if self.gaps:reasons.append("prior-coverage-gap")
            return {"eligible":not reasons,"reasons":reasons,"handoffImplemented":False,"coreProofImplemented":False}

    def stream_final_ledger(self,setup,*,max_rows=1024):
        if type(max_rows) is not int or not 1<=max_rows<=1024:raise ValueError("Ledger draft row bound")
        if self.installation is None or self._closed:raise ProvenanceError("Initialize and finalize before close")
        if not self.quiescence_report()["eligible"]:raise ProvenanceError("Stop and close all business connections without gaps first")
        idle_setup(setup);n=self.profile.names;count=0;query="SELECT token::text,key,action,present,predecessor::text,old_value,new_value FROM "+n.object("audit")+" ORDER BY token"
        try:
            setup.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            setup.execute("LOCK TABLE "+n.business+" IN ACCESS EXCLUSIVE MODE")
            verify_installation(setup,self.installation)
            # An actual server cursor bounds the driver's result buffer; a
            # normal client PGresult plus fetchmany would not prove that.
            with setup.cursor(name="mtw_plain_ledger_"+uuid.uuid4().hex) as cursor:
                cursor.execute(query)
                while rows:=cursor.fetchmany(32):
                    for row in rows:
                        count+=1
                        if count>max_rows:raise ProvenanceError("Actual ledger exceeds bounded draft window")
                        self.sources.append({"kind":"ledger-row","ordinal":count,"query":query,"row":self.encode(row)})
            acknowledgement=setup.execute("COMMIT").statusmessage
            self.sources.append({"kind":"ledger-end","rows":count,"commandTag":acknowledgement,"complete":True})
            self._ledger_complete=True;return {"rows":count,"complete":True,"coreProofImplemented":False}
        except BaseException:
            self.gap("ledger_incomplete","Final ledger query, provenance or row/byte budget was incomplete; no truncation is declared complete.")
            try:setup.execute("ROLLBACK")
            except Exception:self.gap("ledger_rollback_unknown","Readonly finalization rollback not acknowledged")
            raise

    def close(self,*,source_closed=False):
        if not self._closed:
            if self._pending_results:self.gap("unconsumed_result","Undelivered cursor identity remains, including discarded wrappers")
            if not self._ledger_complete:self.gap("ledger_not_finalized","No complete bounded final ledger was established")
            try:
                self.sources.close()
                if self.sources.failed or self.sources.invalidated:
                    self.gap("source_log_failed","Separate source evidence is failed or invalidated")
            except Exception:self.gap("source_log_failed","Bounded separate source log did not synchronize")
        return super().close(source_closed=source_closed)


class PlainConnection(CapturedV3Connection):
    def _begin(self):
        self._session._ledger_complete=False
        return super()._begin()

    def cursor(self,*args,**kwargs):
        raw=self._raw.cursor(*args,**kwargs)
        if len(self._session._cursors)>=self._session._max_cursors:
            self._session.gap("cursor_budget","Unwrapped cursor exceeded bounded registry");return raw
        unsupported=bool(args or kwargs.get("name") or kwargs.get("withhold") or kwargs.get("row_factory"))
        if unsupported:self._session.gap("cursor_mode_unsupported","Only unnamed tuple business cursors are in the draft")
        result=PlainCursor(self,raw,unsupported=unsupported)
        self._cursors.add(result);self._session._cursors.add(result);return result


class PlainCursor(CapturedV3Cursor):
    def __init__(self,connection,raw,*,unsupported=False):
        super().__init__(connection,raw);self._command=False;self._unsupported=unsupported

    @property
    def description(self):return None if self._command else super().description

    @property
    def rownumber(self):return None if self._command else self._raw.rownumber

    def _track(self):
        with self._session._lock:
            pending=self._session._pending_results
            if self._pending:
                if self._identity not in pending and len(pending)>=PENDING_RESULT_LIMIT:
                    self._session.gap("pending_result_budget","At most512 retained unread identities are supported; later unread references make this window incomplete")
                else:pending.add(self._identity)
            else:self._session._pending_results.discard(self._identity)

    def _rows(self,rows,exhausted):
        super()._rows(rows,exhausted);self._track()

    def _exhausted(self,rows,eof=False):
        count,position=getattr(self._raw,"rowcount",-1),getattr(self._raw,"rownumber",None)
        if type(count) is int and count>=0 and type(position) is int:return position>=count
        return bool(eof)

    def _passthrough(self,query,params,kwargs,sql):
        self._session.gap("point_profile_unsupported","Original SQL ran without source rewrite because its parameters/factory/scope are unsupported")
        self._session.activity("execute");self._connection._begin()
        if self._pending:self._session.gap("result_replaced","An undelivered result was replaced")
        self._mapping=None;self._bound={};self._result_complete=False;self._server_rows_seen=0;self._command=False
        fields={"tx":self._connection._tx,"sql":sql}
        try:fields["parameters"]=self._session.encode(params)
        except Exception:self._session.gap("parameter_encoding_failed","Parameters exceeded raw evidence budget; original business query still runs")
        self._statement=self._session.emit("statement",**fields)
        try:self._raw.execute(query,params,**kwargs)
        except BaseException as error:
            self._pending=False;self._track()
            self._session.emit("rows",tx=self._connection._tx,statement=self._statement,rows=[],complete=False,
                error={"class":type(error).__name__,"sqlstate":getattr(error,"sqlstate",None)})
            self._session.gap("statement_failed","Original business exception was preserved");raise
        self._pending=self._raw.description is not None
        if not self._pending:self._rows([],True)
        self._track();return self

    def execute(self,query,params=None,**kwargs):
        with self._connection._operation_lock:
            self._command=False
            try:sql=self._sql(query)
            except Exception:return super().execute(query,params,**kwargs)
            mapping=self._session._mappings.get(sql)
            if mapping is None:
                # The inherited protocol records actual savepoint operations;
                # every non-control unknown statement remains a coverage gap.
                from moontxnwitness_capture.capture_v3 import _control
                if not _control(sql):self._session.gap("unknown_sql","SQL is outside the two fixed point operations")
                result=super().execute(query,params,**kwargs);self._track();return result
            from psycopg.rows import tuple_row
            factory=getattr(self._raw,"row_factory",None)
            valid=not self._unsupported and factory is tuple_row
            try:mapping.bind_parameters(params)
            except Exception:valid=False
            if not valid:return self._passthrough(query,params,kwargs,sql)
            self._command=sql==self._session.profile.write_sql
            result=super().execute(query,params,**kwargs)
            if self._command:
                try:
                    rows=self._raw.fetchmany(2)
                    if len(rows)!=1 or type(rows[0]) is not tuple or len(rows[0])!=2 or self._raw.rowcount!=1:
                        raise ValueError("Missing or multiple internal point update results")
                    old,new=map(token,rows[0]);business_rows=self._session.emit("rows",tx=self._connection._tx,statement=self._statement,rows=[],complete=True)
                    source=self._session.sources.append({"kind":"command-effect","statement":self._statement,"businessRowsEvent":business_rows,
                        "tx":self._connection._tx,"actualSql":mapping.executed_sql,"effectRows":self._session.encode(rows),
                        "businessCommand":{"rowcount":self._raw.rowcount,"statusmessage":self._raw.statusmessage,"description":None,"rownumber":None}})
                    if business_rows is None:raise ValueError("Business command event was not retained")
                    self.fact("write",key=self._bound["key"],predecessor=old,version=new,
                        evidence={"sourceLogSeq":source,"effectRow":0})
                except Exception:self._session.gap("write_source_unavailable","Business update result preserved but internal same-statement source was incomplete")
                self._pending=False;self._result_complete=True;self._bound={}
            self._track();return result

    def _check_fetch(self):
        if self._command:
            self._session.activity("hidden-command-fetch")
            import psycopg
            if self._raw.closed:raise psycopg.InterfaceError("the cursor is closed")
            tag=self._raw.statusmessage
            raise psycopg.ProgrammingError("the last operation didn't produce records"+(" (command status: "+tag+")" if tag else ""))

    def fetchone(self):self._check_fetch();return super().fetchone()
    def fetchmany(self,size=None):self._check_fetch();return super().fetchmany(size)
    def fetchall(self):self._check_fetch();return super().fetchall()

    def close(self):
        try:return super().close()
        finally:self._session._pending_results.discard(self._identity)
