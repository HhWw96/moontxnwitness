// Recompute the bounded semantic result of the retained real COMMIT response.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {sourceFingerprint} from '../../../scripts/build-fingerprint.mjs';
import * as sdk from '../../../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
if(process.argv.length!==3)throw Error('Usage: node experiments/business/dislock/v3_commit_e2e.mjs RETAINED_COMMIT_DIRECTORY');
const folder=resolve(process.argv[2]),sha=raw=>createHash('sha256').update(raw).digest('hex');
const raw=readFileSync(resolve(folder,'commit-receipt.json')),database=JSON.parse(raw);
assert.equal(database.passed,true);assert.equal(database.actualDatabaseExecution,true);
assert.equal(database.sourceBindingsUnchanged,true);assert.deepEqual(database.sourceBindings,database.sourceBindingsAfter);
for(const[file,b]of Object.entries(database.sourceBindings)){const bytes=readFileSync(resolve(root,file));assert.equal(bytes.length,b.bytes);assert.equal(sha(bytes),b.sha256);}
const build=JSON.parse(readFileSync(resolve(root,'dist/build-manifest.json'),'utf8'));
assert.equal(build.sourceSha256,sourceFingerprint(root));
for(const[file,key]of[['core.mjs','coreSha256'],['capture-core.mjs','captureCoreSha256']])assert.equal(sha(readFileSync(resolve(root,'dist',file))),build[key]);
for(const file of['sdk.mjs','evidence.mjs','moontxnwitness.mjs'])assert.equal(sha(readFileSync(resolve(root,'dist',file))),sha(readFileSync(resolve(root,'cmd',file))));
const trace=JSON.parse(readFileSync(resolve(folder,'capture.json'),'utf8'));
const report=sdk.analyzeV3(trace),normalized=sdk.normalizeCaptureV3(trace);
assert.equal(report.status,'inconclusive');assert.equal(report.coverage.complete,false);assert.equal(report.evidence,null);
assert.deepEqual(normalized.observations,trace.events);
assert.equal(normalized.algorithm,'v3-lifecycle-2');
assert.equal(normalized.transactions.filter(t=>t.status==='committed').length,1);
assert.equal(normalized.transactions.filter(t=>t.status==='aborted').length,1);
assert.equal(normalized.transactions.filter(t=>t.status==='unknown').length,0);
const proofEvent=trace.events.find(e=>e.kind==='rollback_ok'&&e.commitResponse?.sqlstate==='40001');
assert.ok(proofEvent);assert.deepEqual(proofEvent,database.rollbackProof);
const request=trace.events.find(e=>e.seq===proofEvent.commitResponse.request);
assert.equal(request.kind,'commit_request');assert.equal(request.tx,proofEvent.tx);
assert.equal(database.outcomes.find(o=>o.outcome==='server-confirmed-aborted').idleRollbackAddedEvents,0);
assert.equal(sdk.verifyV3(trace,report).valid,true);
const capsule=sdk.makeCapsuleV3(trace,report);assert.equal(sdk.replayCapsuleV3(capsule).valid,true);
const bindings=[];
function bind(file){const bytes=readFileSync(file);bindings.push({file:relative(folder,file).replaceAll('\\','/'),bytes:bytes.length,sha256:sha(bytes)});}
for(const[file,text]of[['model-report.json',JSON.stringify(report,null,2)+'\n'],['capsule.json',capsule]]){writeFileSync(resolve(folder,file),text,{flag:'wx'});bind(resolve(folder,file));}
for(const file of['commit-receipt.json','capture.json'])bind(resolve(folder,file));
for(const file of readdirSync(resolve(folder,'journal')))if(/^(?:segment-\d+\.jsonl|journal-index\.json|transactions\.sqlite3)$/.test(file))bind(resolve(folder,'journal',file));
const receipt={schema:1,passed:true,actualDatabaseExecution:false,sourceDatabaseExecutionRetained:true,
  scope:'Real server-confirmed COMMIT rollback protocol; raw SQL deliberately unmapped, no G2 or isolation classification',
  databaseReceiptSha256:sha(raw),sourceSha256:sha(readFileSync(fileURLToPath(import.meta.url))),build,
  status:report.status,committed:1,aborted:1,unknown:0,rollbackProof:proofEvent,bindings};
assert.equal(build.sourceSha256,sourceFingerprint(root));
writeFileSync(resolve(folder,'model-receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:true,status:report.status,actualDatabaseExecution:false,committed:1,aborted:1,unknown:0}));
