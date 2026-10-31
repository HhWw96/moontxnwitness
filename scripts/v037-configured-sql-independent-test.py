"""Independent AST-candidate boundaries; no driver, SQL, database or original tests executed."""
from pathlib import Path
import sys,hashlib,json,dataclasses,subprocess,importlib.metadata,csv,base64,concurrent.futures
ROOT=Path(__file__).resolve().parents[1]; sys.dont_write_bytecode=True
DEP=ROOT/'artifacts/sqlglot-deps'; sys.path.insert(0,str(ROOT/'integrations/python'));sys.path.insert(0,str(DEP))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
freeze_path=ROOT/'artifacts/v037-configured-sql-freeze.json';freeze=json.loads(freeze_path.read_text(encoding='utf8'))
protected={**freeze['fileSha256'],**freeze['originalProtectedSha256']}
for name,digest in protected.items():assert sha(ROOT/name)==digest,name

def source_map():return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src').rglob('*')) if p.is_file()}
before=source_map()
assert 'sqlglot' not in sys.modules
from moontxnwitness_capture import configured_sql as cs
assert 'sqlglot' not in sys.modules,'Optional parser imported at module import'
assert not any(x=='psycopg' or x.startswith('psycopg.') or x=='sqlalchemy' or x.startswith('sqlalchemy.') for x in sys.modules)
OUT=ROOT/'artifacts/v037-configured-sql-independent';OUT.mkdir(parents=True,exist_ok=True)
rows=[];observed=None

def check(name,fn):
 global observed
 observed=None
 try:fn();rows.append({'name':name,'passed':True})
 except Exception as error:rows.append({'name':name,'passed':False,'error':repr(error),'observed':observed})

def eq(a,b):assert a==b,(a,b)
def err(fn,kind=cs.RecognitionError):
 try:fn()
 except kind as e:
  if isinstance(e,cs.RecognitionError):assert type(e.code) is str and e.code
  return e
 raise AssertionError('Expected conservative rejection')

def column(n,t):return cs.ColumnConfig(n,t,cs.TEXT_COMPARISON if t=='text' else None)
tables=(
 cs.TableConfig('money','accounts2','account_no',(column('account_no','int64'),column('balance','int64'),column('enabled','bool'),column('memo','text'),column('revision','int64')),'point-register-v1'),
 cs.TableConfig('settings','key_values','lookup',(column('lookup','text'),column('enabled','bool'),column('caption','text')),'append-list-v1'),
 cs.TableConfig('工程.域','配置"集','项号',(column('项号','int64'),column('文字','text'),column('数量','int64'),column('有效','bool'),column('owner','text'),column('stamp','int64')),'relation-set-v1'),
)
config=cs.SQLCaptureConfig(tables);parser=cs.ConfiguredSQLParser(config)
q=lambda x:'"'+x.replace('"','""')+'"'
def val(c,index=1):return (9007199254740993+index if c.type=='int64' else index%2==1 if c.type=='bool' else 'driver-secret-值-'+str(index))
def candidate(sql,config_parser=parser):
 global observed
 p=config_parser.recognize(sql);observed=p.to_dict()
 for flag in ['databaseSyntaxValidated','sourceAuthenticated','captureFactsProduced','moonbitProjectionVerified','returningIsPredicateRead']:eq(observed[flag],False)
 eq(p.original_sql,sql);eq(observed['sqlSha256'],hashlib.sha256(sql.encode()).hexdigest());eq(observed['format'],'moontxnwitness-sql-ast-candidate/v1');assert 'traceSchema' not in observed
 assert 'same-statement-or-native-observed-read-version-identity' in observed['requiredProofs']
 return p

