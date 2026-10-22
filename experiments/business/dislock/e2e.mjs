import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {normalizeCapture,analyzeWithOptions,version} from '../../../dist/sdk.mjs';
import {makeCapsule,replayCapsule} from '../../../dist/evidence.mjs';

const args=process.argv.slice(2);
const outputIndex=args.indexOf('--output');
if(outputIndex<0 || !args.includes('--schema'))throw Error('Use --schema new_controlled_schema --output new_folder');
const folder=resolve(args[outputIndex+1]);
const digest=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const binding=name=>{
  const bytes=readFileSync(resolve(folder,name));
  return {path:name,sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length};
};
const manifest=JSON.parse(readFileSync('dist/build-manifest.json','utf8'));
const captureSource={adapterSha256:digest('integrations/python/moontxnwitness_capture/capture.py'),
  analysisCoreSha256:digest('dist/core.mjs'),captureCoreSha256:digest('dist/capture-core.mjs'),
  buildManifestSha256:digest('dist/build-manifest.json'),buildManifestSourceSha256:manifest.sourceSha256,
  e2eSha256:digest('experiments/business/dislock/e2e.mjs')};
const implementationPaths=["integrations/python/moontxnwitness_capture/__init__.py", "integrations/python/moontxnwitness_capture/capture.py", "integrations/python/moontxnwitness_capture/_provenance.py", "integrations/python/moontxnwitness_capture/_column_profile.py", "integrations/python/moontxnwitness_capture/_initialization_guard.py", "integrations/python/moontxnwitness_capture/_source_inventory.py", "integrations/python/moontxnwitness_capture/presence.py"];
const implementationFiles=Object.fromEntries(implementationPaths.map(path=>[path,digest(path)]));
captureSource.implementationFiles=implementationFiles;
captureSource.compatibilityRole="experiments profile hashes bind aliases; implementationFiles binds actual package code";
const child=spawnSync(process.env.MTW_PYTHON || (process.platform==='win32'?'python':'python3'),
  ['experiments/business/dislock/postgres_test.py',...args],{encoding:'utf8',windowsHide:true});
if(child.stdout)process.stdout.write(child.stdout);
if(child.stderr)process.stderr.write(child.stderr);
if(child.status!==0)process.exit(child.status??1);
const receipt=JSON.parse(readFileSync(resolve(folder,'business-database.json'),'utf8'));
let capsules=0;
try{
  for(const[path,sha]of Object.entries(implementationFiles))assert.equal(digest(path),sha,"Implementation changed: "+path);
  const expectedImplementationKeys=implementationPaths.map(path=>path.slice('integrations/python/'.length)).sort();
  assert.equal(receipt.implementationSources.unchanged,true);
  assert.deepEqual(Object.keys(receipt.implementationSources.before).sort(),expectedImplementationKeys,'Incomplete implementation source inventory before execution');
  assert.deepEqual(Object.keys(receipt.implementationSources.after).sort(),expectedImplementationKeys,'Incomplete implementation source inventory after execution');
  assert.deepEqual(receipt.implementationSources.before,receipt.implementationSources.after,'Implementation source inventory changed during execution');
  for(const[path,item]of Object.entries(receipt.implementationSources.after)){
    assert.equal(implementationFiles["integrations/python/"+path],item.sha256,"Actual package source differs: "+path);
    assert.equal(readFileSync("integrations/python/"+path).length,item.bytes,"Actual package source size differs: "+path);
  }
  for(const item of receipt.scenarios){
    const normalized=normalizeCapture(readFileSync(resolve(folder,item.trace),'utf8'));
    const coverage=item.name+'.coverage.json';
    writeFileSync(resolve(folder,coverage),JSON.stringify(normalized,null,2)+'\n');
    item.projectionVersion='column-old-new-register-v0.1.2-experimental';
    item.artifactBindings={trace:binding(item.trace),coverage:binding(coverage)};
    if(item.protocol)item.artifactBindings.protocol=binding(item.protocol);
    assert.equal(normalized.status,item.expectedStatus,item.name+': '+JSON.stringify(normalized));
    if(normalized.status!=='ready'){assert.equal(normalized.history,null);continue;}
    const report=analyzeWithOptions(normalized.history);
    assert.equal(report.status,item.expectedVerdict,item.name);
    const history=item.name+'.history.json',reportFile=item.name+'.report.json';
    writeFileSync(resolve(folder,history),JSON.stringify(normalized.history,null,2)+'\n');
    writeFileSync(resolve(folder,reportFile),JSON.stringify(report,null,2)+'\n');
    const capsule=makeCapsule(JSON.stringify(normalized.history),report);
    assert.equal(replayCapsule(capsule).valid,true,item.name);
    const capsuleFile=item.name+'.capsule.json';
    writeFileSync(resolve(folder,capsuleFile),capsule);
    Object.assign(item.artifactBindings,{history:binding(history),report:binding(reportFile),capsule:binding(capsuleFile)});
    capsules++;
  }
  Object.assign(receipt,{status:'passed',passed:true,coreVersion:version(),captureSource,
    replayedCapsules:capsules,generatedAt:new Date().toISOString(),
    projection:{version:'column-old-new-register-v0.1.2-experimental',
      scope:'fixed existing leases; successful same-statement OLD reads and NEW writes; unsupported/failed predicates remain gaps',
      bindingClaim:'file SHA-256 and byte counts detect receipt/artifact mismatches; they do not authenticate collection or complete evidence v3'},
    analysisScope:'unique-version point-register projection; no proof of the entire lease/CLI/heartbeat system'});
  writeFileSync(resolve(folder,'business-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log('Frozen dislock business slice: '+receipt.scenarios.length+' actual PostgreSQL traces, '+capsules+' replayed capsules.');
}catch(error){
  writeFileSync(resolve(folder,'business-core-failure.json'),JSON.stringify({status:'failed',phase:'core',
    errorClass:error.name,message:error.message,actualDatabaseExecution:true},null,2)+'\n');
  throw error;
}
