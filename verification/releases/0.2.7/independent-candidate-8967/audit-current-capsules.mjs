// Offline installed-package replay. Only the candidate's extracted SDK is imported.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,relative,sep,isAbsolute} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {freemem} from 'node:os';
const [packageArg,outputArg,...extra]=process.argv.slice(2);assert(packageArg&&outputArg&&!extra.length);
const root=realpathSync(resolve(packageArg)),output=resolve(outputArg);assert(!output.startsWith(root+sep));mkdirSync(output);
const sha=x=>createHash('sha256').update(x).digest('hex'),pretty=x=>JSON.stringify(x,null,2)+'\n',records=[],checks=[];
function save(name,value){writeFileSync(resolve(output,name),pretty(value),{flag:'wx'});}
function bound(name,record){
 assert(!isAbsolute(name)&&!name.split('/').includes('..')&&!name.includes('\\'));
 const path=resolve(root,name),r=relative(root,realpathSync(path));assert(r&&!r.startsWith('..'+sep)&&r!=='..'&&!isAbsolute(r));assert(lstatSync(path).isFile()&&!lstatSync(path).isSymbolicLink());
 const raw=readFileSync(path);assert.equal(raw.length,record.bytes);assert.equal(sha(raw),record.sha256);records.push({file:name,...record});return raw.toString('utf8');
}
let calls=0,version,fatal=null,sourceHash;
try{
 assert(process.execArgv.includes('--max-old-space-size=384'));assert.equal(process.env.NODE_OPTIONS??'','');assert.equal(process.env.NODE_PATH??'','');
 const resources={availablePhysicalBytes:freemem(),minimumPhysicalBytes:1073741824,nodeHeapMiB:384};save('resources.json',resources);assert(resources.availablePhysicalBytes>=resources.minimumPhysicalBytes,'RAM below fixed1GiB; SDK not imported');
 const aggregatePath='verification/releases/0.2.7/current-pg-sdk-loop/aggregate.json';const raw=readFileSync(resolve(root,aggregatePath));sourceHash=sha(raw);assert.equal(sourceHash,'76ae109bba4ef250789f80c587dd35df951a82d5b4da4701c9c2a1cca3406e14');
 const aggregate=JSON.parse(raw);assert.equal(aggregate.passed,true);assert.equal(aggregate.uniqueCompletedCases,10);assert.equal(aggregate.supportedMappings,7);assert.equal(aggregate.expectedInconclusiveGuards,3);assert.equal(aggregate.sourceClosedReductionClaimed,false);
 for(const [label,subdir]of [['first','first/first-run/results/'],['continuation','continuation/continuation-first/results/']]){
  const prefix='verification/releases/0.2.7/current-pg-sdk-loop/'+subdir;
  const original=JSON.parse(bound(prefix+'receipt.json',aggregate.executionHistory[label].sdkReceipt));
  for(const record of original.files)bound(prefix+record.file,{bytes:record.bytes,sha256:record.sha256});
 }
 const manifest=JSON.parse(readFileSync(resolve(root,'dist/build-manifest.json'),'utf8'));assert.deepEqual(manifest,aggregate.currentBuildManifest);
 const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
 const call=(name,...args)=>{calls++;return sdk[name](...args);};version=call('version');assert.equal(version,'0.2.7');
 let refusals=0;
 for(const row of aggregate.cases){
  const folder='verification/releases/0.2.7/current-pg-sdk-loop/'+(row.completedIn==='first101'?'first/first-run/results/':'continuation/continuation-first/results/')+row.case+'/';
  const envelope=bound(folder+'source.original.json',row.source),reportText=bound(folder+'report.json',row.report),capsule=bound(folder+'capsule.json',row.capsule),report=JSON.parse(reportText);
  assert.equal(report.engine.version,version);assert.equal(report.scope.sourceClosedReductionAvailable,false);
  const normalization=call('normalizeCaptureV3',JSON.parse(envelope).traceText);save(row.case+'-normalization.json',normalization);assert.equal(normalization.coverage.complete,false);
  const verified=call('verifyModelProfileV3',envelope,reportText);save(row.case+'-verify.json',verified);assert.equal(verified.valid,true);assert.equal(verified.analysisCoverageAccepted,row.mappingAccepted);
  const replay=call('replayModelProfileCapsuleV3',capsule);save(row.case+'-replay.json',replay);assert.equal(replay.valid,true);assert.equal(replay.status,row.finalStatus);assert.equal(replay.envelopeText,envelope);assert.deepEqual(replay.report,report);
  assert.equal(report.result.originalDiagnosticCoverage!==null,row.profileOriginalDiagnosticCoveragePresent);
  let perCase=0;
  for(const file of readdirSync(resolve(root,folder)).sort()){
   if(!/^tampered-(report|capsule)-.*\.json$/.test(file)||/\.(verification|replay)\.json$/.test(file))continue;
   const text=readFileSync(resolve(root,folder,file),'utf8'),kind=file.startsWith('tampered-report-')?'report':'capsule';
   const recordedName=file.replace(/\.json$/,kind==='report'?'.verification.json':'.replay.json'),recorded=JSON.parse(readFileSync(resolve(root,folder,recordedName),'utf8'));
   const actual=kind==='report'?call('verifyModelProfileV3',envelope,JSON.parse(text)):call('replayModelProfileCapsuleV3',text);save(row.case+'-'+recordedName,actual);assert.equal(actual.valid,false);assert.deepEqual(actual,recorded);perCase++;refusals++;
  }
  assert.equal(perCase,7);checks.push({case:row.case,passed:true,status:replay.status,mappingAccepted:replay.analysisCoverageAccepted,genericGapsPreserved:true,earlyNullProfileCoveragePreserved:true,tamperRefusals:perCase});
 }
 assert.equal(refusals,70);assert.equal(calls,101);
}catch(error){fatal=String(error.stack??error);}
const receipt={format:'prepublication-installed-current-pg-model-capsule-audit/v1',passed:fatal===null&&checks.length===10,version,sdkTopLevelCalls:calls,cases:checks,aggregateSha256:sourceHash,allOriginalEvidenceReadOnly:true,sourceClosedReductionClaimed:false,newSQL:false,newHTTP:false,newService:false,compilerExecuted:false,publicDownloadVerification:false,prepublicationCandidateOnly:true,fatal,originalBindings:records};
save('receipt.json',receipt);console.log(JSON.stringify({...receipt,originalBindings:undefined,cases:checks.map(x=>({case:x.case,passed:x.passed,status:x.status}))}));if(!receipt.passed)process.exitCode=1;