for t in tables:
 full=q(t.schema)+'.'+q(t.table);pk=q(t.primary_key);key=val(t.column(t.primary_key));cols=','.join(q(c.name) for c in t.columns);slots=','.join('%s' for c in t.columns)
 def crud(t=t,full=full,pk=pk,key=key,cols=cols,slots=slots):
  p=candidate(f'SELECT * FROM {full} WHERE {pk}=%s');eq(len(p.projections),len(t.columns));eq(p.table,t);eq(p.bind((key,))[0][1],key)
  p=candidate(f'INSERT INTO {full} ({cols}) VALUES ({slots}),({slots}) RETURNING {pk}');values=tuple(val(c,i+1) for i in range(2) for c in t.columns);eq(tuple(v for _,v in p.bind(values)),values);eq(len(p.insert_rows),2);eq(len(p.parameters),2*len(t.columns))
  changed=t.columns[1];p=candidate(f'UPDATE {full} SET {q(changed.name)}=%s WHERE {pk}=%s RETURNING {q(changed.name)} AS "same output",{pk}');bound=p.bind((val(changed),key));eq(bound[0][0].value,0);eq(bound[1][0].value,1);eq([r.output_name for r in p.returning],['same output',t.primary_key])
  p=candidate(f'DELETE FROM {full} WHERE {pk}=%s RETURNING *');eq(len(p.returning),len(t.columns));eq(len(p.bind((key,))),1)
 check('independent CRUD through same parser: '+t.schema+'.'+t.table,crud)

check('actual optional parser origin and version',lambda:(eq(importlib.metadata.version('sqlglot'),'30.26.0'),__import__('sqlglot').__file__ and eq(Path(__import__('sqlglot').__file__).resolve().is_relative_to(DEP.resolve()),True)))
check('more than eight runtime keys need no configuration or SQL changes',lambda:[eq(candidate('SELECT lookup FROM settings.key_values WHERE lookup=%s').bind(('variable-key-'+str(i),))[0][1],'variable-key-'+str(i)) for i in range(257)])
check('named repeated placeholders retain lexical order and exact typed value use',lambda:(lambda p:(eq([x.value for x in p.parameters],['key','key']),eq([v for _,v in p.bind({'key':'named-secret'})],['named-secret','named-secret']),err(lambda:p.bind({'Key':'named-secret'})),err(lambda:p.bind({'key':'v','extra':'v'}))))(candidate('SELECT lookup,caption FROM settings.key_values WHERE lookup >= %(key)s AND lookup <= %(key)s')))
check('parameter assignment order precedes WHERE; original alias spelling and SQL retained',lambda:(lambda p:(eq([x.value for x in p.parameters],[0,1,2]),eq([x.type for x in p.parameters],['text','bool','text']),eq([v for _,v in p.bind(('caption-secret',False,'primary-secret'))],['caption-secret',False,'primary-secret'])))(candidate('UPDATE settings.key_values AS z SET caption=%s,enabled=%s WHERE z.lookup=%s RETURNING z.lookup AS "Key Alias"')))
check('comments do not create bind slots; string-literal percent needs None',lambda:(lambda p:(eq(len(p.parameters),0),eq(p.bind(None),()),err(lambda:p.bind(()))))(candidate("SELECT lookup FROM settings.key_values WHERE caption='literal %s text' /* %(fake)s */")))
check('percent escapes next to driver binds remain conservative',lambda:err(lambda:parser.recognize("SELECT lookup FROM settings.key_values WHERE lookup=%s AND caption='100%%'")))
check('mixed named positional or non-s drivers are rejected',lambda:[err(lambda s=s:parser.recognize(s)) for s in ['SELECT lookup FROM settings.key_values WHERE lookup=%s AND caption=%(v)s','SELECT lookup FROM settings.key_values WHERE lookup=%b','SELECT lookup FROM settings.key_values WHERE lookup=%t','SELECT lookup FROM settings.key_values WHERE lookup=$1','SELECT lookup FROM settings.key_values WHERE lookup=:key','SELECT lookup FROM settings.key_values WHERE lookup=?']])
check('quoted Unicode names are literal; unquoted Unicode has no guessed folding',lambda:(eq(candidate('SELECT "项号","文字" FROM "工程.域"."配置""集" WHERE "项号"=%s').table,tables[2]),err(lambda:parser.recognize('SELECT 项号 FROM "工程.域"."配置""集"'))))
check('unqualified table requires configured schema proof, not lookup guessing',lambda:(err(lambda:parser.recognize('SELECT lookup FROM key_values')),eq(candidate('SELECT lookup FROM key_values',cs.ConfiguredSQLParser(cs.SQLCaptureConfig(tables,default_schema='settings'))).schema_resolution,'configured-default-schema-requires-session-proof')))
check('int64 literal preserves exact decimal text beyond JavaScript exact integer range',lambda:(lambda p:(eq(p.predicates[0].value.value,9223372036854775807),eq(p.to_dict()['predicates'][0]['value']['value'],'9223372036854775807')))(candidate('SELECT account_no FROM money.accounts2 WHERE account_no=9223372036854775807')))
check('wrong implicit parameter casts are never accepted',lambda:[err(lambda p=p,v=v:p.bind((v,))) for p,v in [(candidate('SELECT account_no FROM money.accounts2 WHERE account_no=%s'),True),(candidate('SELECT account_no FROM money.accounts2 WHERE account_no=%s'),'3'),(candidate('SELECT lookup FROM settings.key_values WHERE lookup=%s'),None),(candidate('SELECT lookup FROM settings.key_values WHERE enabled=%s'),1),(candidate('SELECT lookup FROM settings.key_values WHERE lookup=%s'),'x\x00y')]])

