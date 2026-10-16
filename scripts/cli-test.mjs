import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, existsSync, mkdtempSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { analyze, analyzeWithOptions, version, shrink, shrinkWithOptions, compareModels, replayReport } from '../dist/sdk.mjs';
import { noisy as noisyHistoryFixture } from './benchmark-fixtures.mjs';
import { root } from './moon.mjs';

export function runCliTests() {
  const release = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8')).version;
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
  test('version matches release metadata', () => { assert.equal(version(), release); assert.equal(run(['--version'], 0).stdout.trim(), release); });
  test('v0.0.7 exhaustive-search capsule preserves v1 replay counts', () => assert.equal(JSON.parse(run(['replay', fixture('legacy-v0.0.7.capsule')], 0).stdout).valid, true));
  test('help and no arguments are usable', () => { assert.match(run(['--help'], 0).stdout, /退出码/); assert.match(run([], 0).stdout, /用法/); });
  test('balanced CLI exports and replays a v2 negative proof', () => {
    const capsule = resolve(work, 'balanced.capsule.json');
    const r = JSON.parse(run(['check', fixture('fractured-observation'), '--profile', 'balanced', '--format', 'json', '--capsule', capsule], 1).stdout);
    assert.equal(r.schemaVersion, 2); assert.equal(r.search.status, 'exhausted'); assert.equal(r.effectiveLimits.transactions, 12);
    assert.equal(JSON.parse(readFileSync(capsule, 'utf8')).format, 'moontxnwitness-replay/v2');
    assert.equal(JSON.parse(run(['replay', capsule], 0).stdout).valid, true);
    const damaged=JSON.parse(readFileSync(capsule,'utf8'));const report=JSON.parse(damaged.reportText);report.effectiveLimits.attempts=0;
    damaged.reportText=JSON.stringify(report);damaged.reportSha256=createHash('sha256').update(damaged.reportText).digest('hex');
    assert.equal(JSON.parse(run(['replay',tempJson('changed-budget.capsule.json',damaged)],2).stdout).valid,false);
  });
  test('balanced SDK budgets and legacy default remain distinct', () => {
    const h={initial:{x:'x0'},transactions:Array.from({length:12},(_,i)=>({id:`T${i}`,status:'committed',ops:[{type:'write',key:'x',version:`v${i}`}]}))};
    assert.equal(analyze(h).status,'inconclusive');assert.equal(analyzeWithOptions(h).status,'consistent');
    const r=analyzeWithOptions(h,{maxAttempts:0});assert.equal(r.status,'inconclusive');assert.equal(r.search.status,'budget');
    assert.equal(replayReport(h,r).valid,true);
    assert.equal(analyzeWithOptions(h,{maxAttempts:-1}).status,'invalid');
    run(['check',fixture('consistent'),'--profile','unknown'],2);
  });
  test('balanced large reduction 512 to 2 preserves source facts and replays', () => {
    const h=noisyHistoryFixture(512);const input=tempJson('large-history.json',h);
    const result=JSON.parse(run(['shrink',input,'--profile','balanced'],0).stdout);
    assert.equal(result.reducedHistory.transactions.length,2);assert.equal(result.oneMinimal,true);assert.ok(result.checks<=4);
    assert.deepEqual(result.reducedHistory.initial,h.initial);assert.deepEqual(result.reducedHistory.versionOrders,{});
    assert.equal(replayReport(result.reducedHistory,result.report).valid,true);
    assert.equal(shrink(h).status,'skipped');
    const limited=shrinkWithOptions(h,{maxChecks:1});assert.equal(limited.status,'budget');assert.equal(limited.oneMinimal,false);
    assert.equal(shrinkWithOptions(h,{maxChecks:257}).status,'invalid');
  });
  for (const [name, status, exit] of [['consistent', 'consistent', 0], ['write-skew', 'violation', 1], ['information-cycle', 'violation', 1], ['unknown-order', 'consistent', 0], ['lost-update', 'violation', 1], ['aborted-read', 'violation', 1], ['strict-realtime', 'violation', 1], ['fractured-observation', 'violation', 1]]) {
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
    ['wrong tool version', p => { p.version = '999.0.0'; }],
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
  const noisy = json('write-skew');
  noisy.transactions = [{ id: 'noise-before', status: 'committed', ops: [] }, ...noisy.transactions, { id: 'noise-after', status: 'committed', ops: [] }];
  const noisyPath = tempJson('noisy.json', noisy);
  test('SDK reduction retains only necessary transactions', () => { const r = shrink(noisy); assert.equal(r.oneMinimal, true); assert.equal(r.reducedHistory.transactions.length, 2); assert.equal(r.report.status, 'violation'); });
  test('CLI reduction exports an independently checkable history', () => { const output = resolve(work, 'reduction.json'); const mini = resolve(work, 'mini.json'); run(['shrink', noisyPath, '--output', output, '--history', mini], 0); assert.equal(JSON.parse(readFileSync(output, 'utf8')).oneMinimal, true); assert.equal(JSON.parse(run(['check', mini, '--format', 'json'], 1).stdout).stats.transactions, 2); });
  test('reduction does not label a consistent source as a counterexample', () => assert.equal(JSON.parse(run(['shrink', fixture('consistent')], 2).stdout).status, 'not-violation'));
  test('exact-search violation can be reduced', () => { const r = JSON.parse(run(['shrink', fixture('fractured-observation')], 0).stdout); assert.equal(r.oneMinimal, true); assert.equal(r.report.search.status, 'exhausted'); });
  test('reduction output does not overwrite its input', () => run(['shrink', noisyPath, '--history', noisyPath], 2));
  test('reduction rejects duplicate or missing options', () => { run(['shrink', noisyPath, '--output', 'x', '--output', 'y'], 2); run(['shrink', noisyPath, '--history'], 2); });
  test('model comparison isolates a realtime-only violation', () => { const r = JSON.parse(run(['compare-models', fixture('strict-realtime')], 0).stdout); assert.equal(r.classification, 'realtime-only-violation'); assert.equal(r.serializable.status, 'consistent'); assert.equal(r.strictSerializable.status, 'violation'); });
  test('model comparison keeps missing intervals inconclusive', () => assert.equal(compareModels(json('consistent')).classification, 'inconclusive'));
  test('old v0.0.1 compact cycle certificate remains verifiable', () => assert.equal(JSON.parse(run(['verify', fixture('write-skew'), resolve(root, 'examples/legacy-v0.0.1.witness.json')], 0).stdout).valid, true));
  test('SDK semantic replay checks counts and findings', () => { const h = json('write-skew'); const r = analyze(h); assert.equal(replayReport(h, r).valid, true); r.stats.transactions++; assert.equal(replayReport(h, r).valid, false); });
  const capsulePath = resolve(work, '复现包.json');
  test('capsule works after reading only its own file', () => { run(['check', fixture('write-skew'), '--capsule', capsulePath], 1); const result = JSON.parse(run(['replay', capsulePath], 0).stdout); assert.equal(result.valid, true); assert.equal(result.status, 'violation'); });
  test('capsules support consistent histories and non-cycle violations', () => { for (const [name, exit] of [['unknown-order', 0], ['fractured-observation', 1], ['aborted-read', 1]]) { const p = resolve(work, `capsule-${name}.json`); run(['check', fixture(name), '--capsule', p], exit); assert.equal(JSON.parse(run(['replay', p], 0).stdout).valid, true); } });
  const digest = text => createHash('sha256').update(text, 'utf8').digest('hex');
  test('capsule rejects changed source content before semantic replay', () => { const c = JSON.parse(readFileSync(capsulePath, 'utf8')); c.historyText += ' '; const p = tempJson('bad-source-capsule.json', c); assert.equal(JSON.parse(run(['replay', p], 2).stdout).valid, false); });
  test('capsule rejects changed report content before semantic replay', () => { const c = JSON.parse(readFileSync(capsulePath, 'utf8')); c.reportText += ' '; assert.equal(JSON.parse(run(['replay', tempJson('bad-report-capsule.json', c)], 2).stdout).valid, false); });
  test('updated hashes cannot disguise a manufactured conclusion', () => { const c = JSON.parse(readFileSync(capsulePath, 'utf8')); const r = JSON.parse(c.reportText); r.status = 'consistent'; c.reportText = JSON.stringify(r); c.reportSha256 = digest(c.reportText); assert.equal(JSON.parse(run(['replay', tempJson('forged-conclusion.json', c)], 2).stdout).valid, false); });
  test('updated source hash cannot bind an unrelated old report', () => { const c = JSON.parse(readFileSync(capsulePath, 'utf8')); c.historyText = readFileSync(fixture('consistent'), 'utf8'); c.historySha256 = digest(c.historyText); assert.equal(JSON.parse(run(['replay', tempJson('wrong-binding.json', c)], 2).stdout).valid, false); });
  test('capsule rejects duplicate fields and malformed headers', () => { const text = JSON.stringify(JSON.parse(readFileSync(capsulePath, 'utf8'))); const p = resolve(work, 'duplicate-capsule.json'); writeFileSync(p, text.slice(0, -1) + ',"schemaVersion":1}'); assert.equal(JSON.parse(run(['replay', p], 2).stdout).valid, false); const c = JSON.parse(text); c.format = 'other/v1'; assert.equal(JSON.parse(run(['replay', tempJson('wrong-format.json', c)], 2).stdout).valid, false); });
  test('capsule path cannot overwrite the input or report', () => { run(['check', fixture('write-skew'), '--capsule', fixture('write-skew')], 2); const p = resolve(work, 'duplicate-output.json'); run(['check', fixture('write-skew'), '--output', p, '--capsule', p], 2); assert.equal(existsSync(p), false); });
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
  test('human reports explain searched order provenance in Chinese', () => { const text = run(['check', fixture('unknown-order')], 0).stdout; assert.match(text, /非观测事实/); assert.match(text, /只证明存在/); });
  test('coverage exposes source gaps and concrete next collection steps', () => { const h = { initial: { x: 'x0' }, transactions: [{ id: 'R', status: 'committed', ops: [{ type: 'read', key: 'x', version: 'outside' }] }] }; const r = analyze(h); assert.equal(r.coverage[0].unresolvedReads, 1); assert.ok(r.nextSteps.some(s => s.includes('采集窗口'))); assert.equal(r.status, 'inconclusive'); });
  test('acyclic graph skips cycle breadth-first search', () => { const r = analyze(json('consistent')); assert.equal(r.graph.bfsRoots, 0); assert.equal(r.graph.cyclicTransactions, 0); });
  const concurrentRuns = [];
  test('actual two-thread SQLite WAL races, aborts and retries', () => {
    for (let repetition = 0; repetition < 3; repetition++) {
      const captured = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), [resolve(root, 'examples/capture_sqlite_concurrent.py'), '--rounds', '2'], { encoding: 'utf8', timeout: 30000 });
      assert.ifError(captured.error); assert.equal(captured.status, 0, captured.stderr);
      const history = JSON.parse(captured.stdout);
      const metadata = JSON.parse(captured.stderr);
      assert.equal(metadata.actualDatabaseExecution, true); assert.equal(metadata.journalMode, 'wal');
      assert.equal(metadata.workers, 2); assert.equal(metadata.committed, 4); assert.equal(metadata.aborted, 2);
      const report = analyze(history);
      assert.equal(report.status, 'consistent'); assert.equal(report.complete, true);
      assert.equal(report.serialOrder.length, 4); assert.equal(compareModels(history).classification, 'compatible-with-both');
      assert.equal(replayReport(history, report).valid, true);
      concurrentRuns.push(metadata);
      if (repetition === 0) {
        writeFileSync(resolve(root, 'verification/sqlite-concurrent.json'), JSON.stringify(history, null, 2) + '\n');
        writeFileSync(resolve(root, 'verification/sqlite-concurrent-report.json'), JSON.stringify(report, null, 2) + '\n');
      }
    }
  });
  test('concurrent capture never overwrites an existing output', () => {
    const p = resolve(work, 'existing-sqlite-capture.json'); writeFileSync(p, 'keep');
    const result = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), [resolve(root, 'examples/capture_sqlite_concurrent.py'), p, '--rounds', '1'], { encoding: 'utf8', timeout: 30000 });
    assert.notEqual(result.status, 0); assert.equal(readFileSync(p, 'utf8'), 'keep');
  });
  test('one-command demo exports a reduced and independently replayable case', () => {
    const demo = spawnSync(process.execPath, [resolve(root, 'dist/demo.mjs'), '--json'], { cwd: work, encoding: 'utf8', timeout: 30000 });
    assert.ifError(demo.error); assert.equal(demo.status, 0, demo.stderr);
    const receipt = JSON.parse(demo.stdout);
    assert.equal(receipt.passed, true); assert.equal(receipt.version, release);
    assert.equal(receipt.profile, 'balanced'); assert.equal(receipt.reportSchemaVersion, 2);
    assert.equal(receipt.oneMinimal, true); assert.equal(receipt.reducedTransactions, 2);
    assert.equal(receipt.classification, 'realtime-only-violation');
    const directory = resolve(work, receipt.outputDirectory);
    for (const file of receipt.files) assert.ok(existsSync(resolve(directory, file)));
    assert.equal(JSON.parse(readFileSync(resolve(directory, 'case.capsule.json'), 'utf8')).format, 'moontxnwitness-replay/v2');
    const mini = JSON.parse(readFileSync(resolve(directory, 'mini.json'), 'utf8'));
    assert.equal(analyze(mini).status, 'violation');
    assert.equal(JSON.parse(run(['replay', resolve(directory, 'case.capsule.json')], 0).stdout).valid, true);
  });
  test('optional PostgreSQL workflow explicitly records missing Python as not executed', () => {
    const result=spawnSync(process.execPath,[resolve(root,'dist/postgres-demo.mjs')],{cwd:work,encoding:'utf8',timeout:30000,env:{...process.env,MTW_PYTHON:resolve(work,'absent-python')}});
    assert.ifError(result.error);assert.equal(result.status,3,result.stderr);
    const r=JSON.parse(result.stdout);assert.equal(r.status,'not-executed');assert.equal(r.passed,false);assert.equal(r.actualDatabaseExecution,false);
    const saved=JSON.parse(readFileSync(resolve(r.outputDirectory,'receipt.json'),'utf8'));assert.equal(saved.status,'not-executed');assert.equal(saved.version,release);
  });
  test('PostgreSQL capture without driver or connection configuration cannot pass', () => {
    const env={...process.env};delete env.MTW_PG_DSN;delete env.MTW_PG_CONNECTION_FILE;
    const result=spawnSync(process.env.PYTHON||(process.platform==='win32'?'python':'python3'),[resolve(root,'examples/capture_postgres.py'),'--output',resolve(work,'unexecuted-pg-capture')],{encoding:'utf8',timeout:30000,env});
    assert.ifError(result.error);assert.equal(result.status,3,result.stderr);
    const r=JSON.parse(result.stdout);assert.equal(r.status,'not-executed');assert.equal(r.passed,false);assert.equal(r.actualDatabaseExecution,false);
  });
  const receipt = { tool: 'MoonTxnWitness', version: version(), passed: true, checks: checks.length, names: checks, sqlite: 'actual in-memory SQLite sequential commits', concurrentRuns };
  mkdirSync(resolve(root, 'verification'), { recursive: true });
  writeFileSync(resolve(root, 'verification/cli.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(`CLI integration: ${checks.length} checks passed, including actual SQLite capture.`);
  return receipt;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) runCliTests();
