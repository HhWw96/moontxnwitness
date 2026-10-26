// Freeze exact genuine public027 bytes after its externally pinned producer run.
// This verifier does not import any producer SDK.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync,lstatSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const SOURCE='c10b06c5bfcabd1f40b0ff0099717072a816ec74',VERSION='0.2.7';
const sha=x=>createHash('sha256').update(x).digest('hex'),encode=x=>Buffer.from(JSON.stringify(x,null,2)+'\n');
const safe=n=>typeof n==='string'&&n&&!n.includes(String.fromCharCode(92))&&!n.includes(':')&&!n.includes('\0')&&!n.startsWith('/')&&n.split('/').every(s=>s&&s!=='.'&&s!=='..');
const digest=n=>typeof n==='string'&&/^[0-9a-f]{64}$/.test(n),plain=n=>n!==null&&typeof n==='object'&&!Array.isArray(n);
export function freezePublicV027(fixtures,expectedFixtureSHA,repository){
 assert.ok(digest(expectedFixtureSHA)&&expectedFixtureSHA!=='0'.repeat(64));const base=resolve(fixtures),root=resolve(repository);
 const regular=p=>{const s=lstatSync(p);assert.ok(s.isDirectory()&&!s.isSymbolicLink());};regular(base);regular(root);regular(resolve(root,'cmd'));
 const read=(name,limit=128*1024*1024)=>{assert.ok(safe(name));let p=base;for(const part of name.split('/')){p=resolve(p,part);assert.equal(lstatSync(p).isSymbolicLink(),false);}const s=lstatSync(p);assert.ok(s.isFile()&&s.size<=limit);const b=readFileSync(p);assert.equal(s.size,b.length);return b;};
 const bound=row=>{assert.ok(plain(row)&&safe(row.file)&&digest(row.sha256)&&Number.isSafeInteger(row.bytes)&&row.bytes>=0);const b=read(row.file);assert.equal(b.length,row.bytes);assert.equal(sha(b),row.sha256);return b;};
 const raw=read('manifest.json',4*1024*1024);assert.equal(sha(raw),expectedFixtureSHA);const f=JSON.parse(raw);
 assert.equal(f.format,'moontxnwitness-actual-public-producer-fixtures/v1');assert.equal(f.producerEngineVersion,VERSION);assert.equal(f.sourceCommit,SOURCE);assert.equal(f.expectedSourceCommit,SOURCE);
 for(const key of ['actualPublishedProducer','rawEsmIdentityPreserved','entirePublicDistPreserved','originalProducerReplaysPassed','originalProducerVerificationsPassed'])assert.equal(f[key],true);
 for(const key of ['authorDistRead','headerRewriting','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(f[key],false);
 assert.equal(f.existingFamilies,35);assert.equal(f.modelProfileCases,11);assert.equal(f.cases.length,46);assert.equal(new Set(f.cases.map(r=>r.name)).size,46);
 const providerRaw=read('provider-origin.json',4*1024*1024);assert.equal(sha(providerRaw),f.providerSha256);const p=JSON.parse(providerRaw);
 assert.equal(p.format,'moontxnwitness-v027-provider/v1');assert.equal(p.version,VERSION);assert.equal(p.sourceCommit,SOURCE);assert.equal(p.cases.length,46);assert.deepEqual(p.buildManifest,f.producerBuild);
 assert.deepEqual(Object.keys(f.producerFiles).sort(),Object.keys(p.runtime).sort());const names=Object.keys(f.producerFiles);assert.equal(names.length,103);assert.ok(names.every(safe));assert.equal(new Set(names.map(n=>n.toLowerCase())).size,103);assert.ok(!names.includes('origin.json')&&!names.includes('manifest.json'));
 const payload={};let total=0;
 for(const name of names){const entry=f.producerFiles[name];assert.equal(entry.file,'producer-runtime/'+name);const b=bound(entry);assert.ok(b.length<=32*1024*1024);total+=b.length;assert.ok(total<=128*1024*1024);assert.deepEqual({bytes:b.length,sha256:sha(b)},p.runtime[name]);assert.deepEqual(p.runtime[name],p.bindings['runtime/'+name]);payload[name]=b;}
 for(const name of ['core.mjs','capture-core.mjs','sdk.mjs','model-profile.mjs','orm-profile.mjs','classification.mjs','classification-models.mjs','legacy-v024.mjs','legacy-v025.mjs','legacy-v026.mjs','legacy-v026-runtime.mjs','legacy-v026-worker.mjs','legacy-v026-binding.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt'])assert.ok(payload[name]?.length,'Missing fixed public027 closure '+name);
 const build=JSON.parse(payload['build-manifest.json']);assert.equal(build.version,VERSION);assert.deepEqual(build,p.buildManifest);assert.equal(build.sourceSha256,'82d1bff2dbdbfba5a09b11095b4aa348fa445c36f70535f30fd52b4f9ab47518');assert.equal(sha(payload['core.mjs']),build.coreSha256);assert.equal(sha(payload['capture-core.mjs']),build.captureCoreSha256);
 const versions={'orm-profile':r=>r.engineVersion,'category-classification':r=>r.engine?.version,'model-classification':r=>r.engine?.version,'model-profile':r=>r.engine?.version};
 for(let i=0;i<46;i++){
  const row=f.cases[i],old=p.cases[i];assert.equal(row.name,old.name);assert.equal(row.type,old.type);assert.equal(row.operation,old.operation);assert.deepEqual(row.requestOptions,old.requestOptions);
  const input=bound(row.input),report=JSON.parse(bound(row.report)),capsule=JSON.parse(bound(row.capsule)),replay=JSON.parse(bound(row.producerReplay)),verification=JSON.parse(bound(row.producerVerification));
  assert.deepEqual({bytes:input.length,sha256:sha(input)},p.bindings['package/'+old.inputPath]);assert.equal(row.inputOrigin.originalInputUnchanged,true);assert.equal(row.inputOrigin.databaseExecutedHere,false);assert.deepEqual(row.inputOrigin.preservedPublishedInputOrigin,old.inputOrigin);
  assert.equal(replay.valid,true);assert.equal(verification.valid,true);assert.equal(row.expectedStatus,report.status);assert.equal(capsule.engine?.version??capsule.engineVersion,VERSION);
  if(Object.hasOwn(versions,row.type)){assert.equal(versions[row.type](report),VERSION);assert.deepEqual(replay.report,report);}
 }
 payload['origin.json']=encode({sourceCommit:SOURCE,fixtureManifestSha256:expectedFixtureSHA,providerSha256:f.providerSha256,publicPackage:f.publicPackage,outerArtifact:f.outerArtifact,producerBuild:build,totalFamilies:46,existingFamilies:35,modelProfileFamilies:11,rawEsmIdentityPreserved:true,headerRewriting:false,authorDistRead:false,scope:'Exact original top102 dist plus root LICENSE from the frozen anonymously downloaded public027 portable package; original nested modules and notices remain raw. No next-version consumer acceptance or new DB run.'});
 const manifest={format:'moontxnwitness-frozen-public-runtime/v1',version:VERSION,sourceCommit:SOURCE,moduleExecution:'fixed-esm-worker/1',actualPublishedProducer:true,rawEsmIdentityPreserved:true,headerRewriting:false,authorDistRead:false,fixtureManifestSha256:expectedFixtureSHA,files:Object.fromEntries(Object.entries(payload).map(([name,b])=>[name,{bytes:b.length,sha256:sha(b)}]))};
 const manifestRaw=encode(manifest),target=resolve(root,'cmd/legacy/v027'),binding=resolve(root,'cmd/legacy-v027-binding.mjs'),worker=resolve(root,'cmd/legacy-v027-worker.mjs');
 const binfo=lstatSync(binding),winfo=lstatSync(worker);assert.ok(binfo.isFile()&&!binfo.isSymbolicLink()&&winfo.isFile()&&!winfo.isSymbolicLink());assert.ok(readFileSync(binding,'utf8').includes('manifestSha256:null,workerSha256:null'));assert.equal(existsSync(target),false,'Never overwrite a frozen public runtime');
 const pin={version:VERSION,sourceCommit:SOURCE,manifestSha256:sha(manifestRaw),workerSha256:sha(readFileSync(worker))};
 // Every original byte/header/provenance check precedes the first runtime write.
 mkdirSync(target,{recursive:true});for(const [name,b]of Object.entries(payload)){const q=resolve(target,name);mkdirSync(dirname(q),{recursive:true});writeFileSync(q,b,{flag:'wx'});}writeFileSync(resolve(target,'manifest.json'),manifestRaw,{flag:'wx'});
 writeFileSync(binding,'// Exact genuine public027 ESM, bound to the original producer and fixed worker.\nexport const PUBLIC_V027=Object.freeze('+JSON.stringify(pin)+');\n');
 return {frozen:true,actualPublicRuntime:true,...pin,fixtureManifestSha256:expectedFixtureSHA,files:Object.keys(payload).length,installedFiles:Object.keys(payload).length+1,totalFamilies:46,originalModuleBytesUnchanged:true,producerSDKExecutedHere:false};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){const a=process.argv.slice(2);assert.ok(a.length===6&&a[0]==='--fixtures'&&a[2]==='--expected-fixture-sha256'&&a[4]==='--root');console.log(JSON.stringify(freezePublicV027(a[1],a[3],a[5])));}