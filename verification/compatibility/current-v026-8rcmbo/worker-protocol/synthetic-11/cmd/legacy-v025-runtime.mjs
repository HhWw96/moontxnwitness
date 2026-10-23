// Verify fixed installed bytes. No request supplies a path, module or manifest.
import {readFileSync,lstatSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {PUBLIC_V025} from './legacy-v025-binding.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const EXPECTED_SOURCE='6b3434b19fc080bc9a3a9518950021061d2849dd';
const ROOT=fileURLToPath(new URL('./legacy/v025/',import.meta.url));
const SAFE=name=>typeof name==='string'&&name.length>0&&!name.includes('\\')&&!name.includes(':')&&!name.startsWith('/')&&name.split('/').every(s=>s&&s!=='.'&&s!=='..');
function readFixed(name,limit){
 if(!SAFE(name))throw new Error('Unsafe fixed historical runtime name');
 const path=resolve(ROOT,name),rel=relative(ROOT,path);
 if(rel==='..'||rel.startsWith('..'+sep))throw new Error('Historical runtime escaped fixed root');
 let cursor=ROOT;
 const root=lstatSync(ROOT);if(root.isSymbolicLink()||!root.isDirectory())throw new Error('Fixed historical runtime is not a regular directory');
 for(const component of name.split('/')){cursor=resolve(cursor,component);if(lstatSync(cursor).isSymbolicLink())throw new Error('Historical runtime symlink refused');}
 const info=lstatSync(path);if(!info.isFile()||info.size>limit)throw new Error('Historical runtime entry exceeds regular-file budget');
 const raw=readFileSync(path);if(raw.length>limit||raw.length!==info.size)throw new Error('Historical runtime entry changed during verification');return raw;
}
export function verifyPublicV025Runtime(){
 if(PUBLIC_V025.version!=='0.2.5'||PUBLIC_V025.sourceCommit!==EXPECTED_SOURCE||!(/^[0-9a-f]{64}$/).test(PUBLIC_V025.manifestSha256)||!(/^[0-9a-f]{64}$/).test(PUBLIC_V025.workerSha256))throw new Error('Genuine public25 runtime has not been frozen');
 const raw=readFixed('manifest.json',1024*1024);if(sha(raw)!==PUBLIC_V025.manifestSha256)throw new Error('Fixed public25 manifest differs');
 const value=JSON.parse(raw);
 if(value.format!=='moontxnwitness-frozen-public-runtime/v1'||value.version!=='0.2.5'||value.sourceCommit!==EXPECTED_SOURCE||value.moduleExecution!=='fixed-esm-worker/1'||value.actualPublishedProducer!==true||value.rawEsmIdentityPreserved!==true||value.headerRewriting!==false||value.authorDistRead!==false||!(/^[0-9a-f]{64}$/).test(value.fixtureManifestSha256))throw new Error('Unsupported fixed public25 manifest');
 if(!value.files||typeof value.files!=='object'||Array.isArray(value.files))throw new Error('Invalid fixed public25 file manifest');
 const names=Object.keys(value.files);if(names.length<7||names.length>128||names.some(n=>!SAFE(n)||n==='manifest.json'))throw new Error('Fixed public25 file list differs');
 for(const required of ['core.mjs','orm-profile.mjs','classification.mjs','legacy-v024.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt','origin.json'])if(!names.includes(required))throw new Error('Fixed public25 closure missing '+required);
 let total=0;
 for(const name of names){const expected=value.files[name];if(!expected||Object.keys(expected).sort().join(',')!=='bytes,sha256'||!Number.isSafeInteger(expected.bytes)||expected.bytes<0||expected.bytes>32*1024*1024||!(/^[0-9a-f]{64}$/).test(expected.sha256))throw new Error('Invalid fixed public25 file binding');const bytes=readFixed(name,32*1024*1024);total+=bytes.length;if(total>128*1024*1024||bytes.length!==expected.bytes||sha(bytes)!==expected.sha256)throw new Error('Fixed public25 file differs: '+name);}
 const found=[];function visit(folder,prefix=''){for(const entry of readdirSync(folder,{withFileTypes:true})){const name=prefix+entry.name;if(entry.isSymbolicLink())throw new Error('Unexpected historical symlink');if(entry.isDirectory())visit(resolve(folder,entry.name),name+'/');else if(entry.isFile())found.push(name);else throw new Error('Unexpected historical file type');}}visit(ROOT);
 if(found.sort().join('\n')!==[...names,'manifest.json'].sort().join('\n'))throw new Error('Fixed public25 installed closure differs');
 const worker=readFileSync(new URL('./legacy-v025-worker.mjs',import.meta.url));if(sha(worker)!==PUBLIC_V025.workerSha256)throw new Error('Fixed public25 worker differs');
 return {manifest:value,manifestSha256:sha(raw),runtimeRoot:ROOT,workerSha256:sha(worker)};
}
