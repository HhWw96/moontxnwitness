// Fixed public24 module wrappers. No capsule-provided source or paths are executed.
import assert from 'node:assert/strict';
import {readFileSync,readdirSync,existsSync,mkdirSync,writeFileSync,copyFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
export const PUBLIC_V024_SOURCE='d583cb4f3cb1c4da4cc63e2ce255cc8834b08e2a';
export const PUBLIC_V024_FIXTURE_SHA='f5bb94653aaa16ff98510a86f6585ebe1da2aabbdbd27f8576c80c6b7a8762dd';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const encode=value=>Buffer.from(JSON.stringify(value,null,2)+'\n');
const ORIGINAL=['core.mjs','orm-profile.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt'];
function wrapCore(text){
 const tail=/^export \{ ([^\r\n{}]+) \}\r?\n?$/.exec(text.slice(text.lastIndexOf('\nexport ')+1));
 assert.ok(tail,'Unknown original24 core export syntax');
 const at=text.lastIndexOf('\nexport ')+1,body=text.slice(0,at);
 assert.ok(at>0&&!/^(?:import|export)\b/m.test(body)&&!/(?:\bimport\s*\(|import\.meta)/.test(body),'Unexpected core module syntax');
 const fields=tail[1].split(', ').map(field=>{
  const match=/^([A-Za-z_$][\w$]*) as ([A-Za-z_$][\w$]*)$/.exec(field);
  assert.ok(match,'Unknown original24 core export binding');return [match[2],match[1]];
 });
 assert.equal(new Set(fields.map(f=>f[0])).size,fields.length);
 for(const needed of ['orm_profile_source_v3_json','shrink_options_json','analyze_options_json','replay_report_json','version'])assert.ok(fields.some(f=>f[0]===needed));
 return Buffer.from('"use strict";\nmodule.exports=(function(){"use strict";\n'+body+'\nreturn Object.freeze({'+fields.map(([name,binding])=>JSON.stringify(name)+':'+binding).join(',')+'});\n}).call(undefined);\n');
}
function wrapOrm(text){
 const imports=["import {createHash} from 'node:crypto';","import {orm_profile_source_v3_json, shrink_options_json, analyze_options_json, replay_report_json, version} from './core.mjs';"];
 const functions=['analyzeOrmProfileV3','reduceOrmProfileV3','verifyOrmProfileV3','replayOrmProfileCapsuleV3'];
 const constants=['makeOrmProfileCapsuleV3','makeOrmProfileReductionCapsuleV3'];
 const foundImports=[],foundExports=[],lines=[];
 for(const raw of text.match(/[^\n]*\n|[^\n]+$/g)??[]){
  const line=raw.replace(/\r?\n$/,'');
  if(line.startsWith('import ')){assert.ok(imports.includes(line),'Unknown original24 ORM import');foundImports.push(line);continue;}
  if(line.startsWith('export ')){
   const match=/^export (?:function|const) ([A-Za-z_$][\w$]*)/.exec(line);assert.ok(match,'Unknown ORM export syntax');
   assert.ok((line.startsWith('export function ')?functions:constants).includes(match[1]),'Unknown ORM export binding');
   foundExports.push(match[1]);lines.push(raw.slice('export '.length));
  }else lines.push(raw);
 }
 assert.deepEqual(foundImports,imports);assert.deepEqual([...foundExports].sort(),[...functions,...constants].sort());
 const body=lines.join('');assert.ok(!/^(?:import|export)\b/m.test(body)&&!/(?:\bimport\s*\(|import\.meta)/.test(body),'Unexpected ORM module syntax');
 return Buffer.from('"use strict";\nmodule.exports=(function(createHash,__mtw_original_core){"use strict";\nconst {orm_profile_source_v3_json,shrink_options_json,analyze_options_json,replay_report_json,version}=__mtw_original_core;\n'+body+'\nreturn Object.freeze({'+[...functions,...constants].join(',')+'});\n})(require("node:crypto").createHash,require("./core.cjs"));\n');
}
export function deriveFrozenLegacyV024(root){
 const fixture=resolve(root,'fixtures/compat-v024'),raw=readFileSync(resolve(fixture,'manifest.json'));assert.equal(hash(raw),PUBLIC_V024_FIXTURE_SHA,'Immutable authentic24 fixture manifest differs');
 const original=JSON.parse(raw);assert.equal(original.sourceCommit,PUBLIC_V024_SOURCE);assert.equal(original.actualPublishedProducer,true);assert.equal(original.authorDistRead,false);
 const files={};
 for(const name of ORIGINAL){
  const record=original.producerFiles[name],bytes=readFileSync(resolve(fixture,record.file));assert.equal(bytes.length,record.bytes);assert.equal(hash(bytes),record.sha256);files[name]=bytes;
 }
 files['core.cjs']=wrapCore(files['core.mjs'].toString('utf8'));files['orm-profile.cjs']=wrapOrm(files['orm-profile.mjs'].toString('utf8'));
 files['origin.json']=encode({sourceCommit:PUBLIC_V024_SOURCE,fixtureManifestSha256:PUBLIC_V024_FIXTURE_SHA,publicPackage:original.publicPackage,registryPackage:original.registryPackage,publicationReceiptSha256:original.publicationReceiptSha256,producerBuild:original.producerBuild});
 const manifest={format:'moontxnwitness-frozen-orm-runtime/v1',version:'0.2.4',sourceCommit:PUBLIC_V024_SOURCE,
  moduleWrapperAlgorithm:'fixed-public024-esm-cjs/1',originalModuleBytesUnchanged:true,headerRewriting:false,
  minimalOriginalFiles:['core.mjs','orm-profile.mjs'],lazyExecutableFiles:['core.cjs','orm-profile.cjs'],
  files:Object.fromEntries(Object.entries(files).map(([name,bytes])=>[name,{bytes:bytes.length,sha256:hash(bytes)}]))};
 files['manifest.json']=encode(manifest);return {files,manifest,manifestSha256:hash(files['manifest.json'])};
}
export function verifyFrozenLegacyV024(root,directory=resolve(root,'cmd/legacy/v024')){
 const expected=deriveFrozenLegacyV024(root);assert.deepEqual(readdirSync(directory).sort(),Object.keys(expected.files).sort(),'Frozen legacy file set differs');
 for(const [name,bytes]of Object.entries(expected.files))assert.deepEqual(readFileSync(resolve(directory,name)),bytes,'Frozen public24 runtime differs: '+name);
 return {verified:true,manifestSha256:expected.manifestSha256,files:Object.keys(expected.files)};
}
export function copyFrozenLegacyV024(root,output){
 const status=verifyFrozenLegacyV024(root),source=resolve(root,'cmd/legacy/v024'),target=resolve(output,'legacy/v024');mkdirSync(target,{recursive:true});
 for(const name of status.files)copyFileSync(resolve(source,name),resolve(target,name));verifyFrozenLegacyV024(root,target);return status;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const [mode,rootArg,...rest]=process.argv.slice(2);assert.ok(rootArg&&!rest.length&&['--generate','--verify'].includes(mode),'Usage: --generate|--verify ROOT');
 const root=resolve(rootArg),directory=resolve(root,'cmd/legacy/v024');
 if(mode==='--generate'){
  assert.equal(existsSync(directory),false,'Never overwrite frozen legacy runtime');const derived=deriveFrozenLegacyV024(root);mkdirSync(directory,{recursive:true});
  for(const [name,bytes]of Object.entries(derived.files))writeFileSync(resolve(directory,name),bytes,{flag:'wx'});
 }
 console.log(JSON.stringify(verifyFrozenLegacyV024(root,directory)));
}
