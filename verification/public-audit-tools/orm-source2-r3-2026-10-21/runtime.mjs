// Independent component probes. Never import the author's check-source2 harness.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const work=resolve(process.argv[2]), output=resolve(process.argv[3]);
mkdirSync(output,{recursive:false});
const bytes=p=>readFileSync(resolve(work,p));
const load=p=>JSON.parse(bytes(p));
const sha=b=>createHash('sha256').update(b).digest('hex');
const profile=load('profile.json'), contract=load('contract-v1.json');
const traceText=bytes('inputs/fixtures/diagnostic-trace.json').toString('utf8');
const sourceText=bytes('inputs/fixtures/source-observations.jsonl').toString('utf8');
for(const [name,binding]of Object.entries(profile.inputs)){
 const raw=bytes('inputs/'+name);assert.equal(raw.length,binding.bytes);assert.equal(sha(raw),binding.sha256);
}
const modulePath=resolve(work,'artifact/experimental-capture-core.mjs');
assert.equal(sha(readFileSync(modulePath)),profile.moduleSha256);
const trace=JSON.parse(traceText), records=sourceText.trimEnd().split('\n').map(JSON.parse);
const bySeq=new Map(records.map(r=>[r.sourceSeq,r]));
const events=new Map(trace.events.map(e=>[e.seq,e]));
const batches=records.filter(r=>r.kind==='source-batch');
const controls=records.filter(r=>r.kind==='control-query');
const installation=records.find(r=>r.kind==='installation');
const final=records.find(r=>r.kind==='final-effect-ledger');
assert.equal(records.length,147);assert.equal(controls.length,121);assert.equal(batches.length,21);
const plain=x=>Array.isArray(x)?x.map(plain):x&&typeof x==='object'
 ?x.captureType==='UUID'?x.value:Object.fromEntries(Object.entries(x).map(([k,v])=>[k,plain(v)])):x;
