"""Explicit V2 installation components, never source/window/model admission.

Only an opted-in dedicated idle autocommit control connection is used. No
business SQL/cursors, driver imports, source Window or history API exists here.
Physical catalog order is preserved, while ordinary column checks use names.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys

from . import configured_source as _v1
from .configured_source import SourceInstallPolicy, SourceInstallError
from .configured_sql_v2 import SQLCaptureConfigV2, TableConfigV2, _input_value

FORMAT = 'moontxnwitness-configured-source-installation/v2'
CONTRACT = 'postgres18-explicit-point-source-installation-components/v2'
LOG_FORMAT = 'moontxnwitness-source-installation-log/v2'
VERSION_COLUMN = _v1.VERSION_COLUMN
BEFORE_TRIGGER, AFTER_TRIGGER = _v1.BEFORE_TRIGGER, _v1.AFTER_TRIGGER
ENVIRONMENT_SQL, TABLE_CATALOG_SQL = _v1.ENVIRONMENT_SQL, _v1.TABLE_CATALOG_SQL
SOURCE_CATALOG_SQL, LOCKS_SQL, PERMISSIONS_SQL = _v1.SOURCE_CATALOG_SQL, _v1.LOCKS_SQL, _v1.PERMISSIONS_SQL
canonical, identifier, literal, target = _v1.canonical, _v1.identifier, _v1.literal, _v1.target


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise SourceInstallError(label + ' requires an exact bounded integer')
    return value


def _inputs(config, policy):
    if type(config) is not SQLCaptureConfigV2 or type(policy) is not SourceInstallPolicy:
        raise ValueError('Explicit immutable SQLCaptureConfigV2 and SourceInstallPolicy required')
    if VERSION_COLUMN in {c.name for c in config.table.columns}:
        raise ValueError('Installed version column collides with a configured column')


def function_bodies_v2(policy):
    """Retain the strict old login/scope guard; additionally freeze V2 key identity.

    DELETE ledger IDs identify ledger events, not a new deleted-row version.
    OLD's actual row version remains base_version; no source fact is authorized.
    """
    before, after = _v1.function_bodies(policy)
    marker = 'NEW.' + identifier(VERSION_COLUMN) + ' :='
    guard = ("IF TG_OP='UPDATE' THEN IF (pg_catalog.to_jsonb(OLD)->TG_ARGV[0]) IS DISTINCT FROM "
             "(pg_catalog.to_jsonb(NEW)->TG_ARGV[0]) THEN RAISE EXCEPTION 'V2 primary key is immutable' "
             "USING ERRCODE='23514'; END IF; END IF; ")
    if before.count(marker) != 1:
        raise SourceInstallError('Reviewed source DDL helper changed')
    return before.replace(marker, guard + marker, 1), after


def installation_ddl_v2(config, policy):
    _inputs(config, policy)
    old_before, _ = _v1.function_bodies(policy)
    before, _ = function_bodies_v2(policy)
    # This pure helper consumes V2's own one-table properties directly. No V1
    # config object, config parser, installation receipt or wire is constructed.
    return tuple(sql.replace(literal(old_before), literal(before))
                 for sql in _v1.installation_ddl(config, policy))


def verify_environment_v2(policy, value):
    owner = _v1.verify_environment(policy, value)
    _integer(value.get('databaseOid'), 1, 2**32-1, 'Database OID')
    _integer(value.get('backendPid'), 1, 2**31-1, 'Backend PID')
    identifier(owner)
    return owner


def verify_source_catalog_v2(policy, owner, value):
    _v1.verify_source_catalog(policy, owner, value)
    for name in ('type','start','increment','minimum','maximum','cache'):
        _integer(value['sequence'].get(name), 1, 2**63-1, 'Sequence ' + name)
    if type(value['sequence'].get('cycle')) is not bool:
        raise SourceInstallError('Sequence cycle must be an observed boolean')


def _columns(value):
    columns = value.get('columns')
    if type(columns) is not list or not 1 <= len(columns) <= 18 or any(type(c) is not dict for c in columns):
        raise SourceInstallError('Complete raw physical catalog column inventory required')
    names, numbers = set(), []
    for column in columns:
        name = column.get('name')
        identifier(name)
        number = _integer(column.get('number'), 1, 32767, 'Physical column number')
        if name in names or (numbers and number <= numbers[-1]):
            raise SourceInstallError('Duplicate or unordered raw physical column identity')
        names.add(name); numbers.append(number)
    return {c['name']:c for c in columns}


def _type(column, kind):
    oid = _integer(column.get('oid'), 1, 2**32-1, 'Native type OID')
    if (oid not in {'int64':{20,21,23},'bool':{16},'text':{25,1043},'uuid':{2950}}[kind]
            or column.get('typeKind') != 'b' or column.get('typeSchema') != 'pg_catalog'
            or type(column.get('elementType')) is not int or column['elementType'] != 0
            or column.get('generated') != '' or column.get('identity') != ''
            or column.get('notNull') is not True):
        raise SourceInstallError('Non-NULL native pg_catalog scalar type without domain/array/generation required')
    if kind == 'text':
        if (column.get('collation') != 'C' or column.get('collationSchema') != 'pg_catalog'
                or column.get('collationDeterministic') is not True):
            raise SourceInstallError('Explicit deterministic pg_catalog C text comparison required')
    elif column.get('collation') is not None or column.get('collationSchema') is not None:
        raise SourceInstallError('Unexpected non-text collation')


def verify_table_catalog_v2(table, policy, owner, value, *, installed=False):
    if type(table) is not TableConfigV2 or type(policy) is not SourceInstallPolicy:
        raise ValueError('Independent V2 table and installation policy required')
    if type(value) is not dict or (value.get('schema'),value.get('table')) != (table.schema,table.table):
        raise SourceInstallError('V2 table identity mismatch')
    if (value.get('owner') != owner or value.get('kind') != 'r' or value.get('persistence') != 'p'
            or any(value.get(k) is not False for k in ('rls','forceRls','inherits','rules'))):
        raise SourceInstallError('Owner-controlled permanent ordinary table without RLS/rules/inheritance required')
    oid = _integer(value.get('oid'), 1, 2**32-1, 'Table OID')
    columns = _columns(value)
    expected = {c.name for c in table.columns} | ({VERSION_COLUMN} if installed else set())
    if set(columns) != expected:
        raise SourceInstallError('Complete configured column inventory by name required')
    for configured in table.columns:
        _type(columns[configured.name], configured.type)
    primary = value.get('primaryKeys')
    if (type(primary) is not list or len(primary) != 1 or type(primary[0]) is not dict
            or primary[0].get('columns') != [table.primary_key]
            or type(primary[0].get('keys')) is not int or primary[0]['keys'] != 1
            or any(primary[0].get(k) is not True for k in ('valid','ready','immediate'))):
        raise SourceInstallError('One immediate valid single-column primary key required')
    triggers = value.get('triggers')
    if type(triggers) is not list:
        raise SourceInstallError('Actual trigger inventory required')
    if not installed:
        if triggers: raise SourceInstallError('Existing user triggers require another semantics profile')
        return oid
    metadata = columns[VERSION_COLUMN]
    _type(metadata, 'int64')
    if metadata['oid'] != 20 or metadata.get('default') is not None:
        raise SourceInstallError('Installed metadata must be non-NULL bigint without a default')
    indexes = value.get('uniqueIndexes')
    if type(indexes) is not list or not any(type(i) is dict and i.get('columns') == [VERSION_COLUMN]
            and type(i.get('keys')) is int and i['keys'] == 1
            and all(i.get(k) is True for k in ('valid','ready','immediate','noPredicate','noExpression')) for i in indexes):
        raise SourceInstallError('Complete unique version index required')
    before, after = function_bodies_v2(policy)
    expected_triggers = {BEFORE_TRIGGER:(23,'before_write',before), AFTER_TRIGGER:(29,'after_write',after)}
    if len(triggers) != 2 or any(type(t) is not dict for t in triggers) or {t.get('name') for t in triggers} != set(expected_triggers):
        raise SourceInstallError('Exact V2 source trigger inventory required')
    for trigger in triggers:
        kind, name, body = expected_triggers[trigger['name']]
        if (type(trigger.get('type')) is not int or trigger['type'] != kind or trigger.get('enabled') != 'A'
                or trigger.get('argsHex') != (table.primary_key.encode('utf-8')+b'\0').hex()
                or trigger.get('noCondition') is not True or trigger.get('noColumns') is not True
                or trigger.get('functionSchema') != policy.namespace or trigger.get('function') != name
                or trigger.get('body') != body or trigger.get('owner') != owner
                or trigger.get('securityDefiner') is not True or type(trigger.get('returnType')) is not int
                or trigger['returnType'] != 2279 or trigger.get('volatile') != 'v' or trigger.get('parallel') != 'u'
                or type(trigger.get('argCount')) is not int or trigger['argCount'] != 0):
            raise SourceInstallError('V2 source trigger/function identity, role guard or immutable-key body differs')
        settings = trigger.get('settings')
        if type(settings) is not list or len(settings) != 2 or any(type(s) is not str or '=' not in s for s in settings):
            raise SourceInstallError('Source function settings missing')
        settings_map = dict(s.split('=',1) for s in settings)
        if (set(settings_map) != {'search_path','standard_conforming_strings'}
                or settings_map['standard_conforming_strings'] != 'on'
                or [s.strip() for s in settings_map['search_path'].split(',')] != ['pg_catalog','pg_temp']):
            raise SourceInstallError('Unsafe source function settings')
    return oid


def compare_installation_catalogs_v2(table, policy, owner, before, after):
    verify_table_catalog_v2(table,policy,owner,before)
    verify_table_catalog_v2(table,policy,owner,after,installed=True)
    if before['oid'] != after['oid']:
        raise SourceInstallError('Installed relation identity changed')
    old, new = _columns(before), _columns(after)
    if any(old[c.name] != new[c.name] for c in table.columns):
        raise SourceInstallError('Business physical/type attributes changed during installation')
    old_order = [c['name'] for c in before['columns']]
    new_order = [c['name'] for c in after['columns']]
    if new_order != old_order+[VERSION_COLUMN] or new[VERSION_COLUMN]['number'] <= max(c['number'] for c in before['columns']):
        raise SourceInstallError('Only the new version column may be appended')
    return {'format':'moontxnwitness-v2-star-catalog-comparison/v2','beforePhysicalColumns':old_order,
            'afterPhysicalColumns':new_order,'onlyVersionColumnAdded':True,
            'declaredBusinessViewMatchesBeforeOrder':old_order == [c.name for c in table.columns],
            'catalogInstallationSourceAuthorized':False,'moonbitProjectionVerified':False}


class _LogV2:
    def __init__(self, path, maximum, *, log_format=LOG_FORMAT, contract=CONTRACT):
        self.file = Path(path).open('xb'); self.maximum = maximum
        self.log_format, self.contract = log_format, contract
        self.count = self.size = 0; self.failed = self.closed = False; self.digest = hashlib.sha256()
        try:self.append({'kind':'header','format':log_format,'contract':contract,'sourceFactsProduced':False})
        except BaseException:self.file.close();self.closed=True;raise
    def append(self, value):
        if self.failed or self.closed: raise SourceInstallError('V2 installation log is not writable')
        raw = (canonical({'seq':self.count+1,**value})+'\n').encode('utf-8')
        if len(raw)>524288 or self.count>=65535 or self.size+len(raw)>self.maximum-1024:
            self.failed=True; raise SourceInstallError('V2 installation log budget exhausted')
        try:
            if self.file.write(raw) != len(raw): raise OSError('Short installation log write')
            self.digest.update(raw); self.count+=1; self.size+=len(raw)
        except BaseException: self.failed=True; raise
    def close(self):
        try:
            if not self.failed: self.append({'kind':'seal','prefixSha256':self.digest.hexdigest(),'records':self.count})
            self.file.flush(); os.fsync(self.file.fileno())
        except BaseException: self.failed=True; raise
        finally: self.closed=True; self.file.close()
        return {'format':self.log_format,'sealed':not self.failed,'records':self.count,'bytes':self.size,'sha256':self.digest.hexdigest()}


def _python_type(value): return type(value).__module__+'.'+type(value).__qualname__


def _json(text):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise SourceInstallError('Duplicate original control JSON key')
            result[key]=value
        return result
    def nonfinite(_): raise SourceInstallError('Nonfinite original control JSON')
    return json.loads(text,object_pairs_hook=unique,parse_constant=nonfinite)


class _ControlV2:
    def __init__(self, connection, log, *, terminal_queries=('installation-commit','installation-rollback')):
        self.connection,self.log,self.terminal_queries=connection,log,terminal_queries
    def command(self, query_id, sql, params=None, *, max_rows=1):
        request=self.log.count+1; phase='execute'; native={'rawComplete':False,'rows':[]}
        self.log.append({'kind':'control-request','format':'moontxnwitness-source-control-request/v2','queryId':query_id,
                         'sql':sql,'parameters':params,'transactionStatusBefore':int(self.connection.info.transaction_status)})
        try:
            cursor=self.connection.execute(sql,params); phase='native'; result=cursor.pgresult
            status,fields,rows=int(result.status),int(result.nfields),int(result.ntuples)
            tag=result.command_status
            if tag is not None and type(tag) is not bytes: raise SourceInstallError('Original command_status bytes required')
            count=result.command_tuples
            if count is not None and type(count) is not int: raise SourceInstallError('Original integer command_tuples getter required')
            native.update(status=status,fieldCount=fields,rowCount=rows,commandStatusBase64=None if tag is None else base64.b64encode(tag).decode('ascii'),
                          commandTuples={'pythonType':_python_type(count),'value':None if count is None else str(count)},fields=[])
            if not 0<=rows<=max_rows or not 0<=fields<=1: raise SourceInstallError('Control native dimensions exceed bound')
            size=0
            for col in range(fields): native['fields'].append({'oid':result.ftype(col),'format':result.fformat(col)})
            for row in range(rows):
                cells=[]
                for col in range(fields):
                    cell=result.get_value(row,col)
                    if cell is not None and type(cell) is not bytes: raise SourceInstallError('Original control cell bytes required')
                    size+=len(cell) if cell is not None else 0
                    if size>131072: raise SourceInstallError('Control native byte budget exhausted')
                    cells.append(None if cell is None else base64.b64encode(cell).decode('ascii'))
                native['rows'].append(cells)
            native['rawComplete']=True
            self.log.append({'kind':'control-native','format':'moontxnwitness-source-control-native/v2','requestSeq':request,'queryId':query_id,
                             'native':native,'transactionStatusAfter':int(self.connection.info.transaction_status)})
            if query_id not in self.terminal_queries and int(self.connection.info.transaction_status)!=2:
                raise SourceInstallError('Control transaction is no longer active')
            phase='delivery'; decoded=cursor.fetchall() if fields else None
            observation={'method':'fetchall' if fields else None,'fetchExecuted':bool(fields),'pythonType':_python_type(decoded),'rows':[]}
            if type(decoded) in (list,tuple):
                for row in decoded:
                    observation['rows'].append({'pythonType':_python_type(row),'cells':[{'pythonType':_python_type(v),'value':v if type(v) is str else None} for v in row] if type(row) in (list,tuple) else []})
            self.log.append({'kind':'control-delivery','format':'moontxnwitness-source-control-delivery/v2','requestSeq':request,'queryId':query_id,'observation':observation})
            if fields:
                if status!=2 or fields!=1 or result.ftype(0)!=25 or result.fformat(0)!=0 or type(decoded) is not list or len(decoded)!=rows:
                    raise SourceInstallError('Control native text/default delivery required')
                for index,row in enumerate(decoded):
                    if (type(row) is not tuple or len(row)!=1 or type(row[0]) is not str
                            or base64.b64encode(row[0].encode('utf-8')).decode('ascii')!=native['rows'][index][0]):
                        raise SourceInstallError('Decoded catalog result differs from original native bytes')
            elif status!=1 or rows!=0: raise SourceInstallError('Control COMMAND_OK required')
            text_tag=tag.decode('ascii') if tag is not None else None
            if fields and (text_tag!='SELECT '+str(rows) or count!=rows): raise SourceInstallError('Native SELECT tag/getter count mismatch')
            ack={'native':native,'tag':text_tag,'count':count,'transactionStatusAfter':int(self.connection.info.transaction_status),'requestSeq':request}
            return [_json(row[0]) for row in decoded] if fields else [],ack
        except BaseException as error:
            try:self.log.append({'kind':'control-error','format':'moontxnwitness-source-control-error/v2','requestSeq':request,'queryId':query_id,
                                 'phase':phase,'native':native,'errorClass':_python_type(error),'sqlstate':getattr(error,'sqlstate',None),'message':str(error)})
            except BaseException:pass
            raise


def _one(control, name, sql, params=None):
    rows,_=control.command(name,sql,params)
    if len(rows)!=1 or type(rows[0]) is not dict: raise SourceInstallError('One actual catalog object required: '+name)
    return rows[0]


def _ack(control, name, sql, tag, state=2):
    _,ack=control.command(name,sql,max_rows=0)
    if (ack['native']['status'],ack['tag'],ack['native']['fieldCount'],ack['transactionStatusAfter'])!=(1,tag,0,state):
        raise SourceInstallError('Actual control acknowledgement missing: '+name)
    return ack


def _qi(name): return identifier(name).replace('%','%%')
def _qt(table): return _qi(table.schema)+'.'+_qi(table.table)


def initial_snapshot_sql_v2(config, page_size=1):
    table=config.table; row='pg_catalog.to_jsonb(t)'; version=_qi(VERSION_COLUMN)
    limits=' OR '.join('pg_catalog.octet_length(t.'+_qi(c.name)+')>'+str(min(config.max_text_bytes,65536)) for c in table.columns if c.type=='text') or 'FALSE'
    return ("SELECT CASE WHEN ("+limits+") OR pg_catalog.octet_length("+row+"::text)>65536 THEN pg_catalog.jsonb_build_object('kind','initial-row-budget') "
            "ELSE pg_catalog.jsonb_build_object('kind','initial-row','row',"+row+") END::text FROM "+_qt(table)+" t WHERE t."+version+">%s ORDER BY t."+version+" LIMIT "+str(_integer(page_size, 1, 128, "Snapshot page size")))


def initial_ledger_sql_v2(policy):
    return ("SELECT CASE WHEN pg_catalog.octet_length(p.payload)>65536 THEN '{\"kind\":\"initial-ledger-budget\"}' ELSE p.payload END FROM "
            "(SELECT e.version,pg_catalog.jsonb_build_object('kind','initial-ledger','version',e.version,'baseVersion',e.base_version,'relationOid',e.relation_oid::bigint,"
            "'operation',e.operation,'writerXid',e.writer_xid,'writerLogin',e.writer_login,'writerPid',e.writer_pid,'rowKey',e.row_key,'oldKey',e.old_key,'rowValues',e.row_values)::text payload FROM "+_qi(policy.namespace)+".effects e WHERE e.version>%s ORDER BY e.version LIMIT 1) p")


def _initial_row(config, raw, last):
    if type(raw) is not dict or set(raw)!={'kind','row'} or raw['kind']!='initial-row' or type(raw['row']) is not dict:
        raise SourceInstallError('Initial row exceeds snapshot bound or has a malformed observation')
    row=raw['row']; expected={c.name for c in config.table.columns}|{VERSION_COLUMN}
    if set(row)!=expected: raise SourceInstallError('Initial row column inventory differs')
    version=_integer(row[VERSION_COLUMN],1,2**63-1,'Installed initial version')
    if version<=last: raise SourceInstallError('Initial versions are not strictly increasing')
    for column in config.table.columns:
        value=row[column.name]
        try: identity=_input_value(value,column.type,config.max_text_bytes)
        except ValueError as error: raise SourceInstallError('Invalid initial configured scalar') from error
        if column.type=='uuid' and (type(value) is not str or value!=identity): raise SourceInstallError('Canonical native UUID JSON required')
    key=config.table.key
    return version,row,(key.type,_input_value(row[key.name],key.type,config.max_text_bytes))


@dataclass(frozen=True,slots=True)
class SourceInstallationV2:
    _text:str
    def to_dict(self): return json.loads(self._text)


def install_configured_source_v2(connection, output, config, policy, *, opt_in=False):
    """Explicit installer only. All source/Window/model admission remains false."""
    if opt_in is not True: raise ValueError('Explicit opt_in=True required before connection/filesystem access')
    _inputs(config,policy)
    if connection.autocommit is not True or int(connection.info.transaction_status)!=0:
        raise ValueError('Dedicated idle autocommit control connection required')
    path=Path(output).resolve(); path.mkdir(parents=True,exist_ok=False)
    log=_LogV2(path/'source-install-v2.jsonl',policy.max_log_bytes); control=_ControlV2(connection,log)
    requested=confirmed=False; pending=None; snapshot={}; initial_digest=hashlib.sha256()
    receipt={'format':FORMAT,'contract':CONTRACT,'config':config.to_dict(),'configSha256':config.sha256,'policy':policy.to_dict(),
             'versionColumn':VERSION_COLUMN,'versionType':'int64',
             'status':'started','catalogComponentsChecked':False,'initialSnapshotComponentsChecked':False,'initialLedgerComponentsChecked':False,
             'actualCommitAcknowledged':False,'actualCommitConfirmed':False,'sourceFactsProduced':False,'captureFactsProduced':False,
             'sourceAuthenticated':False,'moonbitCatalogVerified':False,'moonbitProjectionVerified':False,'writerWindowVerified':False,
             'completeWindow':False,'modelCoverageAccepted':False,'driverFetchVerified':False,'commitVerified':False,
             'deleteLedgerIdentity':'ledger-event-only-not-a-new-deleted-row-version',
             'gaps':['independent-MoonBit-V2-installation-not-verified','driver-and-source-projection-not-connected','writer-window-not-closed','privileged-DDL-and-cascade-exclusion-not-proven']}
    try:
        _ack(control,'begin','BEGIN','BEGIN'); _ack(control,'standard-strings','SET LOCAL standard_conforming_strings=on','SET')
        _ack(control,'safe-search-path','SET LOCAL search_path TO pg_catalog, pg_temp','SET')
        table=config.table
        _ack(control,'install-lock','LOCK TABLE '+target(table)+' IN ACCESS EXCLUSIVE MODE NOWAIT','LOCK TABLE')
        environment=_one(control,'environment',ENVIRONMENT_SQL,(list(policy.writers),)); owner=verify_environment_v2(policy,environment)
        receipt['environment']=environment
        before=_one(control,'before-catalog',TABLE_CATALOG_SQL,(table.schema,table.table))
        receipt['beforeCatalog']=before; oid=verify_table_catalog_v2(table,policy,owner,before)
        privileges=[]
        for writer in policy.writers:
            row=_one(control,'writer-privileges',PERMISSIONS_SQL,(writer,target(table),writer,target(table),writer,target(table),writer,owner))
            privileges.append(row)
            if row.get('role')!=writer or row.get('table')!=target(table) or any(row.get(k) is not False for k in ('trigger','truncate','ownerMembership')):
                raise SourceInstallError('Writer can bypass the declared row-only source scope')
        receipt['writerPrivileges']=privileges
        locks=_one(control,'held-locks',LOCKS_SQL,([oid],)); receipt['initializationLocks']=locks
        if locks.get('pid')!=environment['backendPid'] or {r.get('relation') for r in locks.get('locks',[]) if r.get('mode')=='AccessExclusiveLock' and r.get('granted') is True}!={oid}:
            raise SourceInstallError('Actual installation lock inventory incomplete')
        update_count=None
        for sql in installation_ddl_v2(config,policy):
            _,ack=control.command('install-ddl',sql,max_rows=0)
            if sql.startswith('UPDATE '):
                update_count=_integer(ack['count'],0,policy.max_initial_rows,'Initial UPDATE count')
                if ack['tag']!='UPDATE '+str(update_count): raise SourceInstallError('Initial UPDATE acknowledgement differs')
            else:
                expected=next((tag for prefix,tag in [('CREATE SCHEMA ','CREATE SCHEMA'),('CREATE SEQUENCE ','CREATE SEQUENCE'),('CREATE TABLE ','CREATE TABLE'),('CREATE FUNCTION ','CREATE FUNCTION'),('CREATE UNIQUE INDEX ','CREATE INDEX'),('CREATE TRIGGER ','CREATE TRIGGER'),('ALTER TABLE ','ALTER TABLE'),('REVOKE ','REVOKE')] if sql.startswith(prefix)),None)
                if expected is None or ack['tag']!=expected: raise SourceInstallError('DDL command acknowledgement differs')
        q=_qi(policy.namespace); v=_qi(VERSION_COLUMN)
        _,scope_ack=control.command('install-scope',f'INSERT INTO {q}.scope VALUES(%s,%s,%s,%s,%s)',(oid,table.schema,table.table,table.primary_key,config.sha256),max_rows=0)
        if scope_ack['tag']!='INSERT 0 1' or scope_ack['count']!=1: raise SourceInstallError('Scope insertion not acknowledged')
        _,ledger_ack=control.command('initial-ledger',f"INSERT INTO {q}.effects(version,base_version,relation_oid,operation,writer_xid,writer_login,writer_pid,row_key,old_key,row_values) SELECT {v},NULL,%s,'INITIAL',pg_catalog.pg_current_xact_id()::text,SESSION_USER,pg_catalog.pg_backend_pid(),pg_catalog.to_jsonb(t)->%s,NULL,pg_catalog.to_jsonb(t)-%s FROM {_qt(table)} t",(oid,table.primary_key,VERSION_COLUMN),max_rows=0)
        last=0; keys=set()
        while True:
            rows,_=control.command('initial-snapshot',initial_snapshot_sql_v2(config),(last,))
            if not rows: break
            version,row,key=_initial_row(config,rows[0],last)
            if key in keys: raise SourceInstallError('Duplicate initial primary-key identity')
            keys.add(key); snapshot[version]=row; last=version
            if len(snapshot)>policy.max_initial_rows: raise SourceInstallError('Initial snapshot row budget exhausted')
            initial_digest.update((canonical({'schema':table.schema,'table':table.table,'row':row})+'\n').encode('utf-8'))
        if update_count!=len(snapshot) or ledger_ack['count']!=len(snapshot) or ledger_ack['tag']!='INSERT 0 '+str(len(snapshot)):
            raise SourceInstallError('Initialization UPDATE/ledger/snapshot counts differ')
        after=_one(control,'installed-catalog',TABLE_CATALOG_SQL,(table.schema,table.table)); receipt['afterCatalog']=after
        receipt['starCatalogComparison']=compare_installation_catalogs_v2(table,policy,owner,before,after)
        source=_one(control,'source-catalog',SOURCE_CATALOG_SQL,(policy.namespace,)); receipt['sourceCatalog']=source
        verify_source_catalog_v2(policy,owner,source)
        scope,_=control.command('source-scope',f"SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint,'relation_schema',s.relation_schema,'relation_table',s.relation_table,'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM {q}.scope s ORDER BY relation_schema,relation_table")
        if scope!=[{'relation_oid':oid,'relation_schema':table.schema,'relation_table':table.table,'primary_key':table.primary_key,'config_sha256':config.sha256}]: raise SourceInstallError('Installed V2 scope differs')
        receipt['sourceScope']=scope
        last=0; seen=set(); writer=None
        while True:
            rows,_=control.command('verify-initial-ledger',initial_ledger_sql_v2(policy),(last,))
            if not rows: break
            row=rows[0]; version=_integer(row.get('version'),1,2**63-1,'Ledger version')
            values=snapshot.get(version)
            if (row.get('kind')!='initial-ledger' or version<=last or values is None or row.get('operation')!='INITIAL'
                    or row.get('relationOid')!=oid or row.get('baseVersion') is not None or row.get('oldKey') is not None
                    or canonical(row.get('rowKey'))!=canonical(values[table.primary_key]) or canonical(row.get('rowValues'))!=canonical({k:v for k,v in values.items() if k!=VERSION_COLUMN})
                    or row.get('writerPid')!=environment['backendPid'] or type(row.get('writerXid')) is not str
                    or not row['writerXid'].isascii() or not row['writerXid'].isdigit() or len(row['writerXid'])>20
                    or not 1<=int(row['writerXid'])<=2**64-1 or str(int(row['writerXid']))!=row['writerXid']
                    or type(row.get('writerLogin')) is not str or not row['writerLogin']):
                raise SourceInstallError('Initial ledger row does not match the complete native snapshot')
            _integer(row.get('relationOid'),1,2**32-1,'Ledger relation OID')
            _integer(row.get('writerPid'),1,2**31-1,'Ledger writer PID')
            identifier(row['writerLogin'])
            identity=(row['writerXid'],row['writerLogin'],row['writerPid'])
            if writer is not None and writer!=identity: raise SourceInstallError('Initial ledger writer identity changed')
            writer=identity; seen.add(version); last=version
        if seen!=set(snapshot): raise SourceInstallError('Initial ledger omitted snapshot versions')
        counts=_one(control,'initial-ledger-count',f"SELECT pg_catalog.jsonb_build_object('rows',count(*),'nonInitial',count(*) FILTER(WHERE operation<>'INITIAL'))::text FROM {q}.effects")
        if counts!={'rows':len(snapshot),'nonInitial':0} or type(counts.get('rows')) is not int or type(counts.get('nonInitial')) is not int: raise SourceInstallError('Initial ledger count/inventory incomplete')
        receipt['initialLedger']=counts
        before_commit=int(connection.info.transaction_status)
        log.append({'kind':'installation-commit-request','format':'moontxnwitness-source-commit-request/v2','transactionStatusBefore':before_commit})
        if before_commit!=2: raise SourceInstallError('Installation was not in transaction before COMMIT')
        requested=True; _ack(control,'installation-commit','COMMIT','COMMIT',state=0); confirmed=True
        receipt.update(status='installed-components-only',actualCommitAcknowledged=True,actualCommitConfirmed=True,
                       catalogComponentsChecked=True,initialSnapshotComponentsChecked=True,initialLedgerComponentsChecked=True,
                       initialRows=len(snapshot),initialSnapshotSha256=initial_digest.hexdigest())
    except BaseException as error:
        pending=error
        receipt.update(status='installation-commit-unknown' if requested and not confirmed else 'failed',
                       errorClass=_python_type(error),error=str(error),actualCommitAcknowledged=confirmed,actualCommitConfirmed=confirmed)
        if requested: receipt['gaps'].append('inspect-owned-schema-before-any-retry')
        receipt['rollbackRequested']=True
        try:
            connection.rollback();receipt['rollbackCallReturned']=True
            receipt['transactionStatusAfterRollbackCall']=int(connection.info.transaction_status)
            receipt['gaps'].append('rollback-call-return-is-not-a-retained-native-ACK')
        except BaseException: receipt['gaps'].append('rollback-outcome-unknown')
        try: log.append({'kind':'installation-failed','format':FORMAT,'errorClass':_python_type(error),'message':str(error)})
        except BaseException: pass
        raise
    finally:
        final_error=None
        try: receipt['log']=log.close()
        except BaseException as error:
            final_error=error; receipt['log']={'format':LOG_FORMAT,'sealed':False}
        if not receipt['log'].get('sealed'):
            receipt.update(status='recording-failed',catalogComponentsChecked=False,initialSnapshotComponentsChecked=False,
                           initialLedgerComponentsChecked=False,actualCommitConfirmed=False)
            receipt['gaps'].append('inspect-owned-schema-before-any-retry')
            final_error=final_error or SourceInstallError('V2 installation log is unsealed')
        try: (path/'receipt-v2.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        except BaseException as error: final_error=final_error or error
        if pending is None and final_error is not None:
            raise final_error
    return SourceInstallationV2(canonical(receipt))
