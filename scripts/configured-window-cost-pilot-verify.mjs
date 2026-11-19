import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import {parseArgs} from 'node:util';

const {values: args} = parseArgs({options: {
  receipt: {type: 'string'}, core: {type: 'string'}, output: {type: 'string'},
}});
for (const filename of ['receipt', 'core', 'output']) assert(args[filename], `Require --${filename}`);

const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const bytes = await readFile(args.receipt);
const receipt = JSON.parse(bytes);
assert.equal(receipt.format, 'configured-source-window-cost-pilot/v1');
assert.equal(receipt.actualDatabaseExecution, true);
assert.equal(receipt.passed, true);
assert.deepEqual(receipt.batches.map(batch => batch.order), ['ABC', 'BCA', 'CAB']);
const compiled = await readFile(args.core);
const core = await import('data:text/javascript;base64,' + compiled.toString('base64'));
const checks = [];

for (const batch of receipt.batches) {
  for (const phase of ['A', 'B', 'C']) {
    assert.equal(batch.cells[phase].commits, receipt.transactionsPerPhase);
    assert.equal(batch.cells[phase].finalBusinessSha256, batch.cells.A.finalBusinessSha256);
  }
  const full = batch.cells.C;
  const raw = await readFile(full.bundle, 'utf8');
  assert.equal(sha256(raw), full.bundleSha256);
  const config = JSON.stringify(full.config), policy = JSON.stringify(full.policy);
  const report = core.analyze_configured_window_v2_json(config, policy, raw, '{}');
  const analysis = JSON.parse(report);
  assert.equal(analysis.sourceMappingVerified, true, analysis.reason);
  assert.equal(analysis.writerWindowVerified, true, analysis.reason);
  const transactions = analysis.history.events.filter(event => event.kind === 'begin');
  assert.equal(transactions.length, full.commits);
  const replay = JSON.parse(core.verify_configured_window_v2_json(config, policy, raw, report, '{}'));
  assert.equal(replay.reportMatches, true);
  checks.push({order: batch.order, commits: full.commits, sourceClosed: true, modelStatus: analysis.status,
    throughputCA: batch.completeWindowThroughputRatioCA, transactionP95CA: batch.transactionP95RatioCA});
}

const result = {format: 'configured-source-window-cost-pilot-verification/v1', passed: true,
  formalPerformanceMeasurement: false, originalReceiptSha256: sha256(bytes), coreSha256: sha256(compiled), checks};
await writeFile(args.output, JSON.stringify(result, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({passed: true, windows: checks.length, output: args.output}));
