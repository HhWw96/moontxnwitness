"""Explicit configured PostgreSQL row-version installation, not history facts.

This module never rewrites/executes business SQL or consumes business cursors.
It uses a dedicated autocommit control connection and a bounded existing log.
"""
from __future__ import annotations
import base64,hashlib,json,sys
from dataclasses import dataclass
from pathlib import Path
from .configured_sql import SQLCaptureConfig
from .instrumentation import _LifecycleLog

VERSION_COLUMN='__mtw_source_version'
BEFORE_TRIGGER='__mtw_source_before'
AFTER_TRIGGER='__mtw_source_after'

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()
def identifier(name):
    if type(name)is not str or not name or '\x00'in name or len(name.encode('utf8'))>63:raise ValueError('PostgreSQL identifier required')
    return '"'+name.replace('"','""')+'"'
def literal(value):return "'"+value.replace("'","''")+"'"
def target(table):return identifier(table.schema)+'.'+identifier(table.table)

@dataclass(frozen=True,slots=True)
class SourceInstallPolicy:
    namespace:str
    writers:tuple[str,...]
    max_initial_rows:int=4096
    max_log_bytes:int=16*1024*1024
    def __post_init__(self):
        identifier(self.namespace)
        if not self.namespace.startswith('mtw_source_'):raise ValueError('Explicit private mtw_source_* namespace required')
        if type(self.writers)is not tuple or not 1<=len(self.writers)<=16 or len(set(self.writers))!=len(self.writers):raise ValueError('1..16 distinct immutable writer login roles required')
        for writer in self.writers:identifier(writer)
        if type(self.max_initial_rows)is not int or not 1<=self.max_initial_rows<=16384:raise ValueError('Initial row budget must be 1..16384')
        if type(self.max_log_bytes)is not int or not 1024*1024<=self.max_log_bytes<=64*1024*1024:raise ValueError('Bounded log budget required')
    def to_dict(self):return {'namespace':self.namespace,'writers':list(self.writers),'maxInitialRows':self.max_initial_rows,'maxLogBytes':self.max_log_bytes}

class SourceInstallError(RuntimeError):pass

ENVIRONMENT_SQL="""SELECT pg_catalog.jsonb_build_object(
 'database',pg_catalog.current_database(),'databaseOid',(SELECT oid::bigint FROM pg_catalog.pg_database WHERE datname=pg_catalog.current_database()),'backendPid',pg_catalog.pg_backend_pid(),
 'serverVersionNum',pg_catalog.current_setting('server_version_num'),'serverEncoding',pg_catalog.current_setting('server_encoding'),
 'clientEncoding',pg_catalog.current_setting('client_encoding'),'standardConformingStrings',pg_catalog.current_setting('standard_conforming_strings'),
 'replicationRole',pg_catalog.current_setting('session_replication_role'),'owner',CURRENT_USER,
 'eventTriggers',COALESCE((SELECT pg_catalog.jsonb_agg(evtname ORDER BY evtname) FROM pg_catalog.pg_event_trigger WHERE evtenabled<>'D'),'[]'::jsonb),
 'ownerRole',(SELECT pg_catalog.jsonb_build_object('name',rolname,'superuser',rolsuper,'login',rolcanlogin,'createRole',rolcreaterole,'replication',rolreplication,'bypassRls',rolbypassrls) FROM pg_catalog.pg_roles WHERE rolname=CURRENT_USER),
 'writers',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',rolname,'superuser',rolsuper,'login',rolcanlogin,'createRole',rolcreaterole,'createDb',rolcreatedb,'replication',rolreplication,'bypassRls',rolbypassrls,'ownerMembership',pg_catalog.pg_has_role(oid,CURRENT_USER,'MEMBER'),'privilegedMembership',EXISTS(SELECT 1 FROM pg_catalog.pg_roles privileged WHERE (privileged.rolsuper OR privileged.rolcreaterole OR privileged.rolreplication OR privileged.rolbypassrls) AND pg_catalog.pg_has_role(pg_roles.oid,privileged.oid,'MEMBER')),'canSetReplicationRole',pg_catalog.has_parameter_privilege(oid,'session_replication_role','SET')) ORDER BY rolname) FROM pg_catalog.pg_roles WHERE rolname::text COLLATE pg_catalog."C"=ANY(%s)))::text"""

