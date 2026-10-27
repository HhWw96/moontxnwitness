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
function knownChildHeads(header){
 // Only documented report output slots; never normalized facts/history/events.
 const paths=[['report'],['result'],['result','analysis'],['result','originalReport'],['result','originalReport','analysis'],['result','report'],['result','reduction','report'],['result','finalReanalysis'],['result','genericAttempt']];
 for(const path of paths){let value=header;for(const key of path)value=value?.[key];
  if(plain(value)&&Object.hasOwn(value,'version')&&value.version!=='0.2.8')throw Error('Mixed nested algorithm engine');
 }
}
function engine(header,kind){
 if(!plain(header))throw Error('Expected algorithm header');
 knownChildHeads(header);
 if(kind==='core12'){if(![1,2].includes(header.schemaVersion)||header.version!=='0.2.8')throw Error('Only current028 core12 accepted');return;}
 if(kind==='core3'){if(header.schemaVersion!==3||header.version!=='0.2.8')throw Error('Only current028 core3 accepted');return;}
 if(kind==='cycle'){if(header.kind!=='moontxnwitness-register-cycle-explanation/v1'||header.sourceReportVersion!=='0.2.8')throw Error('Only current028 cycle accepted');return;}
 if(kind==='capsule12'||kind==='capsule3'){
  const valid=kind==='capsule12'?['moontxnwitness-replay/v1','moontxnwitness-replay/v2']:['moontxnwitness-replay/v3'];
  if(!valid.includes(header.format)||header.engineVersion!=='0.2.8')throw Error('Only current028 capsule accepted');
  engine(parse(header.reportText),kind==='capsule12'?'core12':'core3');return;
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
 if(inner)engine(parse(header.reportText),inner);
 if(kind==='moontxnwitness-diagnosis-report/v1'){
  engine(header.analysis,'core3');engine(header.models,'moontxnwitness-isolation-model-report/v1');
 }
}

export function targets028(operation,args){
 if(!Object.hasOwn(METHODS,operation)||!Array.isArray(args))return false;
 const kind=METHODS[operation][4];let header;try{header=parse(operation.startsWith('verify-')?args[1]:args[0]);}catch{return false;}
 if(!plain(header))return false;
 const simple=['capsule12','capsule3','moontxnwitness-orm-profile-report/v1','moontxnwitness-orm-profile/v1','moontxnwitness-execution/v1'].includes(kind);
 return (['core12','core3','cycle'].includes(kind)?header.version:simple?header.engineVersion:header.engine?.version)==='0.2.8';
}
export function assertOperation028(operation,args){
 if(!Object.hasOwn(METHODS,operation)||!Array.isArray(args))throw Error('Unknown fixed028 operation');
 const [name,method,min,max,kind]=METHODS[operation];
 if(args.length<min||args.length>max||Buffer.byteLength(JSON.stringify(args),'utf8')>MAX_BYTES)throw Error('Fixed028 arguments exceed contract');
 if(kind==='cycle'){engine(parse(args[1]),'core3');engine(parse(args[2]),'cycle');}
 else engine(parse(operation.startsWith('verify-')?args[1]:args[0]),kind);
 return {name,method,runtimeId:selectRuntime028(operation,args)};
}

// Select only from documented algorithm ENGINE metadata. Business values and
// trace/source payloads are deliberately outside this traversal.
export function selectRuntime028(operation,args){
 const kind=METHODS[operation]?.[4];if(!kind)throw Error('Unknown fixed028 operation');
 let selected;
 function visit(header,form){
  if(!plain(header))throw Error('Expected algorithm header');
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
  if(inner)visit(parse(header.reportText),inner);
  if(form==='moontxnwitness-diagnosis-report/v1'){visit(header.analysis,'core3');visit(header.models,'moontxnwitness-isolation-model-report/v1');}
 }
 visit(parse(operation.startsWith('verify-')?args[1]:args[0]),kind);
 return selected??null;
}

// No-hash evidence cannot identify a compiled filesystem path. Only these fixed
// verification APIs may try the fixed originals inside the same bounded worker.
export const RUNTIME_ORDER=Object.freeze(['linux-public-portable','windows-public-source-rebuild','windows-public-source-fs-uppercase-rebuild']);
export const NO_HASH_VERIFY_OPERATIONS=Object.freeze(['verify-v1v2','replay-v1v2','verify-v3','replay-v3','verify-orm','replay-orm','replay-execution','verify-cycle']);
