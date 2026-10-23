// Public v0.2.0 SDK baseline. Formal measurement must run alone on this host.
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,writeFileSync,copyFileSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {performance} from 'node:perf_hooks';
import {gzipSync,gunzipSync} from 'node:zlib';
import {platform,release,arch,cpus,homedir} from 'node:os';
import {isDeepStrictEqual} from 'node:util';
import {performanceFixturesV020} from './performance-v020-fixtures.mjs';
import {verificationFingerprint} from './verification-fingerprint.mjs';
import {sourceFingerprint} from './build-fingerprint.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const digest=value=>createHash('sha256').update(value).digest('hex');
const load=p=>JSON.parse(readFileSync(p,'utf8'));
const rel=p=>relative(root,p).split('\\').join('/');
const json=value=>JSON.stringify(value,null,2)+'\n';
const median=a=>[...a].sort((x,y)=>x-y)[Math.floor(a.length/2)];
const p95=a=>[...a].sort((x,y)=>x-y)[Math.ceil(a.length*.95)-1];
const geomean=a=>Math.exp(a.reduce((s,v)=>s+Math.log(v),0)/a.length);
const immutable=(p,value)=>writeFileSync(p,typeof value==='string'||Buffer.isBuffer(value)?value:json(value),{flag:'wx'});
function cleanError(error) {
  let message=String(error?.stack||error);
  for(const [path,label] of [[root,'<workspace>'],[homedir(),'<home>']])
    for(const variant of [path,path.split('\\').join('/')]) message=message.replaceAll(variant,label);
  return {name:error?.name||'Error',message};
}
function normalizedEngine(value,phase,engine) {
  const result=structuredClone(value);
  const report=(phase==='reduce'||phase==='legacy-reduce')?result.report:result;
  if(phase==='legacy-reduce'){assert.equal(result.version,engine,'Unexpected reduction engine');result.version='<engine-version>';}
  if(phase==='normalize')return result;
  assert.equal(report.version,engine,'Unexpected report engine');
  report.version='<engine-version>';
  if(phase==='analyze'||phase==='reduce') {
    const evidence=report.evidence;
    if(evidence?.tool==='MoonTxnWitness'&&evidence.schemaVersion===2) {
      assert.equal(evidence.version,engine,'Unexpected nested evidence engine');
      evidence.version='<engine-version>';
    }
  }
  return result;
}
function invoke(sdk,fixture,text) {
  if(fixture.phase==='normalize')return sdk.normalizeCaptureV3(text);
  if(fixture.phase==='analyze')return sdk.analyzeV3(text);
  if(fixture.phase==='reduce')return sdk.reduceV3(text);
  if(fixture.phase==='legacy')return sdk.analyzeWithOptions(text);
  if(fixture.phase==='legacy-reduce')return sdk.shrinkWithOptions(text);
  throw Error('Unknown phase');
}
async function worker() {
  const [sdkPath,fixturePath,warmupText,sampleText,engine,outputPath]=process.argv.slice(3);
  const fixture=load(fixturePath),text=JSON.stringify(fixture.input);
  const startLoad=performance.now();
  const sdk=await import(pathToFileURL(sdkPath).href);
  const loadMs=performance.now()-startLoad;
  assert.equal(sdk.version(),engine);
  const startCold=performance.now();let output=invoke(sdk,fixture,text);const coldMs=performance.now()-startCold;
  if(fixture.expectedStatus!==null)assert.equal(output.status,fixture.expectedStatus,fixture.name+' '+fixture.phase);
  for(let i=0;i<Number(warmupText);i++)invoke(sdk,fixture,text);
  const timesMs=[];
  for(let i=0;i<Number(sampleText);i++) {
    const start=performance.now();output=invoke(sdk,fixture,text);timesMs.push(performance.now()-start);
  }
  const peakRssKiB=process.resourceUsage().maxRSS;
  // Correctness, encoding, compression and archival deliberately follow samples
  // and the process RSS snapshot. Complete SDK analysis/normalization is timed.
  if(fixture.expectedStatus!==null)assert.equal(output.status,fixture.expectedStatus,fixture.name+' '+fixture.phase);
  const comparable=normalizedEngine(output,fixture.phase,engine);
  const bytes=Buffer.from(json(output)),packed=gzipSync(bytes);
  immutable(outputPath,packed);
  console.log(JSON.stringify({version:engine,name:fixture.name,phase:fixture.phase,group:fixture.group,
    inputSha256:digest(Buffer.from(text)),loadMs,coldMs,timesMs,medianMs:median(timesMs),p95Ms:p95(timesMs),peakRssKiB,
    fullOutput:{jsonBytes:bytes.length,jsonSha256:digest(bytes),gzipBytes:packed.length,gzipSha256:digest(packed),normalizedSha256:digest(json(comparable))}}));
}
function prepareBaseline(work) {
  const manifestPath=resolve(root,'verification/baselines/0.2.0/manifest.json');
  assert.equal(digest(readFileSync(manifestPath)),'0b764ff214e1a5cf6732a7c783899c4bbfeec2dd13b7c0ecbeb0732757f68503','Published20 baseline manifest changed');
  const pinned=load(manifestPath);
  assert.equal(pinned.version,'0.2.0');
  assert.equal(pinned.publicArchiveSha256,'92ffd79314841e09b7ba13209c7678d4626265d74c3c12dba2726089e9b490a3');
  assert.equal(digest(readFileSync(resolve(root,pinned.anonymousDownloadReviewReceipt))),pinned.anonymousDownloadReviewReceiptSha256);
  assert.equal(load(resolve(root,pinned.anonymousDownloadReviewReceipt)).passed,true);
  const out=resolve(work,'baseline');mkdirSync(out);
  for(const [name,record] of Object.entries(pinned.files)) {
    const source=resolve(root,pinned.provider,name),bytes=readFileSync(source);
    assert.equal(bytes.length,record.bytes);assert.equal(digest(bytes),record.sha256);
    copyFileSync(source,resolve(out,name));
  }
  assert.deepEqual(load(resolve(out,'build-manifest.json')),pinned.buildManifest);
  return {sdk:resolve(out,'sdk.mjs'),pin:pinned,manifestSha256:digest(readFileSync(manifestPath))};
}
async function controller() {
  const args=process.argv.slice(2);
  if(args.some(x=>x!=='--quick')||args.length>1)throw Error('Usage: node scripts/performance-v020.mjs [--quick]');
  const quick=args.includes('--quick'),warmups=quick?1:5,samples=quick?1:30,batches=quick?1:3;
  const version=load(resolve(root,'package.json')).version;
  const stamp=new Date().toISOString().replace(/[:.]/g,'-')+'-'+randomUUID().slice(0,8);
  const work=resolve(root,'verification/performance-v020','run-'+stamp);mkdirSync(work,{recursive:true});
  const baseline=prepareBaseline(work),candidate=resolve(root,'dist/sdk.mjs');
  const candidateManifest=load(resolve(root,'dist/build-manifest.json'));
  assert.equal(candidateManifest.version,version);
  assert.equal(candidateManifest.sourceSha256,sourceFingerprint(root),'Candidate source differs from current build');
  for(const [name,field] of [['core.mjs','coreSha256'],['capture-core.mjs','captureCoreSha256']])assert.equal(digest(readFileSync(resolve(root,'dist',name))),candidateManifest[field]);
  for(const name of ['sdk.mjs','evidence.mjs'])assert.deepEqual(readFileSync(resolve(root,'dist',name)),readFileSync(resolve(root,'cmd',name)),'Candidate wrapper differs');
  assert.deepEqual(candidateManifest.toolchain,baseline.pin.buildManifest.toolchain,'Use the same compiler/toolchain');
  const originalInputs=verificationFingerprint(root);
  const fixtures=performanceFixturesV020(root),fixtureFiles=[];
  for(const fixture of fixtures) {
    const path=resolve(work,fixture.name+'-'+fixture.phase+'.fixture.json');immutable(path,fixture);fixtureFiles.push(path);
  }
  const rows=[],comparisons=[];
  const receipt={schema:1,kind:'public-v020-complete-sdk-performance',version,baselineVersion:'0.2.0',
    formalPerformanceMeasurement:!quick,warmups,samples,batches,startedAt:new Date().toISOString(),
    candidateBuild:candidateManifest,baselineManifestSha256:baseline.manifestSha256,
    machine:{platform:platform(),release:release(),arch:arch(),cpus:cpus().map(x=>x.model),node:process.version,nodeSha256:digest(readFileSync(process.execPath))},
    inputBindings:Object.fromEntries(fixtureFiles.map(p=>[rel(p),digest(readFileSync(p))])),
    correctnessPassed:false,performancePassed:null,completed:false,workers:rows,comparisons};
  immutable(resolve(work,'plan.json'),receipt);
  try {
    for(let batch=0;batch<batches;batch++) {
      for(let i=0;i<fixtures.length;i++) {
        const fixture=fixtures[i],pair={};
        const order=batch%2===0?['baseline','candidate']:['candidate','baseline'];
        for(const which of order) {
          const prefix=`batch-${batch+1}-${fixture.name}-${fixture.phase}-${which}`;
          const output=resolve(work,prefix+'.output.json.gz');
          const sdk=which==='baseline'?baseline.sdk:candidate,engine=which==='baseline'?'0.2.0':version;
          const child=spawnSync(process.execPath,[fileURLToPath(import.meta.url),'--worker',sdk,fixtureFiles[i],String(warmups),String(samples),engine,output],
            {cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024,timeout:300000});
          immutable(resolve(work,prefix+'.stdout.txt'),child.stdout||'');
          immutable(resolve(work,prefix+'.stderr.txt'),String(child.stderr||'').replaceAll(root,'<workspace>').replaceAll(root.split('\\').join('/'),'<workspace>'));
          if(child.error)throw child.error;
          assert.equal(child.status,0,'Worker failed: '+prefix);
          const row=JSON.parse(child.stdout.trim());row.batch=batch+1;row.variant=which;row.output=rel(output);
          const packed=readFileSync(output);assert.equal(digest(packed),row.fullOutput.gzipSha256);
          const raw=gunzipSync(packed);assert.equal(digest(raw),row.fullOutput.jsonSha256);
          row.outputObject=normalizedEngine(JSON.parse(raw),fixture.phase,engine);
          pair[which]=row;rows.push({...row,outputObject:undefined});
          immutable(resolve(work,prefix+'.samples.json'),rows.at(-1));
        }
        assert.ok(isDeepStrictEqual(pair.baseline.outputObject,pair.candidate.outputObject),'Complete output disagreement: '+fixture.name+' '+fixture.phase);
        comparisons.push({batch:batch+1,name:fixture.name,phase:fixture.phase,group:fixture.group,semanticAgreement:true,
          medianSpeedup:pair.baseline.medianMs/pair.candidate.medianMs,
          rssRatio:pair.candidate.peakRssKiB/pair.baseline.peakRssKiB,
          baselineP95Ms:pair.baseline.p95Ms,candidateP95Ms:pair.candidate.p95Ms,
          controlP95Passed:pair.candidate.p95Ms-pair.baseline.p95Ms<=Math.max(2,pair.baseline.p95Ms*.1)});
        console.log(JSON.stringify({batch:batch+1,name:fixture.name,phase:fixture.phase,completeOutputAgreement:true,completedWorkers:rows.length}));
      }
    }
    assert.deepEqual(verificationFingerprint(root),originalInputs,'Executable files changed during measurement');
    const groups={};
    for(const group of ['full-v3','normalization','reduction-v3','control']) {
      const pairs=comparisons.filter(x=>x.group===group);
      groups[group]={cases:new Set(pairs.map(x=>x.name+' '+x.phase)).size,comparisons:pairs.length,
        medianSpeedupGeomean:geomean(pairs.map(x=>x.medianSpeedup)),peakRssRatioGeomean:geomean(pairs.map(x=>x.rssRatio)),
        controlFailures:pairs.filter(x=>!x.controlP95Passed).map(x=>({batch:x.batch,name:x.name,phase:x.phase}))};
    }
    receipt.groups=groups;receipt.correctnessPassed=true;receipt.completed=true;
    receipt.performancePassed=quick?null:comparisons.every(x=>x.controlP95Passed)&&groups['full-v3'].medianSpeedupGeomean>=1.15;
    receipt.controlPassed=comparisons.every(x=>x.controlP95Passed);
    receipt.targetPassed=quick?null:groups['full-v3'].medianSpeedupGeomean>=1.15;
    receipt.finishedAt=new Date().toISOString();
    immutable(resolve(work,'receipt.json'),receipt);
    console.log(JSON.stringify({receipt:rel(resolve(work,'receipt.json')),quick,correctnessPassed:true,performancePassed:receipt.performancePassed,groups}));
    if(!quick&&!receipt.performancePassed)process.exitCode=2;
  } catch(error) {
    receipt.failure=cleanError(error);receipt.finishedAt=new Date().toISOString();receipt.performancePassed=false;
    immutable(resolve(work,'receipt.json'),receipt);throw error;
  }
}
if(process.argv[2]==='--worker')await worker();else await controller();
