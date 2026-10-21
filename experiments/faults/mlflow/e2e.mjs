// Read-only model/fault verification of retained actual database observations.
import assert from 'node:assert/strict';
import {readFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,relative,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {homedir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {analyzeV3,normalizeCaptureV3,inspectExecutionFailuresV3,verifyV3,makeCapsuleV3,replayCapsuleV3} from '../../../dist/sdk.mjs';
import {sourceFingerprint} from '../../../scripts/build-fingerprint.mjs';
import {writeImmutableEvidence} from '../../../scripts/performance-evidence.mjs';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const args=process.argv.slice(2);
assert.ok(args.length===1||(args.length===3&&args[1]==='--output'),
  'Usage: node experiments/faults/mlflow/e2e.mjs INPUT [--output NEW_DIRECTORY]');
const input=resolve(args[0]);
const output=resolve(args[2]||'verification/faults/mlflow/replay-'+new Date().toISOString().replace(/[:.]/g,'-'));
assert.ok(!existsSync(output),'Output must be new');
mkdirSync(output,{recursive:true});
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const binding=path=>{const b=readFileSync(path);return{sha256:hash(b),bytes:b.length};};
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const save=(name,value)=>{
  const text=typeof value==='string'?value:JSON.stringify(value,null,2)+'\n';
  writeImmutableEvidence(resolve(output,name),text);return binding(resolve(output,name));
};
const receipt={schema:1,passed:false,actualDatabaseExecution:false,
  sourceDatabaseExecutionRetained:true,scope:'Controlled unchanged MLflow component; no full server or isolation proof',
  sourceSha256:sourceFingerprint(root),build:read(resolve(root,'dist/build-manifest.json')),
  inputReceipt:binding(resolve(input,'receipt.json')),checks:[],cases:[],sourceBindings:{}};
const check=(name,fn)=>{try{fn();receipt.checks.push({name,passed:true});}catch(e){receipt.checks.push({name,passed:false,error:String(e.message||e)});throw e;}};
try{
  check('current-build-binding',()=>{
    assert.equal(receipt.sourceSha256,receipt.build.sourceSha256);
    assert.equal(binding(resolve(root,'dist/core.mjs')).sha256,receipt.build.coreSha256);
    assert.equal(binding(resolve(root,'dist/capture-core.mjs')).sha256,receipt.build.captureCoreSha256);
  });
  for(const file of ['experiments/faults/mlflow/e2e.mjs','cmd/sdk.mjs','cmd/evidence.mjs',
    'dist/core.mjs','dist/capture-core.mjs','dist/sdk.mjs','dist/evidence.mjs','dist/moontxnwitness.mjs'])
    receipt.sourceBindings[file]=binding(resolve(root,file));
  const database=read(resolve(input,'receipt.json'));
  check('actual-postgresql18-comparison',()=>{
    assert.equal(database.passed,true);assert.equal(database.actualDatabaseExecution,true);
    assert.ok(database.serverVersionNumber>=180000&&database.serverVersionNumber<190000);
    assert.equal(database.cases.length,2);
  });
  for(const label of ['before','fixed']){
    const folder=resolve(input,label),native=read(resolve(folder,'receipt.json'));
    const traceText=readFileSync(resolve(folder,'capture.json'),'utf8');
    const trace=JSON.parse(traceText),rawRows=read(resolve(folder,'final-rows.json'));
    check(label+'-native-bindings',()=>{
      assert.equal(native.passed,true);assert.equal(native.actualDatabaseExecution,true);
      assert.equal(native.G2Claim,false);assert.equal(native.isolationViolationClaim,false);
      assert.equal(native.runtimeSourceUnchanged,true);assert.equal(native.sqlObservationsComplete,true);
      assert.deepEqual(native.runtimeSourceBindings,native.runtimeSourceBindingsAfter);
      for(const [file,b] of Object.entries(native.runtimeSourceBindings)){
        assert.deepEqual(binding(resolve(root,file)),b);
        const bytes=gunzipSync(readFileSync(resolve(folder,'source-snapshots',basename(file)+'.gz')),{maxOutputLength:2*1024*1024});
        assert.equal(hash(bytes),b.sha256);assert.equal(bytes.length,b.bytes);
      }
      assert.equal(hash(Buffer.from(traceText)),native.captureSha256);
      assert.equal(binding(resolve(folder,'final-rows.json')).sha256,native.finalRowsSha256);
      assert.equal(binding(resolve(folder,'sql-executions.jsonl')).sha256,native.sqlExecutionsSha256);
      assert.equal(rawRows.length,1000);assert.equal(new Set(rawRows.map(r=>r[0])).size,1000);
      const winners=Object.entries(native.workers).filter(([,worker])=>worker.committed).map(([id])=>id==='A'?1:2);
      const expected=Math.max(...winners);
      for(const row of rawRows){assert.equal(row[1],expected);assert.equal(row[2],expected);assert.equal(row[3],expected);}
    });
    const executions=readFileSync(resolve(folder,'sql-executions.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
    check(label+'-actual-sql-failure-and-commit-counts',()=>{
      const errors=executions.filter(e=>e.phase==='error');
      assert.equal(native.originalBatchSize,500);assert.equal(native.keysEach,1000);
      assert.ok(executions.some(e=>e.phase==='before'&&e.executemany===true));
      assert.ok(executions.some(e=>e.phase==='after'&&e.executemany===true&&e.rowcount===1000));
      if(label==='before'){
        assert.equal(native.committed,1);assert.equal(native.errors.length,1);
        assert.equal(native.errors[0].sqlstate,'40P01');
        assert.equal(errors.length,1);assert.equal(errors[0].sqlstate,'40P01');
        assert.match(errors[0].sql,/FOR UPDATE/);
      }else{assert.equal(native.committed,2);assert.equal(native.errors.length,0);assert.equal(errors.length,0);}
    });
    const normalized=normalizeCaptureV3(traceText),report=analyzeV3(traceText),faults=inspectExecutionFailuresV3(traceText);
    check(label+'-fault-channel-keeps-isolation-inconclusive',()=>{
      assert.equal(normalized.status,'inconclusive');assert.equal(report.status,'inconclusive');
      assert.equal(report.evidence,null);assert.equal(report.coverage.complete,false);
      assert.equal(faults.valid,true);assert.equal(faults.modelViolationClaim,false);
      assert.equal(faults.databaseAuthenticityVerified,false);assert.equal(faults.certifiesFailureAbsence,false);
      assert.equal(faults.observedFaultCount,label==='before'?1:0);
      const statuses=normalized.transactions.map(tx=>tx.status);
      assert.equal(statuses.filter(s=>s==='committed').length,label==='before'?1:2);
      assert.equal(statuses.filter(s=>s==='aborted').length,label==='before'?1:0);
      assert.ok(!statuses.includes('unknown'));
      for(const fault of faults.faults){
        const rows=trace.events.find(e=>e.seq===fault.seq),statement=trace.events.find(e=>e.seq===fault.statement);
        assert.equal(rows.kind,'rows');assert.equal(rows.tx,statement.tx);assert.equal(rows.statement,statement.seq);
        assert.equal(statement.kind,'statement');assert.match(statement.sql,/FOR UPDATE/);
        assert.equal(rows.error.sqlstate,'40P01');assert.equal(fault.kind,'deadlock');
      }
    });
    const capsule=makeCapsuleV3(traceText,report);
    check(label+'-capsule-and-report-verification',()=>{
      assert.equal(verifyV3(traceText,report).valid,true);assert.equal(replayCapsuleV3(capsule).valid,true);
      const forged=structuredClone(report);forged.status='violation';
      assert.equal(verifyV3(traceText,forged).valid,false);
    });
    save(label+'.normalized.json',normalized);save(label+'.report.json',report);
    save(label+'.faults.json',faults);save(label+'.capsule.json',capsule);
    check(label+'-cli-recorded-failures',()=>{
      const cli=spawnSync(process.execPath,['dist/moontxnwitness.mjs','failures-v3',resolve(folder,'capture.json')],
        {cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:16*1024*1024});
      assert.equal(cli.status,0,cli.stderr);assert.deepEqual(JSON.parse(cli.stdout),faults);
    });
    receipt.cases.push({label,observedFaultCount:faults.observedFaultCount,committed:native.committed,
      capture:binding(resolve(folder,'capture.json')),nativeReceipt:binding(resolve(folder,'receipt.json'))});
  }
  check('source-and-runtime-stayed-frozen',()=>{
    assert.equal(sourceFingerprint(root),receipt.sourceSha256);
    for(const[file,b]of Object.entries(receipt.sourceBindings))assert.deepEqual(binding(resolve(root,file)),b);
  });
  receipt.passed=true;
}catch(e){
  let error=String(e.message||e);
  for(const path of [root,homedir()])error=error.replaceAll(path,'<private-path>').replaceAll(path.replaceAll('\\','/'),'<private-path>');
  receipt.error=error;
}finally{
  receipt.finishedAt=new Date().toISOString();save('receipt.json',receipt);
}
console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.length,checks:receipt.checks.length,
  actualDatabaseExecution:false,sourceDatabaseExecutionRetained:true,
  receipt:relative(root,resolve(output,'receipt.json')).replaceAll('\\','/'),
  failures:receipt.checks.filter(c=>!c.passed),error:receipt.error||null}));
if(!receipt.passed)process.exitCode=1;
