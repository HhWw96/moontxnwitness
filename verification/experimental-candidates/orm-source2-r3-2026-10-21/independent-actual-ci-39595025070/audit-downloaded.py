"""Static independent review of actual downloaded remote results; no Node/product import."""
from pathlib import Path
import base64
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CURRENT = HERE / 'independent-orm-source2-r3'
PREVIOUS = ROOT / 'artifacts/remote-ci-39593218616/independent-orm-source2-r3'
checks = []

def binding(path):
    h = hashlib.sha256(); n = 0
    with path.open('rb') as stream:
        while block := stream.read(65536): n += len(block); h.update(block)
    return {'bytes':n,'sha256':h.hexdigest()}

def sha(raw): return hashlib.sha256(raw).hexdigest()
def load(path): return json.loads(path.read_bytes())
def check(name, value):
    checks.append({'name':name,'passed':bool(value)})
    if not value: raise AssertionError(name)

def plain(value):
    if isinstance(value,list): return [plain(x) for x in value]
    if isinstance(value,dict):
        if value.get('captureType') == 'UUID': return value['value']
        return {k:plain(v) for k,v in value.items()}
    return value

def wire(field):
    raw = field['raw']
    if raw is None: return None
    assert raw['captureType']=='bytes' and field['format']==0
    text = base64.b64decode(raw['base64'],validate=True).decode('utf-8')
    if field['oid']==16:
        assert text in ('t','f'); return text=='t'
    return text

result = {'schema':1,'kind':'independent-downloaded-orm-r3-revision2-actual-audit',
          'passed':False,'complete':False,'run':39595025070,
          'workflowCommit':'7e8728a5294f8e05b001eb53a5cdb52e9225bab5',
          'originalModuleRun':39588309646,'originalModuleCommit':'ca4a81d4eddfb4d3c4f92cb0bcac86ef05320a10',
          'firstReferenceFailureRunPreserved':39593218616,
          'localProductRuntimeExecuted':False,'localDatabaseCompilationOrPerformance':False,
          'fullApplicationAccepted':False,'modelCoverageAccepted':False,'stableReleaseAccepted':False,
          'humanAcceptance':False,'checks':checks}
