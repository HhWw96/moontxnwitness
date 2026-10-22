import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync} from 'node:fs';
import {resolve, dirname, relative} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const candidate = resolve(root, process.argv[2]);
const expectedManifest = process.argv[3];
const hash = text => createHash('sha256').update(text).digest('hex');
const bind = path => {const raw = readFileSync(path); return {sha256: hash(raw), bytes: raw.length};};
const before = bind(resolve(candidate, 'candidate-manifest.json'));
assert.equal(before.sha256, expectedManifest);
mkdirSync(resolve(here, 'runs'), {recursive:true});
const output = mkdtempSync(resolve(here, 'runs', 'malformed-'));
const sdk = await import(pathToFileURL(resolve(candidate, 'runtime/sdk.mjs')).href);
const generic = await import(pathToFileURL(resolve(candidate, 'runtime/generic-sdk.mjs')).href);
const receipt = {schema:1, kind:'independent-reproduction-malformed-generic-capsule',
  passed:false, expected:'A valid generic invalid-JSON diagnostic is stably rejected by the fixed-list replay API without throwing',
  candidate:relative(root,candidate).replaceAll('\\','/'), manifest:before, cases:[],
  databaseExecuted:false, buildExecuted:false, downloaded:false, trackedFilesModified:false};
for (const trace of ['{', '', '{"incomplete":', 'not json']) {
  const report = generic.analyzeV3(trace);
  const capsule = generic.makeCapsuleV3(trace, report);
  const genericReplay = generic.replayCapsuleV3(capsule);
  assert.equal(report.status, 'invalid'); assert.equal(genericReplay.valid,true);
  const row = {trace, genericStatus:report.status, genericReplay};
  try {row.listReplay = sdk.replayListCapsuleV3(capsule); row.passed = row.listReplay.valid === false;}
  catch(error) {row.exception={name:error.name,message:error.message};row.passed=false;}
  receipt.cases.push(row);
  writeFileSync(resolve(output, 'case-' + receipt.cases.length + '.json'), capsule, {flag:'wx'});
}
receipt.passed = receipt.cases.every(row=>row.passed);
assert.deepEqual(bind(resolve(candidate,'candidate-manifest.json')),before);
writeFileSync(resolve(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({passed:receipt.passed,cases:receipt.cases.map(row=>({passed:row.passed,exception:row.exception?.name})),receipt:relative(root,resolve(output,'receipt.json')).replaceAll('\\','/')}));
if(!receipt.passed)process.exitCode=1;
