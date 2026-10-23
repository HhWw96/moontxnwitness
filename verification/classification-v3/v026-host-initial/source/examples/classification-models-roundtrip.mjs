// Offline synthetic model comparison, explicit call source and full-source replay.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {version,classifyModelsV3,verifyModelsClassificationV3,makeModelsClassificationCapsuleV3,replayModelsClassificationCapsuleV3} from '../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),index=process.argv.indexOf('--out-root');
const base=resolve(index>=0?process.argv[index+1]:resolve(root,'artifacts/classification-models-example'));mkdirSync(base,{recursive:true});
const output=resolve(base,'models-'+randomUUID());mkdirSync(output);
const load=name=>readFileSync(resolve(root,'fixtures/classification-models-v3',name+'.json'),'utf8'),files=[];
const skew=classifyModelsV3(load('list-skew')),empty=classifyModelsV3(load('empty-register')),bound=classifyModelsV3(load('strict-bound-synthetic'));
assert.equal(skew.result.models['elle-generalized-si-v1'].status,'checked-compatible');assert.equal(skew.result.models['adya-pl-3-v1'].status,'refuted');
assert.equal(empty.result.models['strict-pl-ss-v1'].status,'inconclusive');assert.equal(bound.result.models['strict-pl-ss-v1'].status,'checked-compatible');
for(const name of ['list-skew','empty-register','strict-bound-synthetic']){
  const text=load(name),r=classifyModelsV3(text),capsule=makeModelsClassificationCapsuleV3(text);
  assert.equal(verifyModelsClassificationV3(text,r).valid,true);assert.equal(replayModelsClassificationCapsuleV3(capsule).valid,true);
  const prefix=name==='strict-bound-synthetic'?'bound-synthetic':name;
  for(const[file,raw]of [[prefix+'.report.json',JSON.stringify(r,null,2)+'\n'],[prefix+'.capsule.json',capsule]]){
    writeFileSync(resolve(output,file),raw,{flag:'wx'});files.push({file,bytes:Buffer.byteLength(raw),sha256:createHash('sha256').update(raw).digest('hex')});
  }
}
console.log(JSON.stringify({passed:true,version:version(),syntheticInputs:true,actualDatabaseExecution:false,formalPerformanceMeasured:false,
  relationModelClassificationSupported:false,modelPreservingReductionSupported:false,generalizedSI:skew.result.models['elle-generalized-si-v1'].status,
  serial:skew.result.models['adya-pl-3-v1'].status,strictWithoutIntervals:empty.result.models['strict-pl-ss-v1'].status,
  strictBoundSynthetic:bound.result.models['strict-pl-ss-v1'].status,outputDirectory:relative(base,output).replaceAll('\\','/'),files}));