unsupported=[
 'SELECT count(*) FROM money.accounts2','SELECT lower(memo) FROM money.accounts2','SELECT account_no::text FROM money.accounts2','SELECT account_no FROM money.accounts2 WHERE account_no IS NULL',
 'SELECT account_no FROM money.accounts2 WHERE account_no=1 OR balance=2','SELECT account_no FROM money.accounts2 WHERE account_no IN (1,2)','SELECT account_no FROM money.accounts2 WHERE account_no BETWEEN 1 AND 2',
 'SELECT a.account_no FROM money.accounts2 a JOIN settings.key_values b ON true','SELECT account_no FROM money.accounts2,money.accounts2 other','WITH c AS (SELECT * FROM money.accounts2) SELECT * FROM c',
 'SELECT account_no FROM money.accounts2 UNION SELECT account_no FROM money.accounts2','SELECT (SELECT account_no FROM money.accounts2) FROM money.accounts2','SELECT * FROM money.accounts2 LIMIT 1','SELECT * FROM money.accounts2 OFFSET 1',
 'SELECT DISTINCT account_no FROM money.accounts2','SELECT * FROM money.accounts2 FOR UPDATE','SELECT unknown FROM money.accounts2','SELECT * FROM money.unconfigured','SELECT * FROM money.accounts2; DELETE FROM money.accounts2',
 'UPDATE money.accounts2 SET account_no=2 WHERE account_no=1','UPDATE money.accounts2 SET balance=balance+1 WHERE account_no=1','INSERT INTO money.accounts2(account_no,balance) VALUES(1,2) ON CONFLICT(account_no) DO NOTHING',
 'DELETE FROM money.accounts2 USING settings.key_values WHERE true','SELECT account_no FROM money.accounts2 WHERE balance=1.5','SELECT account_no FROM money.accounts2 WHERE account_no=9223372036854775808',
 'SELECT lookup FROM settings.key_values WHERE caption COLLATE "POSIX" = \'x\'','BEGIN','COMMIT','SAVEPOINT s','EXPLAIN SELECT * FROM money.accounts2','CREATE TABLE guessed(id int)',
]
for sql in unsupported:check('conservative unknown/unsupported '+sql,lambda sql=sql:err(lambda:parser.recognize(sql)))

def immutability():
 original=config.sha256;p=candidate('SELECT lookup FROM settings.key_values WHERE lookup=%s');raw=config.to_dict();raw['tables'][0]['columns'][0]['name']='changed';raw['limits']['max_terms']=1;eq(config.sha256,original)
 d=p.to_dict();d['table']['columns'][0]['name']='tamper';d['parameters'][0]['value']='tamper';eq(candidate(p.original_sql).parameters[0].value,0)
 for item,attribute,value in [(config,'default_schema','other'),(tables[0],'table','other'),(tables[0].columns[0],'name','other'),(p,'original_sql','other')]:err(lambda item=item,attribute=attribute,value=value:setattr(item,attribute,value),dataclasses.FrozenInstanceError)
 err(lambda:setattr(parser,'config',cs.SQLCaptureConfig(tables)),AttributeError)
 eq(config.sha256,original)
