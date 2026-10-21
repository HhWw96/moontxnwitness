import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const sourceRoot=path.resolve(process.argv[2]||process.cwd());
const hash=x=>createHash('sha256').update(x).digest('hex');
const before=await import(pathToFileURL(path.resolve('baseline/core.mjs')));
const after=await import(pathToFileURL(path.resolve('dist/core.mjs')));
const oldBuild=JSON.parse(fs.readFileSync('baseline/build-manifest.json'));
const newBuild=JSON.parse(fs.readFileSync('dist/build-manifest.json'));
assert.equal(hash(fs.readFileSync('baseline/core.mjs')),oldBuild.coreSha256);
assert.equal(hash(fs.readFileSync('dist/core.mjs')),newBuild.coreSha256);
const manifest=JSON.parse(fs.readFileSync(path.join(sourceRoot,'verification/fixtures/v010-comparison/manifest.json')));
const checks=[];
function compare(name,h,options={},shrink=false){
  const input=JSON.stringify(h),opts=JSON.stringify(options),fn=shrink?'shrink_options_json':'analyze_options_json';
  const original=before[fn](input,opts),candidate=after[fn](input,opts);
  if(original!==candidate){fs.writeFileSync('receipts/byte-first-failure.json',JSON.stringify({name,input,options,original,candidate},null,2)+'\n',{flag:'wx'});throw Error('Full bytes differ: '+name);}
  const result=JSON.parse(candidate);
  checks.push({name,inputSha256:hash(input),optionsSha256:hash(opts),outputSha256:hash(candidate),outputBytes:Buffer.byteLength(candidate),status:result.status,metrics:result.metrics??result.report?.metrics,checks:result.checks,oneMinimal:result.oneMinimal});
}
for(const row of manifest.cases){const bytes=fs.readFileSync(path.join(sourceRoot,row.file));assert.equal(hash(bytes),row.fixtureSha256);const c=JSON.parse(bytes);compare(c.name,c.history,{},c.operation==='shrink');}
for(const n of [6,7,8,9,10,11,12]){
  const row=manifest.cases.find(x=>x.name==='completion-impossible-'+n),h=JSON.parse(fs.readFileSync(path.join(sourceRoot,row.file))).history;
  for(const options of [{maxAttempts:0},{maxAttempts:1},{maxAttempts:107},{maxAttempts:108},{maxOperationChecks:0},{maxOperationChecks:1},{maxOperationChecks:147},{maxOperationChecks:148},{maxAttempts:2000,maxOperationChecks:5000,maxCachedStates:0},{maxAttempts:2000,maxOperationChecks:5000,maxCachedStates:1},{maxCachedStates:2},{maxCachedStates:50000}]) compare('completion-'+n+':'+JSON.stringify(options),h,options);
}
const large=JSON.parse(fs.readFileSync('inputs/reduction-512.json')).history;
for(const maxChecks of [0,1,2,3,256])compare('reduce512-checks-'+maxChecks,large,{maxChecks},true);
for(const options of [{analysisOptions:{maxAttempts:0}},{analysisOptions:{maxOperationChecks:0}},{maxChecks:3,analysisOptions:{maxCachedStates:0}}])compare('reduce512-'+JSON.stringify(options),large,options,true);
const textHist=(key,initial,id,version)=>({schemaVersion:1,initial:{[key]:initial},transactions:[{id,status:'committed',ops:[{type:'write',key,version},{type:'read',key,version}]}]});
for(const [key,initial,id,version] of [['键😀','零','事务𝄞','新'],['q"\\','old"','T\\','v\n'],['k','v0','A','v1'],['é'.repeat(256),'零','A','v1'],['😀'.repeat(128),'😀','😀','值']])compare('unicode-'+checks.length,textHist(key,initial,id,version));
const equivalence={schema:1,passed:true,diagnosticOnly:true,formalReleaseGateApplicable:false,baseline:oldBuild,candidate:newBuild,checks:checks.length,exactCompleteOutput:true,notes:'Complete output bytes include all fields, edge provenance, graph/search/reduction counters, budgets and evidence.',cases:checks};
fs.writeFileSync('receipts/v2-complete-byte-equivalence.json',JSON.stringify(equivalence,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({completeByteChecks:checks.length,passed:true}));
