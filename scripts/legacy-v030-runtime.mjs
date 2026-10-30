import {spawnSync} from 'node:child_process';
import {readFileSync,copyFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';

export async function copyPublic030(root,output){
 const python=process.env.MTW_PYTHON||process.env.PYTHON||(process.platform==='win32'?'python':'python3');
 const prepared=spawnSync(python,['-X','utf8',resolve(root,'scripts/prepare_public030.py'),root],{encoding:'utf8',windowsHide:true,timeout:300000,maxBuffer:1024*1024});
 if(prepared.error||prepared.status!==0)throw Error('Cannot prepare pinned public030 runtime: '+(prepared.stderr||''));
 const source=resolve(root,'artifacts/compat-v030/runtime'),manifest=JSON.parse(readFileSync(resolve(source,'public-runtime-manifest.json')));
 for(const name of [...Object.keys(manifest.files),'public-runtime-manifest.json']){
  const destination=resolve(output,'legacy/v030',name);mkdirSync(dirname(destination),{recursive:true});copyFileSync(resolve(source,name),destination);
 }
 copyFileSync(resolve(root,'cmd/legacy-v030.mjs'),resolve(output,'legacy-v030.mjs'));
 const installed=await import(pathToFileURL(resolve(output,'legacy-v030.mjs')).href);installed.verifyPublic030Runtime();
}
