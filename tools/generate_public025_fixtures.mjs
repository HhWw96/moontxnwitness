// Future actual-public25 producer only. No author checkout, rewrite or compiler.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync,copyFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const VERSION='0.2.5',sha=x=>createHash('sha256').update(x).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
const safe=x=>{assert.equal(typeof x,'string');assert.ok(x&&!x.includes('\\')&&!x.includes(':')&&!x.startsWith('/')&&!x.split('/').some(p=>!p||p==='.'||p==='..'));return x;};
export async function produceV025(providerDirectory,outputDirectory,expectedSource){
 assert.match(expectedSource,/^[0-9a-f]{40}$/);const base=resolve(providerDirectory),out=resolve(outputDirectory),providerText=readFileSync(resolve(base,'provider.json'),'utf8'),provider=JSON.parse(providerText);
 assert.equal(provider.format,'moontxnwitness-v025-provider/v1');assert.equal(provider.version,VERSION);assert.equal(provider.sourceCommit,expectedSource);
 for(const k of ['actualPublishedProducer','rawEsmIdentityPreserved'])assert.equal(provider[k],true);
 for(const k of ['authorDistRead','headerRewriting','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(provider[k],false);
 const bound=name=>{const b=readFileSync(resolve(base,safe(name))),r=provider.bindings[name];assert.ok(r);assert.equal(b.length,r.bytes);assert.equal(sha(b),r.sha256);return b;};
 for(const name of Object.keys(provider.bindings))bound(name);
 const publication=JSON.parse(bound('origin/publication.json'));assert.equal(publication.passed,true);assert.equal(publication.version,VERSION);assert.equal(publication.github.ci.headSha,expectedSource);
 assert.equal(existsSync(out),false,'Do not overwrite original fixtures');
 const runtime=resolve(base,'runtime'),sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href),orm=await import(pathToFileURL(resolve(runtime,'orm-profile.mjs')).href),evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href),category=await import(pathToFileURL(resolve(runtime,'classification.mjs')).href);
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
 assert.equal(provider.existingCases.length,15);
 for(const row of provider.existingCases){
  const input=read(row.inputPath),options=row.requestOptions??{};let report,capsule,replay;
  if(row.type==='orm-profile'){
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
  if(row.type!=='execution')assert.equal(report.status,row.expectedStatus);
  record(row.name,row.type,row.operation??'analyze',input,options,report,capsule,replay,{kind:'exact-input-from-public25-preserved-public24-bundle',path:row.inputPath,reusedInputVersion:'0.2.4',preservedPriorInputOrigin:row.preservedPriorInputOrigin,originalInputUnchanged:true,databaseExecutedHere:false,executedAsNew25BusinessRun:false});
 }
 function categoryCase(name,key,operation,options,expected){
  const input=read(provider.categoryInputPaths[key]),report=operation==='reduce'?category.reduceClassificationV3(input,options):category.classifyV3(input,options);
  const capsule=operation==='reduce'?category.makeClassificationReductionCapsuleV3(input,options):category.makeClassificationCapsuleV3(input,options),replay=category.replayClassificationCapsuleV3(capsule);
  assert.equal(report.status,expected);assert.equal(category.verifyClassificationV3(input,report,options).valid,true);assert.deepEqual(replay.report,report);
  assert.equal(report.engine.version,VERSION);assert.equal(report.engine.coreSha256,provider.runtime['core.mjs'].sha256);assert.equal(report.engine.hostSha256,provider.runtime['classification.mjs'].sha256);assert.equal(report.originalSourceText,input);
  if(operation==='reduce'){
   assert.equal(report.sourceClosure.complete,true);assert.equal(report.sourceClosure.originalEventsPreserved,true);assert.equal(report.result.oneMinimal,true);assert.equal(report.result.category,'G2-item');assert.equal(report.finalReplay.valid,true);assert.ok(report.result.checks<=options.maxChecks);
  }
  record(name,'category-classification',operation,input,options,report,capsule,replay,{kind:'exact-published-synthetic-category-input',path:provider.categoryInputPaths[key],originalInputUnchanged:true,actualPostgresAnomaly:false,databaseExecutedHere:false});
 }
 categoryCase('category-g0','g0','classify',{categories:['G0']},'refuted');
 categoryCase('category-g1c','g1c','classify',{categories:['G1c']},'refuted');
 categoryCase('category-g2-item','source-closed-noisy-g2','classify',{categories:['G2-item']},'refuted');
 categoryCase('category-reduce-g2-item','source-closed-noisy-g2','reduce',{category:'G2-item',maxChecks:256},'reduced');
 categoryCase('category-zero-budget','source-closed-noisy-g2','classify',{categories:['G2-item'],maxStates:0,maxEdgeChecks:0},'inconclusive');
 categoryCase('category-missing-source','missing-source','classify',{},'inconclusive');
 assert.equal(cases.length,21);
 const manifest={schema:1,format:'moontxnwitness-actual-public-producer-fixtures/v1',producerEngineVersion:VERSION,actualPublishedProducer:true,sourceCommit:expectedSource,expectedSourceCommit:expectedSource,providerSha256:sha(providerText),publicPackages:provider.publicPackages,checksumAsset:provider.checksumAsset,registryPackage:provider.registryPackage,publicationReceiptSha256:provider.publicationReceiptSha256,publisherReferenceSha256:provider.publisherReferenceSha256,transportReceiptSha256:provider.transportReceiptSha256,producerBuild:provider.buildManifest,producerFiles:files,fullSdkEsmFiles:provider.fullSdkEsmFiles,minimalCategoryReplayFiles:provider.minimalCategoryReplayFiles,minimalOrmEsmReplayFiles:provider.minimalOrmEsmReplayFiles,rawEsmIdentityPreserved:true,headerRewriting:false,authorDistRead:false,actualDatabaseExecutedHere:false,compilerExecutedHere:false,originalProducerReplaysPassed:true,existingFamilies:15,categoryCases:6,cases,scope:'Naturally generated by actual anonymously downloaded public25 ESM only. Earlier observed business origins, synthetic cases and deliberately unmatched facts remain labelled. No current/future SDK acceptance or new live business run is implied.'};
 write('manifest.json',manifest);
 return {passed:true,producerEngineVersion:VERSION,actualPublishedProducer:true,cases:21,existingFamilies:15,categoryCases:6,rawEsmIdentityPreserved:true,fixtureManifestSha256:sha(readFileSync(resolve(out,'manifest.json'))),actualDatabaseExecutedHere:false,compilerExecutedHere:false};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const a=process.argv.slice(2);assert.ok(a.length===6&&a[0]==='--provider'&&a[2]==='--expected-source'&&a[4]==='--out','Usage: --provider VERIFIED_PUBLIC25_PROVIDER --expected-source REAL_PUBLISHED_TAG_SHA --out NEW_OUTPUT');
 console.log(JSON.stringify(await produceV025(a[1],a[5],a[3])));
}
