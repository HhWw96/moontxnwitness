// Independent counterexamples for relation code authored by another developer.
// A tiny consumer imports the local library; no implementation snapshot is copied.
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
const reviewed=['src/relation_graph_v4.mbt','src/relation_classification_v4.mbt'];
const before=sourceBindings(),outputs=resolve(root,'artifacts');mkdirSync(outputs,{recursive:true});
const storage=statfsSync(root);assert(Number(storage.bavail)*Number(storage.bsize)>=500*1024*1024,'Less than 500 MiB available: stop before building');
const parent=resolve(outputs,'validation-temp');mkdirSync(parent,{recursive:true});
const harness=mkdtempSync(resolve(parent,'v034-independent-relation-'));
mkdirSync(resolve(harness,'src/bridge'),{recursive:true});mkdirSync(resolve(harness,'temp'),{recursive:true});
const rootVersion=readFileSync(resolve(root,'moon.mod'),'utf8').match(/^version\s*=\s*"([^"]+)"/m)?.[1];
assert(rootVersion,'Missing local module version');
writeFileSync(resolve(harness,'moon.mod'),`name = "independent/relation-review"\nversion = "0.0.0"\nsource = "src"\nimport {\n  "HhWw96/moontxnwitness@${rootVersion}",\n}\n`);
writeFileSync(resolve(harness,'moon.work'),`members = [".", ${JSON.stringify(relative(harness,root).replaceAll('\\','/'))}]\n`);
writeFileSync(resolve(harness,'package.json'),'{"type":"module"}\n');
writeFileSync(resolve(harness,'src/bridge/moon.pkg'),`import {
  "HhWw96/moontxnwitness" @txn,
  "moonbitlang/core/json",
}
pkgtype(kind: "foreign_library")
options(link: { "js": { "format": "esm" } })
`);
writeFileSync(resolve(harness,'src/bridge/bridge.mbt'),`fn cats(text : String) -> Array[String] raise {
  match @json.parse(text) {
    Array(items) => items.map(item => { match item { String(s) => s; _ => abort("Expected category name") } })
    _ => abort("Expected categories array")
  }
}
#export_name("classify")
pub fn classify(text : String, categories : String, states : Int, edges : Int, graph : Int) -> String {
  try {
    match @txn.parse_history_v4(text) {
      Err(reason) => ({"error":Json(reason)} : Json).stringify()
      Ok(history) => @txn.render_relation_classification_v4(@txn.classify_relation_point_v4(history,categories=cats(categories),max_states=states,max_edge_checks=edges,max_graph_checks=graph))
    }
  } catch { error => ({"error":Json(error.to_string())} : Json).stringify() }
}
#export_name("graph")
pub fn graph(text : String, budget : Int) -> String {
  match @txn.parse_history_v4(text) {
    Err(reason) => ({"error":Json(reason)} : Json).stringify()
    Ok(history) => match @txn.build_relation_point_graph_v4(history,max_checks=budget) {
      Err(reason) => ({"error":Json(reason)} : Json).stringify()
      Ok(result) => @txn.relation_point_graph_v4_json(result).stringify()
    }
  }
}
#export_name("verify")
pub fn verify(text : String, report : String, categories : String, states : Int, edges : Int, graph : Int) -> Bool {
  try {
    match @txn.parse_history_v4(text) {
      Err(_) => false
      Ok(history) => @txn.verify_relation_classification_v4(history,@json.parse(report),categories=cats(categories),max_states=states,max_edge_checks=edges,max_graph_checks=graph)
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
if(compiled.status!==0){writeFileSync(resolve(outputs,'v034-independent-relation-build-failure.json'),JSON.stringify({passed:false,status:compiled.status,stdout:compiled.stdout,stderr:compiled.stderr,harness,sourceBefore:before,sourceAfter:sourceBindings()},null,2));throw new Error('Independent consumer build failed: '+compiled.stderr);}
const compiledPaths=[];
function findBridge(directory){for(const entry of readdirSync(directory,{withFileTypes:true})){const path=join(directory,entry.name);if(entry.isDirectory())findBridge(path);else if(entry.name==='bridge.js')compiledPaths.push(path);}}
findBridge(resolve(harness,'_build/js/release/build'));
assert.equal(compiledPaths.length,1,'Independent build must expose one bridge');
const bridgePath=compiledPaths[0];
const api=await import(pathToFileURL(bridgePath).href),results=[];
const defaultCategories=['G0','G1a','G1b','G1c','G2-item','INT'];
let lastObserved=null,lastSource=null,lastOptions=null;
const opt=o=>({categories:defaultCategories,states:100000,edges:1000000,graph:1000000,...o});
function classify(source,options={}){lastSource=source;lastOptions=opt(options);lastObserved=JSON.parse(api.classify(JSON.stringify(source),JSON.stringify(lastOptions.categories),lastOptions.states,lastOptions.edges,lastOptions.graph));assert(!lastObserved.error,lastObserved.error);return lastObserved;}
function graph(source,budget=1000000){lastSource=source;lastOptions={graph:budget};lastObserved=JSON.parse(api.graph(JSON.stringify(source),budget));assert(!lastObserved.error,lastObserved.error);return lastObserved;}
function verify(source,report,options={}){const o=opt(options);return api.verify(JSON.stringify(source),JSON.stringify(report),JSON.stringify(o.categories),o.states,o.edges,o.graph);}
function summary(r){if(!r)return null;return {status:r.judgment?.status??r.reason,complete:r.judgment?.dependencyGraphComplete??r.complete,journal:r.execution?.sourceJournalComplete??r.journalComplete,rules:Object.fromEntries(Object.entries(r.judgment?.rules??r.directChecks??{}).map(([k,v])=>[k,{status:v.status,specific:v.evidence?.specificCategory,requested:v.evidence?.requestedCategory}])),gaps:(r.judgment?.sourceOrOrderGaps??r.gaps??[]).map(g=>g.code)};}
function check(name,fn){lastObserved=null;lastSource=null;lastOptions=null;try{fn();results.push({name,passed:true,observed:summary(lastObserved)});}catch(error){results.push({name,passed:false,error:error.message,observed:summary(lastObserved),input:lastSource,options:lastOptions,actualReport:lastObserved});}}
const row=(key,version,value='same')=>({key,version,values:{value}});
const begin=tx=>({kind:'begin',tx,connection:'connection:'+tx});
const end=tx=>[{kind:'commit_request',tx},{kind:'commit_ok',tx}];
const write=(tx,key,version,predecessor,{table='items',action='update',value='same'}={})=>({kind:'row_write',tx,relation:table,key,action,version,predecessor,values:action==='delete'?null:{value}});
const read=(tx,key,version,{table='items',value='same'}={})=>({kind:'row_read',tx,relation:table,predicate:[{column:'id',op:'eq',value:key}],rows:version===null?[]:[row(key,version,value)],complete:true});
const mark=(tx,instance='s')=>({kind:'savepoint',tx,name:'same',instance});
const undo=(tx,instance='s')=>({kind:'rollback_to',tx,instance});
function trace(body,{initial={items:[row('1','v0'),row('2','u0')]},schema={items:{primaryKey:'id',columns:{id:'int64',value:'text'}}},gaps=[],exclusive=true}={}){return {traceSchema:3,dataModel:'relation-set-v1',relationSchema:schema,clockDomain:'independent-relation',scope:{exclusiveWriters:exclusive,completeSnapshotTables:Object.keys(schema)},events:[{kind:'snapshot',consistent:true,initial},...body].map((e,i)=>({seq:i+1,time:i,...e})),gaps};}
const rule=(report,category)=>report.judgment.rules[category];
function notComplete(report){assert.notEqual(report.judgment.status,'checked-compatible');assert.equal(report.judgment.dependencyGraphComplete,false);}
const simple=trace([begin('R'),read('R','1','v0'),...end('R')]);
check('point read completes six declared category checks with separate model scope',()=>{const r=classify(simple);assert.equal(r.judgment.status,'checked-compatible');assert.equal(r.judgment.acceptsIsolationModels,false);assert.deepEqual(r.execution.categories,defaultCategories);assert(verify(simple,r));});
const changed=trace([begin('W'),write('W','1','v1','v0'),...end('W'),begin('R'),read('R','1','v0'),read('R','1','v1'),...end('R')]);
check('formal INT includes two external same-key point reads without own write',()=>{const r=classify(changed,{categories:['INT']});assert.equal(rule(r,'INT').status,'refuted');assert.equal(r.judgment.acceptsIsolationModels,false);});
check('formal INT keeps external read expectation across savepoint rollback',()=>{const s=trace([begin('W'),write('W','1','v1','v0'),...end('W'),begin('R'),mark('R'),read('R','1','v0'),undo('R'),read('R','1','v1'),...end('R')]);assert.equal(rule(classify(s,{categories:['INT']}),'INT').status,'refuted');});
check('formal INT detects a point row becoming uniquely absent within a transaction',()=>{const s=trace([begin('W'),write('W','1','deleted','v0',{action:'delete'}),...end('W'),begin('R'),read('R','1','v0'),read('R','1',null),...end('R')]);assert.equal(rule(classify(s,{categories:['INT']}),'INT').status,'refuted');});
check('formal INT detects initial absence becoming a known row within a transaction',()=>{const s=trace([begin('W'),write('W','1','inserted',null,{action:'insert'}),...end('W'),begin('R'),read('R','1',null),read('R','1','inserted'),...end('R')],{initial:{items:[]}});assert.equal(rule(classify(s,{categories:['INT']}),'INT').status,'refuted');});
check('own-at-delivery row read never becomes an irreversible external base',()=>{const s=trace([begin('R'),mark('R'),write('R','1','own','v0'),read('R','1','own'),undo('R'),read('R','1','v0'),...end('R')]);assert.equal(rule(classify(s,{categories:['INT']}),'INT').status,'checked-compatible');});
check('different point keys keep independent internal expectations',()=>{const s=trace([begin('R'),read('R','1','v0'),read('R','2','u0'),read('R','1','v0'),...end('R')]);assert.equal(rule(classify(s,{categories:['INT']}),'INT').status,'checked-compatible');});
check('same external row version repeated does not create INT',()=>{const s=trace([begin('R'),read('R','1','v0'),read('R','1','v0'),...end('R')]);assert.equal(rule(classify(s,{categories:['INT']}),'INT').status,'checked-compatible');});
const restored=trace([begin('A'),mark('A'),write('A','1','gone','v0',{action:'delete'}),undo('A'),...end('A'),begin('R'),read('R','1','v0'),...end('R')]);
check('savepoint-revoked tombstone does not invalidate surviving positive row source',()=>{const g=graph(restored);assert.equal(g.journalComplete,true);assert(!JSON.stringify(g).includes('relation-effect-ledger-mismatch'));assert.equal(g.directChecks.G1a.status,'checked-compatible');});
check('whole abort restores all write effects in actual journal',()=>{const s=trace([begin('A'),write('A','1','aborted','v0'),{kind:'rollback_ok',tx:'A'},begin('R'),read('R','1','v0'),...end('R')]);const g=graph(s);const a=g.sourceAudit.find(x=>x.fact.version==='aborted');assert.equal(a.survivesSavepoints,false);assert.equal(a.finalCommittedEffect,false);assert.equal(a.writerOutcome,'aborted');assert.equal(g.journalComplete,true);});
for(const status of ['aborted','revoked','intermediate','unknown'])check('raw '+status+' tombstone remains an alternative empty-result source',()=>{
 let body=[begin('A')];if(status==='revoked')body.push(mark('A'));body.push(write('A','1','a-delete','v0',{action:'delete'}));
 if(status==='aborted')body.push({kind:'rollback_ok',tx:'A'});else if(status==='revoked')body.push(undo('A'),...end('A'));else if(status==='unknown')body.push({kind:'disconnect',tx:'A'});else body.push(write('A','1','a-reinsert','a-delete',{action:'insert'}),...end('A'));
 const pred=status==='intermediate'?'a-reinsert':'v0';body.push(begin('B'),write('B','1','b-delete',pred,{action:'delete'}),...end('B'),begin('R'),read('R','1',null),...end('R'));
 const r=classify(trace(body));notComplete(r);assert(r.judgment.sourceOrOrderGaps.some(g=>JSON.stringify(g).includes('ambiguous-point-absence')));
});
check('initial absence plus raw tombstone cannot select final delete uniquely',()=>{const s=trace([begin('W'),write('W','1','inserted',null,{action:'insert'}),write('W','1','deleted','inserted',{action:'delete'}),...end('W'),begin('R'),read('R','1',null),...end('R')],{initial:{items:[]}});notComplete(classify(s));});
check('single known initial absence can be resolved with no delete candidates',()=>{const s=trace([begin('R'),read('R','1',null),...end('R')],{initial:{items:[]}});const r=classify(s);assert.equal(r.judgment.status,'checked-compatible');assert(r.inferences.readSourceResolutions.some(x=>x.reason==='unique-initial-point-absence'));});
check('single final committed tombstone can explain a delivered empty result',()=>{const s=trace([begin('W'),write('W','1','deleted','v0',{action:'delete'}),...end('W'),begin('R'),read('R','1',null),...end('R')]);const r=classify(s);assert.equal(r.judgment.status,'checked-compatible');assert(r.inferences.readSourceResolutions.some(x=>x.reason==='unique-final-tombstone-absence'));});
check('later cross-connection capture sequence cannot prune an aborted delete candidate',()=>{const s=trace([begin('A'),begin('B'),begin('R'),read('R','1',null),write('A','1','a-delete','v0',{action:'delete'}),{kind:'rollback_ok',tx:'A'},write('B','1','b-delete','v0',{action:'delete'}),...end('B'),...end('R')]);notComplete(classify(s));});
const abortedRead=trace([begin('W'),write('W','1','bad','v0'),{kind:'rollback_ok',tx:'W'},begin('R'),write('R','1','own','v0'),read('R','1','bad'),...end('R')]);
check('own-state INT and external aborted-source G1a remain independent',()=>{const r=classify(abortedRead);assert.equal(rule(r,'G1a').status,'refuted');assert.equal(rule(r,'INT').status,'refuted');assert.notEqual(rule(r,'G1b').status,'refuted');});
const intermediate=trace([begin('W'),write('W','1','mid','v0'),write('W','1','final','mid'),...end('W'),begin('R'),write('R','1','own','final'),read('R','1','mid'),...end('R')]);
check('same-valued intermediate version and INT retain both concrete identities',()=>{const r=classify(intermediate);assert.equal(rule(r,'G1b').status,'refuted');assert.equal(rule(r,'INT').status,'refuted');assert.equal(rule(r,'G1b').evidence.proofs[0].source.fact.version,'mid');});
check('zero cycle budgets retain direct G1a and INT witnesses',()=>{const r=classify(abortedRead,{states:0,edges:0});assert.equal(rule(r,'G1a').status,'refuted');assert.equal(rule(r,'INT').status,'refuted');assert.equal(r.judgment.status,'refuted');assert.equal(rule(r,'G1a').states,0);});
check('unknown graph budget cannot report completed source audits',()=>{const r=classify(simple,{graph:0});assert.equal(r.judgment.status,'inconclusive');assert.equal(r.execution.sourceJournalComplete,false);for(const source of r.inferences.sourceAudit){assert.equal(source.effectAuditComplete,false);assert.equal(source.survivesSavepoints,null);assert.equal(source.finalCommittedEffect,null);}});
check('branching committed row-version chains remain incomplete',()=>{const s=trace([begin('A'),write('A','1','a','v0'),...end('A'),begin('B'),write('B','1','b','v0'),...end('B'),begin('R'),read('R','1','a'),...end('R')]);notComplete(classify(s));});
check('missing predecessor row source cannot become completed classification',()=>{const s=trace([begin('W'),write('W','1','new','missing'),...end('W')]);notComplete(classify(s));});
check('primary-equality query returning multiple rows remains unknown',()=>{const query=read('R','1','v0');query.rows.push(row('2','u0'));const r=classify(trace([begin('R'),query,...end('R')]));notComplete(r);});
check('incomplete fetch does not infer a complete point read',()=>{const query=read('R','1','v0');query.complete=false;notComplete(classify(trace([begin('R'),query,...end('R')])));});
const g0=trace([begin('A'),begin('B'),write('A','1','a1','v0'),write('B','1','b1','a1'),write('B','2','b2','u0'),write('A','2','a2','b2'),...end('A'),...end('B')]);
check('G1c request keeps a more specific WW-only G0 witness',()=>{const r=classify(g0,{categories:['G1c']});assert.equal(rule(r,'G1c').evidence.requestedCategory,'G1c');assert.equal(rule(r,'G1c').evidence.specificCategory,'G0');assert(r.judgment.impliedAnomalies.includes('G0'));});
const skew=trace([begin('A'),begin('B'),read('A','1','v0'),write('A','2','a1','u0'),read('B','2','u0'),write('B','1','b1','v0'),...end('A'),...end('B')]);
check('item anti-dependency cycle does not inherit an unrelated category name',()=>{const r=classify(skew,{categories:['G0','G1c','G2-item']});assert.equal(rule(r,'G2-item').status,'refuted');assert.equal(rule(r,'G2-item').evidence.specificCategory,'G2-item');assert.notEqual(rule(r,'G0').status,'refuted');assert.notEqual(rule(r,'G1c').status,'refuted');});
for(const category of ['G1a','G1b','INT'])check('explicit direct '+category+' has matching request and witness metadata',()=>{const source=category==='G1b'?intermediate:abortedRead;const r=classify(source,{categories:[category]});assert.equal(rule(r,category).evidence.requestedCategory,category);assert.equal(rule(r,category).evidence.specificCategory,category);});
check('typed primary keys and table names cannot share graph identities',()=>{const schema={'a_b':{primaryKey:'id',columns:{id:'int64',value:'text'}},a:{primaryKey:'id',columns:{id:'text',value:'text'}}};const initial={'a_b':[row('1','i0')],a:[row('1','t0')]};const source=trace([begin('R'),read('R','1','i0',{table:'a_b'}),read('R','1','t0',{table:'a'}),...end('R')],{schema,initial});const g=graph(source);assert.equal(g.complete,true);const ids=g.identities.filter(x=>x.primaryKey==='1');assert.equal(ids.length,2);assert.notEqual(ids[0].graphKey,ids[1].graphKey);assert.deepEqual(new Set(ids.map(x=>x.primaryType)),new Set(['int64','text']));});
check('a version from another table never supplies a valid point source',()=>{const schema={left:{primaryKey:'id',columns:{id:'int64',value:'text'}},right:{primaryKey:'id',columns:{id:'int64',value:'text'}}};const source=trace([begin('R'),read('R','1','l0',{table:'right'}),...end('R')],{schema,initial:{left:[row('1','l0')],right:[row('1','r0')]}});notComplete(classify(source));});
check('source/query/version/identity and contract tampering are independently rejected',()=>{const r=classify(skew,{categories:['G2-item']});assert(verify(skew,r,{categories:['G2-item']}));for(const mutate of [x=>x.algorithm='unknown',x=>x.semanticContract='unknown',x=>x.execution.counterContract='unknown',x=>x.execution.limits.graphChecks=0,x=>x.observations.document.events[1].tx='other',x=>x.judgment.rules['G2-item'].evidence.edges[0].identity.primaryKey='other']){const forged=structuredClone(r);mutate(forged);assert.equal(verify(skew,forged,{categories:['G2-item']}),false);}});
check('caller budgets and categories cannot be authorized by a supplied report',()=>{const r=classify(skew,{categories:['G2-item'],states:0});assert(verify(skew,r,{categories:['G2-item'],states:0}));assert.equal(verify(skew,r,{categories:['G2-item']}),false);assert.equal(verify(skew,r,{categories:['G1c'],states:0}),false);});
const after=sourceBindings(),sourceUnchanged=JSON.stringify(after)===JSON.stringify(before);
if(!sourceUnchanged)results.push({name:'reviewed and dependency sources unchanged during independent checks',passed:false,error:'Executable source changed during test'});
const failed=results.filter(r=>!r.passed),receipt={suite:'v034-independent-relation-counterexamples-1',utc:new Date().toISOString(),passed:failed.length===0,checks:results.length,failed:failed.length,
 testSha256:hash(readFileSync(import.meta.filename)),reviewedImplementationAuthoredByThisReviewer:false,reviewedModules:reviewed,actualDatabaseExecution:false,formalPerformanceMeasurement:false,publicWireExercised:false,
 harness:{path:harness,bridgeSha256:hash(readFileSync(bridgePath)),localDependency:root,sourceCopied:false,buildArgs:['build','src/bridge','--target','js','--release','--jobs','1']},
 sourceUnchanged,sourceBefore:before,sourceAfter:after,results};
writeFileSync(resolve(outputs,'v034-independent-relation.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({suite:receipt.suite,passed:receipt.passed,checks:receipt.checks,failed:receipt.failed,failures:failed.map(x=>({name:x.name,error:x.error,observed:x.observed})),receipt:'artifacts/v034-independent-relation.json'}));
if(failed.length)process.exitCode=1;
