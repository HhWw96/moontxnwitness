import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, existsSync, mkdtempSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { analyze, version } from '../dist/sdk.mjs';
import { root } from './moon.mjs';

export function runCliTests() {
  mkdirSync(resolve(root, 'artifacts/test-work'), { recursive: true });
  const work = mkdtempSync(resolve(root, 'artifacts/test-work/run-'));
  const cli = resolve(root, 'dist/moontxnwitness.mjs');
  const fixture = name => resolve(root, `examples/${name}.json`);
  const checks = [];
  function test(name, fn) { fn(); checks.push(name); }
  function run(args, status, input) {
    const result = spawnSync(process.execPath, [cli, ...args], { cwd: root, input, encoding: 'utf8', timeout: 30000, maxBuffer: 8 * 1024 * 1024 });
    assert.ifError(result.error);
    assert.equal(result.status, status, `${args.join(' ')}\n${result.stdout}\n${result.stderr}`);
    return result;
  }
  function json(name) { return JSON.parse(readFileSync(fixture(name), 'utf8')); }
  function tempJson(name, obj) { const path = resolve(work, name); writeFileSync(path, JSON.stringify(obj)); return path; }
  test('version is 0.0.1', () => { assert.equal(version(), '0.0.1'); assert.equal(run(['--version'], 0).stdout.trim(), '0.0.1'); });
  test('help and no arguments are usable', () => { assert.match(run(['--help'], 0).stdout, /退出码/); assert.match(run([], 0).stdout, /用法/); });
  for (const [name, status, exit] of [['consistent', 'consistent', 0], ['write-skew', 'violation', 1], ['information-cycle', 'violation', 1], ['unknown-order', 'inconclusive', 3], ['lost-update', 'violation', 1], ['aborted-read', 'violation', 1], ['strict-realtime', 'violation', 1]]) {
    test(`${name} fixture status and exit code`, () => { const r = JSON.parse(run(['check', fixture(name), '--format', 'json'], exit).stdout); assert.equal(r.status, status); });
  }
  test('plain text explains witness', () => { const t = run(['check', fixture('write-skew')], 1).stdout; assert.match(t, /异常环证据/); assert.match(t, /操作下标/); });
  test('Markdown report exports a cycle', () => assert.match(run(['check', fixture('write-skew'), '--format', 'markdown'], 1).stdout, /^# MoonTxnWitness/));
  test('DOT report highlights witness', () => assert.match(run(['check', fixture('write-skew'), '--format', 'dot'], 1).stdout, /penwidth=3/));
  test('standard input', () => assert.equal(JSON.parse(run(['check', '-', '--format', 'json'], 0, readFileSync(fixture('consistent'))).stdout).status, 'consistent'));
  const reportPath = resolve(work, '报告 with spaces.json');
  const proofPath = resolve(work, '环证据.json');
  test('Unicode paths and combined report/witness export', () => { const r = run(['check', fixture('write-skew'), '--format', 'json', '--output', reportPath, '--witness', proofPath], 1); assert.equal(r.stdout, ''); assert.equal(JSON.parse(readFileSync(reportPath, 'utf8')).status, 'violation'); assert.ok(existsSync(proofPath)); });
  test('compact certificate verification', () => assert.equal(JSON.parse(run(['verify', fixture('write-skew'), proofPath], 0).stdout).valid, true));
  test('full report verification', () => assert.equal(JSON.parse(run(['verify', fixture('write-skew'), reportPath], 0).stdout).verifiedEdges, 2));
  for (const [name, mutate] of [
    ['changed edge provenance', p => { p.witness.edges[0].fromVersion = 'forged'; }],
    ['broken transaction path', p => { p.witness.transactions[1] = 'not-a-transaction'; }],
    ['wrong tool version', p => { p.version = '0.0.2'; }],
    ['wrong model', p => { p.model = 'strict-serializable'; }],
    ['wrong verdict', p => { p.status = 'consistent'; }],
    ['repeated cycle source', p => { p.witness.edges[1] = p.witness.edges[0]; }],
  ]) test(`rejects ${name}`, () => { const p = JSON.parse(readFileSync(proofPath, 'utf8')); mutate(p); assert.equal(JSON.parse(run(['verify', fixture('write-skew'), tempJson(`${checks.length}-bad.json`, p)], 2).stdout).valid, false); });
  test('certificate does not fit unrelated history', () => assert.equal(JSON.parse(run(['verify', fixture('consistent'), proofPath], 2).stdout).valid, false));
  test('direct read violation has findings but no cycle', () => { const r = analyze(json('aborted-read')); assert.equal(r.witness, null); assert.ok(r.findings.some(f => f.code === 'aborted_read')); const dest = resolve(work, 'no-cycle.json'); run(['check', fixture('aborted-read'), '--witness', dest], 2); assert.equal(existsSync(dest), false); });
  test('never overwrites an existing report', () => { const before = readFileSync(reportPath); run(['check', fixture('consistent'), '--output', reportPath], 2); assert.deepEqual(readFileSync(reportPath), before); });
  test('output cannot be the input', () => { const before = readFileSync(fixture('consistent')); run(['check', fixture('consistent'), '--output', fixture('consistent')], 2); assert.deepEqual(readFileSync(fixture('consistent')), before); });
  test('report and proof paths must differ', () => { const p = resolve(work, 'same.json'); run(['check', fixture('write-skew'), '--output', p, '--witness', p], 2); assert.equal(existsSync(p), false); });
  test('failed export removes newly reserved companion file', () => { const p = resolve(work, 'rolled-back.json'); run(['check', fixture('write-skew'), '--witness', p, '--output', resolve(work, 'absent-dir/report.json')], 2); assert.equal(existsSync(p), false); });
  test('unknown commands and options', () => { run(['scan'], 2); run(['check', fixture('consistent'), '--oops'], 2); });
  test('unknown format', () => run(['check', fixture('consistent'), '--format', 'html'], 2));
  test('duplicate options', () => run(['check', fixture('consistent'), '--format', 'json', '--format', 'dot'], 2));
  test('missing arguments', () => { run(['check'], 2); run(['check', fixture('consistent'), '--output'], 2); run(['verify', fixture('consistent')], 2); });
  test('extra history arguments', () => run(['check', fixture('consistent'), fixture('consistent')], 2));
  test('missing input file', () => run(['check', resolve(work, 'missing.json')], 2));
  test('invalid UTF-8 input', () => { const p = resolve(work, 'invalid-utf8.json'); writeFileSync(p, Buffer.from([0xC3, 0x28])); run(['check', p], 2); });
  test('bounded file input', () => { const p = resolve(work, 'too-large.json'); writeFileSync(p, ' '.repeat(2 * 1024 * 1024 + 1)); run(['check', p], 2); });
  test('bounded core input', () => assert.equal(analyze(' '.repeat(1048577)).status, 'invalid'));
  test('duplicate object keys rejected', () => { const p = resolve(work, 'duplicate.json'); writeFileSync(p, '{"initial":{},"transactions":[],"transactions":[]}'); assert.equal(JSON.parse(run(['check', p, '--format', 'json'], 2).stdout).status, 'invalid'); });
  test('unknown outcome stays inconclusive', () => { const p = tempJson('unknown.json', { initial: { x: 'x0' }, transactions: [{ id: 'u', status: 'unknown', ops: [] }] }); assert.equal(JSON.parse(run(['check', p, '--format', 'json'], 3).stdout).status, 'inconclusive'); });
  test('semantic invalid input', () => { const p = tempJson('duplicate-tx.json', { initial: {}, transactions: [{ id: 'u', status: 'committed', ops: [] }, { id: 'u', status: 'committed', ops: [] }] }); assert.equal(JSON.parse(run(['check', p, '--format', 'json'], 2).stdout).status, 'invalid'); });
  test('identifier escaping in Markdown and DOT', () => { const h = json('write-skew'); h.transactions[0].id = '<script>[bad]"'; const p = tempJson('escaped.json', h); const md = run(['check', p, '--format', 'markdown'], 1).stdout; assert.equal(md.includes('<script>'), false); const dot = run(['check', p, '--format', 'dot'], 1).stdout; assert.ok(dot.includes('\\"')); });
  test('deterministic JSON output', () => { const a = run(['check', fixture('write-skew'), '--format', 'json'], 1).stdout; const b = run(['check', fixture('write-skew'), '--format', 'json'], 1).stdout; assert.equal(a, b); });
  test('transaction and operation limits', () => { const tooMany = { initial: {}, transactions: Array.from({ length: 513 }, (_, i) => ({ id: `t${i}`, status: 'committed', ops: [] })) }; assert.equal(analyze(tooMany).status, 'invalid'); const manyOps = { initial: { x: 'x0' }, transactions: [{ id: 't', status: 'committed', ops: Array.from({ length: 10001 }, () => ({ type: 'read', key: 'x', version: 'x0' })) }] }; assert.equal(analyze(manyOps).status, 'invalid'); });
  test('actual SQLite transaction capture and CLI import', () => {
    const captured = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), [resolve(root, 'examples/capture_sqlite.py')], { encoding: 'utf8', timeout: 30000 });
    assert.ifError(captured.error); assert.equal(captured.status, 0, captured.stderr);
    const history = JSON.parse(captured.stdout);
    const p = tempJson('sqlite.json', history);
    const report = JSON.parse(run(['check', p, '--format', 'json'], 0).stdout);
    assert.equal(report.status, 'consistent'); assert.equal(report.model, 'strict-serializable');
    assert.deepEqual(report.serialOrder, ['sql-T1', 'sql-T2', 'sql-T3']);
    mkdirSync(resolve(root, 'verification'), { recursive: true });
    writeFileSync(resolve(root, 'verification/sqlite-baseline.json'), JSON.stringify(history, null, 2) + '\n');
    writeFileSync(resolve(root, 'verification/sqlite-report.json'), JSON.stringify(report, null, 2) + '\n');
  });
  const receipt = { tool: 'MoonTxnWitness', version: version(), passed: true, checks: checks.length, names: checks, sqlite: 'actual in-memory SQLite sequential commits; baseline only' };
  mkdirSync(resolve(root, 'verification'), { recursive: true });
  writeFileSync(resolve(root, 'verification/cli.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(`CLI integration: ${checks.length} checks passed, including actual SQLite capture.`);
  return receipt;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) runCliTests();
