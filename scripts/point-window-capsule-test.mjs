// Run against a compiled SDK and three retained original PostgreSQL inputs.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';

const [sdkFile,startFile,endFile,sessionFile]=process.argv.slice(2);
if(!sessionFile)throw Error('Usage: point-window-capsule-test.mjs SDK START END SESSION');
const sdk=await import(pathToFileURL(resolve(sdkFile)).href);
const inputs=[startFile,endFile,sessionFile].map(p=>readFileSync(p,'utf8'));
const capsule=sdk.makeConfiguredPointWindowCapsuleV4(...inputs);
const replay=sdk.replayConfiguredPointWindowCapsuleV4(capsule);
assert.equal(replay.valid,true);
assert.equal(replay.sourceAuthenticated,false);
const envelope=JSON.parse(capsule);
for(const [i,name]of ['before','after','session'].entries())assert.equal(envelope[name+'Text'],inputs[i]);
assert.deepEqual(replay.report,sdk.analyzeConfiguredPointWindowV4(...inputs));
for(const field of ['beforeText','afterText','sessionText','reportText','optionsText']){
 const bad=structuredClone(envelope);bad[field]+=' ';
 assert.equal(sdk.replayConfiguredPointWindowCapsuleV4(bad).valid,false);
}
const forged=structuredClone(envelope),report=JSON.parse(forged.reportText);
report.status=report.status==='refuted'?'checked-compatible':'refuted';
forged.reportText=JSON.stringify(report);
forged.reportSha256=createHash('sha256').update(forged.reportText).digest('hex');
assert.equal(sdk.replayConfiguredPointWindowCapsuleV4(forged).valid,false);
assert.equal(sdk.replayConfiguredPointWindowCapsuleV4(capsule,{maxPointChecks:0}).valid,false);
assert.equal(sdk.replayConfiguredPointWindowCapsuleV4({...envelope,sourceAuthenticated:true}).valid,false);
assert.equal(sdk.replayConfiguredPointWindowCapsuleV4({...envelope,format:'other'}).valid,false);
assert.equal(sdk.replayConfiguredPointWindowCapsuleV4('null').valid,false);
const limited=sdk.makeConfiguredPointWindowCapsuleV4(...inputs,{maxPointChecks:0});
assert.equal(sdk.replayConfiguredPointWindowCapsuleV4(limited).valid,false);
const exhausted=sdk.replayConfiguredPointWindowCapsuleV4(limited,{maxPointChecks:0});
assert.equal(exhausted.valid,true);
assert.equal(exhausted.report.status,'unknown');
assert.equal(exhausted.report.coverageComplete,false);
console.log(JSON.stringify({passed:true,scope:'compiled SDK capsule replay, original texts, digest/report/budget tampering and exhaustion',actualDatabaseExecution:false}));
