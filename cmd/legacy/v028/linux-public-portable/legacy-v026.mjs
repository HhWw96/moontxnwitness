// Synchronous historical replay through a fixed, byte-verified ESM child.
// Importing this module never loads old core code or starts a worker.
import {spawnSync} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {verifyPublicV026Runtime} from './legacy-v026-runtime.mjs';
const FORMAT='moontxnwitness-historical-worker/v1';
const OPERATIONS=new Set(['verify-orm','replay-orm','verify-classification','replay-classification','verify-models','replay-models']);
const MAX_BYTES=384*1024*1024,TIMEOUT_MS=300000;
export function callLegacyV026(operation,args){
 if(!OPERATIONS.has(operation)||!Array.isArray(args)||!(operation.startsWith('verify-')?[2,3]:[1]).includes(args.length))throw new Error('Unsupported fixed historical operation');
 verifyPublicV026Runtime();
 const id=randomBytes(16).toString('hex'),input=Buffer.from(JSON.stringify({format:FORMAT,id,operation,arguments:args})+'\n');
 if(input.length>MAX_BYTES)throw new Error('Historical worker request exceeds byte budget');
 const env={TZ:'UTC'};
 for(const [key,value]of Object.entries(process.env))if(['systemroot','windir','systemdrive','temp','tmp','tmpdir'].includes(key.toLowerCase()))env[key]=value;
 const child=spawnSync(process.execPath,['--no-addons',fileURLToPath(new URL('./legacy-v026-worker.mjs',import.meta.url))],{input,encoding:null,env,cwd:fileURLToPath(new URL('.',import.meta.url)),windowsHide:true,timeout:TIMEOUT_MS,killSignal:'SIGKILL',maxBuffer:MAX_BYTES});
 if(child.error||child.status!==0||child.signal||!Buffer.isBuffer(child.stdout)||child.stdout.length>MAX_BYTES||child.stderr?.length)throw new Error('Fixed public26 worker failed'+(child.error?.code?': '+child.error.code:': exit '+child.status));
 const raw=child.stdout.toString('utf8');if(!Buffer.from(raw,'utf8').equals(child.stdout))throw new Error('Historical worker returned malformed UTF-8');
 let response;try{response=JSON.parse(raw);}catch{throw new Error('Historical worker returned invalid JSON');}
 if(!response||Object.keys(response).sort().join(',')!=='format,id,result'||response.format!==FORMAT||response.id!==id||!response.result||typeof response.result!=='object'||Array.isArray(response.result)||typeof response.result.valid!=='boolean'||JSON.stringify(response)+'\n'!==raw)throw new Error('Historical worker response differs');
 return response.result;
}
