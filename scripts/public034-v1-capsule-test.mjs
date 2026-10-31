// Additional schema1 checks. The original 47-case/15-family suite is unchanged.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(import.meta.dirname,'..'),args=process.argv.slice(2);
assert(args.length===0||(args.length===2&&args[0]==='--runtime'),'Only current consumer --runtime is accepted');
const runtime=resolve(args[1]||resolve(root,'dist')),hash=x=>createHash('sha256').update(x).digest('hex');
const {PUBLIC034:pin}=await import(pathToFileURL(resolve(runtime,'legacy-v034-binding.mjs')));
const loader=await import(pathToFileURL(resolve(runtime,'legacy-v034.mjs')));
const producerRoot=resolve(loader.verifyPublic034Runtime());assert.notEqual(producerRoot,runtime);
const old=await import(pathToFileURL(resolve(producerRoot,'sdk.mjs'))),oldEvidence=await import(pathToFileURL(resolve(producerRoot,'evidence.mjs')));
const current=await import(pathToFileURL(resolve(runtime,'sdk.mjs'))),newEvidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')));
assert.equal(pin.version,'0.3.4');assert.equal(old.version(),'0.3.4');assert.notEqual(current.version(),'0.3.4');
assert.equal(current.version(),JSON.parse(readFileSync(resolve(root,'package.json'),'utf8')).version);
const watched=[resolve(runtime,'legacy-v034-binding.mjs'),resolve(producerRoot,'core.mjs'),resolve(producerRoot,'sdk.mjs'),resolve(producerRoot,'evidence.mjs')];
const snapshot=()=>watched.map(n=>hash(readFileSync(n))),before=snapshot(),cases=[];
function check(name,fn){try{fn();cases.push({name,passed:true});}catch(error){cases.push({name,passed:false,error:error.message});}}
for(const fixture of ['examples/write-skew.json','examples/consistent.json']){
  const source=readFileSync(resolve(root,fixture),'utf8'),report=old.analyze(source);
  assert.equal(report.schemaVersion,1,'This supplement must create actual schema1 output');assert.equal(report.version,'0.3.4');
  const capsule=oldEvidence.makeCapsule(source,report);
  check(fixture+' direct schema1 report and capsule replay',()=>{assert.equal(current.replayReport(source,report).valid,true);assert.equal(newEvidence.replayCapsule(capsule).valid,true);});
  check(fixture+' rehashed schema1 conclusion is still refused',()=>{const c=JSON.parse(capsule),r=JSON.parse(c.reportText);r.status=r.status==='violation'?'consistent':'violation';assert.equal(current.replayReport(source,r).valid,false);c.reportText=JSON.stringify(r);c.reportSha256=hash(c.reportText);assert.equal(newEvidence.replayCapsule(JSON.stringify(c)).valid,false);});
  check(fixture+' schema1 mixed engine headers are refused',()=>{const c=JSON.parse(capsule);c.engineVersion=current.version();assert.equal(newEvidence.replayCapsule(JSON.stringify(c)).valid,false);});
}
assert.equal(cases.length,6);assert.deepEqual(snapshot(),before);loader.verifyPublic034Runtime();
const result={suite:'public034-explicit-schema1-supplement/v1',passed:cases.every(x=>x.passed),checks:6,failed:cases.filter(x=>!x.passed).length,producerVersion:pin.version,producerSourceCommit:pin.sourceCommit,producerArchiveSha256:pin.archiveSha256,producerComponentSha256:pin.componentSha256,currentVersion:current.version(),original47SuiteModified:false,original15FamiliesModified:false,producerBytesUnchanged:true,cases};
console.log(JSON.stringify(result));if(!result.passed)process.exitCode=1;
