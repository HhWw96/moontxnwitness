// Independent relation categories and raw-source rules. Existing v4 APIs are unchanged.
import {createHash} from 'node:crypto';
import {classify_relation_v4_json,verify_relation_classification_v4_json,
  classify_relation_predicate_v4_json,verify_relation_predicate_classification_v4_json,
  inspect_capture_anomalies_v4_json,verify_capture_anomalies_v4_json,
  inspect_internal_consistency_v4_json,verify_internal_consistency_v4_json,
  source_rules_report_v4_content_json,source_rules_capsule_v4_content_json,
  options_v4_content_json,version} from './core.mjs';
const MiB=1024*1024;
export const SOURCE_RULES_V4_LIMITS=Object.freeze({sourceUtf8Bytes:8*MiB,optionsUtf8Bytes:8192,reportUtf8Bytes:32*MiB,capsuleUtf8Bytes:64*MiB,maxStates:100000,maxEdgeChecks:1000000,maxGraphChecks:1000000,maxChecks:1000000});
const SCOPE='semantic reproduction under caller-supplied options; source observations are not authenticated';
const FORMAT='moontxnwitness-source-rules-replay/v4';
const categories=Object.freeze(['G0','G1a','G1b','G1c','G2-item','INT']);
const predicateCategories=Object.freeze(['G0','G1c','G2-item','G2','G-single-item','G-single','G-nonadjacent']);
const predicateRules=Object.freeze(['adya-2000-scoped-categories-v1','elle-4e359e5-scoped-categories-v1']);
const definitions=Object.freeze({
  'relation-predicate-classification':Object.freeze({run:classify_relation_predicate_v4_json,verify:verify_relation_predicate_classification_v4_json,format:'moontxnwitness-relation-predicate-category/v4',semanticContract:'relation-predicate-category-on-keyslots-v1',algorithm:'relation-predicate-scoped-category-2',counterContract:'relation-predicate-category-composite-counters-1',profile:'relation-predicate-categories/v4-1'}),
  'relation-classification':Object.freeze({run:classify_relation_v4_json,verify:verify_relation_classification_v4_json,format:'moontxnwitness-relation-classification/v4',semanticContract:'moontxnwitness-relation-point-category-classification-v4-5',algorithm:'v4-relation-point-category-5',counterContract:'v4-relation-point-category-counters-5',profile:'relation-point-categories/v4-5'}),
  'capture-anomalies':Object.freeze({run:inspect_capture_anomalies_v4_json,verify:verify_capture_anomalies_v4_json,format:'moontxnwitness-captured-source-anomalies/v4',semanticContract:'moontxnwitness-captured-source-anomalies-v4-2',algorithm:'v4-capture-effective-source-anomalies-2',counterContract:'v4-capture-source-reference-checks-2',profile:'raw-capture-source-anomalies/v2'}),
  'internal-consistency':Object.freeze({run:inspect_internal_consistency_v4_json,verify:verify_internal_consistency_v4_json,format:'moontxnwitness-internal-consistency/v4',semanticContract:'moontxnwitness-internal-consistency-v4-2',algorithm:'v4-effective-overlay-internal-consistency-2',counterContract:'v4-internal-overlay-reference-checks-2',profile:'captured-formal-int/v2'}),
});
const hash=text=>createHash('sha256').update(text,'utf8').digest('hex');
function bounded(value,maximum,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(label+' must be JSON text or a serializable object');
  if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds '+maximum+' UTF-8 bytes');
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');
  return text;
}
function plain(value,label){
  if(value===null||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw new TypeError(label+' must be a plain object');
  return value;
}
function guarded(text,core,label){
  const result=JSON.parse(core(text));
  if(result.valid!==true)throw new TypeError(result.error||'Invalid '+label);
  return result.value??result.options;
}
export function parseSourceRulesOptionsV4(input){
  return guarded(bounded(input,SOURCE_RULES_V4_LIMITS.optionsUtf8Bytes,'source rules options'),options_v4_content_json,'source rules options');
}
function integer(value,fallback,maximum,label){
  if(value===undefined)return fallback;
  if(!Number.isSafeInteger(value)||value<0||value>maximum)throw new RangeError(label+' must be an integer in 0..'+maximum);
  return value;
}
function normalize(operation,value){
  plain(value,'source rules options');
  if(operation==='relation-predicate-classification'){
    const allowed=['category','ruleSet','maxGraphChecks','maxPredicateChecks','maxCandidateVisits','maxStates','maxEdgeChecks'];
    for(const key of Object.keys(value))if(!allowed.includes(key))throw new TypeError('Unknown relation predicate option: '+key);
    if(!predicateCategories.includes(value.category))throw new TypeError('category must explicitly select '+predicateCategories.join(', '));
    if(!predicateRules.includes(value.ruleSet))throw new TypeError('ruleSet must explicitly select '+predicateRules.join(', '));
    return {category:value.category,ruleSet:value.ruleSet,maxGraphChecks:integer(value.maxGraphChecks,1000000,1000000,'maxGraphChecks'),maxPredicateChecks:integer(value.maxPredicateChecks,1000000,1000000,'maxPredicateChecks'),maxCandidateVisits:integer(value.maxCandidateVisits,100000,100000,'maxCandidateVisits'),maxStates:integer(value.maxStates,100000,100000,'maxStates'),maxEdgeChecks:integer(value.maxEdgeChecks,1000000,1000000,'maxEdgeChecks')};
  }
  const relation=operation==='relation-classification',allowed=relation?['categories','maxStates','maxEdgeChecks','maxGraphChecks']:['maxChecks'];
  for(const key of Object.keys(value))if(!allowed.includes(key))throw new TypeError('Unknown source rules option: '+key);
  if(!relation)return {maxChecks:integer(value.maxChecks,1000000,1000000,'maxChecks')};
  const chosen=value.categories===undefined?categories:value.categories;
  if(!Array.isArray(chosen)||!chosen.length||chosen.length>6||new Set(chosen).size!==chosen.length||chosen.some(c=>!categories.includes(c)))throw new TypeError('categories must be distinct relation rule names: '+categories.join(', '));
  return {categories:[...chosen],maxStates:integer(value.maxStates,100000,100000,'maxStates'),maxEdgeChecks:integer(value.maxEdgeChecks,1000000,1000000,'maxEdgeChecks'),maxGraphChecks:integer(value.maxGraphChecks,1000000,1000000,'maxGraphChecks')};
}
function prepared(operation,options){
  if(typeof options!=='string')normalize(operation,options);
  const optionsText=bounded(options,SOURCE_RULES_V4_LIMITS.optionsUtf8Bytes,'source rules options');
  const parsed=parseSourceRulesOptionsV4(optionsText);
  return {optionsText,normalized:normalize(operation,parsed)};
}
function identity(operation,report){
  const def=definitions[operation];
  if(!def||!['point-register-v1','append-list-v1','relation-set-v1'].includes(report.dataModel)||report.schemaVersion!==4||report.format!==def.format||report.semanticContract!==def.semanticContract||report.algorithm!==def.algorithm||report.execution?.counterContract!==def.counterContract||(operation!=='relation-classification'&&report.profile!==def.profile))throw new TypeError('Unsupported source rules report format, model, semantic, algorithm, profile or counter contract');
  return {semanticContract:def.semanticContract,algorithm:def.algorithm,counterContract:def.counterContract,profile:def.profile};
}
function run(operation,sourceText,optionsText){
  const reportText=bounded(definitions[operation].run(sourceText,optionsText),SOURCE_RULES_V4_LIMITS.reportUtf8Bytes,'source rules report');
  return {reportText,report:JSON.parse(reportText)};
}
function inspect(operation,source,options){
  const sourceText=bounded(source,SOURCE_RULES_V4_LIMITS.sourceUtf8Bytes,'source rules source');
  return run(operation,sourceText,prepared(operation,options).optionsText).report;
}
export function classifyRelationPredicateV4(source,options){return inspect('relation-predicate-classification',source,options);}
export function classifyRelationV4(source,options={}){return inspect('relation-classification',source,options);}
export function inspectCaptureAnomaliesV4(source,options={}){return inspect('capture-anomalies',source,options);}
export function inspectInternalConsistencyV4(source,options={}){return inspect('internal-consistency',source,options);}
function verify(operation,source,report,expectedOptions){
  try{
    const sourceText=bounded(source,SOURCE_RULES_V4_LIMITS.sourceUtf8Bytes,'source rules source');
    const reportText=bounded(report,SOURCE_RULES_V4_LIMITS.reportUtf8Bytes,'source rules report');
    return JSON.parse(definitions[operation].verify(sourceText,reportText,prepared(operation,expectedOptions).optionsText));
  }catch(error){return {valid:false,reason:error.message,scope:SCOPE};}
}
export function verifyRelationPredicateClassificationV4(source,report,expectedOptions){return verify('relation-predicate-classification',source,report,expectedOptions);}
export function verifyRelationClassificationV4(source,report,expectedOptions={}){return verify('relation-classification',source,report,expectedOptions);}
export function verifyCaptureAnomaliesV4(source,report,expectedOptions={}){return verify('capture-anomalies',source,report,expectedOptions);}
export function verifyInternalConsistencyV4(source,report,expectedOptions={}){return verify('internal-consistency',source,report,expectedOptions);}
function make(operation,source,options){
  const sourceText=bounded(source,SOURCE_RULES_V4_LIMITS.sourceUtf8Bytes,'source rules source');
  const {optionsText}=prepared(operation,options),{reportText,report}=run(operation,sourceText,optionsText);
  return bounded({format:FORMAT,schemaVersion:4,tool:'MoonTxnWitness',producer:{version:version()},operation,...identity(operation,report),sourceText,sourceSha256:hash(sourceText),optionsText,optionsSha256:hash(optionsText),reportText,reportSha256:hash(reportText)},SOURCE_RULES_V4_LIMITS.capsuleUtf8Bytes,'source rules capsule');
}
export function makeRelationPredicateClassificationCapsuleV4(source,options){return make('relation-predicate-classification',source,options);}
export function makeRelationClassificationCapsuleV4(source,options={}){return make('relation-classification',source,options);}
export function makeCaptureAnomaliesCapsuleV4(source,options={}){return make('capture-anomalies',source,options);}
export function makeInternalConsistencyCapsuleV4(source,options={}){return make('internal-consistency',source,options);}
/** Replay reproduces semantics; hashes do not authenticate the original observer. */
export function replayRelationCapsuleV4(input,expectedOptions={}){
  const reject=reason=>({valid:false,reason,scope:SCOPE});
  try{
    const capsule=JSON.parse(source_rules_capsule_v4_content_json(bounded(input,SOURCE_RULES_V4_LIMITS.capsuleUtf8Bytes,'source rules capsule')));
    if(capsule.format!==FORMAT||!Object.hasOwn(definitions,capsule.operation))return reject('unsupported-source-rules-capsule');
    const sourceText=bounded(capsule.sourceText,SOURCE_RULES_V4_LIMITS.sourceUtf8Bytes,'source rules source');
    const optionsText=bounded(capsule.optionsText,SOURCE_RULES_V4_LIMITS.optionsUtf8Bytes,'source rules options');
    const reportText=bounded(capsule.reportText,SOURCE_RULES_V4_LIMITS.reportUtf8Bytes,'source rules report');
    for(const [name,text]of [['source',sourceText],['options',optionsText],['report',reportText]])if(!/^[a-f0-9]{64}$/.test(capsule[name+'Sha256'])||capsule[name+'Sha256']!==hash(text))return reject(name+'-sha256-mismatch');
    const report=guarded(reportText,source_rules_report_v4_content_json,'source rules report'),ids=identity(capsule.operation,report);
    for(const key of Object.keys(ids))if(capsule[key]!==ids[key])return reject('capsule-report-'+key+'-mismatch');
    const requested=normalize(capsule.operation,parseSourceRulesOptionsV4(optionsText));
    const independent=prepared(capsule.operation,expectedOptions);
    if(JSON.stringify(requested)!==JSON.stringify(independent.normalized))return reject('caller-expected-options-mismatch');
    const checked=verify(capsule.operation,sourceText,reportText,expectedOptions);
    if(checked.valid!==true)return reject('recomputed-source-rules-report-differs');
    return {valid:true,schemaVersion:4,status:'recomputed',operation:capsule.operation,...ids,producer:capsule.producer,scope:SCOPE};
  }catch(error){return reject(error.message);}
}
