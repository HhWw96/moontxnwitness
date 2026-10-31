// Source-bound maintenance of the prior independently authored semantic cases.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {sourceFingerprint} from './build-fingerprint.mjs';
import {runPredicateRegression} from './v035-predicate-regression-body.mjs';
const root=path.resolve(import.meta.dirname,'..'),node=process.execPath;
const hash=b=>crypto.createHash('sha256').update(b).digest('hex'),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b),copy=structuredClone;
const provenance=JSON.parse(fs.readFileSync(path.join(root,'scripts/v035-predicate-regression-provenance.json'),'utf8'));
const text=fs.readFileSync(path.join(root,'scripts/v035-predicate-regression-body.mjs'),'utf8');
const start='// BEGIN frozen semantic body\n',end='// END frozen semantic body\n';
const body=text.slice(text.indexOf(start)+start.length,text.lastIndexOf(end));
assert(text.includes(start)&&text.includes(end));assert.equal(hash(body),provenance.semanticBodySha256);
const parent=path.join(root,'artifacts/v035-predicate-maintenance');fs.mkdirSync(parent,{recursive:true});
const out=fs.mkdtempSync(path.join(parent,'run-'));
const guard=()=>{const disk=fs.statfsSync(root,{bigint:true});assert(disk.bavail*disk.bsize>=64n*1024n*1024n,'64 MiB temporary-output reserve required');};guard();
const checks=[],results=[],inputs=[],representative=[];
const ck=(id,actual,expected=true)=>checks.push({id,ok:same(actual,expected),actual,expected});
function list(folder){return fs.readdirSync(path.join(root,folder),{withFileTypes:true}).flatMap(e=>e.isDirectory()?list(folder+'/'+e.name):[folder+'/'+e.name]);}
const files=[...list('src'),...list('cmd'),...list('scripts').filter(n=>/\.(mjs|py|json|gz)$/.test(n)),
 'moon.mod','package.json','docs/relation-predicate-categories-v4.md',
 ...fs.readdirSync(path.join(root,'dist')).filter(n=>n.endsWith('.mjs')||n==='build-manifest.json').map(n=>'dist/'+n)].sort();
const snapshot=()=>Object.fromEntries(files.map(n=>[n,hash(fs.readFileSync(path.join(root,n)))]));
const before=snapshot(),manifestText=fs.readFileSync(path.join(root,'dist/build-manifest.json'),'utf8'),manifest=JSON.parse(manifestText);
const S=await import(pathToFileURL(path.join(root,'dist/sdk.mjs')));
ck('current-product-version-binding',manifest.version,JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).version);
ck('actual-source-fingerprint',sourceFingerprint(root),manifest.sourceSha256);
ck('actual-core-sha256',hash(fs.readFileSync(path.join(root,'dist/core.mjs'))),manifest.coreSha256);
ck('actual-capture-sha256',hash(fs.readFileSync(path.join(root,'dist/capture-core.mjs'))),manifest.captureCoreSha256);
runPredicateRegression({root,out,node,S,guard,ck,copy,same,hash,checks,results,inputs,representative});
const after=snapshot();ck('all-source-host-dist-files-unchanged',after,before);
ck('build-manifest-unchanged',fs.readFileSync(path.join(root,'dist/build-manifest.json'),'utf8'),manifestText);
const afterText=fs.readFileSync(path.join(root,'scripts/v035-predicate-regression-body.mjs'),'utf8');
ck('original-semantic-body-unchanged',hash(afterText.slice(afterText.indexOf(start)+start.length,afterText.lastIndexOf(end))),provenance.semanticBodySha256);
assert.equal(checks.length,513,'506 original semantic assertions and seven current-build guards');
const receipt={format:'v035-predicate-maintenance/v1',passed:checks.every(x=>x.ok),checks:checks.length,failed:checks.filter(x=>!x.ok).length,
 semanticAssertions:506,currentBuildGuards:7,originalScriptSha256:provenance.originalScriptSha256,semanticBodySha256:provenance.semanticBodySha256,
 newIndependentReviewPerformed:false,developerRegressionRun:true,sourceAuditPerformed:true,actualDatabaseExecution:false,formalPerformanceMeasurement:false,
 requiresSourceTree:true,requiresCommandSource:true,sourceBefore:before,sourceAfter:after,sourceUnchanged:same(before,after),buildManifest:manifest,version:manifest.version,
 results:checks,caseResults:results,domainPatterns:64,outputRoot:out};
fs.writeFileSync(path.join(out,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
fs.writeFileSync(path.join(out,'inputs.json'),JSON.stringify(inputs,null,2)+'\n');
fs.writeFileSync(path.join(out,'representative-reports.json'),JSON.stringify(representative,null,2)+'\n');
console.log(JSON.stringify({...receipt,sourceBefore:undefined,sourceAfter:undefined,results:undefined,caseResults:undefined,failures:checks.filter(x=>!x.ok)}));
if(!receipt.passed)process.exitCode=1;
