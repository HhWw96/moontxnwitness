// Assemble only an internal fixed PIN. This module never accepts capsule paths,
// selects an algorithm, starts a worker, or changes an installed runtime.
import {constants,lstatSync,readdirSync,openSync,closeSync,readSync,writeSync,
  linkSync,mkdirSync,mkdtempSync,unlinkSync,rmdirSync,fstatSync,fsyncSync,statfsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,dirname,join,relative,isAbsolute,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';

const MiB=1024*1024;
export const COMPACT_RUNTIME_LIMITS=Object.freeze({files:20000,memberBytes:32*MiB,
  totalBytes:1024*MiB,pinBytes:8*MiB,pathBytes:1024,depth:32,minimumFreeBytes:500*MiB});
const own=(value,key)=>Object.hasOwn(value,key);
const scratch=Buffer.allocUnsafe(MiB);
function fail(message){throw new Error('Compact runtime: '+message);}
function dataObject(value,label){
  if(value===null||typeof value!=='object'||Array.isArray(value)||
      ![Object.prototype,null].includes(Object.getPrototypeOf(value)))fail(label+' must be a plain object');
  if(Object.getOwnPropertySymbols(value).length)fail(label+' has symbol fields');
  for(const descriptor of Object.values(Object.getOwnPropertyDescriptors(value)))
    if(!own(descriptor,'value'))fail(label+' must contain data fields only');
  return value;
}
function member(value){
  if(typeof value!=='string'||!value||Buffer.byteLength(value)>COMPACT_RUNTIME_LIMITS.pathBytes||
      /[\\\u0000-\u001f\u007f<>:"|?*]/.test(value))fail('unsafe member path');
  const parts=value.split('/');
  if(parts.length>COMPACT_RUNTIME_LIMITS.depth||parts.some(part=>!part||part==='.'||part==='..'||
      /[ .]$/.test(part)||/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part)))fail('unsafe member path');
  return parts;
}
function directoryChain(path){
  path=resolve(path);
  const parents=[];
  for(let p=path;;p=dirname(p)){parents.push(p);if(p===dirname(p))break;}
  for(const p of parents.reverse()){
    const st=lstatSync(p);
    if(!st.isDirectory()||st.isSymbolicLink())fail('directory link or non-directory');
  }
  return path;
}
function identity(a,b){return a.dev===b.dev&&a.ino===b.ino;}
function sameFileStamp(a,b){
  return identity(a,b)&&a.size===b.size&&a.mode===b.mode&&a.nlink===b.nlink&&
    a.mtimeNs===b.mtimeNs&&a.ctimeNs===b.ctimeNs&&
    a.mtimeMs===b.mtimeMs&&a.ctimeMs===b.ctimeMs;
}
// Link creation/removal changes ctime without changing file content. Never use
// such observations to reuse a digest. Genuine content/identity changes fail.
function linkOnlyStampChange(a,b){
  return identity(a,b)&&a.size===b.size&&a.mode===b.mode&&
    a.mtimeNs===b.mtimeNs&&a.mtimeMs===b.mtimeMs&&a.nlink!==b.nlink;
}
function regularFile(path,spec){
  // Metadata is useful for detecting changes, never proof of unchanged bytes.
  // Hash every selected pathname, including aliases of a previously read inode.
  for(let attempt=0;attempt<3;attempt++){
    directoryChain(dirname(path));
    const before=lstatSync(path,{bigint:true});
    if(!before.isFile()||before.isSymbolicLink()||before.size!==BigInt(spec.bytes))fail('member shape or size differs');
    const fd=openSync(path,constants.O_RDONLY|(constants.O_NOFOLLOW||0));
    try{
      const opened=fstatSync(fd,{bigint:true});
      if(!opened.isFile()||opened.size!==BigInt(spec.bytes)||
          !sameFileStamp(opened,before)&&!linkOnlyStampChange(before,opened))fail('member identity or metadata differs');
      const digest=createHash('sha256');let count=0;
      for(;;){
        const n=readSync(fd,scratch,0,Math.min(scratch.length,spec.bytes-count+1),null);
        if(!n)break;
        count+=n;if(count>spec.bytes)fail('member read budget exceeded');
        digest.update(scratch.subarray(0,n));
      }
      const checksum=digest.digest('hex');
      const finalDescriptor=fstatSync(fd,{bigint:true}),after=lstatSync(path,{bigint:true});
      if(count!==spec.bytes||checksum!==spec.sha256||!after.isFile()||after.isSymbolicLink())fail('member checksum or identity differs');
      if(!sameFileStamp(opened,finalDescriptor)||!sameFileStamp(finalDescriptor,after)){
        const linkOrSame=(a,b)=>sameFileStamp(a,b)||linkOnlyStampChange(a,b);
        if(!linkOrSame(opened,finalDescriptor)||!linkOrSame(finalDescriptor,after))fail('member checksum or identity differs');
        if(attempt===2)fail('member concurrent link metadata did not stabilize');
        continue;
      }
      return opened;
    }finally{closeSync(fd);}
  }
}

function diskSpace(path,pending=0){
  const info=statfsSync(path,{bigint:true});
  if(info.bavail*info.bsize-BigInt(pending)<BigInt(COMPACT_RUNTIME_LIMITS.minimumFreeBytes))
    fail('less than 500 MiB available for temporary runtime');
}
function normalizePin(pin){
  dataObject(pin,'PIN');if(!own(pin,'version')||!own(pin,'files'))fail('missing fixed PIN fields');
  dataObject(pin.files,'PIN files');
  if(typeof pin.version!=='string'||pin.version.length>32||!/^\d+\.\d+\.\d+$/.test(pin.version))fail('invalid fixed version');
  const rows=Object.entries(pin.files);
  if(!rows.length||rows.length>COMPACT_RUNTIME_LIMITS.files)fail('file count budget exceeded');
  const aliases=new Map(),files=new Map(),directories=new Set(),sources=new Map();
  let total=0,pinBytes=0;
  function alias(path){
    const parts=member(path);
    for(let n=1;n<=parts.length;n++){
      const name=parts.slice(0,n).join('/'),key=name.normalize('NFC').toLowerCase();
      if(aliases.has(key)&&aliases.get(key)!==name)fail('case or normalization collision');
      aliases.set(key,name);
    }
    return parts;
  }
  for(const [name,raw] of rows){
    const parts=alias(name);dataObject(raw,'PIN member');
    if(Object.keys(raw).sort().join(',')!=='bytes,sha256,source')fail('unknown PIN member field');
    if(!Number.isSafeInteger(raw.bytes)||raw.bytes<0||raw.bytes>COMPACT_RUNTIME_LIMITS.memberBytes||
        typeof raw.sha256!=='string'||!/^[a-f0-9]{64}$/.test(raw.sha256))fail('member budget or checksum invalid');
    member(raw.source);
    if(!raw.source.startsWith('legacy/')&&!raw.source.startsWith('legacy-components/v032/')&&!raw.source.startsWith('legacy-components/v033/'))fail('source is outside immutable installed components');
    pinBytes+=Buffer.byteLength(name)+Buffer.byteLength(raw.source)+96;
    total+=raw.bytes;
    if(total>COMPACT_RUNTIME_LIMITS.totalBytes||pinBytes>COMPACT_RUNTIME_LIMITS.pinBytes)fail('total runtime or PIN budget exceeded');
    const spec=Object.freeze({bytes:raw.bytes,sha256:raw.sha256,source:raw.source});
    const prior=sources.get(spec.source);
    if(prior&&(prior.bytes!==spec.bytes||prior.sha256!==spec.sha256))fail('conflicting source identity');
    sources.set(spec.source,spec);files.set(name,spec);
    for(let n=1;n<parts.length;n++)directories.add(parts.slice(0,n).join('/'));
  }
  for(const name of files.keys())if(directories.has(name))fail('file/directory collision');
  const sourceAliases=new Map();
  for(const source of sources.keys())for(let n=1,p=member(source);n<=p.length;n++){
    const name=p.slice(0,n).join('/'),key=name.normalize('NFC').toLowerCase();
    if(sourceAliases.has(key)&&sourceAliases.get(key)!==name)fail('source path case collision');
    sourceAliases.set(key,name);
  }
  return {version:pin.version,files,directories,sources,total};
}
function verifySources(installation,pin){
  directoryChain(installation);
  const stats=new Map();
  for(const [source,spec]of pin.sources)stats.set(source,regularFile(join(installation,...member(source)),spec));
  return stats;
}
function originalDirectory(root,id){
  directoryChain(dirname(root));
  const st=lstatSync(root);
  if(!st.isDirectory()||st.isSymbolicLink()||!identity(st,id))fail('private runtime directory identity differs');
}
function verifyTree(root,id,pin){
  originalDirectory(root,id);const seen=new Set();
  function inspect(path,prefix=''){
    for(const name of readdirSync(path)){
      const rel=prefix+name,target=join(path,name),st=lstatSync(target);
      if(st.isSymbolicLink())fail('runtime contains a link');
      if(st.isDirectory()){
        if(!pin.directories.has(rel))fail('unexpected runtime directory');
        directoryChain(target);inspect(target,rel+'/');
      }else if(st.isFile()&&pin.files.has(rel)){
        regularFile(target,pin.files.get(rel));seen.add(rel);
      }else fail('unexpected runtime member');
    }
  }
  inspect(root);
  if(seen.size!==pin.files.size)fail('runtime inventory differs');
}
function copyExclusive(source,target,spec,temporaryRoot){
  diskSpace(temporaryRoot,spec.bytes);
  const input=openSync(source,constants.O_RDONLY|(constants.O_NOFOLLOW||0));
  let output;
  try{
    const opened=fstatSync(input),current=lstatSync(source);
    if(!opened.isFile()||opened.size!==spec.bytes||!current.isFile()||current.isSymbolicLink()||!identity(opened,current))fail('copy source identity differs');
    output=openSync(target,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL,0o600);
    const digest=createHash('sha256');let count=0;
    for(;;){
      const n=readSync(input,scratch,0,Math.min(scratch.length,spec.bytes-count+1),null);
      if(!n)break;
      count+=n;if(count>spec.bytes)fail('copy input budget exceeded');
      digest.update(scratch.subarray(0,n));let written=0;
      while(written<n){
        diskSpace(temporaryRoot,n-written);
        const size=writeSync(output,scratch,written,n-written,null);
        if(size<=0)fail('copy made no progress');written+=size;
      }
    }
    if(count!==spec.bytes||digest.digest('hex')!==spec.sha256)fail('copied member differs');
    fsyncSync(output);
  }finally{
    closeSync(input);if(output!==undefined)closeSync(output);
  }
  regularFile(target,spec);
}
function removeOwnedTree(root,id){
  originalDirectory(root,id);
  function remove(path){
    originalDirectory(root,id);directoryChain(dirname(path));
    const st=lstatSync(path);
    if(st.isSymbolicLink()){unlinkSync(path);return;}
    if(st.isDirectory()){
      directoryChain(path);
      for(const name of readdirSync(path))remove(join(path,name));
      rmdirSync(path);
    }else if(st.isFile())unlinkSync(path);
    else fail('refusing to clean an unexpected filesystem object');
  }
  for(const name of readdirSync(root))remove(join(root,name));
  originalDirectory(root,id);rmdirSync(root);
}

/**
 * Internal fixed-PIN loader. installationRoot is the installed dist directory.
 * Each instance owns one process-private temporary tree. Unreferenced files in
 * the shared legacy source pools are inert; the assembled tree inventory is exact.
 * get()/verify() always revalidate every used source path and the complete destination.
 * Every source and destination pathname is fully hashed on each validation.
 * A damaged tree is poisoned and never repaired. cleanup() is explicit; process
 * exit also attempts cleanup. No files are created in installationRoot.
 */
export function createCompactRuntimeLoader(pin,{installationRoot=dirname(fileURLToPath(import.meta.url)),temporaryRoot=tmpdir()}={}){
  const fixed=normalizePin(pin),installation=resolve(installationRoot),temporary=resolve(temporaryRoot);
  const overlap=relative(installation,temporary);
  if(overlap===''||!isAbsolute(overlap)&&overlap!=='..'&&!overlap.startsWith('..'+sep))fail('temporary root must be outside installation');
  let state='new',root,id,failure;
  function cleanup(){
    if(state==='disposed')return false;
    process.removeListener('exit',onExit);
    if(root){removeOwnedTree(root,id);root=undefined;}
    state='disposed';return true;
  }
  function onExit(){try{cleanup();}catch{/* private cleanup is best effort after exit */}}
  function get(){
    if(state==='failed')fail('previous validation failed; create a new loader after diagnosis: '+failure);
    if(state==='disposed')fail('loader is disposed');
    const existing=state==='ready';
    try{
      directoryChain(temporary);const sourceStats=verifySources(installation,fixed);
      if(!root){
        diskSpace(temporary);
        root=mkdtempSync(join(temporary,'moontxnwitness-compact-'+process.pid+'-'));
        id=lstatSync(root);process.once('exit',onExit);
        for(const [name,spec]of fixed.files){
          const target=join(root,...member(name)),source=join(installation,...member(spec.source));
          let directory=root;
          for(const part of member(name).slice(0,-1)){
            directory=join(directory,part);
            try{mkdirSync(directory,0o700);}catch(error){if(error.code!=='EEXIST')throw error;}
            directoryChain(directory);
          }
          diskSpace(temporary);
          // A readonly inode may not be unlinkable on Windows. Copy it without
          // changing the source's permissions or readonly file attributes.
          if((sourceStats.get(spec.source).mode&0o200n)===0n)copyExclusive(source,target,spec,temporary);
          else try{linkSync(source,target);}catch(error){
            if(error.code==='EEXIST')throw error;
            copyExclusive(source,target,spec,temporary);
          }
        }
      }
      verifySources(installation,fixed);verifyTree(root,id,fixed);
      state='ready';return root;
    }catch(error){
      failure=error.message;state='failed';
      if(!existing&&root){try{removeOwnedTree(root,id);root=undefined;process.removeListener('exit',onExit);}catch{/* keep ownership for explicit/exit cleanup */}}
      throw error;
    }
  }
  return Object.freeze({get,verify:get,cleanup});
}
