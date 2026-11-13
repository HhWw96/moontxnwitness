// Frozen semantic families; expectations are chosen before either checker runs.
export const MODELS = Object.freeze(['read-uncommitted','read-committed','repeatable-read','serializable','strict-serializable','snapshot-isolation','consistent-view','strong-session-read-uncommitted','strong-read-uncommitted','strong-session-read-committed','strong-read-committed','strong-session-serializable','strong-session-snapshot-isolation','strong-snapshot-isolation']);
const b = tx => ({kind:'begin',tx,connection:'physical-'+tx});
const c = tx => [{kind:'commit_request',tx},{kind:'commit_ok',tx}];
const r = (tx,key,version) => ({kind:'read',tx,key,version});
const w = (tx,key,version,predecessor) => ({kind:'write',tx,key,version,predecessor});
const app = (tx,key,id) => ({kind:'append',tx,key,id,value:'repeated-business-value'});
const lr = (tx,key,ids) => ({kind:'list_read',tx,key,items:ids.map(id=>({id,value:'repeated-business-value'}))});
function capture(body, list=false) {
  return {traceSchema:3,dataModel:list?'append-list-v1':'point-register-v1',clockDomain:'shared-matrix-clock/v1',scope:{exclusiveWriters:true},gaps:[],
    events:[{kind:'snapshot',consistent:true,initial:list?{x:[],y:[],z:[],t:[]}:{x:'x0',y:'y0',z:'z0',t:'t0'}},...body].map((e,i)=>({...e,seq:i+1,time:i}))};
}
function clients(source, together=false) {
  const txs=source.events.filter(e=>e.kind==='begin').map(e=>e.tx);
  return together?[{id:'declared-client',transactions:txs}]:txs.map(tx=>({id:'declared-'+tx,transactions:[tx]}));
}
function families(list) {
  const read=list?(tx,key,version)=>lr(tx,key,version.endsWith('0')?[]:[version]):r;
  const write=list?(tx,key,version)=>app(tx,key,version):w;
  const good=capture([b('A'),read('A','x','x0'),write('A','x','x1','x0'),read('A','x','x1'),...c('A')],list);
  const g0=list?capture([b('A'),b('B'),app('A','x','ax'),app('A','y','ay'),app('B','x','bx'),app('B','y','by'),...c('A'),...c('B'),b('C'),lr('C','x',['ax','bx']),lr('C','y',['by','ay']),...c('C')],true):capture([b('A'),b('B'),w('A','x','x1','x0'),w('B','y','y1','y0'),w('A','y','y2','y1'),w('B','x','x2','x1'),...c('A'),...c('B')]);
  const missing=structuredClone(good);missing.events=missing.events.filter(e=>e.seq!==3);
  return {
    clean:good, 'ww-cycle':g0, 'missing-event':missing,
    'wr-cycle':capture([b('A'),b('B'),write('A','y','y1','y0'),write('B','x','x1','x0'),read('A','x','x1'),read('B','y','y1'),...c('A'),...c('B')],list),
    'future-wr-cycle':capture([b('A'),b('B'),read('A','x','x1'),read('B','y','y1'),write('A','y','y1','y0'),write('B','x','x1','x0'),...c('A'),...c('B')],list),
    'write-skew':capture([b('A'),b('B'),read('A','x','x0'),read('B','y','y0'),write('A','y','y1','y0'),write('B','x','x1','x0'),...c('A'),...c('B')],list),
    'single-anti':capture([b('A'),b('B'),write('A','x','x1','x0'),write('A','y','y1','y0'),read('B','x','x1'),read('B','y','y0'),...c('A'),...c('B')],list),
    'stale-order':capture([b('W'),write('W','x','x1','x0'),...c('W'),b('R'),read('R','x','x0'),...c('R')],list),
    'nonadjacent':capture([b('A'),b('B'),b('C'),b('D'),read('A','x','x0'),write('B','x','x1','x0'),read('C','x','x1'),read('C','y','y0'),write('D','y','y1','y0'),read('A','y','y1'),...c('A'),...c('B'),...c('C'),...c('D')],list),
    'aborted-read':capture([b('W'),write('W','x','x1','x0'),{kind:'rollback_ok',tx:'W'},b('R'),read('R','x','x1'),...c('R')],list),
    'intermediate-read':capture([b('W'),b('R'),write('W','x','x1','x0'),read('R','x','x1'),write('W','x','x2','x1'),...c('W'),...c('R')],list),
    'own-read-mismatch':capture([b('A'),write('A','x','x1','x0'),read('A','x','x0'),...c('A')],list),
  };
}
function negative(model) {
  if(model.includes('uncommitted'))return 'ww-cycle';
  if(model.includes('committed'))return 'wr-cycle';
  if(['snapshot-isolation','consistent-view'].includes(model))return 'single-anti';
  if(['strict-serializable','strong-session-serializable','strong-session-snapshot-isolation','strong-snapshot-isolation'].includes(model))return 'stale-order';
  return 'write-skew';
}
export function matrixCases() {
  const cases=[];
  for(const list of [false,true]) {
    const fs=families(list),dataModel=list?'append-list-v1':'point-register-v1';
    for(const model of MODELS) {
      for(const kind of ['clean',negative(model),'missing-event']) {
        const source=structuredClone(fs[kind]);
        cases.push({id:`${dataModel}/${model}/${kind}`,dataModel,model,family:kind,
          input:source,options:{models:[model],...(list?{listProfile:'captured-list-prefix-state/v2'}:{}),clients:clients(source,kind==='stale-order'),clientsComplete:true},
          expected:kind==='clean'?'checked-compatible':kind==='missing-event'?'unknown':'refuted',
          upstreamEligible:kind!=='missing-event',cohort:!list&&kind==='ww-cycle'?'explicit-original-order':'client-observations',required:true});
      }
    }
    // Additional families distinguish anomaly strength and order contexts.
    for(const family of ['wr-cycle','future-wr-cycle','write-skew','single-anti','stale-order','nonadjacent','aborted-read','intermediate-read','own-read-mismatch']) {
      for(const model of MODELS) {
        if(cases.some(c=>c.id===`${dataModel}/${model}/${family}`))continue;
        const source=structuredClone(fs[family]);
        cases.push({id:`${dataModel}/${model}/${family}`,dataModel,model,family,input:source,
          options:{models:[model],...(list?{listProfile:'captured-list-prefix-state/v2'}:{}),clients:clients(source,family==='stale-order'),clientsComplete:true},
          expected:null,upstreamEligible:true,cohort:'client-observations',required:false});
      }
    }
  }
  return {format:'moontxnwitness-shared-model-matrix/v1',fixedElleCommit:'4e359e597c52938b0afebb8bc42273914d68a424',models:MODELS,cases};
}
