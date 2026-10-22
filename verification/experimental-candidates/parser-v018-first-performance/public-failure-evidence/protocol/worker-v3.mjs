// This file is inert until invoked by the externally authorized protocol launcher.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {pathToFileURL} from 'node:url';
import {cpus,platform,release,arch} from 'node:os';
import {historyText} from './logical-history.mjs';
import {projectEngineHeader} from './engine-header-projection-v3.mjs';
const [jobPath,jobSha]=process.argv.slice(2);assert.ok(jobPath&&/^[a-f0-9]{64}$/.test(jobSha));
const hash=b=>createHash('sha256').update(b).digest('hex'),jobRaw=readFileSync(jobPath);assert.equal(hash(jobRaw),jobSha);const job=JSON.parse(jobRaw);
assert.equal(job.authorized,true);assert.ok(['equivalence','warm','cold'].includes(job.mode));assert.ok(['parse','full'].includes(job.phase));assert.equal(job.warmups,5);assert.equal(job.samples,30);
const moduleBytes=readFileSync(job.corePath),inputBytes=readFileSync(job.inputPath);assert.equal(hash(moduleBytes),job.coreSha256);assert.equal(hash(inputBytes),job.inputSha256);const input=inputBytes.toString('utf8');
const rssBeforeImport=process.memoryUsage().rss,started=performance.now();
const core=await import(pathToFileURL(job.corePath));
const importMs=performance.now()-started,rssAfterImport=process.memoryUsage().rss;assert.equal(core.version(),job.expectedVersion);assert.ok((job.engine==='baseline'&&job.expectedVersion==='0.1.7')||(job.engine==='current'&&job.expectedVersion==='0.1.8'));
assert.equal(typeof core.analyze_options_json,'function');assert.equal(typeof core.benchmark_parse_balanced,'function');
const run=job.phase==='full'?()=>core.analyze_options_json(input,'{}'):()=>core.benchmark_parse_balanced(input);
const encode=value=>job.phase==='full'?(assert.equal(typeof value,'string'),value):historyText(value);
const checkOutput=value=>{try{const text=encode(value),projection=job.phase==='full'?projectEngineHeader(text,job.expectedVersion):null,projectedText=projection?projection.projectedText:text,rawDigest=hash(text),digest=hash(projectedText);if(job.expectedRawOutputSha256)assert.equal(rawDigest,job.expectedRawOutputSha256,'Native full output changed within this exact runtime');if(job.expectedOutputSha256)assert.equal(digest,job.expectedOutputSha256,'Projected complete output differs');if(job.phase==='full')assert.equal(JSON.parse(text).status,job.expectedStatus);return{text,projectedText,projection,rawDigest,digest,bytes:Buffer.byteLength(text),projectedBytes:Buffer.byteLength(projectedText)};}catch(error){if(!existsSync(job.firstFailureOutputPath))writeFileSync(job.firstFailureOutputPath,typeof value==='string'?value:JSON.stringify(value,(_k,v)=>typeof v==='bigint'?{'$moonbitInt64':v.toString()}:v),{flag:'wx'});throw error;}};
const firstStart=performance.now();let value=run();const firstCallMs=performance.now()-firstStart;const first=checkOutput(value);
const rssSamples=[process.memoryUsage().rss],timesMs=[];
if(job.mode==='equivalence'){writeFileSync(job.fullOutputPath,first.text,{flag:'wx'});writeFileSync(job.projectedOutputPath,first.projectedText,{flag:'wx'});}
else if(job.mode==='warm'){
  // The recorded first call is warmup 1; four more make exactly five.
  for(let i=1;i<5;i++){value=run();checkOutput(value);}
  for(let i=0;i<30;i++){const start=performance.now();value=run();timesMs.push(performance.now()-start);checkOutput(value);rssSamples.push(process.memoryUsage().rss);}
}
const sorted=timesMs.slice().sort((a,b)=>a-b),median=a=>a.length?(a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2):null;
const row={schema:1,passed:true,mode:job.mode,phase:job.phase,engine:job.engine,batch:job.batch,version:core.version(),coreSha256:job.coreSha256,inputSha256:job.inputSha256,inputBytes:inputBytes.length,fullOutputSha256:first.digest,rawFullOutputSha256:first.rawDigest,projectedOutputSha256:first.digest,outputBytes:first.bytes,projectedOutputBytes:first.projectedBytes,engineMetadataProjection:first.projection?{path:first.projection.projectedPath,nativeEngine:first.projection.engineVersion,valueStart:first.projection.rawValueStart,valueEnd:first.projection.rawValueEnd,otherCharactersPreserved:true}:null,exactCompleteOutputValidated:true,importMs,firstCallMs,warmups:job.mode==='warm'?5:0,measuredSamples:timesMs.length,timesMs,medianMs:median(sorted),p95Ms:sorted.length?sorted[Math.ceil(sorted.length*.95)-1]:null,rssBeforeImportBytes:rssBeforeImport,rssAfterImportBytes:rssAfterImport,rssSamplesBytes:rssSamples,maxObservedRssBytes:Math.max(...rssSamples),lifetimePeakRssKiB:process.resourceUsage().maxRSS,peakRssScope:'Whole worker lifetime including input/hash/import/validation and serialization; not allocation-only.',environment:{node:process.version,nodeExecutable:process.execPath,os:platform(),release:release(),arch:arch(),cpu:cpus()[0]?.model,logicalCpus:cpus().length},formal18Build:false,networkUsed:false,databaseExecuted:false};
assert.equal(hash(readFileSync(job.corePath)),job.coreSha256);assert.equal(hash(readFileSync(job.inputPath)),job.inputSha256);
writeFileSync(job.resultPath,JSON.stringify(row,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({passed:true,resultPath:job.resultPath}));
