import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2);if(args.length!==2||args[0]!=='--runtime')throw Error('Usage: --runtime <new revision2 bridge>');
const base=root;
const pins=JSON.parse(await readFile(resolve(root,'fixtures/source-components-v4/integration-components.json'),'utf8'));
const sha=x=>createHash('sha256').update(x).digest('hex');
const clone=x=>structuredClone(x);const before={};
for(const [name,digest]of Object.entries(pins.files)){const actual=sha(await readFile(resolve(root,name)));assert.equal(actual,digest);before[name]=actual;}
const runtime=resolve(args[1]);const core=await import(pathToFileURL(runtime));
const {createSourceComponentsV4}=await import(pathToFileURL(resolve(base,'cmd/source-components-v4.mjs')));const sdk=createSourceComponentsV4(core);
const fixture=resolve(base,'fixtures/source-components-v4');
const source=Object.fromEntries(await Promise.all([['config','config.json'],['policy','policy.json'],['log','control.jsonl'],['receipt','receipt.json']].map(async([k,n])=>[k,await readFile(resolve(fixture,n),'utf8')])));
const synthetic=JSON.parse(await readFile(resolve(fixture,'SYNTHETIC-fetch-inputs.json'),'utf8'));assert.equal(synthetic.syntheticNativeBuffers,true);
const cases=[];let failures=0;
function test(name,fn){try{fn();cases.push({name,passed:true});}catch(error){failures++;cases.push({name,passed:false,error:error.stack});}}
function flags(r){for(const field of ['sourceFactsProduced','sourceAuthenticated','writerWindowVerified','isolationModelChecked'])assert.equal(r[field],false,field);}
function map(c=synthetic.cases[0],options={}){const r=sdk.mapInitialSourceFetchV4({...source,...c},options);flags(r);return r;}
function wrongParameter(){const c=clone(synthetic.cases[0]);c.execution.parameters=[18];c.execution.candidate.bindings[0].value.value='18';c.execution.candidate.parametersSha256=sha('[18]');c.native.parametersSha256=sha('[18]');return c;}
function duplicate(){const c=clone(synthetic.cases[0]);c.native.rows.push(clone(c.native.rows[0]));c.deliveries[0].rows.push(clone(c.deliveries[0].rows[0]));return c;}
function reproject(c,indices){
 c=clone(c);const d=c.execution.candidate.descriptor,q=x=>'"'+x.replaceAll('"','""')+'"';d.projections=indices.map(i=>clone(d.projections[i]));
 const sql='SELECT '+d.projections.map(p=>q(p.column)).join(',')+' FROM '+q(d.table.schema)+'.'+q(d.table.table)+' WHERE '+q(d.table.primaryKey)+'=%s';
 c.execution.sql=sql;d.originalSql=sql;d.sqlSha256=sha(sql);c.execution.candidate.sqlSha256=sha(sql);c.native.sqlSha256=sha(sql);
 c.native.fields=indices.map(i=>clone(c.native.fields[i]));c.native.rows=c.native.rows.map(row=>indices.map(i=>row[i]));for(const delivery of c.deliveries)delivery.rows=delivery.rows.map(row=>indices.map(i=>row[i]));return c;
}
let full;
test('new profile keeps separate native and returned-row contracts',()=>{full=map();assert.equal(full.valid,true);assert.equal(full.algorithm,'independent-native-initial-row-and-predicate-join-2');assert.equal(full.counterContract,'source-fetch-mapping-step-counters/v4-2');assert.equal(full.fetch.format,'moontxnwitness-select-returned-row-constraints/v4');assert.equal(full.nativeDeliveryCheck.valid,true);assert.equal(full.fetch.valid,true);assert.equal(full.fetch.resultSetCompletenessVerified,false);});
test('independent duplicate PK counterexample now has a specific witness',()=>{const r=map(duplicate());assert.equal(r.nativeDeliveryCheck.valid,true);assert.equal(r.valid,false);assert.equal(r.status,'mismatch');assert.equal(r.fetch.valid,false);assert.equal(r.fetch.witness.rule,'single-table-primary-key-result-uniqueness');assert.equal(r.fetch.witness.firstRowIndex,0);assert.equal(r.fetch.witness.secondRowIndex,1);});
test('independent WHERE18 return17 now rejects SELECT consistency',()=>{const r=map(wrongParameter());assert.equal(r.nativeDeliveryCheck.valid,true);assert.equal(r.fetch.valid,false);assert.equal(r.status,'mismatch');assert.equal(r.fetch.witness.rule,'returned-row-WHERE-AND');assert.equal(r.fetch.witness.observed.value,'17');assert.equal(r.fetch.witness.expected.value,'18');});
test('missing noncondition business field is never filled from sidecar',()=>{const c=synthetic.cases[0],r=map(reproject(c,c.native.fields.map((_,i)=>i).filter(i=>i!==1)));assert.equal(r.fetch.valid,true);assert.equal(r.valid,false);assert.match(r.reason,/row-projection-incomplete/);});
test('missing predicate/PK field is an explicit constraint gap',()=>{const c=synthetic.cases[0],r=map(reproject(c,c.native.fields.map((_,i)=>i).filter(i=>i!==0)));assert.equal(r.nativeDeliveryCheck.valid,true);assert.equal(r.fetch.valid,false);assert.equal(r.status,'unknown');assert.ok(r.fetch.gaps.some(x=>x.startsWith('predicate-column-not-delivered:')));});
test('legal complete empty result is not a fabricated negative source',()=>{const c=clone(synthetic.cases[0]);c.native.rows=[];c.deliveries[0].rows=[];const r=map(c);assert.equal(r.fetch.valid,true);assert.equal(r.fetch.negativeReadSourceVerified,false);assert.equal(r.fetch.resultSetCompletenessVerified,false);assert.equal(r.status,'unknown');assert.match(r.reason,/empty-result/);});
test('repeated fetch start cannot create a second SELECT delivery',()=>{const c=clone(synthetic.cases[0]);c.deliveries.push(clone(c.deliveries[0]));const r=map(c);assert.equal(r.nativeDeliveryCheck.valid,false);assert.equal(r.fetch.valid,false);assert.equal(r.valid,false);});
test('unsupported scroll is unknown and not SELECT verified',()=>{const c=clone(synthetic.cases[0]);c.deliveries[0].method='scroll';const r=map(c);assert.equal(r.status,'unknown');assert.equal(r.fetch.valid,false);assert.equal(r.nativeDeliveryCheck.valid,false);});
test('unexhausted native prefix keeps an explicit gap',()=>{const c=clone(synthetic.cases[0]);c.deliveries[0].method='fetchone';c.deliveries[0].complete=false;const r=map(c);assert.equal(r.nativeDeliveryCheck.valid,true);assert.equal(r.fetch.valid,false);assert.equal(r.status,'unknown');assert.match(r.reason,/fetch-not-exhausted/);});
test('reliable WHERE mismatch survives an unexhausted prefix',()=>{const c=wrongParameter();c.deliveries[0].method='fetchone';c.deliveries[0].complete=false;const r=map(c);assert.equal(r.status,'mismatch');assert.equal(r.fetch.witness.rule,'returned-row-WHERE-AND');});
test('new report replays with caller default options',()=>assert.equal(sdk.verifyInitialSourceFetchReportV4({...source,...synthetic.cases[0]},full),true));
test('new exact/one-short shared check limits remain bounded',()=>{const n=full.execution.checks;assert.equal(map(synthetic.cases[0],{maxChecks:n}).valid,true);assert.equal(map(synthetic.cases[0],{maxChecks:n-1}).valid,false);});
test('report cannot hide the observed WHERE counterexample',()=>{const c=wrongParameter(),r=map(c);r.fetch.valid=true;r.fetch.returnedRowConstraintsVerified=true;assert.equal(sdk.verifyInitialSourceFetchReportV4({...source,...c},r),false);});
test('all pinned integrated component/fixture bytes stay unchanged',()=>{});
for(const [name,digest]of Object.entries(before))assert.equal(sha(await readFile(resolve(base,name))),digest,name);
const output={format:'source-select-session-integration-tests/v4',cases,checks:cases.length,passed:cases.length-failures,failures,runtimeSha256:sha(await readFile(runtime)),currentPinnedComponentsUnchanged:true,historicalOriginalTreeAccessed:false,syntheticNativeInputs:true,actualDatabaseExecution:false,oldAuthor56Modified:false,oldIndependent50Modified:false};
await writeFile(resolve(root,'artifacts/source-select-session-integration-tests.json'),JSON.stringify(output,null,2)+'\n');console.log(JSON.stringify({checks:output.checks,passed:output.passed,failures}));if(failures)process.exitCode=1;
