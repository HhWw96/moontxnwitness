// Independent frozen relation histories, scope ledgers, sources and exact budgets.
// This runner never builds or opens a database and never rewrites expectations.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,mkdirSync,openSync,writeSync,closeSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {sourceFingerprint} from './build-fingerprint.mjs';
import {writeImmutableEvidence} from './performance-evidence.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const fixture=resolve(root,'fixtures/relation-v3');
const folder=resolve(root,'verification/relation-v3','acceptance-'+new Date().toISOString().replace(/[:.]/g,'-'));
mkdirSync(folder,{recursive:true});
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const rel=p=>relative(root,p).replaceAll('\\','/');
const load=p=>JSON.parse(readFileSync(p,'utf8'));
const copy=value=>structuredClone(value);
const binding=p=>{const raw=readFileSync(p);return{bytes:raw.length,sha256:hash(raw)};};
const retain=(name,value)=>{const raw=typeof value==='string'?value:JSON.stringify(value,null,2)+'\n';const p=resolve(folder,name);writeImmutableEvidence(p,raw);return{file:rel(p),bytes:Buffer.byteLength(raw),sha256:hash(raw)};};
const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
const receipt={schema:1,kind:'independent-relation-v3-acceptance',passed:false,complete:false,
  actualDatabaseExecution:false,performanceMeasurement:false,automaticG2OrPLClassification:false,
  sourceBindingMode:'Strict current working tree and actual compiled/runtime bytes',
  cases:0,inputCases:0,normalizationCases:0,sourceEvidenceCases:0,budgetCases:0,witnesses:0,
  differences:[],checks:[]};
