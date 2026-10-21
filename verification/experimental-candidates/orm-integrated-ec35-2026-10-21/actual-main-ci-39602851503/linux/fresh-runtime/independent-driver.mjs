
import assert from 'node:assert/strict';
import {readFileSync as nativeReadFileSync,writeFileSync,mkdirSync,statSync} from 'node:fs';
const readFileSync=(path,...args)=>{assert(statSync(path).size<=32*1024*1024,'Consumer input byte limit');return nativeReadFileSync(path,...args);};
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import * as sdk from './dist/sdk.mjs';
import * as evidence from './dist/evidence.mjs';
const base=process.cwd(), pg=process.argv[2], cases=[];
const load=p=>JSON.parse(readFileSync(p,'utf8'));
const output=resolve('audit-output');mkdirSync(output);
const check=(name,fn)=>{try{fn();cases.push({name,passed:true});}catch(e){cases.push({name,passed:false,error:String(e.message).replaceAll(base,'<fresh>').replaceAll(pg,'<downloaded-pg>')});}};
const trace=load('fixtures/v3/write-skew-safe-projection.json');
let report,proof;
check('v3-real-runtime-import-and-analysis',()=>{assert.equal(sdk.version(),'0.1.1');report=sdk.analyzeV3(trace);assert.equal(report.status,'violation');assert.equal(report.normalized.status,'ready');});
check('v3-report-verification',()=>assert.equal(sdk.verifyV3(trace,report).valid,true));
check('v3-capsule-and-replay',()=>{proof=sdk.makeCapsuleV3(trace,report);assert.equal(sdk.replayCapsuleV3(proof).valid,true);});
check('v3-recomputed-digest-forged-conclusion-rejected',()=>{const c=JSON.parse(proof),r=JSON.parse(c.reportText);r.status='consistent';c.reportText=JSON.stringify(r);c.reportSha256=(awaitHash(c.reportText));assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);});
function awaitHash(text){return createHash('sha256').update(text).digest('hex');}
import {createHash} from 'node:crypto';
check('v3-own-read-before-rollback-observation-retained',()=>{const t=load('fixtures/v3/read-of-later-reverted-own-write.json'),n=sdk.normalizeCaptureV3(t);assert.equal(n.status,'ready');assert.deepEqual(n.observations,t.events);assert.notEqual(n.effects[0].revertedBy,null);assert.deepEqual(n.history.transactions[0].ops,[]);});
check('v3-own-read-after-rollback-remains-incomplete',()=>{const n=sdk.normalizeCaptureV3(load('fixtures/v3/read-after-rollback-revoked-own-write.json'));assert.equal(n.status,'inconclusive');assert.equal(n.history,null);assert.ok(n.coverage.gaps.some(g=>g.code==='own_read_mismatch'));});
check('v3-release-does-not-commit',()=>{const n=sdk.normalizeCaptureV3(load('fixtures/v3/release-is-not-commit.json'));assert.equal(n.status,'inconclusive');assert.equal(n.transactions[0].status,'unknown');});
check('v3-unknown-commit-not-cured-by-rollback',()=>{const r=sdk.analyzeV3(load('fixtures/v3/rollback-after-request-not-proof.json'));assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);});
check('v3-source-closure-and-budget',()=>{const t=load('fixtures/v3/reduction-source-closure.json'),z=sdk.reduceV3(t,{maxChecks:0}),r=sdk.reduceV3(t,{maxChecks:256});assert.equal(z.oneMinimal,false);assert.equal(z.checks,0);assert.equal(r.oneMinimal,true);assert.deepEqual(r.removed,['noise']);assert.deepEqual(r.report.normalized.transactions.map(t=>t.id),['source','A','B']);});
check('v3-disk-journal-export-runtime-analysis',()=>{const r=sdk.analyzeV3(load('journal-export.json'));assert.equal(r.status,'consistent');assert.equal(r.normalized.status,'ready');});
const old=load('examples/write-skew.json');let r1,p1,r2,p2;
check('legacy-v1-actual-core-analysis',()=>{r1=sdk.analyze(old);assert.equal(r1.status,'violation');});
check('legacy-v1-capsule-replay',()=>{p1=evidence.makeCapsule(JSON.stringify(old),r1);assert.equal(JSON.parse(p1).format,'moontxnwitness-replay/v1');assert.equal(evidence.replayCapsule(p1).valid,true);});
check('legacy-v2-balanced-actual-core-analysis',()=>{r2=sdk.analyzeWithOptions(old);assert.equal(r2.schemaVersion,2);assert.equal(r2.status,'violation');});
check('legacy-v2-capsule-replay',()=>{p2=evidence.makeCapsule(JSON.stringify(old),r2);assert.equal(JSON.parse(p2).format,'moontxnwitness-replay/v2');assert.equal(evidence.replayCapsule(p2).valid,true);});
check('capsule-generations-do-not-mix',()=>{assert.equal(sdk.replayCapsuleV3(p1).valid,false);assert.equal(sdk.replayCapsuleV3(p2).valid,false);assert.equal(evidence.replayCapsule(proof).valid,false);});
for(const name of ['read-before-rollback','read-after-rollback','released-child-parent-rollback','duplicate-name-reveal','repeated-rollback-target','cursor-position-survives'])check('downloaded-postgres-v3-'+name,()=>{const path=resolve(pg,'v3/postgres-ci',name),t=load(path+'.trace.json'),r=load(path+'.report.json');assert.equal(sdk.verifyV3(t,r).valid,true);const replay=sdk.replayCapsuleV3(readFileSync(path+'.capsule.json','utf8'));assert.equal(replay.valid,true);assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);assert.deepEqual(r.normalized.observations,t.events);assert.ok(r.coverage.gaps.some(g=>g.code==='unmapped_statement'));});
for(const name of ['rr','serial','mini'])check('downloaded-postgres-v2-'+name,()=>assert.equal(evidence.replayCapsule(readFileSync(resolve(pg,'releases/0.1.1/postgres',name+'.capsule.json'),'utf8')).valid,true));
writeFileSync(resolve(output,'v3-report.json'),JSON.stringify(report));writeFileSync(resolve(output,'v3-capsule.json'),proof);writeFileSync(resolve(output,'v1-capsule.json'),p1);writeFileSync(resolve(output,'v2-capsule.json'),p2);
function cli(name,args,code,predicate){check(name,()=>{const p=spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:base,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});const actual={args,exitCode:p.status,stdout:p.stdout,stderr:p.stderr,error:p.error?.name||null};writeFileSync(resolve(output,name+'.process.json'),JSON.stringify(actual,null,2));assert.equal(p.error,undefined);assert.equal(p.status,code,p.stderr);predicate(JSON.parse(p.stdout));});}
cli('cli-v3-ingest',['ingest-v3','fixtures/v3/write-skew-safe-projection.json'],0,r=>assert.equal(r.status,'ready'));
cli('cli-v3-analysis',['check-v3','fixtures/v3/write-skew-safe-projection.json'],1,r=>assert.equal(r.status,'violation'));
cli('cli-v3-verify',['verify-v3','fixtures/v3/write-skew-safe-projection.json','audit-output/v3-report.json'],0,r=>assert.equal(r.valid,true));
cli('cli-v3-replay',['replay-v3','audit-output/v3-capsule.json'],0,r=>assert.equal(r.valid,true));
cli('cli-v3-reduce',['reduce-v3','fixtures/v3/reduction-source-closure.json'],0,r=>assert.equal(r.oneMinimal,true));
cli('cli-v3-unknown',['check-v3','fixtures/v3/rollback-after-request-not-proof.json'],3,r=>assert.equal(r.status,'inconclusive'));
cli('cli-v3-invalid',['ingest-v3','fixtures/v3/wrong-schema.json'],2,r=>assert.equal(r.status,'invalid'));
cli('cli-v1-replay',['replay','audit-output/v1-capsule.json'],0,r=>assert.equal(r.valid,true));
cli('cli-v2-replay',['replay','audit-output/v2-capsule.json'],0,r=>assert.equal(r.valid,true));

