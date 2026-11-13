import {createHash} from 'node:crypto';
import {infer_dependencies_v4_json, classify_with_inference_v4_json,
  verify_inference_v4_json, verify_with_inference_v4_json,
  inference_options_v4_content_json, inference_report_v4_content_json, version} from './core.mjs';

const MiB=1024*1024;
export const INFERENCE_V4_LIMITS=Object.freeze({sourceUtf8Bytes:8*MiB,optionsUtf8Bytes:16384,reportUtf8Bytes:64*MiB,capsuleUtf8Bytes:160*MiB});
export const INFERENCE_MODULES_V4=Object.freeze(['original-read-sources/v1','original-version-constraints/v1','observed-list-prefixes/v1','declared-transaction-orders/v1']);
const FORMAT='moontxnwitness-registered-inference-replay/v4';
const SCOPE='recomputed under independently selected compiled modules and budgets; original observations are not authenticated';
const digest=text=>createHash('sha256').update(text,'utf8').digest('hex');
function bounded(value,maximum,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(label+' must be JSON text or serializable data');
  if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds '+maximum+' UTF-8 bytes');
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');
  return text;
}
function parsed(text,normalizer,label){
  const result=JSON.parse(normalizer(text));
  if(result.valid!==true)throw new TypeError(result.error||'Invalid '+label);
  return result.options??result.value;
}
function prepared(options){
  if(typeof options!=='string'&&(options===null||typeof options!=='object'||Array.isArray(options)||![Object.prototype,null].includes(Object.getPrototypeOf(options))))throw new TypeError('inference options must be a plain object or JSON object text');
  const normalized=parsed(bounded(options,INFERENCE_V4_LIMITS.optionsUtf8Bytes,'inference options'),inference_options_v4_content_json,'inference options');
  return {normalized,text:bounded(normalized,INFERENCE_V4_LIMITS.optionsUtf8Bytes,'normalized inference options')};
}
/** Module selection is mandatory; options never come from a report. */
export function parseInferenceOptionsV4(input){return prepared(input).normalized;}
function identity(report){
  const classify=report.format==='moontxnwitness-model-inference-composition/v4';
  const expected=classify?['registered-inference-and-model-refutations/v1','base-models-and-conditional-module-refutations-1']:['registered-source-inference-modules/v1','same-original-index-single-pass-modules-1'];
  if(report.schemaVersion!==4||report.semanticContract!==expected[0]||report.algorithm!==expected[1])throw new TypeError('Unsupported inference report identity');
  const inference=classify?report.inference:report;
  if(inference?.execution?.counterContract!=='shared-module-invocations-callback-and-output-checks-1')throw new TypeError('Unsupported inference counter contract');
  return {semanticContract:expected[0],algorithm:expected[1],counterContract:inference.execution.counterContract};
}
function run(sourceText,optionsText,operation){
  const core=operation==='infer-dependencies'?infer_dependencies_v4_json:classify_with_inference_v4_json;
  const text=bounded(core(sourceText,optionsText),INFERENCE_V4_LIMITS.reportUtf8Bytes,'inference report');
  const report=parsed(text,inference_report_v4_content_json,'inference report');
  identity(report);return {text,report};
}
export function inferDependenciesV4(source,options){return run(bounded(source,INFERENCE_V4_LIMITS.sourceUtf8Bytes,'inference source'),prepared(options).text,'infer-dependencies').report;}
export function classifyWithInferenceV4(source,options){return run(bounded(source,INFERENCE_V4_LIMITS.sourceUtf8Bytes,'inference source'),prepared(options).text,'classify-with-inference').report;}
function verify(source,report,expectedOptions,operation){
  try{
    const sourceText=bounded(source,INFERENCE_V4_LIMITS.sourceUtf8Bytes,'inference source');
    const reportText=bounded(report,INFERENCE_V4_LIMITS.reportUtf8Bytes,'inference report');
    const value=parsed(reportText,inference_report_v4_content_json,'inference report');identity(value);
    if((value.format==='moontxnwitness-inference/v4')!==(operation==='infer-dependencies'))throw new TypeError('Inference operation/report mismatch');
    const core=operation==='infer-dependencies'?verify_inference_v4_json:verify_with_inference_v4_json;
    return JSON.parse(core(sourceText,reportText,prepared(expectedOptions).text));
  }catch(error){return {valid:false,reason:error.message,scope:SCOPE};}
}
export function verifyInferenceV4(source,report,expectedOptions){return verify(source,report,expectedOptions,'infer-dependencies');}
export function verifyWithInferenceV4(source,report,expectedOptions){return verify(source,report,expectedOptions,'classify-with-inference');}
export function makeInferenceCapsuleV4(source,options,operation='classify-with-inference'){
  if(!['infer-dependencies','classify-with-inference'].includes(operation))throw new TypeError('Unsupported inference operation');
  const sourceText=bounded(source,INFERENCE_V4_LIMITS.sourceUtf8Bytes,'inference source');
  const optionsText=prepared(options).text,{text:reportText,report}=run(sourceText,optionsText,operation);
  return bounded({format:FORMAT,schemaVersion:4,tool:'MoonTxnWitness',producer:{version:version()},operation,...identity(report),sourceText,sourceSha256:digest(sourceText),optionsText,optionsSha256:digest(optionsText),reportText,reportSha256:digest(reportText)},INFERENCE_V4_LIMITS.capsuleUtf8Bytes,'inference capsule');
}
/** A canonical envelope rejects duplicate decoded keys before semantic replay. */
export function replayInferenceCapsuleV4(input,expectedOptions){
  const reject=reason=>({valid:false,reason,scope:SCOPE});
  try{
    const text=bounded(input,INFERENCE_V4_LIMITS.capsuleUtf8Bytes,'inference capsule'),capsule=JSON.parse(text);
    if(text!==JSON.stringify(capsule))return reject('noncanonical-inference-capsule');
    const keys=['format','schemaVersion','tool','producer','operation','semanticContract','algorithm','counterContract','sourceText','sourceSha256','optionsText','optionsSha256','reportText','reportSha256'];
    if(capsule===null||Array.isArray(capsule)||JSON.stringify(Object.keys(capsule))!==JSON.stringify(keys)||capsule.format!==FORMAT||capsule.schemaVersion!==4||capsule.tool!=='MoonTxnWitness'||!['infer-dependencies','classify-with-inference'].includes(capsule.operation)||!capsule.producer||JSON.stringify(Object.keys(capsule.producer))!=='["version"]'||typeof capsule.producer.version!=='string')return reject('unsupported-inference-capsule');
    for(const [key,max]of [['source',INFERENCE_V4_LIMITS.sourceUtf8Bytes],['options',INFERENCE_V4_LIMITS.optionsUtf8Bytes],['report',INFERENCE_V4_LIMITS.reportUtf8Bytes]]){
      if(typeof capsule[key+'Text']!=='string')return reject('invalid-'+key+'-text');
      const raw=bounded(capsule[key+'Text'],max,key);
      if(!/^[a-f0-9]{64}$/.test(capsule[key+'Sha256'])||digest(raw)!==capsule[key+'Sha256'])return reject(key+'-sha256-mismatch');
    }
    const report=parsed(capsule.reportText,inference_report_v4_content_json,'inference report'),ids=identity(report);
    for(const [key,value]of Object.entries(ids))if(capsule[key]!==value)return reject('capsule-report-'+key+'-mismatch');
    if(prepared(capsule.optionsText).text!==prepared(expectedOptions).text)return reject('caller-expected-inference-options-mismatch');
    const result=verify(capsule.sourceText,capsule.reportText,expectedOptions,capsule.operation);
    if(result.valid!==true)return reject('recomputed-inference-report-differs');
    return {valid:true,status:'recomputed',operation:capsule.operation,...ids,producer:capsule.producer,scope:SCOPE};
  }catch(error){return reject(error.message);}
}
