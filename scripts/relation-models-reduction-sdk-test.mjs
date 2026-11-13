import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const runtime = resolve(process.env.MTW_RELATION_MODEL_REDUCTION_RUNTIME || resolve(root, 'dist'));
const {
  reduceRelationModelsV4: reduce,
  verifyRelationModelReductionV4: verify,
  parseRelationModelReductionOptionsV4: parse,
  makeRelationModelReductionCapsuleV4: make,
  replayRelationModelReductionCapsuleV4: replay,
} = await import(pathToFileURL(resolve(runtime, 'relation-models-reduction-v4.mjs')));
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

const source = JSON.parse(readFileSync(resolve(root, 'examples/relation-predicate-categories.json'), 'utf8'));
source.events.splice(1, 0,
  {kind: 'begin', tx: 'noise', connection: 'physical-noise'},
  {kind: 'commit_request', tx: 'noise'},
  {kind: 'commit_ok', tx: 'noise'},
);
source.events.forEach((event, index) => { event.seq = index + 1; event.time = index; });
const register = JSON.parse(readFileSync(resolve(root, 'examples/models-v4-register.json'), 'utf8'));
const options = {model: 'serializable'};
const report = reduce(source, options);
const capsuleText = make(source, options);
const stale = structuredClone(source);
stale.events = [
  {kind: 'snapshot', consistent: true, initial: {items: [{key: '1', version: 'v0', values: {value: 'zero'}}]}},
  {kind: 'begin', tx: 'W', connection: 'physical-W'},
  {kind: 'row_write', tx: 'W', relation: 'items', key: '1', action: 'update', predecessor: 'v0', version: 'w1', values: {value: 'one'}},
  {kind: 'commit_request', tx: 'W'}, {kind: 'commit_ok', tx: 'W'},
  {kind: 'begin', tx: 'R', connection: 'physical-R'},
  {kind: 'row_read', tx: 'R', relation: 'items', predicate: [{column: 'id', op: 'eq', value: '1'}], rows: [{key: '1', version: 'v0', values: {value: 'zero'}}], complete: true},
  {kind: 'commit_request', tx: 'R'}, {kind: 'commit_ok', tx: 'R'},
].map((event, index) => ({...event, seq: index + 1, time: index}));

check('fixed model reduction removes noise and verifies the retained refutation', () => {
  assert.equal(report.status, 'reduced');
  assert.equal(report.oneMinimal, true);
  assert.deepEqual(report.selectedTransactions, ['A', 'B']);
  assert.deepEqual(report.removedTransactions, ['noise']);
  assert.equal(report.preserveModel, 'serializable');
  assert.equal(report.classification.status, 'refuted');
  assert.equal(verify(source, report, options).valid, true);
});
check('exact deletion budget distinguishes completed minimality from exhaustion', () => {
  const exact = reduce(source, {...options, maxChecks: 3});
  const short = reduce(source, {...options, maxChecks: 2});
  assert.equal(exact.oneMinimal, true);
  assert.equal(exact.execution.candidateLimitReached, true);
  assert.equal(exact.execution.candidateBudgetExhausted, false);
  assert.equal(short.oneMinimal, false);
  assert.equal(short.status, 'budget');
});
check('zero budget retains original facts and fully revalidates their refutation', () => {
  const zero = {...options, maxChecks: 0};
  const limited = reduce(source, zero);
  assert.equal(limited.status, 'budget');
  assert.equal(limited.oneMinimal, false);
  assert.equal(limited.execution.candidateChecks, 0);
  assert.equal(limited.execution.finalRevalidation, true);
  assert.deepEqual(limited.analysisView, limited.originalFacts);
  assert.equal(verify(source, limited, zero).valid, true);
  assert.equal(verify(source, limited, options).valid, false);
});
check('a legal RR phantom cannot be reduced using serializability as a replacement target', () => {
  const result = reduce(source, {model: 'repeatable-read'});
  assert.equal(result.status, 'not-refuted');
  assert.equal(result.execution.candidateChecks, 0);
  assert.equal(result.classification.status, 'checked-compatible');
});
check('all original events and the derived local-index map remain independently traceable', () => {
  assert.deepEqual(report.originalFacts.history, source);
  assert.equal(report.selectedOriginalEvents.length, report.originalEventSequence.length);
  for (const [index, event] of report.selectedOriginalEvents.entries()) {
    assert.equal(event.seq, report.originalEventSequence[index]);
    assert.deepEqual(event, source.events.find(original => original.seq === event.seq));
    const view = report.analysisView.history.events[index];
    assert.deepEqual({...view, seq: event.seq}, event);
  }
});
check('source and returned evidence do not alias', () => {
  const before = JSON.stringify(source);
  const result = reduce(source, options);
  result.originalFacts.history.events.length = 0;
  result.analysisView.history.events.length = 0;
  assert.equal(JSON.stringify(source), before);
  assert.equal(reduce(source, options).oneMinimal, true);
});
check('wrong source model is rejected', () => assert.throws(() => reduce(register, options)));
check('missing explicit model is rejected at reduction and replay', () => {
  assert.throws(() => reduce(source));
  assert.equal(replay(capsuleText).valid, false);
});
check('nested unknown real-time policy remains bound through reduction verification and capsule replay', () => {
  const policy = {model: 'strict-serializable', modelOptions: {realtimeKnown: false}};
  const result = reduce(stale, policy);
  assert.equal(result.status, 'unknown');
  assert.equal(result.execution.candidateChecks, 0);
  assert.deepEqual(result.sourcePolicy, {realtimeKnown: false});
  assert.equal(verify(stale, result, policy).valid, true);
  assert.equal(verify(stale, result, {model: 'strict-serializable'}).valid, false);
  assert.equal(replay(make(stale, policy), policy).valid, true);
  assert.equal(replay(make(stale, policy), {model: 'strict-serializable'}).valid, false);
});
check('unknown real-time policy is propagated to every data-refutation candidate and final report', () => {
  const result = reduce(source, {model: 'strict-serializable', modelOptions: {realtimeKnown: false}});
  assert.equal(result.classification.status, 'refuted');
  assert.deepEqual(result.sourcePolicy, {realtimeKnown: false});
  assert.deepEqual(result.initialClassification.sourcePolicy, {realtimeKnown: false});
  assert.deepEqual(result.classification.sourcePolicy, {realtimeKnown: false});
  assert.equal(result.oneMinimal, false);
  assert.ok(result.execution.candidateAudit.some(candidate => candidate.classificationStatus === 'unknown'));
});

