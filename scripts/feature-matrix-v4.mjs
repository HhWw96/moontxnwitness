// Execute the declared profile/model matrix without treating internal replay as
// a new execution of the reference Elle checker.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const settings = {};
while (args.length) {
  const key = args.shift();
  assert(['--runtime', '--output'].includes(key) && args.length && !Object.hasOwn(settings, key),
    'Usage: feature-matrix-v4.mjs [--runtime DIST_DIR] [--output NEW_DIRECTORY]');
  settings[key] = args.shift();
}
const runtime = resolve(settings['--runtime'] || resolve(root, 'dist'));
const destination = resolve(settings['--output'] || resolve(root, 'artifacts', 'feature-matrix-' + Date.now()));
// A previous result is never overwritten, including after a failed run.
mkdirSync(destination, {recursive: false});
const sha = value => createHash('sha256').update(value).digest('hex');
const read = name => readFileSync(resolve(root, name));
const catalogBytes = read('docs/feature-matrix-v4.json');
const fixtureBytes = read('fixtures/feature-matrix-v4.json');
const runnerBytes = readFileSync(fileURLToPath(import.meta.url));
const catalog = JSON.parse(catalogBytes);
const fixtures = JSON.parse(fixtureBytes);
const runtimeNames = ['core.mjs', 'models-v4.mjs', 'build-manifest.json'];
const bindings = () => Object.fromEntries(runtimeNames.map(name => [name, sha(readFileSync(resolve(runtime, name)))]));
const before = bindings();
const build = JSON.parse(readFileSync(resolve(runtime, 'build-manifest.json')));
assert.equal(before['core.mjs'], build.coreSha256);
const api = await import(pathToFileURL(resolve(runtime, 'models-v4.mjs')));
const checks = [];
const rows = [];
function check(name, action) {
  try { action(); checks.push({name, passed: true}); }
  catch (error) { checks.push({name, passed: false, error: error.message}); }
}
check('declared canonical model names equal the runtime namespace', () => {
  assert.equal(catalog.models.length, 14);
  assert.equal(new Set(catalog.models.map(m => m.name)).size, 14);
  assert.deepEqual(catalog.models.map(m => m.name), api.ELLE_CORE_MODELS_V4);
});
check('each declared source profile has compatible, refuted and incomplete fixtures', () => {
  assert.equal(new Set(fixtures.cases.map(f => f.id)).size, fixtures.cases.length);
  assert.equal(fixtures.cases.length, catalog.profiles.length * 3);
  for (const profile of catalog.profiles) {
    const cases = fixtures.cases.filter(f => f.profile === profile.id);
    assert.deepEqual(cases.map(f => f.expected).sort(), ['checked-compatible', 'refuted', 'unknown']);
    for (const f of cases) assert.equal(f.input.dataModel, profile.dataModel);
  }
});
for (const fixture of fixtures.cases) {
  const profile = catalog.profiles.find(p => p.id === fixture.profile);
  assert(profile, 'Fixture names an undeclared profile');
  const sourceText = JSON.stringify(fixture.input);
  const options = {models: 'elle-core', ...profile.options, ...fixture.options};
  let report;
  check(fixture.id + '/classify', () => {
    report = api.classifyModelsV4(sourceText, options);
    if (fixture.expected === 'unknown') {
      assert(profile.incompleteSourceProfiles.includes(report.sourceProfile));
    } else {
      assert.equal(report.sourceProfile, profile.sourceProfile);
    }
    assert.equal(report.models.length, 14);
    assert.equal(report.status, fixture.expected);
  });
  if (!report?.models) continue;
  check(fixture.id + '/verify-original-and-independent-options', () => {
    assert.equal(api.verifyModelsV4(sourceText, report, options).valid, true);
    assert.equal(api.verifyModelsV4(sourceText, report, {...options, maxSourceChecks: 0}).valid, false);
  });
  for (const model of catalog.models) {
    const actual = report.models.find(m => m.model === model.name);
    rows.push({fixture: fixture.id, dataModel: profile.dataModel,
      requestedSourceProfile: profile.sourceProfile, sourceProfile: report.sourceProfile,
      semanticContract: report.semanticContract, algorithm: report.algorithm,
      counterContract: report.execution?.counterContract,
      model: model.name, expected: fixture.expected, actual: actual?.status,
      inputSha256: sha(sourceText), optionsSha256: sha(JSON.stringify(options)),
      reportSha256: sha(JSON.stringify(report)),
      rules: actual?.rules.map(r => ({id: r.rule, status: r.status}))});
    check(fixture.id + '/' + model.name, () => {
      assert.equal(actual?.status, fixture.expected);
      assert(actual.rules.length > 0);
      if (fixture.expected === 'checked-compatible') assert(actual.rules.every(r => r.status === 'checked-compatible'));
      if (fixture.expected === 'refuted') assert(actual.rules.some(r => r.status === 'refuted'));
    });
    check(fixture.id + '/' + model.name + '/reject-changed-verdict', () => {
      const altered = structuredClone(report);
      altered.models.find(m => m.model === model.name).status = fixture.expected === 'refuted' ? 'checked-compatible' : 'refuted';
      assert.equal(api.verifyModelsV4(sourceText, altered, options).valid, false);
    });
  }
  check(fixture.id + '/capsule-roundtrip-with-caller-policy', () => {
    const capsule = api.makeModelsCapsuleV4(sourceText, options);
    assert.equal(api.replayModelsCapsuleV4(capsule, options).valid, true);
    assert.equal(api.replayModelsCapsuleV4(capsule, {...options, maxSourceChecks: 0}).valid, false);
  });
}
for (const profile of catalog.profiles) {
  const fixture = fixtures.cases.find(f => f.profile === profile.id && f.expected === 'checked-compatible');
  check(profile.id + '/zero-source-budget-is-unknown', () => {
    const options = {models: ['snapshot-isolation'], ...profile.options, ...fixture.options, maxSourceChecks: 0};
    const report = api.classifyModelsV4(fixture.input, options);
    assert.equal(report.status, 'unknown');
    assert.equal(api.verifyModelsV4(fixture.input, report, options).valid, true);
  });
}
const comparison = JSON.parse(read(catalog.reference.commonComparison));
check('frozen upstream comparison keeps its exact common scope', () => {
  assert.equal(comparison.fixedElleCommit, catalog.reference.commit);
  assert.deepEqual(comparison.models, catalog.reference.commonModels);
  assert.deepEqual(Object.keys(comparison.byModel), catalog.reference.commonDataModels);
  assert.equal(comparison.classifications, 2000);
  assert.equal(comparison.verifications, 2000);
  assert.equal(Object.values(comparison.totals).reduce((a, b) => a + b, 0), 2000);
  assert.equal(comparison.upstreamElleReexecuted, false);
});
check('runtime bytes are unchanged after matrix execution', () => assert.deepEqual(bindings(), before));
check('runner, declaration and original fixture bytes remain unchanged', () => {
  assert.deepEqual(readFileSync(fileURLToPath(import.meta.url)), runnerBytes);
  assert.deepEqual(read('docs/feature-matrix-v4.json'), catalogBytes);
  assert.deepEqual(read('fixtures/feature-matrix-v4.json'), fixtureBytes);
});
const items = rows.map(row => JSON.stringify(row)).join('\n') + '\n';
const summary = {
  format: 'moontxnwitness-executed-feature-matrix/v1',
  passed: checks.every(c => c.passed), checks: checks.length,
  modelRows: rows.length, profiles: catalog.profiles.length,
  sourceVersion: build.version, sourceFingerprint: build.sourceSha256, runtime: before,
  runnerSha256: sha(runnerBytes), catalogSha256: sha(catalogBytes),
  fixturesSha256: sha(fixtureBytes), itemsSha256: sha(items),
  scope: 'SDK source-profile/model obligations, independent-option verification, tamper rejection and capsule replay',
  newUpstreamElleExecution: false, allModelsDifferentiallyVerified: false,
  referenceComparison: {sha256: sha(read(catalog.reference.commonComparison)), models: comparison.models,
    dataModels: Object.keys(comparison.byModel), totals: comparison.totals},
  results: checks
};
writeFileSync(resolve(destination, 'items.jsonl'), items, {flag: 'wx'});
writeFileSync(resolve(destination, 'summary.json'), JSON.stringify(summary, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({passed: summary.passed, checks: checks.length, modelRows: rows.length,
  newUpstreamElleExecution: false, failed: checks.filter(c => !c.passed), output: destination}));
if (!summary.passed) process.exitCode = 1;
