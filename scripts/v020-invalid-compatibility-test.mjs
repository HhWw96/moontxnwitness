// Consume frozen public20 bytes; regeneration is never part of verification.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),hash=x=>createHash('sha256').update(x).digest('hex');
const bindings=[
 ['fixtures/compat-v020-invalid','853198ff096bbbb1fa7b8ec36777edeab293c2e1f6bded639df6c7b7ffa4d207'],
 ['fixtures/compat-v020-list-wrapper','0706936b11ca39313e216dfdb1318770489b0dca1ef681a8b0929697418c9614'],
];
const frozenCases=bindings.flatMap(([folder,sha])=>{const dir=resolve(root,folder),bytes=readFileSync(resolve(dir,'manifest.json'));assert.equal(hash(bytes),sha);return JSON.parse(bytes).cases.map(c=>({...c,dir}));});
const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')));
assert.notEqual(sdk.version(),'0.2.0');
let checks=0;const cases=[];
function check(value,label){assert.equal(value,true,label);checks++;}
function capsule(content,report){content.reportText=JSON.stringify(report);content.normalizedText=JSON.stringify(report.normalized);content.evidenceText=JSON.stringify(report.evidence);for(const key of ['trace','report','normalized','evidence'])content[key+'Sha256']=hash(content[key+'Text']);return JSON.stringify(content,null,2)+'\n';}
for(const c of frozenCases){
 const text={};for(const key of ['input','report','capsule']){const b=readFileSync(resolve(c.dir,c[key].file));check(b.length===c[key].bytes&&hash(b)===c[key].sha256,c.name+' frozen '+key);text[key]=b.toString('utf8');}
 const cap=JSON.parse(text.capsule),report=JSON.parse(text.report);
 check(report.status==='invalid'&&report.normalized.status==='invalid',c.name+' original judgment');
 check(sdk.verifyV3(text.input,report).valid===true,c.name+' original full report');
 check(sdk.replayCapsuleV3(text.capsule).valid===true,c.name+' original capsule');
 function mutate(label,edit){const next=structuredClone(cap),r=structuredClone(report);edit(next,r);check(sdk.replayCapsuleV3(capsule(next,r)).valid===false,c.name+' '+label);}
 mutate('verdict',(_,r)=>{r.status='consistent';});
 mutate('budget',(_,r)=>{r.execution.analysisOptions.maxStates=0;});
 function diagnostic(r,edit){let changed=0;if(typeof r.normalized.error==='string'){r.normalized.error=edit(r.normalized.error);changed++;}for(const coverage of [r.normalized.coverage,r.coverage])for(const g of coverage.gaps)if(['invalid_capture_v3','invalid_list_capture_v3','invalid_relation_capture_v3'].includes(g.code)){g.message=edit(g.message);changed++;}assert.ok(changed>0,'Mutation must alter an actual generated diagnostic');}
 mutate('numeric compiler coordinate',(_,r)=>diagnostic(r,s=>{const changed=s.replace(/(Failure\(src\/[^:]+:)\d+:/,'$199999:');assert.notEqual(changed,s);return changed;}));
 mutate('diagnostic text',(_,r)=>diagnostic(r,s=>s.replace(' FAILED: ',' FAILED: forged ')));
 mutate('observed input with matching digest',(next,_)=>{const input=JSON.parse(next.traceText);input.events[0].time=Number(input.events[0].time)+1;next.traceText=JSON.stringify(input);});
 mutate('future engine',(next,r)=>{next.engineVersion='9.9.9';r.version='9.9.9';});
 cases.push({name:c.name,dataModel:c.dataModel,passed:true});
}
console.log(JSON.stringify({passed:true,runtimeVersion:sdk.version(),producerEngineVersion:'0.2.0',actualPublishedProducer:true,capsules:cases.length,checks,manifestSha256:bindings[0][1],supplementalManifestSha256:bindings[1][1],actualDatabaseExecutedHere:false,cases}));
