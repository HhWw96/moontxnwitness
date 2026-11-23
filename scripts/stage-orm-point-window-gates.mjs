// Recompute the downstream fixtures from a successful real FastAPI Users run.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir, readFile, realpath, writeFile} from 'node:fs/promises';
import {dirname, isAbsolute, relative, resolve, sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';

const {values: args} = parseArgs({options: {
  receipt: {type: 'string'}, runtime: {type: 'string'}, output: {type: 'string'},
}});
assert(args.receipt && args.runtime && args.output, 'Use --receipt FILE --runtime DIST --output NEW_DIR');
const receiptPath = await realpath(args.receipt);
const receiptBytes = await readFile(receiptPath);
const receipt = JSON.parse(receiptBytes);
assert.equal(receipt.passed, true);
assert.equal(receipt.actualDatabaseExecution, true);
assert.equal(receipt.fastapiUsersSeedCampaign, true);
assert.equal(receipt.postgresVersion, 'postgres (PostgreSQL) 18.6');

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const parent = dirname(receiptPath);
const planBytes = await readFile(resolve(parent, 'async-users-seeds.json'));
const plan = JSON.parse(planBytes);
const seeds = Array.from({length: 30}, (_, index) => index);
assert.deepEqual(plan, {upstreamCommit: '6397ace506d829a2ee12786da5d724c3f4c6b634', seeds});
const fixtures = receipt.records.flatMap(record => record.analysisFixtures);
const campaign = fixtures.filter(fixture => fixture.name.startsWith('fastapi-users-base-crud-'));
assert.deepEqual(campaign.map(fixture => fixture.seed), seeds);
for (const fixture of campaign) {
  assert.equal(fixture.upstreamCommit, plan.upstreamCommit);
  assert.equal(fixture.seedPlanSha256, sha(planBytes));
  assert.equal(fixture.businessParityVerified, true);
  assert.equal(fixture.expected, 'compatible');
}
const duplicates = fixtures.filter(fixture => fixture.name === 'fastapi-users-duplicate-email');
assert.equal(duplicates.length, 1);
const [duplicate] = duplicates;
assert.equal(duplicate.upstreamCommit, plan.upstreamCommit);
assert.equal(duplicate.businessParityVerified, true);
assert.equal(duplicate.businessSqlstate, '23505');
assert.equal(duplicate.expected, 'unknown');
const ordered = campaign[0];
assert.deepEqual(ordered.config, duplicate.config);
assert.deepEqual(ordered.policy, duplicate.policy);

const runtime = await import(pathToFileURL(resolve(args.runtime, 'configured-window-v2-capsule.mjs')).href);
const config = JSON.stringify(ordered.config) + '\n';
const policy = JSON.stringify(ordered.policy) + '\n';
const options = {config, policy, maxPointChecks: 1_000_000};
const output = resolve(args.output);
await mkdir(output);
const cases = [];
for (const [name, fixture, status, code] of [
  ['ordered', ordered, 'checked-compatible', 0], ['duplicate', duplicate, 'unknown', 2],
]) {
  const path = await realpath(fixture.bundle);
  const confined = relative(parent, path);
  assert(confined && !isAbsolute(confined) && confined.split(sep)[0] !== '..', fixture.name);
  const raw = await readFile(path);
  assert.equal(sha(raw), fixture.bundleSha256, fixture.name);
  const text = raw.toString('utf8');
  assert(Buffer.from(text).equals(raw), 'Original ORM capture requires valid UTF-8');
  const events = JSON.parse(JSON.parse(text).diagnosticTraceText).events;
  if (code === 2) {
    const rollbacks = events.filter(event => event.kind === 'rollback_ok');
    assert.equal(rollbacks.length, 1);
    const [rollback] = rollbacks;
    assert(events.some(event => event.kind === 'commit_ok' && event.seq > rollback.seq && event.tx !== rollback.tx),
      'Duplicate-email recovery must commit in a new transaction');
  }
  const capsule = runtime.makeConfiguredWindowCapsuleV4(text, options);
  const checked = runtime.replayConfiguredWindowCapsuleV4(capsule, options);
  assert.equal(checked.reportMatches, true);
  assert.equal(checked.status, status);
  assert.equal(checked.report.coverageComplete, code === 0);
  await writeFile(resolve(output, name + '.capsule.json'), capsule, {flag: 'wx'});
  cases.push({name, code, status, bundleSha256: fixture.bundleSha256, capsuleSha256: sha(capsule)});
}
await writeFile(resolve(output, 'config.json'), config, {flag: 'wx'});
await writeFile(resolve(output, 'policy.json'), policy, {flag: 'wx'});
const report = {passed: true, upstreamCommit: plan.upstreamCommit, comparedSeeds: seeds.length,
  databaseReceiptSha256: sha(receiptBytes), sqlstate: duplicate.businessSqlstate, cases};
await writeFile(resolve(output, 'staged.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify(report));
