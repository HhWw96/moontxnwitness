// Reproduce retained real business observations; fixed SQL proof is still a
// separate gate. Raw transport metadata must never turn into complete coverage.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {sourceFingerprint} from '../../../scripts/build-fingerprint.mjs';
import * as sdk from '../../../dist/sdk.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
if(process.argv.length!==3)throw Error('Usage: node experiments/business/dislock/v3_e2e.mjs RETAINED_DATABASE_DIRECTORY');
const folder=resolve(process.argv[2]);
const sha=raw=>createHash('sha256').update(raw).digest('hex');
const load=file=>JSON.parse(readFileSync(file,'utf8'));
const build=load(resolve(root,'dist/build-manifest.json'));
assert.equal(build.sourceSha256,sourceFingerprint(root),'The actual build must match the current MoonBit source');
for(const[file,key]of[['core.mjs','coreSha256'],['capture-core.mjs','captureCoreSha256']])assert.equal(sha(readFileSync(resolve(root,'dist',file))),build[key]);
for(const file of['sdk.mjs','evidence.mjs','moontxnwitness.mjs'])assert.equal(sha(readFileSync(resolve(root,'dist',file))),sha(readFileSync(resolve(root,'cmd',file))));
const databaseRaw=readFileSync(resolve(folder,'database-receipt.json'));
const database=JSON.parse(databaseRaw);
assert.equal(database.passed,true);
assert.equal(database.actualDatabaseExecution,true);
assert.equal(database.cases.length,7);
for(const[file,digest]of Object.entries(database.sourceSha256))assert.equal(sha(readFileSync(resolve(root,'experiments/business/dislock',file))),digest);
assert.equal(database.sourceBindingsUnchanged,true,'Business source changed during collection');
assert.deepEqual(database.sourceBindings,database.sourceBindingsAfter,'Pre/post source bindings must agree');
for(const[file,b]of Object.entries(database.sourceBindings)){
  const raw=readFileSync(resolve(root,file));assert.equal(raw.length,b.bytes);assert.equal(sha(raw),b.sha256);
}
const receipt={schema:1,passed:false,actualDatabaseExecution:false,sourceDatabaseExecutionRetained:true,
  databaseReceiptSha256:sha(databaseRaw),build,fullBusinessAnalysisAccepted:false,
  sourceBindings:database.sourceBindings,
  scope:'Original dislock execution, bounded journal, raw observations and semantic replay; fixed SQL/source proof and complete application analysis remain unaccepted',
  cases:[],inputBindings:[],outputBindings:[]};
function bind(file,list){const raw=readFileSync(file);list.push({file:relative(folder,file).replaceAll('\\','/'),bytes:raw.length,sha256:sha(raw)});return raw;}
function visit(dir){for(const e of readdirSync(dir,{withFileTypes:true})){const p=resolve(dir,e.name);if(e.isDirectory())visit(p);else if(e.isFile())bind(p,receipt.inputBindings);}}
for(const item of database.cases){
  const record={name:item.name,passed:false};
  try{
    assert.equal(item.passed,true);
    const dir=resolve(folder,item.name);
    assert.ok(dir.startsWith(folder+'/')||dir.startsWith(folder+'\\'));
    visit(dir);
    const traceRaw=readFileSync(resolve(dir,'capture.json'),'utf8');
    const trace=JSON.parse(traceRaw);
    const normalized=sdk.normalizeCaptureV3(traceRaw);
    const report=sdk.analyzeV3(traceRaw);
    assert.equal(normalized.status,'inconclusive','Unverified SQL cannot establish complete coverage');
    assert.equal(report.status,'inconclusive');
    assert.equal(report.coverage.complete,false);
    assert.equal(report.evidence,null);
    assert.deepEqual(normalized.observations,trace.events);
    assert.ok(normalized.coverage.gaps.length>0);
    assert.equal(sdk.verifyV3(traceRaw,report).valid,true);
    const capsule=sdk.makeCapsuleV3(traceRaw,report);
    assert.equal(sdk.replayCapsuleV3(capsule).valid,true);
    const policy={sqlProof:'dislock-f9946f0-sql-proof-1'};
    const sqlNormalized=sdk.normalizeCaptureV3(traceRaw,policy),sqlReport=sdk.analyzeV3(traceRaw,policy);
    const expectedSQL=['schedule-and-server-clock','acquire-heartbeat-cleanup','body-exception-cleanup'].includes(item.name)?'consistent':'inconclusive';
    assert.equal(sqlReport.status,expectedSQL);
    assert.equal(sqlReport.algorithm,'v3-register-sql-1');
    assert.deepEqual(sqlReport.normalized,sqlNormalized);
    assert.equal(sqlReport.execution.analysisOptions.sqlProof,policy.sqlProof);
    assert.equal(sqlReport.coverage.complete,expectedSQL==='consistent');
    assert.deepEqual(sqlNormalized.observations,trace.events);
    assert.equal(sdk.verifyV3(traceRaw,sqlReport).valid,true);
    const sqlCapsule=sdk.makeCapsuleV3(traceRaw,sqlReport);
    assert.equal(sdk.replayCapsuleV3(sqlCapsule).valid,true);
    if(item.name==='aborted-commit-response'){
      assert.equal(normalized.transactions.length,1);
      assert.equal(normalized.transactions[0].status,'aborted');
      assert.ok(trace.events.some(e=>e.kind==='rollback_ok'&&e.commitResponse?.commandTag==='ROLLBACK'));
    }
    const reportText=JSON.stringify(report,null,2)+'\n';
    for(const[file,raw]of[['model-report.json',reportText],['capsule.json',capsule],['sql-proof-report.json',JSON.stringify(sqlReport,null,2)+'\n'],['sql-proof-capsule.json',sqlCapsule]]){
      const target=resolve(dir,file);writeFileSync(target,raw,{flag:'wx'});bind(target,receipt.outputBindings);
    }
    record.passed=true;record.status=report.status;record.eventCount=trace.events.length;
    record.gapCodes=[...new Set(report.coverage.gaps.map(g=>g.code))];
    record.capsuleReproduced=true;
    record.explicitSqlPolicy={policy:policy.sqlProof,status:sqlReport.status,coverageComplete:sqlReport.coverage.complete,capsuleReproduced:true};
  }catch(e){record.error=String(e.message).replaceAll(root,'<workspace>').replaceAll(folder,'<retained-db-fixture>');}
  receipt.cases.push(record);
}
receipt.passed=receipt.cases.every(c=>c.passed);
assert.equal(build.sourceSha256,sourceFingerprint(root),'MoonBit source changed during reproduction');
for(const b of receipt.inputBindings){const raw=readFileSync(resolve(folder,b.file));assert.equal(raw.length,b.bytes);assert.equal(sha(raw),b.sha256,'Input changed during reproduction');}
writeFileSync(resolve(folder,'model-receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.length,fullBusinessAnalysisAccepted:false,
  actualDatabaseExecution:false,failures:receipt.cases.filter(c=>!c.passed)}));
if(!receipt.passed)process.exitCode=1;