TABLE_CATALOG_SQL="""SELECT pg_catalog.jsonb_build_object(
 'schema',n.nspname,'table',c.relname,'oid',c.oid::bigint,'kind',c.relkind,'persistence',c.relpersistence,
 'owner',pg_catalog.pg_get_userbyid(c.relowner),'rls',c.relrowsecurity,'forceRls',c.relforcerowsecurity,
 'inherits',EXISTS(SELECT 1 FROM pg_catalog.pg_inherits WHERE inhrelid=c.oid OR inhparent=c.oid),
 'rules',EXISTS(SELECT 1 FROM pg_catalog.pg_rewrite WHERE ev_class=c.oid AND rulename<>'_RETURN'),
 'columns',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',a.attname,'number',a.attnum,'oid',a.atttypid::bigint,'generated',a.attgenerated,'identity',a.attidentity,'notNull',a.attnotnull,'typeKind',ty.typtype,'typeSchema',tn.nspname,'elementType',ty.typelem::bigint,'collation',co.collname,'collationSchema',cn.nspname,'collationProvider',co.collprovider,'collationDeterministic',co.collisdeterministic,'default',pg_catalog.pg_get_expr(ad.adbin,ad.adrelid)) ORDER BY a.attnum) FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_type ty ON ty.oid=a.atttypid JOIN pg_catalog.pg_namespace tn ON tn.oid=ty.typnamespace LEFT JOIN pg_catalog.pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum LEFT JOIN pg_catalog.pg_collation co ON co.oid=a.attcollation LEFT JOIN pg_catalog.pg_namespace cn ON cn.oid=co.collnamespace WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),'[]'::jsonb),
 'primaryKeys',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('valid',i.indisvalid,'ready',i.indisready,'immediate',i.indimmediate,'keys',i.indnkeyatts,'columns',(SELECT pg_catalog.jsonb_agg(a.attname ORDER BY k.ordinality) FROM pg_catalog.unnest(i.indkey) WITH ORDINALITY k(num,ordinality) JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num WHERE k.ordinality<=i.indnkeyatts))) FROM pg_catalog.pg_index i WHERE i.indrelid=c.oid AND i.indisprimary),'[]'::jsonb),
 'uniqueIndexes',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('valid',i.indisvalid,'ready',i.indisready,'immediate',i.indimmediate,'keys',i.indnkeyatts,'noPredicate',i.indpred IS NULL,'noExpression',i.indexprs IS NULL,'columns',(SELECT pg_catalog.jsonb_agg(a.attname ORDER BY k.ordinality) FROM pg_catalog.unnest(i.indkey) WITH ORDINALITY k(num,ordinality) JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num WHERE k.ordinality<=i.indnkeyatts))) FROM pg_catalog.pg_index i WHERE i.indrelid=c.oid AND i.indisunique),'[]'::jsonb),
 'triggers',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',t.tgname,'type',t.tgtype,'enabled',t.tgenabled,'argsHex',pg_catalog.encode(t.tgargs,'hex'),'noCondition',t.tgqual IS NULL,'noColumns',t.tgattr=''::int2vector,'functionSchema',pn.nspname,'function',p.proname,'body',p.prosrc,'securityDefiner',p.prosecdef,'returnType',p.prorettype::bigint,'volatile',p.provolatile,'parallel',p.proparallel,'argCount',p.pronargs,'owner',pg_catalog.pg_get_userbyid(p.proowner),'settings',p.proconfig) ORDER BY t.tgname) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace WHERE t.tgrelid=c.oid AND NOT t.tgisinternal),'[]'::jsonb))::text
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s"""

LOCKS_SQL="""SELECT pg_catalog.jsonb_build_object('pid',pg_catalog.pg_backend_pid(),'locks',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('relation',relation::bigint,'mode',mode,'granted',granted) ORDER BY relation) FROM pg_catalog.pg_locks WHERE pid=pg_catalog.pg_backend_pid() AND relation=ANY(%s::oid[])),'[]'::jsonb))::text"""

PERMISSIONS_SQL="""SELECT pg_catalog.jsonb_build_object('role',%s::text,'table',%s::text,
 'trigger',pg_catalog.has_table_privilege(%s,%s,'TRIGGER'),'truncate',pg_catalog.has_table_privilege(%s,%s,'TRUNCATE'),
 'ownerMembership',pg_catalog.pg_has_role(%s,%s,'MEMBER'))::text"""


