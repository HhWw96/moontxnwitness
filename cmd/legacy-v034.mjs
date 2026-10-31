import {PUBLIC034 as PIN} from './legacy-v034-binding.mjs';
// Fixed public runtime only. Requests cannot select a module, path or executable.
import {randomBytes} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {METHODS} from './legacy-v028-policy.mjs';
import {createCompactRuntimeLoader} from './compact-runtime.mjs';
let loader;
const fixedLoader=()=>loader??=createCompactRuntimeLoader(PIN);


const FORMAT='moontxnwitness-public034-worker/v1',MAX=768*1024*1024;
const MiB=1024*1024;
const budgets={
 'verify-v1v2':[[1048576,true],[32*MiB,true]],'replay-v1v2':[[32*MiB,true]],
 'verify-v3':[[8*MiB],[32*MiB]],'replay-v3':[[32*MiB]],'verify-cycle':[[8*MiB],[32*MiB],[8*MiB]],
 'verify-orm':[[64*MiB],[64*MiB],[4096]],'replay-orm':[[128*MiB]],
 'verify-classification':[[8*MiB],[64*MiB],[8192]],'replay-classification':[[128*MiB]],
 'verify-models':[[32*MiB],[96*MiB],[8192]],'replay-models':[[192*MiB]],
 'verify-model-profile':[[64*MiB],[64*MiB],[4096]],'replay-model-profile':[[128*MiB]],
 'verify-diagnosis':[[8*MiB],[160*MiB],[16384]],'replay-execution':[[32*MiB]],
};
function bounded(value,max,units=false){
 if(typeof value==='string'&&(value.length>max||!units&&Buffer.byteLength(value,'utf8')>max))throw Error('Public034 original input budget');
 return value;
}
function header(operation,args){
 if(!Object.hasOwn(METHODS,operation)||!Array.isArray(args))throw Error('Unknown public034 operation');
 const [module,method,min,max,kind]=METHODS[operation];
 if(args.length<min||args.length>max)throw Error('Public034 argument count');
 budgets[operation].forEach((limit,i)=>bounded(args[i],...limit));
 const raw=operation.startsWith('verify-')?args[1]:args[0];
 const value=typeof raw==='string'?JSON.parse(raw):raw;
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Public034 header required');
 const simple=['capsule12','capsule3','moontxnwitness-orm-profile-report/v1','moontxnwitness-orm-profile/v1','moontxnwitness-execution/v1'].includes(kind);
 const version=['core12','core3','cycle'].includes(kind)?value.version:simple?value.engineVersion:value.engine?.version;
 const formatMatches=kind==='core12'?[1,2].includes(value.schemaVersion):kind==='core3'||kind==='cycle'?value.schemaVersion===3:
  kind==='capsule12'?['moontxnwitness-replay/v1','moontxnwitness-replay/v2'].includes(value.format):
  kind==='capsule3'?value.format==='moontxnwitness-replay/v3':value.format===kind;
 if(!formatMatches||version!=='0.3.4')throw Error('Not a supported public034 algorithm header');
 if(kind==='capsule3'){
  const report=typeof value.reportText==='string'?JSON.parse(bounded(value.reportText,32*MiB)):value.reportText;
  if(!report||report.schemaVersion!==3||report.version!==version)throw Error('Mixed legacy v3 engine headers');
 }
 // Original embedded-source budgets must be enforced before creating a worker request.
 if(kind==='capsule12'){bounded(value.historyText,1048576,true);bounded(value.reportText,32*MiB,true);}
 if(kind==='capsule3'){bounded(value.traceText,8*MiB);bounded(value.reportText,32*MiB);}
 const embedded={
  'moontxnwitness-orm-profile/v1':['envelopeText',64*MiB,64*MiB,4096],
  'moontxnwitness-classification/v1':['sourceText',8*MiB,64*MiB,value.operation==='reduce'?8192:4096],
  'moontxnwitness-isolation-models/v1':['sourceText',32*MiB,96*MiB,8192],
  'moontxnwitness-model-profile/v1':['envelopeText',64*MiB,64*MiB,4096],
 }[kind];
 if(embedded){bounded(value[embedded[0]],embedded[1]);bounded(value.reportText,embedded[2]);bounded(value.requestOptionsText,embedded[3]);}
 if(kind==='moontxnwitness-execution/v1'){bounded(value.traceText,8*MiB);bounded(value.diagnosticText,32*MiB);}
 return {module,method};
}

export function verifyPublic034Runtime(){return fixedLoader().get();}

export function routeLegacyV034(operation,args,currentVersion){
 if(currentVersion==='0.3.4')return {matched:false};
 try{header(operation,args);}catch{return {matched:false};}
 try{
  if(process.env.MTW_PUBLIC034_WORKER)throw Error('Nested public034 worker');
  verifyPublic034Runtime();
  const id=randomBytes(16).toString('hex'),input=Buffer.from(JSON.stringify({format:FORMAT,id,operation,arguments:args})+'\n');
  if(input.length>MAX)throw Error('Public034 request budget');
  const env={TZ:'UTC',MTW_PUBLIC034_WORKER:'1'};
  for(const[k,v]of Object.entries(process.env))if(['systemroot','windir','systemdrive','temp','tmp','tmpdir'].includes(k.toLowerCase()))env[k]=v;
  const child=spawnSync(process.execPath,['--no-addons',fileURLToPath(import.meta.url)],{input,encoding:null,env,windowsHide:true,timeout:300000,maxBuffer:MAX});
  if(child.error||child.status!==0||child.signal||child.stderr?.length)throw Error('Public034 worker failed');
  const text=child.stdout.toString('utf8');if(!Buffer.from(text).equals(child.stdout))throw Error('Public034 output encoding');
  const result=JSON.parse(text);
  if(Object.keys(result).sort().join(',')!=='format,id,result'||result.id!==id||result.format!==FORMAT||typeof result.result?.valid!=='boolean'||JSON.stringify(result)+'\n'!==text)throw Error('Public034 response differs');
  if(['verify-v1v2','replay-v1v2'].includes(operation)&&Object.hasOwn(result.result,'currentEngine'))result.result.currentEngine=currentVersion;
  return {matched:true,result:result.result};
 }catch(error){return {matched:true,result:{valid:false,reason:'public034-unavailable-or-refused: '+error.message}};}
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  if(process.argv.length!==2||process.env.MTW_PUBLIC034_WORKER!=='1')throw Error('No worker selectors');
  let count=0;const chunks=[];
  for await(const b of process.stdin){count+=b.length;if(count>MAX)throw Error('Worker input budget');chunks.push(b);}
  const raw=Buffer.concat(chunks),text=raw.toString('utf8');if(!Buffer.from(text).equals(raw))throw Error('Worker encoding');
  const q=JSON.parse(text);
  if(Object.keys(q).sort().join(',')!=='arguments,format,id,operation'||q.format!==FORMAT||!/^[0-9a-f]{32}$/.test(q.id)||JSON.stringify(q)+'\n'!==text)throw Error('Worker request differs');
  const {module,method}=header(q.operation,q.arguments);const root=verifyPublic034Runtime();
  const original=await import(pathToFileURL(resolve(root,module)).href),result=original[method](...q.arguments);
  if(typeof result?.valid!=='boolean')throw Error('Worker result differs');
  const output=JSON.stringify({format:FORMAT,id:q.id,result})+'\n';if(Buffer.byteLength(output)>MAX)throw Error('Worker output budget');
  process.stdout.write(output);
 }catch{process.stderr.write('Public034 worker refused the request.\n');process.exitCode=2;}
}
