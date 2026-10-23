import assert from 'node:assert/strict';
import{readFileSync,existsSync,writeFileSync}from'node:fs';
import{resolve}from'node:path';import{pathToFileURL}from'node:url';import{createRequire}from'node:module';
const[mode,runtimeArg,fixturesArg,markerArg]=process.argv.slice(2),runtime=resolve(runtimeArg),fixtures=resolve(fixturesArg),marker=resolve(markerArg),require=createRequire(import.meta.url);
const count=()=>Object.keys(require.cache).filter(k=>k.replaceAll('\\','/').includes('/legacy/v024/')&&k.endsWith('.cjs')).length;
const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);assert.equal(count(),0);
const manifest=JSON.parse(readFileSync(resolve(fixtures,'manifest.json'),'utf8')),row=manifest.cases.find(x=>x.name==='orm-actual-1');
const text=readFileSync(resolve(fixtures,row.capsule.file),'utf8'),original=JSON.parse(text),input=readFileSync(resolve(fixtures,row.input.file),'utf8'),expected=JSON.parse(readFileSync(resolve(fixtures,row.producerReplay.file),'utf8'));
let result,second;
if(mode==='normal-missing-legacy'){
 const point=manifest.cases.find(x=>x.name==='register-v1');result={point:sdk.analyze(readFileSync(resolve(fixtures,point.input.file),'utf8')),orm:sdk.analyzeOrmProfileV3(input)};
 assert.equal(result.orm.engineVersion,'0.2.5');assert.equal(sdk.verifyOrmProfileV3(input,result.orm).valid,true);assert.equal(count(),0);
}else if(mode==='cache'){
 result=sdk.replayOrmProfileCapsuleV3(text);second=sdk.replayOrmProfileCapsuleV3(text);assert.deepEqual(result,expected);assert.deepEqual(second,expected);assert.equal(count(),2);
}else{
 const cap=structuredClone(original);
 if(mode==='unknown-engine-missing-legacy'){cap.engineVersion='9.9.9';cap.modulePath=pathToFileURL(resolve(runtime,'../evil.cjs')).href;}
 if(mode==='known-engine-untrusted-path')cap.modulePath=pathToFileURL(resolve(runtime,'../evil.cjs')).href;
 if(mode==='retagged-old-as-current')cap.engineVersion=sdk.version();
 if(mode==='old-report-wrong-envelope')result=sdk.verifyOrmProfileV3(input+'\n',JSON.parse(readFileSync(resolve(fixtures,row.report.file),'utf8')));
 else result=sdk.replayOrmProfileCapsuleV3(mode==='reject-original'?text:JSON.stringify(cap,null,2)+'\n');
 assert.equal(result.valid,false);
 const expectedCount=['known-engine-untrusted-path','old-report-wrong-envelope'].includes(mode)?2:0;assert.equal(count(),expectedCount);
}
assert.equal(existsSync(marker),false);assert.equal(globalThis.__mtw_untrusted_loaded,undefined);
console.log(JSON.stringify({passed:true,mode,actualEngine:sdk.version(),oldCjsCount:count(),untrustedCodeExecuted:false,result,...(second?{second}:{} )}));
