// CPU/GC diagnostics only. Observer/profiler overhead makes these samples
// unsuitable for the formal release gate. Both engines use this same worker.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {performance,PerformanceObserver} from 'node:perf_hooks';
import {Session} from 'node:inspector';

const [coreArg,fixtureArg,outputArg]=process.argv.slice(2);
assert.ok(coreArg&&fixtureArg&&outputArg&&process.argv.length===5,
  'Usage: node scripts/diagnose-analysis.mjs CORE FIXTURE NEW_OUTPUT.json');
const outputPath=resolve(outputArg);
assert.ok(!existsSync(outputPath),'Diagnostic output must be new');
const coreBytes=readFileSync(coreArg), fixtureBytes=readFileSync(fixtureArg);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const fixture=JSON.parse(fixtureBytes);
const core=await import(pathToFileURL(resolve(coreArg)).href);
const text=JSON.stringify(fixture.history);
const run=()=>JSON.parse(fixture.operation==='shrink'
  ? core.shrink_options_json(text,'{}') : core.analyze_options_json(text,'{}'));
const gc=[];
const observer=new PerformanceObserver(list=>{
  for(const e of list.getEntries())gc.push({startMs:e.startTime,durationMs:e.duration,
    kind:e.detail?.kind,flags:e.detail?.flags});
});
observer.observe({entryTypes:['gc']});
const inspector=new Session();inspector.connect();
const post=(method,params={})=>new Promise((done,reject)=>
  inspector.post(method,params,(error,result)=>error?reject(error):done(result)));
await post('Profiler.enable');
await post('Profiler.setSamplingInterval',{interval:1000});
await post('Profiler.start');
const rows=[];
let output;
for(let i=-5;i<30;i++){
  const cpu=process.cpuUsage();
  const before=process.memoryUsage().heapUsed;
  const startMs=performance.now();
  output=run();
  const endMs=performance.now();
  const used=process.cpuUsage(cpu);
  rows.push({warmup:i<0,index:i,startMs,endMs,durationMs:endMs-startMs,
    cpuUserUs:used.user,cpuSystemUs:used.system,
    heapBeforeBytes:before,heapAfterBytes:process.memoryUsage().heapUsed});
}
const {profile}=await post('Profiler.stop');
inspector.disconnect();
// GC entries are delivered asynchronously; drain outside all timed samples.
await new Promise(done=>setImmediate(done));
await new Promise(done=>setImmediate(done));
for(const e of observer.takeRecords())gc.push({startMs:e.startTime,durationMs:e.duration,
  kind:e.detail?.kind,flags:e.detail?.flags});
observer.disconnect();
for(const row of rows){
  const events=gc.filter(e=>e.startMs<row.endMs&&e.startMs+e.durationMs>row.startMs);
  row.gcEvents=events.length;
  row.gcOverlapMs=events.reduce((n,e)=>n+Math.max(0,
    Math.min(e.startMs+e.durationMs,row.endMs)-Math.max(e.startMs,row.startMs)),0);
}
assert.equal(output.status,fixture.status);
const samples=rows.filter(r=>!r.warmup);
const percentile=(values,p)=>[...values].sort((a,b)=>a-b)[Math.ceil(values.length*p)-1];
const byId=new Map(profile.nodes.map(n=>[n.id,n]));
const selfTime=new Map();
for(let i=0;i<(profile.samples||[]).length;i++){
  const n=byId.get(profile.samples[i]);
  const name=n?.callFrame.functionName||'(anonymous)';
  selfTime.set(name,(selfTime.get(name)||0)+(profile.timeDeltas?.[i]||0));
}
const cpuTotalUs=[...selfTime.values()].reduce((a,b)=>a+b,0);
const topCpu=[...selfTime].sort((a,b)=>b[1]-a[1]).slice(0,30)
  .map(([functionName,selfUs])=>({functionName,selfUs,share:selfUs/cpuTotalUs}));
const result={schema:1,diagnosticOnly:true,formalReleaseGateApplicable:false,
  protocol:'fixed 5 warmups + 30 synchronous full-output samples; CPU 1000us sampling and GC observer on both engines; no forced GC',
  scenario:fixture.name,version:core.version(),node:process.version,
  coreSha256:sha(coreBytes),fixtureSha256:sha(fixtureBytes),
  scriptSha256:sha(readFileSync(new URL(import.meta.url))),
  medianMs:percentile(samples.map(r=>r.durationMs),.5),
  p95Ms:percentile(samples.map(r=>r.durationMs),.95),
  sampledGcOverlapMs:samples.reduce((n,r)=>n+r.gcOverlapMs,0),
  sampledTotalMs:samples.reduce((n,r)=>n+r.durationMs,0),
  peakRssKiB:process.resourceUsage().maxRSS,
  outputBytes:Buffer.byteLength(JSON.stringify(output)),
  rows,gc,topCpu,
  rawCpuProfile:outputPath+'.cpuprofile'};
writeFileSync(outputPath+'.cpuprofile',JSON.stringify(profile),{flag:'wx'});
writeFileSync(outputPath,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({scenario:result.scenario,version:result.version,
  diagnosticOnly:true,medianMs:result.medianMs,p95Ms:result.p95Ms,
  gcShare:result.sampledGcOverlapMs/result.sampledTotalMs,topCpu:topCpu.slice(0,8)}));
