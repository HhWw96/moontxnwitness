// Called only by an explicitly approved formal controller; not auto-executed by preparation.
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {performance} from 'node:perf_hooks';
import {gzipSync} from 'node:zlib';
import {sha,canonical,stats,safeFile,expectation} from './common.mjs';
const [planArg,planSha,id,batchText,outArg]=process.argv.slice(2);if(process.argv.length!==7)throw Error('Worker protocol argument count');
const planPath=resolve(planArg),root=dirname(planPath),rawPlan=readFileSync(planPath);if(sha(rawPlan)!==planSha)throw Error('Worker plan SHA differs');
const plan=JSON.parse(rawPlan),f=plan.fixtures.find(x=>x.id===id),batch=Number(batchText),out=resolve(outArg);
if(!f||![1,2,3].includes(batch)||plan.warmups!==5||plan.samples!==30||plan.batches!==3)throw Error('Frozen worker protocol differs');
if(process.env.NODE_OPTIONS||process.env.NODE_PATH||process.execArgv.length)throw Error('Runtime injection flags refused');
const inputRaw=readFileSync(safeFile(root,f.file));if(sha(inputRaw)!==f.sha256||inputRaw.length!==f.bytes)throw Error('Input bytes differ');
const source=inputRaw.toString('utf8');if(!Buffer.from(source).equals(inputRaw))throw Error('Malformed UTF-8 fixture');
const options=Object.freeze({...plan.requestOptions}),startedAtProcessMs=process.uptime()*1000;
const loadStart=performance.now(),sdk=await import(pathToFileURL(safeFile(root,plan.runtime.directory+'/sdk.mjs')).href),coldLoadMs=performance.now()-loadStart;
if(typeof sdk.classifyModelsV3!=='function')throw Error('Missing full SDK six-model entry');
const firstStart=performance.now();let report=sdk.classifyModelsV3(source,options);const firstCallMs=performance.now()-firstStart,processElapsedAtFirstCallMs=process.uptime()*1000;
expectation(report,f,plan.models);if(report.engine.version!==plan.runtime.buildManifest.version||report.engine.coreSha256!==plan.runtime.files['core.mjs'].sha256||report.engine.hostSha256!==plan.runtime.files['classification-models.mjs'].sha256)throw Error('Actual report engine does not match frozen runtime');
for(let i=0;i<plan.warmups;i++)report=sdk.classifyModelsV3(source,options);
const samples=[];for(let i=0;i<plan.samples;i++){const before=performance.now();report=sdk.classifyModelsV3(source,options);samples.push(performance.now()-before);}
// Snapshot process high-water BEFORE caller final validation/JSON/gzip/file output allocations.
const usage=process.resourceUsage(),rss=usage.maxRSS;if(!Number.isSafeInteger(rss)||rss<=0)throw Error('Peak RSS unavailable');
expectation(report,f,plan.models);
const output=Buffer.from(JSON.stringify(report)+'\n');if(output.length>plan.retainedOutputLimitBytes)throw Error('Full last output exceeds explicit archive budget');
const compressed=gzipSync(output);writeFileSync(resolve(out,'last-output.json.gz'),compressed,{flag:'wx'});
const result={format:'moontxnwitness-six-model-cost-worker/v1',passed:true,id,batch,planSha256:planSha,engine:report.engine,requestedModels:plan.models,verificationPasses:report.verificationPasses,status:report.status,modelStatuses:Object.fromEntries(plan.models.map(m=>[m,report.result.models[m].status])),node:process.version,platform:process.platform,arch:process.arch,processId:process.pid,startedAtProcessMs,coldLoadMs,firstCallMs,processElapsedAtFirstCallMs,warmupCount:5,sampleCount:30,samplesMs:samples,sampleStatsMs:stats(samples),peakRssKiB:rss,resourceUsageBeforeFinalEncoding:usage,output:{file:'last-output.json.gz',bytes:output.length,sha256:sha(output),gzipBytes:compressed.length,gzipSha256:sha(compressed)},fullOutputsRetained:1,intermediateFullOutputsRetained:false,callerEncodingIncludedInLatency:false};
writeFileSync(resolve(out,'receipt.json'),canonical(result),{flag:'wx'});console.log(JSON.stringify({passed:true,id,batch,sampleCount:samples.length,peakRssKiB:rss,outputBytes:output.length}));
