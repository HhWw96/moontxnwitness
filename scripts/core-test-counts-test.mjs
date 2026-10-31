import assert from 'node:assert/strict';
import {parseMoonTestTotal,jsCoreTestCount} from './core-test-counts.mjs';
const valid={executedTargets:['js','wasm-gc','wasm'],coreTestsPerTarget:1841,coreTestCountsByTarget:{js:1853,'wasm-gc':1841,wasm:1841}};let checks=0;
assert.equal(jsCoreTestCount(valid,{expectedJS:1853,jsOnly:12}),1853);checks++;
assert.equal(jsCoreTestCount({coreTestsPerTarget:977}),977);checks++;
for(const edit of [s=>s.coreTestCountsByTarget.js=1841,s=>delete s.coreTestCountsByTarget.wasm,s=>s.coreTestCountsByTarget.wasm=1842,s=>s.coreTestsPerTarget=1853]){const bad=structuredClone(valid);edit(bad);assert.throws(()=>jsCoreTestCount(bad,{expectedJS:1853,jsOnly:12}));checks++;}
assert.equal(parseMoonTestTotal('Total tests: 1853, passed: 1853, failed: 0.\n','js'),1853);checks++;
for(const raw of ['Total tests: 1853, passed: 1852, failed: 1.','Total tests: 0, passed: 0, failed: 0.','Total tests: 1, passed: 1, failed: 0.\nTotal tests: 2, passed: 2, failed: 0.']){assert.throws(()=>parseMoonTestTotal(raw,'js'));checks++;}
console.log(JSON.stringify({passed:true,checks,summaryTamperCases:4,legacyFallbackRetained:true}));
