// Deterministic boundary checks; this fake core makes no SQL or model claim.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync} from 'node:fs';
const host = existsSync(new URL('../cmd/configured-window-v2-host.mjs', import.meta.url))
  ? '../cmd/configured-window-v2-host.mjs' : '../dist/configured-window-v2-host.mjs';
const {createConfiguredWindowV4, CONFIGURED_WINDOW_V4_LIMITS} = await import(host);
const sha = value => createHash('sha256').update(value).digest('hex');
const calls = [];
const analyze = (...args) => {
  calls.push(args);
  return JSON.stringify({format: 'fake-window-report', status: 'checked-compatible',
    sourceAuthenticated: false, originalTextSha256: args.map(sha)});
};
const core = {
  analyze_configured_window_v2_json: analyze,
  verify_configured_window_v2_json: (config, policy, bundle, report, options) => {
    const recomputed = JSON.parse(analyze(config, policy, bundle, options));
    const valid = JSON.stringify(JSON.parse(report)) === JSON.stringify(recomputed);
    return JSON.stringify({format: 'fake-window-verification', valid, reportMatches: valid, recomputed});
  },
};
const sdk = createConfiguredWindowV4(core);
const bundle = ' {"configText":"bundle-cannot-authorize", "raw":"原始"}\r\n';
const config = ' {"caller":"config"}\n';
const policy = ' {"caller":"policy"}\r\n';
const independent = {config, policy};
const results = [];
function test(name, fn) {
  try {fn(); results.push({name, passed: true});}
  catch (error) {results.push({name, passed: false, error: error.stack});}
}
test('original bundle and independent config/policy text reach the core unchanged', () => {
  sdk.analyzeConfiguredWindowV4(bundle, independent);
  assert.deepEqual(calls.at(-1), [config, policy, bundle, '{}']);
});
test('bundle object is rejected before parsing or reencoding', () => {
  const count = calls.length;
  assert.throws(() => sdk.analyzeConfiguredWindowV4(JSON.parse(bundle), independent), TypeError);
  assert.equal(calls.length, count);
});
test('embedded policy and configuration cannot replace independent arguments', () => {
  for (const options of [undefined, {}, {config}, {policy}, Object.create(independent)]) {
    assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, options), TypeError);
  }
});
test('null/array configuration and policy are not silently serialized', () => {
  for (const value of [null, [], undefined]) {
    assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, config: value}), TypeError);
    assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, policy: value}), TypeError);
  }
});
test('explicit zero and maximum budgets are forwarded independently', () => {
  const budgets = Object.fromEntries(Object.entries(CONFIGURED_WINDOW_V4_LIMITS).filter(([name]) => name.startsWith('max')));
  sdk.analyzeConfiguredWindowV4(bundle, {...independent, ...budgets});
  assert.deepEqual(JSON.parse(calls.at(-1)[3]), budgets);
  sdk.analyzeConfiguredWindowV4(bundle, {...independent, maxSourceChecks: 0, maxPointChecks: 0});
  assert.deepEqual(JSON.parse(calls.at(-1)[3]), {maxSourceChecks: 0, maxPointChecks: 0});
});
test('negative, fractional, unsafe and over-limit budgets are rejected', () => {
  for (const value of [-1, 0.5, 1000001, Number.MAX_SAFE_INTEGER + 1, NaN, Infinity, '1', null]) {
    assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, maxPointChecks: value}), RangeError);
  }
  assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, maxRows: 16385}), RangeError);
});
test('unknown options cannot silently grant completeness or source authority', () => {
  for (const name of ['sourceAuthenticated', 'completeWindow', 'installationVerified', 'maxChecks']) {
    assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, [name]: true}), TypeError);
  }
});
test('projection options are passed without deriving them from bundle content', () => {
  const projectionOptions = {maxChecks: 0};
  sdk.analyzeConfiguredWindowV4(bundle, {...independent, projectionOptions});
  assert.deepEqual(JSON.parse(calls.at(-1)[3]), {projectionOptions});
  assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, projectionOptions: 'auto'}), TypeError);
});
test('malformed Unicode and UTF-8 byte overflow are rejected before execution', () => {
  assert.throws(() => sdk.analyzeConfiguredWindowV4('\ud800', independent), TypeError);
  assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, config: '月'.repeat(90000)}), TypeError);
  assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, policy: '\udfff'}), TypeError);
});
test('unsafe JSON numbers and omitted non-JSON values require original text', () => {
  for (const value of [Number.MAX_SAFE_INTEGER + 1, NaN, undefined, () => 1, Symbol('x')]) {
    assert.throws(() => sdk.analyzeConfiguredWindowV4(bundle, {...independent, config: {value}}), TypeError);
  }
  const raw = '{"exact":9223372036854775807}';
  sdk.analyzeConfiguredWindowV4(bundle, {...independent, config: raw});
  assert.equal(calls.at(-1)[0], raw);
});
test('CLI text entry preserves duplicate option keys for strict core rejection', () => {
  const limits = ' {"maxPointChecks":0,"maxPointChecks":1}\n';
  sdk.analyzeConfiguredWindowTextV4(bundle, config, policy, limits);
  assert.deepEqual(calls.at(-1), [config, policy, bundle, limits]);
});
test('verification returns the core report and recomputed result', () => {
  const report = sdk.analyzeConfiguredWindowV4(bundle, independent);
  const result = sdk.verifyConfiguredWindowV4(bundle, report, independent);
  assert.equal(result.valid, true);
  assert.equal(result.reportMatches, true);
  assert.deepEqual(result.recomputed, report);
  assert.equal(result.recomputed.sourceAuthenticated, false);
});
test('verification independently supplies configuration policy and all limits', () => {
  const report = sdk.analyzeConfiguredWindowV4(bundle, independent);
  for (const change of [{config: '{"different":true}'}, {policy: '{"different":true}'}, {maxSourceChecks: 0}]) {
    assert.equal(sdk.verifyConfiguredWindowV4(bundle, report, {...independent, ...change}).valid, false);
  }
});
test('tampered report or raw bundle is rechecked rather than trusted', () => {
  const report = sdk.analyzeConfiguredWindowV4(bundle, independent);
  assert.equal(sdk.verifyConfiguredWindowV4(bundle, {...report, sourceAuthenticated: true}, independent).valid, false);
  assert.equal(sdk.verifyConfiguredWindowV4(bundle + ' ', report, independent).valid, false);
});
test('raw report text reaches verification without JSON normalization', () => {
  let received;
  const mock = createConfiguredWindowV4({...core, verify_configured_window_v2_json: (...args) => {
    received = args;
    return '{"valid":false,"reportMatches":false}';
  }});
  const report = ' {"duplicate":0,"duplicate":1}\n';
  assert.equal(mock.verifyConfiguredWindowTextV4(bundle, report, config, policy, '{}').valid, false);
  assert.deepEqual(received, [config, policy, bundle, report, '{}']);
});
console.log(JSON.stringify({format: 'configured-window-v2-host-boundaries/v1', passed: results.every(item => item.passed),
  checks: results.length, failed: results.filter(item => !item.passed).length, results,
  fakeCore: true, moonbitSemanticsExecuted: false, actualDatabaseExecution: false}));
if (results.some(item => !item.passed)) process.exitCode = 1;
