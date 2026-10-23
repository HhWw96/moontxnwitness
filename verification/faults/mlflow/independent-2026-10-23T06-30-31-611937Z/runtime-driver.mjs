
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
