import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import {parseArgs} from 'node:util';
import {gunzipSync} from 'node:zlib';
import {replayConfiguredWindowCapsuleV4, replayConfiguredWindowReductionCapsuleV4}
  from '../dist/configured-window-v2-capsule.mjs';
import {explainConfiguredWindowV4} from '../dist/configured-window-v2-standalone.mjs';

const {values: args} = parseArgs({options: {html: {type: 'string'}}});
const root = new URL('./point-window-replay-data/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('manifest.json', root), 'utf8'));
assert.equal(manifest.format, 'moontxnwitness-point-window-replay/v1');
const files = ['config.json', 'policy.json', 'before.json.gz', 'reduced.json.gz', 'retry.json.gz', 'ordered.json.gz'];
assert.deepEqual(Object.keys(manifest.sha256).sort(), files.slice().sort());
const inputs = Object.fromEntries(await Promise.all(files.map(async name => {
  const bytes = await readFile(new URL(name, root));
  assert.equal(createHash('sha256').update(bytes).digest('hex'), manifest.sha256[name], name);
  const text = name.endsWith('.gz') ? gunzipSync(bytes, {maxOutputLength: 64 * 1024 * 1024}) : bytes;
  return [name.replace(/\.gz$/, ''), text.toString('utf8')];
})));

const options = {config: inputs['config.json'], policy: inputs['policy.json'], maxPointChecks: 1_000_000};
const reductionOptions = {config: options.config, policy: options.policy,
  preserveModel: 'serializable', windowOptions: {maxPointChecks: options.maxPointChecks},
  reductionOptions: {maxChecks: 256}};

function replay(name, status, valid) {
  const result = replayConfiguredWindowCapsuleV4(inputs[name], options);
  assert.deepEqual([result.envelopeVerified, result.reportMatches, result.status, result.valid],
    [true, true, status, valid], name);
  return {report: result.report, bundleText: JSON.parse(inputs[name]).bundleText, sha256: result.bundleSha256};
}

function snapshot(bundle, field, query) {
  return JSON.parse(bundle[field]).logText.trimEnd().split('\n').map(line => JSON.parse(line))
    .filter(record => record.kind === 'control-delivery' && record.queryId === query)
    .flatMap(record => record.observation.rows.map(row => JSON.parse(row.cells[0].value)));
}

function caseEvidence(bundleText) {
  const bundle = JSON.parse(bundleText);
  const initial = snapshot(bundle, 'startInputText', 'visible-row');
  const final = snapshot(bundle, 'endInputText', 'visible-row');
  const [server] = snapshot(bundle, 'endInputText', 'environment');
  const key = (rows, identity) => {
    const entry = rows.find(entry => entry.row.identity === identity).row;
    return {identity, enabled: entry.enabled, version: String(entry.__mtw_source_version)};
  };
  return {serverVersionNum: server.serverVersionNum, initial: [7, 101].map(id => key(initial, id)),
    final: [7, 101].map(id => key(final, id)), events: JSON.parse(bundle.diagnosticTraceText).events};
}

const before = replay('before.json', 'refuted', true);
const retry = replay('retry.json', 'unknown', false);
const ordered = replay('ordered.json', 'checked-compatible', true);
const reduced = replayConfiguredWindowReductionCapsuleV4(inputs['reduced.json'], reductionOptions);
assert.deepEqual([reduced.valid, reduced.refutationVerified, reduced.oneMinimalVerified, reduced.bundleSha256],
  [true, true, true, before.sha256]);
const selection = reduced.report.reduction;
const selected = selection.selectedTransactions.length;
const original = before.report.history.events.filter(event => event.kind === 'begin').length;
assert.deepEqual([original, selected], [5, 2]);
const category = before.report.itemCategory.judgment.rules['G2-item'];
assert.equal(category.status, 'refuted');

const failed = caseEvidence(before.bundleText), repaired = caseEvidence(retry.bundleText);
const control = caseEvidence(ordered.bundleText);
for (const evidence of [failed, repaired, control]) {
  assert.equal(evidence.serverVersionNum, '180006');
  assert.deepEqual(evidence.initial.map(row => row.enabled), [true, true]);
}
assert.deepEqual(failed.final.map(row => row.enabled), [false, false]);
assert.deepEqual(repaired.final.map(row => row.enabled), [false, true]);
assert.deepEqual(control.final.map(row => row.enabled), [false, true]);
assert.equal(failed.events.filter(event => event.kind === 'commit_ok').length, 5);
const rollbacks = repaired.events.filter(event => event.kind === 'rollback_ok');
assert.equal(rollbacks.length, 1);
const [rollback] = rollbacks;
assert.equal(rollback.commitResponse.sqlstate, '40001');
const commits = repaired.events.filter(event => event.kind === 'commit_ok');
assert.equal(commits.length, 2);
assert.notEqual(commits[1].tx, rollback.tx);
assert(commits[1].seq > rollback.seq);

if (args.html) {
  const html = explainConfiguredWindowV4(before.bundleText, before.report, options,
    {reduction: reduced.report, reductionOptions});
  await writeFile(args.html, html, {flag: 'wx'});
}
console.log(JSON.stringify({passed: true, databaseExecutedDuringReplay: false,
  capturedPostgreSQLVersion: '18.6', category: 'G2-item', model: 'serializable',
  originalTransactions: original, reducedTransactions: selected, oneMinimalVerified: true,
  before: {status: before.report.status, finalRows: failed.final, witness: category.evidence},
  retry: {status: retry.report.status, sqlstate: rollback.commitResponse.sqlstate,
    committedRetry: commits[1].tx, finalRows: repaired.final},
  orderedControl: {status: ordered.report.status, finalRows: control.final},
}, null, 2));
