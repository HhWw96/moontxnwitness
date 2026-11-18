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
  reduce_configured_window_v2_json: (...args) => {
    calls.push(args);
    return JSON.stringify({format: 'fake-window-reduction', status: 'unchanged', oneMinimal: true,
      originalTextSha256: args.map(sha)});
  },
  verify_configured_window_reduction_v2_json: (config, policy, bundle, report, options) => {
    const recomputed = JSON.parse(core.reduce_configured_window_v2_json(config, policy, bundle, options));
    const valid = JSON.stringify(JSON.parse(report)) === JSON.stringify(recomputed);
    return JSON.stringify({valid, reportMatches: valid, refutationVerified: valid, oneMinimalVerified: valid});
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
const reductionOptions = {...independent, preserveModel: 'serializable', reductionOptions: {
  maxChecks: 256, modelOptions: {maxSourceChecks: 1000000, maxStates: 100000, maxEdgeChecks: 1000000},
}};
test('reduction requires independent configuration policy and exact explicit model', () => {
  for (const options of [{}, independent, {...reductionOptions, preserveModel: 'read-committed'}]) {
    assert.throws(() => sdk.reduceConfiguredWindowV4(bundle, options), TypeError);
  }
  assert.throws(() => sdk.reduceConfiguredWindowV4(JSON.parse(bundle), reductionOptions), TypeError);
});
test('reduction maximum and zero budgets retain independent argument order', () => {
  sdk.reduceConfiguredWindowV4(bundle, reductionOptions);
  assert.deepEqual(calls.at(-1), [config, policy, bundle, JSON.stringify({preserveModel: 'serializable', reductionOptions: reductionOptions.reductionOptions})]);
  sdk.reduceConfiguredWindowV4(bundle, {...independent, preserveModel: 'serializable', reductionOptions: {
    maxChecks: 0, modelOptions: {maxSourceChecks: 0, maxStates: 0, maxEdgeChecks: 0},
  }});
  assert.equal(JSON.parse(calls.at(-1)[3]).reductionOptions.maxChecks, 0);
});
test('reduction rejects authority claims alternative models and out-of-range budgets', () => {
  for (const extra of [{history: {}}, {sourceAuthenticated: true}, {model: 'serializable'}]) {
    assert.throws(() => sdk.reduceConfiguredWindowV4(bundle, {...reductionOptions, ...extra}), TypeError);
  }
  for (const nested of [{maxChecks: 257}, {maxChecks: -1}, {maxChecks: 0.5}, {modelOptions: {models: ['serializable']}},
    {modelOptions: {clients: []}}, {modelOptions: {realtimeKnown: true}}, {modelOptions: {maxStates: 100001}}]) {
    assert.throws(() => sdk.reduceConfiguredWindowV4(bundle, {...reductionOptions, reductionOptions: nested}));
  }
});
test('reduction verification cannot select limits from its report', () => {
  const report = sdk.reduceConfiguredWindowV4(bundle, reductionOptions);
  assert.equal(sdk.verifyConfiguredWindowReductionV4(bundle, report, reductionOptions).valid, true);
  assert.equal(sdk.verifyConfiguredWindowReductionV4(bundle, report, {...reductionOptions, reductionOptions: {maxChecks: 0}}).valid, false);
  assert.equal(sdk.verifyConfiguredWindowReductionV4(bundle + ' ', report, reductionOptions).valid, false);
  assert.equal(sdk.verifyConfiguredWindowReductionV4(bundle, {...report, oneMinimal: false}, reductionOptions).valid, false);
});
test('reduction text entries preserve repeated original option and report keys', () => {
  const limits = '{"preserveModel":"serializable","preserveModel":"read-committed"}';
  sdk.reduceConfiguredWindowTextV4(bundle, config, policy, limits);
  assert.deepEqual(calls.at(-1), [config, policy, bundle, limits]);
  let received;
  const mock = createConfiguredWindowV4({...core, verify_configured_window_reduction_v2_json: (...args) => {
    received = args; return '{"valid":false}';
  }});
  mock.verifyConfiguredWindowReductionTextV4(bundle, '{"oneMinimal":true,"oneMinimal":false}', config, policy, limits);
  assert.deepEqual(received, [config, policy, bundle, '{"oneMinimal":true,"oneMinimal":false}', limits]);
});
// This deliberately small presentation fixture does not describe a SQL/model run.
function presentationFixture() {
  const originalSql = 'SELECT "<script>evil()</script>" FROM table WHERE id=%s';
  const executedSql = 'SELECT projected FROM table WHERE id=%s';
  const projection = {descriptor: {originalSql, originalParameters: {value: '<img src=x onerror=evil()>'},
    projectedSql: executedSql, businessResult: {mode: 'rows'}}};
  const native = {statementSeq: 17, tx: 'tx', projectionNoteSeq: 2, resultId: 'result', native: {rows: [['MQ==']]}};
  const lifecycle = [{seq: 2, kind: 'configured-point-projection', frameText: JSON.stringify(projection)},
    {seq: 3, kind: 'configured-point-native', frameText: JSON.stringify(native)},
    {seq: 4, kind: 'configured-point-delivery', frameText: JSON.stringify({resultId: 'result', statementSeq: 17, tx: 'tx', rows: [['business-only']]})}];
  const history = {events: [{seq: 1, kind: 'snapshot'}, {seq: 2, kind: 'begin', tx: 'tx'},
    {seq: 3, kind: 'begin', tx: 'noise'}, {seq: 4, kind: 'row_read', tx: 'tx', rows: [{version: 'row:1'}]},
    {seq: 5, kind: 'commit_request', tx: 'tx'}, {seq: 6, kind: 'commit_ok', tx: 'tx'}]};
  const data = {format: 'moontxnwitness-configured-window-analysis/v2', status: 'checked-compatible',
    sourceAuthenticated: false, coverageComplete: true, history,
    operationSources: [{historySeq: 4, originalStatementSeq: 17, projectionNoteSeq: 2, nativeNoteSeq: 3}],
    startSnapshot: {rows: {'1': {version: 'row:1'}}}, endSnapshot: {effects: {'1': {version: 'row:1'}}},
    model: {status: 'checked-compatible'}, itemCategory: {}, serialReplay: {judgment: {status: 'consistent'}}};
  const text = JSON.stringify({lifecycleText: lifecycle.map(JSON.stringify).join('\n') + '\n',
    diagnosticTraceText: JSON.stringify({events: [{seq: 17, kind: 'statement', tx: 'tx', sql: executedSql}]})});
  const reduction = {format: 'moontxnwitness-configured-window-reduction/v1', status: 'budget', oneMinimal: false,
    window: {history}, reduction: {originalEventSequence: [1, 2, 4, 5, 6],
      analysisView: {history: {events: history.events.filter(event => event.seq !== 3).map((event, index) => ({...event, seq: index + 1}))}},
      classification: {models: [{rules: [{rule: 'graph/D/data-only', evidence: {witness: {
        steps: [{sources: [{query: {readSeq: 3}, source: {sourceSeq: 1}}]}],
      }}}]}]}, selectedTransactions: ['tx'], removedTransactions: ['noise']}};
  return {text, data, reduction};
}
function presentationCore(data, verification = {valid: true, refutationVerified: true, oneMinimalVerified: false}) {
  return createConfiguredWindowV4({...core,
    verify_configured_window_v2_json: () => JSON.stringify({valid: true, recomputed: data}),
    verify_configured_window_reduction_v2_json: () => JSON.stringify(verification)});
}
test('explanation refuses a failed verifier before parsing presentation fields', () => {
  const mock = createConfiguredWindowV4({...core, verify_configured_window_v2_json: () => '{"valid":false}'});
  assert.throws(() => mock.explainConfiguredWindowV4('not JSON', {}, independent), /does not match/);
});
test('explanation follows explicit original mappings and escapes SQL parameters and rows', () => {
  const fixture = presentationFixture(), html = presentationCore(fixture.data).explainConfiguredWindowV4(fixture.text, fixture.data, independent);
  assert(html.includes('Content-Security-Policy'));
  assert(html.includes("default-src 'none'"));
  assert(html.includes('&lt;script&gt;evil()&lt;/script&gt;'));
  assert(html.includes('&lt;img src=x onerror=evil()&gt;'));
  assert(!html.includes('<script>evil()'));
  assert(html.includes('Actual business deliveries'));
  assert(html.includes('business-only'));
  assert(html.includes('id="history-4"'));
});
test('explanation rejects absent history binding instead of guessing array positions', () => {
  const fixture = presentationFixture(); delete fixture.data.operationSources[0].historySeq;
  assert.throws(() => presentationCore(fixture.data).explainConfiguredWindowV4(fixture.text, fixture.data, independent), /explicit history/);
});
test('optional reduction always requires independent options and its verifier', () => {
  const fixture = presentationFixture(), mock = presentationCore(fixture.data);
  assert.throws(() => mock.explainConfiguredWindowV4(fixture.text, fixture.data, independent, {reduction: fixture.reduction}), /both required/);
  const refused = presentationCore(fixture.data, {valid: false});
  assert.throws(() => refused.explainConfiguredWindowV4(fixture.text, fixture.data, independent,
    {reduction: fixture.reduction, reductionOptions}), /does not match/);
});
test('reduced witness references map through original sequence and minimality stays separate', () => {
  const fixture = presentationFixture();
  const html = presentationCore(fixture.data).explainConfiguredWindowV4(fixture.text, fixture.data, independent,
    {reduction: fixture.reduction, reductionOptions});
  assert(html.includes('href="#history-4">row_read 4</a>'));
  assert(html.includes('Report recomputed: true. Refutation verified: true. Single-minimality verified: false.'));
  const unknown = presentationCore(fixture.data, {valid: true, refutationVerified: false, oneMinimalVerified: false})
    .explainConfiguredWindowV4(fixture.text, fixture.data, independent, {reduction: fixture.reduction, reductionOptions});
  assert(unknown.includes('Refutation verified: false. Single-minimality verified: false.'));
});
test('explanation rejects invalid reduced mappings and unbound history', () => {
  const fixture = presentationFixture();
  fixture.reduction.reduction.originalEventSequence[2] = 999;
  assert.throws(() => presentationCore(fixture.data).explainConfiguredWindowV4(fixture.text, fixture.data, independent,
    {reduction: fixture.reduction, reductionOptions}), /mapping/);
  fixture.reduction.window.history = {events: []};
  assert.throws(() => presentationCore(fixture.data).explainConfiguredWindowV4(fixture.text, fixture.data, independent,
    {reduction: fixture.reduction, reductionOptions}), /bind/);
});
console.log(JSON.stringify({format: 'configured-window-v2-host-boundaries/v1', passed: results.every(item => item.passed),
  checks: results.length, failed: results.filter(item => !item.passed).length, results,
  fakeCore: true, moonbitSemanticsExecuted: false, actualDatabaseExecution: false}));
if (results.some(item => !item.passed)) process.exitCode = 1;
