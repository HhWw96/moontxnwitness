// Fixed public runtime only. Requests cannot select a module, path or executable.
import {readFileSync,lstatSync} from 'node:fs';
import {createHash,randomBytes} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {METHODS} from './legacy-v028-policy.mjs';

const FORMAT='moontxnwitness-public030-worker/v1',MAX=384*1024*1024;
const MANIFEST='80c462863a0036a867b5a18b65bd496ea992f1111ec5eb2ca0a313f7b41ce73d';
const root=fileURLToPath(new URL('./legacy/v030/',import.meta.url));
const hash=b=>createHash('sha256').update(b).digest('hex');
const MiB=1024*1024;
// Preserve released v3 diagnostics, including compiler source coordinates.
// Later host formats retain their existing per-version runtime selection.
const LEGACY_V3_ENGINES=Object.freeze([
 '0.1.1','0.1.2','0.1.3','0.1.4','0.1.5','0.1.6','0.1.7','0.1.8',
 '0.2.0','0.2.1','0.2.2','0.2.3','0.2.4','0.2.5','0.2.6','0.2.7',
]);
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
 if(typeof value==='string'&&(value.length>max||!units&&Buffer.byteLength(value,'utf8')>max))throw Error('Public030 original input budget');
 return value;
}
function header(operation,args){
 if(!Object.hasOwn(METHODS,operation)||!Array.isArray(args))throw Error('Unknown public030 operation');
 const [module,method,min,max,kind]=METHODS[operation];
 if(args.length<min||args.length>max)throw Error('Public030 argument count');
 budgets[operation].forEach((limit,i)=>bounded(args[i],...limit));
 const raw=operation.startsWith('verify-')?args[1]:args[0];
 const value=typeof raw==='string'?JSON.parse(raw):raw;
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Public030 header required');
 const simple=['capsule12','capsule3','moontxnwitness-orm-profile-report/v1','moontxnwitness-orm-profile/v1','moontxnwitness-execution/v1'].includes(kind);
 const version=['core12','core3','cycle'].includes(kind)?value.version:simple?value.engineVersion:value.engine?.version;
 const formatMatches=kind==='core12'?[1,2].includes(value.schemaVersion):kind==='core3'||kind==='cycle'?value.schemaVersion===3:
  kind==='capsule12'?['moontxnwitness-replay/v1','moontxnwitness-replay/v2'].includes(value.format):
  kind==='capsule3'?value.format==='moontxnwitness-replay/v3':value.format===kind;
 const oldCore=['core3','capsule3'].includes(kind)&&LEGACY_V3_ENGINES.includes(version);
 if(!formatMatches||version!=='0.3.0'&&!oldCore)throw Error('Not a supported public030 algorithm header');
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

export function verifyPublic030Runtime(){
 for(let p=resolve(root);;p=resolve(p,'..')){const st=lstatSync(p);if(!st.isDirectory()||st.isSymbolicLink())throw Error('Unsafe public030 runtime directory');if(p===resolve(p,'..'))break;}
 const path=resolve(root,'public-runtime-manifest.json'),st=lstatSync(path);
 if(!st.isFile()||st.isSymbolicLink()||st.size>256*1024)throw Error('Public030 manifest budget');
 const raw=readFileSync(path);if(hash(raw)!==MANIFEST)throw Error('Public030 runtime manifest differs');
 const manifest=JSON.parse(raw);if(manifest.version!=='0.3.0')throw Error('Public030 version differs');
 for(const [name,entry] of Object.entries(manifest.files)){
  if(name.includes('\\')||name.includes(':')||name.split('/').some(x=>!x||x==='.'||x==='..'))throw Error('Unsafe public030 member');
  const path=resolve(root,name),st=lstatSync(path);
  if(!st.isFile()||st.isSymbolicLink()||st.size!==entry.bytes||st.size>16*MiB)throw Error('Public030 member size differs');
  if(hash(readFileSync(path))!==entry.sha256)throw Error('Public030 runtime member differs: '+name);
 }
 return root;
}

export function routeLegacyV030(operation,args,currentVersion){
 if(currentVersion==='0.3.0')return {matched:false};
 try{header(operation,args);}catch{return {matched:false};}
 try{
  if(process.env.MTW_PUBLIC030_WORKER)throw Error('Nested public030 worker');
  verifyPublic030Runtime();
  const id=randomBytes(16).toString('hex'),input=Buffer.from(JSON.stringify({format:FORMAT,id,operation,arguments:args})+'\n');
  if(input.length>MAX)throw Error('Public030 request budget');
  const env={TZ:'UTC',MTW_PUBLIC030_WORKER:'1'};
  for(const[k,v]of Object.entries(process.env))if(['systemroot','windir','systemdrive','temp','tmp','tmpdir'].includes(k.toLowerCase()))env[k]=v;
  const child=spawnSync(process.execPath,['--no-addons',fileURLToPath(import.meta.url)],{input,encoding:null,env,windowsHide:true,timeout:300000,maxBuffer:MAX});
  if(child.error||child.status!==0||child.signal||child.stderr?.length)throw Error('Public030 worker failed');
  const text=child.stdout.toString('utf8');if(!Buffer.from(text).equals(child.stdout))throw Error('Public030 output encoding');
  const result=JSON.parse(text);
  if(Object.keys(result).sort().join(',')!=='format,id,result'||result.id!==id||result.format!==FORMAT||typeof result.result?.valid!=='boolean'||JSON.stringify(result)+'\n'!==text)throw Error('Public030 response differs');
  if(['verify-v1v2','replay-v1v2'].includes(operation)&&Object.hasOwn(result.result,'currentEngine'))result.result.currentEngine=currentVersion;
  return {matched:true,result:result.result};
 }catch(error){return {matched:true,result:{valid:false,reason:'public030-unavailable-or-refused: '+error.message}};}
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  if(process.argv.length!==2||process.env.MTW_PUBLIC030_WORKER!=='1')throw Error('No worker selectors');
  let count=0;const chunks=[];
  for await(const b of process.stdin){count+=b.length;if(count>MAX)throw Error('Worker input budget');chunks.push(b);}
  const raw=Buffer.concat(chunks),text=raw.toString('utf8');if(!Buffer.from(text).equals(raw))throw Error('Worker encoding');
  const q=JSON.parse(text);
  if(Object.keys(q).sort().join(',')!=='arguments,format,id,operation'||q.format!==FORMAT||!/^[0-9a-f]{32}$/.test(q.id)||JSON.stringify(q)+'\n'!==text)throw Error('Worker request differs');
  const {module,method}=header(q.operation,q.arguments);verifyPublic030Runtime();
  const original=await import(pathToFileURL(resolve(root,module)).href),result=original[method](...q.arguments);
  if(typeof result?.valid!=='boolean')throw Error('Worker result differs');
  const output=JSON.stringify({format:FORMAT,id:q.id,result})+'\n';if(Buffer.byteLength(output)>MAX)throw Error('Worker output budget');
  process.stdout.write(output);
 }catch{process.stderr.write('Public030 worker refused the request.\n');process.exitCode=2;}
}
