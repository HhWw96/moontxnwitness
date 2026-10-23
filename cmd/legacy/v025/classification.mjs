// Explicit category classification and source-checked category reduction.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {isDeepStrictEqual} from 'node:util';
import {classify_v3_json,reduce_classification_v3_json,verify_classification_v3_json,version} from './core.mjs';

const MiB=1024*1024;
const ALGORITHM='classification-host-1';
const CATEGORY_ALGORITHM='v3-register-category-1';
const REDUCTION_ALGORITHM='v3-classification-source-checked-single-delete-1';
const CATEGORIES=Object.freeze(['G0','G1c','G2-item']);
const BUDGETS=Object.freeze({sourceUtf8Bytes:8*MiB,optionsUtf8Bytes:4096,reductionOptionsUtf8Bytes:8192,
  coreReportUtf8Bytes:32*MiB,reportUtf8Bytes:64*MiB,capsuleUtf8Bytes:128*MiB,
  transactions:128,operations:4096,edges:50000,statesPerCategory:100000,edgeChecksPerCategory:1000000,maxCandidateChecks:256});
const hash=text=>createHash('sha256').update(text).digest('hex');
const canonical=value=>JSON.stringify(value,null,2)+'\n';
const ENGINE=Object.freeze({version:version(),coreSha256:hash(readFileSync(new URL('./core.mjs',import.meta.url))),
  hostSha256:hash(readFileSync(new URL(import.meta.url)))});
const scope=()=>({categoryDefinitions:CATEGORIES.slice(),isolationModelsAccepted:false,
  supportedDataModel:'point-register-v1',versionOrderCompletion:false,categoryShortestWitnessClaim:false,
  collectorAuthenticityVerified:false,actualDatabaseExecution:false,oldAnalyzeAndCapsulesUnchanged:true,
  reductionPredicate:'the same requested category has a source-verified counterexample',
  oneMinimalMeaning:'transaction single deletion under this fixed source-checked category predicate'});

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
function integer(value,name,limit){
  if(!Number.isSafeInteger(value)||value<0||value>limit)throw new RangeError(name+' must be an integer in 0..'+limit);
}
function categoryOptions(options){
  plain(options,'Classification options');
  for(const name of Object.keys(options)){
    if(name==='categories'){
      const values=options[name];
      if(!Array.isArray(values)||!values.length||values.length>3||values.some(v=>!CATEGORIES.includes(v))||new Set(values).size!==values.length)
        throw new RangeError('categories must be a unique nonempty G0/G1c/G2-item subset');
    }else if(name==='maxStates')integer(options[name],name,100000);
    else if(name==='maxEdgeChecks')integer(options[name],name,1000000);
    else throw new RangeError('Unsupported classification option: '+name);
  }
  return bounded(options,BUDGETS.optionsUtf8Bytes,'classification options');
}
function reductionOptions(options){
  plain(options,'Classification reduction options');
  for(const name of Object.keys(options)){
    if(name==='category'){if(!CATEGORIES.includes(options[name]))throw new RangeError('Unsupported reduction category');}
    else if(name==='maxChecks')integer(options[name],name,256);
    else if(name==='classificationOptions')categoryOptions(options[name]);
    else throw new RangeError('Unsupported classification reduction option: '+name);
  }
  if(!Object.hasOwn(options,'category'))throw new RangeError('Classification reduction requires category');
  if(!(options.classificationOptions?.categories??CATEGORIES).includes(options.category))
    throw new RangeError('Reduction category must be requested by classificationOptions');
  return bounded(options,BUDGETS.reductionOptionsUtf8Bytes,'classification reduction options');
}
function sourceBindings(sourceText){return {sourceSha256:hash(sourceText),traceSha256:hash(sourceText)};}
function originalFacts(sourceText,result){
  const unavailable=reason=>({complete:false,originalEventsPreserved:false,reason});
  if(typeof result.reducedTraceText!=='string'||!Array.isArray(result.retainedOriginalSeq))return unavailable('no-reduced-capture');
  const original=JSON.parse(sourceText),reduced=JSON.parse(result.reducedTraceText);
  if(!Array.isArray(original.events)||!Array.isArray(reduced.events)||result.retainedOriginalSeq.length!==reduced.events.length)
    throw new Error('Classification reduction sequence mapping is incomplete');
  const {events:originalEvents,...originalRoot}=original,{events:reducedEvents,...reducedRoot}=reduced;
  if(!isDeepStrictEqual(originalRoot,reducedRoot)||!isDeepStrictEqual(reduced,result.reducedCapture))
    throw new Error('Classification reduction changed original root facts');
  const bySeq=new Map(originalEvents.map((event,index)=>[event.seq,{event,index}]));
  const newSeq=new Map(result.retainedOriginalSeq.map((seq,index)=>[seq,index+1]));
  if(bySeq.size!==originalEvents.length||newSeq.size!==result.retainedOriginalSeq.length)
    throw new Error('Classification reduction sequence identity is not unique');
  let last=-1;
  for(let i=0;i<reducedEvents.length;i++){
    const item=bySeq.get(result.retainedOriginalSeq[i]);
    if(!item||item.index<=last)throw new Error('Classification reduction is not an original event subsequence');
    last=item.index;
    const expected=structuredClone(item.event);expected.seq=i+1;
    if(Object.hasOwn(expected,'statement'))expected.statement=newSeq.get(expected.statement);
    if(expected.commitResponse)expected.commitResponse.request=newSeq.get(expected.commitResponse.request);
    if(!isDeepStrictEqual(expected,reducedEvents[i]))throw new Error('Classification reduction modified an observed fact');
  }
  const removed=new Set(result.removed??[]);
  if((result.removed??[]).length!==removed.size||originalEvents.some(e=>e.tx!==undefined&&removed.has(e.tx)&&newSeq.has(e.seq))||
     originalEvents.some(e=>e.tx!==undefined&&!removed.has(e.tx)&&!newSeq.has(e.seq))||
     originalEvents.some(e=>e.tx===undefined&&!newSeq.has(e.seq)))
    throw new Error('Classification reduction did not delete whole transactions');
  const sourceComplete=result.report?.normalized?.coverage?.complete===true;
  return {complete:sourceComplete,originalEventsPreserved:true,
    originalEventCount:originalEvents.length,retainedEventCount:reducedEvents.length,
    retainedOriginalSeqSha256:hash(JSON.stringify(result.retainedOriginalSeq)),
    reason:sourceComplete?'reduced source independently normalized complete':'reduced-source-coverage-incomplete'};
}
function assemble(sourceText,requestOptionsText,operation,result,verification){
  if(result?.version!==version()||!(operation==='classify'?[CATEGORY_ALGORITHM]:[REDUCTION_ALGORITHM,CATEGORY_ALGORITHM]).includes(result?.algorithm)||
     operation==='reduce'&&result.algorithm===CATEGORY_ALGORITHM&&result.status!=='invalid')
    throw new Error('Unsupported classification core algorithm/engine');
  const report={format:'moontxnwitness-classification-report/v1',schemaVersion:1,tool:'MoonTxnWitness',
    algorithm:ALGORITHM,operation,coreAlgorithm:result.algorithm,engine:{...ENGINE},status:result.status,
    requestOptionsText,originalSourceText:sourceText,sourceBindings:sourceBindings(sourceText),
    budgets:{...BUDGETS},scope:scope(),result,...verification};
  bounded(report,BUDGETS.reportUtf8Bytes,'classification report');return report;
}

