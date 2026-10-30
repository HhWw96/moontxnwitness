// Source-rule and formal INT coexistence, separate from the frozen first 35 cases.
// Run the base independent consumer first so this uses its exact bound runtime.
import assert from 'node:assert/strict';
import {readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {resolve,relative,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(import.meta.dirname,'..'),hash=x=>createHash('sha256').update(x).digest('hex');
function bindings(){const names=['moon.mod'];function scan(dir){for(const e of readdirSync(dir,{withFileTypes:true})){const path=join(dir,e.name);if(e.isDirectory())scan(path);else if(e.name.endsWith('.mbt')||e.name==='moon.pkg')names.push(relative(root,path).replaceAll('\\','/'));}}scan(resolve(root,'src'));names.sort();return Object.fromEntries(names.map(n=>[n,hash(readFileSync(resolve(root,n)))]));}
const before=bindings(),base=JSON.parse(readFileSync(resolve(root,'artifacts/v034-independent-relation.json'),'utf8'));
assert.equal(base.passed,true,'First run the unchanged base independent relation suite successfully');
assert.deepEqual(before,base.sourceAfter,'Base runtime is not bound to current sources');
const compiled=[];function find(dir){for(const e of readdirSync(dir,{withFileTypes:true})){const path=join(dir,e.name);if(e.isDirectory())find(path);else if(e.name==='bridge.js')compiled.push(path);}}find(resolve(base.harness.path,'_build/js/release/build'));
assert.equal(compiled.length,1);assert.equal(hash(readFileSync(compiled[0])),base.harness.bridgeSha256);
const api=await import(pathToFileURL(compiled[0]).href),results=[];
const row=(key,version)=>({key,version,values:{value:'same'}});
const begin=tx=>({kind:'begin',tx,connection:tx});
const end=tx=>[{kind:'commit_request',tx},{kind:'commit_ok',tx}];
const write=(tx,key,version,predecessor)=>({kind:'row_write',tx,relation:'items',key,action:'update',version,predecessor,values:{value:'same'}});
const read=(tx,key,version)=>({kind:'row_read',tx,relation:'items',predicate:[{column:'id',op:'eq',value:key}],rows:[row(key,version)],complete:true});
const trace=body=>({traceSchema:3,dataModel:'relation-set-v1',relationSchema:{items:{primaryKey:'id',columns:{id:'int64',value:'text'}}},clockDomain:'independent-relation-addons',scope:{exclusiveWriters:true,completeSnapshotTables:['items']},events:[{kind:'snapshot',consistent:true,initial:{items:[row('1','v0'),row('2','u0')]}},...body].map((e,i)=>({seq:i+1,time:i,...e})),gaps:[]});
let actual=null,input=null,options=null;
function classify(source,{states=100000,edges=1000000}={}){input=source;options={states,edges};actual=JSON.parse(api.classify(JSON.stringify(source),JSON.stringify(['G1a','G1b','INT']),states,edges,1000000));assert(!actual.error,actual.error);return actual;}
const status=(r,k)=>r.judgment.rules[k].status;
function check(name,fn){actual=null;input=null;options=null;try{fn();results.push({name,passed:true,observed:{status:actual.judgment.status,rules:Object.fromEntries(['G1a','G1b','INT'].map(k=>[k,status(actual,k)]))}});}catch(error){results.push({name,passed:false,error:error.message,input,options,actualReport:actual});}}
const failedSource=trace([begin('W'),write('W','1','aborted','v0'),{kind:'rollback_ok',tx:'W'},begin('R'),read('R','1','v0'),read('R','1','aborted'),...end('R')]);
check('external-base INT and aborted-source G1a both retain original known identities',()=>{const r=classify(failedSource);assert.equal(status(r,'INT'),'refuted');assert.equal(status(r,'G1a'),'refuted');assert.notEqual(status(r,'G1b'),'refuted');});
check('zero cycle budgets cannot hide two independent direct source witnesses',()=>{const r=classify(failedSource,{states:0,edges:0});assert.equal(status(r,'INT'),'refuted');assert.equal(status(r,'G1a'),'refuted');});
check('external-base INT and nonfinal committed-source G1b remain independent',()=>{const s=trace([begin('W'),write('W','1','mid','v0'),write('W','1','final','mid'),...end('W'),begin('R'),read('R','1','v0'),read('R','1','mid'),...end('R')]);const r=classify(s);assert.equal(status(r,'INT'),'refuted');assert.equal(status(r,'G1b'),'refuted');assert.notEqual(status(r,'G1a'),'refuted');});
check('known observed version with uncertain writer outcome can still refute formal INT',()=>{const s=trace([begin('W'),write('W','1','uncertain','v0'),{kind:'disconnect',tx:'W'},begin('R'),read('R','1','v0'),read('R','1','uncertain'),...end('R')]);const r=classify(s);assert.equal(status(r,'INT'),'refuted');assert.notEqual(status(r,'G1a'),'refuted');assert.notEqual(status(r,'G1b'),'refuted');assert.equal(r.judgment.dependencyGraphComplete,false);});
check('missing version producer remains unknown rather than completed INT',()=>{const s=trace([begin('R'),read('R','1','v0'),read('R','1','missing'),...end('R')]);const r=classify(s);assert.equal(status(r,'INT'),'unknown');assert.equal(r.judgment.dependencyGraphComplete,false);});
check('unrelated unknown row source cannot erase an earlier INT witness',()=>{const s=trace([begin('W'),write('W','1','v1','v0'),...end('W'),begin('R'),read('R','1','v0'),read('R','1','v1'),read('R','2','unknown-u'),...end('R')]);const r=classify(s);assert.equal(status(r,'INT'),'refuted');assert.equal(r.judgment.dependencyGraphComplete,false);});
const after=bindings(),unchanged=JSON.stringify(before)===JSON.stringify(after);if(!unchanged)results.push({name:'sources remain unchanged during independent addon checks',passed:false,error:'Source changed'});
const failed=results.filter(x=>!x.passed),receipt={suite:'v034-independent-relation-source-int-coexistence-1',utc:new Date().toISOString(),passed:failed.length===0,checks:results.length,failed:failed.length,testSha256:hash(readFileSync(import.meta.filename)),reviewedImplementationAuthoredByThisReviewer:false,actualDatabaseExecution:false,formalPerformanceMeasurement:false,publicWireExercised:false,baseReceipt:'v034-independent-relation.json',baseReceiptSha256:hash(readFileSync(resolve(root,'artifacts/v034-independent-relation.json'))),bridgeSha256:base.harness.bridgeSha256,sourceUnchanged:unchanged,sourceBefore:before,sourceAfter:after,results};
writeFileSync(resolve(root,'artifacts/v034-independent-relation-addon.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({suite:receipt.suite,passed:receipt.passed,checks:receipt.checks,failed:receipt.failed,failures:failed.map(x=>({name:x.name,error:x.error}))}));if(failed.length)process.exitCode=1;
