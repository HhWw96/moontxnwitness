import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {resolve,dirname,relative,isAbsolute} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {sha,fileSHA,environment,checkSubject,checkSources} from './common.mjs';
const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
assert.equal(process.platform,'linux');assert.equal(process.version,'v24.13.0');
assert.equal(process.env.GITHUB_ACTIONS,'true','Registered Linux job required');
const metadata=JSON.parse(readFileSync(resolve(ROOT,'subjects.json'))),inputs=JSON.parse(readFileSync(resolve(ROOT,'input-manifest.json')));
const imports=/(?:\b(?:import|export)\s+(?:[^;\n]*?\s+from\s*)?)["'](\.[^"']+)["']/g;
function closure(entry,expected=null){
 const base=dirname(entry),todo=[entry],files={},staticImports=[];
 while(todo.length){const file=todo.pop(),name=relative(base,file).replaceAll('\\','/');assert(!name.startsWith('../')&&!isAbsolute(name));if(files[name])continue;
  const bytes=readFileSync(file),digest=sha(bytes);if(expected){assert.equal(digest,expected[name]?.sha256,name);assert.equal(bytes.length,expected[name]?.bytes,name);}
  files[name]={path:file,bytes:bytes.length,sha256:digest};
  for(const match of bytes.toString('utf8').matchAll(imports)){const target=resolve(dirname(file),match[1]),key=relative(base,target).replaceAll('\\','/');assert(!key.startsWith('../')&&!isAbsolute(key));staticImports.push({from:name,to:key});todo.push(target);}
 }return{entry,files,staticImports,dynamicCompatibilityCallsNotExecuted:true};
}
const baseline={...metadata.baseline,...closure(metadata.baseline.entry,metadata.baseline.publicFiles),label:'actual-public031-original-compiled-SDK'};
const candidate={...metadata.candidate,...closure(metadata.candidate.entry),label:'Linux-CI-checkout-'+metadata.candidate.sourceCommit};
assert.equal(baseline.files['core.mjs'].sha256,'5b004a504ef787bb806899cd1fa243ed9db02ad68c0276599c9aad5821719cb9');
assert.equal(baseline.files['sdk.mjs'].sha256,'534b4c0a2767aee02a7d090c4ce51d49a67f05ccde18424d2a2944df559f407d');
assert.equal(candidate.files['core.mjs'].sha256,metadata.candidate.actualMainCoreSha256);
assert.equal(candidate.files['capture-core.mjs'].sha256,metadata.candidate.actualCaptureCoreSha256);
assert.equal(candidate.toolchain.compiler,'v0.10.16+b1a0e846e');
assert.equal(baseline.buildManifest.value.toolchain.compiler,candidate.toolchain.compiler);
for(const subject of[baseline,candidate]){checkSubject(subject);checkSources(subject);const sdk=await import(pathToFileURL(subject.entry));assert.equal(sdk.version(),subject.version);for(const method of['analyze','analyzeWithOptions'])assert.equal(typeof sdk[method],'function');}
assert.equal(inputs.scenarios.length,8);
for(const entry of inputs.scenarios){const bytes=readFileSync(resolve(ROOT,entry.path));assert.equal(sha(bytes),entry.sha256);const fixture=JSON.parse(bytes);assert.equal(sha(JSON.stringify(fixture.history)),entry.originalHistorySha256);assert.equal(fixture.expectedEdges,entry.expectedEdges);assert.equal(fixture.method,entry.method);}
const runnerSha256=Object.fromEntries(readdirSync(resolve(ROOT,'runner')).filter(n=>n.endsWith('.mjs')).sort().map(n=>['runner/'+n,fileSHA(resolve(ROOT,'runner',n))]));
const protocol={format:'full-sdk-gha-linux-node24.13-heap768-protocol/v1',status:'frozen-plan-before-Linux-preflight',formalMeasurementExecuted:false,
 hostScope:'GitHub-hosted Ubuntu job; same-job paired versions on recorded CPU/Node, no dedicated physical-host guarantee',
 scope:'Complete shared analyze/analyzeWithOptions SDK calls; not renderer speed or a claim about every SDK method',
 previousWindowsAttempt:{protocolSha256:'416befcb5159c5a45ed0d8be93082101c5d2efa29122c101adf31035978c36ee',failureSha256:'3591c128c8fc132fa9ac768900e9a09b130f92488fcd1e463427a1982ae57eed',completedWorkers:1,measuredSamples:30,oldDiskThresholdMiB:512,samplesIncludedHere:false,functionalPreflightInherited:false},
 heapPolicy:{id:'same-job-both-versions-node24.13-old-space768MiB/v1',execArgv:['--max-old-space-size=768'],NODE_OPTIONS:'',defaultHeapProtocol:false,explicitGC:false,sameFlagsForBothSubjects:true,oldSpaceDoesNotCapTotalRSS:true},
 fixedSamples:{coldCalls:1,warmup:5,measuredSamples:30,batches:3,independentProcessesPerEngineScenarioBatch:1,expectedWorkers:48},
 order:[['baseline','candidate'],['candidate','baseline'],['baseline','candidate']],
 outputPolicy:{timedReturn:'complete unfiltered SDK Report object',capturedRawEncoding:'JSON.stringify exact returned object outside SDK timing',normalization:'unchanged original normalizer at root report.version only for actual reports',negativeControls:6,allReportsArchivedPerEngineScenario:1,preflightArchivesReusedWithoutFormalDuplication:true,gzipAndHashOutsideTimedCalls:true},
 budgetsAndApplicability:{legacyUsesSDK:'analyze(historyObject)',balancedUsesSDK:'analyzeWithOptions(historyObject,{})',defaultPolicy:'Original run_options_json uses options_input(text,"{}"); legacy uses no options',sameHistoryObjectsAndNoSummary:true,complete49770EdgesRequired:true,twoErrorsNeverCountAsSpeedup:true,compilerVersionExactlyMatchesPublishedBaseline:true},
 metricDefinitions:{median:'arithmetic midpoint for even count',p95:'nearest rank ceil(0.95*n)',RSS:'OS maxRSS captured after SDK calls before output validation/hash/gzip',cold:'new-process import, first full call and audited parent-spawn wall separately',filesystemCacheNotFlushed:true,integrityReadsPrimeModuleFiles:true,samples:'90 raw timings and all three30-sample batch summaries per version/scenario',controls:'median and P95 <= baseline + max(10% baseline,2ms)'},
 goals:{targetCompleteSDKGeometricMeanSpeedup:1.3,targetPeakRssGeometricMeanRatio:.8,goalsDoNotAuthorizeRetries:true,oldWindowsOrCoreTransportNumbersNotUsed:true},
 resourcePolicy:{preparationTotalBytes:64*1024*1024,minimumFreeWorkspaceBytes:2*1024*1024*1024,minimumPhysicalMemoryBytes:1024*1024*1024,formalPairedJobRequired:true,forbidConcurrentSameJob:['build','SQL','download/extraction','packaging'],noAutomaticRetry:true},
 subjects:{baseline,candidate},environmentAtPreparation:environment(),normalizer:{path:'runner/report-transport-normalization.mjs',sha256:fileSHA(resolve(ROOT,'runner/report-transport-normalization.mjs'))},
 scenarios:inputs.scenarios,runnerSha256,sourceOrSDKOrAlgorithmChangeRequiresNewProtocolAndMeasurement:true,
 currentRuntimeUsesActualLinuxBuildHashes:true,windowsC7BytecodeAssumed:false,allPreparationCommandsCompletedBeforeTiming:true};
writeFileSync(resolve(ROOT,'protocol.json'),JSON.stringify(protocol,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({protocolSha256:fileSHA(resolve(ROOT,'protocol.json')),baselineCore:baseline.files['core.mjs'].sha256,candidateCore:candidate.files['core.mjs'].sha256,candidateSDK:candidate.files['sdk.mjs'].sha256,node:process.version,formalMeasurementExecuted:false}));
