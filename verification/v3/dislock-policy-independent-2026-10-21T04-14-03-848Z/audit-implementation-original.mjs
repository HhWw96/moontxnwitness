// Independent explicit-policy integration acceptance. No build/database/fixtures edits.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {sourceFingerprint} from '../../../scripts/build-fingerprint.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const planPath='verification/v3/dislock-explicit-policy-preregistration-2026-10-21.json';
const hash=b=>createHash('sha256').update(b).digest('hex');
const load=p=>JSON.parse(readFileSync(resolve(root,p),'utf8'));
const copy=o=>JSON.parse(JSON.stringify(o));
const binding=p=>{const b=readFileSync(resolve(root,p));return{sha256:hash(b),bytes:b.length};};
const plan=load(planPath),policy=plan.strategy.value;
const output=resolve(root,'verification/v3','dislock-policy-independent-'+new Date().toISOString().replace(/[:.]/g,'-'));
mkdirSync(output,{recursive:false});
const retain=(name,value)=>{const b=typeof value==='string'?value:JSON.stringify(value,null,2)+'\n';writeFileSync(resolve(output,name),b,{flag:'wx'});return{path:relative(root,resolve(output,name)).replaceAll('\\','/'),sha256:hash(b),bytes:Buffer.byteLength(b)};};
const build=load('dist/build-manifest.json');
const receipt={schema:1,scope:'Explicit fixed SQL policy integration, not database authenticity or full application adoption',actualDatabaseExecution:false,passed:false,plan:{path:planPath,...binding(planPath)},build,sourceSha256:sourceFingerprint(root),implementation:binding('verification/v3/tools/dislock_explicit_policy_audit.mjs'),checks:[],failures:[],cases:[],tamper:[]};
const check=(name,fn)=>{try{fn();receipt.checks.push({name,passed:true});}catch(error){const message=String(error.message).replaceAll(root,'<workspace>');receipt.checks.push({name,passed:false,error:message});receipt.failures.push({name,error:message});}};
const replaySafe=(sdk,text)=>{try{return sdk.replayCapsuleV3(text);}catch(error){return{valid:false,errorClass:error.name};}};
const badOptions=[{sqlProof:'unknown-policy'},{sqlProof:true},{sqlProof:1},{sqlProof:null},{sqlProof:{}},{sqlProof:[policy]}];
const reportTamper=[
  ['strategy-removed',r=>{delete r.execution.analysisOptions.sqlProof;}],
  ['strategy-unknown',r=>{r.execution.analysisOptions.sqlProof='unknown-policy';}],
  ['strategy-wrong-type',r=>{r.execution.analysisOptions.sqlProof=true;}],
  ['conclusion-changed',r=>{r.status='violation';}],
  ['model-changed',r=>{r.modelDefinition.id='append-list-serializable-v1';}],
  ['effective-budget-changed',r=>{const k=Object.keys(r.execution.effectiveLimits).find(k=>typeof r.execution.effectiveLimits[k]==='number');assert.ok(k,'A numeric effective limit must be recorded');r.execution.effectiveLimits[k]+=1;}],
  ['normal-source-version-changed',r=>{const w=r.normalized.observations.find(e=>e.kind==='write');w.version='unobserved-source';}],
  ['normal-model-source-changed',r=>{const w=r.normalized.effects[0];w.predecessor='unobserved-source';}],
  ['evidence-conclusion-changed',r=>{r.evidence.status='violation';}],
];
retain('frozen-execution-plan.json',{...receipt,executionStarted:false,reportMutations:reportTamper.map(([name])=>name),badOptions,expectedCases:plan.expectations,stage:'Expectations and input SHAs loaded before SDK import; no post-output adjustment.'});
try{
  assert.equal(build.sourceSha256,receipt.sourceSha256,'Build must match current source');
  for(const [file,key]of[['core.mjs','coreSha256'],['capture-core.mjs','captureCoreSha256']])assert.equal(binding('dist/'+file).sha256,build[key]);
  for(const file of['sdk.mjs','evidence.mjs','moontxnwitness.mjs'])assert.equal(binding('dist/'+file).sha256,binding('cmd/'+file).sha256);
  const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
  for(const [name,expected]of Object.entries(plan.expectations)){
    const inputPath=plan.sourceCaptureDirectory+'/'+name+'/capture.json';
    assert.deepEqual(binding(inputPath),plan.inputBindings[name]);
    const traceText=readFileSync(resolve(root,inputPath),'utf8'),trace=JSON.parse(traceText);
    const ordinary=sdk.analyzeV3(traceText),normal=sdk.normalizeCaptureV3(traceText);
    const selected=sdk.analyzeV3(traceText,{sqlProof:policy}),selectedNormal=sdk.normalizeCaptureV3(traceText,{sqlProof:policy});
    const result={name,expected,defaultStatus:ordinary.status,selectedStatus:selected.status,defaultNormalizedStatus:normal.status,selectedNormalizedStatus:selectedNormal.status,
      selectedReport:retain(name+'-selected-report.json',selected)};
    receipt.cases.push(result);
    check(name+':default-unchanged',()=>{assert.equal(ordinary.status,expected.default);assert.equal(normal.status,'inconclusive');assert.equal(normal.history,null);assert.deepEqual(ordinary.normalized,normal);});
    check(name+':selected-frozen-result',()=>{assert.equal(selected.status,expected.explicit);assert.equal(selectedNormal.status,expected.explicit==='consistent'?'ready':'inconclusive');assert.equal(selected.coverage.complete,expected.explicit==='consistent');});
    check(name+':explicit-normalized-equals-report',()=>{assert.deepEqual(selected.normalized,selectedNormal);assert.deepEqual(selectedNormal.observations,trace.events);assert.equal(selected.execution.analysisOptions.sqlProof,policy);assert.equal(selectedNormal.algorithm,'v3-lifecycle-sql-1');assert.equal(selected.algorithm,'v3-register-sql-1');});
    check(name+':both-reports-verify',()=>{assert.equal(sdk.verifyV3(traceText,ordinary).valid,true);assert.equal(sdk.verifyV3(traceText,selected).valid,true);});
    const capsuleText=sdk.makeCapsuleV3(traceText,selected),capsule=JSON.parse(capsuleText);
    result.capsule=retain(name+'-selected-capsule.json',capsuleText);
    check(name+':selected-capsule-replays',()=>{const r=replaySafe(sdk,capsuleText);assert.equal(r.valid,true);assert.equal(r.status,expected.explicit);assert.deepEqual(JSON.parse(capsule.normalizedText),selectedNormal);});
    const oldPath=plan.sourceCaptureDirectory+'/'+name+'/capsule.json';
    const oldCapsule=readFileSync(resolve(root,oldPath),'utf8');
    check(name+':old-default-capsule-still-replays',()=>{const r=replaySafe(sdk,oldCapsule);assert.equal(r.valid,true);assert.equal(r.status,'inconclusive');});
    check(name+':reduction-propagates-explicit-policy',()=>{const r=sdk.reduceV3(traceText,{analysisOptions:{sqlProof:policy},maxChecks:0});assert.equal(r.status,'not-violation');assert.equal(r.checks,0);assert.equal(r.oneMinimal,false);assert.deepEqual(r.report,selected);assert.deepEqual(r.reducedCapture,trace);});
    if(expected.explicit==='consistent'){
      for(const [mutation,change]of reportTamper){
        const changed=copy(selected);change(changed);
        const verify=sdk.verifyV3(traceText,changed);
        const altered=copy(capsule);altered.reportText=JSON.stringify(changed);altered.reportSha256=hash(altered.reportText);
        altered.normalizedText=JSON.stringify(changed.normalized);altered.normalizedSha256=hash(altered.normalizedText);
        altered.evidenceText=JSON.stringify(changed.evidence);altered.evidenceSha256=hash(altered.evidenceText);
        const replay=replaySafe(sdk,JSON.stringify(altered));
        receipt.tamper.push({case:name,mutation,verify,replay,allChangedEnvelopeHashesRecomputed:true});
        check(name+':tamper:'+mutation,()=>{assert.equal(verify.valid,false);assert.equal(replay.valid,false);});
      }
      for(const key of['trace','normalized','evidence']){
        const changed=copy(capsule),part=JSON.parse(changed[key+'Text']);
        if(key==='trace'){part.events.find(e=>e.kind==='snapshot').consistent=false;}
        else if(key==='normalized'){part.coverage.complete=false;}
        else{part.status='violation';}
        changed[key+'Text']=JSON.stringify(part);changed[key+'Sha256']=hash(changed[key+'Text']);
        const replay=replaySafe(sdk,JSON.stringify(changed));receipt.tamper.push({case:name,mutation:key+'-text-rehashed',replay});
        check(name+':capsule:'+key+'-text-rehashed',()=>assert.equal(replay.valid,false));
      }
    }
    for(const options of badOptions){
      check(name+':bad-options:'+JSON.stringify(options),()=>{
        let report;try{report=sdk.analyzeV3(traceText,options);}catch{return;}
        assert.equal(report.status,'invalid','Unsupported policy must be rejected instead of silently selected');
      });
      check(name+':bad-normalization-options:'+JSON.stringify(options),()=>{
        let normalized;try{normalized=sdk.normalizeCaptureV3(traceText,options);}catch{return;}
        assert.equal(normalized.status,'invalid','Unsupported policy must not silently become normalization default');
      });
    }
    if(['acquire-heartbeat-cleanup','busy-acquisition'].includes(name)){
      const runCLI=(command,extra=[])=>{const r=spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),command,resolve(root,inputPath),...extra],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});assert.equal(r.error,undefined);return r;};
      const cliNormal=resolve(output,name+'-cli-normal.json'),cliReport=resolve(output,name+'-cli-report.json'),cliCapsule=resolve(output,name+'-cli-capsule.json'),cliReduce=resolve(output,name+'-cli-reduction.json');
      check(name+':cli-ingest-explicit',()=>{const r=runCLI('ingest-v3',['--sql-proof',policy,'--output',cliNormal]);assert.equal(r.status,expected.explicit==='consistent'?0:3);assert.deepEqual(JSON.parse(readFileSync(cliNormal)),selectedNormal);});
      check(name+':cli-check-explicit',()=>{const r=runCLI('check-v3',['--sql-proof',policy,'--output',cliReport,'--capsule',cliCapsule]);assert.equal(r.status,expected.explicit==='consistent'?0:3);assert.deepEqual(JSON.parse(readFileSync(cliReport)),selected);assert.equal(replaySafe(sdk,readFileSync(cliCapsule,'utf8')).valid,true);});
      check(name+':cli-reduce-explicit',()=>{const r=runCLI('reduce-v3',['--sql-proof',policy,'--max-checks','0','--output',cliReduce]);assert.equal(r.status,3);const reduced=JSON.parse(readFileSync(cliReduce));assert.equal(reduced.report.execution.analysisOptions.sqlProof,policy);assert.deepEqual(reduced.report,selected);});
      check(name+':cli-default-unchanged',()=>{const r=runCLI('check-v3');assert.equal(r.status,3);assert.equal(JSON.parse(r.stdout).status,'inconclusive');});
      check(name+':cli-unknown-policy-rejected',()=>{const r=runCLI('check-v3',['--sql-proof','unknown-policy']);assert.equal(r.status,2);assert.equal(JSON.parse(r.stdout).status,'invalid');});
      check(name+':cli-verify-recorded-policy',()=>{const r=spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),'verify-v3',resolve(root,inputPath),cliReport],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000});assert.equal(r.status,0);assert.equal(JSON.parse(r.stdout).valid,true);});
      check(name+':cli-replay-recorded-policy',()=>{const r=spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),'replay-v3',cliCapsule],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000});assert.equal(r.status,0);assert.equal(JSON.parse(r.stdout).valid,true);});
      check(name+':cli-verify-cannot-override-policy',()=>{const r=spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),'verify-v3',resolve(root,inputPath),cliReport,'--sql-proof',policy],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000});assert.notEqual(r.status,0);});
    }
  }
  check('source-and-runtime-frozen',()=>{assert.equal(sourceFingerprint(root),receipt.sourceSha256);assert.deepEqual(load('dist/build-manifest.json'),build);for(const [name,b]of Object.entries(plan.inputBindings))assert.deepEqual(binding(plan.sourceCaptureDirectory+'/'+name+'/capture.json'),b);});
}catch(error){receipt.failures.push({name:'execution',error:String(error.message).replaceAll(root,'<workspace>')});}
receipt.passed=receipt.failures.length===0;const saved=retain('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.length,tamper:receipt.tamper.length,checks:receipt.checks.length,failures:receipt.failures,receipt:saved}));
process.exitCode=receipt.passed?0:1;
