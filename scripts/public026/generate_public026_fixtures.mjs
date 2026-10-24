// Future actual-public26 producer only. No author checkout, rewrite or compiler.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync,copyFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const VERSION='0.2.6',sha=x=>createHash('sha256').update(x).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
const safe=x=>{assert.equal(typeof x,'string');assert.ok(x&&!x.includes('\\')&&!x.includes(':')&&!x.startsWith('/')&&!x.split('/').some(p=>!p||p==='.'||p==='..'));return x;};
export async function produceV026(providerDirectory,outputDirectory,expectedSource){
 assert.match(expectedSource,/^[0-9a-f]{40}$/);const base=resolve(providerDirectory),out=resolve(outputDirectory),providerText=readFileSync(resolve(base,'provider.json'),'utf8'),provider=JSON.parse(providerText);
 assert.equal(provider.format,'moontxnwitness-v026-provider/v1');assert.equal(provider.version,VERSION);assert.equal(provider.sourceCommit,expectedSource);
 for(const k of ['actualPublishedProducer','rawEsmIdentityPreserved'])assert.equal(provider[k],true);
 for(const k of ['authorDistRead','headerRewriting','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(provider[k],false);
 const bound=name=>{const b=readFileSync(resolve(base,safe(name))),r=provider.bindings[name];assert.ok(r);assert.equal(b.length,r.bytes);assert.equal(sha(b),r.sha256);return b;};
 for(const name of Object.keys(provider.bindings))bound(name);
 const publication=JSON.parse(bound('origin/publication.json'));assert.equal(publication.passed,true);assert.equal(publication.version,VERSION);assert.equal(publication.github.ci.headSha,expectedSource);
 assert.equal(existsSync(out),false,'Do not overwrite original fixtures');
 const runtime=resolve(base,'runtime'),sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href),orm=await import(pathToFileURL(resolve(runtime,'orm-profile.mjs')).href),evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href),category=await import(pathToFileURL(resolve(runtime,'classification.mjs')).href),models=await import(pathToFileURL(resolve(runtime,'classification-models.mjs')).href);
 assert.equal(sdk.version(),VERSION);mkdirSync(out);mkdirSync(resolve(out,'producer-runtime'));const files={};
 const write=(name,value)=>{safe(name);const b=Buffer.from(typeof value==='string'?value:canonical(value));writeFileSync(resolve(out,name),b,{flag:'wx'});return {file:name,bytes:b.length,sha256:sha(b)};};
 for(const [name,record]of Object.entries(provider.runtime)){
  const b=bound('runtime/'+name);assert.equal(sha(b),record.sha256);const target=resolve(out,'producer-runtime',safe(name));mkdirSync(dirname(target),{recursive:true});copyFileSync(resolve(runtime,name),target);files[name]={file:'producer-runtime/'+name,bytes:b.length,sha256:sha(b)};
 }
 write('provider-origin.json',providerText);const cases=[];const read=name=>bound('package/'+safe(name)).toString('utf8');
 const record=(name,type,operation,input,options,report,capsule,replay,origin)=>{
  assert.equal(replay.valid,true);const capsuleValue=JSON.parse(capsule);assert.equal(capsuleValue.engine?.version??capsuleValue.engineVersion,VERSION);
  cases.push({name,type,operation,requestOptions:options,expectedStatus:report.status,inputOrigin:origin,input:write(name+'.input.json',input),report:write(name+'.report.json',report),capsule:write(name+'.capsule.json',capsule),producerReplay:write(name+'.producer-replay.json',replay)});
 };
 assert.equal(provider.existingCases.length,21);
 for(const row of provider.existingCases){
  const input=read(row.inputPath),options=row.requestOptions??{};let report,capsule,replay;
  if(row.type==='category-classification'){
   report=row.operation==='reduce'?category.reduceClassificationV3(input,options):category.classifyV3(input,options);
   capsule=row.operation==='reduce'?category.makeClassificationReductionCapsuleV3(input,options):category.makeClassificationCapsuleV3(input,options);replay=category.replayClassificationCapsuleV3(capsule);
   assert.equal(category.verifyClassificationV3(input,report,options).valid,true);assert.deepEqual(replay.report,report);
  }else if(row.type==='orm-profile'){
   report=row.operation==='reduce'?orm.reduceOrmProfileV3(input,options):orm.analyzeOrmProfileV3(input,options);
   capsule=row.operation==='reduce'?orm.makeOrmProfileReductionCapsuleV3(input,options):orm.makeOrmProfileCapsuleV3(input,options);replay=orm.replayOrmProfileCapsuleV3(capsule);
   assert.equal(orm.verifyOrmProfileV3(input,report,options).valid,true);assert.deepEqual(replay.report,report);assert.equal(replay.envelopeText,input);
  }else if(row.type==='execution'){
   report=sdk.inspectExecutionFailuresV3(input);capsule=sdk.makeExecutionCapsuleV3(input);replay=sdk.replayExecutionCapsuleV3(capsule);assert.ok(report.transactionOutcomes.some(x=>x.status==='unknown'));
  }else if(row.type==='v3'){
   report=sdk.analyzeV3(input);capsule=sdk.makeCapsuleV3(input,report);replay=sdk.replayCapsuleV3(capsule);
  }else{
   assert.ok(['v1','v2'].includes(row.type));report=row.type==='v1'?sdk.analyze(input):sdk.analyzeWithOptions(input);capsule=evidence.makeCapsule(input,report);replay=evidence.replayCapsule(capsule);
  }
  record(row.name,row.type,row.operation??'analyze',input,options,report,capsule,replay,{kind:'exact-input-from-public26-preserved-public25-bundle',path:row.inputPath,reusedInputVersion:'0.2.5',preservedPriorInputOrigin:row.preservedPriorInputOrigin,originalInputUnchanged:true,databaseExecutedHere:false,executedAsNew26BusinessRun:false});
 }
 assert.equal(provider.modelCases.length,14);
 for(const row of provider.modelCases){
  const input=read(row.inputPath),options=row.options;
  const report=models.classifyModelsV3(input,options),capsule=models.makeModelsClassificationCapsuleV3(input,options),replay=models.replayModelsClassificationCapsuleV3(capsule);
  assert.equal(models.verifyModelsClassificationV3(input,report,options).valid,true);assert.deepEqual(replay.report,report);
  assert.equal(report.engine.version,VERSION);assert.equal(report.engine.coreSha256,provider.runtime['core.mjs'].sha256);assert.equal(report.engine.hostSha256,provider.runtime['classification-models.mjs'].sha256);assert.equal(report.originalSourceText,input);
  record(row.name,'model-classification','classify-models',input,options,report,capsule,replay,{...row.origin,kind:'exact-published-model-input',preservedPublishedOrigin:row.origin,path:row.inputPath,originalInputUnchanged:true,databaseExecutedHere:false,newActualBusinessRun:false});
 }
 assert.equal(cases.length,35);
 const manifest={schema:1,format:'moontxnwitness-actual-public-producer-fixtures/v1',producerEngineVersion:VERSION,actualPublishedProducer:true,sourceCommit:expectedSource,expectedSourceCommit:expectedSource,providerSha256:sha(providerText),publicPackages:provider.publicPackages,checksumAsset:provider.checksumAsset,registryPackage:provider.registryPackage,publicationReceiptSha256:provider.publicationReceiptSha256,publisherReferenceSha256:provider.publisherReferenceSha256,transportReceiptSha256:provider.transportReceiptSha256,producerBuild:provider.buildManifest,producerFiles:files,fullSdkEsmFiles:provider.fullSdkEsmFiles,minimalCategoryReplayFiles:provider.minimalCategoryReplayFiles,minimalOrmEsmReplayFiles:provider.minimalOrmEsmReplayFiles,minimalModelReplayFiles:provider.minimalModelReplayFiles,entirePublicDistPreserved:provider.entirePublicDistPreserved,externalBindingsSha256:provider.externalBindingsSha256,rawEsmIdentityPreserved:true,headerRewriting:false,authorDistRead:false,actualDatabaseExecutedHere:false,compilerExecutedHere:false,originalProducerReplaysPassed:true,existingFamilies:21,modelCases:14,cases,scope:'Naturally generated by actual anonymously downloaded public26 ESM only. Earlier observed business origins, synthetic cases and deliberately unmatched facts remain labelled. No next-version SDK acceptance or new live business run is implied.'};
 write('manifest.json',manifest);
 return {passed:true,producerEngineVersion:VERSION,actualPublishedProducer:true,cases:35,existingFamilies:21,modelCases:14,rawEsmIdentityPreserved:true,fixtureManifestSha256:sha(readFileSync(resolve(out,'manifest.json'))),actualDatabaseExecutedHere:false,compilerExecutedHere:false};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const a=process.argv.slice(2);assert.ok(a.length===6&&a[0]==='--provider'&&a[2]==='--expected-source'&&a[4]==='--out','Usage: --provider VERIFIED_PUBLIC25_PROVIDER --expected-source REAL_PUBLISHED_TAG_SHA --out NEW_OUTPUT');
 console.log(JSON.stringify(await produceV026(a[1],a[5],a[3])));
}