SOURCE_CATALOG_SQL="""SELECT pg_catalog.jsonb_build_object(
 'namespace',n.nspname,'owner',pg_catalog.pg_get_userbyid(n.nspowner),
 'objects',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',c.relname,'kind',c.relkind,'owner',pg_catalog.pg_get_userbyid(c.relowner)) ORDER BY c.relname) FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid),
 'nonOwnerGrants',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('object',z.name,'grantee',a.grantee::bigint,'privilege',a.privilege_type)) FROM (SELECT n.nspname name,n.nspowner owner,n.nspacl acl,'n'::"char" object_type UNION ALL SELECT c.relname,c.relowner,c.relacl,CASE WHEN c.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid UNION ALL SELECT p.proname,p.proowner,p.proacl,'f'::"char" FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid) z CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(z.acl,pg_catalog.acldefault(z.object_type,z.owner))) a WHERE a.grantee<>z.owner),'[]'::jsonb),
 'ownerMembers',COALESCE((SELECT pg_catalog.jsonb_agg(r.rolname) FROM pg_catalog.pg_roles r WHERE r.oid<>n.nspowner AND NOT r.rolsuper AND pg_catalog.pg_has_role(r.oid,n.nspowner,'MEMBER')),'[]'::jsonb),
 'sequence',(SELECT pg_catalog.jsonb_build_object('type',seqtypid::bigint,'start',seqstart,'increment',seqincrement,'minimum',seqmin,'maximum',seqmax,'cache',seqcache,'cycle',seqcycle) FROM pg_catalog.pg_sequence s JOIN pg_catalog.pg_class c ON c.oid=s.seqrelid WHERE c.relnamespace=n.oid AND c.relname='versions'),
 'functionCount',(SELECT count(*) FROM pg_catalog.pg_proc WHERE pronamespace=n.oid))::text FROM pg_catalog.pg_namespace n WHERE n.nspname=%s"""


def verify_source_catalog(policy,owner,value):
    if value.get('namespace')!=policy.namespace or value.get('owner')!=owner:raise SourceInstallError('Private source namespace owner differs')
    if value.get('nonOwnerGrants')!=[]or value.get('ownerMembers')!=[]:raise SourceInstallError('Non-owner can access source objects or assume the source owner role')
    objects=value.get('objects')or[]
    expected={'scope':'r','effects':'r','scope_pkey':'i','effects_pkey':'i','versions':'S'}
    if len(objects)!=len(expected)or {o.get('name'):o.get('kind')for o in objects}!=expected or any(o.get('owner')!=owner for o in objects):raise SourceInstallError('Source sidecar object inventory differs')
    if value.get('sequence')!={'type':20,'start':1,'increment':1,'minimum':1,'maximum':9223372036854775807,'cache':1,'cycle':False}:raise SourceInstallError('Version sequence can cycle, skip or use a different type')
    if value.get('functionCount')!=2:raise SourceInstallError('Unexpected private source functions')


@dataclass(frozen=True,slots=True)
class SourceInstallation:
    _text:str
    def to_dict(self):return json.loads(self._text)


def function_bodies(policy):
    q=identifier(policy.namespace);version=identifier(VERSION_COLUMN);sequence=literal(q+'.versions')
    roles='ARRAY['+','.join(literal(name)for name in policy.writers)+']::text[]'
    guard=("IF NOT (SESSION_USER::text COLLATE pg_catalog.\"C\" = ANY("+roles+")) THEN RAISE EXCEPTION 'writer login outside source scope' USING ERRCODE='42501'; END IF; "
      +f"IF NOT EXISTS(SELECT 1 FROM {q}.scope WHERE relation_oid=TG_RELID AND primary_key=TG_ARGV[0]) THEN RAISE EXCEPTION 'relation outside source scope' USING ERRCODE='42501'; END IF; ")
    before='BEGIN '+guard+f"NEW.{version} := pg_catalog.nextval({sequence}::pg_catalog.regclass); RETURN NEW; END;"
    after=('DECLARE v bigint; b bigint; k jsonb; oldk jsonb; vals jsonb; BEGIN '+guard
      +f"IF TG_OP='DELETE' THEN v:=pg_catalog.nextval({sequence}::pg_catalog.regclass); b:=OLD.{version}; k:=pg_catalog.to_jsonb(OLD)->TG_ARGV[0]; oldk:=k; vals:=NULL; "
      +f"ELSE v:=NEW.{version}; k:=pg_catalog.to_jsonb(NEW)->TG_ARGV[0]; vals:=pg_catalog.to_jsonb(NEW)-{literal(VERSION_COLUMN)}; IF TG_OP='UPDATE' THEN b:=OLD.{version}; oldk:=pg_catalog.to_jsonb(OLD)->TG_ARGV[0]; ELSE b:=NULL; oldk:=NULL; END IF; END IF; "
      +f"INSERT INTO {q}.effects(version,base_version,relation_oid,operation,writer_xid,writer_login,writer_pid,row_key,old_key,row_values) VALUES(v,b,TG_RELID,TG_OP,pg_catalog.pg_current_xact_id()::text,SESSION_USER,pg_catalog.pg_backend_pid(),k,oldk,vals); RETURN NULL; END;")
    return before,after


