// A new registry-only MoonBit consumer runs the same normalized histories as JS.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {gunzipSync} from 'node:zlib';

const {values: args} = parseArgs({options: {
  output: {type: 'string'}, runtime: {type: 'string'}, 'module-version': {type: 'string'},
}});
assert(args.output && args.runtime && /^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$/.test(args['module-version'] ?? ''),
  'Use --module-version X.Y.Z --runtime DIST --output NEW_DIR');
const root = resolve(args.output);
const runtime = resolve(args.runtime);
const {classifyModelsV4} = await import(pathToFileURL(join(runtime, 'models-v4.mjs')).href);
const {version} = await import(pathToFileURL(join(runtime, 'core.mjs')).href);
assert.equal(version(), args['module-version'], 'Use the same SDK and Mooncakes version');
const {replayConfiguredWindowCapsuleV4} = await import(pathToFileURL(join(runtime, 'configured-window-v2-capsule.mjs')).href);
const folder = new URL('../examples/point-window-replay-data/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('manifest.json', folder), 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
async function original(name) {
  const bytes = await readFile(new URL(name, folder));
  assert.equal(hash(bytes), manifest.sha256[name], name);
  return bytes;
}
const modelOptions = {models: ['serializable'], relationProfile: 'captured-relation-row-slots/v1'};
const windowOptions = {config: (await original('config.json')).toString('utf8'),
  policy: (await original('policy.json')).toString('utf8'), maxPointChecks: 1_000_000};
const tests = [];
for (const [name, expected] of [['before', 'refuted'], ['ordered', 'checked-compatible']]) {
  const compressed = await original(name + '.json.gz');
  const capsule = gunzipSync(compressed, {maxOutputLength: 64 * 1024 * 1024}).toString('utf8');
  const replay = replayConfiguredWindowCapsuleV4(capsule, windowOptions);
  assert.equal(replay.valid, true, name);
  assert.equal(replay.status, expected, name);
  const history = JSON.stringify(replay.report.history);
  const js = classifyModelsV4(history, modelOptions);
  assert.equal(js.status, expected, name);
  assert.equal(js.sourceSha256, replay.report.model.sourceSha256, name);
  assert(js.models && typeof js.models === 'object', name);
  assert.deepEqual(js.models, replay.report.model.models, name);
  tests.push({name, history, js});
}

await mkdir(root);
const write = (name, value) => writeFile(join(root, name), value, {flag: 'wx'});
await write('moon.mod', 'name = "consumer/point-window-registry-check"\n');
await write('moon.pkg', 'import { "HhWw96/moontxnwitness" @txn, "moonbitlang/core/json" }\npkgtype(kind: "executable")\n');
const inputs = tests.map(({history}, index) => `  let history${index} =\n    #|${history}\n` +
  `  let report${index} = @txn.classify_models_v4_json(history${index}, options)\n` +
  `  println((try! @json.parse(report${index})).stringify())\n`).join('');
await write('main.mbt', `///|\nfn main {\n  let options =\n    #|${JSON.stringify(modelOptions)}\n` + inputs + '}\n');

const moon = process.env.MOON_HOME
  ? join(process.env.MOON_HOME, 'bin', process.platform === 'win32' ? 'moon.exe' : 'moon') : 'moon';
function run(args) {
  const child = spawnSync(moon, args, {cwd: root, encoding: 'utf8', windowsHide: true, maxBuffer: 16 * 1024 * 1024});
  if (child.error) throw child.error;
  assert.equal(child.status, 0, child.stderr || child.stdout);
  return child.stdout.trim();
}
run(['update']);
run(['add', `HhWw96/moontxnwitness@${args['module-version']}`]);
const packageMetadata = await readFile(join(root, '.mooncakes', 'HhWw96', 'moontxnwitness', 'moon.mod'), 'utf8');
assert(packageMetadata.split(/\r?\n/).includes(`version = "${args['module-version']}"`), 'Installed registry module differs');
const moonReports = run(['run', '--target', 'wasm-gc', '.', '--deny-warn']).split(/\r?\n/).map(line => JSON.parse(line));
assert.equal(moonReports.length, tests.length);
for (const [index, {name, js}] of tests.entries()) {
  assert.equal(moonReports[index].sourceSha256, js.sourceSha256, name);
  assert.equal(moonReports[index].status, js.status, name);
  assert.deepEqual(moonReports[index].models, js.models, name);
}
const result = {passed: true, mooncakesVersion: args['module-version'], runtimeVersion: version(),
  compared: tests.map(({name, js}) => ({name, normalizedHistorySha256: js.sourceSha256, status: js.status}))};
await write('verification.json', JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
