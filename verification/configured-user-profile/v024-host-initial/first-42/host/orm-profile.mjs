// Explicit configured profile. Generic diagnostics and prior capsules are unchanged.
import {createHash} from 'node:crypto';
import {orm_profile_source_v3_json, shrink_options_json, analyze_options_json, replay_report_json, version} from './core.mjs';

const PROFILE='fastapi-users-sqlalchemy-7.0.0-pg18/1';
const ALGORITHM='orm-profile-host-1';
const SOURCE_ALGORITHM='v3-orm-profile-source-promotion-1';
const MiB=1024*1024;
const BUDGETS=Object.freeze({sourceEnvelopeUtf8Bytes:64*MiB,traceUtf8Bytes:8*MiB,
  sourceJournalUtf8Bytes:16*MiB,lifecycleUtf8Bytes:8*MiB,journalIndexUtf8Bytes:2*MiB,
  optionsUtf8Bytes:4096,reportUtf8Bytes:64*MiB,capsuleUtf8Bytes:128*MiB,
  exactSearchTransactions:12,exactSearchOperations:512,exactSearchKeys:128,
  reductionTransactions:512,reductionOperations:10000,reductionCandidateChecks:256});
const hash=text=>createHash('sha256').update(text,'utf8').digest('hex');
const canonical=value=>JSON.stringify(value,null,2)+'\n';
const scope=()=>({configuredBaseUserPointCrudOnly:true,rawDiagnosticsRemainPartial:true,
  actualDatabaseExecution:false,databaseAuthenticityVerified:false,
  eventSegmentPayloadsRehashed:false,completeAuthenticationSystem:false,
  arbitrarySqlSupported:false,realTimeOrderInferred:false});
function bounded(value,limit,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(`${label} must be JSON text or an object`);
  if(Buffer.byteLength(text,'utf8')>limit)throw new RangeError(`${label} exceeds ${limit} UTF-8 bytes`);
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(`${label} is not well-formed Unicode`);
  return text;
}
function object(value,label){
  if(value===null||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value)))throw new TypeError(`${label} must be a plain object`);
  return value;
}
function analysisOptions(options){
  object(options,'analysis options');
  const maxima={maxAttempts:100000,maxOperationChecks:1000000,maxCachedStates:50000};
  for(const name of Object.keys(options)){
    if(!Object.hasOwn(maxima,name)||!Number.isSafeInteger(options[name])||options[name]<0||options[name]>maxima[name])throw new RangeError(`Unsupported analysis budget: ${name}`);
  }
  return options;
}
function optionsText(options,operation){
  if(operation==='analyze')analysisOptions(options);
  else {
    object(options,'reduction options');
    for(const name of Object.keys(options))if(!['maxChecks','analysisOptions'].includes(name))throw new TypeError(`Unsupported reduction option: ${name}`);
    if(Object.hasOwn(options,'maxChecks')&&(!Number.isSafeInteger(options.maxChecks)||options.maxChecks<0||options.maxChecks>256))throw new RangeError('maxChecks must be in 0..256');
    if(Object.hasOwn(options,'analysisOptions'))analysisOptions(options.analysisOptions);
  }
  return bounded(options,BUDGETS.optionsUtf8Bytes,'profile options');
}
function sourceBindings(envelopeText){
  const bindings={envelopeSha256:hash(envelopeText),traceSha256:null,sourceJournalSha256:null,lifecycleSha256:null,journalIndexSha256:null};
  let parsed;try{parsed=JSON.parse(envelopeText);}catch{return bindings;}
  for(const [name,limit] of [['trace',BUDGETS.traceUtf8Bytes],['sourceJournal',BUDGETS.sourceJournalUtf8Bytes],['lifecycle',BUDGETS.lifecycleUtf8Bytes],['journalIndex',BUDGETS.journalIndexUtf8Bytes]]){
    const text=parsed?.[name+'Text'];
    if(typeof text==='string')bindings[name+'Sha256']=hash(bounded(text,limit,'original '+name));
  }
  return bindings;
}
function promote(envelopeText,requestOptionsText){
  const result=JSON.parse(orm_profile_source_v3_json(envelopeText,requestOptionsText));
  if(result.algorithm!==SOURCE_ALGORITHM||result.version!==version())throw new Error('Unsupported profile core algorithm/engine');
  return result;
}
function report(operation,envelopeText,requestOptionsText,result){
  const bindings=sourceBindings(envelopeText);
  const promoted=operation==='analyze'?result:result.originalReport;
  if(promoted.analysisCoverageAccepted===true){
    for(const name of ['trace','sourceJournal','lifecycle','journalIndex'])if(promoted.sourceBindings?.[name+'Sha256']!==bindings[name+'Sha256'])throw new Error('Core and host original-source binding differ');
  }
  const value={format:'moontxnwitness-orm-profile-report/v1',schemaVersion:1,tool:'MoonTxnWitness',
    engineVersion:version(),algorithm:ALGORITHM,sourceAlgorithm:SOURCE_ALGORITHM,
    profile:PROFILE,operation,status:result.status,
    analysisCoverageAccepted:operation==='analyze'?result.analysisCoverageAccepted===true:result.originalReport.analysisCoverageAccepted===true,
    requestOptionsText,sourceBindings:bindings,budgets:{...BUDGETS},result,scope:scope()};
  bounded(value,BUDGETS.reportUtf8Bytes,'profile report');return value;
}

