// Static analysis of already collected CPU/GC evidence; runs no workloads.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { basename } from 'node:path';

const input = process.argv[2];
assert.ok(input && process.argv.length === 3,
  'Usage: node scripts/analyze-common-paths-profile.mjs RESULT.json');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const bytes = readFileSync(input);
const result = JSON.parse(bytes);
assert.equal(result.complete, true);
assert.equal(result.diagnosticOnly, true);
const groups = {
  parseHistory: n => /parse__history__optimized|direct__history|HistoryScan/.test(n),
  typedValidation: n => /validate__history/.test(n),
  identifierValidation: n => /valid__identifier/.test(n),
  orderResolution: n => /resolve__orders/.test(n),
  coverage: n => /coverage__indexed/.test(n),
  dependencyInference: n => /analyze__internal/.test(n),
  topologicalOrder: n => /topological__order/.test(n),
  serialization: n => /write__report|report__string|write__analysis__result|analysis__result__string/.test(n),
};
const summaries = [];
let countedWorkers = 0, countedSamples = 0;
for (const scenario of result.results) {
  const engines = {};
  for (const engine of ['baseline', 'current']) {
    const self = new Map();
    const inclusive = Object.fromEntries(Object.keys(groups).map(k => [k, 0]));
    let totalUs = 0;
    const samples = [];
    const profileBindings = [];
    const negativeTimeDeltas = [];
    for (const observation of scenario.observations[engine]) {
      const profileBytes = readFileSync(observation.rawProfile);
      assert.equal(sha(profileBytes), observation.rawProfileSha256);
      const rawBytes = readFileSync(observation.rawObservation);
      assert.equal(sha(rawBytes), observation.rawObservationSha256);
      const profile = JSON.parse(profileBytes);
      assert.equal(profile.samples.length, profile.timeDeltas.length);
      const nodes = new Map(profile.nodes.map(n => [n.id, n]));
      const parents = new Map();
      for (const n of profile.nodes) for (const child of n.children || []) {
        assert.ok(!parents.has(child), 'CPU profile must be a tree');
        parents.set(child, n.id);
      }
      for (let i = 0; i < profile.samples.length; i++) {
        const timeUs = profile.timeDeltas[i];
        assert.ok(Number.isFinite(timeUs));
        if (timeUs < 0) negativeTimeDeltas.push({
          file: basename(observation.rawProfile), sampleIndex: i, timeDeltaUs: timeUs,
        });
        const name = nodes.get(profile.samples[i]).callFrame.functionName || '(anonymous)';
        self.set(name, (self.get(name) || 0) + timeUs);
        totalUs += timeUs;
        const matched = new Set();
        let id = profile.samples[i];
        while (id !== undefined) {
          const frame = nodes.get(id).callFrame.functionName || '(anonymous)';
          for (const [group, match] of Object.entries(groups)) {
            if (match(frame)) matched.add(group);
          }
          id = parents.get(id);
        }
        // Each sample contributes at most once per category; categories overlap.
        for (const group of matched) inclusive[group] += timeUs;
      }
      const timed = observation.rows.filter(row => !row.warmup);
      assert.equal(timed.length, 30);
      countedWorkers++;
      countedSamples += timed.length;
      for (const row of timed) samples.push({ batch: observation.batch, ...row });
      profileBindings.push({
        file: basename(observation.rawProfile),
        sha256: observation.rawProfileSha256,
      });
    }
    const summarizeRows = rows => ({
      samples: rows.length,
      totalWallMs: rows.reduce((n, r) => n + r.durationMs, 0),
      totalGcOverlapMs: rows.reduce((n, r) => n + r.gcOverlapMs, 0),
      maxDurationMs: rows.length ? Math.max(...rows.map(r => r.durationMs)) : null,
    });
    engines[engine] = {
      totalProfileUs: totalUs,
      topSelf: [...self].sort((a, b) => b[1] - a[1]).slice(0, 50)
        .map(([functionName, selfUs]) => ({ functionName, selfUs, share: selfUs / totalUs })),
      inclusiveCategories: Object.fromEntries(Object.entries(inclusive)
        .map(([key, inclusiveUs]) => [key, { inclusiveUs, share: inclusiveUs / totalUs }])),
      observedTimedSamples: {
        all: summarizeRows(samples),
        withGc: summarizeRows(samples.filter(r => r.gcOverlapMs > 0)),
        withoutGc: summarizeRows(samples.filter(r => r.gcOverlapMs === 0)),
        slowestFive: [...samples].sort((a, b) => b.durationMs - a.durationMs).slice(0, 5),
      },
      profiles: profileBindings,
      negativeTimeDeltas,
    };
  }
  summaries.push({ scenario: scenario.scenario, engines });
}
assert.equal(countedWorkers, 12);
assert.equal(countedSamples, 360);
const report = {
  schema: 1,
  diagnosticOnly: true,
  formalReleaseGateApplicable: false,
  complete: true,
  source: input.replaceAll('\\', '/'),
  sourceSha256: sha(bytes),
  scriptSha256: sha(readFileSync(new URL(import.meta.url))),
  fixed: result.fixed,
  workerProcesses: countedWorkers,
  timedSamples: countedSamples,
  methodology: [
    'Static aggregation of complete CPU profiles, weighted by each sample timeDelta.',
    'Profile includes five warmups, 30 timed operations and inspector start/stop overhead. Top self uses the full profile denominator.',
    'Inclusive categories traverse ancestor stacks, count each sample once within a category, and overlap across categories; do not sum their shares.',
    'GC overlap uses only timed operation intervals. Profile GC self time is a different metric.',
    'Original signed profiler timeDeltas are retained, including the explicitly listed negative delta; none is clamped or dropped.',
    'Sampling noise, JIT and inspector overhead preclude inferring the cause of a previous uninstrumented P95 failure from these observations.',
  ],
  analysisAttemptNote: 'The first static aggregation rejected a V8-recorded -14us timeDelta before writing any analysis output. This analysis retains the original signed value, matching the diagnostic worker. No workload was repeated.',
  summaries,
  conclusions: [
    'The same instruments did not reproduce the previous formal P95 regression; the formal release gate remains failed.',
    'Some slow timed samples have no observed GC overlap. These profiles do not establish GC as the sole tail-latency cause.',
    'Identifier parsing has distinct scanning and validation frames in both scenarios. Source inspection confirms an extra identifier validation pass after string scanning, with later typed validation retained independently.',
    'Coverage is already indexed and does not repeatedly scan all history per key. Do not claim that obsolete pattern as a diagnosed hotspot.',
    'Sparse consistent graphs also execute topological ordering. Current source repeatedly scans the original transaction prefix to select the smallest ready index; any replacement must preserve this exact tie order.',
  ],
};
const output = input.replace(/-result\.json$/, '-analysis.json');
assert.notEqual(output, input);
assert.ok(!existsSync(output), 'Analysis must be new');
const encoded = JSON.stringify(report, null, 2) + '\n';
writeFileSync(output, encoded, { flag: 'wx' });
console.log(JSON.stringify({ output, sha256: sha(encoded), workerProcesses: countedWorkers,
  timedSamples: countedSamples, categories: summaries.map(s => ({ scenario: s.scenario,
    baseline: s.engines.baseline.inclusiveCategories,
    current: s.engines.current.inclusiveCategories })) }, null, 2));
