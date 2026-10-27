// Own-engine-only worker: original published028 ESM bytes remain unchanged.
import fs from 'node:fs';import cp from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';import {pathToFileURL,fileURLToPath} from 'node:url';import {resolve} from 'node:path';
import {FORMAT,MAX_BYTES,assertOperation028} from './legacy-v028-policy.mjs';
import {verifyPublicV028Runtime} from './legacy-v028-runtime.mjs';
// Block every process launcher before any historical ESM is imported.
for(const name of ['spawn','spawnSync','exec','execSync','execFile','execFileSync','fork'])cp[name]=()=>{throw Error('Nested worker forbidden');};
for(const name of ['readFileSync','lstatSync','readdirSync','openSync']){const original=fs[name];fs[name]=function(path,...rest){const p=String(path instanceof URL?fileURLToPath(path):path).replaceAll(String.fromCharCode(92),'/');if(/\/legacy\/v0(?:24|25|26|27)(?:\/|$)/.test(p))throw Error('Nested historical payload forbidden');return original(path,...rest);};}syncBuiltinESMExports();
try{
 if(process.argv.length!==2||process.env.MTW_FIXED_WORKER_DEPTH!=='1')throw Error('No selectors or nested worker');let size=0;const chunks=[];for await(const b of process.stdin){size+=b.length;if(size>MAX_BYTES)throw Error('Historical028 input budget');chunks.push(b);}
 const raw=Buffer.concat(chunks),text=raw.toString('utf8');if(!Buffer.from(text,'utf8').equals(raw))throw Error('Historical028 input UTF8');const q=JSON.parse(text);
 if(!q||Object.keys(q).sort().join(',')!=='arguments,format,id,operation'||q.format!==FORMAT||!/^[0-9a-f]{32}$/.test(q.id)||JSON.stringify(q)+'\n'!==text)throw Error('Fixed028 request differs');
 const {name,method,runtimeId}=assertOperation028(q.operation,q.arguments),runtime=verifyPublicV028Runtime(runtimeId);const host=await import(pathToFileURL(resolve(runtime.runtimeRoot,name)).href),result=host[method](...q.arguments);
 if(!result||Array.isArray(result)||typeof result.valid!=='boolean')throw Error('Historical028 result differs');const output=Buffer.from(JSON.stringify({format:FORMAT,id:q.id,result})+'\n');if(output.length>MAX_BYTES)throw Error('Historical028 output budget');await new Promise((ok,no)=>process.stdout.write(output,e=>e?no(e):ok()));
}catch{process.stderr.write('Fixed public028 worker refused the request.\n');process.exitCode=2;}
