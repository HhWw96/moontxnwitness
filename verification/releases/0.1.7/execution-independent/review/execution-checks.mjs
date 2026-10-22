// Exact diagnostic behavior assertions extracted from the frozen candidate81 runner.
// Environment checks are separate. No product code runs when this file is staged.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const sha=b=>createHash('sha256').update(b).digest('hex'),canon=x=>JSON.stringify(x,null,2)+'\n',clone=x=>structuredClone(x);
const reject=(sdk,text,reason)=>{const result=sdk.replayExecutionCapsuleV3(text);assert.equal(result.valid,false);assert.equal(result.scope.actualDatabaseExecution,false);if(reason)assert.equal(result.reason,reason);return result.reason;};
const reseal=x=>{x.traceSha256=sha(x.traceText);x.diagnosticSha256=sha(x.diagnosticText);return canon(x);};
export function runExecutionChecks({sdk,rows,expectedDiagnostics,check,retain}) {
  const capsules=new Map();
  for(const row of rows)check('independent-fixture-'+row.id,()=>{const capsule=sdk.makeExecutionCapsuleV3(row.traceText),pack=JSON.parse(capsule),replay=sdk.replayExecutionCapsuleV3(capsule),diag=replay.diagnostic;assert.equal(replay.valid,true);assert.equal(pack.traceText,row.traceText);assert.equal(sha(Buffer.from(pack.traceText)),sha(Buffer.from(row.traceText)));assert.deepEqual(diag,expectedDiagnostics[row.id]);assert.equal(diag.observedFaultCount,row.expectedFaults);assert.equal(diag.transactionOutcomes[0].status,row.expectedOutcome);if(row.expectedKind)assert.equal(diag.faults[0].kind,row.expectedKind);assert.equal(diag.modelViolationClaim,false);assert.equal(diag.certifiesFailureAbsence,false);assert.equal(diag.databaseAuthenticityVerified,false);for(const k of ['actualDatabaseExecution','databaseAuthenticityVerified','certifiesFailureAbsence','modelViolationClaim','completeApplicationIntegration'])assert.equal(replay.scope[k],false);capsules.set(row.id,capsule);retain(row.id+'.capsule.json',capsule);retain(row.id+'.replay.json',replay);return {validMeans:'diagnostic-recomputed',observedFaults:diag.observedFaultCount,outcome:row.expectedOutcome,captureStatus:diag.captureStatus};});
  const text=capsules.get('rows-40P01'),base=JSON.parse(text);
  check('faulted-valid-package-is-not-G2-or-absence-certificate',()=>{const result=sdk.replayExecutionCapsuleV3(text);assert.equal(result.valid,true);assert.equal(result.status,'recomputed-observations');assert.equal(result.diagnostic.faults[0].sqlstate,'40P01');assert.equal(result.diagnostic.faults[0].kind,'deadlock');const report=sdk.analyzeV3(base.traceText);assert.equal(report.evidence,null);assert.notEqual(report.status,'violation');retain('deadlock.model-report.json',report);});
  check('unknown-COMMIT-and-idle-ROLLBACK-both-stay-unknown',()=>{for(const id of ['unknown-commit','idle-rollback-after-unacknowledged-commit']){const d=sdk.replayExecutionCapsuleV3(capsules.get(id)).diagnostic;assert.equal(d.captureStatus,'inconclusive');assert.equal(d.transactionOutcomes[0].status,'unknown');assert.equal(d.observedFaultCount,0);assert.equal(d.captureCoverage.complete,false);assert.ok(d.captureCoverage.gaps.some(x=>x.code==='unknown_commit'));}});
  const outerRaw={
    'outer-duplicate-known-key':text.replace('{','{"schemaVersion":1,'),
    'outer-escaped-equivalent-duplicate':text.replace('{','{"schema\\u0056ersion":1,'),
    'outer-duplicate-budgets':text.replace('"traceUtf8Bytes": 8388608,','"traceUtf8Bytes": 8388608, "traceUtf8Bytes": 8388608,'),
    'outer-noncanonical-minified':JSON.stringify(base),
    'outer-missing-final-newline':text.slice(0,-1),
    'outer-UTF8-BOM':'\uFEFF'+text,
    'outer-trailing-data':text+'{}',
  };
  for(const [name,value]of Object.entries(outerRaw))check(name,()=>reject(sdk,value));
  for(const [name,mutate]of Object.entries({
    'outer-unknown':x=>x.unrecognized=true,'nested-budget-unknown':x=>x.budgets.unknown=1,
    'budget-trace':x=>x.budgets.traceUtf8Bytes--,'budget-diagnostic':x=>x.budgets.diagnosticUtf8Bytes++,
    'budget-envelope':x=>x.budgets.capsuleUtf8Bytes++,'budget-normalization-units':x=>x.budgets.normalizedJsonCodeUnits++,
    'budget-normalization-policy':x=>x.budgets.normalizationPolicy='unsafe','budget-model-search':x=>x.budgets.modelSearch=true,
    'version-future':x=>x.engineVersion='99.0.0','version-wildcard':x=>x.engineVersion='0.1.*','version-stale':x=>x.engineVersion='0.1.4',
    'algorithm-future':x=>x.diagnosticAlgorithm='v3-observed-failures-2','format-model':x=>x.format='moontxnwitness-replay/v3',
    'schema':x=>x.schemaVersion=2,'tool':x=>x.tool='Other','trace-digest':x=>x.traceSha256='0'.repeat(64),
  }))check('rehashed-'+name,()=>{const x=clone(base);mutate(x);return reject(sdk,name==='trace-digest'?canon(x):reseal(x));});
  const rawDiagnostic={
    'duplicate-root':base.diagnosticText.replace('{','{"valid":true,'),
    'duplicate-fault':base.diagnosticText.replace('"kind":"deadlock"','"kind":"deadlock","kind":"deadlock"'),
    'escaped-duplicate-fault':base.diagnosticText.replace('"kind":"deadlock"','"kind":"deadlock","ki\\u006ed":"deadlock"'),
    'noncanonical-diagnostic-whitespace':base.diagnosticText+' ',
  };
  for(const [name,value]of Object.entries(rawDiagnostic))check('rehashed-diagnostic-'+name,()=>{const x=clone(base);assert.notEqual(value,x.diagnosticText);x.diagnosticText=value;return reject(sdk,reseal(x),'execution-diagnostic-does-not-reproduce');});
  for(const [name,mutate]of Object.entries({
    'unknown-root':d=>d.unrecognized=true,'unknown-nested-fault':d=>d.faults[0].unrecognized=true,
    'unknown-coverage':d=>d.captureCoverage.unrecognized=true,'kind-G2':d=>d.faults[0].kind='G2',
    'sqlstate':d=>d.faults[0].sqlstate='40001','driver':d=>d.faults[0].driverClass='OtherDriver',
    'event-source':d=>d.faults[0].seq++,'fault-count':d=>d.observedFaultCount=0,
    'outcome':d=>d.transactionOutcomes[0].status='committed','coverage':d=>d.captureCoverage.complete=true,
    'drop-gaps':d=>d.captureCoverage.gaps=[],'missing-status':d=>delete d.captureStatus,
    'model-claim':d=>d.modelViolationClaim=true,'authenticity':d=>d.databaseAuthenticityVerified=true,
    'failure-absence':d=>d.certifiesFailureAbsence=true,
  }))check('rehashed-semantic-'+name,()=>{const x=clone(base),d=JSON.parse(x.diagnosticText);mutate(d);const changed=JSON.stringify(d);assert.notEqual(changed,x.diagnosticText);x.diagnosticText=changed;return reject(sdk,reseal(x),'execution-diagnostic-does-not-reproduce');});
  check('rehashed-source-SQLSTATE-with-stale-diagnostic-rejected',()=>{const x=clone(base),t=JSON.parse(x.traceText);t.events.find(e=>e.error).error.sqlstate='40001';x.traceText=JSON.stringify(t);return reject(sdk,reseal(x),'execution-diagnostic-does-not-reproduce');});
  check('resealed-new-record-with-new-correct-diagnostic-is-not-authentication',()=>{const t=JSON.parse(base.traceText);t.events.find(e=>e.error).error.sqlstate='40001';const fresh=sdk.replayExecutionCapsuleV3(sdk.makeExecutionCapsuleV3(JSON.stringify(t)));assert.equal(fresh.valid,true);assert.equal(fresh.diagnostic.faults[0].kind,'serialization_abort');assert.equal(fresh.scope.databaseAuthenticityVerified,false);retain('caller-rewritten-record.replay.json',fresh);});
  const commitBase=JSON.parse(capsules.get('commit-native-deadlock'));
  for(const [name,mutate]of Object.entries({
    'mismatched-diagnostics':p=>p.diagnosticSqlstate='40001','wrong-request':p=>p.request=2,
    'wrong-transaction-status':p=>p.transactionStatus='INERROR','unknown-response-field':p=>p.extra=true,
    'unsupported-error':p=>{p.sqlstate='23505';p.diagnosticSqlstate='23505';},
    'wrong-command-tag':p=>{delete p.sqlstate;delete p.diagnosticSqlstate;delete p.transactionStatus;p.commandTag='COMMIT';},
  }))check('invalid-COMMIT-response-'+name,()=>{const x=clone(commitBase),t=JSON.parse(x.traceText);mutate(t.events[3].commitResponse);x.traceText=JSON.stringify(t);assert.equal(sdk.inspectExecutionFailuresV3(x.traceText).valid,false);assert.throws(()=>sdk.makeExecutionCapsuleV3(x.traceText));return reject(sdk,reseal(x));});
  for(const [name,value]of Object.entries({
    'duplicate-source-root':base.traceText.replace('{','{"traceSchema":3,'),
    'escaped-duplicate-source-nested':base.traceText.replace('"class": "ReviewerNativeError"','"class": "ReviewerNativeError", "cl\\u0061ss": "ReviewerNativeError"'),
    'unknown-source-field':base.traceText.replace('"traceSchema": 3,','"traceSchema": 3, "extra": true,'),
    'malformed':'{','primitive':'null',
  }))check('source-rejected-'+name,()=>{assert.notEqual(value,base.traceText);assert.throws(()=>sdk.makeExecutionCapsuleV3(value));const x=clone(base);x.traceText=value;return reject(sdk,reseal(x));});
  check('exact-original-Unicode-whitespace-CRLF-roundtrip',()=>{const row=rows[0],p=JSON.parse(capsules.get(row.id));assert.ok(row.traceText.includes('\r\n'));assert.ok(row.traceText.includes('🚀'));assert.deepEqual(Buffer.from(p.traceText),Buffer.from(row.traceText));return {traceSha256:sha(row.traceText),bytes:Buffer.byteLength(row.traceText)};});
  check('unpaired-literal-surrogate-rejected',()=>{const x=clone(base);x.traceText=x.traceText.replace('🚀','\uD800');assert.throws(()=>sdk.makeExecutionCapsuleV3(x.traceText),TypeError);return reject(sdk,reseal(x),'execution-trace-not-well-formed-unicode');});
  check('trace-UTF8-over-budget-by-ASCII-or-multibyte-rejected',()=>{for(const t of [' '.repeat(8388609),'中'.repeat(Math.floor(8388608/3)+1)]){assert.ok(Buffer.byteLength(t)>8388608);assert.throws(()=>sdk.makeExecutionCapsuleV3(t),RangeError);const x=clone(base);x.traceText=t;reject(sdk,reseal(x),'execution-content-byte-budget');}});
  check('capsule-over-32MiB-rejected-before-parse',()=>reject(sdk,' '.repeat(33554433),'execution-capsule-byte-budget'));
  check('core-event-budget-65536-accepted-65537-rejected',()=>{const t={traceSchema:3,clockDomain:'independent-event-boundary',scope:{exclusiveWriters:true},gaps:[],events:[{seq:1,time:0,kind:'snapshot',initial:{},consistent:true},{seq:2,time:1,kind:'begin',tx:'A',connection:'c'},{seq:3,time:2,kind:'savepoint',tx:'A',name:'s',instance:'i'}]};while(t.events.length<65535){const seq=t.events.length+1;t.events.push({seq,time:seq-1,kind:'rollback_to',tx:'A',instance:'i'});}t.events.push({seq:65536,time:65535,kind:'rollback_ok',tx:'A'});let value=JSON.stringify(t);assert.ok(Buffer.byteLength(value)<8388608);assert.equal(sdk.inspectExecutionFailuresV3(value).valid,true);t.events.splice(t.events.length-1,0,{seq:65536,time:65535,kind:'rollback_to',tx:'A',instance:'i'});t.events.at(-1).seq=65537;t.events.at(-1).time=65536;value=JSON.stringify(t);assert.ok(Buffer.byteLength(value)<8388608);assert.equal(sdk.inspectExecutionFailuresV3(value).valid,false);assert.throws(()=>sdk.makeExecutionCapsuleV3(value));const x=clone(base);x.traceText=value;reject(sdk,reseal(x));return {acceptedEvents:65536,rejectedEvents:65537,overLimitTraceBytes:Buffer.byteLength(value),generator:'review.mjs frozen source'};});
  check('model-execution-formats-cannot-be-interchanged',()=>{const m=sdk.makeCapsuleV3(base.traceText);assert.equal(sdk.replayCapsuleV3(m).valid,true);reject(sdk,m);assert.equal(sdk.replayCapsuleV3(text).valid,false);});

  return {capsules,base};
}
