import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import {basename, resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {gunzipSync} from 'node:zlib';

const {values: args} = parseArgs({options: {
  receipt: {type: 'string'}, core: {type: 'string'}, output: {type: 'string'},
  'writer-proof-profile': {type: 'string'}, 'snapshot-profile': {type: 'string'}, 'artifact-dir': {type: 'string'},
}});
for (const filename of ['receipt', 'core', 'output']) assert(args[filename], `Require --${filename}`);

const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const bytes = await readFile(args.receipt);
const receipt = JSON.parse(bytes);
const multicolumn = receipt.format === 'configured-source-window-cost/v2';
const formal = multicolumn || receipt.format === 'configured-source-window-cost/v1';
assert(formal || receipt.format === 'configured-source-window-cost-pilot/v1');
assert.equal(receipt.actualDatabaseExecution, true);
assert.equal(receipt.passed, true);
const profile = args['writer-proof-profile'] ?? null;
assert([null, 'returning-v1'].includes(profile), 'Unknown independent writer proof profile');
assert.equal(receipt.writerProofProfileRequested ?? null, profile);
const snapshotProfile = args['snapshot-profile'];
const snapshotFormats = new Map([
  ['paged-v1', 'moontxnwitness-configured-source-snapshot-paged/v1'],
  ['paged-256-v1', 'moontxnwitness-configured-source-snapshot-paged/v2'],
]);
if (multicolumn) {
  assert(snapshotFormats.has(snapshotProfile), 'Supply the independently expected --snapshot-profile');
  assert.equal(receipt.snapshotProfileRequested, snapshotProfile);
} else {
  assert.equal(snapshotProfile, undefined);
}
const options = JSON.stringify(profile === null ? {} : {projectionOptions: {writerProofProfile: profile}});
const orders = ['ABC', 'BCA', 'CAB'];
if (formal) {
  const shape = [['small', 24, 1], ['wide', 1024, 4], ['hot', 32, 8]];
  if (multicolumn) {
    shape.forEach(load => load.push(0));
    shape.push(['multicolumn', 1024, 4, 12]);
  }
  assert.deepEqual(receipt.batches.map(b => [b.workload, b.keys, b.connections,
    ...(multicolumn ? [b.payloadColumns] : []), b.order]),
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
const artifact = path => args['artifact-dir'] ? resolve(args['artifact-dir'], basename(path)) : path;
if (args['artifact-dir']) assert.equal(receipt.artifactStorage, 'gzip-original-capture/v1');

async function verifyWindow(cells, connections, payloadColumns, checkTampering) {
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
  const captureBytes = await readFile(artifact(full.bundle));
  let raw;
  if (full.bundleEncoding === 'gzip') {
    assert.equal(receipt.artifactStorage, 'gzip-original-capture/v1');
    assert.equal(sha256(captureBytes), full.compressedSha256);
    assert.equal(sha256(await readFile(artifact(cells.B.sourceInstallation))), cells.B.sourceInstallationSha256);
    raw = new TextDecoder('utf-8', {fatal: true}).decode(gunzipSync(captureBytes, {maxOutputLength: 64 * 1024 * 1024}));
  } else {
    assert.equal(receipt.artifactStorage, undefined);
    raw = new TextDecoder('utf-8', {fatal: true}).decode(captureBytes);
  }
  assert.equal(sha256(raw), full.bundleSha256);
  if (formal) assert.equal(Buffer.byteLength(raw), full.outputBytes);
  let bundle;
  if (multicolumn) {
    assert.equal(full.config.table.businessColumns.length, 1 + payloadColumns);
    bundle = JSON.parse(raw);
    for (const boundary of ['startInputText', 'endInputText']) {
      const input = JSON.parse(bundle[boundary]);
      assert.equal(input.format, snapshotFormats.get(snapshotProfile));
      assert.equal(JSON.parse(input.receiptText).format, input.format);
    }
  }
  const config = JSON.stringify(full.config), policy = JSON.stringify(full.policy);
  const report = core.analyze_configured_window_v2_json(config, policy, raw, options);
  const analysis = JSON.parse(report);
  assert.equal(analysis.sourceMappingVerified, true, analysis.reason);
  assert.equal(analysis.writerWindowVerified, true, analysis.reason);
  const transactions = analysis.history.events.filter(event => event.kind === 'begin');
  assert.equal(transactions.length, full.commits);
  if (profile !== null) {
    assert.equal(analysis.execution.returningWriterProofs, full.commits);
    assert.equal(analysis.execution.precommitWriterProofs, 0);
  }
  const replay = JSON.parse(core.verify_configured_window_v2_json(config, policy, raw, report, options));
  assert.equal(replay.reportMatches, true);
  if (checkTampering && snapshotProfile === 'paged-256-v1') {
    const start = JSON.parse(bundle.startInputText);
    start.format = snapshotFormats.get('paged-v1');
    const changedReceipt = {...JSON.parse(start.receiptText), format: start.format};
    bundle.startInputText = JSON.stringify({...start, receiptText: JSON.stringify(changedReceipt)});
    const changed = JSON.parse(core.analyze_configured_window_v2_json(config, policy, JSON.stringify(bundle), options));
    assert.notEqual(changed.sourceMappingVerified, true);
  }
  return {commits: full.commits, sourceClosed: true, modelStatus: analysis.status,
    ...(profile === null ? {} : {returningWriterProofs: analysis.execution.returningWriterProofs})};
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
  for (const cells of [...warmup, ...measured]) {
    verified.push(await verifyWindow(cells, batch.connections, batch.payloadColumns, verified.length === 0));
  }
  const results = formal ? {workload: batch.workload, warmup: warmup.length, windows: verified,
    phases: phaseStatistics(measured)} : verified[0];
  checks.push({order: batch.order, ...results, throughputCA: batch.completeWindowThroughputRatioCA,
    transactionP95CA: batch.transactionP95RatioCA});
}

const result = {format: multicolumn ? 'configured-source-window-cost-verification/v2'
  : formal ? 'configured-source-window-cost-verification/v1'
                              : 'configured-source-window-cost-pilot-verification/v1', passed: true,
  formalPerformanceMeasurement: receipt.formalPerformanceMeasurement,
  originalReceiptSha256: sha256(bytes), coreSha256: sha256(compiled), checks};
if (profile !== null) result.writerProofProfile = profile;
if (multicolumn) result.snapshotProfile = snapshotProfile;
if (formal && Number.isSafeInteger(receipt.peakProcessRssBytes)) {
  result.peakProcessRssBytes = receipt.peakProcessRssBytes;
}
await writeFile(args.output, JSON.stringify(result, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({passed: true, windows: checks.length, output: args.output}));
