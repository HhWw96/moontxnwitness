// Explicit-profile checks; original database observations are optional external inputs.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const args = {};
const argv = process.argv.slice(2);
for (let index = 0; index < argv.length; index++) {
  const item = argv[index], equal = item.indexOf('=');
  assert(item.startsWith('--'), 'Expected --runtime, --receipt or --output');
  const name = item.slice(2, equal < 0 ? undefined : equal);
  assert(['runtime', 'receipt', 'output'].includes(name), 'Unknown option: ' + name);
  assert(!Object.hasOwn(args, name), 'Duplicate option: ' + name);
  args[name] = equal < 0 ? argv[++index] : item.slice(equal + 1);
  assert(args[name], 'Missing option value: ' + name);
}
const runtime = resolve(args.runtime ?? resolve(import.meta.dirname, '../dist'));
const sha = (value) => createHash('sha256').update(value).digest('hex');
const names = ['core.mjs', 'sql-projection-v2-core.mjs', 'configured-window-v2.mjs',
  'configured-window-v2-host.mjs', 'configured-window-v2-standalone.mjs',
  'structured-window-verification-core.mjs', 'configured-window-v2-structured.mjs'];
const hashes = () => Object.fromEntries(names.map((name) => [name, sha(readFileSync(resolve(runtime, name)))]));
const before = hashes();
const manifest = JSON.parse(readFileSync(resolve(runtime, 'build-manifest.json'), 'utf8'));
const normal = await import(pathToFileURL(resolve(runtime, 'configured-window-v2-standalone.mjs')).href);
const structured = await import(pathToFileURL(resolve(runtime, 'configured-window-v2-structured.mjs')).href);
const wireCores = await Promise.all(['sql-projection-v2-core.mjs', 'structured-window-verification-core.mjs']
  .map((name) => import(pathToFileURL(resolve(runtime, name)).href)));
const results = [];
function test(name, run) {
  try {run(); results.push({name, passed: true});}
  catch (error) {results.push({name, passed: false, error: error.stack ?? String(error)});}
}
function flags(report) {
  return Object.fromEntries(['format', 'semanticContract', 'status', 'coverageComplete',
    'sourceMappingVerified', 'writerWindowVerified', 'sourceAuthenticated', 'windowVerified',
    'refutationPreserved', 'oneMinimal'].filter((key) => Object.hasOwn(report, key)).map((key) => [key, report[key]]));
}
function checkSelfVerification(api, bundle, report, options, complete) {
  const verified = api.verifyConfiguredWindowV4(bundle, report, options);
  assert.equal(verified.valid, complete);
  assert.equal(verified.reportMatches, true);
  return verified;
}

test('independent two-slot manifest preserves both existing four-slot inventories', () => {
  assert.equal(before['core.mjs'], manifest.coreSha256);
  assert.deepEqual(Object.keys(manifest.configuredCoreSha256).sort(), [
    'configured-session-core.mjs', 'source-components-core.mjs', 'sql-fetch-core.mjs', 'sql-projection-core.mjs'].sort());
  const windows = ['sql-projection-v2-core.mjs', 'configured-window-v2.mjs',
    'configured-window-v2-host.mjs', 'configured-window-v2-standalone.mjs'];
  assert.deepEqual(Object.keys(manifest.configuredWindowRuntimeSha256).sort(), windows.sort());
  assert.deepEqual(Object.keys(manifest.structuredWindowRuntimeSha256).sort(), [
    'structured-window-verification-core.mjs', 'configured-window-v2-structured.mjs'].sort());
  for (const field of ['configuredWindowRuntimeSha256', 'structuredWindowRuntimeSha256']) {
    for (const [name, digest] of Object.entries(manifest[field])) assert.equal(before[name], digest);
  }
});

test('explicit module preserves all host APIs, limits and independent caller inputs', () => {
  assert.deepEqual(Object.keys(structured).sort(), Object.keys(normal).sort());
  assert.deepEqual(structured.CONFIGURED_WINDOW_V4_LIMITS, normal.CONFIGURED_WINDOW_V4_LIMITS);
  assert.deepEqual(structured.CONFIGURED_WINDOW_REDUCTION_V4_LIMITS, normal.CONFIGURED_WINDOW_REDUCTION_V4_LIMITS);
  for (const api of [normal, structured]) {
    assert.throws(() => api.analyzeConfiguredWindowV4('{}', {}), TypeError);
    assert.throws(() => api.verifyConfiguredWindowV4('{}', {}, {config: '{}'}), TypeError);
    assert.throws(() => api.reduceConfiguredWindowV4('{}', {config: '{}', policy: '{}'}), TypeError);
  }
});

