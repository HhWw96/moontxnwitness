// Replay retained database observations; this script does not start PostgreSQL.
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
const sdk = await import(pathToFileURL(resolve(runtime, 'configured-window-v2-standalone.mjs')).href);
const capsules = await import(pathToFileURL(resolve(runtime, 'configured-window-v2-capsule.mjs')).href);
const sha256 = value => createHash('sha256').update(value).digest('hex');
const runtimeNames = ['sql-projection-v2-core.mjs', 'configured-window-v2-host.mjs',
  'configured-window-v2-standalone.mjs', 'configured-window-v2-capsule.mjs'];
const runtimeHashes = () => Object.fromEntries(runtimeNames.map(name => [name, sha256(readFileSync(resolve(runtime, name)))]));
const beforeRuntime = runtimeHashes();
const results = [];
function test(name, run) {
  try {run(); results.push({name, passed: true});}
  catch (error) {results.push({name, passed: false, error: error.stack ?? String(error)});}
}

// Rebuild all transport digests after deliberate tampering. A matching outer
// SHA-256 must never substitute for independently recomputed source semantics.
function reseal(value) {
  const body = {
    format: value.format, operation: value.operation,
    bundleText: value.bundleText, bundleSha256: sha256(value.bundleText),
    reportText: value.reportText, reportSha256: sha256(value.reportText),
  };
  return JSON.stringify({...body, capsuleSha256: sha256(JSON.stringify(body))}) + '\n';
}
function changedReport(capsule, change) {
  const value = JSON.parse(capsule), report = JSON.parse(value.reportText);
  change(report);
  value.reportText = JSON.stringify(report);
  return reseal(value);
}

test('factory accepts only an explicit SDK with all existing verification entries', () => {
  assert.throws(() => capsules.createConfiguredWindowCapsulesV4(null), TypeError);
  assert.throws(() => capsules.createConfiguredWindowCapsulesV4({}), TypeError);
  assert.deepEqual(Object.keys(capsules.createConfiguredWindowCapsulesV4(sdk)).sort(), [
    'makeConfiguredWindowCapsuleV4', 'replayConfiguredWindowCapsuleV4',
    'makeConfiguredWindowReductionCapsuleV4', 'replayConfiguredWindowReductionCapsuleV4'].sort());
});

test('strict outer schema and duplicate/escaped keys fail before semantic replay', () => {
  const options = {config: '{}', policy: '{}'};
  const capsule = capsules.makeConfiguredWindowCapsuleV4('{}', options);
  assert.equal(capsules.replayConfiguredWindowCapsuleV4(capsule, options).reportMatches, true);
  for (const altered of [
    capsule.trimEnd(), ' ' + capsule, JSON.stringify(JSON.parse(capsule), null, 2) + '\n',
    capsule.replace('{"format":', '{"format":"ignored","format":'),
    capsule.replace('{"format":', '{"\\u0066ormat":"ignored","format":'),
    capsule.replace('{"format":', '{"\\u0066ormat":'),
    capsule.replace('{"format":', '{"optionsText":"{}","format":'),
    capsule.replace('{"format":', '{"module":"file:///untrusted.mjs","format":'),
    'null', '[]', '{}', '\ud800',
  ]) {
    const checked = capsules.replayConfiguredWindowCapsuleV4(altered, options);
    assert.equal(checked.valid, false);
    assert.equal(checked.envelopeVerified, false);
    assert.equal(checked.sourceAuthenticated, false);
  }
  assert.equal(capsules.replayConfiguredWindowCapsuleV4(JSON.parse(capsule), options).valid, false);
});

test('creation requires independent options and keeps matching invalid diagnostics non-authorizing', () => {
  const options = {config: '{}', policy: '{}'};
  assert.throws(() => capsules.makeConfiguredWindowCapsuleV4('{}'), TypeError);
  assert.throws(() => capsules.makeConfiguredWindowCapsuleV4('{}', {config: '{}'}), TypeError);
  assert.throws(() => capsules.makeConfiguredWindowReductionCapsuleV4('{}', options), TypeError);
  assert.throws(() => capsules.makeConfiguredWindowCapsuleV4({}, options), TypeError);
  assert.throws(() => capsules.makeConfiguredWindowCapsuleV4('\ud800', options), TypeError);
  const capsule = capsules.makeConfiguredWindowCapsuleV4('{}', options);
  const checked = capsules.replayConfiguredWindowCapsuleV4(capsule, options);
  assert.equal(checked.envelopeVerified, true);
  assert.equal(checked.reportMatches, true);
  assert.equal(checked.valid, false);
  assert.equal(checked.status, 'invalid');
  assert.equal(checked.refutationVerified, false);
  assert.equal(checked.oneMinimalVerified, false);
  assert.equal(capsules.replayConfiguredWindowCapsuleV4(capsule).valid, false);
});

