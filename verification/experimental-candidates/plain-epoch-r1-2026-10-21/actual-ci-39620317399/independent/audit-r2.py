"""Independent read-only audit of downloaded R1 CI evidence; no source imports.

Only stdlib reads, Git object reads and already fetched official API responses.
Never runs a candidate, tests, a consistency checker or PostgreSQL.
"""
from pathlib import Path,PurePosixPath
import ast
from datetime import datetime,timezone
import hashlib
import json
import re
import stat
import subprocess
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
ACTUAL=ROOT/'artifacts/plain-epoch-ci-r1/actual-second-39620317399'
RAW=ACTUAL/'raw'
WORK=RAW/'epoch-work-39620317399-1'
EVIDENCE=WORK/'evidence'
SOURCE='bee9e3dbdb6e9306a249fddfcd462a48a8ebc08b'
ZIP=ACTUAL/'artifact-12354338110.zip'
ZIP_SHA='36f860426993b416ddc62f45a57ebd892d69d7799991818b6a33b7f890399232'
R1='verification/experimental-candidates/plain-epoch-r1-2026-10-21'
R2='verification/experimental-candidates/plain-journal-r2-2026-10-21'
PREFIX='artifacts/plain-v3-epoch-r1'
checks=[];summaries={};zip_bindings={};git_bindings={};catalog_differences=[]


def unique(items):
    output={}
    for k,v in items:
        if k in output:raise ValueError('Duplicate JSON field')
        output[k]=v
    return output


def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)


def raw(path,limit=16777216):
    if path.is_symlink() or not path.is_file():raise ValueError('Regular artifact required')
    with path.open('rb') as f:value=f.read(limit+1)
    if len(value)>limit:raise ValueError('Read bound')
    return value


def digest(data):return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def binding(path):return digest(raw(path))
def load(path):return json.loads(raw(path),object_pairs_hook=unique)
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()


