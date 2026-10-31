import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'..'),runtime=resolve(root,'dist/configured-session-core.mjs');
const suites=[
 ['hostEnvelope','configured-session-host-test.mjs',[],8],
 ['sessionSdk','configured-session-v4-test.mjs',[runtime],25],
 ['sourceComponents','source-components-v4-test.mjs',['--runtime',runtime],56],
 ['selectConstraints','source-select-session-integration-test.mjs',['--runtime',runtime],14],
 ['runtimeConsumer','configured-session-runtime-test.mjs',[],14],
];
const results={};
for(const [name,script,args,count]of suites){
 const child=spawnSync(process.execPath,[resolve(root,'scripts',script),...args],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:16*1024*1024});
 assert.equal(child.status,0,child.stdout+child.stderr);
 const value=JSON.parse(child.stdout);
 const checks=typeof value.checks==='number'?value.checks:value.passed;
 assert.equal(checks,count,name);
 assert.equal(value.failures??value.failed??0,0,name);
 results[name]={passed:true,checks:count};
}
console.log(JSON.stringify({format:'configured-session-current-integration-tests/v1',passed:true,results,actualDatabaseExecution:false,sourceFactsProduced:false,writerWindowVerified:false,isolationAnalysisReady:false}));
