import {copyFileSync,mkdirSync} from 'node:fs';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';
export async function copyFrozenLegacyV028(root,output){
 const original=await import(pathToFileURL(resolve(root,'cmd/legacy-v028-runtime.mjs')).href),verified=original.verifyPublicV028Runtime();
 mkdirSync(resolve(output,'legacy/v028'),{recursive:true});copyFileSync(resolve(verified.runtimeRoot,'manifest.json'),resolve(output,'legacy/v028/manifest.json'));
 for(const [id,v]of Object.entries(verified.variants)){mkdirSync(resolve(output,'legacy/v028',id),{recursive:true});for(const name of [...Object.keys(v.manifest.files),'manifest.json'])copyFileSync(resolve(v.runtimeRoot,name),resolve(output,'legacy/v028',id,name));}
 const installed=await import(pathToFileURL(resolve(output,'legacy-v028-runtime.mjs')).href),checked=installed.verifyPublicV028Runtime();if(checked.manifestSha256!==verified.manifestSha256)throw Error('Installed genuine028 runtime differs');return {verified:true,files:66,installedFiles:70,bytes:checked.bytes,manifestSha256:checked.manifestSha256};
}
