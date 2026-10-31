"""Construct SYNTHETIC native buffers from real initial sources; never run SQL."""
import argparse,base64,hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--producer-root',required=True);p.add_argument('--dependency-root',required=True);a=p.parse_args()
sys.dont_write_bytecode=True;sys.path.insert(0,str(Path(a.producer_root)/'integrations/python'));sys.path.insert(0,a.dependency_root)
from moontxnwitness_capture.configured_sql import SQLCaptureConfig,ConfiguredSQLParser
fixture=root/'fixtures/source-components-v4';config=json.loads((fixture/'config.json').read_text(encoding='utf8'));receipt=json.loads((fixture/'receipt.json').read_text(encoding='utf8'));log=(fixture/'control.jsonl').read_text(encoding='utf8')
for t in config['tables']:t['columns'].append({'name':'__mtw_source_version','type':'int64','comparison':None})
configuration=SQLCaptureConfig.from_json(json.dumps(config,ensure_ascii=False));parser=ConfiguredSQLParser(configuration)
canonical=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
sha=lambda v:hashlib.sha256(v.encode('utf8')).hexdigest();quote=lambda s:'"'+s.replace('"','""')+'"'
rows=[json.loads(r['decodedRows'][0][0])['row']for r in map(json.loads,log.splitlines())if r.get('queryId')=='initial-snapshot'and r.get('kind')=='source-control'and r.get('decodedRows')]
cases=[]
for index,(table,entry)in enumerate(zip(config['tables'],receipt['tables'])):
 catalog=entry['catalog'];row=next(row for row in rows if table['primaryKey']in row);columns=table['columns'];params=[row[table['primaryKey']]]
 sql='SELECT '+','.join(quote(c['name'])for c in columns)+' FROM '+quote(table['schema'])+'.'+quote(table['table'])+' WHERE '+quote(table['primaryKey'])+'=%s'
 plan=parser.recognize(sql);bindings=[{'reference':ref.to_dict(),'value':{'type':ref.type,'value':str(value)if ref.type=='int64'else value}}for ref,value in plan.bind(params)]
 candidate={'format':'moontxnwitness-sql-binding-candidate/v1','descriptor':plan.to_dict(),'bindings':bindings,'configSha256':configuration.sha256,'sqlSha256':sha(sql),'parametersSha256':sha(canonical(params))}
 identity={'connection':'SYNTHETIC-connection-'+str(index),'cursor':'SYNTHETIC-cursor-'+str(index),'tx':'SYNTHETIC-tx-'+str(index),'statementSeq':3};result_id='SYNTHETIC-result-'+str(index)
 execution={'format':'moontxnwitness-configured-execution/v1',**identity,'sql':sql,'parameters':params,'candidate':candidate,'sourceFactsProduced':False}
 def cell(c):
  value=row[c['name']];text=('t'if value else'f')if c['type']=='bool'else str(value)
  return base64.b64encode(text.encode('utf8')).decode('ascii')
 fields=[{'name':c['name'],'oid':actual['oid'],'format':0,'typmod':-1,'tableOid':catalog['oid'],'tableColumn':actual['number']}for c,actual in zip(columns,catalog['columns'])]
 native={'format':'moontxnwitness-native-result/v1',**identity,'resultId':result_id,'executionNoteSeq':4,'sqlSha256':candidate['sqlSha256'],'parametersSha256':candidate['parametersSha256'],'status':2,'fields':fields,'rows':[[cell(c)for c in columns]],'storedColumnDeclarations':['__mtw_source_version'],'sourceFactsProduced':False}
 deliveries=[{'format':'moontxnwitness-actual-delivery/v1',**identity,'resultId':result_id,'nativeNoteSeq':5,'method':'fetchall','start':0,'rows':[[{'type':c['type'],'value':str(row[c['name']])if c['type']=='int64'else row[c['name']]}for c in columns]],'complete':True,'sourceFactsProduced':False}]
 cases.append({'execution':execution,'native':native,'deliveries':deliveries,'sourceContext':{'format':'caller-asserted-installation-epoch/v1','installationLogSha256':sha(log),'databaseOid':receipt['environment']['databaseOid']}})
output={'format':'source-components-SYNTHETIC-fetch-inputs/v4','actualDatabaseExecution':False,'syntheticNativeBuffers':True,'actualSQLGlotExecution':True,'sqlglotVersion':'30.26.0','sourceFactsProduced':False,'origin':'Real locked initial rows/catalog, but execution/native/delivery identity frames are synthetic unit inputs, not a database capture.','producerModuleSha256':hashlib.sha256((Path(a.producer_root)/'integrations/python/moontxnwitness_capture/configured_sql.py').read_bytes()).hexdigest(),'cases':cases}
path=fixture/'SYNTHETIC-fetch-inputs.json';path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'cases':len(cases),'bytes':path.stat().st_size,'actualDatabaseExecution':False,'syntheticNativeBuffers':True}))
