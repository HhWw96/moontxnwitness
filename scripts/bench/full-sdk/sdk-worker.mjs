import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {performance} from 'node:perf_hooks';
import {getHeapStatistics} from 'node:v8';
import {gzipSync} from 'node:zlib';
import {checkSubject,checkResult,fileSHA,sha,environment,guard,treeBytes} from './common.mjs';
import {normalizeProductMetadataOnly} from './report-transport-normalization.mjs';
const [protocolPath,subjectName,scenarioName,mode,launchText]=process.argv.slice(2),root=dirname(resolve(protocolPath)),protocolBytes=readFileSync(protocolPath),protocol=JSON.parse(protocolBytes);
assert(['preflight','measure'].includes(mode));assert(['baseline','candidate'].includes(subjectName));assert.equal(process.env.NODE_OPTIONS,'');assert.deepEqual(process.execArgv,protocol.heapPolicy.execArgv);guard(root,protocol);
const fixtureRecord=protocol.scenarios.find(x=>x.name===scenarioName);assert(fixtureRecord);const fixtureBytes=readFileSync(resolve(root,fixtureRecord.path));assert.equal(sha(fixtureBytes),fixtureRecord.sha256);const fixture=JSON.parse(fixtureBytes),subject=protocol.subjects[subjectName];checkSubject(subject);
const sourceBefore=JSON.stringify(fixture.history),optionsBefore=JSON.stringify(fixture.options);assert.equal(sha(sourceBefore),fixtureRecord.originalHistorySha256);
const importStart=performance.now(),sdk=await import(pathToFileURL(subject.entry).href),importMs=performance.now()-importStart;assert.equal(sdk.version(),subject.version);assert.equal(typeof sdk[fixture.method],'function');
let output;const call=()=>{output=fixture.method==='analyzeWithOptions'?sdk.analyzeWithOptions(fixture.history,fixture.options):sdk.analyze(fixture.history);};
let start=performance.now();call();const firstCallMs=performance.now()-start,spawnToFirstReturnMs=Date.now()-Number(launchText);
// O(1) cold validation only. Full edge/source/equality checks happen after timed
// work, so they neither warm the semantic checks nor enter any SDK sample.
assert.equal(output?.status,fixture.expectedStatus,'Invalid/unknown/error return is not a speedup');assert.equal(output?.edges?.length,fixture.expectedEdges);assert.equal(output?.stats?.dependencies,fixture.expectedEdges);
const timesMs=[];
if(mode==='measure'){for(let i=0;i<protocol.fixedSamples.warmup;i++)call();for(let i=0;i<protocol.fixedSamples.measuredSamples;i++){start=performance.now();call();timesMs.push(performance.now()-start);}}
const usage=process.resourceUsage(),heapAtReturn=getHeapStatistics();
checkResult(output,fixture,sdk.version());assert.equal(JSON.stringify(fixture.history),sourceBefore,'SDK changed original input');assert.equal(JSON.stringify(fixture.options),optionsBefore);
const raw=JSON.stringify(output);assert(raw.length>0);if(fixture.expectedEdges===49770)assert(Buffer.byteLength(raw)>5*1024*1024,'Dense case must retain the entire large report');const normalized=normalizeProductMetadataOnly(raw,{entry:'analyze_json',format:null,version:sdk.version()});
let archive=null;
if(mode==='preflight'){const bytes=gzipSync(raw,{mtime:0});archive={path:'preflight/'+scenarioName+'-'+subjectName+'.json.gz',bytes:bytes.length,sha256:sha(bytes)};assert(bytes.length<=512*1024,'One compressed report exceeded preparation evidence reserve');assert(treeBytes(root)+bytes.length<=protocol.resourcePolicy.preparationTotalBytes,'Preparation archive budget exceeded');writeFileSync(resolve(root,archive.path),bytes,{flag:'wx'});}
checkSubject(subject);
const result={format:'full-sdk-heap768-worker/v1',mode,subject:subjectName,scenario:scenarioName,sdkMethod:fixture.method,sdkOptions:fixture.options,originalScenario:fixture.originalScenario,protocolSha256:sha(protocolBytes),fixtureSha256:sha(fixtureBytes),sdkSha256:subject.files['sdk.mjs'].sha256,coreSha256:subject.files['core.mjs'].sha256,captureCoreSha256:subject.files['capture-core.mjs'].sha256,environment:environment(),nodeExecArgv:process.execArgv,heapLimitBytes:heapAtReturn.heap_size_limit,importMs,firstCallMs,spawnToFirstReturnMs,warmups:mode==='measure'?protocol.fixedSamples.warmup:0,samples:timesMs.length,timesMs,peakRssKiB:usage.maxRSS,userCpuMicroseconds:usage.userCPUTime,systemCpuMicroseconds:usage.systemCPUTime,outputBytes:Buffer.byteLength(raw),outputSha256:sha(raw),normalizedSha256:sha(normalized),archive,completeStatus:output.status,dependencies:output.stats.dependencies,fullReportValidated:true,inputUnchanged:true,SDKInputStringifyAndCoreAndReturnParseTimed:true,postReturnStringifyHashGzipNotTimed:true,rssCapturedBeforeEvidenceEncoding:true,filesystemCachesNotFlushed:true,integrityPinReadsPrimeModuleFiles:true,formalMeasurementExecuted:mode==='measure'};
console.log(JSON.stringify(result));
