import {readFileSync,lstatSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {spawnSync} from 'node:child_process';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
export function frozenInputs(root){
 const header=JSON.parse(readFileSync(resolve(root,'scripts/frozen-inputs.json'),'utf8'));
 if(header.format!=='moontxnwitness-frozen-input-index/v1'||!/^[\w.-]+$/.test(header.index))throw Error('Invalid frozen input header');
 const raw=readFileSync(resolve(root,'scripts',header.index));
 if(raw.length!==header.indexBytes||hash(raw)!==header.indexSha256)throw Error('Frozen input index differs');
 const index=JSON.parse(gunzipSync(raw,{maxOutputLength:8*1024*1024}));
 if(Object.keys(index).length!==header.fileCount)throw Error('Frozen input count differs');
 return index;
}
export function prepareInputs(root,scope='tests'){
 const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
 const child=spawnSync(python,['-X','utf8',resolve(root,'scripts/input_cache.py'),'prepare','--scope',scope],{cwd:root,encoding:'utf8',windowsHide:true,timeout:900000,maxBuffer:1024*1024});
 if(child.error||child.status!==0)throw Error('Frozen input preparation failed: '+(child.stdout||child.error?.message||''));
 const result=JSON.parse(child.stdout);if(result.passed!==true)throw Error('Frozen inputs were not verified');return result;
}
