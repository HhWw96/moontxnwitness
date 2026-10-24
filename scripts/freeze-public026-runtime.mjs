// Freeze original public26 ESM only after an externally pinned 35-family producer.
// This checks bytes and provenance bindings; it never imports a producer SDK.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync,lstatSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const SOURCE='4c74fd29f45c2e6756a20881fefb03677fa9bf52',VERSION='0.2.6';
const sha=b=>createHash('sha256').update(b).digest('hex'),encode=x=>Buffer.from(JSON.stringify(x,null,2)+'\n');
const safe=n=>typeof n==='string'&&n.length>0&&!n.includes('\\')&&!n.includes(':')&&!n.startsWith('/')&&n.split('/').every(s=>s&&s!=='.'&&s!=='..');
const digest=n=>typeof n==='string'&&/^[0-9a-f]{64}$/.test(n);
const plain=n=>n!==null&&typeof n==='object'&&!Array.isArray(n);
function regularRoot(path){const info=lstatSync(path);assert.ok(info.isDirectory()&&!info.isSymbolicLink(),'Regular non-symlink root required');}
export function freezePublicV026(fixtureDirectory,expectedFixtureSha256,repository){
 assert.ok(digest(expectedFixtureSha256)&&expectedFixtureSha256!=='0'.repeat(64),'External fixture SHA required');
 const base=resolve(fixtureDirectory),root=resolve(repository);regularRoot(base);regularRoot(root);regularRoot(resolve(root,'cmd'));
 function read(name,limit=32*1024*1024){
  assert.ok(safe(name),'Unsafe original fixture path');let cursor=base;
  for(const part of name.split('/')){cursor=resolve(cursor,part);assert.equal(lstatSync(cursor).isSymbolicLink(),false,'Original fixture symlink refused');}
  const info=lstatSync(cursor);assert.ok(info.isFile()&&info.size<=limit,'Bounded regular fixture required');
  const bytes=readFileSync(cursor);assert.equal(bytes.length,info.size);assert.ok(bytes.length<=limit);return bytes;
 }
 const bound=(entry,limit)=>{assert.ok(plain(entry)&&safe(entry.file)&&Number.isSafeInteger(entry.bytes)&&entry.bytes>=0&&digest(entry.sha256),'Invalid original file binding');const bytes=read(entry.file,limit);assert.equal(bytes.length,entry.bytes);assert.equal(sha(bytes),entry.sha256);return bytes;};
 const raw=read('manifest.json',4*1024*1024);assert.equal(sha(raw),expectedFixtureSha256,'Externally recorded genuine26 fixture manifest differs');const fixture=JSON.parse(raw);
 assert.equal(fixture.format,'moontxnwitness-actual-public-producer-fixtures/v1');assert.equal(fixture.producerEngineVersion,VERSION);assert.equal(fixture.sourceCommit,SOURCE);assert.equal(fixture.expectedSourceCommit,SOURCE);
 for(const k of ['actualPublishedProducer','rawEsmIdentityPreserved','originalProducerReplaysPassed','entirePublicDistPreserved'])assert.equal(fixture[k],true,k);
 for(const k of ['headerRewriting','authorDistRead','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(fixture[k],false,k);
 assert.ok(Array.isArray(fixture.cases));assert.equal(fixture.cases.length,35);assert.equal(fixture.existingFamilies,21);assert.equal(fixture.modelCases,14);
 const originRaw=read('provider-origin.json',4*1024*1024);assert.equal(sha(originRaw),fixture.providerSha256);const provider=JSON.parse(originRaw);
 assert.equal(provider.format,'moontxnwitness-v026-provider/v1');assert.equal(provider.version,VERSION);assert.equal(provider.sourceCommit,SOURCE);
 for(const k of ['actualPublishedProducer','rawEsmIdentityPreserved','entirePublicDistPreserved'])assert.equal(provider[k],true,k);
 for(const k of ['headerRewriting','authorDistRead','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(provider[k],false,k);
 assert.ok(plain(provider.runtime)&&plain(provider.bindings)&&plain(fixture.producerFiles));
 for(const key of ['publicPackages','checksumAsset','registryPackage','publicationReceiptSha256','publisherReferenceSha256','transportReceiptSha256','externalBindingsSha256'])assert.deepEqual(fixture[key],provider[key],'Provider provenance differs: '+key);
 assert.deepEqual(Object.keys(fixture.producerFiles).sort(),Object.keys(provider.runtime).sort());
 const names=Object.keys(fixture.producerFiles);assert.ok(names.length>=13&&names.length<=126&&names.every(safe)&&!names.includes('manifest.json')&&!names.includes('origin.json'));
 assert.equal(new Set(names.map(n=>n.toLowerCase())).size,names.length,'Case-ambiguous runtime paths refused');
 const payload={};let total=0;
 for(const [name,entry]of Object.entries(fixture.producerFiles)){
  assert.equal(entry.file,'producer-runtime/'+name);const bytes=bound(entry,32*1024*1024),record={bytes:bytes.length,sha256:sha(bytes)};
  assert.deepEqual(record,provider.runtime[name]);assert.deepEqual(record,provider.bindings['runtime/'+name]);total+=bytes.length;assert.ok(total<=128*1024*1024);payload[name]=bytes;
 }
 for(const required of ['core.mjs','capture-core.mjs','orm-profile.mjs','classification.mjs','classification-models.mjs','legacy-v024.mjs','legacy-v025.mjs','legacy-v025-runtime.mjs','legacy-v025-worker.mjs','legacy-v025-binding.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt'])assert.ok(payload[required],'Missing original closure member '+required);
 assert.ok(payload.LICENSE.length&&payload['THIRD_PARTY_NOTICES.txt'].length,'Original licences must be nonempty');
 const build=JSON.parse(payload['build-manifest.json']);assert.equal(build.version,VERSION);assert.deepEqual(build,fixture.producerBuild);assert.deepEqual(build,provider.buildManifest);
 assert.equal(sha(payload['core.mjs']),build.coreSha256);assert.equal(sha(payload['capture-core.mjs']),build.captureCoreSha256);
 for(const [key,required]of [['minimalModelReplayFiles',['classification-models.mjs','core.mjs']]])assert.deepEqual(fixture[key],required);
 for(const key of ['minimalModelReplayFiles','minimalCategoryReplayFiles','minimalOrmEsmReplayFiles','fullSdkEsmFiles']){assert.ok(Array.isArray(fixture[key])&&fixture[key].every(n=>safe(n)&&Object.hasOwn(payload,n)));assert.deepEqual(fixture[key],provider[key]);}
 for(const [folder,format]of [['legacy/v024/','moontxnwitness-frozen-orm-runtime/v1'],['legacy/v025/','moontxnwitness-frozen-public-runtime/v1']]){
  assert.ok(payload[folder+'manifest.json'],'Original nested runtime missing');const old=JSON.parse(payload[folder+'manifest.json']);assert.equal(old.format,format);assert.ok(plain(old.files));
  for(const [name,entry]of Object.entries(old.files)){assert.ok(safe(name)&&Object.hasOwn(payload,folder+name));const bytes=payload[folder+name];assert.deepEqual({bytes:bytes.length,sha256:sha(bytes)},entry);}
 }
 assert.equal(provider.existingCases.length,21);assert.equal(provider.modelCases.length,14);
 const originalRows=[...provider.existingCases.map(r=>({...r,requestOptions:r.requestOptions??{},operation:r.operation??'analyze'})),...provider.modelCases.map(r=>({...r,type:'model-classification',operation:'classify-models',requestOptions:r.options}))];
 assert.equal(new Set(fixture.cases.map(r=>r.name)).size,35,'Duplicate original family');
 for(let i=0;i<35;i++){
  const row=fixture.cases[i],original=originalRows[i];assert.ok(safe(row.name)&&!row.name.includes('/'));
  for(const key of ['name','type','operation'])assert.equal(row[key],original[key]);assert.deepEqual(row.requestOptions,original.requestOptions);
  const bytes={};for(const key of ['input','report','capsule','producerReplay'])bytes[key]=bound(row[key],192*1024*1024);
  assert.deepEqual({bytes:bytes.input.length,sha256:sha(bytes.input)},provider.bindings['package/'+original.inputPath],'Original input changed');
  const report=JSON.parse(bytes.report),capsule=JSON.parse(bytes.capsule),replay=JSON.parse(bytes.producerReplay);assert.equal(replay.valid,true,'Original producer replay failed');assert.equal(report.status,row.expectedStatus);
  if(['orm-profile','category-classification','model-classification'].includes(row.type)){
   const formats=row.type==='orm-profile'?['moontxnwitness-orm-profile-report/v1','moontxnwitness-orm-profile/v1']:row.type==='category-classification'?['moontxnwitness-classification-report/v1','moontxnwitness-classification/v1']:['moontxnwitness-isolation-model-report/v1','moontxnwitness-isolation-models/v1'];
   assert.equal(report.format,formats[0]);assert.equal(capsule.format,formats[1]);const reportVersion=row.type==='orm-profile'?report.engineVersion:report.engine?.version,capsuleVersion=row.type==='orm-profile'?capsule.engineVersion:capsule.engine?.version;assert.equal(reportVersion,VERSION);assert.equal(capsuleVersion,VERSION);assert.deepEqual(replay.report,report);
  }
 }
 payload['origin.json']=encode({sourceCommit:SOURCE,fixtureManifestSha256:expectedFixtureSha256,providerSha256:fixture.providerSha256,publicPackages:fixture.publicPackages,checksumAsset:fixture.checksumAsset,registryPackage:fixture.registryPackage,publicationReceiptSha256:fixture.publicationReceiptSha256,publisherReferenceSha256:fixture.publisherReferenceSha256,transportReceiptSha256:fixture.transportReceiptSha256,externalBindingsSha256:fixture.externalBindingsSha256,producerBuild:fixture.producerBuild,existingFamilies:21,modelCases:14,totalFamilies:35,scope:'Exact original anonymously downloaded public26 ESM and licence bytes, externally pinned genuine 35-family producer. No author dist, SDK execution here or header rewriting.'});
 const manifest={format:'moontxnwitness-frozen-public-runtime/v1',version:VERSION,sourceCommit:SOURCE,moduleExecution:'fixed-esm-worker/1',actualPublishedProducer:true,rawEsmIdentityPreserved:true,headerRewriting:false,authorDistRead:false,fixtureManifestSha256:expectedFixtureSha256,files:Object.fromEntries(Object.entries(payload).map(([name,bytes])=>[name,{bytes:bytes.length,sha256:sha(bytes)}]))};
 const manifestRaw=encode(manifest),workerPath=resolve(root,'cmd/legacy-v026-worker.mjs'),binding=resolve(root,'cmd/legacy-v026-binding.mjs'),target=resolve(root,'cmd/legacy/v026');
 for(const p of [workerPath,binding]){const info=lstatSync(p);assert.ok(info.isFile()&&!info.isSymbolicLink(),'Regular fixed worker/binding required');}
 const worker=readFileSync(workerPath),oldBinding=readFileSync(binding,'utf8');assert.ok(oldBinding.includes('manifestSha256:null,workerSha256:null'),'Freeze only the unready framework binding');
 if(existsSync(resolve(root,'cmd/legacy')))regularRoot(resolve(root,'cmd/legacy'));
 assert.equal(existsSync(target),false,'Never overwrite a frozen public runtime');
 // All producer/header/byte checks above complete before writing any runtime file.
 mkdirSync(target,{recursive:true});for(const [name,bytes]of Object.entries(payload)){const p=resolve(target,name);mkdirSync(dirname(p),{recursive:true});writeFileSync(p,bytes,{flag:'wx'});}writeFileSync(resolve(target,'manifest.json'),manifestRaw,{flag:'wx'});
 const pin={version:VERSION,sourceCommit:SOURCE,manifestSha256:sha(manifestRaw),workerSha256:sha(worker)};
 writeFileSync(binding,'// Exact genuine public26 ESM runtime; generated from the externally pinned producer manifest.\nexport const PUBLIC_V026=Object.freeze('+JSON.stringify(pin)+');\n');
 return {frozen:true,actualPublicRuntime:true,sourceCommit:SOURCE,fixtureManifestSha256:expectedFixtureSha256,...pin,files:Object.keys(payload).length,existingFamilies:21,modelCases:14,totalFamilies:35,originalModuleBytesUnchanged:true,producerSdkExecutedHere:false};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){const a=process.argv.slice(2);assert.ok(a.length===6&&a[0]==='--fixtures'&&a[2]==='--expected-fixture-sha256'&&a[4]==='--root','Usage: --fixtures GENUINE_PUBLIC26_OUTPUT --expected-fixture-sha256 EXTERNAL_SHA --root FRAMEWORK_ROOT');console.log(JSON.stringify(freezePublicV026(a[1],a[3],a[5])));}
