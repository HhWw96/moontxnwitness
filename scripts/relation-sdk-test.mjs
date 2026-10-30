// Explicit fixed-model SDK behavior and a runnable evidence round trip.
// No build, database, download, or fixture rewrite is performed.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync, readdirSync, copyFileSync} from 'node:fs';
import {resolve, dirname, relative} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

const defaults = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2), options = {};
for (let i = 0; i < args.length; i += 2) {
  assert.ok(['--repository', '--runtime', '--output-root', '--example-root'].includes(args[i]));
  assert.ok(args[i + 1]); assert.equal(options[args[i]], undefined);
  options[args[i]] = resolve(args[i + 1]);
}
const root = options['--repository'] || defaults;
const runtime = options['--runtime'] || resolve(root, 'dist');
const exampleRoot = options['--example-root'] || root;
const outputRoot = options['--output-root'] || resolve(root, 'verification/relation-sdk');
mkdirSync(outputRoot, {recursive: true});
const output = mkdtempSync(resolve(outputRoot, 'run-'));
const hash = raw => createHash('sha256').update(raw).digest('hex');
const load = file => JSON.parse(readFileSync(resolve(root, file), 'utf8'));
const copy = value => structuredClone(value);
const receipt = {schema: 1, kind: 'fixed-relation-sdk-tests', passed: false,
  actualDatabaseExecution: false, performanceMeasurement: false,
  independentOfImplementation: false, checks: [], manualCases: 0};
const save = (name, value) => writeFileSync(resolve(output, name), JSON.stringify(value, null, 2) + '\n', {encoding: 'utf8', flag: 'wx'});
const check = (name, fn) => {
  try {fn(); receipt.checks.push({name, passed: true});}
  catch (error) {receipt.checks.push({name, passed: false, error: String(error.message)});}
};

