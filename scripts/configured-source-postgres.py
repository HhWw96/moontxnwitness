"""Owned PG18 installation/sidecar checks. Run only when the database window is enabled."""
from __future__ import annotations
import argparse,hashlib,json,os,runpy,secrets,socket,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture.configured_source import (SourceInstallPolicy,SourceInstallError,VERSION_COLUMN,BEFORE_TRIGGER,
 install_configured_source,TABLE_CATALOG_SQL,verify_table_catalog,identifier,literal)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def jsonable(value):
 if isinstance(value,tuple):return list(value)
 return value

def run_database(private,work):
 import psycopg
 values=json.loads(private.read_text(encoding='utf8'))
 # Reuse only the already-frozen three-table configuration, not any facade/projection.
 configuration=runpy.run_path(str(ROOT/'scripts/configured-fetch-postgres.py'))['config']()
 owner_role='mtw_source_owner';writer='mtw_source_writer';outsider='mtw_source_outsider'
 password=secrets.token_hex(20);q=identifier
 originals=[(17,100,True,'version-α'),('feature🙂',True,'version-β'),(19,'𐀀与\ue000',23,False,'东','version-γ')]
 for role in (writer,outsider):
  with psycopg.connect(**values,autocommit=True)as setup:setup.execute('CREATE ROLE '+q(role)+' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '+literal(password))
 with psycopg.connect(**values,autocommit=True)as setup:
  setup.execute('CREATE ROLE '+q(owner_role)+' NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
  setup.execute('GRANT CREATE ON DATABASE postgres TO '+q(owner_role));setup.execute('SET ROLE '+q(owner_role))
  for table,row in zip(configuration.tables,originals):
   target=q(table.schema)+'.'+q(table.table);types={'int64':'bigint','bool':'boolean','text':'text COLLATE "C"'}
   setup.execute('CREATE SCHEMA '+q(table.schema));setup.execute('CREATE TABLE '+target+'('+','.join(q(c.name)+' '+types[c.type]+(' PRIMARY KEY'if c.name==table.primary_key else'')for c in table.columns)+')')
   setup.execute('INSERT INTO '+target+' VALUES('+','.join('%s'for _ in row)+')',row)
   for role in (writer,outsider):setup.execute('GRANT USAGE ON SCHEMA '+q(table.schema)+' TO '+q(role));setup.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON '+target+' TO '+q(role))
  # Exercise dynamic initialization well above the old eight-key shape.
  table=configuration.tables[0];target=q(table.schema)+'.'+q(table.table)
  with setup.cursor()as cursor:cursor.executemany('INSERT INTO '+target+' VALUES(%s,%s,%s,%s)',[(i,100,True,'seed-'+str(i))for i in range(100,357)])
 policy=SourceInstallPolicy("mtw_source_quote'\\safe",(writer,))
 owner=psycopg.connect(**values,autocommit=True);owner.execute('SET ROLE '+q(owner_role))
 result=install_configured_source(owner,work/'installation',configuration,policy,opt_in=True).to_dict()
 assert result['catalogVerified']and result['initialSnapshotVerified']and result['actualCommitConfirmed']
 assert result['initialRows']==260
 for flag in ('sourceFactsProduced','writerWindowVerified','driverFetchVerified','moonbitCatalogVerified'):assert result[flag]is False
 actor={**values,'user':writer,'password':password};other={**values,'user':outsider,'password':password}
 (work/'writer-connection.json').write_text(json.dumps(actor),encoding='utf8')
 observations=[];checks=[];source=identifier(policy.namespace);meta=identifier(VERSION_COLUMN)
 def effect_count():return owner.execute('SELECT count(*) FROM '+source+'.effects').fetchone()[0]
 def business(connection,sql,params=None):
  cursor=connection.execute(sql,params);native=cursor.pgresult;rows=cursor.fetchall()if cursor.description else[]
  observations.append({'sql':sql,'parameters':params,'nativeStatus':int(native.status),'nativeTag':native.command_status.decode('ascii'),'rows':rows,'transactionStatusAfter':int(connection.info.transaction_status)})
  return rows
 def commit(connection):
  cursor=connection.execute('COMMIT');assert cursor.pgresult.command_status==b'COMMIT'and int(cursor.pgresult.status)==1 and int(connection.info.transaction_status)==0
 def rollback(connection):
  cursor=connection.execute('ROLLBACK');assert cursor.pgresult.command_status==b'ROLLBACK'and int(connection.info.transaction_status)==0
 app=psycopg.connect(**actor,autocommit=False)
 try:
  for index,(table,original)in enumerate(zip(configuration.tables,originals)):
   target=q(table.schema)+'.'+q(table.table);pk=q(table.primary_key);columns=','.join(q(c.name)for c in table.columns)
   key=2000+index if table.columns[0].type=='int64'else'new🙂'
   inserted=[key,*original[1:]];before=effect_count()
   rows=business(app,'INSERT INTO '+target+'('+columns+') VALUES('+','.join('%s'for _ in inserted)+') RETURNING '+columns+','+meta,tuple(inserted))
   assert tuple(rows[0][:-1])==tuple(inserted);version=rows[0][-1];commit(app)
   assert effect_count()==before+1;checks.append('table'+str(index)+' installed original insert and actual AFTER effect')
   effect=owner.execute('SELECT operation,base_version,row_key,row_values,writer_login FROM '+source+'.effects WHERE version=%s',(version,)).fetchone()
   assert effect[0]=='INSERT'and effect[1]is None and effect[2]==key and effect[3][table.primary_key]==key and effect[4]==writer
   before=effect_count();rows=business(app,'INSERT INTO '+target+'('+columns+') VALUES('+','.join('%s'for _ in inserted)+') ON CONFLICT('+pk+') DO NOTHING RETURNING '+meta,tuple(inserted));assert rows==[];commit(app)
   assert effect_count()==before;checks.append('table'+str(index)+' ON CONFLICT DO NOTHING has no ghost effect')
   column=table.columns[1];changed=not inserted[1]if column.type=='bool'else 201 if column.type=='int64'else'changed🙂'
   rows=business(app,'UPDATE '+target+' SET '+q(column.name)+'=%s WHERE '+pk+'=%s RETURNING '+meta,(changed,key));new_version=rows[0][0];commit(app)
   effect=owner.execute('SELECT operation,base_version,row_values FROM '+source+'.effects WHERE version=%s',(new_version,)).fetchone();assert effect[0]=='UPDATE'and effect[1]==version and effect[2][column.name]==changed
   checks.append('table'+str(index)+' actual OLD source and final update version')
   before=effect_count();missing=-999 if table.columns[0].type=='int64'else'missing'
   rows=business(app,'UPDATE '+target+' SET '+q(column.name)+'=%s WHERE '+pk+'=%s RETURNING '+meta,(changed,missing));assert rows==[];commit(app);assert effect_count()==before
   observations.append({'kind':'zero-row-condition','table':[table.schema,table.table],'statementReturnedRows':0,'fabricatedSelectRead':False,'sourceFactsProduced':False});checks.append('table'+str(index)+' zero-row condition remains separate')
   rows=business(app,'DELETE FROM '+target+' WHERE '+pk+'=%s RETURNING '+meta,(key,));assert rows==[(new_version,)];commit(app)
   deleted=owner.execute('SELECT version,base_version,row_key,row_values FROM '+source+'.effects WHERE operation=%s AND relation_oid=%s ORDER BY version DESC LIMIT 1',('DELETE',result['tables'][index]['catalog']['oid'])).fetchone()
   assert deleted[0]!=new_version and deleted[1]==new_version and deleted[2]==key and deleted[3]is None;checks.append('table'+str(index)+' tombstone identity is not old RETURNING version')
  table=configuration.tables[0];target=q(table.schema)+'.'+q(table.table);pk=q(table.primary_key);value=q(table.columns[1].name)
  base=business(app,'SELECT '+meta+' FROM '+target+' WHERE '+pk+'=%s',(17,))[0][0];commit(app);before=effect_count()
  business(app,'SAVEPOINT same');first=business(app,'UPDATE '+target+' SET '+value+'=%s WHERE '+pk+'=%s RETURNING '+meta,(301,17))[0][0]
  business(app,'SAVEPOINT same');business(app,'UPDATE '+target+' SET '+value+'=%s WHERE '+pk+'=%s RETURNING '+meta,(302,17))
  business(app,'ROLLBACK TO same');assert business(app,'SELECT '+meta+' FROM '+target+' WHERE '+pk+'=%s',(17,))==[(first,)]
  business(app,'RELEASE same');business(app,'ROLLBACK TO same');assert business(app,'SELECT '+meta+' FROM '+target+' WHERE '+pk+'=%s',(17,))==[(base,)];commit(app);assert effect_count()==before
  checks.append('same-name savepoints restore physical row and transactional effect ledger')
  rows=business(app,'UPDATE '+target+' SET '+value+'=%s WHERE '+pk+'=%s RETURNING '+meta,(303,17));aborted=rows[0][0];rollback(app)
  assert owner.execute('SELECT count(*) FROM '+source+'.effects WHERE version=%s',(aborted,)).fetchone()[0]==0;checks.append('full rollback does not leave an installed effect')
  for sql in ('SELECT pg_catalog.nextval('+literal(source+'.versions')+')','DELETE FROM '+source+'.effects'):
   try:app.execute(sql)
   except psycopg.Error as error:assert error.sqlstate=='42501';rollback(app)
   else:raise AssertionError('Writer directly accessed private source objects')
  checks.append('writer cannot access private sequence or ledger')
 finally:app.close()
 with psycopg.connect(**other,autocommit=False)as intruder:
  table=configuration.tables[0];target=q(table.schema)+'.'+q(table.table)
  try:intruder.execute('UPDATE '+target+' SET '+q(table.columns[1].name)+'=0 WHERE '+q(table.primary_key)+'=17')
  except psycopg.Error as error:assert error.sqlstate=='42501';intruder.rollback()
  else:raise AssertionError('Out-of-scope login bypassed row trigger scope')
 checks.append('unknown login cannot write even with base table DML privilege')
 table=configuration.tables[0];target=q(table.schema)+'.'+q(table.table)
 owner.execute('ALTER TABLE '+target+' DISABLE TRIGGER '+q(BEFORE_TRIGGER))
 raw=owner.execute(TABLE_CATALOG_SQL,(table.schema,table.table)).fetchone()[0]
 try:verify_table_catalog(table,policy,owner_role,json.loads(raw),installed=True)
 except SourceInstallError:checks.append('disabled trigger is rejected by fresh catalog validation')
 else:raise AssertionError('Disabled trigger was accepted')
 owner.execute('ALTER TABLE '+target+' ENABLE ALWAYS TRIGGER '+q(BEFORE_TRIGGER));owner.close()
 (work/'business-observations.json').write_text(json.dumps({'observations':observations,'sourceFactsProduced':False,'notDriverProjectionEvidence':True},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 return {'checks':checks,'checkCount':len(checks),'threeTableColumnCounts':[len(t.columns)for t in configuration.tables],'initialRows':result['initialRows'],'actualCommitConfirmed':result['actualCommitConfirmed'],'installationReceiptSha256':sha(work/'installation/receipt.json'),'sourceFactsProduced':False,'writerWindowVerified':False,'moonbitCatalogVerified':False,'driverFetchVerified':False}


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bin',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
 work=Path(args.output).resolve();work.mkdir(parents=True,exist_ok=False);data=work/'data';binaries=Path(args.bin).resolve();suffix='.exe'if os.name=='nt'else''
 for name in ('initdb','pg_ctl','postgres'):
  if not(binaries/(name+suffix)).is_file():raise ValueError('Existing complete PG18 bin required; no download')
 secret=secrets.token_hex(20);(work/'password.txt').write_text(secret+'\n',encoding='ascii');private=work/'connection.json'
 env={**os.environ,'TEMP':str(work),'TMP':str(work),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
 receipt={'format':'configured-source-owned-postgres/v1','status':'started','actualDatabaseExecution':False,'sourceFactsProduced':False,'formalPerformanceMeasurement':False,'wrapperSha256':sha(__file__),'implementationSha256':sha(ROOT/'integrations/python/moontxnwitness_capture/configured_source.py')};started=False;code=1
 with(work/'control.log').open('xb')as log:
  def run(parts):return subprocess.run([str(p)for p in parts],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,check=True,timeout=120,creationflags=flags)
  try:
   run([binaries/('initdb'+suffix),'-D',data,'-U','mtw','--locale=C','--encoding=UTF8','--auth-host=scram-sha-256','--auth-local=trust','--pwfile='+str(work/'password.txt')])
   with socket.socket()as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   run([binaries/('pg_ctl'+suffix),'-D',data,'-l',work/'server.log','-o','-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=10 -c work_mem=2MB','-w','start']);started=True;receipt['actualDatabaseExecution']=True
   private.write_text(json.dumps({'host':'127.0.0.1','port':port,'dbname':'postgres','user':'mtw','password':secret}),encoding='utf8')
   receipt.update(run_database(private,work));receipt['status']='passed';code=0
  except BaseException as error:(work/'failure.txt').write_text(traceback.format_exc(),encoding='utf8');receipt.update(status='failed',errorClass=type(error).__name__)
  finally:
   if started:
    pid=data/'postmaster.pid'
    if pid.exists():
     actual=Path(pid.read_text(encoding='utf8').splitlines()[1]).resolve()
     if actual!=data.resolve()or data.parent!=work:raise ValueError('Refuse to stop unrelated server')
     run([binaries/('pg_ctl'+suffix),'-D',data,'-m','fast','-w','stop']);receipt['ownedClusterStopped']=True
   (work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
 print(json.dumps(receipt));return code
if __name__=='__main__':raise SystemExit(main())
