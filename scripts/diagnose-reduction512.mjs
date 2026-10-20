// Freeze first, then run exactly six symmetric diagnostic workers. Not a gate.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cpus, arch, platform, release } from 'node:os';
import { spawnSync } from 'node:child_process';
import { writeImmutableEvidence } from './performance-evidence.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const rel = path => relative(root, path).split('\\').join('/');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const load = path => JSON.parse(readFileSync(path));
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const currentSource = '4b8ec7fc3b325473b695f11ab318f27491b68499f15a8cd7b897647cb2ff2ef3';
const currentCore = '8f221e9935b867ebc797f8dce8285adfc3c00f9a5c0fbd1e4d1f8b60f3662af6';
const baselineCore = '6c76b3be6c45ff633232568b3ffed3c1393ade3b4d012ee5c21c49cbb8dcf97b';
const pinnedCommit = '3d94d41920dd991bfa0a49fccb01b8076b371958';

function prepare() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const stem = `reduction512-diagnostic-${stamp}`;
  const work = resolve(root, 'artifacts', stem);
  mkdirSync(work, { recursive: false });
  const manifest = load(resolve(root, 'dist/build-manifest.json'));
  assert.equal(manifest.sourceSha256, currentSource);
  assert.equal(manifest.coreSha256, currentCore);
  assert.equal(digest(readFileSync(resolve(root, 'dist/core.mjs'))), currentCore);
  const ci = load(resolve(root, 'verification/releases/0.1.1/independent-ci-3d94d41.json'));
  assert.equal(ci.sourceCommit, pinnedCommit);
  assert.equal(ci.sourceAudit.computedMoonBitSourceSha256, currentSource);
  const frozen = load(resolve(root, 'verification/baselines/0.1.0/manifest.json'));
  assert.equal(frozen.engine.coreSha256, baselineCore);
  const original = load(resolve(root, frozen.latestFormalReceipt));
  assert.ok(original.passed && original.formalBaselineEstablished);
  copyFileSync(resolve(root, original.artifacts, 'core.mjs'), resolve(work, 'baseline.mjs'));
  copyFileSync(resolve(root, 'dist/core.mjs'), resolve(work, 'current.mjs'));
  copyFileSync(resolve(root, 'scripts/diagnose-analysis.mjs'), resolve(work, 'diagnose-worker.mjs'));
  assert.equal(digest(readFileSync(resolve(work, 'baseline.mjs'))), baselineCore);
  const fixtureManifestBytes = readFileSync(resolve(root, 'verification/fixtures/v010-comparison/manifest.json'));
  assert.equal(digest(fixtureManifestBytes), frozen.fixtureManifestSha256);
  const fixtures = JSON.parse(fixtureManifestBytes);
  const fixture = fixtures.cases.find(row => row.name === 'reduction-512');
  assert.equal(digest(readFileSync(resolve(root, fixture.file))), fixture.fixtureSha256);
  const priorPath = 'verification/releases/0.1.1/performance-v010-formal-2026-10-20T12-47-56-435Z.checkpoints/000038-5334bf6a-e1ce-433e-9fa5-c302f0fcfbdd.json';
  const priorBytes = readFileSync(resolve(root, priorPath)), prior = JSON.parse(priorBytes);
  assert.equal(digest(priorBytes), 'bda7cfab146cbc88e5044ba57076d7ea95e2dc85e1ca8fe5470623f4677fa6c6');
  assert.ok(prior.complete && prior.correctnessPassed && !prior.formalReleaseGatePassed);
  assert.equal(prior.provenance.currentBuildManifest.coreSha256, currentCore);
  const priorRow = prior.results.find(row => row.scenario === 'reduction-512');
  assert.equal(priorRow.inputSha256, fixture.historySha256);
  const protocol = { schema: 1, diagnosticOnly: true, formalReleaseGateApplicable: false,
    frozenAt: new Date().toISOString(), runId: stem, work: rel(work),
    sourceCommit: pinnedCommit, sourceSha256: currentSource,
    engineSnapshots: { baseline: { version: '0.1.0', core: rel(resolve(work, 'baseline.mjs')), sha256: baselineCore },
      current: { version: '0.1.1', core: rel(resolve(work, 'current.mjs')), sha256: currentCore } },
    baselineProvenance: frozen.engine, fixture,
    worker: { file: rel(resolve(work, 'diagnose-worker.mjs')),
      sha256: digest(readFileSync(resolve(work, 'diagnose-worker.mjs'))), derivedFrom: 'scripts/diagnose-analysis.mjs',
      modified: false },
    orchestrator: { file: 'scripts/diagnose-reduction512.mjs', sha256: digest(readFileSync(new URL(import.meta.url))) },
    protocol: { independentBatches: 3, warmups: 5, samplesPerBatch: 30,
      operation: 'JSON.parse(core.shrink_options_json(frozenHistoryText, "{}")); full output retained during each operation',
      profilerSamplingIntervalUs: 1000, gcObserver: true, forcedGc: false,
      perSample: ['wall time', 'user/system CPU', 'heap before/after', 'GC overlap'],
      batchEngineOrders: [['current', 'baseline'], ['baseline', 'current'], ['current', 'baseline']],
      p50Definition: 'Existing diagnostic worker nearest-rank P50 (30 samples index 14); distinct from formal worker index 15',
      aggregate: 'Median of three worker statistics; GC overlap/time also pooled descriptively',
      instrumentation: 'Both engines run the identical copied diagnostic worker and Node executable',
      cpuWindow: 'Profiler includes warmups and measured operations; timings/GC summaries select 30 measured samples',
      rssCaveat: 'Diagnostic maxRSS includes profiler/observer, unlike the formal gate RSS point',
      semanticAgreement: { basis: 'Prior complete formal run independently validated these exact fixture/core snapshots against frozen full output',
        receipt: priorPath, receiptSha256: digest(priorBytes), currentAndBaselineOutputBytes: priorRow.current.outputBytes,
        diagnosticWorkerChecks: 'Final output status equals fixture status; output byte count must agree with prior formal output' },
      retries: 'No workload/process retries. A failed worker terminates this diagnostic and preserves the failure.' },
    environment: { node: process.version, nodeExecutableSha256: digest(readFileSync(process.execPath)),
      os: platform(), release: release(), arch: arch(), cpu: cpus()[0]?.model, logicalCpus: cpus().length },
    privacy: 'Raw CPU profiles and unredacted worker records remain ignored artifacts; public summaries omit absolute profile paths',
    bounds: 'Only reduction-512. No database, compilation, forced GC, cache eviction, or formal gate run.' };
  const path = resolve(root, 'verification/releases/0.1.1', `${stem}-protocol.json`);
  const saved = writeImmutableEvidence(path, json(protocol));
  console.log(json({ prepared: true, protocol: rel(path), sha256: saved.sha256, work: rel(work) }));
}

