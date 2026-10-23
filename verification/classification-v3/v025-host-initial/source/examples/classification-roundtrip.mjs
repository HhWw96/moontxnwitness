// Offline synthetic category witness, source-closed reduction and exact replay.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {version,classifyV3,reduceClassificationV3,verifyClassificationV3,makeClassificationCapsuleV3,makeClassificationReductionCapsuleV3,replayClassificationCapsuleV3} from '../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),index=process.argv.indexOf('--out-root');
const base=resolve(index>=0?process.argv[index+1]:resolve(root,'artifacts/classification-example'));mkdirSync(base,{recursive:true});
const output=resolve(base,'classification-'+randomUUID());mkdirSync(output);
const source=readFileSync(resolve(root,'fixtures/classification-v3/source-closed-noisy-g2.json'),'utf8'),files=[];
const classification=classifyV3(source,{categories:['G2-item']}),reduction=reduceClassificationV3(source,{category:'G2-item'});
assert.equal(classification.result.rules['G2-item'].status,'refuted');assert.equal(classification.scope.isolationModelsAccepted,false);
assert.equal(reduction.sourceClosure.complete,true);assert.equal(reduction.result.oneMinimal,true);
assert.deepEqual(new Set(reduction.result.removed),new Set(['N']));assert.equal(verifyClassificationV3(source,reduction).valid,true);
for(const[name,raw]of [['classification.report.json',JSON.stringify(classification,null,2)+'\n'],
  ['reduction.report.json',JSON.stringify(reduction,null,2)+'\n'],
  ['classification.capsule.json',makeClassificationCapsuleV3(source,{categories:['G2-item']})],
  ['reduction.capsule.json',makeClassificationReductionCapsuleV3(source,{category:'G2-item'})]]){
  if(name.endsWith('.capsule.json'))assert.equal(replayClassificationCapsuleV3(raw).valid,true);
  writeFileSync(resolve(output,name),raw,{flag:'wx'});files.push({file:name,bytes:Buffer.byteLength(raw),sha256:createHash('sha256').update(raw).digest('hex')});
}
console.log(JSON.stringify({passed:true,version:version(),syntheticInputs:true,actualDatabaseExecution:false,formalPerformanceMeasured:false,
  originalTransactions:4,reducedTransactions:3,preservedCategory:'G2-item',sourceClosureComplete:true,oneMinimal:true,
  fixedCandidateChecks:reduction.result.checks,maxCandidateChecks:reduction.result.maxChecks,
  outputDirectory:relative(base,output).replaceAll('\\','/'),files}));
