// Fixed-category relation reduction. Existing v4 analysis/capsules are unchanged.
import {createHash} from 'node:crypto';
import {normalizeRelationPredicateOptionsV4} from './relation-v4.mjs';
import {reduce_relation_category_v4_json,verify_relation_category_reduction_v4_json,
  relation_reduction_report_v4_content_json,relation_reduction_capsule_v4_content_json,
  options_v4_content_json,version} from './core.mjs';
const MiB=1024*1024;
export const RELATION_REDUCTION_V4_LIMITS=Object.freeze({sourceUtf8Bytes:8*MiB,optionsUtf8Bytes:8192,reportUtf8Bytes:32*MiB,capsuleUtf8Bytes:64*MiB,maxChecks:256,maxStates:100000,maxEdgeChecks:1000000,maxGraphChecks:1000000});
const CATEGORIES=Object.freeze(['G0','G1a','G1b','G1c','G2-item','INT']);
const IDS=Object.freeze({semanticContract:'relation-point-category-transaction-reduction-2',algorithm:'relation-category-single-delete-2',counterContract:'relation-category-candidate-checks-1',profile:'relation-point-category-reduction/v4-2'});
const PREDICATE_IDS=Object.freeze({semanticContract:'relation-predicate-category-transaction-reduction-1',algorithm:'relation-predicate-single-delete-1',counterContract:'relation-predicate-candidate-checks-1',profile:'relation-predicate-category-reduction/v4-1'});
const FORMAT='moontxnwitness-relation-category-replay/v4',OPERATION='relation-category-reduction';
const SCOPE='semantic reproduction under the caller-selected category and budgets; hashes do not authenticate observations';
const hash=text=>createHash('sha256').update(text,'utf8').digest('hex');
function bounded(value,maximum,label){const text=typeof value==='string'?value:JSON.stringify(value);if(typeof text!=='string')throw new TypeError(label+' must be JSON text or a serializable object');if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds '+maximum+' UTF-8 bytes');if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');return text;}
function plain(value){if(value===null||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw new TypeError('relation reduction options must be a plain object');return value;}
function guarded(text,core){const parsed=JSON.parse(core(text));if(parsed.valid!==true)throw new TypeError(parsed.error||'Invalid relation reduction JSON');return parsed.value??parsed.options;}
export function parseRelationReductionOptionsV4(value){return guarded(bounded(value,8192,'relation reduction options'),options_v4_content_json);}
function integer(value,fallback,maximum,label){if(value===undefined)return fallback;if(!Number.isSafeInteger(value)||value<0||value>maximum)throw new RangeError(label+' must be an integer in 0..'+maximum);return value;}
function normalize(value){
  plain(value);
  if(Object.hasOwn(value,'ruleSet')){
    const {maxChecks,...classification}=value;
    return {...normalizeRelationPredicateOptionsV4(classification),maxChecks:integer(maxChecks,256,256,'maxChecks')};
  }
  for(const key of Object.keys(value))if(!['category','maxChecks','maxStates','maxEdgeChecks','maxGraphChecks'].includes(key))throw new TypeError('Unknown relation reduction option: '+key);
  if(!CATEGORIES.includes(value.category))throw new TypeError('category is required: '+CATEGORIES.join(', '));
  return {category:value.category,maxChecks:integer(value.maxChecks,256,256,'maxChecks'),maxStates:integer(value.maxStates,100000,100000,'maxStates'),maxEdgeChecks:integer(value.maxEdgeChecks,1000000,1000000,'maxEdgeChecks'),maxGraphChecks:integer(value.maxGraphChecks,1000000,1000000,'maxGraphChecks')};
}
function prepared(options){if(typeof options!=='string')normalize(options);const text=bounded(options,8192,'relation reduction options');return {text,value:normalize(parseRelationReductionOptionsV4(text))};}
function identity(report){
  const ids=Object.hasOwn(report,'ruleSet')?PREDICATE_IDS:IDS;
  if(ids===PREDICATE_IDS)normalizeRelationPredicateOptionsV4({category:report.preserveCategory,ruleSet:report.ruleSet});
  if(report.format!=='moontxnwitness-relation-category-reduction/v4'||report.schemaVersion!==4||!['point-register-v1','append-list-v1','relation-set-v1'].includes(report.dataModel)||report.semanticContract!==ids.semanticContract||report.algorithm!==ids.algorithm||report.profile!==ids.profile||report.execution?.counterContract!==ids.counterContract||(ids===IDS&&!CATEGORIES.includes(report.preserveCategory)))throw new TypeError('Unsupported relation reduction report identity');
  return ids;
}
function run(sourceText,optionsText){const reportText=bounded(reduce_relation_category_v4_json(sourceText,optionsText),RELATION_REDUCTION_V4_LIMITS.reportUtf8Bytes,'relation reduction report');const report=guarded(reportText,relation_reduction_report_v4_content_json);identity(report);return {reportText,report};}
export function reduceRelationCategoryV4(source,options){const sourceText=bounded(source,RELATION_REDUCTION_V4_LIMITS.sourceUtf8Bytes,'relation reduction source');return run(sourceText,prepared(options).text).report;}
export function verifyRelationCategoryReductionV4(source,report,expectedOptions){try{const sourceText=bounded(source,RELATION_REDUCTION_V4_LIMITS.sourceUtf8Bytes,'relation reduction source'),reportText=bounded(report,RELATION_REDUCTION_V4_LIMITS.reportUtf8Bytes,'relation reduction report');return JSON.parse(verify_relation_category_reduction_v4_json(sourceText,reportText,prepared(expectedOptions).text));}catch(error){return {valid:false,reason:error.message,scope:SCOPE};}}
export function makeRelationCategoryReductionCapsuleV4(source,options){const sourceText=bounded(source,RELATION_REDUCTION_V4_LIMITS.sourceUtf8Bytes,'relation reduction source'),expected=prepared(options),{reportText,report}=run(sourceText,expected.text);return bounded({format:FORMAT,schemaVersion:4,tool:'MoonTxnWitness',producer:{version:version()},operation:OPERATION,...identity(report),sourceText,sourceSha256:hash(sourceText),optionsText:expected.text,optionsSha256:hash(expected.text),reportText,reportSha256:hash(reportText)},RELATION_REDUCTION_V4_LIMITS.capsuleUtf8Bytes,'relation reduction capsule');}
export function replayRelationCategoryReductionCapsuleV4(input,expectedOptions){
  const reject=reason=>({valid:false,reason,scope:SCOPE});
  try{
    const capsule=JSON.parse(relation_reduction_capsule_v4_content_json(bounded(input,RELATION_REDUCTION_V4_LIMITS.capsuleUtf8Bytes,'relation reduction capsule')));
    if(capsule.format!==FORMAT||capsule.operation!==OPERATION)return reject('unsupported-relation-reduction-capsule');
    const independent=prepared(expectedOptions);
    const ids=independent.value.ruleSet===undefined?IDS:PREDICATE_IDS;
    for(const [key,value]of Object.entries(ids))if(capsule[key]!==value)return reject('capsule-'+key+'-mismatch');
    const sourceText=bounded(capsule.sourceText,RELATION_REDUCTION_V4_LIMITS.sourceUtf8Bytes,'relation reduction source');
    const optionsText=bounded(capsule.optionsText,8192,'relation reduction options');
    const reportText=bounded(capsule.reportText,RELATION_REDUCTION_V4_LIMITS.reportUtf8Bytes,'relation reduction report');
    for(const [key,text]of [['source',sourceText],['options',optionsText],['report',reportText]])if(!/^[a-f0-9]{64}$/.test(capsule[key+'Sha256'])||hash(text)!==capsule[key+'Sha256'])return reject(key+'-sha256-mismatch');
    const report=guarded(reportText,relation_reduction_report_v4_content_json);
    if(identity(report)!==ids)return reject('report-reduction-contract-mismatch');
    const original=normalize(parseRelationReductionOptionsV4(optionsText));
    if(JSON.stringify(original)!==JSON.stringify(independent.value))return reject('caller-expected-options-mismatch');
    if(report.preserveCategory!==independent.value.category)return reject('caller-category-mismatch');
    if(report.ruleSet!==independent.value.ruleSet)return reject('caller-rule-set-mismatch');
    const checked=verifyRelationCategoryReductionV4(sourceText,reportText,expectedOptions);
    if(checked.valid!==true)return reject('recomputed-reduction-differs');
    return {valid:true,status:'recomputed',operation:OPERATION,...ids,scope:SCOPE};
  }catch(error){return reject(error.message);}
}
