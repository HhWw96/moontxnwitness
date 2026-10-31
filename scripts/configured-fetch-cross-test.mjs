import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {verifyConfiguredFetchV1 as verify} from '../dist/sql-fetch-v1.mjs';
const root=resolve(import.meta.dirname,'..'),pg=resolve(process.argv[2]||resolve(root,'artifacts/configured-fetch-pg-second'));
const hash=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const fixture=JSON.parse(readFileSync(resolve(root,'artifacts/configured-fetch-fixture.json'),'utf8'));
const cases=[],results=[];
function check(name,fn){try{fn();results.push({name,status:'passed'});}catch(error){results.push({name,status:'failed',message:error.message});}}
function call(f=fixture,options={}){return verify(...['config','execution','native','deliveries'].map(k=>JSON.stringify(f[k])),options);}
for(const file of ['sync-cases.json','async-cases.json']){
 const path=resolve(pg,file),input=JSON.parse(readFileSync(path,'utf8'));assert.equal(input.actualDatabaseExecution,true);
 for(const [index,f]of input.cases.entries()){
  cases.push(f);
  check(file+':'+index,()=>{const r=call(f);assert.equal(r.status,'matched',JSON.stringify(r.gaps));assert.equal(r.completeFetchVerified,true);assert.equal(r.sourceFactsProduced,false);assert.equal(r.sourceWindowVerified,false);assert.equal(r.catalogVerified,false);assert.equal(r.grammar.status,'matched');});
 }
}
check('three different schemas and 4/3/6 column layouts',()=>{
 assert.equal(new Set(cases.map(f=>f.execution.candidate.descriptor.table.schema)).size,3);
 assert.deepEqual([...new Set(cases.map(f=>f.execution.candidate.descriptor.table.columns.length))].sort(),[3,4,6]);
});
check('original version projections observed without source authorization',()=>{
 assert(cases.some(f=>call(f).storedColumnObservations>0));
 assert(cases.some(f=>call(f).storedColumnObservations===0&&f.native.rows.length>0));
 for(const f of cases)assert.equal(call(f).isolationModelChecked,false);
});
const mutations=[
 ['original SQL',f=>f.execution.sql+=' AND id=1'],
 ['original parameters',f=>f.execution.parameters=[99]],
 ['Python descriptor',f=>f.execution.candidate.descriptor.operation='delete'],
 ['Python binding',f=>f.execution.candidate.bindings[0].value.value='99'],
 ['Python status boolean cannot grant trust',f=>f.execution.candidate.descriptor.moonbitProjectionVerified=true],
 ['native bytes',f=>f.native.rows[0][0]=Buffer.from('99').toString('base64')],
 ['actual delivery',f=>f.deliveries[0].rows[0][0].value='99'],
 ['native statement',f=>f.native.statementSeq++],
 ['actual statement',f=>f.deliveries[0].statementSeq++],
 ['native SQL digest',f=>f.native.sqlSha256='0'.repeat(64)],
 ['native parameter digest',f=>f.native.parametersSha256='0'.repeat(64)],
 ['native output alias',f=>f.native.fields[0].name='unexpected'],
 ['actual result identity',f=>f.deliveries[0].resultId='unexpected'],
 ['actual row position',f=>f.deliveries[0].start++],
 ['native grant',f=>f.native.sourceFactsProduced=true],
 ['delivery grant',f=>f.deliveries[0].sourceFactsProduced=true],
 ['unknown protocol field',f=>f.native.attested=true],
];
for(const[name,mutate]of mutations)check('refuses '+name,()=>{const f=structuredClone(fixture);mutate(f);assert.equal(call(f).valid,false);});
check('caller zero budget remains unknown',()=>assert.equal(call(fixture,{maxChecks:0}).status,'unknown'));
check('caller grammar budget independently bounded',()=>assert.equal(call(fixture,{grammarOptions:{maxChecks:0}}).status,'unknown'));
check('exact caller budget and one below',()=>{const r=call(),n=r.execution.checks;assert.equal(call(fixture,{maxChecks:n}).status,'matched');assert.equal(call(fixture,{maxChecks:n-1}).status,'unknown');});
for(const options of ['{"maxChecks":0,"max\\u0043hecks":100}', '{"unknown":true}', '{"maxChecks":1000001}'])check('invalid caller options '+options,()=>assert.equal(call(fixture,options).valid,false));
check('config wrong table cannot approve original SQL',()=>{const f=structuredClone(fixture);f.config.tables[0].table='other';assert.equal(call(f).valid,false);});
check('partial delivery is distinct from complete',()=>{const f=structuredClone(fixture);f.deliveries=[];const r=call(f);assert.equal(r.status,'partial');assert.equal(r.completeFetchVerified,false);assert.equal(r.sourceFactsProduced,false);});
check('stored column configuration cannot prove source window',()=>{const f=structuredClone(fixture);f.native.storedColumnDeclarations=['version'];const r=call(f);assert.equal(r.storedColumnObservations,2);assert.equal(r.sourceWindowVerified,false);assert(r.gaps.includes('read_version_unproven'));});
check('unknown native OID is not silently decoded',()=>{const f=structuredClone(fixture);f.native.fields[0].oid=2950;assert.equal(call(f).status,'unknown');});
check('NULL native result stays unknown',()=>{const f=structuredClone(fixture);f.native.rows[0][0]=null;assert.equal(call(f).status,'unknown');});
check('native binary result stays unknown',()=>{const f=structuredClone(fixture);f.native.fields[0].format=1;assert.equal(call(f).status,'unknown');});
check('forged report budget cannot authorize independent call',()=>{const f=structuredClone(fixture);f.native.execution={limits:{maxChecks:1000000}};assert.equal(call(f,{maxChecks:0}).valid,false);});
check('structured unsafe integer is refused without rounding',()=>{const f=structuredClone(fixture);f.execution.parameters=[Number.MAX_SAFE_INTEGER+1];assert.equal(verify(f.config,f.execution,f.native,f.deliveries).status,'invalid');});
check('actual CLI matched and Unicode duplicate options refused',()=>{
 const dir=resolve(root,'artifacts/configured-fetch-cli');mkdirSync(dir,{recursive:true});
 const paths=['config','execution','native','deliveries'].map(k=>{const p=resolve(dir,k+'.json');writeFileSync(p,JSON.stringify(fixture[k]));return p;});
 const before=paths.map(hash),cli=resolve(root,'scripts/verify-configured-fetch-v1.mjs');
 const invoke=extra=>spawnSync(process.execPath,[cli,...paths,...extra],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:2*1024*1024});
 const matched=invoke([]);assert.equal(matched.status,0,matched.stderr);assert.equal(JSON.parse(matched.stdout).status,'matched');
 const options=resolve(dir,'options.json');writeFileSync(options,'{"maxChecks":0,"max\\u0043hecks":100}');
 const bad=invoke([options]);assert.equal(bad.status,2,bad.stderr);assert.equal(JSON.parse(bad.stdout).valid,false);assert.deepEqual(paths.map(hash),before);
});
const receipt={format:'configured-fetch-core-cross-validation/v1',passed:results.filter(r=>r.status==='passed').length,failed:results.filter(r=>r.status==='failed').length,results,
 actualDatabaseExecution:true,actualDatabaseCases:cases.length,formalPerformanceMeasurement:false,publicReleasePerformed:false,sourceFactsProduced:false,
 coreSha256:hash(resolve(root,'dist/sql-fetch-core.mjs')),sdkSha256:hash(resolve(root,'dist/sql-fetch-v1.mjs')),scriptSha256:hash(import.meta.filename),
 fixtureSha256:hash(resolve(root,'artifacts/configured-fetch-fixture.json')),postgresReceiptSha256:hash(resolve(pg,'receipt.json')),inputs:Object.fromEntries(['sync-cases.json','async-cases.json'].map(n=>[n,hash(resolve(pg,n))]))};
writeFileSync(resolve(root,'artifacts/configured-fetch-core-cross.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({passed:receipt.passed,failed:receipt.failed,actualDatabaseCases:cases.length,failures:results.filter(r=>r.status==='failed')}));if(receipt.failed)process.exitCode=1;
