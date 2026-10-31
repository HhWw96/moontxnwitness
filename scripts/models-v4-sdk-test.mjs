import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const modulePath=resolve(root,process.env.MTW_MODELS_SDK||'dist/models-v4.mjs');
const cliPath=resolve(root,process.env.MTW_MODELS_CLI||'dist/moontxnwitness.mjs');
const sdk=await import(pathToFileURL(modulePath));
const {classifyModelsV4:run,verifyModelsV4:verify,makeModelsCapsuleV4:make,replayModelsCapsuleV4:replay,parseModelOptionsV4:parse,ELLE_CORE_MODELS_V4:models}=sdk;
const digest=value=>createHash('sha256').update(value).digest('hex');
const corePath=resolve(dirname(modulePath),'core.mjs'),before=digest(readFileSync(corePath));
const results=[];
function test(name,fn){try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.stack});}}
function trace(body,model='point-register-v1',initial={x:'x0',y:'y0'}){return {traceSchema:3,dataModel:model,clockDomain:'model-wire-check',scope:{exclusiveWriters:true},gaps:[],events:[{kind:'snapshot',initial,consistent:true},...body].map((e,i)=>({...e,seq:i+1,time:i}))};}
const begin=tx=>({kind:'begin',tx,connection:'connection-'+tx}),commit=tx=>[{kind:'commit_request',tx},{kind:'commit_ok',tx}],read=(tx,key,version)=>({kind:'read',tx,key,version}),write=(tx,key,version,predecessor)=>({kind:'write',tx,key,version,predecessor});
const good=trace([begin('A'),read('A','x','x0'),write('A','x','x1','x0'),read('A','x','x1'),...commit('A')]);
const bad=trace([begin('A'),begin('B'),write('A','x','x1','x0'),write('B','y','y1','y0'),write('A','y','y2','y1'),write('B','x','x2','x1'),...commit('A'),...commit('B')]);
const gap=structuredClone(good);gap.events=gap.events.filter(e=>e.seq!==3);
const membership={clients:[{id:'logical-A',transactions:['A']}],clientsComplete:true};
const options=model=>({models:[model],...membership});
for(const model of models){
 test(model+' actual required rules finish',()=>{const o=options(model),r=run(good,o);assert.equal(r.models.length,1);assert.equal(r.models[0].model,model);assert.equal(r.status,'checked-compatible');assert.ok(r.models[0].rules.length>0);assert.ok(r.models[0].rules.every(x=>x.status==='checked-compatible'));assert.equal(verify(good,r,o).valid,true);});
 test(model+' retains real WW refutation',()=>{const r=run(bad,{models:[model]});assert.equal(r.status,'refuted');assert.ok(r.models[0].rules.some(x=>x.status==='refuted'));});
 test(model+' incomplete original window stays unknown',()=>assert.equal(run(gap,options(model)).status,'unknown'));
 test(model+' model status tampering is rejected',()=>{const o=options(model),r=run(good,o);r.models[0].status='refuted';assert.equal(verify(good,r,o).valid,false);});
}
const append=(tx,key,id)=>({kind:'append',tx,key,id,value:'same'}),listRead=(tx,key,ids)=>({kind:'list_read',tx,key,items:ids.map(id=>({id,value:'same'}))});
const own=trace([begin('A'),listRead('A','x',[]),append('A','x','a1'),listRead('A','x',['a1']),append('A','x','a2'),listRead('A','x',['a1','a2']),...commit('A')],'append-list-v1',{x:[],y:[]});
const listOptions={models:['snapshot-isolation'],listProfile:'captured-list-prefix-state/v2'};
const revoked=trace([begin('W'),append('W','x','w'),append('W','y','y1'),...commit('W'),begin('A'),listRead('A','y',['y1']),{kind:'savepoint',tx:'A',name:'s',instance:'s-A'},append('A','x','a'),listRead('A','x',['a']),{kind:'rollback_to',tx:'A',instance:'s-A'},...commit('A')],'append-list-v1',{x:[],y:[]});
test('explicit list profile preserves old default pending',()=>{assert.equal(run(own,{models:['snapshot-isolation']}).status,'unknown');const r=run(own,listOptions);assert.equal(r.status,'checked-compatible');assert.equal(verify(own,r,listOptions).valid,true);assert.equal(verify(own,r,{}).valid,false);});
test('all fourteen list definitions finish on the original multiappend program',()=>{const r=run(own,{models:'elle-core',listProfile:'captured-list-prefix-state/v2',...membership});assert.equal(r.models.length,14);assert.ok(r.models.every(m=>m.status==='checked-compatible'));});
test('revoked own read retains its real external-prefix constraint',()=>{const original=JSON.stringify(revoked);assert.equal(run(revoked,listOptions).status,'refuted');assert.equal(JSON.stringify(revoked),original);});
test('RC external rereads are not rejected by an SI snapshot oracle',()=>{const source=trace([begin('R'),listRead('R','x',[]),begin('W'),append('W','x','a'),...commit('W'),listRead('R','x',['a']),...commit('R')],'append-list-v1',{x:[],y:[]});const r=run(source,{models:['read-committed','snapshot-isolation'],listProfile:'captured-list-prefix-state/v2'});assert.equal(r.models[0].status,'checked-compatible');assert.equal(r.models[1].status,'refuted');});
test('independent zero source budget cannot be self-elevated',()=>{const o={models:['snapshot-isolation'],maxSourceChecks:0},r=run(good,o);assert.equal(r.status,'unknown');assert.equal(verify(good,r,o).valid,true);assert.equal(verify(good,r,{models:['snapshot-isolation']}).valid,false);});
test('given logical snapshots remain unsupported',()=>assert.equal(run(good,{models:['snapshot-isolation'],completionPolicy:'given-logical-snapshot-assertions/unsupported'}).status,'unknown'));
test('canonical parser preserves omission for CLI option merging',()=>assert.deepEqual(parse('{"maxStates":1}'),{maxStates:1}));
for(const invalid of ['{"models":["PL-1"]}','{"models":["serializable","serializable"]}','{"models":[]}','{"maxStates":100001}','{"maxSourceChecks":-1}','{"models":"elle-core","mo\\u0064els":[]}','{"listProfile":"legacy"}','{"maxAttempts":1}'])test('invalid model options '+invalid,()=>assert.throws(()=>run(good,invalid)));
test('capsule replays only under independently selected models and policy',()=>{const c=make(own,listOptions);assert.equal(replay(c,listOptions).valid,true);assert.equal(replay(c,{}).valid,false);assert.equal(replay(c,{...listOptions,maxSourceChecks:999999}).valid,false);});
test('capsule evidence mutation fails even with updated report digest',()=>{const c=JSON.parse(make(own,listOptions)),r=JSON.parse(c.reportText);r.models[0].rules[0].status='refuted';c.reportText=JSON.stringify(r);c.reportSha256=digest(c.reportText);assert.equal(replay(c,listOptions).valid,false);});
test('capsule options mutation cannot grant profile or greater budget',()=>{const c=JSON.parse(make(own,listOptions)),o=JSON.parse(c.optionsText);o.maxSourceChecks=0;c.optionsText=JSON.stringify(o);c.optionsSha256=digest(c.optionsText);assert.equal(replay(c,listOptions).valid,false);assert.equal(replay(c,o).valid,false);});
for(const key of ['sourceText','optionsText','reportText','semanticContract','algorithm','counterContract','sourceProfile'])test('capsule bound field '+key,()=>{const c=JSON.parse(make(own,listOptions));c[key]+=' ';assert.equal(replay(c,listOptions).valid,false);});
test('capsule duplicate decoded envelope key is refused',()=>{const c=make(own,listOptions);assert.equal(replay(c.replace('"format":','"format":"x","for\\u006dat":'),listOptions).valid,false);});
test('producer version is metadata and cannot select a verifier',()=>{const c=JSON.parse(make(own,listOptions));c.producer.version='unrelated-producer';assert.equal(replay(c,listOptions).valid,true);});
test('detached report edits do not mutate source or subsequent report',()=>{const original=JSON.stringify(own),r=run(own,listOptions);r.observations.history.events.length=0;assert.equal(JSON.stringify(own),original);assert.equal(run(own,listOptions).status,'checked-compatible');});
if(existsSync(cliPath)){
 const dir=resolve(root,'artifacts','model-cli-'+Date.now());mkdirSync(dir,{recursive:true});const source=resolve(dir,'source.json'),opts=resolve(dir,'options.json'),report=resolve(dir,'report.json'),capsule=resolve(dir,'capsule.json');writeFileSync(source,JSON.stringify(own));writeFileSync(opts,JSON.stringify(listOptions));
 const cli=args=>spawnSync(process.execPath,[cliPath,...args],{encoding:'utf8',windowsHide:true});
 test('CLI classify models creates source-bound report and capsule',()=>{const r=cli(['classify-models-v4',source,'--options',opts,'--output',report,'--capsule',capsule]);assert.equal(r.status,0,r.stderr);assert.equal(JSON.parse(readFileSync(report)).status,'checked-compatible');});
 test('CLI verifies with independent options',()=>{const r=cli(['verify-models-v4',source,report,'--options',opts]);assert.equal(r.status,0,r.stderr);assert.equal(JSON.parse(r.stdout).valid,true);});
 test('CLI replay refuses omitted caller source policy',()=>{const r=cli(['replay-models-v4',capsule]);assert.equal(r.status,2,r.stderr);});
 test('CLI replay accepts independent matching policy',()=>{const r=cli(['replay-models-v4',capsule,'--options',opts]);assert.equal(r.status,0,r.stderr);});
 test('CLI does not overwrite existing reports',()=>assert.equal(cli(['classify-models-v4',source,'--options',opts,'--output',report]).status,2));
}
const after=digest(readFileSync(corePath));test('compiled consumer core bytes stay unchanged',()=>assert.equal(after,before));
const summary={format:'moontxnwitness-model-namespace-sdk-check/v1',modulePath,corePath,coreSha256:before,sourceCoreUnchanged:after===before,passed:results.every(r=>r.passed),tests:results.length,results};
mkdirSync(resolve(root,'artifacts'),{recursive:true});const receipt=resolve(root,'artifacts','models-sdk-'+Date.now()+'.json');writeFileSync(receipt,JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:summary.passed,tests:summary.tests,failed:results.filter(r=>!r.passed).map(r=>({name:r.name,error:r.error})),receipt}));if(!summary.passed)process.exitCode=1;
