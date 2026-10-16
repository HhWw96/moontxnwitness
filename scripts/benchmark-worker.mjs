import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
const [corePath, fixturePath, phase='full', warm='5', sample='30', profile='compat'] = process.argv.slice(2);
const started=performance.now();
const core=await import(pathToFileURL(corePath).href);
const loadMs=performance.now()-started;
const fixture=JSON.parse(readFileSync(fixturePath,'utf8'));
const text=JSON.stringify(fixture.history);
let run;
if(phase==='full')run=()=>JSON.parse(fixture.operation==='shrink'
  ? profile==='balanced' && core.shrink_options_json ? core.shrink_options_json(text,'{}') : core.shrink_json(text)
  : profile==='balanced' && core.analyze_options_json ? core.analyze_options_json(text,'{}') : core.analyze_json(text));
else {
  if(!core.benchmark_parse){console.log(JSON.stringify({available:false,phase}));process.exit(0);}
  const parse=profile==='balanced'&&core.benchmark_parse_balanced?core.benchmark_parse_balanced:core.benchmark_parse;
  const h=parse(text);const r=core.benchmark_infer(h);
  const functions={parse:()=>parse(text),inference:()=>core.benchmark_infer(h),cycle:()=>core.benchmark_cycle(h,r),search:()=>profile==='balanced' && core.benchmark_search_balanced ? core.benchmark_search_balanced(h,r) : core.benchmark_search(h,r),render:()=>core.benchmark_render(r),reduction:()=>profile==='balanced' && core.benchmark_reduce_balanced ? core.benchmark_reduce_balanced(h) : core.benchmark_reduce(h)};
  run=functions[phase];if(!run)throw Error('Unknown phase');
}
const first=performance.now();let output=run();const firstMs=performance.now()-first;
for(let i=0;i<Number(warm);i++)run();
const timesMs=[];
for(let i=0;i<Number(sample);i++){const start=performance.now();output=run();timesMs.push(performance.now()-start);}
let semantic=null;let outputBytes=null;
if(phase==='full'){
  const report=output.report||output;
  assert.equal(output.status,fixture.status);
  if(fixture.cycle)assert.equal(report.witness.edges.length,fixture.cycle);
  if(fixture.operation==='shrink'){assert.equal(output.oneMinimal,true);assert.equal(output.reducedHistory.transactions.length,2);}
  const {version,schemaVersion,algorithm,analysisOptions,effectiveLimits,metrics,graph,search,coverage,nextSteps,...stable}=report;
  semantic=stable;outputBytes=Buffer.byteLength(JSON.stringify(output));
}
const sorted=[...timesMs].sort((a,b)=>a-b);
console.log(JSON.stringify({available:true,version:core.version(),profile,phase,loadMs,firstMs,timesMs,medianMs:sorted[Math.floor(sorted.length/2)],p95Ms:sorted[Math.ceil(sorted.length*.95)-1],peakRssKiB:process.resourceUsage().maxRSS,outputBytes,semantic}));
