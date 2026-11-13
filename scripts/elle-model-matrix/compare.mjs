import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const sha=x=>createHash('sha256').update(x).digest('hex');
// These are the same original-source pins verified by run_upstream.py.
export const FIXED_ELLE_SOURCE_PINS=Object.freeze({
  'project.clj':'d4608919c02b20de53cb017467e54c4b8267c4f146619a612a1a585f42f7c89f',
  'LICENSE':'721c2da257578bace3332b14d8ea06643d7d26753e7ef25a837b4e904edc0bf5',
  'src/elle/graph.clj':'9cbe589d740593671cd02ee48300a929b9bb863ffe4da506b906eebbb222ea3f',
  'src/elle/core.clj':'396fcbd5683787366f3bf111f512aa4f7976e0d48414f8939e3e71edeeddff98',
  'src/elle/rw_register.clj':'9ad17da5b86e6e25fe66b77e0deab9000265901a1bedd5045dbba98c7dddd1ce',
  'src/elle/list_append.clj':'f4bfeee8afef994e662a4f5e2d36219ddd714254a9590f6bc36ca0b52bf3d2e7',
  'src/elle/txn.clj':'8c3c87062d518cc7ba9cee49408fe552e8057a59e5b2068f4f8aa0bf6421a5a6',
  'src/elle/consistency_model.clj':'f909f517351081001054bef461fcdec709f6bd2d2c058955777e68033d4fb10b',
});
const fileBinding=bytes=>({bytes:bytes.length,sha256:sha(bytes)});
export function validateExecution({actual,execution,sourceBindings,requestsBytes,resultsBytes,checkerBytes}){
  assert.equal(actual.format,'moontxnwitness-actual-fixed-elle-model-results/v1');
  assert.equal(execution.format,'moontxnwitness-actual-fixed-elle-execution/v1');
  assert.equal(execution.passed,true,'Original upstream execution did not pass');
  assert(!execution.error&&!execution.inputChanged,'Original upstream execution was incomplete or its inputs changed');
  assert.equal(actual.passed,true,'Original upstream checker execution failed');
  assert.equal(execution.fixedElleCommit,'4e359e597c52938b0afebb8bc42273914d68a424');
  assert.equal(actual.fixedElleCommit,execution.fixedElleCommit);
  assert.equal(execution.jdkMajor,21);
  assert.equal(execution.leinVersion,'2.11.2');
  assert.equal(execution.clojureVersion,'1.12.6');
  assert.deepEqual(execution.requests,fileBinding(requestsBytes),'Execution requests differ from the original prepared bytes');
  assert.equal(actual.requestsSha256,execution.requests.sha256);
  assert.deepEqual(execution.resultBinding,fileBinding(resultsBytes),'Actual checker result bytes differ from their execution receipt');
  assert.deepEqual(execution.checker,fileBinding(checkerBytes),'Executed checker differs from this original source adapter');
  assert.deepEqual(execution.actualSources,sourceBindings,'Upstream source bindings differ from their execution receipt');
  assert.deepEqual(Object.keys(sourceBindings).sort(),Object.keys(FIXED_ELLE_SOURCE_PINS).sort());
  for(const [name,digest]of Object.entries(FIXED_ELLE_SOURCE_PINS)){
    assert.equal(sourceBindings[name].sha256,digest,'Upstream source differs from its fixed pin: '+name);
    assert(Number.isSafeInteger(sourceBindings[name].bytes)&&sourceBindings[name].bytes>0);
  }
  assert(Array.isArray(execution.stages)&&execution.stages.length,'Original execution stages are missing');
  const stages=new Map();
  for(const stage of execution.stages){
    assert(typeof stage.name==='string'&&!stages.has(stage.name),'Duplicate/missing execution stage identity');
    assert.equal(stage.status,'passed','Original upstream stage did not pass: '+stage.name);
    assert.equal(stage.exitCode,0,'Original upstream stage returned an error: '+stage.name);
    stages.set(stage.name,stage);
  }
  for(const name of ['java-version','git-identify','dependency-tree','actual-model-checkers','upstream-source-status'])assert(stages.has(name),'Missing original execution stage: '+name);
  assert.equal(execution.requestCount,actual.results.length);
  assert.equal(actual.requestCount,actual.results.length);
  assert.equal(actual.executionErrors,0);
  assert.equal(execution.executionErrors,0);
  assert.equal(actual.timeouts,0);
  assert.equal(execution.timeouts,0);
  return true;
}
export function compare(matrix,moon,upstream){
  assert.equal(matrix.fixedElleCommit,upstream.fixedElleCommit);
  assert.equal(new Set(matrix.cases.map(x=>x.id)).size,matrix.cases.length);
  const indexed=(rows,label)=>{const result=new Map();for(const row of rows){assert(typeof row.id==='string'&&!result.has(row.id),label+' duplicate/missing identity');result.set(row.id,row);}return result;};
  const m=indexed(moon,'SDK'),u=indexed(upstream.results,'Elle');
  assert.equal(m.size,matrix.cases.length);
  assert.equal(u.size,matrix.cases.filter(c=>c.upstreamEligible).length);
  const counts=()=>({matched:0,difference:0,unknown:0,notComparable:0,timeout:0,executionFailed:0});
  const totals=counts(),byModel={},rows=[],failures=[];
  for(const fixture of matrix.cases){
    const own=m.get(fixture.id);assert(own);
    assert.equal(own.inputSha256,sha(JSON.stringify(fixture.input)));
    assert.equal(own.optionsSha256,sha(JSON.stringify(fixture.options)));
    assert(own.verified&&own.changedVerdictRejected);
    assert(['checked-compatible','refuted','unknown','pending'].includes(own.status));
    if(fixture.expected&&own.status!==fixture.expected)failures.push({id:fixture.id,kind:'sdk-semantic-expectation',expected:fixture.expected,actual:own.status});
    const other=u.get(fixture.id);
    let outcome,reason;
    if(!fixture.upstreamEligible){assert(!other);outcome='notComparable';reason=fixture.cohort==='incomplete-logical-context'?'missing-original-logical-clients-not-filled-from-physical-connections':'original-capture-gap-not-represented-as-complete-upstream-history';}
    else {
      assert(other,'Missing actual upstream execution');
      if(!other.error){
        const expectedDataModel={'point-register-v1':'register','append-list-v1':'list'}[fixture.dataModel];
        assert(expectedDataModel,'Unsupported comparison datatype');
        assert.equal(other.model,fixture.model,'Actual upstream model differs from the original request');
        assert.equal(other.dataModel,expectedDataModel,'Actual upstream datatype differs from the original request');
      }
      if(other.error)outcome='executionFailed';
      else if(other.timeout)outcome='timeout';
      else if(other.unknown||other.validity===null||['unknown','pending'].includes(own.status))outcome='unknown';
      else {assert.equal(typeof other.validity,'boolean');outcome=((own.status==='checked-compatible')===other.validity)?'matched':'difference';}
      if(fixture.required&&typeof other.validity==='boolean'&&other.validity!==(fixture.expected==='checked-compatible'))failures.push({id:fixture.id,kind:'upstream-semantic-expectation',expected:fixture.expected,actual:other.validity});
      if(fixture.required&&outcome!=='matched')failures.push({id:fixture.id,kind:'required-pair-not-matched',outcome});
    }
    const key=fixture.dataModel+'/'+fixture.model;
    byModel[key]??=counts();byModel[key][outcome]++;totals[outcome]++;
    rows.push({id:fixture.id,dataModel:fixture.dataModel,model:fixture.model,family:fixture.family,cohort:fixture.cohort,required:fixture.required,
      inputSha256:own.inputSha256,optionsSha256:own.optionsSha256,sdkStatus:own.status,sdkProfile:own.sourceProfile,
      upstream:other??null,outcome,...(reason?{reason}:{})});
  }
  const requiredComparable=matrix.cases.filter(c=>c.required&&c.upstreamEligible).length;
  assert(requiredComparable>=56);
  return {format:'moontxnwitness-actual-elle-model-comparison/v1',fixedElleCommit:matrix.fixedElleCommit,
    passed:!failures.length&&!totals.difference&&!totals.executionFailed&&!totals.timeout,
    actualUpstreamRequests:u.size,requiredComparable,totals,byModel,failures,rows};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  const [dir,...extra]=process.argv.slice(2);assert(dir&&!extra.length,'Usage: compare.mjs OUTPUT_DIR');
  const out=resolve(dir),read=n=>readFileSync(resolve(out,n));
  const preparation=JSON.parse(read('preparation.json'));
  assert(preparation.passed,'Original SDK preparation failed');
  for(const [file,hash]of Object.entries(preparation.inputs))assert.equal(sha(read(file)),hash,'Prepared original input changed: '+file);
  const actual=JSON.parse(read('upstream/results.json'));
  assert.equal(actual.requestsSha256,preparation.inputs['requests.edn'],'Upstream result must bind these exact original requests');
  validateExecution({actual,execution:JSON.parse(read('upstream/run.json')),
    sourceBindings:JSON.parse(read('upstream/source-bindings.json')),requestsBytes:read('requests.edn'),
    resultsBytes:read('upstream/results.json'),checkerBytes:readFileSync(new URL('./upstream.clj',import.meta.url))});
  const result=compare(JSON.parse(read('matrix.json')),read('moon-results.jsonl').toString().trim().split('\n').map(JSON.parse),actual);
  const rows=result.rows.map(r=>JSON.stringify(r)).join('\n')+'\n';
  const summary={...result,rows:undefined,sourceRuntime:preparation.sourceRuntime,preparedInputs:preparation.inputs,itemsSha256:sha(rows),upstreamResultsSha256:sha(read('upstream/results.json'))};
  assert(!existsSync(resolve(out,'comparison.json')),'Never overwrite an earlier result');
  writeFileSync(resolve(out,'comparison-items.jsonl'),rows,{flag:'wx'});
  writeFileSync(resolve(out,'comparison.json'),JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({passed:summary.passed,actualUpstreamRequests:summary.actualUpstreamRequests,requiredComparable:summary.requiredComparable,totals:summary.totals,failures:summary.failures}));
  if(!summary.passed)process.exitCode=1;
}
