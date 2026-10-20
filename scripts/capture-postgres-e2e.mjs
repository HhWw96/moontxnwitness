import {spawnSync} from 'node:child_process';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {resolve, relative, sep} from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {normalizeCapture,analyzeWithOptions,shrinkWithOptions,version} from '../dist/sdk.mjs';
import {makeCapsule,replayCapsule} from '../dist/evidence.mjs';

const folder=resolve('verification/releases',version(),'capture',new Date().toISOString().replaceAll(/[:.]/g,'-'));
mkdirSync(folder,{recursive:true});
const child=spawnSync(process.env.MTW_PYTHON || (process.platform==='win32'?'python':'python3'),
  ['scripts/capture-postgres-test.py',folder],{encoding:'utf8',windowsHide:true});
if(child.stdout)process.stdout.write(child.stdout);
if(child.stderr)process.stderr.write(child.stderr);
if(child.status!==0){
  const failure=resolve('artifacts/capture-integration-failures',new Date().toISOString().replaceAll(/[:.]/g,'-'));
  mkdirSync(failure,{recursive:true});
  writeFileSync(resolve(failure,'driver.txt'),(child.stdout||'')+'\n'+(child.stderr||'')+'\n'+String(child.error||''));
  throw Error('Actual capture tests not completed: '+child.status+'; private diagnostics in artifacts/capture-integration-failures');
}
const receipt=JSON.parse(readFileSync(resolve(folder,'database.json'),'utf8'));
let replays=0;
for(const scenario of receipt.scenarios){
  const normalized=normalizeCapture(readFileSync(resolve(folder,scenario.trace),'utf8'));
  writeFileSync(resolve(folder,scenario.name+'.coverage.json'),JSON.stringify(normalized,null,2)+'\n');
  assert.equal(normalized.status,scenario.expectedStatus,scenario.name+': '+JSON.stringify(normalized));
  if(normalized.status!=='ready'){assert.equal(normalized.history,null);continue;}
  const report=analyzeWithOptions(normalized.history);
  assert.equal(report.status,scenario.expectedVerdict,scenario.name);
  writeFileSync(resolve(folder,scenario.name+'.report.json'),JSON.stringify(report,null,2)+'\n');
  const capsule=makeCapsule(JSON.stringify(normalized.history),report);
  assert.equal(replayCapsule(capsule).valid,true,scenario.name);
  writeFileSync(resolve(folder,scenario.name+'.capsule.json'),capsule);
  replays++;
  if(report.status==='violation'){
    const reduced=shrinkWithOptions(normalized.history);
    assert.equal(reduced.reducedHistory.transactions.length,2);
    assert.equal(reduced.oneMinimal,true);
    writeFileSync(resolve(folder,scenario.name+'.reduction.json'),JSON.stringify(reduced,null,2)+'\n');
  }
}
receipt.passed=true;receipt.version=version();receipt.replayedCapsules=replays;
const digest=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
receipt.captureSource={
  adapterSha256:digest('integrations/python/moontxnwitness_capture/capture.py'),
  captureCoreSha256:digest('dist/capture-core.mjs'),
  analysisCoreSha256:digest('dist/core.mjs'),
  fixtureSha256:digest('scripts/capture-postgres-test.py'),
  e2eSha256:digest('scripts/capture-postgres-e2e.mjs'),
};
receipt.generatedAt=new Date().toISOString();
writeFileSync(resolve(folder,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
writeFileSync('verification/capture-postgres.json',JSON.stringify({...receipt,path:relative(resolve('verification'),folder).split(sep).join('/')},null,2)+'\n');
console.log('Actual PostgreSQL capture, normalization, analysis and replay passed: '+receipt.scenarios.length+' scenarios.');
