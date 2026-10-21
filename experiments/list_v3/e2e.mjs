// Offline comparison of retained real SQL-derived fixture observations.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as sdk from '../../dist/sdk.mjs';
import {sourceFingerprint} from '../../scripts/build-fingerprint.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const folder=resolve(process.argv[2]||'');
if(process.argv.length!==3&&!(process.argv.length===5&&process.argv[3]==='--output'))throw new Error('Usage: node experiments/list_v3/e2e.mjs RETAINED_DATABASE_DIRECTORY [--output NEW_RECHECK_DIRECTORY]');
const output=process.argv[3]==='--output'?resolve(process.argv[4]):folder;
if(output!==folder)mkdirSync(output,{recursive:false});
const sha=raw=>createHash('sha256').update(raw).digest('hex');
const load=p=>JSON.parse(readFileSync(p,'utf8'));
const rawReceipt=readFileSync(resolve(folder,'database-receipt.json'));
const database=JSON.parse(rawReceipt);assert.equal(database.passed,true);assert.equal(database.actualDatabaseExecution,true);
assert.equal(database.sourceSha256,sha(readFileSync(resolve(root,'experiments/list_v3/postgres.py'))),'Database fixture source changed');
const build=load(resolve(root,'dist/build-manifest.json'));
assert.equal(build.sourceSha256,sourceFingerprint(root),'Analyzer source is stale');
assert.equal(build.coreSha256,sha(readFileSync(resolve(root,'dist/core.mjs'))),'Actual analysis runtime bytes differ from manifest');
assert.equal(build.captureCoreSha256,sha(readFileSync(resolve(root,'dist/capture-core.mjs'))),'Actual lifecycle runtime bytes differ from manifest');
for(const wrapper of['sdk.mjs','evidence.mjs','moontxnwitness.mjs'])assert.equal(sha(readFileSync(resolve(root,'dist',wrapper))),sha(readFileSync(resolve(root,'cmd',wrapper))),'Built wrapper is stale: '+wrapper);
const receipt={schema:1,passed:false,actualDatabaseExecution:false,rawDatabaseExecutionReceipt:{file:'database-receipt.json',sha256:sha(rawReceipt)},
  inputDatabaseDirectory:relative(root,folder).replaceAll('\\','/'),readOnlyDatabaseEvidence:output!==folder,
  sourceSha256:sha(readFileSync(fileURLToPath(import.meta.url))),build,
  sourceBindings:Object.fromEntries(['experiments/list_v3/postgres.py','experiments/list_v3/e2e.mjs','scripts/list-v3-oracle.py',
    'dist/build-manifest.json','dist/core.mjs','dist/capture-core.mjs','dist/sdk.mjs','dist/evidence.mjs','dist/moontxnwitness.mjs'].map(p=>[p,sha(readFileSync(resolve(root,p)))])),
  mappingScope:database.mappingScope,roundsPerScenario:database.roundsPerScenario,smokeOnly:database.smokeOnly,
  automaticG2OrPLClassification:false,cases:[],bindings:[]};
const oracleBytes=readFileSync(resolve(root,'scripts/list-v3-oracle.py'));
const oracleSnapshot=resolve(output,'independent-oracle-executed.py');
writeFileSync(oracleSnapshot,oracleBytes,{flag:'wx'});
receipt.executedOracleSnapshot={file:'independent-oracle-executed.py',bytes:oracleBytes.length,sha256:sha(oracleBytes)};
const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
for(const c of database.cases){const dir=resolve(folder,c.directory),destination=resolve(output,c.directory);if(output!==folder)mkdirSync(destination,{recursive:false});const actual={name:c.name,round:c.round,passed:false};try{
  for(const b of c.files){const raw=readFileSync(resolve(dir,b.file));assert.equal(raw.length,b.bytes);assert.equal(sha(raw),b.sha256);}
  const traceText=readFileSync(resolve(dir,'trace.json'),'utf8'),trace=JSON.parse(traceText);
  assert.deepEqual(readFileSync(resolve(dir,'events.jsonl'),'utf8').trim().split('\n').map(JSON.parse),trace.events);
  const p=spawnSync(python,['-B',oracleSnapshot,'--trace',resolve(dir,'trace.json')],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});assert.equal(p.status,0,p.stderr);
  const independent=JSON.parse(p.stdout);assert.equal(independent.analysis,c.expectedModelStatus);
  const normalized=sdk.normalizeCaptureV3(traceText),report=sdk.analyzeV3(traceText);
  assert.equal(report.status,c.expectedModelStatus);assert.deepEqual(normalized.observations,trace.events);assert.deepEqual(report.normalized,normalized);
  assert.equal(sdk.verifyV3(traceText,report).valid,true);
  const proof=sdk.makeCapsuleV3(traceText,report);assert.equal(sdk.replayCapsuleV3(proof).valid,true);
  for(const[name,raw]of[['report.json',JSON.stringify(report,null,2)+'\n'],['capsule.json',proof]]){writeFileSync(resolve(destination,name),raw,{flag:'wx'});receipt.bindings.push({file:c.directory+'/'+name,bytes:Buffer.byteLength(raw),sha256:sha(raw)});}
  actual.passed=true;actual.status=report.status;actual.normalization=normalized.status;actual.capsuleReproduced=true;
}catch(e){actual.error=String(e.message).replaceAll(root,'<workspace>').replaceAll(folder,'<retained-db-fixture>');}receipt.cases.push(actual);}
receipt.passed=receipt.cases.length===database.cases.length&&receipt.cases.every(c=>c.passed);
assert.equal(sha(readFileSync(resolve(root,'scripts/list-v3-oracle.py'))),sha(oracleBytes),'Original oracle changed during verification');
assert.equal(sourceFingerprint(root),build.sourceSha256,'Analyzer source changed during verification');
writeFileSync(resolve(output,'model-receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.length,roundsPerScenario:receipt.roundsPerScenario,smokeOnly:receipt.smokeOnly,
  failures:receipt.cases.filter(c=>!c.passed),actualDatabaseExecution:false,sourceDatabaseExecutionRetained:true}));
if(!receipt.passed)process.exitCode=1;