try {
  const sdk = await import(pathToFileURL(resolve(runtime, 'sdk.mjs')).href);
  const baselinePath = resolve(runtime, 'generic-sdk.mjs');
  // The isolated candidate copies the prior SDK separately. The integrated
  // test uses the retained generic functions exported by the same SDK.
  const baseline = readdirSync(runtime).includes('generic-sdk.mjs')
    ? await import(pathToFileURL(baselinePath).href) : sdk;
  const boundFiles = ['sdk.mjs', 'core.mjs', 'capture-core.mjs', 'evidence.mjs', 'build-manifest.json'];
  receipt.runtime = Object.fromEntries(boundFiles.map(file => {
    const raw = readFileSync(resolve(runtime, file));
    return [file, {bytes: raw.length, sha256: hash(raw)}];
  }));
  receipt.build = JSON.parse(readFileSync(resolve(runtime, 'build-manifest.json'), 'utf8'));
  assert.equal(receipt.runtime['core.mjs'].sha256, receipt.build.coreSha256);
  assert.equal(receipt.runtime['capture-core.mjs'].sha256, receipt.build.captureCoreSha256);

  const manual = load('fixtures/relation-v3/boundary.json');
  const byId = new Map(manual.map(row => [row.id, row]));
  for (const row of manual) check('frozen-manual-' + row.id, () => {
    assert.equal(hash(row.traceText), row.inputSha256);
    const trace = JSON.parse(row.traceText);
    if (trace.traceSchema !== 3 || trace.dataModel !== 'relation-set-v1') {
      assert.throws(() => sdk.normalizeRelationCaptureV3(row.traceText), TypeError);
      assert.throws(() => sdk.analyzeRelationV3(row.traceText, row.options), TypeError);
      assert.throws(() => sdk.reduceRelationV3(row.traceText), TypeError);
    } else {
      assert.deepEqual(sdk.normalizeRelationCaptureV3(row.traceText), baseline.normalizeCaptureV3(row.traceText));
      const report = sdk.analyzeRelationV3(row.traceText, row.options);
      assert.deepEqual(report, baseline.analyzeV3(row.traceText, row.options));
      assert.equal(report.status, row.expected);
      assert.deepEqual(sdk.verifyRelationV3(row.traceText, report), baseline.verifyV3(row.traceText, report));
    }
    receipt.manualCases++;
  });
  const traceText = readFileSync(resolve(root, 'fixtures/relation-v3/reduction-source-closure.json'), 'utf8');
  const trace = JSON.parse(traceText);
  const report = sdk.analyzeRelationV3(traceText);
  check('no-object-input-or-options-mutation', () => {
    const options = {maxStates: 20, maxOperationChecks: 200}, oldOptions = copy(options), oldTrace = copy(trace);
    assert.deepEqual(sdk.analyzeRelationV3(trace, options), baseline.analyzeV3(trace, options));
    assert.deepEqual(options, oldOptions); assert.deepEqual(trace, oldTrace);
  });
  check('raw-json-text-is-retained-exactly', () => {
    const raw = '\n  ' + traceText + '  \n';
    const capsule = sdk.makeRelationCapsuleV3(raw);
    assert.equal(JSON.parse(capsule).traceText, raw);
    assert.deepEqual(sdk.replayRelationCapsuleV3(capsule), baseline.replayCapsuleV3(capsule));
    save('raw-preserved.capsule.json', JSON.parse(capsule));
  });
  check('duplicate-json-keys-still-rejected-by-core', () => {
    const raw = traceText.replace('{', '{"dataModel":"relation-set-v1",');
    assert.equal(sdk.normalizeRelationCaptureV3(raw).status, 'invalid');
    const diagnostic = sdk.analyzeRelationV3(raw);
    assert.equal(diagnostic.status, 'invalid');
    assert.deepEqual(diagnostic, baseline.analyzeV3(raw));
    // Existing v3 permits a reproducible invalid diagnostic to be packaged.
    // Semantic replay validity must never be mistaken for model validity.
    const capsule = sdk.makeRelationCapsuleV3(raw, diagnostic);
    assert.deepEqual(sdk.replayRelationCapsuleV3(capsule), baseline.replayCapsuleV3(capsule));
    assert.equal(sdk.replayRelationCapsuleV3(capsule).status, 'invalid');
  });
  check('register-and-list-captures-cannot-use-relation-entries', () => {
    const register = load('examples/v3-write-skew.json');
    const list = JSON.parse(load('fixtures/list-v3/manual.json')[0].traceText);
    for (const foreign of [register, list]) {
      for (const fn of ['normalizeRelationCaptureV3', 'analyzeRelationV3', 'reduceRelationV3', 'verifyRelationV3', 'makeRelationCapsuleV3']) {
        assert.throws(() => sdk[fn](foreign, {}), TypeError, fn);
      }
      const genericReport = baseline.analyzeV3(foreign);
      const genericCapsule = baseline.makeCapsuleV3(foreign, genericReport);
      assert.equal(baseline.replayCapsuleV3(genericCapsule).valid, true);
      assert.equal(sdk.replayRelationCapsuleV3(genericCapsule).valid, false);
    }
  });
  check('invalid-root-types-never-default-to-register', () => {
    for (const value of [null, [], 7, true, undefined, {}, 'null', '[]', '7']) {
      assert.throws(() => sdk.analyzeRelationV3(value), TypeError);
    }
    assert.throws(() => sdk.analyzeRelationV3('{'), SyntaxError);
    assert.throws(() => sdk.replayRelationCapsuleV3({}), TypeError);
  });
  check('foreign-invalid-diagnostic-capsules-are-rejected-without-null-dereference', () => {
    for (const foreign of [null, [], 7, {}]) {
      const capsule = baseline.makeCapsuleV3(foreign);
      assert.equal(baseline.replayCapsuleV3(capsule).valid, true);
      assert.equal(sdk.replayRelationCapsuleV3(capsule).valid, false);
    }
  });
  check('malformed-json-trace-capsules-decline-the-relation-model-without-throwing', () => {
    for (const foreign of ['{', '', 'not JSON', '{"traceSchema":3,']) {
      const capsule = baseline.makeCapsuleV3(foreign);
      assert.equal(baseline.replayCapsuleV3(capsule).valid, true);
      assert.equal(sdk.replayRelationCapsuleV3(capsule).valid, false);
    }
  });
  check('utf8-input-byte-limit-before-parse', () => {
    assert.throws(() => sdk.analyzeRelationV3(' '.repeat(8 * 1024 * 1024 + 1)), RangeError);
    const huge = {traceSchema: 3, dataModel: 'relation-set-v1', note: '列'.repeat(3 * 1024 * 1024)};
    assert.throws(() => sdk.analyzeRelationV3(huge), RangeError);
  });
  check('search-budgets-exhaust-as-inconclusive', () => {
    for (const options of [{maxStates: 0}, {maxOperationChecks: 0}]) {
      const got = sdk.analyzeRelationV3(traceText, options);
      assert.deepEqual(got, baseline.analyzeV3(traceText, options));
      assert.equal(got.status, 'inconclusive'); assert.equal(got.execution.metrics.complete, false);
      assert.equal(got.evidence.kind, 'search-incomplete');
      assert.equal(sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(traceText, got)).valid, true);
    }
  });
  check('missing-source-and-unknown-outcome-retain-gaps', () => {
    for (const id of ['unknown-read-version', 'unknown-commit', 'supplement-later-read-source-does-not-repair-gap', 'partial-query', 'snapshot-coverage-omitted']) {
      const row = byId.get(id), got = sdk.analyzeRelationV3(row.traceText);
      assert.equal(got.status, 'inconclusive'); assert.equal(got.coverage.complete, false); assert.equal(got.evidence, null);
      assert.deepEqual(got.normalized.observations, JSON.parse(row.traceText).events);
      const reduced = sdk.reduceRelationV3(row.traceText);
      assert.equal(reduced.oneMinimal, false); assert.equal(reduced.status, 'not-violation');
      assert.equal(sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(row.traceText, got)).valid, true);
    }
  });
  check('exact-capacity-remains-six-transactions-and-128-operations', () => {
    for (const id of ['seven-committed-capacity', 'aborted-ops-exact-capacity-129']) {
      const got = sdk.analyzeRelationV3(byId.get(id).traceText);
      assert.equal(got.status, 'inconclusive'); assert.equal(got.execution.metrics.reason, 'exact_capacity');
      assert.equal(got.execution.effectiveLimits.committedTransactions, 6); assert.equal(got.execution.effectiveLimits.operations, 128);
    }
  });
  check('model-options-do-not-accept-register-search-or-sql-proof', () => {
    for (const options of [{maxAttempts: 12}, {sqlProof: 'dislock-f9946f0-sql-proof-1'}, {maxStates: 100001}, {maxOperationChecks: 1000001}]) {
      assert.deepEqual(sdk.analyzeRelationV3(traceText, options), baseline.analyzeV3(traceText, options));
      assert.equal(sdk.analyzeRelationV3(traceText, options).status, 'invalid');
    }
  });
  const source = load('fixtures/relation-v3/reduction-source-closure.json');
  check('zero-reduction-budget-never-claims-one-minimal', () => {
    const got = sdk.reduceRelationV3(source, {maxChecks: 0});
    assert.deepEqual(got, baseline.reduceV3(source, {maxChecks: 0}));
    assert.equal(got.checks, 0); assert.equal(got.oneMinimal, false); assert.equal(got.status, 'budget');
    assert.deepEqual(got.reducedCapture, source);
  });
  check('reduction-keeps-exhausted-analysis-separate-from-candidate-budget', () => {
    const options = {maxChecks: 256, analysisOptions: {maxStates: 0}};
    const got = sdk.reduceRelationV3(traceText, options);
    assert.deepEqual(got, baseline.reduceV3(traceText, options));
    assert.equal(got.status, 'not-violation'); assert.equal(got.oneMinimal, false); assert.equal(got.checks, 0);
    assert.equal(got.report.status, 'inconclusive'); assert.equal(got.report.execution.analysisOptions.maxStates, 0);
  });
  check('reduction-keeps-required-producer-and-original-facts', () => {
    const got = sdk.reduceRelationV3(source);
    assert.deepEqual(got, baseline.reduceV3(source)); assert.equal(got.oneMinimal, true);
    assert.deepEqual(got.removed, ['N']); assert.deepEqual(got.report.normalized.transactions.map(tx => tx.id), ['P', 'A', 'B']);
    for (let index = 0; index < got.retainedOriginalSeq.length; index++) {
      const original = copy(source.events.find(event => event.seq === got.retainedOriginalSeq[index]));
      original.seq = index + 1; assert.deepEqual(got.reducedCapture.events[index], original);
    }
    assert.equal(sdk.verifyRelationV3(got.reducedCapture, got.report).valid, true);
    assert.equal(sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(got.reducedCapture, got.report)).valid, true);
  });
  check('full-report-model-budget-source-tampering-is-rejected', () => {
    const mutations = [r => r.status = 'consistent', r => r.modelDefinition.id = 'register-serializable-v1',
      r => r.execution.analysisOptions.maxStates = 0, r => r.evidence.sourceEvidence[0].values.t = 'forged'];
    for (const mutate of mutations) {
      const changed = copy(report); mutate(changed);
      assert.equal(sdk.verifyRelationV3(traceText, changed).valid, false);
      assert.throws(() => sdk.makeRelationCapsuleV3(traceText, changed));
    }
    assert.equal(sdk.verifyRelationV3(traceText, baseline.analyzeV3(load('examples/v3-write-skew.json'))).valid, false);
  });
  check('rehashed-capsule-tampering-still-rejected', () => {
    const capsule = JSON.parse(sdk.makeRelationCapsuleV3(traceText, report));
    const changed = copy(report); changed.status = 'consistent';
    capsule.reportText = JSON.stringify(changed); capsule.reportSha256 = hash(capsule.reportText);
    assert.equal(sdk.replayRelationCapsuleV3(JSON.stringify(capsule)).valid, false);
  });
  check('malformed-and-duplicate-capsule-headers-remain-invalid', () => {
    assert.equal(sdk.replayRelationCapsuleV3('{').valid, false);
    const capsule = sdk.makeRelationCapsuleV3(traceText, report);
    assert.equal(sdk.replayRelationCapsuleV3(capsule.replace('{', '{"schemaVersion":3,')).valid, false);
  });
  check('example-anomaly-reduction-and-replay-are-repeatable-with-new-output', () => {
    const paths = [];
    for (let index = 0; index < 2; index++) {
      const p = spawnSync(process.execPath, [resolve(exampleRoot, 'examples/relation-roundtrip.mjs'), '--out-root', output], {
        cwd: exampleRoot, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 1024 * 1024});
      save('example-process-' + index + '.json', {status: p.status, stdout: p.stdout, stderr: p.stderr, error: p.error?.message || null});
      assert.equal(p.error, undefined); assert.equal(p.status, 0, p.stderr);
      const got = JSON.parse(p.stdout); assert.equal(got.passed, true); assert.equal(got.originalTransactions, 4);
      assert.equal(got.reducedTransactions, 3); assert.equal(got.oneMinimal, true); assert.equal(got.replayValid, true);
      for (const binding of got.files) {
        const raw = readFileSync(resolve(output, got.outputDirectory, binding.file));
        assert.equal(hash(raw), binding.sha256); assert.equal(raw.length, binding.bytes);
      }
      paths.push(got.outputDirectory);
    }
    assert.notEqual(paths[0], paths[1]);
    receipt.examples = paths;
  });
  check('example-wrong-model-preserves-a-failure-receipt', () => {
    const isolated = resolve(output, 'wrong-model-example');
    mkdirSync(resolve(isolated, 'examples'), {recursive: true}); mkdirSync(resolve(isolated, 'dist'));
    for (const name of readdirSync(runtime).filter(name => name.endsWith('.mjs'))) {
      copyFileSync(resolve(runtime, name), resolve(isolated, 'dist', name));
    }
    copyFileSync(resolve(exampleRoot, 'examples/relation-roundtrip.mjs'), resolve(isolated, 'examples/relation-roundtrip.mjs'));
    writeFileSync(resolve(isolated, 'examples/relation-source-closure.json'), JSON.stringify(load('examples/v3-write-skew.json')), {flag: 'wx'});
    const p = spawnSync(process.execPath, [resolve(isolated, 'examples/relation-roundtrip.mjs'), '--out-root', isolated], {
      cwd: isolated, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 1024 * 1024});
    save('example-wrong-model.process.json', {status: p.status, stdout: p.stdout, stderr: p.stderr, error: p.error?.message || null});
    assert.equal(p.error, undefined); assert.equal(p.status, 2); assert.equal(p.stdout, '');
    const created = readdirSync(isolated).filter(name => name.startsWith('moontxnwitness-relation-'));
    assert.equal(created.length, 1);
    const files = readdirSync(resolve(isolated, created[0]));
    assert.deepEqual(files, ['failure.json']);
    assert.equal(JSON.parse(readFileSync(resolve(isolated, created[0], 'failure.json'), 'utf8')).passed, false);
  });
  check('independent-interpreter-confirms-source-closure-and-all-single-deletes', () => {
    assert.equal(receipt.examples?.length, 2);
    const folder = resolve(output, receipt.examples[0]);
    const original = JSON.parse(readFileSync(resolve(folder, 'input.json'), 'utf8'));
    const reduction = JSON.parse(readFileSync(resolve(folder, 'reduction.json'), 'utf8'));
    const python = process.env.MTW_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    for (const [name, input, expected] of [['original', original, 'violation'], ['reduced', reduction.reducedCapture, 'violation'],
      ...reduction.report.normalized.transactions.map(tx => {
        const input = copy(reduction.reducedCapture);
        input.events = input.events.filter(event => event.tx !== tx.id).map((event, index) => ({...event, seq: index + 1}));
        return ['delete-' + tx.id, input, tx.id === 'P' ? 'inconclusive' : 'consistent'];
      })]) {
      const file = resolve(output, 'independent-' + name + '.json'); save('independent-' + name + '.json', input);
      const p = spawnSync(python, ['-B', resolve(root, 'scripts/relation-v3-oracle.py'), '--trace', file], {
        cwd: root, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 2 * 1024 * 1024});
      save('independent-' + name + '.process.json', {status: p.status, stdout: p.stdout, stderr: p.stderr, error: p.error?.message || null});
      assert.equal(p.error, undefined); assert.equal(p.status, 0, p.stderr);
      assert.equal(JSON.parse(p.stdout).status, expected);
    }
  });
  check('six-relation-exports-and-all-previous-sdk-entries-remain-present', () => {
    const added = [
      'analyzeRelationV3', 'makeRelationCapsuleV3', 'normalizeRelationCaptureV3',
      'reduceRelationV3', 'replayRelationCapsuleV3', 'verifyRelationV3',
    ];
    for (const name of [...added, 'analyzeV3', 'normalizeCaptureV3', 'reduceV3', 'verifyV3',
      'makeCapsuleV3', 'replayCapsuleV3', 'analyzeListV3', 'normalizeListCaptureV3',
      'reduceListV3', 'verifyListV3', 'makeListCapsuleV3', 'replayListCapsuleV3']) {
      assert.equal(typeof sdk[name], 'function');
    }
    receipt.priorSdkSnapshotAvailable = baseline !== sdk;
    if (baseline !== sdk) assert.deepEqual(Object.keys(sdk).filter(name => !(name in baseline)).sort(), added.sort());
  });
  check('all-released-list-entry-behavior-remains-identical', () => {
    const cases = load('fixtures/list-v3/manual.json');
    for (const row of cases) {
      const trace = JSON.parse(row.traceText);
      if (trace.traceSchema !== 3 || trace.dataModel !== 'append-list-v1') {
        assert.throws(() => sdk.analyzeListV3(row.traceText, row.options), TypeError);
        assert.throws(() => baseline.analyzeListV3(row.traceText, row.options), TypeError);
        continue;
      }
      const normalized = sdk.normalizeListCaptureV3(row.traceText);
      assert.deepEqual(normalized, baseline.normalizeListCaptureV3(row.traceText));
      assert.equal(normalized.status, row.expected.normalization);
      const report = sdk.analyzeListV3(row.traceText, row.options);
      assert.deepEqual(report, baseline.analyzeListV3(row.traceText, row.options));
      assert.equal(report.status, row.expected.analysis);
      assert.deepEqual(sdk.verifyListV3(row.traceText, report), baseline.verifyListV3(row.traceText, report));
      let oldCapsule;
      try {oldCapsule = baseline.makeListCapsuleV3(row.traceText, report);}
      catch (error) {
        assert.throws(() => sdk.makeListCapsuleV3(row.traceText, report),
          actual => actual.constructor === error.constructor && actual.message === error.message);
        (receipt.preservedListCapsuleRejections ??= []).push(row.id);
        continue;
      }
      const capsule = sdk.makeListCapsuleV3(row.traceText, report);
      assert.equal(capsule, oldCapsule);
      assert.deepEqual(sdk.replayListCapsuleV3(capsule), baseline.replayListCapsuleV3(capsule));
    }
    const source = load('fixtures/list-v3/reduction-source-closure.json');
    assert.deepEqual(sdk.reduceListV3(source), baseline.reduceListV3(source));
    receipt.preservedListManualCases = cases.length;
  });
  check('declared-relation-without-schema-remains-invalid-instead-of-being-filled-in', () => {
    const input = JSON.parse(traceText); delete input.relationSchema;
    const report = sdk.analyzeRelationV3(input);
    assert.equal(report.status, 'invalid');
    assert.equal(report.coverage.complete, false);
    assert.deepEqual(report, baseline.analyzeV3(input));
    assert.equal(sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(input, report)).status, 'invalid');
  });

  receipt.passed = receipt.checks.every(item => item.passed);
} catch (error) {receipt.error = String(error.message);}
receipt.finishedAt = new Date().toISOString();
save('receipt.json', receipt);
console.log(JSON.stringify({passed: receipt.passed, checks: receipt.checks.length,
  manualCases: receipt.manualCases, failures: receipt.checks.filter(item => !item.passed),
  error: receipt.error || null, receipt: relative(process.cwd(), resolve(output, 'receipt.json')).replaceAll('\\', '/')}));
if (!receipt.passed) process.exitCode = 1;
