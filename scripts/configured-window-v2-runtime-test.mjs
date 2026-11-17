// Current compiled SDK/standalone parity; optional original DB records stay external.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
const root = resolve(import.meta.dirname, '..');
const args = process.argv.slice(2);
if (args.length !== 0 && (args.length !== 2 || args[0] !== '--receipt')) {
  throw new Error('Usage: node scripts/configured-window-v2-runtime-test.mjs [--receipt ORIGINAL.json]');
}
const sha = value => createHash('sha256').update(value).digest('hex');
const runtimeNames = ['core.mjs', 'sql-projection-v2-core.mjs', 'configured-window-v2.mjs',
  'configured-window-v2-host.mjs', 'configured-window-v2-standalone.mjs'];
const runtimeHashes = () => Object.fromEntries(runtimeNames.map(name => [name, sha(readFileSync(resolve(root, 'dist', name)))]));
const before = runtimeHashes();
const sdk = await import('../dist/sdk.mjs');
const standalone = await import('../dist/configured-window-v2-standalone.mjs');
const manifest = JSON.parse(readFileSync(resolve(root, 'dist/build-manifest.json'), 'utf8'));
const results = [];
function test(name, fn) {
  try {fn(); results.push({name, passed: true});}
  catch (error) {results.push({name, passed: false, error: error.stack});}
}
test('current manifest binds every new runtime and retains the old four slots', () => {
  assert.equal(before['core.mjs'], manifest.coreSha256);
  assert.deepEqual(Object.keys(manifest.configuredWindowRuntimeSha256).sort(), runtimeNames.filter(name => name !== 'core.mjs').sort());
  for (const [name, digest] of Object.entries(manifest.configuredWindowRuntimeSha256)) assert.equal(before[name], digest);
  assert.deepEqual(Object.keys(manifest.configuredCoreSha256).sort(), [
    'configured-session-core.mjs', 'source-components-core.mjs', 'sql-fetch-core.mjs', 'sql-projection-core.mjs'].sort());
});
test('SDK and standalone expose the same limits and reject bundle self-authorization', () => {
  assert.deepEqual(sdk.CONFIGURED_WINDOW_V4_LIMITS, standalone.CONFIGURED_WINDOW_V4_LIMITS);
  for (const api of [sdk, standalone]) {
    assert.throws(() => api.analyzeConfiguredWindowV4('{"configText":"{}","policyText":"{}"}', {}), TypeError);
    assert.throws(() => api.verifyConfiguredWindowV4('{}', {}, {config: '{}'}), TypeError);
  }
});
test('actual compiled entry points agree on invalid input and deny a complete verification', () => {
  const options = {config: '{}', policy: '{}'};
  const report = sdk.analyzeConfiguredWindowV4('{}', options);
  assert.equal(report.status, 'invalid');
  assert.equal(report.coverageComplete, false);
  assert.deepEqual(standalone.analyzeConfiguredWindowV4('{}', options), report);
  const verified = sdk.verifyConfiguredWindowV4('{}', report, options);
  assert.equal(verified.valid, false);
  assert.equal(verified.reportMatches, true);
  assert.deepEqual(standalone.verifyConfiguredWindowV4('{}', report, options), verified);
});
let originalCases = 0;
if (args.length) {
  const receipt = JSON.parse(readFileSync(resolve(args[1]), 'utf8'));
  assert.equal(receipt.passed, true, 'Original producer receipt must have passed');
  const fixtures = receipt.records.flatMap(record => record.analysisFixtures.map(fixture => ({...fixture, keyType: record.keyType})));
  assert(fixtures.length > 0, 'No original analysis fixtures');
  for (const fixture of fixtures) {
    test('recorded ' + fixture.keyType + ' ' + fixture.name + ' SDK/standalone analysis and independent verification', () => {
      const bundle = readFileSync(fixture.bundle, 'utf8');
      assert.equal(sha(bundle), fixture.bundleSha256, 'Original bundle bytes changed');
      const options = {config: fixture.config, policy: fixture.policy};
      const report = sdk.analyzeConfiguredWindowV4(bundle, options);
      const coverageComplete = fixture.coverageComplete ?? fixture.expected !== 'unknown';
      assert.equal(report.status, fixture.expected === 'compatible' ? 'checked-compatible' : fixture.expected);
      assert.equal(report.coverageComplete, coverageComplete);
      if (coverageComplete) assert.equal(report.bundleSha256, fixture.bundleSha256);
      assert.equal(report.sourceAuthenticated, false);
      assert.deepEqual(standalone.analyzeConfiguredWindowV4(bundle, options), report);
      const verified = sdk.verifyConfiguredWindowV4(bundle, report, options);
      assert.equal(verified.valid, coverageComplete);
      assert.equal(verified.reportMatches, true);
      assert.deepEqual(standalone.verifyConfiguredWindowV4(bundle, report, options), verified);
      assert.equal(sdk.verifyConfiguredWindowV4(bundle, {...report, coverageComplete: false}, options).valid, false);
      assert.equal(sdk.verifyConfiguredWindowV4(bundle + '\n', report, options).valid, false);
      const exhausted = sdk.analyzeConfiguredWindowV4(bundle, {...options, maxSourceChecks: 0});
      assert.equal(exhausted.status, 'unknown');
      assert.equal(exhausted.coverageComplete, false);
      assert.equal(sdk.verifyConfiguredWindowV4(bundle, report, {...options, maxSourceChecks: 0}).valid, false);
    });
    originalCases++;
  }
}
test('runtime bytes remain unchanged during the consumer checks', () => assert.deepEqual(runtimeHashes(), before));
const result = {format: 'configured-window-v2-runtime-consumer/v1', passed: results.every(item => item.passed),
  checks: results.length, failed: results.filter(item => !item.passed).length, originalCases,
  actualDatabaseExecution: false, moonbitSemanticsExecuted: true, formalPerformanceMeasurement: false,
  runtimeSha256: before, results};
console.log(JSON.stringify(result));
if (!result.passed) process.exitCode = 1;
