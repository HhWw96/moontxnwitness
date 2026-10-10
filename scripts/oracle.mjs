// Test-only oracle: replay whole transactions in every possible serial order.
// It does not construct WR/WW/RW edges or call the production graph search.
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';
import { analyze, verify, shrink } from '../dist/sdk.mjs';
import { root } from './moon.mjs';

function permutations(items) {
  if (items.length === 0) return [[]];
  return items.flatMap((v, i) => permutations(items.filter((_, j) => j !== i)).map(rest => [v, ...rest]));
}

function serialReplay(history, ids) {
  const txs = new Map(history.transactions.map(t => [t.id, t]));
  const committed = history.transactions.filter(t => t.status === 'committed');
  if (ids.length !== committed.length || new Set(ids).size !== ids.length || ids.some(id => !txs.has(id) || txs.get(id).status !== 'committed')) return false;
  const rank = new Map(ids.map((id, i) => [id, i]));
  if (history.model === 'strict-serializable') {
    for (const a of committed) for (const b of committed) {
      if (a.id !== b.id && a.end < b.start && rank.get(a.id) >= rank.get(b.id)) return false;
    }
  }
  const state = { ...history.initial };
  const orders = Object.fromEntries(Object.entries(history.initial).map(([k, v]) => [k, [v]]));
  for (const id of ids) {
    const finalWrites = new Map();
    for (const op of txs.get(id).ops) {
      if (op.type === 'read') {
        if (state[op.key] !== op.version) return false;
      } else {
        state[op.key] = op.version;
        finalWrites.set(op.key, op.version);
      }
    }
    for (const [key, version] of finalWrites) orders[key].push(version);
  }
  for (const [key, order] of Object.entries(history.versionOrders || {})) {
    if (JSON.stringify(orders[key]) !== JSON.stringify(order)) return false;
  }
  return true;
}

function independentShortestCycle(report, ids) {
  const outgoing = new Map(ids.map(id => [id, new Set()]));
  for (const e of report.edges) outgoing.get(e.from).add(e.to);
  let minimum = Infinity;
  function walk(start, here, visited) {
    for (const next of outgoing.get(here)) {
      if (next === start) minimum = Math.min(minimum, visited.size);
      else if (!visited.has(next) && visited.size < minimum) walk(start, next, new Set([...visited, next]));
    }
  }
  for (const id of ids) walk(id, id, new Set([id]));
  return minimum;
}