def installation_ddl(config,policy):
    q=identifier(policy.namespace);v=identifier(VERSION_COLUMN);sequence=literal(q+'.versions');before,after=function_bodies(policy)
    statements=[f'CREATE SCHEMA {q}',f'REVOKE ALL ON SCHEMA {q} FROM PUBLIC',
      f'CREATE SEQUENCE {q}.versions AS bigint NO CYCLE',
      f'CREATE TABLE {q}.scope(relation_oid oid PRIMARY KEY, relation_schema text COLLATE pg_catalog."C" NOT NULL, relation_table text COLLATE pg_catalog."C" NOT NULL, primary_key text COLLATE pg_catalog."C" NOT NULL, config_sha256 text COLLATE pg_catalog."C" NOT NULL)',
      f'CREATE TABLE {q}.effects(version bigint PRIMARY KEY, base_version bigint, relation_oid oid NOT NULL, operation text NOT NULL, writer_xid text NOT NULL, writer_login text NOT NULL, writer_pid integer NOT NULL, row_key jsonb NOT NULL, old_key jsonb, row_values jsonb)',
      f'CREATE FUNCTION {q}.before_write() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET standard_conforming_strings=on AS '+literal(before),
      f'CREATE FUNCTION {q}.after_write() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET standard_conforming_strings=on AS '+literal(after)]
    for table in config.tables:
        t=target(table);index=identifier('__mtw_source_idx_'+hashlib.sha256((table.schema+'\0'+table.table).encode()).hexdigest()[:16])
        statements += [f'ALTER TABLE {t} ADD COLUMN {v} bigint',f"UPDATE {t} SET {v}=pg_catalog.nextval({sequence}::pg_catalog.regclass)",f'ALTER TABLE {t} ALTER COLUMN {v} SET NOT NULL',f'CREATE UNIQUE INDEX {index} ON {t}({v})',
          f'CREATE TRIGGER {identifier(BEFORE_TRIGGER)} BEFORE INSERT OR UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION {q}.before_write({literal(table.primary_key)})',
          f'CREATE TRIGGER {identifier(AFTER_TRIGGER)} AFTER INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION {q}.after_write({literal(table.primary_key)})',
          f'ALTER TABLE {t} ENABLE ALWAYS TRIGGER {identifier(BEFORE_TRIGGER)}',f'ALTER TABLE {t} ENABLE ALWAYS TRIGGER {identifier(AFTER_TRIGGER)}']
    for role in ('PUBLIC',*map(identifier,policy.writers)):
        statements += [f'REVOKE ALL ON ALL TABLES IN SCHEMA {q} FROM {role}',f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA {q} FROM {role}',f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {q} FROM {role}']
        if role!='PUBLIC':statements.append(f'REVOKE ALL ON SCHEMA {q} FROM {role}')
    return tuple(statements)


def verify_environment(policy,value):
    if not isinstance(value,dict):raise SourceInstallError('Missing environment catalog')
    if not 180000<=int(value.get('serverVersionNum','0'))<190000:raise SourceInstallError('PostgreSQL18 required')
    if any(value.get(name)!=expected for name,expected in [('serverEncoding','UTF8'),('clientEncoding','UTF8'),('standardConformingStrings','on'),('replicationRole','origin')]):raise SourceInstallError('Unsupported installation environment')
    if value.get('eventTriggers')!=[]:raise SourceInstallError('Database event triggers require a separate DDL semantics profile')
    owner=value.get('ownerRole',{})
    if owner.get('name')!=value.get('owner')or any(owner.get(name)is not False for name in ('superuser','login','createRole','replication','bypassRls')):raise SourceInstallError('Dedicated non-login, non-privileged owner role required')
    writers=value.get('writers')or[]
    if sorted(item.get('name')for item in writers)!=sorted(policy.writers):raise SourceInstallError('All declared writer logins must exist')
    for writer in writers:
        if writer.get('login')is not True or any(writer.get(name)is not False for name in ('superuser','createRole','createDb','replication','bypassRls','ownerMembership','privilegedMembership','canSetReplicationRole')):raise SourceInstallError('Writer login can bypass the declared DML scope')
    return value['owner']


