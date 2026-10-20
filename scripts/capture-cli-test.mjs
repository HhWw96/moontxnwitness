import {spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync, existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {normalizeCapture, analyzeWithOptions} from '../dist/sdk.mjs';

export function runCaptureCliTests() {
  const directory=mkdtempSync(resolve(tmpdir(),'moontxnwitness-capture-'));
  const initial={x:'x0',y:'y0'};
  const events=[
    {kind:'snapshot',initial,consistent:true},
    {kind:'begin',tx:'A'}, {kind:'begin',tx:'B'},
    {kind:'op',tx:'A',op:{type:'read',key:'x',version:'x0'}},
    {kind:'op',tx:'B',op:{type:'read',key:'y',version:'y0'}},
    {kind:'op',tx:'A',op:{type:'write',key:'y',version:'y1'}},
    {kind:'op',tx:'B',op:{type:'write',key:'x',version:'x1'}},
    {kind:'end',tx:'A',status:'committed'}, {kind:'end',tx:'B',status:'committed'},
  ].map((event,i)=>({...event,seq:i+1,time:i+1}));
  const trace={traceSchema:1,clockDomain:'test-monotonic',scope:{exclusiveWriters:true},events,gaps:[]};
  const ready=normalizeCapture(trace);
  assert.equal(ready.status,'ready');
  assert.equal(ready.coverage.complete,true);
  assert.equal(analyzeWithOptions(ready.history).status,'violation');
  const path=resolve(directory,'trace.json');
  const history=resolve(directory,'history.json');
  writeFileSync(path,JSON.stringify(trace));
  function run(args){return spawnSync(process.execPath,['dist/moontxnwitness.mjs','ingest',...args],{encoding:'utf8',windowsHide:true});}
  const exported=run([path,'--history',history]);
  assert.equal(exported.status,0,exported.stderr);
  assert.deepEqual(JSON.parse(readFileSync(history,'utf8')),ready.history);
  assert.equal(run([path,'--history',history]).status,2);
  const partial=structuredClone(trace);partial.events.splice(4,1);
  writeFileSync(path,JSON.stringify(partial));
  const incomplete=run([path]);
  assert.equal(incomplete.status,3,incomplete.stderr);
  assert.equal(JSON.parse(incomplete.stdout).history,null);
  const rejected=resolve(directory,'must-not-exist.json');
  assert.equal(run([path,'--history',rejected]).status,2);
  assert.equal(existsSync(rejected),false);
  const unknown=structuredClone(trace);unknown.events.at(-1).status='unknown';
  assert.equal(normalizeCapture(unknown).status,'inconclusive');
  const open=structuredClone(trace);open.scope.exclusiveWriters=false;
  assert.equal(normalizeCapture(open).history,null);
  const duplicate=JSON.stringify(trace).replace('"traceSchema":1','"traceSchema":1,"traceSchema":1');
  assert.equal(normalizeCapture(duplicate).status,'invalid');
  assert.equal(normalizeCapture('{').status,'invalid');
  console.log('Capture SDK/CLI checks passed (complete skew, missing event, unknown outcome, open scope, duplicate keys, safe output).');
  return {checks:14};
}
