// Explicit source-verified synchronous model profile. Old v3/ORM APIs stay separate.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {model_profile_source_v3_json,version} from './core.mjs';

const PROFILE='pg18-configured-models/1';
const ALGORITHM='model-profile-host-1';
const SOURCE_ALGORITHM='v3-configured-model-source-projection-1';
const MiB=1024*1024;
const BUDGETS=Object.freeze({sourceEnvelopeUtf8Bytes:64*MiB,traceUtf8Bytes:8*MiB,
  sourceJournalUtf8Bytes:16*MiB,lifecycleUtf8Bytes:8*MiB,journalIndexUtf8Bytes:2*MiB,
  optionsUtf8Bytes:4096,reportUtf8Bytes:64*MiB,capsuleUtf8Bytes:128*MiB,
  exactSearchTransactions:6,exactSearchOperations:128,maxStates:100000,maxOperationChecks:1000000});
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const canonical=value=>JSON.stringify(value,null,2)+'\n';
const ENGINE=Object.freeze({version:version(),coreSha256:hash(readFileSync(new URL('./core.mjs',import.meta.url))),
  hostSha256:hash(readFileSync(new URL(import.meta.url)))});
const scope=()=>({configuredNativeSyncFactoryOnly:true,explicitOwnedSchemaInstallation:true,
  originalDiagnosticsRemainPartial:true,actualDatabaseExecution:false,
  serverAuthenticityVerified:false,eventSegmentPayloadsRehashed:false,
  arbitrarySqlSupported:false,ormSupported:false,asynchronousSupported:false,
  realTimeOrderInferred:false,sourceClosedReductionAvailable:false});

function bounded(value,maximum,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(label+' must be JSON text or a serializable object');
  if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds its explicit UTF-8 budget');
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');
  return text;
}
function optionsText(options){
  if(options===null||typeof options!=='object'||Array.isArray(options)||![Object.prototype,null].includes(Object.getPrototypeOf(options)))
    throw new TypeError('Model search options must be a plain object');
  const maxima={maxStates:100000,maxOperationChecks:1000000};
  for(const name of Object.keys(options)){
    const limit=maxima[name];
    if(!Object.hasOwn(maxima,name)||!Number.isSafeInteger(options[name])||options[name]<0||options[name]>limit)
      throw new RangeError('Unsupported model search option: '+name);
  }
  return bounded(options,BUDGETS.optionsUtf8Bytes,'model options');
}
function sourceBindings(envelopeText){
  const result={envelopeSha256:hash(envelopeText),traceSha256:null,sourceJournalSha256:null,lifecycleSha256:null,journalIndexSha256:null};
  let input;try{input=JSON.parse(envelopeText);}catch{return result;}
  for(const name of ['trace','sourceJournal','lifecycle','journalIndex']){
    if(typeof input?.[name+'Text']==='string')result[name+'Sha256']=hash(bounded(input[name+'Text'],BUDGETS[name+'Utf8Bytes'],'original '+name));
  }
  return result;
}

/** Explicit configured-source analysis. No generic diagnostic is rewritten. */
export function analyzeModelProfileV3(envelope,options={}){
  const envelopeText=bounded(envelope,BUDGETS.sourceEnvelopeUtf8Bytes,'model source envelope');
  const requested=optionsText(options),bindings=sourceBindings(envelopeText);
  const result=JSON.parse(model_profile_source_v3_json(envelopeText,requested));
  if(result.algorithm!==SOURCE_ALGORITHM||result.profile!==PROFILE||result.version!==version())
    throw new Error('Unsupported model source algorithm/profile/engine');
  if(result.analysisCoverageAccepted===true){
    for(const name of ['trace','sourceJournal','lifecycle','journalIndex'])
      if(result.sourceBindings?.[name+'Sha256']!==bindings[name+'Sha256'])throw new Error('Core and host original-source bindings differ');
  }
  const report={format:'moontxnwitness-model-profile-report/v1',schemaVersion:1,tool:'MoonTxnWitness',
    algorithm:ALGORITHM,sourceAlgorithm:SOURCE_ALGORITHM,profile:PROFILE,engine:{...ENGINE},
    status:result.status,analysisCoverageAccepted:result.analysisCoverageAccepted===true,
    requestOptionsText:requested,sourceBindings:bindings,budgets:{...BUDGETS},scope:scope(),result};
  bounded(report,BUDGETS.reportUtf8Bytes,'model profile report');return report;
}