test('invalid analysis agrees on decisions and flags with each profile independently replayed', () => {
  const options = {config: '{}', policy: '{}'};
  const reports = [normal, structured].map((api) => {
    const text = api.analyzeConfiguredWindowTextV4('{}', '{}', '{}');
    const report = api.analyzeConfiguredWindowV4('{}', options);
    assert.deepEqual(text, report);
    assert.equal(report.status, 'invalid');
    assert.equal(report.coverageComplete, false);
    checkSelfVerification(api, '{}', report, options, false);
    assert.equal(api.verifyConfiguredWindowV4('{}', {...report, coverageComplete: true}, options).valid, false);
    return report;
  });
  // The compiled profiles may identify errors at different source locations.
  assert.deepEqual(flags(reports[0]), flags(reports[1]));
});

test('invalid reduction agrees on flags without authorizing a source window', () => {
  const options = {config: '{}', policy: '{}', preserveModel: 'serializable'};
  const reports = [normal, structured].map((api) => {
    const text = api.reduceConfiguredWindowTextV4('{}', '{}', '{}', '{"preserveModel":"serializable"}');
    const report = api.reduceConfiguredWindowV4('{}', options);
    assert.deepEqual(text, report);
    assert.equal(report.windowVerified, false);
    assert.equal(report.refutationPreserved, false);
    assert.equal(report.oneMinimal, false);
    const verified = api.verifyConfiguredWindowReductionV4('{}', report, options);
    assert.equal(verified.valid, false);
    assert.equal(verified.reportMatches, true);
    assert.equal(verified.refutationVerified, false);
    assert.equal(verified.oneMinimalVerified, false);
    return report;
  });
  assert.deepEqual(flags(reports[0]), flags(reports[1]));
});

test('profile does not relax raw-text or independent-budget host boundaries', () => {
  for (const api of [normal, structured]) {
    const options = {config: '{}', policy: '{}'};
    assert.throws(() => api.analyzeConfiguredWindowV4({}, options), TypeError);
    assert.throws(() => api.analyzeConfiguredWindowV4('\ud800', options), TypeError);
    assert.throws(() => api.analyzeConfiguredWindowV4('{}', {...options, maxPointChecks: -1}), RangeError);
    assert.throws(() => api.analyzeConfiguredWindowV4('{}', {...options, maxSerialOperationChecks: 1000001}), RangeError);
  }
});

