// Genuine fixed public027 expectations versus an actually built v028 consumer.
// Never regenerate expected reports or rewrite original old modules/headers.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,relative,isAbsolute,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports,createRequire} from 'node:module';
import {PUBLIC027_FIXTURE_MANIFEST_SHA256} from './public027-fixture-binding.mjs';
const [runtimeArg,fixturesArg,outputArg,...extra]=process.argv.slice(2);assert.ok(runtimeArg&&fixturesArg&&outputArg&&!extra.length);
const runtime=resolve(runtimeArg),fixtures=resolve(fixturesArg),output=resolve(outputArg);mkdirSync(output);
const sha=x=>createHash('sha256').update(x).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n',checks=[];
const SOURCE='c10b06c5bfcabd1f40b0ff0099717072a816ec74',VERSION='0.2.7';
const receipt={format:'genuine-public027-current-consumer/v1',passed:false,expectedRegenerated:false,actualDatabaseExecuted:false,compilerExecuted:false,performanceMeasured:false,checks};
const count={v024:0,v025:0,v026:0,v027:0},spawn=childProcess.spawnSync;
childProcess.spawnSync=(...a)=>{for(const name of Object.keys(count))if(a[1]?.some?.(x=>String(x).endsWith('legacy-'+name+'-worker.mjs')))count[name]++;return spawn(...a);};syncBuiltinESMExports();
const require=createRequire(import.meta.url),total=()=>Object.values(count).reduce((a,b)=>a+b,0),oldCjs=()=>Object.keys(require.cache).filter(p=>p.replaceAll(String.fromCharCode(92),'/').includes('/legacy/v024/')&&p.endsWith('.cjs')).length;
const check=(name,fn)=>{fn();checks.push({name,passed:true});};
const HOST={'orm-profile':['verifyOrmProfileV3','replayOrmProfileCapsuleV3'],'category-classification':['verifyClassificationV3','replayClassificationCapsuleV3'],'model-classification':['verifyModelsClassificationV3','replayModelsClassificationCapsuleV3'],'model-profile':['verifyModelProfileV3','replayModelProfileCapsuleV3']};
function file(name){assert.ok(typeof name==='string'&&name&&!name.includes(String.fromCharCode(92))&&!name.includes(':')&&!name.startsWith('/')&&name.split('/').every(x=>x&&x!=='.'&&x!=='..'));const p=resolve(fixtures,name),rel=relative(realpathSync(fixtures),realpathSync(p));assert.ok(rel&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..'+sep));const s=lstatSync(p);assert.ok(s.isFile()&&!s.isSymbolicLink());return p;}
function bound(row){assert.ok(row&&Number.isSafeInteger(row.bytes)&&row.bytes>=0&&row.bytes<=256*1024*1024);assert.match(row.sha256,/^[0-9a-f]{64}$/);const b=readFileSync(file(row.file));assert.equal(b.length,row.bytes);assert.equal(sha(b),row.sha256);return b;}
function compare(actual,expected,type,current){if(['v1','v2'].includes(type)){assert.equal(expected.currentEngine,VERSION);assert.equal(expected.recordedEngine,VERSION);assert.deepEqual(actual,{...expected,currentEngine:current});}else assert.deepEqual(actual,expected);}
try{
 assert.match(PUBLIC027_FIXTURE_MANIFEST_SHA256,/^[0-9a-f]{64}$/);const raw=readFileSync(file('manifest.json'));assert.equal(sha(raw),PUBLIC027_FIXTURE_MANIFEST_SHA256);const m=JSON.parse(raw);
 check('externally pinned actual46 public027 producer contract',()=>{assert.equal(m.format,'moontxnwitness-actual-public-producer-fixtures/v1');assert.equal(m.producerEngineVersion,VERSION);assert.equal(m.sourceCommit,SOURCE);assert.equal(m.expectedSourceCommit,SOURCE);for(const k of ['actualPublishedProducer','rawEsmIdentityPreserved','entirePublicDistPreserved','originalProducerReplaysPassed','originalProducerVerificationsPassed'])assert.equal(m[k],true);for(const k of ['authorDistRead','headerRewriting','actualDatabaseExecutedHere','compilerExecutedHere'])assert.equal(m[k],false);assert.equal(m.cases.length,46);assert.equal(new Set(m.cases.map(r=>r.name)).size,46);assert.equal(m.existingFamilies,35);assert.equal(m.modelProfileCases,11);assert.equal(m.cases.filter(r=>r.type==='model-profile').length,11);});
 const providerRaw=readFileSync(file('provider-origin.json'));assert.equal(sha(providerRaw),m.providerSha256);const provider=JSON.parse(providerRaw);
 check('original complete103 producer files including original licences and nested runtimes',()=>{assert.equal(provider.version,VERSION);assert.equal(provider.sourceCommit,SOURCE);assert.equal(Object.keys(m.producerFiles).length,103);assert.deepEqual(Object.keys(m.producerFiles).sort(),Object.keys(provider.runtime).sort());for(const [name,row]of Object.entries(m.producerFiles)){assert.equal(row.file,'producer-runtime/'+name);const b=bound(row);assert.deepEqual({bytes:b.length,sha256:sha(b)},provider.runtime[name]);}assert.equal(m.producerBuild.version,VERSION);assert.equal(m.producerBuild.coreSha256,m.producerFiles['core.mjs'].sha256);assert.equal(m.producerBuild.captureCoreSha256,m.producerFiles['capture-core.mjs'].sha256);});
 const records=m.cases.flatMap(r=>['input','report','capsule','producerReplay','producerVerification'].map(k=>r[k]));check('original inputs expectations and producer results all byte-bound',()=>{for(const r of records)bound(r);});
 const read=r=>bound(r).toString('utf8'),find=name=>{const row=m.cases.find(r=>r.name===name);assert.ok(row);return row;};
 const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href),evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href);
 receipt.currentRuntimeVersion=sdk.version();assert.equal(sdk.version(),'0.2.8','This test requires an actual separately built v0.2.8 consumer');
 const build=JSON.parse(readFileSync(resolve(runtime,'build-manifest.json')));check('actual current runtime version core and capture manifest bindings',()=>{assert.equal(build.version,sdk.version());assert.equal(sha(readFileSync(resolve(runtime,'core.mjs'))),build.coreSha256);assert.equal(sha(readFileSync(resolve(runtime,'capture-core.mjs'))),build.captureCoreSha256);});
 check('ordinary imports start no historical worker or old in-process CJS',()=>{assert.equal(total(),0);assert.equal(oldCjs(),0);});
 check('normal analysis uses current engine without historical workers',()=>{sdk.analyze(read(find('register-v1').input));const profile=sdk.analyzeModelProfileV3(read(find('model-profile-list-values').input));assert.equal(profile.engine.version,sdk.version());assert.equal(sdk.verifyModelProfileV3(read(find('model-profile-list-values').input),profile).valid,true);const orm=sdk.analyzeOrmProfileV3(read(find('orm-actual-1').input));assert.equal(orm.engineVersion,sdk.version());const model=sdk.classifyModelsV3(read(find('model-empty-default').input));assert.equal(model.engine.version,sdk.version());assert.equal(total(),0);assert.equal(oldCjs(),0);});
 receipt.normalAnalysisHistoricalWorkersStarted=total();
 const replay=(row,text)=>HOST[row.type]?sdk[HOST[row.type][1]](text):row.type==='execution'?sdk.replayExecutionCapsuleV3(text):row.type==='v3'?sdk.replayCapsuleV3(text):evidence.replayCapsule(text);
 const refuse=(row,text,label)=>check(row.name+' refuses '+label,()=>assert.equal(replay(row,text).valid,false));
 for(const row of m.cases){
  const input=read(row.input),report=JSON.parse(read(row.report)),captext=read(row.capsule),cap=JSON.parse(captext),expected=JSON.parse(read(row.producerReplay));
  check(row.name+' reproduces complete original public027 capsule result',()=>{assert.equal(cap.engine?.version??cap.engineVersion,VERSION);assert.equal(expected.valid,true);compare(replay(row,captext),expected,row.type,sdk.version());});
  if(HOST[row.type]){
   const [verify]=HOST[row.type];check(row.name+' original report verifies with exact original response',()=>assert.deepEqual(sdk[verify](input,report,row.requestOptions),JSON.parse(read(row.producerVerification))));
   for(const [label,mutate]of [['conclusion',r=>r.status='forged'],['budget',r=>{const k=Object.keys(r.budgets).find(k=>Number.isSafeInteger(r.budgets[k]));assert.ok(k);r.budgets[k]++;}],['engine',r=>{if(r.engine)r.engine.coreSha256='0'.repeat(64);else r.engineVersion='9.9.9';}]]){
    const changed=structuredClone(report);mutate(changed);check(row.name+' refuses false report '+label,()=>assert.equal(sdk[verify](input,changed,row.requestOptions).valid,false));
    const c=structuredClone(cap),r=JSON.parse(c.reportText);mutate(r);c.reportText=JSON.stringify(r);c.reportSha256=sha(c.reportText);refuse(row,canonical(c),'rehashed false '+label);
   }
   refuse(row,captext+' ','noncanonical suffix');const duplicate=captext.replace(/\n}\n$/,'\n,"algorithm":'+JSON.stringify(cap.algorithm)+'}\n');assert.notEqual(duplicate,captext);refuse(row,duplicate,'duplicate header');
  }else{
   const c=structuredClone(cap),field=row.type==='execution'?'diagnosticText':'reportText',value=JSON.parse(c[field]);value.status='forged';c[field]=JSON.stringify(value);c[row.type==='execution'?'diagnosticSha256':'reportSha256']=sha(c[field]);refuse(row,canonical(c),'rehashed false semantic result');
   if(row.type==='v3')check(row.name+' core report verifies unchanged',()=>assert.deepEqual(sdk.verifyV3(input,report),JSON.parse(read(row.producerVerification))));
   if(['v1','v2'].includes(row.type))check(row.name+' report permits only currentEngine response delta',()=>compare(sdk.replayReport(input,report),JSON.parse(read(row.producerVerification)),row.type,sdk.version()));
  }
 }
 for(const [name,command]of [['register-v1','replay'],['register','replay-v3'],['orm-actual-1','replay-orm-profile-v3'],['category-g0','replay-classification-v3'],['model-g0','replay-models-classification-v3'],['model-profile-list-values','replay-model-profile-v3'],['model-profile-relation-write-skew','replay-model-profile-v3']]){
  const row=find(name);check(name+' actual current CLI exact original replay',()=>{const c=spawn(process.execPath,[resolve(runtime,'moontxnwitness.mjs'),command,file(row.capsule.file)],{encoding:'utf8',windowsHide:true,timeout:300000,maxBuffer:384*1024*1024});writeFileSync(resolve(output,name+'.cli.stdout.original'),c.stdout??'',{flag:'wx'});writeFileSync(resolve(output,name+'.cli.stderr.original'),c.stderr??'',{flag:'wx'});assert.equal(c.error,undefined);assert.equal(c.status,0);compare(JSON.parse(c.stdout),JSON.parse(read(row.producerReplay)),row.type,sdk.version());});
 }
 check('original partial unknown and zero budget boundaries retained',()=>{for(const name of ['model-profile-list-unknown-sql','model-profile-relation-zero-write','model-profile-relation-partial-fetch','model-profile-list-zero-budget'])assert.equal(JSON.parse(read(find(name).report)).status,'inconclusive');const zero=JSON.parse(read(find('model-profile-list-zero-budget').report));assert.equal(JSON.parse(zero.requestOptionsText).maxStates,0);for(const row of m.cases)assert.equal(row.inputOrigin.databaseExecutedHere,false);});
 check('all original files and fixture manifest remain byte-identical',()=>{for(const r of records)bound(r);for(const r of Object.values(m.producerFiles))bound(r);assert.equal(sha(readFileSync(file('manifest.json'))),PUBLIC027_FIXTURE_MANIFEST_SHA256);assert.equal(sha(readFileSync(file('provider-origin.json'))),m.providerSha256);});
 receipt.passed=true;receipt.originalProducerFamilies=46;receipt.originalModelProfileFamilies=11;receipt.inProcessHistoricalWorkerLaunchesByVersion={...count};receipt.originalReportsAndCapsulesRemainByteIdentical=true;receipt.verificationResponseOnlyCurrentEngineDeltaAllowedFor=['v1','v2'];
}catch(e){receipt.failure={name:e.name,message:e.message};process.exitCode=1;}
receipt.checkCount=checks.length;writeFileSync(resolve(output,'receipt.json'),canonical(receipt),{flag:'wx'});console.log(JSON.stringify({passed:receipt.passed,currentRuntimeVersion:receipt.currentRuntimeVersion,checks:checks.length,families:receipt.originalProducerFamilies,expectedRegenerated:false,failure:receipt.failure??null}));