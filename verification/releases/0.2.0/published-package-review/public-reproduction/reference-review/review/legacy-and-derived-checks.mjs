import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {resolve} from 'node:path';import {createHash} from 'node:crypto';import {projectMetadata} from './metadata-projection.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex'),load=p=>JSON.parse(readFileSync(p)),clone=x=>structuredClone(x),bind=p=>{const b=readFileSync(p);return{bytes:b.length,sha256:hash(b)};};
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



export async function runLegacyAndDerived({here,sdk,evidence,baseline17,baselineEvidence17,check,retain}){
 const originalHere=here;here=resolve(here,'inputs/v016');const inputRoot=resolve(here,'source-inputs'),manual=load(resolve(here,'handwritten-inputs.json')),custom=load(resolve(here,'independent-inputs.json')),byId=new Map(manual.map(row=>[row.id,row])),reviewed=new Map(),base=sdk,old=baseline17,priorEvidence=baselineEvidence17,save=retain;
 assert.equal(manual.length,13);assert.equal(custom.length,119);const frozen=load(resolve(here,'independent-input-manifest.json'));assert.deepEqual(bind(resolve(here,'independent-inputs.json')),{bytes:frozen.bytes,sha256:frozen.sha256});
 await check('132-original16-derived-expectations-preserve-native17-vs20-full-register-report',()=>{const results=[];for(const row of [...manual,...custom]){const result=verifyExplanation(sdk,row),prior=verifyExplanation(baseline17,row);assert.equal(result.report.version,'0.2.0');assert.equal(prior.report.version,'0.1.7');const currentText=JSON.stringify(result.report),priorText=JSON.stringify(prior.report);assert.equal(projectMetadata(currentText,'0.2.0','v3-register').projectedText,projectMetadata(priorText,'0.1.7','v3-register').projectedText);reviewed.set(row.id,result);results.push({id:row.id,inputSha256:row.inputSha256,sourceStatus:result.report.status,subtype:result.exp.subtype,reportSha256:hash(currentText),priorReportSha256:hash(priorText)});}assert.equal(results.length,132);save('derived132-results.json',results);return{histories:132,frozenExpectationsUnchanged:true,noOtherCycleSearch:true,noIsolationModelAcceptance:true};});
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

await check('287-stored-old-v2-list-relation-capsules-replay-on-actual-v020',()=>{
 const manifest=load(resolve(here,'legacy-capsules-manifest.json')),results=[];
 assert.deepEqual(manifest.families,{'register-v2':3,'capture-v2':4,'append-list-v3':120,'relation-v3':160});
 for(const row of manifest.capsules){
  const file=resolve(here,row.file.replace(/^inputs\//,''));assert.deepEqual(bind(file),{bytes:row.bytes,sha256:row.sha256});
  const raw=readFileSync(file,'utf8'),capsule=JSON.parse(raw);
  const actual=row.schemaVersion===3?sdk.replayCapsuleV3(raw):evidence.replayCapsule(raw);
  const prior=row.schemaVersion===3?old.replayCapsuleV3(raw):priorEvidence.replayCapsule(raw);
  assert.equal(actual.valid,true,row.file);assert.equal(prior.valid,true,row.file);
  const actualBody=clone(actual),priorBody=clone(prior);
  if(row.schemaVersion===2){assert.equal(actual.currentEngine,'0.2.0');assert.equal(prior.currentEngine,'0.1.7');assert.equal(actual.recordedEngine,row.engineVersion);assert.equal(prior.recordedEngine,row.engineVersion);delete actualBody.currentEngine;delete priorBody.currentEngine;}
  assert.deepEqual(actualBody,priorBody,'Complete replay result except the explicitly advanced currentEngine header must match frozen v0.1.7: '+row.file);
  if(row.schemaVersion===3){assert.equal(actual.status,row.expectedStatus);
   const fixed=row.family==='append-list-v3'?sdk.replayListCapsuleV3(raw):sdk.replayRelationCapsuleV3(raw);assert.equal(fixed.valid,true,row.file);
   const exp=sdk.explainRegisterCycleV3(capsule.traceText,capsule.reportText);assert.equal(exp.subtype,null);assert.notEqual(exp.status,'explained');assert.equal(exp.scope.acceptsIsolationModels,false);
  }
  results.push({family:row.family,inputSha256:row.sha256,engineVersion:row.engineVersion,storedStatus:row.expectedStatus,valid:true,resultSha256:hash(JSON.stringify(actual))});
 }
 assert.equal(results.length,287);save('old-capsule-replay-results.json',results);
 return {storedCapsules:287,v2RegisterAndCapture:7,listV3:120,relationV3:160,sourceDatabaseReexecuted:false,relationCapsulesDerivedFromPreservedRealSql:true};
});

 await check('old-MLflow-deadlock-derived-scope-remains-inconclusive-and-never-G2',()=>{const trace=readFileSync(resolve(originalHere,'inputs/mlflow/before/capture.json'),'utf8'),report=sdk.analyzeV3(trace),exp=sdk.explainRegisterCycleV3(trace,report);assert.equal(report.status,'inconclusive');assert.equal(report.evidence,null);assert.equal(exp.subtype,null);assert.notEqual(exp.status,'explained');assert.equal(exp.scope.classifiesExecutionFailures,false);save('old-deadlock-derived.json',exp);});
}
