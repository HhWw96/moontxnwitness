import {PUBLIC031 as PIN} from '../cmd/legacy-v031-binding.mjs';
import {readFileSync,lstatSync,mkdirSync,linkSync,copyFileSync,constants} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const hash=b=>createHash('sha256').update(b).digest('hex');
export async function copyPublic031(root,output){
 const source=resolve(root,'artifacts/compat-v031/runtime');
 for(const name of Object.keys(PIN.files)){
  const from=resolve(source,name),to=resolve(output,'legacy/v031',name),expected=PIN.files[name];
  if(lstatSync(from).isSymbolicLink()||hash(readFileSync(from))!==expected.sha256)throw Error('Prepared public031 runtime differs');
  mkdirSync(dirname(to),{recursive:true});
  try{linkSync(from,to);}catch(e){
   if(e.code==='EEXIST'){if(lstatSync(to).isSymbolicLink()||hash(readFileSync(to))!==expected.sha256)throw Error('Existing public031 destination differs');}
   else copyFileSync(from,to,constants.COPYFILE_EXCL);
  }
 }
 for(const name of ['legacy-v031.mjs','legacy-v031-binding.mjs'])copyFileSync(resolve(root,'cmd',name),resolve(output,name));
 const installed=await import(pathToFileURL(resolve(output,'legacy-v031.mjs')).href);installed.verifyPublic031Runtime();
}
