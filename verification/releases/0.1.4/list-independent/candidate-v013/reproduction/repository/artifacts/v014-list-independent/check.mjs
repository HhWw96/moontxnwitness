import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync, copyFileSync} from 'node:fs';
import {resolve, dirname, relative} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../..');
const candidate=resolve(root,'artifacts/v014-list-candidate');
const expected='cda1b71bbfc2cb5e7c9b93f69f97065d5a9be950f1e8c059acc8a70ea093f9ff';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const bind=path=>{const raw=readFileSync(path);return {sha256:hash(raw),bytes:raw.length};};
const load=path=>JSON.parse(readFileSync(path,'utf8'));
const manifestPath=resolve(candidate,'candidate-manifest-v2.json');
assert.equal(bind(manifestPath).sha256,expected);
const manifest=load(manifestPath);
const before=Object.fromEntries(Object.keys(manifest.files).map(name=>[name,bind(resolve(candidate,name))]));
assert.deepEqual(before,manifest.files);
const baseline=load(resolve(candidate,'baseline-inputs.json'));
for(const [name,value] of Object.entries(baseline))assert.deepEqual(bind(resolve(root,name)),value,name);
mkdirSync(resolve(here,'runs'),{recursive:true});
const output=mkdtempSync(resolve(here,'runs','review-'));
const receipt={schema:1,kind:'independent-ai-fixed-list-sdk-review',passed:false,
  independentOfImplementation:true,checks:[],manualCases:0,manifestSha256:expected,
  databaseExecuted:false,buildExecuted:false,downloaded:false,performanceMeasurement:false,
  humanAcceptance:false,contestApproval:false};
