// Fixed single-worker bridge. No request accepts path/module or env selectors.
import {spawnSync} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {verifyPublicV028Runtime} from './legacy-v028-runtime.mjs';
import {FORMAT,MAX_BYTES,assertOperation028} from './legacy-v028-policy.mjs';
export function callLegacyV028(operation,args){
 if(process.env.MTW_FIXED_WORKER_DEPTH)throw Error('Nested historical worker refused');
 const {runtimeId}=assertOperation028(operation,args);verifyPublicV028Runtime(runtimeId??undefined);
 const id=randomBytes(16).toString('hex'),input=Buffer.from(JSON.stringify({format:FORMAT,id,operation,arguments:args})+'\n');if(input.length>MAX_BYTES)throw Error('Historical028 input budget');
 const env={TZ:'UTC',MTW_FIXED_WORKER_DEPTH:'1'};for(const [k,v]of Object.entries(process.env))if(['systemroot','windir','systemdrive','temp','tmp','tmpdir'].includes(k.toLowerCase()))env[k]=v;
 const child=spawnSync(process.execPath,['--no-addons',fileURLToPath(new URL('./legacy-v028-worker.mjs',import.meta.url))],{input,encoding:null,env,cwd:fileURLToPath(new URL('.',import.meta.url)),windowsHide:true,timeout:300000,killSignal:'SIGKILL',maxBuffer:MAX_BYTES});
 if(child.error||child.status!==0||child.signal||child.stderr?.length||!Buffer.isBuffer(child.stdout)||child.stdout.length>MAX_BYTES)throw Error('Fixed public028 worker failed');
 const text=child.stdout.toString('utf8');if(!Buffer.from(text,'utf8').equals(child.stdout))throw Error('Historical028 output UTF8');const r=JSON.parse(text);
 if(!r||Object.keys(r).sort().join(',')!=='format,id,result'||r.format!==FORMAT||r.id!==id||!r.result||Array.isArray(r.result)||typeof r.result.valid!=='boolean'||JSON.stringify(r)+'\n'!==text)throw Error('Historical028 response differs');return r.result;
}
