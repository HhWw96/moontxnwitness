// Explicit experimental fixture; no production application/credentials emitted.
import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {normalizeCapture,analyzeWithOptions,shrinkWithOptions,version} from '../../dist/sdk.mjs';
import {makeCapsule,replayCapsule} from '../../dist/evidence.mjs';

const args=process.argv.slice(2);
const folder=args.indexOf('--output')>=0 ? resolve(args[args.indexOf('--output')+1]) : null;
if(!folder || !args.includes('--schema'))throw Error('Use --schema new_mtw_provenance_schema --output new_folder');
const digest=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const buildManifest=JSON.parse(readFileSync('dist/build-manifest.json','utf8'));
// Capture provenance before the database run. These are metadata, not new
// normalization/analysis rules, and do not retrofit older run receipts.
const captureSource={
  adapterSha256:digest('integrations/python/moontxnwitness_capture/capture.py'),
  analysisCoreSha256:digest('dist/core.mjs'),
  captureCoreSha256:digest('dist/capture-core.mjs'),
  buildManifestSha256:digest('dist/build-manifest.json'),
  buildManifestSourceSha256:buildManifest.sourceSha256,
};
const child=spawnSync(process.env.MTW_PYTHON || (process.platform==='win32'?'python':'python3'),
  ['experiments/provenance/capture_profile_postgres.py',...args],{encoding:'utf8',windowsHide:true});
if(child.stdout)process.stdout.write(child.stdout);
if(child.stderr)process.stderr.write(child.stderr);
if(child.status!==0)process.exit(child.status??1);
const receipt=JSON.parse(readFileSync(resolve(folder,'profile-database.json'),'utf8'));
let capsules=0;
try {
  for(const item of receipt.scenarios){
    const normalized=normalizeCapture(readFileSync(resolve(folder,item.trace),'utf8'));
    writeFileSync(resolve(folder,item.name+'.coverage.json'),JSON.stringify(normalized,null,2)+'\n');
    assert.equal(normalized.status,item.expectedStatus,item.name+': '+JSON.stringify(normalized));
    if(normalized.status!=='ready'){assert.equal(normalized.history,null);continue;}
    const report=analyzeWithOptions(normalized.history);
    assert.equal(report.status,item.expectedVerdict,item.name);
    writeFileSync(resolve(folder,item.name+'.report.json'),JSON.stringify(report,null,2)+'\n');
    const capsule=makeCapsule(JSON.stringify(normalized.history),report);
    assert.equal(replayCapsule(capsule).valid,true,item.name);
    writeFileSync(resolve(folder,item.name+'.capsule.json'),capsule);
    capsules++;
    if(report.status==='violation'){
      const reduced=shrinkWithOptions(normalized.history);
      assert.equal(reduced.reducedHistory.transactions.length,2,item.name);
      assert.equal(reduced.oneMinimal,true,item.name);
      writeFileSync(resolve(folder,item.name+'.reduction.json'),JSON.stringify(reduced,null,2)+'\n');
    }
  }
  Object.assign(receipt,{status:'passed',passed:true,coreVersion:version(),replayedCapsules:capsules,
    captureSource,
    normalizerScope:'register projection only; no general SQL or isolation-level classification',
    generatedAt:new Date().toISOString(),
    e2eSha256:digest('experiments/provenance/capture_profile_e2e.mjs')});
  writeFileSync(resolve(folder,'profile-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log('Experimental profile: '+receipt.scenarios.length+' actual PostgreSQL scenarios, '+capsules+' replayed capsules.');
} catch(error){
  writeFileSync(resolve(folder,'profile-core-failure.json'),JSON.stringify({status:'failed',phase:'core',
    errorClass:error.name,message:error.message,actualDatabaseExecution:true},null,2)+'\n');
  throw error;
}