let originalCases = 0;
let originalReceiptSha256 = null;
if (args.receipt) {
  const receiptText = readFileSync(resolve(args.receipt), 'utf8');
  const receipt = JSON.parse(receiptText);
  originalReceiptSha256 = sha(receiptText);
  assert.equal(receipt.passed, true, 'Original database producer did not pass');
  assert.equal(receipt.actualDatabaseExecution, true, 'Need actual database observations');
  const fixtures = receipt.records.flatMap((record) => record.analysisFixtures.map((fixture) => ({...fixture, keyType: record.keyType})));
  assert(fixtures.length > 0, 'No original window fixtures');
  for (const fixture of fixtures) {
    test(`original ${fixture.keyType}/${fixture.name}: full analysis/reduction, counters, bytes and cross-profile verification`, () => {
      const bundle = readFileSync(fixture.bundle, 'utf8');
      assert.equal(sha(bundle), fixture.bundleSha256);
      const source = {config: fixture.config, policy: fixture.policy};
      const options = {...source, ...fixture.analysisOptions};
      const analysisOptionsText = JSON.stringify(fixture.analysisOptions ?? {});
      const configText = JSON.stringify(fixture.config), policyText = JSON.stringify(fixture.policy);
      const complete = fixture.coverageComplete ?? fixture.expected !== 'unknown';
      const expected = fixture.expected === 'compatible' ? 'checked-compatible' : fixture.expected;
      const raw = wireCores.map((core) => core.analyze_configured_window_v2_json(configText, policyText, bundle, analysisOptionsText));
      const reports = raw.map(JSON.parse);
      for (let index = 0; index < 2; index++) {
        const api = [normal, structured][index], report = reports[index];
        assert.equal(report.status, expected);
        assert.equal(report.coverageComplete, complete);
        assert.equal(report.sourceAuthenticated, false);
        if (fixture.expectedReason) assert(report.reason?.includes(fixture.expectedReason), report.reason);
        assert.deepEqual(api.analyzeConfiguredWindowV4(bundle, options), report);
        assert.deepEqual(api.analyzeConfiguredWindowTextV4(bundle, configText, policyText, analysisOptionsText), report);
        checkSelfVerification(api, bundle, report, options, complete);
        const other = [normal, structured][1 - index];
        assert.equal(api.verifyConfiguredWindowV4(bundle, reports[1 - index], options).valid, complete);
        assert.equal(other.verifyConfiguredWindowV4(bundle, {...report, status: 'forged'}, options).valid, false);
      }
      if (complete) {
        assert.deepEqual(reports[0], reports[1]);
        assert.equal(raw[0], raw[1], 'Complete report wire bytes differ');
        assert.equal(Buffer.byteLength(raw[0]), Buffer.byteLength(raw[1]));
      } else assert.deepEqual(flags(reports[0]), flags(reports[1]));

      const reduction = {preserveModel: 'serializable', reductionOptions: {maxChecks: 256}};
      if (fixture.analysisOptions) reduction.windowOptions = fixture.analysisOptions;
      const target = {...source, ...reduction};
      const reductionOptionsText = JSON.stringify(reduction);
      const reducedRaw = wireCores.map((core) => core.reduce_configured_window_v2_json(configText, policyText, bundle, reductionOptionsText));
      const reductions = reducedRaw.map(JSON.parse);
      for (let index = 0; index < 2; index++) {
        const api = [normal, structured][index], reduced = reductions[index];
        assert.equal(reduced.windowVerified, complete);
        assert.deepEqual(api.reduceConfiguredWindowV4(bundle, target), reduced);
        assert.deepEqual(api.reduceConfiguredWindowTextV4(bundle, configText, policyText, reductionOptionsText), reduced);
        const verified = api.verifyConfiguredWindowReductionV4(bundle, reduced, target);
        assert.equal(verified.valid, complete);
        assert.equal(verified.reportMatches, true);
        assert.equal(api.verifyConfiguredWindowReductionV4(bundle, reductions[1 - index], target).valid, complete);
        assert.equal(api.verifyConfiguredWindowReductionV4(bundle, {...reduced, oneMinimal: !reduced.oneMinimal}, target).valid, false);
        if (fixture.expected === 'refuted') {
          assert.equal(reduced.refutationPreserved, true);
          assert.equal(reduced.oneMinimal, true);
          if (fixture.expectedReducedTransactions != null) assert.equal(reduced.reduction.selectedTransactions.length, fixture.expectedReducedTransactions);
        } else {
          assert.equal(reduced.refutationPreserved, false);
          assert.equal(reduced.oneMinimal, false);
        }
      }
      if (complete) {
        assert.deepEqual(reductions[0], reductions[1]);
        assert.equal(reducedRaw[0], reducedRaw[1], 'Complete reduction wire bytes differ');
      } else assert.deepEqual(flags(reductions[0]), flags(reductions[1]));
      assert.equal(sha(readFileSync(fixture.bundle)), fixture.bundleSha256);
    });
    originalCases++;
  }
  assert.equal(sha(readFileSync(resolve(args.receipt))), originalReceiptSha256);
}

test('all runtime bytes remain unchanged throughout profile replay', () => assert.deepEqual(hashes(), before));
const result = {format: 'configured-window-structured-consumer/v1', passed: results.every((entry) => entry.passed),
  checks: results.length, failed: results.filter((entry) => !entry.passed).length, originalCases,
  actualDatabaseExecution: false, moonbitSemanticsExecuted: true, formalPerformanceMeasurement: false,
  originalReceiptSha256, runtimeSha256: before, results};
const text = JSON.stringify(result);
if (args.output) writeFileSync(resolve(args.output), text + '\n');
console.log(text);
if (!result.passed) process.exitCode = 1;