def verify_table_catalog(table,policy,owner,value,*,installed=False):
    if not isinstance(value,dict)or value.get('schema')!=table.schema or value.get('table')!=table.table:raise SourceInstallError('Table identity mismatch')
    if value.get('owner')!=owner or value.get('kind')!='r'or value.get('persistence')!='p'or any(value.get(k)is not False for k in ('rls','forceRls','inherits','rules')):raise SourceInstallError('Ordinary permanent owner-controlled tables without RLS/rules/inheritance required')
    if type(value.get('oid'))is not int or value['oid']<=0:raise SourceInstallError('Invalid table OID')
    columns=value.get('columns')or[];expected=[c.name for c in table.columns]+([VERSION_COLUMN]if installed else[])
    if [c.get('name')for c in columns]!=expected:raise SourceInstallError('Complete ordered configured column inventory required')
    kinds={'int64':{20,21,23},'bool':{16},'text':{25,1043}}
    for configured,actual in zip(table.columns,columns):
        if actual.get('oid')not in kinds[configured.type]or actual.get('typeKind')!='b'or actual.get('typeSchema')!='pg_catalog'or actual.get('elementType')!=0 or actual.get('generated')!=''or actual.get('identity')!='':raise SourceInstallError('Unsupported source column type or generation')
        if configured.type=='text'and (actual.get('collation')!='C'or actual.get('collationSchema')!='pg_catalog'or actual.get('collationDeterministic')is not True):raise SourceInstallError('Explicit deterministic pg_catalog C collation required')
    primary=value.get('primaryKeys')or[]
    if len(primary)!=1 or primary[0].get('columns')!=[table.primary_key]or primary[0].get('keys')!=1 or any(primary[0].get(k)is not True for k in ('valid','ready','immediate')):raise SourceInstallError('One immediate valid single-column primary key required')
    if not next(c for c in columns if c['name']==table.primary_key)['notNull']:raise SourceInstallError('Non-null primary key required')
    triggers=value.get('triggers')or[]
    if not installed:
        if triggers:raise SourceInstallError('Existing user triggers need a separate semantics profile')
        return value['oid']
    metadata=columns[-1]
    if metadata.get('oid')!=20 or metadata.get('notNull')is not True or metadata.get('generated')!=''or metadata.get('identity')!=''or metadata.get('default')is not None:raise SourceInstallError('Installed version column differs')
    indexes=value.get('uniqueIndexes')or[]
    if not any(i.get('columns')==[VERSION_COLUMN]and i.get('keys')==1 and all(i.get(k)is True for k in ('valid','ready','immediate','noPredicate','noExpression'))for i in indexes):raise SourceInstallError('Unique installed version index missing')
    before,after=function_bodies(policy);expected_triggers={BEFORE_TRIGGER:(23,'before_write',before),AFTER_TRIGGER:(29,'after_write',after)}
    if len(triggers)!=2 or {t.get('name')for t in triggers}!=set(expected_triggers):raise SourceInstallError('Trigger inventory differs')
    args=(table.primary_key.encode('utf8')+bytes([0])).hex()
    for trigger in triggers:
        kind,function,body=expected_triggers[trigger['name']]
        if trigger.get('type')!=kind or trigger.get('enabled')!='A'or trigger.get('argsHex')!=args or trigger.get('noCondition')is not True or trigger.get('noColumns')is not True:raise SourceInstallError('Trigger is disabled, filtered or differently scoped')
        if trigger.get('functionSchema')!=policy.namespace or trigger.get('function')!=function or trigger.get('body')!=body or trigger.get('owner')!=owner or trigger.get('securityDefiner')is not True or trigger.get('returnType')!=2279 or trigger.get('volatile')!='v'or trigger.get('parallel')!='u'or trigger.get('argCount')!=0:raise SourceInstallError('Source function identity/body differs')
        settings=trigger.get('settings')or[]
        settings_map=dict(item.split('=',1)for item in settings if '='in item)
        if len(settings)!=2 or set(settings_map)!={'search_path','standard_conforming_strings'}or settings_map['standard_conforming_strings']!='on'or [x.strip()for x in settings_map['search_path'].split(',')]!=['pg_catalog','pg_temp']:raise SourceInstallError('Unsafe source function settings')
    return value['oid']


