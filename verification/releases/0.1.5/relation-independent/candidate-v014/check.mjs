import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,copyFileSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const here=dirname(fileURLToPath(import.meta.url));
const flags=new Map();
for(let i=2;i<process.argv.length;i+=2){assert.ok(['--repository','--candidate','--output-root'].includes(process.argv[i]));assert.ok(process.argv[i+1]);flags.set(process.argv[i],process.argv[i+1]);}
const root=resolve(flags.get('--repository')||resolve(here,'../..'));
const candidate=resolve(flags.get('--candidate')||resolve(root,'artifacts/v015-relation-candidate'));
const expectedManifest='c88a0d62507ead5e1b5393aa95b7fea28b0e5081f81efa46e737168e7d41bf76';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const bind=file=>{const raw=readFileSync(file);return{bytes:raw.length,sha256:hash(raw)};};
const load=file=>JSON.parse(readFileSync(file,'utf8'));
const posix=file=>relative(root,file).replaceAll('\\','/');
const outRoot=resolve(flags.get('--output-root')||resolve(here,'runs'));mkdirSync(outRoot,{recursive:true});
const out=mkdtempSync(resolve(outRoot,'review-'));
const save=(name,value)=>writeFileSync(resolve(out,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const manifestPath=resolve(candidate,'candidate-manifest.json');
assert.equal(bind(manifestPath).sha256,expectedManifest);
const manifest=load(manifestPath),baseline=load(resolve(candidate,'baseline-inputs.json'));
const before=Object.fromEntries(Object.keys(manifest.files).map(name=>[name,bind(resolve(candidate,name))]));
assert.deepEqual(before,manifest.files);
const additional=['fixtures/list-v3/manual.json','fixtures/list-v3/reduction-source-closure.json','examples/v3-write-skew.json'];
const inputs={...baseline,...Object.fromEntries(additional.map(name=>[name,bind(resolve(root,name))]))};
for(const[name,binding]of Object.entries(inputs))assert.deepEqual(bind(resolve(root,name)),binding,name);
const receipt={schema:1,kind:'independent-ai-fixed-relation-sdk-candidate-review',passed:false,
  scope:'Candidate SDK using the frozen v0.1.4 core; not an actual v0.1.5 build or release acceptance',
  independentOfImplementation:true,databaseExecuted:false,buildExecuted:false,downloaded:false,
  performanceMeasurement:false,humanAcceptance:false,contestApproval:false,checks:[]};
const check=async(name,fn)=>{try{receipt.checks.push({name,passed:true,...await fn()});}
 catch(error){receipt.checks.push({name,passed:false,error:{name:error.name,message:error.message}});}};
const runtime=resolve(candidate,'runtime');
const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
const old=await import(pathToFileURL(resolve(runtime,'generic-sdk.mjs')).href);
const relation=load(resolve(root,'fixtures/relation-v3/boundary.json'));
const list=load(resolve(root,'fixtures/list-v3/manual.json'));
const byId=new Map(relation.map(row=>[row.id,row]));
const sourceText=readFileSync(resolve(root,'fixtures/relation-v3/reduction-source-closure.json'),'utf8');
const names=['normalizeRelationCaptureV3','analyzeRelationV3','reduceRelationV3','verifyRelationV3','makeRelationCapsuleV3'];
const clone=value=>structuredClone(value);
const compareOutcome=(left,right)=>{let result,error;try{result=right();}catch(e){error=e;}
 if(error){assert.throws(left,e=>e.constructor===error.constructor&&e.message===error.message);return{rejected:true};}
 const got=left();assert.deepEqual(got,result);return{result:got};};

await check('frozen-36-file-candidate-and-unchanged-v014-sdk-prefix',()=>{
 assert.equal(Object.keys(before).length,36);
 const current=readFileSync(resolve(runtime,'sdk.mjs'));
 const prior=readFileSync(resolve(runtime,'generic-sdk.mjs'));
 assert.ok(current.subarray(0,prior.length).equals(prior));
 const added=['analyzeRelationV3','makeRelationCapsuleV3','normalizeRelationCaptureV3','reduceRelationV3','replayRelationCapsuleV3','verifyRelationV3'];
 assert.deepEqual(Object.keys(sdk).filter(name=>!(name in old)).sort(),added.sort());
 const build=load(resolve(runtime,'build-manifest.json'));
 assert.equal(sdk.version(),'0.1.4');
 assert.equal(bind(resolve(runtime,'core.mjs')).sha256,build.coreSha256);
 assert.equal(bind(resolve(runtime,'capture-core.mjs')).sha256,build.captureCoreSha256);
 assert.deepEqual(bind(resolve(runtime,'generic-sdk.mjs')),inputs['dist/sdk.mjs']);
 assert.deepEqual(bind(resolve(runtime,'sdk.mjs')),bind(resolve(candidate,'payload/cmd/sdk.mjs')));
 return{files:36,runtimeVersion:sdk.version(),newExports:6,priorSdkPrefixBytes:prior.length,build};
});

await check('170-relation-histories-match-frozen-generic-normalization-analysis-and-verification',()=>{
 let accepted=0,guardRejected=0,packageable=0,originalCapsuleRejections=0;
 for(const row of relation){assert.equal(hash(row.traceText),row.inputSha256,row.id);
  const trace=JSON.parse(row.traceText);
  if(trace?.traceSchema!==3||trace?.dataModel!=='relation-set-v1'){
   for(const name of names)assert.throws(()=>sdk[name](row.traceText,{}),TypeError,row.id);guardRejected++;continue;
  }
  const report=sdk.analyzeRelationV3(row.traceText,row.options);
  assert.deepEqual(report,old.analyzeV3(row.traceText,row.options),row.id);
  assert.equal(report.status,row.expected,row.id);
  assert.deepEqual(sdk.normalizeRelationCaptureV3(row.traceText),old.normalizeCaptureV3(row.traceText),row.id);
  assert.deepEqual(sdk.verifyRelationV3(row.traceText,report),old.verifyV3(row.traceText,report),row.id);
  const outcome=compareOutcome(()=>sdk.makeRelationCapsuleV3(row.traceText,report),()=>old.makeCapsuleV3(row.traceText,report));
  if(outcome.rejected)originalCapsuleRejections++;else{packageable++;
   assert.deepEqual(sdk.replayRelationCapsuleV3(outcome.result),old.replayCapsuleV3(outcome.result),row.id);}
  accepted++;
 }
 assert.equal(relation.length,170);return{histories:relation.length,accepted,guardRejected,packageable,originalCapsuleRejections};
});

await check('all-71-released-list-histories-preserve-all-six-entries',()=>{
 let rejected=0;
 for(const row of list){assert.equal(hash(row.traceText),row.inputSha256,row.id);const trace=JSON.parse(row.traceText);
  if(trace?.traceSchema!==3||trace?.dataModel!=='append-list-v1'){
   assert.throws(()=>sdk.analyzeListV3(row.traceText,row.options),TypeError);assert.throws(()=>old.analyzeListV3(row.traceText,row.options),TypeError);continue;
  }
  const report=sdk.analyzeListV3(row.traceText,row.options);
  assert.deepEqual(report,old.analyzeListV3(row.traceText,row.options),row.id);
  assert.deepEqual(sdk.normalizeListCaptureV3(row.traceText),old.normalizeListCaptureV3(row.traceText),row.id);
  assert.deepEqual(sdk.verifyListV3(row.traceText,report),old.verifyListV3(row.traceText,report),row.id);
  const outcome=compareOutcome(()=>sdk.makeListCapsuleV3(row.traceText,report),()=>old.makeListCapsuleV3(row.traceText,report));
  if(outcome.rejected)rejected++;else assert.deepEqual(sdk.replayListCapsuleV3(outcome.result),old.replayListCapsuleV3(outcome.result));
 }
 const source=load(resolve(root,'fixtures/list-v3/reduction-source-closure.json'));
 assert.deepEqual(sdk.reduceListV3(source),old.reduceListV3(source));assert.equal(list.length,71);
 return{histories:71,reductionComparisons:1,originalCapsuleRejections:rejected};
});

await check('exact-text-duplicate-keys-utf8-and-object-serialization-are-preserved',async()=>{
 const folder=resolve(out,'spy-runtime');mkdirSync(folder);const source=readFileSync(resolve(runtime,'sdk.mjs'),'utf8');
 copyFileSync(resolve(runtime,'sdk.mjs'),resolve(folder,'sdk.mjs'));globalThis.__relationCalls=[];
 for(const moduleName of ['core','capture-core']){
  const expression=new RegExp("import\\s*\\{([^}]+)\\}\\s*from\\s*['\"]\\./"+moduleName+"\\.mjs['\"]");
  const symbols=source.match(expression)[1].split(',').map(x=>x.trim());
  writeFileSync(resolve(folder,moduleName+'.mjs'),symbols.map(name=>name==='version'?`export function ${name}(){return 'spy';}`:
   `export function ${name}(...args){globalThis.__relationCalls.push({name:'${name}',args});return JSON.stringify({valid:true});}`).join('\n'),{flag:'wx'});
 }
 writeFileSync(resolve(folder,'evidence.mjs'),"export function makeCapsuleV3(...args){globalThis.__relationCalls.push({name:'makeCapsuleV3',args});return 'spy';}\nexport function replayCapsuleV3(){return {valid:false};}\n",{flag:'wx'});
 const spy=await import(pathToFileURL(resolve(folder,'sdk.mjs')).href);
 const raw='\n\t'+sourceText.replace('{','{"unknownDuplicate":"old","unknownDuplicate":"new",')+' \r\n';
 for(const name of names){globalThis.__relationCalls.length=0;spy[name](raw,{});assert.equal(globalThis.__relationCalls.length,1);assert.equal(globalThis.__relationCalls[0].args[0],raw,name);}
 let count=0;const object={toJSON(){count++;return JSON.parse(sourceText);}};globalThis.__relationCalls.length=0;spy.analyzeRelationV3(object);assert.equal(count,1);
 assert.equal(globalThis.__relationCalls[0].args[0],JSON.stringify(JSON.parse(sourceText)));
 const exact=' '.repeat(8*1024*1024-Buffer.byteLength(sourceText))+sourceText;
 spy.analyzeRelationV3(exact);assert.throws(()=>spy.analyzeRelationV3(' '+exact),RangeError);
 assert.throws(()=>spy.analyzeRelationV3({traceSchema:3,dataModel:'relation-set-v1',note:'列'.repeat(3*1024*1024)}),RangeError);
 delete globalThis.__relationCalls;
 let invalid=0;
 for(const raw of ['\n'+sourceText+'\t\r\n',sourceText.replace('{','{"dataModel":"relation-set-v1",')]){
  const report=sdk.analyzeRelationV3(raw);assert.deepEqual(report,old.analyzeV3(raw));
  const capsule=sdk.makeRelationCapsuleV3(raw,report);assert.equal(JSON.parse(capsule).traceText,raw);
  assert.deepEqual(sdk.replayRelationCapsuleV3(capsule),old.replayCapsuleV3(capsule));
  if(report.status==='invalid'){invalid++;assert.equal(sdk.replayRelationCapsuleV3(capsule).valid,true);}
 }
 assert.equal(invalid,1);return{captureEntries:5,exactUtf8Bytes:8*1024*1024,objectSerializations:1,realCoreRawVariants:2,
  spyScope:'Transport only; semantic checks use the frozen real core'};
});

await check('malformed-generic-diagnostics-and-foreign-model-capsules-reject-without-throw',()=>{
 const results=[];
 for(const text of ['{','','not JSON','{"traceSchema":3,']){
  const report=old.analyzeV3(text),capsule=old.makeCapsuleV3(text,report);const baseline=old.replayCapsuleV3(capsule);
  assert.equal(baseline.valid,true);assert.equal(baseline.status,'invalid');
  const got=sdk.replayRelationCapsuleV3(capsule);assert.equal(got.valid,false);results.push({traceText:text,baseline,got});
 }
 for(const trace of [null,[],1,true,'text',{},load(resolve(root,'examples/v3-write-skew.json')),JSON.parse(list[0].traceText)]){
  const raw=JSON.stringify(trace);for(const name of names)assert.throws(()=>sdk[name](raw,{}),TypeError);
  const capsule=old.makeCapsuleV3(raw,old.analyzeV3(raw));assert.equal(old.replayCapsuleV3(capsule).valid,true);
  assert.equal(sdk.replayRelationCapsuleV3(capsule).valid,false);
 }
 assert.throws(()=>sdk.replayRelationCapsuleV3({}),TypeError);assert.equal(sdk.replayRelationCapsuleV3('{').valid,false);
 save('malformed-trace-regression.json',results);return{malformedTraces:4,foreignRoots:8,validReplayIsNotConsistency:true};
});

await check('source-gaps-unknown-commits-capacity-and-budget-do-not-gain-completeness',()=>{
 const gaps=['unknown-read-version','unknown-commit','supplement-later-read-source-does-not-repair-gap','partial-query','snapshot-coverage-omitted'];
 for(const id of gaps){const row=byId.get(id);assert.ok(row,id);const report=sdk.analyzeRelationV3(row.traceText,row.options);
  assert.deepEqual(report,old.analyzeV3(row.traceText,row.options));assert.equal(report.status,'inconclusive');assert.equal(report.coverage.complete,false);
  const replay=sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(row.traceText,report));assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');assert.equal(replay.coverageComplete,false);
 }
 for(const options of [{maxStates:0},{maxOperationChecks:0}]){const report=sdk.analyzeRelationV3(sourceText,options);
  assert.deepEqual(report,old.analyzeV3(sourceText,options));assert.equal(report.status,'inconclusive');assert.equal(report.execution.metrics.complete,false);}
 for(const id of ['seven-committed-capacity','aborted-ops-exact-capacity-129']){
  const row=byId.get(id);assert.ok(row,id);const report=sdk.analyzeRelationV3(row.traceText,row.options);
  assert.deepEqual(report,old.analyzeV3(row.traceText,row.options));assert.equal(report.status,'inconclusive');assert.equal(report.execution.metrics.reason,'exact_capacity');
  assert.equal(report.execution.effectiveLimits.committedTransactions,6);assert.equal(report.execution.effectiveLimits.operations,128);
 }
 for(const options of [{maxChecks:0},{maxChecks:1},{maxChecks:256,analysisOptions:{maxStates:0}}]){
  const got=sdk.reduceRelationV3(sourceText,options);assert.deepEqual(got,old.reduceV3(sourceText,options));
  if(options.maxChecks===0||options.analysisOptions){assert.equal(got.oneMinimal,false);assert.equal(got.checks,0);}
 }
 const object=JSON.parse(sourceText),options={maxStates:9,maxOperationChecks:200};const beforeObject=clone(object),beforeOptions=clone(options);
 sdk.analyzeRelationV3(object,options);assert.deepEqual(object,beforeObject);assert.deepEqual(options,beforeOptions);
 return{gapHistories:5,zeroSearchBudgets:2,capacityChecks:2,reductionBudgets:3,exactCommittedTransactions:6,exactOperations:128};
});

await check('rehashed-conclusion-model-budget-and-source-tampering-is-rejected',()=>{
 const report=sdk.analyzeRelationV3(sourceText),original=JSON.parse(sdk.makeRelationCapsuleV3(sourceText,report));
 for(const mutate of [r=>r.status='consistent',r=>r.modelDefinition.id='register-serializable-v1',
  r=>r.execution.analysisOptions.maxStates=0,r=>r.evidence.sourceEvidence[0].values.t='forged']){
  const changed=clone(report);mutate(changed);assert.equal(sdk.verifyRelationV3(sourceText,changed).valid,false);
  assert.throws(()=>sdk.makeRelationCapsuleV3(sourceText,changed));
  const capsule=clone(original);capsule.reportText=JSON.stringify(changed);capsule.reportSha256=hash(capsule.reportText);
  assert.equal(sdk.replayRelationCapsuleV3(JSON.stringify(capsule)).valid,false);
 }
 const derived=clone(original);derived.normalizedText='null';derived.normalizedSha256=hash(derived.normalizedText);
 assert.equal(sdk.replayRelationCapsuleV3(JSON.stringify(derived)).valid,false);
 return{reportMutations:4,rehashedDerivedMutations:1};
});

let reduction;
await check('source-closed-4-to-3-reduction-and-all-three-single-deletes',()=>{
 assert.deepEqual(bind(resolve(candidate,'payload/examples/relation-source-closure.json')),inputs['fixtures/relation-v3/reduction-source-closure.json']);
 reduction=sdk.reduceRelationV3(sourceText);assert.deepEqual(reduction,old.reduceV3(sourceText));
 assert.equal(reduction.status,'reduced');assert.equal(reduction.oneMinimal,true);assert.deepEqual(reduction.removed,['N']);
 assert.deepEqual(reduction.report.normalized.transactions.map(x=>x.id),['P','A','B']);assert.equal(reduction.report.status,'violation');
 const original=JSON.parse(sourceText);
 for(let i=0;i<reduction.retainedOriginalSeq.length;i++){
  const event=clone(original.events.find(x=>x.seq===reduction.retainedOriginalSeq[i]));event.seq=i+1;
  assert.deepEqual(reduction.reducedCapture.events[i],event);
 }
 const deletes=[];
 for(const tx of reduction.report.normalized.transactions){const trace=clone(reduction.reducedCapture);
  trace.events=trace.events.filter(x=>x.tx!==tx.id).map((event,i)=>({...event,seq:i+1}));
  const report=sdk.analyzeRelationV3(trace);assert.equal(report.status,tx.id==='P'?'inconclusive':'consistent');
  deletes.push({id:'delete-'+tx.id,traceText:JSON.stringify(trace),expected:tx.id==='P'?'inconclusive':'consistent'});
 }
 assert.equal(sdk.verifyRelationV3(reduction.reducedCapture,reduction.report).valid,true);
 const capsule=sdk.makeRelationCapsuleV3(reduction.reducedCapture,reduction.report);assert.equal(sdk.replayRelationCapsuleV3(capsule).valid,true);
 save('reduction.json',reduction);save('reduced-capsule.json',JSON.parse(capsule));save('single-deletes.json',deletes);
 return{originalTransactions:4,reducedTransactions:3,retained:['P','A','B'],removed:['N'],singleDeletes:deletes.map(({id,expected})=>({id,expected})),oneMinimal:true};
});

await check('independent-relation-interpreter-checks-all-boundaries-and-reduction',()=>{
 assert.ok(reduction);const rows=relation.map(row=>({id:row.id,traceText:row.traceText,options:row.options,expected:row.expected}));
 rows.push({id:'closure-original',traceText:sourceText,expected:'violation'},
  {id:'closure-reduced',traceText:JSON.stringify(reduction.reducedCapture),expected:'violation'},...load(resolve(out,'single-deletes.json')));
 save('oracle-inputs.json',rows);
 const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
 const result=spawnSync(python,['-B',resolve(here,'oracle-batch.py'),resolve(root,'scripts/relation-v3-oracle.py'),resolve(out,'oracle-inputs.json'),resolve(out,'oracle-results.json')],
  {cwd:root,encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:2*1024*1024});
 save('oracle-process.json',{exitCode:result.status,stdout:result.stdout,stderr:result.stderr,error:result.error?.name||null});
 assert.equal(result.error,undefined);assert.equal(result.status,0,result.stderr||result.stdout);
 const got=load(resolve(out,'oracle-results.json'));assert.equal(got.passed,true);assert.equal(got.inputs,175);
 return{inputs:175,frozenInterpreterSha256:inputs['scripts/relation-v3-oracle.py'].sha256,independentInvocationNotNewInterpreter:true};
});

await check('author-194-regressions-independently-invoked-with-prior-sdk-snapshot',()=>{
 const result=spawnSync(process.execPath,[resolve(candidate,'payload/scripts/relation-sdk-test.mjs'),'--repository',root,
  '--runtime',runtime,'--output-root',out,'--example-root',resolve(candidate,'example-repository')],
  {cwd:root,encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:2*1024*1024});
 save('author-process.json',{exitCode:result.status,stdout:result.stdout,stderr:result.stderr,error:result.error?.name||null});
 assert.equal(result.error,undefined);assert.equal(result.status,0,result.stderr||result.stdout);
 const summary=JSON.parse(result.stdout),got=load(resolve(root,summary.receipt));assert.equal(got.passed,true);
 assert.equal(got.checks.length,194);assert.equal(got.priorSdkSnapshotAvailable,true);assert.equal(got.manualCases,170);
 return{checks:194,relationHistories:170,listHistories:71,receipt:summary.receipt,priorSdkSnapshotAvailable:true};
});

const after=Object.fromEntries(Object.keys(manifest.files).map(name=>[name,bind(resolve(candidate,name))]));
receipt.candidateUnchanged=JSON.stringify(before)===JSON.stringify(after);
receipt.inputsUnchanged=Object.entries(inputs).every(([name,binding])=>JSON.stringify(bind(resolve(root,name)))===JSON.stringify(binding));
receipt.manifestUnchanged=bind(manifestPath).sha256===expectedManifest;
receipt.passed=receipt.checks.every(x=>x.passed)&&receipt.candidateUnchanged&&receipt.inputsUnchanged&&receipt.manifestUnchanged;
receipt.candidateManifest={path:'artifacts/v015-relation-candidate/candidate-manifest.json',sha256:expectedManifest};
receipt.candidateBindings=before;receipt.inputBindings=inputs;
receipt.implementation={check:bind(fileURLToPath(import.meta.url)),oracleBatch:bind(resolve(here,'oracle-batch.py'))};
save('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,groups:receipt.checks.length,failed:receipt.checks.filter(x=>!x.passed),receipt:posix(resolve(out,'receipt.json'))}));
if(!receipt.passed)process.exitCode=1;