test('raw inner UTF-8 limit is checked before invoking the SDK', () => {
  let called = false;
  const wrong = () => {called = true; throw new Error('Should not reach SDK');};
  const api = capsules.createConfiguredWindowCapsulesV4({
    analyzeConfiguredWindowV4: wrong, verifyConfiguredWindowV4: wrong,
    reduceConfiguredWindowV4: wrong, verifyConfiguredWindowReductionV4: wrong,
  });
  const options = {config: '{}', policy: '{}'};
  assert.throws(() => api.makeConfiguredWindowCapsuleV4('é'.repeat(16 * 1024 * 1024 + 1), options), RangeError);
  assert.equal(called, false);
});

test('matching unknown reports remain non-authorizing even when coverage verification succeeds', () => {
  const report = {format: 'moontxnwitness-configured-window-analysis/v2', status: 'unknown', coverageComplete: true};
  const api = capsules.createConfiguredWindowCapsulesV4({
    analyzeConfiguredWindowV4: () => report,
    verifyConfiguredWindowV4: () => ({valid: true, reportMatches: true}),
    reduceConfiguredWindowV4: () => {throw new Error('Not called');},
    verifyConfiguredWindowReductionV4: () => {throw new Error('Not called');},
  });
  const options = {config: '{}', policy: '{}'};
  const result = api.replayConfiguredWindowCapsuleV4(api.makeConfiguredWindowCapsuleV4('{}', options), options);
  assert.equal(result.reportMatches, true);
  assert.equal(result.valid, false);
  assert.equal(result.refutationVerified, false);
});

test('builder refuses a report that does not match same-budget core recomputation', () => {
  const api = capsules.createConfiguredWindowCapsulesV4({
    analyzeConfiguredWindowV4: () => ({format: 'moontxnwitness-configured-window-analysis/v2', status: 'refuted'}),
    verifyConfiguredWindowV4: () => ({valid: false, reportMatches: false}),
    reduceConfiguredWindowV4: () => {throw new Error('Not called');},
    verifyConfiguredWindowReductionV4: () => {throw new Error('Not called');},
  });
  assert.throws(() => api.makeConfiguredWindowCapsuleV4('{}', {config: '{}', policy: '{}'}), /does not independently reproduce/);
});