def relative(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or p.as_posix()!=value or '\\' in value or ':' in value:
        raise ValueError('Unsafe relative artifact name')
    return value


def git_file(name):
    relative(name)
    result=subprocess.check_output(['git','-c','core.longpaths=true','ls-tree','-z',SOURCE,'--',name],cwd=ROOT)
    fields=result.rstrip(b'\0').split(b'\t')
    if len(fields)!=2 or fields[1].decode()!=name:raise ValueError('Exact source Git entry required')
    meta=fields[0].split();assert meta[0]==b'100644' and meta[1]==b'blob'
    data=subprocess.check_output(['git','cat-file','blob',meta[2].decode()],cwd=ROOT)
    if len(data)>1048576:raise ValueError('Source Git blob budget')
    git_bindings[name]={'gitBlob':meta[2].decode(),**digest(data)}
    return data


def source_log(path,complete):
    index=load(path/'index.json');data=raw(path/'records.jsonl',8388608)
    previous='0'*64;records=[]
    for seq,line in enumerate(data.splitlines(keepends=True),1):
        check(f'{path.relative_to(WORK)}/line{seq}',len(line)<=65536 and line.endswith(b'\n'))
        event=json.loads(line,object_pairs_hook=unique)
        check(f'{path.relative_to(WORK)}/chain{seq}',event['sourceSchema']==1 and event['seq']==seq and event['previous']==previous)
        previous=hashlib.sha256(line).hexdigest();records.append(event['payload'])
    check(f'{path.relative_to(WORK)}/index',index['records']==len(records) and index['bytes']==len(data)
          and index['sha256']==hashlib.sha256(data).hexdigest() and index['lastRecordSha256']==previous)
    check(f'{path.relative_to(WORK)}/closure',index['closed'] is complete and (path/'writer.lock').exists() is (not complete))
    return records


def journal(path,complete):
    index=load(path/'journal-index.json')
    check(f'{path.relative_to(WORK)}/index-self-hash',index['indexSha256']==hashlib.sha256(canonical({k:v for k,v in index.items() if k!='indexSha256'})).hexdigest())
    events=[];last_time=-1
    for segment in index['segments']:
        name=relative(segment['name']);data=raw(path/name)
        check(f'{path.relative_to(WORK)}/{name}/bytes',digest(data)=={k:segment[k] for k in ('bytes','sha256')})
        rows=[json.loads(line,object_pairs_hook=unique) for line in data.splitlines()]
        check(f'{path.relative_to(WORK)}/{name}/range',len(rows)==segment['eventCount'] and rows[0]['seq']==segment['firstSeq'] and rows[-1]['seq']==segment['lastSeq'])
        for event in rows:
            check(f'{path.relative_to(WORK)}/event{event["seq"]}',event['seq']==len(events)+1 and type(event['time']) is int and event['time']>=last_time)
            last_time=event['time'];events.append(event)
    check(f'{path.relative_to(WORK)}/event-count',len(events)==index['eventCount']==index['durableSeq'] and index['lastTime']==last_time)
    check(f'{path.relative_to(WORK)}/closure',index['closed'] is True and index['sourceClosed'] is complete
          and (not complete or (index['gaps']==[] and index['activeTransactions']==[] and index['commitRequests']==[])))
    check(f'{path.relative_to(WORK)}/no-prune',index['retention']['deletionImplemented'] is False and index['transactionIndex']['authoritative'] is False)
    return events,index


def native(value):
    if not isinstance(value,dict):return value
    kind=value['nativeType'];items=[native(x) for x in value['items']]
    if kind=='list':return items
    if kind=='tuple':return tuple(items)
    raise ValueError('Unexpected native transport in controlled fixture')


def catalog_rows_equal(before,after,label,sql_schema,prefix):
    query=("SELECT c.contype,c.conkey::smallint[],c.condeferrable,c.condeferred,c.convalidated,"
        "rn.nspname,r.relname,c.confkey::smallint[],c.confupdtype,c.confdeltype,c.confmatchtype,"
        "c.conenforced,c.conislocal,c.coninhcount,c.conparentid,c.connoinherit,c.conperiod "
        "FROM pg_catalog.pg_constraint c LEFT JOIN pg_catalog.pg_class r ON r.oid=c.confrelid "
        "LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid=r.relnamespace "
        "WHERE c.conrelid=%s::regclass ORDER BY c.contype")
    if before['sql']!=query:return before['nativeRows']==after['nativeRows']
    target=native(before['parameters'])[0]
    suffix=next((name for name in ('installation','audit','state') if target.endswith(prefix+'_'+name+'"')),None)
    check(label+'/known-metadata-target',suffix is not None)
    columns={'installation':[1,2,3],'audit':[1,2,3,4],'state':[1,2,3]}[suffix]
    expected=[('n',[n],False,False,True,None,None,None,' ',' ',' ',True,True,0,0,False,False) for n in columns]
    expected.append(('p',[1],False,False,True,None,None,None,' ',' ',' ',True,True,0,0,True,False))
    if suffix!='installation':expected.append(('f',[5 if suffix=='audit' else 2],False,False,True,sql_schema,prefix+'_audit',[1],'a','a','s',True,True,0,0,True,False))
    expected_set=sorted(canonical(row) for row in expected)
    actual_before,actual_after=native(before['nativeRows']),native(after['nativeRows'])
    for name,rows in [('before',actual_before),('after',actual_after)]:
        check(label+'/'+name+'/exact-constraint-facts',sorted(canonical(row) for row in rows)==expected_set)
        check(label+'/'+name+'/promised-contype-order',[row[0] for row in rows]==sorted(row[0] for row in rows))
    if before['nativeRows']!=after['nativeRows']:
        catalog_differences.append({'boundary':label,'sql':query,'parameters':native(before['parameters']),
            'beforeRows':actual_before,'afterRows':actual_after,'reason':'ORDER BY contype leaves ties unspecified; full17-field row multiset remains exact, duplicates forbidden by exact expected rows.'})
    return True


def boundary(chain,entry):
    path=chain/'boundaries'/relative(entry['name'])
    check(f'{chain.parent.name}/{entry["name"]}/file-set',set(p.name for p in path.iterdir())==set(entry['files']))
    for name,b in entry['files'].items():check(f'{chain.parent.name}/{entry["name"]}/{name}',binding(path/name)==b)
    rows=source_log(path,True);summary=entry['summary']
    check(f'{chain.parent.name}/{entry["name"]}/footer',rows[-1]=={'kind':'boundary-end','summary':summary})
    sql_schema=chain_state[chain.parent.name]['scope']['schema'];table=chain_state[chain.parent.name]['scope']['table']
    def ident(s):return '"'+s.replace('"','""')+'"'
    prefix='mtwp_'+hashlib.sha256((table+'\0column').encode()).hexdigest()[:16]
    business=ident(sql_schema)+'.'+ident(table)
    objects=[ident(sql_schema)+'.'+ident(prefix+'_'+part) for part in ('installation','audit','state')]
    expected_lock='LOCK TABLE '+','.join([business]+objects)+' IN ACCESS EXCLUSIVE MODE'
    check(f'{chain.parent.name}/{entry["name"]}/begin',rows[0]['sql']=='BEGIN ISOLATION LEVEL READ COMMITTED' and rows[0]['commandTag']=='BEGIN' and rows[0]['pgStatus']==1 and rows[0]['statusAfter']==2)
    check(f'{chain.parent.name}/{entry["name"]}/actual-identity',rows[1]['sql']=='SELECT pg_backend_pid(),pg_current_xact_id()::text'
          and native(rows[1]['nativeRows'])==[(summary['backendPid'],summary['transaction'])])
    check(f'{chain.parent.name}/{entry["name"]}/all-locks',summary['lockSeq']==3 and rows[2]['sql']==expected_lock and rows[2]['commandTag']=='LOCK TABLE' and rows[2]['pgStatus']==1)
    for i,row in enumerate(rows[:-1],1):
        check(f'{chain.parent.name}/{entry["name"]}/connection{i}',row['connection']==summary['connection'] and row['backendPid']==summary['backendPid']
              and (i<=2 or row['transaction']==summary['transaction']))
    commit=rows[summary['commitSeq']-1]
    check(f'{chain.parent.name}/{entry["name"]}/commit-ack',commit['sql']=='COMMIT' and commit['commandTag']=='COMMIT' and commit['pgStatus']==1 and commit['statusBefore']==2 and commit['statusAfter']==0 and native(commit['nativeRows'])==[] and commit['complete'] is True)
    a,b=summary['verifyRanges']
    first,second=rows[a[0]-1:a[1]],rows[b[0]-1:b[1]]
    # Compare the actual before/after catalog SQL, parameters and returned rows.
    # This is not an independent full general SQL-provenance implementation.
    check(f'{chain.parent.name}/{entry["name"]}/catalog-ranges',len(first)==len(second)==22 and all(
        {k:x[k] for k in ('sql','parameters','fetch','complete','pgStatus')}==
        {k:y[k] for k in ('sql','parameters','fetch','complete','pgStatus')}
        and catalog_rows_equal(x,y,f'{chain.parent.name}/{entry["name"]}/catalog',sql_schema,prefix)
        and x['complete'] is True and x['pgStatus']==2 for x,y in zip(first,second)))
    check(f'{chain.parent.name}/{entry["name"]}/catalog-installation',native(first[0]['nativeRows'])==[(summary['nonce'],'column',summary['tableOid'])])
    def snapshot(span):
        output={}
        for row in rows[span[0]-1:span[1]]:
            check(f'{chain.parent.name}/{entry["name"]}/snapshot-query{row["part"]}',row['kind']=='query' and row['fetch']=='many' and row['pgStatus']==2
                  and row['sql']=='SELECT "id","value",'+ident(prefix+'_version')+'::text FROM '+business+' ORDER BY "id" LIMIT 65')
            for key,value,token in native(row['nativeRows']):
                check(f'{chain.parent.name}/{entry["name"]}/snapshot-key-{key}',key not in output and type(value) is int and str(uuid.UUID(token))==token)
                output[key]=(value,token)
        check(f'{chain.parent.name}/{entry["name"]}/snapshot-coverage',set(output)=={'k','other'})
        return output
    final=snapshot(summary['finalSnapshot']);following=snapshot(summary['nextSnapshot'])
    check(f'{chain.parent.name}/{entry["name"]}/snapshot-stable',final==following)
    ledger=[];lo,hi=summary['ledgerRange'];batches=rows[lo-1:hi]
    for row in batches:
        check(f'{chain.parent.name}/{entry["name"]}/ledger-query-{row["countThrough"]}',row['kind']=='ledger-batch' and row['pgStatus']==2
              and row['sql']=='SELECT token::text,key,action,present,predecessor::text,old_value,new_value FROM '+objects[1]+' ORDER BY token')
        ledger.extend(native(row['nativeRows']))
        check(f'{chain.parent.name}/{entry["name"]}/ledger-count-{len(ledger)}',row['countThrough']==len(ledger))
    check(f'{chain.parent.name}/{entry["name"]}/ledger-exhausted',batches[-1]['exhausted'] is True and native(batches[-1]['nativeRows'])==[] and len(ledger)==summary['ledgerRows']
          and len({row[0] for row in ledger})==len(ledger))
    by_token={row[0]:row for row in ledger}
    check(f'{chain.parent.name}/{entry["name"]}/snapshot-from-ledger',all(token in by_token and by_token[token][1]==key and by_token[token][3] is True and by_token[token][6]==value for key,(value,token) in final.items()))
    return {'summary':summary,'final':final,'ledger':ledger}


def main():
    receipt={'schema':1,'kind':'independent-AI-read-only-actual-R1-evidence-audit','run':39620317399,'sourceCommit':SOURCE,
        'passed':False,'actualTestsReexecuted':False,'actualDatabaseReexecuted':False,'candidateModulesImported':False,
        'formalPerformanceMeasured':False,'sourceClosureVerified':False,'coreProofImplemented':False,'formalEligible':False,
        'scope':'Controlled47 unit/4 actual PG raw evidence, source binding and facts; not independent general SQL proof, R2 acceptance, release, human adoption or organizer acceptance.',
        'limits':['Original exception object identity is an assertion in byte-bound actual executed fixture, not reconstructed from JSON alone.',
                  'Catalog SQL/parameters/rows are compared before/after; exact17-field metadata constraints use contype order plus complete row multiset because tied contype order is unspecified. No new independent full SQL-core verifier is claimed.',
                  'Unknown ACK is deliberately injected after real COMMIT, not an actual network fault.']}
    try:
        api=load(HERE/'official-run.json');artifact=load(HERE/'official-artifact.json');jobs=load(HERE/'official-jobs.json')
        check('fresh-official-run',api['id']==39620317399 and api['head_sha']==SOURCE and api['status']=='completed' and api['conclusion']=='success' and api['run_attempt']==1)
        check('fresh-official-artifact',artifact['id']==12354338110 and artifact['workflow_run']['id']==39620317399 and artifact['workflow_run']['head_sha']==SOURCE
              and artifact['name']=='two-epoch-first-raw' and artifact['digest']=='sha256:'+ZIP_SHA and artifact['size_in_bytes']==939621)
        check('fresh-official-job',jobs['total_count']==1 and jobs['jobs'][0]['conclusion']=='success' and jobs['jobs'][0]['head_sha']==SOURCE
              and all(step['conclusion']=='success' for step in jobs['jobs'][0]['steps']))
        check('downloaded-ZIP-official-digest',binding(ZIP)=={'bytes':939621,'sha256':ZIP_SHA})
        with zipfile.ZipFile(ZIP) as z:
            infos=z.infolist();check('bounded-ZIP-inventory',len(infos)==740 and sum(i.file_size for i in infos)==4249537 and len({i.filename for i in infos})==740)
            for info in infos:
                name=relative(info.filename)
                check('ZIP-regular-'+name,not info.is_dir() and info.file_size<=16777216 and not stat.S_ISLNK(info.external_attr>>16))
                value=z.read(info);item=digest(value)
                check('ZIP-original-bytes-'+name,item['bytes']==info.file_size and binding(RAW/name)==item)
                zip_bindings[name]=item
        check('no-extra-unpacked-files',set(zip_bindings)=={p.relative_to(RAW).as_posix() for p in RAW.rglob('*') if p.is_file()})
        new=json.loads(git_file(R1+'/bundle-index.json'));old=json.loads(git_file(R2+'/bundle/bundle-index.json'))
        sources_expected={name:{k:v[k] for k in ('bytes','sha256')} for name,v in old['files'].items()}
        for name,v in old['files'].items():check('immutable-Git-old-source-'+name,digest(git_file(R2+'/bundle/'+v['bundleFile']))==sources_expected[name])
        for name,v in new['files'].items():check('immutable-Git-new-source-'+name,digest(git_file(R1+'/bundle/'+name))==v)
        sources_expected.update(new['files'])
        check('all-restored-source-count',len(sources_expected)==97)
        for name,b in sources_expected.items():check('actual-restored-source-'+name,binding(WORK/'repository'/name)==b)
        execution=load(EVIDENCE/'execution-receipt.json')
        check('actual-source-before-after',execution['sourceCommit']==SOURCE and execution['workflowCommit']==SOURCE and execution['run']=='39620317399'
              and execution['allSourceBindingsBefore']==sources_expected==execution['allSourceBindingsAfter'])
        context=RAW/'epoch-context-39620317399-1';source_context=load(context/'source.json')
        check('actual-immutable-context',source_context['actualSource']==source_context['requestedSource']==source_context['workflowSource']==SOURCE and source_context['databaseExecutedAtContextCreation'] is False)
        workflow=git_file('.github/workflows/experimental-plain-epoch.yml').decode();runner=git_file('scripts/experimental_plain_epoch_ci.py')
        check('actual-pinned-fixture-workflow','postgres:18.6-bookworm@sha256:afc7e2d441324c0388fa80c3d24f733b4194a4eb7f47dd8ee2b08eb1a24a647c' in workflow and "python-version: '3.12.5'" in workflow)
        check('actual-server-and-driver-log',b'PostgreSQL 18.6' in raw(context/'postgres.log') and b'psycopg-3.3.6' in raw(context/'driver.log')
              and re.fullmatch(r'sha256:[0-9a-f]{64}\n',raw(context/'postgres-image.txt').decode()) is not None)
        for stage in execution['stages']:check('actual-stage-'+stage['name'],stage['executed'] is True and stage['exitCode']==0 and binding(EVIDENCE/stage['log'])==stage['logBinding'])
        check('actual-stage-inventory',[s['name'] for s in execution['stages']]==['unit-first','postgres-first'])
        unit_path=WORK/relative(execution['unitReceipt']['path']);unit=load(unit_path)
        check('actual-unit-receipt-binding',binding(unit_path)=={k:execution['unitReceipt'][k] for k in ('bytes','sha256')})
        declared={name:b for name,b in new['files'].items() if PurePosixPath(name).parent.as_posix()==PREFIX and PurePosixPath(name).suffix in ('.py','.json') and PurePosixPath(name).name!='candidate-index.json'}
        declared.update({name:b for name,b in new['dependencies'].items() if name not in ('examples/postgres-requirements.txt','integrations/python/moontxnwitness_capture/__init__.py')})
        check('actual-unit-exact-source',unit['sourceBindingsBefore']==declared==unit['sourceBindingsAfter'])
        check('actual-unit-47-not-PG',unit['tests']==47 and unit['syntaxFiles']==5 and unit['failures']==[] and unit['skipped']==[] and unit['actualDatabaseExecution'] is False)
        test_source=raw(WORK/'repository'/PREFIX/'test_epoch.py');tree=ast.parse(test_source)
        expected_tests={n.name for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='EpochTests' for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
        actual_tests=re.findall(r'^(test_\S+) \(__main__\.EpochTests\.\S+\) \.\.\. ok$',raw(EVIDENCE/'unit-first.log').decode(),re.M)
        check('actual-unit-each-first-result',len(expected_tests)==len(actual_tests)==47 and set(actual_tests)==expected_tests and 'Ran 47 tests' in raw(EVIDENCE/'unit-first.log').decode())
        pg=load(EVIDENCE/'postgres/postgres-receipt.json');declared['integrations/python/moontxnwitness_capture/__init__.py']=new['dependencies']['integrations/python/moontxnwitness_capture/__init__.py']
        check('actual-PG-exact-source',pg['sourceBindingsBefore']==declared==pg['sourceBindingsAfter'] and pg['serverVersion']==180006 and pg['driver']=='3.3.6')
        cases={c['name']:c for c in pg['cases']}
        check('actual-PG-four-cases',list(cases)==['two-epochs-same-value','rollback-and-savepoint','unsupported-statement','discarded-setup-commit-ack'])
        global chain_state
        chain_state={}
        for name,case in cases.items():
            case_root=EVIDENCE/'postgres'/name;chain=case_root/'chain'
            check(name+'/standalone-receipt',load(case_root/'case-receipt.json')==case)
            actual={p.relative_to(chain).as_posix():binding(p) for p in chain.rglob('*') if p.is_file()}
            check(name+'/raw-all-files',actual==case['rawFileBindings'])
            state=load(chain/'manifest.json');chain_state[name]=state
            check(name+'/unproved-flags',all(state[k] is False for k in ('sourceClosureVerified','coreProofImplemented','formalEligible'))
                  and case['actualDatabaseExecution'] is True and case['coreProofImplemented'] is False and case['formalEligible'] is False)
            positive=name in ('two-epochs-same-value','rollback-and-savepoint')
            if positive:
                check(name+'/closed-two-epochs',state['generation']==2 and state['phase']=='closed' and state['current'] is None
                      and [r['epoch'] for r in state['sealed']]==['epoch-0000','epoch-0001'] and len(state['boundaries'])==2
                      and not any((chain/p).exists() for p in ('operation.lock','intent.json','failed.json')))
                parsed=[]
                for entry in state['sealed']:
                    epoch=chain/'epochs'/entry['epoch']
                    check(name+'/'+entry['epoch']+'/sealed-hashes',{p.relative_to(epoch).as_posix():binding(p) for p in epoch.rglob('*') if p.is_file()}==entry['files'])
                    events,index=journal(epoch/'journal',True);side=source_log(epoch/'sources',True)
                    check(name+'/'+entry['epoch']+'/snapshot',events[0]['kind']=='snapshot' and events[0]['consistent'] is True)
                    parsed.append((events,side))
                transitions=[boundary(chain,b) for b in state['boundaries']]
                check(name+'/cross-epoch-raw-token-map',parsed[1][0][0]['initial']=={key:value[1] for key,value in transitions[0]['final'].items()})
                init=parsed[1][1][0]
                check(name+'/cross-epoch-bound-original-source',init['kind']=='boundary-initialization' and init['boundaryId']==state['boundaries'][0]['name']
                      and init['boundaryBindings']==state['boundaries'][0]['files'] and init['boundarySummary']==state['boundaries'][0]['summary']
                      and init['initialRows']==[[key,value,token] for key,(value,token) in sorted(transitions[0]['final'].items())])
                for i,(_,side) in enumerate(parsed):
                    footer=side[-1];b=state['boundaries'][i]
                    check(name+'/epoch'+str(i)+'/footer',footer['kind']=='ledger-end' and footer['complete'] is True and footer['commandTag']=='COMMIT'
                          and footer['boundaryId']==b['name'] and footer['boundaryBindings']==b['files'] and footer['rows']==b['summary']['ledgerRows'])
                first_events,first_side=parsed[0];writes=[e for e in first_events if e['kind']=='write']
                if name=='two-epochs-same-value':
                    check(name+'/distinct-equal-value-write-identities',len(writes)==2 and writes[0]['version']!=writes[1]['version'] and [w['version'] for w in writes]==case['writeTokens'])
                    by_seq={e['seq']:e for e in first_events}
                    check(name+'/original-equal-business-values',[by_seq[w['statement']]['parameters'] for w in writes]==[[5,'k'],[5,'k']]
                          and writes[1]['predecessor']==writes[0]['version'])
                    check(name+'/same-transaction-self-read',any(e['kind']=='read' and e['version']==writes[1]['version'] and e['tx']==writes[1]['tx'] for e in first_events))
                    check(name+'/actual-committed-ledger-tokens',all(w['version'] in {r[0] for r in transitions[0]['ledger']} for w in writes)
                          and transitions[0]['final']['k']==(5,writes[1]['version']) and transitions[1]['final']['k'][0]==7)
                    summaries[name]={'writeTokens':[w['version'] for w in writes],'actualInitialValue':5,'actualFinalValue':7,'crossEpochContinuity':True}
                else:
                    check(name+'/three-raw-writes-retained',len(writes)==3 and len({w['version'] for w in writes})==3)
                    kinds=[e['kind'] for e in first_events];save=next(e for e in first_events if e['kind']=='savepoint');undo=next(e for e in first_events if e['kind']=='rollback_to');release=next(e for e in first_events if e['kind']=='release')
                    check(name+'/actual-savepoint-identity',save['instance']==undo['instance']==release['instance'] and save['seq']<writes[2]['seq']<undo['seq']<release['seq']
                          and writes[0]['tx']!=writes[1]['tx']==writes[2]['tx'] and any(e['kind']=='rollback_ok' and e['tx']==writes[0]['tx'] for e in first_events))
                    tokens={r[0] for r in transitions[0]['ledger']}
                    check(name+'/rolled-effects-absent-from-actual-ledger',writes[1]['version'] in tokens and writes[0]['version'] not in tokens and writes[2]['version'] not in tokens
                          and case['actualCommittedWriteTokens']==[writes[1]['version']] and transitions[0]['final']['k']==(10,writes[1]['version']))
                    summaries[name]={'allRawWriteTokens':[w['version'] for w in writes],'actualCommittedToken':writes[1]['version'],'rawAbortedAndRevertedRetained':2}
            else:
                check(name+'/never-published-next-epoch',state['generation']==0 and state['phase']=='running' and state['boundaries']==[] and state['sealed']==[] and not (chain/'epochs/epoch-0001').exists())
                events,index=journal(chain/'epochs/epoch-0000/journal',False);side=source_log(chain/'epochs/epoch-0000/sources',True)
                check(name+'/no-complete-ledger-footer',all(r['kind']!='ledger-end' for r in side))
                if name=='unsupported-statement':
                    check(name+'/raw-business-result-preserved',any(e['kind']=='statement' and e['sql'].startswith('SELECT value+1 FROM ') for e in events)
                          and any(e['kind']=='rows' and e['rows']==[[2]] for e in events) and not any(e['kind']=='read' for e in events))
                    check(name+'/gap-and-no-authority-created',{'unknown_sql','ledger_not_finalized'}<={g['code'] for g in index['gaps']}
                          and not (chain/'operation.lock').exists() and not (chain/'intent.json').exists() and not any((chain/'boundaries').iterdir()))
                    summaries[name]={'actualBusinessRows':[[2]],'explicitUnknownSqlGap':True,'nextEpochPublished':False}
                else:
                    failed=load(chain/'failed.json');owner=load(chain/'operation.lock');intent=load(chain/'intent.json')
                    check(name+'/recovery-authority-retained',failed['reason']=='operation_failed' and failed['nonce']==owner['nonce']==intent['nonce']==state['nonce']
                          and owner['kind']==intent['kind']=='handoff' and owner['generation']==intent['generation']==0)
                    failed_rows=source_log(chain/'boundaries/boundary-0000',False)
                    check(name+'/raw-unknown-COMMIT-preserved',failed_rows[-1]['kind']=='query-error' and failed_rows[-1]['sql']=='COMMIT'
                          and failed_rows[-1]['error']['class']=='InjectedLostAck' and not any(row['kind']=='boundary-end' for row in failed_rows))
                    check(name+'/injected-not-network',case['injectedAckLoss'] is True and case['actualNetworkFault'] is False)
                    pg_source=raw(WORK/'repository'/PREFIX/'postgres_epoch.py').decode()
                    check(name+'/exception-identity-assertion-executed','result=self.raw.execute(sql,params)' in pg_source
                          and 'if sql=="COMMIT":raise self.original' in pg_source and 'except InjectedLostAck as error:assert error is probe.original' in pg_source)
                    summaries[name]={'unknownCommitRetained':True,'nextEpochPublished':False,'injectedAfterRealCommit':True,'actualNetworkFault':False,
                        'exceptionIdentityEvidence':'Actual frozen fixture assertion; no object identity inferred from JSON.'}
        check('unproved-flags-remain-visible',all(execution[k] is False and pg[k] is False for k in ('coreProofImplemented','sourceClosureVerified','formalEligible','independentAcceptance')))
        first=load(HERE/'official-first-failure.json')
        check('earlier-run-not-silently-replaced',first['id']==39619434773 and first['conclusion']=='failure' and first['id']!=api['id'])
        receipt['passed']=True
    except BaseException as error:
        receipt['failure']={'class':type(error).__name__,'message':str(error)}
    finally:
        receipt.update(checks=checks,checkCount=len(checks),failedChecks=sum(not c['passed'] for c in checks),caseFacts=summaries,
            originalZipBinding=binding(ZIP),zipMemberCount=len(zip_bindings),immutableGitBlobCount=len(git_bindings),
            finished=datetime.now(timezone.utc).isoformat(),auditSourceBinding=binding(Path(__file__)),catalogOrderDifferences=catalog_differences,
            priorIndependentAttempt={'tool':binding(HERE/'audit-r1.py'),'receipt':binding(HERE/'receipt-r1.json'),'failedCheck':'rollback-and-savepoint/boundary-0001/catalog-ranges','reason':'Auditor required tie ordering not promised by SQL. Original first result retained.'})
        for name,value in [('zip-member-bindings-r2.json',zip_bindings),('immutable-git-bindings-r2.json',git_bindings),('receipt-r2.json',receipt)]:
            with (HERE/name).open('x',encoding='utf8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=True);f.write('\n')
    print(json.dumps({k:receipt[k] for k in ('passed','checkCount','failedChecks','zipMemberCount','immutableGitBlobCount')}))
    return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
