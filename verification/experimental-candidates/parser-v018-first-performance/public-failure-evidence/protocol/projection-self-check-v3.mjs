// Runs only inside the explicitly authorized protocol. No core import or timing.
import assert from 'node:assert/strict';
import {projectEngineHeader} from './engine-header-projection-v3.mjs';
const before=' {"tool":"MoonTxnWitness","schemaVersion":2,"version":"0.1.7","algorithm":"bounded-register-v2.1","versionOrders":{"x":["0.1.7","0.1.8"]},"metrics":{"attempts":7},"message":"business 0.1.7 / 0.1.8"}\n';
const after=before.replace('"version":"0.1.7"','"version":"0.1.8"');
const a=projectEngineHeader(before,'0.1.7'),b=projectEngineHeader(after,'0.1.8');
assert.equal(a.projectedText,b.projectedText);assert.ok(a.projectedText.includes('"x":["0.1.7","0.1.8"]'));assert.ok(a.projectedText.includes('business 0.1.7 / 0.1.8'));
assert.notEqual(projectEngineHeader(after.replace('"attempts":7','"attempts":8'),'0.1.8').projectedText,a.projectedText);
assert.notEqual(projectEngineHeader(after.replace('business 0.1.7','business 0.1.8'),'0.1.8').projectedText,a.projectedText);
for(const text of [before.replace('"version":"0.1.7"','"version":"0.1.7","version":"0.1.7"'),before.replace('"attempts":7','"attempts":7,"attempts":7'),before.replace('"bounded-register-v2.1"','"unknown"'),before.replace('"version":"0.1.7"','"version":"99.0.0"'),before.replace('"version":"0.1.7"','"vers\\u0069on":"0.1.7"')])assert.throws(()=>projectEngineHeader(text,'0.1.7'));
console.log(JSON.stringify({passed:true,coreImported:false,timingExecuted:false,scope:'Only known root engine metadata spans; business strings, budgets and all other characters remain exact.'}));