let originalCases = 0, originalReceiptSha256 = null;
if (args.receipt) {
  const receiptText = readFileSync(resolve(args.receipt), 'utf8');
  const receipt = JSON.parse(receiptText);
  originalReceiptSha256 = sha256(receiptText);
  assert.equal(receipt.passed, true);
  assert.equal(receipt.actualDatabaseExecution, true);
  const fixtures = receipt.records.flatMap(record => record.analysisFixtures.map(fixture => ({...fixture, keyType: record.keyType})));
  assert(fixtures.length > 0, 'Receipt contains no original analysis fixtures');
  for (const fixture of fixtures) {
    test(`original ${fixture.keyType}/${fixture.name}: both capsule domains and independent source/budget verification`, () => {
      const bundle = readFileSync(fixture.bundle, 'utf8');
      assert.equal(sha256(bundle), fixture.bundleSha256);
      const options = {config: fixture.config, policy: fixture.policy};
      const target = {...options, preserveModel: 'serializable', reductionOptions: {maxChecks: 256}};
      const analysisCapsule = capsules.makeConfiguredWindowCapsuleV4(bundle, options);
      const reductionCapsule = capsules.makeConfiguredWindowReductionCapsuleV4(bundle, target);
      const analysis = capsules.replayConfiguredWindowCapsuleV4(analysisCapsule, options);
      const reduced = capsules.replayConfiguredWindowReductionCapsuleV4(reductionCapsule, target);
      const complete = fixture.coverageComplete ?? fixture.expected !== 'unknown';
      const expected = fixture.expected === 'compatible' ? 'checked-compatible' : fixture.expected;
      assert.equal(analysis.status, expected);
      assert.equal(analysis.reportMatches, true);
      assert.equal(analysis.valid, complete && expected !== 'unknown');
      assert.equal(analysis.sourceAuthenticated, false);
      assert.equal(reduced.reportMatches, true);
      assert.equal(reduced.valid, complete && !['unknown', 'invalid'].includes(reduced.status));
      assert.equal(reduced.sourceAuthenticated, false);
      assert.equal(reduced.refutationVerified, complete && fixture.expected === 'refuted');
      assert.equal(reduced.oneMinimalVerified, complete && fixture.expected === 'refuted');
      assert.equal(JSON.parse(analysisCapsule).bundleText, bundle);
      assert.equal(JSON.parse(reductionCapsule).bundleText, bundle);
      assert.deepEqual(analysis.report, sdk.analyzeConfiguredWindowV4(bundle, options));
      assert.deepEqual(reduced.report, sdk.reduceConfiguredWindowV4(bundle, target));
      assert.equal(capsules.replayConfiguredWindowReductionCapsuleV4(analysisCapsule, target).valid, false);
      assert.equal(capsules.replayConfiguredWindowCapsuleV4(reductionCapsule, options).valid, false);

      const claimed = changedReport(analysisCapsule, report => {
        report.status = report.status === 'refuted' ? 'checked-compatible' : 'refuted';
        report.coverageComplete = true;
      });
      const forged = capsules.replayConfiguredWindowCapsuleV4(claimed, options);
      assert.equal(forged.envelopeVerified, true);
      assert.equal(forged.reportMatches, false);
      assert.equal(forged.valid, false);
      const forgedReduction = capsules.replayConfiguredWindowReductionCapsuleV4(
        changedReport(reductionCapsule, report => {report.oneMinimal = !report.oneMinimal;}), target);
      assert.equal(forgedReduction.envelopeVerified, true);
      assert.equal(forgedReduction.reportMatches, false);
      assert.equal(forgedReduction.refutationVerified, false);
      assert.equal(forgedReduction.oneMinimalVerified, false);

      const newBundle = JSON.parse(analysisCapsule);
      newBundle.bundleText += ' ';
      const changed = capsules.replayConfiguredWindowCapsuleV4(reseal(newBundle), options);
      assert.equal(changed.envelopeVerified, true);
      if (complete) assert.equal(changed.reportMatches, false);
      // An unbound failure diagnostic can remain the same after JSON whitespace
      // changes, but it still cannot verify a source window or model result.
      assert.equal(changed.valid, false);
      const newDomain = JSON.parse(analysisCapsule);
      newDomain.format = JSON.parse(reductionCapsule).format;
      newDomain.operation = 'reduction';
      assert.equal(capsules.replayConfiguredWindowReductionCapsuleV4(reseal(newDomain), target).reportMatches, false);

      const config = structuredClone(fixture.config);
      config.table.table += '_not_the_original';
      assert.equal(capsules.replayConfiguredWindowCapsuleV4(analysisCapsule, {...options, config}).reportMatches, false);
      const policy = structuredClone(fixture.policy);
      policy.namespace += '_not_the_original';
      assert.equal(capsules.replayConfiguredWindowCapsuleV4(analysisCapsule, {...options, policy}).reportMatches, false);
      assert.equal(capsules.replayConfiguredWindowCapsuleV4(analysisCapsule, {...options, maxPointChecks: 0}).valid, false);
      assert.equal(capsules.replayConfiguredWindowReductionCapsuleV4(reductionCapsule, {...target, preserveModel: 'strict-serializable'}).valid, false);
      assert.equal(capsules.replayConfiguredWindowReductionCapsuleV4(reductionCapsule,
        {...target, windowOptions: {maxPointChecks: 0}}).valid, false);
      assert.equal(capsules.replayConfiguredWindowReductionCapsuleV4(reductionCapsule,
        {...target, reductionOptions: {maxChecks: 0}}).reportMatches, false);
      assert.equal(sha256(readFileSync(fixture.bundle)), fixture.bundleSha256);
    });
    originalCases++;
  }
  // One complete source window is sufficient to exercise independently selected
  // budget exhaustion in both formats; the original raw window is retained.
  const complete = fixtures.find(fixture => fixture.expected === 'refuted');
  assert(complete, 'Need an actual refutation fixture for budget cases');
  test('budget-exhausted analysis and reduction diagnostics reproduce without valid/refutation claims', () => {
    const bundle = readFileSync(complete.bundle, 'utf8');
    const options = {config: complete.config, policy: complete.policy, maxPointChecks: 0};
    const capsule = capsules.makeConfiguredWindowCapsuleV4(bundle, options);
    const checked = capsules.replayConfiguredWindowCapsuleV4(capsule, options);
    assert.equal(checked.status, 'unknown');
    assert.equal(checked.reportMatches, true);
    assert.equal(checked.valid, false);
    assert.equal(capsules.replayConfiguredWindowCapsuleV4(capsule,
      {config: complete.config, policy: complete.policy}).reportMatches, false);
    const target = {config: complete.config, policy: complete.policy, preserveModel: 'serializable', windowOptions: {maxPointChecks: 0}};
    const reduced = capsules.makeConfiguredWindowReductionCapsuleV4(bundle, target);
    const replayed = capsules.replayConfiguredWindowReductionCapsuleV4(reduced, target);
    assert.equal(replayed.status, 'unknown');
    assert.equal(replayed.reportMatches, true);
    assert.equal(replayed.valid, false);
    assert.equal(replayed.refutationVerified, false);
    assert.equal(replayed.oneMinimalVerified, false);
  });
  test('recomputed outer digests cannot authorize forged report configuration or budget evidence', () => {
    const bundle = readFileSync(complete.bundle, 'utf8');
    const options = {config: complete.config, policy: complete.policy};
    const capsule = capsules.makeConfiguredWindowCapsuleV4(bundle, options);
    for (const field of ['configSha256', 'optionsSha256']) {
      const altered = changedReport(capsule, report => {report[field] = '0'.repeat(64);});
      const checked = capsules.replayConfiguredWindowCapsuleV4(altered, options);
      assert.equal(checked.envelopeVerified, true);
      assert.equal(checked.reportMatches, false);
      assert.equal(checked.valid, false);
    }
    const duplicate = JSON.parse(capsule);
    duplicate.reportText = '{"format":"duplicate",' + duplicate.reportText.slice(1);
    const duplicateChecked = capsules.replayConfiguredWindowCapsuleV4(reseal(duplicate), options);
    assert.equal(duplicateChecked.envelopeVerified, true);
    assert.equal(duplicateChecked.reportMatches, false);
    assert.equal(duplicateChecked.valid, false);
    const target = {...options, preserveModel: 'serializable', reductionOptions: {maxChecks: 256}};
    const reduction = capsules.makeConfiguredWindowReductionCapsuleV4(bundle, target);
    const altered = changedReport(reduction, report => {report.suppliedOptions.reductionOptions.maxChecks = 0;});
    const checked = capsules.replayConfiguredWindowReductionCapsuleV4(altered, target);
    assert.equal(checked.envelopeVerified, true);
    assert.equal(checked.reportMatches, false);
    assert.equal(checked.refutationVerified, false);
    assert.equal(checked.oneMinimalVerified, false);
  });
  assert.equal(sha256(readFileSync(resolve(args.receipt))), originalReceiptSha256);
}

test('all imported runtime and wrapper bytes remain unchanged', () => assert.deepEqual(runtimeHashes(), beforeRuntime));
const result = {format: 'configured-window-v2-capsule-consumer/v1', passed: results.every(entry => entry.passed),
  checks: results.length, failed: results.filter(entry => !entry.passed).length, originalCases,
  actualDatabaseExecution: false, moonbitSemanticsExecuted: true, formalPerformanceMeasurement: false,
  originalReceiptSha256, runtimeSha256: beforeRuntime, results};
const text = JSON.stringify(result);
if (args.output) writeFileSync(resolve(args.output), text + '\n');
console.log(text);
if (!result.passed) process.exitCode = 1;