function wire(x,oid){
 if(x===null)return null;
 assert.equal(x.captureType,'bytes');const s=Buffer.from(x.base64,'base64').toString('utf8');
 if(oid===16){assert(['t','f'].includes(s));return s==='t';}
 return s;
}
const factRows=[], effectByVersion=new Map(), effectAtRows=new Map();
for(const batch of batches){
 const st=events.get(batch.statement), rowEvent=events.get(batch.businessRowsEvent), pg=batch.actualPGresult;
 assert.equal(st.kind,'statement');assert.equal(rowEvent.kind,'rows');assert.equal(rowEvent.complete,true);
 assert.equal(st.tx,batch.tx);assert.equal(rowEvent.tx,batch.tx);assert.equal(rowEvent.statement,st.seq);
 assert.equal(st.sql,batch.originalSql);assert.equal(st.executedSql,batch.executedSql);
 assert.deepEqual(st.parameters,batch.parameters);assert.equal(st.mappingId,batch.mappingId);
 assert.equal(pg.status,2);assert.equal(pg.ntuples,1);assert.equal(pg.fields.length,8);
 assert(pg.fields.every(f=>f.format===0));
 const row=pg.fields.map(f=>wire(f.raw,f.oid));
 let data;
 if(batch.operation==='get'){
  const image=row[7]?Object.fromEntries(['id','email','hashed_password','is_active','is_superuser','is_verified'].map((k,i)=>[k,row[i]])):null;
  data={key:String(batch.parameters.id_1),version:row[6],present:row[7],image};
  assert.deepEqual(plain(rowEvent.rows),row[7]?[row.slice(0,6)]:[]);
  assert.equal(batch.observation.source.version,data.version);assert.equal(batch.observation.source.present,data.present);
 }else{
  row[5]=row[5]===null?null:JSON.parse(row[5]);row[6]=row[6]===null?null:JSON.parse(row[6]);
  assert.deepEqual(batch.observation.effectRows,[row]);
  data=Object.fromEntries(['key','predecessor','version','oldPresent','newPresent','oldImage','newImage','action'].map((k,i)=>[k,row[i]]));
  assert.equal(effectByVersion.has(data.version),false);
  const e={data,tx:batch.tx,rows:rowEvent.seq,sourceSeq:batch.sourceSeq,revertedBy:null,outcome:'unknown'};
  effectByVersion.set(data.version,e);effectAtRows.set(rowEvent.seq,e);
 }
 factRows.push({kind:batch.operation==='get'?'read':'write',sourceSeq:batch.sourceSeq,
                statement:st.seq,rows:rowEvent.seq,tx:batch.tx,data});
}
// Scope replay is independent of the component implementation and its result.
const active=new Map(), marks=new Map(), outcomes=new Map();
for(const e of trace.events){
 if(e.kind==='begin'){active.set(e.tx,[]);marks.set(e.tx,[]);}
 if(effectAtRows.has(e.seq))active.get(e.tx).push(effectAtRows.get(e.seq));
 if(e.kind==='savepoint')marks.get(e.tx).push({instance:e.instance,length:active.get(e.tx).length});
 if(e.kind==='rollback_to'){
  const stack=marks.get(e.tx), i=stack.findIndex(s=>s.instance===e.instance);assert(i>=0);
  const keep=stack[i].length;for(const effect of active.get(e.tx).slice(keep))effect.revertedBy=e.seq;
  active.set(e.tx,active.get(e.tx).slice(0,keep));marks.set(e.tx,stack.slice(0,i+1));
 }
 if(e.kind==='release'){
  const stack=marks.get(e.tx),i=stack.findIndex(s=>s.instance===e.instance);assert(i>=0);marks.set(e.tx,stack.slice(0,i));
 }
 if(e.kind==='rollback_ok'){
  for(const effect of active.get(e.tx))effect.revertedBy=e.seq;active.set(e.tx,[]);outcomes.set(e.tx,'aborted');
 }
 if(e.kind==='commit_ok')outcomes.set(e.tx,'committed');
 if(e.kind==='disconnect')outcomes.set(e.tx,'unknown');
}
for(const e of effectByVersion.values())e.outcome=outcomes.get(e.tx)??'unknown';
const effects=[...effectByVersion.values()], live=effects.filter(e=>e.outcome==='committed'&&e.revertedBy===null);
assert.equal(effects.length,8);assert.equal(live.length,7);assert.equal(effects.filter(e=>e.revertedBy!==null).length,1);
const keyed=a=>new Map(a.map(e=>[e.version,e]));
assert.deepEqual(keyed(live.map(e=>e.data)),keyed(final.ledger));
// Source-derived chains, never an order invented from event/ACK position.
const state=structuredClone(installation.metadata.initialState), remaining=new Map(live.map(e=>[e.data.version,e.data]));
for(const [key,start]of Object.entries(state)){
 let current=start;
 for(;;){
  const next=[...remaining.values()].filter(e=>e.key===key&&e.predecessor===current.version);
  assert(next.length<=1);if(!next.length)break;const e=next[0];
  assert.equal(e.oldPresent,current.present);assert.deepEqual(e.oldImage,current.image);
  current={version:e.version,present:e.newPresent,image:e.newImage};remaining.delete(e.version);
 }
 state[key]=current;
}
assert.equal(remaining.size,0);assert.deepEqual(state,final.state);
const jsonb=controls.filter(q=>Array.isArray(q.parameters)&&q.parameters[3]?.captureType==='psycopg-jsonb');
assert.equal(jsonb.length,1);

