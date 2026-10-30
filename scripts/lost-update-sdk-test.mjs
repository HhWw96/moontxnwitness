import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {inspectLostUpdatesV4,verifyLostUpdatesV4,makeLostUpdatesCapsuleV4,inspectAnomaliesV4,replayCapsuleV4} from '../dist/sdk.mjs';
const root=resolve(import.meta.dirname,'..'),rows=[];const check=(name,fn)=>{fn();rows.push({name,passed:true});};
const hash=text=>createHash('sha256').update(text,'utf8').digest('hex');
const source={schemaVersion:1,model:'serializable',initial:{x:'x0'},transactions:[
 {id:'A',status:'committed',ops:[{type:'read',key:'x',version:'x0'},{type:'write',key:'x',version:'a1'}]},
 {id:'B',status:'committed',ops:[{type:'read',key:'x',version:'x0'},{type:'write',key:'x',version:'b1'}]},
]};
const report=inspectLostUpdatesV4(source),capsule=makeLostUpdatesCapsuleV4(source);
check('proven same-identity external reads and final writes produce source-bound pair',()=>{
 const finding=report.findings.find(item=>item.kind==='lost-update');assert(finding);
 assert.equal(finding.evidence.readVersionIdentity,'x0');assert.equal(finding.evidence.versionOrderRequired,false);
 assert.deepEqual(finding.impliedAnomalies,['lost-update','write-skew','G2-item','G2']);
 assert.equal(finding.evidence.transactions.length,2);assert.equal(report.scope.acceptsIsolationModels,false);
 assert.equal(report.scope.dirtyUpdateSupported,false);assert.equal(report.profile,'register-source-lost-update/v1');
});
check('source-only default does not silently enable new profile',()=>{
 const old=inspectAnomaliesV4(source);assert.equal(old.algorithm,'v4-source-index-and-order-witness-1');
 assert(!old.findings.some(item=>item.kind==='lost-update'));assert.equal(report.algorithm,'v4-register-source-lost-update-1');
});
check('report and default capsule reproduce with independently fixed limits',()=>{
 assert.equal(verifyLostUpdatesV4(source,report).valid,true);assert.equal(replayCapsuleV4(capsule).valid,true);
 assert.equal(JSON.parse(capsule).operation,'lost-updates');
});
check('zero-work capsule requires independent caller expectation',()=>{
 const packed=makeLostUpdatesCapsuleV4(source,{maxChecks:0});assert.equal(replayCapsuleV4(packed).valid,false);
 assert.equal(replayCapsuleV4(packed,{maxChecks:0}).valid,true);
 assert.equal(inspectLostUpdatesV4(source,{maxChecks:0}).coverage.complete,false);
});
for(const [name,change] of [
 ['identity',r=>{r.findings.find(item=>item.kind==='lost-update').evidence.readVersionIdentity='forged';}],
 ['final write',r=>{r.findings.find(item=>item.kind==='lost-update').evidence.transactions[0].finalEffectiveWrite.identity='forged';}],
 ['source',r=>{r.observations.document.model='strict-serializable';}],
 ['algorithm',r=>{r.algorithm='unknown';}],['counter',r=>{r.execution.counterContract='unknown';}],
 ['profile',r=>{r.profile='unknown';}],['budget',r=>{r.execution.maxChecks=1000001;}],
 ['dirty-update support',r=>{r.scope.dirtyUpdateSupported=true;}],
])check('tampered '+name+' rejected',()=>{const copy=structuredClone(report);change(copy);assert.equal(verifyLostUpdatesV4(source,copy).valid,false);});
check('self-consistent capsule hashes cannot authorize an unknown algorithm',()=>{
 const copy=JSON.parse(capsule),result=JSON.parse(copy.reportText);result.algorithm=copy.algorithm='unknown';
 copy.reportText=JSON.stringify(result);copy.reportSha256=hash(copy.reportText);
 assert.equal(replayCapsuleV4(JSON.stringify(copy)).valid,false);
});
check('capsule cannot authorize over-limit work',()=>{
 const copy=JSON.parse(capsule);copy.optionsText='{"maxChecks":1000001}';copy.optionsSha256=hash(copy.optionsText);
 assert.equal(replayCapsuleV4(JSON.stringify(copy),{maxChecks:1000001}).valid,false);
});
for(const options of [{maxChecks:-1},{maxChecks:1000001},{maxChecks:1.5},{models:['serializable']},{listGraph:'effective-v1'}])
 check('invalid options '+JSON.stringify(options),()=>assert.throws(()=>inspectLostUpdatesV4(source,options)));
check('blind writes and version adjacency do not create observed reads or dirty-update',()=>{
 const copy=structuredClone(source);copy.transactions.forEach(tx=>{tx.ops=tx.ops.filter(op=>op.type==='write');});
 copy.versionOrders={x:['x0','a1','b1']};const result=inspectLostUpdatesV4(copy);
 assert(!result.findings.some(item=>['lost-update','dirty-update'].includes(item.kind)));assert.equal(result.scope.dirtyUpdateSupported,false);
});
check('unknown read source stays a gap',()=>{
 const copy=structuredClone(source);copy.transactions.forEach(tx=>{tx.ops[0].version='missing';});
 const result=inspectLostUpdatesV4(copy);assert(!result.findings.some(item=>item.kind==='lost-update'));
 assert(result.coverage.diagnosticGaps.some(item=>item.kind==='lost-update-read-source-unconfirmed'));
});
const temporaryRoot=resolve(root,'artifacts/validation-temp');mkdirSync(temporaryRoot,{recursive:true});
const temporary=mkdtempSync(resolve(temporaryRoot,'lost-sdk-')),input=resolve(temporary,'source.json'),output=resolve(temporary,'report.json'),packed=resolve(temporary,'capsule.json');
writeFileSync(input,JSON.stringify(source));
const cli=args=>spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),...args],{encoding:'utf8',windowsHide:true,maxBuffer:5*1024*1024});
check('CLI exports explicit lost-update diagnosis and capsule',()=>{
 const result=cli(['inspect-lost-updates-v4',input,'--output',output,'--capsule',packed]);assert.equal(result.status,1,result.stderr);
 assert.deepEqual(JSON.parse(readFileSync(output)),report);
});
check('CLI verifies lost-update diagnosis and generic replay',()=>{
 const verified=cli(['verify-lost-updates-v4',input,output]);assert.equal(verified.status,0,verified.stderr);
 const replay=cli(['replay-v4',packed]);assert.equal(replay.status,0,replay.stderr);assert.equal(JSON.parse(replay.stdout).valid,true);
});
for(const command of ['inspect-lost-updates-v4','verify-lost-updates-v4'])for(const unicode of [false,true])
 check(command+' refuses '+(unicode?'Unicode-equivalent ':'')+'duplicate option keys',()=>{
  const file=resolve(temporary,command+'-'+unicode+'.json');
  const second=unicode?'max\\u0043hecks':'maxChecks';writeFileSync(file,'{"maxChecks":1000000,"'+second+'":1000000}');
  assert.equal(cli([command,input,...(command.startsWith('verify')?[output]:[]),'--options',file]).status,2);
 });
check('CLI output remains protected',()=>{
 const before=readFileSync(output,'utf8');assert.equal(cli(['inspect-lost-updates-v4',input,'--output',output]).status,2);assert.equal(readFileSync(output,'utf8'),before);
});
const receipt={suite:'v033-register-lost-update-sdk-1',passed:true,checks:rows.length,actualDatabaseExecution:false,results:rows};
writeFileSync(resolve(root,'artifacts/lost-update-sdk-validation.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
