"""Exact opt-in PostgreSQL18 model plans; no SQL guessing or semantic input.

The fixed protocol is intentionally small. Identifiers and predicate structure
are configuration; predicate values remain the original DBAPI parameters.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

PROFILE = 'pg18-configured-models/1'
FORMAT = 'moontxnwitness-model-profile-source/v1'
IDENT = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
OPS = {'eq':'=', 'lt':'<', 'le':'<=', 'gt':'>', 'ge':'>='}
TYPES = {'id':'int64', 'balance':'int64', 'active':'bool', 'region':'text'}


def quote(value):
    if type(value) is not str or not IDENT.fullmatch(value):
        raise ValueError('Lowercase bounded SQL identifiers required')
    return '"'+value+'"'


@dataclass(frozen=True)
class ModelScope:
    schema: str
    model: str
    keys: tuple
    predicates: tuple = ()

    def __post_init__(self):
        quote(self.schema)
        if self.model not in ('append-list-v1','relation-set-v1'):
            raise ValueError('One supported model per source window')
        if type(self.keys) is not tuple or not 1 <= len(self.keys) <= 8 or len(set(self.keys)) != len(self.keys):
            raise ValueError('One to eight distinct immutable domain keys required')
        if self.model == 'append-list-v1':
            if self.predicates or any(type(k) is not str or not IDENT.fullmatch(k) for k in self.keys):
                raise ValueError('List domain uses lowercase identifiers and no predicates')
        elif any(type(k) is not int or not -(1<<63) <= k < 1<<63 for k in self.keys):
            raise ValueError('Relation domain uses exact signed int64 primary keys')
        if type(self.predicates) is not tuple or len(self.predicates)>8:
            raise ValueError('At most eight configured read plans')
        for terms in self.predicates:
            if type(terms) is not tuple or not 1 <= len(terms) <= 8:
                raise ValueError('One to eight ordered AND terms per read plan')
            for column,op in terms:
                if column not in TYPES or op not in OPS or TYPES[column]=='bool' and op!='eq':
                    raise ValueError('Unsupported configured predicate')
        if len(set(self.predicates)) != len(self.predicates):raise ValueError('Duplicate predicate plans')

    @property
    def target(self):return quote(self.schema)+'."business"'
    def owned(self,name):return quote(self.schema)+'.'+quote(name)
    def config(self):
        return {'schema':self.schema,'model':self.model,'keys':list(self.keys),
                'predicates':[[list(term) for term in terms] for terms in self.predicates]}


@dataclass(frozen=True)
class ModelPlan:
    operation: str
    sql: str
    executed_sql: str
    columns: int
    predicate: tuple = ()


def plans(scope):
    t=scope.target;q=quote(scope.schema)
    if scope.model=='append-list-v1':
        read='SELECT items FROM '+t+' WHERE key=%s'
        append='UPDATE '+t+' SET items=items || %s::jsonb WHERE key=%s RETURNING items'
        return (ModelPlan('list-read',read,read,1),ModelPlan('list-append',append,append,1))
    fields='id,balance,active,region'
    read='SELECT '+fields+' FROM '+t+' WHERE id=%s'
    insert='INSERT INTO '+t+'(id,balance,active,region) VALUES(%s,%s,%s,%s) RETURNING '+fields
    update='UPDATE '+t+' SET balance=%s,active=%s,region=%s WHERE id=%s RETURNING '+fields
    delete='DELETE FROM '+t+' WHERE id=%s RETURNING '+fields
    result=[ModelPlan('row-read',read,read.replace('SELECT '+fields,'SELECT '+fields+',version'),4,(('id','eq'),)),
        ModelPlan('row-insert',insert,insert+',version,'+q+'."predecessor"(version)',4),
        ModelPlan('row-update',update,update[:update.index(' RETURNING ')]+
            ' RETURNING WITH (OLD AS o,NEW AS n) n.id,n.balance,n.active,n.region,n.version,o.version',4),
        ModelPlan('row-delete',delete,delete[:delete.index(' RETURNING ')]+
            ' RETURNING WITH (OLD AS o,NEW AS n) o.id,o.balance,o.active,o.region,'+q+'."delete_token"(o.id,o.version),o.version',4)]
    for predicate in scope.predicates:
        clauses=[quote(column)+(' COLLATE "C"' if TYPES[column]=='text' else '')+OPS[op]+'%s' for column,op in predicate]
        sql='SELECT '+fields+' FROM '+t+' WHERE '+' AND '.join(clauses)+' ORDER BY id'
        result.append(ModelPlan('row-read',sql,sql.replace('SELECT '+fields,'SELECT '+fields+',version'),4,predicate))
    return tuple(result)


def validate_parameters(scope,plan,params):
    if type(params) not in (tuple,list):raise ValueError('Original positional parameters required')
    params=tuple(params)
    def integer(v):return type(v) is int and -(1<<63)<=v<1<<63
    def text(v):return type(v) is str and '\x00' not in v and len(v)<=1024 and not any(0xd800<=ord(c)<=0xdfff for c in v)
    if scope.model=='append-list-v1':
        import json
        if plan.operation=='list-read':
            if len(params)!=1 or params[0] not in scope.keys:raise ValueError('List key outside installed domain')
        else:
            if len(params)!=2 or params[1] not in scope.keys or type(params[0]) is not str:raise ValueError('Single JSON append plus known key required')
            items=json.loads(params[0])
            if type(items) is not list or len(items)!=1 or type(items[0]) is not dict or set(items[0])!={'id','value'}:
                raise ValueError('Exactly one append item required')
            if not text(items[0]['id']) or not 1<=len(items[0]['id'])<=128 or not text(items[0]['value']):
                raise ValueError('Unique bounded append identity and string value required')
    elif plan.operation=='row-read':
        if len(params)!=len(plan.predicate):raise ValueError('Exact predicate parameter arity required')
        for (column,_),value in zip(plan.predicate,params):
            if not {'int64':integer,'bool':lambda v:type(v) is bool,'text':text}[TYPES[column]](value):
                raise ValueError('Canonical supported predicate value required')
    else:
        key=params[0] if plan.operation=='row-insert' else params[-1] if params else None
        if not integer(key) or key not in scope.keys:raise ValueError('Write key outside installed domain')
        values=params[1:] if plan.operation=='row-insert' else params[:-1]
        if plan.operation=='row-delete':
            if len(params)!=1:raise ValueError('Exact delete parameter layout required')
        elif len(params)!=4 or not integer(values[0]) or type(values[1]) is not bool or not text(values[2]):
            raise ValueError('Exact int64/bool/text row parameters required')
    return params


def ddl(scope):
    q=quote(scope.schema);t=scope.target;state=scope.owned('state');effects=scope.owned('effects')
    if scope.model=='append-list-v1':
        before=f'''BEGIN
IF TG_OP<>'UPDATE' OR NEW.key IS DISTINCT FROM OLD.key OR jsonb_typeof(NEW.items)<>'array' OR jsonb_array_length(NEW.items)<>jsonb_array_length(OLD.items)+1 OR NEW.items- (jsonb_array_length(NEW.items)-1) IS DISTINCT FROM OLD.items THEN RAISE EXCEPTION 'only one append is supported'; END IF;
IF jsonb_typeof(NEW.items->-1)<>'object' OR NOT (NEW.items->-1 ?& ARRAY['id','value']) OR (SELECT count(*) FROM jsonb_object_keys(NEW.items->-1))<>2 OR jsonb_typeof(NEW.items->-1->'id')<>'string' OR jsonb_typeof(NEW.items->-1->'value')<>'string' THEN RAISE EXCEPTION 'invalid append item'; END IF;
INSERT INTO {scope.owned('identities')}(id,key,value) VALUES(NEW.items->-1->>'id',NEW.key,NEW.items->-1->>'value');
RETURN NEW; END'''
        after=f'''BEGIN INSERT INTO {effects}(key,item,items) VALUES(NEW.key,NEW.items->-1,NEW.items); RETURN NEW; END'''
        return [f'CREATE SCHEMA {q}',f'CREATE TABLE {t}(key text COLLATE "C" PRIMARY KEY,items jsonb NOT NULL)',
            f'CREATE TABLE {scope.owned("identities")}(id text COLLATE "C" PRIMARY KEY,key text NOT NULL REFERENCES {t}(key),value text NOT NULL)',
            f'CREATE TABLE {effects}(key text NOT NULL,item jsonb NOT NULL,items jsonb NOT NULL)',
            f'CREATE FUNCTION {q}."before"() RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model${before}$model$',
            f'CREATE FUNCTION {q}."after"() RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model${after}$model$',
            f'CREATE TRIGGER model_before BEFORE INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION {q}."before"()',
            f'CREATE TRIGGER model_after AFTER UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION {q}."after"()']
    candidates=scope.owned('candidates');pred=q+'."predecessor"';deleted=q+'."delete_token"'
    image=lambda a:"jsonb_build_object('balance',"+a+".balance::text,'active',"+a+".active,'region',"+a+".region)"
    before=f'''DECLARE k bigint; p uuid; live boolean; v uuid; BEGIN
IF TG_OP<>'DELETE' AND (NEW.id IS NULL OR NEW.balance IS NULL OR NEW.active IS NULL OR NEW.region IS NULL) THEN RETURN NEW; END IF;
IF TG_OP='UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN RAISE EXCEPTION 'primary key mutation'; END IF;
k:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
SELECT version,present INTO p,live FROM {state} WHERE key=k FOR UPDATE;
IF NOT FOUND THEN RAISE EXCEPTION 'key outside configured domain'; END IF;
IF TG_OP<>'INSERT' AND (NOT live OR p IS DISTINCT FROM OLD.version) THEN RAISE EXCEPTION 'source mismatch'; END IF;
v:=gen_random_uuid();
INSERT INTO {candidates} VALUES(v,k,p,TG_OP,live,TG_OP<>'DELETE',CASE WHEN TG_OP='DELETE' THEN NULL ELSE {image('NEW')} END);
IF TG_OP='DELETE' THEN RETURN OLD; ELSE NEW.version:=v; RETURN NEW; END IF;
END'''
    predecessor=f'''DECLARE n integer; p uuid; BEGIN SELECT count(*),min(predecessor::text)::uuid INTO n,p FROM {candidates} WHERE version=v; IF n<>1 THEN RAISE EXCEPTION 'predecessor not unique'; END IF; RETURN p; END'''
    delete=f'''DECLARE n integer; v uuid; BEGIN SELECT count(*),min(version::text)::uuid INTO n,v FROM {candidates} WHERE key=k AND predecessor=p AND action='DELETE'; IF n<>1 THEN RAISE EXCEPTION 'delete not unique'; END IF; RETURN v; END'''
    after=f'''DECLARE v uuid; c record; n integer; BEGIN
v:=CASE WHEN TG_OP='DELETE' THEN {deleted}(OLD.id,OLD.version) ELSE NEW.version END;
SELECT * INTO c FROM {candidates} WHERE version=v;
IF NOT FOUND OR c.action<>TG_OP OR c.key IS DISTINCT FROM (CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END) OR c.image IS DISTINCT FROM (CASE WHEN TG_OP='DELETE' THEN NULL ELSE {image('NEW')} END) THEN RAISE EXCEPTION 'actual effect mismatch'; END IF;
IF TG_OP='INSERT' AND c.old_present THEN RAISE EXCEPTION 'insert presence mismatch'; END IF;
UPDATE {state} SET version=v,present=(TG_OP<>'DELETE') WHERE key=c.key AND version IS NOT DISTINCT FROM c.predecessor AND present=c.old_present;
GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'effect state mismatch'; END IF;
INSERT INTO {effects} SELECT * FROM {candidates} WHERE version=v;
IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END'''
    result=[f'CREATE SCHEMA {q}',f'CREATE TABLE {t}(id bigint PRIMARY KEY,balance bigint NOT NULL,active boolean NOT NULL,region text COLLATE "C" NOT NULL,version uuid NOT NULL)',
        f'CREATE TABLE {state}(key bigint PRIMARY KEY,version uuid,present boolean NOT NULL)',
        f'CREATE TABLE {candidates}(version uuid PRIMARY KEY,key bigint NOT NULL,predecessor uuid,action text NOT NULL,old_present boolean NOT NULL,new_present boolean NOT NULL,image jsonb)',
        f'CREATE TABLE {effects}(LIKE {candidates} INCLUDING ALL)',f'CREATE UNIQUE INDEX ON {effects}(predecessor) WHERE predecessor IS NOT NULL']
    for name,args,returns,body in [('before','','trigger',before),('after','','trigger',after),('predecessor','v uuid','uuid',predecessor),('delete_token','k bigint,p uuid','uuid',delete)]:
        result.append(f'CREATE FUNCTION {q}.{quote(name)}({args}) RETURNS {returns} LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model${body}$model$')
    result += [f'CREATE TRIGGER model_before BEFORE INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION {q}."before"()',
        f'CREATE TRIGGER model_after AFTER INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION {q}."after"()']
    return result


def control_sql(scope):
    t=scope.target;q=quote(scope.schema)
    owned=['business','identities','effects'] if scope.model=='append-list-v1' else ['business','state','candidates','effects']
    lock='LOCK TABLE '+','.join(scope.owned(n) for n in owned)+' IN ACCESS EXCLUSIVE MODE'
    snapshot=('SELECT jsonb_build_object(\'key\',key,\'items\',items) FROM '+t+' ORDER BY key' if scope.model=='append-list-v1' else
        "SELECT jsonb_build_object('key',id::text,'version',version::text,'values',jsonb_build_object('balance',balance::text,'active',active,'region',region)) FROM "+t+' ORDER BY id')
    ledger=("SELECT jsonb_build_object('key',key,'item',item,'items',items) FROM "+scope.owned('effects')+' ORDER BY key,jsonb_array_length(items)' if scope.model=='append-list-v1' else
        "SELECT jsonb_build_object('key',key::text,'version',version::text,'predecessor',predecessor::text,'action',action,'oldPresent',old_present,'newPresent',new_present,'values',image) FROM "+scope.owned('effects')+' ORDER BY key,version')
    state=("SELECT jsonb_build_object('id',id,'key',key,'value',value) FROM "+scope.owned('identities')+' ORDER BY id' if scope.model=='append-list-v1' else
        "SELECT jsonb_build_object('key',key::text,'version',version::text,'present',present) FROM "+scope.owned('state')+' ORDER BY key')
    catalog="SELECT jsonb_build_object('name',p.proname,'body',p.prosrc,'securityDefiner',p.prosecdef,'volatility',p.provolatile,'config',p.proconfig,'arguments',pg_get_function_identity_arguments(p.oid),'return',p.prorettype::regtype::text,'language',l.lanname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname=%s ORDER BY p.proname"
    triggers="SELECT jsonb_build_object('name',t.tgname,'function',p.proname,'type',t.tgtype,'enabled',t.tgenabled,'args',encode(t.tgargs,'hex'),'internal',t.tgisinternal,'noPredicate',t.tgqual IS NULL) FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid WHERE t.tgrelid=%s::regclass ORDER BY t.tgname"
    return {'lock':lock,'snapshot':snapshot,'ledger':ledger,'state':state,'catalog':catalog,'triggers':triggers,
        'locale':"SELECT jsonb_build_object('collate',datcollate,'ctype',datctype) FROM pg_database WHERE datname=current_database()"}
