import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const sha=x=>createHash('sha256').update(x).digest('hex');
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
  const result=compare(JSON.parse(read('matrix.json')),read('moon-results.jsonl').toString().trim().split('\n').map(JSON.parse),actual);
  const rows=result.rows.map(r=>JSON.stringify(r)).join('\n')+'\n';
  const summary={...result,rows:undefined,sourceRuntime:preparation.sourceRuntime,preparedInputs:preparation.inputs,itemsSha256:sha(rows),upstreamResultsSha256:sha(read('upstream/results.json'))};
  assert(!existsSync(resolve(out,'comparison.json')),'Never overwrite an earlier result');
  writeFileSync(resolve(out,'comparison-items.jsonl'),rows,{flag:'wx'});
  writeFileSync(resolve(out,'comparison.json'),JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({passed:summary.passed,actualUpstreamRequests:summary.actualUpstreamRequests,requiredComparable:summary.requiredComparable,totals:summary.totals,failures:summary.failures}));
  if(!summary.passed)process.exitCode=1;
}
