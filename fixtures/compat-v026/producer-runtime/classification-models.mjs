// Explicit six-definition model checks. Category SDK/reducer remains separate.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {isDeepStrictEqual} from 'node:util';
import {classify_v3_json,verify_classification_v3_json,version} from './core.mjs';

const MiB=1024*1024,ALGORITHM='isolation-model-host-1',CORE_ALGORITHM='v3-isolation-model-1';
const MODELS=Object.freeze(['adya-pl-1-v1','adya-pl-2-v1','adya-pl-2.99-v1','elle-generalized-si-v1','adya-pl-3-v1','strict-pl-ss-v1']);
const BUDGETS=Object.freeze({sourceUtf8Bytes:32*MiB,rawTraceUtf8Bytes:8*MiB,sourceComponentUtf8Bytes:8*MiB,
  optionsUtf8Bytes:8192,coreReportUtf8Bytes:32*MiB,reportUtf8Bytes:96*MiB,capsuleUtf8Bytes:192*MiB,
  registerTransactions:128,registerOperations:4096,listCommittedTransactions:6,listOperations:128,
  edges:50000,statesPerRule:100000,edgeChecksPerRule:1000000});
const hash=text=>createHash('sha256').update(text).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
const ENGINE=Object.freeze({version:version(),coreSha256:hash(readFileSync(new URL('./core.mjs',import.meta.url))),
  hostSha256:hash(readFileSync(new URL(import.meta.url)))});
const scope=()=>({modelDefinitions:MODELS.slice(),supportedDataModels:['point-register-v1','append-list-v1'],
  relationModelClassificationSupported:false,modelPreservingReductionSupported:false,categoryReducerUnchanged:true,
  listGraphProfile:'one append per transaction per key, complete captured order, no savepoints',
  strictRequiresExplicitClientIntervals:true,traceTimeInfersRealTime:false,beginInfersSnapshot:false,
  clientEvidenceAuthenticatesCollector:false,journalSegmentPayloadsRehashed:false,
  actualDatabaseExecution:false,databaseWideCertification:false,oldAnalyzeAndCapsulesUnchanged:true});
function bounded(value,maximum,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(label+' must be JSON text or a serializable object');
  if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds its explicit UTF-8 budget');
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');
  return text;
}
function plain(value,label){
  if(value===null||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value))||
     Object.getOwnPropertySymbols(value).length||Object.values(Object.getOwnPropertyDescriptors(value)).some(d=>d.get||d.set))
    throw new TypeError(label+' must be a plain JSON object');
}
function optionsText(options){
  plain(options,'Model classification options');
  for(const name of Object.keys(options)){
    if(name==='models'){
      const a=options.models;
      if(!Array.isArray(a)||!a.length||a.length>6||a.some(v=>!MODELS.includes(v))||new Set(a).size!==a.length)
        throw new RangeError('models must contain unique supported definition identifiers');
    }else if(name==='maxStates'||name==='maxEdgeChecks'){
      const limit=name==='maxStates'?100000:1000000;
      if(!Number.isSafeInteger(options[name])||options[name]<0||options[name]>limit)throw new RangeError('Unsupported '+name+' budget');
    }else if(name==='normalizationOptions'){
      plain(options[name],'Normalization options');
      for(const field of Object.keys(options[name]))
        if(field!=='sqlProof'||options[name][field]!=='dislock-f9946f0-sql-proof-1')throw new RangeError('Unsupported explicit SQL proof policy');
    }else throw new RangeError('Unsupported model classification option: '+name);
  }
  return bounded(options,BUDGETS.optionsUtf8Bytes,'model options');
}
function sourceBindings(sourceText){
  const bindings={sourceSha256:hash(sourceText),traceSha256:hash(sourceText),intervalEvidenceSha256:null,lifecycleSha256:null,journalIndexSha256:null};
  let source;try{source=JSON.parse(sourceText);}catch{return bindings;}
  if(source?.format==='moontxnwitness-classification-source/v1'){
    for(const name of ['trace','intervalEvidence','lifecycle','journalIndex']){
      if(typeof source[name+'Text']==='string')bindings[name+'Sha256']=hash(bounded(source[name+'Text'],BUDGETS.sourceComponentUtf8Bytes,name+' source'));
      else bindings[name+'Sha256']=null;
    }
  }else bounded(sourceText,BUDGETS.rawTraceUtf8Bytes,'raw model trace');
  return bindings;
}