export function runOracle() {
  const started = performance.now();
  const counts = { exhaustive: 0, generated: 0, completion: 0, consistent: 0, violation: 0, certificates: 0, shortestCycles: 0, serialOrders: 0, reductionsVerified: 0, reductionDeletionChecks: 0 };
  function check(history, category) {
    const ids = history.transactions.filter(t => t.status === 'committed').map(t => t.id);
    const serializations = permutations(ids);
    const exists = serializations.some(order => serialReplay(history, order));
    const report = analyze(history);
    assert.equal(report.status, exists ? 'consistent' : 'violation', JSON.stringify({ history, report, exists }));
    if (category !== 'completion' || exists) assert.equal(report.complete, true);
    counts[category]++;
    counts[report.status]++;
    if (exists) {
      assert.equal(serialReplay(history, report.serialOrder), true, 'Reported serial order must replay every read and final-write order');
      assert.equal(serialReplay({ ...history, versionOrders: report.versionOrders }, report.serialOrder), true, 'Searched orders must match the concrete serial replay');
      counts.serialOrders++;
    }
    const minimum = independentShortestCycle(report, ids);
    if (report.witness) {
      assert.equal(verify(history, report).valid, true);
      assert.equal(report.witness.edges.length, minimum, 'Returned witness must be shortest among all simple cycles in the graph');
      counts.certificates++;
      counts.shortestCycles++;
    } else assert.equal(minimum, Infinity);
    if (category === 'generated' && !exists && counts.generated % 11 === 0) {
      const reduced = shrink(history);
      assert.equal(reduced.report.status, 'violation');
      assert.equal(reduced.oneMinimal, true);
      const mini = reduced.reducedHistory;
      assert.deepEqual(mini.initial, history.initial);
      for (const t of mini.transactions) assert.deepEqual(t.ops, history.transactions.find(original => original.id === t.id).ops);
      assert.equal(permutations(mini.transactions.map(t => t.id)).some(ids => serialReplay(mini, ids)), false);
      if (reduced.report.witness) {
        const verified = verify(mini, reduced.report);
        assert.equal(verified.valid, true, JSON.stringify({ mini, report: reduced.report, verified }));
      }
      for (const t of mini.transactions) {
        const remainder = mini.transactions.filter(other => other.id !== t.id);
        const final = Object.fromEntries(Object.keys(mini.initial).map(k => [k, new Set([mini.initial[k]])]));
        for (const other of remainder) {
          const writes = new Map(other.ops.filter(op => op.type === 'write').map(op => [op.key, op.version]));
          for (const [key, v] of writes) final[key].add(v);
        }
        const versionOrders = Object.fromEntries(Object.entries(mini.versionOrders || {}).map(([k, order]) => [k, order.filter(v => final[k].has(v))]));
        assert.notEqual(analyze({ ...mini, transactions: remainder, versionOrders }).status, 'violation');
        counts.reductionDeletionChecks++;
      }
      counts.reductionsVerified++;
    }
  }

  // Exhaustive family: 2 or 3 committed transactions; two keys; each transaction
  // has one read then one write. Every write key, read key/source and per-key
  // final-write order is enumerated, in both supported models.
  for (const n of [2, 3]) {
    const ids = Array.from({ length: n }, (_, i) => `T${i + 1}`);
    for (let writeMask = 0; writeMask < 2 ** n; writeMask++) {
      const writeKeys = ids.map((_, i) => (writeMask >> i) & 1 ? 'y' : 'x');
      const versions = ids.map((id, i) => `${writeKeys[i]}-${id}`);
      const finalByKey = { x: [], y: [] };
      versions.forEach((v, i) => finalByKey[writeKeys[i]].push(v));
      const reads = ['x', 'y'].flatMap(key => [key + '0', ...finalByKey[key]].map(version => ({ type: 'read', key, version })));
      function chooseReads(chosen) {
        if (chosen.length < n) {
          for (const op of reads) chooseReads([...chosen, op]);
          return;
        }
        for (const model of ['serializable', 'strict-serializable']) {
          check({ schemaVersion: 1, model, initial: { x: 'x0', y: 'y0' }, transactions: ids.map((id, i) => ({ id, status: 'committed', start: i * 3, end: i * 3 + 1, ops: [chosen[i], { type: 'write', key: writeKeys[i], version: versions[i] }] })) }, 'completion');
        }
        for (const x of permutations(finalByKey.x)) for (const y of permutations(finalByKey.y)) {
          for (const model of ['serializable', 'strict-serializable']) {
            check({ schemaVersion: 1, model, initial: { x: 'x0', y: 'y0' }, versionOrders: { x: ['x0', ...x], y: ['y0', ...y] }, transactions: ids.map((id, i) => ({ id, status: 'committed', start: i * 3, end: i * 3 + 1, ops: [chosen[i], { type: 'write', key: writeKeys[i], version: versions[i] }] })) }, 'exhaustive');
          }
        }
      }
      chooseReads([]);
    }
  }

  // Fixed seed. Half start from actual serial executions; half perturb read
  // sources and orders. Multiple own writes, repeated reads and three keys are
  // covered; all assertions are still checked by replay, not by expected labels.
  let seed = 0x51A17E;
  function random(max) {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    return (seed >>> 0) % max;
  }
  function shuffle(items) {
    const a = [...items];
    for (let i = a.length - 1; i > 0; i--) { const j = random(i + 1); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  }
  for (let sample = 0; sample < 1000; sample++) {
    const initial = { x: 'x0', y: 'y0', z: 'z0' };
    const state = { ...initial };
    const orders = { x: ['x0'], y: ['y0'], z: ['z0'] };
    const transactions = [];
    for (let i = 0; i < 2 + sample % 3; i++) {
      const ops = [];
      const last = new Map();
      for (let j = 0; j < 2 + random(4); j++) {
        const key = ['x', 'y', 'z'][random(3)];
        if (random(3) === 0) {
          const version = `${key}-s${sample}-t${i}-o${j}`;
          state[key] = version; last.set(key, version);
          ops.push({ type: 'write', key, version });
        } else ops.push({ type: 'read', key, version: state[key] });
      }
      for (const [key, version] of last) orders[key].push(version);
      transactions.push({ id: `G${i}`, status: 'committed', start: i * 3, end: i * 3 + 1, ops });
    }
    if (sample % 2) {
      const sources = Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, [v]]));
      for (const t of transactions) for (const op of t.ops) if (op.type === 'write') sources[op.key].push(op.version);
      for (const t of transactions) for (const op of t.ops) if (op.type === 'read' && random(2)) op.version = sources[op.key][random(sources[op.key].length)];
      for (const key of Object.keys(orders)) orders[key] = [initial[key], ...shuffle(orders[key].slice(1))];
    }
    const history = { schemaVersion: 1, model: sample % 4 < 2 ? 'serializable' : 'strict-serializable', initial, versionOrders: orders, transactions: shuffle(transactions) };
    check(history, 'generated');
    const partial = Object.fromEntries(Object.entries(orders).filter(([key]) => sample % 2 === 0 && key !== 'x'));
    check({ ...history, versionOrders: partial }, 'completion');
  }
  assert.equal(counts.exhaustive, 6192);
  assert.equal(counts.completion, 3128);
  const receipt = { tool: 'MoonTxnWitness', version: JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version, passed: true, method: 'Independent full serial-order enumeration and register replay; DFS shortest-cycle comparison', seed: '0x51A17E', counts, elapsedMs: Math.round(performance.now() - started) };
  mkdirSync(resolve(root, 'verification'), { recursive: true });
  writeFileSync(resolve(root, 'verification/oracle.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(`Independent oracle: ${counts.exhaustive + counts.generated + counts.completion} histories agree; ${counts.certificates} cycle certificates verified.`);
  return receipt;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) runOracle();
