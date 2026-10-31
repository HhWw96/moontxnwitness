// Host envelope/policy tests use a deterministic fake core, never SQL semantics.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createConfiguredSessionV4} from '../cmd/configured-session-v4.mjs';
const digest=v=>createHash('sha256').update(v).digest('hex');
const defaults={maxJournalChecks:1000000,maxResults:32,maxInstallationChecks:1000000,
 maxFetchChecksPerResult:1000000,maxReturnedRowChecksPerResult:1000000,maxSourceChecksPerResult:1000000};
const flags={sourceFactsProduced:false,writerWindowVerified:false,sourceAuthenticated:false,
 serverInstanceIdentityAuthenticated:false,isolationModelChecked:false,isolationAnalysisReady:false};
const options=raw=>{const v=JSON.parse(raw);for(const [k,n]of Object.entries(v))if(!Object.hasOwn(defaults,k)||!Number.isSafeInteger(n)||n<0)throw Error('fake-core-options');return {...defaults,...v};};
const diagnose=(...args)=>JSON.stringify({format:'moontxnwitness-configured-session-diagnostic/v4',
 ...flags,status:'diagnostic-only',inputDigest:digest(args.slice(0,4).join('\0')),options:options(args[4])});
const core={configured_session_options_v4_json:raw=>JSON.stringify({valid:true,options:options(raw)}),
 configured_session_bundle_v4_json:raw=>JSON.stringify({valid:true,input:JSON.parse(raw)}),
 diagnose_configured_session_v4_json:diagnose,
 verify_configured_session_diagnostic_v4_json:(a,b,c,d,report,expected)=>diagnose(a,b,c,d,expected)===report};
const sdk=createConfiguredSessionV4(core);
const input=JSON.stringify({format:'moontxnwitness-configured-session-input/v1',
 configText:' { "exact": 1 }\n',lifecycleText:'original\n',diagnosticTraceText:'null',sourceInputsText:'null'});
const results=[];function test(name,fn){try{fn();results.push({name,passed:true});}catch(e){results.push({name,passed:false,error:e.stack});}}
let capsule;
test('host capsule retains exact original outer and inner text',()=>{capsule=sdk.makeConfiguredSessionCapsuleV4(input);const v=JSON.parse(capsule);assert.equal(v.inputText,input);assert.equal(v.inputSha256,digest(input));assert.equal(JSON.parse(v.inputText).configText,' { "exact": 1 }\n');});
test('independent caller defaults reverify the supplied report',()=>assert.equal(sdk.replayConfiguredSessionCapsuleV4(capsule).valid,true));
test('capsule cannot select a different caller budget',()=>assert.equal(sdk.replayConfiguredSessionCapsuleV4(capsule,{maxResults:0}).valid,false));
test('extra and duplicate envelope keys are rejected',()=>{const v=JSON.parse(capsule);v.trusted=true;assert.equal(sdk.replayConfiguredSessionCapsuleV4(JSON.stringify(v)+'\n').valid,false);assert.equal(sdk.replayConfiguredSessionCapsuleV4(capsule.replace('{','{"scope":"diagnostic-only",')).valid,false);});
test('changed raw digest is rejected',()=>{const v=JSON.parse(capsule);v.inputSha256='0'.repeat(64);assert.equal(sdk.replayConfiguredSessionCapsuleV4(JSON.stringify(v)+'\n').valid,false);});
test('rehashing a changed report cannot bypass core recomputation',()=>{const v=JSON.parse(capsule),report=JSON.parse(v.reportText);report.inputDigest='0'.repeat(64);v.reportText=JSON.stringify(report);v.reportSha256=digest(v.reportText);assert.equal(sdk.replayConfiguredSessionCapsuleV4(JSON.stringify(v)+'\n').valid,false);});
test('diagnostic facade refuses a fact-authorizing core response',()=>{const bad=createConfiguredSessionV4({...core,diagnose_configured_session_v4_json:()=>JSON.stringify({format:'moontxnwitness-configured-session-diagnostic/v4',...flags,sourceFactsProduced:true})});assert.throws(()=>bad.diagnoseConfiguredSessionV4(input));});
test('malformed original Unicode is rejected before verification',()=>assert.throws(()=>sdk.diagnoseConfiguredSessionV4('\ud800')));
console.log(JSON.stringify({format:'configured-session-host-envelope-tests/v1',passed:results.every(v=>v.passed),
 checks:results.length,failed:results.filter(v=>!v.passed).length,results,fakeCore:true,
 moonbitSemanticsExecuted:false,actualDatabaseExecution:false,sourceFactsProduced:false}));
if(results.some(v=>!v.passed))process.exitCode=1;
