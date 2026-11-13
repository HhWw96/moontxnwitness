import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {matrixCases} from './cases.mjs';
import {compare,validateExecution,FIXED_ELLE_SOURCE_PINS} from './compare.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex'),matrix=matrixCases();
// Synthetic checker responses exercise only accounting and fault rejection.
const moon=matrix.cases.map(c=>({id:c.id,inputSha256:sha(JSON.stringify(c.input)),optionsSha256:sha(JSON.stringify(c.options)),status:c.expected??'unknown',verified:true,changedVerdictRejected:true}));
const upstream={fixedElleCommit:matrix.fixedElleCommit,results:matrix.cases.filter(c=>c.upstreamEligible).map(c=>({id:c.id,model:c.model,dataModel:c.dataModel==='point-register-v1'?'register':'list',validity:c.expected==='refuted'?false:true,unknown:false,timeout:false}))};
const run=(m=moon,u=upstream)=>compare(matrix,m,u);
const requiredCount=matrix.cases.filter(c=>c.required&&c.upstreamEligible).length;
const notComparableCount=matrix.cases.filter(c=>!c.upstreamEligible).length;
let checks=0;
const test=(name,f)=>{try{f();checks++;}catch(e){throw Error(name+': '+e.message);}};
test('required pairs and missing evidence use separate counters',()=>{const r=run();assert(r.passed);assert(requiredCount>=56);assert.equal(r.requiredComparable,requiredCount);assert.equal(r.totals.matched,requiredCount);assert.equal(r.totals.notComparable,notComparableCount);assert(r.totals.unknown>0);});
test('opposite upstream verdict fails the required expectation',()=>{const u=structuredClone(upstream);u.results[0].validity=false;const r=run(moon,u);assert(!r.passed);assert(r.failures.length);assert.equal(r.totals.difference,1);});
test('unknown must not be counted as matching a required result',()=>{const u=structuredClone(upstream);Object.assign(u.results[0],{validity:null,unknown:true});const r=run(moon,u);assert(!r.passed);assert.equal(r.totals.matched,requiredCount-1);});
test('timeout does not become an unknown model result',()=>{const u=structuredClone(upstream);Object.assign(u.results[0],{timeout:true,validity:null});assert.equal(run(moon,u).totals.timeout,1);});
test('execution error never becomes no anomaly',()=>{const u=structuredClone(upstream);u.results[0].error='test execution failed';assert.equal(run(moon,u).totals.executionFailed,1);});
test('duplicate upstream identity is refused',()=>{const u=structuredClone(upstream);u.results[1].id=u.results[0].id;assert.throws(()=>run(moon,u));});
test('missing actual request is refused',()=>{const u=structuredClone(upstream);u.results.pop();assert.throws(()=>run(moon,u));});
test('same-verdict results from another model are refused',()=>{const u=structuredClone(upstream);const a=u.results[0],b=u.results.find(r=>r.model!==a.model&&r.validity===a.validity);[a.model,b.model]=[b.model,a.model];assert.throws(()=>run(moon,u),/upstream model differs/);});
test('same-verdict results from another datatype are refused',()=>{const u=structuredClone(upstream);const a=u.results[0],b=u.results.find(r=>r.dataModel!==a.dataModel&&r.validity===a.validity);[a.dataModel,b.dataModel]=[b.dataModel,a.dataModel];assert.throws(()=>run(moon,u),/upstream datatype differs/);});
test('missing returned model identity is refused',()=>{const u=structuredClone(upstream);delete u.results[0].model;assert.throws(()=>run(moon,u),/upstream model differs/);});
test('missing returned datatype identity is refused',()=>{const u=structuredClone(upstream);delete u.results[0].dataModel;assert.throws(()=>run(moon,u),/upstream datatype differs/);});
test('other reference commit is refused',()=>{const u=structuredClone(upstream);u.fixedElleCommit='other';assert.throws(()=>run(moon,u));});
test('different original history bytes are refused',()=>{const m=structuredClone(moon);m[0].inputSha256='0'.repeat(64);assert.throws(()=>run(m));});
test('different independent options are refused',()=>{const m=structuredClone(moon);m[0].optionsSha256='0'.repeat(64);assert.throws(()=>run(m));});
test('invalid own model status is refused',()=>{const m=structuredClone(moon);m[0].status='passed';assert.throws(()=>run(m));});
test('unverified reports are refused',()=>{const m=structuredClone(moon);m[0].verified=false;assert.throws(()=>run(m));});
test('changed-verdict checks cannot be omitted',()=>{const m=structuredClone(moon);m[0].changedVerdictRejected=false;assert.throws(()=>run(m));});
// Synthetic receipts below test only the accounting boundary. They are not
// claimed as an execution of the upstream checker.
const executionFixture=()=>{
  const requestsBytes=Buffer.from('synthetic request bytes'),checkerBytes=Buffer.from('synthetic adapter bytes');
  const binding=bytes=>({bytes:bytes.length,sha256:sha(bytes)});
  const sourceBindings=Object.fromEntries(Object.entries(FIXED_ELLE_SOURCE_PINS).map(([name,digest])=>[name,{bytes:1,sha256:digest}]));
  const actual={format:'moontxnwitness-actual-fixed-elle-model-results/v1',fixedElleCommit:matrix.fixedElleCommit,passed:true,
    requestsSha256:sha(requestsBytes),requestCount:1,executionErrors:0,timeouts:0,results:[{id:'synthetic-accounting-only'}]};
  const resultsBytes=Buffer.from(JSON.stringify(actual));
  const execution={format:'moontxnwitness-actual-fixed-elle-execution/v1',fixedElleCommit:matrix.fixedElleCommit,passed:true,
    jdkMajor:21,leinVersion:'2.11.2',clojureVersion:'1.12.6',requests:binding(requestsBytes),checker:binding(checkerBytes),
    resultBinding:binding(resultsBytes),actualSources:structuredClone(sourceBindings),requestCount:1,executionErrors:0,timeouts:0,
    stages:['java-version','git-identify','dependency-tree','actual-model-checkers','upstream-source-status'].map(name=>({name,status:'passed',exitCode:0}))};
  return {actual,execution,sourceBindings,requestsBytes,checkerBytes,resultsBytes};
};
test('consistent execution receipt is accepted for accounting',()=>assert.equal(validateExecution(executionFixture()),true));
test('execution failure after checker output is refused',()=>{const f=executionFixture();Object.assign(f.execution,{passed:false,error:{message:'post-run source validation failed'}});assert.throws(()=>validateExecution(f),/execution did not pass/);});
test('failure hidden behind an execution pass flag is refused',()=>{const f=executionFixture();f.execution.error={message:'execution failed'};assert.throws(()=>validateExecution(f),/incomplete or its inputs changed/);});
test('changed original request bytes are refused',()=>{const f=executionFixture();f.requestsBytes=Buffer.concat([f.requestsBytes,Buffer.from('\n')]);assert.throws(()=>validateExecution(f),/requests differ/);});
test('changed checker output bytes are refused',()=>{const f=executionFixture();f.resultsBytes=Buffer.concat([f.resultsBytes,Buffer.from('\n')]);assert.throws(()=>validateExecution(f),/result bytes differ/);});
test('another executed source adapter is refused',()=>{const f=executionFixture();f.checkerBytes=Buffer.from('another adapter');assert.throws(()=>validateExecution(f),/Executed checker differs/);});
test('source inventory disagreement is refused',()=>{const f=executionFixture();f.sourceBindings['project.clj'].bytes++;assert.throws(()=>validateExecution(f),/source bindings differ/);});
test('a consistently substituted upstream source pin is refused',()=>{const f=executionFixture();f.sourceBindings['project.clj'].sha256='0'.repeat(64);f.execution.actualSources=structuredClone(f.sourceBindings);assert.throws(()=>validateExecution(f),/fixed pin/);});
test('a required post-run validation stage cannot be omitted',()=>{const f=executionFixture();f.execution.stages.pop();assert.throws(()=>validateExecution(f),/Missing original execution stage/);});
test('a failed post-run validation stage cannot be relabeled as complete',()=>{const f=executionFixture();f.execution.stages.at(-1).status='failed';assert.throws(()=>validateExecution(f),/stage did not pass/);});
test('duplicate execution stages are refused',()=>{const f=executionFixture();f.execution.stages.push({...f.execution.stages[0]});assert.throws(()=>validateExecution(f),/Duplicate\/missing execution stage/);});
test('the comparator and runner use the same fixed original source pins',()=>{const source=readFileSync(new URL('./run_upstream.py',import.meta.url),'utf8');for(const [name,digest]of Object.entries(FIXED_ELLE_SOURCE_PINS))assert(source.includes(JSON.stringify(name)+': '+JSON.stringify(digest)));});
console.log(JSON.stringify({passed:true,checks,syntheticComparatorUnitTests:true,actualUpstreamExecution:false}));
