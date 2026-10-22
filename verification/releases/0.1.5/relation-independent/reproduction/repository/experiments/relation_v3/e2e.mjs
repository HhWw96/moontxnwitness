// Offline source binding/oracle/model checks; does not execute a database.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as sdk from '../../dist/sdk.mjs';
import {sourceFingerprint} from '../../scripts/build-fingerprint.mjs';
const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../..');
assert.equal(process.argv.length,4,'Usage: node e2e.mjs RETAINED_DATABASE_OUTPUT NEW_OFFLINE_OUTPUT');
const folder=resolve(process.argv[2]),output=resolve(process.argv[3]);mkdirSync(output,{recursive:false});
const sha=b=>createHash('sha256').update(b).digest('hex'),load=p=>JSON.parse(readFileSync(p,'utf8'));
const bind=p=>{const raw=readFileSync(p);return{bytes:raw.length,sha256:sha(raw)};};
const save=(p,x)=>writeFileSync(p,typeof x==='string'?x:JSON.stringify(x,null,2)+'\n',{flag:'wx'});
const database=load(resolve(folder,'database-receipt.json'));
assert.equal(database.passed,true);assert.equal(database.actualPostgresExecution,true);assert.equal(database.scenarios.length,160);
const build=load(resolve(root,'dist/build-manifest.json'));
assert.equal(sourceFingerprint(root),build.sourceSha256,'Production source/build drift');
assert.equal(bind(resolve(root,'dist/core.mjs')).sha256,build.coreSha256);
assert.equal(bind(resolve(root,'dist/capture-core.mjs')).sha256,build.captureCoreSha256);
const oracle=readFileSync(resolve(root,'scripts/relation-v3-oracle.py'));
save(resolve(output,'independent-oracle-executed.py'),oracle.toString('utf8'));
const python=process.env.MTW_PYTHON||'python';
const receipt={schema:1,passed:false,actualDatabaseExecution:false,
  sourceDatabaseExecutionReceipt:bind(resolve(folder,'database-receipt.json')),
  productionBuild:build,oracleSnapshot:bind(resolve(output,'independent-oracle-executed.py')),
  fixtureScope:'controlled fixed SQL observations and explicit relational facts; no arbitrary SQL capture or ORM coverage claim',
  preregisteredPlan:database.plan,formalPerformanceMeasurement:false,cases:[]};