const save=(name,value)=>writeFileSync(resolve(output,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const check=async(name,fn)=>{try{const detail=await fn();receipt.checks.push({name,passed:true,...detail});}
  catch(error){receipt.checks.push({name,passed:false,error:{name:error.name,message:error.message}});}};
const runtime=resolve(candidate,'runtime');
const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
const generic=await import(pathToFileURL(resolve(runtime,'generic-sdk.mjs')).href);
const manual=load(resolve(root,'fixtures/list-v3/manual.json'));
const byId=new Map(manual.map(row=>[row.id,row]));
const sourceText=byId.get('two-key-read-append-cycle').traceText;
const clone=value=>structuredClone(value);

await check('48-frozen-files-and-original-shared-core',()=>{
  assert.equal(Object.keys(before).length,48);
  const build=load(resolve(runtime,'build-manifest.json'));
  assert.equal(bind(resolve(runtime,'core.mjs')).sha256,build.coreSha256);
  assert.equal(bind(resolve(runtime,'capture-core.mjs')).sha256,build.captureCoreSha256);
  assert.deepEqual(bind(resolve(runtime,'generic-sdk.mjs')),baseline['dist/sdk.mjs']);
  assert.deepEqual(bind(resolve(runtime,'evidence.mjs')),baseline['dist/evidence.mjs']);
  assert.deepEqual(bind(resolve(runtime,'sdk.mjs')),bind(resolve(candidate,'payload/cmd/sdk.mjs')));
  return {files:48,coreVersion:build.version};
});

await check('all-71-frozen-histories-field-for-field-and-status',()=>{
  for(const row of manual){
    assert.equal(hash(row.traceText),row.inputSha256);
    const parsed=JSON.parse(row.traceText);
    if(parsed?.traceSchema!==3||parsed?.dataModel!=='append-list-v1'){
      assert.throws(()=>sdk.analyzeListV3(row.traceText,row.options),TypeError);
    }else{
      const report=sdk.analyzeListV3(row.traceText,row.options);
      assert.deepEqual(report,generic.analyzeV3(row.traceText,row.options),row.id);
      assert.deepEqual(sdk.normalizeListCaptureV3(row.traceText),generic.normalizeCaptureV3(row.traceText),row.id);
      assert.deepEqual(sdk.verifyListV3(row.traceText,report),generic.verifyV3(row.traceText,report),row.id);
      assert.equal(report.status,row.expected.analysis,row.id);
    }
    receipt.manualCases++;
  }
  assert.equal(receipt.manualCases,71);
  return {histories:71};
});

await check('all-five-capture-guards-pass-exact-raw-text-to-underlying-core',async()=>{
  const folder=resolve(output,'spy-runtime');mkdirSync(folder);
  const source=readFileSync(resolve(runtime,'sdk.mjs'),'utf8');
  copyFileSync(resolve(runtime,'sdk.mjs'),resolve(folder,'sdk.mjs'));
  globalThis.__listIndependentCalls=[];
  for(const moduleName of ['core','capture-core']){
    const expression=new RegExp("import\\s*\\{([^}]+)\\}\\s*from\\s*['\"]\\./"+moduleName+"\\.mjs['\"]");
    const names=source.match(expression)[1].split(',').map(value=>value.trim());
    writeFileSync(resolve(folder,moduleName+'.mjs'),names.map(name=>name==='version'
      ?`export function ${name}(){return 'spy';}`
      :`export function ${name}(...args){globalThis.__listIndependentCalls.push({name:'${name}',args});return JSON.stringify({valid:true,spy:true});}`).join('\n'),{flag:'wx'});
  }
  writeFileSync(resolve(folder,'evidence.mjs'),"export function makeCapsuleV3(...args){globalThis.__listIndependentCalls.push({name:'makeCapsuleV3',args});return 'spy';}\nexport function replayCapsuleV3(){return {valid:false,reason:'spy'};}\n",{flag:'wx'});
  const spy=await import(pathToFileURL(resolve(folder,'sdk.mjs')).href);
  const raw='\n\t'+sourceText.replace('{','{"extraDuplicate":"old","extraDuplicate":"new",')+' \r\n';
  const functions=['normalizeListCaptureV3','analyzeListV3','reduceListV3','verifyListV3','makeListCapsuleV3'];
  for(const name of functions){
    globalThis.__listIndependentCalls.length=0;
    spy[name](raw,{});
    assert.equal(globalThis.__listIndependentCalls.length,1,name);
    assert.equal(globalThis.__listIndependentCalls[0].args[0],raw,name);
  }
  let serializations=0;
  const object={toJSON(){serializations++;return JSON.parse(sourceText);}};
  globalThis.__listIndependentCalls.length=0;
  spy.analyzeListV3(object);
  assert.equal(serializations,1);
  assert.equal(globalThis.__listIndependentCalls[0].args[0],JSON.stringify(JSON.parse(sourceText)));
  // Spy only: test the exact boundary without allocating core parsing state.
  const exact=' '.repeat(8*1024*1024-Buffer.byteLength(sourceText))+sourceText;
  globalThis.__listIndependentCalls.length=0;
  spy.analyzeListV3(exact);
  assert.equal(globalThis.__listIndependentCalls[0].args[0],exact);
  globalThis.__listIndependentCalls.length=0;
  assert.throws(()=>spy.analyzeListV3(' '+exact),RangeError);
  assert.equal(globalThis.__listIndependentCalls.length,0);
  assert.throws(()=>spy.analyzeListV3({traceSchema:3,dataModel:'append-list-v1',note:'列'.repeat(3*1024*1024)}),RangeError);
  delete globalThis.__listIndependentCalls;
  return {captureEntries:5,exactUtf8Bytes:8*1024*1024,objectSerializationCount:1,spyScope:'Raw transport only; semantic checks use the real unchanged core'};
});

await check('raw-duplicate-root-nested-and-unicode-inputs-match-generic-invalid-semantics',()=>{
  const variants=[
    '\n'+sourceText+'\t\r\n',
    sourceText.replace('{','{"dataModel":"append-list-v1",'),
    sourceText.replace('"seq":1','"seq":1,"seq":1'),
    sourceText.replace('"clockDomain":','"clockDomain" :'),
  ];
  for(const raw of variants){
    const report=sdk.analyzeListV3(raw);
    assert.deepEqual(report,generic.analyzeV3(raw));
    const capsule=sdk.makeListCapsuleV3(raw,report);
    assert.equal(JSON.parse(capsule).traceText,raw);
    assert.deepEqual(sdk.replayListCapsuleV3(capsule),generic.replayCapsuleV3(capsule));
  }
  const duplicate=variants[1];
  const result=sdk.replayListCapsuleV3(sdk.makeListCapsuleV3(duplicate));
  assert.equal(result.valid,true);assert.equal(result.status,'invalid');assert.equal(result.coverageComplete,false);
  return {rawVariants:variants.length,invalidReplayMeansModelAccepted:false};
});

await check('first-failure-inputs-now-reject-without-throwing',()=>{
  const results=[];
  for(const trace of ['{','','{"incomplete":','not json']){
    const report=generic.analyzeV3(trace),capsule=generic.makeCapsuleV3(trace,report);
    const base=generic.replayCapsuleV3(capsule);
    assert.equal(base.valid,true);assert.equal(base.status,'invalid');
    const got=sdk.replayListCapsuleV3(capsule);
    assert.equal(got.valid,false);results.push({trace,base,got});
  }
  save('malformed-trace-regression.json',results);
  return {retainedFirstFailure:'artifacts/v014-list-independent/runs/malformed-gf67h3/receipt.json',unchangedInputs:4};
});

await check('foreign-null-array-primitive-register-relation-and-missing-model-rejected',()=>{
  const foreign=[null,[],7,{},true,'text',load(resolve(root,'examples/v3-write-skew.json')),
    JSON.parse(load(resolve(root,'fixtures/relation-v3/boundary.json'))[0].traceText),
    {...JSON.parse(sourceText),dataModel:undefined}];
  for(const trace of foreign){
    const captureArgument=typeof trace==='string'?JSON.stringify(trace):trace;
    for(const name of ['normalizeListCaptureV3','analyzeListV3','reduceListV3','verifyListV3','makeListCapsuleV3'])
      assert.throws(()=>sdk[name](captureArgument,{}),TypeError,name);
    const raw=JSON.stringify(trace),report=generic.analyzeV3(raw),capsule=generic.makeCapsuleV3(raw,report);
    assert.equal(generic.replayCapsuleV3(capsule).valid,true);
    assert.equal(sdk.replayListCapsuleV3(capsule).valid,false);
  }
  return {foreignRoots:foreign.length};
});

await check('unknown-source-unknown-outcome-and-search-budget-remain-inconclusive',()=>{
  const cases=[...['unknown-item-source','disconnect-keeps-unknown','future-producer-does-not-repair-source'].map(id=>[byId.get(id).traceText,{}]),
    [sourceText,{maxStates:0}],[sourceText,{maxOperationChecks:0}]];
  for(const [raw,options] of cases){
    const report=sdk.analyzeListV3(raw,options);
    assert.deepEqual(report,generic.analyzeV3(raw,options));
    assert.equal(report.status,'inconclusive');
    assert.deepEqual(report.normalized.observations,JSON.parse(raw).events);
    assert.equal(report.normalized.history,null);
    const replay=sdk.replayListCapsuleV3(sdk.makeListCapsuleV3(raw,report));
    assert.deepEqual(replay,generic.replayCapsuleV3(generic.makeCapsuleV3(raw,report)));
    assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');
    if(report.coverage.complete===false)assert.equal(replay.coverageComplete,false);
  }
  return {cases:cases.length,validReplayDoesNotMeanConsistent:true};
});

await check('capacity-and-independent-reduction-budget-unchanged',()=>{
  for(const id of ['seven-committed-exceeds-capacity','129-operations-exceeds-capacity']){
    const raw=byId.get(id).traceText,report=sdk.analyzeListV3(raw);
    assert.deepEqual(report,generic.analyzeV3(raw));
    assert.equal(report.status,'inconclusive');assert.equal(report.execution.metrics.reason,'exact_capacity');
    assert.equal(report.execution.effectiveLimits.committedTransactions,6);assert.equal(report.execution.effectiveLimits.operations,128);
  }
  for(const options of [{maxChecks:0},{maxChecks:1},{maxChecks:256,analysisOptions:{maxStates:0}}]){
    const got=sdk.reduceListV3(sourceText,options);
    assert.deepEqual(got,generic.reduceV3(sourceText,options));
    if(options.maxChecks===0||options.analysisOptions){assert.equal(got.oneMinimal,false);assert.equal(got.checks,0);}
  }
  const object=JSON.parse(sourceText),options={maxStates:5,maxOperationChecks:200};
  const oldTrace=clone(object),oldOptions=clone(options);
  sdk.analyzeListV3(object,options);assert.deepEqual(object,oldTrace);assert.deepEqual(options,oldOptions);
  return {exactCommittedTransactions:6,exactOperations:128,reductionVariants:3};
});

await check('capsule-source-budget-model-and-derived-facts-cannot-be-rehashed-to-forge-result',()=>{
  const report=sdk.analyzeListV3(sourceText),original=JSON.parse(sdk.makeListCapsuleV3(sourceText,report));
  for(const mutate of [r=>r.status='consistent',r=>r.coverage.complete=false,
    r=>r.modelDefinition.id='register-serializable-v1',r=>r.execution.analysisOptions.maxStates=0]){
    const changed=clone(report);mutate(changed);
    assert.equal(sdk.verifyListV3(sourceText,changed).valid,false);
    const capsule=clone(original);capsule.reportText=JSON.stringify(changed);capsule.reportSha256=hash(capsule.reportText);
    assert.equal(sdk.replayListCapsuleV3(JSON.stringify(capsule)).valid,false);
  }
  const capsule=clone(original);capsule.normalizedText='null';capsule.normalizedSha256=hash(capsule.normalizedText);
  assert.equal(sdk.replayListCapsuleV3(JSON.stringify(capsule)).valid,false);
  assert.equal(sdk.replayListCapsuleV3('{').valid,false);
  return {reportMutations:4,rehashedDerivedFactMutations:1};
});

await check('author-92-regression-independent-invocation-retains-examples-and-oracle',()=>{
  const result=spawnSync(process.execPath,[resolve(candidate,'payload/scripts/list-sdk-test.mjs'),
    '--repository',root,'--runtime',runtime,'--output-root',output,'--example-root',resolve(candidate,'example-repository')],
    {cwd:root,encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:2*1024*1024});
  save('author-run-process.json',{exitCode:result.status,stdout:result.stdout,stderr:result.stderr,error:result.error?.name||null});
  assert.equal(result.error,undefined);assert.equal(result.status,0,result.stderr||result.stdout);
  const summary=JSON.parse(result.stdout),author=load(resolve(root,summary.receipt));
  assert.equal(author.passed,true);assert.equal(author.checks.length,92);assert.equal(author.manualCases,71);
  return {checks:92,output:summary.receipt};
});

const after=Object.fromEntries(Object.keys(manifest.files).map(name=>[name,bind(resolve(candidate,name))]));
receipt.candidateUnchanged=JSON.stringify(before)===JSON.stringify(after);
receipt.mainlineUnchanged=Object.entries(baseline).every(([name,value])=>{const got=bind(resolve(root,name));return got.sha256===value.sha256&&got.bytes===value.bytes;});
receipt.manifestUnchanged=bind(manifestPath).sha256===expected;
receipt.passed=receipt.checks.every(row=>row.passed)&&receipt.candidateUnchanged&&receipt.mainlineUnchanged&&receipt.manifestUnchanged;
receipt.candidateBindings=before;receipt.originalBaseline=baseline;
receipt.implementation=bind(fileURLToPath(import.meta.url));
save('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,groups:receipt.checks.length,failed:receipt.checks.filter(row=>!row.passed),receipt:relative(root,resolve(output,'receipt.json')).replaceAll('\\','/')}));
if(!receipt.passed)process.exitCode=1;
