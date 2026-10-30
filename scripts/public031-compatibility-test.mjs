// Verify compatibility against the exact published 0.3.1 portable runtime.
// No historical source tree or rebuilt historical core is created.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,linkSync,copyFileSync,unlinkSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const root=resolve(import.meta.dirname,'..'),args=process.argv.slice(2),options={};
for(let index=0;index<args.length;index+=2){
  assert.ok(['--runtime','--producer-runtime','--output-root'].includes(args[index]));
  assert.ok(args[index+1]);assert.equal(options[args[index]],undefined);options[args[index]]=resolve(args[index+1]);
}
const runtime=options['--runtime']||resolve(root,'dist');
const cached=options['--producer-runtime']||(existsSync(resolve(root,'artifacts/compat-v031/runtime/sdk.mjs'))?
  resolve(root,'artifacts/compat-v031/runtime'):resolve(runtime,'legacy/v031'));
const output=options['--output-root']||resolve(root,'artifacts');mkdirSync(output,{recursive:true});
const {PUBLIC031:PIN}=await import(pathToFileURL(resolve(runtime,'legacy-v031-binding.mjs')).href);
const sha=raw=>createHash('sha256').update(raw).digest('hex');
const read=path=>readFileSync(resolve(root,path),'utf8');
let checks=0;const cases=[];
function check(name,run){run();checks++;cases.push({name,passed:true});}
check('public portable archive and commit pins',()=>{
  assert.equal(PIN.version,'0.3.1');
  assert.equal(PIN.archiveSha256,'05ce492f51c75f99dc49a1d95658d0d128102913cab6c806956493f1b79b2597');
  assert.equal(PIN.sourceCommit,'44e768d0bdd4a51b2c41179494798ea89f4cc57f');
});
check('cached producer and installed compatibility runtime have exact published bytes',()=>{
  for(const [name,expected] of Object.entries(PIN.files)){
    for(const base of [cached,resolve(runtime,'legacy/v031')]){
      const raw=readFileSync(resolve(base,name));
      assert.equal(raw.length,expected.bytes,name);assert.equal(sha(raw),expected.sha256,name);
    }
  }
});
const bridge=await import(pathToFileURL(resolve(runtime,'legacy-v031.mjs')).href);
check('installed public031 inventory verification',()=>assert.equal(resolve(bridge.verifyPublic031Runtime()),resolve(runtime,'legacy/v031')));
// Import only after independently checking every cached producer member.
const original=await import(pathToFileURL(resolve(cached,'sdk.mjs')).href);
const oldEvidence=await import(pathToFileURL(resolve(cached,'evidence.mjs')).href);
const current=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href),newEvidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href);
const currentVersion=current.version();
check('published producer and current consumer versions',()=>{assert.equal(original.version(),'0.3.1');assert.equal(current.version(),currentVersion);assert.notEqual(currentVersion,'0.3.1');});
for(const fixture of ['examples/write-skew.json','examples/consistent.json']){
  const source=read(fixture),report=original.analyzeWithOptions(source);
  check(fixture+' public031 SDK report replay',()=>assert.equal(current.replayReport(source,report).valid,true));
  check(fixture+' public031 capsule replay',()=>assert.equal(newEvidence.replayCapsule(oldEvidence.makeCapsule(source,report)).valid,true));
  check(fixture+' changed conclusion refused',()=>{const changed=structuredClone(report);changed.status=report.status==='violation'?'consistent':'violation';assert.equal(current.replayReport(source,changed).valid,false);});
}
for(const fixture of ['examples/list-cycle.json','examples/relation-source-closure.json','fixtures/classification-v3/source-closed-noisy-g2.json']){
  const source=read(fixture),report=original.analyzeV3(source);
  check(fixture+' public031 typed capture report',()=>assert.equal(current.verifyV3(source,report).valid,true));
  check(fixture+' public031 source capsule',()=>assert.equal(current.replayCapsuleV3(original.makeCapsuleV3(source,report)).valid,true));
  check(fixture+' report source tamper refused',()=>{const altered=structuredClone(report);altered.normalized.status='forged';assert.equal(current.verifyV3(source,altered).valid,false);});
}
for(const fixture of ['fixtures/classification-models-v3/list-skew.json','fixtures/classification-models-v3/empty-register.json']){
  const source=read(fixture),report=original.classifyModelsV3(source);
  check(fixture+' public031 model report',()=>assert.equal(current.verifyModelsClassificationV3(source,report).valid,true));
  check(fixture+' public031 model capsule',()=>assert.equal(current.replayModelsClassificationCapsuleV3(original.makeModelsClassificationCapsuleV3(source)).valid,true));
  check(fixture+' forged model judgment refused',()=>assert.equal(current.verifyModelsClassificationV3(source,{...report,status:'forged'}).valid,false));
}
const trace=read('fixtures/classification-v3/source-closed-noisy-g2.json'),analysis=original.analyzeV3(trace);
const category=original.classifyV3(trace),reductionOptions={category:'G2-item',maxChecks:0};
check('public031 category report',()=>assert.equal(current.verifyClassificationV3(trace,category).valid,true));
check('public031 category capsule',()=>assert.equal(current.replayClassificationCapsuleV3(original.makeClassificationCapsuleV3(trace)).valid,true));
check('public031 category-preserving reduction capsule',()=>assert.equal(current.replayClassificationCapsuleV3(original.makeClassificationReductionCapsuleV3(trace,reductionOptions)).valid,true));
check('public031 diagnosis',()=>assert.equal(current.verifyDiagnosisV3(trace,original.diagnoseV3(trace)).valid,true));
check('public031 execution capsule',()=>assert.equal(current.replayExecutionCapsuleV3(original.makeExecutionCapsuleV3(trace)).valid,true));
check('public031 cycle explanation',()=>{
  const explanation=original.explainRegisterCycleV3(trace,analysis);
  assert.equal(current.verifyRegisterCycleExplanationV3(trace,analysis,explanation).valid,true);
});
const ormSource=read('verification/configured-user-profile/v024-initial/producer-first/profile-source.json');
check('public031 configured ORM report and capsule',()=>{
  const report=original.analyzeOrmProfileV3(ormSource);
  assert.equal(current.verifyOrmProfileV3(ormSource,report).valid,true);
  assert.equal(current.replayOrmProfileCapsuleV3(original.makeOrmProfileCapsuleV3(ormSource)).valid,true);
});
const modelSource=read('verification/model-profile-v3/v027-initial/database/list-write-skew/profile-source.json');
check('public031 configured model report and capsule',()=>{
  const report=original.analyzeModelProfileV3(modelSource);
  assert.equal(current.verifyModelProfileV3(modelSource,report).valid,true);
  assert.equal(current.replayModelProfileCapsuleV3(original.makeModelProfileCapsuleV3(modelSource)).valid,true);
});
check('031 route selected by documented header',()=>{
  const routed=bridge.routeLegacyV031('verify-v3',[trace,analysis],currentVersion);
  assert.equal(routed.matched,true);assert.equal(routed.result.valid,true);
});
check('current engine bypasses 031 worker',()=>assert.equal(bridge.routeLegacyV031('verify-v3',[trace,analysis],'0.3.1').matched,false));
check('business version cannot select legacy runtime',()=>assert.equal(bridge.routeLegacyV031('verify-v3',[trace,{version:'unknown',schemaVersion:3,business:{version:'0.3.1'}}],currentVersion).matched,false));
check('unknown method cannot select a runtime',()=>assert.equal(bridge.routeLegacyV031('select-an-executable',[trace,analysis],currentVersion).matched,false));
check('mixed report and capsule engine headers are not accepted as 031',()=>{
  const capsule=JSON.parse(original.makeCapsuleV3(trace,analysis));capsule.reportText=JSON.stringify({...analysis,version:'0.3.0'});
  assert.equal(bridge.routeLegacyV031('replay-v3',[JSON.stringify(capsule)],currentVersion).matched,false);
});

