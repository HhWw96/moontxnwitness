import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const runtime = resolve(process.env.MTW_RELATION_MODELS_RUNTIME || resolve(root, 'dist'));
const {
  classifyRelationModelsV4: classify,
  verifyRelationModelsV4: verify,
  parseRelationModelOptionsV4: parse,
  makeRelationModelsCapsuleV4: make,
  replayRelationModelsCapsuleV4: replay,
} = await import(pathToFileURL(resolve(runtime, 'relation-models-v4.mjs')));
const hash = text => createHash('sha256').update(text).digest('hex');
const coreSha256 = hash(readFileSync(resolve(runtime, 'core.mjs')));
const results = [];
function check(name, run) {
  try {
    run();
    results.push({name, passed: true});
  } catch (error) {
    results.push({name, passed: false, error: error.stack});
  }
}

const good = {
  traceSchema: 3,
  dataModel: 'relation-set-v1',
  clockDomain: 'relation-model-sdk-example',
  relationSchema: {items: {primaryKey: 'id', columns: {id: 'int64', value: 'text'}}},
  scope: {exclusiveWriters: true, completeSnapshotTables: ['items']},
  gaps: [],
  events: [
    {seq: 1, time: 0, kind: 'snapshot', consistent: true, initial: {items: []}},
    {seq: 2, time: 1, kind: 'begin', tx: 'A', connection: 'physical-A'},
    {seq: 3, time: 2, kind: 'row_read', tx: 'A', relation: 'items', predicate: [{column: 'value', op: 'eq', value: 'yes'}], rows: [], complete: true},
    {seq: 4, time: 3, kind: 'commit_request', tx: 'A'},
    {seq: 5, time: 4, kind: 'commit_ok', tx: 'A'},
  ],
};
const skew = JSON.parse(readFileSync(resolve(root, 'examples/relation-predicate-categories.json'), 'utf8'));
const register = JSON.parse(readFileSync(resolve(root, 'examples/models-v4-register.json'), 'utf8'));
const options = {models: 'elle-core'};
const statuses = report => Object.fromEntries(report.models.map(model => [model.model, model.status]));
const stale = structuredClone(good);
stale.events = [
  {kind: 'snapshot', consistent: true, initial: {items: [{key: '1', version: 'v0', values: {value: 'zero'}}]}},
  {kind: 'begin', tx: 'W', connection: 'physical-W'},
  {kind: 'row_write', tx: 'W', relation: 'items', key: '1', action: 'update', predecessor: 'v0', version: 'w1', values: {value: 'one'}},
  {kind: 'commit_request', tx: 'W'}, {kind: 'commit_ok', tx: 'W'},
  {kind: 'begin', tx: 'R', connection: 'physical-R'},
  {kind: 'row_read', tx: 'R', relation: 'items', predicate: [{column: 'id', op: 'eq', value: '1'}], rows: [{key: '1', version: 'v0', values: {value: 'zero'}}], complete: true},
  {kind: 'commit_request', tx: 'R'}, {kind: 'commit_ok', tx: 'R'},
].map((event, index) => ({...event, seq: index + 1, time: index}));