/** Recompute this explicitly installed engine-only profile; never upgrades generic diagnostics. */
export function analyzeOrmProfileV3(envelope,options={}){
  const text=bounded(envelope,BUDGETS.sourceEnvelopeUtf8Bytes,'profile source envelope');
  const requested=optionsText(options,'analyze');sourceBindings(text);
  return report('analyze',text,requested,promote(text,requested));
}

const equal=(a,b)=>{
  if(a===b)return true;
  if(a===null||b===null||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;
  const ka=Object.keys(a),kb=Object.keys(b);
  return ka.length===kb.length&&ka.every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k]));
};
function isOriginalPruning(original,reduced){
  if(!reduced||reduced.model!==original.model||!equal(reduced.initial,original.initial)||!Array.isArray(reduced.transactions))return false;
  let cursor=0;
  for(const tx of reduced.transactions){
    while(cursor<original.transactions.length&&original.transactions[cursor].id!==tx.id)cursor++;
    if(cursor===original.transactions.length||!equal(tx,original.transactions[cursor++]))return false;
  }
  if(!reduced.versionOrders||typeof reduced.versionOrders!=='object'||Array.isArray(reduced.versionOrders))return false;
  for(const [key,values] of Object.entries(reduced.versionOrders)){
    const source=original.versionOrders?.[key];if(!Array.isArray(source)||!Array.isArray(values))return false;
    let at=0;for(const value of values){while(at<source.length&&source[at]!==value)at++;if(at===source.length)return false;at++;}
  }
  return true;
}

/** Delete transactions only from independently promoted original facts. */
export function reduceOrmProfileV3(envelope,options={}){
  const text=bounded(envelope,BUDGETS.sourceEnvelopeUtf8Bytes,'profile source envelope');
  const requested=optionsText(options,'reduce');sourceBindings(text);
  const analysisRequested=JSON.stringify(options.analysisOptions??{});
  const original=promote(text,analysisRequested);
  const result={status:'inconclusive',reason:'Configured source mapping or definite anomaly not proven.',
    originalEnvelopeText:text,originalReport:original,retainedOriginalSeq:original.retainedOriginalSeq??[],
    originalHistorySha256:original.history?hash(JSON.stringify(original.history)):null,
    reduction:null,finalReplay:null,finalReanalysis:null,
    scope:'Only transaction deletion from the independently derived ORIGINAL history; original observations and source window are retained unchanged.'};
  if(original.analysisCoverageAccepted!==true||original.mappingCoverage?.complete!==true||!original.history||original.status==='inconclusive')return report('reduce',text,requested,result);
  if(original.status!=='violation'){
    result.status='skipped';result.reason='No definite violation in the original verified source history.';
    return report('reduce',text,requested,result);
  }
  const reduction=JSON.parse(shrink_options_json(JSON.stringify(original.history),requested));
  if(!reduction.reducedHistory||!reduction.report||!isOriginalPruning(original.history,reduction.reducedHistory))throw new Error('Reduction does not preserve original derived facts');
  const mini=JSON.stringify(reduction.reducedHistory);
  const replay=JSON.parse(replay_report_json(mini,JSON.stringify(reduction.report)));
  const final=JSON.parse(analyze_options_json(mini,analysisRequested));
  if(replay.valid!==true||final.status!=='violation'||reduction.report.status!=='violation')throw new Error('Reduced original facts do not replay a definite anomaly');
  result.status=reduction.status;result.reason=reduction.reason;result.reduction=reduction;
  result.finalReplay=replay;result.finalReanalysis=final;
  return report('reduce',text,requested,result);
}

