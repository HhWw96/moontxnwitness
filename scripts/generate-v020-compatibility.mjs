// Freeze new compatibility fixtures only from the already published20 runtime.
// Never overwrite an existing directory or regenerate expected results in tests.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const hash=x=>createHash('sha256').update(x).digest('hex');
const args=process.argv.slice(2);
assert.equal(args.length,2);assert.equal(args[0],'--out');
const out=resolve(args[1]);assert.equal(existsSync(out),false,'Frozen fixtures must never be overwritten');
const pin=JSON.parse(readFileSync(resolve(root,'verification/baselines/0.2.0/manifest.json'),'utf8'));
const runtime=resolve(root,pin.provider);
for(const [name,f] of Object.entries(pin.files))assert.equal(hash(readFileSync(resolve(runtime,name))),f.sha256);
const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
const evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href);
assert.equal(sdk.version(),'0.2.0');mkdirSync(out,{recursive:true});
const canonical=v=>JSON.stringify(v,null,2)+'\n';
const write=(n,v)=>{const b=typeof v==='string'?v:canonical(v);writeFileSync(resolve(out,n),b,{flag:'wx'});return {file:n,bytes:Buffer.byteLength(b),sha256:hash(b)};};
const cases=[];
for(const [name,path] of [['register','examples/v3-write-skew.json'],['list','examples/list-cycle.json'],['relation','examples/relation-source-closure.json']]) {
 const input=JSON.parse(readFileSync(resolve(root,path),'utf8'));input.clockDomain='business-literal-0.2.0';
 function values(v){if(v===null||typeof v!=='object')return;if(v.values&&typeof v.values.t==='string')v.values.t='0.2.0';if(typeof v.value==='string')v.value='0.2.0';for(const x of Object.values(v))values(x);}
 values(input);const text=canonical(input),report=sdk.analyzeV3(text);
 assert.equal(report.version,'0.2.0');assert.equal(report.status,'violation');
 const capsule=sdk.makeCapsuleV3(text,report);assert.equal(sdk.replayCapsuleV3(capsule).valid,true);
 cases.push({name,type:'v3',input:write(name+'.trace.json',text),report:write(name+'.report.json',report),capsule:write(name+'.capsule.json',capsule)});
}
const history=readFileSync(resolve(root,'examples/write-skew.json'),'utf8');
for(const [name,report] of [['register-v1',sdk.analyze(history)],['register-v2',sdk.analyzeWithOptions(history)]]) {
 assert.equal(report.version,'0.2.0');const capsule=evidence.makeCapsule(history,report);
 assert.equal(evidence.replayCapsule(capsule).valid,true);
 cases.push({name,type:report.schemaVersion===2?'v2':'v1',input:write(name+'.history.json',history),report:write(name+'.report.json',report),capsule:write(name+'.capsule.json',capsule)});
}
const unknown=readFileSync(resolve(root,'fixtures/v3/disconnect-after-request.json'),'utf8');
const capsule=sdk.makeExecutionCapsuleV3(unknown);assert.equal(sdk.replayExecutionCapsuleV3(capsule).valid,true);
cases.push({name:'unknown-commit',type:'execution',input:write('unknown-commit.trace.json',unknown),capsule:write('unknown-commit.capsule.json',capsule)});
write('manifest.json',{schema:1,kind:'frozen-public-v020-producer-compatibility',producerVersion:'0.2.0',producerSourceCommit:pin.sourceCommit,producerBuild:pin.buildManifest,publicArchiveSha256:pin.publicArchiveSha256,producerFiles:pin.files,syntheticInputs:true,actualDatabaseExecution:false,cases});
console.log(JSON.stringify({producerVersion:'0.2.0',cases:cases.length,publicArchiveSha256:pin.publicArchiveSha256}));
