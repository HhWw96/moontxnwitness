// Bind maintenance checks to this actual build, not a private historical freeze.
import assert from 'node:assert/strict';
import {existsSync,readFileSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {sourceFingerprint} from './build-fingerprint.mjs';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const REQUIRED=['core.mjs','capture-core.mjs','sdk.mjs','moontxnwitness.mjs','relation-v4.mjs','relation-reduction-v4.mjs'];
export function bindV034CurrentBuild(root){
 const dist=resolve(root,'dist');
 if(!existsSync(dist)){const error=new Error('Build dist before running the v034 maintained public-boundary checks');error.code='DIST_NOT_BUILT';throw error;}
 const manifestPath=resolve(dist,'build-manifest.json'),manifestBytes=readFileSync(manifestPath),manifest=JSON.parse(manifestBytes);
 const fingerprint=sourceFingerprint(root),version=JSON.parse(readFileSync(resolve(root,'package.json'),'utf8')).version;
 assert.equal(manifest.sourceSha256,fingerprint,'Current source differs from compiled build manifest');
 assert.equal(manifest.version,version,'Current package differs from compiled build version');
 for(const name of REQUIRED)assert(existsSync(resolve(dist,name)),'Missing built module '+name);
 assert.equal(hash(readFileSync(resolve(dist,'core.mjs'))),manifest.coreSha256,'Compiled core digest differs from build manifest');
 assert.equal(hash(readFileSync(resolve(dist,'capture-core.mjs'))),manifest.captureCoreSha256,'Compiled capture digest differs from build manifest');
 const fileSha256={'dist/build-manifest.json':hash(manifestBytes)};
 for(const entry of readdirSync(dist,{withFileTypes:true}))if(entry.isFile()&&entry.name.endsWith('.mjs'))fileSha256['dist/'+entry.name]=hash(readFileSync(resolve(dist,entry.name)));
 for(const name of ['sdk.mjs','moontxnwitness.mjs','relation-v4.mjs','relation-reduction-v4.mjs']){
  const path='cmd/'+name;fileSha256[path]=hash(readFileSync(resolve(root,path)));
  assert.equal(fileSha256[path],fileSha256['dist/'+name],'Built host module differs from current '+path);
 }
 return {kind:'current-build-manifest-and-source-snapshot/v1',sourceFingerprint:fingerprint,buildManifestSha256:hash(manifestBytes),buildManifest:manifest,fileSha256,actualPublishedProducer:false};
}
