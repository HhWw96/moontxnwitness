import {spawnSync} from 'node:child_process';
import {mkdtempSync,readFileSync,writeFileSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {normalizeCapture,normalizePresenceCapture} from '../dist/sdk.mjs';

// The insert's predecessor is evidence about a write, never a second read.
export function runPresenceCliTests() {
  const x0='10000000-0000-4000-8000-000000000001';
  const n0='10000000-0000-4000-8000-000000000002';
  const n1='10000000-0000-4000-8000-000000000003';
  const trace={traceSchema:2,clockDomain:'presence-cli-monotonic',
    scope:{exclusiveWriters:true},gaps:[],events:[
      {seq:1,time:1,kind:'snapshot',initial:{x:x0,n:n0},consistent:true},
      {seq:2,time:2,kind:'begin',tx:'A'},
      {seq:3,time:3,kind:'op',tx:'A',op:{type:'read',key:'n',version:n0}},
      {seq:4,time:4,kind:'op',tx:'A',op:{type:'write',key:'n',version:n1}},
      {seq:5,time:5,kind:'end',tx:'A',status:'committed'},
    ],presenceFacts:{schema:1,projection:'column-presence-register-v0.1.2-experimental',
      initial:[{key:'x',version:x0,present:true},{key:'n',version:n0,present:false}],
      reads:[{seq:3,tx:'A',key:'n',version:n0,present:false}],
      writes:[{seq:4,tx:'A',key:'n',version:n1,predecessor:n0,
        oldPresent:false,newPresent:true,action:'insert'}]}};
  let checks=0;
  const eq=(actual,expected)=>{assert.deepEqual(actual,expected);checks++;};
  const ready=normalizePresenceCapture(trace);
  eq(ready.status,'ready');
  eq(ready.coverage.complete,true);
  eq(ready.history.transactions[0].ops,[
    {type:'read',key:'n',version:n0},{type:'write',key:'n',version:n1}]);
  eq(ready.history.versionOrders,{x:[x0],n:[n0,n1]});
  eq(ready.sourceFacts,trace.presenceFacts);
  eq(ready.projection.version,trace.presenceFacts.projection);
  eq(normalizeCapture(trace).status,'invalid');
  const directory=mkdtempSync(resolve(tmpdir(),'moontxnwitness-presence-'));
  const path=resolve(directory,'trace.json'),history=resolve(directory,'history.json');
  writeFileSync(path,JSON.stringify(trace));
  const run=(command,args)=>spawnSync(process.execPath,['dist/moontxnwitness.mjs',command,...args],{encoding:'utf8',windowsHide:true});
  const exported=run('ingest-presence',[path,'--history',history]);
  eq(exported.status,0);
  eq(JSON.parse(readFileSync(history,'utf8')),ready.history);
  eq(run('ingest-presence',[path,'--history',history]).status,2);
  eq(run('ingest',[path]).status,2);
  for(const change of [
    value=>{value.presenceFacts.writes=[];},
    value=>{value.presenceFacts.reads[0].present=true;},
    value=>{value.events.at(-1).status='unknown';},
  ]) {
    const incomplete=structuredClone(trace);change(incomplete);
    const result=normalizePresenceCapture(incomplete);
    assert.notEqual(result.status,'ready');checks++;
    eq(result.history,null);
  }
  const incomplete=structuredClone(trace);incomplete.presenceFacts.writes=[];
  writeFileSync(path,JSON.stringify(incomplete));
  const refused=resolve(directory,'must-not-exist.json');
  eq(run('ingest-presence',[path,'--history',refused]).status,2);
  eq(existsSync(refused),false);
  const duplicate=JSON.stringify(trace).replace('"traceSchema":2','"traceSchema":2,"traceSchema":2');
  eq(normalizePresenceCapture(duplicate).status,'invalid');
  eq(normalizePresenceCapture('{').status,'invalid');
  const gap=structuredClone(trace);
  gap.gaps.push({code:'test-gap',message:'Explicit controlled coverage gap.'});
  eq(normalizePresenceCapture(gap).status,'inconclusive');
  writeFileSync(path,JSON.stringify(gap));
  const gapResult=run('ingest-presence',[path]);
  eq(gapResult.status,3);
  eq(JSON.parse(gapResult.stdout).history,null);
  eq(run('ingest-presence',[path,'--history',refused]).status,2);
  eq(existsSync(refused),false);
  console.log('Presence SDK/CLI checks passed ('+checks+'; experimental schema, source facts, absence, safe export, fail-closed gaps).');
  return {checks};
}