/** Check explicit frozen model definitions against supplied facts, including applicability gaps. */
export function classifyModelsV3(source,options={}){
  const sourceText=bounded(source,BUDGETS.sourceUtf8Bytes,'model classification source'),requested=optionsText(options);
  const effective=Object.hasOwn(options,'models')?requested:JSON.stringify({...options,models:MODELS});
  bounded(effective,BUDGETS.optionsUtf8Bytes,'effective model options');
  const bindings=sourceBindings(sourceText);
  const raw=bounded(classify_v3_json(sourceText,effective),BUDGETS.coreReportUtf8Bytes,'core model report'),result=JSON.parse(raw);
  if(result?.version!==version()||![CORE_ALGORITHM,'v3-register-category-1'].includes(result?.algorithm)||
     result.algorithm!==CORE_ALGORITHM&&!['invalid','inconclusive'].includes(result.status))
    throw new Error('Unsupported model classification core algorithm/engine');
  const replay=JSON.parse(verify_classification_v3_json(sourceText,raw));
  if(result.algorithm===CORE_ALGORITHM&&replay.valid!==true)throw new Error('Core model report failed exact verification');
  const interval=result.intervalEvidence;
  if(interval?.traceBytesBound===true){
    for(const[name,field]of [['trace','sourceTraceSha256'],['intervalEvidence','sourceIntervalEvidenceSha256'],['lifecycle','sourceLifecycleSha256'],['journalIndex','sourceJournalIndexSha256']])
      if(bindings[name+'Sha256']!==interval[field])throw new Error('Core and host interval source hashes differ');
  }
  const report={format:'moontxnwitness-isolation-model-report/v1',schemaVersion:1,tool:'MoonTxnWitness',
    algorithm:ALGORITHM,coreAlgorithm:result.algorithm,engine:{...ENGINE},status:result.status,
    requestOptionsText:requested,coreOptionsText:effective,originalSourceText:sourceText,sourceBindings:bindings,
    budgets:{...BUDGETS},scope:scope(),result,coreReportReplay:replay,
    verificationPasses:{coreClassification:1,coreReportVerification:1}};
  bounded(report,BUDGETS.reportUtf8Bytes,'model classification report');return report;
}
export function verifyModelsClassificationV3(source,supplied,options){
  try{
    const text=bounded(supplied,BUDGETS.reportUtf8Bytes,'model report'),value=JSON.parse(text);
    if(value?.format!=='moontxnwitness-isolation-model-report/v1'||value.algorithm!==ALGORITHM||typeof value.requestOptionsText!=='string')
      return {valid:false,reason:'unsupported-model-classification-report',scope:scope()};
    const expected=classifyModelsV3(source,options??JSON.parse(value.requestOptionsText));
    if(!isDeepStrictEqual(value,expected)||typeof supplied==='string'&&text!==JSON.stringify(expected)&&text!==canonical(expected))
      return {valid:false,reason:'model-classification-report-does-not-reproduce',scope:scope()};
    return {valid:true,status:expected.status,sourceBindings:expected.sourceBindings,scope:scope()};
  }catch(error){return {valid:false,reason:'model-classification-verification-failed: '+error.message,scope:scope()};}
}
function capsuleFields(sourceText,requestOptionsText,reportText){
  return {format:'moontxnwitness-isolation-models/v1',schemaVersion:1,tool:'MoonTxnWitness',algorithm:ALGORITHM,
    coreAlgorithm:JSON.parse(reportText).coreAlgorithm,engine:{...ENGINE},budgets:{...BUDGETS},
    sourceText,sourceBindings:sourceBindings(sourceText),requestOptionsText,requestOptionsSha256:hash(requestOptionsText),
    reportText,reportSha256:hash(reportText)};
}
export function makeModelsClassificationCapsuleV3(source,options={}){
  const sourceText=bounded(source,BUDGETS.sourceUtf8Bytes,'model source'),requested=optionsText(options),report=classifyModelsV3(sourceText,options);
  return bounded(canonical(capsuleFields(sourceText,requested,JSON.stringify(report))),BUDGETS.capsuleUtf8Bytes,'model capsule');
}
export function replayModelsClassificationCapsuleV3(text){
  const reject=reason=>({valid:false,reason,scope:scope()});
  try{
    if(typeof text!=='string')return reject('model-capsule-must-be-original-text');
    bounded(text,BUDGETS.capsuleUtf8Bytes,'model capsule');const value=JSON.parse(text);
    if(value?.format!=='moontxnwitness-isolation-models/v1'||value.schemaVersion!==1||value.tool!=='MoonTxnWitness'||
       value.algorithm!==ALGORITHM||!isDeepStrictEqual(value.engine,ENGINE)||typeof value.sourceText!=='string'||
       typeof value.requestOptionsText!=='string'||typeof value.reportText!=='string')return reject('unsupported-model-classification-capsule');
    bounded(value.sourceText,BUDGETS.sourceUtf8Bytes,'model source');bounded(value.reportText,BUDGETS.reportUtf8Bytes,'model report');
    const options=JSON.parse(bounded(value.requestOptionsText,BUDGETS.optionsUtf8Bytes,'model options'));
    if(optionsText(options)!==value.requestOptionsText)return reject('model-options-not-canonical');
    if(canonical(capsuleFields(value.sourceText,value.requestOptionsText,value.reportText))!==text)
      return reject('model-capsule-fields-digest-or-original-bytes-differ');
    const result=verifyModelsClassificationV3(value.sourceText,value.reportText,options);
    if(!result.valid)return reject(result.reason);
    const report=JSON.parse(value.reportText);
    return {valid:true,status:report.status,report,sourceBindings:report.sourceBindings,scope:scope()};
  }catch(error){return reject('model-classification-capsule-replay-failed: '+error.message);}
}
