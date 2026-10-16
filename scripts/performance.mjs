import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync, readFileSync, copyFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cpus, platform, release, arch } from 'node:os';
import { spawn } from 'node:child_process';
import { fixtures } from './benchmark-fixtures.mjs';
import { root } from './moon.mjs';
const args=process.argv.slice(2);
let baseline=resolve(root,'artifacts/baseline-v0.0.6/core.mjs'),quick=false,profile='compat',label='performance';
for(let i=0;i<args.length;i++){
  if(args[i]==='--baseline')baseline=resolve(args[++i]);
  else if(args[i]==='--quick')quick=true;
  else if(args[i]==='--profile')profile=args[++i];
  else if(args[i]==='--label')label=args[++i];
  else throw Error('Usage: performance [--baseline core.mjs] [--quick] [--profile compat|balanced] [--label NAME]');
}
assert.ok(['compat','balanced'].includes(profile));assert.match(label,/^[a-zA-Z0-9-]+$/);
const version=JSON.parse(readFileSync(resolve(root,'package.json'),'utf8')).version;
const work=resolve(root,`artifacts/bench-${version}-${label}-${Date.now()}`);mkdirSync(work,{recursive:true});
copyFileSync(resolve(root,'dist/core.mjs'),resolve(work,'current.mjs'));copyFileSync(baseline,resolve(work,'baseline.mjs'));
const hash=text=>createHash('sha256').update(text).digest('hex');
const cases=fixtures();for(const c of cases)writeFileSync(resolve(work,c.name+'.json'),JSON.stringify(c));
function run(engine,c,phase='full'){
  return new Promise((done,reject)=>{
    const child=spawn(process.execPath,[resolve(root,'scripts/benchmark-worker.mjs'),resolve(work,engine+'.mjs'),resolve(work,c.name+'.json'),phase,quick?'1':'5',quick?'3':'30',engine==='current'?profile:'compat'],{stdio:['ignore','pipe','pipe']});
    let stdout='',stderr='';child.stdout.on('data',v=>stdout+=v);child.stderr.on('data',v=>stderr+=v);
    const timer=setTimeout(()=>child.kill(),240000);
    child.on('error',reject);child.on('close',code=>{clearTimeout(timer);if(code!==0)return reject(Error(`Benchmark ${engine}/${c.name}/${phase}: ${stderr}`));try{done(JSON.parse(stdout));}catch(e){reject(e);}});
  });
}
const receipt={tool:'MoonTxnWitness',version,passed:false,protocol:quick?'smoke-only':'5 warmups, 30 measured samples, 3 independent alternating process batches',profile,baselineVersion:'0.0.6',baselineSha256:hash(readFileSync(baseline)),currentSha256:hash(readFileSync(resolve(work,'current.mjs'))),environment:{node:process.version,os:platform(),release:release(),arch:arch(),cpu:cpus()[0].model},results:[],phases:[],targets:{graphSpeedup:2,graphPeakMemoryReduction:.3,searchSpeedup:2,reductionSpeedup:2},caveat:'Full reports compared with full reports. Local measurements; target attainment is separate from correctness.'};
const median=a=>[...a].sort((x,y)=>x-y)[Math.floor(a.length/2)];
for(const c of cases){
  const observations={current:[],baseline:[]};let semantic=null;
  for(let batch=0;batch<(quick?1:3);batch++)for(const engine of batch%2?['baseline','current']:['current','baseline']){
    const row=await run(engine,c);const stable=row.semantic;delete row.semantic;
    if(!semantic)semantic=stable;else assert.deepEqual(stable,semantic,`Semantic disagreement: ${c.name}`);
    observations[engine].push(row);
  }
  const current=median(observations.current.map(r=>r.medianMs)),old=median(observations.baseline.map(r=>r.medianMs));
  receipt.results.push({scenario:c.name,group:c.group,inputSha256:hash(JSON.stringify(c.history)),inputBytes:Buffer.byteLength(JSON.stringify(c.history)),semanticAgreement:true,speedup:old/current,memoryRatio:median(observations.current.map(r=>r.peakRssKiB))/median(observations.baseline.map(r=>r.peakRssKiB)),...observations});
  console.log(`${c.name}: ${current.toFixed(2)} ms; ${(old/current).toFixed(2)}x baseline`);
}
for(const name of ['dense-rt-192','long-ring-128','completion-impossible-8','reduction-64']){
  const c=cases.find(c=>c.name===name);const rows=[];
  const phases=c.operation==='shrink'?['parse','inference','reduction']:c.group==='search'?['parse','inference','search','render']:['parse','inference','cycle','render'];
  for(const phase of phases)rows.push(await run('current',c,phase));
  receipt.phases.push({scenario:name,measurements:rows});
}
receipt.groups=Object.fromEntries(['graph','search','reduction','control'].map(group=>{
  const rows=receipt.results.filter(r=>r.group===group);const speedup=Math.exp(rows.reduce((s,r)=>s+Math.log(r.speedup),0)/rows.length);const memoryRatio=Math.exp(rows.reduce((s,r)=>s+Math.log(r.memoryRatio),0)/rows.length);
  return [group,{geometricMeanSpeedup:speedup,geometricMeanPeakMemoryRatio:memoryRatio,targetMet:group==='graph'?speedup>=2&&memoryRatio<=.7:group==='control'?rows.every(r=>median(r.current.map(v=>v.p95Ms))-median(r.baseline.map(v=>v.p95Ms))<=Math.max(2,median(r.baseline.map(v=>v.p95Ms))*.1)):speedup>=2}];
}));
receipt.passed=true;receipt.performanceTargetsMet=!quick&&Object.values(receipt.groups).every(g=>g.targetMet);
mkdirSync(resolve(root,'verification/releases',version),{recursive:true});
writeFileSync(resolve(root,'verification/releases',version,label+'.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({correctnessPassed:receipt.passed,performanceTargetsMet:receipt.performanceTargetsMet,groups:receipt.groups}));