const listDB=load(resolve(pg,'list-v3/postgres-ci/database-receipt.json'));
for(const c of listDB.cases)check('downloaded-list-'+c.name+'-'+c.round,()=>{
 const folder=resolve(pg,'list-v3/postgres-ci',c.directory),t=load(resolve(folder,'trace.json')),r=load(resolve(folder,'report.json'));
 assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(folder,'capsule.json'),'utf8')).valid,true);
 assert.equal(r.status,c.expectedModelStatus);assert.equal(r.modelDefinition.id,'append-list-serializable-v1');
});
const policy='dislock-f9946f0-sql-proof-1';
const sqlDB=load(resolve(pg,'business/dislock/v3-ci/model-receipt.json'));
for(const c of sqlDB.cases)check('downloaded-business-default-and-policy-'+c.name,()=>{
 const d=resolve(pg,'business/dislock/v3-ci',c.name),t=load(resolve(d,'capture.json')),r=load(resolve(d,'model-report.json')),s=load(resolve(d,'sql-proof-report.json'));
 assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(r.status,'inconclusive');assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'capsule.json'),'utf8')).valid,true);
 assert.equal(sdk.verifyV3(t,s).valid,true);assert.equal(s.status,c.explicitSqlPolicy.status);
 assert.deepEqual(sdk.normalizeCaptureV3(t,{sqlProof:policy}),s.normalized);
 assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'sql-proof-capsule.json'),'utf8')).valid,true);
});
check('downloaded-real-commit-40001-source-proof',()=>{
 const d=resolve(pg,'business/dislock/v3-commit-ci'),t=load(resolve(d,'capture.json')),r=load(resolve(d,'model-report.json'));
 assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(r.status,'inconclusive');assert.equal(r.normalized.transactions.filter(x=>x.status==='aborted').length,1);
 assert.equal(r.normalized.transactions.filter(x=>x.status==='unknown').length,0);assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'capsule.json'),'utf8')).valid,true);
});
check('explicit-sql-source-closure-reduction',()=>{
 const t=load('verification/v3/synthetic-dislock-source-closure-v1/trace.json'),r=sdk.reduceV3(t,{analysisOptions:{sqlProof:policy},maxChecks:256});
 assert.equal(r.status,'reduced');assert.equal(r.oneMinimal,true);assert.deepEqual(r.removed,['N']);assert.deepEqual(r.report.normalized.transactions.map(t=>t.id),['P','A','B']);
 assert.equal(sdk.verifyV3(r.reducedCapture,r.report).valid,true);
});
const sqlTrace=resolve(pg,'business/dislock/v3-ci/schedule-and-server-clock/capture.json');
cli('cli-explicit-sql-ingest',['ingest-v3',sqlTrace,'--sql-proof',policy],0,r=>assert.equal(r.status,'ready'));
cli('cli-explicit-sql-check',['check-v3',sqlTrace,'--sql-proof',policy],0,r=>assert.equal(r.status,'consistent'));
cli('cli-default-sql-stays-incomplete',['check-v3',sqlTrace],3,r=>assert.equal(r.status,'inconclusive'));
const listTrace=resolve(pg,'list-v3/postgres-ci/duplicate-business-values-00/trace.json');
cli('cli-append-list-check',['check-v3',listTrace],0,r=>assert.equal(r.status,'consistent'));


