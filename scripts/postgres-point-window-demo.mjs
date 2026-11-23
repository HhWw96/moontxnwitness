// Re-run and independently replay three isolation outcomes in a disposable database.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {gunzipSync} from 'node:zlib';

const {values: args} = parseArgs({options: {
  output: {type: 'string'}, runtime: {type: 'string'},
  bin: {type: 'string'}, 'dsn-env': {type: 'string'},
}});
assert(args.output && args.runtime && Boolean(args.bin) !== Boolean(args['dsn-env']),
  'Use --output NEW_DIR --runtime DIST with exactly one of --bin PG_BIN or --dsn-env DISPOSABLE_DSN');
const root = fileURLToPath(new URL('..', import.meta.url));
const output = resolve(args.output);
const runtime = resolve(args.runtime);
const python = process.env.MTW_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const db = args.bin ? ['--bin', resolve(args.bin)] : ['--dsn-env', args['dsn-env'], '--owned-database'];
const runs = [];
const namespaces = new Set();
const start = Date.now();
await mkdir(output);

function run(executable, script, options, pipe = false) {
  const result = spawnSync(executable, [resolve(root, script), ...options], {
    cwd: root, stdio: ['ignore', pipe ? 'pipe' : 'inherit', 'inherit'],
    encoding: 'utf8', windowsHide: true, timeout: 600_000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${script} exited with status ${result.status}`);
  return result.stdout;
}

let passed = false;
try {
  for (let index = 1; index <= 5; index++) {
    const round = resolve(output, 'round-' + index);
    const database = resolve(round, 'database');
    const receipt = resolve(database, 'receipt.json');
    const fixtures = resolve(round, 'fixtures');
    const capture = spawnSync(python, ['-B', resolve(root, 'scripts/configured-source-v2-postgres.py'),
      ...db, '--output', database, '--with-window', '--with-analysis', '--with-reduction', '--with-async'], {
      cwd: root, stdio: 'inherit', windowsHide: true, timeout: 600_000,
    });
    if (capture.error) throw capture.error;
    assert.equal(capture.status, 0, 'PostgreSQL capture round ' + index);
    if (args['dsn-env']) {
      const raw = JSON.parse(await readFile(receipt, 'utf8'));
      assert.match(raw.fixtureNamespace, /^_[0-9a-f]{10}$/);
      assert(!namespaces.has(raw.fixtureNamespace), 'PostgreSQL rounds must use isolated fixture names');
      namespaces.add(raw.fixtureNamespace);
    }
    run(process.execPath, 'scripts/stage-point-window-replay.mjs', [
      '--runtime', runtime, '--receipt', receipt, '--output', fixtures,
    ]);
    const replay = JSON.parse(run(process.execPath, 'examples/point-window-replay.mjs', [
      '--runtime', runtime, '--fixtures', fixtures, '--html', resolve(round, 'witness.html'),
    ], true));
    assert.deepEqual([replay.passed, replay.capturedPostgreSQLVersion, replay.category,
      replay.originalTransactions, replay.reducedTransactions, replay.oneMinimalVerified],
      [true, '18.6', 'G2-item', 5, 2, true]);
    assert.equal(replay.retry.sqlstate, '40001');
    assert.equal(replay.orderedControl.status, 'checked-compatible');
    await writeFile(resolve(round, 'replay.json'), JSON.stringify(replay, null, 2) + '\n', {flag: 'wx'});
    if (index === 1) {
      for (const name of ['before', 'ordered', 'retry']) {
        const capsule = gunzipSync(await readFile(resolve(fixtures, name + '.json.gz')),
          {maxOutputLength: 64 * 1024 * 1024});
        await writeFile(resolve(fixtures, name + '.capsule.json'), capsule, {flag: 'wx'});
      }
    }
    runs.push({round: index, category: replay.category, original: replay.originalTransactions,
      reduced: replay.reducedTransactions, oneMinimalVerified: replay.oneMinimalVerified,
      retrySqlstate: replay.retry.sqlstate, control: replay.orderedControl.status});
  }
  passed = true;
} finally {
  const result = {passed, actualDatabaseExecution: runs.length > 0, postgres: '18.6',
    elapsedSeconds: (Date.now() - start) / 1000, rounds: runs};
  await writeFile(resolve(output, 'receipt.json'), JSON.stringify(result, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify(result));
}
