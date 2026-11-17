// Complete SDK verification calls, with independent timing, memory and cold workers.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,readdirSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {performance} from 'node:perf_hooks';
import {cpus,totalmem,freemem,platform,arch,release} from 'node:os';
const self=fileURLToPath(import.meta.url),sha=value=>createHash('sha256').update(value).digest('hex');
const canonical=value=>value===null||typeof value!=='object'?JSON.stringify(value):Array.isArray(value)?'['+value.map(canonical).join(',')+']':'{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonical(value[key])).join(',')+'}';
const save=(path,value)=>writeFileSync(path,JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const stats=values=>{const sorted=[...values].sort((a,b)=>a-b),n=sorted.length;assert(n>0);return {count:n,median:n%2?sorted[(n-1)/2]:(sorted[n/2-1]+sorted[n/2])/2,p95:sorted[Math.ceil(n*.95)-1]};};
const geomean=values=>Math.exp(values.reduce((sum,value)=>sum+Math.log(value),0)/values.length);
function runtime(sdk){
  const folder=dirname(resolve(sdk)),files={};
  for(const name of readdirSync(folder).filter(name=>/\.(mjs|json)$/.test(name)).sort())files[name]=sha(readFileSync(resolve(folder,name)));
  const manifest=JSON.parse(readFileSync(resolve(folder,'build-manifest.json')));assert.equal(files['core.mjs'],manifest.coreSha256);
  return {sdk:resolve(sdk),manifest,files};
}
async function worker(path){
  const job=JSON.parse(readFileSync(path)),inputBytes=readFileSync(job.input),input=JSON.parse(inputBytes);
  assert.equal(sha(inputBytes),job.inputSha256,'Frozen input differs');
  const started=performance.now(),api=await import(pathToFileURL(job.sdk).href),importMs=performance.now()-started;
  assert.equal(typeof api[input.api],'function');const before=sha(JSON.stringify(input.arguments));
  let output,wire,firstCallMs=null;
  const call=()=>{output=api[input.api](...input.arguments);wire=JSON.stringify(output);};
  if(job.mode==='cold'){const mark=performance.now();call();firstCallMs=performance.now()-mark;}
  else for(let i=0;i<job.warmups;i++)call();
  const samples=[];
  if(job.mode!=='cold')for(let i=0;i<job.samples;i++){const mark=performance.now();call();samples.push(performance.now()-mark);}
  assert.equal(sha(JSON.stringify(input.arguments)),before,'SDK mutated independent arguments');
  assert.equal(sha(canonical(output)),input.expectedCanonicalSha256,'Complete output differs from frozen baseline');
  assert.equal(Buffer.byteLength(wire),input.outputBytes,'Output scope changed');
  assert.equal(sha(readFileSync(job.input)),sha(inputBytes),'Frozen input changed');
  save(job.result,{passed:true,mode:job.mode,api:input.api,importMs,firstCallMs,
    coldFullMs:firstCallMs===null?null:importMs+firstCallMs,samples,
    peakRssKiB:process.resourceUsage().maxRSS,fullOutputBytes:Buffer.byteLength(wire),
    fullOutputSha256:sha(wire),canonicalOutputSha256:sha(canonical(output)),argumentsUnchanged:true});
}
async function controller(argv){
  const flags={};while(argv.length){const key=argv.shift();assert(['--config','--output','--smoke'].includes(key)&&!Object.hasOwn(flags,key));flags[key]=key==='--smoke'?true:argv.shift();}
  assert(flags['--config']&&flags['--output']);
  const configPath=resolve(flags['--config']),configBytes=readFileSync(configPath),config=JSON.parse(configBytes),base=dirname(configPath);
  assert.equal(config.schemaVersion,1);assert(Array.isArray(config.cases)&&config.cases.length>0&&config.cases.length<=32);
  const formal=!flags['--smoke'];assert(!formal||config.exclusiveExecution===true,'Stop other local work before formal measurements');
  const protocol=formal?{warmups:5,samples:30,batches:3}:{warmups:1,samples:2,batches:1};
  const output=resolve(flags['--output']);mkdirSync(output);mkdirSync(resolve(output,'inputs'));mkdirSync(resolve(output,'workers'));
  const before={baseline:runtime(resolve(base,config.baseline.sdk)),candidate:runtime(resolve(base,config.candidate.sdk))};
  const harnessBytes=readFileSync(self),frozenHarness=resolve(output,'harness.mjs');writeFileSync(frozenHarness,harnessBytes,{flag:'wx'});
  save(resolve(output,'config.json'),config);save(resolve(output,'environment.json'),{
    node:process.version,platform:platform(),architecture:arch(),osRelease:release(),cpus:cpus().map(cpu=>cpu.model),
    totalMemoryBytes:totalmem(),freeMemoryBytesBefore:freemem(),protocol,formal,
    scope:'complete synchronous SDK call plus full JSON output serialization; fresh-process import/cold and independent memory workers',
    baselineSource:config.baseline.sourceCommit,candidateSource:config.candidate.sourceCommit,harnessSha256:sha(harnessBytes),before});
  const inputs=[];
  for(const item of config.cases){
    assert(/^[a-z0-9-]+$/.test(item.id)&&!inputs.some(input=>input.id===item.id));
    const bytes=readFileSync(resolve(base,item.input)),parsed=JSON.parse(bytes);
    assert(['verifyConfiguredWindowV4','verifyConfiguredWindowReductionV4','analyze','classifyModelsV4'].includes(parsed.api));
    assert(Array.isArray(parsed.arguments)&&typeof parsed.expectedCanonicalSha256==='string');
    const input=resolve(output,'inputs',item.id+'.json');writeFileSync(input,bytes,{flag:'wx'});inputs.push({...item,input,inputSha256:sha(bytes)});
  }
  assert(inputs.some(input=>input.control===true),'Explicit common controls are required');
  const jobs=[];let index=0;
  for(let batch=0;batch<protocol.batches;batch++)for(const item of inputs)for(const mode of ['timing','memory','cold']){
    for(const side of batch%2?['candidate','baseline']:['baseline','candidate']){
      const prefix=String(index++).padStart(4,'0')+'-'+item.id+'-'+side+'-'+batch+'-'+mode;
      const result=resolve(output,'workers',prefix+'.result.json'),path=resolve(output,'workers',prefix+'.job.json');
      const job={sdk:before[side].sdk,input:item.input,inputSha256:item.inputSha256,result,mode,...protocol};save(path,job);
      const run=spawnSync(process.execPath,[frozenHarness,'--worker',path],{encoding:'utf8',windowsHide:true,timeout:300000,maxBuffer:1024*1024});
      if(run.error||run.status!==0){save(resolve(output,'failure.json'),{job:prefix,status:run.status,error:run.error?.message??null,stderr:run.stderr});throw Error('Worker failed: '+prefix);}
      const data=JSON.parse(readFileSync(result));assert.equal(data.passed,true);jobs.push({id:item.id,side,batch,mode,data});
    }
    console.log(JSON.stringify({phase:'measured',case:item.id,batch,mode}));
  }
  assert.deepEqual(runtime(before.baseline.sdk),before.baseline,'Baseline runtime mutated');assert.deepEqual(runtime(before.candidate.sdk),before.candidate,'Candidate runtime mutated');
  assert.equal(sha(readFileSync(frozenHarness)),sha(harnessBytes),'Frozen harness mutated');assert.equal(sha(readFileSync(configPath)),sha(configBytes),'Original config mutated');
  for(const item of inputs)assert.equal(sha(readFileSync(item.input)),item.inputSha256,'Frozen workload mutated');
  const rows=inputs.map(item=>{
    const metrics={};for(const side of ['baseline','candidate']){
      const selected=jobs.filter(job=>job.id===item.id&&job.side===side),timing=selected.filter(job=>job.mode==='timing').flatMap(job=>job.data.samples);
      metrics[side]={...stats(timing),peakRssKiB:stats(selected.filter(job=>job.mode==='memory').map(job=>job.data.peakRssKiB)).median,
        coldFullMs:stats(selected.filter(job=>job.mode==='cold').map(job=>job.data.coldFullMs)).median,
        outputBytes:selected[0].data.fullOutputBytes,canonicalOutputSha256:selected[0].data.canonicalOutputSha256};
    }
    const speedup=metrics.baseline.median/metrics.candidate.median,rssRatio=metrics.candidate.peakRssKiB/metrics.baseline.peakRssKiB;
    return {id:item.id,control:item.control===true,api:jobs.find(job=>job.id===item.id).data.api,...metrics,speedup,rssRatio,
      p95ControlPassed:!item.control||metrics.candidate.p95-metrics.baseline.p95<=Math.max(2,metrics.baseline.p95*.1)};
  });
  const targets=rows.filter(row=>!row.control),result={format:'moontxnwitness-window-verification-performance/v1',formal,passed:rows.every(row=>row.p95ControlPassed),protocol,
    measurementScope:'full public SDK verification and complete output; baseline is the frozen local source-closed-window build, not an earlier public release',
    timingSamples:jobs.filter(job=>job.mode==='timing').reduce((sum,job)=>sum+job.data.samples.length,0),
    geometricSpeedup:geomean(targets.map(row=>row.speedup)),geometricRssRatio:geomean(targets.map(row=>row.rssRatio)),rows};
  save(resolve(output,'summary.json'),result);console.log(JSON.stringify({phase:'complete',formal,passed:result.passed,timingSamples:result.timingSamples,geometricSpeedup:result.geometricSpeedup,geometricRssRatio:result.geometricRssRatio}));
  if(!result.passed)process.exitCode=1;
}
try{if(process.argv[2]==='--worker')await worker(process.argv[3]);else await controller(process.argv.slice(2));}
catch(error){console.error(error.stack);process.exitCode=1;}
