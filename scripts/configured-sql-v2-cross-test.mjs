// Independent compiled MoonBit versus actual Python V2 candidates. No DB or worker.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
const {values}=parseArgs({options:{core:{type:'string'},inputs:{type:'string'},output:{type:'string'}}});
for(const name of ['core','inputs','output'])assert(values[name],`--${name} is required`);
const output=resolve(values.output),core=resolve(values.core),inputs=resolve(values.inputs);
mkdirSync(dirname(output),{recursive:true});
const snapshot=resolve(dirname(output),'sql-v2-core.mjs');
writeFileSync(snapshot,readFileSync(core));
const api=await import(pathToFileURL(snapshot).href);
const fixture=JSON.parse(readFileSync(inputs,'utf8')),rows=[];
const canonical=value=>value===null||typeof value!=='object'?JSON.stringify(value):Array.isArray(value)?'['+value.map(canonical).join(',')+']':'{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonical(value[key])).join(',')+'}';
const sha=value=>createHash('sha256').update(value).digest('hex');
const normalize=(c,p=c.parametersText,o='{}')=>JSON.parse(api.normalize_configured_sql_v2_json(c.configText,c.sql,p,o));
const verify=(c,d=c.candidateText,p=c.parametersText,o='{}')=>JSON.parse(api.verify_configured_sql_v2_json(c.configText,c.sql,p,d,o));
const noFacts=report=>{
 for(const name of ['captureFactsProduced','sourceFactsProduced','sourceAuthenticated','actualDriverResultsVerified','sourceWindowVerified','modelCoverageAccepted','moonbitProjectionVerified','databaseSyntaxValidated'])assert.equal(report[name],false,name);
};
function check(name,fn){try{fn();rows.push({name,passed:true});}catch(error){rows.push({name,passed:false,error:error.stack});}}
for(const c of fixture.cases)check(c.name,()=>{
 const normalized=normalize(c),matched=verify(c);
 assert.equal(normalized.status,'recognized');assert.equal(matched.status,'matched');
 assert.equal(matched.configSha256,c.configSha256);
 assert.equal(matched.originalParametersSha256,c.originalParametersSha256);
 assert.deepEqual(matched.bindings,c.bindings);
 assert.equal(sha(canonical(normalized.descriptor)),c.descriptorSha256);
 noFacts(normalized);noFacts(matched);
 if(c.name.startsWith('uuid-spelling'))assert.deepEqual(matched.originalParameters,JSON.parse(c.parametersText));
});
const base=fixture.cases[0],uuid=fixture.cases.find(c=>c.layout===2&&c.name.endsWith('-select'));
for(const c of [base,fixture.cases.find(c=>c.layout===1&&c.name.endsWith('-select')),uuid]){
 for(let key=0;key<40;key++)check(`dynamic-layout-${c.layout}-key-${key}`,()=>{
  const value=c.layout===0?key:c.layout===1?'not-seeded-'+key:key.toString(16).padStart(32,'0');
  const report=verify(c,c.candidateText,JSON.stringify([value]));
  assert.equal(report.status,'matched');noFacts(report);
 });
}
for(const field of ['sourceFactsProduced','sourceAuthenticated','modelCoverageAccepted','moonbitProjectionVerified'])check('candidate-self-authorization-'+field,()=>{
 const candidate=JSON.parse(base.candidateText);candidate[field]=true;
 const report=verify(base,JSON.stringify(candidate));assert.equal(report.status,'mismatch');noFacts(report);
});
check('candidate-config-hash-is-untrusted',()=>{
 const candidate=JSON.parse(base.candidateText);candidate.configSha256='0'.repeat(64);
 const report=verify(base,JSON.stringify(candidate));assert.equal(report.status,'mismatch');noFacts(report);
});
check('v1-candidate-refused',()=>{
 const candidate=JSON.parse(base.candidateText);candidate.format='moontxnwitness-sql-ast-candidate/v1';
 const report=verify(base,JSON.stringify(candidate));assert.equal(report.status,'mismatch');noFacts(report);
});
check('v1-config-refused',()=>{
 const config=JSON.parse(base.configText);config.format='moontxnwitness-configured-sql/v1';
 const report=normalize({...base,configText:JSON.stringify(config)});assert.equal(report.status,'invalid');noFacts(report);
});
for(const options of [{maxChecks:0},{maxTokens:0},{maxSqlBytes:0}])check('caller-budget-'+JSON.stringify(options),()=>{
 const report=verify(base,base.candidateText,base.parametersText,JSON.stringify(options));assert.equal(report.status,'unknown');assert.equal(report.valid,false);noFacts(report);
});
for(const raw of ['null','[true]','[9223372036854775808]','[]','[1,2]'])check('wrong-original-bind-'+raw,()=>{
 const report=verify(base,base.candidateText,raw);assert.equal(report.status,'mismatch');assert.equal(report.valid,false);noFacts(report);
});
for(const raw of ['[null]','["not-uuid"]','["0000000000000000-0000000000000000"]','["{00000000-0000-0000-0000-000000000001}"]'])check('wrong-uuid-bind-'+raw,()=>{
 const report=verify(uuid,uuid.candidateText,raw);assert.equal(report.status,'mismatch');assert.equal(report.valid,false);noFacts(report);
});
for(const sql of [
 'SELECT account_no FROM ledger.accounts WHERE account_no=%s',
 'SELECT * FROM ledger.accounts WHERE account_no=%s AND active=true',
 'SELECT * FROM ledger.accounts WHERE account_no>%s',
 'SELECT * FROM ledger.accounts WHERE account_no=%s LIMIT 1',
 'SELECT * FROM ledger.accounts WHERE account_no=%s::UUID',
 'UPDATE ledger.accounts SET account_no=%s WHERE account_no=%s',
 'UPDATE ledger.accounts SET balance=balance+1 WHERE account_no=%s',
 'UPDATE ledger.accounts SET label=NULL WHERE account_no=%s',
 'INSERT INTO ledger.accounts(account_no,balance) VALUES(%s,%s)',
 'INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,%s),(%s,%s,%s,%s)',
 'INSERT INTO ledger.accounts(account_no,balance,active,label) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',
 'SELECT * FROM ledger.accounts a JOIN ledger.accounts b ON a.account_no=b.account_no WHERE a.account_no=%s',
])check('unsupported-'+sql,()=>{const report=normalize({...base,sql});assert.equal(report.valid,false);noFacts(report);});
check('v2-config-normalization',()=>{
 for(const c of fixture.cases){const report=JSON.parse(api.normalize_sql_config_v2_json(c.configText));assert.equal(report.valid,true);assert.equal(report.configSha256,c.configSha256);assert.deepEqual(report.config,JSON.parse(c.configText));}
});
const root=resolve(import.meta.dirname,'..');
const sources=['src/configured_sql_config_v2.mbt','src/configured_sql_grammar_v2.mbt','src/configured_sql_verify_v2.mbt','src/configured_sql_lexer_v1.mbt','src/sql_projection_v2_bridge/bridge.mbt','scripts/configured-sql-v2-cross-test.mjs'];
const receipt={format:'configured-sql-v2-independent-cross-validation/v1',passed:rows.every(row=>row.passed),testsRun:rows.length,failed:rows.filter(row=>!row.passed).length,pythonCandidates:fixture.cases.length,coreSha256:sha(readFileSync(core)),inputsSha256:sha(readFileSync(inputs)),sourceSha256:Object.fromEntries(sources.map(name=>[name,sha(readFileSync(resolve(root,name)))])),actualDatabaseExecution:false,sourceFactsProduced:false,modelCoverageAccepted:false,formalPerformanceMeasurement:false,publicReleasePerformed:false,results:rows};
writeFileSync(output,JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({passed:receipt.passed,tests:receipt.testsRun,failed:receipt.failed,output}));
if(!receipt.passed){for(const row of rows.filter(row=>!row.passed))console.error(row.name,row.error);process.exitCode=1;}
