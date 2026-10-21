// Functional original-byte/tamper harness. No database or benchmark is launched.
import {readFileSync, writeFileSync, existsSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const here=dirname(fileURLToPath(import.meta.url));
const modulePath=resolve(process.argv[2]??'dist/capture-core.mjs');
const fixtureRoot=resolve(process.argv[3]??resolve(here,'fixtures'));
const receiptPath=resolve(process.argv[4]??resolve(here,'source2-functional-first.json'));
if(existsSync(receiptPath))throw Error('Refusing to replace an existing first receipt');
const sha=x=>createHash('sha256').update(x).digest('hex');
const bindings={
  'diagnostic-trace.json':'3ee5a826c5d80cc6b753b35456c0921c62b867312fb56e43aae233f311c9f97a',
  'source-observations.jsonl':'88cbaaee15e5e0faf403b2a91ce4ace53d4e2ddf656a06b1f15cf979fbf7a3ec',
};
const original={};
for(const [name,digest]of Object.entries(bindings)){
  const bytes=readFileSync(resolve(fixtureRoot,name));
  if(sha(bytes)!==digest)throw Error('Original fixture bytes changed: '+name);
  original[name]=bytes.toString('utf8');
}
const core=await import(pathToFileURL(modulePath).href);
if(typeof core.orm_sql_source2_v3_proof_json!=='function')throw Error('Missing separate experimental export');
const source=original['source-observations.jsonl'];
const trace=JSON.parse(original['diagnostic-trace.json']);
const records=source.trimEnd().split('\n').map(JSON.parse);
const installation=records.find(x=>x.kind==='installation');
const terminal=records.find(x=>x.kind==='final-effect-ledger');
const clone=x=>structuredClone(x);
const envelope=(t,s,schema=2)=>({schema,profile:'fastapi-users-sqlalchemy-7.0.0-pg18/1',traceText:typeof t==='string'?t:JSON.stringify(t),sourceJournalText:s});
function reseal(rows){
  const body=rows.filter(x=>x.kind!=='seal');
  const prefix=body.map(x=>JSON.stringify(x)+'\n').join('');
  return prefix+JSON.stringify({sourceSeq:body.length+1,kind:'seal',sourceRecords:body.length,prefixSha256:sha(prefix)})+'\n';
}
const raw=x=>({captureType:'bytes',base64:Buffer.from(x).toString('base64')});
const control=(a,seq)=>a.find(x=>x.kind==='control-query'&&x.sourceSeq===seq);
const inst=a=>a.find(x=>x.kind==='installation');
const end=a=>a.find(x=>x.kind==='final-effect-ledger');
const firstSelect=a=>a.find(x=>x.kind==='control-query'&&x.result?.actualPGresult.fields.length);
const firstBatch=a=>a.find(x=>x.kind==='source-batch');
const setCell=(q,r,c,native,wire)=>{q.result.rows[r][c]=native;q.result.actualPGresult.rawRows[r][c]=wire===null?null:raw(wire);};
const tests=[];
const add=(name,change)=>tests.push({name,change});
add('native-vs-wire',a=>{firstSelect(a).result.rows[0][0]++;});
add('description-vs-pg-oid',a=>{firstSelect(a).result.columns[0].typeCode=16;});
add('unsupported-binary-format',a=>{firstSelect(a).result.actualPGresult.fields[0].format=1;});
add('unsupported-catalog-typmod',a=>{firstSelect(a).result.actualPGresult.fields[0].typmod=1;});
add('raw-tuple-count',a=>{firstSelect(a).result.actualPGresult.ntuples++;});
add('raw-field-count',a=>{firstSelect(a).result.actualPGresult.nfields++;});
add('native-rowcount',a=>{firstSelect(a).result.rowcount++;});
add('command-tuples',a=>{firstSelect(a).result.actualPGresult.commandTuples++;});
add('raw-command-tag',a=>{firstSelect(a).result.actualPGresult.commandTag=raw('SELECT 999');});
add('raw-status',a=>{firstSelect(a).result.actualPGresult.status=1;});
add('incomplete-control-result',a=>{firstSelect(a).result.complete=false;});
add('invalid-control-UTF8',a=>{firstSelect(a).result.actualPGresult.rawRows[0][0]={captureType:'bytes',base64:'/w=='};});
add('noncanonical-base64',a=>{firstSelect(a).result.actualPGresult.rawRows[0][0].base64+='\n';});
add('exact-control-SQL',a=>{firstSelect(a).sql+='; SELECT 1';});
add('exact-control-parameters',a=>{firstSelect(a).parameters[0]='other-schema';});
add('same-physical-connection',a=>{control(a,3).connection+='other';});
add('same-backend-PID',a=>{control(a,3).backendPid++;});
add('same-client-transaction',a=>{control(a,3).transaction+='other';});
add('BEGIN-ACK-status',a=>{control(a,2).transactionStatusAfter='IDLE';});
add('first-lock-required',a=>{control(a,3).sql=control(a,3).sql.replace('ACCESS EXCLUSIVE','ACCESS SHARE');});
add('all-owned-lock-required',a=>{const s=inst(a).metadata.initializationWindow[1].querySeqs[1];control(a,s).sql=control(a,3).sql;});
add('initial-COMMIT-not-request',a=>{const q=control(a,inst(a).metadata.initializationWindow.at(-1).querySeq);q.result.commandTag='ROLLBACK';q.result.actualPGresult.commandTag=raw('ROLLBACK');});
add('initial-COMMIT-status',a=>{control(a,inst(a).metadata.initializationWindow.at(-1).querySeq).transactionStatusAfter='INTRANS';});
add('initial-window-false-reference',a=>{inst(a).metadata.initializationWindow[1].querySeqs[0]++;});
add('initial-catalog-false-reference',a=>{inst(a).metadata.catalogQueryRefs.relation++;});
add('pre-migration-sideeffect-native-and-wire',a=>{setCell(control(a,10),0,0,1,'1');});
add('pre-migration-default',a=>{setCell(control(a,6),0,5,true,'t');});
for(const seq of [13,14,15,17,18,19,20,25,27,29,31,33,35])add('exact-DDL-'+seq,a=>{control(a,seq).sql+=' /* different DDL */';});
add('initial-null-state-presence',a=>{control(a,22).parameters[2]=true;});
add('initial-null-state-image',a=>{control(a,23).parameters[3]={captureType:'psycopg-jsonb',objectDumps:'stdlib-json-dumps',value:{}};});
add('explicit-Jsonb-dumps',a=>{control(a,24).parameters[3].objectDumps='driver-default';});
add('explicit-Jsonb-value',a=>{control(a,24).parameters[3].value.email='invented@example.invalid';});
add('explicit-Jsonb-type',a=>{control(a,24).parameters[3].captureType='other';});
add('initial-state-parameter-token',a=>{control(a,22).parameters[1]='00000000-0000-4000-8000-ffffffffffff';});
add('initial-raw-marker',a=>{const m=inst(a).metadata;setCell(control(a,m.initialMarkerQuerySeq),0,0,'00000000-0000-4000-8000-ffffffffffff','00000000-0000-4000-8000-ffffffffffff');});
add('initial-snapshot-reference',a=>{inst(a).metadata.initialSnapshotQuerySeq++;});
add('initial-six-null-payload-not-SQL-null',a=>{
  const m=inst(a).metadata,q=control(a,m.initialSnapshotQuerySeq),r=q.result.rows.findIndex(x=>x[2]===false);
  setCell(q,r,6,null,'null');m.initialSnapshotRows[r][6]=null;m.initializationWindow[3].rows[r][6]=null;
});
add('final-raw-marker',a=>{const f=end(a);setCell(control(a,f.finalMarkerQuerySeq),0,1,1,'1');});
add('final-catalog-leaf-reference',a=>{end(a).finalCatalogQueryRefs.relation++;});
add('final-function-source-selfreported-hash',a=>{const f=end(a).finalFunctions.before;f.source+='\n';f.sourceSha256=sha(f.source);});
add('final-function-query-reference',a=>{end(a).finalFunctions.before.functionQuerySeq++;});
add('final-owned-unsafe-count',a=>{const f=end(a),seq=f.finalOwnedCatalogQueryRefs.state.unsafeEffects;setCell(control(a,seq),0,0,1,'1');f.finalOwnedCatalog.state.unsafeEffects[0]=1;});
add('final-owned-trigger-set',a=>{end(a).finalOwnedCatalog.state.userTriggers=[[99999]];});
add('final-COMMIT-status',a=>{control(a,end(a).finalizationWindow.at(-1).querySeq).transactionStatusAfter='INTRANS';});
add('final-ledger-query-reference',a=>{end(a).ledgerQuerySeq++;});
add('final-snapshot-query-reference',a=>{end(a).finalSnapshotQuerySeq++;});
add('final-ledger-omission',a=>{end(a).ledger.pop();});
add('final-ledger-old-image',a=>{end(a).ledger.find(x=>x.oldImage).oldImage.email='invented@example.invalid';});
add('final-state-token',a=>{end(a).state[installation.knownIds[0]].version='00000000-0000-4000-8000-ffffffffffff';});
add('business-original-SQL',a=>{firstBatch(a).originalSql+=' /* not the registry */';});
add('business-executed-SQL',a=>{firstBatch(a).executedSql+=' /* not the registry */';});
add('business-row-event-reference',a=>{firstBatch(a).businessRowsEvent++;});
add('business-statement-reference',a=>{firstBatch(a).statement++;});
add('checked-true-cannot-repair-raw-error',a=>{inst(a).metadata.checked=true;firstSelect(a).result.actualPGresult.fields[0].format=1;});
add('record-node-budget',a=>{inst(a).untrustedArray=Array(4097).fill(0);});
add('record-byte-budget',a=>{inst(a).untrustedText='x'.repeat(131073);});

const checks=[],errors=[];
function call(name,t,s,expected){
  try{
    const result=JSON.parse(core.orm_sql_source2_v3_proof_json(JSON.stringify(envelope(t,s))));
    const safe=result.history===null&&result.analysisCoverageAccepted===false&&result.verifiedProfiles?.length===0;
    const passed=safe&&(expected==='baseline'?result.controlProfileComplete===true&&result.provenStatements.length===21&&result.provenFacts.length===21&&result.verifiedControlQueries.length===121&&result.ledger.observedEffects===8&&result.ledger.committedUnrevertedEffects===7&&result.initializationEvidence.explicitJsonbParameters===1&&result.gaps.some(x=>x.code==='orm_source_gap'):result.controlProfileComplete===false&&result.provenStatements.length===0&&result.provenFacts.length===0);
    checks.push({name,expected,passed,result});if(!passed)errors.push(name);
  }catch(error){checks.push({name,expected,passed:false,error:String(error)});errors.push(name);}
}
call('original-raw-baseline',original['diagnostic-trace.json'],source,'baseline');
for(const test of tests){
  try{const rows=clone(records);test.change(rows);call(test.name,trace,reseal(rows),'rejected');}
  catch(error){checks.push({name:test.name,expected:'rejected',passed:false,harnessError:String(error)});errors.push(test.name);}
}
for(const [name,change]of [['snapshot-inconsistent',x=>{x.events[0].consistent=false;}],['open-writer-scope',x=>{x.scope.exclusiveWriters=false;}]]){
  const value=clone(trace);change(value);call(name,value,source,'rejected');
}
const wrongHeader=clone(records);wrongHeader[0].sourceSchema='orm-source-draft/1';call('old-header-not-source2',trace,reseal(wrongHeader),'rejected');
call('missing-terminal-seal',trace,source.split('\n').slice(0,-2).join('\n')+'\n','rejected');
const duplicate=source.replace('"sourceSeq":1','"sourceSeq":1,"sourceSeq":1');call('duplicate-original-JSON-key',trace,duplicate,'rejected');
const result={schema:1,kind:'experimental-sourceSchema2-functional',passed:errors.length===0,
  localModelTestsOnly:true,actualDatabaseExecution:false,formalPerformanceMeasurement:false,
  productionModelCoverageAccepted:false,legacySource1Replaced:false,
  module:{path:'<temporary-build>/capture-core.mjs',sha256:sha(readFileSync(modulePath))},
  originalBindings:bindings,checks,errors};
writeFileSync(receiptPath,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({passed:result.passed,checks:checks.length,errors,receiptSha256:sha(readFileSync(receiptPath))}));
if(errors.length)process.exitCode=1;
