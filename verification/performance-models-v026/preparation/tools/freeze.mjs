// Prepare only: byte-copy final runtime, never import or execute it.
import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {sha,canonical,walk,verifyBindings,safeFile} from './common.mjs';
const here=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const [runtimeArg,expectedManifestSha,outArg]=process.argv.slice(2);
if(process.argv.length!==5||!(/^[a-f0-9]{64}$/).test(expectedManifestSha??''))throw Error('Usage: freeze.mjs FINAL_DIST EXPECTED_RAW_MANIFEST_SHA NEW_BUNDLE');
const source=resolve(runtimeArg),out=resolve(outArg),manifest=readFileSync(safeFile(source,'build-manifest.json'));
if(sha(manifest)!==expectedManifestSha)throw Error('Explicit final build-manifest SHA differs');
const parsed=JSON.parse(manifest);if(parsed.version!=='0.2.6')throw Error('Expected actual integrated 0.2.6 candidate');
const files=walk(source);if(files['core.mjs']?.sha256!==parsed.coreSha256||files['capture-core.mjs']?.sha256!==parsed.captureCoreSha256)throw Error('Build manifest and actual core byte hashes differ');if(!Object.hasOwn(files,'sdk.mjs')||!Object.hasOwn(files,'classification-models.mjs')||!Object.hasOwn(files,'core.mjs'))throw Error('Full SDK runtime incomplete');
if(Object.values(files).reduce((n,x)=>n+x.bytes,0)>128*1024*1024)throw Error('Runtime copy exceeds explicit 128 MiB preparation budget');
mkdirSync(out);mkdirSync(resolve(out,'runtime'));
for(const name of Object.keys(files)){const to=resolve(out,'runtime',name);mkdirSync(dirname(to),{recursive:true});copyFileSync(safeFile(source,name),to);}
const protocol=JSON.parse(readFileSync(resolve(here,'protocol.json')));mkdirSync(resolve(out,'fixtures'));
for(const f of protocol.fixtures){copyFileSync(safeFile(here,f.file),resolve(out,f.file));}
mkdirSync(resolve(out,'tools'));const tools=walk(resolve(here,'tools'));for(const name of Object.keys(tools))copyFileSync(safeFile(resolve(here,'tools'),name),resolve(out,'tools',name));
const plan={...protocol,phase:'frozen-candidate-for-root-review-not-yet-measured',runtime:{directory:'runtime',files,buildManifest:parsed,buildManifestRawSha256:sha(manifest)},toolFiles:tools};
writeFileSync(resolve(out,'plan.json'),canonical(plan),{flag:'wx'});verifyBindings(source,files);verifyBindings(resolve(out,'runtime'),files);
console.log(JSON.stringify({prepared:true,formalExecuted:false,planSha256:sha(readFileSync(resolve(out,'plan.json'))),runtimeFiles:Object.keys(files).length,runtimeBytes:Object.values(files).reduce((n,x)=>n+x.bytes,0)}));