for (const [label, input] of [
  ['missing target', {}],
  ['unknown target', {model: 'unknown'}],
  ['array target', {model: ['serializable']}],
  ['unknown envelope field', {...options, supported: true}],
  ['negative candidate budget', {...options, maxChecks: -1}],
  ['excessive candidate budget', {...options, maxChecks: 257}],
  ['fractional candidate budget', {...options, maxChecks: 0.5}],
  ['boolean candidate budget', {...options, maxChecks: true}],
  ['null nested options', {...options, modelOptions: null}],
  ['array nested options', {...options, modelOptions: []}],
  ['unknown nested model', {...options, modelOptions: {models: ['unknown']}}],
  ['duplicate nested models', {...options, modelOptions: {models: ['serializable', 'serializable']}}],
  ['unknown nested field', {...options, modelOptions: {complete: true}}],
  ['excessive states', {...options, modelOptions: {maxStates: 100001}}],
  ['excessive source checks', {...options, modelOptions: {maxSourceChecks: 1000001}}],
  ['fractional edge checks', {...options, modelOptions: {maxEdgeChecks: 0.1}}],
  ['invalid client completeness', {...options, modelOptions: {clientsComplete: 1}}],
  ['invalid nested real-time policy', {...options, modelOptions: {realtimeKnown: 1}}],
  ['duplicate nested real-time policy', '{"model":"serializable","modelOptions":{"realtimeKnown":false,"realtime\\u004bnown":true}}'],
  ['null envelope', null],
  ['array envelope', []],
  ['decoded duplicate target', '{"model":"serializable","mo\\u0064el":"read-uncommitted"}'],
  ['decoded duplicate budget', '{"model":"serializable","maxChecks":0,"max\\u0043hecks":256}'],
  ['nested decoded duplicate budget', '{"model":"serializable","modelOptions":{"maxStates":0,"max\\u0053tates":100000}}'],
  ['nested decoded duplicate client', '{"model":"serializable","modelOptions":{"clients":[{"id":"a","transactions":[],"trans\\u0061ctions":[]}]}}'],
  ['oversized option text', ' '.repeat(8193)],
]) {
  check('strict options reject ' + label, () => assert.throws(() => parse(input)));
}
check('option parsing preserves omitted nested defaults', () => assert.deepEqual(parse('{"model":"serializable","maxChecks":0}'), {model: 'serializable', maxChecks: 0}));
check('decoded duplicate source keys cannot survive normalization', () => assert.throws(() => reduce('{"traceSchema":3,' + JSON.stringify(source).slice(1), options)));
check('decoded duplicate report keys cannot hide an incorrect minimum', () => assert.equal(verify(source, '{"oneMinimal":false,' + JSON.stringify(report).slice(1), options).valid, false));
for (const [label, independent] of [
  ['target', {model: 'read-uncommitted'}],
  ['candidate budget', {...options, maxChecks: 0}],
  ['source budget', {...options, modelOptions: {maxSourceChecks: 999999}}],
  ['state budget', {...options, modelOptions: {maxStates: 99999}}],
  ['edge budget', {...options, modelOptions: {maxEdgeChecks: 999999}}],
  ['logical clients', {...options, modelOptions: {clients: [{id: 'logical-A', transactions: ['A']}], clientsComplete: false}}],
]) {
  check('verification binds caller-selected ' + label, () => assert.equal(verify(source, report, independent).valid, false));
}
for (const field of ['status', 'semanticContract', 'classificationContract', 'algorithm', 'preserveModel']) {
  check('changed report ' + field + ' is rejected', () => {
    const altered = structuredClone(report);
    altered[field] = 'altered';
    assert.equal(verify(source, altered, options).valid, false);
  });
}
check('unknown report fields cannot select a runtime', () => assert.equal(verify(source, {...report, runtimePath: 'other'}, options).valid, false));
check('report original events and local mapping are independently recomputed', () => {
  const altered = structuredClone(report);
  altered.selectedOriginalEvents[1].time = 999999;
  altered.originalEventSequence[1] = altered.originalEventSequence[0];
  assert.equal(verify(source, altered, options).valid, false);
});

