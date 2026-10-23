// New host checks only. Uses existing frozen compiled core; never builds or runs PG.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {sourceFingerprint} from './build-fingerprint.mjs';

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
  const bound=['core.mjs','capture-core.mjs','build-manifest.json','sdk.mjs','evidence.mjs','orm-profile.mjs','moontxnwitness.mjs'];
  receipt.runtime=Object.fromEntries(bound.map(name=>[name,hash(readFileSync(resolve(runtime,name)))]));
  const build=JSON.parse(readFileSync(resolve(runtime,'build-manifest.json'),'utf8'));
  receipt.build=build;
  assert.equal(receipt.runtime['core.mjs'],build.coreSha256);assert.equal(receipt.runtime['capture-core.mjs'],build.captureCoreSha256);
  assert.equal(sourceFingerprint(root),build.sourceSha256,'Frozen MoonBit sources must match this core; no rebuild is performed');
  receipt.hostSources=Object.fromEntries(['cmd/sdk.mjs','cmd/orm-profile.mjs','cmd/moontxnwitness.mjs','scripts/orm-profile-sdk-test.mjs','scripts/build.mjs','scripts/package_release.py'].map(name=>[name,hash(readFileSync(resolve(root,name)))]));
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
    sourceHash:r=>r.result.sourceBindings.traceSha256='0'.repeat(64),
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
  receipt.passed=receipt.checks.every(row=>row.passed);
}catch(error){receipt.error=String(error.stack||error);}
save('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,checks:receipt.checks.length,failures:receipt.checks.filter(row=>!row.passed),error:receipt.error??null,output},null,2));
if(!receipt.passed)process.exitCode=1;
