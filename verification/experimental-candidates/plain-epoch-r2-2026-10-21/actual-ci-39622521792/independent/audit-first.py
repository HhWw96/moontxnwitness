"""Independently audit fixed original R2 execution bytes, never run a candidate.

Stdlib, public metadata and immutable Git-object reads only. The R1 review was
read as a reference for the wire formats; this script binds the new R2 sources,
73 exact test identities and initial ACK barrier and rechecks actual raw facts.
"""
from pathlib import Path,PurePosixPath
import ast,hashlib,json,re,stat,subprocess,uuid,zipfile
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
ACTUAL=ROOT/'artifacts/epoch-r2-local-first/actual-r2-39622521792'
RAW=ACTUAL/'raw'
WORK=RAW/'epoch-r2-work-39622521792-1'
EVIDENCE=WORK/'evidence'
CONTEXT=RAW/'epoch-r2-context-39622521792-1'
SOURCE='e63df4b815f130674bc0f10939d8513e534679a8'
RUN=39622521792
ZIP=ACTUAL/'artifact-12355956248.zip'
ZIP_SHA='bd569323de9a3d8fef27a68692c9f97a140dd1006182362d09a9b05da16aaaed'
PUBLIC='verification/experimental-candidates/plain-epoch-r2-2026-10-21'
OLD='verification/experimental-candidates/plain-journal-r2-2026-10-21'
PREFIX='artifacts/plain-v3-epoch-r2-draft'
CHECKS=[];BLOBS={};MEMBERS={};FACTS={};INITIAL=[]

