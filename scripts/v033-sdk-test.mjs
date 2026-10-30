// Targeted v0.3.3 additions; the original v4 SDK suite remains unchanged.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire,syncBuiltinESMExports} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'..'),child=createRequire(import.meta.url)('node:child_process');
const realSpawn=child.spawnSync;let sdkSpawns=0;
child.spawnSync=(...args)=>{sdkSpawns++;return realSpawn(...args);};syncBuiltinESMExports();
const {analyzeV4,verifyV4,reduceV4,verifyReductionV4,makeCapsuleV4,classifyV4,verifyClassificationV4,makeClassificationCapsuleV4,inspectAnomaliesV4,verifyAnomaliesV4,
  makeAnomaliesCapsuleV4,replayCapsuleV4}=await import('../dist/sdk.mjs');
const {parseOptionsV4}=await import('../dist/v4.mjs');
const sha=text=>createHash('sha256').update(text,'utf8').digest('hex');
const rows=[];function check(name,fn){fn();rows.push({name,passed:true});}
const history={schemaVersion:1,model:'serializable',initial:{x:'x0'},versionOrders:{x:['x0','x1','x2']},transactions:[
 {id:'A',status:'committed',ops:[{type:'read',key:'x',version:'x0'},{type:'write',key:'x',version:'x1'}]},
 {id:'B',status:'committed',ops:[{type:'read',key:'x',version:'x0'},{type:'write',key:'x',version:'x2'}]},
]};
const future={schemaVersion:1,model:'serializable',initial:{x:'x0'},transactions:[
 {id:'A',status:'committed',ops:[{type:'read',key:'x',version:'x1'},{type:'write',key:'x',version:'x1'}]},
]};
const options={categories:['G-single']},category=classifyV4(history,options),capsule=makeClassificationCapsuleV4(history,options);
check('explicit G-single uses independent algorithm and one-RW witness',()=>{
 assert.equal(category.algorithm,'v4-source-bound-category-g-single-1');
 assert.equal(category.execution.counterContract,'v4-category-g-single-seed-bfs-counters-1');
 const evidence=category.judgment.rules['G-single'].evidence;
 assert.equal(evidence.specificCategory,'G-single-item');assert.equal(evidence.requestedCategory,'G-single');
 assert.equal(evidence.rwEdgeCount,1);assert.equal(evidence.edges.filter(edge=>edge.edge.kind==='rw').length,1);
 assert.equal(category.judgment.status,'refuted');assert.equal(category.judgment.acceptsIsolationModels,false);
});
check('G-single verification binds caller category',()=>{
 assert.equal(verifyClassificationV4(history,category,options).valid,true);
 assert.equal(verifyClassificationV4(history,category).valid,false);
});
check('G-single capsule requires independent explicit category',()=>{
 assert.equal(replayCapsuleV4(capsule).valid,false);assert.equal(replayCapsuleV4(capsule,options).valid,true);
});
check('old category default retains old algorithm and counter IDs',()=>{
 const old=classifyV4(history);assert.equal(old.algorithm,'v4-source-bound-category-bfs-1');
 assert.equal(old.execution.counterContract,'v4-category-seed-bfs-counters-1');
 assert.deepEqual(old.execution.categories,['G0','G1c','G2-item']);
 assert.equal(replayCapsuleV4(makeClassificationCapsuleV4(history)).valid,true);
});
check('all four explicit categories are accepted without changing defaults',()=>{
 const requested={categories:['G0','G1c','G2-item','G-single']};
 const result=classifyV4(history,requested);assert.equal(result.judgment.rules['G-single'].status,'refuted');
 assert.equal(verifyClassificationV4(history,result,requested).valid,true);
});
check('G-single exhausted budget stays inconclusive',()=>{
 const result=classifyV4(history,{...options,maxStates:0,maxEdgeChecks:0});
 assert.equal(result.judgment.status,'inconclusive');assert.equal(result.judgment.rules['G-single'].status,'unknown');
});
check('unknown G-single spelling is rejected',()=>assert.throws(()=>classifyV4(history,{categories:['G-single-item']})));
check('duplicate G-single request is rejected',()=>assert.throws(()=>classifyV4(history,{categories:['G-single','G-single']})));
check('G-single forged counter contract is refused',()=>{
 const altered=structuredClone(category);altered.execution.counterContract='v4-category-seed-bfs-counters-1';
 assert.equal(verifyClassificationV4(history,altered,options).valid,false);
});
const inspection=inspectAnomaliesV4(future),inspectionCapsule=makeAnomaliesCapsuleV4(future);
check('inspection has separate source-only contract',()=>{
 assert.equal(inspection.format,'moontxnwitness-anomaly-inspection/v4');
 assert.equal(inspection.algorithm,'v4-source-index-and-order-witness-1');
 assert.equal(inspection.execution.counterContract,'v4-anomaly-source-checks-1');
 assert.equal(inspection.scope.acceptsIsolationModels,false);assert.equal(inspection.scope.authenticityVerified,false);
 assert.equal(inspection.findings[0].kind,'future-read');assert.equal(inspection.findings[0].evidence.read.operationIndex,0);
 assert.equal(inspection.findings[0].evidence.source.operationIndex,1);
});
check('inspection preserves original source and verifies',()=>{
 assert.deepEqual(inspection.observations.document,future);assert.equal(verifyAnomaliesV4(future,inspection).valid,true);
});
check('inspection default capsule replays semantically',()=>{
 assert.equal(JSON.parse(inspectionCapsule).operation,'inspection');assert.equal(replayCapsuleV4(inspectionCapsule).valid,true);
});
check('inspection zero budget needs caller authority and cannot report complete',()=>{
 const limited=inspectAnomaliesV4(future,{maxChecks:0});assert.equal(limited.status,'inconclusive');
 assert.equal(limited.coverage.complete,false);assert.equal(limited.execution.checks,0);
 const packed=makeAnomaliesCapsuleV4(future,{maxChecks:0});
 assert.equal(replayCapsuleV4(packed).valid,false);assert.equal(replayCapsuleV4(packed,{maxChecks:0}).valid,true);
 assert.equal(verifyAnomaliesV4(future,limited).valid,false);
});
for(const [name,change] of [
 ['conclusion',r=>{r.status='checked';}],['algorithm',r=>{r.algorithm='unrecognized';}],
 ['counter',r=>{r.execution.counterContract='unrecognized';}],['budget',r=>{r.execution.maxChecks=0;}],
 ['source',r=>{r.observations.document.model='strict-serializable';}],['coverage',r=>{r.coverage.complete=false;}],
 ['identity',r=>{r.findings[0].evidence.identity='unobserved';}],
])check('inspection tampered '+name+' rejected',()=>{
 const altered=structuredClone(inspection);change(altered);assert.equal(verifyAnomaliesV4(future,altered).valid,false);
});
for(const requested of [{maxChecks:-1},{maxChecks:1000001},{maxChecks:0.5},{models:['serializable']},{maxAttempts:1},null,[]])
 check('inspection rejects unsupported options '+JSON.stringify(requested),()=>assert.throws(()=>inspectAnomaliesV4(future,requested)));