class _Control:
    """Only installer-owned SQL. Never wrap a business cursor with this class."""
    def __init__(self,connection,log):self.connection,self.log=connection,log
    def command(self,query_id,sql,params=None,*,max_rows=256):
        request=self.log.count+1
        self.log.append({'kind':'source-control-request','queryId':query_id,'sql':sql,'parameters':params,'transactionStatusBefore':int(self.connection.info.transaction_status)})
        try:cursor=self.connection.execute(sql,params)
        except BaseException as error:
            try:self.log.append({'kind':'source-control-error','requestSeq':request,'errorClass':type(error).__name__,'sqlstate':getattr(error,'sqlstate',None)})
            except BaseException:pass
            raise
        result=cursor.pgresult
        status=int(result.status);fields=int(result.nfields);rows=int(result.ntuples)
        if rows>max_rows or fields>1:raise SourceInstallError('Control result exceeds bound')
        raw=[];size=0
        for r in range(rows):
            cells=[]
            for col in range(fields):
                cell=result.get_value(r,col);size+=len(cell)if cell else 0
                if size>128*1024:raise SourceInstallError('Control raw result byte budget exhausted')
                cells.append(None if cell is None else base64.b64encode(cell).decode('ascii'))
            raw.append(cells)
        decoded=cursor.fetchall()if fields else[]
        if fields:
            if status!=2 or result.ftype(0)!=25 or result.fformat(0)!=0 or len(decoded)!=rows:raise SourceInstallError('Control query must return actual native text rows')
            for index,row in enumerate(decoded):
                if type(row)is not tuple or len(row)!=1 or type(row[0])is not str or base64.b64encode(row[0].encode('utf8')).decode('ascii')!=raw[index][0]:raise SourceInstallError('Decoded catalog result differs from the native result')
        tag=result.command_status.decode('ascii')if result.command_status else None
        payload={'kind':'source-control','requestSeq':request,'transactionStatusAfter':int(self.connection.info.transaction_status),'queryId':query_id,'sql':sql,'parameters':params,'native':{'status':status,'tag':tag,'fields':fields,'columns':[{'oid':result.ftype(0),'format':result.fformat(0)}]if fields else[],'rows':raw},'decodedRows':[list(row)for row in decoded]}
        self.log.append(payload)
        return [json.loads(row[0])for row in decoded],payload


def _one(control,query_id,sql,params=None):
    rows,_=control.command(query_id,sql,params,max_rows=1)
    if len(rows)!=1:raise SourceInstallError('Expected one catalog row: '+query_id)
    return rows[0]



def initial_snapshot_sql(table):
    """One bounded native JSON cell; oversized rows are rejected, never truncated."""
    text_limits=[f'pg_catalog.octet_length(t.{identifier(column.name)})>65536'for column in table.columns if column.type=='text']
    too_large=' OR '.join(text_limits)if text_limits else'FALSE'
    row='pg_catalog.to_jsonb(t)'
    return (f"SELECT CASE WHEN ({too_large}) THEN pg_catalog.jsonb_build_object('kind','initial-row-budget') "
      +f"WHEN pg_catalog.octet_length({row}::text)>65536 THEN pg_catalog.jsonb_build_object('kind','initial-row-budget') "
      +f"ELSE pg_catalog.jsonb_build_object('kind','initial-row','row',{row}) END::text FROM {target(table)} t WHERE t.{identifier(VERSION_COLUMN)}>%s ORDER BY t.{identifier(VERSION_COLUMN)} LIMIT 1")


