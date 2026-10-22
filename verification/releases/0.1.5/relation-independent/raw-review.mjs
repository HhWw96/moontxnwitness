// Independent projection of the controlled fixture's retained SQL responses.
// This module does not connect to PostgreSQL and does not infer commit order.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
const load=file=>JSON.parse(readFileSync(file,'utf8'));
const project=row=>({key:row[0],version:row[4],values:{balance:row[1],active:row[2],region:row[3]}});
export function auditRawRelation(directory,trace){
 const raw=readFileSync(resolve(directory,'raw-sql.jsonl'),'utf8').trim().split(/\r?\n/).map(JSON.parse);
 const rawById=new Map();
 for(let i=0;i<raw.length;i++){assert.equal(Number(raw[i].rawSeq),i+1);rawById.set(i+1,raw[i]);}
 const pair=source=>{const request=rawById.get(Number(source.request)),response=rawById.get(Number(source.response));
  assert.ok(request);assert.ok(response);assert.equal(request.kind,'request');assert.equal(response.kind,'response');
  assert.equal(Number(response.request),Number(request.rawSeq));assert.equal(response.tx,request.tx);
  if(source.commandTag!==undefined)assert.equal(response.commandTag,source.commandTag);
  return{request,response};};
 const installation=load(resolve(directory,'installation.json'));
 const snapshot=pair(installation.snapshotBinding);
 assert.deepEqual(snapshot.response.rows.map(project),trace.events[0].initial.accounts);
 const table='"'+installation.controlledSchema+'"."accounts"';
 const bindings=load(resolve(directory,'semantic-bindings.json'));
 assert.equal(bindings.controlledFixtureOnly,true);
 const seen=new Set();let reads=0,writes=0,commitAcks=0,rollbackAcks=0,errors=0;
 for(const binding of bindings.bindings){
  const event=trace.events.find(event=>event.seq===binding.event);assert.ok(event);assert.ok(!seen.has(event.seq));seen.add(event.seq);
  const{request,response}=pair(binding.source);assert.equal(request.tx,event.tx);
  if(event.kind==='row_read'){
   const operators={eq:'=',lt:'<',le:'<=',gt:'>',ge:'>='};
   const predicates=event.predicate.map(p=>{assert.ok(operators[p.op]);return '"'+p.column+'"'+(trace.relationSchema.accounts.columns[p.column]==='text'?' COLLATE "C"':'')+operators[p.op]+'%s';});
   assert.equal(request.sql,'SELECT id,balance,active,region,version FROM '+table+(predicates.length?' WHERE '+predicates.join(' AND '):''));
   assert.deepEqual(request.parameters,predicates.length?event.predicate.map(p=>p.value):null);
   assert.equal(event.complete,true);assert.equal(Number(response.rowcount),response.rows.length);
   assert.deepEqual(response.rows.map(project),event.rows);reads++;
  }else if(event.kind==='row_write'){
   const verb={insert:'INSERT INTO',update:'UPDATE',delete:'DELETE FROM'}[event.action];assert.ok(verb);
   assert.ok(request.sql.startsWith(verb+' '+table));assert.ok(request.sql.includes(' RETURNING '));
   assert.equal(Number(response.rowcount),1);assert.equal(response.rows.length,1);const row=response.rows[0];
   assert.equal(row[0],event.key);
   if(event.action==='delete'){assert.equal(row[1],event.version);assert.equal(row[2],event.predecessor);assert.equal(event.values,null);}
   else{assert.equal(row[4],event.version);assert.equal(row[5],event.predecessor);assert.deepEqual(project(row).values,event.values);}
   writes++;
  }else if(event.kind==='begin'){
   assert.match(request.sql,/^BEGIN ISOLATION LEVEL (REPEATABLE READ|SERIALIZABLE)$/);assert.equal(response.commandTag,'BEGIN');
  }else if(event.kind==='commit_ok'){
   assert.equal(request.sql,'COMMIT');assert.equal(response.commandTag,'COMMIT');assert.equal(response.transactionStatus,'IDLE');commitAcks++;
  }else if(event.kind==='rollback_ok'){
   assert.ok(request.sql==='ROLLBACK'||request.sql==='COMMIT');assert.equal(response.commandTag,'ROLLBACK');assert.equal(response.transactionStatus,'IDLE');rollbackAcks++;
  }else if(['savepoint','rollback_to','release'].includes(event.kind)){
   const prefix={savepoint:'SAVEPOINT ',rollback_to:'ROLLBACK TO SAVEPOINT ',release:'RELEASE SAVEPOINT '}[event.kind];
   const mark=trace.events.find(e=>e.tx===event.tx&&e.kind==='savepoint'&&e.instance===event.instance);assert.ok(mark);
   assert.equal(request.sql,prefix+'"'+mark.name+'"');
  }else throw new Error('Unreviewed bound event '+event.kind);
 }
 for(const event of trace.events){
  if(['row_read','row_write','begin','commit_ok','savepoint','rollback_to','release'].includes(event.kind))assert.ok(seen.has(event.seq),'Unbound semantic event '+event.kind);
  if(event.kind==='rollback_ok'&&!seen.has(event.seq)){
   assert.ok(event.commitResponse?.sqlstate);const requestEvent=trace.events.find(e=>e.seq===event.commitResponse.request);
   assert.equal(requestEvent.kind,'commit_request');assert.equal(requestEvent.tx,event.tx);
   const failure=raw.find(r=>r.kind==='error'&&r.tx===event.tx&&r.sqlstate===event.commitResponse.sqlstate);assert.ok(failure);
   const request=rawById.get(Number(failure.request));assert.equal(request.sql,'COMMIT');assert.equal(request.tx,event.tx);
   assert.equal(failure.hasServerResult,true);assert.equal(failure.diagnosticSqlstate,event.commitResponse.diagnosticSqlstate);
   assert.equal(failure.transactionStatus,'IDLE');assert.equal(event.commitResponse.transactionStatus,'IDLE');
  }
  if(event.kind==='commit_request')assert.ok(trace.events.some(e=>e.tx===event.tx&&e.seq>event.seq&&['commit_ok','rollback_ok','disconnect'].includes(e.kind)));
 }
 for(const row of raw){if(row.kind==='error'){assert.ok(row.sqlstate);assert.ok(['40001','40P01'].includes(row.sqlstate));assert.equal(row.diagnosticSqlstate,row.sqlstate);errors++;}}
 const effects=load(resolve(directory,'actual-effects.json'));
 assert.equal(effects.actualLedgerEqualsAllCommittedUnrevertedEffects,true);
 assert.equal(effects.versionOrderInferredFromAckUuidOrTransactionIds,false);
 const transactions=new Map(),scopes=new Map(),outcomes=new Map();
 for(const event of trace.events){
  if(event.kind==='begin'){assert.ok(!transactions.has(event.tx));transactions.set(event.tx,[]);scopes.set(event.tx,[]);}
  else if(event.kind==='row_write')transactions.get(event.tx).push(event);
  else if(event.kind==='savepoint')scopes.get(event.tx).push({instance:event.instance,size:transactions.get(event.tx).length});
  else if(event.kind==='rollback_to'||event.kind==='release'){
   const stack=scopes.get(event.tx),i=stack.findLastIndex(x=>x.instance===event.instance);assert.ok(i>=0);
   if(event.kind==='rollback_to'){transactions.set(event.tx,transactions.get(event.tx).slice(0,stack[i].size));scopes.set(event.tx,stack.slice(0,i+1));}
   else scopes.set(event.tx,stack.slice(0,i));
  }else if(event.kind==='commit_ok')outcomes.set(event.tx,'committed');
  else if(event.kind==='rollback_ok')outcomes.set(event.tx,'aborted');
 }
 const committed=[...transactions].filter(([tx])=>outcomes.get(tx)==='committed').flatMap(([,events])=>events);
 assert.deepEqual(new Set(effects.survivingWriteEvents),new Set(committed.map(event=>event.seq)));
 assert.equal(effects.effectLedger.length,committed.length);
 const written=new Map(committed.map(event=>[event.version,event]));
 for(const row of effects.effectLedger){const event=written.get(row[0]);assert.ok(event);assert.equal(event.key,row[1]);assert.equal(event.predecessor,row[2]);assert.equal(event.action,row[3].toLowerCase());assert.deepEqual(event.values,row[6]);}
 for(const [tx,outcome]of Object.entries(effects.outcomes)){
  assert.equal(outcomes.get(tx),outcome.status);
  if(!outcome.source){assert.equal(outcome.status,'aborted');assert.equal(outcome.serverResponse,true);
   assert.ok(raw.some(r=>r.kind==='error'&&r.tx===tx&&r.sqlstate===outcome.sqlstate&&r.hasServerResult===true));continue;}
  const{request,response}=pair(outcome.source);
  if(outcome.status==='committed'){assert.equal(request.sql,'COMMIT');assert.equal(response.commandTag,'COMMIT');}
  else{assert.ok(request.sql==='COMMIT'||request.sql==='ROLLBACK');assert.equal(response.commandTag,'ROLLBACK');}
 }
 for(const[name,source]of Object.entries(effects.sources)){
  const{response}=pair(source);
  if(name==='effects')assert.deepEqual(response.rows,effects.effectLedger);
  else if(name==='state')assert.deepEqual(response.rows,effects.state);
  else if(name==='final')assert.deepEqual(response.rows.map(project),effects.finalRows);
  else throw new Error('Unreviewed effect source '+name);
 }
 const final=new Map(effects.finalRows.map(row=>[row.key,row.version]));
 assert.deepEqual(new Map(effects.state.filter(row=>row[2]).map(row=>[row[0],row[1]])),final);
 return{rawRecords:raw.length,reads,writes,commitAcks,rollbackAcks,errors,
  ledgerEffects:committed.length,controlledFixtureOnly:true,commitOrderInferred:false};
}
