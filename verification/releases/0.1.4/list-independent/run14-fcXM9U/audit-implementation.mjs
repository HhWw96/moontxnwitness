// Independent checks of the actual v0.1.4 SDK and retained raw PG observations.
// No compiler, database connection, dependency installation or download is used.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,readdirSync,mkdirSync,mkdtempSync,copyFileSync,existsSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../../../..');
const run=mkdtempSync(resolve(here,'run14-'));
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const bind=path=>{const raw=readFileSync(path);return {sha256:hash(raw),bytes:raw.length};};
const load=path=>JSON.parse(readFileSync(path,'utf8'));
const lines=path=>readFileSync(path,'utf8').trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
const rel=path=>relative(root,path).replaceAll('\\','/');
const redact=text=>[root,root.replaceAll('\\','/'),JSON.stringify(root).slice(1,-1)].reduce((text,prefix)=>text.replaceAll(prefix,'<repository>'),text);
const save=(name,value)=>writeFileSync(resolve(run,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
function walk(path){return readdirSync(path,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?walk(resolve(path,entry.name)):[resolve(path,entry.name)]);}
const sourceFiles=[...walk(resolve(root,'src')).filter(path=>path.endsWith('.mbt')||path.endsWith('.json')||path.endsWith('moon.pkg')),
  ...['moon.mod','package.json','cmd/sdk.mjs','cmd/evidence.mjs','examples/list-cycle.json','examples/list-roundtrip.mjs','scripts/list-v3-oracle.py','fixtures/list-v3/manual.json','fixtures/list-v3/reduction-source-closure.json'].map(name=>resolve(root,name))];
const runtimeFiles=walk(resolve(root,'dist')).filter(path=>path.endsWith('.mjs')||path.endsWith('build-manifest.json'));
const inventory=paths=>Object.fromEntries(paths.map(path=>[rel(path),bind(path)]));
const sourceBefore=inventory(sourceFiles),runtimeBefore=inventory(runtimeFiles);
const build=load(resolve(root,'dist/build-manifest.json'));
const receipt={schema:1,kind:'independent-actual-v014-sdk-and-raw-list-evidence',passed:false,
  reviewerRole:'Independent AI technical reviewer, not SDK wrapper or database-fixture author',
  version:'0.1.4',node:process.version,build,sourceBindingsBefore:sourceBefore,runtimeBindingsBefore:runtimeBefore,
  databaseReexecuted:false,buildExecuted:false,dependencyInstallationExecuted:false,downloaded:false,
  formalPerformanceMeasured:false,humanAcceptance:false,contestApproval:false,checks:[]};
const check=async(name,fn)=>{try{const details=await fn();receipt.checks.push({name,passed:true,...details});}
  catch(error){receipt.checks.push({name,passed:false,error:{name:error.name,message:redact(error.message)}});}};
const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
const evidence=await import(pathToFileURL(resolve(root,'dist/evidence.mjs')).href);
const manual=load(resolve(root,'fixtures/list-v3/manual.json')),byId=new Map(manual.map(row=>[row.id,row]));
const cycle=byId.get('two-key-read-append-cycle').traceText;
const oracleCases=[];
await check('actual-v014-runtime-and-source-byte-bindings',()=>{
  assert.equal(build.version,'0.1.4');assert.equal(sdk.version(),'0.1.4');
  assert.equal(build.sourceSha256,'4dd5beb88d618d60a7172aa9254b47d6f51018d664e9f89d655b0a11286fe233');
  assert.equal(bind(resolve(root,'dist/core.mjs')).sha256,build.coreSha256);
  assert.equal(bind(resolve(root,'dist/capture-core.mjs')).sha256,build.captureCoreSha256);
  assert.deepEqual(bind(resolve(root,'cmd/sdk.mjs')),bind(resolve(root,'dist/sdk.mjs')));
  return {core:build.coreSha256,captureCore:build.captureCoreSha256,sourceFiles:sourceFiles.length};
});
await check('71-frozen-histories-current-list-and-generic-field-parity',()=>{
  const results=[];
  for(const row of manual){
    assert.equal(hash(row.traceText),row.inputSha256);
    const trace=JSON.parse(row.traceText);
    if(trace?.traceSchema!==3||trace?.dataModel!=='append-list-v1')assert.throws(()=>sdk.analyzeListV3(row.traceText,row.options),TypeError);
    else{
      const got=sdk.analyzeListV3(row.traceText,row.options),generic=sdk.analyzeV3(row.traceText,row.options);
      assert.deepEqual(got,generic,row.id);assert.equal(got.status,row.expected.analysis,row.id);
      assert.deepEqual(sdk.normalizeListCaptureV3(row.traceText),sdk.normalizeCaptureV3(row.traceText),row.id);
      assert.deepEqual(sdk.verifyListV3(row.traceText,got),sdk.verifyV3(row.traceText,got),row.id);
      results.push({id:row.id,status:got.status,reportSha256:hash(JSON.stringify(got)),complete:got.coverage.complete});
    }
    oracleCases.push({id:'manual/'+row.id,traceText:row.traceText,options:row.options,expected:row.expected.analysis});
  }
  assert.equal(manual.length,71);save('manual-results.json',results);return {histories:71};
});
await check('four-original-malformed-capsules-reject-fixed-model-without-exception',()=>{
  const results=[];
  for(const raw of ['{','','{"incomplete":','not json']){
    const report=sdk.analyzeV3(raw),capsule=sdk.makeCapsuleV3(raw,report);
    const generic=sdk.replayCapsuleV3(capsule),list=sdk.replayListCapsuleV3(capsule);
    assert.equal(generic.valid,true);assert.equal(generic.status,'invalid');assert.equal(list.valid,false);
    results.push({raw,generic,list});
  }
  const duplicate=cycle.replace('{','{"dataModel":"append-list-v1",');
  const diagnostic=sdk.replayListCapsuleV3(sdk.makeListCapsuleV3(duplicate));
  assert.equal(diagnostic.valid,true);assert.equal(diagnostic.status,'invalid');assert.equal(diagnostic.coverageComplete,false);
  save('malformed-regression.json',results);return {originalFailureInputs:4,reproducibleInvalidListDiagnosticPreserved:true};
});
await check('source-outcome-capacity-and-independent-budgets-stay-visible',()=>{
  const cases=[...['unknown-item-source','disconnect-keeps-unknown','future-producer-does-not-repair-source'].map(id=>[id,byId.get(id).traceText,{}]),
    ['maxStates0',cycle,{maxStates:0}],['maxOperations0',cycle,{maxOperationChecks:0}],
    ...['seven-committed-exceeds-capacity','129-operations-exceeds-capacity'].map(id=>[id,byId.get(id).traceText,{}])];
  for(const [id,raw,options] of cases){
    const report=sdk.analyzeListV3(raw,options);assert.deepEqual(report,sdk.analyzeV3(raw,options));
    assert.equal(report.status,'inconclusive');assert.equal(report.normalized.history,null);
    assert.deepEqual(report.normalized.observations,JSON.parse(raw).events);
    const replay=sdk.replayListCapsuleV3(sdk.makeListCapsuleV3(raw,report));
    assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');
    if(report.coverage.complete===false)assert.equal(replay.coverageComplete,false);
    oracleCases.push({id:'budget/'+id,traceText:raw,options,expected:'inconclusive'});
  }
  for(const options of [{maxChecks:0},{maxChecks:256,analysisOptions:{maxStates:0}}]){
    const got=sdk.reduceListV3(cycle,options);assert.deepEqual(got,sdk.reduceV3(cycle,options));
    assert.equal(got.oneMinimal,false);assert.equal(got.checks,0);
  }
  return {inconclusiveInputs:cases.length,independentReductionBudgetChecks:2};
});
await check('old-v013-real-postgres-v2-and-list-v3-capsules-replay',()=>{
  const legacy=resolve(here,'legacy-v013');mkdirSync(legacy,{recursive:true});
  const original=resolve(root,'verification/releases/0.1.3/postgres');
  const oldReceipt=load(resolve(original,'receipt.json'));
  assert.equal(oldReceipt.version,'0.1.3');assert.equal(oldReceipt.actualDatabaseExecution,true);assert.equal(oldReceipt.passed,true);
  const outputs=[];
  for(const name of ['rr.capsule.json','serial.capsule.json','mini.capsule.json']){
    const raw=readFileSync(resolve(original,name),'utf8'),capsule=JSON.parse(raw);
    assert.equal(capsule.engineVersion,'0.1.3');
    const result=evidence.replayCapsule(raw);assert.equal(result.valid,true,name);
    copyFileSync(resolve(original,name),resolve(legacy,name));outputs.push({name,origin:'Actual v0.1.3 PostgreSQL capture',...bind(resolve(legacy,name)),result});
  }
  copyFileSync(resolve(original,'receipt.json'),resolve(legacy,'postgres-receipt.json'));
  const oldList=resolve(root,'verification/list-v3/acceptance-2026-10-22T11-38-04-456Z/genuine-list-v3.capsule.json');
  const listText=readFileSync(oldList,'utf8');assert.equal(JSON.parse(listText).engineVersion,'0.1.3');
  const listReplay=sdk.replayListCapsuleV3(listText);assert.equal(listReplay.valid,true);
  copyFileSync(oldList,resolve(legacy,'synthetic-list-v3.capsule.json'));
  outputs.push({name:'synthetic-list-v3.capsule.json',origin:'Synthetic frozen list interpreter case, not a database capture',...bind(resolve(legacy,'synthetic-list-v3.capsule.json')),result:listReplay});
  save('legacy-results.json',outputs);return {realPostgresV2Capsules:3,syntheticListV3Capsules:1};
});

await check('actual-v014-three-to-two-roundtrip-and-every-single-deletion',()=>{
  const work=mkdtempSync(resolve(root,'artifacts/l14x-'));
  const p=spawnSync(process.execPath,['examples/list-roundtrip.mjs','--out-root',work],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:1024*1024});
  save('example-process.json',{exitCode:p.status,stdout:redact(p.stdout),stderr:redact(p.stderr),error:p.error?.name||null});
  assert.equal(p.error,undefined);assert.equal(p.status,0,p.stderr);
  const demo=JSON.parse(p.stdout);assert.equal(demo.version,'0.1.4');assert.equal(demo.passed,true);
  assert.equal(demo.originalTransactions,3);assert.equal(demo.reducedTransactions,2);assert.equal(demo.oneMinimal,true);assert.equal(demo.replayValid,true);
  const folder=resolve(work,demo.outputDirectory),publicExample=resolve(run,'example');mkdirSync(publicExample);
  for(const entry of demo.files){assert.deepEqual(bind(resolve(folder,entry.file)),{sha256:entry.sha256,bytes:entry.bytes});copyFileSync(resolve(folder,entry.file),resolve(publicExample,entry.file));}
  copyFileSync(resolve(folder,'receipt.json'),resolve(publicExample,'receipt.json'));
  const originalText=readFileSync(resolve(folder,'input.json'),'utf8'),reduction=load(resolve(folder,'reduction.json'));
  assert.equal(sdk.analyzeListV3(originalText).status,'violation');assert.equal(sdk.analyzeListV3(reduction.reducedCapture).status,'violation');
  assert.equal(sdk.replayListCapsuleV3(readFileSync(resolve(folder,'case.capsule.json'),'utf8')).valid,true);
  oracleCases.push({id:'example/original',traceText:originalText,expected:'violation'});
  oracleCases.push({id:'example/reduced',traceText:JSON.stringify(reduction.reducedCapture),expected:'violation'});
  for(const tx of reduction.report.normalized.transactions){
    const deleted=structuredClone(reduction.reducedCapture);
    deleted.events=deleted.events.filter(event=>event.tx!==tx.id).map((event,index)=>({...event,seq:index+1}));
    assert.equal(sdk.analyzeListV3(deleted).status,'consistent');
    oracleCases.push({id:'example/delete-'+tx.id,traceText:JSON.stringify(deleted),expected:'consistent'});
  }
  return {originalTransactions:3,reducedTransactions:2,singleDeletesChecked:2,sourceAuthenticityClaimed:false};
});

// Independently project the literal fixture SQL cells; never infer commit order
// from reply ordering or write these fixture facts back into the semantic trace.
function sqlAudit(trace,sql,finalLists,name){
  const byTx=new Map();for(const row of sql){if(!byTx.has(row.tx))byTx.set(row.tx,[]);byTx.get(row.tx).push(row);}
  const committed=[];let reads=0,appends=0,commitAcks=0,rollbackAcks=0,serverErrors=0;
  for(let i=0;i<sql.length;i++)assert.equal(sql[i].ordinal,i+1);
  for(const [tx,rows] of byTx){
    const events=trace.events.filter(event=>event.tx===tx),data=events.filter(event=>['list_read','append'].includes(event.kind));
    let index=0;let writes=[];let stack=[];
    const controls=events.filter(event=>['savepoint','rollback_to','release'].includes(event.kind));let controlIndex=0;
    for(const row of rows){
      if(row.sqlstate){assert.ok(['40001','40P01'].includes(row.sqlstate));assert.equal(row.diagnosticSqlstate,row.sqlstate);serverErrors++;continue;}
      if(/^SELECT items FROM /.test(row.sql)){
        assert.equal(row.rowcount,1);assert.equal(row.rows.length,1);assert.ok(Array.isArray(row.rows[0][0]));
        assert.deepEqual(data[index++],{...data[index-1],kind:'list_read',tx,key:row.parameters[0],items:row.rows[0][0]});reads++;
      }else if(/^UPDATE .* SET items=items \|\| %s::jsonb WHERE key=%s RETURNING items$/.test(row.sql)){
        assert.equal(row.rowcount,1);const requested=JSON.parse(row.parameters[0]);assert.equal(requested.length,1);
        assert.deepEqual(row.rows[0][0].at(-1),requested[0]);
        const wanted={kind:'append',tx,key:row.parameters[1],...requested[0]};
        assert.deepEqual(Object.fromEntries(Object.keys(wanted).map(key=>[key,data[index]?.[key]])),wanted);index++;
        writes.push({key:row.parameters[1],...requested[0]});appends++;
      }else if(row.sql.startsWith('SAVEPOINT ')){
        const mark=row.sql.match(/^SAVEPOINT "([a-z_]+)"$/);assert.ok(mark);const event=controls[controlIndex++];
        assert.equal(event.kind,'savepoint');assert.equal(event.name,mark[1]);stack.push({name:mark[1],instance:event.instance,length:writes.length});
      }else if(row.sql.startsWith('ROLLBACK TO SAVEPOINT ')||row.sql.startsWith('RELEASE SAVEPOINT ')){
        const match=row.sql.match(/^(ROLLBACK TO|RELEASE) SAVEPOINT "([a-z_]+)"$/);assert.ok(match);
        const position=stack.findLastIndex(mark=>mark.name===match[2]);assert.ok(position>=0);
        const event=controls[controlIndex++];assert.equal(event.instance,stack[position].instance);
        if(match[1]==='ROLLBACK TO'){assert.equal(event.kind,'rollback_to');writes=writes.slice(0,stack[position].length);stack=stack.slice(0,position+1);}
        else{assert.equal(event.kind,'release');stack=stack.slice(0,position);}
      }else if(row.sql==='COMMIT'){
        if(row.commandTag==='COMMIT'){
          committed.push(...writes);commitAcks++;
          if(name==='injected-commit-ack-loss'){assert.ok(events.some(event=>event.kind==='disconnect'));assert.ok(!events.some(event=>event.kind==='commit_ok'));}
          else assert.ok(events.some(event=>event.kind==='commit_ok'));
        }else{assert.equal(row.commandTag,'ROLLBACK');assert.ok(events.some(event=>event.kind==='rollback_ok'));rollbackAcks++;}
        writes=[];
      }else if(row.sql==='ROLLBACK'){assert.equal(row.commandTag,'ROLLBACK');assert.ok(events.some(event=>event.kind==='rollback_ok'));writes=[];rollbackAcks++;}
      else{assert.match(row.sql,/^BEGIN ISOLATION LEVEL (REPEATABLE READ|SERIALIZABLE)$/);assert.equal(row.commandTag,'BEGIN');assert.ok(events.some(event=>event.kind==='begin'));}
    }
    assert.equal(index,data.length);assert.equal(controlIndex,controls.length);
    for(const event of events.filter(event=>event.commitResponse)){
      const request=trace.events[event.commitResponse.request-1];assert.equal(request.kind,'commit_request');assert.equal(request.tx,tx);
      const response=rows.find(row=>row.sql==='COMMIT');assert.ok(response);
      if(event.commitResponse.sqlstate){assert.equal(response.sqlstate,event.commitResponse.sqlstate);assert.equal(response.diagnosticSqlstate,response.sqlstate);assert.equal(response.transactionStatus,'IDLE');}
      else assert.equal(response.commandTag,event.commitResponse.commandTag);
    }
  }
  for(const key of Object.keys(finalLists)){
    const expected=[...(trace.events[0].initial[key]||[]),...committed.filter(item=>item.key===key).map(({id,value})=>({id,value}))];
    const sort=items=>[...items].sort((a,b)=>a.id.localeCompare(b.id));assert.deepEqual(sort(finalLists[key]),sort(expected));
  }
  return {reads,appends,commitAcks,rollbackAcks,serverErrors};
}
await check('all-120-actual-pg-cases-bind-source-log-cells-model-and-capsules',()=>{
  const phasePath=resolve(root,'verification/releases/0.1.4/list-database-20261022T122254Z-de29c8ae.json'),phase=load(phasePath);
  assert.equal(phase.version,'0.1.4');assert.equal(phase.passed,true);assert.equal(phase.actualDatabaseExecution,true);
  assert.deepEqual(phase.buildManifestBefore,build);assert.deepEqual(phase.buildManifestAfter,build);
  const directory=resolve(root,'verification',phase.receipts.list.path),raw=load(resolve(directory,'database-receipt.json')),model=load(resolve(directory,'model-receipt.json'));
  assert.equal(bind(resolve(directory,'database-receipt.json')).sha256,phase.receipts.list.sha256);
  assert.equal(bind(resolve(directory,'model-receipt.json')).sha256,phase.receipts.listModel.sha256);
  assert.equal(raw.passed,true);assert.equal(raw.actualDatabaseExecution,true);assert.equal(raw.ownedSchemaCleanup,true);
  assert.equal(raw.serverAckOrderUsedAsCommitOrder,false);assert.equal(raw.cases.length,120);assert.deepEqual(model.build,build);
  assert.equal(model.rawDatabaseExecutionReceipt.sha256,bind(resolve(directory,'database-receipt.json')).sha256);
  for(const [name,sha] of Object.entries(model.sourceBindings))assert.equal(bind(resolve(root,name)).sha256,sha,name);
  assert.equal(bind(resolve(root,'experiments/list_v3/postgres.py')).sha256,raw.sourceSha256);
  for(const entry of model.bindings)assert.deepEqual(bind(resolve(directory,entry.file)),{sha256:entry.sha256,bytes:entry.bytes});
  const counts={},results=[];let rawFiles=0;
  for(const row of raw.cases){
    assert.equal(row.passed,true);counts[row.name]=(counts[row.name]||0)+1;
    const folder=resolve(directory,row.directory);for(const entry of row.files){assert.deepEqual(bind(resolve(folder,entry.file)),{sha256:entry.sha256,bytes:entry.bytes});rawFiles++;}
    const traceText=readFileSync(resolve(folder,'trace.json'),'utf8'),trace=JSON.parse(traceText),sql=lines(resolve(folder,'sql-results.jsonl'));
    assert.deepEqual(trace.events,lines(resolve(folder,'events.jsonl')));
    const logCheck=sqlAudit(trace,sql,row.serverFinalLists,row.name);
    const report=sdk.analyzeListV3(traceText);assert.deepEqual(report,sdk.analyzeV3(traceText));assert.deepEqual(report,load(resolve(folder,'report.json')));
    assert.equal(report.status,row.expectedModelStatus);assert.equal(report.normalized.history,null);
    const capsule=readFileSync(resolve(folder,'capsule.json'),'utf8'),replay=sdk.replayListCapsuleV3(capsule);assert.equal(replay.valid,true);assert.equal(replay.status,report.status);
    if(row.name==='injected-commit-ack-loss'){assert.ok(row.faultInjection);assert.equal(report.status,'inconclusive');assert.equal(report.coverage.complete,false);}
    oracleCases.push({id:'actual-pg/'+row.directory,traceText,expected:report.status});
    results.push({directory:row.directory,status:report.status,report:bind(resolve(folder,'report.json')),capsule:bind(resolve(folder,'capsule.json')),rawSql:logCheck});
  }
  assert.equal(Object.keys(counts).length,6);for(const count of Object.values(counts))assert.equal(count,20);
  save('actual-pg-120-results.json',results);return {actualEvidenceOrigin:rel(directory),rawFilesVerified:rawFiles,modelFilesVerified:model.bindings.length,cases:120,scenarios:counts,databaseReexecuted:false,phaseReceipt:bind(phasePath)};
});
await check('independent-frozen-python-interpreter-manual-database-and-single-delete-results',()=>{
  save('oracle-inputs.json',oracleCases);
  const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
  const code="import importlib.util,sys,json; p=sys.argv[1]; s=importlib.util.spec_from_file_location('independent_list_reference',p); m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m); cases=json.load(open(sys.argv[2],encoding='utf8')); print(json.dumps([{'id':c['id'],'reference':m.reference(c['traceText'],c.get('options'))} for c in cases],ensure_ascii=True))";
  const processResult=spawnSync(python,['-B','-c',code,resolve(root,'scripts/list-v3-oracle.py'),resolve(run,'oracle-inputs.json')],{cwd:root,encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:8*1024*1024});
  save('oracle-process.json',{exitCode:processResult.status,stderr:redact(processResult.stderr),error:processResult.error?.name||null});
  assert.equal(processResult.error,undefined);assert.equal(processResult.status,0,processResult.stderr);
  const reference=JSON.parse(processResult.stdout);assert.equal(reference.length,oracleCases.length);
  for(let i=0;i<reference.length;i++){assert.equal(reference[i].id,oracleCases[i].id);assert.equal(reference[i].reference.analysis,oracleCases[i].expected,reference[i].id);}
  save('oracle-results.json',reference);return {cases:reference.length,fixtureExpectedResultsUnchanged:true,interpreter:bind(resolve(root,'scripts/list-v3-oracle.py'))};
});
receipt.sourceBindingsAfter=inventory(sourceFiles);receipt.runtimeBindingsAfter=inventory(runtimeFiles);
receipt.sourceUnchanged=JSON.stringify(sourceBefore)===JSON.stringify(receipt.sourceBindingsAfter);
receipt.runtimeUnchanged=JSON.stringify(runtimeBefore)===JSON.stringify(receipt.runtimeBindingsAfter);
receipt.passed=receipt.checks.every(row=>row.passed)&&receipt.sourceUnchanged&&receipt.runtimeUnchanged;
receipt.implementation=bind(fileURLToPath(import.meta.url));save('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,groups:receipt.checks.length,failures:receipt.checks.filter(row=>!row.passed),receipt:rel(resolve(run,'receipt.json'))}));
if(!receipt.passed)process.exitCode=1;
