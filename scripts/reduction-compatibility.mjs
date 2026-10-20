// Freeze old same-version full bytes before an internal reduction change, then
// compare the new engine without normalizing any report field or runtime count.
import assert from 'node:assert/strict';
import { readFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { gzipSync, gunzipSync } from 'node:zlib';
import { isDeepStrictEqual } from 'node:util';
import { writeImmutableEvidence } from './performance-evidence.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const folder = resolve(root, 'verification/fixtures/reduction-cache-v011');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const rel = path => relative(root, path).split('\\').join('/');
const load = path => JSON.parse(readFileSync(path));
const oldCore = '8f221e9935b867ebc797f8dce8285adfc3c00f9a5c0fbd1e4d1f8b60f3662af6';
const oldSource = '4b8ec7fc3b325473b695f11ab318f27491b68499f15a8cd7b897647cb2ff2ef3';
const op = (type, key, version) => ({ type, key, version });
const tx = (id, ops, status = 'committed') => ({ id, status, ops });
const history = transactions => ({ schemaVersion: 1, initial: { x: 'x0', y: 'y0' }, transactions });
const skew = (a = 'A', b = 'B') => [tx(a, [op('read', 'x', 'x0'), op('write', 'y', 'y1')]),
  tx(b, [op('read', 'y', 'y0'), op('write', 'x', 'x1')])];
const counts = output => ({ status: output.status, checks: output.checks ?? null,
  cachedCandidateChecks: output.cachedCandidateChecks ?? null, oneMinimal: output.oneMinimal,
  limits: output.limits ?? null, effectiveLimits: output.report?.effectiveLimits ?? null,
  search: output.report?.search ?? null, analysisOptions: output.report?.analysisOptions ?? null });

async function freeze(corePath) {
  assert.equal(hash(readFileSync(corePath)), oldCore);
  const core = await import(pathToFileURL(corePath).href);
  assert.equal(core.version(), '0.1.1');
  mkdirSync(folder, { recursive: false });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const work = resolve(root, 'artifacts', `reduction-compatibility-old-${stamp}`);
  mkdirSync(work, { recursive: false });
  const cases = [7, 32, 64, 512].map(size => ({ name: `noise-${size}`, options: {},
    history: load(resolve(root, `verification/fixtures/v010-comparison/reduction-${size}.json`)).history }));
  const large = cases.at(-1).history;
  for (const maxChecks of [0, 1, 2]) cases.push({ name: `noise-512-budget-${maxChecks}`, options: { maxChecks }, history: large });
  cases.push({ name: 'similar-and-unicode-identifiers', options: {},
    history: history([tx('a', []), tx('bc', []), ...skew('ab', 'c'), tx('引号"\\🙂', [op('read', 'x', 'x0')])]) });
  cases.push({ name: 'asserted-source-chain', options: {}, history: { ...history([
    tx('noise', [op('write', 'x', 'x1')]),
    tx('A', [op('read', 'x', 'x1'), op('write', 'y', 'y1')]),
    tx('B', [op('read', 'y', 'y0'), op('write', 'x', 'x2')]),
  ]), versionOrders: { x: ['x0', 'x1', 'x2'], y: ['y0', 'y1'] } } });
  cases.push({ name: 'aborted-source', options: {}, history: history([
    tx('writer', [op('write', 'x', 'dead')], 'aborted'), tx('reader', [op('read', 'x', 'dead')]),
    tx('noise', [op('read', 'y', 'y0')]),
  ]) });
  cases.push({ name: 'intermediate-source', options: {}, history: history([
    tx('writer', [op('write', 'x', 'x1'), op('write', 'x', 'x2')]),
    tx('reader', [op('read', 'x', 'x1')]), tx('noise', [op('read', 'y', 'y0')]),
  ]) });
  cases.push({ name: 'coexisting-anomalies', options: {}, history: history([
    tx('writer', [op('write', 'x', 'dead')], 'aborted'), tx('reader', [op('read', 'x', 'dead')]), ...skew(),
  ]) });
  cases.push({ name: 'consistent', options: {}, history: history([tx('a', [op('read', 'x', 'x0')])]) });
  cases.push({ name: 'invalid-options', options: { maxChecks: 257 }, history: history(skew()) });
  const manifest = { schema: 1, version: '0.1.1', frozenAt: new Date().toISOString(),
    sourceCommit: '3d94d41920dd991bfa0a49fccb01b8076b371958', sourceSha256: oldSource,
    coreSha256: oldCore, exactSameVersionBytesRequired: true, fieldsIgnored: [],
    rawOutputs: rel(work), scope: 'Reduction candidate-key internal optimization; complete original output and accounting retained', cases: [] };
  for (const fixture of cases) {
    const input = json(fixture), encoded = Buffer.from(core.shrink_options_json(JSON.stringify(fixture.history), JSON.stringify(fixture.options)));
    const output = JSON.parse(encoded), inputPath = resolve(folder, fixture.name + '.json');
    const outputPath = resolve(folder, fixture.name + '.output.json.gz');
    writeImmutableEvidence(inputPath, input);
    writeImmutableEvidence(outputPath, gzipSync(encoded, { level: 9 }));
    writeImmutableEvidence(resolve(work, fixture.name + '.output.json'), encoded);
    manifest.cases.push({ name: fixture.name, fixture: rel(inputPath), fixtureSha256: hash(input),
      output: rel(outputPath), outputBytes: encoded.length, outputSha256: hash(encoded),
      accounting: counts(output) });
  }
  const manifestPath = resolve(folder, 'manifest.json');
  writeImmutableEvidence(manifestPath, json(manifest));
  console.log(json({ frozen: true, cases: cases.length, version: core.version(), coreSha256: oldCore,
    manifest: rel(manifestPath), manifestSha256: hash(readFileSync(manifestPath)), rawOutputs: rel(work) }));
}

async function verify(corePath) {
  const manifest = load(resolve(folder, 'manifest.json'));
  const core = await import(pathToFileURL(corePath).href);
  assert.equal(core.version(), manifest.version);
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const work = resolve(root, 'artifacts', `reduction-compatibility-new-${stamp}`);
  mkdirSync(work, { recursive: false });
  const receipt = { schema: 1, passed: true, checkedAt: new Date().toISOString(), sameVersion: core.version(),
    oldCoreSha256: manifest.coreSha256, newCoreSha256: hash(readFileSync(corePath)),
    manifestSha256: hash(readFileSync(resolve(folder, 'manifest.json'))), fieldsIgnored: [],
    notPerformanceMeasurement: true, rawOutputs: rel(work), cases: [] };
  for (const item of manifest.cases) {
    const input = readFileSync(resolve(root, item.fixture));
    assert.equal(hash(input), item.fixtureSha256);
    const fixture = JSON.parse(input), expected = gunzipSync(readFileSync(resolve(root, item.output)));
    assert.equal(hash(expected), item.outputSha256);
    const actual = Buffer.from(core.shrink_options_json(JSON.stringify(fixture.history), JSON.stringify(fixture.options)));
    writeImmutableEvidence(resolve(work, item.name + '.output.json'), actual);
    const result = { name: item.name, exactBytesPassed: actual.equals(expected),
      structuredValuesPassed: isDeepStrictEqual(JSON.parse(actual), JSON.parse(expected)),
      oldSha256: item.outputSha256, newSha256: hash(actual),
      accountingPassed: isDeepStrictEqual(counts(JSON.parse(actual)), item.accounting) };
    receipt.cases.push(result);
    if (!result.exactBytesPassed || !result.structuredValuesPassed || !result.accountingPassed) receipt.passed = false;
  }
  const path = resolve(root, 'verification/releases/0.1.1', `reduction-compatibility-${stamp}.json`);
  writeImmutableEvidence(path, json(receipt));
  console.log(json({ passed: receipt.passed, cases: receipt.cases.length, receipt: rel(path), sha256: hash(readFileSync(path)) }));
  if (!receipt.passed) process.exitCode = 1;
}

if (process.argv.length === 4 && process.argv[2] === '--freeze') await freeze(resolve(process.argv[3]));
else if (process.argv.length === 4 && process.argv[2] === '--verify') await verify(resolve(process.argv[3]));
else throw Error('Usage: node scripts/reduction-compatibility.mjs --freeze OLD_CORE | --verify NEW_CORE');
