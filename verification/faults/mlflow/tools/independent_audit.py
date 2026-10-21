"""Independent byte/AST/raw-SQL and executable audit of a controlled MLflow case.

No production Python import, database, compilation, dependency installation or
upstream source rewrite. Only a new audit directory is created.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
SHA = lambda raw: hashlib.sha256(raw).hexdigest()
LOAD = lambda path: json.loads(path.read_bytes())


def immutable(path, value):
    raw = value.encode('utf8') if isinstance(value, str) else (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('utf8')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    return {'file': path.relative_to(ROOT).as_posix(), 'bytes': len(raw), 'sha256': SHA(raw)}


NODE = r'''
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const [root,db,out]=process.argv.slice(2),sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
const load=p=>JSON.parse(readFileSync(p,'utf8')),copy=x=>structuredClone(x),hash=x=>createHash('sha256').update(x).digest('hex');
const cases=[],retain=(name,value)=>writeFileSync(resolve(out,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const check=(name,fn)=>{try{fn();cases.push({name,passed:true});}catch(e){cases.push({name,passed:false,error:String(e.message).replaceAll(root,'<workspace>')});}};
const before=load(resolve(db,'before/capture.json')),fixed=load(resolve(db,'fixed/capture.json'));
for(const[label,t]of[['before',before],['fixed',fixed]]){
  check('actual-'+label+'-faults-are-observations-only',()=>{const d=sdk.inspectExecutionFailuresV3(t);retain(label+'-faults.json',d);
    assert.equal(d.valid,true);assert.equal(d.status,'observations');assert.equal(d.captureCoverage.complete,false);
    assert.equal(d.modelViolationClaim,false);assert.equal(d.databaseAuthenticityVerified,false);assert.equal(d.certifiesFailureAbsence,false);
    assert.equal(d.observedFaultCount,label==='before'?1:0);
    const errors=t.events.filter(e=>e.kind==='rows'&&e.error);
    for(let i=0;i<errors.length;i++){const e=errors[i],f=d.faults[i],statement=t.events.find(s=>s.seq===e.statement);
      assert.deepEqual({seq:f.seq,tx:f.tx,statement:f.statement,sqlstate:f.sqlstate,driverClass:f.driverClass},
        {seq:e.seq,tx:e.tx,statement:e.statement,sqlstate:e.error.sqlstate,driverClass:e.error.class});
      assert.equal(statement.kind,'statement');assert.equal(statement.tx,e.tx);assert.equal(f.kind,'deadlock');assert.equal(f.origin,'rows.error');
    }
  });
  check('actual-'+label+'-default-analysis-stays-incomplete',()=>{const r=sdk.analyzeV3(t);retain(label+'-report.json',r);
    assert.equal(r.status,'inconclusive');assert.equal(r.coverage.complete,false);assert.equal(r.evidence,null);
    assert.equal(sdk.verifyV3(t,r).valid,true);const c=sdk.makeCapsuleV3(t,r);writeFileSync(resolve(out,label+'-capsule.json'),c,{flag:'wx'});
    assert.equal(sdk.replayCapsuleV3(c).valid,true);assert.deepEqual(r.normalized.observations,t.events);
    const altered=JSON.parse(c),trace=JSON.parse(altered.traceText);
    if(label==='before')trace.events.find(e=>e.kind==='rows'&&e.error).error.sqlstate='40001';else trace.scope.exclusiveWriters=true;
    altered.traceText=JSON.stringify(trace);altered.traceSha256=hash(altered.traceText);
    assert.equal(sdk.replayCapsuleV3(JSON.stringify(altered)).valid,false);
  });
}
const rowIndex=before.events.findIndex(e=>e.kind==='rows'&&e.error);
for(const[state,kind]of[['40P01','deadlock'],['40001','serialization_abort'],['55P03','lock_not_available'],['57014','query_canceled'],['23505','statement_error'],[null,'statement_error']])
  check('declared-sqlstate-'+String(state),()=>{const t=copy(before);t.events[rowIndex].error.sqlstate=state;const d=sdk.inspectExecutionFailuresV3(t);
    assert.equal(d.valid,true);assert.equal(d.faults[0].kind,kind);assert.equal(d.modelViolationClaim,false);
    assert.equal(d.databaseAuthenticityVerified,false);assert.equal(sdk.analyzeV3(t).status,'inconclusive');
  });
const invalids={
  'wrong-statement-reference':t=>t.events[rowIndex].statement=1,
  'cross-transaction-reference':t=>t.events[rowIndex].tx=t.events.find(e=>e.kind==='begin'&&e.tx!==t.events[rowIndex].tx).tx,
  'duplicate-sequence':t=>t.events[rowIndex].seq=t.events[rowIndex-1].seq,
  'wrong-schema':t=>t.traceSchema=2,
  'invalid-sqlstate':t=>t.events[rowIndex].error.sqlstate='40p01',
  'error-field-injection':t=>t.events[rowIndex].error.claimG2=true,
};
for(const[name,mutate]of Object.entries(invalids))check('invalid-'+name,()=>{const t=copy(before);mutate(t);retain('invalid-'+name+'.json',t);
  const d=sdk.inspectExecutionFailuresV3(t);assert.equal(d.valid,false);assert.equal(d.status,'invalid');assert.deepEqual(d.faults,[]);
});
check('missing-error-observation-never-certifies-absence',()=>{const t=copy(before);delete t.events[rowIndex].error;const d=sdk.inspectExecutionFailuresV3(t);
  assert.equal(d.valid,true);assert.equal(d.observedFaultCount,0);assert.equal(d.certifiesFailureAbsence,false);assert.equal(d.captureCoverage.complete,false);assert.equal(sdk.analyzeV3(t).status,'inconclusive');
});
check('malformed-json-fails-closed',()=>{assert.equal(sdk.inspectExecutionFailuresV3('{').valid,false);});
check('duplicate-json-key-fails-closed',()=>{assert.equal(sdk.inspectExecutionFailuresV3(JSON.stringify(before).replace('{','{"traceSchema":3,')).valid,false);});
const unknown=load(resolve(root,'fixtures/v3/rollback-after-request-not-proof.json'));
check('unknown-commit-not-inferred-as-error-or-abort',()=>{const d=sdk.inspectExecutionFailuresV3(unknown);assert.equal(d.valid,true);assert.equal(d.captureStatus,'inconclusive');assert.equal(d.observedFaultCount,0);assert.ok(d.transactionOutcomes.some(t=>t.status==='unknown'));});
const commit={traceSchema:3,clockDomain:'independent-synthetic-commit-protocol',scope:{exclusiveWriters:true},gaps:[],events:[
  {seq:1,time:1,kind:'snapshot',initial:{x:'x0'},consistent:true},{seq:2,time:2,kind:'begin',tx:'T',connection:'c'},
  {seq:3,time:3,kind:'commit_request',tx:'T'},{seq:4,time:4,kind:'rollback_ok',tx:'T',commitResponse:{request:3,sqlstate:'40P01',diagnosticSqlstate:'40P01',transactionStatus:'IDLE'}}]};
check('synthetic-commit-response-retains-sequence-provenance',()=>{const t=commit,d=sdk.inspectExecutionFailuresV3(t);assert.equal(d.valid,true);const e=t.events.find(e=>e.kind==='rollback_ok'&&e.commitResponse);assert.ok(e);const f=d.faults.find(f=>f.seq===e.seq);assert.ok(f);assert.equal(f.request,e.commitResponse.request);assert.equal(f.origin,'rollback_ok.commitResponse');assert.equal(d.modelViolationClaim,false);});
check('synthetic-inconsistent-commit-diagnostic-refused',()=>{const t=copy(commit);t.events[3].commitResponse.diagnosticSqlstate='40001';assert.equal(sdk.inspectExecutionFailuresV3(t).valid,false);});
for(const label of['before','fixed'])check('cli-actual-'+label+'-failures',()=>{const p=spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),'failures-v3',resolve(db,label,'capture.json')],{cwd:root,encoding:'utf8',timeout:30000,windowsHide:true,maxBuffer:16*1024*1024});retain('cli-'+label+'.json',{exitCode:p.status,stdout:p.stdout,stderr:p.stderr,error:p.error?.name??null});assert.equal(p.error,undefined);assert.equal(p.status,0);const d=JSON.parse(p.stdout);assert.equal(d.valid,true);assert.equal(d.status,'observations');assert.equal(d.captureCoverage.complete,false);assert.equal(d.modelViolationClaim,false);assert.equal(d.observedFaultCount,label==='before'?1:0);});
const result={passed:cases.every(c=>c.passed),checks:cases.length,cases,localDatabaseExecution:false,localBuild:false};retain('runtime-result.json',result);console.log(JSON.stringify(result));if(!result.passed)process.exitCode=1;
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = args.output or ROOT/'verification/faults/mlflow'/('independent-'+datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S-%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    receipt = {'schema':1,'kind':'independent-mlflow-component-execution-fault-audit','passed':False,'complete':False,
               'independentAIAcceptance':True,'humanAcceptance':False,'localDatabaseExecution':False,'localBuild':False,
               'fullMlflowApplicationExecuted':False,'stableReleaseAccepted':False,'formalPerformanceMeasured':False,
               'officialSqlstateReference':'https://www.postgresql.org/docs/18/errcodes-appendix.html',
               'implementationSha256':SHA(Path(__file__).read_bytes()),'bindings':[]}
    def bind(path, expected=None):
        raw=path.read_bytes();binding={'file':path.relative_to(ROOT).as_posix(),'bytes':len(raw),'sha256':SHA(raw)}
        if expected:
            assert binding['sha256']==(expected if isinstance(expected,str) else expected['sha256']),str(path)
            if isinstance(expected,dict) and 'bytes' in expected:assert len(raw)==expected['bytes']
        receipt['bindings'].append(binding)
        return raw
    try:
        database=args.database.resolve();aggregate=LOAD(database/'receipt.json');assert aggregate['passed'] and aggregate['actualDatabaseExecution']
        assert 180000<=aggregate['serverVersionNumber']<190000 and aggregate['notCompletePlanAcceptance']
        bind(database/'receipt.json')
        manifest=LOAD(ROOT/'dist/build-manifest.json')
        names=sorted(['moon.mod']+[p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*') if p.is_file() and (p.suffix=='.mbt' or p.name=='moon.pkg')])
        digest=hashlib.sha256()
        for name in names:digest.update(name.encode()+b'\0'+(ROOT/name).read_bytes()+b'\0')
        assert digest.hexdigest()==manifest['sourceSha256']
        for filename,key in [('core.mjs','coreSha256'),('capture-core.mjs','captureCoreSha256')]:bind(ROOT/'dist'/filename,manifest[key])
        for filename in ['sdk.mjs','evidence.mjs','moontxnwitness.mjs']:assert bind(ROOT/'dist'/filename)==bind(ROOT/'cmd'/filename)
        receipt['build']=manifest
        upstream=ROOT/'experiments/faults/mlflow/upstream';fetch=LOAD(upstream/'fetch-receipt.json');bind(upstream/'fetch-receipt.json')
        static=[]
        for label,commit in [('before','c2dcdb96c62c75f35af3f28b5d493c0cf139a856'),('fixed','40c146a23518813e8488e55fc9752e08c3a8bad5')]:
            d=database/label;r=LOAD(d/'receipt.json');bind(d/'receipt.json')
            assert r['passed'] and r['actualDatabaseExecution'] and r['commit']==commit
            assert not r['isolationViolationClaim'] and not r['G2Claim'] and r['sqlObservationsComplete']
            assert r['committed']==sum(w['committed'] for w in r['workers'].values())==(1 if label=='before' else 2)
            assert r['keysEach']==1000 and r['originalBatchSize']==500
            assert r['runtimeSourceBindings']==r['runtimeSourceBindingsAfter'] and r['runtimeSourceUnchanged']
            assert not r['threadsStillAlive'] and r['controllerError'] is None
            for name,b in r['runtimeSourceBindings'].items():
                bind(ROOT/name,b);snapshot=gzip.decompress(bind(d/'source-snapshots'/(Path(name).name+'.gz')))
                assert snapshot==(ROOT/name).read_bytes()
            license=bind(upstream/label/'LICENSE.txt');assert b'Apache License' in license and b'Version 2.0' in license
            for source in r['sourceBindings']:
                f=next(f for f in fetch if f['label']==label and f['file']==source['file']);assert f['commit']==commit and commit in f['url']
                zipped=bind(upstream/f['compressedFile'],f['compressedSha256']);raw=gzip.decompress(zipped);assert len(raw)==f['bytes'] and SHA(raw)==source['sha256']==f['sha256']
                tree=ast.parse(raw.decode('utf8'));container=next(n for n in tree.body if getattr(n,'name','')=='SqlAlchemyStore') if source['node'].startswith('_update_') else tree
                node=next(n for n in container.body if getattr(n,'name','')==source['node'])
                assert SHA(ast.dump(node,include_attributes=False).encode())==source['astSha256']
                assert (node.lineno,node.end_lineno)==(source['firstLine'],source['lastLine'])
            trace=LOAD(d/'capture.json');bind(d/'capture.json',r['captureSha256'])
            rows=LOAD(d/'final-rows.json');bind(d/'final-rows.json',r['finalRowsSha256'])
            assert len(rows)==1000 and len({x[0] for x in rows})==1000
            assert {x[0] for x in rows}=={'X','Y'}|{'a%04d'%i for i in range(499)}|{'b%04d'%i for i in range(499)}
            winner=next(name for name,w in r['workers'].items() if w['committed']) if label=='before' else 'B';step=1 if winner=='A' else 2
            assert all(x[1]==float(step) and x[2]==step and x[3]==step for x in rows)
            sql=[json.loads(line) for line in bind(d/'sql-executions.jsonl',r['sqlExecutionsSha256']).splitlines()]
            assert all(x['phase'] in ('before','after','error') for x in sql)
            assert len([x for x in sql if x['phase']=='before'])==len([x for x in sql if x['phase'] in ('after','error')])
            actual_errors=[x for x in sql if x['phase']=='error'];error_events=[e for e in trace['events'] if e['kind']=='rows' and e.get('error')]
            assert len(actual_errors)==len(error_events)==(1 if label=='before' else 0)
            for event in error_events:
                statement=next(e for e in trace['events'] if e['seq']==event['statement']);assert statement['kind']=='statement' and statement['tx']==event['tx']
                assert any(x['sql']==statement['sql'] and x['sqlstate']==event['error']['sqlstate']=='40P01' and x['driverClass']==event['error']['class'] for x in actual_errors)
            before_sql=Counter((x['sql'],json.dumps(x.get('parameters'),sort_keys=True)) for x in sql if x['phase']=='before')
            captured=Counter((e['sql'],json.dumps(e.get('parameters'),sort_keys=True)) for e in trace['events'] if e['kind']=='statement')
            assert not (captured-before_sql),'Captured statement/parameters absent from the independently recorded execution log'
            missing=sum((before_sql-captured).values())
            if missing:assert any(g['code']=='cursor_api_unsupported' for g in trace['gaps'])
            index=LOAD(d/'journal/journal-index.json');bind(d/'journal/journal-index.json');events=[]
            for segment in index['segments']:
                raw=bind(d/'journal'/segment['name'],segment);items=[json.loads(line) for line in raw.splitlines()];assert len(items)==segment['eventCount'];events.extend(items)
            assert events==trace['events'] and [e['seq'] for e in events]==list(range(1,len(events)+1))
            assert index['eventCount']==index['durableSeq']==len(events) and not index['sourceClosed']
            static.append({'label':label,'actualSqlExecutions':sum(before_sql.values()),'capturedStatements':sum(captured.values()),'uncapturedExecutionApisRemainGap':missing,
                           'finalRows':len(rows),'observedFaults':len(error_events),'committed':r['committed'],'sourceSnapshotsAndAstExact':True})
        receipt['static']=static
        driver=out/'runtime-driver.mjs';immutable(driver,NODE)
        p=subprocess.run(['node',str(driver),str(ROOT),str(database),str(out)],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=120)
        immutable(out/'runtime-process.json',{'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        receipt['runtime']=LOAD(out/'runtime-result.json');assert p.returncode==0 and receipt['runtime']['passed']
        for b in receipt['bindings']:assert SHA((ROOT/b['file']).read_bytes())==b['sha256'],'Source/evidence changed during independent audit'
        receipt['complete']=True;receipt['passed']=True
    except Exception as error:
        receipt['errorClass']=type(error).__name__;receipt['error']=str(error).replace(str(ROOT),'<workspace>')
    saved=immutable(out/'receipt.json',receipt)
    print(json.dumps({'passed':receipt['passed'],'complete':receipt['complete'],'checks':receipt.get('runtime',{}).get('checks',0),'receipt':saved,'error':receipt.get('error')},ensure_ascii=True))
    return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
