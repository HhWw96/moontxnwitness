// Formal execution requires Root approval of the exact frozen plan and exclusive machine window.
import {readFileSync,writeFileSync,mkdirSync,statfsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {performance} from 'node:perf_hooks';
import os from 'node:os';
import {gunzipSync} from 'node:zlib';
import {sha,canonical,stats,binding,verifyBindings,safeFile} from './common.mjs';
const [mode,planArg,approvedSha,outArg]=process.argv.slice(2);
if(mode!=='--execute-root-approved-exclusive'||process.argv.length!==6||!(/^[a-f0-9]{64}$/).test(approvedSha??''))throw Error('Usage: run.mjs --execute-root-approved-exclusive PLAN EXACT_APPROVED_PLAN_SHA NEW_RESULT_DIR');
if(process.env.NODE_OPTIONS||process.env.NODE_PATH||process.execArgv.length)throw Error('Node injection flags refused');
const planPath=resolve(planArg),root=dirname(planPath),out=resolve(outArg),raw=readFileSync(planPath);if(sha(raw)!==approvedSha)throw Error('Approved plan SHA differs');
const p=JSON.parse(raw);if(p.phase!=='frozen-candidate-for-root-review-not-yet-measured'||p.warmups!==5||p.samples!==30||p.batches!==3||p.concurrentWorkers!==1||p.fixtures.length!==6)throw Error('Protocol changed');
verifyBindings(root,Object.fromEntries(p.fixtures.map(f=>[f.file,{bytes:f.bytes,sha256:f.sha256}])));verifyBindings(resolve(root,'runtime'),p.runtime.files);verifyBindings(resolve(root,'tools'),p.toolFiles);
const fs=statfsSync(dirname(out)),free=Number(fs.bavail)*Number(fs.bsize);if(free<p.minFreeBytes)throw Error('Insufficient explicit free-space minimum');
mkdirSync(out);const receipt={format:'moontxnwitness-six-model-cost-run/v1',phase:'formal-candidate-cost-not-stable-release-performance',planSha256:approvedSha,startedAt:new Date().toISOString(),node:{version:process.version,binary:binding(process.execPath)},machine:{platform:os.platform(),release:os.release(),arch:os.arch(),cpu:os.cpus()[0]?.model,logicalCpus:os.cpus().length,totalMemory:os.totalmem()},exclusiveMachineAssertedByInvoker:true,baseline:null,speedupComputed:false,nonTargetControlsModified:false,fullOutputsRetained:'one last complete output per fixture per batch, 18 total on success',workers:[],completed:false,performanceTargetsEvaluated:false};
writeFileSync(resolve(out,'started.json'),canonical(receipt),{flag:'wx'});
for(let batch=1;batch<=3;batch++)for(let k=0;k<p.fixtures.length;k++){
 const f=p.fixtures[(k+2*(batch-1))%p.fixtures.length],name=`batch-${batch}-${f.id}`,workerOut=resolve(out,name);mkdirSync(workerOut);
 const row={name,id:f.id,batch,passed:false};
 try{verifyBindings(resolve(root,'runtime'),p.runtime.files);verifyBindings(resolve(root,'tools'),p.toolFiles);const t=performance.now();const child=spawnSync(process.execPath,[resolve(root,'tools/worker.mjs'),planPath,approvedSha,f.id,String(batch),workerOut],{encoding:'utf8',timeout:p.workerTimeoutMs,maxBuffer:p.workerOutputLimitBytes,windowsHide:true,env:process.env});row.workerWallMs=performance.now()-t;writeFileSync(resolve(workerOut,'stdout.log'),child.stdout??'',{flag:'wx'});writeFileSync(resolve(workerOut,'stderr.log'),child.stderr??'',{flag:'wx'});row.exitCode=child.status;row.signal=child.signal;row.error=child.error?{name:child.error.name,message:child.error.message,code:child.error.code}:null;verifyBindings(resolve(root,'runtime'),p.runtime.files);verifyBindings(resolve(root,'tools'),p.toolFiles);if(child.error||child.status!==0||child.signal)throw Error('Worker did not complete');const r=JSON.parse(readFileSync(resolve(workerOut,'receipt.json')));if(!r.passed||r.id!==f.id||r.batch!==batch||r.planSha256!==approvedSha||r.sampleCount!==30||r.samplesMs.length!==30||r.fullOutputsRetained!==1)throw Error('Worker receipt differs');const compressed=readFileSync(resolve(workerOut,r.output.file));if(sha(compressed)!==r.output.gzipSha256||compressed.length!==r.output.gzipBytes)throw Error('Retained gzip output differs');const original=gunzipSync(compressed,{maxOutputLength:p.retainedOutputLimitBytes});if(original.length!==r.output.bytes||sha(original)!==r.output.sha256)throw Error('Retained full output differs');row.passed=true;row.receipt=r;}
 catch(error){row.failure=error.message;}
 receipt.workers.push(row);writeFileSync(resolve(out,'progress.json'),canonical(receipt));
}
receipt.completed=receipt.workers.length===18&&receipt.workers.every(x=>x.passed);
receipt.groups={};if(receipt.completed)for(const f of p.fixtures){const a=receipt.workers.filter(x=>x.id===f.id).map(x=>x.receipt);const outputs=a.map(x=>x.output.sha256);const equal=new Set(outputs).size===1;if(!equal)receipt.completed=false;receipt.groups[f.id]={samplesMs:stats(a.flatMap(x=>x.samplesMs)),perBatch:a.map(x=>({batch:x.batch,stats:x.sampleStatsMs,peakRssKiB:x.peakRssKiB,coldLoadMs:x.coldLoadMs,firstCallMs:x.firstCallMs,processElapsedAtFirstCallMs:x.processElapsedAtFirstCallMs,output:x.output})),peakRssKiBAcrossThreeIndependentProcesses:stats(a.map(x=>x.peakRssKiB)),rssP95OverThreeEqualsMaximum:true,lastFullOutputsEqualAcrossBatches:equal,medianColdLoadMs:stats(a.map(x=>x.coldLoadMs)).median,medianFirstCallMs:stats(a.map(x=>x.firstCallMs)).median};}
receipt.finishedAt=new Date().toISOString();writeFileSync(resolve(out,'receipt.json'),canonical(receipt),{flag:'wx'});console.log(JSON.stringify({completed:receipt.completed,workers:receipt.workers.length,failures:receipt.workers.filter(x=>!x.passed).map(x=>({name:x.name,failure:x.failure})),performanceTargetsEvaluated:false}));process.exitCode=receipt.completed?0:1;