check('model reduction capsule replays only under the independent target and budgets', () => assert.equal(replay(capsuleText, options).valid, true));
check('descriptive producer version does not select a verifier', () => {
  const capsule = JSON.parse(capsuleText);
  capsule.producer.version = 'another-producer';
  assert.equal(replay(capsule, options).valid, true);
});
for (const key of ['source', 'options', 'report']) {
  check('capsule rejects altered ' + key + ' digest', () => {
    const capsule = JSON.parse(capsuleText);
    capsule[key + 'Sha256'] = '0'.repeat(64);
    assert.equal(replay(capsule, options).valid, false);
  });
}
for (const key of ['format', 'operation', 'semanticContract', 'classificationContract', 'algorithm', 'counterContract']) {
  check('capsule cannot change ' + key + ' to select another checker', () => {
    const capsule = JSON.parse(capsuleText);
    capsule[key] = 'other';
    assert.equal(replay(capsule, options).valid, false);
  });
}
check('rehashing fabricated minimality does not pass semantic recomputation', () => {
  const capsule = JSON.parse(capsuleText);
  const forged = JSON.parse(capsule.reportText);
  forged.oneMinimal = false;
  capsule.reportText = JSON.stringify(forged);
  capsule.reportSha256 = hash(capsule.reportText);
  assert.equal(replay(capsule, options).valid, false);
});
check('rehashing a changed embedded target cannot authorize caller policy', () => {
  const capsule = JSON.parse(capsuleText);
  const policy = JSON.parse(capsule.optionsText);
  policy.model = 'read-uncommitted';
  capsule.optionsText = JSON.stringify(policy);
  capsule.optionsSha256 = hash(capsule.optionsText);
  assert.equal(replay(capsule, options).valid, false);
});
check('rehashing decoded duplicate nested report keys remains invalid', () => {
  const capsule = JSON.parse(capsuleText);
  capsule.reportText = '{"oneMinimal":true,' + capsule.reportText.slice(1);
  capsule.reportSha256 = hash(capsule.reportText);
  assert.equal(replay(capsule, options).valid, false);
});
check('unknown capsule fields and duplicate decoded keys are rejected', () => {
  assert.equal(replay({...JSON.parse(capsuleText), runtime: 'other'}, options).valid, false);
  assert.equal(replay('{"schemaVersion":4,' + capsuleText.slice(1), options).valid, false);
});
check('replay validates the original source after hashes are updated', () => {
  const capsule = JSON.parse(capsuleText);
  const original = JSON.parse(capsule.sourceText);
  original.events.find(event => event.kind === 'row_read').complete = false;
  capsule.sourceText = JSON.stringify(original);
  capsule.sourceSha256 = hash(capsule.sourceText);
  assert.equal(replay(capsule, options).valid, false);
});
check('compiled runtime bytes remain unchanged', () => assert.equal(hash(readFileSync(resolve(runtime, 'core.mjs'))), coreSha256));

const summary = {
  format: 'moontxnwitness-relation-model-reduction-sdk-check/v1',
  passed: results.every(result => result.passed),
  tests: results.length,
  coreSha256,
  failed: results.filter(result => !result.passed),
  results,
};
const output = resolve(process.env.MTW_RELATION_MODEL_REDUCTION_ARTIFACTS || resolve(root, 'artifacts', 'relation-model-reduction-sdk-' + Date.now()));
mkdirSync(output, {recursive: true});
const receipt = resolve(output, 'receipt.json');
writeFileSync(receipt, JSON.stringify(summary, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({passed: summary.passed, tests: summary.tests, failed: summary.failed, receipt}));
if (!summary.passed) process.exitCode = 1;
