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
const formal = receipt.format === 'configured-source-window-cost/v1';
assert(formal || receipt.format === 'configured-source-window-cost-pilot/v1');
assert.equal(receipt.actualDatabaseExecution, true);
assert.equal(receipt.passed, true);
const orders = ['ABC', 'BCA', 'CAB'];
if (formal) {
  const shape = [['small', 24, 1], ['wide', 1024, 4], ['hot', 32, 8]];
  assert.deepEqual(receipt.batches.map(b => [b.workload, b.keys, b.connections, b.order]),
    shape.flatMap(load => orders.map(order => [...load, order])));
  assert.equal(receipt.transactionsPerPhase, 24);
  assert.equal(receipt.warmupWindowsPerPhase, receipt.formalPerformanceMeasurement ? 5 : 0);
  assert.equal(receipt.measuredWindowsPerPhase, receipt.formalPerformanceMeasurement ? 30 : 1);
  if (receipt.formalPerformanceMeasurement) {
    assert(Number.isSafeInteger(receipt.peakProcessRssBytes) && receipt.peakProcessRssBytes > 0);
  }
} else {
  assert.equal(receipt.formalPerformanceMeasurement, false);
  assert.deepEqual(receipt.batches.map(batch => batch.order), orders);
}
const compiled = await readFile(args.core);
const core = await import('data:text/javascript;base64,' + compiled.toString('base64'));
const checks = [];

async function verifyWindow(cells, connections) {
  for (const phase of ['A', 'B', 'C']) {
    const cell = cells[phase];
    assert.equal(cell.phase, phase);
    assert.equal(cell.commits, receipt.transactionsPerPhase);
    assert.equal(cell.finalBusinessSha256, cells.A.finalBusinessSha256);
    if (formal) {
      assert.equal(cell.connections, connections);
      assert.equal(cell.transactionSamplesNs.length, cell.commits);
      assert(cell.transactionSamplesNs.every(sample => Number.isSafeInteger(sample) && sample > 0));
      assert.equal(cell.windowNs, cell.windowOpenNs + cell.businessNs + cell.windowSealNs);
    }
  }
  const full = cells.C;
  const raw = await readFile(full.bundle, 'utf8');
  assert.equal(sha256(raw), full.bundleSha256);
  if (formal) assert.equal(Buffer.byteLength(raw), full.outputBytes);
  const config = JSON.stringify(full.config), policy = JSON.stringify(full.policy);
  const report = core.analyze_configured_window_v2_json(config, policy, raw, '{}');
  const analysis = JSON.parse(report);
  assert.equal(analysis.sourceMappingVerified, true, analysis.reason);
  assert.equal(analysis.writerWindowVerified, true, analysis.reason);
  const transactions = analysis.history.events.filter(event => event.kind === 'begin');
  assert.equal(transactions.length, full.commits);
  const replay = JSON.parse(core.verify_configured_window_v2_json(config, policy, raw, report, '{}'));
  assert.equal(replay.reportMatches, true);
  return {commits: full.commits, sourceClosed: true, modelStatus: analysis.status};
}

function percentile(samples, fraction) {
  return [...samples].sort((a, b) => a - b)[Math.ceil(samples.length * fraction) - 1];
}

function median(samples) {
  const values = [...samples].sort((a, b) => a - b);
  const lower = Math.floor((values.length - 1) / 2);
  return (values[lower] + values[values.length - 1 - lower]) / 2;
}

function phaseStatistics(measured) {
  const stats = values => ({median: median(values), p95: percentile(values, .95)});
  return Object.fromEntries(['A', 'B', 'C'].map(phase => {
    const windows = measured.map(cells => cells[phase]);
    const values = field => stats(windows.map(cell => cell[field]));
    return [phase, {openNs: values('windowOpenNs'), businessNs: values('businessNs'),
      sealNs: values('windowSealNs'), windowNs: values('windowNs'),
      throughputPerSecond: 1e9 * receipt.transactionsPerPhase / median(windows.map(cell => cell.windowNs)),
      transactionNs: stats(windows.flatMap(cell => cell.transactionSamplesNs)),
      outputBytes: values('outputBytes')}];
  }));
}

for (const batch of receipt.batches) {
  const measured = formal ? batch.windows : [batch.cells];
  const warmup = formal ? batch.warmup : [];
  if (formal) {
    assert.equal(measured.length, receipt.measuredWindowsPerPhase);
    assert.equal(warmup.length, receipt.warmupWindowsPerPhase);
    const duration = phase => median(measured.map(cells => cells[phase].windowNs));
    const latency = phase => percentile(measured.flatMap(cells => cells[phase].transactionSamplesNs), .95);
    assert.equal(batch.completeWindowThroughputRatioCA, duration('A') / duration('C'));
    assert.equal(batch.transactionP95RatioCA, latency('C') / latency('A'));
  }
  const verified = [];
  for (const cells of [...warmup, ...measured]) verified.push(await verifyWindow(cells, batch.connections));
  const results = formal ? {workload: batch.workload, warmup: warmup.length, windows: verified,
    phases: phaseStatistics(measured)} : verified[0];
  checks.push({order: batch.order, ...results, throughputCA: batch.completeWindowThroughputRatioCA,
    transactionP95CA: batch.transactionP95RatioCA});
}

const result = {format: formal ? 'configured-source-window-cost-verification/v1'
                              : 'configured-source-window-cost-pilot-verification/v1', passed: true,
  formalPerformanceMeasurement: receipt.formalPerformanceMeasurement,
  originalReceiptSha256: sha256(bytes), coreSha256: sha256(compiled), checks};
if (formal && Number.isSafeInteger(receipt.peakProcessRssBytes)) {
  result.peakProcessRssBytes = receipt.peakProcessRssBytes;
}
await writeFile(args.output, JSON.stringify(result, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({passed: true, windows: checks.length, output: args.output}));
