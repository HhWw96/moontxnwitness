// Replay recorded original-SQL payloads; this process starts no database or driver.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
const {values}=parseArgs({options:{core:{type:'string'},inputs:{type:'string'},output:{type:'string'}}});
for(const name of ['core','inputs','output'])assert(values[name],`--${name} is required`);
const core=resolve(values.core),input=resolve(values.inputs),output=resolve(values.output),sha=data=>createHash('sha256').update(data).digest('hex');
mkdirSync(dirname(output),{recursive:true});
const snapshot=resolve(dirname(output),'result-v2-core.mjs');writeFileSync(snapshot,readFileSync(core));
const api=await import(pathToFileURL(snapshot).href),fixture=JSON.parse(readFileSync(input,'utf8'));
const original=readFileSync(fixture.inputReceipt),recorded=JSON.parse(original);
assert.equal(sha(original),fixture.inputReceiptSha256);
const rows=[],reports=[];
const clone=value=>structuredClone(value);
const parse=c=>({config:JSON.parse(c.configText),execution:JSON.parse(c.executionText),native:JSON.parse(c.nativeText),deliveries:JSON.parse(c.deliveriesText)});
const run=(v,options={})=>JSON.parse(api.verify_configured_result_v2_json(JSON.stringify(v.config),JSON.stringify(v.execution),JSON.stringify(v.native),JSON.stringify(v.deliveries),JSON.stringify(options)));
const noFacts=report=>{for(const name of ['captureFactsProduced','sourceFactsProduced','sourceAuthenticated','catalogVerified','sourceWindowVerified','sourceColumnMappingVerified','modelCoverageAccepted','commitVerified','committedWriteEffectVerified','moonbitProjectionVerified'])assert.equal(report[name],false,name);};
function check(name,kind,fn){try{fn();rows.push({name,kind,passed:true});}catch(error){rows.push({name,kind,passed:false,error:error.stack});}}
for(const [index,c] of fixture.cases.entries())check(c.name,'recorded-payload-replay',()=>{
 const v=parse(c),report=run(v),actual=recorded.records[index];
 assert.equal(report.status,'matched');assert.equal(report.valid,true);assert.equal(report.completeObservationVerified,true);noFacts(report);
 for(const name of ['fields','rows','status','commandStatusBase64','clientEncodingBase64'])assert.deepEqual(v.native[name],actual.baselineNative[name]);
 assert.deepEqual(c.originalParameterObservation,actual.projection.originalParameters);
 assert.deepEqual(c.originalBusinessRows,actual.baselineBusinessRows);
 assert.deepEqual(v.native.commandTuples,{pythonType:'builtins.int',value:String(actual.baselineNative.commandTuples)});
 assert.deepEqual(report.nativeObservation,v.native);assert.deepEqual(report.deliveryObservations,v.deliveries);
 if(v.native.status===1){assert.equal(report.completeFetchVerified,false);assert.equal(report.commandObservationVerified,true);assert.equal(report.returnedKeyObserved,false);assert.deepEqual(v.deliveries,[]);}
 else{
  assert.equal(report.completeFetchVerified,true);
  const delivery=v.deliveries[0],observed=actual.baselineNative.deliveryObservation;
  assert.equal(delivery.method,observed.method);assert.equal(delivery.resultPythonType,observed.rowsContainerPythonType);
  assert.deepEqual(delivery.rows.map(row=>row.pythonType),observed.rowPythonTypes);
  assert.deepEqual(delivery.rows.map(row=>row.cells),actual.baselineBusinessRows);
  const descriptor=v.execution.candidate,projections=descriptor.operation==='select'?descriptor.projections:descriptor.returning;
  const keyReturned=projections.some(p=>p.column===v.config.table.primaryKey.name)&&v.native.rows.length===1;
  assert.equal(report.returnedKeyObserved,keyReturned);assert.equal(report.returnedKeyConsistencyVerified,keyReturned);
 }
 assert.equal(c.originalTestOutcome,'rolled-back');
 reports.push({name:c.name,report});
});
const pick=(layout,suffix)=>fixture.cases.find(c=>c.layout===layout&&c.name.endsWith(suffix));
function fault(name,c,mutate,status,options={}){check(name,'synthetic-fault-from-recorded-payload',()=>{const v=parse(c);mutate(v);const r=run(v,options);assert.equal(r.status,status);assert.equal(r.completeObservationVerified,false);assert.equal(r.valid,false);noFacts(r);});}
for(const layout of [0,1,2])fault('wrong-original-key-'+layout,pick(layout,'select-explicit'),v=>{
 const wrong=layout===0?'8':layout===1?'wrong-key':'a8098c1a-f86e-11da-bd1a-00112444be1f';
 v.native.rows[0][0]=Buffer.from(wrong,'utf8').toString('base64');v.deliveries[0].rows[0].cells[0].value=wrong;
},'mismatch');
fault('actual-uuid-object-cannot-be-str',pick(2,'select-explicit'),v=>v.deliveries[0].rows[0].cells[0].pythonType='builtins.str','unknown');
fault('empty-result-still-checks-oid',pick(2,'select-empty'),v=>v.native.fields[0].oid=25,'unknown');
fault('empty-fetchmany-zero-not-negative-read',pick(2,'select-empty'),v=>Object.assign(v.deliveries[0],{method:'fetchmany',requestedSize:0,effectiveSize:0}),'partial');
fault('no-fetch-not-negative-read',pick(2,'select-empty'),v=>v.deliveries=[],'partial');
fault('partial-fetch-not-complete',pick(0,'select-explicit'),v=>Object.assign(v.deliveries[0],{method:'fetchmany',requestedSize:0,effectiveSize:0,rows:[],exhaustedObserved:false}),'partial');
fault('missing-native',pick(2,'select-explicit'),v=>v.native=null,'unknown');
fault('missing-encoding-observation',pick(2,'select-explicit'),v=>delete v.native.clientEncodingBase64,'unknown');
fault('missing-collection-type',pick(2,'select-explicit'),v=>delete v.deliveries[0].resultPythonType,'unknown');
fault('missing-row-type',pick(2,'select-explicit'),v=>delete v.deliveries[0].rows[0].pythonType,'unknown');
fault('binary-even-on-empty',pick(2,'select-empty'),v=>v.native.fields[0].format=1,'unknown');
fault('tag-and-getter-must-agree',pick(0,'insert-no-returning'),v=>v.native.commandTuples.value='0','mismatch');
fault('command-more-than-one-not-point',pick(0,'delete-no-returning'),v=>{v.native.commandStatusBase64=Buffer.from('DELETE 2').toString('base64');v.native.commandTuples.value='2';},'unknown');
fault('success-cannot-authorize-native-failure',pick(0,'select-explicit'),v=>v.native.status=7,'unknown');
fault('candidate-source-flag-does-not-authorize',pick(0,'select-explicit'),v=>v.execution.candidate.sourceFactsProduced=true,'mismatch');
for(const options of [{maxChecks:0},{maxTotalBytes:0},{grammarOptions:{maxChecks:0}}])fault('caller-budget-'+JSON.stringify(options),pick(0,'select-explicit'),()=>{},'unknown',options);
const root=resolve(import.meta.dirname,'..'),sources=['src/configured_result_v2.mbt','src/api_configured_result_v2.mbt','src/configured_result_v2_wbtest.mbt','src/sql_projection_v2_bridge/bridge.mbt','scripts/configured-result-v2-replay-inputs.py','scripts/configured-result-v2-replay-test.mjs','docs/configured-result-v2.md'];
const originalUnchanged=sha(readFileSync(fixture.inputReceipt))===fixture.inputReceiptSha256;
const result={format:'configured-result-v2-recorded-payload-replay-validation/v1',passed:originalUnchanged&&rows.every(row=>row.passed),testsRun:rows.length,failed:rows.filter(row=>!row.passed).length,recordedPayloadCases:fixture.cases.length,syntheticFaultCases:rows.length-fixture.cases.length,inputReceipt:fixture.inputReceipt,inputReceiptSha256:fixture.inputReceiptSha256,originalReceiptUnchanged:originalUnchanged,inputPostgresVersion:fixture.inputPostgresVersion,inputRecordedActualDatabaseExecution:true,actualDatabaseExecution:false,actualDriverWrapperExecuted:false,actualLifecycleVerified:false,sourceFactsProduced:false,modelCoverageAccepted:false,commitVerified:false,publicReleasePerformed:false,fixtureDerivedFields:fixture.fixtureDerivedFields,parameterSerializationRule:fixture.parameterSerializationRule,scope:fixture.scope,coreSha256:sha(readFileSync(core)),inputsSha256:sha(readFileSync(input)),sourceSha256:Object.fromEntries(sources.map(name=>[name,sha(readFileSync(resolve(root,name)))])),results:rows,recordedPayloadReports:reports};
writeFileSync(output,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({passed:result.passed,tests:result.testsRun,failed:result.failed,recordedPayloads:result.recordedPayloadCases,syntheticFaults:result.syntheticFaultCases,output}));
if(!result.passed){for(const row of rows.filter(row=>!row.passed))console.error(row.name,row.error);process.exitCode=1;}
