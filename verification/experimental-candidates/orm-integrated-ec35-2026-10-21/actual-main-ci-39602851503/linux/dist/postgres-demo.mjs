import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,copyFileSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {analyzeWithOptions,shrinkWithOptions,replayReport,compareModels,version} from './sdk.mjs';
import {makeCapsule,replayCapsule} from './evidence.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const args=process.argv.slice(2);let connectionFile=process.env.MTW_PG_CONNECTION_FILE,record=false;
for(let i=0;i<args.length;i++){
  if(args[i]==='--connection-file'){assert.ok(args[i+1]);connectionFile=args[++i];}
  else if(args[i]==='--record-verification')record=true;
  else throw Error('Usage: postgres-demo [--connection-file PATH]');
}
const python=process.env.MTW_PYTHON || (process.platform==='win32'?'python':'python3');
const work=mkdtempSync(resolve(process.cwd(),'moontxnwitness-postgres-'));
const captured=resolve(work,'capture');
const argv=[resolve(root,'examples/capture_postgres.py'),'--rounds','20','--output',captured];
if(connectionFile)argv.push('--connection-file',resolve(connectionFile));
const receipt={tool:'MoonTxnWitness',version:version(),passed:false,actualDatabaseExecution:false,roundsPerScenario:20};
const save=(name,data)=>writeFileSync(resolve(work,name),JSON.stringify(data,null,2)+'\n');
try{
  const result=spawnSync(python,argv,{cwd:process.cwd(),encoding:'utf8',timeout:240000,maxBuffer:4*1024*1024,windowsHide:true});
  if(result.error?.code==='ENOENT'){
    Object.assign(receipt,{status:'not-executed',reason:'Optional Python runtime is missing'});process.exitCode=3;
  }else if(result.error)throw result.error;
  else if(result.status===3){Object.assign(receipt,JSON.parse(result.stdout));process.exitCode=3;}
  else{
    assert.equal(result.status,0,'Actual PostgreSQL capture failed; inspect capture/capture-failure.json');
    const metadata=JSON.parse(readFileSync(resolve(captured,'capture.json'),'utf8'));
    receipt.actualDatabaseExecution=metadata.actualDatabaseExecution;
    assert.equal(metadata.actualDatabaseExecution,true);assert.equal(metadata.passed,true);
    assert.equal(metadata.cases.length,2);assert.ok(metadata.cases.every(c=>c.rounds===20&&c.results.length===20));
    const rr=readFileSync(resolve(captured,'rr-history.json'),'utf8');
    const serial=readFileSync(resolve(captured,'serial-history.json'),'utf8');
    const anomaly=analyzeWithOptions(rr),fixed=analyzeWithOptions(serial);
    assert.equal(anomaly.status,'violation');assert.equal(anomaly.witness.edges.length,2);
    assert.equal(fixed.status,'consistent');assert.equal(fixed.complete,true);
    assert.equal(compareModels(rr).classification,'data-order-violation');
    assert.equal(compareModels(serial).classification,'compatible-with-both');
    const reduction=shrinkWithOptions(rr);
    assert.equal(reduction.oneMinimal,true);assert.equal(reduction.reducedHistory.transactions.length,2);
    assert.equal(replayReport(reduction.reducedHistory,reduction.report).valid,true);
    for(const [name,history,report]of [['rr',rr,anomaly],['serial',serial,fixed],['mini',JSON.stringify(reduction.reducedHistory),reduction.report]]){
      assert.equal(replayReport(history,report).valid,true);
      const capsule=makeCapsule(history,report);assert.equal(replayCapsule(capsule).valid,true);
      writeFileSync(resolve(work,name+'.capsule.json'),capsule);save(name+'-report.json',report);
    }
    for(const name of readdirSync(captured))copyFileSync(resolve(captured,name),resolve(work,name));
    save('reduction.json',reduction);save('mini-history.json',reduction.reducedHistory);
    const files={};
    for(const name of readdirSync(work).filter(n=>n!=='capture'))files[name]=createHash('sha256').update(readFileSync(resolve(work,name))).digest('hex');
    Object.assign(receipt,{status:'passed',passed:true,actualDatabaseExecution:true,server:metadata.server,driver:metadata.driver,cases:metadata.cases,observedTransactions:JSON.parse(rr).transactions.length+JSON.parse(serial).transactions.length,anomaly:'controlled RR write skew',fixed:'Serializable with server-reported 40001 and fresh retry',minimalTransactions:2,oneMinimal:true,v2CapsulesReplayed:3,files,scope:metadata.claim});
  }
}catch(error){Object.assign(receipt,{status:'failed',failure:error.name});process.exitCode=1;}
finally{
  save('receipt.json',receipt);
  if(record){
    const target=resolve(root,'verification/releases',version(),'postgres');mkdirSync(target,{recursive:true});
    // Every invocation keeps its receipt, including failed or unexecuted attempts.
    const stamp=new Date().toISOString().replace(/[:.]/g,'-');
    writeFileSync(resolve(target,'attempt-'+stamp+'.json'),JSON.stringify(receipt,null,2)+'\n');
    if(receipt.passed)for(const name of readdirSync(work).filter(n=>n!=='capture'))copyFileSync(resolve(work,name),resolve(target,name));
    writeFileSync(resolve(root,'verification/postgres.json'),JSON.stringify(receipt,null,2)+'\n');
  }
  const {cases,files,...summary}=receipt;
  console.log(JSON.stringify({...summary,cases:cases?.map(({results,...c})=>c),evidenceFiles:files?Object.keys(files).length:0,outputDirectory:work},null,2));
}
