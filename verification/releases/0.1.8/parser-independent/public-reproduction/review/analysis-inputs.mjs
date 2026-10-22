// Original117 cases/options/order; no SDK is loaded by this module.
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import {createHash} from 'node:crypto';
const hash=b=>createHash('sha256').update(b).digest('hex');
export function analysisCases(here){const sourceRoot=path.join(here,'inputs/source-root'),manifest=JSON.parse(fs.readFileSync(path.join(sourceRoot,'verification/fixtures/v010-comparison/manifest.json'))),checks=[];
function compare(name,h,options={},shrink=false){checks.push({name,input:JSON.stringify(h),optionsText:JSON.stringify(options),fn:shrink?'shrink_options_json':'analyze_options_json'});}
for(const row of manifest.cases){const bytes=fs.readFileSync(path.join(sourceRoot,row.file));assert.equal(hash(bytes),row.fixtureSha256);const c=JSON.parse(bytes);compare(c.name,c.history,{},c.operation==='shrink');}
for(const n of [6,7,8,9,10,11,12]){
  const row=manifest.cases.find(x=>x.name==='completion-impossible-'+n),h=JSON.parse(fs.readFileSync(path.join(sourceRoot,row.file))).history;
  for(const options of [{maxAttempts:0},{maxAttempts:1},{maxAttempts:107},{maxAttempts:108},{maxOperationChecks:0},{maxOperationChecks:1},{maxOperationChecks:147},{maxOperationChecks:148},{maxAttempts:2000,maxOperationChecks:5000,maxCachedStates:0},{maxAttempts:2000,maxOperationChecks:5000,maxCachedStates:1},{maxCachedStates:2},{maxCachedStates:50000}]) compare('completion-'+n+':'+JSON.stringify(options),h,options);
}
const large=JSON.parse(fs.readFileSync(path.join(here,'inputs/parser/reduction-512.json'))).history;
for(const maxChecks of [0,1,2,3,256])compare('reduce512-checks-'+maxChecks,large,{maxChecks},true);
for(const options of [{analysisOptions:{maxAttempts:0}},{analysisOptions:{maxOperationChecks:0}},{maxChecks:3,analysisOptions:{maxCachedStates:0}}])compare('reduce512-'+JSON.stringify(options),large,options,true);
const textHist=(key,initial,id,version)=>({schemaVersion:1,initial:{[key]:initial},transactions:[{id,status:'committed',ops:[{type:'write',key,version},{type:'read',key,version}]}]});
for(const [key,initial,id,version] of [['键😀','零','事务𝄞','新'],['q"\\','old"','T\\','v\n'],['k','v0','A','v1'],['é'.repeat(256),'零','A','v1'],['😀'.repeat(128),'😀','😀','值']])compare('unicode-'+checks.length,textHist(key,initial,id,version));

assert.equal(checks.length,117);return checks;}
