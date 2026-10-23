import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';

const clone = value => JSON.parse(JSON.stringify(value));
function trace(model, initial) {
  return {traceSchema:3,...(model?{dataModel:model}:{}),clockDomain:'frozen-v020-benchmark',scope:{exclusiveWriters:true},gaps:[],events:[{seq:1,time:0,kind:'snapshot',consistent:true,initial}]};
}
function emit(t, event) {t.events.push({...event,seq:t.events.length+1,time:t.events.length});}
function begin(t, id) {emit(t,{kind:'begin',tx:id,connection:'connection-'+id});}
function commit(t, id) {emit(t,{kind:'commit_request',tx:id});emit(t,{kind:'commit_ok',tx:id});}
function register(n, pairs, escaped=false) {
  const key=i=>escaped?'key\"\\汉字/'+i:'key/'+i;
  const label=escaped?'0.2.0/\"\\版本/':'v/';
  const versions=Object.fromEntries(Array.from({length:16},(_,i)=>[key(i),'initial/'+i]));
  const t=trace(null,{...versions});
  for(let j=0;j<n;j++) {
    const tx='register-'+j;begin(t,tx);
    for(let i=0;i<pairs;i++) {
      const k=key(i%16), prior=versions[k], next=label+j+'/'+i;
      emit(t,{kind:'read',tx,key:k,version:prior});
      emit(t,{kind:'write',tx,key:k,version:next,predecessor:prior});
      versions[k]=next;
    }
    commit(t,tx);
  }
  return t;
}
function listChain() {
  const value='0.2.0 / repeated business value / 汉字 '.repeat(2);
  const current=Array.from({length:4},(_,i)=>({id:'seed/'+i,value}));
  const t=trace('append-list-v1',{x:clone(current)});
  for(let j=0;j<6;j++) {
    const tx='list-'+j;begin(t,tx);
    for(let i=0;i<8;i++) {
      emit(t,{kind:'list_read',tx,key:'x',items:clone(current)});
      const item={id:'item/'+j+'/'+i,value};
      emit(t,{kind:'append',tx,key:'x',...item});current.push(item);
    }
    commit(t,tx);
  }
  return t;
}
function relationChain() {
  let row={key:'0',version:'r0',values:{n:'0',b:true,t:'0.2.0 / relation '.repeat(4)}};
  const t=trace('relation-set-v1',{r:[clone(row)]});
  t.relationSchema={r:{primaryKey:'id',columns:{id:'int64',n:'int64',b:'bool',t:'text'}}};
  t.scope.completeSnapshotTables=['r'];
  for(let j=0;j<6;j++) {
    const tx='relation-'+j;begin(t,tx);
    for(let i=0;i<8;i++) {
      emit(t,{kind:'row_read',tx,relation:'r',predicate:[],rows:[clone(row)],complete:true});
      const next={...row,version:'row/'+j+'/'+i,values:{...row.values,n:String(j*8+i+1)}};
      emit(t,{kind:'row_write',tx,relation:'r',key:'0',action:'update',version:next.version,predecessor:row.version,values:next.values});row=next;
    }
    commit(t,tx);
  }
  return t;
}

// Deterministic supported inputs. Expectations are frozen by the public20 engine,
// not inferred from the candidate. Inputs remain within existing exact limits.
export function performanceFixturesV020(root) {
  const from=name=>JSON.parse(readFileSync(resolve(root,name),'utf8'));
  const targets=[
    ['register-chain',register(12,16), 'consistent'],
    ['register-wide',register(6,24), 'consistent'],
    ['register-escaped',register(6,24,true), 'consistent'],
    ['list-chain',listChain(), 'consistent'],
    ['list-noisy-cycle',from('examples/list-cycle.json'), 'violation'],
    ['relation-chain',relationChain(), 'consistent'],
    ['relation-source-cycle',from('examples/relation-source-closure.json'), 'violation'],
    ['register-savepoint',from('examples/v3-savepoint.json'), 'consistent'],
    ['register-missing-source',from('fixtures/v3/missing-read-version-never-inferred.json'), 'inconclusive'],
  ];
  const cases=[];
  for(const [name,input,status] of targets) {
    cases.push({name,phase:'normalize',input,expectedStatus:status==='inconclusive'?'inconclusive':'ready',group:'normalization'});
    cases.push({name,phase:'analyze',input,expectedStatus:status,group:'full-v3'});
  }
  for(const [name,path] of [['register-noisy-cycle','fixtures/v3/reduction-source-closure.json'],['list-noisy-cycle','examples/list-cycle.json'],['relation-source-cycle','examples/relation-source-closure.json']])
    cases.push({name,phase:'reduce',input:from(path),expectedStatus:'reduced',group:'reduction-v3'});
  const bytes=readFileSync(resolve(root,'verification/fixtures/v010-comparison/manifest.json'));
  const hash=value=>createHash('sha256').update(value).digest('hex');
  assert.equal(hash(bytes),'208a86d4f19224b7bdea753e6380b677b52155bab557f734b2021f525f9056a6','Frozen control manifest changed');
  const controls=JSON.parse(bytes).cases;
  assert.equal(controls.length,20);assert.equal(new Set(controls.map(x=>x.name)).size,20);
  for(const control of controls) {
    const raw=readFileSync(resolve(root,control.file));
    assert.equal(hash(raw),control.fixtureSha256,'Control fixture changed: '+control.name);
    const frozen=JSON.parse(raw);
    assert.equal(hash(JSON.stringify(frozen.history)),control.historySha256,'Control history changed: '+control.name);
    assert.equal(Buffer.byteLength(JSON.stringify(frozen.history)),control.inputBytes);
    cases.push({name:'legacy-'+frozen.name,phase:frozen.operation==='shrink'?'legacy-reduce':'legacy',input:frozen.history,expectedStatus:frozen.status,group:'control'});
  }
  return cases;
}