/** Point-register category proof. Compatibility is scoped to requested categories. */
export function classifyV3(source,options={}){
  const sourceText=bounded(source,BUDGETS.sourceUtf8Bytes,'classification source'),requested=categoryOptions(options);
  const raw=bounded(classify_v3_json(sourceText,requested),BUDGETS.coreReportUtf8Bytes,'core classification report');
  return assemble(sourceText,requested,'classify',JSON.parse(raw),{verificationPasses:{coreClassification:1}});
}

/** Each candidate is source-normalized and searched for the same exact category by the core. */
export function reduceClassificationV3(source,options){
  const sourceText=bounded(source,BUDGETS.sourceUtf8Bytes,'classification source'),requested=reductionOptions(options);
  const result=JSON.parse(bounded(reduce_classification_v3_json(sourceText,requested),BUDGETS.coreReportUtf8Bytes,'core classification reduction'));
  const passes={coreReduction:1,finalClassification:0,finalReportVerification:0};
  let facts={complete:false,originalEventsPreserved:false,reason:'no-reduced-capture'},finalReplay={valid:false,reason:'no-reduced-report'};
  if(result.algorithm===REDUCTION_ALGORITHM){
    integer(result.checks,'actual candidate checks',options.maxChecks??256);
    if(result.maxChecks!==(options.maxChecks??256)||result.category!==options.category)throw new Error('Core reduction budget/category differs');
    facts=originalFacts(sourceText,result);
    const coreOptions=JSON.stringify(result.classificationOptions);
    const fresh=JSON.parse(bounded(classify_v3_json(result.reducedTraceText,coreOptions),BUDGETS.coreReportUtf8Bytes,'final classification'));
    passes.finalClassification++;
    if(!isDeepStrictEqual(fresh,result.report))throw new Error('Final classification differs from candidate report');
    finalReplay=JSON.parse(verify_classification_v3_json(result.reducedTraceText,JSON.stringify(result.report)));
    passes.finalReportVerification++;
    if(finalReplay.valid!==true)throw new Error('Final classification did not replay');
    if(result.status!=='not-refuted'&&result.status!=='invalid'&&
       (!facts.complete||result.report?.rules?.[result.category]?.status!=='refuted'))
      throw new Error('Reduction lacks complete original source or the requested category refutation');
  }
  return assemble(sourceText,requested,'reduce',result,{sourceClosure:facts,finalReplay,verificationPasses:passes});
}

