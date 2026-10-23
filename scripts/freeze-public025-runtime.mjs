// Freeze only genuinely published25 producer outputs with an external manifest pin.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync,existsSync,lstatSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const SOURCE='6b3434b19fc080bc9a3a9518950021061d2849dd',sha=b=>createHash('sha256').update(b).digest('hex'),encode=x=>Buffer.from(JSON.stringify(x,null,2)+'\n');
const safe=n=>typeof n==='string'&&n&&!n.includes('\\')&&!n.includes(':')&&!n.startsWith('/')&&n.split('/').every(s=>s&&s!=='.'&&s!=='..');
export function freezePublicV025(fixtureDirectory,expectedFixtureSha256,repository){
 assert.match(expectedFixtureSha256,/^[0-9a-f]{64}$/);const base=resolve(fixtureDirectory),root=resolve(repository);
 function read(name,limit=32*1024*1024){assert.ok(safe(name));let cursor=base;for(const part of name.split('/')){cursor=resolve(cursor,part);assert.equal(lstatSync(cursor).isSymbolicLink(),false);}const info=lstatSync(cursor);assert.ok(info.isFile()&&info.size<=limit);const bytes=readFileSync(cursor);assert.equal(bytes.length,info.size);return bytes;}
 const raw=read('manifest.json',4*1024*1024);assert.equal(sha(raw),expectedFixtureSha256,'Externally recorded genuine25 fixture manifest differs');const fixture=JSON.parse(raw);
 assert.equal(fixture.format,'moontxnwitness-actual-public-producer-fixtures/v1');assert.equal(fixture.producerEngineVersion,'0.2.5');assert.equal(fixture.sourceCommit,SOURCE);assert.equal(fixture.expectedSourceCommit,SOURCE);
 for(const k of ['actualPublishedProducer','rawEsmIdentityPreserved','originalProducerReplaysPassed'])assert.equal(fixture[k],true);
 for(const k of ['headerRewriting','authorDistRead','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(fixture[k],false);
 assert.equal(fixture.cases.length,21);assert.equal(fixture.existingFamilies,15);assert.equal(fixture.categoryCases,6);
 const originRaw=read('provider-origin.json',4*1024*1024);assert.equal(sha(originRaw),fixture.providerSha256);const provider=JSON.parse(originRaw);
 assert.equal(provider.format,'moontxnwitness-v025-provider/v1');assert.equal(provider.sourceCommit,SOURCE);assert.equal(provider.actualPublishedProducer,true);assert.equal(provider.authorDistRead,false);
 assert.deepEqual(Object.keys(fixture.producerFiles).sort(),Object.keys(provider.runtime).sort());
 const files={};const payload={};
 for(const [name,entry]of Object.entries(fixture.producerFiles)){
  assert.ok(safe(name));assert.equal(entry.file,'producer-runtime/'+name);const bytes=read(entry.file);assert.deepEqual({bytes:bytes.length,sha256:sha(bytes)},provider.runtime[name]);assert.equal(bytes.length,entry.bytes);assert.equal(sha(bytes),entry.sha256);payload[name]=bytes;
 }
 for(const required of ['core.mjs','orm-profile.mjs','classification.mjs','legacy-v024.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt'])assert.ok(payload[required]);
 assert.equal(JSON.parse(payload['build-manifest.json']).version,'0.2.5');assert.equal(sha(payload['core.mjs']),fixture.producerBuild.coreSha256);
 for(const row of fixture.cases)for(const key of ['input','report','capsule','producerReplay']){const entry=row[key];const bytes=read(entry.file,192*1024*1024);assert.equal(bytes.length,entry.bytes);assert.equal(sha(bytes),entry.sha256);}
 payload['origin.json']=encode({sourceCommit:SOURCE,fixtureManifestSha256:expectedFixtureSha256,providerSha256:fixture.providerSha256,publicPackages:fixture.publicPackages,checksumAsset:fixture.checksumAsset,registryPackage:fixture.registryPackage,publicationReceiptSha256:fixture.publicationReceiptSha256,publisherReferenceSha256:fixture.publisherReferenceSha256,transportReceiptSha256:fixture.transportReceiptSha256,producerBuild:fixture.producerBuild,scope:'Exact anonymously downloaded public25 ESM and licence bytes; no author dist or header rewriting.'});
 const manifest={format:'moontxnwitness-frozen-public-runtime/v1',version:'0.2.5',sourceCommit:SOURCE,moduleExecution:'fixed-esm-worker/1',actualPublishedProducer:true,rawEsmIdentityPreserved:true,headerRewriting:false,authorDistRead:false,fixtureManifestSha256:expectedFixtureSha256,files:Object.fromEntries(Object.entries(payload).map(([name,bytes])=>[name,{bytes:bytes.length,sha256:sha(bytes)}]))};
 const manifestRaw=encode(manifest),worker=readFileSync(resolve(root,'cmd/legacy-v025-worker.mjs')),binding=resolve(root,'cmd/legacy-v025-binding.mjs'),target=resolve(root,'cmd/legacy/v025');
 assert.equal(existsSync(target),false,'Never overwrite a frozen public runtime');const oldBinding=readFileSync(binding,'utf8');assert.ok(oldBinding.includes('manifestSha256:null,workerSha256:null'),'Freeze only the unready framework binding');
 mkdirSync(target,{recursive:true});for(const [name,bytes]of Object.entries(payload)){const p=resolve(target,name);mkdirSync(dirname(p),{recursive:true});writeFileSync(p,bytes,{flag:'wx'});}writeFileSync(resolve(target,'manifest.json'),manifestRaw,{flag:'wx'});
 const pin={version:'0.2.5',sourceCommit:SOURCE,manifestSha256:sha(manifestRaw),workerSha256:sha(worker)};
 writeFileSync(binding,'// Exact genuine public25 ESM runtime; generated from the externally pinned producer manifest.\nexport const PUBLIC_V025=Object.freeze('+JSON.stringify(pin)+');\n');
 return {frozen:true,actualPublicRuntime:true,sourceCommit:SOURCE,fixtureManifestSha256:expectedFixtureSha256,...pin,files:Object.keys(payload).length,originalModuleBytesUnchanged:true};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){const a=process.argv.slice(2);assert.ok(a.length===6&&a[0]==='--fixtures'&&a[2]==='--expected-fixture-sha256'&&a[4]==='--root','Usage: --fixtures GENUINE_PUBLIC25_OUTPUT --expected-fixture-sha256 EXTERNAL_SHA --root FRAMEWORK_ROOT');console.log(JSON.stringify(freezePublicV025(a[1],a[3],a[5])));}
