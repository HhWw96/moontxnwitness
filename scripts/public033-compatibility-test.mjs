// Verify a fixed public 0.3.3 runtime against the installed current SDK.
// The producer is assembled only by the installed fixed compatibility loader.
// No historical source tree, arbitrary producer path or rebuilt old core is used.
import assert from 'node:assert/strict';
import {PUBLIC033_GROUPS,PUBLIC033_COMMON,validatePublic033Group} from './public033-compatibility-groups.mjs';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,linkSync,copyFileSync,unlinkSync,lstatSync,readdirSync,statfsSync} from 'node:fs';
import {resolve,dirname,relative,isAbsolute} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';

const root=resolve(import.meta.dirname,'..'),args=process.argv.slice(2),options={};
for(let index=0;index<args.length;index+=2){
 assert.ok(['--runtime','--output-root','--group'].includes(args[index]),'Unknown compatibility option');
 assert.ok(args[index+1],'Missing compatibility option value');
 assert.equal(options[args[index]],undefined,'Duplicate compatibility option');
 options[args[index]]=args[index]==='--group'?args[index+1]:resolve(args[index+1]);
}
const group=options['--group']||'all';
assert(group==='all'||Object.hasOwn(PUBLIC033_GROUPS,group),'Unknown fixed compatibility group');
const runtime=options['--runtime']||resolve(root,'dist');
const output=options['--output-root']||resolve(root,'artifacts');mkdirSync(output,{recursive:true});
const storage=statfsSync(output);assert(Number(storage.bavail)*Number(storage.bsize)>=500*1024*1024,'Less than 500 MiB available');
const run=mkdtempSync(resolve(output,'public033-compatibility-'));
const temporary=resolve(run,'temporary');mkdirSync(temporary);
// Current workers and their private assemblies must remain on the chosen volume.
process.env.TEMP=temporary;process.env.TMP=temporary;process.env.TMPDIR=temporary;
const sha=raw=>createHash('sha256').update(raw).digest('hex');
const read=path=>readFileSync(resolve(root,path),'utf8');
const finalCommit='79f03ecb3b7764b03bcb6ef99bdef38ce42e37bd'; // Verified published source and downloaded runtime bytes.
const operations=new Set(),cases=[],preconditions=[],postconditions=[];let original,current,bridge,PIN,producerRoot,currentVersion,producerInventoryVerified=false,sourcePoolVerifiedUnchanged=false;
const policyOperations=['verify-v1v2','replay-v1v2','verify-v3','replay-v3','verify-orm','replay-orm',
 'verify-classification','replay-classification','verify-models','replay-models','verify-model-profile',
 'replay-model-profile','verify-diagnosis','replay-execution','verify-cycle'];