function run(protocolPath) {
  const protocolBytes = readFileSync(protocolPath), protocol = JSON.parse(protocolBytes);
  assert.equal(protocol.orchestrator.sha256, digest(readFileSync(new URL(import.meta.url))));
  assert.equal(protocol.sourceCommit, pinnedCommit);
  assert.equal(process.version, protocol.environment.node);
  assert.equal(digest(readFileSync(process.execPath)), protocol.environment.nodeExecutableSha256);
  const work = resolve(root, protocol.work), observations = { baseline: [], current: [] };
  const receiptPath = resolve(root, 'verification/releases/0.1.1', `${protocol.runId}-result.json`);
  let activeWorker = null;
  try {
    assert.equal(digest(readFileSync(resolve(root, protocol.worker.file))), protocol.worker.sha256);
    assert.equal(digest(readFileSync(resolve(root, protocol.fixture.file))), protocol.fixture.fixtureSha256);
    for (const [batch, order] of protocol.protocol.batchEngineOrders.entries()) {
      for (const engine of order) {
        const snapshot = protocol.engineSnapshots[engine];
        assert.equal(digest(readFileSync(resolve(root, snapshot.core))), snapshot.sha256);
        const output = resolve(work, `${engine}-${batch}.json`);
        activeWorker = { engine, batch, output: rel(output) };
        const child = spawnSync(process.execPath, [resolve(root, protocol.worker.file),
          resolve(root, snapshot.core), resolve(root, protocol.fixture.file), output],
        { cwd: root, windowsHide: true, encoding: 'utf8', timeout: 60000 });
        writeImmutableEvidence(resolve(work, `${engine}-${batch}-stdout.txt`), child.stdout || '');
        if (child.stderr) writeImmutableEvidence(resolve(work, `${engine}-${batch}-stderr.txt`), child.stderr);
        assert.ifError(child.error);
        assert.equal(child.status, 0, 'Diagnostic worker failed; private stderr retained in ignored artifacts');
        const bytes = readFileSync(output), observation = JSON.parse(bytes);
        assert.equal(observation.coreSha256, snapshot.sha256);
        assert.equal(observation.fixtureSha256, protocol.fixture.fixtureSha256);
        assert.equal(observation.scriptSha256, protocol.worker.sha256);
        assert.equal(observation.version, snapshot.version);
        assert.equal(observation.rows.filter(row => row.warmup).length, 5);
        assert.equal(observation.rows.filter(row => !row.warmup).length, 30);
        assert.equal(observation.outputBytes, protocol.protocol.semanticAgreement.currentAndBaselineOutputBytes);
        const profilePath = output + '.cpuprofile', profileBytes = readFileSync(profilePath);
        const { rawCpuProfile, ...publicObservation } = observation;
        observations[engine].push({ batch, engineOrder: order, ...publicObservation,
          rawObservation: rel(output), rawObservationSha256: digest(bytes),
          rawProfile: rel(profilePath), rawProfileSha256: digest(profileBytes) });
        console.log(json({ engine, batch, medianMs: observation.medianMs, p95Ms: observation.p95Ms,
          gcOverlapMs: observation.sampledGcOverlapMs,
          gcFraction: observation.sampledGcOverlapMs / observation.sampledTotalMs }));
      }
    }
    const aggregate = engine => {
      const rows = observations[engine];
      const gcMs = rows.reduce((sum, row) => sum + row.sampledGcOverlapMs, 0);
      const wallMs = rows.reduce((sum, row) => sum + row.sampledTotalMs, 0);
      return { medianMs: median(rows.map(row => row.medianMs)), p95Ms: median(rows.map(row => row.p95Ms)),
        peakRssKiB: median(rows.map(row => row.peakRssKiB)), sampledGcOverlapMs: gcMs,
        sampledTotalMs: wallMs, gcFraction: gcMs / wallMs };
    };
    const result = { schema: 1, passed: true, complete: true, diagnosticOnly: true,
      formalReleaseGateApplicable: false, formalReleaseGatePassed: false,
      generatedAt: new Date().toISOString(), protocol: rel(resolve(protocolPath)), protocolSha256: digest(protocolBytes),
      sourceCommit: pinnedCommit, sourceSha256: currentSource, coreSha256: currentCore,
      workerProcesses: 6, timedSamples: 180, warmupOperations: 30, observations,
      aggregate: { baseline: aggregate('baseline'), current: aggregate('current') },
      interpretation: 'Instrumented diagnostic only; no acceptance threshold or improvement claim. CPU self time includes warmups. Raw profile URLs stay private.' };
    const saved = writeImmutableEvidence(receiptPath, json(result));
    console.log(json({ complete: true, diagnosticOnly: true, result: rel(receiptPath), sha256: saved.sha256,
      aggregate: result.aggregate, workerProcesses: 6, timedSamples: 180 }));
  } catch (error) {
    writeImmutableEvidence(resolve(work, 'private-original-error.json'), json({ message: error.message, stack: error.stack }));
    const failure = { complete: false, passed: false, diagnosticOnly: true, formalReleaseGateApplicable: false,
      failedAt: new Date().toISOString(), protocol: rel(resolve(protocolPath)), protocolSha256: digest(protocolBytes),
      activeWorker, completedObservations: observations, error: { name: error.name, code: error.code || null },
      privateError: rel(resolve(work, 'private-original-error.json')) };
    writeImmutableEvidence(receiptPath.replace('-result.json', '-failure.json'), json(failure));
    console.error(json({ failed: true, diagnosticOnly: true, activeWorker,
      error: failure.error, observationsRetained: observations.baseline.length + observations.current.length }));
    process.exitCode = 1;
  }
}

if (process.argv[2] === '--prepare' && process.argv.length === 3) prepare();
else if (process.argv[2] === '--run' && process.argv.length === 4) run(resolve(process.argv[3]));
else throw Error('Usage: node scripts/diagnose-reduction512.mjs --prepare | --run FROZEN_PROTOCOL.json');
