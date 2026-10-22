// Independent candidate review. No build, database, network, JVM or new Elle run.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,copyFileSync,readdirSync} from 'node:fs';
import {dirname,resolve,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const here=dirname(fileURLToPath(import.meta.url)),flags=new Map();
for(let i=2;i<process.argv.length;i+=2){assert.ok(['--repository','--candidate','--output-root'].includes(process.argv[i]));assert.ok(process.argv[i+1]);flags.set(process.argv[i],process.argv[i+1]);}
const root=resolve(flags.get('--repository')||resolve(here,'../..'));
const candidate=resolve(flags.get('--candidate')||resolve(root,'artifacts/v016-classification-planning'));
const expectedManifest='61205262bbe46daabdc5383eeea13aff4899ab27a61262107b2925fc65170803';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const bind=file=>{const raw=readFileSync(file);return{bytes:raw.length,sha256:hash(raw)};};
const load=file=>JSON.parse(readFileSync(file,'utf8'));
const clone=value=>structuredClone(value);
const posix=file=>relative(root,file).replaceAll('\\','/');
const redact=text=>[root,root.replaceAll('\\','/'),JSON.stringify(root).slice(1,-1)].reduce((text,prefix)=>text.replaceAll(prefix,'<repository>'),text);
const outputRoot=resolve(flags.get('--output-root')||resolve(here,'runs'));mkdirSync(outputRoot,{recursive:true});const out=mkdtempSync(resolve(outputRoot,'review-'));
const save=(name,value)=>writeFileSync(resolve(out,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const receipt={schema:1,kind:'independent-ai-register-cycle-candidate-review',passed:false,
 scope:'Candidate v0.1.4 runtime and isolated addition to frozen v0.1.5 runtime; not an actual v0.1.6 build',
 independentOfImplementation:true,newElleExecution:false,newCoreBuild:false,databaseExecuted:false,downloaded:false,
 performanceMeasurement:false,humanAcceptance:false,contestApproval:false,checks:[]};
const check=async(name,fn)=>{try{receipt.checks.push({name,passed:true,...await fn()});}
 catch(error){receipt.checks.push({name,passed:false,error:{name:error.name,message:redact(error.message)}});}};
const manifestPath=resolve(candidate,'candidate-manifest.json');assert.equal(bind(manifestPath).sha256,expectedManifest);
const manifest=load(manifestPath);
const candidateBefore=Object.fromEntries(manifest.files.map(row=>[row.file,bind(resolve(candidate,row.file))]));
for(const row of manifest.files)assert.deepEqual(candidateBefore[row.file],{bytes:row.bytes,sha256:row.sha256});
const rootFiles=['cmd/sdk.mjs','cmd/evidence.mjs','dist/sdk.mjs','dist/evidence.mjs','dist/core.mjs','dist/capture-core.mjs','dist/build-manifest.json'];
const mainlineBefore=Object.fromEntries(rootFiles.map(name=>[name,bind(resolve(root,name))]));
const customFile=resolve(here,'independent-inputs.json'),customManifest=load(resolve(here,'independent-input-manifest.json'));
assert.deepEqual(bind(customFile),{bytes:customManifest.bytes,sha256:customManifest.sha256});
const custom=load(customFile),manual=load(resolve(candidate,'handwritten-inputs.json'));
const sdk=await import(pathToFileURL(resolve(candidate,'runtime/sdk.mjs')).href);
const base=await import(pathToFileURL(resolve(candidate,'runtime/generic-sdk.mjs')).href);
const byId=new Map(manual.map(row=>[row.id,row]));
const inputRoot=resolve(candidate,'source-inputs');
const referenceRoot=resolve(inputRoot,'verification/experimental-candidates/elle-smoke-r2-2026-10-21');
function subtype(types){
 const positions=types.flatMap((type,index)=>type==='rw'?[index]:[]);
 if(positions.length===0)return types.includes('wr')?'G1c':'G0';
 if(positions.length===1)return 'G-single-item';
 const distances=positions.map((position,index)=>(positions[(index+1)%positions.length]-position+types.length)%types.length);
 return distances.includes(1)?'G2-item':'G-nonadjacent-item';
}
function verifyExplanation(api,row){
 assert.equal(hash(row.traceText),row.inputSha256);const report=api.analyzeV3(row.traceText),exp=api.explainRegisterCycleV3(row.traceText,report);
 if(row.expectedSourceStatus!==null)assert.equal(report.status,row.expectedSourceStatus,row.id);
 assert.equal(exp.verifiedReport,true,row.id);assert.equal(exp.sourceStatus,report.status);
 assert.equal(exp.subtype,row.expectedSubtype,row.id);assert.equal(exp.scope.witnessOnly,true);
 for(const field of ['searchesOtherCategoryCycles','acceptsIsolationModels','completeIsolationClassification','classifiesExecutionFailures','authenticatesCaptureSources'])assert.equal(exp.scope[field],false);
 assert.equal(exp.categoriesSearched,false);assert.equal(api.verifyRegisterCycleExplanationV3(row.traceText,report,exp).valid,true);
 if(exp.status==='explained'){
  assert.equal(exp.subtype,subtype(report.evidence.witness.edges.map(edge=>edge.kind)));
  assert.deepEqual(exp.witness,report.evidence.witness);assert.equal(exp.steps.length,exp.witness.edges.length);
  assert.equal(exp.sourceCoverageComplete,true);assert.equal(report.evidence.complete,true);
  for(const step of exp.steps){
   assert.deepEqual(step.dependency,exp.witness.edges[step.edgeIndex]);
   for(const side of ['from','to']){
    const point=step[side],transaction=report.normalized.history.transactions.find(tx=>tx.id===point.transaction);
    assert.equal(transaction.status,'committed');assert.deepEqual(point.operation,transaction.ops[point.projectedOperation]);
    const op=point.operation;
    const expected=report.normalized.observations.filter(event=>event.tx===point.transaction&&event.key===op.key&&event.kind===op.type&&event.version===op.version).map(event=>event.seq);
    assert.ok(expected.length);assert.deepEqual(point.matchingOriginalSeqs,expected);assert.ok(step.sourceReferenceKind.includes('no unique occurrence inferred'));
   }
  }
 }else assert.equal(exp.subtype,null);
 return{report,exp};
}

await check('frozen-candidate-inputs-fixed-upstream-source-and-runtime-labels',()=>{
 assert.equal(manifest.files.length,160);assert.equal(sdk.version(),'0.1.4');
 const pins=load(resolve(referenceRoot,'source-pins.json')),rulePath=resolve(referenceRoot,'primary-references/src/elle/txn.clj');
 assert.equal(pins.fixedCommit,'4e359e597c52938b0afebb8bc42273914d68a424');
 assert.deepEqual(bind(rulePath),pins.files['src/elle/txn.clj']);
 const text=readFileSync(rulePath,'utf8');assert.ok(text.includes('(cons (last (:steps ex)))'));assert.ok(text.includes('"G-nonadjacent-item"'));
 const build=load(resolve(candidate,'runtime/build-manifest.json'));assert.equal(bind(resolve(candidate,'runtime/core.mjs')).sha256,build.coreSha256);
 assert.ok(readFileSync(resolve(candidate,'runtime/sdk.mjs'),'utf8').startsWith(readFileSync(resolve(candidate,'runtime/generic-sdk.mjs'),'utf8')));
 assert.equal(custom.length,119);return{frozenFiles:160,customInputs:119,manualInputs:13,candidateRuntime:'0.1.4',primaryRuleSource:bind(rulePath)};
});

const reviewed=new Map();
await check('132-real-history-explanations-source-map-and-independent-cyclic-distance-rules',()=>{
 const results=[];for(const row of [...manual,...custom]){
  const result=verifyExplanation(sdk,row);assert.deepEqual(result.report,base.analyzeV3(row.traceText));reviewed.set(row.id,result);
  results.push({id:row.id,sourceStatus:result.report.status,status:result.exp.status,subtype:result.exp.subtype,
   reportSha256:hash(JSON.stringify(result.report)),explanationSha256:hash(JSON.stringify(result.exp))});
 }
 save('132-real-history-results.json',results);assert.equal(results.length,132);
 return{realHistories:132,generatedRingPatterns:117,additionalSavepointHistories:2,originalManualHistories:13};
});

await check('wraparound-adjacency-and-coexisting-unsearched-category-cycles',()=>{
 const wrap=reviewed.get('wraparound-adjacent-is-g2');assert.equal(wrap.exp.subtype,'G2-item');
 const kinds=wrap.exp.witness.edges.map(edge=>edge.kind);assert.equal(kinds[0],'rw');assert.equal(kinds.at(-1),'rw');
 assert.equal(kinds.slice(0,-1).some((kind,i)=>kind==='rw'&&kinds[i+1]==='rw'),false);
 assert.equal(wrap.exp.pattern.adjacentAntiDependenciesIncludingWraparound,true);
 const coexist=reviewed.get('shortest-ww-does-not-search-other-g2');assert.equal(coexist.exp.subtype,'G0');
 const adjacency=new Map();for(const edge of coexist.report.evidence.edges){if(!adjacency.has(edge.from))adjacency.set(edge.from,[]);adjacency.get(edge.from).push(edge);}
 const found=[];
 for(const start of adjacency.keys()){
  const visit=(at,path,seen)=>{for(const edge of adjacency.get(at)||[]){if(edge.to===start&&path.length){found.push([...path,edge]);}
   else if(!seen.has(edge.to)){const next=new Set(seen);next.add(edge.to);visit(edge.to,[...path,edge],next);}}};
  visit(start,[],new Set([start]));
 }
 assert.ok(found.some(cycle=>subtype(cycle.map(edge=>edge.kind))==='G2-item'));
 assert.equal(coexist.exp.scope.searchesOtherCategoryCycles,false);assert.equal(coexist.exp.scope.acceptsIsolationModels,false);
 save('coexisting-verified-graph-cycles.json',found.map(edges=>({edges,subtype:subtype(edges.map(edge=>edge.kind))})));
 return{wraparoundOnlyAdjacencyChecked:true,otherG2CycleIndependentlyFound:true,wholeCategoryExclusionClaimed:false};
});

await check('same-name-savepoint-reads-and-rolled-back-write-operation-mapping',()=>{
 const reads=reviewed.get('same-name-savepoints-retain-reads');assert.equal(reads.exp.subtype,'G-single-item');
 const rw=reads.exp.steps.find(step=>step.dependency.kind==='rw');assert.equal(rw.from.matchingOriginalSeqs.length,2);
 const rolled=reviewed.get('reverted-write-not-projected');assert.equal(rolled.exp.subtype,'G-single-item');
 assert.ok(rolled.report.normalized.observations.some(event=>event.kind==='write'&&event.version==='audit|discarded'));
 assert.ok(!rolled.report.normalized.history.transactions.some(tx=>tx.ops.some(op=>op.version==='audit|discarded')));
 save('savepoint-read-result.json',reads);save('savepoint-write-result.json',rolled);
 return{savepointCases:2,duplicateNameInstances:2,deliveredMatchingReads:2,revertedEffectNotProjected:true};
});

await check('isolated-current-v015-addition-preserves-old-exports-and-132-history-results',async()=>{
 const runtime=resolve(out,'integration-v015');mkdirSync(runtime);
 for(const name of ['core.mjs','capture-core.mjs','evidence.mjs','build-manifest.json'])copyFileSync(resolve(root,'dist',name),resolve(runtime,name));
 const prior=readFileSync(resolve(root,'cmd/sdk.mjs')),addition=readFileSync(resolve(candidate,'cycle-sdk-additions.mjs'));
 assert.deepEqual(prior,readFileSync(resolve(candidate,'integration-base/cmd/sdk.mjs')));
 assert.deepEqual(Buffer.concat([prior,addition]),readFileSync(resolve(candidate,'proposed/cmd/sdk.mjs')));
 writeFileSync(resolve(runtime,'sdk.mjs'),Buffer.concat([prior,addition]),{flag:'wx'});
 const integrated=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href),old=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
 assert.equal(integrated.version(),'0.1.5');assert.deepEqual(Object.keys(integrated).filter(name=>!(name in old)).sort(),['explainRegisterCycleV3','verifyRegisterCycleExplanationV3']);
 const results=[];for(const row of [...manual,...custom]){const result=verifyExplanation(integrated,row);assert.deepEqual(result.report,old.analyzeV3(row.traceText));results.push({id:row.id,status:result.exp.status,subtype:result.exp.subtype});}
 save('132-integration-v015-results.json',results);return{histories:132,integrationRuntime:'0.1.5',newV016Build:false,addedExports:2,priorExportsPreserved:Object.keys(old).length};
});

await check('coverage-unknown-model-and-budget-diagnostics-never-become-complete-classification',()=>{
 for(const id of ['unconfirmed-commit','explicit-coverage-gap','unknown-read-source']){
  const{report,exp}=reviewed.get(id);assert.equal(report.status,'inconclusive');assert.equal(exp.status,'inconclusive');assert.equal(exp.subtype,null);assert.equal(exp.sourceCoverageComplete,false);
 }
 const list=load(resolve(inputRoot,'fixtures/list-v3/manual.json')),relation=load(resolve(inputRoot,'fixtures/relation-v3/boundary.json'));
 const selected=[list.find(row=>row.id==='two-key-read-append-cycle'),list.find(row=>row.id==='zero-state-budget'),relation.find(row=>row.id==='read-zero-state-budget')];
 for(const row of selected){const report=sdk.analyzeV3(row.traceText,row.options),exp=sdk.explainRegisterCycleV3(row.traceText,report);
  assert.equal(exp.sourceStatus,report.status);assert.equal(exp.subtype,null);assert.notEqual(exp.status,'explained');assert.equal(exp.scope.acceptsIsolationModels,false);
  if(report.status==='inconclusive')assert.equal(exp.status,'inconclusive');}
 for(const raw of ['{','null',byId.get('single-item-rw').traceText.replace('{','{"traceSchema":3,')]){
  const report=sdk.analyzeV3(raw),exp=sdk.explainRegisterCycleV3(raw,report);assert.equal(exp.status,'invalid');assert.equal(exp.sourceStatus,'invalid');assert.equal(exp.subtype,null);
  assert.equal(sdk.verifyRegisterCycleExplanationV3(raw,report,exp).valid,true);
 }
 return{registerSourceGaps:3,otherModelAndBudgetCases:3,reproducibleInvalidDiagnostics:3,validDiagnosticNotCompleteModelAcceptance:true};
});

await check('derived-and-source-tampering-and-exact-text-binding-are-rejected',()=>{
 const row=byId.get('adjacent-item-rw'),{report,exp}=reviewed.get(row.id);
 const derived=[e=>e.subtype='G0',e=>e.scope.completeIsolationClassification=true,e=>e.scope.searchesOtherCategoryCycles=true,
  e=>e.steps[0].from.matchingOriginalSeqs=[0],e=>e.steps[0].to.projectedOperation=999,e=>e.steps[0].versionOrder.reverse(),
  e=>e.rules.commit='0'.repeat(40),e=>e.traceTextSha256='0'.repeat(64),e=>e.reportTextSha256='0'.repeat(64),
  e=>delete e.sourceCoverageComplete,e=>e.acceptsSnapshotIsolation=true];
 for(const mutate of derived){const changed=clone(exp);mutate(changed);assert.equal(sdk.verifyRegisterCycleExplanationV3(row.traceText,report,changed).valid,false);}
 const source=[r=>r.status='consistent',r=>r.modelDefinition.id='relation-set-serializable-v1',r=>r.evidence.witness.edges[0].kind='wr',
  r=>r.evidence.witness.edges[0].fromVersion='forged',r=>r.normalized.observations[0].consistent=false,r=>r.execution.analysisOptions.maxAttempts=0,
  r=>r.evidence.complete=false,r=>r.evidence.versionOrderSources[r.evidence.witness.edges[0].key]='searched'];
 for(const mutate of source){const changed=clone(report);mutate(changed);const got=sdk.explainRegisterCycleV3(row.traceText,changed);assert.equal(got.verifiedReport,false);assert.equal(got.status,'invalid');assert.equal(got.subtype,null);assert.equal(sdk.verifyRegisterCycleExplanationV3(row.traceText,changed,got).valid,false);}
 for(const raw of ['{',JSON.stringify(report).replace('{','{"status":"violation",')])assert.equal(sdk.explainRegisterCycleV3(row.traceText,raw).verifiedReport,false);
 assert.equal(sdk.verifyV3('\n'+row.traceText,report).valid,true);assert.equal(sdk.verifyRegisterCycleExplanationV3('\n'+row.traceText,report,exp).valid,false);
 const beforeReport=clone(report),beforeTrace=JSON.parse(row.traceText),beforeObject=clone(beforeTrace);sdk.explainRegisterCycleV3(beforeTrace,report);assert.deepEqual(report,beforeReport);assert.deepEqual(beforeTrace,beforeObject);
 return{derivedMutations:11,sourceMutations:8,duplicateOrMalformedReports:2,exactTraceBytesBound:true,inputsNotMutated:true};
});

await check('existing-v3-capsule-format-and-size-argument-boundaries-preserved',()=>{
 const row=byId.get('single-item-rw'),{report,exp}=reviewed.get(row.id),raw=sdk.makeCapsuleV3(row.traceText,report);
 assert.equal(raw,base.makeCapsuleV3(row.traceText,report));assert.equal(sdk.replayCapsuleV3(raw).valid,true);
 const capsule=JSON.parse(raw);assert.equal(sdk.verifyRegisterCycleExplanationV3(capsule.traceText,capsule.reportText,exp).valid,true);
 assert.throws(()=>sdk.explainRegisterCycleV3(' '.repeat(8*1024*1024+1),report),RangeError);
 assert.throws(()=>sdk.explainRegisterCycleV3(row.traceText,' '.repeat(32*1024*1024+1)),RangeError);
 assert.throws(()=>sdk.verifyRegisterCycleExplanationV3(row.traceText,report,{text:'a'.repeat(8*1024*1024)}),RangeError);
 assert.throws(()=>sdk.verifyRegisterCycleExplanationV3(row.traceText,report,'{}'),TypeError);
 assert.throws(()=>sdk.explainRegisterCycleV3(row.traceText),TypeError);
 save('unchanged-v3-capsule.json',capsule);return{originalCapsuleFormatUnchanged:true,byteBoundaries:3,argumentRejections:2};
});

await check('actual-old-deadlock-and-fixed-stored-elle-results-are-not-renamed-or-rerun',()=>{
 const deadlock=readFileSync(resolve(inputRoot,'verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c/before/capture.json'),'utf8');
 const report=sdk.analyzeV3(deadlock),exp=sdk.explainRegisterCycleV3(deadlock,report),failures=sdk.inspectExecutionFailuresV3(deadlock);
 assert.ok(JSON.stringify(failures).includes('40P01'));assert.equal(exp.subtype,null);assert.notEqual(exp.status,'explained');assert.equal(exp.scope.classifiesExecutionFailures,false);
 const originals=load(resolve(referenceRoot,'smoke-inputs-v1.json')).cases.filter(row=>row.expected.adapter==='eligible');
 const stored=load(resolve(referenceRoot,'actual-ci-39599513353/actual/elle-result.json'));assert.equal(stored.passed,true);assert.equal(stored.cases.length,8);
 const result=[];for(const row of originals){const old=stored.cases.find(value=>value.id===row.id),current=sdk.analyzeV3(row.input),derived=sdk.explainRegisterCycleV3(row.input,current);
  assert.equal(current.status,row.expected.toolStatus);assert.equal(old.valid,row.expected.elleValid);
  if(row.input.dataModel==='point-register-v1'&&old.valid===false){assert.ok(old.anomalyTypes.includes(derived.subtype));assert.equal(derived.status,'explained');}
  else assert.equal(derived.subtype,null);
  result.push({id:row.id,storedElleValid:old.valid,storedAnomalyTypes:old.anomalyTypes,currentStatus:current.status,derivedSubtype:derived.subtype,newElleExecution:false});}
 assert.equal(result.filter(row=>row.storedElleValid==='unknown').length,2);assert.equal(result.filter(row=>row.derivedSubtype!==null).length,2);
 save('old-actual-40P01-diagnostic.json',{sourceStatus:report.status,explanation:exp,failures});save('stored-eight-elle-inputs-reviewed.json',result);
 return{actualHistoricalDeadlockReviewed:true,storedElleInputs:8,matchingRegisterWitnessTypes:2,retainedEmptyGraphUnknowns:2,newElleExecution:false};
});

await check('author43-regressions-invoked-independently-with-frozen-closed-inputs',()=>{
 const p=spawnSync(process.execPath,[resolve(candidate,'check_candidate.mjs'),'--output-root',out],{cwd:root,encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:2*1024*1024});
 save('author-process.json',{exitCode:p.status,stdout:redact(p.stdout||''),stderr:redact(p.stderr||''),error:p.error?.name||null});assert.equal(p.error,undefined);assert.equal(p.status,0,p.stderr||p.stdout);
 const summary=JSON.parse(p.stdout),author=load(resolve(root,summary.receipt));assert.equal(author.passed,true);assert.equal(author.checks.length,43);assert.equal(author.handwrittenCases,13);
 return{checks:43,receipt:summary.receipt,newElleExecution:false,authorTestsIndependentlyInvokedNotIndependentOracle:true};
});

const candidateAfter=Object.fromEntries(manifest.files.map(row=>[row.file,bind(resolve(candidate,row.file))]));
const mainlineAfter=Object.fromEntries(rootFiles.map(name=>[name,bind(resolve(root,name))]));
receipt.candidateUnchanged=JSON.stringify(candidateBefore)===JSON.stringify(candidateAfter);
receipt.mainlineUnchanged=JSON.stringify(mainlineBefore)===JSON.stringify(mainlineAfter);
receipt.inputUnchanged=bind(customFile).sha256===customManifest.sha256;
receipt.manifestUnchanged=bind(manifestPath).sha256===expectedManifest;
receipt.passed=receipt.checks.every(row=>row.passed)&&receipt.candidateUnchanged&&receipt.mainlineUnchanged&&receipt.inputUnchanged&&receipt.manifestUnchanged;
receipt.manifest={sha256:expectedManifest,files:160};receipt.candidateBindings=candidateBefore;receipt.mainlineBindings=mainlineBefore;
receipt.implementation=bind(fileURLToPath(import.meta.url));receipt.frozenIndependentInputs=bind(customFile);
save('receipt.json',receipt);console.log(JSON.stringify({passed:receipt.passed,groups:receipt.checks.length,failed:receipt.checks.filter(row=>!row.passed),receipt:posix(resolve(out,'receipt.json'))}));if(!receipt.passed)process.exitCode=1;
