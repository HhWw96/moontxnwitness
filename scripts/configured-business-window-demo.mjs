import { spawnSync } from 'node:child_process';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const root = fileURLToPath(new URL('..', import.meta.url));
const { values: args } = parseArgs({ options: {
  output: { type: 'string' },
  runtime: { type: 'string' },
  receipt: { type: 'string' },
  bin: { type: 'string' },
  'dsn-env': { type: 'string' },
  upstream: { type: 'string' },
}});
if (!args.output || !args.runtime ||
    (args.receipt ? args.bin || args['dsn-env'] || args.upstream :
      !args.upstream || Boolean(args.bin) === Boolean(args['dsn-env']))) {
  throw new Error('Use --output DIR --runtime DIST with --receipt FILE, or with --upstream REPO and exactly one of --bin PG_BIN / --dsn-env DISPOSABLE_DSN');
}

const output = resolve(args.output);
const runtime = resolve(args.runtime);
const evidence = args.receipt ? resolve(args.receipt) : resolve(output, 'database', 'receipt.json');
const node = process.execPath;
const python = process.env.MTW_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const run = (executable, command) => {
  const result = spawnSync(executable, command, { cwd: root, stdio: 'inherit', windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(command[0] + ' failed with status ' + result.status);
};
await mkdir(output);
if (!args.receipt) {
  const database = args.bin ? ['--bin', resolve(args.bin)] :
    ['--dsn-env', args['dsn-env'], '--owned-database'];
  run(python, ['-B', 'scripts/configured-source-v2-postgres.py', ...database,
    '--output', resolve(output, 'database'), '--with-window', '--with-analysis', '--with-reduction',
    '--with-async', '--with-sqlalchemy', '--fastapi-users-checkout', resolve(args.upstream),
    '--fastapi-users-seed-campaign']);
}
const original = JSON.parse(await readFile(evidence, 'utf8'));
if (original.fastapiUsersSeedCampaign !== true) {
  throw new Error('The selected receipt does not contain the fixed business seed campaign');
}
const core = resolve(runtime, 'sql-projection-v2-core.mjs');
run(node, ['scripts/configured-window-v2-check.mjs', '--core', core, '--receipt', evidence,
  '--output', resolve(output, 'analysis-checks.json')]);
run(node, ['scripts/configured-window-reduction-v2-check.mjs', '--core', core, '--receipt', evidence,
  '--output', resolve(output, 'reduction', 'checks.json')]);
run(node, ['scripts/configured-window-v2-capsule-test.mjs', '--runtime', runtime, '--receipt', evidence,
  '--output', resolve(output, 'capsule-checks.json')]);
run(node, ['scripts/stage-orm-point-window-gates.mjs', '--runtime', runtime, '--receipt', evidence,
  '--output', resolve(output, 'orm-gate')]);