const core=await import(pathToFileURL(modulePath).href);
assert.equal(typeof core.orm_sql_source2_v3_proof_json,'function');
const copy=x=>structuredClone(x);
const envelope=(t=traceText,s=sourceText)=>({schema:2,profile:'fastapi-users-sqlalchemy-7.0.0-pg18/1',traceText:t,sourceJournalText:s});
function reseal(rs,{headerBytes}={}){
 const body=rs.filter(r=>r.kind!=='seal').map(r=>JSON.stringify(r));
 if(headerBytes!==undefined){const n=headerBytes-Buffer.byteLength(body[0]);assert(n>=0);body[0]=' '.repeat(n)+body[0];}
 const prefix=body.join('\n')+'\n';
 return prefix+JSON.stringify({sourceSeq:body.length+1,kind:'seal',sourceRecords:body.length,prefixSha256:sha(prefix)})+'\n';
}
function journalMutation(fn){const rs=copy(records);fn(rs);return envelope(traceText,reseal(rs));}
function traceMutation(fn){const t=copy(trace);fn(t);return envelope(JSON.stringify(t));}
const cases=[];
const add=(name,expected,input)=>cases.push({name,expected,input});
add('original-raw-source-closure','partial-positive',()=>envelope());
add('pretty-trace-preserves-facts','partial-positive',()=>envelope(JSON.stringify(trace,null,4)+'\n'));
add('exact-trace-byte-boundary','partial-positive',()=>envelope(' '.repeat(8388608-Buffer.byteLength(traceText))+traceText));
add('exact-source-record-byte-boundary','partial-positive',()=>envelope(traceText,reseal(records,{headerBytes:131072})));
add('over-trace-byte-budget','rejected',()=>envelope(' '.repeat(8388609-Buffer.byteLength(traceText))+traceText));
add('over-source-record-byte-budget','rejected',()=>envelope(traceText,reseal(records,{headerBytes:131073})));
for(const [name,value]of [['envelope-schema1',1],['envelope-schema3',3],['envelope-schema-string','2']])add(name,'rejected',()=>({...envelope(),schema:value}));
add('unknown-profile','rejected',()=>({...envelope(),profile:'unreviewed/profile'}));
add('scope-not-exclusive','rejected',()=>traceMutation(t=>{t.scope.exclusiveWriters=false;}));
add('scope-declaration-missing','rejected',()=>traceMutation(t=>{delete t.scope.exclusiveWriters;}));
add('committing-writer-ack-unknown','rejected',()=>traceMutation(t=>{
 const tx=batches.find(b=>b.operation==='create').tx,e=t.events.find(e=>e.tx===tx&&e.kind==='commit_ok');assert(e);e.kind='disconnect';
}));
add('source-seal-digest-corrupt','rejected',()=>{const lines=sourceText.trimEnd().split('\n'),s=JSON.parse(lines.at(-1));s.prefixSha256='0'.repeat(64);lines[lines.length-1]=JSON.stringify(s);return envelope(traceText,lines.join('\n')+'\n');});
add('resealed-control-sql-whitespace','rejected',()=>journalMutation(rs=>{rs.find(r=>r.kind==='control-query').sql+=' ';}));
add('resealed-native-wire-mismatch','rejected',()=>journalMutation(rs=>{const q=rs.find(r=>r.kind==='control-query'&&r.result.rows.length);q.result.rows[0][0]++;}));
add('resealed-initial-catalog-reference','rejected',()=>journalMutation(rs=>{const m=rs.find(r=>r.kind==='installation').metadata;m.catalogQueryRefs.relation=m.catalogQueryRefs.locks;}));
add('resealed-ledger-effect-omitted','rejected',()=>journalMutation(rs=>{rs.find(r=>r.kind==='final-effect-ledger').ledger.pop();}));
add('resealed-reverted-effect-in-ledger','rejected',()=>journalMutation(rs=>{rs.find(r=>r.kind==='final-effect-ledger').ledger.push(copy(effects.find(e=>e.revertedBy!==null).data));}));
add('resealed-effect-image-raw-mismatch','rejected',()=>journalMutation(rs=>{rs.find(r=>r.kind==='source-batch'&&r.operation==='create').observation.effectRows[0][6].email='changed-without-wire@example.invalid';}));
add('unknown-envelope-field','rejected',()=>({...envelope(),checked:true}));
add('source-schema1','rejected',()=>journalMutation(rs=>{rs[0].sourceSchema=1;}));
add('business-result-not-complete','rejected',()=>traceMutation(t=>{t.events.find(e=>e.seq===batches[0].businessRowsEvent).complete=false;}));
add('empty-source-journal','rejected',()=>envelope(traceText,''));
assert.deepEqual(cases.map(c=>({name:c.name,expected:c.expected})),contract.cases);
assert.equal(cases.length,24);

