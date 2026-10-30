// Independent formal-INT counterexamples; no production bridge or dist is rebuilt.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,readdirSync,mkdirSync,mkdtempSync,statfsSync} from 'node:fs';
import {resolve,relative,join,delimiter} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const root=resolve(import.meta.dirname,'..'),hash=x=>createHash('sha256').update(x).digest('hex');
function sourceBindings(){
 const paths=['moon.mod'];
 function visit(dir){for(const entry of readdirSync(dir,{withFileTypes:true})){const path=join(dir,entry.name);if(entry.isDirectory())visit(path);else if(entry.name.endsWith('.mbt')||entry.name==='moon.pkg')paths.push(relative(root,path).replaceAll('\\','/'));}}
 visit(resolve(root,'src'));paths.sort();return Object.fromEntries(paths.map(path=>[path,hash(readFileSync(resolve(root,path)))]));
}
const before=sourceBindings(),outputs=resolve(root,'artifacts');mkdirSync(outputs,{recursive:true});
const storage=statfsSync(root);assert(Number(storage.bavail)*Number(storage.bsize)>=500*1024*1024,'Less than 500 MiB available');
const parent=resolve(outputs,'validation-temp');mkdirSync(parent,{recursive:true});
const harness=mkdtempSync(resolve(parent,'v034-independent-int-'));
mkdirSync(resolve(harness,'src/bridge'),{recursive:true});mkdirSync(resolve(harness,'temp'),{recursive:true});
const version=readFileSync(resolve(root,'moon.mod'),'utf8').match(/^version\s*=\s*"([^"]+)"/m)?.[1];assert(version);
writeFileSync(resolve(harness,'moon.mod'),`name = "independent/internal-review"\nversion = "0.0.0"\nsource = "src"\nimport {\n "HhWw96/moontxnwitness@${version}",\n}\n`);
writeFileSync(resolve(harness,'moon.work'),`members = [".", ${JSON.stringify(relative(harness,root).replaceAll('\\','/'))}]\n`);
writeFileSync(resolve(harness,'package.json'),'{"type":"module"}\n');
writeFileSync(resolve(harness,'src/bridge/moon.pkg'),`import {\n "HhWw96/moontxnwitness" @txn,\n "moonbitlang/core/json",\n}\npkgtype(kind: "foreign_library")\noptions(link: { "js": { "format": "esm" } })\n`);
writeFileSync(resolve(harness,'src/bridge/bridge.mbt'),`#export_name("inspect")
pub fn inspect(text : String, budget : Int) -> String {
 match @txn.parse_history_v4(text) {
  Err(reason) => ({"error":Json(reason)} : Json).stringify()
  Ok(history) => @txn.internal_consistency_v4_json(@txn.inspect_internal_consistency_v4(history,max_checks=budget)).stringify()
 }
}
#export_name("verify")
pub fn verify(text : String, report : String, budget : Int) -> Bool {
 try {
  match @txn.parse_history_v4(text) {
   Err(_) => false
   Ok(history) => @txn.verify_internal_consistency_v4(history,@json.parse(report),max_checks=budget)
  }
 } catch { _ => false }
}
`);
const home=process.env.MOON_HOME||'D:\\CodexScratch\\toolchains\\moonbit-0.10.16-b1a0e846e';
const env={...process.env,MOON_HOME:home,TEMP:resolve(harness,'temp'),TMP:resolve(harness,'temp')};
const inherited=Object.entries(env).find(([k])=>k.toLowerCase()==='path')?.[1]||'';
for(const key of Object.keys(env))if(key.toLowerCase()==='path')delete env[key];
env.PATH=[resolve(home,'bin'),resolve(process.execPath,'..'),inherited].join(delimiter);
const compiled=spawnSync(resolve(home,'bin',process.platform==='win32'?'moon.exe':'moon'),['build','src/bridge','--target','js','--release','--jobs','1'],{cwd:harness,env,encoding:'utf8',windowsHide:true,maxBuffer:6*1024*1024});
writeFileSync(resolve(harness,'build.txt'),(compiled.stdout||'')+(compiled.stderr||''));
if(compiled.status!==0){writeFileSync(resolve(outputs,'v034-independent-int-build-failure.json'),JSON.stringify({passed:false,status:compiled.status,stdout:compiled.stdout,stderr:compiled.stderr,harness},null,2));throw Error('Independent consumer build failed: '+compiled.stderr);}
const bridges=[];function find(dir){for(const e of readdirSync(dir,{withFileTypes:true})){const p=join(dir,e.name);if(e.isDirectory())find(p);else if(e.name==='bridge.js')bridges.push(p);}}
find(resolve(harness,'_build/js/release/build'));assert.equal(bridges.length,1);
const api=await import(pathToFileURL(bridges[0]).href),results=[];let lastSource,lastReport,historyChecks=0;
function inspect(source,budget=1000000){lastSource=source;historyChecks++;lastReport=JSON.parse(api.inspect(JSON.stringify(source),budget));assert(!lastReport.error,lastReport.error);return lastReport;}
function verify(source,report,budget=1000000){return api.verify(JSON.stringify(source),JSON.stringify(report),budget);}
function check(name,fn){lastSource=null;lastReport=null;try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.message,input:lastSource,report:lastReport});}}
const begin=tx=>({kind:'begin',tx,connection:'c:'+tx});
const commit=tx=>[{kind:'commit_request',tx},{kind:'commit_ok',tx}];
const read=(tx,key,version)=>({kind:'read',tx,key,version});
const write=(tx,key,version,predecessor)=>({kind:'write',tx,key,version,predecessor});
const append=(tx,key,id)=>({kind:'append',tx,key,id,value:'same'});
const item=id=>({id,value:'same'});
const listRead=(tx,key,ids)=>({kind:'list_read',tx,key,items:ids.map(item)});
function trace(body,{list=false,gaps=[]}={}){return {traceSchema:3,dataModel:list?'append-list-v1':'point-register-v1',clockDomain:'independent-int',scope:{exclusiveWriters:true},events:[{kind:'snapshot',consistent:true,initial:list?{x:[item('p')],y:[item('q')]}:{x:'x0',y:'y0'}},...body].map((e,i)=>({seq:i+1,time:i,...e})),gaps};}
function lifecycle(seed,list,corrupt){
 let n=seed>>>0;const rand=max=>{n^=n<<13;n^=n>>>17;n^=n<<5;return (n>>>0)%max};
 let serial=0,state=list?{x:['p'],y:['q']}:{x:'x0',y:'y0'};const initial=structuredClone(state),points=[];
 const body=[begin('R')],observe=k=>list?listRead('R',k,state[k]):read('R',k,state[k]);body.push(observe('x'),observe('y'));
 for(let step=0;step<32;step++){
  const action=rand(5),key=rand(2)?'x':'y';
  if(action===0){const id='write-'+seed+'-'+(++serial);if(list){body.push(append('R',key,id));state[key].push(id);}else{body.push(write('R',key,id,state[key]));state[key]=id;}}
  else if(action===1&&points.length<6){const id='save-'+(++serial);points.push({id,state:structuredClone(state)});body.push({kind:'savepoint',tx:'R',name:id,instance:id});}
  else if(action===2&&points.length){const pos=rand(points.length),point=points[pos];body.push({kind:'rollback_to',tx:'R',instance:point.id});state=structuredClone(point.state);points.splice(pos+1);}
  else if(action===3&&points.length){const point=points.pop();body.push({kind:'release',tx:'R',instance:point.id});}
  else body.push(observe(key));
 }
 if(corrupt){const id='final-'+seed;if(list){const previous=state.x.slice();body.push(append('R','x',id),listRead('R','x',previous));}else body.push(write('R','x',id,state.x),read('R','x',initial.x));}
 else body.push(observe('x'),observe('y'));
 return trace([...body,...commit('R')],{list});
}
for(const list of [false,true])for(const corrupt of [false,true])check(`${list?'list':'register'} ${corrupt?'refutes deliberate stale own read':'accepts legal effective rollback lifecycle'} across 64 independent seeds`,()=>{
 for(let seed=1;seed<=64;seed++){
  const source=lifecycle(seed,list,corrupt),r=inspect(source);assert.equal(r.status,corrupt?'refuted':'checked',`seed=${seed}`);assert(verify(source,r));
  assert.equal(r.scope.acceptsIsolationModels,false);assert.equal(r.scope.databaseProductIsolationLevelAsserted,false);
 }
});
for(const list of [false,true])check(`${list?'list':'register'} shadowed savepoint names restore only after inner release`,()=>{
 const mark=instance=>({kind:'savepoint',tx:'R',name:'same',instance}),undo=instance=>({kind:'rollback_to',tx:'R',instance});
 const source=trace(list?[begin('R'),listRead('R','x',['p']),mark('outer'),append('R','x','a'),mark('inner'),append('R','x','b'),listRead('R','x',['p','a','b']),undo('inner'),listRead('R','x',['p','a']),{kind:'release',tx:'R',instance:'inner'},undo('outer'),listRead('R','x',['p']),...commit('R')]
 :[begin('R'),read('R','x','x0'),mark('outer'),write('R','x','a','x0'),mark('inner'),write('R','x','b','a'),read('R','x','b'),undo('inner'),read('R','x','a'),{kind:'release',tx:'R',instance:'inner'},undo('outer'),read('R','x','x0'),...commit('R')],{list});
 const r=inspect(source);assert.equal(r.status,'checked');assert(verify(source,r));
});
const witness=trace([begin('R'),read('R','x','x0'),write('R','x','r1','x0'),read('R','x','x0'),...commit('R')]);
check('first witness remains tied to original event pair',()=>{const source=structuredClone(witness);source.events.splice(-2,0,{kind:'read',tx:'R',key:'x',version:'r1'},{kind:'read',tx:'R',key:'x',version:'x0'});source.events=source.events.map((e,i)=>({...e,seq:i+1,time:i}));const r=inspect(source);assert.equal(r.findings.length,1);assert.equal(r.findings[0].evidence.actualObservation.eventSeq,5);assert.equal(r.findings[0].evidence.expected.observation.eventSeq,4);});
check('unlocated journal gap blocks a purported program proof',()=>{const source=structuredClone(witness);source.gaps=[{code:'missing_segment',message:'Unknown program segment'}];const r=inspect(source);assert.equal(r.status,'unknown');assert.equal(r.findings.length,0);});
check('later unproved SQL preserves earlier reliable INT',()=>{const source=trace([begin('R'),write('R','x','r1','x0'),read('R','x','x0'),{kind:'statement',tx:'R',sql:'UPDATE unknown SET value=1'},...commit('R')]);assert.equal(inspect(source).status,'refuted');});
check('earlier unproved SQL does not authorize proof across omitted writes',()=>{const source=trace([begin('R'),{kind:'statement',tx:'R',sql:'UPDATE unknown SET value=1'},write('R','x','r1','x0'),read('R','x','x0'),...commit('R')]);const r=inspect(source);assert.equal(r.status,'unknown');assert.equal(r.findings.length,0);});
check('aborted observer cannot refute committed INT',()=>{const source=trace([begin('R'),write('R','x','r1','x0'),read('R','x','x0'),{kind:'rollback_ok',tx:'R'}]);assert.notEqual(inspect(source).status,'refuted');});
check('missing actual read source is a gap, never a guessed witness',()=>{const source=trace([begin('R'),write('R','x','r1','x0'),read('R','x','missing'),...commit('R')]);const r=inspect(source);assert.equal(r.status,'unknown');assert.equal(r.findings.length,0);});
check('exact and one-short work budgets remain explicit',()=>{const full=inspect(witness),used=full.execution.checks;assert.equal(inspect(witness,used).status,'refuted');const short=inspect(witness,used-1);assert.equal(short.execution.limited,true);assert.equal(short.coverage.complete,false);assert(verify(witness,short,used-1));assert.equal(verify(witness,short,used),false);});
check('negative and oversized budgets grant zero work',()=>{for(const budget of [-1,1000001]){const r=inspect(witness,budget);assert.equal(r.status,'invalid-budget');assert.equal(r.execution.checks,0);assert.equal(r.findings.length,0);}});
check('contract, evidence and caller-budget tampering is rejected',()=>{const r=inspect(witness);assert(verify(witness,r));for(const mutate of [x=>x.algorithm='other',x=>x.semanticContract='other',x=>x.definition.id='other',x=>x.scope.acceptsIsolationModels=true,x=>x.execution.limits.maxChecks=0,x=>x.findings[0].evidence.actualObservation.eventSeq=2]){const bad=structuredClone(r);mutate(bad);assert.equal(verify(witness,bad),false);}assert.equal(verify(witness,r,0),false);});
check('declared history remains explicitly unsupported',()=>{const r=inspect({schemaVersion:1,model:'serializable',initial:{x:'x0'},transactions:[]});assert.equal(r.status,'unsupported');assert.equal(r.coverage.complete,false);});
const after=sourceBindings(),unchanged=JSON.stringify(before)===JSON.stringify(after);
if(!unchanged)results.push({name:'dependency source hashes unchanged during independent consumer run',passed:false,error:'Dependency sources changed during test'});
const failures=results.filter(r=>!r.passed),receipt={suite:'v034-independent-int-counterexamples-1',passed:failures.length===0,checks:results.length,histories:historyChecks,failed:failures.length,
 reviewedImplementationAuthoredByThisReviewer:false,actualDatabaseExecution:false,formalPerformanceMeasurement:false,publicWireExercised:false,
 reviewedModules:['src/internal_consistency_v4.mbt'],harness:{path:harness,localDependency:root,sourceCopied:false,bridgeSha256:hash(readFileSync(bridges[0]))},sourceUnchanged:unchanged,sourceBefore:before,sourceAfter:after,results};
writeFileSync(resolve(outputs,'v034-independent-int.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({suite:receipt.suite,passed:receipt.passed,checks:receipt.checks,histories:receipt.histories,failed:receipt.failed,failures:failures.map(x=>({name:x.name,error:x.error})),receipt:'artifacts/v034-independent-int.json'}));
if(failures.length)process.exitCode=1;