function recompute(operation,envelope,options){
  if(operation==='analyze')return analyzeOrmProfileV3(envelope,options);
  if(operation==='reduce')return reduceOrmProfileV3(envelope,options);
  throw new TypeError('Unsupported profile operation');
}
/** Exact host/core recomputation, including options, budgets, source hashes and counters. */
export function verifyOrmProfileV3(envelope,supplied,options){
  const reject=reason=>({valid:false,reason,scope:scope()});
  try{
    const text=bounded(supplied,BUDGETS.reportUtf8Bytes,'profile report');const parsed=JSON.parse(text);
    if(parsed?.format!=='moontxnwitness-orm-profile-report/v1'||parsed.engineVersion!==version()||parsed.algorithm!==ALGORITHM||parsed.sourceAlgorithm!==SOURCE_ALGORITHM||typeof parsed.requestOptionsText!=='string')return reject('unsupported-profile-report-header');
    const requested=options??JSON.parse(parsed.requestOptionsText);
    const expected=recompute(parsed.operation,envelope,requested);
    if(typeof supplied==='string'&&text!==JSON.stringify(expected)&&text!==canonical(expected))return reject('profile-report-is-not-exact-recomputation');
    if(JSON.stringify(parsed)!==JSON.stringify(expected))return reject('profile-report-is-not-exact-recomputation');
    return {valid:true,status:expected.status,analysisCoverageAccepted:expected.analysisCoverageAccepted,
      sourceBindings:expected.sourceBindings,scope:scope()};
  }catch(error){return reject('profile-report-recomputation-failed: '+error.message);}
}

function capsuleFields(operation,envelopeText,requestOptionsText,reportText){
  return {format:'moontxnwitness-orm-profile/v1',schemaVersion:1,tool:'MoonTxnWitness',
    engineVersion:version(),algorithm:ALGORITHM,sourceAlgorithm:SOURCE_ALGORITHM,profile:PROFILE,operation,
    budgets:{...BUDGETS},requestOptionsText,requestOptionsSha256:hash(requestOptionsText),
    envelopeText,sourceBindings:sourceBindings(envelopeText),reportText,reportSha256:hash(reportText)};
}
function makeCapsule(operation,envelope,options){
  const envelopeText=bounded(envelope,BUDGETS.sourceEnvelopeUtf8Bytes,'profile source envelope');
  const requested=optionsText(options,operation);const expected=recompute(operation,envelopeText,options);
  return bounded(canonical(capsuleFields(operation,envelopeText,requested,JSON.stringify(expected))),BUDGETS.capsuleUtf8Bytes,'profile capsule');
}
export const makeOrmProfileCapsuleV3=(envelope,options={})=>makeCapsule('analyze',envelope,options);
export const makeOrmProfileReductionCapsuleV3=(envelope,options={})=>makeCapsule('reduce',envelope,options);

/** Canonical capsule check and current-engine exact recomputation; preserves unknown outcomes. */
export function replayOrmProfileCapsuleV3(text){
  const reject=reason=>({valid:false,reason,scope:scope()});
  try{
    if(typeof text!=='string')return reject('profile-capsule-must-be-text');
    bounded(text,BUDGETS.capsuleUtf8Bytes,'profile capsule');const value=JSON.parse(text);
    if(value?.format!=='moontxnwitness-orm-profile/v1'||value.schemaVersion!==1||value.tool!=='MoonTxnWitness'||
       value.engineVersion!==version()||value.algorithm!==ALGORITHM||value.sourceAlgorithm!==SOURCE_ALGORITHM||
       value.profile!==PROFILE||!['analyze','reduce'].includes(value.operation)||typeof value.envelopeText!=='string'||
       typeof value.reportText!=='string'||typeof value.requestOptionsText!=='string')return reject('unsupported-profile-capsule-header');
    bounded(value.envelopeText,BUDGETS.sourceEnvelopeUtf8Bytes,'profile source envelope');
    bounded(value.reportText,BUDGETS.reportUtf8Bytes,'profile report');
    const requested=JSON.parse(bounded(value.requestOptionsText,BUDGETS.optionsUtf8Bytes,'profile options'));
    if(optionsText(requested,value.operation)!==value.requestOptionsText)return reject('profile-options-not-canonical');
    const expectedFields=capsuleFields(value.operation,value.envelopeText,value.requestOptionsText,value.reportText);
    if(text!==canonical(expectedFields))return reject('profile-envelope-or-digest-mismatch');
    const expected=recompute(value.operation,value.envelopeText,requested);
    if(JSON.stringify(expected)!==value.reportText)return reject('profile-result-does-not-reproduce');
    return {valid:true,status:expected.status,analysisCoverageAccepted:expected.analysisCoverageAccepted,
      engineVersion:version(),envelopeText:value.envelopeText,sourceBindings:expected.sourceBindings,report:expected,scope:scope()};
  }catch(error){return reject('profile-capsule-recomputation-failed: '+error.message);}
}