/** Exact recomputation checks even an inconclusive report; no facts are lost. */
export function verifyModelProfileV3(envelope,supplied,options){
  try{
    const text=bounded(supplied,BUDGETS.reportUtf8Bytes,'model report'),parsed=JSON.parse(text);
    if(parsed?.format!=='moontxnwitness-model-profile-report/v1'||parsed.algorithm!==ALGORITHM||
       parsed.sourceAlgorithm!==SOURCE_ALGORITHM||parsed.profile!==PROFILE||typeof parsed.requestOptionsText!=='string')
      return {valid:false,reason:'unsupported-model-profile-report',scope:scope()};
    const expected=analyzeModelProfileV3(envelope,options??JSON.parse(parsed.requestOptionsText));
    if(JSON.stringify(parsed)!==JSON.stringify(expected)||typeof supplied==='string'&&text!==JSON.stringify(expected)&&text!==canonical(expected))
      return {valid:false,reason:'model-profile-report-does-not-reproduce',scope:scope()};
    return {valid:true,status:expected.status,analysisCoverageAccepted:expected.analysisCoverageAccepted,
      sourceBindings:expected.sourceBindings,scope:scope()};
  }catch(error){return {valid:false,reason:'model-profile-verification-failed: '+error.message,scope:scope()};}
}

function capsuleFields(envelopeText,requestOptionsText,reportText){
  return {format:'moontxnwitness-model-profile/v1',schemaVersion:1,tool:'MoonTxnWitness',
    algorithm:ALGORITHM,sourceAlgorithm:SOURCE_ALGORITHM,profile:PROFILE,engine:{...ENGINE},
    budgets:{...BUDGETS},requestOptionsText,requestOptionsSha256:hash(requestOptionsText),
    envelopeText,sourceBindings:sourceBindings(envelopeText),reportText,reportSha256:hash(reportText)};
}

export function makeModelProfileCapsuleV3(envelope,options={}){
  const envelopeText=bounded(envelope,BUDGETS.sourceEnvelopeUtf8Bytes,'model source envelope');
  const requestOptionsText=optionsText(options),report=analyzeModelProfileV3(envelopeText,options);
  return bounded(canonical(capsuleFields(envelopeText,requestOptionsText,JSON.stringify(report))),BUDGETS.capsuleUtf8Bytes,'model capsule');
}

/** Self-contained full-source replay, bound to the exact current core/host bytes. */
export function replayModelProfileCapsuleV3(text){
  const reject=reason=>({valid:false,reason,scope:scope()});
  try{
    if(typeof text!=='string')return reject('model-capsule-must-be-original-text');
    bounded(text,BUDGETS.capsuleUtf8Bytes,'model capsule');const value=JSON.parse(text);
    if(value?.format!=='moontxnwitness-model-profile/v1'||value.schemaVersion!==1||value.tool!=='MoonTxnWitness'||
       value.algorithm!==ALGORITHM||value.sourceAlgorithm!==SOURCE_ALGORITHM||value.profile!==PROFILE||
       JSON.stringify(value.engine)!==JSON.stringify(ENGINE)||typeof value.envelopeText!=='string'||
       typeof value.requestOptionsText!=='string'||typeof value.reportText!=='string')return reject('unsupported-model-capsule-header');
    bounded(value.envelopeText,BUDGETS.sourceEnvelopeUtf8Bytes,'model source envelope');
    bounded(value.reportText,BUDGETS.reportUtf8Bytes,'model report');
    const options=JSON.parse(bounded(value.requestOptionsText,BUDGETS.optionsUtf8Bytes,'model options'));
    if(optionsText(options)!==value.requestOptionsText)return reject('model-options-not-canonical');
    if(text!==canonical(capsuleFields(value.envelopeText,value.requestOptionsText,value.reportText)))return reject('model-capsule-fields-or-digests-differ');
    const expected=analyzeModelProfileV3(value.envelopeText,options);
    if(JSON.stringify(expected)!==value.reportText)return reject('model-result-does-not-reproduce');
    return {valid:true,status:expected.status,analysisCoverageAccepted:expected.analysisCoverageAccepted,
      envelopeText:value.envelopeText,sourceBindings:expected.sourceBindings,report:expected,scope:scope()};
  }catch(error){return reject('model-capsule-recomputation-failed: '+error.message);}
}
