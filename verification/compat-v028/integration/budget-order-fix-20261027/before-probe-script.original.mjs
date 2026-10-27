// API default budgets must precede compatibility parsing and request serialization.
// Tiny byte-count probes instrument real imported entry points; UTF-16 contracts
// additionally use exact logical string lengths without parsing/serializing them.
import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const MiB=1024*1024;
export async function runBudgetChecks(runtime){
 const policy=await import(pathToFileURL(resolve(runtime,'legacy-v028-policy.mjs')).href);
 const pin=(await import(pathToFileURL(resolve(runtime,'legacy-v028-binding.mjs')).href)).PUBLIC_V028;
 const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
 const evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href);
 const checks=[];function check(name,fn){try{const detail=fn();checks.push({name,passed:true,...(detail?{detail}:{})});}catch(e){checks.push({name,passed:false,failure:{name:e.name,message:e.message}});}}
 const core12={schemaVersion:1,version:'0.2.8'},core3={schemaVersion:3,version:'0.2.8'};
 const identities=pin.runtimeIdentities['linux-public-portable'];
 const engine=host=>({version:'0.2.8',coreSha256:identities.coreSha256,...(host==='diagnosis'?{captureCoreSha256:identities.captureCoreSha256,modelHostSha256:identities.hosts.models}:{}),hostSha256:identities.hosts[host]});
 const report=(format,host)=>({format,...(host?{engine:engine(host)}:{engineVersion:'0.2.8'}),operation:'reduce'});
 const orm=report('moontxnwitness-orm-profile-report/v1');
 const category=report('moontxnwitness-classification-report/v1','classification');
 const models=report('moontxnwitness-isolation-model-report/v1','models');
 const profile=report('moontxnwitness-model-profile-report/v1','modelProfile');
 const diagnosis={...report('moontxnwitness-diagnosis-report/v1','diagnosis'),analysis:core3,models};
 const explanation={kind:'moontxnwitness-register-cycle-explanation/v1',sourceReportVersion:'0.2.8'};
 const capsule=(format,inner,host)=>({...report(format,host),reportText:JSON.stringify(inner),historyText:'{}',traceText:'{}',envelopeText:'{}',sourceText:'{}',requestOptionsText:'{}',diagnosticText:'{}'});
 const args={
  'verify-v1v2':['{}',core12],'replay-v1v2':[capsule('moontxnwitness-replay/v1',core12)],
  'verify-v3':['{}',core3],'replay-v3':[capsule('moontxnwitness-replay/v3',core3)],
  'verify-orm':['{}',orm,'{}'],'replay-orm':[capsule('moontxnwitness-orm-profile/v1',orm)],
  'verify-classification':['{}',category,'{}'],'replay-classification':[capsule('moontxnwitness-classification/v1',category,'classification')],
  'verify-models':['{}',models,'{}'],'replay-models':[capsule('moontxnwitness-isolation-models/v1',models,'models')],
  'verify-model-profile':['{}',profile,'{}'],'replay-model-profile':[capsule('moontxnwitness-model-profile/v1',profile,'modelProfile')],
  'verify-diagnosis':['{}',diagnosis,'{}'],'replay-execution':[capsule('moontxnwitness-execution/v1',core3)],
  'verify-cycle':['{}',core3,explanation],
 };
 const parse0=JSON.parse,length0=Buffer.byteLength,stringify0=JSON.stringify;
 function probe(fn,marker,bytes,parsed,stopSerialize=false){
  const events=[];let result,error;
  JSON.parse=function(value,...rest){if(value===marker){events.push('parse-marker');return parsed;}return parse0(value,...rest);};
  Buffer.byteLength=function(value,...rest){if(value===marker){events.push('measure-marker');return bytes;}return length0(value,...rest);};
  JSON.stringify=function(value,...rest){if(Array.isArray(value)&&value.includes(marker)){events.push('serialize-arguments');if(stopSerialize)throw Error('TEST_STOP_ARGUMENT_SERIALIZATION');}return stringify0(value,...rest);};
  try{result=fn();}catch(e){error={name:e.name,message:e.message};}finally{JSON.parse=parse0;Buffer.byteLength=length0;JSON.stringify=stringify0;}
  return {events,result,error};
 }
 const utf8=[
  ['verify-v3',0,8*MiB],['verify-v3',1,32*MiB],['replay-v3',0,32*MiB],
  ['verify-cycle',0,8*MiB],['verify-cycle',1,32*MiB],['verify-cycle',2,8*MiB],
  ['verify-orm',0,64*MiB],['verify-orm',1,64*MiB],['verify-orm',2,4096],['replay-orm',0,128*MiB],
  ['verify-classification',0,8*MiB],['verify-classification',1,64*MiB],['verify-classification',2,8192],['replay-classification',0,128*MiB],
  ['verify-models',0,32*MiB],['verify-models',1,96*MiB],['verify-models',2,8192],['replay-models',0,192*MiB],
  ['verify-model-profile',0,64*MiB],['verify-model-profile',1,64*MiB],['verify-model-profile',2,4096],['replay-model-profile',0,128*MiB],
  ['verify-diagnosis',0,8*MiB],['verify-diagnosis',1,160*MiB],['verify-diagnosis',2,16384],['replay-execution',0,32*MiB],
 ];
 for(const[operation,index,limit]of utf8){
  const marker='{"budgetProbe":"'+operation+'-'+index+'"}',values=[...args[operation]],header=index===2&&operation==='verify-cycle'?explanation:values[operation.startsWith('verify-')?1:0];values[index]=marker;
  check('raw UTF8 preflight '+operation+'['+index+']',()=>{
   const route=probe(()=>policy.targets028(operation,values),marker,limit+1,header,true);
   assert.equal(route.result,false);assert.deepEqual(route.events,['measure-marker']);
   for(const method of ['assertOperation028','selectRuntime028']){const r=probe(()=>policy[method](operation,values),marker,limit+1,header,true);assert.equal(r.error?.name,'RangeError');assert.deepEqual(r.events,['measure-marker']);}
   return {limit,unit:'UTF8 bytes',noMarkerParseOrArgumentSerialization:true};
  });
  check('raw UTF8 exact boundary '+operation+'['+index+']',()=>{
   const r=probe(()=>policy.targets028(operation,values),marker,limit,header,true);assert.equal(r.result,true);assert.equal(r.error,undefined);assert.equal(r.events[0],'measure-marker');
  });
 }
 const unitRows=[['verify-v1v2',0,1048576],['verify-v1v2',1,33554432],['replay-v1v2',0,33554432]];
 for(const[operation,index,limit]of unitRows)for(const delta of [0,1]){
  check('UTF16 contract '+operation+'['+index+'] '+(delta?'over':'exact'),()=>{
   const marker='é'.repeat(limit+delta),values=[...args[operation]],header=values[operation.startsWith('verify-')?1:0];values[index]=marker;
   const r=probe(()=>policy.targets028(operation,values),marker,2*(limit+delta),header,true);
   assert.equal(r.result,delta===0);assert.equal(r.error,undefined);assert.equal(r.events.includes('measure-marker'),false);assert.equal(r.events.includes('parse-marker'),delta===0&&index!==0||delta===0&&operation.startsWith('replay-'));
   if(delta){const a=probe(()=>policy.assertOperation028(operation,values),marker,2*(limit+delta),header,true);assert.equal(a.error?.name,'RangeError');assert.deepEqual(a.events,[]);}
   return {limit,unit:'UTF16 code units',logicalCodeUnits:limit+delta,noUTF8Tightening:true};
  });
 }
 const nested=[
  ['replay-v1v2','reportText',33554432,true],['replay-v1v2','historyText',1048576,true],
  ['replay-v3','reportText',32*MiB],['replay-v3','traceText',8*MiB],
  ['replay-orm','reportText',64*MiB],['replay-orm','envelopeText',64*MiB],['replay-orm','requestOptionsText',4096],
  ['replay-classification','reportText',64*MiB],['replay-classification','sourceText',8*MiB],['replay-classification','requestOptionsText',8192],
  ['replay-models','reportText',96*MiB],['replay-models','sourceText',32*MiB],['replay-models','requestOptionsText',8192],
  ['replay-model-profile','reportText',64*MiB],['replay-model-profile','envelopeText',64*MiB],['replay-model-profile','requestOptionsText',4096],
  ['replay-execution','traceText',8*MiB],['replay-execution','diagnosticText',32*MiB],
 ];
 for(const[operation,field,limit,units]of nested)for(const method of ['assertOperation028','selectRuntime028'])check('nested '+method+' '+operation+'.'+field,()=>{
  const marker=units?'é'.repeat(limit+1):'{"nestedBudgetProbe":"'+operation+'-'+field+'"}',values=[{...args[operation][0],[field]:marker}];
  const r=probe(()=>policy[method](operation,values),marker,limit+1,{},true);
  assert.equal(r.error?.name,'RangeError');assert.deepEqual(r.events,units?[]:['measure-marker']);return {limit,unit:units?'UTF16 code units':'UTF8 bytes',noNestedParseOrArgumentSerialization:true};
 });
 // Public entry points, including a current non028 report: the route must not
 // parse rejected generic strings before the existing public guard runs.
 const apis=[['verifyV3 report',x=>sdk.verifyV3('{}',x),32*MiB],['verifyV3 source',x=>sdk.verifyV3(x,core3),8*MiB],['replayCapsuleV3',x=>evidence.replayCapsuleV3(x),32*MiB],['cycle report',x=>sdk.verifyRegisterCycleExplanationV3('{}',x,{}),32*MiB],['verifyListV3',x=>sdk.verifyListV3('{}',x),32*MiB],['verifyRelationV3',x=>sdk.verifyRelationV3('{}',x),32*MiB]];
 for(const[name,api,limit]of apis)for(const version of ['0.2.8','0.3.0'])check('SDK preparse '+name+' '+version,()=>{
  const marker='{"schemaVersion":3,"version":"'+version+'","budgetProbe":"public"}',r=probe(()=>api(marker),marker,limit+1,{schemaVersion:3,version},true);
  assert.equal(r.events.includes('parse-marker'),false);assert.equal(r.events.includes('serialize-arguments'),false);assert.ok(r.events.includes('measure-marker'));assert.ok(r.error||r.result?.valid===false);return {events:r.events};
 });
 check('real nonASCII UTF8 source rejects before header parse',()=>{
  const marker='é'.repeat(4*MiB+1),values=[marker,core3];let parses=0;JSON.parse=function(...a){parses++;return parse0(...a);};try{assert.equal(policy.targets028('verify-v3',values),false);assert.throws(()=>policy.assertOperation028('verify-v3',values),RangeError);assert.equal(parses,0);}finally{JSON.parse=parse0;}
 });
 return {format:'moontxnwitness-fixed028-api-budget-order/v1',passed:checks.every(c=>c.passed),checkCount:checks.length,checks,byteLimitProbesSimulatedWithTinyStrings:true,utf16LogicalBoundaryStringsUsed:true,realNonAsciiUtf8BoundaryChecked:true,largeRejectedTextParsedOrSerialized:false,actualDatabaseExecuted:false,formalPerformanceMeasured:false};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 const[runtime,output,...rest]=process.argv.slice(2);assert.ok(runtime&&output&&!rest.length);mkdirSync(output);const receipt=await runBudgetChecks(resolve(runtime));writeFileSync(resolve(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({passed:receipt.passed,checks:receipt.checkCount,failures:receipt.checks.filter(c=>!c.passed).map(c=>c.name)}));if(!receipt.passed)process.exitCode=1;
}