check('default policy checks exactly six canonical models', () => {
  const report = classify(good);
  assert.equal(report.models.length, 6);
  assert.equal(report.status, 'checked-compatible');
  assert.equal(verify(good, report).valid, true);
});
check('fourteen relation model definitions each return a verified result', () => {
  const report = classify(good, options);
  assert.equal(report.models.length, 14);
  assert.equal(report.semanticContract, 'relation-predicate-models/v1');
  assert.ok(report.models.every(model => model.status === 'checked-compatible'));
  assert.equal(verify(good, report, options).valid, true);
});
check('predicate skew distinguishes serializable from RR and SI', () => {
  const report = classify(skew, options);
  const actual = statuses(report);
  assert.equal(actual.serializable, 'refuted');
  assert.equal(actual['repeatable-read'], 'checked-compatible');
  assert.equal(actual['snapshot-isolation'], 'checked-compatible');
  assert.equal(verify(skew, report, options).valid, true);
});
check('partial delivered query remains unknown', () => {
  const source = structuredClone(good);
  source.events.find(event => event.kind === 'row_read').complete = false;
  assert.equal(classify(source, options).status, 'unknown');
});
check('exhausted search remains unknown and independently replayable', () => {
  const policy = {...options, maxStates: 0};
  const report = classify(good, policy);
  assert.equal(report.status, 'unknown');
  assert.equal(verify(good, report, policy).valid, true);
  assert.equal(verify(good, report, options).valid, false);
});
check('wrong source model is rejected', () => assert.throws(() => classify(register, options)));
check('wrong source model cannot verify a relation report', () => assert.equal(verify(register, classify(good, options), options).valid, false));
check('unknown real time removes RT-only violations without changing data analysis', () => {
  const policy = {models: ['serializable', 'strict-serializable'], realtimeKnown: false};
  const report = classify(stale, policy);
  assert.equal(statuses(report).serializable, 'checked-compatible');
  assert.equal(statuses(report)['strict-serializable'], 'unknown');
  assert.equal(report.orderFacts.realtimeComplete, false);
  assert.deepEqual(report.sourcePolicy, {realtimeKnown: false});
  assert.equal(verify(stale, report, policy).valid, true);
  assert.equal(verify(stale, report, {...policy, realtimeKnown: true}).valid, false);
  assert.equal(replay(make(stale, policy), policy).valid, true);
  assert.equal(replay(make(stale, policy), {...policy, realtimeKnown: true}).valid, false);
});
check('unknown real time preserves an independently established data G2 refutation', () => {
  const policy = {models: ['strict-serializable'], realtimeKnown: false};
  assert.equal(classify(skew, policy).status, 'refuted');
});
check('unknown real time preserves separately declared session constraints', () => {
  const policy = {models: ['strong-session-serializable', 'strict-serializable'], realtimeKnown: false, clients: [{id: 'logical', transactions: ['W', 'R']}], clientsComplete: true};
  const report = statuses(classify(stale, policy));
  assert.equal(report['strong-session-serializable'], 'refuted');
  assert.equal(report['strict-serializable'], 'unknown');
});
check('missing mandatory clock syntax remains invalid even when real time is unknown', () => {
  const missing = structuredClone(stale);
  delete missing.clockDomain;
  assert.throws(() => classify(missing, {realtimeKnown: false}));
});

for (const [label, input] of [
  ['unknown field', {allComplete: true}],
  ['unknown model', {models: ['unknown']}],
  ['duplicate model', {models: ['serializable', 'serializable']}],
  ['empty model list', {models: []}],
  ['negative states', {maxStates: -1}],
  ['fractional edge budget', {maxEdgeChecks: 0.5}],
  ['excessive state budget', {maxStates: 100001}],
  ['excessive source budget', {maxSourceChecks: 1000001}],
  ['invalid logical-client flag', {clientsComplete: 1}],
  ['invalid real-time flag', {realtimeKnown: 1}],
  ['duplicate real-time policy', '{"realtimeKnown":false,"realtime\\u004bnown":true}'],
  ['array options', []],
  ['null options', null],
  ['decoded duplicate key', '{"models":"elle-core","mo\\u0064els":["serializable"]}'],
  ['nested duplicate client key', '{"clients":[{"id":"a","transactions":[],"trans\\u0061ctions":[]}]}'],
  ['duplicate budget', '{"maxStates":0,"maxStates":100000}'],
  ['oversized option text', ' '.repeat(8193)],
]) {
  check('strict options reject ' + label, () => assert.throws(() => parse(input)));
}
check('option parser preserves omitted fields for command merging', () => assert.deepEqual(parse('{"models":["serializable"]}'), {models: ['serializable']}));
check('decoded duplicate source keys are rejected', () => {
  const text = '{"traceSchema":3,' + JSON.stringify(good).slice(1);
  assert.throws(() => classify(text, options));
});
check('decoded duplicate report keys are rejected', () => {
  const text = '{"schemaVersion":4,' + JSON.stringify(classify(good, options)).slice(1);
  assert.equal(verify(good, text, options).valid, false);
});
for (const [label, policy] of [
  ['model selection', {models: ['serializable']}],
  ['source budget', {...options, maxSourceChecks: 999999}],
  ['state budget', {...options, maxStates: 99999}],
  ['edge budget', {...options, maxEdgeChecks: 999999}],
  ['logical-client membership', {...options, clients: [{id: 'logical-A', transactions: ['A']}], clientsComplete: true}],
]) {
  check('verification binds independent ' + label, () => assert.equal(verify(good, classify(good, options), policy).valid, false));
}
check('altered original query cannot verify', () => {
  const source = structuredClone(good);
  source.events.find(event => event.kind === 'row_read').predicate[0].value = 'different';
  assert.equal(verify(source, classify(good, options), options).valid, false);
});
for (const field of ['status', 'semanticContract', 'algorithm']) {
  check('altered report ' + field + ' cannot verify', () => {
    const report = classify(good, options);
    report[field] = 'altered';
    assert.equal(verify(good, report, options).valid, false);
  });
}
check('generic report identity cannot select the relation verifier', () => {
  const report = classify(good, options);
  report.format = 'moontxnwitness-model-composition/v4';
  assert.equal(verify(good, report, options).valid, false);
});

