// Direct current-build/v0.1.0 regression check. Run only when the machine is idle:
// node scripts/performance-v010.mjs [--quick]
// --quick is semantic smoke only. Formal: 5 warmups, 30 samples, 3 alternating
// independent process batches. Full-output comparison ignores only the engine
// version at the report root and, for shrink, at report.version.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { cpus, platform, release, arch } from 'node:os';
import { spawn, spawnSync } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { gunzipSync } from 'node:zlib';
import { isDeepStrictEqual } from 'node:util';
import { sourceFingerprint } from './build-fingerprint.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const frozen = resolve(root, 'verification/baselines/0.1.0');
const fixtureRoot = resolve(root, 'verification/fixtures/v010-comparison');
const publicUrl = 'https://github.com/HhWw96/moontxnwitness/releases/download/v0.1.0/MoonTxnWitness-v0.1.0-portable.zip';
const archiveSha = 'd7495482b8267f327edf40e95111acbd2502290fc97e5f1e5e1203e7bc59488c';
const coreSha = '6c76b3be6c45ff633232568b3ffed3c1393ade3b4d012ee5c21c49cbb8dcf97b';
const sourceSha = 'dcc8653278a9f98dc6056d23c8b7d7d9db3fc6b8406b22987fc9ff03997dd830';
const hash = value => createHash('sha256').update(value).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const rel = path => relative(root, path).split('\\').join('/');
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const geomean = values => Math.exp(values.reduce((sum, value) => sum + Math.log(value), 0) / values.length);

function normalizeEngineVersion(output, expectedVersion) {
  assert.equal(output.version, expectedVersion, 'Unexpected engine version at output root');
  output.version = '<engine-version>';
  if (output.report !== undefined) {
    assert.equal(output.report.version, expectedVersion, 'Unexpected engine version at shrink report root');
    output.report.version = '<engine-version>';
  }
  return output;
}

async function worker() {
  const [corePath, fixturePath, phase, warmups, samples, version, frozenOutputPath, outputPath] = process.argv.slice(3);
  const loaded = performance.now();
  const core = await import(pathToFileURL(corePath).href);
  const loadMs = performance.now() - loaded;
  assert.equal(core.version(), version, 'Copied engine does not match the requested version');
  const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'));
  const text = JSON.stringify(fixture.history);
  let run;
  if (phase === 'full') run = () => JSON.parse(fixture.operation === 'shrink'
    ? core.shrink_options_json(text, '{}') : core.analyze_options_json(text, '{}'));
  else {
    const history = core.benchmark_parse_balanced(text);
    const result = core.benchmark_infer(history);
    const phases = {
      parse: () => core.benchmark_parse_balanced(text),
      inference: () => core.benchmark_infer(history),
      cycle: () => core.benchmark_cycle(history, result),
      search: () => core.benchmark_search_balanced(history, result),
      reduction: () => core.benchmark_reduce_balanced(history),
      render: () => core.benchmark_render(result),
    };
    run = phases[phase];
    assert.ok(run, 'Unknown benchmark phase');
  }
  const first = performance.now();
  let output = run();
  const firstMs = performance.now() - first;
  for (let i = 0; i < Number(warmups); i++) run();
  const timesMs = [];
  for (let i = 0; i < Number(samples); i++) {
    const started = performance.now();
    output = run();
    timesMs.push(performance.now() - started);
  }
  // Frozen-output decompression, comparison, hashing and artifact writes are
  // deliberately outside the measured operation and its process RSS snapshot.
  const peakRssKiB = process.resourceUsage().maxRSS;
  let fullOutput = null;
  if (phase === 'full') {
    assert.equal(output.status, fixture.status, fixture.name);
    const report = output.report || output;
    if (fixture.cycle) assert.equal(report.witness.edges.length, fixture.cycle);
    if (fixture.operation === 'shrink') {
      assert.equal(output.oneMinimal, true);
      assert.equal(output.reducedHistory.transactions.length, 2);
    }
    const encoded = Buffer.from(JSON.stringify(output));
    const expectedBytes = gunzipSync(readFileSync(frozenOutputPath));
    const expected = JSON.parse(expectedBytes);
    const actualNormalized = normalizeEngineVersion(output, version);
    const expectedNormalized = normalizeEngineVersion(expected, '0.1.0');
    if (!isDeepStrictEqual(actualNormalized, expectedNormalized)) {
      throw Error(`Full report disagreement for ${fixture.name}; only root version and shrink report.version may differ`);
    }
    writeFileSync(outputPath, encoded);
    fullOutput = { outputBytes: encoded.length, outputSha256: hash(encoded),
      versionNormalizedSha256: hash(JSON.stringify(actualNormalized)),
      frozenOutputSha256: hash(expectedBytes), semanticAgreement: true,
      ignoredFields: fixture.operation === 'shrink' ? ['version', 'report.version'] : ['version'] };
  }
  const sorted = [...timesMs].sort((a, b) => a - b);
  console.log(JSON.stringify({ version: core.version(), profile: 'balanced', phase,
    loadMs, firstMs, timesMs, medianMs: median(timesMs),
    p95Ms: sorted[Math.ceil(sorted.length * .95) - 1], peakRssKiB, fullOutput }));
}