check('frozen public records and detached dictionaries really remain immutable',immutability)
check('configuration duplicate escaped fields and mutable collections are rejected',lambda:(err(lambda:cs.SQLCaptureConfig(list(tables)),ValueError),err(lambda:cs.TableConfig('s','t','k',[column('k','int64')]),ValueError),err(lambda:cs.SQLCaptureConfig.from_json(json.dumps(config.to_dict()).replace('"tables":','"tables":[],"tabl\\u0065s":',1)),ValueError)))

def cache_privacy():
 local=cs.ConfiguredSQLParser(config,cache_entries=2,cache_bytes=12000);sql='SELECT lookup FROM settings.key_values WHERE lookup=%s';p=local.recognize(sql);secret='UNIQUE_BIND_VALUE_b8e1973a_NO_SQL_LITERAL';parameters=[secret];bindings=p.bind(parameters);eq(parameters,[secret]);eq(bindings[0][1],secret);assert secret not in repr(local.__dict__)
 class Explosive:
  def __iter__(self):raise AssertionError('Business iterator consumed')
 err(lambda:p.bind(Explosive()));assert 'Explosive' not in repr(local.__dict__)
 for i in range(12):local.recognize('SELECT lookup FROM settings.key_values WHERE lookup=\'literal-key-'+str(i)+'\'')
 info=local.cache_info();assert info.entries<=2 and info.bytes<=12000
 assert secret not in repr(local.__dict__)
 fresh=cs.ConfiguredSQLParser(config,cache_entries=0,cache_bytes=0);fresh.recognize(sql);eq(fresh.cache_info().entries,0)
 # Raw SQL including its inline literal is intentionally retained. Do not claim
 # that the structural cache never contains business data embedded in SQL.
 literal='inline-literal-visible-in-original-SQL';local.recognize("SELECT lookup FROM settings.key_values WHERE lookup='"+literal+"'");assert literal in repr(local.__dict__)
check('cache retains SQL structure/literals but never bind values/results or iterators',cache_privacy)

def concurrent_cache():
 local=cs.ConfiguredSQLParser(config,cache_entries=3,cache_bytes=24000)
 def work(i):
  p=local.recognize('SELECT lookup FROM settings.key_values WHERE lookup=%s');value='parallel-secret-'+str(i);eq(p.bind((value,))[0][1],value);return p.config_sha256
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:values=list(pool.map(work,range(80)))
 assert all(v==config.sha256 for v in values);info=local.cache_info();assert info.entries<=3 and info.bytes<=24000;assert 'parallel-secret-' not in repr(local.__dict__)
check('concurrent recognizes keep bounded structure and isolate supplied bind values',concurrent_cache)
def exact_byte_boundary():
 sql='SELECT account_no FROM money.accounts2'
 size=len(sql.encode('utf8'))
 exact=cs.ConfiguredSQLParser(cs.SQLCaptureConfig(tables,max_sql_bytes=size))
 eq(exact.recognize(sql).original_sql,sql)
 eq(exact.recognize(sql).original_sql,sql)
 eq(exact.cache_info().hits,1)
 err(lambda:cs.ConfiguredSQLParser(cs.SQLCaptureConfig(tables,max_sql_bytes=size-1)).recognize(sql))
 err(lambda:cs.ConfiguredSQLParser(cs.SQLCaptureConfig(tables,max_nesting=1)).recognize('SELECT account_no FROM money.accounts2 WHERE ((account_no=1))'))
check('exact SQL byte limit admits cached call; one-short and excessive nesting reject',exact_byte_boundary)
check('SQL/term/insert/parameter-resource bounds reject without creating facts',lambda:(err(lambda:cs.ConfiguredSQLParser(cs.SQLCaptureConfig(tables,max_sql_bytes=8)).recognize('SELECT * FROM money.accounts2')),err(lambda:cs.ConfiguredSQLParser(cs.SQLCaptureConfig(tables,max_terms=1)).recognize('SELECT account_no FROM money.accounts2 WHERE account_no=1 AND balance=2')),err(lambda:cs.ConfiguredSQLParser(cs.SQLCaptureConfig(tables,max_insert_rows=1)).recognize('INSERT INTO money.accounts2(account_no) VALUES(1),(2)'))))

