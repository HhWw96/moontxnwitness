// Canonical isolation-model obligations; independent of graph-category APIs.
import {createHash} from 'node:crypto';
import {classify_models_v4_json,verify_model_classification_v4_json,
  model_options_v4_content_json,model_report_v4_content_json,model_capsule_v4_content_json,version} from './core.mjs';
const MiB=1024*1024;
export const MODEL_V4_LIMITS=Object.freeze({sourceUtf8Bytes:8*MiB,optionsUtf8Bytes:8192,reportUtf8Bytes:32*MiB,capsuleUtf8Bytes:64*MiB,maxSourceChecks:1000000,maxStates:100000,maxEdgeChecks:1000000});
export const ELLE_CORE_MODELS_V4=Object.freeze(['read-uncommitted','read-committed','repeatable-read','serializable','strict-serializable','snapshot-isolation','consistent-view','strong-session-read-uncommitted','strong-read-uncommitted','strong-session-read-committed','strong-read-committed','strong-session-serializable','strong-session-snapshot-isolation','strong-snapshot-isolation']);
const SCOPE='semantic model reproduction under caller-supplied source policy and budgets; original observations are not authenticated';
const FORMAT='moontxnwitness-model-obligations-replay/v4';
const hash=text=>createHash('sha256').update(text,'utf8').digest('hex');
function bounded(value,maximum,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(label+' must be JSON text or serializable data');
  if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds '+maximum+' UTF-8 bytes');
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');
  return text;
}
function guarded(text,core,label){
  const result=JSON.parse(core(text));
  if(result.valid!==true)throw new TypeError(result.error||'Invalid '+label);
  return result.options??result.value;
}
function prepared(options={}){
  if(typeof options!=='string' && (options===null||typeof options!=='object'||Array.isArray(options)||![Object.prototype,null].includes(Object.getPrototypeOf(options))))throw new TypeError('model options must be a plain object or JSON object text');
  const requested=bounded(options,MODEL_V4_LIMITS.optionsUtf8Bytes,'model options');
  const normalized=guarded(requested,model_options_v4_content_json,'model options');
  return {normalized,optionsText:bounded(normalized,MODEL_V4_LIMITS.optionsUtf8Bytes,'normalized model options')};
}
/** Preserve omitted fields for CLI merging, after strict duplicate/field validation. */
export function parseModelOptionsV4(input){const text=bounded(input,MODEL_V4_LIMITS.optionsUtf8Bytes,'model options');prepared(text);return JSON.parse(text);}
function identity(report){
  if(report?.format!=='moontxnwitness-model-composition/v4'||report.schemaVersion!==4)throw new TypeError(report?.error||'Unsupported model report');
  const profile=report.sourceProfile;
  const row=profile==='captured-relation-row-slots/v1',list=profile==='captured-list-prefix-state/v2',raw=profile==='captured-register-full-program/v2';
  if(![ 'declared-register-full-program/v1','captured-register-full-program/v2','effective-list-appends/v1','captured-list-prefix-state/v2','relation-point-final-installed/v1','adya-2000-predicate-on-keyslots-v1','captured-relation-row-slots/v1'].includes(profile))throw new TypeError('Unsupported model source profile');
  const expected=row?['elle-4e359e5-captured-relation-row-slot-completion-models-1','captured-row-slot-obligations-and-original-program-completion-1','captured-row-slot-independent-source-and-per-rule-graph-counters-1']:list?['elle-4e359e5-captured-list-prefix-state-completion-models-2','captured-list-prefix-obligations-and-completion-2','captured-list-prefix-independent-source-and-per-rule-graph-counters-2']:raw?['elle-4e359e5-captured-register-observation-completion-models-2','captured-point-source-obligations-and-prefix-completion-2','captured-point-independent-source-and-per-rule-graph-counters-2']:['elle-4e359e5-transaction-observation-completion-models-1','history-source-obligations-scoped-graph-and-prefix-completion-1','model-independent-source-and-per-rule-graph-counters-1'];
  if(report.semanticContract!==expected[0]||report.algorithm!==expected[1]||report.execution?.counterContract!==expected[2])throw new TypeError('Unsupported model semantic/algorithm/counter identity');
  return {semanticContract:expected[0],algorithm:expected[1],counterContract:expected[2],sourceProfile:profile};
}
function run(sourceText,optionsText){
  const reportText=bounded(classify_models_v4_json(sourceText,optionsText),MODEL_V4_LIMITS.reportUtf8Bytes,'model report');
  const report=guarded(reportText,model_report_v4_content_json,'model report');
  identity(report);return {reportText,report};
}
export function classifyModelsV4(source,options={}){
  return run(bounded(source,MODEL_V4_LIMITS.sourceUtf8Bytes,'model source'),prepared(options).optionsText).report;
}
export function verifyModelsV4(source,report,expectedOptions={}){
  try{
    const sourceText=bounded(source,MODEL_V4_LIMITS.sourceUtf8Bytes,'model source');
    const reportText=bounded(report,MODEL_V4_LIMITS.reportUtf8Bytes,'model report');
    identity(guarded(reportText,model_report_v4_content_json,'model report'));
    return JSON.parse(verify_model_classification_v4_json(sourceText,reportText,prepared(expectedOptions).optionsText));
  }catch(error){return {valid:false,reason:error.message,scope:SCOPE};}
}
export function makeModelsCapsuleV4(source,options={}){
  const sourceText=bounded(source,MODEL_V4_LIMITS.sourceUtf8Bytes,'model source');
  const {optionsText}=prepared(options),{reportText,report}=run(sourceText,optionsText);
  return bounded({format:FORMAT,schemaVersion:4,tool:'MoonTxnWitness',producer:{version:version()},operation:'classify-models',...identity(report),sourceText,sourceSha256:hash(sourceText),optionsText,optionsSha256:hash(optionsText),reportText,reportSha256:hash(reportText)},MODEL_V4_LIMITS.capsuleUtf8Bytes,'model capsule');
}
/** Replay is full reanalysis; embedded limits/profile never grant authorization. */
export function replayModelsCapsuleV4(input,expectedOptions={}){
  const reject=reason=>({valid:false,reason,scope:SCOPE});
  try{
    const capsule=JSON.parse(model_capsule_v4_content_json(bounded(input,MODEL_V4_LIMITS.capsuleUtf8Bytes,'model capsule')));
    if(capsule.format!==FORMAT||capsule.operation!=='classify-models')return reject('unsupported-model-capsule');
    const sourceText=bounded(capsule.sourceText,MODEL_V4_LIMITS.sourceUtf8Bytes,'model source');
    const optionsText=bounded(capsule.optionsText,MODEL_V4_LIMITS.optionsUtf8Bytes,'model options');
    const reportText=bounded(capsule.reportText,MODEL_V4_LIMITS.reportUtf8Bytes,'model report');
    for(const [name,text]of [['source',sourceText],['options',optionsText],['report',reportText]])if(!/^[a-f0-9]{64}$/.test(capsule[name+'Sha256'])||capsule[name+'Sha256']!==hash(text))return reject(name+'-sha256-mismatch');
    const report=guarded(reportText,model_report_v4_content_json,'model report'),ids=identity(report);
    for(const key of Object.keys(ids))if(capsule[key]!==ids[key])return reject('capsule-report-'+key+'-mismatch');
    const embedded=prepared(optionsText),independent=prepared(expectedOptions);
    if(embedded.optionsText!==independent.optionsText)return reject('caller-expected-model-options-mismatch');
    if(verifyModelsV4(sourceText,reportText,expectedOptions).valid!==true)return reject('recomputed-model-report-differs');
    return {valid:true,schemaVersion:4,status:'recomputed',modelStatus:report.status,operation:'classify-models',...ids,models:report.models.map(m=>({model:m.model,status:m.status})),producer:capsule.producer,scope:SCOPE};
  }catch(error){return reject(error.message);}
}
