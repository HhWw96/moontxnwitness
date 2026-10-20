// Frozen v0.1.0 performance inputs, published engine provenance and measurements.
// Run: node scripts/baseline-v010.mjs [--quick] [--refresh-download]
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { cpus, platform, release, arch } from 'node:os';
import { spawn, spawnSync } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { gzipSync, gunzipSync } from 'node:zlib';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const frozen = resolve(root, 'verification/baselines/0.1.0');
const inputs = resolve(root, 'verification/fixtures/v010-comparison');
const publicUrl = 'https://github.com/HhWw96/moontxnwitness/releases/download/v0.1.0/MoonTxnWitness-v0.1.0-portable.zip';
const publishedCommit = '540a9e390ed54f8b5e6d3b87aba3367c971c18b3';
const archiveSha = 'd7495482b8267f327edf40e95111acbd2502290fc97e5f1e5e1203e7bc59488c';
const coreSha = '6c76b3be6c45ff633232568b3ffed3c1393ade3b4d012ee5c21c49cbb8dcf97b';
const sourceSha = 'dcc8653278a9f98dc6056d23c8b7d7d9db3fc6b8406b22987fc9ff03997dd830';
const hash = value => createHash('sha256').update(value).digest('hex');
const json = value => JSON.stringify(value, null, 2) + '\n';
const rel = value => relative(root, value).split('\\').join('/');
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

// A subprocess measures one engine/scenario/phase, including a fresh module load.
async function worker() {
  const [corePath, fixturePath, phase, warmups, samples, outputPath] = process.argv.slice(3);
  const loaded = performance.now();
  const core = await import(pathToFileURL(corePath).href);
  const loadMs = performance.now() - loaded;
  assert.equal(core.version(), '0.1.0');
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
  // Capture resource usage before hashing/writing the measured full output.
  const peakRssKiB = process.resourceUsage().maxRSS;
  let outputBytes = null, outputSha256 = null, correctness = null;
  if (phase === 'full') {
    assert.equal(output.status, fixture.status, fixture.name);
    const report = output.report || output;
    if (fixture.cycle) assert.equal(report.witness.edges.length, fixture.cycle);
    if (fixture.operation === 'shrink') {
      assert.equal(output.oneMinimal, true);
      assert.equal(output.reducedHistory.transactions.length, 2);
    }
    const encoded = Buffer.from(JSON.stringify(output));
    outputBytes = encoded.length;
    outputSha256 = hash(encoded);
    writeFileSync(outputPath, encoded);
    correctness = { status: output.status, witnessEdges: report.witness?.edges.length ?? null,
      oneMinimal: output.oneMinimal ?? null, reducedTransactions: output.reducedHistory?.transactions.length ?? null,
      search: report.search ?? null };
  }
  const sorted = [...timesMs].sort((a, b) => a - b);
  console.log(JSON.stringify({ phase, version: core.version(), profile: 'balanced', loadMs, firstMs,
    timesMs, medianMs: median(timesMs), p95Ms: sorted[Math.ceil(sorted.length * .95) - 1],
    peakRssKiB, outputBytes, outputSha256, correctness }));
}

function exec(binary, args, options = {}) {
  const result = spawnSync(binary, args, { cwd: root, encoding: 'utf8', windowsHide: true, ...options });
  assert.ifError(result.error);
  assert.equal(result.status, 0, `${binary} failed: ${(result.stderr || '').slice(-2000)}`);
  return result.stdout;
}

