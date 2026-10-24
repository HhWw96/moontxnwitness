// Pure fake-file freeze controls. No genuine producer/runtime or SDK is executed.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync,existsSync,readdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {freezePublicV026} from './freeze-public026-runtime.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),out=resolve(process.argv[2]??'');assert.equal(process.argv.length,3,'One NEW directory required');mkdirSync(out);
const SOURCE='4c74fd29f45c2e6756a20881fefb03677fa9bf52',sha=b=>createHash('sha256').update(b).digest('hex'),encode=x=>Buffer.from(JSON.stringify(x,null,2)+'\n'),rows=[];let number=0;
function write(p,b){mkdirSync(dirname(p),{recursive:true});writeFileSync(p,b);}
function fixture(){
 const at=resolve(out,'synthetic-'+(++number)),base=resolve(at,'producer'),repo=resolve(at,'framework');mkdirSync(base,{recursive:true});mkdirSync(resolve(repo,'cmd'),{recursive:true});
 for(const name of ['legacy-v026-worker.mjs','legacy-v026-binding.mjs'])copyFileSync(resolve(root,'cmd',name),resolve(repo,'cmd',name));
 const binding=readFileSync(resolve(repo,'cmd/legacy-v026-binding.mjs')),payload={};
 for(const name of ['core.mjs','capture-core.mjs','orm-profile.mjs','classification.mjs','classification-models.mjs','legacy-v024.mjs','legacy-v025.mjs','legacy-v025-runtime.mjs','legacy-v025-worker.mjs','legacy-v025-binding.mjs'])payload[name]=Buffer.from('throw Error("Synthetic module must NEVER execute");\n');
 payload.LICENSE=Buffer.from('synthetic licence placeholder\n');payload['THIRD_PARTY_NOTICES.txt']=Buffer.from('synthetic notice placeholder\n');
 const build={version:'0.2.6',coreSha256:sha(payload['core.mjs']),captureCoreSha256:sha(payload['capture-core.mjs'])};payload['build-manifest.json']=encode(build);
 for(const [folder,format]of [['legacy/v024/','moontxnwitness-frozen-orm-runtime/v1'],['legacy/v025/','moontxnwitness-frozen-public-runtime/v1']]){const raw=Buffer.from('throw Error("Synthetic nested module must never execute");\n');payload[folder+'core.mjs']=raw;payload[folder+'manifest.json']=encode({format,files:{'core.mjs':{bytes:raw.length,sha256:sha(raw)}}});}
 const producerFiles={},runtime={},bindings={};
 for(const [name,b]of Object.entries(payload)){const meta={bytes:b.length,sha256:sha(b)};write(resolve(base,'producer-runtime',name),b);producerFiles[name]={file:'producer-runtime/'+name,...meta};runtime[name]=meta;bindings['runtime/'+name]=meta;}
 const cases=[],existingCases=[],modelCases=[];
 for(let i=0;i<35;i++){
  const model=i>=21,orm=i===0,name='synthetic-'+i,type=model?'model-classification':orm?'orm-profile':'category-classification',operation=model?'classify-models':orm?'analyze':'classify',inputPath=name+'.json',input=Buffer.from('{"syntheticOnly":true,"number":'+i+'}\n');bindings['package/'+inputPath]={bytes:input.length,sha256:sha(input)};
  if(model)modelCases.push({name,type,inputPath,options:{}});else existingCases.push({name,type,operation,inputPath,requestOptions:{}});
  const report={format:model?'moontxnwitness-isolation-model-report/v1':orm?'moontxnwitness-orm-profile-report/v1':'moontxnwitness-classification-report/v1',...(orm?{engineVersion:'0.2.6'}:{engine:{version:'0.2.6'}}),status:'inconclusive',syntheticOnly:true},capsule={format:model?'moontxnwitness-isolation-models/v1':orm?'moontxnwitness-orm-profile/v1':'moontxnwitness-classification/v1',...(orm?{engineVersion:'0.2.6'}:{engine:{version:'0.2.6'}}),syntheticOnly:true},parts={input,report:encode(report),capsule:encode(capsule),producerReplay:encode({valid:true,report,syntheticOnly:true})};
  const row={name,type,operation,requestOptions:{},expectedStatus:report.status};for(const [key,b]of Object.entries(parts)){const file=name+'.'+key+'.json';write(resolve(base,file),b);row[key]={file,bytes:b.length,sha256:sha(b)};}cases.push(row);
 }
 const common={sourceCommit:SOURCE,actualPublishedProducer:true,rawEsmIdentityPreserved:true,entirePublicDistPreserved:true,headerRewriting:false,authorDistRead:false,actualDatabaseExecutedHere:false,compilerExecutedHere:false,publicPackages:{syntheticOnly:true},checksumAsset:{syntheticOnly:true},registryPackage:{syntheticOnly:true},publicationReceiptSha256:'a'.repeat(64),publisherReferenceSha256:'b'.repeat(64),transportReceiptSha256:'c'.repeat(64),externalBindingsSha256:'d'.repeat(64),fullSdkEsmFiles:['core.mjs'],minimalCategoryReplayFiles:['classification.mjs','core.mjs'],minimalOrmEsmReplayFiles:['core.mjs','orm-profile.mjs'],minimalModelReplayFiles:['classification-models.mjs','core.mjs']};
 const provider={...common,format:'moontxnwitness-v026-provider/v1',version:'0.2.6',runtime,bindings,buildManifest:build,existingCases,modelCases};
 const manifest={...common,format:'moontxnwitness-actual-public-producer-fixtures/v1',producerEngineVersion:'0.2.6',expectedSourceCommit:SOURCE,originalProducerReplaysPassed:true,existingFamilies:21,modelCases:14,cases,producerBuild:build,producerFiles};
 function repin(){const raw=encode(provider);write(resolve(base,'provider-origin.json'),raw);manifest.providerSha256=sha(raw);const m=encode(manifest);write(resolve(base,'manifest.json'),m);return sha(m);}
 repin();return {at,base,repo,payload,binding,provider,manifest,repin};
}
function check(name,fn){try{fn();rows.push({name,passed:true});}catch(error){rows.push({name,passed:false,error:error.message});}}
function unchanged(f){assert.equal(existsSync(resolve(f.repo,'cmd/legacy/v026')),false);assert.deepEqual(readFileSync(resolve(f.repo,'cmd/legacy-v026-binding.mjs')),f.binding);}
check('well-formed synthetic contract freezes exact bytes without importing modules',()=>{const f=fixture(),pin=f.repin(),r=freezePublicV026(f.base,pin,f.repo);assert.equal(r.totalFamilies,35);assert.equal(r.originalModuleBytesUnchanged,true);assert.equal(r.producerSdkExecutedHere,false);for(const [name,b]of Object.entries(f.payload))assert.deepEqual(readFileSync(resolve(f.repo,'cmd/legacy/v026',name)),b);assert.throws(()=>freezePublicV026(f.base,pin,f.repo));});
check('external fixture pin mismatch refuses without writes',()=>{const f=fixture();assert.throws(()=>freezePublicV026(f.base,'0'.repeat(63)+'1',f.repo));unchanged(f);});
for(const [name,mutate]of [
 ['unpublished producer',f=>{f.manifest.actualPublishedProducer=false;}],
 ['author dist provenance',f=>{f.manifest.authorDistRead=true;}],
 ['header rewriting',f=>{f.manifest.headerRewriting=true;}],
 ['wrong source commit',f=>{f.manifest.sourceCommit='0'.repeat(40);}],
 ['missing original family',f=>{f.manifest.cases.pop();}],
 ['wrong existing family count',f=>{f.manifest.existingFamilies=20;}],
 ['wrong model family count',f=>{f.manifest.modelCases=13;}],
 ['duplicate family identity',f=>{f.manifest.cases[1].name=f.manifest.cases[0].name;}],
 ['changed producer provenance',f=>{f.manifest.externalBindingsSha256='e'.repeat(64);}],
 ['missing runtime closure',f=>{delete f.manifest.producerFiles['classification-models.mjs'];}],
 ['runtime path escape',f=>{f.manifest.producerFiles['core.mjs'].file='../outside.mjs';}],
 ['raw report path escape',f=>{f.manifest.cases[0].report.file='../outside.json';}],
 ['report byte hash differs',f=>{f.manifest.cases[0].report.sha256='e'.repeat(64);}],
 ['original input metadata differs',f=>{f.provider.bindings['package/synthetic-0.json'].sha256='e'.repeat(64);}],
 ['changed original operation',f=>{f.manifest.cases[0].operation='reduce';}],
 ['changed request options',f=>{f.manifest.cases[0].requestOptions={maxStates:0};}],
 ['truncated original licence',f=>{write(resolve(f.base,'producer-runtime/LICENSE'),Buffer.from(''));}],
 ['changed original ESM bytes',f=>{write(resolve(f.base,'producer-runtime/core.mjs'),Buffer.from('changed'));}],
 ['wrong model minimal closure',f=>{f.manifest.minimalModelReplayFiles=['core.mjs'];}],
 ['existing target refused',f=>{mkdirSync(resolve(f.repo,'cmd/legacy/v026'),{recursive:true});write(resolve(f.repo,'cmd/legacy/v026/KEEP'),'do not overwrite');}]
])check(name+' refuses without mutation',()=>{const f=fixture();mutate(f);const pin=f.repin();assert.throws(()=>freezePublicV026(f.base,pin,f.repo));assert.deepEqual(readFileSync(resolve(f.repo,'cmd/legacy-v026-binding.mjs')),f.binding);if(name==='existing target refused')assert.equal(readFileSync(resolve(f.repo,'cmd/legacy/v026/KEEP'),'utf8'),'do not overwrite');else unchanged(f);});
check('changed original report header refuses even when its raw hash is repinned',()=>{const f=fixture(),entry=f.manifest.cases[0].report,b=encode({format:'wrong',engine:{version:'0.2.6'},status:'inconclusive'});write(resolve(f.base,entry.file),b);entry.bytes=b.length;entry.sha256=sha(b);assert.throws(()=>freezePublicV026(f.base,f.repin(),f.repo));unchanged(f);});
// Field selection is intentionally identical to the six-operation worker.
// For report mutations, replay.report is repinned too: equality is not the rejection cause.
const fieldSelectionChecks=[];
for(const type of ['orm-profile','category-classification','model-classification'])for(const key of ['report','capsule'])for(const variant of ['missing-required-version','conflicting-required-version'])check(type+' '+key+' '+variant+' rejects mixed-field fallback',()=>{
 const f=fixture(),row=f.manifest.cases.find(r=>r.type===type),entry=row[key],value=JSON.parse(readFileSync(resolve(f.base,entry.file)));
 if(type==='orm-profile'){
  if(variant==='missing-required-version')delete value.engineVersion;else value.engineVersion='0.2.7';value.engine={version:'0.2.6'};
 }else{
  value.engineVersion='0.2.6';if(variant==='missing-required-version')delete value.engine;else value.engine={version:'0.2.7'};
 }
 const replace=(e,v)=>{const b=encode(v);write(resolve(f.base,e.file),b);e.bytes=b.length;e.sha256=sha(b);};replace(entry,value);
 if(key==='report'){const replay=JSON.parse(readFileSync(resolve(f.base,row.producerReplay.file)));replay.report=value;replace(row.producerReplay,replay);assert.deepEqual(JSON.parse(readFileSync(resolve(f.base,row.producerReplay.file))).report,value);}
 const oldSelectedVersion=value.engineVersion??value.engine?.version,requiredSelectedVersion=type==='orm-profile'?value.engineVersion:value.engine?.version;
 assert.notEqual(requiredSelectedVersion,'0.2.6');const oldPredicateWouldAccept=oldSelectedVersion==='0.2.6';
 if(type!=='orm-profile'||variant==='missing-required-version')assert.equal(oldPredicateWouldAccept,true,'Regression must expose the original fallback hole');
 assert.throws(()=>freezePublicV026(f.base,f.repin(),f.repo));unchanged(f);
 fieldSelectionChecks.push({type,artifact:key,variant,oldPredicateWouldAccept,requiredVersion:requiredSelectedVersion??null,reportReplayEqualityPreserved:key==='report'});
});
const result={format:'synthetic-public26-freezer-tests/v1',passed:rows.every(r=>r.passed),checks:rows.length,fieldSelectionChecks,syntheticOnly:true,realSdkImported:false,actualPublicProducerExecuted:false,actualPublicRuntimeFrozen:false,rootModified:false,compilerExecuted:false,databaseExecuted:false,performanceMeasured:false,cases:rows};writeFileSync(resolve(out,'receipt.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(result));process.exitCode=result.passed?0:1;
