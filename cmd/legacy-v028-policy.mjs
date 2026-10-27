import {PUBLIC_V028 as PIN} from './legacy-v028-binding.mjs';
// Fixed known algorithm headers only; business versions are never traversed.
export const FORMAT='moontxnwitness-current028-worker/v1',MAX_BYTES=384*1024*1024;
const plain=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const parse=v=>typeof v==='string'?JSON.parse(v):v;
export const METHODS=Object.freeze({
 'verify-v1v2':['sdk.mjs','replayReport',2,2,'core12'],
 'replay-v1v2':['evidence.mjs','replayCapsule',1,1,'capsule12'],
 'verify-v3':['sdk.mjs','verifyV3',2,2,'core3'],
 'replay-v3':['evidence.mjs','replayCapsuleV3',1,1,'capsule3'],
 'verify-orm':['orm-profile.mjs','verifyOrmProfileV3',2,3,'moontxnwitness-orm-profile-report/v1'],
 'replay-orm':['orm-profile.mjs','replayOrmProfileCapsuleV3',1,1,'moontxnwitness-orm-profile/v1'],
 'verify-classification':['classification.mjs','verifyClassificationV3',2,3,'moontxnwitness-classification-report/v1'],
 'replay-classification':['classification.mjs','replayClassificationCapsuleV3',1,1,'moontxnwitness-classification/v1'],
 'verify-models':['classification-models.mjs','verifyModelsClassificationV3',2,3,'moontxnwitness-isolation-model-report/v1'],
 'replay-models':['classification-models.mjs','replayModelsClassificationCapsuleV3',1,1,'moontxnwitness-isolation-models/v1'],
 'verify-model-profile':['model-profile.mjs','verifyModelProfileV3',2,3,'moontxnwitness-model-profile-report/v1'],
 'replay-model-profile':['model-profile.mjs','replayModelProfileCapsuleV3',1,1,'moontxnwitness-model-profile/v1'],
 'verify-diagnosis':['diagnosis.mjs','verifyDiagnosisV3',2,3,'moontxnwitness-diagnosis-report/v1'],
 'replay-execution':['sdk.mjs','replayExecutionCapsuleV3',1,1,'moontxnwitness-execution/v1'],
 'verify-cycle':['sdk.mjs','verifyRegisterCycleExplanationV3',3,3,'cycle'],
});
for(const descriptor of Object.values(METHODS))Object.freeze(descriptor);
// Match each public API's existing default before compatibility adds parsing or
// serializes a whole worker request. v1/v2 limits count UTF-16 code units.
const MiB=1024*1024;
function stringBudget(value,maximum,codeUnits=false){
 if(typeof value==='string'&&(value.length>maximum||!codeUnits&&Buffer.byteLength(value,'utf8')>maximum))
  throw new RangeError('Fixed028 input exceeds original API '+(codeUnits?'UTF-16 code-unit':'UTF-8 byte')+' budget');
 return value;
}
const ARGUMENT_BUDGETS=Object.freeze({
 'verify-v1v2':[[1048576,true],[32*MiB,true]],'replay-v1v2':[[32*MiB,true]],
 'verify-v3':[[8*MiB],[32*MiB]],'replay-v3':[[32*MiB]],
 'verify-cycle':[[8*MiB],[32*MiB],[8*MiB]],
 'verify-orm':[[64*MiB],[64*MiB],[4096]],'replay-orm':[[128*MiB]],
 'verify-classification':[[8*MiB],[64*MiB],[8192]],'replay-classification':[[128*MiB]],
 'verify-models':[[32*MiB],[96*MiB],[8192]],'replay-models':[[192*MiB]],
 'verify-model-profile':[[64*MiB],[64*MiB],[4096]],'replay-model-profile':[[128*MiB]],
 'verify-diagnosis':[[8*MiB],[160*MiB],[16384]],'replay-execution':[[32*MiB]],
});
function argumentBudgets(operation,args){
 for(const[index,budget]of ARGUMENT_BUDGETS[operation].entries())stringBudget(args[index],...budget);
}
const HEADER_BUDGETS=Object.freeze({
 core12:[32*MiB,true],capsule12:[32*MiB,true],core3:[32*MiB],capsule3:[32*MiB],cycle:[8*MiB],
 'moontxnwitness-orm-profile-report/v1':[64*MiB],'moontxnwitness-orm-profile/v1':[128*MiB],
 'moontxnwitness-classification-report/v1':[64*MiB],'moontxnwitness-classification/v1':[128*MiB],
 'moontxnwitness-isolation-model-report/v1':[96*MiB],'moontxnwitness-isolation-models/v1':[192*MiB],
 'moontxnwitness-model-profile-report/v1':[64*MiB],'moontxnwitness-model-profile/v1':[128*MiB],
 'moontxnwitness-diagnosis-report/v1':[160*MiB],'moontxnwitness-execution/v1':[32*MiB],
});
const parseHeader=(value,kind)=>parse(stringBudget(value,...HEADER_BUDGETS[kind]));
function capsuleBudgets(header,kind){
 if(kind==='capsule12'){stringBudget(header.historyText,1048576,true);stringBudget(header.reportText,32*MiB,true);}
 if(kind==='capsule3'){stringBudget(header.traceText,8*MiB);stringBudget(header.reportText,32*MiB);}
 const limits={
  'moontxnwitness-orm-profile/v1':['envelopeText',64*MiB,64*MiB,4096],
  'moontxnwitness-classification/v1':['sourceText',8*MiB,64*MiB,header.operation==='reduce'?8192:4096],
  'moontxnwitness-isolation-models/v1':['sourceText',32*MiB,96*MiB,8192],
  'moontxnwitness-model-profile/v1':['envelopeText',64*MiB,64*MiB,4096],
 }[kind];
 if(limits){stringBudget(header[limits[0]],limits[1]);stringBudget(header.reportText,limits[2]);stringBudget(header.requestOptionsText,limits[3]);}
 if(kind==='moontxnwitness-execution/v1'){stringBudget(header.traceText,8*MiB);stringBudget(header.diagnosticText,32*MiB);}
}