function within(base,name){const path=resolve(base,name),rel=relative(base,path);assert(rel&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..\\')&&!rel.startsWith('../'),'Path leaves its installed root');return path;}
// The root directory is allowed only for listing; member resolution stays strict.
function inventory(base,prefix=''){
 const values=[];
 for(const entry of readdirSync(prefix?within(base,prefix):base,{withFileTypes:true})){
  const name=prefix+entry.name,path=within(base,name),st=lstatSync(path);
  assert(!st.isSymbolicLink(),'Linked runtime member');
  if(st.isDirectory())values.push(...inventory(base,name+'/'));
  else{assert(st.isFile(),'Unexpected runtime entry');values.push(name);}
 }
 return values.sort();
}
function selected(name){return group==='all'||PUBLIC033_COMMON.includes(name)||PUBLIC033_GROUPS[group].includes(name);}
async function check(name,fn){
 if(!selected(name))return;
 const destination=group==='all'?cases:PUBLIC033_COMMON.slice(0,3).includes(name)?preconditions:PUBLIC033_COMMON[3]===name?postconditions:cases;
 try{await fn();destination.push({name,passed:true});}catch(error){destination.push({name,passed:false,error:error.message});throw error;}
}
function valid(operation,result){assert.equal(result.valid,true,operation+': '+JSON.stringify(result));operations.add(operation);}
function keep(name,report,capsule){
 const parent=resolve(run,'producer-results');mkdirSync(parent,{recursive:true});
 if(report!==undefined)writeFileSync(resolve(parent,name+'.report.json'),JSON.stringify(report,null,2)+'\n');
 if(capsule!==undefined)writeFileSync(resolve(parent,name+'.capsule.json'),typeof capsule==='string'?capsule:JSON.stringify(capsule));
}
function memberHash(base,name){const raw=readFileSync(within(base,name));return {bytes:raw.length,sha256:sha(raw)};}
function verifyInventory(base){
 assert.deepEqual(inventory(base),Object.keys(PIN.files).sort(),'Constructed full inventory differs from fixed PIN');
 for(const [name,spec]of Object.entries(PIN.files))assert.deepEqual(memberHash(base,name),{bytes:spec.bytes,sha256:spec.sha256},name);
}
const sources=new Map();let sourceBefore,coreBefore,producerCoreBefore;
function sourceHashes(){return Object.fromEntries([...sources].map(([name,spec])=>{const found=memberHash(runtime,name);assert.deepEqual(found,{bytes:spec.bytes,sha256:spec.sha256},name);return [name,found.sha256];}));}
async function isolate(label){
 const isolatedRoot=mkdtempSync(resolve(run,label+'-'));
 for(const name of ['legacy-v033.mjs','legacy-v033-binding.mjs','legacy-v028-policy.mjs','legacy-v028-binding.mjs','compact-runtime.mjs'])
  copyFileSync(within(runtime,name),within(isolatedRoot,name));
 const coreSource=PIN.files['core.mjs'].source;
 for(const [name]of sources){
  const from=within(runtime,name),to=within(isolatedRoot,name);mkdirSync(dirname(to),{recursive:true});
  // Only this independent copy is mutated. All other original bytes are linked.
  if(name===coreSource)copyFileSync(from,to);
  else try{linkSync(from,to);}catch(error){if(error.code==='EXDEV'||error.code==='ENOTSUP'||error.code==='EPERM')copyFileSync(from,to);else throw error;}
 }
 const module=await import(pathToFileURL(within(isolatedRoot,'legacy-v033.mjs')).href);
 return {root:isolatedRoot,module,coreSource:within(isolatedRoot,coreSource)};
}
let suiteError;
try{
 ({PUBLIC033:PIN}=await import(pathToFileURL(within(runtime,'legacy-v033-binding.mjs')).href));
 await check('fixed public033 final commit and archive identity',()=>{
  assert.match(finalCommit??'',/^[a-f0-9]{40}$/,'Final public033 release commit has not been bound yet');
  assert.equal(PIN.version,'0.3.3');assert.equal(PIN.sourceCommit,finalCommit);
  assert.match(PIN.archiveSha256,/^[a-f0-9]{64}$/);assert.match(PIN.componentSha256,/^[a-f0-9]{64}$/);
  assert(Object.keys(PIN.files).length>0);assert(PIN.files['core.mjs']);assert(PIN.files['sdk.mjs']);
 });
 bridge=await import(pathToFileURL(within(runtime,'legacy-v033.mjs')).href);
 await check('producer comes only from the fixed installed complete snapshot',()=>{
  producerRoot=resolve(bridge.verifyPublic033Runtime());assert.notEqual(producerRoot,resolve(runtime));
  verifyInventory(producerRoot);producerInventoryVerified=true;
  for(const spec of Object.values(PIN.files)){
   if(sources.has(spec.source))assert.deepEqual(sources.get(spec.source),spec,'Shared source identity differs');
   else sources.set(spec.source,spec);
  }
  sourceBefore=sourceHashes();coreBefore=sha(readFileSync(within(runtime,PIN.files['core.mjs'].source)));
  producerCoreBefore=sha(readFileSync(within(producerRoot,'core.mjs')));
  assert.equal(coreBefore,producerCoreBefore);
 });
 // Import producer modules only after the complete private inventory was checked.
 original=await import(pathToFileURL(within(producerRoot,'sdk.mjs')).href);
 const oldEvidence=await import(pathToFileURL(within(producerRoot,'evidence.mjs')).href);
 current=await import(pathToFileURL(within(runtime,'sdk.mjs')).href);
 const newEvidence=await import(pathToFileURL(within(runtime,'evidence.mjs')).href);
 currentVersion=current.version();
 await check('published producer033 and configured consumer versions',()=>{assert.equal(original.version(),'0.3.3');assert.equal(currentVersion,JSON.parse(read('package.json')).version);});
 for(const fixture of ['examples/write-skew.json','examples/consistent.json']){
  if(!selected(fixture+' original report and v1/v2 capsule replay'))continue;
  const source=read(fixture),report=original.analyzeWithOptions(source),capsule=oldEvidence.makeCapsule(source,report);
  keep(fixture.includes('write-skew')?'core-skew':'core-consistent',report,capsule);
  await check(fixture+' original report and v1/v2 capsule replay',()=>{valid('verify-v1v2',current.replayReport(source,report));valid('replay-v1v2',newEvidence.replayCapsule(capsule));});
  await check(fixture+' modified conclusion is refused',()=>{const altered=structuredClone(report);altered.status=report.status==='violation'?'consistent':'violation';assert.equal(current.replayReport(source,altered).valid,false);});
 }
 for(const [label,fixture]of [['list','examples/list-cycle.json'],['relation','examples/relation-source-closure.json'],['register','fixtures/classification-v3/source-closed-noisy-g2.json']]){
  if(!selected(label+' original v3 report and capsule replay'))continue;
  const source=read(fixture),report=original.analyzeV3(source),capsule=original.makeCapsuleV3(source,report);keep('capture-'+label,report,capsule);
  await check(label+' original v3 report and capsule replay',()=>{valid('verify-v3',current.verifyV3(source,report));valid('replay-v3',current.replayCapsuleV3(capsule));});
  await check(label+' modified normalized evidence is refused',()=>{const bad=structuredClone(report);bad.normalized.status='forged';assert.equal(current.verifyV3(source,bad).valid,false);});
 }
 for(const [label,fixture]of [['list','fixtures/classification-models-v3/list-skew.json'],['empty','fixtures/classification-models-v3/empty-register.json']]){
  if(!selected(label+' original model report and capsule replay'))continue;
  const source=read(fixture),report=original.classifyModelsV3(source),capsule=original.makeModelsClassificationCapsuleV3(source);keep('models-'+label,report,capsule);
  await check(label+' original model report and capsule replay',()=>{valid('verify-models',current.verifyModelsClassificationV3(source,report));valid('replay-models',current.replayModelsClassificationCapsuleV3(capsule));});
  await check(label+' forged model result is refused',()=>assert.equal(current.verifyModelsClassificationV3(source,{...report,status:'forged'}).valid,false));
 }
 const trace=read('fixtures/classification-v3/source-closed-noisy-g2.json');
 const analysis=(group==='all'||group==='classification'||group==='integrity')?original.analyzeV3(trace):undefined;
 await check('original category report and capsule',()=>{const report=original.classifyV3(trace),capsule=original.makeClassificationCapsuleV3(trace);keep('category',report,capsule);valid('verify-classification',current.verifyClassificationV3(trace,report));valid('replay-classification',current.replayClassificationCapsuleV3(capsule));});
 await check('original category-preserving reduction capsule',()=>{const capsule=original.makeClassificationReductionCapsuleV3(trace,{category:'G2-item',maxChecks:0});keep('category-reduction',undefined,capsule);valid('replay-classification',current.replayClassificationCapsuleV3(capsule));});
 await check('original diagnosis and execution capsule',()=>{const report=original.diagnoseV3(trace),capsule=original.makeExecutionCapsuleV3(trace);keep('diagnosis',report,capsule);valid('verify-diagnosis',current.verifyDiagnosisV3(trace,report));valid('replay-execution',current.replayExecutionCapsuleV3(capsule));});
 await check('original register cycle explanation',()=>{const report=original.explainRegisterCycleV3(trace,analysis);keep('cycle',report);valid('verify-cycle',current.verifyRegisterCycleExplanationV3(trace,analysis,report));});
 const orm=read('verification/configured-user-profile/v024-initial/producer-first/profile-source.json');
 await check('original configured ORM report and capsule',()=>{const report=original.analyzeOrmProfileV3(orm),capsule=original.makeOrmProfileCapsuleV3(orm);keep('orm',report,capsule);valid('verify-orm',current.verifyOrmProfileV3(orm,report));valid('replay-orm',current.replayOrmProfileCapsuleV3(capsule));});
 const profile=read('verification/model-profile-v3/v027-initial/database/list-write-skew/profile-source.json');
 await check('original configured model report and capsule',()=>{const report=original.analyzeModelProfileV3(profile),capsule=original.makeModelProfileCapsuleV3(profile);keep('model-profile',report,capsule);valid('verify-model-profile',current.verifyModelProfileV3(profile,report));valid('replay-model-profile',current.replayModelProfileCapsuleV3(capsule));});
 await check('all fifteen original fixed method classes were exercised',()=>assert.deepEqual([...operations].sort(),policyOperations.slice().sort()));
 for(const [label,fixture]of [['register','examples/write-skew.json'],['list','examples/list-cycle.json'],['relation','examples/relation-source-closure.json']]){
  if(!selected(label+' original v4 analysis semantic report and capsule'))continue;
  const source=read(fixture),report=original.analyzeV4(source),capsule=original.makeCapsuleV4(source);keep('v4-analysis-'+label,report,capsule);
  await check(label+' original v4 analysis semantic report and capsule',()=>{assert.equal(current.verifyV4(source,report).valid,true);assert.equal(current.replayCapsuleV4(capsule).valid,true);});
  const category=original.classifyV4(source),categoryCapsule=original.makeClassificationCapsuleV4(source);keep('v4-classification-'+label,category,categoryCapsule);
  await check(label+' original v4 classification semantic report and capsule',()=>{assert.equal(current.verifyClassificationV4(source,category).valid,true);assert.equal(current.replayCapsuleV4(categoryCapsule).valid,true);if(label==='relation')assert.equal(category.judgment.status,'unsupported');});
  const expected={preserve:'serializable',maxChecks:0},reduction=original.reduceV4(source,expected),reductionCapsule=original.makeReductionCapsuleV4(source,expected);keep('v4-reduction-'+label,reduction,reductionCapsule);
  await check(label+' original v4 reduction needs independent model and budget',()=>{assert.equal(current.verifyReductionV4(source,reduction,expected).valid,true);assert.equal(current.replayCapsuleV4(reductionCapsule,expected).valid,true);assert.equal(current.replayCapsuleV4(reductionCapsule).valid,false);assert.equal(current.replayCapsuleV4(reductionCapsule,{preserve:'strict-serializable',maxChecks:0}).valid,false);});
  await check(label+' self-consistent v4 digest cannot authorize semantic alteration',()=>{const bad=JSON.parse(capsule),changed=JSON.parse(bad.reportText);changed.semanticContract='forged';bad.reportText=JSON.stringify(changed);bad.reportSha256=sha(bad.reportText);bad.semanticContract='forged';assert.equal(current.replayCapsuleV4(JSON.stringify(bad)).valid,false);});
 }
 await check('matching documented033 header routes to the fixed runtime',()=>{const routed=bridge.routeLegacyV033('verify-v3',[trace,analysis],currentVersion);assert.equal(routed.matched,true);assert.equal(routed.result.valid,true);});
 await check('current033 consumer bypasses compatibility worker',()=>assert.equal(bridge.routeLegacyV033('verify-v3',[trace,analysis],'0.3.3').matched,false));
 await check('business versions and executable selectors cannot choose a runtime',()=>{assert.equal(bridge.routeLegacyV033('verify-v3',[trace,{schemaVersion:3,version:'unknown',business:{version:'0.3.3'}}],currentVersion).matched,false);assert.equal(bridge.routeLegacyV033('select-an-executable',[trace,analysis],currentVersion).matched,false);});
 await check('mixed capsule/report engine headers are refused before routing',()=>{const capsule=JSON.parse(original.makeCapsuleV3(trace,analysis));capsule.reportText=JSON.stringify({...analysis,version:'0.3.1'});assert.equal(bridge.routeLegacyV033('replay-v3',[JSON.stringify(capsule)],currentVersion).matched,false);});
 await check('raw worker refuses command-line selectors',()=>{const child=spawnSync(process.execPath,['--no-addons',within(runtime,'legacy-v033.mjs'),'--module','sdk.mjs'],{input:'{}\n',encoding:'utf8',env:{...process.env,MTW_PUBLIC033_WORKER:'1'},windowsHide:true,timeout:30000,maxBuffer:1024*1024});assert.equal(child.status,2);assert.equal(child.stdout,'');assert.match(child.stderr,/worker refused/);});
 if(group==='all'||group==='integrity'){
 const corrupt=await isolate('source-corruption');
 await check('isolated source inventory initially assembles',()=>verifyInventory(corrupt.module.verifyPublic033Runtime()));
 const originalCore=readFileSync(corrupt.coreSource);
 await check('source corruption poisons its independent loader without repairing',()=>{writeFileSync(corrupt.coreSource,'// corrupted source, never execute\n');assert.throws(()=>corrupt.module.verifyPublic033Runtime());writeFileSync(corrupt.coreSource,originalCore);assert.throws(()=>corrupt.module.verifyPublic033Runtime());const r=corrupt.module.routeLegacyV033('verify-v3',[trace,analysis],currentVersion);assert.equal(r.matched,true);assert.equal(r.result.valid,false);assert.match(r.result.reason,/public033-unavailable-or-refused/);});
 const extra=await isolate('private-extra'),privateRoot=extra.module.verifyPublic033Runtime(),unexpected=within(privateRoot,'unexpected-member.mjs');
 await check('an extra member in the private full tree poisons only that loader',()=>{writeFileSync(unexpected,'// unexpected private member\n');assert.throws(()=>extra.module.verifyPublic033Runtime());unlinkSync(unexpected);assert.throws(()=>extra.module.verifyPublic033Runtime());});
 const missing=await isolate('missing-source'),missingBytes=readFileSync(missing.coreSource);
 await check('a missing source remains poisoned after bytes are restored',()=>{unlinkSync(missing.coreSource);assert.throws(()=>missing.module.verifyPublic033Runtime());writeFileSync(missing.coreSource,missingBytes);assert.throws(()=>missing.module.verifyPublic033Runtime());});
 const inert=await isolate('unused-shared-pool');
 await check('unreferenced shared-pool files remain inert and are not copied',()=>{const added=within(inert.root,'legacy/unreferenced-public033-test/inert.mjs');mkdirSync(dirname(added),{recursive:true});writeFileSync(added,'throw Error("Unreferenced shared code must not execute");\n');const full=inert.module.verifyPublic033Runtime();verifyInventory(full);assert(!inventory(full).includes('legacy/unreferenced-public033-test/inert.mjs'));});
 }
 await check('installed source pool and original producer remain byte-identical',()=>{assert.deepEqual(sourceHashes(),sourceBefore);assert.equal(sha(readFileSync(within(runtime,PIN.files['core.mjs'].source))),coreBefore);assert.equal(sha(readFileSync(within(producerRoot,'core.mjs'))),producerCoreBefore);verifyInventory(bridge.verifyPublic033Runtime());sourcePoolVerifiedUnchanged=true;});
}catch(error){suiteError=error;if(!cases.some(value=>!value.passed))cases.push({name:'compatibility setup or original producer invocation',passed:false,error:error.message});}
const failed=[...preconditions,...cases,...postconditions].filter(value=>!value.passed),receipt={suite:'public033-fixed-runtime-compatibility-1',passed:!suiteError&&failed.length===0,checks:cases.length,
 publicVersion:'0.3.3',currentVersion:currentVersion??null,group,preconditions,postconditions,candidateRuntimeFiles:Object.fromEntries(readdirSync(runtime).filter(name=>lstatSync(within(runtime,name)).isFile()).sort().map(name=>[name,memberHash(runtime,name)])),producerArchiveSha256:PIN?.archiveSha256??null,producerComponentSha256:PIN?.componentSha256??null,
 producerSourceCommit:PIN?.sourceCommit??null,publishedMemberCount:PIN?Object.keys(PIN.files).length:null,immutableSourceCount:sources.size,
 usesPublishedRuntimeOnly:producerInventoryVerified,historicalSourceSnapshotCreated:false,arbitraryProducerSelectorSupported:false,producerOrigin:'installed legacy-v033.verifyPublic033Runtime() fixed complete snapshot',
 runtime,runDirectory:run,operations:[...operations].sort(),scope:'Fixed installed runtime compatibility; public archive publication provenance is verified separately by release receipts.',
 publicArchiveDownloadedByThisTest:false,sourcePoolUnchanged:sourcePoolVerifiedUnchanged,cases,...(suiteError?{error:suiteError.message}:{}),
 testedHarnessSha256:sha(readFileSync(new URL(import.meta.url)))};
if(receipt.passed&&group!=='all')validatePublic033Group(receipt,group);
writeFileSync(resolve(output,'public033-compatibility-validation.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));if(!receipt.passed)process.exitCode=1;
