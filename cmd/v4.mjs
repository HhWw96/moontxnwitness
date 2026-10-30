// Bounded transports for the typed MoonBit v4 API. No compatibility worker is used.
import {createHash} from 'node:crypto';
import {analyze_v4_json, classify_v4_json, reduce_v4_json, verify_v4_json,
  verify_classification_v4_json, verify_reduction_v4_json, capsule_v4_content_json,
  version} from './core.mjs';

const MiB=1024*1024;
export const V4_LIMITS=Object.freeze({sourceUtf8Bytes:8*MiB,optionsUtf8Bytes:8192,
  reportUtf8Bytes:32*MiB,capsuleUtf8Bytes:64*MiB,maxAttempts:100000,maxStates:100000,
  maxOperationChecks:1000000,maxCachedStates:50000,maxEdgeChecks:1000000,maxChecks:256});
const hash=text=>createHash('sha256').update(text,'utf8').digest('hex');
const SCOPE='semantic reproduction under caller-supplied options; source observations are not authenticated';
const analysisDefaults=Object.freeze({maxAttempts:100000,maxStates:100000,maxOperationChecks:1000000,maxCachedStates:50000});
const categoriesDefault=Object.freeze(['G0','G1c','G2-item']);
const operations=Object.freeze({analysis:analyze_v4_json,classification:classify_v4_json,reduction:reduce_v4_json});
const verifiers=Object.freeze({analysis:verify_v4_json,classification:verify_classification_v4_json,reduction:verify_reduction_v4_json});

