import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';

const { values } = parseArgs({ options: {
  baseline: { type: 'string' }, candidate: { type: 'string' }, output: { type: 'string' },
}});
assert(values.baseline && values.candidate && values.output,
  'Provide --baseline DIR --candidate DIR --output FILE');

const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const loadComparisonInput = async directory => {
  const original = await readFile(resolve(directory, 'receipt.json'));
  const receipt = JSON.parse(original);
  const verified = JSON.parse(await readFile(resolve(directory, 'verified.json')));
  assert.equal(receipt.formalPerformanceMeasurement, true);
  assert.equal(receipt.actualDatabaseExecution, true);
  assert.equal(verified.format, 'configured-source-window-cost-verification/v1');
  assert.equal(verified.passed, true);
  assert.equal(verified.formalPerformanceMeasurement, true);
  assert.equal(verified.originalReceiptSha256, digest(original));
  assert.equal(verified.peakProcessRssBytes, receipt.peakProcessRssBytes);
  return { receipt, verified };
};
const [baseline, candidate] = await Promise.all([
  loadComparisonInput(values.baseline), loadComparisonInput(values.candidate),
]);
assert.deepEqual(baseline.receipt.environment, candidate.receipt.environment);
assert.equal(baseline.receipt.harnessSha256, candidate.receipt.harnessSha256);
assert.equal(baseline.verified.coreSha256, candidate.verified.coreSha256);
assert.notEqual(baseline.receipt.producerSha256, candidate.receipt.producerSha256);
assert.equal(baseline.verified.checks.length, candidate.verified.checks.length);
if (baseline.receipt.pairedSchedule || candidate.receipt.pairedSchedule) {
  const schedule = baseline.receipt.pairedSchedule;
  assert.deepEqual(schedule, candidate.receipt.pairedSchedule);
  assert.equal(baseline.receipt.pairedRunnerSha256, candidate.receipt.pairedRunnerSha256);
  const expected = baseline.verified.checks.flatMap(({workload, order}, batchIndex) =>
    [['warmup', 5], ['windows', 30]].flatMap(([kind, count]) => Array.from({length: count}, (_, index) =>
      ({workload, order, kind, index, arms: (index + batchIndex % 3) % 2 === 0
        ? ['baseline', 'candidate'] : ['candidate', 'baseline']}))));
  assert.deepEqual(schedule, expected, 'Incomplete or differently ordered paired schedule');
}
const returning = candidate.verified.writerProofProfile === 'returning-v1';
if (returning) {
  assert.equal(baseline.verified.writerProofProfile, undefined);
  assert.equal(candidate.receipt.writerProofProfileRequested, 'returning-v1');
  assert.equal(baseline.receipt.writerProofProfileRequested, null);
  assert.equal(candidate.receipt.sealProfileRequested, baseline.receipt.sealProfileRequested);
}
const withinControl = (base, next) => next - base <= Math.max(0.10 * base, 2_000_000);

const rows = baseline.verified.checks.map((base, index) => {
  const next = candidate.verified.checks[index];
  assert.equal(base.workload, next.workload);
  assert.equal(base.order, next.order);
  const [oldC, newC] = [base.phases.C, next.phases.C];
  const controls = Object.fromEntries(['A', 'B'].map(phase => {
    const before = base.phases[phase].transactionNs.p95;
    const after = next.phases[phase].transactionNs.p95;
    return [phase, {ratio: after / before, passed: withinControl(before, after)}];
  }));
  return {
    workload: base.workload, order: base.order,
    windowThroughputSpeedup: newC.throughputPerSecond / oldC.throughputPerSecond,
    windowP95Ratio: newC.windowNs.p95 / oldC.windowNs.p95,
    transactionP95Ratio: newC.transactionNs.p95 / oldC.transactionNs.p95,
    sealP95Ratio: newC.sealNs.p95 / oldC.sealNs.p95,
    outputMedianBytes: { baseline: oldC.outputBytes.median, candidate: newC.outputBytes.median },
    transactionP95WithinControl: withinControl(oldC.transactionNs.p95, newC.transactionNs.p95),
    ...(returning ? {controls} : {}),
    captureCostCA: { throughputRatio: next.throughputCA, transactionP95Ratio: next.transactionP95CA },
  };
});
const geometricMean = values => Math.exp(values.reduce((sum, value) => sum + Math.log(value), 0) / values.length);
const output = {
  format: 'configured-source-window-cost-comparison/v1',
  baselineReceiptSha256: baseline.verified.originalReceiptSha256,
  candidateReceiptSha256: candidate.verified.originalReceiptSha256,
  baselineCommit: baseline.receipt.sourceCommit,
  candidateCommit: candidate.receipt.sourceCommit,
  windowThroughputGeometricMean: geometricMean(rows.map(row => row.windowThroughputSpeedup)),
  windowP95GeometricMeanRatio: geometricMean(rows.map(row => row.windowP95Ratio)),
  transactionP95GeometricMeanRatio: geometricMean(rows.map(row => row.transactionP95Ratio)),
  peakProcessRssRatio: candidate.verified.peakProcessRssBytes / baseline.verified.peakProcessRssBytes,
  allTransactionP95ControlsPassed: rows.every(row => row.transactionP95WithinControl),
  rows,
};
if (returning) {
  const throughputTarget = 1.5;
  const p95RatioTarget = 0.70;
  const controlPhasesPassed = rows.every(row => row.controls.A.passed && row.controls.B.passed);
  output.returningQualification = {
    throughputTarget, p95RatioTarget, controlPhasesPassed,
    recommended: controlPhasesPassed && output.allTransactionP95ControlsPassed
      && output.windowThroughputGeometricMean >= throughputTarget
      && output.transactionP95GeometricMeanRatio <= p95RatioTarget,
  };
}
await writeFile(values.output, JSON.stringify(output, null, 2) + '\n', { flag: 'wx' });
