// Prepared actual-v0.1.5 review. Do not run against the candidate's v0.1.4 core.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,readdirSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve,dirname,relative,isAbsolute} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {auditRawRelation} from './raw-review.mjs';
const here=dirname(fileURLToPath(import.meta.url)),flags=new Map();
for(let i=2;i<process.argv.length;i+=2){assert.ok(['--repository','--expected','--output-root'].includes(process.argv[i]));assert.ok(process.argv[i+1]);flags.set(process.argv[i],process.argv[i+1]);}
assert.ok(flags.get('--repository'));assert.ok(flags.get('--expected'));assert.ok(flags.get('--output-root'));
const root=resolve(flags.get('--repository')),expectedFile=resolve(flags.get('--expected'));
const outputRoot=resolve(flags.get('--output-root'));mkdirSync(outputRoot,{recursive:true});const out=mkdtempSync(resolve(outputRoot,'actual15-'));
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const bind=file=>{const raw=readFileSync(file);return{bytes:raw.length,sha256:hash(raw)};};
const load=file=>JSON.parse(readFileSync(file,'utf8'));
const rel=file=>relative(root,file).replaceAll('\\','/');
const redact=text=>[root,root.replaceAll('\\','/'),JSON.stringify(root).slice(1,-1)].reduce((value,prefix)=>value.replaceAll(prefix,'<repository>'),text);
const save=(name,value)=>writeFileSync(resolve(out,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const inside=name=>{assert.equal(typeof name,'string');assert.ok(!isAbsolute(name)&&!name.includes('\\')&&!name.split('/').includes('..')&&!name.includes(':'));
 const path=resolve(root,name);assert.ok(!relative(root,path).startsWith('..'));return path;};
const clone=value=>structuredClone(value);
const walk=folder=>readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?walk(resolve(folder,entry.name)):[resolve(folder,entry.name)]);
const receipt={schema:1,kind:'independent-ai-actual-v015-relation-sdk-and-retained-database-review',passed:false,
 reviewerRole:'Independent AI reviewer, not SDK wrapper or database fixture author',version:'0.1.5',checks:[],
 buildExecuted:false,databaseReexecuted:false,downloaded:false,installed:false,performanceMeasured:false,humanAcceptance:false,contestApproval:false};
const check=async(name,fn)=>{try{receipt.checks.push({name,passed:true,...await fn()});return true;}
 catch(error){receipt.checks.push({name,passed:false,error:{name:error.name,message:redact(error.message)}});return false;}};
let expected,build,sdk,evidence,sourceBefore,runtimeBefore,files;
function fingerprint(){const names=['moon.mod',...walk(resolve(root,'src')).map(rel).filter(name=>name.endsWith('.mbt')||name.endsWith('/moon.pkg'))].sort();
 const h=createHash('sha256');for(const name of names){h.update(name+'\0');h.update(readFileSync(inside(name)));h.update('\0');}return h.digest('hex');}
const inventory=names=>Object.fromEntries(names.map(name=>[name,bind(inside(name))]));
const setupPassed=await check('independently-supplied-actual-v015-build-and-source-bindings',async()=>{
 expected=load(expectedFile);assert.equal(expected.schema,1);assert.equal(expected.version,'0.1.5');
 for(const key of ['sourceSha256','coreSha256','captureCoreSha256'])assert.match(expected[key],/^[a-f0-9]{64}$/);
 const runtimeNames=['dist/build-manifest.json','dist/core.mjs','dist/capture-core.mjs','dist/sdk.mjs','dist/evidence.mjs'];
 assert.deepEqual(Object.keys(expected.runtimeBindings).sort(),[...runtimeNames].sort());
 for(const[name,value]of Object.entries(expected.runtimeBindings)){assert.deepEqual(Object.keys(value).sort(),['bytes','sha256']);assert.match(value.sha256,/^[a-f0-9]{64}$/);assert.ok(Number.isSafeInteger(value.bytes)&&value.bytes>0);assert.deepEqual(bind(inside(name)),value,name);}
 build=load(inside('dist/build-manifest.json'));assert.equal(build.version,'0.1.5');
 for(const key of ['sourceSha256','coreSha256','captureCoreSha256'])assert.equal(build[key],expected[key]);
 assert.equal(fingerprint(),expected.sourceSha256);assert.equal(bind(inside('dist/core.mjs')).sha256,build.coreSha256);assert.equal(bind(inside('dist/capture-core.mjs')).sha256,build.captureCoreSha256);
 assert.deepEqual(bind(inside('cmd/sdk.mjs')),bind(inside('dist/sdk.mjs')));
 files=['moon.mod',...walk(resolve(root,'src')).map(rel).filter(name=>name.endsWith('.mbt')||name.endsWith('/moon.pkg')),
  'cmd/sdk.mjs','cmd/evidence.mjs','examples/relation-source-closure.json','examples/relation-roundtrip.mjs','fixtures/relation-v3/boundary.json',
  'fixtures/relation-v3/reduction-source-closure.json','fixtures/relation-v3/reduction-source-closure.expected.json','fixtures/list-v3/manual.json',
  'fixtures/list-v3/reduction-source-closure.json','scripts/relation-v3-oracle.py','experiments/relation_v3/run_postgres.py',
  'experiments/relation_v3/local_postgres.py','experiments/relation_v3/test_fixture.py','experiments/relation_v3/e2e.mjs'];
 sourceBefore=inventory(files);runtimeBefore=inventory(runtimeNames);
 sdk=await import(pathToFileURL(inside('dist/sdk.mjs')).href);evidence=await import(pathToFileURL(inside('dist/evidence.mjs')).href);assert.equal(sdk.version(),'0.1.5');
 receipt.expectedFingerprint=bind(expectedFile);receipt.build=build;receipt.sourceBindingsBefore=sourceBefore;receipt.runtimeBindingsBefore=runtimeBefore;
 return{version:sdk.version(),sourceFiles:files.length,providedRuntimeBindings:runtimeNames.length};
});
if(setupPassed){
 const relation=load(inside('fixtures/relation-v3/boundary.json')),list=load(inside('fixtures/list-v3/manual.json'));
 const byId=new Map(relation.map(row=>[row.id,row]));const source=readFileSync(inside('examples/relation-source-closure.json'),'utf8');
 const oracle=[];
 function capsuleParity(raw,report,fixedMake,fixedReplay){let old,error;try{old=sdk.makeCapsuleV3(raw,report);}catch(e){error=e;}
  if(error){assert.throws(()=>fixedMake(raw,report),e=>e.constructor===error.constructor&&e.message===error.message);return false;}
  const made=fixedMake(raw,report);assert.equal(made,old);assert.deepEqual(fixedReplay(made),sdk.replayCapsuleV3(old));return true;}
 await check('170-frozen-relation-histories-current-generic-field-parity',()=>{
  let packageable=0;for(const row of relation){assert.equal(hash(row.traceText),row.inputSha256,row.id);const report=sdk.analyzeRelationV3(row.traceText,row.options);
   assert.equal(report.status,row.expected,row.id);assert.deepEqual(report,sdk.analyzeV3(row.traceText,row.options));
   assert.deepEqual(sdk.normalizeRelationCaptureV3(row.traceText),sdk.normalizeCaptureV3(row.traceText));assert.deepEqual(sdk.verifyRelationV3(row.traceText,report),sdk.verifyV3(row.traceText,report));
   if(capsuleParity(row.traceText,report,sdk.makeRelationCapsuleV3,sdk.replayRelationCapsuleV3))packageable++;
   oracle.push({id:'boundary/'+row.id,traceText:row.traceText,options:row.options,expected:row.expected});
  }assert.equal(relation.length,170);return{histories:170,packageable};
 });
 await check('71-prior-list-histories-six-entry-behavior-preserved',()=>{
  let originalRejections=0;for(const row of list){assert.equal(hash(row.traceText),row.inputSha256);const trace=JSON.parse(row.traceText);
   if(trace?.traceSchema!==3||trace?.dataModel!=='append-list-v1'){assert.throws(()=>sdk.analyzeListV3(row.traceText,row.options),TypeError);continue;}
   const report=sdk.analyzeListV3(row.traceText,row.options);assert.equal(report.status,row.expected.analysis);assert.deepEqual(report,sdk.analyzeV3(row.traceText,row.options));
   assert.deepEqual(sdk.normalizeListCaptureV3(row.traceText),sdk.normalizeCaptureV3(row.traceText));assert.deepEqual(sdk.verifyListV3(row.traceText,report),sdk.verifyV3(row.traceText,report));
   if(!capsuleParity(row.traceText,report,sdk.makeListCapsuleV3,sdk.replayListCapsuleV3))originalRejections++;
  }const history=load(inside('fixtures/list-v3/reduction-source-closure.json'));assert.deepEqual(sdk.reduceListV3(history),sdk.reduceV3(history));
  assert.equal(list.length,71);return{histories:71,reductionComparisons:1,originalRejections};
 });
 await check('malformed-generic-diagnostics-invalid-relation-and-foreign-model-guards',()=>{
  for(const raw of ['{','','not JSON','{"traceSchema":3,']){const capsule=sdk.makeCapsuleV3(raw,sdk.analyzeV3(raw));const generic=sdk.replayCapsuleV3(capsule);
   assert.equal(generic.valid,true);assert.equal(generic.status,'invalid');assert.equal(sdk.replayRelationCapsuleV3(capsule).valid,false);assert.equal(sdk.replayListCapsuleV3(capsule).valid,false);}
  const duplicate=source.replace('{','{"dataModel":"relation-set-v1",');const invalid=sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(duplicate));
  assert.equal(invalid.valid,true);assert.equal(invalid.status,'invalid');assert.equal(invalid.coverageComplete,false);
  for(const trace of [null,[],1,true,'text',{},JSON.parse(list[0].traceText)]){const text=JSON.stringify(trace);
   for(const name of ['normalizeRelationCaptureV3','analyzeRelationV3','reduceRelationV3','verifyRelationV3','makeRelationCapsuleV3'])assert.throws(()=>sdk[name](text,{}),TypeError);
   const capsule=sdk.makeCapsuleV3(text,sdk.analyzeV3(text));assert.equal(sdk.replayRelationCapsuleV3(capsule).valid,false);}
  return{malformedTraces:4,foreignRoots:7,invalidRelationDiagnosticPreserved:true};
 });
 await check('source-closure-4-to-3-and-every-retained-single-delete',()=>{
  assert.deepEqual(bind(inside('examples/relation-source-closure.json')),bind(inside('fixtures/relation-v3/reduction-source-closure.json')));
  const reduction=sdk.reduceRelationV3(source);assert.deepEqual(reduction,sdk.reduceV3(source));assert.equal(reduction.status,'reduced');assert.equal(reduction.oneMinimal,true);assert.deepEqual(reduction.removed,['N']);
  assert.deepEqual(reduction.report.normalized.transactions.map(tx=>tx.id),['P','A','B']);assert.equal(reduction.report.status,'violation');
  const original=JSON.parse(source);for(let i=0;i<reduction.retainedOriginalSeq.length;i++){const event=clone(original.events.find(e=>e.seq===reduction.retainedOriginalSeq[i]));event.seq=i+1;assert.deepEqual(event,reduction.reducedCapture.events[i]);}
  oracle.push({id:'closure/original',traceText:source,expected:'violation'},{id:'closure/reduced',traceText:JSON.stringify(reduction.reducedCapture),expected:'violation'});
  for(const tx of reduction.report.normalized.transactions){const deleted=clone(reduction.reducedCapture);deleted.events=deleted.events.filter(e=>e.tx!==tx.id).map((e,i)=>({...e,seq:i+1}));
   const expectedStatus=tx.id==='P'?'inconclusive':'consistent';assert.equal(sdk.analyzeRelationV3(deleted).status,expectedStatus);oracle.push({id:'closure/delete-'+tx.id,traceText:JSON.stringify(deleted),expected:expectedStatus});}
  assert.equal(sdk.verifyRelationV3(reduction.reducedCapture,reduction.report).valid,true);const capsule=sdk.makeRelationCapsuleV3(reduction.reducedCapture,reduction.report);assert.equal(sdk.replayRelationCapsuleV3(capsule).valid,true);
  save('reduction.json',reduction);save('reduced-capsule.json',JSON.parse(capsule));return{original:4,reduced:3,retained:['P','A','B'],singleDeletes:3};
 });
 await check('budget-source-capacity-and-rehashed-tampering-retain-original-semantics',()=>{
  for(const id of ['unknown-read-version','unknown-commit','supplement-later-read-source-does-not-repair-gap','partial-query','snapshot-coverage-omitted']){
   const row=byId.get(id),report=sdk.analyzeRelationV3(row.traceText,row.options);assert.equal(report.status,'inconclusive');assert.equal(report.coverage.complete,false);
   const replay=sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(row.traceText,report));assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');assert.equal(replay.coverageComplete,false);}
  for(const options of [{maxStates:0},{maxOperationChecks:0}]){const report=sdk.analyzeRelationV3(source,options);assert.equal(report.status,'inconclusive');assert.equal(report.execution.metrics.complete,false);}
  for(const id of ['seven-committed-capacity','aborted-ops-exact-capacity-129']){const row=byId.get(id),report=sdk.analyzeRelationV3(row.traceText,row.options);assert.equal(report.status,'inconclusive');assert.equal(report.execution.metrics.reason,'exact_capacity');assert.equal(report.execution.effectiveLimits.committedTransactions,6);assert.equal(report.execution.effectiveLimits.operations,128);}
  for(const options of [{maxChecks:0},{maxChecks:1},{maxChecks:256,analysisOptions:{maxStates:0}}]){const got=sdk.reduceRelationV3(source,options);assert.deepEqual(got,sdk.reduceV3(source,options));if(options.maxChecks===0||options.analysisOptions){assert.equal(got.oneMinimal,false);assert.equal(got.checks,0);}}
  const report=sdk.analyzeRelationV3(source),original=JSON.parse(sdk.makeRelationCapsuleV3(source,report));
  for(const mutate of [r=>r.status='consistent',r=>r.modelDefinition.id='register-serializable-v1',r=>r.execution.analysisOptions.maxStates=0,r=>r.evidence.sourceEvidence[0].values.t='forged']){
   const changed=clone(report);mutate(changed);assert.equal(sdk.verifyRelationV3(source,changed).valid,false);assert.throws(()=>sdk.makeRelationCapsuleV3(source,changed));
   const capsule=clone(original);capsule.reportText=JSON.stringify(changed);capsule.reportSha256=hash(capsule.reportText);assert.equal(sdk.replayRelationCapsuleV3(JSON.stringify(capsule)).valid,false);}
  return{sourceGaps:5,searchBudgets:2,capacityChecks:2,reductionBudgets:3,rehashedReportMutations:4};
 });
 await check('published-v014-real-register-and-list-capsules-still-replay',()=>{
  const legacy=expected.legacy;assert.ok(legacy);
  const registerPath=inside(legacy.registerReceipt);assert.equal(bind(registerPath).sha256,legacy.registerReceiptSha256);const register=load(registerPath);
  assert.equal(register.version,'0.1.4');assert.equal(register.passed,true);assert.equal(register.actualDatabaseExecution,true);
  const results=[];for(const name of ['rr.capsule.json','serial.capsule.json','mini.capsule.json']){const path=resolve(dirname(registerPath),name);assert.equal(bind(path).sha256,register.files[name]);
   const text=readFileSync(path,'utf8');assert.equal(JSON.parse(text).engineVersion,'0.1.4');const replay=evidence.replayCapsule(text);assert.equal(replay.valid,true);results.push({file:rel(path),...bind(path),result:replay});}
  const phasePath=inside(legacy.listPhaseReceipt);assert.equal(bind(phasePath).sha256,legacy.listPhaseReceiptSha256);const phase=load(phasePath);
  assert.equal(phase.version,'0.1.4');assert.equal(phase.passed,true);assert.equal(phase.actualDatabaseExecution,true);
  const directory=inside('verification/'+phase.receipts.list.path),rawPath=resolve(directory,'database-receipt.json'),modelPath=resolve(directory,'model-receipt.json');
  assert.equal(bind(rawPath).sha256,phase.receipts.list.sha256);assert.equal(bind(modelPath).sha256,phase.receipts.listModel.sha256);
  const raw=load(rawPath),model=load(modelPath);assert.equal(raw.actualDatabaseExecution,true);assert.equal(raw.passed,true);assert.equal(model.build.version,'0.1.4');assert.equal(model.passed,true);
  const modelBindings=new Map(model.bindings.map(b=>[b.file,b]));assert.equal(raw.cases.length,120);
  for(const row of raw.cases){const name=row.directory+'/capsule.json',path=resolve(directory,name),binding=modelBindings.get(name);assert.ok(binding);assert.deepEqual(bind(path),{bytes:binding.bytes,sha256:binding.sha256});
   const text=readFileSync(path,'utf8');assert.equal(JSON.parse(text).engineVersion,'0.1.4');const replay=sdk.replayListCapsuleV3(text);assert.equal(replay.valid,true);assert.equal(replay.status,row.expectedModelStatus);results.push({file:rel(path),...bind(path),result:replay});}
  save('legacy-v014-results.json',results);return{realRegisterCapsules:3,realListCapsules:120,noOldCoreUsedToVerify:true};
 });
 await check('new-relation-pg-raw-and-sibling-model-source-ledger-and-output-bindings',()=>{
  const database=expected.database;assert.ok(database);const rawDirectory=inside(database.rawDirectory),modelDirectory=inside(database.modelDirectory);
  assert.equal(modelDirectory,rawDirectory+'-model','Expected explicit raw and -model siblings');
  const rawPath=resolve(rawDirectory,'database-receipt.json'),modelPath=resolve(modelDirectory,'model-receipt.json');
  assert.equal(bind(rawPath).sha256,database.rawReceiptSha256);assert.equal(bind(modelPath).sha256,database.modelReceiptSha256);
  const raw=load(rawPath),model=load(modelPath);assert.equal(raw.passed,true);assert.equal(raw.actualDatabaseExecution,true);assert.equal(raw.actualPostgresExecution,true);assert.equal(raw.sourceBindingsUnchanged,true);
  assert.deepEqual(raw.sourceBindings,raw.sourceBindingsAfter);assert.equal(raw.completeAutomaticSqlCapture,false);
  assert.equal(raw.scenarioCount,8);assert.equal(raw.roundsPerScenario,20);assert.equal(raw.scenarios.length,160);
  for(const[name,binding]of Object.entries(raw.sourceBindings))assert.deepEqual(bind(inside('experiments/relation_v3/'+name)),{bytes:binding.bytes,sha256:binding.sha256});
  assert.equal(model.passed,true);assert.equal(model.actualDatabaseExecution,false);assert.deepEqual(model.sourceDatabaseExecutionReceipt,bind(rawPath));assert.deepEqual(model.productionBuild,build);
  assert.deepEqual(model.oracleSnapshot,bind(inside('scripts/relation-v3-oracle.py')));
  for(const[name,binding]of Object.entries(model.sourceBindings)){const path=name==='e2e.mjs'?'experiments/relation_v3/e2e.mjs':name;assert.deepEqual(bind(inside(path)),binding);}
  assert.equal(model.cases.length,160);const counts={},results=[];let rawFiles=0,modelFiles=0;
  for(const row of raw.scenarios){const directory=resolve(rawDirectory,row.path);for(const b of row.artifacts){assert.deepEqual(bind(resolve(directory,b.path)),{bytes:b.bytes,sha256:b.sha256});rawFiles++;}
   const matched=model.cases.find(c=>c.name===row.name&&c.round===row.round);assert.ok(matched);assert.equal(matched.passed,true);
   const destination=resolve(modelDirectory,row.path);for(const[name,binding]of Object.entries(matched.artifactBindings)){assert.deepEqual(bind(resolve(destination,name)),binding);modelFiles++;}
   const text=readFileSync(resolve(directory,'trace.json'),'utf8'),trace=JSON.parse(text),rawCheck=auditRawRelation(directory,trace);
   const report=sdk.analyzeRelationV3(text);assert.equal(report.status,row.expectedVerdict);assert.deepEqual(report,sdk.analyzeV3(text));assert.deepEqual(report,load(resolve(destination,'report.json')));
   assert.deepEqual(sdk.normalizeRelationCaptureV3(text),load(resolve(destination,'normalized.json')));assert.equal(sdk.verifyRelationV3(text,report).valid,true);
   const capsule=readFileSync(resolve(destination,'capsule.json'),'utf8');assert.equal(JSON.parse(capsule).engineVersion,'0.1.5');const replay=sdk.replayRelationCapsuleV3(capsule);assert.equal(replay.valid,true);assert.equal(replay.status,report.status);
   assert.deepEqual(replay,load(resolve(destination,'replay.json')));assert.equal(load(resolve(destination,'oracle.json')).status,row.expectedVerdict);
   counts[row.name]=(counts[row.name]||0)+1;oracle.push({id:'actual-pg/'+row.path,traceText:text,expected:row.expectedVerdict});
   results.push({path:row.path,status:report.status,rawCheck,report:bind(resolve(destination,'report.json')),capsule:bind(resolve(destination,'capsule.json'))});
  }assert.equal(Object.keys(counts).length,8);for(const count of Object.values(counts))assert.equal(count,20);
  save('actual-pg-results.json',results);return{cases:160,rawFiles,modelFiles,scenarios:counts,databaseReexecuted:false,rawReceipt:bind(rawPath),modelReceipt:bind(modelPath)};
 });
 await check('frozen-independent-relation-interpreter-all-boundaries-reduction-and-new-pg',()=>{
  assert.equal(oracle.length,335);save('oracle-inputs.json',oracle);
  const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
  const p=spawnSync(python,['-B',resolve(here,'oracle-batch.py'),inside('scripts/relation-v3-oracle.py'),resolve(out,'oracle-inputs.json'),resolve(out,'oracle-results.json')],{cwd:root,encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:2*1024*1024});
  save('oracle-process.json',{exitCode:p.status,stdout:redact(p.stdout||''),stderr:redact(p.stderr||''),error:p.error?.name||null});
  assert.equal(p.error,undefined);assert.equal(p.status,0,p.stderr);const result=load(resolve(out,'oracle-results.json'));assert.equal(result.passed,true);assert.equal(result.inputs,335);
  return{inputs:335,relationBoundary:170,closureOriginalReducedAndSingleDeletes:5,newRawPg:160};
 });
 receipt.sourceBindingsAfter=inventory(files);receipt.runtimeBindingsAfter=inventory(Object.keys(runtimeBefore));
 receipt.sourceUnchanged=JSON.stringify(sourceBefore)===JSON.stringify(receipt.sourceBindingsAfter);
 receipt.runtimeUnchanged=JSON.stringify(runtimeBefore)===JSON.stringify(receipt.runtimeBindingsAfter);
 receipt.sourceFingerprintAfter=fingerprint();receipt.fingerprintUnchanged=receipt.sourceFingerprintAfter===build.sourceSha256;
}
receipt.passed=setupPassed&&receipt.checks.length===9&&receipt.checks.every(c=>c.passed)&&receipt.sourceUnchanged&&receipt.runtimeUnchanged&&receipt.fingerprintUnchanged;
receipt.implementation={check:bind(fileURLToPath(import.meta.url)),rawReview:bind(resolve(here,'raw-review.mjs')),oracleBatch:bind(resolve(here,'oracle-batch.py'))};
save('receipt.json',receipt);console.log(JSON.stringify({passed:receipt.passed,groups:receipt.checks.length,failures:receipt.checks.filter(c=>!c.passed),receipt:rel(resolve(out,'receipt.json'))}));if(!receipt.passed)process.exitCode=1;
