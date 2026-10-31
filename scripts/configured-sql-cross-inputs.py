"""Produce real frozen SQLGlot candidates for independent MoonBit cross-checks."""
from pathlib import Path
import argparse,json,hashlib,sys
root=Path(__file__).resolve().parents[1]
args=argparse.ArgumentParser();args.add_argument('--dependency-root',required=True);options=args.parse_args()
sys.dont_write_bytecode=True;sys.path.insert(0,str(root/'integrations/python'));sys.path.insert(0,str(Path(options.dependency_root).resolve()))
from moontxnwitness_capture.configured_sql import ColumnConfig,TableConfig,SQLCaptureConfig,ConfiguredSQLParser,TEXT_COMPARISON
c=lambda name,kind:ColumnConfig(name,kind,TEXT_COMPARISON if kind=='text' else None)
tables=(TableConfig('ledger','accounts','account_no',(c('account_no','int64'),c('balance','int64'),c('active','bool'),c('label','text'))),
 TableConfig('app','flags','feature_key',(c('feature_key','text'),c('enabled','bool'))),
 TableConfig('App-X','Customer.Space','User ID',(c('User ID','text'),c('quota','int64'),c('live','bool'),c('zone','text'),c('score','int64'),c('note','text'))))
config=SQLCaptureConfig(tables,default_schema='ledger');parser=ConfiguredSQLParser(config)
canonical=lambda value:json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
sha=lambda text:hashlib.sha256(text.encode('utf8')).hexdigest()
quote=lambda name:'"'+name.replace('"','""')+'"'
cases=[]
def add(name,sql,parameters):
 plan=parser.recognize(sql);bound=plan.bind(parameters)
 bindings=[{'reference':reference.to_dict(),'value':{'type':reference.type,'value':str(value) if reference.type=='int64' else value}} for reference,value in bound]
 candidate={'format':'moontxnwitness-sql-binding-candidate/v1','descriptor':plan.to_dict(),'bindings':bindings,'configSha256':config.sha256,'sqlSha256':sha(sql),'parametersSha256':sha(canonical(parameters))}
 cases.append({'name':name,'configText':json.dumps(config.to_dict(),ensure_ascii=False),'sql':sql,'parametersText':json.dumps(parameters,ensure_ascii=False),'candidateText':json.dumps(candidate,ensure_ascii=False),'expectedValid':True})
for index,table in enumerate(tables):
 target=quote(table.schema)+'.'+quote(table.table);fields=','.join(quote(column.name) for column in table.columns);pk=quote(table.primary_key)
 values=[('值🙂' if column.type=='text' else True if column.type=='bool' else 17) for column in table.columns]
 add('table'+str(index)+'-select','SELECT '+fields+' FROM '+target+' WHERE '+pk+'=%s',(values[0],))
 add('table'+str(index)+'-insert','INSERT INTO '+target+'('+fields+') VALUES('+','.join('%s' for _ in table.columns)+') RETURNING '+fields,tuple(values))
 add('table'+str(index)+'-update','UPDATE '+target+' SET '+quote(table.columns[1].name)+'=%s WHERE '+pk+'=%s RETURNING '+fields,(values[1],values[0]))
 add('table'+str(index)+'-delete','DELETE FROM '+target+' WHERE '+pk+'=%s RETURNING '+fields,(values[0],))
add('range-and-named','SELECT a.account_no AS "Result ID",a.balance FROM LEDGER.ACCOUNTS a WHERE (a.balance >= %(Min)s AND a.balance < %(Max)s) AND a.active=%(Live)s ORDER BY a.account_no DESC',{'Min':-7,'Max':42,'Live':True})
add('comments-stars','SELECT /* outer /* nested */ proof */ a.* FROM ledger.accounts AS a WHERE a.account_no=%s -- delivered later',(3,))
add('int64-maximum','SELECT account_no FROM ledger.accounts WHERE account_no=%s',(9223372036854775807,))
add('int64-minimum','SELECT account_no FROM ledger.accounts WHERE account_no=%s',(-9223372036854775808,))
add('inline-literals',"SELECT account_no FROM ledger.accounts WHERE balance >= -9223372036854775808 AND active=true AND label='中''文'",None)
add('unicode-collate','SELECT feature_key FROM app.flags WHERE feature_key COLLATE "C">=%s',('\U00010000',))
add('multivalue-insert','INSERT INTO app.flags(feature_key,enabled) VALUES(%s,%s),(%s,%s) RETURNING *',('a',True,'b',False))
add('named-case-sensitive','SELECT account_no FROM accounts WHERE account_no=%(Who)s AND balance>=%(Who)s',{'Who':13})
add('literal-percent-with-no-params',"SELECT feature_key FROM app.flags WHERE feature_key='literal%s'",None)
output={'format':'v037-real-sqlglot-cross-inputs/v1','actualSQLGlotExecution':True,'sqlglotVersion':'30.26.0','producerModuleSha256':hashlib.sha256((root/'integrations/python/moontxnwitness_capture/configured_sql.py').read_bytes()).hexdigest(),'producerScriptSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':cases,'actualDatabaseExecution':False,'sourceFactsProduced':False,'canonicalParameterRule':'Python compact sort_keys JSON, exact integers; matching is not observer authentication'}
out=root/'artifacts/sql-projection-cross-inputs.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'cases':len(cases),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'output':str(out)}))
