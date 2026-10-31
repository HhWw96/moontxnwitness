import assert from 'node:assert/strict';
export function parseMoonTestTotal(output,target){
 const rows=[...output.matchAll(/(?:^|\r?\n)Total tests: (\d+), passed: (\d+), failed: (\d+)\./g)];
 assert.equal(rows.length,1,`One actual Moon summary required for ${target}`);
 const [,total,passed,failed]=rows[0].map((x,i)=>i?Number(x):x);
 assert(Number.isSafeInteger(total)&&total>0);assert.equal(passed,total);assert.equal(failed,0);
 return total;
}
export function jsCoreTestCount(summary,{expectedJS,jsOnly}={}){
 const common=summary.coreTestsPerTarget;assert(Number.isSafeInteger(common)&&common>0);
 if(!Object.hasOwn(summary,'coreTestCountsByTarget'))return common;
 const counts=summary.coreTestCountsByTarget,targets=summary.executedTargets;
 assert(counts&&typeof counts==='object'&&!Array.isArray(counts));assert(Array.isArray(targets)&&targets.includes('js'));
 assert.equal(new Set(targets).size,targets.length);assert(targets.every(t=>['js','wasm-gc','wasm','native'].includes(t)));
 assert.deepEqual(Object.keys(counts).sort(),[...targets].sort());
 for(const [target,n]of Object.entries(counts)){assert(Number.isSafeInteger(n)&&n>0);if(target!=='js')assert.equal(n,common);}
 assert.equal(common,Math.min(...Object.values(counts)));assert(counts.js>=common);
 if(expectedJS!==undefined)assert.equal(counts.js,expectedJS);
 if(jsOnly!==undefined)assert.equal(counts.js-common,jsOnly);
 return counts.js;
}
