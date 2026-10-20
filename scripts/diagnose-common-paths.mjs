// Symmetric CPU/GC evidence for two fixed common-analysis workloads. Not a gate.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cpus, platform, release, arch } from 'node:os';
import { spawnSync } from 'node:child_process';
import { writeImmutableEvidence } from './performance-evidence.mjs';
import { sourceFingerprint } from './build-fingerprint.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const rel = path => relative(root, path).split('\\').join('/');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const read = path => JSON.parse(readFileSync(path));
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const fixed = { commit: 'f76aebfa3fabcc05d5605395c63356198e9b25fc',
  source: '4f1a51358ac60eb6cb2d34443556ab67a79ee6482038590fa7390800a8029fba',
  current: 'f2a0b6d1a07152aa599ce9e799e9b2a7b993b5bf87a73faada8705a1735c2d91',
  baseline: '6c76b3be6c45ff633232568b3ffed3c1393ade3b4d012ee5c21c49cbb8dcf97b' };

function prepare() {
  const build = read(resolve(root, 'dist/build-manifest.json'));
  assert.equal(build.sourceSha256, fixed.source);
  assert.equal(sourceFingerprint(root), fixed.source);
  assert.equal(build.coreSha256, fixed.current);
  assert.equal(sha(readFileSync(resolve(root, 'dist/core.mjs'))), fixed.current);
  const git = spawnSync('git', ['rev-parse', fixed.commit + '^{commit}'], { cwd: root, encoding: 'utf8', windowsHide: true });
  assert.equal(git.status, 0); assert.equal(git.stdout.trim(), fixed.commit);
  const stem = `common-paths-diagnostic-${new Date().toISOString().replace(/[:.]/g, '-')}`;
  const work = resolve(root, 'artifacts', stem); mkdirSync(work, { recursive: false });
  const frozen = read(resolve(root, 'verification/baselines/0.1.0/manifest.json'));
  const old = read(resolve(root, frozen.latestFormalReceipt));
  assert.ok(old.passed && old.formalBaselineEstablished);
  copyFileSync(resolve(root, old.artifacts, 'core.mjs'), resolve(work, 'baseline.mjs'));
  copyFileSync(resolve(root, 'dist/core.mjs'), resolve(work, 'current.mjs'));
  copyFileSync(resolve(root, 'scripts/diagnose-analysis.mjs'), resolve(work, 'worker.mjs'));
  assert.equal(sha(readFileSync(resolve(work, 'baseline.mjs'))), fixed.baseline);
  const priorPath = 'verification/releases/0.1.1/performance-v010-formal-2026-10-20T14-24-26-065Z.checkpoints/000038-bea0407f-971d-4c9d-9b22-373de549c1e7.json';
  const priorBytes = readFileSync(resolve(root, priorPath)), prior = JSON.parse(priorBytes);
  assert.equal(sha(priorBytes), 'aa1a332152ff0e329376a059c56beb1fee983081faa424f968e070fb51227de4');
  assert.ok(prior.complete && prior.correctnessPassed && !prior.formalReleaseGatePassed);
  assert.equal(prior.provenance.currentBuildManifest.sourceSha256, fixed.source);
  assert.equal(prior.provenance.currentBuildManifest.coreSha256, fixed.current);
  const fixtureManifestBytes = readFileSync(resolve(root, 'verification/fixtures/v010-comparison/manifest.json'));
  assert.equal(sha(fixtureManifestBytes), frozen.fixtureManifestSha256);
  const fixtures = JSON.parse(fixtureManifestBytes).cases;
  const scenarios = ['sparse-512', 'small-cycle-noise-64'].map(name => {
    const fixture = fixtures.find(row => row.name === name);
    assert.equal(sha(readFileSync(resolve(root, fixture.file))), fixture.fixtureSha256);
    const row = prior.results.find(result => result.scenario === name);
    assert.equal(row.inputSha256, fixture.historySha256);
    assert.equal(row.baseline.outputBytes, row.current.outputBytes);
    return { ...fixture, engineOrders: row.engineOrders, outputBytes: row.current.outputBytes };
  });
  const protocol = { schema: 1, diagnosticOnly: true, formalReleaseGateApplicable: false,
    frozenAt: new Date().toISOString(), runId: stem, work: rel(work), fixed,
    engines: { baseline: { version: '0.1.0', file: rel(resolve(work, 'baseline.mjs')), sha256: fixed.baseline },
      current: { version: '0.1.1', file: rel(resolve(work, 'current.mjs')), sha256: fixed.current } },
    worker: { file: rel(resolve(work, 'worker.mjs')), source: 'scripts/diagnose-analysis.mjs', modified: false,
      sha256: sha(readFileSync(resolve(work, 'worker.mjs'))) },
    orchestrator: { file: 'scripts/diagnose-common-paths.mjs', sha256: sha(readFileSync(new URL(import.meta.url))) },
    scenarios, protocol: { independentBatchesPerScenario: 3, warmups: 5, timedSamplesPerWorker: 30,
      totalWorkers: 12, timedSamples: 360, profilerSamplingIntervalUs: 1000, gcObserver: true, forcedGc: false,
      operation: 'JSON.parse(core.analyze_options_json(frozenHistoryText,"{}")); complete output on both sides',
      selectedMetrics: ['wall time', 'user/system CPU', 'heap before/after', 'observed GC overlap', 'CPU profile'],
      p50Definition: 'Existing diagnostic nearest-rank P50, not formal median index15',
      aggregation: 'Median of corresponding three worker statistics; pooled GC overlap/time is descriptive only',
      profileWindow: 'Includes five warmups and thirty samples plus instrumentation; maxRSS includes diagnostic overhead',
      retries: 'No workload/process retries; first failed worker ends the diagnostic with partial evidence',
      semanticBasis: { completeSameCoreFormalReceipt: priorPath, receiptSha256: sha(priorBytes),
        checksHere: 'Worker final status and byte count; full semantic agreement was independently verified in the prior identical-core/input formal audit' } },
    environment: { node: process.version, nodeExecutableSha256: sha(readFileSync(process.execPath)),
      os: platform(), release: release(), arch: arch(), cpu: cpus()[0]?.model, logicalCpus: cpus().length },
    privacy: 'CPU callFrame URLs and raw worker output absolute paths remain ignored artifacts. Public records contain relative references/digests.',
    scope: 'Only two predetermined workloads; no database, compilation, formal gate or forced GC.' };
  const path = resolve(root, 'verification/releases/0.1.1', `${stem}-protocol.json`);
  const stored = writeImmutableEvidence(path, json(protocol));
  console.log(json({ prepared: true, protocol: rel(path), sha256: stored.sha256, work: rel(work), workers: 12 }));
}

