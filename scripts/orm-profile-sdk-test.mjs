// New host checks only. Uses existing frozen compiled core; never builds or runs PG.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,copyFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {sourceFingerprint} from './build-fingerprint.mjs';
import {syntheticNonrepeatableProfile} from './orm-profile-synthetic.mjs';

const defaults=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2),options={};
for(let i=0;i<args.length;i+=2){assert.ok(['--repository','--runtime','--output-root'].includes(args[i]));assert.ok(args[i+1]);assert.equal(options[args[i]],undefined);options[args[i]]=resolve(args[i+1]);}
const root=options['--repository']||defaults,runtime=options['--runtime']||resolve(root,'dist');
const outputRoot=options['--output-root']||resolve(root,'artifacts/orm-profile-sdk');mkdirSync(outputRoot,{recursive:true});
const output=mkdtempSync(resolve(outputRoot,'run-'));
const hash=text=>createHash('sha256').update(text).digest('hex');
const canonical=value=>JSON.stringify(value,null,2)+'\n';
const clone=value=>structuredClone(value);
const save=(name,value)=>writeFileSync(resolve(output,name),typeof value==='string'?value:canonical(value),{flag:'wx'});
const receipt={schema:1,kind:'configured-orm-profile-host-tests',passed:false,actualDatabaseExecution:false,
  formalPerformanceMeasurement:false,independentOfImplementation:false,originalIndependent54Reexecuted:false,
  positiveAnomalousProfileReductionExecuted:false,checks:[]};
