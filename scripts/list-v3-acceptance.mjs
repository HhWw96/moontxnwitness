// Independent frozen append-list inputs, full scope ledgers and exact outcomes.
// No build or database is run; every execution writes only new verification.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,mkdirSync} from 'node:fs';
import {resolve,relative,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {sourceFingerprint} from './build-fingerprint.mjs';
import {writeImmutableEvidence} from './performance-evidence.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const stamp=new Date().toISOString().replace(/[:.]/g,'-');
const folder=resolve(root,'verification/list-v3','acceptance-'+stamp);mkdirSync(folder,{recursive:true});
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const rel=p=>relative(root,p).replaceAll('\\','/');
const load=p=>JSON.parse(readFileSync(resolve(root,p),'utf8'));
const copy=v=>structuredClone(v);
const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
const args=process.argv.slice(2),pinned={};
for(let i=0;i<args.length;i+=2){assert.ok(['--frozen-build-source','--frozen-main','--frozen-capture'].includes(args[i]));assert.match(args[i+1]||'',/^[0-9a-f]{64}$/);pinned[args[i]]=args[i+1];}
assert.ok(Object.keys(pinned).length===0||Object.keys(pinned).length===3,'Pin all three build hashes together');
const receipt={schema:1,kind:'independent-list-v3-acceptance',complete:false,passed:false,
  actualDatabaseExecution:false,performanceMeasurement:false,automaticG2OrPLClassification:false,
  sourceEvidenceComparison:'Complete facts compared as a multiset keyed by globally unique item identity',
  checks:[],differences:[]};
const retain=(name,value)=>{const text=typeof value==='string'?value:JSON.stringify(value,null,2)+'\n';const p=resolve(folder,name);writeImmutableEvidence(p,text);return{file:rel(p),bytes:Buffer.byteLength(text),sha256:hash(text)};};
const check=(name,fn)=>{try{fn();receipt.checks.push({name,passed:true});}catch(e){receipt.checks.push({name,passed:false,error:String(e.message).replaceAll(root,'<workspace>')});}};
function py(args,maxBuffer=32*1024*1024){const p=spawnSync(python,['-B','scripts/list-v3-oracle.py',...args],{cwd:root,encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer});assert.equal(p.error,undefined);assert.equal(p.status,0,p.stderr||p.stdout);return JSON.parse(p.stdout);}
function removeTx(trace,id){const t=copy(trace),mapping=new Map();t.events=t.events.filter(e=>e.tx!==id).map((e,i)=>{mapping.set(e.seq,i+1);e.seq=i+1;return e;});for(const e of t.events){if(e.kind==='rows')e.statement=mapping.get(e.statement);if(e.kind==='rollback_ok'&&e.commitResponse)e.commitResponse.request=mapping.get(e.commitResponse.request);}return t;}

try{
  const build=load('dist/build-manifest.json'),workspaceSource=sourceFingerprint(root);
  if(pinned['--frozen-build-source']){assert.equal(build.sourceSha256,pinned['--frozen-build-source']);assert.equal(build.coreSha256,pinned['--frozen-main']);assert.equal(build.captureCoreSha256,pinned['--frozen-capture']);}
  else assert.equal(build.sourceSha256,workspaceSource,'Build externally before list acceptance');
  receipt.sourceBindingMode=pinned['--frozen-build-source']?'explicit frozen compiled snapshot; subsequent working-tree changes are not being certified':'current working tree';
  receipt.workspaceSourceSha256AtStart=workspaceSource;receipt.workspaceMatchesFrozenBuild=workspaceSource===build.sourceSha256;
  for(const [file,key]of[['core.mjs','coreSha256'],['capture-core.mjs','captureCoreSha256']])assert.equal(hash(readFileSync(resolve(root,'dist',file))),build[key]);
  for(const file of['sdk.mjs','evidence.mjs','moontxnwitness.mjs'])assert.equal(hash(readFileSync(resolve(root,'dist',file))),hash(readFileSync(resolve(root,'cmd',file))),'Stale built wrapper '+file);
  const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
  const manifest=load('fixtures/list-v3/manifest.json');
  receipt.build=build;receipt.sourceBindings=Object.fromEntries(['scripts/list-v3-oracle.py','scripts/list-v3-acceptance.mjs',
    'fixtures/list-v3/manifest.json','fixtures/list-v3/manual.json','fixtures/list-v3/generated-10000.json','fixtures/list-v3/extension-unique.json','fixtures/list-v3/unique-10000.json','fixtures/list-v3/reduction-source-closure.json',
    'dist/build-manifest.json','dist/core.mjs','dist/capture-core.mjs','dist/sdk.mjs','dist/evidence.mjs','dist/moontxnwitness.mjs',
    'cmd/sdk.mjs','cmd/evidence.mjs','cmd/moontxnwitness.mjs'].map(p=>[p,hash(readFileSync(resolve(root,p)))]));
  const extension=load('fixtures/list-v3/extension-unique.json');assert.equal(hash(readFileSync(resolve(root,'fixtures/list-v3/manifest.json'))),extension.originalManifestSha256);
  const expectedCases=[...manifest.files,...extension.files].reduce((sum,b)=>sum+b.cases,0);
  const self=py(['--self-test']);assert.equal(self.passed,true);assert.equal(self.cases,expectedCases);receipt.independentSelfTest=self;
  const manual=py(['--manual-results']);const references=new Map(manual.cases.map(c=>[c.id,c.reference]));
  retain('manual-independent-reference.json',manual);
  const records=[];
  for(const binding of[...manifest.files,...extension.files]){const raw=readFileSync(resolve(root,binding.file));assert.equal(hash(raw),binding.sha256);assert.equal(raw.length,binding.bytes);records.push(...JSON.parse(raw));}
  receipt.uniqueAdditionalInputs=extension.uniqueInputSha256Count;receipt.distinctAdditionalProgramShapes=extension.distinctProgramAndInitialLengthShapes;
  receipt.originalGeneratedUniqueInputs=extension.originalUniqueGeneratedInputHashes;
  assert.equal(new Set(records.filter(c=>c.id.startsWith('generated-unique-')).map(c=>c.inputSha256)).size,10000);
  const summaries=[],orders=[];
  for(const c of records){
    assert.equal(hash(c.traceText),c.inputSha256,'Frozen input changed: '+c.id);
    let normalized,report;
    const errors=[];
    try{
      normalized=sdk.normalizeCaptureV3(c.traceText);report=sdk.analyzeV3(c.traceText,c.options);
      assert.equal(normalized.schema,3);
      assert.equal(normalized.status,c.expected.normalization);assert.equal(report.status,c.expected.analysis);
      assert.equal(report.schemaVersion,3);
      if(normalized.status!=='invalid')assert.equal(normalized.algorithm,'v3-list-lifecycle-1');
      if(report.status!=='invalid'){assert.equal(report.algorithm,'v3-list-1');assert.equal(report.modelDefinition.id,'append-list-serializable-v1');}
      else{assert.equal(report.coverage.complete,false);assert.ok(!report.evidence,'Invalid diagnostics must not publish a successful proof');}
      assert.equal(normalized.history,null,'List analysis must not publish a synthetic register history');
      if(c.expected.issue)assert.ok(normalized.coverage.gaps.some(g=>g.code===c.expected.issue),'Missing frozen primary coverage gap');
      if(c.expected.normalization!=='invalid'){
        assert.deepEqual(normalized.observations,JSON.parse(c.traceText).events);
        const r=references.get(c.id);
        if(r){assert.equal(normalized.coverage.complete,r.coverageComplete);assert.deepEqual(normalized.effects,r.normalized.effects);assert.deepEqual(normalized.transactions,r.normalized.transactions);}
      }
      if(report.status!=='invalid'){
        assert.deepEqual(report.normalized,normalized);
        assert.equal(sdk.verifyV3(c.traceText,report).valid,true);
        if(normalized.coverage.complete){
          assert.equal(report.execution.effectiveLimits.committedTransactions,6);assert.equal(report.execution.effectiveLimits.operations,128);
          assert.ok(report.execution.metrics.states<=report.execution.effectiveLimits.states);
          assert.ok(report.execution.metrics.operationChecks<=report.execution.effectiveLimits.operationChecks);
        }else{assert.equal(report.evidence,null);assert.equal(report.status,'inconclusive');}
        if(report.status==='consistent'){
          assert.equal(report.evidence.kind,'serial-list-replay');assert.equal(report.execution.metrics.complete,true);
          orders.push({id:c.id,order:report.evidence.serialOrder});
        }
        if(report.status==='violation'){
          assert.equal(normalized.coverage.complete,true);assert.equal(report.execution.metrics.complete,true);
          assert.ok(['bounded-serial-exhaustion','source-proven-list-anomaly'].includes(report.evidence.kind));
          if(report.evidence.kind==='bounded-serial-exhaustion')assert.equal(report.evidence.code,'no_serial_list_execution');
          for(const finding of report.evidence.findings||[])assert.ok(!['G2','PL-3','PL-2','G1'].includes(finding.code));
        }
        if(report.evidence?.sourceEvidence){
          const expected=references.get(c.id)?.normalized.sources;
          if(expected){const facts=Object.entries(expected).map(([id,s])=>({id,value:s.value,key:s.key,sourceSeq:s.seq,writer:s.initial?null:s.tx,revertedBy:s.initial?null:s.effect.revertedBy}));
            const sort=a=>[...a].sort((x,y)=>x.id<y.id?-1:x.id>y.id?1:0);assert.deepEqual(sort(report.evidence.sourceEvidence),sort(facts));}
        }
      }
    }catch(e){errors.push(String(e.message).replaceAll(root,'<workspace>'));}
    if(references.has(c.id)||errors.length){
      retain(c.id+'.normalized.json',normalized??null);retain(c.id+'.report.json',report??null);
    }
    if(errors.length){receipt.differences.push({id:c.id,inputSha256:c.inputSha256,expected:c.expected,errors,
      trace:retain(c.id+'.trace.json',c.traceText),options:c.options});}
    summaries.push({id:c.id,inputSha256:c.inputSha256,passed:errors.length===0,normalization:normalized?.status,
      analysis:report?.status,reportSha256:report?hash(JSON.stringify(report)):null,errors});
  }
  receipt.differential=retain('differential-results.json',summaries);
  check('frozen-'+expectedCases+'-independent-differential',()=>assert.equal(receipt.differences.length,0));
  const orderPath=retain('production-serial-orders.json',orders);const verified=py(['--verify-orders',orderPath.file]);
  receipt.serialWitnesses=retain('independent-witness-verification.json',verified);
  check('every-consistent-production-witness-independently-replays',()=>{assert.equal(verified.passed,true);assert.equal(verified.checkedOrders,orders.length);assert.ok(orders.length>0);});

  const skew=JSON.parse(records.find(c=>c.id==='two-key-read-append-cycle').traceText),report=sdk.analyzeV3(skew);
  assert.equal(report.status,'violation');
  const proof=sdk.makeCapsuleV3(skew,report),capsule=JSON.parse(proof);retain('genuine-list-v3.capsule.json',proof);
  check('genuine-list-capsule-reproduces',()=>assert.equal(sdk.replayCapsuleV3(proof).valid,true));
  const tamper=[];
  const reportChanges={conclusion:r=>r.status='consistent',model:r=>r.modelDefinition.id='register-serializable-v1',algorithm:r=>r.algorithm='forged-list',
    version:r=>r.version='0.0.0',budget:r=>r.execution.analysisOptions.maxStates+=1,effectiveLimit:r=>r.execution.effectiveLimits.committedTransactions=12,
    metrics:r=>r.execution.metrics.complete=false,source:r=>r.evidence.sourceEvidence[0].value='forged-source',
    observation:r=>r.normalized.observations[0].consistent=false,effect:r=>r.normalized.effects[0].id='forged-id',
    revoked:r=>r.normalized.effects[0].revertedBy=999,transaction:r=>r.normalized.transactions[0].status='aborted',
    coverage:r=>r.coverage.complete=false,evidence:r=>r.evidence.code='G2'};
  for(const[name,mutate]of Object.entries(reportChanges))check('tamper-report-'+name,()=>{const r=copy(report);mutate(r);retain('tamper-report-'+name+'.json',r);assert.equal(sdk.verifyV3(skew,r).valid,false);tamper.push(name);});
  const replace=(c,field,v)=>{c[field+'Text']=JSON.stringify(v);c[field+'Sha256']=hash(c[field+'Text']);};
  for(const[name,mutate]of Object.entries(reportChanges))check('tamper-capsule-rehashed-'+name,()=>{const c=copy(capsule),r=copy(report);mutate(r);replace(c,'report',r);retain('tamper-capsule-'+name+'.json',c);assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);tamper.push('capsule-'+name);});
  check('tamper-capsule-rehashed-trace',()=>{const c=copy(capsule),t=copy(skew);t.events.find(e=>e.kind==='append').value='forged';replace(c,'trace',t);assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);tamper.push('trace');});
  check('tamper-capsule-rehashed-normalized-and-report',()=>{const c=copy(capsule),r=copy(report);r.normalized.effects[0].value='forged';replace(c,'report',r);replace(c,'normalized',r.normalized);assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);tamper.push('normalized-report');});
  check('duplicate-json-key-rejected',()=>{assert.equal(sdk.normalizeCaptureV3(JSON.stringify(skew).replace('{','{"dataModel":"append-list-v1",')).status,'invalid');assert.equal(sdk.replayCapsuleV3(proof.replace('{','{"schemaVersion":3,')).valid,false);tamper.push('duplicate-json');});
  check('coherent-alternative-is-not-source-authentication',()=>{const t=copy(skew);t.clockDomain='another-declared-domain';assert.equal(sdk.replayCapsuleV3(sdk.makeCapsuleV3(t,sdk.analyzeV3(t))).valid,true);});
  receipt.tamperCases=tamper.length;check('at-least-24-distinct-tamper-cases',()=>assert.ok(tamper.length>=24));
  const source=load('fixtures/list-v3/reduction-source-closure.json');
  const original=sdk.analyzeV3(source),zero=sdk.reduceV3(source,{maxChecks:0}),reduced=sdk.reduceV3(source,{maxChecks:256});
  retain('source-closure-original.json',original);retain('source-closure-zero-budget.json',zero);retain('source-closure-reduced.json',reduced);
  check('zero-check-budget-never-single-minimal',()=>{assert.equal(original.status,'violation');assert.equal(zero.checks,0);assert.equal(zero.oneMinimal,false);assert.deepEqual(zero.reducedCapture,source);});
  check('reduction-retains-aborted-source-removes-noise',()=>{assert.equal(reduced.oneMinimal,true);assert.equal(reduced.status,'reduced');assert.deepEqual(reduced.removed,['N']);assert.deepEqual(reduced.report.normalized.transactions.map(t=>t.id),['S','U']);assert.equal(reduced.report.status,'violation');assert.equal(sdk.verifyV3(reduced.reducedCapture,reduced.report).valid,true);});
  check('reduction-remaps-all-protocol-references-without-inventing-facts',()=>{const mapping=new Map(reduced.retainedOriginalSeq.map((old,i)=>[old,i+1]));for(let i=0;i<reduced.reducedCapture.events.length;i++){const e=copy(source.events.find(e=>e.seq===reduced.retainedOriginalSeq[i]));e.seq=i+1;if(e.kind==='rows')e.statement=mapping.get(e.statement);if(e.kind==='rollback_ok'&&e.commitResponse)e.commitResponse.request=mapping.get(e.commitResponse.request);assert.deepEqual(reduced.reducedCapture.events[i],e);}});
  for(const id of['S','U'])check('independent-reduced-single-delete-'+id,()=>{const t=removeTx(reduced.reducedCapture,id),saved=retain('single-delete-'+id+'.trace.json',t),r=py(['--trace',saved.file]);assert.notEqual(r.analysis,'violation');assert.notEqual(sdk.analyzeV3(t).status,'violation');if(id==='S')assert.equal(r.normalization,'inconclusive');});
  for(const[name,args,exitCode,predicate]of[
    ['ingest',['ingest-v3','fixtures/list-v3/reduction-source-closure.json'],0,r=>r.status==='ready'],
    ['analyze',['check-v3','fixtures/list-v3/reduction-source-closure.json'],1,r=>r.status==='violation'],
    ['reduce',['reduce-v3','fixtures/list-v3/reduction-source-closure.json'],0,r=>r.oneMinimal],
    ['replay',['replay-v3',rel(resolve(folder,'genuine-list-v3.capsule.json'))],0,r=>r.valid],
  ])check('cli-list-'+name,()=>{const p=spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});retain('cli-'+name+'.process.json',{args,exitCode:p.status,stdout:p.stdout,stderr:p.stderr,error:p.error?.name||null});assert.equal(p.error,undefined);assert.equal(p.status,exitCode,p.stderr);assert.ok(predicate(JSON.parse(p.stdout)));});
  receipt.inputCases=records.length;receipt.manualCases=71;receipt.generatedCases=records.length-71;
  receipt.distinctInputHashes=new Set(records.map(c=>c.inputSha256)).size;
  receipt.complete=true;receipt.passed=receipt.checks.every(c=>c.passed)&&receipt.differences.length===0;
}catch(e){receipt.notExecuted=!receipt.differential;receipt.error=String(e.message).replaceAll(root,'<workspace>');}
receipt.finishedAt=new Date().toISOString();const out=retain('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,complete:receipt.complete,inputCases:receipt.inputCases||0,
  differences:receipt.differences.length,checks:receipt.checks.length,tamperCases:receipt.tamperCases||0,
  failures:receipt.checks.filter(c=>!c.passed),receipt:out.file,sha256:out.sha256,error:receipt.error||null},null,2));
if(!receipt.passed)process.exitCode=receipt.notExecuted?3:1;
