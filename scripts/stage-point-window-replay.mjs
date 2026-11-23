// Stage exact captured window bytes from a trusted, disposable database run.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir, readFile, realpath, writeFile} from 'node:fs/promises';
import {dirname, isAbsolute, relative, resolve, sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {gzipSync} from 'node:zlib';

const {values: args} = parseArgs({options: {
  receipt: {type: 'string'}, runtime: {type: 'string'}, output: {type: 'string'},
}});
assert(args.receipt && args.runtime && args.output, 'Use --receipt FILE --runtime DIST --output NEW_DIR');
const receiptPath = await realpath(args.receipt);
const receipt = JSON.parse(await readFile(receiptPath, 'utf8'));
assert.equal(receipt.passed, true);
assert.equal(receipt.actualDatabaseExecution, true);
const {makeConfiguredWindowCapsuleV4, makeConfiguredWindowReductionCapsuleV4} = await import(
  pathToFileURL(resolve(args.runtime, 'configured-window-v2-capsule.mjs')).href);
const fixtures = receipt.records.find(record => record.keyType === 'int64').analysisFixtures;
const scenario = name => {
  const matches = fixtures.filter(fixture => fixture.name === name);
  assert.equal(matches.length, 1, name);
  return matches[0];
};
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

const before = scenario('async-rr-write-skew-noise');
const retry = scenario('async-serializable-retry');
const ordered = scenario('serializable-ordered');
assert.deepEqual(before.observations.finalEnabled, [false, false]);
assert.deepEqual(retry.observations.finalEnabled, [false, true]);
assert.equal(retry.observations.rollbackSqlstate, '40001');
assert.equal(retry.observations.retryCommitted, true);
for (const fixture of [retry, ordered]) {
  assert.deepEqual(fixture.config, before.config);
  assert.deepEqual(fixture.policy, before.policy);
}
async function bundle(fixture) {
  const path = await realpath(fixture.bundle);
  const fromReceipt = relative(dirname(receiptPath), path);
  assert(fromReceipt && !isAbsolute(fromReceipt) && fromReceipt.split(sep)[0] !== '..', fixture.name);
  const data = await readFile(path);
  assert.equal(sha256(data), fixture.bundleSha256, fixture.name);
  // Raw observation packets are published only from this isolated fixture.
  // Reject credentials or workstation paths instead of editing the source bytes.
  const value = data.toString('utf8');
  assert(!/(?:[A-Z]:\\{1,}|\/Users\/|\/home\/|postgres(?:ql)?:\/\/|password=)/i.test(value),
    'Fixture contains a private locator or database connection setting');
  assert(Buffer.from(value).equals(data), 'Original packet is not valid UTF-8');
  return value;
}
const [beforeText, retryText, orderedText] = await Promise.all([before, retry, ordered].map(bundle));
const config = JSON.stringify(before.config) + '\n', policy = JSON.stringify(before.policy) + '\n';
const options = {config, policy, maxPointChecks: 1_000_000};
const files = {
  'config.json': config,
  'policy.json': policy,
  'before.json.gz': gzipSync(makeConfiguredWindowCapsuleV4(beforeText, options)),
  'reduced.json.gz': gzipSync(makeConfiguredWindowReductionCapsuleV4(beforeText, {config, policy,
    preserveModel: 'serializable', windowOptions: {maxPointChecks: options.maxPointChecks},
    reductionOptions: {maxChecks: 256}})),
  'retry.json.gz': gzipSync(makeConfiguredWindowCapsuleV4(retryText, options)),
  'ordered.json.gz': gzipSync(makeConfiguredWindowCapsuleV4(orderedText, options)),
};
const manifest = {format: 'moontxnwitness-point-window-replay/v1',
  captureNames: [before.name, retry.name, ordered.name],
  sha256: Object.fromEntries(Object.entries(files).map(([name, value]) => [name, sha256(value)]))};
await mkdir(args.output);
await Promise.all(Object.entries({...files, 'manifest.json': JSON.stringify(manifest, null, 2) + '\n'})
  .map(([name, value]) => writeFile(resolve(args.output, name), value, {flag: 'wx'})));