def unique(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate JSON field')
        result[key]=value
    return result

def check(name,passed):
    CHECKS.append({'name':name,'passed':bool(passed)})
    if not passed:raise AssertionError(name)

def read(path,maximum=16777216):
    if path.is_symlink() or not path.is_file():raise ValueError('Regular evidence file required')
    with path.open('rb') as stream:value=stream.read(maximum+1)
    if len(value)>maximum:raise ValueError('Evidence byte bound')
    return value

def binding(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def file_binding(path):return binding(read(path))
def load(path):return json.loads(read(path),object_pairs_hook=unique)
def canonical(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
def relative(name):
    value=PurePosixPath(name)
    if not name or value.is_absolute() or '..' in value.parts or value.as_posix()!=name or '\\' in name or ':' in name:
        raise ValueError('Unsafe evidence-relative name')
    return name

def immutable_sources():
    paths=[PUBLIC+'/bundle-index.json',PUBLIC+'/bundle',OLD+'/bundle',
           '.github/workflows/experimental-plain-epoch-r2.yml','scripts/experimental_plain_epoch_r2_ci.py']
    listing=subprocess.check_output(['git','-c','core.longpaths=true','ls-tree','-r','-z',SOURCE,'--',*paths],cwd=ROOT)
    entries=[]
    for line in listing.split(b'\0'):
        if not line:continue
        meta,path=line.split(b'\t',1);mode,kind,oid=meta.split()
        if mode!=b'100644' or kind!=b'blob':raise ValueError('Immutable regular Git source required')
        entries.append((path.decode(),oid.decode()))
    output=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,input=''.join(oid+'\n' for _,oid in entries).encode())
    if len(output)>4194304:raise ValueError('Git batch byte limit')
    result={};at=0
    for name,expected in entries:
        stop=output.index(b'\n',at);oid,kind,length=output[at:stop].split();length=int(length)
        if oid.decode()!=expected or kind!=b'blob' or length>1048576:raise ValueError('Exact bounded Git blob required')
        at=stop+1;raw=output[at:at+length];at+=length
        if len(raw)!=length or output[at:at+1]!=b'\n':raise ValueError('Git batch framing')
        at+=1;result[name]=raw;BLOBS[name]={'gitBlob':expected,**binding(raw)}
    if at!=len(output):raise ValueError('Unexpected Git bytes')
    return result

def source_records(path,complete):
    index=load(path/'index.json');data=read(path/'records.jsonl',8388608);previous='0'*64;records=[]
    for ordinal,line in enumerate(data.splitlines(keepends=True),1):
        item=json.loads(line,object_pairs_hook=unique)
        check(str(path.relative_to(WORK))+'/source-'+str(ordinal),line.endswith(b'\n') and len(line)<=65536 and item['sourceSchema']==1
              and item['seq']==ordinal and item['previous']==previous)
        previous=hashlib.sha256(line).hexdigest();records.append(item['payload'])
    check(str(path.relative_to(WORK))+'/source-footer',index['bytes']==len(data) and index['records']==len(records)
          and index['sha256']==hashlib.sha256(data).hexdigest() and index['lastRecordSha256']==previous)
    check(str(path.relative_to(WORK))+'/source-closure',index['closed'] is complete and (path/'writer.lock').exists() is (not complete))
    return records

def events(path,complete):
    index=load(path/'journal-index.json');result=[];clock=-1
    check(str(path.relative_to(WORK))+'/index-own-hash',index['indexSha256']==hashlib.sha256(canonical({k:v for k,v in index.items() if k!='indexSha256'})).hexdigest())
    for segment in index['segments']:
        raw=read(path/relative(segment['name']));rows=[json.loads(line,object_pairs_hook=unique) for line in raw.splitlines()]
        check(str(path.relative_to(WORK))+'/'+segment['name'],binding(raw)=={k:segment[k] for k in ('bytes','sha256')}
              and len(rows)==segment['eventCount'] and rows[0]['seq']==segment['firstSeq'] and rows[-1]['seq']==segment['lastSeq'])
        for row in rows:
            check(str(path.relative_to(WORK))+'/event-'+str(row['seq']),row['seq']==len(result)+1 and type(row['time']) is int and row['time']>=clock)
            result.append(row);clock=row['time']
    check(str(path.relative_to(WORK))+'/closed-journal',index['closed'] is True and index['sourceClosed'] is complete
          and len(result)==index['eventCount']==index['durableSeq'] and clock==index['lastTime'])
    if complete:check(str(path.relative_to(WORK))+'/complete-no-gaps',index['gaps']==[] and index['activeTransactions']==[] and index['commitRequests']==[])
    check(str(path.relative_to(WORK))+'/no-retention-claim',index['retention']['deletionImplemented'] is False and index['transactionIndex']['authoritative'] is False)
    return result,index

def native(value):
    if type(value) is not dict:return value
    if value['nativeType'] not in ('tuple','list'):raise ValueError('Unexpected native fixture encoding')
    items=[native(child) for child in value['items']]
    return tuple(items) if value['nativeType']=='tuple' else items

def boundary(chain,item,state):
    path=chain/'boundaries'/relative(item['name']);label=chain.parent.name+'/'+item['name']
    check(label+'/source-inventory',{p.name:file_binding(p) for p in path.iterdir() if p.is_file()}==item['files'])
    rows=source_records(path,True);summary=item['summary']
    check(label+'/bound-footer',rows[-1]=={'kind':'boundary-end','summary':summary})
    ident=lambda name:'"'+name.replace('"','""')+'"'
    schema,table=state['scope']['schema'],state['scope']['table']
    prefix='mtwp_'+hashlib.sha256((table+'\0column').encode()).hexdigest()[:16]
    business=ident(schema)+'.'+ident(table);objects=[ident(schema)+'.'+ident(prefix+'_'+part) for part in ('installation','audit','state')]
    check(label+'/begin-lock-identity',rows[0]['sql']=='BEGIN ISOLATION LEVEL READ COMMITTED' and rows[0]['commandTag']=='BEGIN' and rows[0]['pgStatus']==1
          and rows[1]['sql']=='SELECT pg_backend_pid(),pg_current_xact_id()::text'
          and native(rows[1]['nativeRows'])==[(summary['backendPid'],summary['transaction'])]
          and summary['lockSeq']==3 and rows[2]['sql']=='LOCK TABLE '+','.join([business]+objects)+' IN ACCESS EXCLUSIVE MODE'
          and rows[2]['commandTag']=='LOCK TABLE' and rows[2]['pgStatus']==1)
    for number,row in enumerate(rows[:-1],1):
        check(label+'/same-server-transaction-'+str(number),row['connection']==summary['connection'] and row['backendPid']==summary['backendPid']
              and (number<=2 or row['transaction']==summary['transaction']))
    commit=rows[summary['commitSeq']-1]
    check(label+'/actual-commit-confirmation',commit['kind']=='query' and commit['sql']=='COMMIT' and commit['commandTag']=='COMMIT'
          and commit['pgStatus']==1 and commit['statusBefore']==2 and commit['statusAfter']==0 and native(commit['nativeRows'])==[])
    # Bind before/after query semantics. Only constraints have unspecified tied
    # row order; preserve every field and multiplicity when comparing those.
    before,after=summary['verifyRanges'];left=rows[before[0]-1:before[1]];right=rows[after[0]-1:after[1]]
    check(label+'/catalog-query-count',len(left)==len(right)==22)
    for number,(a,b) in enumerate(zip(left,right)):
        check(label+'/catalog-sql-'+str(number),all(a[k]==b[k] for k in ('sql','parameters','fetch','complete','pgStatus')) and a['complete'] is True and a['pgStatus']==2)
        if a['sql'].startswith('SELECT c.contype,') and a['sql'].endswith('ORDER BY c.contype'):
            ar,br=native(a['nativeRows']),native(b['nativeRows'])
            check(label+'/catalog-constraint-multiset-'+str(number),all(len(row)==17 for row in ar+br)
                  and sorted(canonical(row) for row in ar)==sorted(canonical(row) for row in br)
                  and [row[0] for row in ar]==sorted(row[0] for row in ar) and [row[0] for row in br]==sorted(row[0] for row in br))
        else:check(label+'/catalog-ordered-rows-'+str(number),a['nativeRows']==b['nativeRows'])
    check(label+'/installation-identity',native(left[0]['nativeRows'])==[(summary['nonce'],'column',summary['tableOid'])])
    def snapshot(span):
        result={}
        for row in rows[span[0]-1:span[1]]:
            check(label+'/snapshot-query-'+str(row['part']),row['kind']=='query' and row['fetch']=='many' and row['pgStatus']==2
                  and row['sql']=='SELECT "id","value",'+ident(prefix+'_version')+'::text FROM '+business+' ORDER BY "id" LIMIT 65')
            for key,value,token in native(row['nativeRows']):
                check(label+'/snapshot-identity-'+key,key not in result and type(value) is int and str(uuid.UUID(token))==token)
                result[key]=(value,token)
        check(label+'/snapshot-complete-keys',set(result)=={'k','other'});return result
    final=snapshot(summary['finalSnapshot']);following=snapshot(summary['nextSnapshot'])
    check(label+'/stable-under-lock',final==following)
    ledger=[];lo,hi=summary['ledgerRange'];batches=rows[lo-1:hi]
    for row in batches:
        check(label+'/ledger-query-'+str(row['countThrough']),row['kind']=='ledger-batch' and row['pgStatus']==2
              and row['sql']=='SELECT token::text,key,action,present,predecessor::text,old_value,new_value FROM '+objects[1]+' ORDER BY token')
        ledger.extend(native(row['nativeRows']));check(label+'/ledger-count-'+str(len(ledger)),row['countThrough']==len(ledger))
    check(label+'/ledger-complete',batches[-1]['exhausted'] is True and native(batches[-1]['nativeRows'])==[] and len(ledger)==summary['ledgerRows']
          and len({row[0] for row in ledger})==len(ledger))
    by_token={row[0]:row for row in ledger}
    check(label+'/snapshot-actual-ledger',all(by_token[token][1]==key and by_token[token][3] is True and by_token[token][6]==value for key,(value,token) in final.items()))
    return final,ledger

def main():
    receipt={'schema':1,'kind':'independent-AI-limited-R2-actual-evidence-audit','run':RUN,'sourceCommit':SOURCE,'passed':False,
             'actualTestsReexecuted':False,'actualDatabaseReexecuted':False,'candidateModulesImported':False,'formalPerformanceMeasured':False,
             'sourceClosureVerified':False,'coreProofImplemented':False,'formalEligible':False,
             'overallJobCompletionMetadataVerified':False,'releaseAcceptance':False,
             'scope':'Exact executed R2 source, 73 emitted test results and4 actual controlled PostgreSQL cases. Not general SQL proof, source closure, crash durability, performance or release acceptance.',
             'limitations':['No object identity inferred from JSON; identity assertions are in the exact byte-bound executed unit and PG fixtures.',
                            'Initial ACK is appended before snapshot by verified code barrier; raw source/journal logs have separate sequence spaces and do not independently timestamp that cross-file order.',
                            'Initial COMMIT fault cases in the new26 are synthetic, not actual network faults. Four actual PG cases exercise normal first initialization and injected boundary ACK loss.',
                            'Source append is not per-record fsync; ledger closure and journal completeness are separately verified.',
                            'Run API success and job API in_progress/null are both retained; overall job completion metadata is not accepted.']}
    try:
        run=load(HERE/'official-run.json');artifact=load(HERE/'official-artifact.json');jobs=load(HERE/'official-jobs.json');direct=load(HERE/'official-job-direct.json')
        check('fresh-run-endpoint',run['id']==RUN and run['head_sha']==SOURCE and run['status']=='completed' and run['conclusion']=='success' and run['run_attempt']==1)
        check('fresh-artifact-endpoint',artifact['id']==12355956248 and artifact['workflow_run']['id']==RUN and artifact['workflow_run']['head_sha']==SOURCE
              and artifact['digest']=='sha256:'+ZIP_SHA and artifact['size_in_bytes']==931937 and artifact['name']=='two-epoch-r2-first-raw')
        check('job-identity-without-invented-conclusion',jobs['total_count']==1 and jobs['jobs'][0]['id']==direct['id']==119299439554 and direct['run_id']==RUN
              and direct['head_sha']==SOURCE)
        receipt['metadataDiscrepancy']={'runStatus':run['status'],'runConclusion':run['conclusion'],'listJobStatus':jobs['jobs'][0]['status'],
                                      'listJobConclusion':jobs['jobs'][0]['conclusion'],'directJobStatus':direct['status'],'directJobConclusion':direct['conclusion'],
                                      'resolution':'No further polling; actual retained evidence is audited separately from overall job completion.'}
        check('original-public-ZIP',file_binding(ZIP)=={'bytes':931937,'sha256':ZIP_SHA})
        with zipfile.ZipFile(ZIP) as archive:
            infos=archive.infolist();check('original-ZIP-inventory',len(infos)==791 and sum(i.file_size for i in infos)==4215046 and len({i.filename for i in infos})==791)
            for info in infos:
                name=relative(info.filename)
                check('regular-ZIP-member-'+name,not info.is_dir() and info.file_size<=16777216 and not stat.S_ISLNK(info.external_attr>>16))
                value=archive.read(info);expected=binding(value)
                check('actual-extracted-member-'+name,expected['bytes']==info.file_size and file_binding(RAW/name)==expected)
                MEMBERS[name]=expected
        check('no-extra-extraction',set(MEMBERS)=={p.relative_to(RAW).as_posix() for p in RAW.rglob('*') if p.is_file()})
        blobs=immutable_sources();new=json.loads(blobs[PUBLIC+'/bundle-index.json']);old=json.loads(blobs[OLD+'/bundle/bundle-index.json'])
        expected={}
        for name,item in old['files'].items():
            value={k:item[k] for k in ('bytes','sha256')};check('immutable-old-source-'+name,binding(blobs[OLD+'/bundle/'+item['bundleFile']])==value);expected[name]=value
        for name,value in new['files'].items():check('immutable-new-source-'+name,binding(blobs[PUBLIC+'/bundle/'+name])==value);expected[name]=value
        check('new-candidate-and-dependencies',new['candidateIndexSha256']=='f6610c932dac6f4576072d366fdbebf6b7ca4e7dfd5da07240ad279742b47e0a'
              and len(new['files'])==18 and len(new['dependencies'])==9 and all(expected[name]==value for name,value in new['dependencies'].items()))
        check('restored80-inventory',len(expected)==80)
        for name,value in expected.items():check('actual-restored-'+name,file_binding(WORK/'repository'/name)==value)
        execution=load(EVIDENCE/'execution-receipt.json')
        check('actual-before-after',execution['allSourceBindingsBefore']==expected==execution['allSourceBindingsAfter'] and execution['sourceCommit']==execution['workflowCommit']==SOURCE
              and execution['run']==str(RUN))
        context=load(CONTEXT/'source.json')
        check('actual-context',context['actualSource']==context['requestedSource']==context['workflowSource']==SOURCE and context['databaseExecutedAtContextCreation'] is False)
        workflow=blobs['.github/workflows/experimental-plain-epoch-r2.yml'].decode()
        check('pinned-server-driver-python','postgres:18.6-bookworm@sha256:afc7e2d441324c0388fa80c3d24f733b4194a4eb7f47dd8ee2b08eb1a24a647c' in workflow
              and "python-version: '3.12.5'" in workflow and b'PostgreSQL 18.6' in read(CONTEXT/'postgres.log') and b'psycopg-3.3.6' in read(CONTEXT/'driver.log'))
        check('stage-inventory',[s['name'] for s in execution['stages']]==['unit-first','postgres-first'])
        for stage in execution['stages']:check('stage-'+stage['name'],stage['executed'] is True and stage['exitCode']==0 and stage['passed'] is True
                                             and file_binding(EVIDENCE/stage['log'])==stage['logBinding'])
        unit_path=WORK/relative(execution['unitReceipt']['path']);unit=load(unit_path)
        check('actual-unit-receipt',file_binding(unit_path)=={k:execution['unitReceipt'][k] for k in ('bytes','sha256')})
        declared={name:value for name,value in new['files'].items() if PurePosixPath(name).parent.as_posix()==PREFIX
                  and PurePosixPath(name).suffix in ('.py','.json') and not PurePosixPath(name).name.startswith('candidate-index')}
        declared.update(new['dependencies'])
        check('unit-executed73-no-skips',unit['passed'] is True and unit['tests']==unit['expectedTests']==73 and unit['skipped']==[] and unit['failures']==[]
              and unit['actualMockExecution'] is True and unit['actualFilesystemExecution'] is True and unit['actualNativeChildExecution'] is True
              and unit['actualDatabaseExecution'] is False and unit['sourceBindingsBefore']==declared==unit['sourceBindingsAfter'])
        def source(name):return blobs[PUBLIC+'/bundle/'+PREFIX+'/'+name].decode()
        def methods(name,cls):
            tree=ast.parse(source(name));node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
            return [n for n in node.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
        original=methods('test_epoch.py','EpochTests');hardening=methods('test_hardening.py','HardeningTests')
        identities={f'test_epoch.EpochTests.{n.name}' for n in original}|{f'__main__.HardeningTests.{n.name}' for n in hardening}
        emitted=re.findall(r'^(test_\w+) \(([^)]+)\) \.\.\. ok$',read(EVIDENCE/'unit-first.log').decode(),re.MULTILINE)
        check('exact73-actual-test-identities',len(original)==47 and len(hardening)==26 and len(emitted)==len({qualified for _,qualified in emitted})==73
              and {qualified for _,qualified in emitted}==identities)
        for _,qualified in emitted:check('emitted-test-'+qualified,qualified in identities)
        # Independent manual review of each new assertion is retained by its
        # exact AST text digest and actual emitted identity, not recomputation.
        receipt['reviewedHardeningAssertions']=[{'name':n.name,'astSha256':hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest(),
                                                'actualResultEmitted':True} for n in hardening]
        guard=source('initialization_guard.py');point=source('point_epoch.py');coordinator=source('epoch_coordinator.py');tests=source('test_hardening.py')
        check('bounded-admission-source-order','for _ in range(65):' in guard and 'items.append(item)' in guard
              and coordinator.index('keys=bounded_keys(keys)')<coordinator.index('path=Path(path);path.mkdir')
              and point.index('kwargs["keys"]=bounded_keys(kwargs["keys"])')<point.index('super().__init__'))
        check('bounded-admission-executed-assertions','if i==65:raise AssertionError("Consumed item66")' in tests and 'self.assertEqual(len(calls),65)' in tests
              and 'Filesystem touched before key admission' in tests and 'self.assertEqual(setup.queries,[])' in tests)
        check('initial-ACK-before-publication-source',guard.index('self.capture.sources.append(record)')<guard.index('self.confirmed=True')
              and 'before==2 and after==0' in guard and 'tag=="COMMIT"' in guard and 'status_value==1 and description is None' in guard
              and 'require(guard.confirmed,"Initial snapshot requires retained COMMIT confirmation")' in point
              and point.index('require(guard.confirmed,"Initial snapshot requires retained COMMIT confirmation")')<point.index('return super().publish_snapshot'))
        check('original-error-and-one-attempt-source','self.primary_error=error;self.primary_traceback=error.__traceback__' in guard
              and 'raise guard.primary_error.with_traceback(guard.primary_traceback) from None' in point
              and 'self._initialization_attempted=True' in point and 'not getattr(self,"_initialization_attempted",False)' in point
              and 'self.assertIs(caught.exception,s.error)' in tests and 'self.assertEqual(s.queries,before)' in tests)
        pg_path=EVIDENCE/'postgres/postgres-receipt.json';pg=load(pg_path)
        declared_pg=dict(declared);declared_pg.pop('examples/postgres-requirements.txt');declared_pg[PREFIX+'/candidate-index-static-v1.json']=new['files'][PREFIX+'/candidate-index-static-v1.json']
        check('actual-PG-receipt-and-sources',file_binding(pg_path)=={k:execution['postgresReceipt'][k] for k in ('bytes','sha256')} and pg['passed'] is True
              and pg['serverVersion']==180006 and pg['driver']=='3.3.6' and pg['actualDatabaseExecution'] is True
              and pg['sourceBindingsBefore']==declared_pg==pg['sourceBindingsAfter'])
        names=['two-epochs-same-value','rollback-and-savepoint','unsupported-statement','discarded-setup-commit-ack']
        check('actual-four-PG-cases',[c['name'] for c in pg['cases']]==names)
        for case in pg['cases']:
            name=case['name'];base=EVIDENCE/'postgres'/name;chain=base/'chain';state=load(chain/'manifest.json')
            check(name+'/exact-case-and-files',load(base/'case-receipt.json')==case and case['rawFileBindings']=={p.relative_to(chain).as_posix():file_binding(p) for p in chain.rglob('*') if p.is_file()})
            check(name+'/scope-flags',case['actualDatabaseExecution'] is True and case['passed'] is True and case['coreProofImplemented'] is False and case['formalEligible'] is False
                  and all(state[k] is False for k in ('sourceClosureVerified','coreProofImplemented','formalEligible')))
            positive=name in names[:2];parsed=[]
            for epoch_id in ('epoch-0000','epoch-0001') if positive else ('epoch-0000',):
                directory=chain/'epochs'/epoch_id;j,idx=events(directory/'journal',positive);s=source_records(directory/'sources',True);parsed.append((j,s,idx))
                if epoch_id=='epoch-0000':
                    ack=s[0];install=s[1]
                    check(name+'/actual-first-ACK',ack=={'kind':'initialization-commit-ack','sql':'COMMIT','statusBefore':2,'statusAfter':0,'commandTag':'COMMIT',
                          'pgStatus':1,'noRows':True,'actualCommitConfirmed':True,'coreProofImplemented':False})
                    check(name+'/initial-ACK-installation-snapshot-binding',install['kind']=='installation' and install['serverVersion']==180006
                          and install['window'][-1]=={'sql':'COMMIT','tag':'COMMIT'} and j[0]['kind']=='snapshot' and j[0]['consistent'] is True
                          and j[0]['initial']=={key:token for key,_,token in install['initialRows']} and {key for key,_,_ in install['initialRows']}=={'k','other'})
                    INITIAL.append({'case':name,'sourceRecord1':ack,'sourceRecord2Kind':install['kind'],'initialJournalSeq':j[0]['seq'],
                                    'orderingEvidence':'Source record sequence plus independently reviewed byte-bound publication barrier and executed test11.'})
            if positive:
                check(name+'/two-complete-epochs',state['phase']=='closed' and state['generation']==2 and state['current'] is None and len(state['boundaries'])==2
                      and [e['epoch'] for e in state['sealed']]==['epoch-0000','epoch-0001'] and not any((chain/p).exists() for p in ('failed.json','operation.lock','intent.json')))
                for item in state['sealed']:
                    directory=chain/'epochs'/item['epoch']
                    check(name+'/'+item['epoch']+'/sealed-file-bindings',item['files']=={p.relative_to(directory).as_posix():file_binding(p) for p in directory.rglob('*') if p.is_file()})
                transitions=[boundary(chain,item,state) for item in state['boundaries']]
                check(name+'/cross-window-snapshot',parsed[1][0][0]['initial']=={key:token for key,(_,token) in transitions[0][0].items()})
                second=parsed[1][1][0]
                check(name+'/cross-window-source-reference',second['kind']=='boundary-initialization' and second['boundaryId']==state['boundaries'][0]['name']
                      and second['boundaryBindings']==state['boundaries'][0]['files'] and second['boundarySummary']==state['boundaries'][0]['summary'])
                writes=[e for e in parsed[0][0] if e['kind']=='write'];tokens={row[0] for row in transitions[0][1]}
                if name=='two-epochs-same-value':
                    by_seq={row['seq']:row for row in parsed[0][0]}
                    check(name+'/distinct-same-value-identities',len(writes)==2 and writes[0]['version']!=writes[1]['version'] and [w['version'] for w in writes]==case['writeTokens']
                          and [by_seq[w['statement']]['parameters'] for w in writes]==[[5,'k'],[5,'k']] and writes[1]['predecessor']==writes[0]['version'])
                    check(name+'/actual-committed-read-and-ledger',all(w['version'] in tokens for w in writes)
                          and any(e['kind']=='read' and e['version']==writes[1]['version'] and e['tx']==writes[1]['tx'] for e in parsed[0][0])
                          and transitions[0][0]['k']==(5,writes[1]['version']) and transitions[1][0]['k'][0]==7)
                    FACTS[name]={'distinctEqualValueIdentities':True,'crossWindowContinuity':True,'finalValue':7}
                else:
                    es=parsed[0][0];save=next(e for e in es if e['kind']=='savepoint');undo=next(e for e in es if e['kind']=='rollback_to');release=next(e for e in es if e['kind']=='release')
                    check(name+'/raw-reverted-and-committed-facts',len(writes)==3 and len({w['version'] for w in writes})==3
                          and save['instance']==undo['instance']==release['instance'] and save['seq']<writes[2]['seq']<undo['seq']<release['seq']
                          and writes[0]['tx']!=writes[1]['tx']==writes[2]['tx'] and any(e['kind']=='rollback_ok' and e['tx']==writes[0]['tx'] for e in es)
                          and writes[1]['version'] in tokens and writes[0]['version'] not in tokens and writes[2]['version'] not in tokens
                          and case['actualCommittedWriteTokens']==[writes[1]['version']] and transitions[0][0]['k']==(10,writes[1]['version']))
                    FACTS[name]={'rawWrites':3,'abortedOrReverted':2,'actualCommittedToken':writes[1]['version'],'finalValue':10}
            else:
                check(name+'/no-published-next-epoch',state['phase']=='running' and state['generation']==0 and state['boundaries']==[] and state['sealed']==[]
                      and not (chain/'epochs/epoch-0001').exists() and not any(s['kind']=='ledger-end' for s in parsed[0][1]))
                if name=='unsupported-statement':
                    j,s,index=parsed[0]
                    check(name+'/preserved-business-result-with-gap',any(e['kind']=='statement' and e['sql'].startswith('SELECT value+1 FROM ') for e in j)
                          and any(e['kind']=='rows' and e['rows']==[[2]] for e in j) and not any(e['kind']=='read' for e in j)
                          and {'unknown_sql','ledger_not_finalized'}<={g['code'] for g in index['gaps']}
                          and not (chain/'operation.lock').exists() and not (chain/'intent.json').exists()
                          and not any(n.startswith((chain/'boundaries').relative_to(RAW).as_posix()+'/') for n in MEMBERS))
                    FACTS[name]={'businessRows':[[2]],'explicitGap':True,'nextWindow':False}
                else:
                    failed=load(chain/'failed.json');owner=load(chain/'operation.lock');intent=load(chain/'intent.json');rows=source_records(chain/'boundaries/boundary-0000',False)
                    check(name+'/unknown-ACK-authority-retained',failed['reason']=='operation_failed' and failed['nonce']==owner['nonce']==intent['nonce']==state['nonce']
                          and owner['kind']==intent['kind']=='handoff' and owner['generation']==intent['generation']==0
                          and rows[-1]['kind']=='query-error' and rows[-1]['sql']=='COMMIT' and rows[-1]['error']['class']=='InjectedLostAck'
                          and not any(r['kind']=='boundary-end' for r in rows) and case['injectedAckLoss'] is True and case['actualNetworkFault'] is False)
                    pg_source=source('postgres_epoch.py')
                    check(name+'/bound-original-error-assertion','result=self.raw.execute(sql,params)' in pg_source and 'if sql=="COMMIT":raise self.original' in pg_source
                          and 'except InjectedLostAck as error:assert error is probe.original' in pg_source)
                    FACTS[name]={'injectedAfterRealCommit':True,'actualNetworkFault':False,'unknownBoundary':True,'authorityRetained':True}
        check('no-claims-promoted',all(execution[k] is False and pg[k] is False for k in ('coreProofImplemented','sourceClosureVerified','formalEligible','independentAcceptance')))
        receipt['passed']=True
    except BaseException as error:
        receipt['failure']={'class':type(error).__name__,'message':str(error)}
    finally:
        receipt.update(checks=CHECKS,checkCount=len(CHECKS),failedChecks=sum(not r['passed'] for r in CHECKS),caseFacts=FACTS,
                       initialAckFacts=INITIAL,originalZipBinding=file_binding(ZIP),zipMemberCount=len(MEMBERS),immutableGitBlobCount=len(BLOBS),
                       finished=datetime.now(timezone.utc).isoformat(),auditSourceBinding=file_binding(Path(__file__)))
        for name,value in [('zip-member-bindings.json',MEMBERS),('immutable-git-bindings.json',BLOBS),('receipt-first.json',receipt)]:
            with (HERE/name).open('x',encoding='utf8',newline='\n') as stream:json.dump(value,stream,indent=2,ensure_ascii=True);stream.write('\n')
    print(json.dumps({k:receipt[k] for k in ('passed','checkCount','failedChecks','zipMemberCount','immutableGitBlobCount','overallJobCompletionMetadataVerified')}))
    return 0 if receipt['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
