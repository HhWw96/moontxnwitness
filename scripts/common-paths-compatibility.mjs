// Non-timed, same-version byte compatibility for parsing/topological ordering.
// Freeze all 20 complete reports before editing, plus 15 development-hook values.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { gzipSync, gunzipSync } from 'node:zlib';
import { writeImmutableEvidence } from './performance-evidence.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const folder = resolve(root, 'verification/fixtures/common-paths-v011');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const rel = path => relative(root, path).split('\\').join('/');
const json = value => JSON.stringify(value, null, 2) + '\n';
const load = path => JSON.parse(readFileSync(path));
const oldCore = 'f2a0b6d1a07152aa599ce9e799e9b2a7b993b5bf87a73faada8705a1735c2d91';
const oldSource = '4f1a51358ac60eb6cb2d34443556ab67a79ee6482038590fa7390800a8029fba';
const phaseEncoding = 'JSON.stringify of development hook value; BigInt encoded as {"$bigint":"decimal"}; full reports retain original returned string bytes';

function execute(core, fixture, phase) {
  const text = JSON.stringify(fixture.history);
  if (phase === 'full') return Buffer.from(fixture.operation === 'shrink'
    ? core.shrink_options_json(text, '{}') : core.analyze_options_json(text, '{}'));
  const history = core.benchmark_parse_balanced(text);
  const result = core.benchmark_infer(history);
  const phases = {
    parse: () => history,
    inference: () => result,
    cycle: () => core.benchmark_cycle(history, result),
    search: () => core.benchmark_search_balanced(history, result),
    reduction: () => core.benchmark_reduce_balanced(history),
    render: () => core.benchmark_render(result),
  };
  assert.ok(phases[phase], 'Unknown phase');
  return Buffer.from(JSON.stringify(phases[phase](), (_key, value) =>
    typeof value === 'bigint' ? { $bigint: value.toString() } : value));
}

async function freeze(corePath) {
  assert.equal(sha(readFileSync(corePath)), oldCore);
  const core = await import(pathToFileURL(corePath).href);
  assert.equal(core.version(), '0.1.1');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const work = resolve(root, 'artifacts', `common-paths-compatibility-old-${stamp}`);
  mkdirSync(folder, { recursive: false });
  mkdirSync(work, { recursive: false });
  copyFileSync(corePath, resolve(work, 'core.mjs'));
  assert.equal(sha(readFileSync(resolve(work, 'core.mjs'))), oldCore);
  const fixtureManifest = load(resolve(root, 'verification/fixtures/v010-comparison/manifest.json'));
  const baselineManifest = load(resolve(root, 'verification/baselines/0.1.0/manifest.json'));
  const oldMeasurement = load(resolve(root, baselineManifest.latestFormalReceipt));
  assert.equal(fixtureManifest.cases.length, 20);
  assert.equal(oldMeasurement.phases.length, 15);
  const operations = [
    ...fixtureManifest.cases.map(item => ({ ...item, phase: 'full' })),
    ...oldMeasurement.phases.map(item => ({
      ...fixtureManifest.cases.find(c => c.name === item.scenario), phase: item.phase,
    })),
  ];
  const manifest = { schema: 1, version: '0.1.1', frozenAt: new Date().toISOString(),
    sourceCommit: 'f76aebfa3fabcc05d5605395c63356198e9b25fc',
    sourceSha256: oldSource, coreSha256: oldCore, retainedCore: rel(resolve(work, 'core.mjs')),
    fieldsIgnored: [], exactSameVersionBytesRequired: true, notPerformanceMeasurement: true,
    phaseEncoding, caveat: 'Prepared hook object encodings are internal development values, not a new public report schema.',
    cases: [] };
  for (const operation of operations) {
    const inputPath = resolve(root, operation.file), input = readFileSync(inputPath);
    assert.equal(sha(input), operation.fixtureSha256);
    const fixture = JSON.parse(input), output = execute(core, fixture, operation.phase);
    if (operation.phase === 'full') assert.equal(JSON.parse(output).status, fixture.status);
    const outputPath = resolve(folder, `${operation.name}-${operation.phase}.output.gz`);
    writeImmutableEvidence(outputPath, gzipSync(output, { level: 9 }));
    manifest.cases.push({ name: operation.name, phase: operation.phase,
      fixture: operation.file, fixtureSha256: sha(input),
      output: rel(outputPath), outputBytes: output.length, outputSha256: sha(output) });
  }
  writeImmutableEvidence(resolve(folder, 'manifest.json'), json(manifest));
  console.log(json({ frozen: true, fullReports: 20, phaseValues: 15,
    oldCoreSha256: oldCore, manifest: rel(resolve(folder, 'manifest.json')),
    manifestSha256: sha(readFileSync(resolve(folder, 'manifest.json'))), retainedCore: manifest.retainedCore }));
}

async function verify(corePath) {
  const manifest = load(resolve(folder, 'manifest.json'));
  const core = await import(pathToFileURL(corePath).href);
  assert.equal(core.version(), manifest.version);
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const receipt = { schema: 1, checkedAt: new Date().toISOString(), passed: true,
    sameVersion: core.version(), oldCoreSha256: manifest.coreSha256,
    newCoreSha256: sha(readFileSync(corePath)), fieldsIgnored: [],
    manifestSha256: sha(readFileSync(resolve(folder, 'manifest.json'))),
    notPerformanceMeasurement: true, phaseEncoding, cases: [] };
  for (const item of manifest.cases) {
    const input = readFileSync(resolve(root, item.fixture));
    assert.equal(sha(input), item.fixtureSha256);
    const expected = gunzipSync(readFileSync(resolve(root, item.output)));
    assert.equal(sha(expected), item.outputSha256);
    const actual = execute(core, JSON.parse(input), item.phase);
    const row = { name: item.name, phase: item.phase, exactBytesPassed: actual.equals(expected),
      expectedSha256: item.outputSha256, actualSha256: sha(actual),
      expectedBytes: expected.length, actualBytes: actual.length };
    if (!row.exactBytesPassed) receipt.passed = false;
    receipt.cases.push(row);
  }
  const path = resolve(root, 'verification/releases/0.1.1', `common-paths-compatibility-${stamp}.json`);
  writeImmutableEvidence(path, json(receipt));
  console.log(json({ passed: receipt.passed, fullReports: 20, phaseValues: 15,
    failed: receipt.cases.filter(r => !r.exactBytesPassed).map(r => `${r.name}/${r.phase}`),
    receipt: rel(path), sha256: sha(readFileSync(path)) }));
  if (!receipt.passed) process.exitCode = 1;
}

if (process.argv.length === 4 && process.argv[2] === '--freeze') await freeze(resolve(process.argv[3]));
else if (process.argv.length === 4 && process.argv[2] === '--verify') await verify(resolve(process.argv[3]));
else throw Error('Usage: node scripts/common-paths-compatibility.mjs --freeze OLD_CORE | --verify NEW_CORE');
