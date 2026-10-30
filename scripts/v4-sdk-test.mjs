import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire,syncBuiltinESMExports} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const threadModule=createRequire(import.meta.url)('node:worker_threads');
const OriginalWorker=threadModule.Worker;
const childModule=createRequire(import.meta.url)('node:child_process');
const OriginalSpawn=childModule.spawnSync;
let spawnedProcesses=0;
childModule.spawnSync=(...args)=>{spawnedProcesses++;return OriginalSpawn(...args);};
let workers=0;
threadModule.Worker=class ForbiddenLegacyWorker {constructor(){workers++;throw Error('Current v4 must not start a legacy worker');}};
syncBuiltinESMExports();
const sdk=await import('../dist/sdk.mjs');
const {analyzeV4,classifyV4,reduceV4,verifyV4,verifyClassificationV4,verifyReductionV4,
  makeCapsuleV4,makeClassificationCapsuleV4,makeReductionCapsuleV4,replayCapsuleV4}=sdk;
const hash=text=>createHash('sha256').update(text,'utf8').digest('hex');
const clone=value=>structuredClone(value);
const register={schemaVersion:1,model:'serializable',initial:{x:'x0',y:'y0'},versionOrders:{x:['x0','x1'],y:['y0','y1']},transactions:[
  {id:'事务一',status:'committed',ops:[{type:'read',key:'x',version:'x0'},{type:'write',key:'y',version:'y1'}]},
  {id:'事务二',status:'committed',ops:[{type:'read',key:'y',version:'y0'},{type:'write',key:'x',version:'x1'}]},
]};
function capture(model,steps){
  const relation=model==='relation-set-v1';
  const events=[{kind:'snapshot',initial:relation?{r:[]}:{x:[]},consistent:true},
    {kind:'begin',tx:'A',connection:'c'},...steps,{kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'}];
  const source={traceSchema:3,dataModel:model,clockDomain:'v4-sdk-fixed',scope:{exclusiveWriters:true},
    events:events.map((event,index)=>({seq:index+1,time:index,...event})),gaps:[]};
  if(relation){source.relationSchema={r:{primaryKey:'id',columns:{id:'int64',n:'int64'}}};source.scope.completeSnapshotTables=['r'];}
  return source;
}
const list=capture('append-list-v1',[{kind:'append',tx:'A',key:'x',id:'唯一',value:'重复值'}]);
const relation=capture('relation-set-v1',[{kind:'row_read',tx:'A',relation:'r',predicate:[],rows:[],complete:true}]);
let passed=0;
const results=[];
function check(name,run){run();passed++;results.push({name,status:'passed'});}
function replayMutation(original,mutate){const capsule=JSON.parse(original);mutate(capsule);return replayCapsuleV4(JSON.stringify(capsule));}
const analysisCapsules=[];
for(const [name,source] of [['register',register],['list',list],['relation',relation]]){
  const original=JSON.stringify(source),report=analyzeV4(source);
  check(name+' typed SDK analysis and source binding',()=>{
    assert.equal(report.schemaVersion,4);assert.equal(report.format,'moontxnwitness-analysis/v4');
    assert.deepEqual(report.observations.document,source);assert.equal(report.observations.authenticityVerified,false);
    assert.equal(JSON.stringify(source),original);assert.equal(verifyV4(source,report).valid,true);
  });
  const capsule=makeCapsuleV4(source);analysisCapsules.push(capsule);
  check(name+' capsule source/options/report digests and replay',()=>{
    const parsed=JSON.parse(capsule);
    for(const field of ['source','options','report'])assert.equal(parsed[field+'Sha256'],hash(parsed[field+'Text']));
    assert.equal(replayCapsuleV4(capsule).valid,true);
  });
  check(name+' report source tamper rejected',()=>{
    const altered=clone(report);altered.observations.document.clockDomain='forged';
    assert.equal(verifyV4(source,altered).valid,false);
  });
  check(name+' exact custom budget requires independent authority',()=>{
    const limited=makeCapsuleV4(source,{maxOperationChecks:0});
    assert.equal(replayCapsuleV4(limited).valid,false);
    assert.equal(replayCapsuleV4(limited,{maxOperationChecks:0}).valid,true);
  });
}
const main=analysisCapsules[0],report=analyzeV4(register);
for(const key of ['semanticContract','algorithm','dataModel'])check('report '+key+' tamper',()=>{
  const altered=clone(report);altered[key]='unsupported';assert.equal(verifyV4(register,altered).valid,false);
});
check('report counter tamper',()=>{const altered=clone(report);altered.execution.counterContract='unsupported';assert.equal(verifyV4(register,altered).valid,false);});
check('report budget tamper',()=>{const altered=clone(report);altered.execution.requestedOptions.maxAttempts=0;assert.equal(verifyV4(register,altered).valid,false);});
check('report conclusion tamper',()=>{const altered=clone(report);altered.judgment.status='consistent';assert.equal(verifyV4(register,altered).valid,false);});
check('history model tamper',()=>{const source=clone(register);source.model='strict-serializable';assert.equal(verifyV4(source,report).valid,false);});
for(const field of ['source','options','report'])check('capsule '+field+' digest mismatch',()=>{
  assert.equal(replayMutation(main,c=>{c[field+'Text']+=' ';}).valid,false);
});
for(const field of ['semanticContract','algorithm','counterContract'])check('capsule unknown '+field,()=>{
  assert.equal(replayMutation(main,c=>{c[field]='unsupported';}).valid,false);
});
check('capsule self-consistent report hash does not authorize forged conclusion',()=>{
  assert.equal(replayMutation(main,c=>{const r=JSON.parse(c.reportText);r.judgment.status='consistent';c.reportText=JSON.stringify(r);c.reportSha256=hash(c.reportText);}).valid,false);
});
check('capsule self-consistent source hash does not authorize changed history',()=>{
  assert.equal(replayMutation(main,c=>{const s=JSON.parse(c.sourceText);s.model='strict-serializable';c.sourceText=JSON.stringify(s);c.sourceSha256=hash(c.sourceText);}).valid,false);
});
check('unknown source schema cannot be authorized with a new digest',()=>{
  assert.equal(replayMutation(main,c=>{c.sourceText='{"traceSchema":4}';c.sourceSha256=hash(c.sourceText);}).valid,false);
});
check('producer version is metadata rather than semantic authority',()=>{
  assert.equal(replayMutation(main,c=>{c.producer.version='future-producer';}).valid,true);
});
check('outer duplicate keys rejected by MoonBit guard',()=>{
  assert.equal(replayCapsuleV4(main.replace('"schemaVersion":4','"schemaVersion":4,"schemaVersion":4')).valid,false);
});
check('inner duplicate options rejected by MoonBit guard',()=>{
  assert.equal(replayMutation(main,c=>{c.optionsText='{"maxAttempts":100000,"maxAttempts":100000}';c.optionsSha256=hash(c.optionsText);}).valid,false);
});
for(const options of [{bogus:true},{maxAttempts:100001},{maxStates:-1},{maxOperationChecks:1.5},{maxCachedStates:50001},{model:'serializable'},null,[]])
  check('analysis rejects option '+JSON.stringify(options),()=>assert.throws(()=>analyzeV4(register,options)));
check('source object is stringified once',()=>{
  let calls=0;const source={toJSON(){calls++;return register;}};assert.equal(analyzeV4(source).judgment.status,'violation');assert.equal(calls,1);
});
check('malformed Unicode rejected before conversion',()=>assert.throws(()=>analyzeV4('\ud800'),/Unicode/));
check('UTF-8 source byte limit is enforced',()=>assert.throws(()=>analyzeV4(' '.repeat(8*1024*1024+1)),/UTF-8/));
check('invalid JSON remains an invalid wire result',()=>assert.equal(analyzeV4('{').status,'invalid'));
check('duplicate source keys remain invalid',()=>assert.equal(analyzeV4('{"traceSchema":3,"traceSchema":3}').status,'invalid'));
check('verification rejects unknown caller options',()=>assert.equal(verifyV4(register,report,{maxAttempt:1}).valid,false));
for(const source of [register,list]){
  const category=classifyV4(source);
  check(source===register?'register classification recomputation':'list classification recomputation',()=>{
    assert.equal(category.judgment.acceptsIsolationModels,false);assert.equal(verifyClassificationV4(source,category).valid,true);
    assert.equal(replayCapsuleV4(makeClassificationCapsuleV4(source)).valid,true);
  });
}
check('relation classification is visibly unsupported and reproducible',()=>{
  const classification=classifyV4(relation);assert.equal(classification.judgment.status,'unsupported');
  assert.equal(verifyClassificationV4(relation,classification).valid,true);
  assert.equal(replayCapsuleV4(makeClassificationCapsuleV4(relation)).valid,true);
});
check('classification custom categories and bounds use external expectations',()=>{
  const options={categories:['G2-item'],maxStates:0,maxEdgeChecks:0},capsule=makeClassificationCapsuleV4(register,options);
  assert.equal(JSON.parse(JSON.parse(capsule).reportText).judgment.status,'inconclusive');
  assert.equal(replayCapsuleV4(capsule).valid,false);assert.equal(replayCapsuleV4(capsule,options).valid,true);
});
for(const options of [{categories:[]},{categories:['G2']},{categories:['G0','G0']},{categories:null},{maxEdgeChecks:1000001},{models:['serializable']}])
  check('classification rejects option '+JSON.stringify(options),()=>assert.throws(()=>classifyV4(register,options)));
for(const options of [undefined,{}, {preserve:'snapshot-isolation'},{preserve:'serializable',maxChecks:257},{preserve:'serializable',analysisOptions:{model:'serializable'}}])
  check('reduction rejects option '+JSON.stringify(options),()=>assert.throws(()=>reduceV4(register,options)));
check('reduction target mismatch is unsupported rather than a different predicate',()=>{
  const reduced=reduceV4(register,{preserve:'strict-serializable'});assert.equal(reduced.status,'unsupported');assert.equal(reduced.oneMinimal,false);assert.equal(reduced.execution.checks,0);
});
for(const [name,source] of [['register',register],['list',list],['relation',relation]])check(name+' reduction external target and budget replay',()=>{
  const options={preserve:'serializable',maxChecks:0},reduced=reduceV4(source,options),capsule=makeReductionCapsuleV4(source,options);
  assert.equal(verifyReductionV4(source,reduced,options).valid,true);assert.equal(verifyReductionV4(source,reduced).valid,false);
  assert.equal(replayCapsuleV4(capsule).valid,false);assert.equal(replayCapsuleV4(capsule,options).valid,true);
  assert.equal(replayCapsuleV4(capsule,{preserve:'strict-serializable',maxChecks:0}).valid,false);
  if(name==='register')assert.equal(reduced.oneMinimal,false);
});

const sdkWorkerSpawns=spawnedProcesses;
const temporaryRoot=resolve(root,'artifacts','validation-temp');mkdirSync(temporaryRoot,{recursive:true});
const temporary=mkdtempSync(resolve(temporaryRoot,'v4-sdk-'));
const sourcePath=resolve(temporary,'source.json'),capsulePath=resolve(temporary,'capsule.json'),reportPath=resolve(temporary,'report.json'),optionsPath=resolve(temporary,'expected.json');
writeFileSync(sourcePath,JSON.stringify(register));writeFileSync(optionsPath,JSON.stringify({preserve:'serializable',maxChecks:0}));
const cli=args=>spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),...args],{encoding:'utf8',windowsHide:true,env:process.env,maxBuffer:5*1024*1024});
check('CLI analysis and capsule output retain anomaly exit status',()=>{
  const result=cli(['analyze-v4',sourcePath,'--output',reportPath,'--capsule',capsulePath]);assert.equal(result.status,1,result.stderr);
  assert.equal(JSON.parse(readFileSync(reportPath)).judgment.status,'violation');
});
check('CLI default capsule replay',()=>{const result=cli(['replay-v4',capsulePath]);assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).valid,true);});
check('CLI verify report with default independent options',()=>{const result=cli(['verify-v4',sourcePath,reportPath]);assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).valid,true);});
check('CLI unknown flag is an error',()=>{const result=cli(['analyze-v4',sourcePath,'--models','elle-core']);assert.equal(result.status,2);});
check('CLI existing output remains unchanged',()=>{
  const before=readFileSync(reportPath,'utf8'),result=cli(['analyze-v4',sourcePath,'--output',reportPath]);assert.equal(result.status,2);assert.equal(readFileSync(reportPath,'utf8'),before);
});
check('CLI output cannot overwrite an input',()=>{const before=readFileSync(sourcePath,'utf8'),result=cli(['analyze-v4',sourcePath,'--output',sourcePath]);assert.equal(result.status,2);assert.equal(readFileSync(sourcePath,'utf8'),before);});
check('CLI reduction accepts independent options file',()=>{const result=cli(['reduce-v4',sourcePath,'--options',optionsPath]);assert.equal(result.status,3,result.stderr);const reduced=JSON.parse(result.stdout);assert.equal(reduced.oneMinimal,false);});
check('CLI missing reduction target fails',()=>assert.equal(cli(['reduce-v4',sourcePath]).status,2));
check('current SDK operations started no legacy worker',()=>{assert.equal(workers,0);assert.equal(sdkWorkerSpawns,0);});
threadModule.Worker=OriginalWorker;childModule.spawnSync=OriginalSpawn;syncBuiltinESMExports();
const receipt={suite:'v4-sdk-transport-and-capsules-1',passed:true,checks:passed,failed:0,legacyWorkers:workers+sdkWorkerSpawns,results};
writeFileSync(resolve(root,'artifacts/v4-sdk-validation.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));