function prepareBaseline(work, frozenManifest, originalReceipt) {
  assert.equal(frozenManifest.engine.coreSha256, coreSha);
  assert.equal(frozenManifest.engine.archiveSha256, archiveSha);
  assert.equal(frozenManifest.engine.sourceSha256, sourceSha);
  const retainedCore = resolve(root, originalReceipt.artifacts, 'core.mjs');
  const destination = resolve(work, 'baseline.mjs');
  if (existsSync(retainedCore)) {
    assert.equal(hash(readFileSync(retainedCore)), coreSha, 'Retained public baseline bytes changed');
    copyFileSync(retainedCore, destination);
    return { transport: 'verified-core-retained-from-frozen-baseline', publicUrl, archiveSha256: archiveSha,
      coreSha256: coreSha, sourceSha256: sourceSha, publishedBuildManifest: frozenManifest.engine.publishedBuildManifest };
  }
  const code = String.raw`
import hashlib,json,sys,urllib.request,zipfile
from pathlib import Path
url,archive_sha,core_sha,source_sha,work,local=sys.argv[1:]
work=Path(work)
if Path(local).exists():
    packed=Path(local).read_bytes(); transport='verified-local-copy-of-pinned-public-archive'
else:
    request=urllib.request.Request(url,headers={'User-Agent':'MoonTxnWitness-v010-regression'})
    with urllib.request.urlopen(request,timeout=60) as response:
        assert response.status==200
        packed=response.read(16*1024*1024+1)
    transport='anonymous-public-download'
assert len(packed)<=16*1024*1024 and hashlib.sha256(packed).hexdigest()==archive_sha
archive=work/'baseline-portable.zip'; archive.write_bytes(packed)
with zipfile.ZipFile(archive) as z:
    core=z.read('MoonTxnWitness-v0.1.0/dist/core.mjs')
    manifest=json.loads(z.read('MoonTxnWitness-v0.1.0/dist/build-manifest.json'))
assert hashlib.sha256(core).hexdigest()==core_sha
assert manifest['version']=='0.1.0' and manifest['coreSha256']==core_sha and manifest['sourceSha256']==source_sha
(work/'baseline.mjs').write_bytes(core)
print(json.dumps({'transport':transport,'manifest':manifest}))
`;
  const prepared = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
    ['-c', code, publicUrl, archiveSha, coreSha, sourceSha, work,
      resolve(root, 'artifacts/MoonTxnWitness-v0.1.0-portable.zip')],
    { cwd: root, encoding: 'utf8', windowsHide: true, timeout: 120000 });
  assert.ifError(prepared.error);
  assert.equal(prepared.status, 0, `Cannot prepare pinned public baseline: ${(prepared.stderr || '').slice(-2000)}`);
  const metadata = JSON.parse(prepared.stdout);
  return { transport: metadata.transport, publicUrl, archiveSha256: archiveSha,
    coreSha256: coreSha, sourceSha256: sourceSha, publishedBuildManifest: metadata.manifest };
}