function run(protocolPath) {
  const protocolBytes = readFileSync(protocolPath), protocol = JSON.parse(protocolBytes);
  assert.equal(protocol.orchestrator.sha256, sha(readFileSync(new URL(import.meta.url))));
  assert.deepEqual(protocol.fixed, fixed);
  assert.equal(process.version, protocol.environment.node);
  assert.equal(sha(readFileSync(process.execPath)), protocol.environment.nodeExecutableSha256);
  assert.equal(sha(readFileSync(resolve(root, protocol.worker.file))), protocol.worker.sha256);
  const work = resolve(root, protocol.work), results = [], startedAt = new Date().toISOString();
  let activeWorker;
  try {
    for (const scenario of protocol.scenarios) {
      assert.equal(sha(readFileSync(resolve(root, scenario.file))), scenario.fixtureSha256);
      const observations = { baseline: [], current: [] };
      results.push({ scenario: scenario.name, observations });
      for (const [batch, order] of scenario.engineOrders.entries()) for (const engine of order) {
        const snapshot = protocol.engines[engine];
        assert.equal(sha(readFileSync(resolve(root, snapshot.file))), snapshot.sha256);
        const prefix = `${scenario.name}-${batch}-${engine}`, path = resolve(work, prefix + '.json');
        activeWorker = { scenario: scenario.name, batch, engine };
        const child = spawnSync(process.execPath, [resolve(root, protocol.worker.file),
          resolve(root, snapshot.file), resolve(root, scenario.file), path],
        { cwd: root, encoding: 'utf8', windowsHide: true, timeout: 60000 });
        writeImmutableEvidence(resolve(work, prefix + '-stdout.txt'), child.stdout || '');
        if (child.stderr) writeImmutableEvidence(resolve(work, prefix + '-stderr.txt'), child.stderr);
        assert.ifError(child.error);
        assert.equal(child.status, 0, 'Worker failed; private diagnostics retained in ignored artifacts');
        const bytes = readFileSync(path), observation = JSON.parse(bytes);
        assert.equal(observation.version, snapshot.version);
        assert.equal(observation.coreSha256, snapshot.sha256);
        assert.equal(observation.scriptSha256, protocol.worker.sha256);
        assert.equal(observation.fixtureSha256, scenario.fixtureSha256);
        assert.equal(observation.outputBytes, scenario.outputBytes);
        assert.equal(observation.rows.filter(row => row.warmup).length, 5);
        assert.equal(observation.rows.filter(row => !row.warmup).length, 30);
        const { rawCpuProfile, ...publicRecord } = observation;
        observations[engine].push({ batch, engineOrder: order, ...publicRecord,
          rawObservation: rel(path), rawObservationSha256: sha(bytes),
          rawProfile: rel(path + '.cpuprofile'), rawProfileSha256: sha(readFileSync(path + '.cpuprofile')) });
        console.log(json({ ...activeWorker, medianMs: observation.medianMs, p95Ms: observation.p95Ms,
          gcFraction: observation.sampledGcOverlapMs / observation.sampledTotalMs }));
      }
      const aggregate = engine => {
        const rows = observations[engine], gc = rows.reduce((sum, row) => sum + row.sampledGcOverlapMs, 0);
        const wall = rows.reduce((sum, row) => sum + row.sampledTotalMs, 0);
        return { medianMs: median(rows.map(row => row.medianMs)), p95Ms: median(rows.map(row => row.p95Ms)),
          peakRssKiB: median(rows.map(row => row.peakRssKiB)), gcOverlapMs: gc, sampleWallMs: wall, gcFraction: gc / wall };
      };
      results.at(-1).aggregate = { baseline: aggregate('baseline'), current: aggregate('current') };
    }
    const result = { schema: 1, diagnosticOnly: true, formalReleaseGateApplicable: false,
      formalReleaseGatePassed: false, complete: true, passed: true, startedAt, completedAt: new Date().toISOString(),
      protocol: rel(protocolPath), protocolSha256: sha(protocolBytes), fixed,
      workerProcesses: 12, timedSamples: 360, results,
      interpretation: 'Instrumented diagnostic only. No previous formal result is superseded or explained solely by these measurements.' };
    const path = resolve(root, 'verification/releases/0.1.1', `${protocol.runId}-result.json`);
    const stored = writeImmutableEvidence(path, json(result));
    console.log(json({ complete: true, diagnosticOnly: true, result: rel(path), sha256: stored.sha256,
      summaries: results.map(row => ({ scenario: row.scenario, aggregate: row.aggregate })) }));
  } catch (error) {
    writeImmutableEvidence(resolve(work, 'private-original-error.json'), json({ message: error.message, stack: error.stack }));
    const failure = { complete: false, passed: false, diagnosticOnly: true, formalReleaseGateApplicable: false,
      startedAt, failedAt: new Date().toISOString(), protocol: rel(protocolPath), protocolSha256: sha(protocolBytes),
      activeWorker, partialResults: results, error: { name: error.name, code: error.code || null },
      privateError: rel(resolve(work, 'private-original-error.json')) };
    writeImmutableEvidence(resolve(root, 'verification/releases/0.1.1', `${protocol.runId}-failure.json`), json(failure));
    console.error(json({ failed: true, activeWorker, error: failure.error })); process.exitCode = 1;
  }
}

if (process.argv[2] === '--prepare' && process.argv.length === 3) prepare();
else if (process.argv[2] === '--run' && process.argv.length === 4) run(resolve(process.argv[3]));
else throw Error('Usage: node scripts/diagnose-common-paths.mjs --prepare | --run FROZEN_PROTOCOL.json');