try:
    metadata=load(HERE/'artifacts.json')['artifacts'];assert len(metadata)==1
    actual=binding(HERE/'independent-orm-source2-r3.zip')
    check('Actual remote ZIP matches independently queried GitHub digest and size',
          'sha256:'+actual['sha256']==metadata[0]['digest'] and actual['bytes']==metadata[0]['size_in_bytes'])
    run=load(HERE/'run.json');jobs=load(HERE/'jobs.json')['jobs']
    check('Actual run and unique remote job succeeded at exact workflow commit',run['head_sha']==result['workflowCommit'] and
          run['conclusion']=='success' and len(jobs)==1 and jobs[0]['id']==119205097598 and jobs[0]['conclusion']=='success')
    profile=load(CURRENT/'profile.json');contract=load(CURRENT/'contract-v1.json')
    audit=load(CURRENT/'independent-audit.json');runtime=load(CURRENT/'result/independent-result.json')
    check('Downloaded module actual bytes are exact frozen original runtime',binding(CURRENT/'artifact/experimental-capture-core.mjs')==
          {'bytes':1573469,'sha256':'3b536b3ba28d912d04fe1ef6225c187bc4aca8dae2cf557d9e50a134a3c8945d'})
    check('Actual independent process used exact corrected driver and unchanged profile/contract',
          audit['driverSha256']=='6f2bf2fe5fcd9e67990cf43fb4069651507a1b48ee057e4da44ec4974cb2d5e3' and
          binding(CURRENT/'profile.json')==binding(PREVIOUS/'profile.json') and
          binding(CURRENT/'contract-v1.json')==binding(PREVIOUS/'contract-v1.json'))
    check('Actual remote runtime process completed Node24.13 Linux and all24 cases',audit['passed'] and audit['complete'] and
          audit['executionComplete'] and audit['stages']=={'downloadPreflight':'passed','independentRuntime':'passed'} and
          runtime['node']=='v24.13.0' and runtime['platform']=='linux' and runtime['checks']==len(runtime['cases'])==24 and
          all(c['passed'] for c in runtime['cases']))
    previous=load(PREVIOUS/'result/independent-result.json')['cases']
    check('All24 actual input hashes/lengths and frozen expected dispositions match original failed run',
          [(c['name'],c['expected'],c['inputBytes'],c['inputSha256']) for c in runtime['cases']]==
          [(c['name'],c['expected'],c['inputBytes'],c['inputSha256']) for c in previous] and
          [(c['name'],c['expected']) for c in runtime['cases']]==[(c['name'],c['expected']) for c in contract['cases']])
    reports=[]
    for i,c in enumerate(runtime['cases'],1):
        name=f"{i:02d}-{c['name']}.report.json";path=CURRENT/'result'/name
        check('Actual complete report bytes unchanged from original module: '+c['name'],
              binding(path)==binding(PREVIOUS/'result'/name) and binding(path)['sha256']==c['reportSha256'])
        reports.append(load(path))
    check('All24 reports retain global analysis refusal/nullhistory/empty verified sets',all(
          r['schema']==2 and r['algorithm']=='v3-orm-source-proof-2' and not r['analysisCoverageAccepted'] and r['history'] is None and
          all(r[x]==[] for x in ('verifiedStatements','verifiedFacts','verifiedProfiles')) and r['gaps'] for r in reports))
    check('The20 deliberately rejected reports remain source-incomplete with no proven facts',all(
          not r['controlProfileComplete'] and r['provenStatements']==[] and r['provenFacts']==[] and
          any(g['code']=='invalid_orm_source2_proof' for g in r['gaps']) for r in reports[4:]))
    for name,expected in profile['inputs'].items():
        check('Original actual public input binding '+name,binding(CURRENT/'inputs'/name)==expected)
    trace=load(CURRENT/'inputs/fixtures/diagnostic-trace.json');events={e['seq']:e for e in trace['events']}
    source_raw=(CURRENT/'inputs/fixtures/source-observations.jsonl').read_bytes();lines=source_raw.splitlines(keepends=True)
    records=[json.loads(x) for x in lines];seal=records[-1]
    check('Actual147record source seal and sequence derive from raw bytes',len(records)==147 and
          [r['sourceSeq'] for r in records]==list(range(1,148)) and seal['kind']=='seal' and
          seal['sourceRecords']==146 and seal['prefixSha256']==sha(b''.join(lines[:-1])))
    batches=[r for r in records if r['kind']=='source-batch'];controls=[r for r in records if r['kind']=='control-query']
    installation=next(r for r in records if r['kind']=='installation');final=next(r for r in records if r['kind']=='final-effect-ledger')
    facts=[];effects=[];effect_at_rows={};pk_reads=[]
    for batch in batches:
        st=events[batch['statement']];rows=events[batch['businessRowsEvent']];pg=batch['actualPGresult']
        assert st['kind']=='statement' and rows['kind']=='rows' and rows['complete'] is True
        assert st['tx']==rows['tx']==batch['tx'] and rows['statement']==st['seq']
        assert st['sql']==batch['originalSql'] and st['executedSql']==batch['executedSql'] and st['parameters']==batch['parameters']
        assert pg['status']==2 and pg['ntuples']==1 and len(pg['fields'])==8
        row=[wire(f) for f in pg['fields']]
        if batch['operation']=='get':
            names=re.findall(r'%\(([A-Za-z_][A-Za-z0-9_]*)\)s',batch['originalSql'])
            assert len(names)==1 and names[0] in ('id_1','pk_1') and list(batch['parameters'])==names
            key=plain(batch['parameters'][names[0]])
            assert batch['observation']['source']['key']==key and row[0]==(key if row[7] else None)
            assert plain(rows['rows'])==([row[:6]] if row[7] else [])
            image=dict(zip(('id','email','hashed_password','is_active','is_superuser','is_verified'),row[:6])) if row[7] else None
            data={'key':key,'version':row[6],'present':row[7],'image':image}
            assert batch['observation']['source']['version']==data['version'] and batch['observation']['source']['present']==data['present']
            if names[0]=='pk_1':pk_reads.append(batch['sourceSeq'])
        else:
            row[5]=None if row[5] is None else json.loads(row[5]);row[6]=None if row[6] is None else json.loads(row[6])
            assert batch['observation']['effectRows']==[row]
            data=dict(zip(('key','predecessor','version','oldPresent','newPresent','oldImage','newImage','action'),row))
            effect={'data':data,'tx':batch['tx'],'rows':rows['seq'],'sourceSeq':batch['sourceSeq'],'revertedBy':None,'outcome':'unknown'}
            effects.append(effect);effect_at_rows[rows['seq']]=effect
        facts.append({'kind':'read' if batch['operation']=='get' else 'write','sourceSeq':batch['sourceSeq'],
                      'statement':st['seq'],'rows':rows['seq'],'tx':batch['tx'],'data':data})
    check('Independent named-bind/native/source derivation includes exact four pk1 observations',pk_reads==[82,88,92,96])
    active={};marks={};outcomes={}
    for e in trace['events']:
        kind=e['kind']
        if kind=='begin':active[e['tx']]=[];marks[e['tx']]=[]
        if e['seq'] in effect_at_rows:active[e['tx']].append(effect_at_rows[e['seq']])
        if kind=='savepoint':marks[e['tx']].append((e['instance'],len(active[e['tx']])))
        if kind=='rollback_to':
            i=next(i for i,m in enumerate(marks[e['tx']]) if m[0]==e['instance']);keep=marks[e['tx']][i][1]
            for effect in active[e['tx']][keep:]:effect['revertedBy']=e['seq']
            active[e['tx']]=active[e['tx']][:keep];marks[e['tx']]=marks[e['tx']][:i+1]
        if kind=='release':
            i=next(i for i,m in enumerate(marks[e['tx']]) if m[0]==e['instance']);marks[e['tx']]=marks[e['tx']][:i]
        if kind=='rollback_ok':
            for effect in active[e['tx']]:effect['revertedBy']=e['seq']
            active[e['tx']]=[];outcomes[e['tx']]='aborted'
        if kind=='commit_ok':outcomes[e['tx']]='committed'
        if kind=='disconnect':outcomes[e['tx']]='unknown'
    for e in effects:e['outcome']=outcomes.get(e['tx'],'unknown')
    live=[e['data'] for e in effects if e['revertedBy'] is None and e['outcome']=='committed']
    check('Independent complete source scope replay derives8effects7ledger1revoked',len(effects)==8 and len(live)==7 and
          sum(e['revertedBy'] is not None for e in effects)==1 and {e['version']:e for e in live}=={e['version']:e for e in final['ledger']})
    state=json.loads(json.dumps(installation['metadata']['initialState']));remaining={e['version']:e for e in live}
    for key,start in list(state.items()):
        current=start
        while True:
            following=[e for e in remaining.values() if e['key']==key and e['predecessor']==current['version']]
            assert len(following)<=1
            if not following:break
            e=following[0];assert e['oldPresent']==current['present'] and e['oldImage']==current['image']
            current={'version':e['version'],'present':e['newPresent'],'image':e['newImage']};remaining.pop(e['version'])
        state[key]=current
    check('Independent predecessor closure reaches actual finalstate without ACK order',not remaining and state==final['state'])
    queries=[{'sourceSeq':q['sourceSeq'],'sqlSha256':sha(q['sql'].encode())} for q in controls]
    source_batches=[{k:f[k] for k in ('sourceSeq','statement','rows','kind')} for f in facts]
    check('Fouractual positive outputs equal independent raw121queries21facts8effects',len(controls)==121 and len(facts)==21 and all(
          r['controlProfileComplete'] and r['verifiedControlQueries']==queries and r['verifiedSourceBatches']==source_batches and
          r['candidateFacts']==facts and r['provenFacts']==facts and r['observedEffects']==effects and
          r['ledger']=={'observedEffects':8,'committedUnrevertedEffects':7,'serverLedgerEffects':7,'sourceChainsChecked':True}
          for r in reports[:4]))
    check('Actual author fourtarget616 is checked only as prerequisite',all(
          'Total tests: 616, passed: 616, failed: 0.' in (CURRENT/'artifact'/f'test-{t}.log').read_text()
          for t in ('js','wasm-gc','wasm','native')))
    result.update(passed=True,complete=True,artifact=actual,actualModule=binding(CURRENT/'artifact/experimental-capture-core.mjs'),
                  actualAudit=binding(CURRENT/'independent-audit.json'),actual24Results=binding(CURRENT/'result/independent-result.json'),
                  actualDownloadReceipt=binding(HERE/'download-receipt.json'),all24InputsUnchanged=True,all24CompleteOutputBytesUnchanged=True,
                  independentlyDerivedCounts={'rawRecords':147,'controlQueries':121,'statementBatches':21,'observedEffects':8,'survivingLedger':7,'revoked':1},
                  independentFreshRemoteRuntimeExecuted=True,independentCases=24)
except Exception as error:
    result.update(errorClass=type(error).__name__,error=str(error).replace(str(ROOT),'<repository>'))
result['checksCount']=len(checks)
path=HERE/'independent-actual-audit.json'
path.open('x',encoding='utf-8',newline='\n').write(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'receiptSha256':binding(path)['sha256']}))
raise SystemExit(0 if result['passed'] else 1)