/** Recompute all categories, source facts, options, budgets, counters and reduction mapping. */
export function verifyClassificationV3(source,supplied,options){
  try{
    const text=bounded(supplied,BUDGETS.reportUtf8Bytes,'classification report'),report=JSON.parse(text);
    if(report?.format!=='moontxnwitness-classification-report/v1'||report.algorithm!==ALGORITHM||
       !['classify','reduce'].includes(report.operation)||typeof report.requestOptionsText!=='string')
      return {valid:false,reason:'unsupported-classification-report',scope:scope()};
    const requested=options??JSON.parse(report.requestOptionsText);
    const expected=report.operation==='classify'?classifyV3(source,requested):reduceClassificationV3(source,requested);
    if(!isDeepStrictEqual(report,expected)||typeof supplied==='string'&&text!==JSON.stringify(expected)&&text!==canonical(expected))
      return {valid:false,reason:'classification-report-does-not-reproduce',scope:scope()};
    return {valid:true,status:expected.status,operation:expected.operation,sourceBindings:expected.sourceBindings,scope:scope()};
  }catch(error){return {valid:false,reason:'classification-verification-failed: '+error.message,scope:scope()};}
}
function capsuleFields(sourceText,requestOptionsText,operation,reportText){
  return {format:'moontxnwitness-classification/v1',schemaVersion:1,tool:'MoonTxnWitness',algorithm:ALGORITHM,
    operation,coreAlgorithm:JSON.parse(reportText).coreAlgorithm,engine:{...ENGINE},budgets:{...BUDGETS},
    sourceText,sourceBindings:sourceBindings(sourceText),requestOptionsText,requestOptionsSha256:hash(requestOptionsText),
    reportText,reportSha256:hash(reportText)};
}
function make(source,options,operation){
  const sourceText=bounded(source,BUDGETS.sourceUtf8Bytes,'classification source');
  const requested=operation==='classify'?categoryOptions(options):reductionOptions(options);
  const report=operation==='classify'?classifyV3(sourceText,options):reduceClassificationV3(sourceText,options);
  return bounded(canonical(capsuleFields(sourceText,requested,operation,JSON.stringify(report))),BUDGETS.capsuleUtf8Bytes,'classification capsule');
}
export function makeClassificationCapsuleV3(source,options={}){return make(source,options,'classify');}
export function makeClassificationReductionCapsuleV3(source,options){return make(source,options,'reduce');}

/** Exact current-runtime replay; a matching inconclusive result remains inconclusive. */
export function replayClassificationCapsuleV3(text){
  const reject=reason=>({valid:false,reason,scope:scope()});
  try{
    if(typeof text!=='string')return reject('classification-capsule-must-be-original-text');
    bounded(text,BUDGETS.capsuleUtf8Bytes,'classification capsule');const value=JSON.parse(text);
    if(value?.format!=='moontxnwitness-classification/v1'||value.schemaVersion!==1||value.tool!=='MoonTxnWitness'||
       value.algorithm!==ALGORITHM||!['classify','reduce'].includes(value.operation)||!isDeepStrictEqual(value.engine,ENGINE)||
       typeof value.sourceText!=='string'||typeof value.requestOptionsText!=='string'||typeof value.reportText!=='string')
      return reject('unsupported-classification-capsule-header');
    bounded(value.sourceText,BUDGETS.sourceUtf8Bytes,'classification source');
    bounded(value.reportText,BUDGETS.reportUtf8Bytes,'classification report');
    bounded(value.requestOptionsText,value.operation==='classify'?BUDGETS.optionsUtf8Bytes:BUDGETS.reductionOptionsUtf8Bytes,'classification options');
    const options=JSON.parse(value.requestOptionsText),requested=value.operation==='classify'?categoryOptions(options):reductionOptions(options);
    if(requested!==value.requestOptionsText)return reject('classification-options-not-canonical');
    if(canonical(capsuleFields(value.sourceText,requested,value.operation,value.reportText))!==text)
      return reject('classification-capsule-fields-digest-or-original-bytes-differ');
    const result=verifyClassificationV3(value.sourceText,value.reportText,options);
    if(result.valid!==true)return reject(result.reason);
    const report=JSON.parse(value.reportText);
    if(value.coreAlgorithm!==report.coreAlgorithm)return reject('classification-algorithm-differs');
    return {valid:true,status:report.status,operation:value.operation,report,sourceBindings:report.sourceBindings,scope:scope()};
  }catch(error){return reject('classification-capsule-replay-failed: '+error.message);}
}
