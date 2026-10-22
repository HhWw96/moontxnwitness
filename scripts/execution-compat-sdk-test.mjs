import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync, readdirSync} from 'node:fs';
import {resolve, dirname, relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as sdk from '../dist/sdk.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const fixture = resolve(root, 'fixtures/execution-v3/compat/v017');
const args = process.argv.slice(2);
assert.ok(args.length === 0 || (args.length === 2 && args[0] === '--output-root'));
const parent = args[1] ? resolve(args[1]) : resolve(root, 'verification/execution-compat-sdk');
mkdirSync(parent, {recursive: true});
const output = mkdtempSync(resolve(parent, 'run-'));
const sha = value => createHash('sha256').update(value).digest('hex');
const canonical = value => JSON.stringify(value, null, 2) + '\n';
const read = path => JSON.parse(readFileSync(path, 'utf8'));
const receipt = {schema: 1, kind: 'actual-v017-execution-capsule-compatibility', passed: false,
  runtimeVersion: sdk.version(), producerEngineVersion: '0.1.7', capsuleCount: 2,
  authorImplementedIntegrationChecks: true, independentAcceptance: false,
  expectationsFromFrozenActualV017: true, actualDatabaseExecution: false,
  networkUsed: false, modelViolationClaim: false, checks: []};
const retain = (name, value) => writeFileSync(resolve(output, name), typeof value === 'string' ? value : canonical(value), {flag: 'wx'});
const check = (name, fn) => {
  try {fn(); receipt.checks.push({name, passed: true});}
  catch (error) {receipt.checks.push({name, passed: false, error: error.message});}
};
function bindings() {
  const walk = folder => readdirSync(resolve(root, folder), {withFileTypes: true}).flatMap(entry =>
    entry.isDirectory() ? walk(folder + '/' + entry.name) : [folder + '/' + entry.name]);
  const names = [...walk('fixtures/execution-v3/compat'), 'scripts/execution-compat-sdk-test.mjs',
    'cmd/sdk.mjs', 'package.json', ...['core.mjs', 'capture-core.mjs', 'sdk.mjs', 'evidence.mjs', 'build-manifest.json'].map(name => 'dist/' + name)];
  return Object.fromEntries(names.sort().map(name => {
    const bytes = readFileSync(resolve(root, name));
    return [name, {bytes: bytes.length, sha256: sha(bytes)}];
  }));
}
const reseal = value => canonical({...value,
  traceSha256: sha(value.traceText), diagnosticSha256: sha(value.diagnosticText)});
try {
  const before = bindings();
  const origin = read(resolve(fixture, 'origin.json'));
  const build = read(resolve(root, 'dist/build-manifest.json'));
  assert.equal(build.version, sdk.version());
  assert.equal(read(resolve(root, 'package.json')).version, sdk.version());
  assert.notEqual(sdk.version(), '0.1.7', 'A cross-engine compatibility run must use a later engine');
  assert.equal(sha(readFileSync(resolve(root, 'dist/core.mjs'))), build.coreSha256);
  assert.equal(sha(readFileSync(resolve(root, 'dist/capture-core.mjs'))), build.captureCoreSha256);
  receipt.buildManifest = build;
  check('actual-v017-producer-and-exact-fixture-bindings', () => {
    assert.equal(origin.producerEngineVersion, '0.1.7');
    assert.equal(origin.sourceSha256, '3359ecaa858a4c737a02a7b89a6ee6197fb912f97074e4bb59c971d633bde932');
    assert.equal(origin.coreSha256, 'd1e419a5cf0aebef442dabaf71babcf742abcce0139ac1d28a199f43f5e62dc1');
    assert.equal(origin.captureCoreSha256, '60da31aafe9d8fb034289d6deb132c36eb61cb021bf3bc0668401e27987bf5ee');
    assert.equal(origin.obtainedFromGitHubPackage, false);
    assert.match(origin.sourceBindingGap, /capture\.py/);
    assert.deepEqual(origin.cases.map(row => row.id), ['before', 'fixed']);
    for (const [name, expected] of Object.entries(origin.files)) {
      const bytes = readFileSync(resolve(fixture, name));
      assert.deepEqual({bytes: bytes.length, sha256: sha(bytes)}, expected);
    }
    const producerBuild = read(resolve(fixture, 'producer-build-manifest.json'));
    assert.equal(producerBuild.version, '0.1.7');
    assert.equal(producerBuild.sourceSha256, origin.sourceSha256);
    assert.equal(producerBuild.coreSha256, origin.coreSha256);
    assert.equal(producerBuild.captureCoreSha256, origin.captureCoreSha256);
    const producer = read(resolve(fixture, 'producer-sdk-receipt.json'));
    assert.equal(producer.passed, true);
    assert.equal(producer.runtimeVersion, '0.1.7');
    assert.equal(producer.checks.length, 54);
    assert.equal(producer.testedInputsUnchanged, true);
    assert.deepEqual(producer.runtimeBuild, producerBuild);
    assert.equal(producer.runtimeFiles['sdk.mjs'], origin.producerSdkSha256);
  });
  for (const row of origin.cases) {
    const text = readFileSync(resolve(fixture, row.file), 'utf8');
    const capsule = JSON.parse(text);
    const originalDiagnostic = JSON.parse(capsule.diagnosticText);
    check('actual-v017-' + row.id + '-replays-with-exact-recorded-diagnostic', () => {
      assert.equal(sha(text), row.sha256);
      assert.equal(Buffer.byteLength(text, 'utf8'), row.bytes);
      assert.equal(capsule.engineVersion, '0.1.7');
      assert.equal(capsule.traceSha256, sha(capsule.traceText));
      assert.equal(capsule.diagnosticSha256, sha(capsule.diagnosticText));
      assert.equal(originalDiagnostic.observedFaultCount, row.id === 'before' ? 1 : 0);
      assert.equal(originalDiagnostic.captureCoverage.complete, false);
      if (row.id === 'before') {
        assert.equal(originalDiagnostic.faults[0].kind, 'deadlock');
        assert.equal(originalDiagnostic.faults[0].sqlstate, '40P01');
      }
      const result = sdk.replayExecutionCapsuleV3(text);
      assert.equal(result.valid, true);
      assert.equal(result.engineVersion, '0.1.7');
      assert.equal(result.traceSha256, capsule.traceSha256);
      assert.equal(result.diagnosticSha256, capsule.diagnosticSha256);
      assert.equal(JSON.stringify(result.diagnostic), capsule.diagnosticText);
      assert.deepEqual(result.diagnostic, originalDiagnostic);
      for (const key of ['actualDatabaseExecution', 'databaseAuthenticityVerified', 'certifiesFailureAbsence', 'modelViolationClaim', 'completeApplicationIntegration']) assert.equal(result.scope[key], false);
      retain(row.id + '.replay.json', result);
    });
    check('actual-v017-' + row.id + '-current-maker-keeps-trace-and-diagnostic-text', () => {
      const currentText = sdk.makeExecutionCapsuleV3(capsule.traceText);
      const current = JSON.parse(currentText);
      assert.equal(current.engineVersion, sdk.version());
      assert.deepEqual(Buffer.from(current.traceText, 'utf8'), Buffer.from(capsule.traceText, 'utf8'));
      assert.equal(current.traceSha256, capsule.traceSha256);
      assert.deepEqual(Buffer.from(current.diagnosticText, 'utf8'), Buffer.from(capsule.diagnosticText, 'utf8'));
      assert.equal(current.diagnosticSha256, capsule.diagnosticSha256);
      assert.equal(sdk.replayExecutionCapsuleV3(currentText).valid, true);
      retain(row.id + '.current-engine.capsule.json', currentText);
    });
    for (const [name, mutate] of [
      ['format', value => value.format = 'moontxnwitness-replay/v3'],
      ['unknown-engine', value => value.engineVersion = '99.0.0'],
      ['algorithm', value => value.diagnosticAlgorithm = 'v3-observed-failures-unknown'],
      ['budget', value => value.budgets.traceUtf8Bytes++],
    ]) check('actual-v017-' + row.id + '-rejects-' + name, () => {
      const changed = structuredClone(capsule); mutate(changed);
      assert.equal(sdk.replayExecutionCapsuleV3(canonical(changed)).valid, false);
    });
    check('actual-v017-' + row.id + '-rejects-rehashed-diagnostic-promotion', () => {
      const changed = structuredClone(capsule);
      const diagnostic = JSON.parse(changed.diagnosticText);
      diagnostic.modelViolationClaim = true;
      diagnostic.captureCoverage.complete = true;
      changed.diagnosticText = JSON.stringify(diagnostic);
      assert.equal(sdk.replayExecutionCapsuleV3(reseal(changed)).valid, false);
    });
    check('actual-v017-' + row.id + '-rejects-rehashed-invalid-original-event', () => {
      const changed = structuredClone(capsule), trace = JSON.parse(changed.traceText);
      trace.events[0].kind = 'unsupported-compatibility-event';
      changed.traceText = JSON.stringify(trace);
      assert.equal(sdk.replayExecutionCapsuleV3(reseal(changed)).valid, false);
    });
  }
  check('compatibility-fixtures-and-execution-inputs-remain-byte-identical', () => {
    receipt.testedInputsBefore = before;
    receipt.testedInputsAfter = bindings();
    assert.deepEqual(receipt.testedInputsAfter, before);
    receipt.testedInputsUnchanged = true;
  });
  assert.equal(receipt.checks.length, 18);
  receipt.passed = receipt.checks.every(row => row.passed);
} catch (error) {receipt.error = error.message;}
retain('receipt.json', receipt);
console.log(JSON.stringify({passed: receipt.passed, checks: receipt.checks.length,
  runtimeVersion: receipt.runtimeVersion, producerEngineVersion: receipt.producerEngineVersion,
  capsuleCount: receipt.capsuleCount, failures: receipt.checks.filter(row => !row.passed), error: receipt.error || null,
  receipt: relative(root, resolve(output, 'receipt.json')).replaceAll('\\', '/')}));
if (!receipt.passed) process.exitCode = 1;