check('missing source remains a gap rather than G1a',()=>{
 const source=structuredClone(future);source.transactions[0].ops=[{type:'read',key:'x',version:'missing'}];
 const report=inspectAnomaliesV4(source);assert.equal(report.status,'inconclusive');assert.equal(report.findings.length,0);
 assert.equal(report.coverage.diagnosticGaps[0].kind,'missing-source');assert.deepEqual(report.coverage.diagnosticGaps[0].impliedAnomalies,[]);
});
check('unknown writer differs from missing source',()=>{
 const source={schemaVersion:1,model:'serializable',initial:{x:'x0'},transactions:[
 {id:'W',status:'unknown',ops:[{type:'write',key:'x',version:'x1'}]},
 {id:'R',status:'committed',ops:[{type:'read',key:'x',version:'x1'}]},]};
 const result=inspectAnomaliesV4(source);assert(result.coverage.diagnosticGaps.some(gap=>gap.kind==='unknown-writer'));
 assert(!result.coverage.diagnosticGaps.some(gap=>gap.kind==='missing-source'));assert.equal(result.findings.length,0);
});
check('inspection capsule options cannot authorize a larger expected budget',()=>{
 const parsed=JSON.parse(inspectionCapsule);parsed.optionsText='{"maxChecks":0}';parsed.optionsSha256=sha(parsed.optionsText);
 assert.equal(replayCapsuleV4(JSON.stringify(parsed),{maxChecks:0}).valid,false);
});
check('capsule duplicate option keys are rejected before replay',()=>{
 const parsed=JSON.parse(inspectionCapsule);parsed.optionsText='{"maxChecks":1000000,"maxChecks":1000000}';parsed.optionsSha256=sha(parsed.optionsText);
 assert.equal(replayCapsuleV4(JSON.stringify(parsed)).valid,false);
});
check('guarded CLI options reject duplicates including Unicode aliases',()=>{
 assert.throws(()=>parseOptionsV4('{"maxChecks":1,"maxChecks":2}'));
 assert.throws(()=>parseOptionsV4('{"maxChecks":1,"max\\u0043hecks":2}'));
 assert.deepEqual(parseOptionsV4('{"maxChecks":0}'),{maxChecks:0});
});
check('new SDK path starts no compatibility process',()=>assert.equal(sdkSpawns,0));
child.spawnSync=realSpawn;syncBuiltinESMExports();
const temporaryRoot=resolve(root,'artifacts/validation-temp');mkdirSync(temporaryRoot,{recursive:true});
const temporary=mkdtempSync(resolve(temporaryRoot,'v033-sdk-'));
const sourceFile=resolve(temporary,'source.json'),categoryFile=resolve(temporary,'category.json'),inspectionFile=resolve(temporary,'inspection.json'),capsuleFile=resolve(temporary,'capsule.json'),optionsFile=resolve(temporary,'options.json');
writeFileSync(sourceFile,JSON.stringify(future));writeFileSync(categoryFile,JSON.stringify(history));writeFileSync(optionsFile,JSON.stringify(options));
const cli=args=>realSpawn(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),...args],{encoding:'utf8',windowsHide:true,maxBuffer:5*1024*1024});
check('inspection CLI exports findings and capsule with diagnostic exit code',()=>{
 const result=cli(['inspect-anomalies-v4',sourceFile,'--output',inspectionFile,'--capsule',capsuleFile]);
 assert.equal(result.status,1,result.stderr);assert.equal(JSON.parse(readFileSync(inspectionFile)).scope.acceptsIsolationModels,false);
});
check('inspection CLI verification succeeds with fixed defaults',()=>{
 const result=cli(['verify-anomalies-v4',sourceFile,inspectionFile]);assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).valid,true);
});
check('inspection CLI capsule replay succeeds',()=>{
 const result=cli(['replay-v4',capsuleFile]);assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).valid,true);
});
check('inspection CLI explicit zero budget remains unknown',()=>{
 const result=cli(['inspect-anomalies-v4',sourceFile,'--max-checks','0']);assert.equal(result.status,3,result.stderr);assert.equal(JSON.parse(result.stdout).coverage.complete,false);
});
check('inspection CLI duplicate option file keys are refused',()=>{
 const file=resolve(temporary,'duplicates.json');writeFileSync(file,'{"maxChecks":0,"maxChecks":1000000}');
 assert.equal(cli(['inspect-anomalies-v4',sourceFile,'--options',file]).status,2);
});
check('inspection CLI never overwrites an existing report',()=>{
 const before=readFileSync(inspectionFile,'utf8');assert.equal(cli(['inspect-anomalies-v4',sourceFile,'--output',inspectionFile]).status,2);
 assert.equal(readFileSync(inspectionFile,'utf8'),before);
});
check('G-single CLI uses guarded explicit options',()=>{
 const result=cli(['classify-v4',categoryFile,'--options',optionsFile]);assert.equal(result.status,1,result.stderr);
 assert.equal(JSON.parse(result.stdout).judgment.rules['G-single'].evidence.rwEdgeCount,1);
});
// Every v4 command shares the guarded option boundary, including old commands.
const analysisFile=resolve(temporary,'old-analysis.json'),oldCategoryFile=resolve(temporary,'old-category.json'),reductionFile=resolve(temporary,'old-reduction.json'),oldCapsuleFile=resolve(temporary,'old-capsule.json');
const oldAnalysis=analyzeV4(history),oldCategory=classifyV4(history),reduceOptions={preserve:'serializable',maxChecks:0},oldReduction=reduceV4(history,reduceOptions);
writeFileSync(analysisFile,JSON.stringify(oldAnalysis));writeFileSync(oldCategoryFile,JSON.stringify(oldCategory));writeFileSync(reductionFile,JSON.stringify(oldReduction));writeFileSync(oldCapsuleFile,makeCapsuleV4(history));
const optionCommands=[
 ['analyze-v4',[categoryFile],'maxAttempts',100000,''],
 ['classify-v4',[categoryFile],'maxStates',100000,''],
 ['reduce-v4',[categoryFile],'maxChecks',0,'"preserve":"serializable",'],
 ['verify-v4',[categoryFile,analysisFile],'maxAttempts',100000,''],
 ['verify-classification-v4',[categoryFile,oldCategoryFile],'maxStates',100000,''],
 ['verify-reduction-v4',[categoryFile,reductionFile],'maxChecks',0,'"preserve":"serializable",'],
 ['replay-v4',[oldCapsuleFile],'maxAttempts',100000,''],
 ['inspect-anomalies-v4',[sourceFile],'maxChecks',1000000,''],
 ['verify-anomalies-v4',[sourceFile,inspectionFile],'maxChecks',1000000,''],
];
for(const [command,paths,name,value,prefix] of optionCommands){
 for(const unicode of [false,true])check(command+' rejects '+(unicode?'Unicode-equivalent ':'')+'duplicate option keys',()=>{
  const second=unicode?name.slice(0,3)+'\\u'+name.charCodeAt(3).toString(16).padStart(4,'0')+name.slice(4):name;
  const raw='{'+prefix+'"'+name+'":'+value+',"'+second+'":'+value+'}';
  const file=resolve(temporary,command+'-duplicate-'+unicode+'.json');writeFileSync(file,raw);
  const result=cli([command,...paths,'--options',file]);assert.equal(result.status,2,result.stderr);
 });
}
const validCases=[
 ['analyze-v4',[categoryFile],'{"max\\u0041ttempts":100000}',oldAnalysis,1],
 ['classify-v4',[categoryFile],'{"categories":["G0","G1c","G2-item"],"maxStates":100000,"maxEdgeChecks":1000000}',oldCategory,1],
 ['reduce-v4',[categoryFile],JSON.stringify(reduceOptions),oldReduction,3],
 ['verify-v4',[categoryFile,analysisFile],'{}',verifyV4(history,oldAnalysis),0],
 ['verify-classification-v4',[categoryFile,oldCategoryFile],'{}',verifyClassificationV4(history,oldCategory),0],
 ['verify-reduction-v4',[categoryFile,reductionFile],JSON.stringify(reduceOptions),verifyReductionV4(history,oldReduction,reduceOptions),0],
 ['replay-v4',[oldCapsuleFile],'{}',replayCapsuleV4(readFileSync(oldCapsuleFile,'utf8')),0],
 ['inspect-anomalies-v4',[sourceFile],'{"maxChecks":1000000}',inspection,1],
 ['verify-anomalies-v4',[sourceFile,inspectionFile],'{"maxChecks":1000000}',verifyAnomaliesV4(future,inspection),0],
];
for(const [command,paths,raw,expected,code] of validCases)check(command+' valid options retain complete SDK output',()=>{
 const file=resolve(temporary,command+'-valid-options.json');writeFileSync(file,raw);
 const result=cli([command,...paths,'--options',file]);assert.equal(result.status,code,result.stderr);
 assert.deepEqual(JSON.parse(result.stdout),expected);
});
const receipt={suite:'v033-source-anomaly-and-g-single-wire-1',passed:true,checks:rows.length,legacyWorkers:sdkSpawns,actualDatabaseExecution:false,results:rows};
writeFileSync(resolve(root,'artifacts/v033-sdk-validation.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));
