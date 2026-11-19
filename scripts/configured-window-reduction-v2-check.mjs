// Recompute selection proofs from original captured windows, never report facts.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
const pending=process.argv.slice(2),args={};
while(pending.length){
  const arg=pending.shift(),at=arg.indexOf('=');assert(arg.startsWith('--'));
  const name=arg.slice(2,at>2?at:undefined),value=at>2?arg.slice(at+1):pending.shift();
  assert(['core','receipt','output'].includes(name)&&value&&!value.startsWith('--')&&!Object.hasOwn(args,name),'Invalid or duplicate option');args[name]=value;
}
for(const name of ['core','receipt','output'])assert(args[name],'Missing --'+name);
const hash=value=>createHash('sha256').update(value).digest('hex'),clone=structuredClone;
const coreBytes=readFileSync(args.core),receiptBytes=readFileSync(args.receipt),campaign=JSON.parse(receiptBytes);
assert.equal(campaign.passed,true);assert.equal(campaign.actualDatabaseExecution,true);
const output=resolve(args.output);mkdirSync(dirname(output),{recursive:true});
const corePath=resolve(dirname(output),'checked-core.mjs');writeFileSync(corePath,coreBytes,{flag:'wx'});
const core=await import(pathToFileURL(corePath).href),checks=[];
function check(name,body){try{body();checks.push({name,passed:true});}catch(error){checks.push({name,passed:false,error:error.message});}}
const fixtureResults=[];
for(const layout of campaign.records)for(const fixture of layout.analysisFixtures){
  const options={preserveModel:'serializable',windowOptions:fixture.analysisOptions};
  const id=layout.keyType+'/'+fixture.name,bundle=readFileSync(fixture.bundle,'utf8');
  assert.equal(hash(bundle),fixture.bundleSha256,'Original fixture changed');
  const config=JSON.stringify(fixture.config),policy=JSON.stringify(fixture.policy);
  const run=selected=>JSON.parse(core.reduce_configured_window_v2_json(config,policy,bundle,JSON.stringify(selected)));
  const verify=(report,selected=options,original=bundle)=>JSON.parse(core.verify_configured_window_reduction_v2_json(config,policy,original,JSON.stringify(report),JSON.stringify(selected)));
  const report=run(options),verified=verify(report),closed=fixture.expected!=='unknown',refuted=fixture.expected==='refuted';
  const selected=report.reduction?.selectedTransactions?.length;
  fixtureResults.push({keyType:layout.keyType,name:fixture.name,status:report.status,windowVerified:report.windowVerified,
    refutationPreserved:report.refutationPreserved,oneMinimal:report.oneMinimal,selectedTransactions:selected??null});
  check(id+'/original-window-and-target',()=>{
    assert.equal(report.windowVerified,closed);assert.equal(report.refutationPreserved,refuted);assert.equal(report.oneMinimal,refuted);
    assert.equal(report.sourceAuthenticated,false);assert.equal(report.originalWindowRetained,true);
    assert.equal(report.bundleSha256,fixture.bundleSha256);
    assert.equal(verified.reportMatches,true);assert.equal(verified.valid,closed);
    assert.equal(verified.refutationVerified,refuted);assert.equal(verified.oneMinimalVerified,refuted);
    if(!closed){assert.equal(report.status,'unknown');assert.equal(report.reduction,null);}
  });
  if(closed){
    check(id+'/original-history-and-selected-event-provenance',()=>{
      const reduced=report.reduction,history=report.window.history;
      assert.deepEqual(reduced.originalFacts.history,history);
      const originals=new Map(history.events.map(event=>[event.seq,event]));
      assert.deepEqual(reduced.selectedOriginalEvents,reduced.originalEventSequence.map(seq=>originals.get(seq)));
      const dense=reduced.analysisView.history.events;
      assert.equal(dense.length,reduced.originalEventSequence.length);
      for(let index=0;index<dense.length;index++){
        const original=originals.get(reduced.originalEventSequence[index]);assert(original);
        assert.equal(original.kind,dense[index].kind);assert.equal(original.tx,dense[index].tx);
      }
    });
    check(id+'/actual-size-and-model-refutation',()=>{
      const original=report.window.history.events.filter(event=>event.kind==='begin').length;
      if(fixture.originalTransactions!==undefined)assert.equal(original,fixture.originalTransactions);
      if(fixture.expectedReducedTransactions!==undefined)assert.equal(selected,fixture.expectedReducedTransactions);
      if(refuted){assert.equal(report.reduction.classification.status,'refuted');assert.equal(report.reduction.initialClassification.status,'refuted');assert.equal(report.status,selected<original?'reduced':'unchanged');}
      else{assert.equal(report.status,'not-refuted');}
    });
    if(fixture.expectedReducedTransactions!==undefined)check(id+'/source-dependent-candidate-is-not-accepted',()=>{
      assert(report.reduction.execution.candidateAudit.some(candidate=>candidate.sourceClosed===false&&candidate.accepted===false),
        'A candidate deleting an observed writer must retain its source gap');
    });
    check(id+'/changed-event-mapping-is-refused',()=>{
      const changed=clone(report);changed.reduction.originalEventSequence[0]=999999;assert.equal(verify(changed).valid,false);
    });
  }
  for(const [name,change] of [
    ['one-minimal',r=>{r.oneMinimal=!r.oneMinimal;}],
    ['target-model',r=>{r.preserveModel='read-committed';}],
    ['source-binding',r=>{r.bundleSha256='0'.repeat(64);}],
  ])check(id+'/report-tamper-'+name,()=>{const changed=clone(report);change(changed);assert.equal(verify(changed).valid,false);});
  check(id+'/independent-budget-change-is-refused',()=>assert.equal(verify(report,{...options,reductionOptions:{maxChecks:0}}).valid,false));
  check(id+'/original-byte-change-is-refused',()=>assert.equal(verify(report,options,bundle+'\n').valid,false));
  check(id+'/zero-window-budget-never-authorizes-selection',()=>{
    const limited=run({...options,windowOptions:{...options.windowOptions,maxPointChecks:0}});assert.equal(limited.status,'unknown');assert.equal(limited.windowVerified,false);assert.equal(limited.oneMinimal,false);
  });
  if(refuted){
    check(id+'/unfinished-candidates-never-one-minimal',()=>{
      const selected={...options,reductionOptions:{maxChecks:0}},limited=run(selected),v=verify(limited,selected);
      assert.equal(limited.status,'budget');assert.equal(limited.oneMinimal,false);assert.equal(v.oneMinimalVerified,false);assert.equal(v.reportMatches,true);
    });
    check(id+'/model-budget-never-authorizes-one-minimal',()=>{
      const limited=run({...options,reductionOptions:{modelOptions:{maxSourceChecks:0}}});assert.equal(limited.oneMinimal,false);assert.equal(limited.refutationPreserved,false);
    });
  }
  check(id+'/original-input-unchanged',()=>assert.equal(hash(readFileSync(fixture.bundle)),fixture.bundleSha256));
}
assert.equal(hash(readFileSync(args.receipt)),hash(receiptBytes));
const failures=checks.filter(item=>!item.passed);
const result={format:'moontxnwitness-configured-window-reduction-check/v1',passed:failures.length===0,
  actualDatabaseExecution:false,originalReceiptActualDatabaseExecution:true,coreSha256:hash(coreBytes),
  originalReceiptSha256:hash(receiptBytes),fixtureCount:fixtureResults.length,checkCount:checks.length,
  failedChecks:failures.length,fixtures:fixtureResults,checks};
writeFileSync(output,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:result.passed,checks:checks.length,failed:failures.length,output}));
for(const item of failures)console.error(item.name+': '+item.error);
if(failures.length)process.exitCode=1;
