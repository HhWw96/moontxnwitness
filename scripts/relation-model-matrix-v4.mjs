/** Frozen fourteen-model relation cases, ordering distinctions and rehashed tamper checks. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,copyFileSync,mkdirSync,existsSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';

const MODELS=Object.freeze(['read-uncommitted','read-committed','repeatable-read','serializable','strict-serializable','snapshot-isolation','consistent-view','strong-session-read-uncommitted','strong-read-uncommitted','strong-session-read-committed','strong-read-committed','strong-session-serializable','strong-session-snapshot-isolation','strong-snapshot-isolation']);
const script=fileURLToPath(import.meta.url),base=dirname(script),sha=x=>createHash('sha256').update(x).digest('hex');
const [distName,outName,...args]=process.argv.slice(2);let python=process.env.MTW_PYTHON??'python';
assert(distName&&outName,'Usage: node scripts/relation-model-matrix-v4.mjs DIST NEW_OUTPUT [--python EXECUTABLE]');
assert(args.length===0||(args.length===2&&args[0]==='--python'),'Only --python EXECUTABLE is supported');
if(args.length)python=args[1];
const out=resolve(outName),dist=resolve(distName),runtime=resolve(out,'runtime'),tools=resolve(out,'tools');
const binding=path=>{const bytes=readFileSync(path);return {bytes:bytes.length,sha256:sha(bytes)};};
const originals={};
for(const name of ['core.mjs','relation-models-v4.mjs'])originals['runtime/'+name]={path:resolve(dist,name),...binding(resolve(dist,name))};
if(existsSync(resolve(dist,'build-manifest.json')))originals['runtime/build-manifest.json']={path:resolve(dist,'build-manifest.json'),...binding(resolve(dist,'build-manifest.json'))};
for(const name of ['relation-model-matrix-v4.mjs','relation-models-corpus.py','relation-models-oracle.py'])originals['tools/'+name]={path:resolve(base,name),...binding(resolve(base,name))};
mkdirSync(out);mkdirSync(runtime);mkdirSync(tools);mkdirSync(resolve(out,'reports'));mkdirSync(resolve(out,'capsules'));
for(const [name,{path}]of Object.entries(originals))copyFileSync(path,resolve(out,name));
const sourceBindings=Object.fromEntries(Object.entries(originals).map(([name,{path,...value}])=>[name,value]));
writeFileSync(resolve(out,'source-bindings.json'),JSON.stringify(sourceBindings,null,2)+'\n',{flag:'wx'});
const failures=[],results=[],tamperRows=[],invalidResults=[];
const row=(key,version,value='0')=>({key:String(key),version,values:{value}});
const begin=tx=>({kind:'begin',tx,connection:'physical-'+tx});
const commit=tx=>[{kind:'commit_request',tx},{kind:'commit_ok',tx}];
const write=(tx,key,version,predecessor,value='0',action='update')=>({kind:'row_write',tx,relation:'entries',key:String(key),version,predecessor,values:{value},action});
const read=(tx,key,version,value='0')=>({kind:'row_read',tx,relation:'entries',complete:true,predicate:[{column:'id',op:'eq',value:String(key)}],rows:[row(key,version,value)]});
const query=(tx,rows)=>({kind:'row_read',tx,relation:'entries',complete:true,predicate:[{column:'value',op:'eq',value:'1'}],rows});
function trace(body){
  return {traceSchema:3,dataModel:'relation-set-v1',clockDomain:'relation-model-matrix-clock/v1',
    relationSchema:{entries:{primaryKey:'id',columns:{id:'int64',value:'int64'}}},
    scope:{exclusiveWriters:true,completeSnapshotTables:['entries']},gaps:[],
    events:[{kind:'snapshot',consistent:true,initial:{entries:[row(1,'x0'),row(2,'y0'),row(3,'z0')]}},...body].map((event,i)=>({...event,seq:i+1,time:i}))};
}
function clients(source,together=[]){
  const txs=source.events.filter(e=>e.kind==='begin').map(e=>e.tx),grouped=new Set(together);
  return [...txs.filter(tx=>!grouped.has(tx)).map(tx=>({id:'client-'+tx,transactions:[tx]})),...(together.length?[{id:'declared-logical-client',transactions:together}]:[])];
}
const configured=(source,together=[])=>({source,options:{clients:clients(source,together),clientsComplete:true}});
function customFamilies(){
  const g0=trace([begin('A'),begin('B'),write('A',1,'a1','x0'),write('B',2,'b1','y0'),write('A',2,'a2','b1'),write('B',1,'b2','a1'),...commit('A'),...commit('B')]);
  // WW A->B, WW C->A and response-before-invocation B->C.
  // The data graph alone is acyclic and serializes C,A,B.
  const g0Order=trace([begin('A'),write('A',1,'a1','x0'),begin('B'),write('B',1,'b1','a1'),...commit('B'),begin('C'),write('C',2,'c1','y0'),...commit('C'),write('A',2,'a2','c1'),...commit('A')]);
  const g1b=trace([begin('P'),begin('R'),write('P',1,'p1','x0'),read('R',1,'p1'),write('P',1,'p2','p1'),...commit('P'),...commit('R')]);
  // WR A->B, WR C->A and real-time B->C, without a data-only cycle.
  const wrOrder=trace([begin('A'),write('A',1,'a1','x0'),begin('B'),read('B',1,'a1'),...commit('B'),begin('C'),write('C',2,'c1','y0'),...commit('C'),read('A',2,'c1'),...commit('A')]);
  const singleAnti=trace([begin('A'),begin('B'),write('A',1,'a1','x0','1'),write('A',2,'a2','y0','1'),read('B',1,'a1','1'),read('B',2,'y0'),...commit('A'),...commit('B')]);
  const predicateOnly=trace([begin('A'),begin('B'),query('A',[]),query('B',[]),write('A',4,'a4',null,'1','insert'),write('B',5,'b5',null,'1','insert'),...commit('A'),...commit('B')]);
  const mixed=trace([begin('A'),begin('B'),begin('C'),write('C',3,'c3','z0'),read('A',1,'x0'),query('B',[]),write('B',1,'b1','x0'),write('C',4,'c4',null,'1','insert'),read('A',3,'c3'),...commit('A'),...commit('B'),...commit('C')]);
  return {g0,g0Order,g1b,wrOrder,singleAnti,predicateOnly,mixed};
}
function casesFrom(reference){
  const custom=customFamilies(),positive={source:reference[0].source,options:reference[0].options};
  const skew={source:reference[2].source,options:reference[2].options};
  const stale={source:reference[3].source,options:reference[3].options};
  const aborted={source:reference[4].source,options:reference[4].options};
  const negatives={
    'read-uncommitted':{...configured(custom.g0),family:'G0-original-final-effects'},
    'read-committed':{...aborted,family:'G1a-original-aborted-source'},
    'repeatable-read':{...skew,family:'G2-item-write-skew'},
    'serializable':{...skew,family:'G2-item-write-skew'},
    'strict-serializable':{...stale,family:'real-time-stale-read'},
    'snapshot-isolation':{...configured(custom.singleAnti),family:'G-single-item'},
    'consistent-view':{...configured(custom.singleAnti),family:'G-single-item'},
    'strong-session-read-uncommitted':{...configured(custom.g0Order,['B','C']),family:'G0-process-order'},
    'strong-read-uncommitted':{...configured(custom.g0Order),family:'G0-real-time-order'},
    'strong-session-read-committed':{...configured(custom.g1b),family:'G1b-original-intermediate-source'},
    'strong-read-committed':{...configured(custom.wrOrder),family:'G1c-real-time-WR-order'},
    'strong-session-serializable':{...stale,family:'process-stale-read'},
    'strong-session-snapshot-isolation':{...stale,family:'process-stale-read'},
    'strong-snapshot-isolation':{...configured(stale.source),family:'real-time-stale-cross-client'},
  };
  const cases=[];
  for(const model of MODELS){
    cases.push({id:model+'/compatible',model,role:'compatible',family:'serial-savepoint-delete-reinsert',expected:'checked-compatible',...structuredClone(positive)});
    cases.push({id:model+'/refuted',model,role:'refuted',expected:'refuted',...structuredClone(negatives[model])});
    const incomplete=structuredClone(positive);let family;
    if(model.startsWith('strong-session-')){incomplete.options={};family='missing-logical-client-membership';}
    else if(model==='strict-serializable'||model.startsWith('strong-')){incomplete.options.realtimeKnown=false;family='unproven-real-time-order';}
    else{incomplete.source.events=incomplete.source.events.filter(e=>e.seq!==3);family='missing-original-event';}
    cases.push({id:model+'/incomplete',model,role:'incomplete',family,expected:'unknown',...incomplete});
  }
  const controls=[
    {model:'strong-session-read-uncommitted',family:'cross-client-G0-order-is-not-session-order',...configured(custom.g0Order),expected:'checked-compatible'},
    {model:'strong-session-read-committed',family:'cross-client-WR-order-is-not-session-order',...configured(custom.wrOrder),expected:'checked-compatible'},
    {model:'strong-session-serializable',family:'cross-client-stale-is-not-session-stale',...configured(stale.source),expected:'checked-compatible'},
    {model:'strong-session-snapshot-isolation',family:'cross-client-stale-is-not-session-stale',...configured(stale.source),expected:'checked-compatible'},
    {model:'repeatable-read',family:'pure-predicate-phantom-cycle',...configured(custom.predicateOnly),expected:'checked-compatible'},
    {model:'repeatable-read',family:'Adya-mixed-item-predicate-cycle',...configured(custom.mixed),expected:'refuted'},
  ];
  for(const model of ['strict-serializable','strong-read-uncommitted','strong-read-committed','strong-snapshot-isolation']){
    const ordered=structuredClone(negatives[model]);ordered.options.realtimeKnown=false;
    controls.push({...ordered,model,family:'RT-only-witness-with-unproven-order',expected:'unknown'});
  }
  for(const [model,entry]of [
    ['strict-serializable',skew],['strong-read-uncommitted',configured(custom.g0)],
    ['strong-read-committed',aborted],['strong-snapshot-isolation',configured(custom.singleAnti)],
  ]){
    const known=structuredClone(entry);known.options.realtimeKnown=false;
    controls.push({model,family:'data-witness-survives-unproven-RT',...known,expected:'refuted'});
  }
  for(const item of controls)cases.push({id:item.model+'/'+item.family,role:'definition-control',...structuredClone(item)});
  const invalidInputs=['strict-serializable','strong-read-uncommitted','strong-read-committed','strong-snapshot-isolation'].map(model=>{
    const input=structuredClone(positive);delete input.source.clockDomain;
    return {id:model+'/missing-required-clockDomain',model,expected:'invalid-input',...input,
      options:{models:[model],...input.options,realtimeKnown:false}};
  });
  return {cases:cases.map(item=>({...item,options:{models:[item.model],...item.options}})),invalidInputs};
}
function tamperSource(source){
  const result=structuredClone(source),snapshot=result.events[0];
  const initial=Object.values(snapshot.initial)[0][0],key=Object.keys(initial.values)[0],value=initial.values[key];
  initial.values[key]=typeof value==='boolean'?!value:value==='0'?'1':'0';
  return result;
}
try{
  const generated=spawnSync(python,['-X','utf8','-B',resolve(tools,'relation-models-corpus.py'),'--output',resolve(out,'reference'),'--count','5','--seed','20261113'],{encoding:'utf8',maxBuffer:8*1024*1024,env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
  writeFileSync(resolve(out,'reference-generation.log'),(generated.stdout??'')+(generated.stderr??''),{flag:'wx'});
  if(generated.error)throw generated.error;assert.equal(generated.status,0,'Frozen reference generation failed');
  const reference=JSON.parse(readFileSync(resolve(out,'reference/histories.json'),'utf8')),{cases,invalidInputs}=casesFrom(reference);
  assert.equal(cases.filter(c=>c.role!=='definition-control').length,42);
  const matrix={format:'moontxnwitness-relation-fourteen-model-matrix/v1',seed:20261113,referenceCommit:'4e359e597c52938b0afebb8bc42273914d68a424',models:MODELS,cases,invalidInputs};
  writeFileSync(resolve(out,'cases.json'),JSON.stringify(matrix,null,2)+'\n',{flag:'wx'});
  const sdk=await import(pathToFileURL(resolve(runtime,'relation-models-v4.mjs')).href);
  const defaults=sdk.classifyRelationModelsV4(reference[0].source,reference[0].options);
  assert.deepEqual(defaults.models.map(m=>m.model),['read-uncommitted','read-committed','repeatable-read','snapshot-isolation','serializable','strict-serializable'],'Existing default six models changed');
  let originalsReplayed=0,tamperChecks=0;
  for(const [index,item]of cases.entries()){
    const filename='matrix-'+String(index).padStart(3,'0');
    try{
      const report=sdk.classifyRelationModelsV4(item.source,item.options);
      assert.equal(report.models.length,1,'Case must select exactly one explicit model');
      assert.equal(report.models[0].model,item.model);
      assert.equal(report.sourcePolicy?.realtimeKnown,item.options.realtimeKnown??true,'Report must bind the independently supplied real-time policy');
      const actual=report.models[0].status,verified=sdk.verifyRelationModelsV4(item.source,report,item.options).valid===true;
      if(actual!==item.expected)failures.push({id:item.id,kind:'fixed-model-expectation',expected:item.expected,actual});
      if(!verified)failures.push({id:item.id,kind:'source-recomputation-failed'});
      writeFileSync(resolve(out,'reports',filename+'.json'),JSON.stringify(report)+'\n',{flag:'wx'});
      const capsuleText=sdk.makeRelationModelsCapsuleV4(item.source,item.options),capsule=JSON.parse(capsuleText);
      const replay=sdk.replayRelationModelsCapsuleV4(capsuleText,item.options);
      if(replay.valid!==true)failures.push({id:item.id,kind:'original-capsule-replay-failed',replay});else originalsReplayed++;
      writeFileSync(resolve(out,'capsules',filename+'.json'),capsuleText+'\n',{flag:'wx'});
      const verdict=structuredClone(capsule),changedReport=JSON.parse(verdict.reportText);
      changedReport.models[0].status=actual==='refuted'?'checked-compatible':'refuted';changedReport.status=changedReport.models[0].status;
      verdict.reportText=JSON.stringify(changedReport);verdict.reportSha256=sha(verdict.reportText);
      const source=structuredClone(capsule);source.sourceText=JSON.stringify(tamperSource(JSON.parse(source.sourceText)));source.sourceSha256=sha(source.sourceText);
      const budget=structuredClone(capsule),options=JSON.parse(budget.optionsText);options.maxStates=options.maxStates===0?1:0;budget.optionsText=JSON.stringify(options);budget.optionsSha256=sha(budget.optionsText);
      const policy=structuredClone(capsule),policyOptions=JSON.parse(policy.optionsText);policyOptions.realtimeKnown=!policyOptions.realtimeKnown;policy.optionsText=JSON.stringify(policyOptions);policy.optionsSha256=sha(policy.optionsText);
      const reportPolicy=structuredClone(capsule),policyReport=JSON.parse(reportPolicy.reportText);policyReport.sourcePolicy.realtimeKnown=!policyReport.sourcePolicy.realtimeKnown;reportPolicy.reportText=JSON.stringify(policyReport);reportPolicy.reportSha256=sha(reportPolicy.reportText);
      const tamper={};
      for(const [kind,changed]of [['rehashed-verdict',verdict],['rehashed-source',source],['rehashed-budget',budget],['rehashed-realtime-policy',policy],['rehashed-report-realtime-policy',reportPolicy]]){
        const outcome=sdk.replayRelationModelsCapsuleV4(JSON.stringify(changed),item.options);tamperChecks++;
        tamper[kind]={rejected:outcome.valid===false,reason:outcome.reason??null};
        if(outcome.valid!==false)failures.push({id:item.id,kind:'tampered-capsule-accepted',tamper:kind,outcome});
        tamperRows.push({id:item.id,kind,expectedOptionsSha256:sha(JSON.stringify(item.options)),capsule:changed,result:outcome});
      }
      results.push({id:item.id,model:item.model,role:item.role,family:item.family,expected:item.expected,actual,verified,
        originalCapsuleReplayed:replay.valid===true,sourceSha256:sha(JSON.stringify(item.source)),optionsSha256:sha(JSON.stringify(item.options)),reportSha256:sha(JSON.stringify(report)),capsuleSha256:sha(capsuleText),tamper});
    }catch(error){failures.push({id:item.id,kind:'execution-failed',error:String(error)});}
  }
  for(const item of invalidInputs){
    const reject=operation=>{
      try{operation();return {rejected:false};}
      catch(error){if(!(error instanceof TypeError))throw error;return {rejected:true,error:String(error)};}
    };
    try{
      const report=sdk.classifyRelationModelsV4(reference[0].source,item.options);
      const classify=reject(()=>sdk.classifyRelationModelsV4(item.source,item.options));
      const capsule=reject(()=>sdk.makeRelationModelsCapsuleV4(item.source,item.options));
      const verify=sdk.verifyRelationModelsV4(item.source,report,item.options).valid===false;
      if(!classify.rejected||!capsule.rejected||!verify)failures.push({id:item.id,kind:'invalid-clock-input-was-not-rejected',classify,capsule,verify});
      invalidResults.push({id:item.id,expected:'invalid-input',actual:'not-a-model-judgment',classify,capsule,verificationRejected:verify,
        sourceSha256:sha(JSON.stringify(item.source)),optionsSha256:sha(JSON.stringify(item.options))});
    }catch(error){failures.push({id:item.id,kind:'invalid-input-guard-execution-failed',error:String(error)});}
  }
  for(const [name,{path,...expected}]of Object.entries(originals)){
    assert.deepEqual(binding(path),expected,'Original source changed: '+name);
    assert.deepEqual(binding(resolve(out,name)),expected,'Frozen source changed: '+name);
  }
  const raw=results.map(r=>JSON.stringify(r)).join('\n')+'\n',tampered=tamperRows.map(r=>JSON.stringify(r)).join('\n')+'\n';
  writeFileSync(resolve(out,'results.jsonl'),raw,{flag:'wx'});writeFileSync(resolve(out,'tamper-cases.jsonl'),tampered,{flag:'wx'});
  const invalidRaw=invalidResults.map(r=>JSON.stringify(r)).join('\n')+'\n';
  writeFileSync(resolve(out,'invalid-input-results.jsonl'),invalidRaw,{flag:'wx'});
  const summary={format:'moontxnwitness-relation-fourteen-model-matrix-result/v1',passed:failures.length===0,
    publicApiExecution:true,publicPackageVerified:false,formalPerformanceMeasurement:false,models:14,requiredPositions:42,
    requiredDeterminatePositions:28,requiredUnknownBoundaries:14,
    definitionControls:cases.length-42,executedPositions:results.length,originalCapsulesReplayed:originalsReplayed,
    invalidInputCases:invalidResults.length,invalidInputGuardChecks:invalidResults.length*3,
    determinateJudgmentPositions:cases.filter(item=>item.expected!=='unknown').length,
    unknownBoundaryPositions:cases.filter(item=>item.expected==='unknown').length,
    matchedDeterminatePositions:results.filter(item=>item.expected!=='unknown'&&item.actual===item.expected).length,
    matchedUnknownBoundaries:results.filter(item=>item.expected==='unknown'&&item.actual===item.expected).length,
    rehashedTamperChecks:tamperChecks,fullFourteenModelParity:false,
    scope:'Predeclared relation model examples and definition boundaries; actual public SDK execution and source recomputation. This matrix is not independent full-model or upstream Elle predicate equivalence.',
    sourceBindings,inputs:{cases:binding(resolve(out,'cases.json')),reference:binding(resolve(out,'reference/histories.json'))},
    resultsSha256:sha(raw),tamperCasesSha256:sha(tampered),invalidInputResultsSha256:sha(invalidRaw),failures};
  writeFileSync(resolve(out,'summary.json'),JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({passed:summary.passed,requiredPositions:42,definitionControls:summary.definitionControls,executedPositions:results.length,rehashedTamperChecks:tamperChecks,invalidInputCases:summary.invalidInputCases,failures}));
  if(!summary.passed)process.exitCode=1;
}catch(error){writeFileSync(resolve(out,'failure.json'),JSON.stringify({passed:false,error:String(error),failures,sourceBindings},null,2)+'\n',{flag:'wx'});throw error;}
