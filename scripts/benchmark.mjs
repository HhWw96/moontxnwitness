import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { analyze } from '../dist/sdk.mjs';
import { root } from './moon.mjs';

const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--baseline')) throw new Error('Usage: node scripts/benchmark.mjs [--baseline core.mjs]');
const baseline = args.length ? await import(pathToFileURL(resolve(args[1])).href) : null;
const engines = [{ name: 'current', version: JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version, analyze }, ...(baseline ? [{ name: 'baseline', version: baseline.version(), analyze: h => JSON.parse(baseline.analyze_json(JSON.stringify(h))) }] : [])];
const n = 64;
const transactions = Array.from({ length: n }, (_, i) => ({ id: `n${i}`, status: 'committed', ops: [{ type: 'read', key: 'x', version: `x${i}` }, { type: 'write', key: 'x', version: `x${i + 1}` }] }));
transactions.push({ id: 'A', status: 'committed', ops: [{ type: 'read', key: 'x', version: `x${n}` }, { type: 'read', key: 'y', version: 'y0' }, { type: 'write', key: 'z', version: 'z1' }] });
transactions.push({ id: 'B', status: 'committed', ops: [{ type: 'read', key: 'z', version: 'z0' }, { type: 'write', key: 'y', version: 'y1' }] });
const cases = [
  { name: '64-prefix-feeding-two-transaction-cycle', status: 'violation', history: { initial: { x: 'x0', y: 'y0', z: 'z0' }, versionOrders: { x: Array.from({ length: n + 1 }, (_, i) => `x${i}`) }, transactions } },
  { name: '96-transaction-strict-acyclic', status: 'consistent', history: { model: 'strict-serializable', initial: {}, transactions: Array.from({ length: 96 }, (_, i) => ({ id: `T${i}`, status: 'committed', start: i * 3, end: i * 3 + 1, ops: [] })) } },
];
const results = [];
for (const scenario of cases) {
  const observations = new Map();
  for (const engine of engines) engine.analyze(scenario.history);
  for (let repetition = 0; repetition < 3; repetition++) {
    for (const engine of repetition % 2 ? [...engines].reverse() : engines) {
      const start = performance.now();
      const report = engine.analyze(scenario.history);
      const elapsed = performance.now() - start;
      assert.equal(report.status, scenario.status);
      if (scenario.status === 'violation') assert.equal(report.witness.edges.length, 2);
      else assert.equal(report.serialOrder.length, 96);
      const row = observations.get(engine.name) || { engine: engine.name, version: engine.version, timesMs: [], dependencies: report.stats.dependencies, graph: report.graph || null };
      row.timesMs.push(Math.round(elapsed * 1000) / 1000);
      observations.set(engine.name, row);
    }
  }
  const rows = [...observations.values()].map(row => ({ ...row, medianMs: [...row.timesMs].sort((a, b) => a - b)[1] }));
  const current = observations.get('current');
  assert.equal(current.graph.bfsRoots, scenario.status === 'violation' ? 1 : 0);
  if (rows.length === 2) assert.equal(rows[0].dependencies, rows[1].dependencies);
  results.push({ scenario: scenario.name, status: scenario.status, measurements: rows });
}
const receipt = { tool: 'MoonTxnWitness', version: engines[0].version, node: process.version, passed: true, method: 'Full JSON-in/JSON-out analysis; warmup then three alternating samples; no timing pass threshold', caveat: 'Local observations only, not a general performance guarantee; current result contains added diagnostics', results };
mkdirSync(resolve(root, 'verification'), { recursive: true });
writeFileSync(resolve(root, 'verification/benchmark.json'), JSON.stringify(receipt, null, 2) + '\n');
console.log('Graph benchmark: verdicts and shortest cycles agree; acyclic roots skipped.');
for (const r of results) console.log(`${r.scenario}: ${r.measurements.map(m => `${m.engine} ${m.medianMs} ms`).join(', ')}`);