function globalRefusal(r){
 assert.equal(r.schema,2);assert.equal(r.algorithm,'v3-orm-source-proof-2');
 assert.equal(r.analysisCoverageAccepted,false);assert.equal(r.history,null);
 for(const name of ['verifiedStatements','verifiedFacts','verifiedProfiles'])assert.deepEqual(r[name],[]);
 assert(r.gaps.length>0);
}
function positive(r,input){
 globalRefusal(r);assert.equal(r.controlProfileComplete,true);
 assert.equal(r.traceSha256,sha(input.traceText));assert.equal(r.sourceJournalSha256,sha(input.sourceJournalText));
 assert.deepEqual(r.verifiedControlQueries,controls.map(q=>({sourceSeq:q.sourceSeq,sqlSha256:sha(q.sql)})));
 assert.deepEqual(r.verifiedSourceBatches,factRows.map(f=>({sourceSeq:f.sourceSeq,statement:f.statement,rows:f.rows,kind:f.kind})));
 assert.deepEqual(r.candidateFacts,factRows);assert.deepEqual(r.provenFacts,factRows);
 assert.equal(r.matchedStatements.length,21);assert.deepEqual(r.provenStatements,r.matchedStatements);
 assert.deepEqual(r.observedEffects,effects);assert.deepEqual(r.ledger,{observedEffects:8,committedUnrevertedEffects:7,serverLedgerEffects:7,sourceChainsChecked:true});
 assert.equal(r.initializationEvidence.explicitJsonbParameters,jsonb.length);
 assert.equal(r.initializationEvidence.migrationDdlStatements,13);assert.equal(r.finalizationEvidence.ledgerEntries,7);
 assert(r.gaps.some(g=>g.code==='orm_source_gap'));assert(r.gaps.some(g=>g.code==='orm_diagnostic_transport_only'));
}
const results=[];
for(const [i,c]of cases.entries()){
 let input,encoded,report;
 try{
  input=c.input();encoded=JSON.stringify(input);report=JSON.parse(core.orm_sql_source2_v3_proof_json(encoded));
  writeFileSync(resolve(output,String(i+1).padStart(2,'0')+'-'+c.name+'.report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  if(c.expected==='partial-positive')positive(report,input);
  else{globalRefusal(report);assert.equal(report.controlProfileComplete,false);assert.deepEqual(report.provenStatements,[]);assert.deepEqual(report.provenFacts,[]);assert(report.gaps.some(g=>g.code==='invalid_orm_source2_proof'));}
  results.push({name:c.name,expected:c.expected,passed:true,inputBytes:Buffer.byteLength(encoded),inputSha256:sha(encoded),reportSha256:sha(JSON.stringify(report,null,2)+'\n')});
 }catch(e){
  if(encoded)writeFileSync(resolve(output,String(i+1).padStart(2,'0')+'-'+c.name+'.failed-input.json'),encoded,{flag:'wx'});
  results.push({name:c.name,expected:c.expected,passed:false,inputBytes:encoded?Buffer.byteLength(encoded):null,inputSha256:encoded?sha(encoded):null,errorClass:e.name,error:String(e.message).replaceAll(work,'<fresh>')});
 }
}
const result={schema:1,kind:'independent-orm-r3-actual-runtime-cases',passed:results.every(r=>r.passed),complete:true,
 checks:results.length,cases:results,node:process.version,platform:process.platform,actualModuleSha256:sha(readFileSync(modulePath)),
 inputBindings:profile.inputs,independentSourceClosure:{sourceRecords:147,controlQueries:121,statementBatches:21,effects:8,committedLedger:7,revertedEffects:1,jsonbParameters:1},
 authorHarnessImported:false,localCompilation:false,actualDatabaseExecution:false,formalPerformance:false,
 productionModelCoverageAccepted:false,fullApplicationAccepted:false,stableReleaseAccepted:false};
writeFileSync(resolve(output,'independent-result.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:result.passed,complete:true,checks:result.checks,failed:results.filter(r=>!r.passed).map(r=>r.name),resultSha256:sha(JSON.stringify(result,null,2)+'\n')}));
if(!result.passed)process.exitCode=1;
