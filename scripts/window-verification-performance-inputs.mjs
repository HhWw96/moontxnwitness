// Freeze comparable full-call inputs from an original, successful PG campaign.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),args={};
const pending=process.argv.slice(2);while(pending.length){const key=pending.shift();assert(['--baseline','--candidate','--candidate-structured','--receipt','--output','--baseline-commit','--candidate-commit'].includes(key)&&!Object.hasOwn(args,key));args[key]=pending.shift();}
for(const key of ['--baseline','--candidate','--receipt','--output','--baseline-commit','--candidate-commit'])assert(args[key],'Missing '+key);
const output=resolve(args['--output']);mkdirSync(output);const sdkPath=resolve(args['--baseline']),sdk=await import(pathToFileURL(sdkPath).href);
const receipt=readFileSync(args['--receipt']),campaign=JSON.parse(receipt);assert.equal(campaign.passed,true);assert.equal(campaign.actualDatabaseExecution,true);
const canonical=value=>value===null||typeof value!=='object'?JSON.stringify(value):Array.isArray(value)?'['+value.map(canonical).join(',')+']':'{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonical(value[key])).join(',')+'}';
const sha=value=>createHash('sha256').update(value).digest('hex'),cases=[];
function add(id,api,parameters,control=false){
  const result=sdk[api](...parameters),data={api,arguments:parameters,expectedCanonicalSha256:sha(canonical(result)),outputBytes:Buffer.byteLength(JSON.stringify(result))};
  const input=resolve(output,id+'.json');writeFileSync(input,JSON.stringify(data)+'\n',{flag:'wx'});
  cases.push({id,input,control,...(!control&&args['--candidate-structured']?{candidateSdk:resolve(args['--candidate-structured'])}:{})});
}
for(const [type,name] of [['int64','crud'],['text','rr-write-skew'],['uuid','rr-write-skew-noise']]){
  const fixture=campaign.records.find(row=>row.keyType===type)?.analysisFixtures.find(row=>row.name===name);assert(fixture,'Missing original case '+type+'/'+name);
  const bundle=readFileSync(fixture.bundle,'utf8');assert.equal(sha(bundle),fixture.bundleSha256);
  const options={config:fixture.config,policy:fixture.policy},report=sdk.analyzeConfiguredWindowV4(bundle,options);
  assert.equal(report.coverageComplete,true);assert.equal(sdk.verifyConfiguredWindowV4(bundle,report,options).valid,true);
  add('window-'+type+'-'+name,'verifyConfiguredWindowV4',[bundle,report,options]);
  if(fixture.expected==='refuted'){
    const target={...options,preserveModel:'serializable'},reduced=sdk.reduceConfiguredWindowV4(bundle,target);
    assert.equal(sdk.verifyConfiguredWindowReductionV4(bundle,reduced,target).oneMinimalVerified,true);
    add('reduction-'+type+'-'+name,'verifyConfiguredWindowReductionV4',[bundle,reduced,target]);
  }
}
add('register-analysis-control','analyze',[readFileSync(resolve(root,'examples/write-skew.json'),'utf8')],true);
add('model-classification-control','classifyModelsV4',[readFileSync(resolve(root,'examples/models-v4-register.json'),'utf8'),{models:'elle-core'}],true);
const config={schemaVersion:1,exclusiveExecution:false,baseline:{sdk:sdkPath,sourceCommit:args['--baseline-commit']},
  candidate:{sdk:resolve(args['--candidate']),sourceCommit:args['--candidate-commit']},originalReceiptSha256:sha(receipt),cases};
writeFileSync(resolve(output,'config.json'),JSON.stringify(config,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({cases:cases.length,config:resolve(output,'config.json'),exclusiveExecution:false}));