async function main() {
  const args = process.argv.slice(2);
  assert.ok(args.every(arg => arg === '--quick'), 'Usage: node scripts/performance-v010.mjs [--quick]');
  const quick = args.includes('--quick');
  const packageVersion = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version;
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outputDirectory = resolve(root, 'verification/releases', packageVersion);
  mkdirSync(outputDirectory, { recursive: true });
  const work = resolve(root, `artifacts/performance-v010-${packageVersion}-${stamp}`);
  mkdirSync(work, { recursive: true });
  const receiptPath = resolve(outputDirectory, `performance-v010-${quick ? 'smoke' : 'formal'}-${stamp}.json`);
  const receipt = { tool: 'MoonTxnWitness', version: packageVersion, baselineVersion: '0.1.0',
    startedAt: new Date().toISOString(), passed: false, smokeOnly: quick,
    correctnessPassed: false, formalReleaseGatePassed: false,
    protocol: { warmups: quick ? 1 : 5, samplesPerBatch: quick ? 3 : 30,
      independentAlternatingBatches: quick ? 1 : 3, profile: 'balanced',
      fullOperation: 'MoonBit JSON-in/JSON-out plus client JSON decoding; all evidence retained',
      summaryStatistic: 'Median of the corresponding three per-process statistics',
      semanticComparison: 'All full-output values must match frozen v0.1.0; only root version and shrink report.version are normalized',
      phaseCaveat: 'Prepared-input phase hooks are separate diagnostic operations, not additive end-to-end stages' },
    environment: { node: process.version, os: platform(), release: release(), arch: arch(), cpu: cpus()[0]?.model },
    releaseGate: { scope: 'All 20 frozen common full-output workloads; phases are diagnostic',
      allowedP95Regression: 'max(0.10 * baseline P95, 2 milliseconds)',
      futureOptimizationTargetsApplied: false, applicable: !quick },
    results: [], phases: [], artifacts: rel(work),
    caveat: 'Same-machine direct comparison. Smoke cannot satisfy release acceptance. v0.1.8 speedup/RSS targets are not v0.1.1 gates.' };
  const save = () => {
    writeFileSync(receiptPath, json(receipt));
    writeFileSync(resolve(outputDirectory, 'performance-v010-latest.json'),
      json({ receipt: rel(receiptPath), passed: receipt.passed, smokeOnly: quick,
        formalReleaseGatePassed: receipt.formalReleaseGatePassed }));
  };
  save();
  try {
    const buildManifest = JSON.parse(readFileSync(resolve(root, 'dist/build-manifest.json'), 'utf8'));
    assert.equal(buildManifest.version, packageVersion, 'Compiled manifest version differs from package version');
    assert.equal(readFileSync(resolve(root, 'moon.mod'), 'utf8').match(/^version\s*=\s*"([^"]+)"/m)?.[1], packageVersion);
    assert.equal(buildManifest.sourceSha256, sourceFingerprint(root), 'Current build source fingerprint is stale');
    assert.equal(buildManifest.coreSha256, hash(readFileSync(resolve(root, 'dist/core.mjs'))), 'Current compiled core digest differs from its build manifest');
    const frozenManifest = JSON.parse(readFileSync(resolve(frozen, 'manifest.json'), 'utf8'));
    assert.ok(frozenManifest.latestFormalReceipt, 'Establish the formal v0.1.0 baseline first');
    const originalReceipt = JSON.parse(readFileSync(resolve(root, frozenManifest.latestFormalReceipt), 'utf8'));
    assert.ok(originalReceipt.passed && originalReceipt.formalBaselineEstablished && !originalReceipt.smokeOnly);
    const baseline = prepareBaseline(work, frozenManifest, originalReceipt);
    assert.deepEqual(buildManifest.toolchain, baseline.publishedBuildManifest.toolchain,
      'Direct gate requires the same compiler/toolchain as the pinned baseline');
    receipt.provenance = { baseline, currentBuildManifest: buildManifest,
      frozenBaselineReceipt: frozenManifest.latestFormalReceipt,
      originalBaselineProtocol: originalReceipt.protocol,
      currentSnapshot: 'Copied dist/core.mjs after checking manifest source/core/version identity' };
    receipt.environment.toolchain = buildManifest.toolchain;
    copyFileSync(resolve(root, 'dist/core.mjs'), resolve(work, 'current.mjs'));
    assert.equal(hash(readFileSync(resolve(work, 'current.mjs'))), buildManifest.coreSha256);
    const fixtureManifestPath = resolve(fixtureRoot, 'manifest.json');
    assert.equal(hash(readFileSync(fixtureManifestPath)), frozenManifest.fixtureManifestSha256,
      'Frozen fixture manifest was changed');
    const fixtureManifest = JSON.parse(readFileSync(fixtureManifestPath, 'utf8'));
    assert.equal(fixtureManifest.cases.length, 20);
    const cases = fixtureManifest.cases.map(item => {
      const path = resolve(root, item.file), bytes = readFileSync(path);
      assert.equal(hash(bytes), item.fixtureSha256, `Frozen fixture bytes changed: ${item.name}`);
      const fixture = JSON.parse(bytes);
      assert.equal(hash(JSON.stringify(fixture.history)), item.historySha256);
      const recorded = originalReceipt.results.find(row => row.scenario === item.name);
      assert.ok(recorded, `Original complete-output record missing: ${item.name}`);
      assert.equal(recorded.inputSha256, item.historySha256);
      const frozenOutputPath = resolve(root, recorded.fullOutput);
      assert.equal(hash(gunzipSync(readFileSync(frozenOutputPath))), recorded.fullOutputSha256,
        `Frozen complete output changed: ${item.name}`);
      return { ...item, path, fixture, frozenOutputPath };
    });
    assert.equal(originalReceipt.phases.length, 15);
    receipt.fixtureManifestSha256 = frozenManifest.fixtureManifestSha256;
    save();
    const run = (engine, c, phase, batch) => new Promise((done, reject) => {
      const name = `${c.name}-${phase}-${batch}-${engine}`;
      const outputPath = resolve(work, name + '-output.json');
      const child = spawn(process.execPath, [fileURLToPath(import.meta.url), '--worker', resolve(work, engine + '.mjs'),
        c.path, phase, String(quick ? 1 : 5), String(quick ? 3 : 30),
        engine === 'baseline' ? '0.1.0' : packageVersion, c.frozenOutputPath, outputPath],
        { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
      let stdout = '', stderr = '';
      child.stdout.on('data', chunk => stdout += chunk);
      child.stderr.on('data', chunk => stderr += chunk);
      const timer = setTimeout(() => child.kill(), 240000);
      child.on('error', error => { clearTimeout(timer); reject(error); });
      child.on('close', code => {
        clearTimeout(timer);
        writeFileSync(resolve(work, name + '-stdout.json'), stdout);
        if (stderr) writeFileSync(resolve(work, name + '-stderr.txt'), stderr);
        if (code !== 0) return reject(Error(`Benchmark ${name} failed: ${stderr.slice(-3000)}`));
        try { done(JSON.parse(stdout)); } catch (error) { reject(error); }
      });
    });
    const compare = async (c, phase, position) => {
      const rows = { baseline: [], current: [] }, engineOrders = [];
      for (let batch = 0; batch < (quick ? 1 : 3); batch++) {
        const order = (position + batch) % 2 ? ['current', 'baseline'] : ['baseline', 'current'];
        engineOrders.push(order);
        for (const engine of order) rows[engine].push(await run(engine, c, phase, batch));
      }
      const aggregate = engine => ({
        medianMs: median(rows[engine].map(row => row.medianMs)),
        p95Ms: median(rows[engine].map(row => row.p95Ms)),
        coldModuleLoadMs: median(rows[engine].map(row => row.loadMs)),
        firstAnalysisMs: median(rows[engine].map(row => row.firstMs)),
        peakRssKiB: median(rows[engine].map(row => row.peakRssKiB)),
        outputBytes: rows[engine][0].fullOutput?.outputBytes ?? null,
      });
      const baseline = aggregate('baseline'), current = aggregate('current');
      const regression = current.p95Ms - baseline.p95Ms;
      const allowed = Math.max(baseline.p95Ms * .1, 2);
      return { scenario: c.name, group: c.group, phase, inputSha256: c.historySha256,
        inputBytes: c.inputBytes, engineOrders, observations: rows, baseline, current,
        speedup: baseline.medianMs / current.medianMs,
        peakMemoryRatio: current.peakRssKiB / baseline.peakRssKiB,
        semanticAgreement: phase === 'full' ? true : 'Covered by the matching full-output scenario',
        p95RegressionMs: regression, allowedP95RegressionMs: allowed,
        p95WithinAllowance: regression <= allowed,
        p95ReleaseGateApplicable: !quick && phase === 'full' };
    };
    for (const [position, c] of cases.entries()) {
      const row = await compare(c, 'full', position);
      receipt.results.push(row); save();
      console.log(`${c.name}: baseline ${row.baseline.medianMs.toFixed(3)} / current ${row.current.medianMs.toFixed(3)} ms; P95 delta ${row.p95RegressionMs.toFixed(3)} ms (allow ${row.allowedP95RegressionMs.toFixed(3)}); ${row.p95WithinAllowance ? 'within' : 'outside'} allowance${quick ? ' [smoke]' : ''}`);
    }
    for (const [position, old] of originalReceipt.phases.entries()) {
      const c = cases.find(item => item.name === old.scenario);
      assert.ok(c);
      receipt.phases.push(await compare(c, old.phase, position));
      save();
    }
    // A copied engine gives stable measurements, but source changes during the
    // run must not be attached to this receipt as if they had been measured.
    assert.equal(sourceFingerprint(root), buildManifest.sourceSha256, 'Current source changed during measurement');
    assert.equal(hash(readFileSync(resolve(root, 'dist/core.mjs'))), buildManifest.coreSha256,
      'Current dist changed during measurement');
    assert.equal(JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version, packageVersion,
      'Current version changed during measurement');
    receipt.groups = Object.fromEntries([...new Set(cases.map(c => c.group))].map(group => {
      const rows = receipt.results.filter(row => row.group === group);
      return [group, { geometricMeanSpeedup: geomean(rows.map(row => row.speedup)),
        geometricMeanPeakMemoryRatio: geomean(rows.map(row => row.peakMemoryRatio)),
        allP95WithinAllowance: rows.every(row => row.p95WithinAllowance) }];
    }));
    receipt.correctnessPassed = true;
    receipt.releaseGate.allFullWorkloadsP95WithinAllowance = receipt.results.every(row => row.p95WithinAllowance);
    receipt.releaseGate.failedScenarios = receipt.results.filter(row => !row.p95WithinAllowance).map(row => row.scenario);
    receipt.formalReleaseGatePassed = !quick && receipt.releaseGate.allFullWorkloadsP95WithinAllowance;
    receipt.passed = quick || receipt.formalReleaseGatePassed;
    receipt.completedAt = new Date().toISOString(); save();
    console.log(JSON.stringify({ passed: receipt.passed, smokeOnly: quick,
      correctnessPassed: true, formalReleaseGatePassed: receipt.formalReleaseGatePassed,
      failedP95Scenarios: receipt.releaseGate.failedScenarios,
      fullScenarios: receipt.results.length, phaseScenarios: receipt.phases.length, receipt: rel(receiptPath) }));
    if (!receipt.passed) process.exitCode = 1;
  } catch (error) {
    receipt.failedAt = new Date().toISOString(); receipt.error = error.message; save(); throw error;
  }
}

if (process.argv[2] === '--worker') await worker();
else await main();