function knownChildHeads(header){
 // Only documented report output slots; never normalized facts/history/events.
 const paths=[['report'],['result'],['result','analysis'],['result','originalReport'],['result','originalReport','analysis'],['result','report'],['result','reduction','report'],['result','finalReanalysis'],['result','genericAttempt']];
 for(const path of paths){let value=header;for(const key of path)value=value?.[key];
  if(plain(value)&&Object.hasOwn(value,'version')&&value.version!=='0.2.8')throw Error('Mixed nested algorithm engine');
 }
}
function engine(header,kind){
 if(!plain(header))throw Error('Expected algorithm header');
 capsuleBudgets(header,kind);
 knownChildHeads(header);
 if(kind==='core12'){if(![1,2].includes(header.schemaVersion)||header.version!=='0.2.8')throw Error('Only current028 core12 accepted');return;}
 if(kind==='core3'){if(header.schemaVersion!==3||header.version!=='0.2.8')throw Error('Only current028 core3 accepted');return;}
 if(kind==='cycle'){if(header.kind!=='moontxnwitness-register-cycle-explanation/v1'||header.sourceReportVersion!=='0.2.8')throw Error('Only current028 cycle accepted');return;}
 if(kind==='capsule12'||kind==='capsule3'){
  const valid=kind==='capsule12'?['moontxnwitness-replay/v1','moontxnwitness-replay/v2']:['moontxnwitness-replay/v3'];
  if(!valid.includes(header.format)||header.engineVersion!=='0.2.8')throw Error('Only current028 capsule accepted');
  engine(parseHeader(header.reportText,kind==='capsule12'?'core12':'core3'),kind==='capsule12'?'core12':'core3');return;
 }
 if(header.format!==kind)throw Error('Algorithm format differs');
 const simple=['moontxnwitness-orm-profile-report/v1','moontxnwitness-orm-profile/v1','moontxnwitness-execution/v1'].includes(kind);
 if((simple?header.engineVersion:header.engine?.version)!=='0.2.8')throw Error('Only current028 algorithm header accepted');
 const inner={
  'moontxnwitness-orm-profile/v1':'moontxnwitness-orm-profile-report/v1',
  'moontxnwitness-classification/v1':'moontxnwitness-classification-report/v1',
  'moontxnwitness-isolation-models/v1':'moontxnwitness-isolation-model-report/v1',
  'moontxnwitness-model-profile/v1':'moontxnwitness-model-profile-report/v1',
 }[kind];
 if(inner)engine(parseHeader(header.reportText,inner),inner);
 if(kind==='moontxnwitness-diagnosis-report/v1'){
  engine(header.analysis,'core3');engine(header.models,'moontxnwitness-isolation-model-report/v1');
 }
}

