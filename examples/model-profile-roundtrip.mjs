// Offline full original-source replay. Never opens or changes a database.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {version,analyzeModelProfileV3,verifyModelProfileV3,makeModelProfileCapsuleV3,replayModelProfileCapsuleV3} from '../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const index=process.argv.indexOf('--out-root');
const base=resolve(index>=0?process.argv[index+1]:resolve(root,'artifacts/model-profile-example'));
mkdirSync(base,{recursive:true});const output=resolve(base,'model-profile-'+randomUUID());mkdirSync(output);
const sha=raw=>createHash('sha256').update(raw).digest('hex'),files=[];
for(const[name,status,accepted]of [['list-write-skew','violation',true],['relation-write-skew','violation',true],['relation-crud','consistent',true],['relation-zero-write','inconclusive',false]]){
  const text=readFileSync(resolve(root,'verification/model-profile-v3/v027-initial/database',name,'profile-source.json'),'utf8');
  const report=analyzeModelProfileV3(text);assert.equal(report.status,status);assert.equal(report.analysisCoverageAccepted,accepted);
  assert.equal(verifyModelProfileV3(text,report).valid,true);
  const capsule=makeModelProfileCapsuleV3(text),replay=replayModelProfileCapsuleV3(capsule);
  assert.equal(replay.valid,true);assert.equal(replay.envelopeText,text);assert.equal(replay.status,status);
  if(accepted)assert.equal(report.result.originalDiagnosticCoverage.complete,false);
  for(const[file,raw]of [[name+'.report.json',JSON.stringify(report,null,2)+'\n'],[name+'.capsule.json',capsule]]){
    writeFileSync(resolve(output,file),raw,{flag:'wx'});files.push({file,bytes:Buffer.byteLength(raw),sha256:sha(raw)});
  }
}
console.log(JSON.stringify({passed:true,version:version(),cases:4,actualDatabaseExecution:false,
  originalInputsFromRetainedDatabaseRun:true,originalDiagnosticsRemainPartial:true,fullOriginalSourcesRetained:true,
  sourceClosedReductionClaimed:false,outputDirectory:relative(base,output).replaceAll('\\','/'),files}));