def install_configured_source(connection,output,config,policy,*,opt_in=False):
    """One explicit owned installation attempt. Never promotes source facts."""
    if opt_in is not True:raise ValueError('Explicit opt_in=True is required before any migration')
    if type(config)is not SQLCaptureConfig or type(policy)is not SourceInstallPolicy:raise ValueError('Immutable config and policy required')
    if not 1<=len(config.tables)<=16:raise ValueError('Initial installer supports 1..16 arbitrary configured tables')
    if any(VERSION_COLUMN in [c.name for c in t.columns]for t in config.tables):raise ValueError('Private version column collides with a business column')
    if not connection.autocommit or int(connection.info.transaction_status)!=0:raise ValueError('A dedicated idle autocommit control connection is required')
    path=Path(output).resolve();path.mkdir(parents=True,exist_ok=False)
    log=_LifecycleLog(path/'source-install.jsonl',max_bytes=policy.max_log_bytes,max_records=65536)
    control=_Control(connection,log);catalogs=[];initial_rows=0;initial_digest=hashlib.sha256();versions=set();confirmed=False;commit_requested=False
    receipt={'format':'configured-source-installation/v1','config':config.to_dict(),'policy':policy.to_dict(),'configSha256':config.sha256,'sourceFactsProduced':False,'sourceAuthenticated':False,'moonbitCatalogVerified':False,'catalogVerified':False,'initialSnapshotVerified':False,'writerWindowVerified':False,'driverFetchVerified':False,'status':'started','gaps':['complete-driver-source-projection-not-connected','writer-window-not-closed','privileged-DDL-exclusion-not-proven']}
    try:
        _,begin_ack=control.command('begin','BEGIN')
        if begin_ack['native']['tag']!='BEGIN'or begin_ack['native']['status']!=1 or begin_ack['native']['fields']!=0 or begin_ack['transactionStatusAfter']!=2:raise SourceInstallError('Explicit source transaction was not acknowledged')
        control.command('standard-strings','SET LOCAL standard_conforming_strings=on')
        lock='LOCK TABLE '+','.join(target(t)for t in sorted(config.tables,key=lambda t:(t.schema,t.table)))+' IN ACCESS EXCLUSIVE MODE NOWAIT'
        _,lock_ack=control.command('install-lock',lock)
        if lock_ack['native']['tag']!='LOCK TABLE'or lock_ack['native']['status']!=1 or lock_ack['native']['fields']!=0:raise SourceInstallError('Installation table lock was not acknowledged')
        environment=_one(control,'environment',ENVIRONMENT_SQL,(list(policy.writers),));owner=verify_environment(policy,environment);receipt['environment']=environment
        oids=[]
        for table in config.tables:
            catalog=_one(control,'before-catalog',TABLE_CATALOG_SQL,(table.schema,table.table));oids.append(verify_table_catalog(table,policy,owner,catalog))
            for writer in policy.writers:
                row=_one(control,'business-writer-privileges',PERMISSIONS_SQL,(writer,target(table),writer,target(table),writer,target(table),writer,owner))
                if row.get('trigger')is not False or row.get('truncate')is not False or row.get('ownerMembership')is not False:raise SourceInstallError('Writer can bypass row-only source scope')
        held=_one(control,'held-install-locks',LOCKS_SQL,(oids,))
        locks=held.get('locks')or[]
        if held.get('pid')!=environment.get('backendPid')or {row.get('relation')for row in locks if row.get('mode')=='AccessExclusiveLock'and row.get('granted')is True}!=set(oids):raise SourceInstallError('Actual initialization lock inventory is incomplete')
        receipt['initializationLocks']=held
        for statement in installation_ddl(config,policy):control.command('install-ddl',statement)
        q=identifier(policy.namespace);v=identifier(VERSION_COLUMN)
        for table,oid in zip(config.tables,oids):
            control.command('install-scope',f'INSERT INTO {q}.scope VALUES(%s,%s,%s,%s,%s)',(oid,table.schema,table.table,table.primary_key,config.sha256))
            t=target(table);pk=identifier(table.primary_key)
            control.command('initial-ledger',f"INSERT INTO {q}.effects(version,base_version,relation_oid,operation,writer_xid,writer_login,writer_pid,row_key,old_key,row_values) SELECT {v},NULL,%s,'INITIAL',pg_catalog.pg_current_xact_id()::text,SESSION_USER,pg_catalog.pg_backend_pid(),pg_catalog.to_jsonb(t)->%s,NULL,pg_catalog.to_jsonb(t)-%s FROM {t} t",(oid,table.primary_key,VERSION_COLUMN))
            last=0;count=0
            while True:
                query=initial_snapshot_sql(table)
                rows,_=control.command('initial-snapshot',query,(last,),max_rows=1)
                for observed in rows:
                    if set(observed)!={'kind','row'}or observed.get('kind')!='initial-row'or not isinstance(observed.get('row'),dict):raise SourceInstallError('Initial row exceeds the native source snapshot bound')
                    row=observed['row']
                    version=row.get(VERSION_COLUMN)
                    if type(version)is not int or version<=0 or version in versions:raise SourceInstallError('Initial installed version is not unique')
                    if row.get(table.primary_key)is None:raise SourceInstallError('Initial key is absent')
                    if any(row.get(column.name)is None for column in table.columns):raise SourceInstallError('NULL initial business values are outside the current fact model')
                    versions.add(version);last=version;count+=1;initial_rows+=1
                    if initial_rows>policy.max_initial_rows:raise SourceInstallError('Initial snapshot row budget exhausted')
                    initial_digest.update(canonical({'schema':table.schema,'table':table.table,'row':row}).encode('utf8')+b'\n')
                if not rows:break
            after=_one(control,'installed-catalog',TABLE_CATALOG_SQL,(table.schema,table.table));verify_table_catalog(table,policy,owner,after,installed=True)
            catalogs.append({'catalog':after,'initialRows':count})
        source_catalog=_one(control,'source-catalog',SOURCE_CATALOG_SQL,(policy.namespace,));verify_source_catalog(policy,owner,source_catalog)
        receipt['sourceCatalog']=source_catalog
        scope_rows,_=control.command('source-scope',f"SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint,'relation_schema',s.relation_schema,'relation_table',s.relation_table,'primary_key',s.primary_key,'config_sha256',s.config_sha256)::text FROM {q}.scope s ORDER BY relation_schema,relation_table")
        expected_scope=sorted([{'relation_oid':oid,'relation_schema':table.schema,'relation_table':table.table,'primary_key':table.primary_key,'config_sha256':config.sha256}for table,oid in zip(config.tables,oids)],key=lambda row:(row['relation_schema'],row['relation_table']))
        if scope_rows!=expected_scope:raise SourceInstallError('Source scope rows differ from the configured tables')
        receipt['sourceScope']=scope_rows
        ledger=_one(control,'initial-ledger-count',f"SELECT pg_catalog.jsonb_build_object('rows',count(*),'nonInitial',count(*) FILTER(WHERE operation<>'INITIAL'))::text FROM {q}.effects")
        if ledger!={'rows':initial_rows,'nonInitial':0}:raise SourceInstallError('Initial effect ledger is not complete')
        receipt['initialLedger']=ledger
        before_status=int(connection.info.transaction_status)
        log.append({'kind':'source-install-commit-request','statusBefore':before_status})
        commit_requested=True
        _,ack=control.command('installation-commit','COMMIT')
        confirmed=before_status==2 and int(connection.info.transaction_status)==0 and ack['native']['tag']=='COMMIT'and ack['native']['status']==1 and ack['native']['fields']==0
        if not confirmed:raise SourceInstallError('COMMIT request did not supply a confirmed commit response')
        receipt.update(status='installed-components-only',catalogVerified=True,initialSnapshotVerified=True,actualCommitConfirmed=True,initialRows=initial_rows,initialSnapshotSha256=initial_digest.hexdigest(),tables=catalogs)
    except BaseException as error:
        receipt.update(status=('installation-commit-unknown'if commit_requested and not confirmed else'failed')if not confirmed else'commit-confirmed-postcheck-failed',errorClass=type(error).__name__,error=str(error),actualCommitConfirmed=confirmed)
        if commit_requested and not confirmed:receipt['gaps'].append('inspect-owned-schema-before-any-retry')
        try:connection.rollback()
        except BaseException:receipt['gaps'].append('rollback-outcome-unknown')
        try:log.append({'kind':'source-install-failed','errorClass':type(error).__name__,'message':str(error),'confirmed':confirmed})
        except BaseException:pass
        raise
    finally:
        try:receipt['log']=log.close()
        except BaseException as error:
            receipt['log']={'sealed':False};receipt['gaps'].append('installation-log-unsealed');receipt.update(sourceFactsProduced=False,catalogVerified=False,initialSnapshotVerified=False,status='installed-unverified-log'if confirmed else'recording-failed')
        if not receipt['log'].get('sealed'):
            receipt.update(catalogVerified=False,initialSnapshotVerified=False)
        active_exception=sys.exc_info()[0]is not None
        try:(path/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        except BaseException as error:
            if not active_exception:raise SourceInstallError('Installation result could not be retained; inspect the owned schema before retry')from error
    return SourceInstallation(canonical(receipt))
