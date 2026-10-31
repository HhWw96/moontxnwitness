// Functional byte/semantic comparison only. No warmups, timing samples or goals.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,lstatSync} from 'node:fs';
import {resolve,relative,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {freemem} from 'node:os';
import {PUBLIC031} from '../cmd/legacy-v031-binding.mjs';
import {checkResult} from './bench/full-sdk/common.mjs';
import {normalizeProductMetadataOnly} from './bench/full-sdk/report-transport-normalization.mjs';
import {originalSixControls} from './bench/full-sdk/metadata-controls.mjs';
import {parseStaticImports,STATIC_IMPORT_CONTRACT} from './bench/full-sdk/parse-static-imports.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const sha=value=>createHash('sha256').update(value).digest('hex');
const index=JSON.parse(readFileSync(resolve(root,'scripts/bench/full-sdk/fixtures/index.json'),'utf8'));
function closure(folder,pins=null){
 const files={},pending=['sdk.mjs'];
 while(pending.length){
  const name=pending.pop();if(Object.hasOwn(files,name))continue;
  const path=resolve(folder,name);assert(!relative(folder,path).startsWith('..'));
  assert(lstatSync(path).isFile());const bytes=readFileSync(path),digest=sha(bytes);
  if(pins){assert(Object.hasOwn(pins,name));assert.equal(digest,pins[name].sha256,name);assert.equal(bytes.length,pins[name].bytes,name);}
  files[name]={sha256:digest,bytes:bytes.length};
  if(name.endsWith('.mjs'))for(const dependency of parseStaticImports(bytes,name).relativeDependencies){
   pending.push(dependency.target);
  }
 }
 return files;
}

if(process.argv[2]==='--worker'){
 const [subjectPath,name,scenario]=process.argv.slice(3),subjects=JSON.parse(readFileSync(subjectPath,'utf8'));
 const folder=subjects[name],before=closure(folder,name==='baseline'?PUBLIC031.files:null);
 const row=index.scenarios.find(value=>value.name===scenario);assert(row);
 const source=readFileSync(resolve(root,'scripts/bench/full-sdk',row.path));assert.equal(sha(source),row.sha256);
 const fixture=JSON.parse(source),original=JSON.stringify(fixture.history),options=JSON.stringify(fixture.options);
 assert.equal(sha(original),row.originalHistorySha256);
 const sdk=await import(pathToFileURL(resolve(folder,'sdk.mjs'))),core=await import(pathToFileURL(resolve(folder,'core.mjs')));
 const report=fixture.method==='analyzeWithOptions'?sdk.analyzeWithOptions(fixture.history,fixture.options):sdk.analyze(fixture.history);
 checkResult(report,fixture,sdk.version());
 if(name==='candidate'){assert.equal(typeof core.analyze_native_js_v1,'function');assert.equal(typeof core.analyze_options_native_js_v1,'function');}
 const wire=fixture.method==='analyzeWithOptions'?core.analyze_options_json(original,options):core.analyze_json(original);
 assert.deepEqual(JSON.parse(wire),report,'Original core wire and actual SDK object differ');
 assert.equal(JSON.stringify(fixture.history),original);assert.equal(JSON.stringify(fixture.options),options);
 const encoded=JSON.stringify(report),normalize=raw=>normalizeProductMetadataOnly(raw,{entry:'analyze_json',format:null,version:sdk.version()});
 if(fixture.expectedEdges===49770){assert(Buffer.byteLength(encoded)>5*1024*1024);assert(Buffer.byteLength(wire)>5*1024*1024);}
 assert.deepEqual(closure(folder,name==='baseline'?PUBLIC031.files:null),before);
 console.log(JSON.stringify({subject:name,scenario,sdkMethod:fixture.method,version:sdk.version(),
  status:report.status,dependencies:report.edges.length,SDKOutputBytes:Buffer.byteLength(encoded),
  wireOutputBytes:Buffer.byteLength(wire),SDKOutputSha256:sha(encoded),wireOutputSha256:sha(wire),
  normalizedSDKSha256:sha(normalize(encoded)),normalizedWireSha256:sha(normalize(wire)),
  fixtureSha256:sha(source),originalHistorySha256:sha(original),inputUnchanged:true,
  runtimeBefore:before,runtimeAfterUnchanged:true,sdkCalls:1,wireCalls:1,
  fullReportValidated:true,formalPerformanceMeasurement:false}));
}else{
 const argv=process.argv.slice(2),args={};
 for(let i=0;i<argv.length;i+=2){assert(['--candidate-runtime','--baseline-runtime','--output'].includes(argv[i]));assert(argv[i+1]);assert(!Object.hasOwn(args,argv[i]));args[argv[i]]=argv[i+1];}
 for(const key of ['--candidate-runtime','--baseline-runtime','--output'])assert(args[key]);
 const out=resolve(args['--output']);mkdirSync(out,{recursive:false});
 const subjects={baseline:resolve(args['--baseline-runtime']),candidate:resolve(args['--candidate-runtime'])};
 const baseline=closure(subjects.baseline,PUBLIC031.files);assert.equal(baseline['core.mjs'].sha256,'5b004a504ef787bb806899cd1fa243ed9db02ad68c0276599c9aad5821719cb9');assert.equal(baseline['sdk.mjs'].sha256,'534b4c0a2767aee02a7d090c4ce51d49a67f05ccde18424d2a2944df559f407d');
 assert.equal(Object.keys(baseline).length,25,'Require the complete actual public031 static module closure');
 const candidate=closure(subjects.candidate),subjectPath=resolve(out,'subjects.json');
 assert.equal(Object.keys(candidate).length,36,'Require the complete actual current SDK static module closure');
 writeFileSync(subjectPath,JSON.stringify(subjects,null,2)+'\n',{flag:'wx'});
 const controls=originalSixControls();assert.equal(controls.negativeControls,6);
 const results=[];
 for(const row of index.scenarios){
  const pair={scenario:row.name};
  for(const name of ['baseline','candidate']){
   assert(freemem()>=1.2*1024**3,'Stop before functional worker when physical reserve is insufficient');
   const child=spawnSync(process.execPath,['--experimental-vm-modules','--max-old-space-size=512',fileURLToPath(import.meta.url),'--worker',subjectPath,name,row.name],{
    cwd:root,env:{...process.env,NODE_OPTIONS:'',NODE_DISABLE_COMPILE_CACHE:'1'},encoding:'utf8',windowsHide:true,maxBuffer:1024*1024,timeout:120000});
   writeFileSync(resolve(out,row.name+'-'+name+'.log'),child.stdout+child.stderr,{flag:'wx'});
   assert.equal(child.status,0,child.stdout+child.stderr);pair[name]=JSON.parse(child.stdout);
  }
  assert.equal(pair.baseline.normalizedSDKSha256,pair.candidate.normalizedSDKSha256,row.name+' full SDK bytes');
  assert.equal(pair.baseline.normalizedWireSha256,pair.candidate.normalizedWireSha256,row.name+' original JSON wire bytes');
  results.push(pair);
 }
 assert.deepEqual(closure(subjects.baseline,PUBLIC031.files),baseline);assert.deepEqual(closure(subjects.candidate),candidate);
 const receipt={format:'native-report-functional-comparison/v1',passed:true,scenarios:results.length,
  SDKCalls:results.length*2,wireCalls:results.length*2,negativeControls:controls.negativeControls,results,
  actualSDKAndCoreWireBothChecked:true,baselinePublicVersion:PUBLIC031.version,
  productMetadataNormalizationOnly:true,businessMetadataNormalizationChanged:false,
  heapFlag:'--max-old-space-size=512',formalPerformanceMeasurement:false,
  staticParser:STATIC_IMPORT_CONTRACT,baselineStaticModules:25,candidateStaticModules:36,
  staticParserOnlyNotLinkedOrEvaluated:true,dynamicImportsIncludedInInventory:false,
  runtimeBeforeAndAfterUnchanged:true,DWritten:false};
 writeFileSync(resolve(out,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify({passed:true,scenarios:receipt.scenarios,SDKCalls:receipt.SDKCalls,
  wireCalls:receipt.wireCalls,negativeControls:receipt.negativeControls,formalPerformanceMeasurement:false}));
}