const message=e=>String(e.message).replaceAll(root,'<workspace>');
const check=(name,fn)=>{try{fn();receipt.checks.push({name,passed:true});}catch(e){receipt.checks.push({name,passed:false,error:message(e)});}};
function py(args){const p=spawnSync(python,['-B','scripts/relation-v3-oracle.py',...args],{cwd:root,encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer:32*1024*1024});assert.equal(p.error,undefined);assert.equal(p.status,0,p.stderr||p.stdout);return JSON.parse(p.stdout);}
function removeTx(trace,id){const t=copy(trace),mapping=new Map();t.events=t.events.filter(e=>e.tx!==id).map((e,i)=>{mapping.set(e.seq,i+1);e.seq=i+1;return e;});for(const e of t.events){if(e.kind==='rows')e.statement=mapping.get(e.statement);if(e.kind==='rollback_ok'&&e.commitResponse)e.commitResponse.request=mapping.get(e.commitResponse.request);}return t;}
function sources(trace,normalized){const expected=[];for(const[relation,rows]of Object.entries(trace.events[0].initial))for(const row of rows)expected.push({relation,key:row.key,version:row.version,values:row.values,action:'snapshot',predecessor:null,sourceSeq:trace.events[0].seq,writer:null,revertedBy:null});for(const e of normalized.effects)expected.push({relation:e.relation,key:e.key,version:e.version,values:e.values,action:e.action,predecessor:e.predecessor,sourceSeq:e.seq,writer:e.tx,revertedBy:e.revertedBy});return expected;}
function compareSources(actual,expected){assert.ok(Array.isArray(actual));const map=new Map(actual.map(e=>[e.version,e]));assert.equal(map.size,actual.length,'Duplicate source identity');assert.equal(map.size,expected.length,'Missing/extra source');for(const e of expected)assert.deepEqual(map.get(e.version),e);}
let raw;
try{
  assert.equal(process.argv.length,2,'This formal runner accepts only the current source/build; no frozen-build override');
  const build=load(resolve(root,'dist/build-manifest.json'));
  assert.equal(sourceFingerprint(root),build.sourceSha256,'Build current source before relation acceptance');
  const runtimeNames=['build-manifest.json','core.mjs','capture-core.mjs','sdk.mjs','evidence.mjs','moontxnwitness.mjs'];
  const runtime=Object.fromEntries(runtimeNames.map(name=>[name,binding(resolve(root,'dist',name))]));
  assert.equal(runtime['core.mjs'].sha256,build.coreSha256);assert.equal(runtime['capture-core.mjs'].sha256,build.captureCoreSha256);
  for(const name of['sdk.mjs','evidence.mjs','moontxnwitness.mjs'])assert.deepEqual(binding(resolve(root,'cmd',name)),runtime[name],'Stale wrapper '+name);
  receipt.build=build;receipt.runtimeBindings=runtime;
  const manifest=load(resolve(fixture,'manifest.json'));
  for(const[name,b]of Object.entries(manifest.files))assert.deepEqual(binding(resolve(fixture,name)),b,'Frozen file changed: '+name);
  receipt.sourceBindings=Object.fromEntries(['scripts/relation-v3-oracle.py','scripts/relation-v3-acceptance.mjs',
    ...Object.keys(manifest.files).map(n=>'fixtures/relation-v3/'+n),'fixtures/relation-v3/manifest.json',
    'fixtures/relation-v3/reduction-source-closure.json','fixtures/relation-v3/reduction-source-closure.expected.json',
    'verification/relation-v3/frozen-corpus-promotion.json',...manifest.historyArchives.map(a=>a.file),
    ...runtimeNames.map(n=>'dist/'+n),'cmd/sdk.mjs','cmd/evidence.mjs','cmd/moontxnwitness.mjs'].map(p=>[p,binding(resolve(root,p))]));
  const self=py(['--self-test']);assert.equal(self.passed,true);assert.equal(self.cases,1170);receipt.independentSelfTest=self;
  const records=[...load(resolve(fixture,'boundary.json')),...load(resolve(fixture,'generated-1000.json'))];
  const refs=new Map(load(resolve(fixture,'normalization-oracle.json')).map(r=>[r.id,r]));
  const budgets=new Map(load(resolve(fixture,'budget-expectations.json')).cases.map(r=>[r.id,r]));
  assert.equal(records.length,1170);assert.equal(new Set(records.slice(170).map(r=>r.inputSha256)).size,1000);
  retain('pre-execution-input-plan.json',{manifest:binding(resolve(fixture,'manifest.json')),build,runtimeBindings:runtime,
    expectationsFrozenBeforeProductionRun:true,caseBindings:records.map(r=>({id:r.id,inputSha256:r.inputSha256,expected:r.expected,options:r.options}))});
  const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
  const orders=[],summaries=[],selected=[];
  raw=openSync(resolve(folder,'production-outputs.jsonl'),'wx');
  for(const r of records){
    assert.equal(hash(r.traceText),r.inputSha256);const errors=[];let n,a;
    const verify=(field,fn)=>{try{fn();}catch(e){errors.push({field,error:message(e)});}};
    try{
      const t=JSON.parse(r.traceText),ref=refs.get(r.id);n=sdk.normalizeCaptureV3(r.traceText);a=sdk.analyzeV3(r.traceText,r.options);
      verify('analysis-status',()=>assert.equal(a.status,r.expected));
      if(r.expected==='invalid')verify('invalid-boundary',()=>{assert.equal(n.status,'invalid');assert.equal(a.coverage.complete,false);assert.equal(a.evidence,null);});
      else{
        const expected=ref.normalization;assert.ok(expected);
        verify('normalization-ledger',()=>{for(const key of manifest.normalizationFields)assert.deepEqual(n[key],expected[key],key);assert.equal(n.coverage.complete,expected.coverage.complete);if(!expected.coverage.complete)assert.ok(n.coverage.gaps.length);});
        receipt.normalizationCases++;
        verify('report-model-and-normalized',()=>{assert.equal(a.algorithm,'v3-relation-1');assert.equal(a.modelDefinition.id,'relation-set-serializable-v1');assert.deepEqual(a.normalized,n);});
        if(a.evidence?.sourceEvidence!==undefined){verify('producer-source-evidence',()=>compareSources(a.evidence.sourceEvidence,sources(t,expected)));receipt.sourceEvidenceCases++;}
        else if(['consistent','violation'].includes(a.status))verify('required-source-evidence',()=>assert.fail('Complete result omitted producer sources'));
        verify('budget-ceilings',()=>{assert.ok(a.execution.metrics.states<=(r.options.maxStates??100000));assert.ok(a.execution.metrics.operationChecks<=(r.options.maxOperationChecks??1000000));if(['consistent','violation'].includes(a.status))assert.equal(a.execution.metrics.complete,true);});
        if(budgets.has(r.id)){const b=budgets.get(r.id);verify('frozen-exact-budget-counter',()=>{assert.equal(a.execution.metrics.states,b.metrics.states);assert.equal(a.execution.metrics.operationChecks,b.metrics.operationChecks);assert.equal(a.execution.metrics.reason,b.reason);});receipt.budgetCases++;}
        if(a.status==='consistent'){orders.push({id:r.id,traceText:r.traceText,order:a.evidence.serialOrder});receipt.witnesses++;}
        if(selected.length<3&&!selected.some(p=>p.report.status===a.status))selected.push({traceText:r.traceText,report:a});
      }
    }catch(e){errors.push({field:'case-execution',error:message(e)});}
    writeSync(raw,JSON.stringify({id:r.id,inputSha256:r.inputSha256,normalized:n??null,report:a??null,errors})+'\n');
    if(errors.length)receipt.differences.push({id:r.id,inputSha256:r.inputSha256,expected:r.expected,errors});
    summaries.push({id:r.id,expected:r.expected,actual:a?.status,normalization:n?.status,differences:errors.length});
    receipt.cases++;if(receipt.cases%200===0)console.log(JSON.stringify({progress:'relation-comparison',cases:receipt.cases,differences:receipt.differences.length}));
  }
  closeSync(raw);raw=undefined;receipt.rawOutputs=binding(resolve(folder,'production-outputs.jsonl'));
  receipt.differential=retain('case-summary.json',summaries);receipt.inputCases=records.length;
  check('1170-frozen-independent-histories-and-complete-ledgers',()=>assert.equal(receipt.differences.length,0));
  const orderFile=retain('serial-witnesses.json',orders);const replay=py(['--verify-orders',orderFile.file]);receipt.serialWitnesses=retain('independent-witness-result.json',replay);
  check('all-consistent-witnesses-independently-replay',()=>{assert.equal(replay.passed,true);assert.equal(replay.cases,orders.length);assert.equal(orders.length,704);});
  for(const p of selected)check('sdk-verify-capsule-'+p.report.status,()=>{assert.equal(sdk.verifyV3(p.traceText,p.report).valid,true);const c=sdk.makeCapsuleV3(p.traceText,p.report);assert.equal(sdk.replayCapsuleV3(c).valid,true);});

  const input=load(resolve(fixture,'reduction-source-closure.json')),expected=load(resolve(fixture,'reduction-source-closure.expected.json'));
  assert.equal(hash(readFileSync(resolve(fixture,'reduction-source-closure.json'))),expected.inputSha256);
  const report=sdk.analyzeV3(input),proof=sdk.makeCapsuleV3(input,report),capsule=JSON.parse(proof);
  const reportFile=retain('relation-report.json',report),capsuleFile=retain('relation-capsule.json',proof);
  check('source-closure-independent-preregistered-violation',()=>assert.equal(report.status,expected.originalStatus));
  const changes={conclusion:r=>r.status='consistent',model:r=>r.modelDefinition.id='append-list-serializable-v1',algorithm:r=>r.algorithm='forged',version:r=>r.version='0.0.0',
    budget:r=>r.execution.analysisOptions.maxStates=99999,effectiveLimit:r=>r.execution.effectiveLimits.committedTransactions=12,
    incompleteMetric:r=>r.execution.metrics.complete=false,coverage:r=>r.coverage.complete=false,
    sourceContent:r=>r.evidence.sourceEvidence[0].values.n='999',sourceVersion:r=>r.evidence.sourceEvidence[0].version='forged-source',
    predecessor:r=>r.normalized.effects[0].predecessor='forged-predecessor',effectRevocation:r=>r.normalized.effects[0].revertedBy=999,
    transaction:r=>r.normalized.transactions[0].status='aborted',finalWrites:r=>r.normalized.transactions[0].finalWrites=[],
    schema:r=>r.normalized.relationSchema.r.columns.n='text',observation:r=>r.normalized.observations.find(e=>e.kind==='row_read').complete=false};
  let tamperCases=0;
  for(const[name,mutate]of Object.entries(changes)){
    check('report-tamper-'+name,()=>{const r=copy(report);mutate(r);retain('tamper-report-'+name+'.json',r);assert.equal(sdk.verifyV3(input,r).valid,false);});tamperCases++;
    check('rehashed-capsule-tamper-'+name,()=>{const c=copy(capsule),r=copy(report);mutate(r);c.reportText=JSON.stringify(r);c.reportSha256=hash(c.reportText);retain('tamper-capsule-'+name+'.json',c);assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);});tamperCases++;
  }
  const replace=(c,field,value)=>{c[field+'Text']=JSON.stringify(value);c[field+'Sha256']=hash(c[field+'Text']);};
  check('rehashed-trace-tamper',()=>{const c=copy(capsule),t=copy(input);t.events.find(e=>e.kind==='row_write').values.n='999';replace(c,'trace',t);assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);});tamperCases++;
  check('rehashed-normalized-and-report-tamper',()=>{const c=copy(capsule),r=copy(report);r.normalized.effects[0].values.n='999';replace(c,'normalized',r.normalized);replace(c,'report',r);assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);});tamperCases++;
  check('duplicate-json-keys-refused',()=>{assert.equal(sdk.normalizeCaptureV3(JSON.stringify(input).replace('{','{"dataModel":"relation-set-v1",')).status,'invalid');assert.equal(sdk.replayCapsuleV3(proof.replace('{','{"schemaVersion":3,')).valid,false);});tamperCases++;
  receipt.tamperCases=tamperCases;
  check('coherent-alternative-is-not-database-authentication',()=>{const t=copy(input);t.clockDomain='independent-alternative-domain';assert.equal(sdk.replayCapsuleV3(sdk.makeCapsuleV3(t,sdk.analyzeV3(t))).valid,true);});
  const rawSql=records.find(r=>r.id==='raw-sql-unmapped');
  check('unknown-sql-keeps-permanent-coverage-gap',()=>{const n=sdk.normalizeCaptureV3(rawSql.traceText),r=sdk.analyzeV3(rawSql.traceText);assert.equal(n.status,'inconclusive');assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);assert.ok(n.coverage.gaps.some(g=>g.code==='unmapped_statement'));assert.deepEqual(n.observations,JSON.parse(rawSql.traceText).events);});
  const zero=sdk.reduceV3(input,{maxChecks:0}),reduced=sdk.reduceV3(input,{maxChecks:256});
  retain('reduction-zero-budget.json',zero);const reducedFile=retain('reduction.json',reduced);
  check('zero-candidate-budget-does-not-claim-one-minimal',()=>{assert.equal(zero.checks,0);assert.equal(zero.oneMinimal,false);assert.deepEqual(zero.reducedCapture,input);});
  check('source-closure-reduction-removes-only-independent-noise',()=>{assert.equal(reduced.status,'reduced');assert.equal(reduced.oneMinimal,true);assert.deepEqual(reduced.removed,expected.removed);assert.deepEqual(reduced.report.normalized.transactions.map(t=>t.id),expected.retained);assert.equal(reduced.report.status,'violation');assert.equal(sdk.verifyV3(reduced.reducedCapture,reduced.report).valid,true);});
  check('reduction-never-invents-source-or-observation-facts',()=>{const mapping=new Map(reduced.retainedOriginalSeq.map((seq,i)=>[seq,i+1]));assert.deepEqual(reduced.reducedCapture.relationSchema,input.relationSchema);assert.deepEqual(reduced.reducedCapture.scope,input.scope);for(let i=0;i<reduced.reducedCapture.events.length;i++){const e=copy(input.events.find(e=>e.seq===reduced.retainedOriginalSeq[i]));e.seq=i+1;if(e.kind==='rows')e.statement=mapping.get(e.statement);if(e.kind==='rollback_ok'&&e.commitResponse)e.commitResponse.request=mapping.get(e.commitResponse.request);assert.deepEqual(reduced.reducedCapture.events[i],e);}});
  for(const id of expected.retained)check('independent-reduced-single-delete-'+id,()=>{const t=removeTx(reduced.reducedCapture,id),p=retain('single-delete-'+id+'.trace.json',t),ref=py(['--trace',p.file]);assert.equal(ref.status,expected.reducedSingleDeleteStatuses[id]);assert.equal(sdk.analyzeV3(t).status,ref.status);assert.notEqual(ref.status,'violation');});
  const rawSqlFile=retain('raw-sql.trace.json',rawSql.traceText),invalidFile=retain('invalid.trace.json',records.find(r=>r.expected==='invalid').traceText);
  const cliCases=[
    ['ingest',['ingest-v3','fixtures/relation-v3/reduction-source-closure.json'],0,r=>r.status==='ready'],
    ['analyze',['check-v3','fixtures/relation-v3/reduction-source-closure.json'],1,r=>r.status==='violation'],
    ['verify',['verify-v3','fixtures/relation-v3/reduction-source-closure.json',reportFile.file],0,r=>r.valid],
    ['replay',['replay-v3',capsuleFile.file],0,r=>r.valid],
    ['reduce',['reduce-v3','fixtures/relation-v3/reduction-source-closure.json'],0,r=>r.oneMinimal&&r.removed.length===1],
    ['reduce-zero',['reduce-v3','fixtures/relation-v3/reduction-source-closure.json','--max-checks','0'],3,r=>r.status==='budget'&&r.checks===0&&!r.oneMinimal],
    ['sql-gap',['check-v3',rawSqlFile.file],3,r=>r.status==='inconclusive'],
    ['invalid',['ingest-v3',invalidFile.file],2,r=>r.status==='invalid']
  ];
  for(const[name,args,exitCode,predicate]of cliCases)check('cli-relation-'+name,()=>{const p=spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:16*1024*1024});retain('cli-'+name+'.process.json',{args,exitCode:p.status,stdout:p.stdout,stderr:p.stderr,error:p.error?.name??null});assert.equal(p.error,undefined);assert.equal(p.status,exitCode,p.stderr);assert.ok(predicate(JSON.parse(p.stdout)));});
  receipt.reductionReceipt=reducedFile;receipt.cliCases=cliCases.length;
  assert.equal(sourceFingerprint(root),build.sourceSha256);for(const[name,b]of Object.entries(runtime))assert.deepEqual(binding(resolve(root,'dist',name)),b,'Runtime changed while checking');
  for(const[p,b]of Object.entries(receipt.sourceBindings))assert.deepEqual(binding(resolve(root,p)),b,'Tested source changed while checking: '+p);
  receipt.complete=true;
}catch(e){receipt.error=message(e);receipt.notExecuted=!receipt.differential;}finally{if(raw!==undefined)closeSync(raw);}
receipt.passed=receipt.complete&&receipt.differences.length===0&&receipt.checks.every(c=>c.passed);
receipt.finishedAt=new Date().toISOString();const saved=retain('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,complete:receipt.complete,inputCases:receipt.inputCases,differences:receipt.differences.length,
  checks:receipt.checks.length,tamperCases:receipt.tamperCases||0,normalizationCases:receipt.normalizationCases,sourceEvidenceCases:receipt.sourceEvidenceCases,
  budgetCases:receipt.budgetCases,witnesses:receipt.witnesses,cliCases:receipt.cliCases||0,failures:receipt.checks.filter(c=>!c.passed),receipt:saved.file,sha256:saved.sha256,error:receipt.error||null},null,2));
if(!receipt.passed)process.exitCode=receipt.notExecuted?3:1;
