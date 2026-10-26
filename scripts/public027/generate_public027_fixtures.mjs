// Produce genuine public027 expectations from fixed original anonymous bytes only.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync,lstatSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const SOURCE='c10b06c5bfcabd1f40b0ff0099717072a816ec74',VERSION='0.2.7';
const sha=x=>createHash('sha256').update(x).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
const safe=x=>{assert.equal(typeof x,'string');assert.ok(x&&!x.includes(String.fromCharCode(92))&&!x.includes(':')&&!x.includes('\0')&&!x.startsWith('/')&&!x.split('/').some(p=>!p||p==='.'||p==='..'));return x;};
export async function produceV027(providerDirectory,outputDirectory,providerSHA){
 assert.match(providerSHA,/^[0-9a-f]{64}$/);const base=resolve(providerDirectory),out=resolve(outputDirectory);
 const raw=readFileSync(resolve(base,'provider.json'));assert.equal(sha(raw),providerSHA);const p=JSON.parse(raw);
 assert.equal(p.format,'moontxnwitness-v027-provider/v1');assert.equal(p.version,VERSION);assert.equal(p.sourceCommit,SOURCE);
 for(const k of ['actualPublishedProducer','rawEsmIdentityPreserved','entirePublicDistPreserved'])assert.equal(p[k],true);
 for(const k of ['authorDistRead','headerRewriting','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(p[k],false);
 assert.equal(p.publicTopDistFiles,102);assert.equal(Object.keys(p.runtime).length,103);assert.equal(p.cases.length,46);
 const bound=name=>{safe(name);let cursor=base;for(const part of name.split('/')){cursor=resolve(cursor,part);assert.equal(lstatSync(cursor).isSymbolicLink(),false);}const info=lstatSync(cursor);assert.ok(info.isFile()&&info.size<=128*1024*1024);const b=readFileSync(cursor),r=p.bindings[name];assert.ok(r);assert.equal(b.length,r.bytes);assert.equal(sha(b),r.sha256);return b;};
 for(const name of Object.keys(p.bindings))bound(name);
 assert.equal(existsSync(out),false,'Never overwrite original producer results');
 const runtime=resolve(base,'runtime');
 const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href),orm=await import(pathToFileURL(resolve(runtime,'orm-profile.mjs')).href),evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href),category=await import(pathToFileURL(resolve(runtime,'classification.mjs')).href),models=await import(pathToFileURL(resolve(runtime,'classification-models.mjs')).href),profile=await import(pathToFileURL(resolve(runtime,'model-profile.mjs')).href);
 assert.equal(sdk.version(),VERSION);mkdirSync(dirname(out),{recursive:true});mkdirSync(out);const producerFiles={};
 const write=(name,value)=>{safe(name);const b=Buffer.isBuffer(value)?value:Buffer.from(typeof value==='string'?value:canonical(value));const q=resolve(out,name);mkdirSync(dirname(q),{recursive:true});writeFileSync(q,b,{flag:'wx'});return {file:name,bytes:b.length,sha256:sha(b)};};
 for(const [name,entry]of Object.entries(p.runtime)){const b=bound('runtime/'+name);assert.deepEqual({bytes:b.length,sha256:sha(b)},entry);producerFiles[name]=write('producer-runtime/'+name,b);}
 write('provider-origin.json',raw);const cases=[];
 for(const row of p.cases){
  const input=bound('package/'+row.inputPath).toString('utf8'),options=row.requestOptions;let report,capsule,replay,verification;
  if(row.type==='model-profile'){
   report=profile.analyzeModelProfileV3(input,options);capsule=profile.makeModelProfileCapsuleV3(input,options);replay=profile.replayModelProfileCapsuleV3(capsule);verification=profile.verifyModelProfileV3(input,report,options);assert.deepEqual(replay.report,report);assert.equal(replay.envelopeText,input);
  }else if(row.type==='model-classification'){
   report=models.classifyModelsV3(input,options);capsule=models.makeModelsClassificationCapsuleV3(input,options);replay=models.replayModelsClassificationCapsuleV3(capsule);verification=models.verifyModelsClassificationV3(input,report,options);assert.deepEqual(replay.report,report);
  }else if(row.type==='category-classification'){
   report=row.operation==='reduce'?category.reduceClassificationV3(input,options):category.classifyV3(input,options);capsule=row.operation==='reduce'?category.makeClassificationReductionCapsuleV3(input,options):category.makeClassificationCapsuleV3(input,options);replay=category.replayClassificationCapsuleV3(capsule);verification=category.verifyClassificationV3(input,report,options);assert.deepEqual(replay.report,report);
  }else if(row.type==='orm-profile'){
   report=row.operation==='reduce'?orm.reduceOrmProfileV3(input,options):orm.analyzeOrmProfileV3(input,options);capsule=row.operation==='reduce'?orm.makeOrmProfileReductionCapsuleV3(input,options):orm.makeOrmProfileCapsuleV3(input,options);replay=orm.replayOrmProfileCapsuleV3(capsule);verification=orm.verifyOrmProfileV3(input,report,options);assert.deepEqual(replay.report,report);assert.equal(replay.envelopeText,input);
  }else if(row.type==='execution'){
   report=sdk.inspectExecutionFailuresV3(input);capsule=sdk.makeExecutionCapsuleV3(input);replay=sdk.replayExecutionCapsuleV3(capsule);verification={valid:replay.valid,scope:'Original public027 execution capsule recomputation'};
  }else if(row.type==='v3'){
   report=sdk.analyzeV3(input);capsule=sdk.makeCapsuleV3(input,report);replay=sdk.replayCapsuleV3(capsule);verification=sdk.verifyV3(input,report);
  }else{
   assert.ok(['v1','v2'].includes(row.type));report=row.type==='v1'?sdk.analyze(input):sdk.analyzeWithOptions(input);capsule=evidence.makeCapsule(input,report);replay=evidence.replayCapsule(capsule);verification=sdk.replayReport(input,report);
  }
  assert.equal(replay.valid,true,row.name+' original replay');assert.equal(verification.valid,true,row.name+' original verification');
  const cap=JSON.parse(capsule);assert.equal(cap.engine?.version??cap.engineVersion,VERSION);
  cases.push({name:row.name,type:row.type,operation:row.operation,requestOptions:options,expectedStatus:report.status,inputOrigin:{kind:'exact-input-preserved-in-public027-package',path:row.inputPath,preservedPublishedInputOrigin:row.inputOrigin,originalInputUnchanged:true,databaseExecutedHere:false,newActualBusinessRun:false},input:write(row.name+'.input.json',input),report:write(row.name+'.report.json',report),capsule:write(row.name+'.capsule.json',capsule),producerReplay:write(row.name+'.producer-replay.json',replay),producerVerification:write(row.name+'.producer-verification.json',verification)});
  console.log(JSON.stringify({completed:cases.length,name:row.name,status:report.status,originalReplayValid:replay.valid}));
 }
 assert.equal(cases.length,46);assert.equal(cases.filter(r=>r.type==='model-profile').length,11);
 for(const name of Object.keys(p.bindings))bound(name);
 const manifest={schema:1,format:'moontxnwitness-actual-public-producer-fixtures/v1',producerEngineVersion:VERSION,actualPublishedProducer:true,sourceCommit:SOURCE,expectedSourceCommit:SOURCE,providerSha256:providerSHA,publicPackage:p.nestedPublicPackage,outerArtifact:p.outerArtifact,producerBuild:p.buildManifest,producerFiles,entirePublicDistPreserved:true,publicTopDistFiles:102,rawEsmIdentityPreserved:true,headerRewriting:false,authorDistRead:false,actualDatabaseExecutedHere:false,compilerExecutedHere:false,originalProducerReplaysPassed:true,originalProducerVerificationsPassed:true,existingFamilies:35,modelProfileCases:11,cases,scope:'Naturally generated by actual anonymously downloaded public027 ESM. Replays original package inputs, including ten historical database model-profile sources and one zero-budget option. No new database execution or new consumer028 acceptance.'};
 const record=write('manifest.json',manifest);
 return {passed:true,producerEngineVersion:VERSION,actualPublishedProducer:true,cases:46,existingFamilies:35,modelProfileCases:11,fixtureManifestSha256:record.sha256,providerSha256:providerSHA,actualDatabaseExecutedHere:false,compilerExecutedHere:false,actualNewConsumerExecuted:false};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){const a=process.argv.slice(2);assert.ok(a.length===6&&a[0]==='--provider'&&a[2]==='--provider-sha256'&&a[4]==='--out');console.log(JSON.stringify(await produceV027(a[1],a[5],a[3])));}