// Tiny synthetic manifests; no production runtime import, compiler or database.
import assert from 'node:assert/strict';
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {sourceFingerprint} from './build-fingerprint.mjs';
import {bindV034CurrentBuild} from './v034-maintenance-bindings.mjs';
const root=resolve(import.meta.dirname,'..'),dir=resolve(root,'artifacts/v034-maintenance-framework');mkdirSync(dir,{recursive:true});
const hash=value=>createHash('sha256').update(value).digest('hex'),results=[];
function fixture({omit,manifest=true}={}){
 const folder=mkdtempSync(resolve(dir,'case-'));mkdirSync(resolve(folder,'src'));mkdirSync(resolve(folder,'cmd'));mkdirSync(resolve(folder,'dist'));
 writeFileSync(resolve(folder,'moon.mod'),'name = "synthetic-only"\nversion = "0.0.0"\n');writeFileSync(resolve(folder,'src/unit.mbt'),'// synthetic input, never compiled\n');writeFileSync(resolve(folder,'package.json'),'{"version":"0.0.0"}');
 for(const name of ['core.mjs','capture-core.mjs','sdk.mjs','moontxnwitness.mjs','relation-v4.mjs','relation-reduction-v4.mjs']){
  const content='// synthetic '+name+'; not executable evidence\n';
  if(name!==omit)writeFileSync(resolve(folder,'dist',name),content);
  if(!['core.mjs','capture-core.mjs'].includes(name))writeFileSync(resolve(folder,'cmd',name),content);
 }
 const data={version:'0.0.0',sourceSha256:sourceFingerprint(folder),coreSha256:hash(readFileSync(resolve(folder,'dist/core.mjs'))),captureCoreSha256:hash(readFileSync(resolve(folder,'dist/capture-core.mjs')))};
 if(manifest)writeFileSync(resolve(folder,'dist/build-manifest.json'),JSON.stringify(data));
 return folder;
}
function check(name,fn){try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.message});}}
check('missing dist is explicitly unexecuted',()=>{const p=mkdtempSync(resolve(dir,'absent-'));assert.throws(()=>bindV034CurrentBuild(p),error=>error.code==='DIST_NOT_BUILT');});
check('current matching synthetic snapshot binds all expected bytes',()=>{const p=fixture(),s=bindV034CurrentBuild(p);assert.equal(s.sourceFingerprint,sourceFingerprint(p));assert.equal(s.actualPublishedProducer,false);assert(s.fileSha256['dist/core.mjs']);assert(s.fileSha256['cmd/relation-reduction-v4.mjs']);});
check('core bytes cannot differ from build manifest',()=>{const p=fixture();writeFileSync(resolve(p,'dist/core.mjs'),'tampered');assert.throws(()=>bindV034CurrentBuild(p),/core digest/);});
check('capture bytes cannot differ from build manifest',()=>{const p=fixture();writeFileSync(resolve(p,'dist/capture-core.mjs'),'tampered');assert.throws(()=>bindV034CurrentBuild(p),/capture digest/);});
check('source changes cannot use an old compiled fingerprint',()=>{const p=fixture();writeFileSync(resolve(p,'src/unit.mbt'),'// changed\n');assert.throws(()=>bindV034CurrentBuild(p),/source differs/);});
check('package version must match the build version',()=>{const p=fixture();writeFileSync(resolve(p,'package.json'),'{"version":"1.0.0"}');assert.throws(()=>bindV034CurrentBuild(p),/package differs/);});
check('current command wrapper must match its copied dist module',()=>{const p=fixture();writeFileSync(resolve(p,'cmd/relation-v4.mjs'),'different');assert.throws(()=>bindV034CurrentBuild(p),/host module differs/);});
check('missing required relation reduction host module is fatal',()=>assert.throws(()=>bindV034CurrentBuild(fixture({omit:'relation-reduction-v4.mjs'})),/Missing built module/));
check('partial dist without a build manifest is fatal',()=>assert.throws(()=>bindV034CurrentBuild(fixture({manifest:false}))));
check('malformed build manifest cannot authorize a snapshot',()=>{const p=fixture();writeFileSync(resolve(p,'dist/build-manifest.json'),'{');assert.throws(()=>bindV034CurrentBuild(p));});
check('additional current top-level runtime modules are also bound',()=>{const p=fixture();writeFileSync(resolve(p,'dist/additional.mjs'),'// additional');const s=bindV034CurrentBuild(p);assert.equal(s.fileSha256['dist/additional.mjs'],hash('// additional'));});
check('unrelated private historical artifact is never required',()=>{const p=fixture();assert.equal(bindV034CurrentBuild(p).kind,'current-build-manifest-and-source-snapshot/v1');});
check('retained semantic-body guard executes without importing a runtime',()=>{
 const source=readFileSync(resolve(root,'scripts/v034-public-boundary-independent-test.mjs'),'utf8');
 const digest=source.match(/const semanticAssertionsSha256='([a-f0-9]+)'/)[1];
 const a=source.indexOf('const ownText='),b=source.indexOf('const bound=',a);
 assert(a>=0&&b>a);
 const guard=source.slice(a,b).replace("readFileSync(import.meta.filename,'utf8')",'input');
 new Function('input','hash','assert','semanticAssertionsSha256',guard)(source,hash,assert,digest);
});
const receipt={format:'v034-maintenance-binding-tests/v1',passed:results.every(x=>x.passed),checks:results.length,failed:results.filter(x=>!x.passed).length,results,syntheticFixturesOnly:true,actualDatabaseExecution:false,newMoonCompilation:false,productionRuntimeExecuted:false,publicReleaseVerified:false};
writeFileSync(resolve(root,'artifacts/v034-maintenance-bindings-validation.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));if(!receipt.passed)process.exitCode=1;
