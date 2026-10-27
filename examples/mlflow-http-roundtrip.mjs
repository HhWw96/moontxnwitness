import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
if (!(args.length === 0 || args.length === 2 && args[0] === '--out-root')) {
  throw new TypeError('Usage: node examples/mlflow-http-roundtrip.mjs [--out-root NEW_OUTPUT_PARENT]');
}
const fixture = resolve(root, 'fixtures/execution-v3/mlflow-http-623');
const manifest = JSON.parse(readFileSync(resolve(fixture, 'manifest.json'), 'utf8'));
assert.equal(manifest.format, 'moontxnwitness-mlflow-native-http-example/v1');
assert.equal(manifest.caseSha256, '9fddccaffd9d300ab23c1cd5b1bdd1d5f6075a75eabdca13a8a2ec36f127d69d');
assert.equal(manifest.oneMinimal, false);
assert.deepEqual(manifest.files.map(record => record.file), ['before.capture.json', 'fixed.capture.json']);
for (const item of manifest.files) {
  const raw = readFileSync(resolve(fixture, item.file));
  assert.equal(raw.length, item.bytes);
  assert.equal(createHash('sha256').update(raw).digest('hex'), item.sha256);
}
const output = resolve(args[1] || resolve(root, 'verification/mlflow-http-roundtrip'));
const child = spawnSync(process.execPath, [resolve(root, 'examples/execution-roundtrip.mjs'),
  ...manifest.files.map(item => resolve(fixture, item.file)), output],
{cwd: root, encoding: 'utf8', windowsHide: true, timeout: 120000, maxBuffer: 1024 * 1024});
if (child.error) throw child.error;
assert.equal(child.status, 0, child.stdout + child.stderr);
const result = JSON.parse(child.stdout);
assert.equal(result.passed, true);
const receipt = JSON.parse(readFileSync(resolve(output, result.outputDirectory, result.receiptFile), 'utf8'));
assert.equal(receipt.actualDatabaseExecution, false);
assert.equal(receipt.certifiesFailureAbsence, false);
assert.equal(receipt.modelViolationClaim, false);
assert.deepEqual(receipt.cases[0].observedSqlstates, ['40P01']);
assert.deepEqual(receipt.cases[1].observedSqlstates, []);
for (let index = 0; index < 2; index++) {
  const record = receipt.cases[index];
  assert.equal(record.originalTraceSha256, manifest.files[index].sha256);
  assert.equal(record.executionDiagnosticRecomputed, true);
  assert.equal(record.originalModelCapsuleReplayed, true);
  assert.equal(record.modelStatus, 'inconclusive');
  assert.equal(record.captureCoverage.complete, false);
}
console.log(JSON.stringify({...result, kind: 'retained-native-HTTP-fault-roundtrip',
  retainedActualDatabaseObservations: true, sameCaseSha256: manifest.caseSha256,
  caseKeys: manifest.keys, oneMinimal: false, coverageRemainsIncomplete: true,
  explanation: 'Offline replay of the same real native HTTP case before and after repair; no new database run or failure-absence certificate.'}));
