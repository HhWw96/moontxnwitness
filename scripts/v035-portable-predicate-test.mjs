// Runtime-only predicate interface verification; no source tree or compiler.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import * as sdk from '../dist/sdk.mjs';
const root=resolve(import.meta.dirname,'..'),hash=x=>createHash('sha256').update(x).digest('hex'),results=[];
const parent=resolve(root,'artifacts/v035-portable-predicate');mkdirSync(parent,{recursive:true});const out=mkdtempSync(resolve(parent,'run-'));
const manifest=JSON.parse(readFileSync(resolve(root,'dist/build-manifest.json'),'utf8'));
const modules=['core.mjs','sdk.mjs','relation-v4.mjs','moontxnwitness.mjs'];
const bindings=()=>Object.fromEntries(modules.map(n=>[n,hash(readFileSync(resolve(root,'dist',n)))])),before=bindings();
const source=readFileSync(resolve(root,'examples/relation-predicate-categories.json'),'utf8');
const options={category:'G2',ruleSet:'adya-2000-scoped-categories-v1'},report=sdk.classifyRelationPredicateV4(source,options);
function check(name,fn){try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.message});}}
const cli=args=>spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),...args],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});
const put=(name,value)=>{const file=resolve(out,name);writeFileSync(file,typeof value==='string'?value:JSON.stringify(value));return file;};
check('core bytes agree with shipped manifest',()=>assert.equal(before['core.mjs'],manifest.coreSha256));
check('predicate refutation retains scope without model acceptance',()=>{assert.equal(report.status,'refuted');assert.equal(report.category,'G2');assert.equal(report.acceptsIsolationModels,false);});
check('item-only category distinguishes the same input',()=>assert.equal(sdk.classifyRelationPredicateV4(source,{...options,category:'G2-item'}).status,'checked-compatible'));
check('original report has independent-option verification',()=>assert.equal(sdk.verifyRelationPredicateClassificationV4(source,report,options).valid,true));
check('capsule replay requires separately selected rule and category',()=>{const c=sdk.makeRelationPredicateClassificationCapsuleV4(source,options);assert.equal(sdk.replayRelationCapsuleV4(c,options).valid,true);assert.equal(sdk.replayRelationCapsuleV4(c).valid,false);assert.equal(sdk.replayRelationCapsuleV4(c,{...options,category:'G0'}).valid,false);});
check('rehashed false capsule report fails semantic verification',()=>{const c=JSON.parse(sdk.makeRelationPredicateClassificationCapsuleV4(source,options)),r=JSON.parse(c.reportText);r.status='checked-compatible';c.reportText=JSON.stringify(r);c.reportSha256=hash(c.reportText);assert.equal(sdk.replayRelationCapsuleV4(c,options).valid,false);});
check('zero caller search budget remains unknown',()=>assert.equal(sdk.classifyRelationPredicateV4(source,{...options,maxStates:0}).status,'unknown'));
check('duplicate and hidden selectors are rejected',()=>{assert.throws(()=>sdk.classifyRelationPredicateV4(source,'{"category":"G2","categ\\u006fry":"G0","ruleSet":"'+options.ruleSet+'"}'));assert.throws(()=>sdk.classifyRelationPredicateV4(source,{...options,models:'elle-core'}));});
check('CLI classification and independent report verification',()=>{const input=put('source.json',source),opts=put('options.json',options),r=cli(['classify-relation-predicate-v4',input,'--options',opts]);assert.equal(r.status,1,r.stderr);assert.deepEqual(JSON.parse(r.stdout),report);const rf=put('report.json',report);const v=cli(['verify-relation-predicate-v4',input,rf,'--options',opts]);assert.equal(v.status,0,v.stderr);assert.equal(JSON.parse(v.stdout).valid,true);});
check('CLI capsule replay and missing caller options',()=>{const c=put('capsule.json',sdk.makeRelationPredicateClassificationCapsuleV4(source,options)),opts=put('replay-options.json',options);const r=cli(['replay-relation-v4',c,'--options',opts]);assert.equal(r.status,0,r.stderr);assert.equal(JSON.parse(r.stdout).valid,true);assert.equal(cli(['replay-relation-v4',c]).status,2);});
check('CLI output protection keeps original bytes',()=>{const input=put('protected-source.json',source),opts=put('protected-options.json',options);assert.equal(cli(['classify-relation-predicate-v4',input,'--options',opts,'--output',input]).status,2);assert.equal(readFileSync(input,'utf8'),source);});
check('runtime bytes unchanged by SDK and CLI calls',()=>assert.deepEqual(bindings(),before));
assert.equal(results.length,12);
const receipt={format:'v035-runtime-only-predicate-probe/v1',passed:results.every(r=>r.passed),checks:results.length,failed:results.filter(r=>!r.passed).length,
 results,runtimeBefore:before,runtimeAfter:bindings(),version:manifest.version,requiresSourceTree:false,requiresCommandSource:false,sourceAuditPerformed:false,
 newIndependentReviewPerformed:false,actualDatabaseExecution:false,newMoonCompilation:false,formalPerformanceMeasurement:false,outputRoot:out};
writeFileSync(resolve(out,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({...receipt,results:undefined,failures:results.filter(r=>!r.passed)}));if(!receipt.passed)process.exitCode=1;