const relationDb=load(resolve(pg,'relation-v3/postgres-ci/database-receipt.json'));
for(const c of relationDb.scenarios)check('downloaded-relation-'+c.name+'-'+c.round,()=>{
 const d=resolve(pg,'relation-v3/postgres-ci',c.path),m=resolve(pg,'relation-v3/postgres-ci-model',c.path),t=load(resolve(d,'trace.json')),r=load(resolve(m,'report.json'));
 assert.equal(r.status,c.expectedVerdict);assert.equal(r.modelDefinition.id,'relation-set-serializable-v1');assert.equal(sdk.verifyV3(t,r).valid,true);
 assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(m,'capsule.json'),'utf8')).valid,true);assert.deepEqual(r.normalized.observations,t.events);
});
const relationTrace=resolve(pg,'relation-v3/postgres-ci/insert-phantom-01/trace.json');
check('relation-source-backed-reduction',()=>{const t=load(relationTrace),r=sdk.reduceV3(t,{maxChecks:256});assert.equal(r.oneMinimal,true);assert.equal(r.report.status,'violation');assert.equal(sdk.verifyV3(r.reducedCapture,r.report).valid,true);});
cli('cli-relation-violation',['check-v3',relationTrace],1,r=>assert.equal(r.modelDefinition.id,'relation-set-serializable-v1'));
cli('cli-relation-consistent',['check-v3',resolve(pg,'relation-v3/postgres-ci/empty-result-01/trace.json')],0,r=>assert.equal(r.status,'consistent'));
for(const label of ['before','fixed'])check('actual-fault-channel-'+label+'-cannot-certify-isolation-or-authenticity',()=>{
 const d=resolve(pg,'faults/mlflow/ci',label),t=load(resolve(d,'capture.json')),f=sdk.inspectExecutionFailuresV3(t),r=sdk.analyzeV3(t);
 assert.equal(f.valid,true);assert.equal(f.observedFaultCount,label==='before'?1:0);assert.equal(f.databaseAuthenticityVerified,false);assert.equal(f.certifiesFailureAbsence,false);assert.equal(f.modelViolationClaim,false);
 assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);assert.equal(sdk.replayCapsuleV3(sdk.makeCapsuleV3(t,r)).valid,true);
});
cli('cli-execution-fault-valid-input',['failures-v3',resolve(pg,'faults/mlflow/ci/before/capture.json')],0,r=>{assert.equal(r.valid,true);assert.equal(r.faults[0].kind,'deadlock');assert.equal(r.databaseAuthenticityVerified,false);assert.equal(r.captureCoverage.complete,false);});

const result={passed:cases.every(c=>c.passed),checks:cases.length,cases,node:process.version,platform:process.platform,localDatabaseExecution:false,localBuild:false,authorRuntimeOrCacheUsed:false};writeFileSync(resolve(output,'fresh-result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));if(!result.passed)process.exitCode=1;
