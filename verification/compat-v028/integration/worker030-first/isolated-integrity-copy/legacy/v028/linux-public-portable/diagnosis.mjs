// Independent diagnostic aggregation. Existing core judgments and model definitions are preserved.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {isDeepStrictEqual} from 'node:util';
import {analyze_v3_json,verify_v3_json,version} from './core.mjs';
import {classifyModelsV3,verifyModelsClassificationV3} from './classification-models.mjs';

const MiB=1024*1024,ALGORITHM='diagnosis-host-1';
const BUDGETS=Object.freeze({rawTraceUtf8Bytes:8*MiB,optionsUtf8Bytes:16384,
  analysisOptionsUtf8Bytes:4096,modelOptionsUtf8Bytes:8192,analysisReportUtf8Bytes:32*MiB,
  modelReportUtf8Bytes:96*MiB,reportUtf8Bytes:160*MiB});
const hash=value=>createHash('sha256').update(value).digest('hex');
const canonical=value=>JSON.stringify(value,null,2)+'\n';
const ENGINE=Object.freeze({version:version(),coreSha256:hash(readFileSync(new URL('./core.mjs',import.meta.url))),
  captureCoreSha256:hash(readFileSync(new URL('./capture-core.mjs',import.meta.url))),
  modelHostSha256:hash(readFileSync(new URL('./classification-models.mjs',import.meta.url))),
  hostSha256:hash(readFileSync(new URL(import.meta.url)))});
const scope=()=>({diagnosticOnly:true,rawV3TraceOnly:true,aggregateDoesNotGrantCaptureCoverage:true,
  formalModelResultsRemainSeparate:true,internalConsistencyIsNotG2:true,realTimeOrderInferred:false,
  sourceAuthenticityVerified:false,databaseWideCertification:false,actualDatabaseExecution:false,
  oldAnalysisAndClassificationMeaningChanged:false,capsuleSupported:false});