# Actual package/record/license consistency, without installing into any environment.
def dependency_license():
 dist=DEP/'sqlglot-30.26.0.dist-info';eq(sha(dist/'METADATA'),freeze['dependency']['metadataSha256']);license_file=dist/'licenses/LICENSE';eq(license_file.read_bytes(),(ROOT/'integrations/python/licenses/SQLGlot-30.26.0-MIT.txt').read_bytes());eq(sha(license_file),freeze['dependency']['license']['sha256'])
 for name,digest,size in csv.reader((dist/'RECORD').open(encoding='utf8',newline='')):
  file=DEP/name;assert file.resolve().is_relative_to(DEP.resolve());assert file.is_file()
  if digest:
   kind,encoded=digest.split('=',1);eq(kind,'sha256');eq(base64.urlsafe_b64encode(hashlib.sha256(file.read_bytes()).digest()).rstrip(b'=').decode(),encoded)
  if size:eq(file.stat().st_size,int(size))
 req=(ROOT/'integrations/python/requirements-configured-sql.txt').read_text();assert 'sqlglot==30.26.0' in req and freeze['dependency']['expectedWheelSha256'] in req
 assert 'License-Expression: MIT' in (dist/'METADATA').read_text(encoding='utf8')
check('actual installed SQLGlot RECORD/MIT license and hash-pinned requirements match',dependency_license)

def isolation():
 text=f'''import sys\nsys.path.insert(0,{str(ROOT/'integrations/python')!r})\nfrom moontxnwitness_capture import configured_sql as c\nassert 'sqlglot' not in sys.modules\nconfig=c.SQLCaptureConfig((c.TableConfig('s','t','k',(c.ColumnConfig('k','int64'),)),))\ntry:c.ConfiguredSQLParser(config).recognize('SELECT k FROM s.t')\nexcept c.OptionalParserUnavailable:pass\nelse:raise AssertionError('Optional parser silently supplied')\nassert not any(n.startswith(('psycopg','sqlalchemy')) for n in sys.modules)\nprint('isolated missing dependency explicit')\n'''
 result=subprocess.run([sys.executable,'-I','-S','-B','-c',text],cwd=ROOT,capture_output=True,text=True,timeout=20);eq(result.returncode,0);assert 'isolated missing dependency explicit' in result.stdout
check('separate no-site interpreter imports no parser/driver and refuses missing dependency',isolation)
assert not any(n.startswith(('psycopg','sqlalchemy')) for n in sys.modules)
after=source_map();eq(after,before)
for name,digest in protected.items():eq(sha(ROOT/name),digest)
receipt={'format':'independent-v037-configured-sql-review/v1','passed':all(x['passed'] for x in rows),'checks':len(rows),'failed':sum(not x['passed'] for x in rows),'results':rows,'threeConfiguredTableShapes':[{'schema':t.schema,'table':t.table,'columns':len(t.columns),'modelHint':t.model} for t in tables],'actualParserVersion':importlib.metadata.version('sqlglot'),'actualParserOrigin':str(Path(__import__('sqlglot').__file__).resolve()),'optionalParserImportLazy':True,'driverAndOrmImported':False,'originalProtectedFiles':freeze['originalProtectedSha256'],'frozenFileSha256':freeze['fileSha256'],'entireSrcBefore':before,'entireSrcAfter':after,'sourceBytesUnchanged':before==after,'scriptSha256':sha(Path(__file__)),'frozenReceiptSha256':sha(freeze_path),'author86TestsExecutedByReviewer':False,'runtimeKeysBound':257,'wheelArchiveRehashedByReviewer':False,'installedRecordAndMetadataAndLicenseChecked':True,'actualDatabaseExecution':False,'driverProjectionIntegrated':False,'moonbitIndependentSqlVerifier':False,'captureFactsProduced':False,'formalPerformanceMeasurement':False,'publicReleaseVerified':False,'scope':'Independent AST-candidate grammar/configuration/cache/license checks only. No automatic capture history or provenance evidence claimed.','cachePrivacyBoundary':'Cache intentionally contains original SQL, including literals written into SQL. It does not retain values supplied to bind() or database results. Serialized cache-byte bounds are not process RSS guarantees.'}
(OUT/'review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'passed':receipt['passed'],'checks':receipt['checks'],'failed':receipt['failed'],'sourceFiles':len(before),'receiptSha256':sha(OUT/'review.json'),'failures':[x for x in rows if not x['passed']]},ensure_ascii=False));sys.exit(0 if receipt['passed'] else 1)
