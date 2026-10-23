// Copy the fixed public25 closure only after validating its fixed source pin.
import {copyFileSync,mkdirSync,readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
export async function copyFrozenLegacyV025(root,output){
 const module=await import(pathToFileURL(resolve(root,'cmd/legacy-v025-runtime.mjs')).href),checked=module.verifyPublicV025Runtime();
 for(const name of [...Object.keys(checked.manifest.files),'manifest.json']){const target=resolve(output,'legacy/v025',name);mkdirSync(dirname(target),{recursive:true});copyFileSync(resolve(root,'cmd/legacy/v025',name),target);}
 const installed=await import(pathToFileURL(resolve(output,'legacy-v025-runtime.mjs')).href);const verified=installed.verifyPublicV025Runtime();if(verified.manifestSha256!==checked.manifestSha256)throw new Error('Installed historical25 manifest differs');
 return {verified:true,manifestSha256:checked.manifestSha256,workerSha256:checked.workerSha256,files:Object.keys(checked.manifest.files).length};
}