check('source-bound relation capsule replays from independent options', () => assert.equal(replay(make(good, options), options).valid, true));
check('default six-model capsule uses the fixed default policy', () => assert.equal(replay(make(good)).valid, true));
check('embedded fourteen-model selection does not grant replay policy', () => assert.equal(replay(make(good, options)).valid, false));
check('changed producer version is descriptive metadata', () => {
  const capsule = JSON.parse(make(good, options));
  capsule.producer.version = 'another-producer';
  assert.equal(replay(capsule, options).valid, true);
});
for (const key of ['source', 'options', 'report']) {
  check('capsule rejects altered ' + key + ' digest', () => {
    const capsule = JSON.parse(make(good, options));
    capsule[key + 'Sha256'] = '0'.repeat(64);
    assert.equal(replay(capsule, options).valid, false);
  });
}
check('rehashed fabricated conclusion fails semantic replay', () => {
  const capsule = JSON.parse(make(good, options));
  const report = JSON.parse(capsule.reportText);
  report.models[0].status = 'refuted';
  capsule.reportText = JSON.stringify(report);
  capsule.reportSha256 = hash(capsule.reportText);
  assert.equal(replay(capsule, options).valid, false);
});
check('rehashed embedded option change cannot choose caller budgets', () => {
  const capsule = JSON.parse(make(good, options));
  const policy = JSON.parse(capsule.optionsText);
  policy.maxStates = 0;
  capsule.optionsText = JSON.stringify(policy);
  capsule.optionsSha256 = hash(capsule.optionsText);
  assert.equal(replay(capsule, options).valid, false);
});
check('capsule duplicate decoded fields are rejected', () => {
  const text = make(good, options);
  assert.equal(replay('{"schemaVersion":4,' + text.slice(1), options).valid, false);
});
check('capsule unknown fields cannot introduce code', () => {
  const capsule = JSON.parse(make(good, options));
  capsule.code = 'run';
  assert.equal(replay(capsule, options).valid, false);
});
check('source and caller objects remain detached', () => {
  const before = JSON.stringify(good);
  const report = classify(good, options);
  report.observations.history.events.length = 0;
  assert.equal(JSON.stringify(good), before);
  assert.equal(classify(good, options).status, 'checked-compatible');
});
check('compiled core bytes remain unchanged', () => assert.equal(hash(readFileSync(resolve(runtime, 'core.mjs'))), coreSha256));

const summary = {
  format: 'moontxnwitness-relation-model-sdk-check/v1',
  passed: results.every(result => result.passed),
  tests: results.length,
  coreSha256,
  failed: results.filter(result => !result.passed),
  results,
};
const output = resolve(process.env.MTW_RELATION_MODELS_ARTIFACTS || resolve(root, 'artifacts', 'relation-models-sdk-' + Date.now()));
mkdirSync(output, {recursive: true});
const receipt = resolve(output, 'receipt.json');
writeFileSync(receipt, JSON.stringify(summary, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({passed: summary.passed, tests: summary.tests, failed: summary.failed, receipt}));
if (!summary.passed) process.exitCode = 1;
