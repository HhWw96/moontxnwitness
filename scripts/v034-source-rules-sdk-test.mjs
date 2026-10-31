// Focused independent namespace transport tests; no database or performance run.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire,syncBuiltinESMExports} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {sourceFingerprint} from './build-fingerprint.mjs';
const root=resolve(import.meta.dirname,'..'),req=createRequire(import.meta.url),cp=req('node:child_process'),wt=req('node:worker_threads');
const spawn=cp.spawnSync,Worker=wt.Worker;let started=0;
cp.spawnSync=(...args)=>{started++;return spawn(...args);};wt.Worker=class extends Worker{constructor(...args){started++;super(...args);}};syncBuiltinESMExports();
const sdk=await import('../dist/sdk.mjs'),wire=await import('../dist/relation-v4.mjs'),core=await import('../dist/core.mjs');
const sha=x=>createHash('sha256').update(x).digest('hex'),clone=structuredClone,results=[];
const bound=['src/api_relation_v4.mbt','src/bridge/bridge.mbt','cmd/relation-v4.mjs','cmd/sdk.mjs','cmd/moontxnwitness.mjs','dist/core.mjs','dist/relation-v4.mjs'];
const bind=()=>Object.fromEntries(bound.map(p=>[p,sha(readFileSync(resolve(root,p)))]));
const before=bind(),sourceBefore=sourceFingerprint(root);
function check(name,fn){try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.message,stack:error.stack});}}
const begin=tx=>({kind:'begin',tx,connection:'c-'+tx}),end=tx=>[{kind:'commit_request',tx},{kind:'commit_ok',tx}],undo=(tx,instance='s1')=>({kind:'rollback_to',tx,instance}),mark=(tx,instance='s1')=>({kind:'savepoint',tx,name:'same',instance});
const write=(tx,version,predecessor='x0',key='x')=>({kind:'write',tx,key,version,predecessor}),read=(tx,version,key='x')=>({kind:'read',tx,key,version});
const stamp=events=>events.map((e,i)=>({seq:i+1,time:i,...e}));
function register(body,{initial={x:'x0'},gaps=[]}={}){return {traceSchema:3,dataModel:'point-register-v1',clockDomain:'sdk034',scope:{exclusiveWriters:true},events:stamp([{kind:'snapshot',initial,consistent:true},...body]),gaps};}
const row=(key,version)=>({key,version,values:{value:'same'}}),rw=(tx,key,version,predecessor)=>({kind:'row_write',tx,relation:'items',key,action:'update',version,predecessor,values:{value:'same'}}),rr=(tx,key,version)=>({kind:'row_read',tx,relation:'items',predicate:[{column:'id',op:'eq',value:key}],rows:[row(key,version)],complete:true});
function relation(body){return {traceSchema:3,dataModel:'relation-set-v1',relationSchema:{items:{primaryKey:'id',columns:{id:'int64',value:'text'}}},clockDomain:'sdk034',scope:{exclusiveWriters:true,completeSnapshotTables:['items']},events:stamp([{kind:'snapshot',initial:{items:[row('1','v0'),row('2','u0')]},consistent:true},...body]),gaps:[]};}
const simple=relation([begin('R'),rr('R','1','v0'),...end('R')]);
const intRelation=relation([begin('W'),rw('W','1','v1','v0'),...end('W'),begin('R'),rr('R','1','v0'),rr('R','1','v1'),...end('R')]);
const g1a=register([begin('W'),write('W','w1'),{kind:'rollback_ok',tx:'W'},begin('R'),read('R','w1'),...end('R')]);
const badInt=register([begin('R'),write('R','r1'),read('R','x0'),...end('R')]);
const goodInt=register([begin('R'),mark('R'),write('R','r1'),read('R','r1'),undo('R'),read('R','x0'),...end('R')]);
const list={traceSchema:3,dataModel:'append-list-v1',clockDomain:'sdk034',scope:{exclusiveWriters:true},gaps:[],events:stamp([{kind:'snapshot',initial:{x:[{id:'p',value:'same'}]},consistent:true},begin('R'),mark('R'),{kind:'append',tx:'R',key:'x',id:'a',value:'same'},{kind:'list_read',tx:'R',key:'x',items:[{id:'p',value:'same'},{id:'a',value:'same'}]},undo('R'),{kind:'list_read',tx:'R',key:'x',items:[{id:'p',value:'same'}]},...end('R')])};
const rel=sdk.classifyRelationV4(simple),cap=sdk.inspectCaptureAnomaliesV4(g1a),internal=sdk.inspectInternalConsistencyV4(badInt);
check('relation point classification has separate fixed identities and six rules',()=>{assert.equal(rel.algorithm,'v4-relation-point-category-4');assert.equal(rel.execution.counterContract,'v4-relation-point-category-counters-4');assert.deepEqual(rel.execution.categories,['G0','G1a','G1b','G1c','G2-item','INT']);assert.equal(rel.judgment.status,'checked-compatible');assert.equal(rel.judgment.acceptsIsolationModels,false);});
check('relation INT evidence survives cycle budget zero',()=>{const r=sdk.classifyRelationV4(intRelation,{maxStates:0,maxEdgeChecks:0});assert.equal(r.judgment.rules.INT.status,'refuted');assert.equal(r.judgment.status,'refuted');});
check('relation object and JSON source produce equal reports',()=>assert.deepEqual(sdk.classifyRelationV4(JSON.stringify(simple)),rel));
check('register raw capture proves aborted-source G1a independently',()=>{assert.equal(cap.status,'refuted');assert(cap.findings.some(f=>f.category==='G1a'));assert.equal(cap.scope.acceptsIsolationModels,false);assert.equal(cap.scope.INT,'unsupported');});
check('register own effect formal INT has actual observations',()=>{assert.equal(internal.status,'refuted');assert(internal.findings.length);assert.equal(internal.scope.databaseProductIsolationLevelAsserted,false);});
check('own observation and savepoint rollback remain legal',()=>{assert.equal(sdk.inspectInternalConsistencyV4(goodInt).findings.length,0);assert.equal(sdk.verifyInternalConsistencyV4(goodInt,sdk.inspectInternalConsistencyV4(goodInt)).valid,true);});
check('list savepoint own suffix is removed without changing external base',()=>{const r=sdk.inspectInternalConsistencyV4(list);assert.equal(r.dataModel,'append-list-v1');assert.equal(r.findings.length,0);assert.equal(sdk.verifyInternalConsistencyV4(list,r).valid,true);});
check('list raw-source diagnostics are separate from INT',()=>{const r=sdk.inspectCaptureAnomaliesV4(list);assert.equal(r.format,'moontxnwitness-captured-source-anomalies/v4');assert.equal(sdk.verifyCaptureAnomaliesV4(list,r).valid,true);assert.equal(r.scope.INT,'unsupported');});
check('existing classifyV4 remains relation unsupported',()=>assert.equal(sdk.classifyV4(simple).judgment.status,'unsupported'));
const operations=[{name:'relation',input:simple,run:sdk.classifyRelationV4,verify:sdk.verifyRelationClassificationV4,make:sdk.makeRelationClassificationCapsuleV4,custom:{categories:['INT'],maxStates:0,maxEdgeChecks:0,maxGraphChecks:1000}},
 {name:'capture',input:g1a,run:sdk.inspectCaptureAnomaliesV4,verify:sdk.verifyCaptureAnomaliesV4,make:sdk.makeCaptureAnomaliesCapsuleV4,custom:{maxChecks:0}},
 {name:'internal',input:badInt,run:sdk.inspectInternalConsistencyV4,verify:sdk.verifyInternalConsistencyV4,make:sdk.makeInternalConsistencyCapsuleV4,custom:{maxChecks:0}}];