async function main() {
  const args = process.argv.slice(2);
  assert.ok(args.every(arg => ['--quick', '--refresh-download'].includes(arg)),
    'Usage: node scripts/baseline-v010.mjs [--quick] [--refresh-download]');
  const quick = args.includes('--quick');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  mkdirSync(frozen, { recursive: true });
  mkdirSync(inputs, { recursive: true });
  const work = resolve(root, `artifacts/baseline-v010-${stamp}`);
  mkdirSync(work, { recursive: true });
  const receiptPath = resolve(frozen, `measurement-${quick ? 'smoke' : 'formal'}-${stamp}.json`);
  const receipt = { tool: 'MoonTxnWitness', benchmark: 'v010-direct-baseline-v1',
    startedAt: new Date().toISOString(), passed: false, smokeOnly: quick,
    protocol: { warmups: quick ? 1 : 5, samplesPerBatch: quick ? 3 : 30,
      independentProcessBatches: quick ? 1 : 3, profile: 'balanced',
      fullOperation: 'MoonBit JSON-in/JSON-out plus client JSON decoding; full evidence retained',
      phaseCaveat: 'Phase hooks prepare input outside timed section; phases do not sum to full analysis.' },
    environment: { node: process.version, os: platform(), release: release(), arch: arch(), cpu: cpus()[0]?.model },
    results: [], phases: [], artifacts: rel(work),
    caveat: 'Absolute frozen-engine baseline, not a speedup claim or official scoring threshold. Smoke is not acceptance.' };
  const save = () => writeFileSync(receiptPath, json(receipt));
  save();
  try {
    const archive = resolve(work, 'published-portable.zip');
    const localArchive = resolve(root, 'artifacts/MoonTxnWitness-v0.1.0-portable.zip');
    const extraction = String.raw`
import hashlib,json,sys,urllib.request,zipfile
from pathlib import Path
url,sha,core_sha,source_sha,destination,local,use_local=sys.argv[1:]
destination=Path(destination)
if use_local=='yes' and Path(local).exists():
    packed=Path(local).read_bytes(); transport='verified-local-copy-of-pinned-public-archive'
else:
    request=urllib.request.Request(url,headers={'User-Agent':'MoonTxnWitness-v010-baseline'})
    with urllib.request.urlopen(request,timeout=60) as response:
        assert response.status==200
        packed=response.read(16*1024*1024+1)
    transport='anonymous-public-download'
assert len(packed)<=16*1024*1024
assert hashlib.sha256(packed).hexdigest()==sha,'Published archive SHA-256 mismatch'
destination.write_bytes(packed)
with zipfile.ZipFile(destination) as archive:
    core=archive.read('MoonTxnWitness-v0.1.0/dist/core.mjs')
    manifest=json.loads(archive.read('MoonTxnWitness-v0.1.0/dist/build-manifest.json'))
assert hashlib.sha256(core).hexdigest()==core_sha
assert manifest['version']=='0.1.0' and manifest['coreSha256']==core_sha
assert manifest['sourceSha256']==source_sha
(destination.parent/'core.mjs').write_bytes(core)
(destination.parent/'published-build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print(json.dumps({'transport':transport,'manifest':manifest}))
`;
    const prepared = JSON.parse(exec(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
      ['-c', extraction, publicUrl, archiveSha, coreSha, sourceSha, archive, localArchive,
        args.includes('--refresh-download') ? 'no' : 'yes']));
    receipt.provenance = { publicUrl, archiveSha256: archiveSha, coreSha256: coreSha,
      publishedSourceCommit: publishedCommit, sourceSha256: sourceSha,
      transport: prepared.transport, publishedBuildManifest: prepared.manifest,
      source: 'Pinned published release bytes; no current-working-tree compilation or dist/core.mjs used' };
    receipt.environment.toolchain = prepared.manifest.toolchain;
    const commit = exec('git', ['rev-parse', 'v0.1.0']).trim();
    assert.equal(commit, publishedCommit, 'v0.1.0 tag does not match the pinned release');
    // Verify that the source fingerprint attested by the release is the local immutable tag.
    const names = exec('git', ['ls-tree', '-r', '--name-only', publishedCommit, '--', 'moon.mod', 'src'])
      .trim().split(/\r?\n/).filter(n => n === 'moon.mod' || n.endsWith('.mbt') || n.endsWith('/moon.pkg')).sort();
    const fingerprint = createHash('sha256');
    for (const name of names) {
      fingerprint.update(name + '\0');
      fingerprint.update(exec('git', ['show', `${publishedCommit}:${name}`], { encoding: null }));
      fingerprint.update('\0');
    }
    assert.equal(fingerprint.digest('hex'), sourceSha, 'Published fingerprint differs from immutable tag source');
    receipt.provenance.tagSourceFingerprintVerified = true;
    const legacyGenerator = exec('git', ['show', `${publishedCommit}:scripts/benchmark-fixtures.mjs`]);
    const legacyPath = resolve(inputs, 'legacy-fixtures-v010.mjs');
    if (existsSync(legacyPath)) assert.equal(readFileSync(legacyPath, 'utf8'), legacyGenerator);
    else writeFileSync(legacyPath, legacyGenerator);
    const { fixtures, noisy, completion } = await import(pathToFileURL(legacyPath).href);
    const cases = fixtures().map(c => ({ ...c, generator: 'v0.1.0 benchmark-fixtures.mjs', seed: null }));
    const next = seed => () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return seed >>> 0; };
    const independentCompletionProof = history => {
      const txs = history.transactions.filter(t => ['A', 'B', 'R'].includes(t.id));
      let valid = 0;
      const visit = (remaining, state) => {
        if (!remaining.length) { valid++; return; }
        for (const t of remaining) {
          const after = { ...state }; let possible = true;
          for (const op of t.ops) {
            if (op.type === 'read' && after[op.key] !== op.version) { possible = false; break; }
            if (op.type === 'write') after[op.key] = op.version;
          }
          if (possible) visit(remaining.filter(other => other !== t), after);
        }
      };
      visit(txs, { ...history.initial });
      assert.equal(valid, 0, 'Independent three-transaction projection must have no serial execution');
      assert.ok(history.transactions.filter(t => !['A', 'B', 'R'].includes(t.id))
        .every(t => t.ops.every(op => op.type === 'read' && op.key === 'z' && op.version === 'z0')));
    };
    for (const n of [9, 10, 11, 12]) {
      const seed = 0x10B000 + n, random = next(seed), history = completion(n);
      for (let i = history.transactions.length - 1; i > 0; i--) {
        const j = random() % (i + 1);
        [history.transactions[i], history.transactions[j]] = [history.transactions[j], history.transactions[i]];
      }
      independentCompletionProof(history);
      cases.push({ name: `completion-impossible-${n}`, group: 'search-large', status: 'violation',
        generator: 'completion(n) plus xorshift32 Fisher-Yates order', seed,
        independentProof: 'All six A/B/R serial orders fail; other transactions only read disjoint z0', history });
    }
    cases.push({ name: 'reduction-512', group: 'reduction-large', operation: 'shrink', status: 'reduced',
      generator: 'v0.1.0 noisy(512): 510 disjoint read-only transactions plus two-transaction write skew', seed: null, history: noisy(512) });
    const index = { schemaVersion: 1, frozenEngineVersion: '0.1.0', sourceCommit: publishedCommit,
      legacyGeneratorSha256: hash(legacyGenerator), generatorScriptSha256: hash(readFileSync(fileURLToPath(import.meta.url))),
      allInputsFrozenBeforeOptimization: true,
      note: '9–12 unsatisfiable search fixtures exercise the existing independent-projection family; they do not represent every difficult search shape.', cases: [] };
    for (const c of cases) {
      const text = json(c), path = resolve(inputs, `${c.name}.json`);
      if (existsSync(path)) assert.equal(readFileSync(path, 'utf8'), text, `Frozen fixture changed: ${c.name}`);
      else writeFileSync(path, text);
      index.cases.push({ name: c.name, group: c.group, file: rel(path), seed: c.seed,
        fixtureSha256: hash(text), historySha256: hash(JSON.stringify(c.history)),
        inputBytes: Buffer.byteLength(JSON.stringify(c.history)), transactions: c.history.transactions.length,
        operations: c.history.transactions.reduce((sum, t) => sum + t.ops.length, 0) });
    }
    const indexPath = resolve(inputs, 'manifest.json');
    if (existsSync(indexPath)) assert.deepEqual(JSON.parse(readFileSync(indexPath, 'utf8')), index, 'Frozen generator manifest changed');
    else writeFileSync(indexPath, json(index));
    receipt.fixtureManifestSha256 = hash(readFileSync(indexPath));
    save();
    const run = (c, phase, batch) => new Promise((done, reject) => {
      const outputPath = resolve(work, `${c.name}-${phase}-${batch}-output.json`);
      const child = spawn(process.execPath, [fileURLToPath(import.meta.url), '--worker', resolve(work, 'core.mjs'),
        resolve(inputs, `${c.name}.json`), phase, String(quick ? 1 : 5), String(quick ? 3 : 30), outputPath],
        { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
      let stdout = '', stderr = '';
      child.stdout.on('data', chunk => stdout += chunk);
      child.stderr.on('data', chunk => stderr += chunk);
      const timer = setTimeout(() => child.kill(), 240000);
      child.on('error', error => { clearTimeout(timer); reject(error); });
      child.on('close', code => {
        clearTimeout(timer);
        writeFileSync(resolve(work, `${c.name}-${phase}-${batch}-stdout.json`), stdout);
        if (stderr) writeFileSync(resolve(work, `${c.name}-${phase}-${batch}-stderr.txt`), stderr);
        if (code !== 0) return reject(Error(`Benchmark failed: ${c.name}/${phase}/${batch}: ${stderr.slice(-3000)}`));
        try { done({ ...JSON.parse(stdout), outputPath }); } catch (error) { reject(error); }
      });
    });
    for (const c of cases) {
      const batches = [];
      for (let batch = 0; batch < (quick ? 1 : 3); batch++) {
        const row = await run(c, 'full', batch);
        const output = readFileSync(row.outputPath);
        const expected = resolve(frozen, 'outputs', `${c.name}.json.gz`);
        mkdirSync(dirname(expected), { recursive: true });
        if (existsSync(expected)) assert.equal(hash(gunzipSync(readFileSync(expected))), row.outputSha256,
          `Pinned full output changed: ${c.name}`);
        else writeFileSync(expected, gzipSync(output, { level: 9 }));
        delete row.outputPath;
        batches.push(row);
      }
      const row = { scenario: c.name, group: c.group, inputSha256: hash(JSON.stringify(c.history)),
        fullOutput: rel(resolve(frozen, 'outputs', `${c.name}.json.gz`)),
        fullOutputSha256: batches[0].outputSha256, batches,
        medianMs: median(batches.map(r => r.medianMs)), p95Ms: median(batches.map(r => r.p95Ms)),
        coldModuleLoadMs: median(batches.map(r => r.loadMs)), firstAnalysisMs: median(batches.map(r => r.firstMs)),
        peakRssKiB: median(batches.map(r => r.peakRssKiB)), outputBytes: batches[0].outputBytes };
      receipt.results.push(row); save();
      console.log(`${c.name}: median ${row.medianMs.toFixed(3)} ms; P95 ${row.p95Ms.toFixed(3)} ms; RSS ${(row.peakRssKiB / 1024).toFixed(1)} MiB`);
    }
    // One representative of each phase. Full and phase measurements both use the formal protocol.
    for (const [name, phases] of [
      ['dense-rt-192', ['parse', 'inference', 'cycle', 'render']],
      ['long-ring-128', ['parse', 'inference', 'cycle', 'render']],
      ['completion-impossible-12', ['parse', 'inference', 'search', 'render']],
      ['reduction-512', ['parse', 'inference', 'reduction']],
    ]) {
      const c = cases.find(item => item.name === name);
      for (const phase of phases) {
        const batches = [];
        for (let batch = 0; batch < (quick ? 1 : 3); batch++) {
          const row = await run(c, phase, batch); delete row.outputPath; batches.push(row);
        }
        receipt.phases.push({ scenario: name, phase, batches,
          medianMs: median(batches.map(r => r.medianMs)), p95Ms: median(batches.map(r => r.p95Ms)),
          peakRssKiB: median(batches.map(r => r.peakRssKiB)) });
        save();
      }
    }
    receipt.passed = true;
    receipt.completedAt = new Date().toISOString();
    receipt.formalBaselineEstablished = !quick;
    save();
    const manifest = { schemaVersion: 1, engine: receipt.provenance,
      fixtureManifest: rel(indexPath), fixtureManifestSha256: receipt.fixtureManifestSha256,
      latestFormalReceipt: !quick ? rel(receiptPath) : null,
      latestSmokeReceipt: quick ? rel(receiptPath) : null,
      note: 'Published engine and frozen complete outputs; timestamped failed/smoke/formal measurements are retained.' };
    const manifestPath = resolve(frozen, 'manifest.json');
    if (existsSync(manifestPath)) {
      const previous = JSON.parse(readFileSync(manifestPath, 'utf8'));
      if (quick) manifest.latestFormalReceipt = previous.latestFormalReceipt;
      else manifest.latestSmokeReceipt = previous.latestSmokeReceipt;
    }
    writeFileSync(manifestPath, json(manifest));
    console.log(JSON.stringify({ passed: true, smokeOnly: quick, formalBaselineEstablished: !quick,
      scenarios: receipt.results.length, phaseScenarios: receipt.phases.length, receipt: rel(receiptPath) }));
  } catch (error) {
    receipt.failedAt = new Date().toISOString(); receipt.error = error.message; save(); throw error;
  }
}

if (process.argv[2] === '--worker') await worker();
else await main();
