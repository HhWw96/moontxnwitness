// Mock-only tests: importing this file never imports any MoonTxnWitness runtime.
import assert from 'node:assert/strict';
import test from 'node:test';
import { callerOptions, canonicalAscii, evaluateSdkCase, loadPinnedBytes, outcomeFor, parseArgs, sha } from './compare_sdk_v2.mjs';

const fixture = (model = 'point-register-v1') => {
  const input = { traceSchema: 3, dataModel: model, events: [], gaps: [] };
  return { id: 'example', input, inputSha256: sha(canonicalAscii(input)) };
};
const reference = (value = false, eligible = true) => ({ comparisonEligible: eligible, validity: value, cycleSearchTimeout: false });
const report = (status = 'refuted', profile = 'captured-register-full-program/v2') => ({
  format: 'moontxnwitness-model-composition/v4', schemaVersion: 4, sourceProfile: profile,
  models: [{ model: 'serializable', status }], options: { models: ['read-uncommitted'], maxStates: 0 },
});
const api = (result = report(), verification = { valid: true }) => ({
  classifyModelsV4() { return result; }, verifyModelsV4() { return verification; },
});

test('caller options fix model, budgets and original list profile', () => {
  assert.deepEqual(callerOptions('append-list-v1'), { models: ['serializable'], maxSourceChecks: 1000000,
    maxStates: 100000, maxEdgeChecks: 1000000, listProfile: 'captured-list-original-serial/v1' });
  assert.throws(() => callerOptions('relation-set-v1'));
});

test('ASCII canonical source preserves frozen input identity', () => {
  assert.equal(canonicalAscii({ z: '中', a: 1 }), '{"a":1,"z":"\\u4e2d"}');
  assert.equal(canonicalAscii({ z: ['🙂'] }), '{"z":["\\ud83d\\ude42"]}');
});

test('source/reference pins reject rehashed-shape lookalikes before JSON consumption', () => {
  const bytes = Buffer.from('{"value":false}');
  assert.deepEqual(loadPinnedBytes(bytes, sha(bytes)), { value: false });
  assert.throws(() => loadPinnedBytes(Buffer.from('{"value":true }'), sha(bytes)));
});

test('matching refutation and compatibility remain separate from differences', () => {
  assert.equal(evaluateSdkCase(api(), fixture(), reference(false)).outcome, 'match');
  assert.equal(evaluateSdkCase(api(report('checked-compatible')), fixture(), reference(true)).outcome, 'match');
  assert.equal(evaluateSdkCase(api(report('checked-compatible')), fixture(), reference(false)).outcome, 'difference');
});

test('verify receives independently regenerated caller options, never report options', () => {
  let classifiedOptions, verifiedOptions;
  const stub = {
    classifyModelsV4(_source, options) { classifiedOptions = options; options.models[0] = 'read-uncommitted'; return report(); },
    verifyModelsV4(_source, _report, options) { verifiedOptions = options; return { valid: true }; },
  };
  const result = evaluateSdkCase(stub, fixture(), reference(false));
  assert.equal(result.outcome, 'match'); assert.notEqual(classifiedOptions, verifiedOptions);
  assert.deepEqual(verifiedOptions, callerOptions('point-register-v1'));
  assert.deepEqual(result.callerOptions, callerOptions('point-register-v1'));
});

test('SDK unknown/pending never becomes upstream notComparable', () => {
  for (const status of ['unknown', 'pending']) {
    const result = evaluateSdkCase(api(report(status)), fixture(), reference(false));
    assert.equal(result.outcome, 'sdkUnknown'); assert.equal(result.sdkDisposition, 'unknown');
    assert.equal(reference(false).comparisonEligible, true);
  }
});

test('unexpected SDK profile remains eligible SDKunknown with complete report', () => {
  const result = evaluateSdkCase(api(report('refuted', 'effective-list-appends/v1')), fixture('append-list-v1'), reference(false));
  assert.equal(result.outcome, 'sdkUnknown'); assert.equal(result.reason, 'unexpected-sdk-source-profile');
  assert.equal(JSON.parse(result.reportText).sourceProfile, 'effective-list-appends/v1');
});

test('upstream unknown remains upstream notComparable even when SDK is decisive', () => {
  assert.equal(evaluateSdkCase(api(), fixture(), reference(null, false)).outcome, 'upstreamNotComparable');
});

test('verification rejection is a failure, never a match or exclusion', () => {
  const result = evaluateSdkCase(api(report(), { valid: false }), fixture(), reference(false));
  assert.equal(result.outcome, 'failure'); assert.equal(result.verificationAttempted, true);
  assert(result.reportText.includes('refuted'));
});

test('classify errors retain attempted counts and do not fabricate verification', () => {
  const result = evaluateSdkCase({ classifyModelsV4() { throw new Error('broken'); } }, fixture(), reference(false));
  assert.equal(result.outcome, 'failure'); assert.equal(result.classificationAttempted, true);
  assert.equal(result.verificationAttempted, false); assert.equal(result.reportText, null);
});

test('wrong model and report schema are failures after actual verification', () => {
  for (const changed of [{ ...report(), schemaVersion: 3 }, { ...report(), models: [{ model: 'read-committed', status: 'refuted' }] }]) {
    const result = evaluateSdkCase(api(changed), fixture(), reference(false));
    assert.equal(result.outcome, 'failure'); assert.equal(result.verificationAttempted, true);
  }
});

test('source tampering fails before classifier execution', () => {
  const row = fixture(); row.input.events.push({ kind: 'invented' });
  const result = evaluateSdkCase(api(), row, reference(false));
  assert.equal(result.outcome, 'failure'); assert.equal(result.classificationAttempted, false);
});

test('timeout and eligibility dispositions do not reinterpret source judgments', () => {
  assert.equal(outcomeFor(reference(false), 'timeout'), 'timeout');
  assert.equal(outcomeFor(reference(false), 'failure'), 'failure');
  assert.equal(outcomeFor(reference(null, false), 'unknown'), 'upstreamNotComparable');
  assert.equal(outcomeFor({ comparisonEligible: false, cycleSearchTimeout: true }, 'complete'), 'timeout');
});

test('CLI rejects duplicate/unknown/missing options and invalid timeout', () => {
  const required = ['--job', 'job', '--reference', 'ref', '--runtime', 'dist', '--expected-version', '0.5.0',
    '--expected-core-sha', 'a'.repeat(64), '--output', 'out'];
  assert.equal(parseArgs(required).caseTimeoutMs, 30000);
  for (const extra of [['--output', 'other'], ['--unknown', 'x'], ['--case-timeout-ms', '0'], ['--runtime-origin', 'trusted-because-I-say-so']]) {
    assert.throws(() => parseArgs([...required, ...extra]));
  }
  assert.throws(() => parseArgs(required.slice(0, -1)));
});
