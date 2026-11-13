import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const [distName,matrixName,outName,...extra]=process.argv.slice(2);
assert(distName&&matrixName&&outName&&!extra.length,'Usage: relation-model-reduction-matrix-v4.mjs DIST MODEL_CASES.json NEW_OUTPUT');
const dist=resolve(distName),out=resolve(outName),matrixPath=resolve(matrixName),raw=readFileSync(matrixPath),matrix=JSON.parse(raw);
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
assert.equal(matrix.format,'moontxnwitness-relation-fourteen-model-matrix/v1');
assert.equal(matrix.models.length,14);assert.equal(new Set(matrix.models).size,14);
const bindings=()=>Object.fromEntries(['core.mjs','relation-models-reduction-v4.mjs'].map(name=>[name,hash(readFileSync(resolve(dist,name)))]));
const before=bindings();
const {reduceRelationModelsV4:reduce,verifyRelationModelReductionV4:verify,
 makeRelationModelReductionCapsuleV4:make,replayRelationModelReductionCapsuleV4:replay}=await import(pathToFileURL(resolve(dist,'relation-models-reduction-v4.mjs')));
mkdirSync(out);mkdirSync(resolve(out,'reports'));mkdirSync(resolve(out,'capsules'));
copyFileSync(matrixPath,resolve(out,'original-model-cases.json'));
const cases=[],results=[],failures=[];
for(const model of matrix.models){
 const fixture=matrix.cases.find(row=>row.id===model+'/refuted');assert(fixture&&fixture.expected==='refuted');
 const source=structuredClone(fixture.source),noise='matrix-unrelated-transaction';
 assert(!source.events.some(event=>event.tx===noise));
 source.events.splice(1,0,{kind:'begin',tx:noise,connection:'synthetic-noise-connection'},
   {kind:'commit_request',tx:noise},{kind:'commit_ok',tx:noise});
 // These are generated test fixtures, never rewritten collection records.
 source.events.forEach((event,index)=>{event.seq=index+1;event.time=index;});
 const modelOptions={...fixture.options,clients:[...(fixture.options.clients??[]),{id:'explicit-synthetic-noise-client',transactions:[noise]}]};
 const options={model,modelOptions,maxChecks:256};
 const item={id:model,family:fixture.family,source,options,expected:'refuted-with-noise-removed'};cases.push(item);
 try{
   const report=reduce(source,options);
   assert.equal(report.classification.status,'refuted');assert.equal(report.preserveModel,model);
   assert.deepEqual(report.removedTransactions,[noise]);
   assert.equal(report.selectedTransactions.length,source.events.filter(event=>event.kind==='begin').length-1);
   assert.deepEqual(report.originalFacts.history,source);
   assert.equal(verify(source,report,options).valid,true);
   const other=matrix.models.find(name=>name!==model);
   assert.equal(verify(source,report,{...options,model:other}).valid,false);
   const capsule=make(source,options);assert.equal(replay(capsule,options).valid,true);
   assert.equal(replay(capsule,{...options,maxChecks:0}).valid,false);
   const reportText=JSON.stringify(report),capsuleName=model+'.json';
   writeFileSync(resolve(out,'reports',capsuleName),reportText+'\n',{flag:'wx'});
   writeFileSync(resolve(out,'capsules',capsuleName),capsule,{flag:'wx'});
   results.push({model,family:fixture.family,passed:true,preserveModel:report.preserveModel,
     status:report.status,oneMinimal:report.oneMinimal,transactionsBefore:report.selectedTransactions.length+1,
     transactionsAfter:report.selectedTransactions.length,reportSha256:hash(reportText),capsuleSha256:hash(capsule)});
 }catch(error){const failure={model,passed:false,error:error.stack};failures.push(failure);results.push(failure);}
}
assert.deepEqual(bindings(),before,'Actual runtime changed during model-preserving reduction');
assert.equal(hash(readFileSync(matrixPath)),hash(raw),'Original definition cases changed');
const caseText=JSON.stringify(cases,null,2)+'\n';writeFileSync(resolve(out,'generated-noise-cases.json'),caseText,{flag:'wx'});
const summary={format:'moontxnwitness-relation-model-reduction-matrix/v1',passed:!failures.length,models:14,
  publicApiExecution:true,publicPackageVerified:false,formalPerformanceMeasurement:false,
  scope:'Fourteen predeclared model counterexamples with one synthetic unrelated transaction; a source-open final deletion remains explicitly non-minimal.',
  runtime:before,originalCasesSha256:hash(raw),generatedCasesSha256:hash(caseText),
  driverSha256:hash(readFileSync(new URL(import.meta.url))),results,failures};
writeFileSync(resolve(out,'summary.json'),JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:summary.passed,models:summary.models,noiseRemoved:results.filter(row=>row.passed).length,failures}));
if(!summary.passed)process.exitCode=1;
