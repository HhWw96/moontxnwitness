import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createSourceComponentsV4 } from '../cmd/source-components-v4.mjs';
const root = resolve(dirname(fileURLToPath(import.meta.url)),'..');
const args = process.argv.slice(2);
if (args.length !== 2 || args[0] !== '--runtime') throw new Error('Usage: --runtime <compiled-source-components-bridge.mjs>');
const runtime = resolve(args[1]);
const core = await import(pathToFileURL(runtime).href);
const sdk = createSourceComponentsV4(core);
const fixture = resolve(root,'fixtures/source-components-v4');
const source = Object.fromEntries(await Promise.all([['config','config.json'],['policy','policy.json'],['log','control.jsonl'],['receipt','receipt.json']].map(async ([key,name])=>[key,await readFile(resolve(fixture,name),'utf8')])));
const synthetic = JSON.parse(await readFile(resolve(fixture,'SYNTHETIC-fetch-inputs.json'),'utf8'));
assert.equal(synthetic.syntheticNativeBuffers,true);assert.equal(synthetic.actualDatabaseExecution,false);
const realFetch = JSON.parse(await readFile(resolve(fixture,'actual-fetch-other-installation.json'),'utf8'));
assert.equal(realFetch.sameInstallationEpoch,false);
const sha = value => createHash('sha256').update(value).digest('hex');
const clone = value => structuredClone(value);
const exactJSON = value => JSON.parse(value,(_key,item,context)=>typeof item==='number'&&Number.isInteger(item)&&!Number.isSafeInteger(item)?JSON.rawJSON(context.source):item);
const checks=[];let failures=0;
function check(name,body){try{body();checks.push({name,status:'passed'});}catch(error){failures++;checks.push({name,status:'failed',error:error.stack});}}
function noFacts(value){for(const key of ['sourceFactsProduced','sourceAuthenticated','writerWindowVerified','isolationModelChecked'])assert.equal(value[key],false,key);}
function run(input=source,opts={}){const report=sdk.verifySourceInstallationV4(input,opts);noFacts(report);return report;}
function mapping(extra,opts={}){const report=sdk.mapInitialSourceFetchV4({...source,...extra},opts);noFacts(report);return report;}
function reject(input,phrase){const report=run(input);assert.equal(report.valid,false);if(phrase)assert.match(report.reason,new RegExp(phrase));}
function mutateReceipt(update){const input=clone(source);const r=exactJSON(input.receipt);update(r);input.receipt=r;return input;}
function changeControl(queryId,update,receiptUpdate=()=>{},occurrence=0){
 const input=clone(source),r=exactJSON(input.receipt),records=input.log.trimEnd().split('\n').map(JSON.parse);
 const targets=records.filter(x=>x.kind==='source-control'&&x.queryId===queryId);const record=targets[occurrence];assert.ok(record);
 const value=record.decodedRows.length?exactJSON(record.decodedRows[0][0]):null;update(value,record,records,r);
 if(value!==null){const cell=JSON.stringify(value);record.decodedRows=[[cell]];record.native.rows=[[Buffer.from(cell).toString('base64')]];}
 receiptUpdate(r,value);
 const prefix=records.slice(0,-1).map(x=>JSON.stringify(x)+'\n').join('');records.at(-1).prefixSha256=sha(prefix);
 input.log=prefix+JSON.stringify(records.at(-1))+'\n';r.log.bytes=Buffer.byteLength(input.log);r.log.sha256=sha(input.log);input.receipt=r;return input;
}
let baseline;
check('actual original three-table installation and 260 sources',()=>{baseline=run();assert.equal(baseline.status,'matched-components');assert.equal(baseline.initialRows,260);assert.deepEqual(baseline.bindings.map(x=>x.versionColumnPosition),[5,4,7]);assert.equal(baseline.actualCommitResponseVerified,true);});
check('actual report recomputed under caller default budget',()=>assert.equal(sdk.verifySourceInstallationReportV4(source,baseline),true));
check('producer checked flags do not authorize recomputation',()=>{const report=run(mutateReceipt(r=>{r.catalogVerified=false;r.initialSnapshotVerified=false;}));assert.equal(report.status,'matched-components');});
check('receipt sourceFacts escalation rejected',()=>reject(mutateReceipt(r=>r.sourceFactsProduced=true),'unproven-producer-claim'));
check('receipt wrong original caller config rejected',()=>reject(mutateReceipt(r=>r.config.tables[0].primaryKey='balance'),'caller-config'));
check('receipt wrong config digest rejected',()=>reject(mutateReceipt(r=>r.configSha256='0'.repeat(64)),'config-digest'));
check('receipt wrong source policy rejected',()=>reject(mutateReceipt(r=>r.policy.writers=['other']),'caller-policy'));
check('unsealed control stream rejected',()=>reject(mutateReceipt(r=>r.log.sealed=false),'log-sealed'));
check('missing final newline cannot be complete',()=>reject({...source,log:source.log.slice(0,-1)}));
check('native raw cell cannot differ from delivered catalog',()=>{const input=clone(source);const records=input.log.trimEnd().split('\n').map(JSON.parse);const record=records.find(x=>x.kind==='source-control'&&x.queryId==='environment');record.native.rows[0][0]=Buffer.from('{}').toString('base64');input.log=records.map(x=>JSON.stringify(x)+'\n').join('');reject(input,'native-delivery');});
check('environment superuser writer is rejected despite matching receipt',()=>reject(changeControl('environment',v=>v.writers[0].superuser=true,(r,v)=>r.environment=v),'writer-privilege'));
check('original environment SQL is independently fixed',()=>reject(changeControl('environment',(_v,record,records)=>{record.sql='SELECT 1';records.find(x=>x.seq===record.requestSeq).sql='SELECT 1';}),'command-SQL'));
check('table OID text rejected despite matching receipt',()=>reject(changeControl('installed-catalog',v=>v.oid=String(v.oid),(r,v)=>r.tables[0].catalog=v),'positive-integer|exact-integer'));
check('configured column type independently checked',()=>reject(changeControl('installed-catalog',v=>v.columns[1].oid=25,(r,v)=>r.tables[0].catalog=v),'column-type'));
check('compatible integer type still cannot change during source-only DDL',()=>reject(changeControl('installed-catalog',v=>v.columns[1].oid=23,(r,v)=>r.tables[0].catalog=v),'business-column-changed'));
check('business default cannot silently change during source-only DDL',()=>reject(changeControl('installed-catalog',v=>v.columns[1].default='1',(r,v)=>r.tables[0].catalog=v),'business-column-changed'));
check('physical column position independently checked',()=>reject(changeControl('installed-catalog',v=>v.columns[1].number=1,(r,v)=>r.tables[0].catalog=v),'column-position'));
check('single immediate primary key required',()=>reject(changeControl('installed-catalog',v=>v.primaryKeys[0].keys=2,(r,v)=>r.tables[0].catalog=v),'single-primary-key'));
check('disabled trigger cannot use receipt self-attestation',()=>reject(changeControl('installed-catalog',v=>v.triggers[0].enabled='D',(r,v)=>r.tables[0].catalog=v),'trigger-scope'));
check('trigger function body independently rebuilt',()=>reject(changeControl('installed-catalog',v=>v.triggers[0].body='RETURN NULL;',(r,v)=>r.tables[0].catalog=v),'trigger-function'));
check('trigger function settings independently checked',()=>reject(changeControl('installed-catalog',v=>v.triggers[0].settings=['search_path=public','standard_conforming_strings=on'],(r,v)=>r.tables[0].catalog=v),'trigger-settings'));
check('wrong trigger UTF8 key argument rejected',()=>reject(changeControl('installed-catalog',v=>v.triggers[0].argsHex='00',(r,v)=>r.tables[0].catalog=v),'trigger-scope'));
check('cyclic version allocation rejected',()=>reject(changeControl('source-catalog',v=>v.sequence.cycle=true,(r,v)=>r.sourceCatalog=v),'sequence-or-functions'));
check('source private grants rejected',()=>reject(changeControl('source-catalog',v=>v.nonOwnerGrants=['outsider'],(r,v)=>r.sourceCatalog=v),'private-access'));
check('initial row must contain original business scalar types',()=>reject(changeControl('initial-snapshot',v=>v.row.active='true')));
check('initial row must have unique increasing version',()=>reject(changeControl('initial-snapshot',v=>v.row.__mtw_source_version=0),'positive-integer'));
check('initial source row cannot omit a column',()=>reject(changeControl('initial-snapshot',v=>delete v.row.active),'initial-columns'));
check('initial source count cannot come from a receipt flag',()=>reject(mutateReceipt(r=>r.initialRows=1),'initial-count'));
check('initial source digest is independently recomputed',()=>reject(mutateReceipt(r=>r.initialSnapshotSha256='0'.repeat(64)),'initial-digest'));
check('COMMIT request with a ROLLBACK response is rejected',()=>reject(changeControl('installation-commit',(_v,record)=>record.native.tag='ROLLBACK'),'acknowledgement'));
check('source checks budget zero is unknown and limited',()=>{const r=run(source,{maxChecks:0});assert.equal(r.status,'unknown');assert.equal(r.execution.limited,true);assert.equal(r.execution.checks,0);});
check('source checks exact boundary succeeds',()=>{const r=run(source,{maxChecks:baseline.execution.checks});assert.equal(r.status,'matched-components');assert.equal(r.execution.checks,baseline.execution.checks);});
check('one fewer source check cannot become compatible',()=>{const r=run(source,{maxChecks:baseline.execution.checks-1});assert.equal(r.valid,false);assert.equal(r.execution.limited,true);});
check('report cannot authorize its own larger budget',()=>assert.equal(sdk.verifySourceInstallationReportV4(source,baseline,{maxChecks:0}),false));
check('custom exact budget requires caller expected options',()=>{const opts={maxChecks:baseline.execution.checks};const r=run(source,opts);assert.equal(sdk.verifySourceInstallationReportV4(source,r),false);assert.equal(sdk.verifySourceInstallationReportV4(source,r,opts),true);});
check('unknown options rejected',()=>assert.equal(run(source,{silentlyAllow:true}).valid,false));
check('Unicode escaped duplicate option rejected by core',()=>assert.equal(run(source,'{"maxChecks":0,"\\u006daxChecks":1000000}').valid,false));
check('negative caller budget rejected',()=>assert.equal(run(source,{maxChecks:-1}).valid,false));
check('boolean caller budget rejected',()=>assert.equal(run(source,{maxChecks:true}).valid,false));
check('report algorithm and model escalation cannot replay',()=>{const r=clone(baseline);r.algorithm='accept-everything';r.isolationModelChecked=true;assert.equal(sdk.verifySourceInstallationReportV4(source,r),false);});
for(const [index,c]of synthetic.cases.entries())check(`SYNTHETIC initial native source mapping table ${index}`,()=>{const r=mapping(c);assert.equal(r.status,'matched-initial-components');assert.equal(r.initialSourceCandidates.length,1);assert.equal(r.serverInstanceIdentityAuthenticated,false);assert.equal(sdk.verifyInitialSourceFetchReportV4({...source,...c},r),true);});
check('SYNTHETIC wrong physical OID rejected',()=>{const c=clone(synthetic.cases[0]);c.native.fields[0].tableOid++;assert.equal(mapping(c).status,'mismatch');});
check('SYNTHETIC actual delivered value cannot change',()=>{const c=clone(synthetic.cases[0]);c.deliveries[0].rows[0][1].value='999';assert.equal(mapping(c).valid,false);});
check('SYNTHETIC native+delivery mutation still differs from original source',()=>{const c=clone(synthetic.cases[0]);c.deliveries[0].rows[0][1].value='999';c.native.rows[0][1]=Buffer.from('999').toString('base64');const r=mapping(c);assert.equal(r.status,'mismatch');assert.match(r.reason,/delivered-initial-business-value/);});
check('SYNTHETIC unknown post-initial version is an explicit gap',()=>{const c=clone(synthetic.cases[0]);c.deliveries[0].rows[0].at(-1).value='999999';c.native.rows[0][c.native.rows[0].length-1]=Buffer.from('999999').toString('base64');const r=mapping(c);assert.equal(r.status,'unknown');assert.match(r.reason,/effective-write-source-missing/);});
check('SYNTHETIC partial result cannot make complete source mapping',()=>{const c=clone(synthetic.cases[0]);c.deliveries[0].method='fetchone';c.deliveries[0].complete=false;const r=mapping(c);assert.equal(r.status,'unknown');assert.match(r.reason,/fetch-not-exhausted/);});
check('SYNTHETIC source epoch mismatch rejected',()=>{const c=clone(synthetic.cases[0]);c.sourceContext.installationLogSha256='0'.repeat(64);assert.equal(mapping(c).status,'mismatch');});
check('SYNTHETIC database identity mismatch rejected',()=>{const c=clone(synthetic.cases[0]);c.sourceContext.databaseOid++;assert.equal(mapping(c).status,'mismatch');});
check('SYNTHETIC independent fetch budget zero remains unknown',()=>{const r=mapping(synthetic.cases[0],{maxFetchChecks:0});assert.equal(r.valid,false);assert.equal(r.execution.limited,true);});
check('SYNTHETIC installation budget zero remains unknown',()=>{const r=mapping(synthetic.cases[0],{maxInstallationChecks:0});assert.equal(r.valid,false);assert.equal(r.installation.valid,false);});
check('SYNTHETIC map budget zero remains unknown',()=>{const r=mapping(synthetic.cases[0],{maxChecks:0});assert.equal(r.valid,false);assert.equal(r.execution.limited,true);});
for(const [index,c]of realFetch.cases.entries())check(`actual fetch from other cluster table ${index} cannot become source facts`,()=>{const extra={...c,sourceContext:synthetic.cases[0].sourceContext};const r=mapping(extra);assert.equal(r.fetch.valid,true);assert.equal(r.valid,false);assert.equal(r.status,'unknown');assert.match(r.reason,/read-version-not-delivered/);});
const output={format:'source-components-sdk-tests/v4',status:failures?'failed':'passed',checks,checkCount:checks.length,passed:checks.length-failures,failures,runtimeSha256:sha(await readFile(runtime)),sourceFactsProduced:false,actualDatabaseExecutionDuringThisTest:false,actualInstallationFixtureRows:260,syntheticMappingCases:3,otherClusterActualFetchCases:3};
await mkdir(resolve(root,'artifacts'),{recursive:true});await writeFile(resolve(root,'artifacts/source-components-sdk-tests.json'),JSON.stringify(output,null,2)+'\n');
process.stdout.write(JSON.stringify({status:output.status,checks:checks.length,passed:output.passed,failures})+'\n');if(failures)process.exitCode=1;