function bounded(value,maximum,label){
  const text=typeof value==='string'?value:JSON.stringify(value);
  if(typeof text!=='string')throw new TypeError(label+' must be JSON text or a serializable value');
  if(Buffer.byteLength(text,'utf8')>maximum)throw new RangeError(label+' exceeds its explicit UTF-8 budget');
  if(Buffer.from(text,'utf8').toString('utf8')!==text)throw new TypeError(label+' contains malformed Unicode');
  return text;
}
function safeJson(value,label,seen=new Set()){
  if(value===null||typeof value==='string'||typeof value==='boolean')return;
  if(typeof value==='number'&&Number.isFinite(value))return;
  if(typeof value!=='object'||seen.has(value))throw new TypeError(label+' must contain finite JSON values without cycles');
  const array=Array.isArray(value),proto=Object.getPrototypeOf(value);
  if((array?proto!==Array.prototype:proto!==Object.prototype&&proto!==null)||Object.getOwnPropertySymbols(value).length)
    throw new TypeError(label+' must contain only plain JSON objects and arrays');
  const descriptors=Object.getOwnPropertyDescriptors(value);
  if(Object.values(descriptors).some(d=>d.get||d.set))throw new TypeError(label+' must not contain accessors');
  if(array&&(Object.keys(value).length!==value.length||Object.keys(value).some((key,i)=>key!==String(i))))
    throw new TypeError(label+' must not contain sparse arrays or extra array fields');
  seen.add(value);for(const key of Object.keys(value))safeJson(descriptors[key].value,label,seen);seen.delete(value);
}
function plain(value,label){
  if(value===null||typeof value!=='object'||Array.isArray(value))throw new TypeError(label+' must be a plain JSON object');
  safeJson(value,label);
}
function optionsText(options){
  plain(options,'Diagnosis options');
  for(const key of Object.keys(options))if(!['analysisOptions','modelOptions'].includes(key))throw new RangeError('Unsupported diagnosis option: '+key);
  for(const name of ['analysisOptions','modelOptions'])if(Object.hasOwn(options,name))plain(options[name],name);
  const text=bounded(options,BUDGETS.optionsUtf8Bytes,'diagnosis options'),copy=JSON.parse(text);
  bounded(copy.analysisOptions??{},BUDGETS.analysisOptionsUtf8Bytes,'analysis options');
  bounded(copy.modelOptions??{},BUDGETS.modelOptionsUtf8Bytes,'model options');
  return text;
}
function sourceText(source){
  if(typeof source!=='string')safeJson(source,'Diagnosis source');
  const text=bounded(source,BUDGETS.rawTraceUtf8Bytes,'diagnosis raw trace');
  const parsed=JSON.parse(text);
  if(parsed===null||typeof parsed!=='object'||Array.isArray(parsed)||parsed.traceSchema!==3||Object.hasOwn(parsed,'format'))
    throw new TypeError('Diagnosis requires a raw traceSchema 3 capture, not a source envelope');
  return text;
}
function ruleFindings(models){
  const result=[];
  for(const [rule,value] of Object.entries(models.result?.rules??{})){
    if(value?.status==='refuted'&&value.evidence!==null&&value.evidence!==undefined)
      result.push({kind:'formal-rule-refutation',rule,reason:value.reason,evidencePath:['models','result','rules',rule,'evidence'],evidence:value.evidence});
  }
  return result;
}
/** Combine unchanged serial analysis and explicit model checks; coverage gaps remain visible. */
export function diagnoseV3(source,options={}){
  const traceText=sourceText(source),requested=optionsText(options),copy=JSON.parse(requested);
  const analysisOptions=copy.analysisOptions??{},modelOptions=copy.modelOptions??{};
  const analysisOptionsText=JSON.stringify(analysisOptions),modelOptionsText=JSON.stringify(modelOptions);
  const analysisText=bounded(analyze_v3_json(traceText,analysisOptionsText),BUDGETS.analysisReportUtf8Bytes,'serial analysis report');
  const analysis=JSON.parse(analysisText),analysisVerification=JSON.parse(verify_v3_json(traceText,analysisText));
  if(analysisVerification.valid!==true)throw new Error('Serial analysis report failed exact verification');
  const models=classifyModelsV3(traceText,modelOptions);
  bounded(models,BUDGETS.modelReportUtf8Bytes,'model classification report');
  const modelVerification=verifyModelsClassificationV3(traceText,models,modelOptions);
  if(modelVerification.valid!==true)throw new Error('Model classification report failed exact verification');
  const findings=ruleFindings(models),serialViolation=analysis.status==='violation';
  const analysisComplete=['consistent','violation'].includes(analysis.status);
  const selectedModels=Object.values(models.result?.models??{});
  const requestedModelVerdictsDeterminate=selectedModels.length>0&&selectedModels.every(m=>['checked-compatible','refuted'].includes(m.status));
  const requestedModelsComplete=requestedModelVerdictsDeterminate&&selectedModels.every(m=>
    Array.isArray(m.incompleteRules)&&m.incompleteRules.length===0&&Array.isArray(m.unsupportedRules)&&m.unsupportedRules.length===0&&
    !['unknown','not-satisfied'].includes(m.internalValidity?.status));
  const status=serialViolation||findings.length?'findings':analysis.status==='invalid'||models.status==='invalid'?'invalid':
    analysisComplete&&requestedModelsComplete?'no-findings':'inconclusive';
  const report={format:'moontxnwitness-diagnosis-report/v1',schemaVersion:1,tool:'MoonTxnWitness',algorithm:ALGORITHM,
    engine:{...ENGINE},status,requestOptionsText:requested,analysisOptionsText,modelOptionsText,
    sourceBindings:{traceSha256:hash(traceText),traceUtf8Bytes:Buffer.byteLength(traceText,'utf8')},
    budgets:{...BUDGETS},scope:scope(),analysis,models,findings,
    summary:{serialAnalysisStatus:analysis.status,modelClassificationStatus:models.status,serialViolation,
      verifiedRuleRefutations:findings.length,analysisComplete,requestedModelVerdictsDeterminate,requestedModelsComplete,allChecksComplete:analysisComplete&&requestedModelsComplete},
    verification:{analysis:analysisVerification,models:modelVerification},
    verificationPasses:{serialAnalysis:1,serialReportVerification:1,modelClassificationHostCalls:1,modelClassificationHostVerificationCalls:1}};
  bounded(report,BUDGETS.reportUtf8Bytes,'diagnosis report');return report;
}
/** Recompute all child judgments and the exact aggregate; matching digests alone do not verify a result. */
export function verifyDiagnosisV3(source,supplied,options){
  try{
    if(typeof supplied!=='string')safeJson(supplied,'Diagnosis report');
    const text=bounded(supplied,BUDGETS.reportUtf8Bytes,'diagnosis report'),value=JSON.parse(text);
    if(value?.format!=='moontxnwitness-diagnosis-report/v1'||value.algorithm!==ALGORITHM||typeof value.requestOptionsText!=='string'||
       !isDeepStrictEqual(value.engine,ENGINE))return {valid:false,reason:'unsupported-diagnosis-report',scope:scope()};
    const original=JSON.parse(bounded(value.requestOptionsText,BUDGETS.optionsUtf8Bytes,'original diagnosis options'));
    if(optionsText(original)!==value.requestOptionsText)return {valid:false,reason:'diagnosis-options-do-not-reproduce',scope:scope()};
    const expected=diagnoseV3(source,options===undefined?original:options);
    if(!isDeepStrictEqual(value,expected)||typeof supplied==='string'&&text!==JSON.stringify(expected)&&text!==canonical(expected))
      return {valid:false,reason:'diagnosis-report-does-not-reproduce',scope:scope()};
    return {valid:true,status:expected.status,sourceBindings:expected.sourceBindings,summary:expected.summary,scope:scope()};
  }catch(error){return {valid:false,reason:'diagnosis-verification-failed: '+error.message,scope:scope()};}
}