function bounded(value,maximum,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(label+' must be JSON text or a serializable object');
  if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds '+maximum+' UTF-8 bytes');
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');
  return text;
}
function object(value,label){
  if(value===null||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw new TypeError(label+' must be a plain object');
  return value;
}
function fields(value,allowed,label){
  object(value,label);
  for(const name of Object.keys(value))if(!allowed.includes(name))throw new TypeError('Unknown '+label+' field: '+name);
}
function integer(value,fallback,maximum,label){
  if(value===undefined)return fallback;
  if(!Number.isSafeInteger(value)||value<0||value>maximum)throw new RangeError(label+' must be an integer in 0..'+maximum);
  return value;
}
function normalizedOptions(operation,options){
  if(operation==='analysis'){
    fields(options,Object.keys(analysisDefaults),'analysis options');
    return Object.fromEntries(Object.entries(analysisDefaults).map(([name,maximum])=>
      [name,integer(options[name],maximum,maximum,name)]));
  }
  if(operation==='classification'){
    fields(options,['categories','maxStates','maxEdgeChecks'],'classification options');
    const categories=options.categories===undefined?categoriesDefault:options.categories;
    if(!Array.isArray(categories)||!categories.length||categories.length>3||
      new Set(categories).size!==categories.length||categories.some(c=>!categoriesDefault.includes(c)))
      throw new TypeError('categories must be distinct supported names: G0, G1c, G2-item');
    return {categories:[...categories],maxStates:integer(options.maxStates,100000,100000,'maxStates'),
      maxEdgeChecks:integer(options.maxEdgeChecks,1000000,1000000,'maxEdgeChecks')};
  }
  if(operation==='reduction'){
    fields(options,['preserve','maxChecks','analysisOptions'],'reduction options');
    if(!['serializable','strict-serializable'].includes(options.preserve))
      throw new TypeError('Reduction requires explicit preserve: serializable or strict-serializable');
    return {preserve:options.preserve,maxChecks:integer(options.maxChecks,256,256,'maxChecks'),
      analysisOptions:normalizedOptions('analysis',options.analysisOptions===undefined?{}:options.analysisOptions)};
  }
  throw new TypeError('Unknown v4 operation');
}
function preparedOptions(operation,options){
  normalizedOptions(operation,options);
  return bounded(options,V4_LIMITS.optionsUtf8Bytes,'v4 options');
}
function run(operation,sourceText,optionsText){
  const reportText=bounded(operations[operation](sourceText,optionsText),V4_LIMITS.reportUtf8Bytes,'v4 report');
  return {reportText,report:JSON.parse(reportText)};
}
function analyze(operation,source,options){
  const sourceText=bounded(source,V4_LIMITS.sourceUtf8Bytes,'v4 source');
  return run(operation,sourceText,preparedOptions(operation,options)).report;
}
/** Original v1 declared history or traceSchema 3 capture; no mixed-model input. */
export function analyzeV4(source,options={}){return analyze('analysis',source,options);}
/** Checks only selected G0/G1c/G2-item categories, not full isolation models. */
export function classifyV4(source,options={}){return analyze('classification',source,options);}
/** The preservation model is an explicit caller choice; it is never read from a report. */
export function reduceV4(source,options){return analyze('reduction',source,options);}

function verify(operation,source,report,options){
  try{
    const sourceText=bounded(source,V4_LIMITS.sourceUtf8Bytes,'v4 source');
    const reportText=bounded(report,V4_LIMITS.reportUtf8Bytes,'v4 report');
    return JSON.parse(verifiers[operation](sourceText,reportText,preparedOptions(operation,options)));
  }catch(error){return {valid:false,reason:error.message,scope:SCOPE};}
}
export function verifyV4(source,report,expectedOptions={}){return verify('analysis',source,report,expectedOptions);}
export function verifyClassificationV4(source,report,expectedOptions={}){return verify('classification',source,report,expectedOptions);}
export function verifyReductionV4(source,report,expectedOptions){return verify('reduction',source,report,expectedOptions);}

function identities(operation,report){
  const counters={'point-register-v1':'bounded-register-v2.1-counters','append-list-v1':'v3-list-1-counters','relation-set-v1':'v3-relation-1-counters'};
  const expected={analysis:['moontxnwitness-analysis/v4','moontxnwitness-history-analysis-v4-1','typed-snapshot-analysis-1',counters[report.dataModel]],
    classification:['moontxnwitness-classification/v4','moontxnwitness-category-classification-v4-1','v4-source-bound-category-bfs-1','v4-category-seed-bfs-counters-1'],
    reduction:['moontxnwitness-reduction/v4','moontxnwitness-history-analysis-v4-1','v4-fixed-model-refutation-reduction-1','v4-model-reduction-checks-1']}[operation];
  if(!expected||!Object.hasOwn(counters,report.dataModel)||report.schemaVersion!==4||report.format!==expected[0]||
     report.semanticContract!==expected[1]||report.algorithm!==expected[2]||report.execution?.counterContract!==expected[3])
    throw new TypeError('Unsupported v4 report semantic, algorithm or counter contract');
  return {semanticContract:expected[1],algorithm:expected[2],counterContract:expected[3]};
}
function make(operation,source,options){
  const sourceText=bounded(source,V4_LIMITS.sourceUtf8Bytes,'v4 source');
  const optionsText=preparedOptions(operation,options);
  const {reportText,report}=run(operation,sourceText,optionsText);
  const ids=identities(operation,report);
  return bounded({format:'moontxnwitness-replay/v4',schemaVersion:4,tool:'MoonTxnWitness',
    producer:{version:version()},operation,...ids,sourceText,sourceSha256:hash(sourceText),
    optionsText,optionsSha256:hash(optionsText),reportText,reportSha256:hash(reportText)},
    V4_LIMITS.capsuleUtf8Bytes,'v4 capsule');
}
/** Preserves the exact source and serialized requested options and core report. */
export function makeCapsuleV4(source,options={}){return make('analysis',source,options);}
export function makeClassificationCapsuleV4(source,options={}){return make('classification',source,options);}
export function makeReductionCapsuleV4(source,options){return make('reduction',source,options);}

/**
 * Replay uses independent expectedOptions. With no argument, analysis/classification
 * use fixed defaults. Reductions always require an explicit preservation target.
 * SHA-256 detects alteration; it does not authenticate who observed the source.
 */
export function replayCapsuleV4(input,expectedOptions){
  const reject=reason=>({valid:false,reason,scope:SCOPE});
  try{
    const inputText=bounded(input,V4_LIMITS.capsuleUtf8Bytes,'v4 capsule');
    // MoonBit rejects duplicate keys and excessive depth before host inspection.
    const capsule=JSON.parse(capsule_v4_content_json(inputText));
    if(capsule.format!=='moontxnwitness-replay/v4')return reject('invalid-v4-capsule-envelope');
    if(!Object.hasOwn(operations,capsule.operation))return reject('unsupported-v4-operation');
    const sourceText=bounded(capsule.sourceText,V4_LIMITS.sourceUtf8Bytes,'v4 source');
    const optionsText=bounded(capsule.optionsText,V4_LIMITS.optionsUtf8Bytes,'v4 options');
    const reportText=bounded(capsule.reportText,V4_LIMITS.reportUtf8Bytes,'v4 report');
    for(const [name,text] of [['source',sourceText],['options',optionsText],['report',reportText]])
      if(!/^[a-f0-9]{64}$/.test(capsule[name+'Sha256'])||hash(text)!==capsule[name+'Sha256'])return reject(name+'-sha256-mismatch');
    const report=JSON.parse(reportText),ids=identities(capsule.operation,report);
    for(const name of Object.keys(ids))if(capsule[name]!==ids[name])return reject('capsule-report-'+name+'-mismatch');
    const expected=expectedOptions===undefined?{}:expectedOptions;
    const requested=normalizedOptions(capsule.operation,JSON.parse(optionsText));
    const independent=normalizedOptions(capsule.operation,expected);
    if(JSON.stringify(requested)!==JSON.stringify(independent))return reject('caller-expected-options-mismatch');
    const checked=verify(capsule.operation,sourceText,reportText,expected);
    if(checked.valid!==true)return reject('recomputed-v4-report-differs');
    return {valid:true,schemaVersion:4,status:'recomputed',operation:capsule.operation,...ids,
      producer:capsule.producer,scope:SCOPE};
  }catch(error){return reject(error.message);}
}