export function targets028(operation,args){
 if(!Object.hasOwn(METHODS,operation)||!Array.isArray(args))return false;
 const kind=METHODS[operation][4];let header;try{argumentBudgets(operation,args);header=parseHeader(operation.startsWith('verify-')?args[1]:args[0],kind==='cycle'?'core3':kind);}catch{return false;}
 if(!plain(header))return false;
 const simple=['capsule12','capsule3','moontxnwitness-orm-profile-report/v1','moontxnwitness-orm-profile/v1','moontxnwitness-execution/v1'].includes(kind);
 return (['core12','core3','cycle'].includes(kind)?header.version:simple?header.engineVersion:header.engine?.version)==='0.2.8';
}
export function assertOperation028(operation,args){
 if(!Object.hasOwn(METHODS,operation)||!Array.isArray(args))throw Error('Unknown fixed028 operation');
 const [name,method,min,max,kind]=METHODS[operation];
 if(args.length<min||args.length>max)throw Error('Fixed028 arguments exceed contract');
 argumentBudgets(operation,args);
 if(kind==='cycle'){engine(parseHeader(args[1],'core3'),'core3');engine(parseHeader(args[2],'cycle'),'cycle');}
 else engine(parseHeader(operation.startsWith('verify-')?args[1]:args[0],kind),kind);
 const runtimeId=selectRuntime028(operation,args);
 if(Buffer.byteLength(JSON.stringify(args),'utf8')>MAX_BYTES)throw Error('Fixed028 arguments exceed contract');
 return {name,method,runtimeId};
}

// Select only from documented algorithm ENGINE metadata. Business values and
// trace/source payloads are deliberately outside this traversal.
export function selectRuntime028(operation,args){
 const kind=METHODS[operation]?.[4];if(!kind||!Array.isArray(args))throw Error('Unknown fixed028 operation');
 argumentBudgets(operation,args);
 let selected;
 function visit(header,form){
  if(!plain(header))throw Error('Expected algorithm header');
  capsuleBudgets(header,form);
  const host={
   'moontxnwitness-classification-report/v1':'classification','moontxnwitness-classification/v1':'classification',
   'moontxnwitness-isolation-model-report/v1':'models','moontxnwitness-isolation-models/v1':'models',
   'moontxnwitness-model-profile-report/v1':'modelProfile','moontxnwitness-model-profile/v1':'modelProfile',
   'moontxnwitness-diagnosis-report/v1':'diagnosis',
  }[form];
  if(host){
   const e=header.engine;if(!plain(e)||e.version!=='0.2.8')throw Error('Missing public028 engine metadata');
   const matches=Object.entries(PIN.runtimeIdentities??{}).filter(([id,r])=>{
    const expected={version:'0.2.8',coreSha256:r.coreSha256,...(host==='diagnosis'?{captureCoreSha256:r.captureCoreSha256,modelHostSha256:r.hosts.models}:{}),hostSha256:r.hosts[host]};
    return Object.keys(e).sort().join(',')===Object.keys(expected).sort().join(',')&&Object.entries(expected).every(([k,v])=>e[k]===v);
   });
   if(matches.length!==1)throw Error('Unknown or mixed public028 runtime metadata');
   if(selected&&selected!==matches[0][0])throw Error('Mixed nested public028 runtime metadata');selected=matches[0][0];
  }
  const inner={capsule12:'core12',capsule3:'core3','moontxnwitness-orm-profile/v1':'moontxnwitness-orm-profile-report/v1','moontxnwitness-classification/v1':'moontxnwitness-classification-report/v1','moontxnwitness-isolation-models/v1':'moontxnwitness-isolation-model-report/v1','moontxnwitness-model-profile/v1':'moontxnwitness-model-profile-report/v1'}[form];
  if(inner)visit(parseHeader(header.reportText,inner),inner);
  if(form==='moontxnwitness-diagnosis-report/v1'){visit(header.analysis,'core3');visit(header.models,'moontxnwitness-isolation-model-report/v1');}
 }
 visit(parseHeader(operation.startsWith('verify-')?args[1]:args[0],kind==='cycle'?'core3':kind),kind);
 return selected??null;
}

// No-hash evidence cannot identify a compiled filesystem path. Only these fixed
// verification APIs may try the fixed originals inside the same bounded worker.
export const RUNTIME_ORDER=Object.freeze(['linux-public-portable','windows-public-source-rebuild','windows-public-source-fs-uppercase-rebuild']);
export const NO_HASH_VERIFY_OPERATIONS=Object.freeze(['verify-v1v2','replay-v1v2','verify-v3','replay-v3','verify-orm','replay-orm','replay-execution','verify-cycle']);
