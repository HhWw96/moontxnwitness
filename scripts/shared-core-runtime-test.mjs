// Actual shared/standalone primitive and SDK parity. No database or benchmark.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {parseStaticImports} from './bench/full-sdk/parse-static-imports.mjs';
const root=resolve(import.meta.dirname,'..'),sha=x=>createHash('sha256').update(x).digest('hex');
function inventory(){
 const files={},pending=['sdk.mjs'];while(pending.length){const name=pending.pop();if(files[name])continue;
  const bytes=readFileSync(resolve(root,'dist',name));files[name]={bytes:bytes.length,sha256:sha(bytes)};
  pending.push(...parseStaticImports(bytes,name).relativeDependencies.map(x=>x.target));
 }return files;
}
if(process.argv[2]==='--inventory'){
 console.log(JSON.stringify(inventory()));
}else{
 const child=spawnSync(process.execPath,['--experimental-vm-modules','--max-old-space-size=384',fileURLToPath(import.meta.url),'--inventory'],{encoding:'utf8',windowsHide:true,maxBuffer:1024*1024,env:{...process.env,NODE_OPTIONS:''}});
 assert.equal(child.status,0,child.stderr);const closure=JSON.parse(child.stdout);
 assert.equal(Object.keys(closure).length,41);assert.deepEqual(Object.keys(closure).filter(x=>x==='core.mjs'||x.endsWith('-core.mjs')).sort(),['capture-core.mjs','core.mjs']);
 const roleNames=['core.mjs','capture-core.mjs','configured-session-core.mjs','source-components-core.mjs','sql-projection-core.mjs','sql-fetch-core.mjs'];
 const beforeRoles=Object.fromEntries(roleNames.map(n=>[n,sha(readFileSync(resolve(root,'dist',n)))]));
 const manifestBytes=readFileSync(resolve(root,'dist/build-manifest.json'));
 const main=await import('../dist/core.mjs'),sdk=await import('../dist/sdk.mjs');
 const cfg=await import('../dist/configured-session-core.mjs'),source=await import('../dist/source-components-core.mjs');
 const sql=await import('../dist/sql-projection-core.mjs'),fetch=await import('../dist/sql-fetch-core.mjs');
 const {createConfiguredSessionV4}=await import('../dist/configured-session-v4.mjs');
 const {createSourceComponentsV4}=await import('../dist/source-components-v4.mjs');
 const {createSQLCandidateV1}=await import('../dist/sql-candidate-host-v1.mjs');
 const {createSQLFetchV1}=await import('../dist/sql-fetch-host-v1.mjs');
 const groups={
  'configured-session-core.mjs':['diagnose_configured_session_v4_json','verify_configured_session_diagnostic_v4_json','configured_session_options_v4_json','configured_session_bundle_v4_json'],
  'source-components-core.mjs':['verify_source_installation_v4_json','verify_source_installation_report_v4_json','verify_source_fetch_mapping_v4_json','verify_source_fetch_mapping_report_v4_json'],
  'sql-projection-core.mjs':['normalize_sql_config_v1_json','normalize_configured_sql_v1_json','verify_configured_sql_v1_json','compare_c_text_v1'],
  'sql-fetch-core.mjs':['verify_configured_fetch_v1_json'],
 };
 const references={'configured-session-core.mjs':cfg,'source-components-core.mjs':source,'sql-projection-core.mjs':sql,'sql-fetch-core.mjs':fetch};
 const primitiveCalls={},tee={};
 for(const [slot,names]of Object.entries(groups))for(const name of names){
  assert.equal(typeof main[name],'function');assert.equal(typeof references[slot][name],'function');
  tee[name]=(...args)=>{assert(args.every(x=>typeof x==='string'));const original=references[slot][name](...args),shared=main[name](...args);assert.deepEqual(shared,original,name+' raw primitive result');primitiveCalls[name]=(primitiveCalls[name]??0)+1;return original;};
 }
 const reference={...createConfiguredSessionV4(tee),...createSourceComponentsV4(tee),...createSQLCandidateV1(tee),...createSQLFetchV1(tee)};
 const results=[];function test(name,fn){try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.stack});}}
 function both(name,...args){const old=reference[name](...args),shared=sdk[name](...args);assert.deepEqual(shared,old,name+' full SDK result');return shared;}
 const dir=resolve(root,'fixtures/source-components-v4'),raw=name=>readFileSync(resolve(dir,name),'utf8');
 const exact=text=>JSON.parse(text,(_k,v,ctx)=>typeof v==='number'&&Number.isInteger(v)&&!Number.isSafeInteger(v)?JSON.rawJSON(ctx.source):v);
 const config=raw('config.json'),actual=exact(raw('actual-fetch-other-installation.json')),synthetic=exact(raw('SYNTHETIC-fetch-inputs.json'));
 const installation={config,policy:raw('policy.json'),log:raw('control.jsonl'),receipt:raw('receipt.json')};
 const input={format:'moontxnwitness-configured-session-input/v1',configText:config,lifecycleText:'',diagnosticTraceText:'null',sourceInputsText:'null'};
 const c=structuredClone(actual.cases[0]),domain={processMonotonicDomain:'SYNTHETIC-shared-core',monotonicNs:'1'};
 const records=[{kind:'header',format:'moontxnwitness-instrumentation/v1',diagnosticOnly:true,processMonotonicDomain:domain.processMonotonicDomain}];
 records.push({...domain,kind:'configured-execution',frameText:JSON.stringify(c.execution)});
 c.native.executionNoteSeq=2;records.push({...domain,kind:'configured-native-result',frameText:JSON.stringify(c.native)});
 for(const d of c.deliveries)records.push({...domain,kind:'configured-delivery',frameText:JSON.stringify({...d,nativeNoteSeq:3})});
 const prefix=records.map((r,i)=>JSON.stringify({seq:i+1,...r})+'\n').join('');
 input.lifecycleText=prefix+JSON.stringify({seq:records.length+1,kind:'seal',records:records.length,prefixSha256:sha(prefix)})+'\n';
 test('session options and original bundle shared/standalone parity',()=>{both('normalizeConfiguredSessionOptionsV4',{});both('diagnoseConfiguredSessionV4',input);});
 test('session raw report and caller-independent verify parity',()=>{const r=both('diagnoseConfiguredSessionV4',input);both('diagnoseConfiguredSessionTextV4',input);assert.equal(both('verifyConfiguredSessionV4',input,r),true);assert.equal(both('verifyConfiguredSessionV4',input,r,{maxResults:0}),false);});
 test('actual original installation and no authority promotion',()=>{const r=both('verifySourceInstallationV4',installation);assert.equal(r.valid,true);assert.equal(r.initialRows,260);assert.equal(r.sourceFactsProduced,false);assert.equal(both('verifySourceInstallationReportV4',installation,r),true);});
 test('initial source mapping and independent report verification',()=>{const c=synthetic.cases[0],i={...installation,...c};const r=both('mapInitialSourceFetchV4',i);assert.equal(r.valid,true);assert.equal(r.sourceFactsProduced,false);assert.equal(both('verifyInitialSourceFetchReportV4',i,r),true);});
 test('SQL config normalization uses unchanged constraints',()=>assert.equal(both('normalizeSQLConfigV1',config).valid,true));
 test('SQL grammar and binding use original raw parameters',()=>{const q='SELECT account_no,balance FROM ledger.accounts WHERE account_no=%(pk)s',p='{"pk":17}',r=both('normalizeSQLCandidateV1',config,q,p);assert.equal(r.valid,true);assert.equal(both('verifySQLCandidateV1',config,q,p,r.expectedCandidate).valid,true);assert.equal(both('verifySQLCandidateV1',config,q,p,r.expectedCandidate,{maxChecks:0}).valid,false);});
 test('SQL Unicode C comparator preserves primitive int results',()=>{for(const [a,b]of [['𐀀',''],['é','é'],['','月']])assert.equal(Math.sign(both('compareConfiguredCTextV1',a,b)),Math.sign(Buffer.compare(Buffer.from(a),Buffer.from(b))));});
 test('actual cross-cluster fetch remains only supplied-result consistency',()=>{assert.equal(actual.actualDriverExecution,true);assert.equal(actual.sameInstallationEpoch,false);for(const c of actual.cases){const r=both('verifyConfiguredFetchV1',config,c.execution,c.native,c.deliveries);assert.equal(r.valid,true);assert.equal(r.sourceFactsProduced,false);assert.equal(r.sourceWindowVerified,false);}});
 test('source and grammar budgets are independently retained',()=>{both('verifySourceInstallationV4',installation,{maxChecks:0});both('normalizeSQLCandidateV1',config,'SELECT account_no FROM ledger.accounts','null',{maxChecks:0});});
 test('all thirteen primitive forwarders actually executed both ways',()=>{assert.equal(Object.keys(tee).length,13);for(const name of Object.keys(tee))assert((primitiveCalls[name]??0)>0,name+' was never called');});
 const manifest=JSON.parse(manifestBytes);
 const roleHashes=Object.fromEntries(roleNames.map(n=>[n,sha(readFileSync(resolve(root,'dist',n)))]));
 test('all six genuine compiled roles match actual build manifest',()=>{assert.deepEqual(roleHashes,beforeRoles);assert.deepEqual(readFileSync(resolve(root,'dist/build-manifest.json')),manifestBytes);assert.equal(roleHashes['core.mjs'],manifest.coreSha256);assert.equal(roleHashes['capture-core.mjs'],manifest.captureCoreSha256);for(const n of Object.keys(groups))assert.equal(roleHashes[n],manifest.configuredCoreSha256[n]);});
 for(const [name,v]of Object.entries(closure))assert.equal(sha(readFileSync(resolve(root,'dist',name))),v.sha256,'Runtime changed during verification');
 const receipt={format:'shared-core-runtime-conformance/v1',passed:results.every(x=>x.passed),checks:results.length,failed:results.filter(x=>!x.passed).length,results,
  version:sdk.version(),sdkSha256:closure['sdk.mjs'].sha256,defaultSDKStaticModules:41,defaultSDKCompiledCores:['core.mjs','capture-core.mjs'],roleHashes,primitiveCalls,
  sourceFactsProduced:false,writerWindowVerified:false,actualDatabaseExecution:false,formalPerformanceMeasurement:false,runtimeBeforeAfterUnchanged:true};
 let path=process.argv[2];if(!path){mkdirSync(resolve(root,'artifacts'),{recursive:true});path=resolve(mkdtempSync(resolve(root,'artifacts/shared-core-runtime-')),'receipt.json');}
 writeFileSync(path,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({...receipt,results:undefined,receipt:path}));if(!receipt.passed)process.exitCode=1;
}
