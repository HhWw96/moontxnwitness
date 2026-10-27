// Verify both immutable public028 runtime variants without importing old ESM.
import {lstatSync,readdirSync,openSync,readSync,closeSync,fstatSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {PUBLIC_V028 as PIN} from './legacy-v028-binding.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const ROOT=fileURLToPath(new URL('./legacy/v028/',import.meta.url));
const REQUIRED=['core.mjs','capture-core.mjs','sdk.mjs','evidence.mjs','orm-profile.mjs','classification.mjs','classification-models.mjs','model-profile.mjs','diagnosis.mjs','legacy-v024.mjs','legacy-v025.mjs','legacy-v025-runtime.mjs','legacy-v025-binding.mjs','legacy-v026.mjs','legacy-v026-runtime.mjs','legacy-v026-binding.mjs','legacy-v027.mjs','legacy-v027-runtime.mjs','legacy-v027-binding.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt'];
const IDS=['linux-public-portable','windows-public-source-rebuild'];
const hex=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
function boundedFile(path,max){
 const st=lstatSync(path);if(st.isSymbolicLink()||!st.isFile()||st.size>max)throw Error('Historical028 regular file budget');
 const fd=openSync(path,'r');try{const before=fstatSync(fd);if(!before.isFile()||before.size>max)throw Error('Fixed028 byte budget');const bytes=Buffer.alloc(before.size+1);let total=0;
  for(;;){const n=readSync(fd,bytes,total,bytes.length-total,null);if(!n)break;total+=n;if(total===bytes.length)throw Error('Fixed028 file grew');}
  const after=fstatSync(fd);if(total!==st.size||total!==before.size||after.size!==before.size||after.ino!==before.ino||after.mtimeMs!==before.mtimeMs)throw Error('Fixed028 file changed');return bytes.subarray(0,total);
 }finally{closeSync(fd);}
}
function directory(path){for(let p=resolve(path);;p=resolve(p,'..')){const st=lstatSync(p);if(st.isSymbolicLink()||!st.isDirectory())throw Error('Historical028 ancestor unsafe');if(p===resolve(p,'..'))break;}}
function inventory(path,expected){const found=readdirSync(path,{withFileTypes:true});if(found.some(e=>e.isSymbolicLink())||found.map(e=>e.name).sort().join('\n')!==[...expected].sort().join('\n'))throw Error('Historical028 installed inventory differs');return found;}
export function verifyPublicV028Runtime(runtimeId){
 if(PIN.actualAnonymousDownloadVerified!==true||PIN.version!=='0.2.8'||PIN.sourceCommit!=='bbce5ddbf7159a0ceec821fb8dd6e0c88599f805'||!['manifestSha256','fixtureManifestSha256','workerSha256','policySha256','sourceSha256','portableSha256'].every(k=>hex(PIN[k])))throw Error('Genuine public028 anonymous download/fixtures have not been frozen');
 if(runtimeId!==undefined&&!IDS.includes(runtimeId))throw Error('Unknown fixed028 runtime');directory(ROOT);
 const raw=boundedFile(resolve(ROOT,'manifest.json'),1024*1024);if(sha(raw)!==PIN.manifestSha256)throw Error('Historical028 manifest differs');const m=JSON.parse(raw);
 if(m.format!=='moontxnwitness-frozen-public-dual-runtime/v1'||m.version!=='0.2.8'||m.sourceCommit!==PIN.sourceCommit||m.portableSha256!==PIN.portableSha256||m.sourceSha256!==PIN.sourceSha256||m.fixtureManifestSha256!==PIN.fixtureManifestSha256||m.moduleExecution!=='fixed-current-engine-esm-worker/1'||m.anonymousDownloadVerified!==true||m.rawEsmIdentityPreserved!==true||m.headerRewriting!==false||m.authorDistRead!==false)throw Error('Historical028 provenance differs');
 if(Object.keys(m.variants??{}).sort().join(',')!==IDS.join(','))throw Error('Historical028 runtime variants differ');
 const top=inventory(ROOT,[...IDS,'manifest.json']);if(top.some(e=>e.name==='manifest.json'?!e.isFile():!e.isDirectory()))throw Error('Historical028 root inventory differs');
 let total=0;const variants={};
 for(const id of IDS){
  const folder=resolve(ROOT,id);directory(folder);const vr=boundedFile(resolve(folder,'manifest.json'),1024*1024),binding=m.variants[id];if(sha(vr)!==binding.manifestSha256||sha(vr)!==PIN.runtimeIdentities[id].manifestSha256)throw Error('Historical028 variant manifest differs');const v=JSON.parse(vr);
  if(v.format!=='moontxnwitness-frozen-public-current-runtime/v2'||v.runtimeId!==id||v.sourceCommit!==PIN.sourceCommit||v.version!=='0.2.8'||v.rawEsmIdentityPreserved!==true||v.headerRewriting!==false||v.authorDistRead!==false||v.origin.kind!==(id===IDS[0]?'anonymous-public-portable':'public-source-windows-rebuild'))throw Error('Historical028 variant provenance differs');
  const names=Object.keys(v.files??{});if(names.length!==22||names.sort().join('\n')!==[...REQUIRED].sort().join('\n'))throw Error('Historical028 exact22-file closure differs');let bytes=0;
  for(const name of names){const row=v.files[name];if(!row||Object.keys(row).sort().join(',')!=='bytes,sha256'||!Number.isSafeInteger(row.bytes)||row.bytes<=0||!hex(row.sha256))throw Error('Historical028 file binding invalid');const b=boundedFile(resolve(folder,name),8*1024*1024);bytes+=b.length;if(bytes>8*1024*1024||row.bytes!==b.length||row.sha256!==sha(b))throw Error('Historical028 original file differs: '+id+'/'+name);}
  if(inventory(folder,[...names,'manifest.json']).some(e=>!e.isFile()))throw Error('Historical028 nonflat variant');
  const build=JSON.parse(boundedFile(resolve(folder,'build-manifest.json'),1024*1024));if(build.version!=='0.2.8'||build.sourceSha256!==PIN.sourceFingerprint||build.coreSha256!==v.files['core.mjs'].sha256||build.captureCoreSha256!==v.files['capture-core.mjs'].sha256||build.coreSha256!==PIN.runtimeIdentities[id].coreSha256||build.captureCoreSha256!==PIN.runtimeIdentities[id].captureCoreSha256)throw Error('Historical028 build binding differs');
  for(const [kind,name]of [['classification','classification.mjs'],['models','classification-models.mjs'],['modelProfile','model-profile.mjs'],['diagnosis','diagnosis.mjs']])if(PIN.runtimeIdentities[id].hosts[kind]!==v.files[name].sha256)throw Error('Historical028 host binding differs');
  variants[id]={runtimeRoot:folder,manifest:v,manifestSha256:sha(vr),bytes,files:22};total+=bytes;
 }
 for(const [name,pin]of [['legacy-v028-worker.mjs',PIN.workerSha256],['legacy-v028-policy.mjs',PIN.policySha256]])if(sha(boundedFile(fileURLToPath(new URL('./'+name,import.meta.url)),65536))!==pin)throw Error('Historical028 worker/policy bytes differ');
 return {runtimeRoot:runtimeId?variants[runtimeId].runtimeRoot:ROOT,manifest:m,manifestSha256:sha(raw),variants,files:44,installedFiles:47,bytes:total};
}
