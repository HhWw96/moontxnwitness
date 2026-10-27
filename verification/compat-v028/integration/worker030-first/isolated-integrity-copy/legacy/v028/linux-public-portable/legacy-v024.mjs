// The only old code path is a fixed, verified public24 ORM pair, loaded on demand.
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const MANIFEST_SHA='ea0b066df93fc3b80485f76437fcb6fe421dd8549548fb4c553542375b0c1a3d';
const FILES=['core.mjs','orm-profile.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt','core.cjs','orm-profile.cjs','origin.json'];
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
let legacy;
export function getLegacyOrmV024(){
 if(legacy)return legacy;
 const read=name=>readFileSync(new URL('./legacy/v024/'+name,import.meta.url));
 const raw=read('manifest.json');if(sha(raw)!==MANIFEST_SHA)throw new Error('Frozen original24 ORM manifest differs');
 const manifest=JSON.parse(raw);
 if(manifest.format!=='moontxnwitness-frozen-orm-runtime/v1'||manifest.version!=='0.2.4'||manifest.moduleWrapperAlgorithm!=='fixed-public024-esm-cjs/1'||manifest.sourceCommit!=='d583cb4f3cb1c4da4cc63e2ce255cc8834b08e2a'||Object.keys(manifest.files).sort().join('\n')!==[...FILES].sort().join('\n'))throw new Error('Unsupported frozen original24 runtime');
 for(const name of FILES){const bytes=read(name),expected=manifest.files[name];if(bytes.length!==expected.bytes||sha(bytes)!==expected.sha256)throw new Error('Frozen original24 module differs: '+name);}
 // This fixed local path is never selected or provided by a capsule.
 legacy=require(fileURLToPath(new URL('./legacy/v024/orm-profile.cjs',import.meta.url)));
 return legacy;
}
