// Freeze original invalid capsules from public20. Never run during regression tests.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),hash=x=>createHash('sha256').update(x).digest('hex');
const args=process.argv.slice(2);assert.ok(args.length===2||(args.length===3&&args[2]==='--wrapped-list-only'));assert.equal(args[0],'--out');
const out=resolve(args[1]);assert.equal(existsSync(out),false,'Never overwrite frozen compatibility evidence');
const manifestBytes=readFileSync(resolve(root,'verification/baselines/0.2.0/manifest.json'));
assert.equal(hash(manifestBytes),'0b764ff214e1a5cf6732a7c783899c4bbfeec2dd13b7c0ecbeb0732757f68503');
const pin=JSON.parse(manifestBytes),runtime=resolve(root,pin.provider);
for(const [name,f] of Object.entries(pin.files)){const b=readFileSync(resolve(runtime,name));assert.equal(b.length,f.bytes);assert.equal(hash(b),f.sha256);}
const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);assert.equal(sdk.version(),'0.2.0');
mkdirSync(out,{recursive:true});
const canonical=v=>JSON.stringify(v,null,2)+'\n';
const write=(n,v)=>{const b=typeof v==='string'?v:canonical(v);writeFileSync(resolve(out,n),b,{flag:'wx'});return {file:n,bytes:Buffer.byteLength(b),sha256:hash(b)};};
const scenarios=args[2]==='--wrapped-list-only'?[
 ['list-forwarded-lifecycle','list-cycle',t=>{t.events[2].time=0;}],
]:[
 ['list-business-value','list-cycle',t=>{t.events[0].initial.x[0].value=7;}],
 ['list-duplicate-identity','list-cycle',t=>{t.events[0].initial.y[0].id='x0';}],
 ['list-lifecycle-time','list-cycle',t=>{t.events[2].time=-1;}],
 ['relation-column-type','relation-source-closure',t=>{t.relationSchema.r.columns.n='numeric';}],
 ['relation-duplicate-producer','relation-source-closure',t=>{t.events.find(e=>e.kind==='row_write').version='p0';}],
 ['relation-lifecycle-time','relation-source-closure',t=>{t.events[2].time=-1;}],
 ['relation-row-columns','relation-source-closure',t=>{delete t.events[0].initial.r[0].values.n;}],
];
const cases=[];
for(const [name,example,edit] of scenarios){
 const trace=JSON.parse(readFileSync(resolve(root,'examples',example+'.json'),'utf8'));edit(trace);
 trace.clockDomain='business-literal-0.2.0';const text=canonical(trace),report=sdk.analyzeV3(text);
 assert.equal(report.version,'0.2.0');assert.equal(report.status,'invalid',name);assert.equal(report.normalized.status,'invalid',name);
 assert.equal(sdk.verifyV3(text,report).valid,true,name+' original verify');
 const capsule=sdk.makeCapsuleV3(text,report);assert.equal(sdk.replayCapsuleV3(capsule).valid,true,name+' original replay');
 cases.push({name,dataModel:trace.dataModel,input:write(name+'.trace.json',text),report:write(name+'.report.json',report),capsule:write(name+'.capsule.json',capsule)});
}
write('manifest.json',{schema:1,kind:'frozen-public-v020-invalid-model-capsules',producerVersion:'0.2.0',producerSourceCommit:pin.sourceCommit,producerBuild:pin.buildManifest,publicArchiveSha256:pin.publicArchiveSha256,producerFiles:pin.files,syntheticInputs:true,actualDatabaseExecution:false,cases});
console.log(JSON.stringify({producerVersion:'0.2.0',cases:cases.length,manifestSha256:hash(readFileSync(resolve(out,'manifest.json')))}));
