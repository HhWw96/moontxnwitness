// Only the small published top-level component is installed. Nested immutable
// files are referenced from the existing legacy pool and assembled on replay.
import {constants,readFileSync,lstatSync,mkdirSync,linkSync,copyFileSync,openSync,closeSync,fstatSync,readSync,writeFileSync,fsyncSync,mkdtempSync,renameSync,unlinkSync,rmdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {createCompactRuntimeLoader as validateFixedPin} from '../cmd/compact-runtime.mjs';
const sha=raw=>createHash('sha256').update(raw).digest('hex');
function directories(path,create=false){
 const chain=[];for(let p=resolve(path);;p=dirname(p)){chain.push(p);if(p===dirname(p))break;}
 for(const p of chain.reverse()){
  let st;
  try{st=lstatSync(p);}catch(error){
   if(error.code!=='ENOENT'||!create)throw error;
   try{mkdirSync(p);}catch(race){if(race.code!=='EEXIST')throw race;}
   st=lstatSync(p);
  }
  if(!st.isDirectory()||st.isSymbolicLink())throw Error('Unsafe component directory');
 }
}
function verify(path,spec){
 const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink()||st.size!==spec.bytes||sha(readFileSync(path))!==spec.sha256)throw Error('Published032 component differs');
}
function safeHelperBytes(path){
 directories(dirname(path));const before=lstatSync(path);
 if(!before.isFile()||before.isSymbolicLink()||before.size>8*1024*1024)throw Error('Unsafe compatibility helper source');
 const fd=openSync(path,constants.O_RDONLY|(constants.O_NOFOLLOW||0));
 try{
  const opened=fstatSync(fd);
  if(!opened.isFile()||opened.dev!==before.dev||opened.ino!==before.ino||opened.size!==before.size)throw Error('Compatibility helper source identity changed');
  const raw=Buffer.alloc(opened.size+1);let count=0;
  while(count<raw.length){const n=readSync(fd,raw,count,raw.length-count,null);if(!n)break;count+=n;}
  const after=lstatSync(path);
  if(count!==opened.size||!after.isFile()||after.isSymbolicLink()||after.dev!==opened.dev||after.ino!==opened.ino||after.size!==opened.size)throw Error('Compatibility helper source changed');
  return raw.subarray(0,count);
 }finally{closeSync(fd);}
}
function helperTarget(path){
 try{const st=lstatSync(path);if(!st.isFile()||st.isSymbolicLink())throw Error('Unsafe compatibility helper target');}
 catch(error){if(error.code!=='ENOENT')throw error;}
}
function installHelper(raw,target){
 if(!Buffer.isBuffer(raw))throw Error('Helper snapshot required');directories(dirname(target));helperTarget(target);
 const temporary=mkdtempSync(resolve(dirname(target),'.compat-helper-')),id=lstatSync(temporary),pending=resolve(temporary,'module.mjs');
 try{
  const fd=openSync(pending,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL,0o600);
  try{writeFileSync(fd,raw);fsyncSync(fd);}finally{closeSync(fd);}
  helperTarget(target);directories(dirname(target));
  // Atomic replacement never opens or follows a target link. A pre-existing
  // link is refused; a racing link can only be replaced as an entry itself.
  renameSync(pending,target);
 }finally{
  const current=lstatSync(temporary);
  if(!current.isDirectory()||current.isSymbolicLink()||current.dev!==id.dev||current.ino!==id.ino)throw Error('Private helper staging identity changed');
  try{unlinkSync(pending);}catch(error){if(error.code!=='ENOENT')throw error;}
  rmdirSync(temporary);
 }
}
export async function copyPublic032(root,output){
 const snapshots=Object.fromEntries(['legacy-v032.mjs','legacy-v032-binding.mjs','compact-runtime.mjs'].map(name=>[name,safeHelperBytes(resolve(root,'cmd',name))]));
 const binding=snapshots['legacy-v032-binding.mjs'],text=binding.toString('utf8');
 const prefix='export const PUBLIC032=Object.freeze(';
 const suffix=');\nfor(const e of Object.values(PUBLIC032.files))Object.freeze(e);\nObject.freeze(PUBLIC032.files);\n';
 if(!Buffer.from(text,'utf8').equals(binding)||!text.startsWith(prefix)||!text.endsWith(suffix))throw Error('Unexpected pure compatibility binding');
 const encoded=text.slice(prefix.length,-suffix.length),PIN=JSON.parse(encoded);
 if(JSON.stringify(PIN)!==encoded)throw Error('Noncanonical compatibility binding');
 // Validate all fixed member/source paths and budgets before filesystem writes.
 const metadataGuard=validateFixedPin(PIN,{installationRoot:output});metadataGuard.cleanup();
 for(const spec of Object.values(PIN.files)){
  if(!spec.source.startsWith('legacy-components/v032/'))continue;
  const from=resolve(root,'cmd',spec.source),to=resolve(output,spec.source);
  directories(dirname(from));verify(from,spec);directories(dirname(to),true);
  try{linkSync(from,to);}catch(error){
   if(error.code==='EEXIST')verify(to,spec);
   else copyFileSync(from,to,constants.COPYFILE_EXCL);
  }
  verify(to,spec);
 }
 directories(resolve(root,'cmd'));directories(resolve(output));
 for(const name of ['legacy-v032.mjs','legacy-v032-binding.mjs','compact-runtime.mjs'])installHelper(snapshots[name],resolve(output,name));
 // Validation uses a temporary full inventory; no nested version snapshot is
 // stored under dist. The worker creates and disposes its own private inventory.
 const {createCompactRuntimeLoader}=await import(pathToFileURL(resolve(output,'compact-runtime.mjs')).href);
 const loader=createCompactRuntimeLoader(PIN,{installationRoot:output});
 try{loader.get();}finally{loader.cleanup();}
}
