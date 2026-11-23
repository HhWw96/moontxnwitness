import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {resolve, join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';

const {values: args} = parseArgs({options: {
  output: {type: 'string'}, runtime: {type: 'string'}, 'dsn-env': {type: 'string'},
}});
assert(args.output && args['dsn-env'], 'Use --dsn-env DISPOSABLE_DSN --output NEW_DIR [--runtime DIST]');
const project = fileURLToPath(new URL('..', import.meta.url));
const runtime = resolve(args.runtime ?? join(project, 'dist'));
const {analyzeConfiguredPredicateWindowV1: analyze, makeConfiguredPredicateCapsuleV1: capsule,
  replayConfiguredPredicateCapsuleV1: replay} = await import(pathToFileURL(join(runtime, 'configured-predicate-window-v1.mjs')));
const read = path => readFile(path, 'utf8');
const write = (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n', {flag: 'wx'});
const digest = text => createHash('sha256').update(text).digest('hex');
const output = resolve(args.output);
await mkdir(output);
const raw = join(output, 'database');
const python = process.env.MTW_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const p = spawnSync(python, ['-B', join(project, 'scripts/predicate-window-postgres.py'),
  '--owned-database', '--reservation-campaign', '--dsn-env', args['dsn-env'], '--output', raw],
  {stdio: 'inherit', windowsHide: true, timeout: 600_000});
if (p.error) throw p.error;
assert.equal(p.status, 0, 'Original reservation campaign did not complete');
const source = JSON.parse(await read(join(raw, 'receipt.json')));
assert(source.passed && source.actualDatabaseExecution && source.postgres === '18.6' && source.rounds.length === 5);

function tamperSnapshot(original) {
  const changed = JSON.parse(original);
  const transaction = changed.transactions.find(tx => tx.calls.some(call => call.parameters[0] === '100'));
  const records = transaction.logText.trimEnd().split('\n').map(JSON.parse);
  for (const row of records) {
    if (row.queryId !== 'transaction-mode') continue;
    if (row.kind === 'control-native') {
      const originalMode = JSON.parse(Buffer.from(row.native.rows[0][0], 'base64').toString('utf8'));
      originalMode.snapshot = '3:3:';
      row.native.rows[0][0] = Buffer.from(JSON.stringify(originalMode)).toString('base64');
    } else if (row.kind === 'control-delivery') {
      const cell = row.observation.rows[0].cells[0];
      cell.value = JSON.stringify({...JSON.parse(cell.value), snapshot: '3:3:'});
    }
  }
  const seal = records.pop();
  const prefix = records.map(value => JSON.stringify(value)).join('\n') + '\n';
  seal.prefixSha256 = digest(prefix);
  transaction.logText = prefix + JSON.stringify(seal) + '\n';
  transaction.logReceipt.sha256 = digest(transaction.logText);
  transaction.logReceipt.bytes = Buffer.byteLength(transaction.logText);
  return JSON.stringify(changed);
}

const rounds = [];
for (const {round, cases} of source.rounds) {
  assert.deepEqual(cases.map(item => item.name), ['before', 'ordered', 'retry']);
  const outcomes = [];
  for (const item of cases) {
    const directory = join(raw, item.directory);
    const original = await read(join(directory, item.path));
    const config = join(directory, 'config.json'), policy = join(directory, 'policy.json');
    const options = {config: await read(config), policy: await read(policy)};
    const status = {before: 'refuted', ordered: 'checked-compatible', retry: 'unknown'}[item.name];
    const code = {before: 1, ordered: 0, retry: 2}[item.name];
    const verdict = analyze(original, options);
    assert.equal(verdict.status, status, item.name + ' ' + JSON.stringify(verdict).slice(0, 1200));
    const encoded = capsule(original, options);
    const decoded = replay(encoded, options);
    assert.equal(decoded.valid, code !== 2);
    assert.equal(decoded.reportMatches, true);
    const gateInput = join(directory, 'analysis-capsule.json');
    await writeFile(gateInput, encoded, {flag: 'wx'});
    const gate = spawnSync(process.execPath, [join(project, 'examples/check-predicate-window.mjs'),
      '--runtime', runtime, '--capsule', gateInput, '--config', config, '--policy', policy],
      {encoding: 'utf8', timeout: 120_000, windowsHide: true});
    assert.equal(gate.status, code, gate.stderr || gate.stdout);
    assert.equal(JSON.parse(gate.stdout).reportMatches, true);
    const result = {...item, status, gate: code};
    if (item.name === 'before') {
      assert.equal(verdict.g2.status, 'refuted');
      assert.equal(verdict.g2Item.status, 'checked-compatible');
      assert.equal(verdict.g2.search.witness.antiDependencies.item, 0);
      assert.equal(verdict.g2.search.witness.antiDependencies.predicate, 2);
      const reduction = capsule(original, options, 'reduction');
      const minimized = replay(reduction, options);
      assert.equal(minimized.valid, true, JSON.stringify(minimized).slice(0, 1400));
      assert.equal(minimized.status, 'reduced');
      const reduced = minimized.report.reduction;
      assert.equal(reduced.oneMinimal, true);
      assert.equal(reduced.sourceCoverage.reducedSourceClosed, true);
      assert.equal(verdict.admission.transactions, 5);
      assert.equal(reduced.history.events.filter(event => event.kind === 'begin').length, 2);
      await writeFile(join(directory, 'reduction-capsule.json'), reduction, {flag: 'wx'});
      assert.equal(replay(encoded, {...options, maxChecks: 0}).valid, false);
      assert.equal(replay(encoded, {...options, maxChecks: 999_999}).reportMatches, false);
      const {capsuleSha256: _, ...forged} = JSON.parse(encoded);
      forged.reportText = JSON.stringify({...JSON.parse(forged.reportText), status: 'checked-compatible'});
      forged.reportSha256 = digest(forged.reportText);
      const rebound = JSON.stringify({...forged, capsuleSha256: digest(JSON.stringify(forged))}) + '\n';
      assert.equal(replay(rebound, options).reportMatches, false);
      const forgedSnapshot = analyze(tamperSnapshot(original), options);
      assert.equal(forgedSnapshot.status, 'unknown');
      assert.match(forgedSnapshot.admission.reason, /predicate-snapshot-outside-window/);
      const missing = JSON.parse(original);
      delete missing.endInputText;
      assert.equal(analyze(JSON.stringify(missing), options).status, 'unknown');
      result.category = 'G2';
      result.predicateAntiDependencies = 2;
      result.original = 5;
      result.reduced = 2;
      result.oneMinimal = true;
    }
    if (item.name === 'retry') assert.equal(item.rollbackSqlstate, '40001');
    outcomes.push(result);
  }
  rounds.push({round, cases: outcomes});
}
const report = {passed: true, actualDatabaseExecution: true, postgres: source.postgres, rounds};
await write(join(output, 'receipt.json'), report);
console.log(JSON.stringify(report));
