// Read-only formal-evidence audit. No engine or database is executed.
import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import { isDeepStrictEqual } from 'node:util';
import { fileURLToPath } from 'node:url';
// Persistence is independently checked below without importing the writer/recovery implementation.

const [receiptPath, expectedReceiptHash, expectedSourceHash, expectedCoreHash, auditFile] = process.argv.slice(2);
assert.ok(auditFile, 'Provide receipt, receipt SHA, source SHA, core SHA and a new audit file');
const root = process.cwd(), rel = path => relative(root, path).split('\\').join('/');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
try {
const path = resolve(receiptPath), directory = dirname(path);
assert.equal(hash(fs.readFileSync(path)), expectedReceiptHash);
const latestPath = resolve('verification/releases/0.1.1/performance-v010-latest.json');
const pointerBytes = fs.readFileSync(latestPath), pointer = JSON.parse(pointerBytes);
assert.equal(resolve(pointer.receipt), path);
assert.equal(hash(fs.readFileSync(path)), pointer.sha256);
assert.equal(fs.readFileSync(path).length,pointer.bytes);
const receipt = JSON.parse(fs.readFileSync(path));
const recovered={source:'independently-validated-published-pointer'};
assert.equal(receipt.complete, true);
assert.equal(receipt.smokeOnly, false);
assert.equal(receipt.correctnessPassed, true);
assert.equal(receipt.formalReleaseGatePassed, receipt.results.every(row => row.p95WithinAllowance));
assert.equal(receipt.passed, receipt.formalReleaseGatePassed);
assert.equal(receipt.results.length, 20);
assert.equal(receipt.phases.length, 15);
assert.equal(receipt.protocol.warmups, 5);
assert.equal(receipt.protocol.samplesPerBatch, 30);
assert.equal(receipt.protocol.independentAlternatingBatches, 3);
assert.equal(receipt.provenance.currentBuildManifest.sourceSha256, expectedSourceHash);
assert.equal(receipt.provenance.currentBuildManifest.coreSha256, expectedCoreHash);
assert.equal(hash(fs.readFileSync('scripts/performance-v010.mjs')), '441ddab4e6e0976b5305e84b25e04b4abd003e13a4293e177115371885e00fca');
assert.equal(hash(fs.readFileSync('scripts/performance-evidence.mjs')), 'fb0fc271d87f29f164013553e57dffbc155e92baf5f83304665654ba0dd1423a');

const files = fs.readdirSync(directory).filter(name => /^\d{6}-[a-f0-9-]+\.json$/.test(name)).sort();
assert.equal(files.length, 38);
let previous = null;
for (const [position, name] of files.entries()) {
  const checkpointPath = resolve(directory, name), bytes = fs.readFileSync(checkpointPath);
  const { evidenceCheckpoint: checkpoint, ...payload } = JSON.parse(bytes);
  assert.equal(checkpoint.sequence, position + 1);
  assert.equal(checkpoint.runId, pointer.runId);
  const encoded = Buffer.from(JSON.stringify(payload, null, 2) + '\n');
  assert.equal(checkpoint.payloadBytes, encoded.length);
  assert.equal(checkpoint.payloadSha256, hash(encoded));
  assert.deepEqual(checkpoint.previous, previous);
  previous = { receipt: rel(checkpointPath), sha256: hash(bytes) };
  if (position < 37) {
    assert.equal(payload.complete, false);
    assert.equal(payload.formalReleaseGatePassed, false);
    assert.equal(payload.correctnessPassed, false);
  }
  const sequence = position + 1;
  assert.equal(payload.results.length, sequence < 3 ? 0 : Math.min(sequence - 2, 20));
  assert.equal(payload.phases.length, sequence < 23 ? 0 : Math.min(sequence - 22, 15));
  assert.ok(isDeepStrictEqual(payload.results, receipt.results.slice(0, payload.results.length)));
  assert.ok(isDeepStrictEqual(payload.phases, receipt.phases.slice(0, payload.phases.length)));
}
assert.equal(previous.receipt, pointer.receipt);
assert.equal(previous.sha256, pointer.sha256);

const original = JSON.parse(fs.readFileSync(resolve(receipt.provenance.frozenBaselineReceipt)));
const normalize = (output, version) => {
  assert.equal(output.version, version);
  output.version = '<engine-version>';
  if (output.report !== undefined) {
    assert.equal(output.report.version, version);
    output.report.version = '<engine-version>';
  }
  return output;
};
let observations = 0, samples = 0, outputs = 0;
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const geomean = values => Math.exp(values.reduce((sum, value) => sum + Math.log(value), 0) / values.length);
for (const [rowPosition, row] of [...receipt.results, ...receipt.phases].entries()) {
  const position = rowPosition < 20 ? rowPosition : rowPosition - 20;
  const expectedName = rowPosition < 20 ? original.results[position].scenario : original.phases[position].scenario;
  assert.equal(row.scenario, expectedName);
  if (rowPosition >= 20) assert.equal(row.phase, original.phases[position].phase);
  assert.deepEqual(row.engineOrders, Array.from({ length: 3 }, (_, batch) =>
    (position + batch) % 2 ? ['current', 'baseline'] : ['baseline', 'current']));
  for (const engine of ['baseline', 'current']) {
    assert.equal(row.observations[engine].length, 3);
    for (const [batch, observation] of row.observations[engine].entries()) {
      const prefix = resolve(receipt.artifacts, `${row.scenario}-${row.phase}-${batch}-${engine}`);
      assert.deepEqual(JSON.parse(fs.readFileSync(prefix + '-stdout.json')), observation);
      assert.equal(observation.timesMs.length, 30);
      assert.ok(observation.timesMs.every(value => Number.isFinite(value) && value >= 0));
      assert.equal(observation.version, engine === 'baseline' ? '0.1.0' : receipt.version);
      assert.equal(observation.phase, row.phase);
      assert.equal(observation.medianMs, median(observation.timesMs));
      assert.equal(observation.p95Ms, [...observation.timesMs].sort((a, b) => a - b)[28]);
      observations++; samples += observation.timesMs.length;
      if (row.phase === 'full') {
        const bytes = fs.readFileSync(prefix + '-output.json');
        assert.equal(bytes.length, observation.fullOutput.outputBytes);
        assert.equal(hash(bytes), observation.fullOutput.outputSha256);
        assert.deepEqual(observation.fullOutput.ignoredFields,
          row.scenario.startsWith('reduction-') ? ['version', 'report.version'] : ['version']);
        const old = original.results.find(item => item.scenario === row.scenario);
        const expected = normalize(JSON.parse(gunzipSync(fs.readFileSync(resolve(old.fullOutput)))), '0.1.0');
        const actual = normalize(JSON.parse(bytes), engine === 'baseline' ? '0.1.0' : receipt.version);
        assert.ok(isDeepStrictEqual(actual, expected), `${row.scenario}/${batch}/${engine}`);
        assert.equal(hash(JSON.stringify(actual)), observation.fullOutput.versionNormalizedSha256);
        outputs++;
      }
    }
    const source = row.observations[engine];
    assert.deepEqual(row[engine], {
      medianMs: median(source.map(o => o.medianMs)),
      p95Ms: median(source.map(o => o.p95Ms)),
      coldModuleLoadMs: median(source.map(o => o.loadMs)),
      firstAnalysisMs: median(source.map(o => o.firstMs)),
      peakRssKiB: median(source.map(o => o.peakRssKiB)),
      outputBytes: source[0].fullOutput?.outputBytes ?? null,
    });
  }
  assert.equal(row.p95RegressionMs, row.current.p95Ms - row.baseline.p95Ms);
  assert.equal(row.allowedP95RegressionMs, Math.max(row.baseline.p95Ms * 0.1, 2));
  assert.equal(row.p95WithinAllowance, row.p95RegressionMs <= row.allowedP95RegressionMs);
  assert.equal(row.p95ReleaseGateApplicable, row.phase === 'full');
  assert.equal(row.speedup, row.baseline.medianMs / row.current.medianMs);
  assert.equal(row.peakMemoryRatio, row.current.peakRssKiB / row.baseline.peakRssKiB);
}
assert.equal(observations, 210);
assert.equal(samples, 6300);
assert.equal(outputs, 120);
const failedRows = receipt.results.filter(row => !row.p95WithinAllowance);
assert.deepEqual(receipt.releaseGate.failedScenarios, failedRows.map(row => row.scenario));
for (const [group, actual] of Object.entries(receipt.groups)) {
  const rows = receipt.results.filter(row => row.group === group);
  assert.ok(rows.length);
  assert.deepEqual(actual, {
    geometricMeanSpeedup: geomean(rows.map(row => row.speedup)),
    geometricMeanPeakMemoryRatio: geomean(rows.map(row => row.peakMemoryRatio)),
    allP95WithinAllowance: rows.every(row => row.p95WithinAllowance),
  });
}
const details = row => ({ scenario: row.scenario, baseline: row.baseline, current: row.current,
  p95RegressionMs: row.p95RegressionMs, allowedP95RegressionMs: row.allowedP95RegressionMs,
  speedup: row.speedup, peakMemoryRatio: row.peakMemoryRatio,
  batches: row.engineOrders.map((engineOrder, batch) => ({ batch, engineOrder,
    ...Object.fromEntries(['baseline', 'current'].map(engine => {
      const observation = row.observations[engine][batch];
      return [engine, { medianMs: observation.medianMs, p95Ms: observation.p95Ms,
        peakRssKiB: observation.peakRssKiB, loadMs: observation.loadMs,
        firstMs: observation.firstMs, timesMs: observation.timesMs }];
    })) })) });
const audit = { tool: 'MoonTxnWitness', check: 'Independent audit of 2026-10-21 common full-output formal samples and unchanged roadmap targets',
  verifiedAt: new Date().toISOString(), evidenceAuditPassed: true, measurementComplete: true,
  smokeOnly: false, correctnessPassed: true, formalReleaseGatePassed: receipt.formalReleaseGatePassed,
  regressionGatePassed: receipt.formalReleaseGatePassed,
  receipt: pointer.receipt, receiptSha256: pointer.sha256, latestPointerSha256: hash(pointerBytes),
  engineSourceSha256: expectedSourceHash, engineCoreSha256: expectedCoreHash,
  runnerSha256: hash(fs.readFileSync('scripts/performance-v010.mjs')),
  evidenceHelperSha256: hash(fs.readFileSync('scripts/performance-evidence.mjs')),
  auditScript: rel(fileURLToPath(import.meta.url)),
  auditScriptSha256: hash(fs.readFileSync(new URL(import.meta.url))),
  counts: { fullScenarios: 20, phaseScenarios: 15, workerProcesses: observations, timedSamples: samples,
    fullJsonOutputsIndependentlyCompared: outputs, immutableCheckpoints: files.length,
    stagingFiles: fs.readdirSync(directory).filter(name => name.endsWith('.pending')).length },
  semanticComparison: 'All complete JSON values match frozen public v0.1.0 reports; only root version and shrink report.version are normalized',
  persistence: { recoverySource: recovered.source, validPointer: true, allSnapshotPayloadDigestsVerified: true,
    allSnapshotLinksVerified: true, onlyFinalCheckpointComplete: true, finalCheckpointSequence: pointer.checkpointSequence,
    pointerComplete: pointer.complete, pointerSmokeOnly: pointer.smokeOnly,
    pointerCorrectnessPassed: pointer.correctnessPassed, pointerFormalReleaseGatePassed: pointer.formalReleaseGatePassed },
  groups: receipt.groups, failedP95Scenarios: failedRows.map(details),
  search12: details(receipt.results.find(row => row.scenario === 'completion-impossible-12')),
  reduction512: details(receipt.results.find(row => row.scenario === 'reduction-512')),
  phaseP95Deltas: receipt.phases.map(row => ({ scenario: row.scenario, phase: row.phase,
    baselineP95Ms: row.baseline.p95Ms, currentP95Ms: row.current.p95Ms, deltaMs: row.p95RegressionMs })),
  interpretation: { rootCauseEstablished: false, gateUnchanged: true, allBatchesRetained: true,
    repeatMeasurementAttempted: false,
    telemetryLimit: 'No per-sample GC/CPU/heap or host-frequency telemetry in this formal protocol; tail timings and process maxRSS alone cannot establish causal explanations.' } };
const work=resolve(root,receipt.artifacts);
assert.equal(hash(fs.readFileSync(resolve(work,'baseline.mjs'))),'6c76b3be6c45ff633232568b3ffed3c1393ade3b4d012ee5c21c49cbb8dcf97b');
assert.equal(hash(fs.readFileSync(resolve(work,'current.mjs'))),expectedCoreHash);
assert.equal(fs.readdirSync(work).filter(n=>n.endsWith('-stdout.json')).length,210);
assert.equal(fs.readdirSync(work).filter(n=>n.endsWith('-output.json')).length,120);
assert.equal(fs.readdirSync(work).filter(n=>n.endsWith('-stderr.txt')).length,0);
const metrics=receipt.groups;
audit.roadmapTargets={source:'docs/roadmap-v0.2.0.md',sourceSha256:hash(fs.readFileSync('docs/roadmap-v0.2.0.md')),comparison:'Fixed v0.1.0 common full-output workloads only; new models, classification and collection costs are not measured here',
 graphSpeed:{requiredMinimum:1.3,observed:metrics.graph.geometricMeanSpeedup,passed:metrics.graph.geometricMeanSpeedup>=1.3},
 graphPeakRss:{requiredMaximum:.8,observed:metrics.graph.geometricMeanPeakMemoryRatio,passed:metrics.graph.geometricMeanPeakMemoryRatio<=.8},
 largeSearchSpeed:{requiredMinimum:1.5,observed:metrics['search-large'].geometricMeanSpeedup,passed:metrics['search-large'].geometricMeanSpeedup>=1.5},
 largeReductionSpeed:{requiredMinimum:1.5,observed:metrics['reduction-large'].geometricMeanSpeedup,passed:metrics['reduction-large'].geometricMeanSpeedup>=1.5}};
audit.roadmapAllOptimizationTargetsPassed=['graphSpeed','graphPeakRss','largeSearchSpeed','largeReductionSpeed'].every(k=>audit.roadmapTargets[k].passed);
audit.finalOptimizationGatePassed=audit.regressionGatePassed&&audit.roadmapAllOptimizationTargetsPassed;
audit.roadmapTargets.graphPeakRss.observedPercentReduction=100*(1-metrics.graph.geometricMeanPeakMemoryRatio);
audit.all20FullP95Rows=receipt.results.map(details);
const rawBindings=fs.readdirSync(work).filter(n=>n==='baseline.mjs'||n==='current.mjs'||n.endsWith('-stdout.json')||n.endsWith('-output.json')).sort().map(n=>{const p=resolve(work,n),b=fs.readFileSync(p);return{file:rel(p),bytes:b.length,sha256:hash(b)};});
const bindingFile=resolve(dirname(resolve(auditFile)),'raw-file-bindings.json');
fs.writeFileSync(bindingFile,JSON.stringify(rawBindings,null,2)+'\n',{flag:'wx'});
audit.rawFileBindings={file:rel(bindingFile),count:rawBindings.length,sha256:hash(fs.readFileSync(bindingFile))};
fs.writeFileSync(resolve(auditFile), JSON.stringify(audit, null, 2) + '\n', { flag: 'wx' });
assert.deepEqual(fs.readFileSync(latestPath), pointerBytes, 'Audit must not modify latest');
console.log(JSON.stringify({ audit: auditFile, auditSha256: hash(fs.readFileSync(resolve(auditFile))),
  counts: audit.counts, persistence: audit.persistence, groups: audit.groups,
  failedP95Scenarios: audit.failedP95Scenarios, search12Summary: { baseline: audit.search12.baseline,
    current: audit.search12.current, speedup: audit.search12.speedup, p95RegressionMs: audit.search12.p95RegressionMs },
  reduction512Summary: { baseline: audit.reduction512.baseline, current: audit.reduction512.current, speedup: audit.reduction512.speedup, p95RegressionMs: audit.reduction512.p95RegressionMs },
  phaseP95Deltas: audit.phaseP95Deltas,roadmapTargets:audit.roadmapTargets,finalOptimizationGatePassed:audit.finalOptimizationGatePassed }, null, 2));

} catch(error) {
 const failure={evidenceAuditPassed:false,complete:false,receipt:receiptPath,expectedReceiptHash,errorClass:error.name,error:String(error.message).replaceAll(root,'<workspace>'),auditScriptSha256:hash(fs.readFileSync(new URL(import.meta.url)))};
 fs.writeFileSync(resolve(auditFile),JSON.stringify(failure,null,2)+'\n',{flag:'wx'});
 console.error(JSON.stringify(failure));process.exitCode=1;
}
