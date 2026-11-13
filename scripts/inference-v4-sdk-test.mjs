import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {matrixCases} from './elle-model-matrix/cases.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const runtime=resolve(process.env.MTW_INFERENCE_RUNTIME||resolve(root,'dist'));
const api=await import(pathToFileURL(resolve(runtime,'inference-v4.mjs')));
const {inferDependenciesV4:infer,classifyWithInferenceV4:classify,verifyInferenceV4:verifyGraph,
 verifyWithInferenceV4:verify,makeInferenceCapsuleV4:make,replayInferenceCapsuleV4:replay,parseInferenceOptionsV4:parse}=api;
const hash=x=>createHash('sha256').update(x).digest('hex');
const before=hash(readFileSync(resolve(runtime,'core.mjs'))),results=[];
const check=(name,fn)=>{try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.stack});}};
const pick=(model,family)=>matrixCases().cases.find(c=>c.dataModel===model&&c.model==='serializable'&&c.family===family);
const good=pick('point-register-v1','clean'),bad=pick('point-register-v1','write-skew'),list=pick('append-list-v1','clean'),gap=pick('point-register-v1','missing-event');
const options={modules:['original-read-sources/v1','original-version-constraints/v1'],modelOptions:good.options};
check('two independently selected compiled modules execute and verify',()=>{const r=infer(good.input,options);assert.equal(r.status,'executed');assert.equal(r.modules.length,2);assert.equal(r.moduleCompletenessCanAuthorizeModels,false);assert.equal(verifyGraph(good.input,r,options).valid,true);});
check('model compatibility keeps original validated completion',()=>{const r=classify(good.input,options);assert.equal(r.status,'checked-compatible');assert.equal(r.baseClassification.status,'checked-compatible');assert.equal(verify(good.input,r,options).valid,true);});
check('actual graph cycle refutes Serializable',()=>{const o={...options,modelOptions:bad.options},r=classify(bad.input,o);assert.equal(r.status,'refuted');assert.equal(verify(bad.input,r,o).valid,true);});
check('list module requires independent prefix policy',()=>{const o={modules:['observed-list-prefixes/v1'],modelOptions:list.options},r=classify(list.input,o);assert.equal(r.status,'checked-compatible');assert.equal(verify(list.input,r,o).valid,true);});
check('missing original event is not repaired by module declarations',()=>assert.notEqual(classify(gap.input,{...options,modelOptions:gap.options}).status,'checked-compatible'));
check('zero inference budget prevents positive authorization',()=>{const o={...options,maxInferenceChecks:0},r=classify(good.input,o);assert.equal(r.status,'unknown');assert.equal(verify(good.input,r,o).valid,true);});
check('zero inference budget preserves independent refutation',()=>assert.equal(classify(bad.input,{...options,modelOptions:bad.options,maxInferenceChecks:0}).status,'refuted'));
check('explicit empty registry keeps independently checked base',()=>assert.equal(classify(good.input,{...options,modules:[]}).status,'checked-compatible'));
for(const [label,value] of [
 ['omitted module registry',{}],['implicit options',undefined],['dynamic callback',{modules:[{id:'x',code:'run()'}]}],
 ['unknown module',{modules:['unknown/v1']}],['duplicate module',{modules:[options.modules[0],options.modules[0]]}],
 ['negative budget',{modules:[],maxInferenceChecks:-1}],['fractional budget',{modules:[],maxInferenceChecks:0.5}],
 ['greater budget',{modules:[],maxInferenceChecks:1000001}],['unrecognized flag',{modules:[],complete:true}],
 ['duplicate decoded option','{"modules":[],"modu\\u006ces":[]}'],
 ['duplicate nested model option','{"modules":[],"modelOptions":{"maxStates":1,"maxStates":2}}'],
 ['malformed Unicode',{modules:[],ignored:'\ud800'}],
])check('strict options reject '+label,()=>assert.throws(()=>parse(value)));
for(const [label,changed]of [
 ['module removal',{...options,modules:[options.modules[0]]}],['module order',{...options,modules:[...options.modules].reverse()}],
 ['independent budget',{...options,maxInferenceChecks:999999}],['model selection',{...options,modelOptions:{...options.modelOptions,models:['read-committed']}}],
])check('verification binds '+label,()=>assert.equal(verify(good.input,classify(good.input,options),changed).valid,false));
check('modified original facts cannot verify',()=>{const source=structuredClone(good.input);source.events.find(e=>e.kind==='read').version='unobserved';assert.equal(verify(source,classify(good.input,options),options).valid,false);});
check('modified verdict cannot verify',()=>{const report=classify(good.input,options);report.models[0].status='refuted';assert.equal(verify(good.input,report,options).valid,false);});
check('wrong report operation cannot verify',()=>{assert.equal(verify(good.input,infer(good.input,options),options).valid,false);assert.equal(verifyGraph(good.input,classify(good.input,options),options).valid,false);});
for(const op of ['infer-dependencies','classify-with-inference']){
 check(op+' capsule independently replays',()=>assert.equal(replay(make(good.input,options,op),options).valid,true));
 check(op+' capsule rejects self-selected options',()=>assert.equal(replay(make(good.input,options,op)).valid,false));
 check(op+' rehashed altered conclusion is rejected',()=>{const c=JSON.parse(make(good.input,options,op)),r=JSON.parse(c.reportText);r.status='refuted';c.reportText=JSON.stringify(r);c.reportSha256=hash(c.reportText);assert.equal(replay(JSON.stringify(c),options).valid,false);});
}
check('capsule duplicate decoded fields are rejected',()=>{const text=make(good.input,options);assert.equal(replay(text.replace('"format":','"format":"x","for\\u006dat":'),options).valid,false);});
check('capsule unknown fields are rejected',()=>{const c=JSON.parse(make(good.input,options));c.code='execute';assert.equal(replay(JSON.stringify(c),options).valid,false);});
check('product version cannot choose verification semantics',()=>{const c=JSON.parse(make(good.input,options));c.producer.version='another-producer';assert.equal(replay(JSON.stringify(c),options).valid,true);});
check('options are detached from subsequent caller mutation',()=>{const original=JSON.stringify(options),r=classify(good.input,options);r.inference.modules.length=0;assert.equal(JSON.stringify(options),original);assert.equal(classify(good.input,options).inference.modules.length,2);});
const dir=resolve(root,'artifacts','inference-cli-'+Date.now());mkdirSync(dir,{recursive:true});
const source=resolve(dir,'source.json'),opts=resolve(dir,'options.json'),report=resolve(dir,'report.json'),capsule=resolve(dir,'capsule.json');
writeFileSync(source,JSON.stringify(good.input));writeFileSync(opts,JSON.stringify(options));
const cli=args=>spawnSync(process.execPath,[resolve(runtime,'moontxnwitness.mjs'),...args],{encoding:'utf8',windowsHide:true});
check('CLI classifies and writes exact replay capsule',()=>{const r=cli(['classify-with-inference-v4',source,'--options',opts,'--output',report,'--capsule',capsule]);assert.equal(r.status,0,r.stderr);assert.equal(replay(readFileSync(capsule,'utf8'),options).valid,true);});
check('CLI independently verifies',()=>{const r=cli(['verify-with-inference-v4',source,report,'--options',opts]);assert.equal(r.status,0,r.stderr);assert.equal(JSON.parse(r.stdout).valid,true);});
check('CLI independently replays',()=>assert.equal(cli(['replay-inference-v4',capsule,'--options',opts]).status,0));
check('CLI requires explicit registry',()=>assert.equal(cli(['classify-with-inference-v4',source]).status,2));
check('CLI refuses overwrite',()=>assert.equal(cli(['classify-with-inference-v4',source,'--options',opts,'--output',report]).status,2));
check('compiled core bytes remain unchanged',()=>assert.equal(hash(readFileSync(resolve(runtime,'core.mjs'))),before));
const summary={format:'moontxnwitness-inference-sdk-check/v1',passed:results.every(x=>x.passed),tests:results.length,coreSha256:before,failed:results.filter(x=>!x.passed),results};
const receipt=resolve(dir,'receipt.json');writeFileSync(receipt,JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:summary.passed,tests:summary.tests,failed:summary.failed,receipt}));if(!summary.passed)process.exitCode=1;
