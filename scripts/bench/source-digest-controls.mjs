// Common paths unaffected by the digest optimization. Each batch is a fresh process.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {cpus, platform, release} from 'node:os';

const hash = value => createHash('sha256').update(value).digest('hex');
const cases = [
  {id: 'register', input: 'examples/write-skew.json', operation: 'analyzeV4', verify: 'verifyV4'},
  {id: 'list', input: 'examples/list-cycle.json', operation: 'analyzeV4', verify: 'verifyV4'},
  {id: 'relation', input: 'examples/relation-atomic-point.json', operation: 'classifyRelationV4', verify: 'verifyRelationClassificationV4'},
  {id: 'reduction', input: 'examples/write-skew.json', operation: 'reduceV4', verify: 'verifyReductionV4', options: {preserve: 'serializable'}},
];
const [baseline, candidate, output, childCase, kind] = process.argv.slice(2);
if (!baseline || !candidate || !output) {
  throw Error('Usage: source-digest-controls.mjs BASELINE_DIST CANDIDATE_DIST NEW_OUTPUT_DIR');
}
const root = fileURLToPath(new URL('../../', import.meta.url));
const percentile = (values, p) => values.toSorted((a, b) => a - b)[Math.ceil(values.length * p) - 1];
if (childCase) {
  const entry = cases.find(value => value.id === childCase);
  assert.ok(entry);
  const source = readFileSync(resolve(root, entry.input), 'utf8');
  const startImport = performance.now();
  const sdk = await import(pathToFileURL(resolve(baseline, 'sdk.mjs')).href);
  const coldImportMs = performance.now() - startImport;
  const samples = [];
  let report, coldCallMs;
  for (let index = 0; index < (kind === 'memory' ? 1 : 35); index++) {
    const start = performance.now();
    report = sdk[entry.operation](source, entry.options ?? {});
    const elapsed = performance.now() - start;
    if (index === 0) coldCallMs = elapsed;
    if (index >= 5) samples.push(elapsed);
  }
  const text = JSON.stringify(report);
  const peakRssKiB = process.resourceUsage().maxRSS;
  assert.equal(sdk[entry.verify](source, report, entry.options ?? {}).valid, true);
  console.log(JSON.stringify({samples, coldCallMs, coldImportMs, peakRssKiB,
    outputSha256: hash(text), outputBytes: Buffer.byteLength(text), inputSha256: hash(source)}));
} else {
  mkdirSync(output);
  const results = [];
  for (const entry of cases) {
    const runs = {baseline: {batches: [], memory: []}, candidate: {batches: [], memory: []}};
    for (let batch = 0; batch < 3; batch++) {
      const labels = batch % 2 ? ['candidate', 'baseline'] : ['baseline', 'candidate'];
      for (const label of labels) for (const mode of ['timing', 'memory']) {
        const runtime = label === 'baseline' ? baseline : candidate;
        const run = spawnSync(process.execPath, [fileURLToPath(import.meta.url), resolve(runtime),
          resolve(runtime), resolve(output), entry.id, mode],
        {encoding: 'utf8', windowsHide: true, timeout: 180000, maxBuffer: 1024 * 1024});
        assert.equal(run.status, 0, run.stderr || run.error?.message);
        runs[label][mode === 'timing' ? 'batches' : 'memory'].push(JSON.parse(run.stdout));
      }
    }
    const all = Object.values(runs).flatMap(value => [...value.batches, ...value.memory]);
    assert.equal(new Set(all.map(value => value.outputSha256)).size, 1);
    assert.equal(new Set(all.map(value => value.inputSha256)).size, 1);
    for (const value of Object.values(runs)) {
      const samples = value.batches.flatMap(batch => batch.samples);
      value.medianMs = percentile(samples, .5);
      value.p95Ms = percentile(samples, .95);
      value.peakRssKiB = Math.max(...value.memory.map(batch => batch.peakRssKiB));
    }
    const regressionMs = runs.candidate.p95Ms - runs.baseline.p95Ms;
    const allowedRegressionMs = Math.max(2, runs.baseline.p95Ms * .1);
    const result = {id: entry.id, operation: entry.operation, input: entry.input,
      inputSha256: all[0].inputSha256, outputSha256: all[0].outputSha256,
      outputBytes: all[0].outputBytes, sameCompleteOutput: true, ...runs,
      regressionMs, allowedRegressionMs, passed: regressionMs <= allowedRegressionMs};
    results.push(result);
    console.log(JSON.stringify({completed: entry.id, passed: result.passed,
      baselineP95: runs.baseline.p95Ms, candidateP95: runs.candidate.p95Ms}));
  }
  const runtime = directory => {
    const manifest = JSON.parse(readFileSync(resolve(directory, 'build-manifest.json')));
    assert.equal(hash(readFileSync(resolve(directory, 'core.mjs'))), manifest.coreSha256);
    return manifest;
  };
  const receipt = {format: 'source-digest-control-comparison/v1',
    passed: results.every(value => value.passed),
    protocol: {warmups: 5, samples: 30, batches: 3, memoryMeasuredInSeparateProcesses: true,
      batchOrder: ['AB', 'BA', 'AB'], outputScope: 'complete SDK report'},
    environment: {node: process.version, platform: platform(), release: release(), cpu: cpus()[0]?.model},
    runtimes: {baseline: runtime(baseline), candidate: runtime(candidate)}, cases: results};
  writeFileSync(resolve(output, 'comparison.json'), JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  assert.equal(receipt.passed, true, 'Common-path P95 regression exceeds its recorded allowance');
}