const errorText=e=>String(e.message).replaceAll(root,'<workspace>').replaceAll(folder,'<retained-database-output>');
function verifyBindings(directory,trace){
  const raw=readFileSync(resolve(directory,'raw-sql.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(raw.length>0);const byId=new Map();
  for(const[r,i]of raw.map((r,i)=>[r,i])){assert.equal(Number(r.rawSeq),i+1);byId.set(i+1,r);}
  const metadata=load(resolve(directory,'installation.json'));
  const snap=byId.get(metadata.snapshotBinding.response);assert.equal(snap.kind,'response');
  assert.deepEqual(snap.rows.map(r=>({key:r[0],version:r[4],values:{balance:r[1],active:r[2],region:r[3]}})),trace.events[0].initial.accounts);
  const facts=load(resolve(directory,'actual-effects.json'));
  assert.equal(facts.actualLedgerEqualsAllCommittedUnrevertedEffects,true);
  assert.equal(facts.versionOrderInferredFromAckUuidOrTransactionIds,false);
  const bs=load(resolve(directory,'semantic-bindings.json'));
  const bound=new Set();
  const target='"'+metadata.controlledSchema+'"."accounts"';
  for(const b of bs.bindings){
    const event=trace.events.find(e=>e.seq===b.event);assert.ok(event);assert.ok(!bound.has(event.seq));bound.add(event.seq);
    const request=byId.get(b.source.request),response=byId.get(b.source.response);
    assert.equal(request.kind,'request');assert.equal(response.kind,'response');assert.equal(Number(response.request),Number(request.rawSeq));
    assert.equal(request.tx,event.tx);assert.equal(response.tx,event.tx);
    if(event.kind==='row_read'){
      const types=trace.relationSchema.accounts.columns,ops={eq:'=',lt:'<',le:'<=',gt:'>',ge:'>='};
      const clauses=event.predicate.map(p=>'"'+p.column+'"'+(types[p.column]==='text'?' COLLATE "C"':'')+ops[p.op]+'%s');
      assert.equal(request.sql,'SELECT id,balance,active,region,version FROM '+target+(clauses.length?' WHERE '+clauses.join(' AND '):''));
      assert.deepEqual(request.parameters,event.predicate.length?event.predicate.map(p=>p.value):null);
      assert.deepEqual(response.rows.map(r=>({key:r[0],version:r[4],values:{balance:r[1],active:r[2],region:r[3]}})),event.rows);assert.equal(event.complete,true);
      assert.equal(response.rows.length,Number(response.rowcount));
    }else if(event.kind==='row_write'){
      assert.equal(response.rows.length,1);const r=response.rows[0];
      assert.equal(r[0],event.key);
      if(event.action==='delete'){assert.equal(r[1],event.version);assert.equal(r[2],event.predecessor);assert.equal(event.values,null);}
      else{assert.equal(r[4],event.version);assert.equal(r[5],event.predecessor);assert.deepEqual({balance:r[1],active:r[2],region:r[3]},event.values);}
    }
  }
  for(const e of trace.events)if(['row_read','row_write'].includes(e.kind))assert.ok(bound.has(e.seq),'Unbound model fact');
  const actual=facts.effectLedger;
  const byVersion=new Map(trace.events.filter(e=>e.kind==='row_write').map(e=>[e.version,e]));
  for(const r of actual){const e=byVersion.get(r[0]);assert.ok(e);assert.equal(e.key,r[1]);assert.equal(e.predecessor,r[2]);assert.equal(e.action,r[3].toLowerCase());assert.deepEqual(e.values,r[6]);}
  assert.equal(actual.length,facts.survivingWriteEvents.length);
  const current=new Map(),scopes=new Map(),committed=new Set();
  for(const e of trace.events){
    if(e.kind==='begin'){current.set(e.tx,[]);scopes.set(e.tx,[]);}
    else if(e.kind==='row_write')current.get(e.tx).push(e);
    else if(e.kind==='savepoint')scopes.get(e.tx).push({instance:e.instance,count:current.get(e.tx).length});
    else if(e.kind==='rollback_to'){
      const stack=scopes.get(e.tx),i=stack.findIndex(s=>s.instance===e.instance);assert.ok(i>=0);
      current.set(e.tx,current.get(e.tx).slice(0,stack[i].count));scopes.set(e.tx,stack.slice(0,i+1));
    }else if(e.kind==='release'){
      const stack=scopes.get(e.tx),i=stack.findIndex(s=>s.instance===e.instance);assert.ok(i>=0);scopes.set(e.tx,stack.slice(0,i));
    }else if(e.kind==='commit_ok')committed.add(e.tx);
  }
  const effective=[...committed].flatMap(tx=>current.get(tx));
  assert.deepEqual(new Set(effective.map(e=>e.seq)),new Set(facts.survivingWriteEvents));
  assert.deepEqual(new Set(effective.map(e=>e.version)),new Set(actual.map(r=>r[0])));
  for(const[name,source]of Object.entries(facts.sources)){
    const request=byId.get(source.request),response=byId.get(source.response);
    assert.equal(request.kind,'request');assert.equal(response.kind,'response');assert.equal(Number(response.request),Number(request.rawSeq));
    if(name==='effects')assert.deepEqual(response.rows,actual);
    if(name==='state')assert.deepEqual(response.rows,facts.state);
    if(name==='final')assert.deepEqual(response.rows.map(r=>({key:r[0],version:r[4],values:{balance:r[1],active:r[2],region:r[3]}})),facts.finalRows);
  }
  const finalTokens=new Map(facts.finalRows.map(r=>[r.key,r.version]));
  assert.deepEqual(new Map(facts.state.filter(r=>r[2]).map(r=>[r[0],r[1]])),finalTokens);
  return{rawSqlRecords:raw.length,boundFacts:trace.events.filter(e=>['row_read','row_write'].includes(e.kind)).length,actualLedgerEffects:actual.length};
}
for(const c of database.scenarios){
  const item={name:c.name,round:c.round,passed:false};
  try{
    const directory=resolve(folder,c.path),destination=resolve(output,c.path);mkdirSync(destination);
    for(const b of c.artifacts)assert.deepEqual(bind(resolve(directory,b.path)),{bytes:b.bytes,sha256:b.sha256});
    const text=readFileSync(resolve(directory,'trace.json'),'utf8'),trace=JSON.parse(text);
    item.rawBindings=verifyBindings(directory,trace);
    const process=spawnSync(python,['-B',resolve(output,'independent-oracle-executed.py'),'--trace',resolve(directory,'trace.json')],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});
    assert.equal(process.error,undefined);assert.equal(process.status,0,process.stderr);
    const independent=JSON.parse(process.stdout);save(resolve(destination,'oracle.json'),independent);
    assert.equal(independent.status,c.expectedVerdict,JSON.stringify(independent));
    const normalized=sdk.normalizeCaptureV3(text),report=sdk.analyzeV3(text);
    save(resolve(destination,'normalized.json'),normalized);save(resolve(destination,'report.json'),report);
    assert.equal(report.status,c.expectedVerdict,JSON.stringify(report));
    assert.equal(sdk.verifyV3(text,report).valid,true);
    const capsule=sdk.makeCapsuleV3(text,report),replay=sdk.replayCapsuleV3(capsule);
    assert.equal(replay.valid,true);save(resolve(destination,'capsule.json'),capsule);
    save(resolve(destination,'replay.json'),replay);
    item.passed=true;item.status=report.status;item.independentOracleStatus=independent.status;
    item.artifactBindings=Object.fromEntries(['oracle.json','normalized.json','report.json','capsule.json','replay.json'].map(p=>[p,bind(resolve(destination,p))]));
  }catch(error){item.error=errorText(error);}
  receipt.cases.push(item);
}
receipt.passed=receipt.cases.length===160&&receipt.cases.every(x=>x.passed);
assert.equal(sha(readFileSync(resolve(root,'scripts/relation-v3-oracle.py'))),sha(oracle));
assert.equal(sourceFingerprint(root),build.sourceSha256);
receipt.sourceBindings={'e2e.mjs':bind(fileURLToPath(import.meta.url)),'dist/sdk.mjs':bind(resolve(root,'dist/sdk.mjs')),'dist/evidence.mjs':bind(resolve(root,'dist/evidence.mjs'))};
save(resolve(output,'model-receipt.json'),receipt);
console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.length,failed:receipt.cases.filter(x=>!x.passed).map(x=>({name:x.name,round:x.round,error:x.error?.slice(0,240)})),actualDatabaseExecution:false}));
if(!receipt.passed)process.exitCode=1;
