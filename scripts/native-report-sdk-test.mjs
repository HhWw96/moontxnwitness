// Functional transport checks only: no benchmark samples or performance claims.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, unlinkSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const [runtimeArg, receiptArg] = process.argv.slice(2);
assert(runtimeArg && receiptArg);
const runtime = resolve(runtimeArg);
const corePath = resolve(runtime, 'core.mjs'), sdkPath = resolve(runtime, 'sdk.mjs');
const sha = value => createHash('sha256').update(value).digest('hex');
const coreBytes = readFileSync(corePath), sdkBytes = readFileSync(sdkPath);
const core = await import(pathToFileURL(corePath)), sdk = await import(pathToFileURL(sdkPath));
const results = [];
function check(name, run) { run(); results.push({name, passed: true}); }
function pair(history, options) {
  const text = typeof history === 'string' ? history : JSON.stringify(history);
  const original = JSON.stringify(history), optionText = JSON.stringify(options);
  const wire = options === undefined ? core.analyze_json(text) : core.analyze_options_json(text, optionText);
  const report = options === undefined ? sdk.analyze(history) : sdk.analyzeWithOptions(history, options);
  assert.deepEqual(report, JSON.parse(wire));
  assert.equal(JSON.stringify(report), JSON.stringify(JSON.parse(wire)), 'Every field and insertion order');
  assert.equal(JSON.stringify(history), original);
  assert.equal(JSON.stringify(options), optionText);
  assert.equal(Object.getPrototypeOf(report), Object.prototype);
  for (const edge of report.edges) {
    assert.equal(Object.getPrototypeOf(edge), Object.prototype);
    assert.deepEqual(Object.keys(edge), ['from','to','kind','key','fromOp','toOp','fromVersion','toVersion','reason']);
  }
  return report;
}
check('Both explicit native bridge exports exist', () => {
  assert.equal(typeof core.analyze_native_js_v1, 'function');
  assert.equal(typeof core.analyze_options_native_js_v1, 'function');
});
for (const text of ['not json','[]','{}','{"unknown":true}', '{"model":"serializable","initial":{},"transactions":[]}']) {
  check('Legacy syntax/schema parity: ' + text, () => pair(text));
  check('Balanced syntax/schema parity: ' + text, () => pair(text, {}));
}
const history = {model:'serializable',initial:{x:'x0'},transactions:[
  {id:'A',status:'committed',ops:[{type:'write',key:'x',version:'x1'}]},
  {id:'B',status:'committed',ops:[{type:'write',key:'x',version:'x2'}]},
]};
for (const options of [{maxAttempts:0},{maxAttempts:1},{maxAttempts:100000,maxOperationChecks:1000000,maxCachedStates:50000},
  {maxOperationChecks:0},{maxOperationChecks:1},{maxCachedStates:0},{maxAttempts:-1},{maxAttempts:100001},
  {maxAttempts:1.5},{maxAttempts:null},{maxAttempts:'1'},{unexpected:true},null,[],true]) {
  check('Exact parser/budget parity ' + JSON.stringify(options), () => {
    const report=pair(history, options);
    if (options && typeof options==='object' && !Array.isArray(options) && Object.entries(options).every(([key,value])=>['maxAttempts','maxOperationChecks','maxCachedStates'].includes(key)&&Number.isInteger(value)&&value>=0&&value<=({maxAttempts:100000,maxOperationChecks:1000000,maxCachedStates:50000})[key])) {
      assert.notEqual(report.status,'invalid','Valid operation fixture must exercise real budgets');
    } else assert.equal(report.status,'invalid');
  });
}
const names=['月🙂𐐷','e\u0301','a"\\b','__proto__','constructor','version'];
for (const name of names) {
  check('Unicode and special identifiers ' + JSON.stringify(name), () => {
    const h={model:'serializable',initial:{x:'x0'},transactions:[
      {id:name,status:'committed',ops:[{type:'write',key:'x',version:'v1'}]},
      {id:'reader-'+name,status:'committed',ops:[{type:'read',key:'x',version:'v1'}]},
    ]};
    const report=pair(h,{});assert.equal(report.status,'consistent');
    assert.equal(report.edges[0].from,name);assert.equal(report.edges[0].fromOp,0);
  });
}
check('ASCII-control identifiers retain existing parser rejection', () => {
  const h={initial:{},transactions:[{id:'control:\n\u0000',status:'committed',ops:[]}]};
  assert.equal(pair(h,{}).status,'invalid');
});
for (const id of ['\ud800','\udfff','A\ud800B']) {
  check('Unpaired UTF-16 input retains original parsing outcome ' + JSON.stringify(id), () => {
    pair({initial:{},transactions:[{id,status:'committed',ops:[]}]},{});
  });
}
check('Returned objects do not alias reports, input, or later calls', () => {
  const original=JSON.stringify(history), before=pair(history,{});
  const expected=JSON.stringify(before);
  before.findings.push({code:'mutated'});before.versionOrders.x.push('mutated');
  before.stats.dependencies=-1;before.edges.push({from:'mutated'});
  assert.equal(JSON.stringify(pair(history,{})),expected);
  assert.equal(JSON.stringify(history),original);
});
const fallbackPath=resolve(runtime,'native-report-fallback-test.mjs');
const fallbackCore=resolve(runtime,'native-report-fallback-core.mjs');
try {
  const exports=Object.keys(core).filter(name=>!['analyze_native_js_v1','analyze_options_native_js_v1'].includes(name));
  assert(exports.every(name=>/^[A-Za-z_$][\w$]*$/.test(name)));
  writeFileSync(fallbackCore,`export {${exports.join(',')}} from './core.mjs';\n`,{flag:'wx'});
  const fallbackSource=sdkBytes.toString().replace("import * as nativeReportCore from './core.mjs';", "import * as nativeReportCore from './native-report-fallback-core.mjs';");
  assert.notEqual(fallbackSource,sdkBytes.toString());
  writeFileSync(fallbackPath,fallbackSource,{flag:'wx'});
  const fallback=await import(pathToFileURL(fallbackPath));
  check('Absent native legacy export feature-detects original text fallback',()=>assert.deepEqual(fallback.analyze(history),JSON.parse(core.analyze_json(JSON.stringify(history)))));
  check('Absent native balanced export feature-detects exact old options path',()=>assert.deepEqual(fallback.analyzeWithOptions(history,{maxAttempts:0}),JSON.parse(core.analyze_options_json(JSON.stringify(history),'{"maxAttempts":0}'))));
} finally {
  for (const path of [fallbackPath,fallbackCore]) try { unlinkSync(path); } catch(error) { if(error.code!=='ENOENT')throw error; }
}
assert.equal(sha(readFileSync(corePath)),sha(coreBytes));
assert.equal(sha(readFileSync(sdkPath)),sha(sdkBytes));
const receipt={format:'native-report-sdk-functional/v1',passed:true,tests:results.length,results,
  coreSha256:sha(coreBytes),sdkSha256:sha(sdkBytes),runtimeUnchanged:true,
  optionsParserAndBudgetsReused:true,textAPIUnchanged:true,formalPerformanceMeasurement:false,DWritten:false};
writeFileSync(receiptArg,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:true,tests:results.length,formalPerformanceMeasurement:false}));