const capsules={};
for(const op of operations){
 const report=op.run(op.input),capsule=op.make(op.input);capsules[op.name]=capsule;
 check(op.name+' exact report verification',()=>assert.equal(op.verify(op.input,report).valid,true));
 check(op.name+' capsule defaults replay using independent default options',()=>{const r=sdk.replayRelationCapsuleV4(capsule);assert.equal(r.valid,true,r.reason);assert.match(r.scope,/not authenticated/);assert.equal(JSON.parse(capsule).format,'moontxnwitness-source-rules-replay/v4');});
 check(op.name+' producer metadata never selects algorithms',()=>{const c=JSON.parse(capsule);c.producer.version='future-metadata-only';assert.equal(sdk.replayRelationCapsuleV4(c).valid,true);});
 check(op.name+' custom expected options required by both verify and replay',()=>{const r=op.run(op.input,op.custom),c=op.make(op.input,op.custom);assert.equal(op.verify(op.input,r).valid,false);assert.equal(op.verify(op.input,r,op.custom).valid,true);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);assert.equal(sdk.replayRelationCapsuleV4(c,op.custom).valid,true);});
 check(op.name+' raw JSON options parse duplicates before host materialization',()=>{const text=JSON.stringify(op.custom);assert.deepEqual(op.run(op.input,text),op.run(op.input,op.custom));assert.throws(()=>op.run(op.input,'{"maxChecks":0,"max\\u0043hecks":1}'));});
 check(op.name+' result and source tampering rejected',()=>{const r=clone(report);if(r.judgment)r.judgment.status='forged';else r.status='forged';assert.equal(op.verify(op.input,r).valid,false);const source=clone(op.input);source.clockDomain='changed-source';assert.equal(op.verify(source,report).valid,false);});
 check(op.name+' report inner duplicates and rehashed duplicate capsule report rejected',()=>{const text=JSON.stringify(report),dup='{"schemaVersion":4,'+text.slice(1);assert.equal(op.verify(op.input,dup).valid,false);const c=JSON.parse(capsule);c.reportText=dup;c.reportSha256=sha(dup);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
 check(op.name+' report budget cannot self authorize',()=>{const c=JSON.parse(capsule),r=JSON.parse(c.reportText);r.execution.limits[op.name==='relation'?'graphChecks':'maxChecks']=0;c.reportText=JSON.stringify(r);c.reportSha256=sha(c.reportText);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
 for(const field of ['semanticContract','algorithm','counterContract','profile'])check(op.name+' unknown '+field+' rejected even when both report and envelope changed',()=>{const c=JSON.parse(capsule),r=JSON.parse(c.reportText);c[field]='unrecognized';if(field==='counterContract')r.execution[field]='unrecognized';else if(field!=='profile'||op.name!=='relation')r[field]='unrecognized';c.reportText=JSON.stringify(r);c.reportSha256=sha(c.reportText);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
 for(const field of ['source','options','report'])check(op.name+' altered '+field+' digest rejected',()=>{const c=JSON.parse(capsule);c[field+'Text']+=' ';assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
 check(op.name+' inner options duplicate keys rejected after hash recomputation',()=>{const c=JSON.parse(capsule);c.optionsText=op.name==='relation'?'{"maxStates":1,"max\\u0053tates":0}':'{"maxChecks":1,"max\\u0043hecks":0}';c.optionsSha256=sha(c.optionsText);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
 check(op.name+' capsule duplicate unknown fields and operations rejected',()=>{const c=JSON.parse(capsule);assert.equal(sdk.replayRelationCapsuleV4('{"schemaVersion":4,'+capsule.slice(1)).valid,false);c.extra=true;assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);delete c.extra;c.operation='analysis';assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
 check(op.name+' source model tamper remains rejected after rehash',()=>{const c=JSON.parse(capsule),s=JSON.parse(c.sourceText);s.dataModel='invented-model';c.sourceText=JSON.stringify(s);c.sourceSha256=sha(c.sourceText);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
}
check('source diagnostic unsupported relation report stays unsupported on replay',()=>{const r=sdk.inspectCaptureAnomaliesV4(simple);assert.equal(r.status,'unsupported');const c=sdk.makeCaptureAnomaliesCapsuleV4(simple);assert.equal(sdk.replayRelationCapsuleV4(c).valid,true);});
check('relation unsupported register stays unsupported without model upgrade',()=>{const r=sdk.classifyRelationV4(g1a);assert.equal(r.judgment.status,'unsupported');assert.equal(sdk.replayRelationCapsuleV4(sdk.makeRelationClassificationCapsuleV4(g1a)).valid,true);});
check('known finding survives a separate coverage gap',()=>{const source=clone(g1a);source.gaps=[{code:'missing-window-tail',message:'Missing tail after the proven observed read'}];const r=sdk.inspectCaptureAnomaliesV4(source);assert.equal(r.status,'refuted');assert.equal(r.coverage.complete,false);assert(r.findings.some(f=>f.category==='G1a'));assert.equal(sdk.replayRelationCapsuleV4(sdk.makeCaptureAnomaliesCapsuleV4(source)).valid,true);});
check('unknown source model is invalid rather than silently mapped',()=>{const s=clone(simple);s.dataModel='unknown';assert.equal(sdk.classifyRelationV4(s).status,'invalid');assert.throws(()=>sdk.makeRelationClassificationCapsuleV4(s));});
check('unknown options and models cannot request full isolation acceptance',()=>{for(const op of operations){assert.throws(()=>op.run(op.input,{models:['serializable']}));assert.throws(()=>op.run(op.input,{model:'read-committed'}));}});
check('category selection validates names duplicates and empty lists',()=>{for(const chosen of [[],['G0','G0'],['G-single'],['serializable'],[1]])assert.throws(()=>sdk.classifyRelationV4(simple,{categories:chosen}));});
check('host options cannot hide unknown fields through custom serialization',()=>{for(const op of operations){assert.throws(()=>op.run(op.input,new Map()));assert.throws(()=>op.run(op.input,{unknown:true,toJSON(){return {};}}));}});
check('integer budgets and hard maxima enforced by all JS entrypoints',()=>{for(const op of operations)for(const n of [-1,0.5,NaN,Infinity,1000001])assert.throws(()=>op.run(op.input,op.name==='relation'?{maxGraphChecks:n}:{maxChecks:n}));assert.throws(()=>sdk.classifyRelationV4(simple,{maxStates:100001}));});
check('raw source escaped duplicate keys rejected by MoonBit parsing',()=>{const source='{"traceSchema":3,"trace\\u0053chema":3,"dataModel":"point-register-v1","events":[]}';for(const op of operations)assert.equal(op.run(source).status,'invalid');});
check('all transport bounds and malformed UTF16 are enforced',()=>{assert.throws(()=>sdk.classifyRelationV4(' '.repeat(8*1024*1024+1)),RangeError);assert.throws(()=>sdk.inspectCaptureAnomaliesV4(g1a,' '.repeat(8193)),RangeError);assert.equal(sdk.verifyInternalConsistencyV4(badInt,' '.repeat(32*1024*1024+1)).valid,false);assert.equal(sdk.replayRelationCapsuleV4(' '.repeat(64*1024*1024+1)).valid,false);assert.throws(()=>sdk.classifyRelationV4(String.fromCharCode(0xd800)),TypeError);});
check('new SDK starts no compatibility workers or external commands',()=>assert.equal(started,0));
const baselinePath=process.env.MTW_V034_BASELINE_CORE;let byteControls={executed:false,actualPublishedProducer:false};
if(baselinePath){
 const old=await import(pathToFileURL(resolve(baselinePath)).href),baselineHash=sha(readFileSync(baselinePath)),rows=[];
 const declared={schemaVersion:1,model:'serializable',initial:{x:'x0',y:'y0'},transactions:[{id:'A',status:'committed',ops:[{type:'read',key:'x',version:'x0'},{type:'write',key:'y',version:'y1'}]},{id:'B',status:'committed',ops:[{type:'read',key:'y',version:'y0'},{type:'write',key:'x',version:'x1'}]}]};
 const controls=[['analyze_v4_json',[JSON.stringify(declared),'{}']],['classify_v4_json',[JSON.stringify(declared),'{}']],['reduce_v4_json',[JSON.stringify(declared),'{"preserve":"serializable"}']],['analyze_v4_json',['{','{}']],['classify_v4_json',[JSON.stringify(declared),'{"categories":["unknown"]}']],['classify_v4_json',[JSON.stringify(simple),'{}']]];
 const wireBaselinePath=process.env.MTW_V034_WIRE_BASELINE_CORE;
 let knownDifference=null;
 for(const [entry,args]of controls)check('frozen032 candidate byte control '+entry+' '+rows.length,()=>{
  const a=old[entry](...args),b=core[entry](...args);
  if(entry==='analyze_v4_json'&&args[0]==='{'){
   assert(wireBaselinePath,'An explicit frozen033 wire baseline is required for the known 032-to-033 error-location difference');
   const oldError=JSON.parse(a),currentError=JSON.parse(b);
   assert.equal(oldError.status,'invalid');assert.equal(currentError.status,'invalid');
   assert.equal(b,a.replace('src/api_v4.mbt:99:20-99:32','src/api_v4.mbt:113:20-113:32'),'Only the documented existing source coordinate may differ');
   knownDifference={kind:'existing-032-to-033-debug-source-coordinate',baseline032:a,current:b,exactDifference:['src/api_v4.mbt:99:20-99:32','src/api_v4.mbt:113:20-113:32'],sourceCoordinateIsNotCapsuleSemanticContract:true};
  }else assert.equal(b,a);
  rows.push({entry,inputSha256:sha(JSON.stringify(args)),baselineOutputSha256:sha(a),currentOutputSha256:sha(b),byteIdentical:a===b,bytes:Buffer.byteLength(a)});
 });
 if(wireBaselinePath){
  const frozen033=await import(pathToFileURL(resolve(wireBaselinePath)).href),frozen033Hash=sha(readFileSync(wireBaselinePath));
  check('new namespace leaves exact frozen033 wire error bytes unchanged',()=>{assert.equal(frozen033Hash,'c3f151762b93b1ddd96309f4105e0b80be2a0598bca027f35a4bf5a190a91d76');assert.equal(core.analyze_v4_json('{','{}'),frozen033.analyze_v4_json('{','{}'));assert(knownDifference);knownDifference.frozen033CoreSha256=frozen033Hash;knownDifference.actualPublishedProducer=false;});
 }
 const oldV4=await import(pathToFileURL(resolve(baselinePath,'../v4.mjs')).href);
 check('old history v4 capsule bytes and replay semantics stay unchanged',()=>{const c=oldV4.makeCapsuleV4(declared);assert.equal(c,sdk.makeCapsuleV4(declared));assert.equal(sdk.replayCapsuleV4(c).valid,true);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);});
 check('both frozen032 and current old namespace refuse wire-error capsules and verification',()=>{assert.throws(()=>oldV4.makeCapsuleV4('{'));assert.throws(()=>sdk.makeCapsuleV4('{'));const report=old.analyze_v4_json('{','{}');assert.equal(oldV4.verifyV4('{',JSON.parse(report)).valid,false);assert.equal(sdk.verifyV4('{',JSON.parse(report)).valid,false);});
 byteControls={executed:true,actualPublishedProducer:false,baselineKind:'frozen development candidate; not a public tag or downloaded published producer',baselineCoreSha256:baselineHash,knownDifference,rows};
}
const sdkStarted=started;
const folder=resolve(root,'artifacts/v034-sdk-tests');mkdirSync(folder,{recursive:true});const temp=mkdtempSync(resolve(folder,'run-'));
const put=(name,value)=>{const path=resolve(temp,name);writeFileSync(path,typeof value==='string'?value:JSON.stringify(value));return path;};
const relFile=put('relation.json',simple),capFile=put('register.json',g1a),intFile=put('int.json',badInt),reportFile=put('relation-report.json',rel),capsuleFile=put('relation-capsule.json',capsules.relation);
const cli=args=>spawn(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),...args],{cwd:temp,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});
check('CLI relation classification and verify execute new namespace',()=>{const a=cli(['classify-relation-v4',relFile]);assert.equal(a.status,0,a.stderr);assert.deepEqual(JSON.parse(a.stdout),rel);const b=cli(['verify-relation-classification-v4',relFile,reportFile]);assert.equal(b.status,0,b.stderr);assert.equal(JSON.parse(b.stdout).valid,true);});
check('CLI capture and internal diagnostics preserve refuted exit status',()=>{for(const [cmd,input,expected]of [['inspect-capture-anomalies-v4',capFile,cap],['inspect-internal-consistency-v4',intFile,internal]]){const a=cli([cmd,input]);assert.equal(a.status,1,a.stderr);assert.deepEqual(JSON.parse(a.stdout),expected);}});
check('CLI diagnostic verify uses explicit report and default expected options',()=>{for(const [cmd,input,report]of [['verify-capture-anomalies-v4',capFile,cap],['verify-internal-consistency-v4',intFile,internal]]){const a=cli([cmd,input,put(cmd+'.json',report)]);assert.equal(a.status,0,a.stderr);assert.equal(JSON.parse(a.stdout).valid,true);}});
check('CLI new capsule replay is independent from old v4 replay',()=>{const a=cli(['replay-relation-v4',capsuleFile]);assert.equal(a.status,0,a.stderr);assert.equal(JSON.parse(a.stdout).valid,true);const b=cli(['replay-v4',capsuleFile]);assert.equal(b.status,2);});
check('CLI custom options require independently expected replay options',()=>{const options=put('custom-options.json',{categories:['INT'],maxStates:0});const custom=put('custom-capsule.json',sdk.makeRelationClassificationCapsuleV4(intRelation,{categories:['INT'],maxStates:0}));assert.equal(cli(['replay-relation-v4',custom]).status,2);assert.equal(cli(['replay-relation-v4',custom,'--options',options]).status,0);});
check('CLI max-checks zero leaves inspection unable to conclude',()=>{const a=cli(['inspect-internal-consistency-v4',intFile,'--max-checks','0']);assert.equal(a.status,3,a.stderr);assert.equal(JSON.parse(a.stdout).status,'unknown');});
check('CLI all new commands reject escaped duplicate options before JSON.parse',()=>{const option=put('ambiguous-options.json','{"maxChecks":1,"max\\u0043hecks":0}');for(const [cmd,paths]of [['classify-relation-v4',[relFile]],['verify-relation-classification-v4',[relFile,reportFile]],['inspect-capture-anomalies-v4',[capFile]],['verify-capture-anomalies-v4',[capFile,put('cap-report.json',cap)]],['inspect-internal-consistency-v4',[intFile]],['verify-internal-consistency-v4',[intFile,put('int-report.json',internal)]],['replay-relation-v4',[capsuleFile]]])assert.equal(cli([cmd,...paths,'--options',option]).status,2,cmd);});
check('CLI duplicate flags and unknown flags cannot be ignored',()=>{assert.equal(cli(['inspect-capture-anomalies-v4',capFile,'--max-checks','0','--max-checks','1']).status,2);assert.equal(cli(['classify-relation-v4',relFile,'--models','elle-core']).status,2);});
check('CLI output cannot overwrite source or existing report',()=>{const initial=readFileSync(relFile,'utf8');assert.equal(cli(['classify-relation-v4',relFile,'--output',relFile]).status,2);assert.equal(readFileSync(relFile,'utf8'),initial);const out=put('existing.json','unchanged');assert.equal(cli(['classify-relation-v4',relFile,'--output',out]).status,2);assert.equal(readFileSync(out,'utf8'),'unchanged');});
check('CLI companion capsule writes only to new distinct paths',()=>{const out=resolve(temp,'new-report.json'),capsule=resolve(temp,'new-capsule.json');const a=cli(['classify-relation-v4',relFile,'--output',out,'--capsule',capsule]);assert.equal(a.status,0,a.stderr);assert.deepEqual(JSON.parse(readFileSync(out,'utf8')),rel);assert.equal(sdk.replayRelationCapsuleV4(readFileSync(capsule,'utf8')).valid,true);assert.equal(cli(['classify-relation-v4',relFile,'--output',resolve(temp,'same-new.json'),'--capsule',resolve(temp,'same-new.json')]).status,2);});
check('source and frozen code remain unchanged during tests',()=>{assert.deepEqual(bind(),before);assert.equal(sourceFingerprint(root),sourceBefore);assert.equal(sdkStarted,0);});
cp.spawnSync=spawn;wt.Worker=Worker;syncBuiltinESMExports();
const failed=results.filter(x=>!x.passed),receipt={format:'v034-source-rules-sdk-cli-validation/v1',passed:!failed.length,checks:results.length,failed:failed.length,sdkExternalProcesses:sdkStarted,sourceFingerprint:sourceBefore,beforeSha256:before,afterSha256:bind(),byteControls,actualDatabaseExecution:false,formalPerformanceMeasurement:false,publicReleasePerformed:false,results};
writeFileSync(resolve(root,'artifacts/v034-source-rules-sdk-validation.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({passed:receipt.passed,checks:receipt.checks,failed:failed.length,sourceFingerprint:sourceBefore,failures:failed}));
if(failed.length)process.exitCode=1;
