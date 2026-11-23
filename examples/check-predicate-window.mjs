import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';

try {
  const {values: args} = parseArgs({options: {
    capsule: {type: 'string'}, config: {type: 'string'}, policy: {type: 'string'},
    runtime: {type: 'string'}, 'max-checks': {type: 'string'},
  }});
  if (!args.capsule || !args.config || !args.policy) {
    throw new Error('Use --capsule FILE --config FILE --policy FILE [--runtime DIR] [--max-checks N]');
  }
  const maxChecks = args['max-checks'] ?? '1000000';
  if (!/^(0|[1-9][0-9]{0,6})$/.test(maxChecks) || Number(maxChecks) > 1_000_000) {
    throw new Error('max-checks must be an integer from 0 to 1000000');
  }
  const runtime = args.runtime ? pathToFileURL(resolve(args.runtime, 'configured-predicate-window-v1.mjs'))
    : new URL('../dist/configured-predicate-window-v1.mjs', import.meta.url);
  const {replayConfiguredPredicateCapsuleV1} = await import(runtime.href);
  const read = async path => new TextDecoder('utf-8', {fatal: true}).decode(await readFile(path));
  const replay = replayConfiguredPredicateCapsuleV1(await read(args.capsule),
    {config: await read(args.config), policy: await read(args.policy), maxChecks: Number(maxChecks)});
  const code = replay.valid && replay.kind === 'analysis' ? (replay.status === 'refuted' ? 1 : 0) : 2;
  console.log(JSON.stringify({accepted: code === 0, verifiedRefutation: code === 1,
    reportMatches: replay.reportMatches, status: replay.status}));
  process.exitCode = code;
} catch (error) {
  console.log(JSON.stringify({accepted: false, verifiedRefutation: false,
    reportMatches: false, status: 'unknown', reason: error.message}));
  process.exitCode = 2;
}
