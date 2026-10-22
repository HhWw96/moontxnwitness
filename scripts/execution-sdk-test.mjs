import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync, readdirSync} from 'node:fs';
import {dirname, resolve, relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as sdk from '../dist/sdk.mjs';
// Reuse the actual shipped core: no historical SDK snapshot is claimed.
const original = sdk;

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const args = process.argv.slice(2);
assert.ok(args.length === 0 || (args.length === 2 && args[0] === '--output-root'));
const parent = args[1] ? resolve(args[1]) : resolve(root, 'verification/execution-sdk');
mkdirSync(parent, {recursive: true});
const output = mkdtempSync(resolve(parent, 'run-'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const load = path => JSON.parse(readFileSync(path, 'utf8'));
const canonical = value => JSON.stringify(value, null, 2) + '\n';
const clone = value => structuredClone(value);
const receipt = {schema: 1, kind: 'shipped-execution-capsule-sdk-tests', passed: false,
  independentAIAcceptance: false, actualDatabaseExecution: false, newCoreBuild: false,
  formalPerformanceMeasurement: false, fullMlflowApplicationExecuted: false,
  modelViolationClaim: false, runtimeVersion: sdk.version(), priorSdkSnapshotAvailable: false, originalCandidateAssertions: 54, recordedMlflowCases: 2, checks: []};
const retain = (name, value) => writeFileSync(resolve(output, name),
  typeof value === 'string' ? value : canonical(value), {flag: 'wx'});
const check = (name, fn) => {try {fn(); receipt.checks.push({name, passed: true});}
  catch (error) {receipt.checks.push({name, passed: false, error: error.message});}};
const rehash = envelope => {
  envelope.traceSha256 = hash(envelope.traceText);
  envelope.diagnosticSha256 = hash(envelope.diagnosticText);
  return canonical(envelope);
};

function executionTestBindings() {
  const walk = folder => readdirSync(resolve(root, folder), {withFileTypes: true}).flatMap(entry =>
    entry.isDirectory() ? walk(folder + '/' + entry.name) : [folder + '/' + entry.name]);
  const names = [...walk('fixtures/execution-v3'), 'scripts/execution-sdk-test.mjs',
    'examples/execution-roundtrip.mjs', 'cmd/sdk.mjs', 'package.json',
    ...['core.mjs', 'capture-core.mjs', 'sdk.mjs', 'evidence.mjs', 'build-manifest.json'].map(name => 'dist/' + name)];
  return Object.fromEntries(names.sort().map(name => {
    const bytes = readFileSync(resolve(root, name));
    return [name, {bytes: bytes.length, sha256: hash(bytes)}];
  }));
}

try {
  const testedInputsBefore = executionTestBindings();
  const build = load(resolve(root, 'dist/build-manifest.json'));
  assert.equal(build.version, sdk.version());
  assert.equal(load(resolve(root, 'package.json')).version, sdk.version());
  assert.equal(hash(readFileSync(resolve(root, 'dist/core.mjs'))), build.coreSha256);
  assert.equal(hash(readFileSync(resolve(root, 'dist/capture-core.mjs'))), build.captureCoreSha256);
  receipt.runtimeBuild = build;
  receipt.runtimeFiles = Object.fromEntries(['core.mjs', 'capture-core.mjs', 'sdk.mjs', 'evidence.mjs'].map(name => [name, hash(readFileSync(resolve(root, 'dist', name)))]));
  const frozen = load(resolve(root, 'fixtures/execution-v3/handwritten-manifest.json'));
  const raw = readFileSync(resolve(root, 'fixtures/execution-v3/handwritten-inputs.json'));
  assert.equal(hash(raw), frozen.input.sha256); assert.equal(raw.length, frozen.input.bytes);
  const cases = JSON.parse(raw), capsules = new Map();
  for (const row of cases) check('handwritten-' + row.id, () => {
    assert.equal(hash(row.traceText), row.traceSha256);
    const diagnostic = sdk.inspectExecutionFailuresV3(row.traceText);
    assert.deepEqual(diagnostic, original.inspectExecutionFailuresV3(row.traceText));
    assert.equal(diagnostic.valid, true); assert.equal(diagnostic.observedFaultCount, row.expectedFaultCount);
    if (row.expectedFaultKind) assert.equal(diagnostic.faults[0].kind, row.expectedFaultKind);
    assert.equal(diagnostic.transactionOutcomes.some(tx => tx.status === 'unknown'), row.expectedUnknownTransaction);
    const capsule = sdk.makeExecutionCapsuleV3(row.traceText), parsed = JSON.parse(capsule);
    assert.equal(parsed.traceText, row.traceText); assert.equal(parsed.engineVersion, build.version);
    assert.deepEqual(JSON.parse(parsed.diagnosticText), diagnostic);
    assert.equal(parsed.budgets.traceUtf8Bytes, 8 * 1024 * 1024);
    assert.equal(parsed.budgets.modelSearch, false);
    const replay = sdk.replayExecutionCapsuleV3(capsule);
    assert.equal(replay.valid, true); assert.deepEqual(replay.diagnostic, diagnostic);
    for (const key of ['actualDatabaseExecution', 'databaseAuthenticityVerified', 'certifiesFailureAbsence', 'modelViolationClaim', 'completeApplicationIntegration']) assert.equal(replay.scope[key], false);
    retain(row.id + '.capsule.json', capsule); retain(row.id + '.replay.json', replay);
    capsules.set(row.id, capsule);
  });
  receipt.handwrittenCases = cases.length;
  const chosen = capsules.get('statement-40P01');
  assert.ok(chosen); const base = JSON.parse(chosen);
  const changes = {
    'format': c => c.format = 'moontxnwitness-replay/v3',
    'schema': c => c.schemaVersion = 3,
    'tool': c => c.tool = 'OtherTool',
    'engine': c => c.engineVersion = '0.1.0',
    'future-engine': c => c.engineVersion = '99.0.0',
    'algorithm': c => c.diagnosticAlgorithm = 'v3-observed-failures-unknown',
    'budget-byte-limit': c => c.budgets.traceUtf8Bytes++,
    'budget-normalization': c => c.budgets.normalizationPolicy = 'unbounded',
    'budget-search': c => c.budgets.modelSearch = true,
    'budget-extra-field': c => c.budgets.maxAttempts = 1,
    'extra-field': c => c.actualDatabaseExecution = true,
    'missing-field': c => delete c.traceSha256,
    'trace-without-new-digest': c => c.traceText += '\n',
    'diagnostic-without-new-digest': c => c.diagnosticText += '\n',
    'trace-digest': c => c.traceSha256 = '0'.repeat(64),
    'diagnostic-digest': c => c.diagnosticSha256 = '0'.repeat(64),
  };
  for (const [name, mutate] of Object.entries(changes)) check('envelope-tamper-' + name, () => {
    const changed = clone(base); mutate(changed);
    assert.equal(sdk.replayExecutionCapsuleV3(canonical(changed)).valid, false);
  });
  const diagnosticChanges = {
    kind: d => d.faults[0].kind = 'G2',
    sqlstate: d => d.faults[0].sqlstate = '40001',
    driver: d => d.faults[0].driverClass = 'ForgedDriver',
    statement: d => d.faults[0].statement++,
    source: d => d.faults[0].seq++,
    count: d => d.observedFaultCount = 0,
    outcome: d => d.transactionOutcomes[0].status = 'committed',
    coverage: d => d.captureCoverage.complete = true,
    gaps: d => d.captureCoverage.gaps = [],
    model: d => d.modelViolationClaim = true,
    authenticity: d => d.databaseAuthenticityVerified = true,
    absence: d => d.certifiesFailureAbsence = true,
    missing: d => delete d.captureStatus,
    extra: d => d.fixed = true,
  };
  for (const [name, mutate] of Object.entries(diagnosticChanges)) check('rehashed-diagnostic-tamper-' + name, () => {
    const changed = clone(base), diagnostic = JSON.parse(changed.diagnosticText);
    mutate(diagnostic); changed.diagnosticText = JSON.stringify(diagnostic);
    assert.equal(sdk.replayExecutionCapsuleV3(rehash(changed)).valid, false);
  });
  check('rehashed-source-sqlstate-change-does-not-reproduce-stale-diagnostic', () => {
    const changed = clone(base), trace = JSON.parse(changed.traceText);
    trace.events.find(e => e.error).error.sqlstate = '40001';
    changed.traceText = JSON.stringify(trace);
    assert.equal(sdk.replayExecutionCapsuleV3(rehash(changed)).valid, false);
  });
  check('duplicate-or-invalid-diagnostic-json-rejected-even-after-rehash', () => {
    for (const text of ['{', base.diagnosticText.replace('{', '{"valid":true,'),
      base.diagnosticText.replace('"kind":"deadlock"', '"kind":"deadlock","kind":"deadlock"')]) {
      const changed = clone(base); changed.diagnosticText = text;
      assert.equal(sdk.replayExecutionCapsuleV3(rehash(changed)).valid, false);
    }
  });
  check('mismatched-commit-response-remains-invalid-after-envelope-reseal', () => {
    const validCommit = JSON.parse(capsules.get('commit-deadlock'));
    const trace = JSON.parse(validCommit.traceText);
    trace.events.find(event => event.commitResponse).commitResponse.diagnosticSqlstate = '40001';
    validCommit.traceText = JSON.stringify(trace);
    assert.throws(() => sdk.makeExecutionCapsuleV3(validCommit.traceText));
    assert.equal(sdk.replayExecutionCapsuleV3(rehash(validCommit)).valid, false);
  });
  check('fixed-core-event-budget-is-not-converted-to-empty-success', () => {
    const trace = JSON.parse(cases.find(row => row.id === 'no-observed-fault-is-not-absence').traceText);
    while (trace.events.length <= 65536) trace.events.push(trace.events[0]);
    const text = JSON.stringify(trace);
    assert.ok(Buffer.byteLength(text, 'utf8') < 8 * 1024 * 1024);
    assert.equal(sdk.inspectExecutionFailuresV3(text).valid, false);
    assert.throws(() => sdk.makeExecutionCapsuleV3(text));
    const changed = clone(base); changed.traceText = text;
    assert.equal(sdk.replayExecutionCapsuleV3(rehash(changed)).valid, false);
  });
  check('duplicate-malformed-or-primitive-envelope-json-returns-rejection', () => {
    for (const text of ['{', 'null', 'true', '[]', chosen.replace('{', '{"schemaVersion":1,'),
      chosen.replace('"format":', '"for\\u006dat":"moontxnwitness-execution/v1","format":')]) {
      assert.equal(sdk.replayExecutionCapsuleV3(text).valid, false);
    }
  });
  check('canonical-envelope-contract-rejects-reserialization-but-not-original-trace-whitespace', () => {
    assert.equal(sdk.replayExecutionCapsuleV3(JSON.stringify(base)).valid, false);
    const text = '\n' + cases[0].traceText + '\n';
    const capsule = sdk.makeExecutionCapsuleV3(text);
    assert.equal(JSON.parse(capsule).traceText, text);
    assert.equal(sdk.replayExecutionCapsuleV3(capsule).valid, true);
  });
  check('invalid-duplicate-or-lifecycle-invalid-source-cannot-be-packaged-or-resealed', () => {
    const invalid = [null, '{', 'null', cases[0].traceText.replace('{', '{"traceSchema":3,')];
    const wrong = JSON.parse(cases[0].traceText); wrong.events.find(e => e.kind === 'rows').statement = 999;
    invalid.push(JSON.stringify(wrong));
    for (const text of invalid) {
      assert.throws(() => sdk.makeExecutionCapsuleV3(text));
      const changed = clone(base); changed.traceText = typeof text === 'string' ? text : JSON.stringify(text);
      assert.equal(sdk.replayExecutionCapsuleV3(rehash(changed)).valid, false);
    }
  });
  check('byte-limits-enforced-on-maker-and-replay', () => {
    assert.throws(() => sdk.makeExecutionCapsuleV3(' '.repeat(8 * 1024 * 1024 + 1)), RangeError);
    assert.equal(sdk.replayExecutionCapsuleV3(' '.repeat(32 * 1024 * 1024 + 1)).valid, false);
    const changed = clone(base); changed.traceText = ' '.repeat(8 * 1024 * 1024 + 1);
    assert.equal(sdk.replayExecutionCapsuleV3(rehash(changed)).valid, false);
  });
  check('unicode-original-sql-parameters-and-json-text-retained-exactly', () => {
    const trace = JSON.parse(cases[0].traceText);
    trace.events.find(e => e.kind === 'statement').sql += " /* 中文 🚀 */";
    const before = clone(trace), text = JSON.stringify(trace, null, 3);
    const capsule = sdk.makeExecutionCapsuleV3(text);
    assert.equal(JSON.parse(capsule).traceText, text); assert.deepEqual(trace, before);
    assert.equal(sdk.replayExecutionCapsuleV3(capsule).valid, true);
    const bad = text.replace('🚀', '\uD800');
    assert.throws(() => sdk.makeExecutionCapsuleV3(bad), TypeError);
    const changed = clone(base); changed.traceText = bad;
    assert.equal(sdk.replayExecutionCapsuleV3(rehash(changed)).valid, false);
  });
  check('unknown-commit-remains-unknown-not-aborted-or-fault-free-certified', () => {
    const replay = sdk.replayExecutionCapsuleV3(capsules.get('unknown-commit'));
    assert.equal(replay.valid, true); assert.equal(replay.diagnostic.captureStatus, 'inconclusive');
    assert.equal(replay.diagnostic.observedFaultCount, 0);
    assert.equal(replay.diagnostic.transactionOutcomes[0].status, 'unknown');
    assert.equal(replay.diagnostic.certifiesFailureAbsence, false);
  });
  check('existing-model-capsule-does-not-silently-become-execution-capsule', () => {
    const generic = sdk.makeCapsuleV3(cases[0].traceText);
    assert.equal(sdk.replayCapsuleV3(generic).valid, true);
    assert.equal(sdk.replayExecutionCapsuleV3(generic).valid, false);
    assert.equal(sdk.replayCapsuleV3(chosen).valid, false);
  });
  const run = resolve(root, 'fixtures/execution-v3/mlflow');
  for (const label of ['before', 'fixed']) check('actual-recorded-mlflow-' + label + '-diagnostic-roundtrip', () => {
    const trace = readFileSync(resolve(run, label, 'capture.json'), 'utf8');
    const originalReceipt = load(resolve(run, label, 'receipt.json'));
    assert.equal(hash(trace), originalReceipt.captureSha256);
    const report = sdk.analyzeV3(trace), diagnostic = sdk.inspectExecutionFailuresV3(trace);
    assert.deepEqual(report, original.analyzeV3(trace));
    assert.deepEqual(diagnostic, original.inspectExecutionFailuresV3(trace));
    assert.equal(report.status, 'inconclusive'); assert.equal(report.coverage.complete, false);
    assert.equal(diagnostic.observedFaultCount, label === 'before' ? 1 : 0);
    assert.equal(diagnostic.captureCoverage.complete, false);
    assert.equal(diagnostic.transactionOutcomes.filter(tx => tx.status === 'committed').length, label === 'before' ? 1 : 2);
    if (label === 'before') {
      assert.equal(diagnostic.faults[0].sqlstate, '40P01'); assert.equal(diagnostic.faults[0].kind, 'deadlock');
      assert.equal(report.evidence, null);
    }
    const capsule = sdk.makeExecutionCapsuleV3(trace), replay = sdk.replayExecutionCapsuleV3(capsule);
    assert.equal(replay.valid, true); assert.deepEqual(replay.diagnostic, diagnostic);
    assert.equal(JSON.parse(capsule).traceText, trace);
    retain('actual-' + label + '.capsule.json', capsule);
    retain('actual-' + label + '.replay.json', replay);
    retain('actual-' + label + '.model-report.json', report);
  });
  check('unchanged-old-api-results-and-new-argument-errors', () => {
    for (const row of cases) assert.deepEqual(sdk.normalizeCaptureV3(row.traceText), original.normalizeCaptureV3(row.traceText));
    assert.throws(() => sdk.replayExecutionCapsuleV3({}), TypeError);
    assert.throws(() => sdk.makeExecutionCapsuleV3(undefined), TypeError);
  });
  receipt.testedInputsBefore = testedInputsBefore;
  receipt.testedInputsAfter = executionTestBindings();
  assert.deepEqual(receipt.testedInputsAfter, testedInputsBefore);
  receipt.testedInputsUnchanged = true;
  assert.equal(receipt.checks.length, 54);
  receipt.passed = receipt.checks.every(row => row.passed);
} catch (error) {receipt.error = error.message;}
retain('receipt.json', receipt);
console.log(JSON.stringify({passed: receipt.passed, checks: receipt.checks.length,
  failures: receipt.checks.filter(row => !row.passed), error: receipt.error || null,
  runtimeVersion: receipt.runtimeVersion, handwrittenCases: receipt.handwrittenCases, originalCandidateAssertions: receipt.originalCandidateAssertions, recordedMlflowCases: receipt.recordedMlflowCases,
  outputDirectory: relative(parent, output).replaceAll('\\', '/'), receiptFile: 'receipt.json',
  receipt: relative(root, resolve(output, 'receipt.json')).replaceAll('\\', '/')}));
if (!receipt.passed) process.exitCode = 1;
