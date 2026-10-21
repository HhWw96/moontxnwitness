// Reproduce the real raw SQL traces without claiming the SQL mapping is complete.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,relative,dirname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {analyzeV3,makeCapsuleV3,replayCapsuleV3} from '../../dist/sdk.mjs';
import {writeImmutableEvidence} from '../../scripts/performance-evidence.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const directory = resolve(process.argv[2] || '');
assert(directory.startsWith(resolve(root,'verification/v3') + sep),'Use a retained owned v3 verification directory');
const databaseText = readFileSync(resolve(directory,'database-receipt.json'));
const database = JSON.parse(databaseText);
assert.equal(database.passed,true);
assert.equal(database.actualDatabaseExecution,true);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const bindings = [];
function save(name,text) {
  const target = resolve(directory,name);
  writeImmutableEvidence(target,text);
  bindings.push({file:name,bytes:Buffer.byteLength(text),sha256:sha(text)});
}
const cases = [];
for (const item of database.cases) {
  assert(/^[a-z][a-z0-9-]*$/.test(item.name));
  assert(!item.trace.includes('/') && !item.trace.includes('\\'));
  const text = readFileSync(resolve(directory,item.trace),'utf8');
  assert.equal(sha(text),item.sha256);
  const report = analyzeV3(text);
  assert.equal(report.status,'inconclusive');
  assert.equal(report.coverage.complete,false);
  assert.equal(report.normalized.history,null);
  assert(report.coverage.gaps.some(gap => gap.code === 'unmapped_statement'));
  assert.deepEqual(report.normalized.observations,JSON.parse(text).events);
  const writes = report.normalized.effects.filter(effect => effect.revertedBy === null);
  const final = writes.at(-1)?.version || 'x0';
  assert.equal(final,item.serverFinalVersion);
  const capsule = makeCapsuleV3(text,report);
  assert.equal(replayCapsuleV3(capsule).valid,true);
  save(item.name+'.report.json',JSON.stringify(report,null,2)+'\n');
  save(item.name+'.capsule.json',capsule);
  cases.push({name:item.name,status:report.status,serverFinalVersion:final,observationsPreserved:true,unmappedSqlVisible:true,capsuleReproduced:true});
}
save('model-receipt.json',JSON.stringify({schema:1,passed:true,actualDatabaseExecution:false,rawDatabaseExecutionReceipt:{file:'database-receipt.json',sha256:sha(databaseText)},cases,bindings,sourceSha256:sha(readFileSync(fileURLToPath(import.meta.url))),scope:'Offline lifecycle/effect validation of retained real PostgreSQL traces; full SQL mapping remains incomplete'},null,2)+'\n');
console.log(JSON.stringify({passed:true,cases:cases.length,receipt:relative(root,resolve(directory,'model-receipt.json')).replaceAll('\\','/')}));
