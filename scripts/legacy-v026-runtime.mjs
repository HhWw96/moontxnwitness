// Copy the fixed public26 closure only after validating its fixed source pin.
import {copyFileSync,mkdirSync,readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
export async function copyFrozenLegacyV026(root,output){
 const module=await import(pathToFileURL(resolve(root,'cmd/legacy-v026-runtime.mjs')).href),checked=module.verifyPublicV026Runtime();
 for(const name of [...Object.keys(checked.manifest.files),'manifest.json']){const target=resolve(output,'legacy/v026',name);mkdirSync(dirname(target),{recursive:true});copyFileSync(resolve(root,'cmd/legacy/v026',name),target);}
 const installed=await import(pathToFileURL(resolve(output,'legacy-v026-runtime.mjs')).href);const verified=installed.verifyPublicV026Runtime();if(verified.manifestSha256!==checked.manifestSha256)throw new Error('Installed historical25 manifest differs');
 return {verified:true,manifestSha256:checked.manifestSha256,workerSha256:checked.workerSha256,files:Object.keys(checked.manifest.files).length};
}
