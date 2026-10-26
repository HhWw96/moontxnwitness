// Actual original public027 runtime through the new fixed worker; not a v028 consumer test.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
import {PUBLIC027_FIXTURE_MANIFEST_SHA256} from './public027-fixture-binding.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),fixtures=resolve(root,'fixtures/compat-v027'),out=resolve(process.argv[2]);assert.equal(process.argv.length,3);mkdirSync(out);
const sha=x=>createHash('sha256').update(x).digest('hex'),enc=x=>JSON.stringify(x,null,2)+'\n',checks=[];let launches=0;
const spawn=childProcess.spawnSync;childProcess.spawnSync=(...a)=>{launches++;return spawn(...a);};syncBuiltinESMExports();
const receipt={format:'actual-public027-fixed-worker-smoke/v1',passed:false,actualPublicRuntimeExecuted:true,actualNewConsumerExecuted:false,actualCompilationExecuted:false,actualDatabaseExecuted:false,expectedRegenerated:false,checks};
const record=(name,fn)=>{fn();checks.push({name,passed:true});};
try{
 const raw=readFileSync(resolve(fixtures,'manifest.json'));assert.equal(sha(raw),PUBLIC027_FIXTURE_MANIFEST_SHA256);const m=JSON.parse(raw);assert.equal(m.cases.length,46);
 const bound=r=>{const b=readFileSync(resolve(fixtures,r.file));assert.equal(b.length,r.bytes);assert.equal(sha(b),r.sha256);return b;};
 for(const r of m.cases)for(const k of ['input','report','capsule','producerReplay','producerVerification'])bound(r[k]);
 const wrapper=await import(new URL('../cmd/legacy-v027.mjs',import.meta.url));assert.equal(launches,0,'Import must not launch a worker');
 const descriptor={'orm-profile':['verify-orm','replay-orm'],'category-classification':['verify-classification','replay-classification'],'model-classification':['verify-models','replay-models'],'model-profile':['verify-model-profile','replay-model-profile']};
 let families=0;
 for(const row of m.cases){if(!descriptor[row.type])continue;const [verify,replay]=descriptor[row.type],input=bound(row.input).toString('utf8'),report=JSON.parse(bound(row.report)),capsule=bound(row.capsule).toString('utf8');families++;
  record(row.name+' fixed original verifier exact result',()=>{const r=wrapper.callLegacyV027(verify,[input,report,row.requestOptions]);assert.deepEqual(r,JSON.parse(bound(row.producerVerification)));});
  record(row.name+' fixed original capsule exact result',()=>{const r=wrapper.callLegacyV027(replay,[capsule]);assert.deepEqual(r,JSON.parse(bound(row.producerReplay)));});
 }
 for(const type of Object.keys(descriptor)){
  const row=m.cases.find(r=>r.type===type),[verify,replay]=descriptor[type],input=bound(row.input).toString('utf8'),report=JSON.parse(bound(row.report)),capsule=JSON.parse(bound(row.capsule));
  record(type+' original report rejects false conclusion',()=>{report.status='forged';assert.equal(wrapper.callLegacyV027(verify,[input,report,row.requestOptions]).valid,false);});
  record(type+' rehashed original capsule rejects false conclusion',()=>{const r=JSON.parse(capsule.reportText);r.status='forged';capsule.reportText=JSON.stringify(r);capsule.reportSha256=sha(capsule.reportText);assert.equal(wrapper.callLegacyV027(replay,[enc(capsule)]).valid,false);});
 }
 record('all raw original producer inputs expectations and runtime preserved',()=>{for(const r of m.cases)for(const k of ['input','report','capsule','producerReplay','producerVerification'])bound(r[k]);for(const r of Object.values(m.producerFiles))bound(r);assert.equal(sha(readFileSync(resolve(fixtures,'manifest.json'))),PUBLIC027_FIXTURE_MANIFEST_SHA256);});
 receipt.passed=true;receipt.actualHistoricalFamilies=families;receipt.actualFixedWorkerLaunches=launches;receipt.fixtureManifestSha256=PUBLIC027_FIXTURE_MANIFEST_SHA256;
}catch(e){receipt.failure={name:e.name,message:e.message};process.exitCode=1;}
writeFileSync(resolve(out,'receipt.json'),enc(receipt),{flag:'wx'});console.log(JSON.stringify({passed:receipt.passed,checks:checks.length,families:receipt.actualHistoricalFamilies,launches:receipt.actualFixedWorkerLaunches,failure:receipt.failure??null}));