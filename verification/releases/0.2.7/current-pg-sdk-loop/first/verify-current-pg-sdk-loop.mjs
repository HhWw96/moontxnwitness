// Exact current CI packets, offline SDK only. Never starts DB, network or children.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,relative,sep,isAbsolute} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {freemem} from 'node:os';
const VERSION='0.2.7',MIN_RAM=1024*1024*1024;
const canonical=x=>JSON.stringify(x,null,2)+'\n',sha=x=>createHash('sha256').update(x).digest('hex');
const exactBinding=bytes=>({bytes:bytes.length,sha256:sha(bytes)});
function argumentsOf(args){
  assert.equal(args.length,10,'Use --plan PLAN --plan-sha256 SHA --runtime ACTUAL_RUNTIME --inputs ORIGINAL_PG_ROOT --output NEW_OUTPUT');
  const value={};for(let i=0;i<args.length;i+=2){assert(['--plan','--plan-sha256','--runtime','--inputs','--output'].includes(args[i]));assert(!Object.hasOwn(value,args[i]));value[args[i]]=args[i+1];}
  assert.equal(Object.keys(value).length,5);return value;
}
const args=argumentsOf(process.argv.slice(2)),output=resolve(args['--output']);mkdirSync(output,{recursive:false});
const files=[];let calls=0,sdkImported=false,plan,inputs,runtime;const cases=[],checks=[],startedAt=new Date().toISOString();
function save(name,value,raw=false){
  assert(!isAbsolute(name)&&!name.split('/').includes('..')&&!name.includes('\\'));
  const data=raw?value:canonical(value);writeFileSync(resolve(output,name),data,{flag:'wx'});
  files.push({file:name,...exactBinding(Buffer.isBuffer(data)?data:Buffer.from(data,'utf8'))});return value;
}
function readExact(root,name,expected){
  assert(!isAbsolute(name)&&!name.split('/').includes('..')&&!name.includes('\\')&&!name.includes(':'));
  const p=resolve(root,name),r=relative(root,p);assert(r&&!r.startsWith('..'+sep)&&r!=='..'&&!isAbsolute(r));
  assert(lstatSync(p).isFile()&&!lstatSync(p).isSymbolicLink(),'Regular original file required');
  assert.equal(realpathSync(p).toLowerCase(),p.toLowerCase(),'Symlink/junction path refused');
  const raw=readFileSync(p);assert.deepEqual(exactBinding(raw),expected,'Original bytes differ: '+name);return raw;
}
function listFiles(root){
  const out=[];function visit(path,prefix=''){
    for(const e of readdirSync(path,{withFileTypes:true})){
      const p=resolve(path,e.name),name=prefix+e.name;assert(!lstatSync(p).isSymbolicLink(),'No linked input/runtime files');
      if(e.isDirectory())visit(p,name+'/');else {assert(e.isFile());out.push(name);}
    }
  }visit(root);return out.sort();
}
function checkTree(root,rows){
  assert.equal(realpathSync(root).toLowerCase(),resolve(root).toLowerCase());
  assert.deepEqual(listFiles(root),rows.map(x=>x.file).sort(),'Exact original closure differs');
  for(const row of rows)readExact(root,row.file,{bytes:row.bytes,sha256:row.sha256});
}
function test(name,action){
  try{action();checks.push({name,passed:true});return true;}catch(error){checks.push({name,passed:false,error:String(error.message)});return false;}
}
function call(sdk,name,...values){calls++;return sdk[name](...values);}
function inverseStatus(status){return status==='consistent'?'violation':'consistent';}
function resign(capsule){
  capsule.requestOptionsSha256=sha(capsule.requestOptionsText);capsule.reportSha256=sha(capsule.reportText);
  const source=JSON.parse(capsule.envelopeText);capsule.sourceBindings.envelopeSha256=sha(capsule.envelopeText);
  for(const name of ['trace','sourceJournal','lifecycle','journalIndex'])capsule.sourceBindings[name+'Sha256']=sha(source[name+'Text']);
  return canonical(capsule);
}
function scopes(report){
  assert.equal(report.scope.actualDatabaseExecution,false);
  assert.equal(report.scope.sourceClosedReductionAvailable,false);
  assert.equal(report.scope.originalDiagnosticsRemainPartial,true);
}
let fatal=null,resourceRefused=false,inputsAfter=false,runtimeAfter=false;
try{
  assert.equal(process.env.NODE_OPTIONS??'','');assert.equal(process.env.NODE_PATH??'','');
  assert(process.execArgv.includes('--max-old-space-size=384'),'Use the fixed384MiB Node heap');
  const rawPlan=readFileSync(resolve(args['--plan']));assert.equal(sha(rawPlan),args['--plan-sha256'],'Externally pinned plan differs');
  plan=JSON.parse(rawPlan);assert.equal(plan.format,'moontxnwitness-current027-pg-sdk-loop-plan/v1');
  assert.equal(plan.version,VERSION);assert.equal(plan.sourceCommit,'32ca42abc7a770767d755c313fc7739d4d5ec9f5');assert.equal(plan.ciRun,40095757205);
  assert.equal(plan.inputs.length,10);assert.equal(plan.inputFiles.length,127);assert.equal(plan.runtimeFiles.length,102);
  assert.equal(plan.inputs.filter(x=>x.expectedProjection==='supported').length,7);assert.equal(plan.inputs.filter(x=>x.expectedProjection==='inconclusive').length,3);
  assert.deepEqual(plan.requestOptions,{});inputs=resolve(args['--inputs']);runtime=resolve(args['--runtime']);
  for(const root of [inputs,runtime]){const r=relative(root,output);assert(r.startsWith('..'+sep)||r==='..'||isAbsolute(r),'Output must be outside read-only originals/runtime');}
  checkTree(inputs,plan.inputFiles);checkTree(runtime,plan.runtimeFiles);
  save('plan.original.json',rawPlan,true);
  const databaseRaw=readExact(inputs,plan.databaseReceipt.file,plan.databaseReceipt.binding),projectionRaw=readExact(inputs,plan.projectionReceipt.file,plan.projectionReceipt.binding);
  save('database-receipt.original.json',databaseRaw,true);save('ci-projection-receipt.original.json',projectionRaw,true);
  const database=JSON.parse(databaseRaw),projection=JSON.parse(projectionRaw);assert(database.sourceUnchanged);assert.deepEqual(database.sourceBefore,database.sourceAfter);
  assert.equal(projection.passed,true);assert.equal(projection.sourceDatabaseReceiptSha256,sha(databaseRaw));
  assert.deepEqual(projection.build,plan.buildManifest);
  const resources={format:'current027-pg-sdk-loop-resource-check/v1',availablePhysicalBytes:freemem(),minimumPhysicalBytes:MIN_RAM,nodeHeapMiB:384,node:process.version,checkedBeforeSdkImport:true};
  resources.passed=resources.availablePhysicalBytes>=MIN_RAM;save('resources-before-sdk.json',resources);
  if(!resources.passed){resourceRefused=true;throw new Error('RESOURCE_REFUSED: available RAM below fixed1GiB; zero SDK import/calls');}
  const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);sdkImported=true;assert.equal(call(sdk,'version'),VERSION);
  for(const entry of plan.inputs){
    const item={case:entry.case,passed:false,sdkTopLevelCallsBefore:calls,expectedProjection:entry.expectedProjection,expectedSerialStatus:entry.expectedSerialStatus};cases.push(item);
    const directory=entry.case;mkdirSync(resolve(output,directory));
    try{
      const originalRecord=database.cases.find(x=>x.case===entry.case);assert(originalRecord);assert.equal(originalRecord.expectedProjection,entry.expectedProjection);assert.equal(originalRecord.expectedSerialStatus??null,entry.expectedSerialStatus);
      const previous=projection.cases.find(x=>x.case===entry.case);assert.equal(previous.passed,true);
      const raw=readExact(inputs,entry.file,entry.binding),text=raw.toString('utf8');assert.deepEqual(Buffer.from(text,'utf8'),raw);
      const envelope=JSON.parse(text);save(directory+'/source.original.json',raw,true);
      const normalization=call(sdk,'normalizeCaptureV3',envelope.traceText,{});save(directory+'/generic-normalization.json',normalization);
      assert.equal(normalization.coverage.complete,false,'No generic diagnostic promotion');assert.equal(normalization.status,'inconclusive');
      const report=call(sdk,'analyzeModelProfileV3',text,plan.requestOptions);const reportText=canonical(report);save(directory+'/report.json',reportText,true);
      assert.equal(report.format,'moontxnwitness-model-profile-report/v1');assert.equal(report.engine.version,VERSION);assert.equal(report.engine.coreSha256,plan.buildManifest.coreSha256);
      assert.equal(report.engine.hostSha256,plan.runtimeFiles.find(x=>x.file==='model-profile.mjs').sha256);assert.equal(report.requestOptionsText,'{}');scopes(report);
      assert.deepEqual(exactBinding(Buffer.from(canonical(report.result),'utf8')),entry.originalCoreProjectionBinding,'SDK core result differs from original current PG projection (no ignored fields)');
      assert.equal(report.status,previous.status);assert.equal(report.analysisCoverageAccepted,entry.expectedProjection==='supported');
      assert.deepEqual(report.result.originalDiagnosticCoverage,normalization.coverage);
      assert.equal(report.sourceBindings.envelopeSha256,sha(raw));
      for(const name of ['trace','sourceJournal','lifecycle','journalIndex'])assert.equal(report.sourceBindings[name+'Sha256'],sha(envelope[name+'Text']));
      if(entry.expectedProjection==='supported'){assert.equal(report.status,entry.expectedSerialStatus);assert(report.result.derivedTrace);assert.equal(report.result.analysis.status,report.status);assert.equal(previous.independentOracleAgreement,true);}
      else{assert.equal(report.status,'inconclusive');assert.equal(report.result.derivedTrace,null);assert.notEqual(report.result.mappingCoverage?.complete,true);}
      const verified=call(sdk,'verifyModelProfileV3',text,reportText,plan.requestOptions);save(directory+'/verify.json',verified);assert.equal(verified.valid,true);assert.equal(verified.status,report.status);assert.equal(verified.analysisCoverageAccepted,report.analysisCoverageAccepted);
      const capsule=call(sdk,'makeModelProfileCapsuleV3',text,plan.requestOptions);save(directory+'/capsule.json',capsule,true);
      const parsed=JSON.parse(capsule);assert.equal(parsed.envelopeText,text);assert.equal(parsed.reportText,JSON.stringify(report));
      const replay=call(sdk,'replayModelProfileCapsuleV3',capsule);save(directory+'/replay.json',replay);assert.equal(replay.valid,true);assert.equal(replay.envelopeText,text);assert.deepEqual(replay.report,report);assert.equal(replay.status,report.status);
      checks.push({name:entry.case+':original-normalize-analyze-verify-capsule-replay',passed:true});
      const reportMutations=[['conclusion',r=>{r.status=inverseStatus(r.status);r.result.status=r.status;}],['source-binding',r=>r.sourceBindings.traceSha256='0'.repeat(64)],['budget',r=>r.budgets.exactSearchTransactions+=1]];
      for(const[name,mutate]of reportMutations)test(entry.case+':reject-report-'+name,()=>{
        const altered=structuredClone(report);mutate(altered);save(directory+'/tampered-report-'+name+'.json',altered);
        const rejected=call(sdk,'verifyModelProfileV3',text,altered);save(directory+'/tampered-report-'+name+'.verification.json',rejected);assert.equal(rejected.valid,false);
      });
      const capsuleMutations=[['engine',c=>c.engine.hostSha256='0'.repeat(64),false],['budget',c=>c.budgets.exactSearchTransactions+=1,false],['resigned-conclusion',c=>{const r=JSON.parse(c.reportText);r.status=inverseStatus(r.status);r.result.status=r.status;c.reportText=JSON.stringify(r);},true],['resigned-source',c=>{const e=JSON.parse(c.envelopeText);e.unrecordedAddedField='tampered';c.envelopeText=JSON.stringify(e);},true]];
      for(const[name,mutate,reSign]of capsuleMutations)test(entry.case+':reject-capsule-'+name,()=>{
        const altered=structuredClone(parsed);mutate(altered);const tampered=reSign?resign(altered):canonical(altered);save(directory+'/tampered-capsule-'+name+'.json',tampered,true);
        const rejected=call(sdk,'replayModelProfileCapsuleV3',tampered);save(directory+'/tampered-capsule-'+name+'.replay.json',rejected);assert.equal(rejected.valid,false);
      });
      item.status=report.status;item.analysisCoverageAccepted=report.analysisCoverageAccepted;item.originalEnvelopeRetainedExactly=true;item.originalCoreProjectionByteIdentical=true;
      item.sourceClosedReductionAvailable=report.scope.sourceClosedReductionAvailable;item.passed=checks.filter(x=>x.name.startsWith(entry.case+':')).every(x=>x.passed);
    }catch(error){item.error=String(error.stack??error);checks.push({name:entry.case+':original-sdk-loop',passed:false,error:item.error});}
    item.sdkTopLevelCalls=calls-item.sdkTopLevelCallsBefore;
  }
}catch(error){fatal=String(error.stack??error);}
if(plan&&inputs&&runtime){
  inputsAfter=test('all127-original-PG-files-unchanged',()=>checkTree(inputs,plan.inputFiles));
  runtimeAfter=test('all102-current-runtime-files-unchanged',()=>checkTree(runtime,plan.runtimeFiles));
}
const result={format:'moontxnwitness-current027-pg-sdk-loop/v1',version:VERSION,passed:!fatal&&!resourceRefused&&cases.length===10&&cases.every(x=>x.passed)&&checks.every(x=>x.passed),startedAt,finishedAt:new Date().toISOString(),sourceCommit:plan?.sourceCommit??null,ciRun:plan?.ciRun??null,originalArtifactSha256:plan?.artifactSha256??null,planSha256:args['--plan-sha256'],buildManifest:plan?.buildManifest??null,sdkImported,sdkTopLevelCalls:calls,cases,checks,fatal,resourceRefused,inputsBeforeAfterUnchanged:inputsAfter,runtimeBeforeAfterUnchanged:runtimeAfter,originalPostgresExecutedInHostedRun:true,newDatabaseExecutedHere:false,networkPerformed:false,servicesStarted:false,subprocessesStarted:false,compilerExecuted:false,formalPerformanceMeasurement:false,sourceClosedReductionClaimed:false,serverAuthenticityCertified:false,allTenFullAnalysisCoverageClaimed:false,files};
save('receipt.json',result);console.log(JSON.stringify({...result,files:undefined,checks:undefined,cases:cases.map(x=>({case:x.case,passed:x.passed,status:x.status,error:x.error}))}));if(!result.passed)process.exitCode=1;