const work=resolve(output,'public031-corruption');mkdirSync(work,{recursive:true});
const isolatedRoot=mkdtempSync(resolve(work,'run-'));
for(const name of ['legacy-v031.mjs','legacy-v031-binding.mjs','legacy-v028-policy.mjs','legacy-v028-binding.mjs'])
  copyFileSync(resolve(runtime,name),resolve(isolatedRoot,name));
// Hardlinks avoid a second opaque runtime allocation. The mutated member below
// is copied independently, so the immutable cache and installed dist stay intact.
for(const name of Object.keys(PIN.files)){
  const source=resolve(cached,name),destination=resolve(isolatedRoot,'legacy/v031',name);
  mkdirSync(dirname(destination),{recursive:true});
  if(name==='core.mjs')copyFileSync(source,destination);else linkSync(source,destination);
}
const isolated=await import(pathToFileURL(resolve(isolatedRoot,'legacy-v031.mjs')).href);
check('isolated runtime initially matches published inventory',()=>isolated.verifyPublic031Runtime());
const installedCore=resolve(runtime,'legacy/v031/core.mjs'),cachedCore=resolve(cached,'core.mjs');
const originalCore=readFileSync(cachedCore),originalHash=sha(originalCore),mutated=resolve(isolatedRoot,'legacy/v031/core.mjs');
check('tampered public031 runtime inventory is refused',()=>{
  writeFileSync(mutated,'corrupted test runtime; must never execute');assert.throws(()=>isolated.verifyPublic031Runtime(),/differs/);
});
check('matching 031 request fails closed after runtime tamper',()=>{
  const routed=isolated.routeLegacyV031('verify-v3',[trace,analysis],currentVersion);
  assert.equal(routed.matched,true);assert.equal(routed.result.valid,false);assert.match(routed.result.reason,/public031-unavailable-or-refused/);
});
check('published cache and installed runtime remain unchanged',()=>{assert.equal(sha(readFileSync(cachedCore)),originalHash);assert.equal(sha(readFileSync(installedCore)),originalHash);});
check('unlisted runtime member is refused',()=>{
  writeFileSync(mutated,originalCore);const added=resolve(isolatedRoot,'legacy/v031/unlisted.mjs');writeFileSync(added,'// unexpected');
  assert.throws(()=>isolated.verifyPublic031Runtime(),/Unexpected/);unlinkSync(added);
});
const receipt={passed:true,checks,publicVersion:'0.3.1',currentVersion,producerArchiveSha256:PIN.archiveSha256,
  producerSourceCommit:PIN.sourceCommit,publishedMemberCount:Object.keys(PIN.files).length,usesPublishedRuntimeOnly:true,
  historicalSourceSnapshotCreated:false,cases};
writeFileSync(resolve(output,'public031-compatibility-validation.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));