const check=(name,fn)=>{try{fn();receipt.checks.push({name,passed:true});}catch(error){receipt.checks.push({name,passed:false,error:error.message});}};
try{
  const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
  const bound=['core.mjs','capture-core.mjs','build-manifest.json','sdk.mjs','evidence.mjs','orm-profile.mjs','legacy-v024.mjs','legacy-v025.mjs','legacy-v025-runtime.mjs','legacy-v025-worker.mjs','legacy-v025-binding.mjs','legacy-v026.mjs','legacy-v026-runtime.mjs','legacy-v026-worker.mjs','legacy-v026-binding.mjs','moontxnwitness.mjs'];
  receipt.runtime=Object.fromEntries(bound.map(name=>[name,hash(readFileSync(resolve(runtime,name)))]));
  const build=JSON.parse(readFileSync(resolve(runtime,'build-manifest.json'),'utf8'));
  receipt.build=build;
  assert.equal(receipt.runtime['core.mjs'],build.coreSha256);assert.equal(receipt.runtime['capture-core.mjs'],build.captureCoreSha256);
  assert.equal(sourceFingerprint(root),build.sourceSha256,'Frozen MoonBit sources must match this core; no rebuild is performed');
  receipt.hostSources=Object.fromEntries(['cmd/sdk.mjs','cmd/orm-profile.mjs','cmd/moontxnwitness.mjs','scripts/orm-profile-sdk-test.mjs','scripts/orm-profile-synthetic.mjs','scripts/build.mjs','scripts/package_release.py'].map(name=>[name,hash(readFileSync(resolve(root,name)))]));
  const inputs=['producer-first','producer-second'].map(name=>readFileSync(resolve(root,'verification/configured-user-profile/v024-initial',name,'profile-source.json'),'utf8'));
  receipt.sourcePackets=inputs.map(hash);
  const reports=[],capsules=[];
  for(const [i,input] of inputs.entries()){
    check(`actual-packet-${i+1}-configured-mapping-with-raw-gaps-retained`,()=>{
      const report=sdk.analyzeOrmProfileV3(input);reports.push(report);
      assert.equal(report.analysisCoverageAccepted,true);assert.equal(report.status,'consistent');
      assert.equal(report.result.originalDiagnosticCoverage.complete,false);
      assert.equal(report.result.originalSourceProof.analysisCoverageAccepted,false);assert.equal(report.result.originalSourceProof.history,null);
      assert.equal(JSON.parse(JSON.parse(input).journalIndexText).sourceClosed,false);
      assert.equal(report.sourceBindings.envelopeSha256,hash(input));
      for(const key of ['trace','sourceJournal','lifecycle','journalIndex'])assert.equal(report.sourceBindings[key+'Sha256'],hash(JSON.parse(input)[key+'Text']));
      save(`packet-${i+1}.report.json`,canonical(report));
    });
    check(`actual-packet-${i+1}-old-source2-diagnostic-unchanged`,()=>{
      const source=JSON.parse(input);
      const legacy=sdk.inspectOrmSourceV3({schema:2,profile:source.profile,traceText:source.traceText,sourceJournalText:source.sourceJournalText});
      assert.deepEqual(legacy,reports[i].result.originalSourceProof);
    });
    check(`actual-packet-${i+1}-exact-report-verification`,()=>{
      assert.equal(sdk.verifyOrmProfileV3(input,reports[i]).valid,true);
      assert.equal(sdk.verifyOrmProfileV3(input,canonical(reports[i])).valid,true);
    });
    check(`actual-packet-${i+1}-canonical-capsule-roundtrip`,()=>{
      const capsule=sdk.makeOrmProfileCapsuleV3(input);capsules.push(capsule);
      const replay=sdk.replayOrmProfileCapsuleV3(capsule);
      assert.equal(replay.valid,true);assert.equal(replay.envelopeText,input);
      assert.deepEqual(replay.report,reports[i]);save(`packet-${i+1}.capsule.json`,capsule);
    });
    check(`actual-packet-${i+1}-consistent-history-is-not-fabricated-reduction`,()=>{
      const reduction=sdk.reduceOrmProfileV3(input,{maxChecks:0});
      assert.equal(reduction.status,'skipped');assert.equal(reduction.result.reduction,null);
      assert.equal(reduction.result.originalEnvelopeText,input);
      assert.equal(sdk.verifyOrmProfileV3(input,reduction).valid,true);
      const replay=sdk.replayOrmProfileCapsuleV3(sdk.makeOrmProfileReductionCapsuleV3(input,{maxChecks:0}));
      assert.equal(replay.valid,true);assert.equal(replay.status,'skipped');assert.equal(replay.envelopeText,input);
    });
  }
  assert.equal(reports.length,2);assert.equal(capsules.length,2);
  const base=JSON.parse(capsules[0]);
  const changes={format:c=>c.format='moontxnwitness-replay/v3',engine:c=>c.engineVersion='99.0.0',
    algorithm:c=>c.algorithm='unknown',sourceAlgorithm:c=>c.sourceAlgorithm='unknown',operation:c=>c.operation='unknown',
    options:c=>c.requestOptionsText='{"maxAttempts":0}',optionsSha:c=>c.requestOptionsSha256='0'.repeat(64),
    sourceSha:c=>c.sourceBindings.traceSha256='0'.repeat(64),envelopeSha:c=>c.sourceBindings.envelopeSha256='0'.repeat(64),
    reportSha:c=>c.reportSha256='0'.repeat(64),budget:c=>c.budgets.exactSearchTransactions=1000,
    extra:c=>c.completeApplicationAccepted=true,missing:c=>delete c.sourceBindings,
    rawText:c=>c.envelopeText+='\n'};
  for(const [name,edit] of Object.entries(changes))check('capsule-header-or-source-tamper-'+name,()=>{
    const changed=clone(base);edit(changed);assert.equal(sdk.replayOrmProfileCapsuleV3(canonical(changed)).valid,false);
  });
  const resultChanges={conclusion:r=>r.status='violation',coverage:r=>r.analysisCoverageAccepted=false,
    rawCoverage:r=>r.result.originalDiagnosticCoverage.complete=true,
    sourceHash:r=>r.result.sourceBindings.traceSha256='0'.repeat(64),originalSeq:r=>r.result.retainedOriginalSeq[0]=999999,
    budget:r=>r.budgets.exactSearchTransactions++,options:r=>r.requestOptionsText='{"maxAttempts":0}',
    engine:r=>r.engineVersion='99.0.0',algorithm:r=>r.algorithm='unknown',extra:r=>r.realDatabaseVerified=true};
  for(const [name,edit] of Object.entries(resultChanges))check('rehashed-report-tamper-'+name,()=>{
    const changed=clone(base),report=JSON.parse(changed.reportText);edit(report);
    changed.reportText=JSON.stringify(report);changed.reportSha256=hash(changed.reportText);
    assert.equal(sdk.replayOrmProfileCapsuleV3(canonical(changed)).valid,false);
    assert.equal(sdk.verifyOrmProfileV3(inputs[0],report,{}).valid,false);
  });
  check('explicit-options-and-request-bind-without-changing-business-version',()=>{
    const report=sdk.analyzeOrmProfileV3(inputs[0],{maxAttempts:0});
    assert.equal(report.requestOptionsText,'{"maxAttempts":0}');
    assert.equal(sdk.verifyOrmProfileV3(inputs[0],report,{maxAttempts:1}).valid,false);
    assert.equal(sdk.verifyOrmProfileV3(inputs[0],report,{maxAttempts:0}).valid,true);
  });
  check('rehash-changed-options-and-original-capture-cannot-reuse-old-report',()=>{
    const changed=clone(base);changed.requestOptionsText='{"maxAttempts":0}';changed.requestOptionsSha256=hash(changed.requestOptionsText);
    assert.equal(sdk.replayOrmProfileCapsuleV3(canonical(changed)).valid,false);
    const capture=clone(base),envelope=JSON.parse(capture.envelopeText),trace=JSON.parse(envelope.traceText);
    trace.events.find(event=>event.kind==='rows'&&event.rows.length).rows[0][1]='forged@example.invalid';
    envelope.traceText=JSON.stringify(trace);capture.envelopeText=JSON.stringify(envelope);
    capture.sourceBindings.envelopeSha256=hash(capture.envelopeText);capture.sourceBindings.traceSha256=hash(envelope.traceText);
    assert.equal(sdk.replayOrmProfileCapsuleV3(canonical(capture)).valid,false);
  });
  check('duplicate-envelope-field-and-trailing-data-rejected',()=>{
    assert.equal(sdk.replayOrmProfileCapsuleV3(capsules[0].replace(/\n}\n$/,'\n,"operation":"analyze"}\n')).valid,false);
    assert.equal(sdk.replayOrmProfileCapsuleV3(capsules[0]+' ').valid,false);
  });
  check('unsupported-budget-options-and-malformed-unicode-rejected',()=>{
    for(const value of [{maxAttempts:100001},{maxOperationChecks:-1},{maxCachedStates:1.2},{unknown:1},null,[]])assert.throws(()=>sdk.analyzeOrmProfileV3(inputs[0],value));
    assert.throws(()=>sdk.reduceOrmProfileV3(inputs[0],{maxChecks:257}));
    assert.throws(()=>sdk.analyzeOrmProfileV3('\ud800'));
  });
  check('engine-looking-json-business-value-stays-verbatim-in-inconclusive-capsule',()=>{
    const source=JSON.parse(inputs[0]);source.businessValue={version:'0.2.0',decimal:1.25,text:'吴芳芳\\n/😀'};
    const text=JSON.stringify(source),capsule=sdk.makeOrmProfileCapsuleV3(text),replay=sdk.replayOrmProfileCapsuleV3(capsule);
    assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');assert.equal(replay.envelopeText,text);
    assert.equal(JSON.parse(replay.envelopeText).businessValue.version,'0.2.0');
    assert.equal(sdk.reduceOrmProfileV3(text).result.reduction,null);
  });
  check('actual-earlier-unknown-commit-remains-unknown-with-unmatched-profile-source',()=>{
    const source=JSON.parse(inputs[0]),where=resolve(root,'verification/capture-persistence/v023-initial/postgres-cases/lost-commit-sync');
    source.traceText=readFileSync(resolve(where,'trace.json'),'utf8');
    source.lifecycleText=readFileSync(resolve(where,'lifecycle.jsonl'),'utf8');source.journalIndexText=readFileSync(resolve(where,'journal-index.json'),'utf8');
    const text=JSON.stringify(source),replay=sdk.replayOrmProfileCapsuleV3(sdk.makeOrmProfileCapsuleV3(text));
    assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');assert.equal(replay.analysisCoverageAccepted,false);
    assert.equal(JSON.parse(replay.envelopeText).traceText,source.traceText);
    assert.ok(sdk.inspectExecutionFailuresV3(source.traceText).transactionOutcomes.some(tx=>tx.status==='unknown'));
  });
  const synthetic=readFileSync(resolve(root,'fixtures/orm-profile-v3/synthetic-nonrepeatable-first/profile-source.json'),'utf8');
  let syntheticReduction;
  check('frozen-synthetic-wire-derivation-is-explicitly-not-a-real-pg-anomaly',()=>{
    const baseFolder=resolve(root,'verification/configured-user-profile/v024-initial/producer-first/profile/capture/journal');
    const generated=syntheticNonrepeatableProfile(inputs[0],readFileSync(resolve(baseFolder,'segment-000001.jsonl'),'utf8'));
    assert.equal(generated.envelopeText,synthetic);assert.equal(generated.manifest.actualPostgresAnomaly,false);
    assert.equal(generated.segmentText,readFileSync(resolve(root,'fixtures/orm-profile-v3/synthetic-nonrepeatable-first/segment-000001.jsonl'),'utf8'));
    const result=sdk.analyzeOrmProfileV3(synthetic);assert.equal(result.analysisCoverageAccepted,true);assert.equal(result.status,'violation');assert.equal(result.result.analysis.complete,true);
    const history=result.result.history,committed=history.transactions.filter(tx=>tx.status==='committed');
    const accepts=(remaining,state)=>remaining.length===0||remaining.some((tx,i)=>{
      const next={...state};for(const op of tx.ops){if(op.type==='read'&&next[op.key]!==op.version)return false;if(op.type==='write')next[op.key]=op.version;}
      return accepts(remaining.filter((_,j)=>i!==j),next);
    });
    assert.equal(accepts(committed,history.initial),false,'Independent serial interpreter must reject all committed orders');
  });
  check('synthetic-positive-reduction-restores-read-and-chain-source-closure',()=>{
    const report=sdk.reduceOrmProfileV3(synthetic);syntheticReduction=report;
    assert.equal(report.status,'reduced');assert.equal(report.result.originalEnvelopeText,synthetic);
    const reduced=report.result.reduction,original=report.result.originalReport.history;
    assert.equal(reduced.sourceClosure.complete,true);assert.ok(reduced.sourceClosure.restoration.required.length>0);
    assert.equal(reduced.sourceClosure.restoration.checked,true);assert.equal(reduced.sourceClosure.restoration.accepted,true);
    assert.equal(reduced.reducedHistory.transactions.length,3);assert.equal(original.transactions.length,4);
    assert.equal(reduced.report.complete,true);assert.equal(reduced.report.status,'violation');
    assert.equal(reduced.oneMinimal,true);assert.equal(reduced.sourceClosure.allRemainingSingleDeletesChecked,true);
    assert.equal(reduced.checks,reduced.genericAttempt.checks+1+reduced.sourceClosure.singleDeletionChecks.length);
    assert.equal(reduced.semanticCandidateChecks,reduced.checks);
    assert.equal(reduced.cachedCandidateLookups,reduced.genericAttempt.cachedCandidateChecks);
    assert.equal(reduced.candidateAttempts,reduced.semanticCandidateChecks+reduced.cachedCandidateLookups);
    assert.ok(reduced.checks<=256);assert.ok(reduced.sourceClosure.singleDeletionChecks.some(row=>row.reason==='missing-source'&&row.status==='unknown'));
    assert.equal(report.result.finalReplay.valid,true);assert.equal(report.result.finalReanalysis.complete,true);
    assert.deepEqual(reduced.reducedHistory.initial,original.initial);
    for(const tx of reduced.reducedHistory.transactions)assert.deepEqual(tx,original.transactions.find(row=>row.id===tx.id));
    for(const [key,chain] of Object.entries(reduced.reducedHistory.versionOrders))assert.deepEqual(chain,original.versionOrders[key].filter(version=>chain.includes(version)));
    const versions=new Set(Object.entries(reduced.reducedHistory.initial).map(([key,value])=>JSON.stringify([key,value])));
    for(const tx of reduced.reducedHistory.transactions)for(const op of tx.ops)if(op.type==='write')versions.add(JSON.stringify([op.key,op.version]));
    for(const tx of reduced.reducedHistory.transactions)for(const op of tx.ops)if(op.type==='read')assert.ok(versions.has(JSON.stringify([op.key,op.version])));
    assert.equal(reduced.sourcePromotionPasses,2);save('synthetic-closed-reduction.json',canonical(report));
    assert.deepEqual(reduced.verificationPasses,{inputSourcePromotions:1,genericCalls:1,finalSourcePromotions:1,finalCandidateAnalyses:1,finalReportReplays:1});
    receipt.positiveAnomalousProfileReductionExecuted=true;
  });
  check('synthetic-positive-reduction-capsule-and-resealed-fact-tampering',()=>{
    const capsule=sdk.makeOrmProfileReductionCapsuleV3(synthetic),replay=sdk.replayOrmProfileCapsuleV3(capsule);
    assert.equal(replay.valid,true);assert.deepEqual(replay.report,syntheticReduction);save('synthetic-closed-reduction.capsule.json',capsule);
    for(const edit of [r=>r.result.originalEnvelopeText+='\n',r=>r.result.reduction.sourceClosure.complete=false,
      r=>r.result.reduction.reducedHistory.initial[Object.keys(r.result.reduction.reducedHistory.initial)[0]]='fabricated',
      r=>r.result.reduction.checks--,r=>r.result.reduction.oneMinimal=false,r=>r.result.retainedOriginalSeq[0]=999999]){
      const changed=JSON.parse(capsule),report=JSON.parse(changed.reportText);edit(report);changed.reportText=JSON.stringify(report);changed.reportSha256=hash(changed.reportText);
      assert.equal(sdk.replayOrmProfileCapsuleV3(canonical(changed)).valid,false);
    }
  });
  check('synthetic-budget-exhaustion-keeps-original-source-closed-facts-without-minimality',()=>{
    const result=sdk.reduceOrmProfileV3(synthetic,{maxChecks:0});
    assert.equal(result.status,'budget');assert.equal(result.result.reduction.checks,0);assert.equal(result.result.reduction.oneMinimal,false);
    assert.equal(result.result.reduction.sourceClosure.complete,true);assert.equal(result.result.finalReplay,null);
    assert.equal(result.result.finalReanalysis,null);assert.equal(result.result.reduction.genericAttempt,null);
    assert.equal(result.result.reduction.sourcePromotionPasses,1);
    assert.equal(result.result.reduction.semanticCandidateChecks,0);assert.equal(result.result.reduction.cachedCandidateLookups,0);
    assert.equal(result.result.reduction.candidateAttempts,0);
    assert.deepEqual(result.result.verificationPasses,{inputSourcePromotions:1,genericCalls:0,finalSourcePromotions:0,finalCandidateAnalyses:0,finalReportReplays:0});
    assert.deepEqual(result.result.reduction.reducedHistory,result.result.originalReport.history);
  });
  // Scoped tracing delegates to the identical compiled core, with no fake result.
  // It verifies exported host call dispatch, not hidden implementation counters.
  const traced=resolve(output,'zero-budget-call-control');mkdirSync(traced);
  copyFileSync(resolve(runtime,'core.mjs'),resolve(traced,'real-core.mjs'));
  copyFileSync(resolve(runtime,'orm-profile.mjs'),resolve(traced,'orm-profile.mjs'));
  copyFileSync(resolve(runtime,'legacy-v024.mjs'),resolve(traced,'legacy-v024.mjs'));
  for(const name of ['legacy-v025.mjs','legacy-v025-runtime.mjs','legacy-v025-worker.mjs','legacy-v025-binding.mjs','legacy-v026.mjs','legacy-v026-runtime.mjs','legacy-v026-worker.mjs','legacy-v026-binding.mjs'])copyFileSync(resolve(runtime,name),resolve(traced,name));
  writeFileSync(resolve(traced,'core.mjs'),"import * as real from './real-core.mjs';\nexport const calls=[];\nexport const version=real.version;\n"+
    ['orm_profile_source_v3_json','shrink_options_json','analyze_options_json','replay_report_json'].map(name=>`export function ${name}(...args){calls.push('${name}');return real.${name}(...args);}\n`).join(''),{flag:'wx'});
  const tracedSdk=await import(pathToFileURL(resolve(traced,'orm-profile.mjs')).href);
  const tracedCalls=await import(pathToFileURL(resolve(traced,'core.mjs')).href);
  check('zero-budget-invokes-only-real-core-input-promotion-at-host-boundary',()=>{
    assert.equal(hash(readFileSync(resolve(traced,'real-core.mjs'))),receipt.runtime['core.mjs']);
    assert.equal(hash(readFileSync(resolve(traced,'legacy-v024.mjs'))),receipt.runtime['legacy-v024.mjs']);
    for(const name of ['legacy-v025.mjs','legacy-v025-runtime.mjs','legacy-v025-worker.mjs','legacy-v025-binding.mjs','legacy-v026.mjs','legacy-v026-runtime.mjs','legacy-v026-worker.mjs','legacy-v026-binding.mjs'])assert.equal(hash(readFileSync(resolve(traced,name))),receipt.runtime[name]);
    assert.equal(tracedSdk.reduceOrmProfileV3(synthetic,{maxChecks:0}).status,'budget');
    assert.deepEqual(tracedCalls.calls,['orm_profile_source_v3_json']);
    save('zero-budget-host-call-control.json',{scope:'Scoped dispatch tracing to byte-identical real compiled core; no fake semantic output',calls:tracedCalls.calls,realCoreSha256:receipt.runtime['core.mjs']});
  });
  const cli=(args,input)=>spawnSync(process.execPath,[resolve(runtime,'moontxnwitness.mjs'),...args],{encoding:'utf8',input,windowsHide:true,maxBuffer:16*1024*1024});
  const inputFile=resolve(output,'original-source.json');save('original-source.json',inputs[0]);
  check('cli-analysis-capsule-and-replay',()=>{
    const report=resolve(output,'cli-report.json'),capsule=resolve(output,'cli-capsule.json');
    const child=cli(['orm-profile-v3',inputFile,'--output',report,'--capsule',capsule]);assert.equal(child.status,0,child.stderr);
    assert.equal(JSON.parse(readFileSync(report,'utf8')).analysisCoverageAccepted,true);
    assert.equal(cli(['replay-orm-profile-v3',capsule,'--output',resolve(output,'cli-replay.json')]).status,0);
    assert.equal(cli(['verify-orm-profile-v3',inputFile,report]).status,0);
  });
  check('cli-reduction-keeps-consistent-original-and-partial-outcome',()=>{
    const out=resolve(output,'cli-reduction.json'),capsule=resolve(output,'cli-reduction-capsule.json');
    const child=cli(['shrink-orm-profile-v3',inputFile,'--max-checks','0','--output',out,'--capsule',capsule]);assert.equal(child.status,3,child.stderr);
    const report=JSON.parse(readFileSync(out,'utf8'));assert.equal(report.result.originalEnvelopeText,inputs[0]);assert.equal(report.result.reduction,null);
    assert.equal(sdk.replayOrmProfileCapsuleV3(readFileSync(capsule,'utf8')).valid,true);
  });
  check('cli-safe-output-refusals-do-not-overwrite-input-or-existing-report',()=>{
    const before=hash(readFileSync(inputFile));const child=cli(['orm-profile-v3',inputFile,'--output',inputFile]);assert.equal(child.status,2);
    assert.equal(hash(readFileSync(inputFile)),before);
    const target=resolve(output,'cli-report.json'),prior=hash(readFileSync(target));
    assert.equal(cli(['orm-profile-v3',inputFile,'--output',target]).status,2);assert.equal(hash(readFileSync(target)),prior);
    assert.equal(cli(['shrink-orm-profile-v3',inputFile,'--max-checks','257']).status,2);
    assert.equal(cli(['shrink-orm-profile-v3',inputFile,'--history',resolve(output,'nonexistent-mini.json')]).status,2);
  });
  check('cli-stdin-source-is-bounded-and-retained',()=>{const child=cli(['orm-profile-v3','-'],inputs[0]);assert.equal(child.status,0,child.stderr);assert.equal(JSON.parse(child.stdout).sourceBindings.envelopeSha256,hash(inputs[0]));});
  check('cli-synthetic-positive-shrink-exports-original-subsequence-and-replay',()=>{
    const source=resolve(root,'fixtures/orm-profile-v3/synthetic-nonrepeatable-first/profile-source.json'),mini=resolve(output,'synthetic-cli-mini.json'),capsule=resolve(output,'synthetic-cli.capsule.json');
    const child=cli(['shrink-orm-profile-v3',source,'--history',mini,'--capsule',capsule,'--output',resolve(output,'synthetic-cli-report.json')]);
    assert.equal(child.status,0,child.stderr);assert.equal(JSON.parse(readFileSync(mini,'utf8')).transactions.length,3);
    assert.equal(cli(['replay-orm-profile-v3',capsule,'--output',resolve(output,'synthetic-cli-replay.json')]).status,0);
  });
  receipt.passed=receipt.checks.every(row=>row.passed);
}catch(error){receipt.error=String(error.stack||error);}
save('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,checks:receipt.checks.length,failures:receipt.checks.filter(row=>!row.passed),error:receipt.error??null,output},null,2));
if(!receipt.passed)process.exitCode=1;
