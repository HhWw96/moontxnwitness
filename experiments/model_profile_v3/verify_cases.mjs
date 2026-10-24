// Read-only original database inputs; offline independently compiled projection
// and frozen existing Python model interpreters, never a new database run.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {sourceFingerprint} from '../../scripts/build-fingerprint.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
assert.equal(process.argv.length,4,'Usage: node verify_cases.mjs RETAINED_SUITE NEW_OFFLINE_OUTPUT');
const original=resolve(process.argv[2]),output=resolve(process.argv[3]);mkdirSync(output,{recursive:false});
const sha=x=>createHash('sha256').update(x).digest('hex'),load=p=>JSON.parse(readFileSync(p,'utf8'));
const save=(name,x)=>writeFileSync(resolve(output,name),typeof x==='string'?x:JSON.stringify(x,null,2)+'\n',{flag:'wx'});
const database=load(resolve(original,'database-receipt.json'));assert.equal(database.status,'passed');assert.equal(database.actualDatabaseExecution,true);
assert.equal(database.sourceUnchanged,true);assert.equal(database.cases.length,10);
const build=load(resolve(root,'dist/build-manifest.json'));assert.equal(build.sourceSha256,sourceFingerprint(root));
assert.equal(build.coreSha256,sha(readFileSync(resolve(root,'dist/core.mjs'))));
const runtime=resolve(output,'runtime');mkdirSync(runtime);
for(const name of ['core.mjs','capture-core.mjs','build-manifest.json','THIRD_PARTY_NOTICES.txt'])copyFileSync(resolve(root,'dist',name),resolve(runtime,name));
const core=await import(pathToFileURL(resolve(runtime,'core.mjs')).href);
const receipt={kind:'configured-model-driver-offline-projection',passed:false,actualDatabaseExecution:false,
  formalPerformanceMeasurement:false,sourceDatabaseReceiptSha256:sha(readFileSync(resolve(original,'database-receipt.json'))),
  build,cases:[],independentHumanOrGPTAcceptance:false};
const python=process.env.MTW_PYTHON||(process.platform==='win32'?'python':'python3');
for(const item of database.cases){
  const result={case:item.case,passed:false};
  try{
    const text=readFileSync(resolve(original,item.case,'profile-source.json'),'utf8');
    assert.equal(sha(text),item.sourceEnvelope.sha256);
    const report=JSON.parse(core.model_profile_source_v3_json(text,'{}'));
    save(item.case+'-projection.json',report);result.status=report.status;result.mappingAccepted=report.analysisCoverageAccepted;
    if(item.expectedProjection==='inconclusive'){
      assert.equal(report.status,'inconclusive');assert.equal(report.analysisCoverageAccepted,false);assert.equal(report.derivedTrace,null);
    }else{
      assert.equal(report.analysisCoverageAccepted,true,JSON.stringify(report.mappingCoverage));
      assert.equal(report.status,item.expectedSerialStatus);
      assert.equal(report.originalDiagnosticCoverage.complete,false);
      const derived=JSON.stringify(report.derivedTrace,null,2)+'\n';save(item.case+'-derived-trace.json',derived);
      const oracleName=item.model==='append-list-v1'?'list-v3-oracle.py':'relation-v3-oracle.py';
      const oracle=readFileSync(resolve(root,'scripts',oracleName));
      const oraclePath=resolve(output,item.case+'-independent-oracle.py');writeFileSync(oraclePath,oracle,{flag:'wx'});
      const run=spawnSync(python,['-B',oraclePath,'--trace',resolve(output,item.case+'-derived-trace.json')],
        {encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024,env:{...process.env,TEMP:output,TMP:output}});
      assert.equal(run.status,0,run.stderr);const independent=JSON.parse(run.stdout);save(item.case+'-oracle.json',independent);
      assert.equal(independent.analysis||independent.status,report.status);result.independentOracleAgreement=true;
      for(const[k,name]of Object.entries({traceSha256:'traceText',sourceJournalSha256:'sourceJournalText',lifecycleSha256:'lifecycleText',journalIndexSha256:'journalIndexText'}))
        assert.equal(report.sourceBindings[k],sha(JSON.parse(text)[name]));
    }
    result.passed=true;
  }catch(error){result.error=String(error.message);}
  receipt.cases.push(result);
}
receipt.passed=receipt.cases.length===10&&receipt.cases.every(c=>c.passed);
assert.equal(sourceFingerprint(root),build.sourceSha256,'Source changed during offline check');
save('receipt.json',receipt);console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.length,failures:receipt.cases.filter(c=>!c.passed)}));
if(!receipt.passed)process.exitCode=1;
