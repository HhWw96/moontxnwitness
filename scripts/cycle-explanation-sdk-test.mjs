// Lightweight isolated prototype tests; never builds or opens a database.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync, mkdtempSync} from 'node:fs';
import {readdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {resolve, dirname, relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as sdk from '../dist/sdk.mjs';
// Generic and fixed entries use the same actual shipped core; no historical binary.
const baseline = sdk;

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '..');
// Exact original evidence/fixtures copied before the final author run. This
// candidate can be reviewed away from a changing main checkout.
const inputRoot = root;
const fixtureRoot = resolve(root, 'fixtures/register-cycle-v3');
const args = process.argv.slice(2);
assert.ok(args.length === 0 || (args.length === 2 && args[0] === '--output-root'));
const parent = args[1] ? resolve(args[1]) : resolve(root, 'verification/cycle-explanation-sdk');
mkdirSync(parent, {recursive: true});
const output = mkdtempSync(resolve(parent, 'run-'));
const sha = text => createHash('sha256').update(text).digest('hex');
const load = path => JSON.parse(readFileSync(path, 'utf8'));
const copy = value => structuredClone(value);
const receipt = {schema: 1, kind: 'shipped-register-cycle-explanation-sdk-tests', passed: false,
  actualDatabaseExecution: false, actualElleExecuted: false, newCoreBuild: false, performanceMeasurement: false,
  independentOfImplementation: false, fullIsolationClassification: false, runtimeVersion: sdk.version(), priorSdkSnapshotAvailable: false, checks: [], handwrittenCases: 0, frozenHistoryCases: 0};
const retain = (name, value) => writeFileSync(resolve(output, name), typeof value === 'string' ? value : JSON.stringify(value, null, 2) + '\n', {flag: 'wx'});
const check = (name, fn) => {try {fn(); receipt.checks.push({name, passed: true});} catch (error) {receipt.checks.push({name, passed: false, error: error.message});}};
const compare = (trace, report) => sdk.explainRegisterCycleV3(trace, report);
const positive = [];

function cycleTestBindings() {
  const walk = folder => readdirSync(resolve(root, folder), {withFileTypes: true}).flatMap(entry =>
    entry.isDirectory() ? walk(folder + '/' + entry.name) : [folder + '/' + entry.name]);
  const names = [...walk('fixtures/register-cycle-v3'),
    'scripts/cycle-explanation-sdk-test.mjs', 'cmd/sdk.mjs', 'package.json',
    'examples/register-cycle.json', 'examples/register-cycle-roundtrip.mjs',
    'fixtures/list-v3/manual.json', 'fixtures/relation-v3/boundary.json',
    'verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c/before/capture.json',
    ...['core.mjs', 'capture-core.mjs', 'sdk.mjs', 'evidence.mjs', 'build-manifest.json'].map(name => 'dist/' + name)];
  return Object.fromEntries(names.sort().map(name => [name, sha(readFileSync(resolve(root, name)))]));
}

try {
  const cycleTestedInputsBefore = cycleTestBindings();
  const manifest = load(resolve(root, 'dist/build-manifest.json'));
  assert.equal(sdk.version(), JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version);
  assert.equal(manifest.version, sdk.version());
  assert.equal(sha(readFileSync(resolve(root, 'dist/core.mjs'))), manifest.coreSha256);
  assert.equal(sha(readFileSync(resolve(root, 'dist/capture-core.mjs'))), manifest.captureCoreSha256);
  receipt.runtimeBuild = manifest;
  receipt.runtimeFiles = Object.fromEntries(['core.mjs', 'capture-core.mjs', 'sdk.mjs', 'evidence.mjs'].map(name => [name, sha(readFileSync(resolve(root, 'dist', name)))]));
  const frozen = load(resolve(fixtureRoot, 'manual-manifest.json'));
  const raw = readFileSync(resolve(fixtureRoot, 'manual.json'));
  assert.equal(sha(raw), frozen.inputFile.sha256); assert.equal(raw.length, frozen.inputFile.bytes);
  const cases = JSON.parse(raw);
  for (const c of cases) check('handwritten-' + c.id, () => {
    assert.equal(sha(c.traceText), c.inputSha256);
    const report = sdk.analyzeV3(c.traceText), oldReport = baseline.analyzeV3(c.traceText);
    assert.deepEqual(report, oldReport);
    const actual = compare(c.traceText, report);
    retain(c.id + '.report.json', report); retain(c.id + '.explanation.json', actual);
    assert.equal(actual.verifiedReport, true); assert.equal(actual.sourceStatus, report.status);
    if (c.expectedSourceStatus !== null) assert.equal(report.status, c.expectedSourceStatus);
    assert.equal(actual.subtype, c.expectedSubtype);
    assert.equal(actual.scope.acceptsIsolationModels, false); assert.equal(actual.categoriesSearched, false);
    assert.equal(actual.scope.classifiesExecutionFailures, false);
    assert.equal(sdk.verifyRegisterCycleExplanationV3(c.traceText, report, actual).valid, true);
    if (c.expectedSubtype) {
      assert.equal(actual.status, 'explained');
      assert.deepEqual(actual.witness, report.evidence.witness);
      for (const step of actual.steps) {
        assert.deepEqual(step.dependency, report.evidence.witness.edges[step.edgeIndex]);
        for (const side of ['from', 'to']) for (const seq of step[side].matchingOriginalSeqs) {
          const event = report.normalized.observations.find(event => event.seq === seq);
          assert.equal(event.tx, step[side].transaction); assert.equal(event.key, step.dependency.key);
          assert.equal(event.kind, step[side].operation.type); assert.equal(event.version, step[side].operation.version);
        }
      }
      positive.push({c, report, actual});
    } else assert.notEqual(actual.status, 'explained');
    receipt.handwrittenCases++;
  });
  check('all-five-subtypes-and-cyclic-wraparound-covered', () => {
    assert.deepEqual([...new Set(positive.map(c => c.actual.subtype))].sort(), ['G0', 'G1c', 'G-single-item', 'G-nonadjacent-item', 'G2-item'].sort());
    const wrap = positive.find(c => c.c.id === 'wraparound-adjacent-is-g2');
    assert.equal(wrap.actual.pattern.adjacentAntiDependenciesIncludingWraparound, true);
    assert.equal(wrap.actual.subtype, 'G2-item');
    const hidden = positive.find(c => c.c.id === 'shortest-ww-does-not-search-other-g2');
    assert.equal(hidden.actual.subtype, 'G0'); assert.equal(hidden.actual.scope.searchesOtherCategoryCycles, false);
  });
  const chosen = positive.find(c => c.c.id === 'adjacent-item-rw');
  assert.ok(chosen);
  const {c, report, actual} = chosen;
  const changes = {
    subtype: x => x.subtype = 'G0', completeClassification: x => x.scope.completeIsolationClassification = true,
    inventedEdge: x => x.steps[0].dependency.kind = 'ww', sourceSeq: x => x.steps[0].from.matchingOriginalSeqs = [0],
    projectedIndex: x => x.steps[0].from.projectedOperation = 999,
    order: x => x.steps[0].versionOrder.reverse(), traceDigest: x => x.traceTextSha256 = '0'.repeat(64),
    reportDigest: x => x.reportTextSha256 = '0'.repeat(64), unsupportedRule: x => x.rules.commit = '0'.repeat(40),
    missingField: x => delete x.scope.witnessOnly, extraField: x => x.acceptsSnapshotIsolation = true,
  };
  for (const [name, mutate] of Object.entries(changes)) check('derived-explanation-tamper-' + name, () => {
    const changed = copy(actual); mutate(changed);
    assert.equal(sdk.verifyRegisterCycleExplanationV3(c.traceText, report, changed).valid, false);
  });
  const reportChanges = {
    conclusion: r => r.status = 'consistent', model: r => r.modelDefinition.id = 'relation-set-serializable-v1',
    edge: r => r.evidence.witness.edges[0].kind = 'wr', sourceVersion: r => r.evidence.witness.edges[0].fromVersion = 'forged',
    observation: r => r.normalized.observations[0].consistent = false,
    budget: r => r.execution.analysisOptions.maxAttempts = 0, complete: r => r.evidence.complete = false,
    sourceOrder: r => r.evidence.versionOrderSources[r.evidence.witness.edges[0].key] = 'searched',
  };
  for (const [name, mutate] of Object.entries(reportChanges)) check('source-report-tamper-' + name, () => {
    const changed = copy(report); mutate(changed);
    const result = compare(c.traceText, changed);
    assert.equal(result.verifiedReport, false); assert.equal(result.status, 'invalid'); assert.equal(result.subtype, null);
    assert.equal(sdk.verifyRegisterCycleExplanationV3(c.traceText, changed, result).valid, false);
  });
  check('malformed-and-duplicate-source-reports-never-explain', () => {
    for (const text of ['{', JSON.stringify(report).replace('{', '{"status":"violation",')]) {
      const result = compare(c.traceText, text);
      assert.equal(result.verifiedReport, false); assert.equal(result.status, 'invalid'); assert.equal(result.subtype, null);
    }
  });
  check('faithful-invalid-trace-diagnostics-remain-invalid', () => {
    for (const text of ['{', 'null', c.traceText.replace('{', '{"traceSchema":3,')]) {
      const report = sdk.analyzeV3(text), result = compare(text, report);
      assert.equal(result.sourceStatus, 'invalid'); assert.equal(result.status, 'invalid'); assert.equal(result.subtype, null);
      assert.equal(sdk.verifyRegisterCycleExplanationV3(text, report, result).valid, true);
    }
  });
  check('unsupported-list-and-relation-models-retain-source-status', () => {
    const list = load(resolve(inputRoot, 'fixtures/list-v3/manual.json'));
    const relation = load(resolve(inputRoot, 'fixtures/relation-v3/boundary.json'));
    const selected = [list.find(c => c.id === 'two-key-read-append-cycle'), list.find(c => c.id === 'zero-state-budget'), relation.find(c => c.id === 'read-zero-state-budget')];
    for (const c of selected) {
      const report = sdk.analyzeV3(c.traceText, c.options), result = compare(c.traceText, report);
      assert.equal(result.sourceStatus, report.status); assert.equal(result.subtype, null); assert.notEqual(result.status, 'explained');
      if (report.status === 'inconclusive') assert.equal(result.status, 'inconclusive');
    }
  });
  check('actual-mlflow-40P01-is-an-execution-failure-not-g2', () => {
    const text = readFileSync(resolve(inputRoot, 'verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c/before/capture.json'), 'utf8');
    const report = sdk.analyzeV3(text), result = compare(text, report);
    const failures = sdk.inspectExecutionFailuresV3(text);
    retain('actual-mlflow-execution-failures.json', failures); retain('actual-mlflow-explanation.json', result);
    assert.ok(JSON.stringify(failures).includes('40P01'));
    assert.equal(result.subtype, null); assert.notEqual(result.status, 'explained');
    assert.equal(result.sourceStatus, report.status); assert.equal(result.scope.classifiesExecutionFailures, false);
  });
  check('source-text-and-core-capsule-roundtrip-stay-bound', () => {
    const capsuleText = sdk.makeCapsuleV3(c.traceText, report), capsule = JSON.parse(capsuleText);
    retain('example.capsule.json', capsuleText); retain('example.explanation.json', actual);
    assert.equal(sdk.replayCapsuleV3(capsuleText).valid, true);
    assert.equal(sdk.verifyRegisterCycleExplanationV3(capsule.traceText, capsule.reportText, actual).valid, true);
    const spaced = '\n' + c.traceText;
    assert.equal(sdk.verifyV3(spaced, report).valid, true);
    assert.equal(sdk.verifyRegisterCycleExplanationV3(spaced, report, actual).valid, false);
  });
  check('old-supported-v3-report-headers-preserve-real-version-values', () => {
    const old = copy(report); old.version = '0.1.3'; old.evidence.version = '0.1.3';
    const result = compare(c.traceText, old);
    assert.equal(result.verifiedReport, true); assert.equal(result.sourceReportVersion, '0.1.3'); assert.equal(result.subtype, 'G2-item');
  });
  check('arguments-and-current-sdk-model-reports-are-not-mutated', () => {
    const trace = JSON.parse(c.traceText), traceBefore = copy(trace), before = copy(report);
    compare(trace, report); assert.deepEqual(trace, traceBefore); assert.deepEqual(report, before);
    assert.deepEqual(sdk.analyzeV3(c.traceText), baseline.analyzeV3(c.traceText));
    assert.throws(() => compare(c.traceText), TypeError);
    assert.throws(() => sdk.verifyRegisterCycleExplanationV3(c.traceText, report, '{}'), TypeError);
    assert.throws(() => compare(' '.repeat(8 * 1024 * 1024 + 1), report), RangeError);
  });
  check('fixed-primary-rule-source-sha-and-actual-old-elle-smoke-are-accounted-separately', () => {
    const folder = resolve(fixtureRoot, 'elle-reference');
    const pins = load(resolve(folder, 'source-pins.json'));
    const raw = readFileSync(resolve(folder, 'primary-references/src/elle/txn.clj'));
    assert.equal(raw.length, pins.files['src/elle/txn.clj'].bytes); assert.equal(sha(raw), pins.files['src/elle/txn.clj'].sha256);
    const old = load(resolve(folder, 'actual-ci-39599513353/actual/elle-result.json'));
    assert.equal(old.passed, true); assert.equal(old.cases.length, 8);
    assert.equal(old.cases.filter(row => row.valid === true).length, 2);
    assert.equal(old.cases.filter(row => row.valid === false).length, 4);
    assert.equal(old.cases.filter(row => row.valid === 'unknown').length, 2);
    receipt.oldElleSmokeAccounted = {fixedCommit: pins.fixedCommit, cases: 8, sourceSha256: sha(raw), newElleExecution: false};
  });
  check('current-core-replays-eight-original-elle-smoke-inputs-with-two-register-subtypes', () => {
    const folder = resolve(fixtureRoot, 'elle-reference');
    const raw = readFileSync(resolve(folder, 'smoke-inputs-v1.json'));
    const prior = load(resolve(folder, 'actual-ci-39599513353/actual/comparison-first.json'));
    assert.equal(sha(raw), prior.originalInputSha256);
    const originals = JSON.parse(raw).cases.filter(row => row.expected.adapter === 'eligible');
    const oldElle = new Map(load(resolve(folder, 'actual-ci-39599513353/actual/elle-result.json')).cases.map(row => [row.id, row]));
    assert.equal(originals.length, 8);
    const results = []; let subtypes = 0;
    for (const row of originals) {
      const report = sdk.analyzeV3(row.input), derived = compare(row.input, report), old = oldElle.get(row.id);
      assert.equal(report.status, row.expected.toolStatus);
      assert.equal(old.valid, row.expected.elleValid);
      if (row.input.dataModel === 'point-register-v1' && old.valid === false) {
        assert.equal(derived.status, 'explained'); assert.ok(old.anomalyTypes.includes(derived.subtype)); subtypes++;
      } else assert.equal(derived.subtype, null);
      results.push({id: row.id, traceSha256: sha(JSON.stringify(row.input)), storedElleValid: old.valid,
        storedElleAnomalies: old.anomalyTypes, currentCoreStatus: report.status, derived,
        knownEmptyGraphDifference: old.valid === 'unknown', newElleExecution: false});
    }
    assert.equal(subtypes, 2); assert.equal(results.filter(row => row.knownEmptyGraphDifference).length, 2);
    retain('current-core-old-elle-smoke.json', results);
    receipt.storedElleComparison = {originalInputs: 8, currentCoreExecuted: true, newElleExecuted: false,
      exactRegisterSubtypeAgreements: subtypes, knownEmptyGraphDifferencesRetained: 2,
      currentListSubtypeClassification: false, sixModelParity: false};
  });
  check('repeated-original-reads-retain-all-matching-sequences-without-unique-source-claim', () => {
    const row = cases.find(c => c.id === 'single-item-rw');
    const trace = JSON.parse(row.traceText);
    const index = trace.events.findIndex(event => event.kind === 'read');
    trace.events.splice(index + 1, 0, copy(trace.events[index]));
    trace.events.forEach((event, i) => {event.seq = i + 1; event.time = i;});
    retain('supplement-repeated-original-read.json', trace);
    const report = sdk.analyzeV3(trace), result = compare(trace, report);
    assert.equal(result.subtype, 'G-single-item');
    const step = result.steps.find(step => step.dependency.kind === 'rw');
    assert.equal(step.from.matchingOriginalSeqs.length, 2);
    assert.ok(step.sourceReferenceKind.includes('no unique occurrence inferred'));
    assert.equal(sdk.verifyRegisterCycleExplanationV3(trace, report, result).valid, true);
  });
  check('frozen-132-histories-cyclic-rules-operation-and-original-source-regression', () => {
    const frozen = load(resolve(fixtureRoot, 'independent-input-manifest.json'));
    const raw = readFileSync(resolve(fixtureRoot, 'independent-inputs.json'));
    assert.equal(raw.length, frozen.bytes); assert.equal(sha(raw), frozen.sha256);
    const additions = JSON.parse(raw);
    assert.equal(additions.length, 119);
    const subtype = types => {
      const positions = types.flatMap((type, index) => type === 'rw' ? [index] : []);
      if (!positions.length) return types.includes('wr') ? 'G1c' : 'G0';
      if (positions.length === 1) return 'G-single-item';
      const distances = positions.map((position, index) =>
        (positions[(index + 1) % positions.length] - position + types.length) % types.length);
      return distances.includes(1) ? 'G2-item' : 'G-nonadjacent-item';
    };
    const results = [];
    for (const row of [...cases, ...additions]) {
      assert.equal(sha(row.traceText), row.inputSha256);
      const current = sdk.analyzeV3(row.traceText);
      if (row.expectedSourceStatus !== null) assert.equal(current.status, row.expectedSourceStatus, row.id);
      const derived = sdk.explainRegisterCycleV3(row.traceText, current);
      assert.equal(derived.subtype, row.expectedSubtype, row.id);
      assert.equal(derived.verifiedReport, true);
      assert.equal(derived.sourceStatus, current.status);
      assert.equal(derived.categoriesSearched, false);
      for (const field of ['searchesOtherCategoryCycles', 'acceptsIsolationModels',
        'completeIsolationClassification', 'classifiesExecutionFailures', 'authenticatesCaptureSources'])
        assert.equal(derived.scope[field], false);
      assert.equal(sdk.verifyRegisterCycleExplanationV3(row.traceText, current, derived).valid, true);
      if (derived.status === 'explained') {
        assert.equal(derived.subtype, subtype(current.evidence.witness.edges.map(edge => edge.kind)));
        assert.deepEqual(derived.witness, current.evidence.witness);
        for (const step of derived.steps) for (const side of ['from', 'to']) {
          const point = step[side];
          const transaction = current.normalized.history.transactions.find(tx => tx.id === point.transaction);
          assert.equal(transaction.status, 'committed');
          assert.deepEqual(point.operation, transaction.ops[point.projectedOperation]);
          const operation = point.operation;
          const sequences = current.normalized.observations.filter(event => event.tx === point.transaction &&
            event.key === operation.key && event.kind === operation.type && event.version === operation.version).map(event => event.seq);
          assert.ok(sequences.length); assert.deepEqual(point.matchingOriginalSeqs, sequences);
          assert.ok(step.sourceReferenceKind.includes('no unique occurrence inferred'));
        }
      } else assert.equal(derived.subtype, null);
      if (row.id === 'same-name-savepoints-retain-reads')
        assert.equal(derived.steps.find(step => step.dependency.kind === 'rw').from.matchingOriginalSeqs.length, 2);
      if (row.id === 'reverted-write-not-projected') {
        assert.ok(current.normalized.observations.some(event => event.kind === 'write' && event.version === 'audit|discarded'));
        assert.ok(!current.normalized.history.transactions.some(tx => tx.ops.some(op => op.version === 'audit|discarded')));
      }
      results.push({id: row.id, sourceStatus: current.status, status: derived.status, subtype: derived.subtype});
    }
    assert.equal(results.length, 132);
    retain('frozen-132-results.json', results);
    receipt.frozenHistoryCases = results.length;
    receipt.frozenHistoricalExpectedResults = true;
    receipt.newIndependentOrElleExecution = false;
  });
  check('shipped-example-original-capsule-and-separate-explanation-roundtrip', () => {
    const child = spawnSync(process.execPath, ['examples/register-cycle-roundtrip.mjs', '--out-root', output], {
      cwd: root, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 1024 * 1024});
    assert.equal(child.error, undefined); assert.equal(child.status, 0, child.stderr);
    const example = JSON.parse(child.stdout);
    assert.equal(example.passed, true); assert.equal(example.version, sdk.version());
    assert.equal(example.sourceReportStatus, 'violation'); assert.equal(example.selectedCycleSubtype, 'G2-item');
    assert.equal(example.originalCapsuleReplayed, true); assert.equal(example.explanationVerified, true);
    assert.equal(example.acceptsIsolationModels, false); assert.equal(example.searchesOtherCategories, false);
    for (const value of example.files) {
      const raw = readFileSync(resolve(output, example.outputDirectory, value.file));
      assert.equal(raw.length, value.bytes); assert.equal(sha(raw), value.sha256);
    }
    const capsule = readFileSync(resolve(output, example.outputDirectory, 'original-v3.capsule.json'), 'utf8');
    assert.equal(sdk.replayCapsuleV3(capsule).valid, true);
    const parsed = JSON.parse(capsule);
    const explanation = load(resolve(output, example.outputDirectory, 'cycle-explanation.json'));
    assert.equal(sdk.verifyRegisterCycleExplanationV3(parsed.traceText, parsed.reportText, explanation).valid, true);
    receipt.example = {outputDirectory: example.outputDirectory, files: example.files,
      version: example.version, originalCapsuleReplayed: true, explanationVerified: true};
  });
  check('executed-sdk-core-fixtures-and-example-bytes-remain-unchanged', () => {
    assert.deepEqual(cycleTestBindings(), cycleTestedInputsBefore);
    receipt.testedInputSha256 = cycleTestedInputsBefore;
    receipt.testedInputsUnchanged = true;
  });
  check('fixed-upstream-source-license-and-original-attribution-remain-bound', () => {
    const folder = resolve(fixtureRoot, 'elle-reference');
    const pins = load(resolve(folder, 'source-pins.json'));
    const attribution = load(resolve(folder, 'reference-attribution.json'));
    assert.equal(attribution.fixedCommit, pins.fixedCommit);
    assert.equal(attribution.projectApacheLicenseAppliesToTheseUpstreamMaterials, false);
    for (const name of ['src/elle/txn.clj', 'project.clj', 'LICENSE']) {
      const raw = readFileSync(resolve(folder, 'primary-references', name));
      assert.equal(raw.length, attribution.files[name].bytes);
      assert.equal(sha(raw), attribution.files[name].sha256);
      assert.deepEqual(attribution.files[name], pins.files[name]);
    }
    assert.ok(readFileSync(resolve(folder, 'primary-references/project.clj'), 'utf8')
      .includes('EPL-2.0 OR GPL-2.0-or-later WITH Classpath-exception-2.0'));
    assert.ok(readFileSync(resolve(folder, 'primary-references/LICENSE'), 'utf8').startsWith('Eclipse Public License - v 2.0'));
  });

  receipt.passed = receipt.checks.every(row => row.passed);
} catch (error) {receipt.error = error.message;}
receipt.finishedAt = new Date().toISOString(); retain('receipt.json', receipt);
console.log(JSON.stringify({passed: receipt.passed, checks: receipt.checks.length, handwrittenCases: receipt.handwrittenCases, frozenHistoryCases: receipt.frozenHistoryCases, runtimeVersion: receipt.runtimeVersion,
  failures: receipt.checks.filter(row => !row.passed), error: receipt.error || null,
  receipt: relative(root, resolve(output, 'receipt.json')).replaceAll('\\', '/')}));
if (!receipt.passed) process.exitCode = 1;
