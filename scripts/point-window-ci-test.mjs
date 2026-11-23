import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtemp, readFile, rm, rmdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {gunzipSync} from 'node:zlib';
import {makeConfiguredWindowCapsuleV4} from '../dist/configured-window-v2-capsule.mjs';

const data = new URL('../examples/point-window-replay-data/', import.meta.url);
const gate = fileURLToPath(new URL('../examples/check-point-window.mjs', import.meta.url));
const {values} = parseArgs({options: {'candidate-gate': {type: 'string'}}});
const candidate = values['candidate-gate'] && resolve(values['candidate-gate']);
const config = fileURLToPath(new URL('config.json', data));
const policy = fileURLToPath(new URL('policy.json', data));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const receipt = JSON.parse(await readFile(new URL('manifest.json', data), 'utf8'));
const capsule = async name => {
  const path = `${name}.json.gz`;
  const bytes = await readFile(new URL(path, data));
  assert.equal(hash(bytes), receipt.sha256[path]);
  return gunzipSync(bytes, {maxOutputLength: 64 * 1024 * 1024}).toString('utf8');
};
const working = await mkdtemp(join(tmpdir(), 'mtw-point-gate-'));
const written = [];
const coldStartMs = {};
function verdictFor(entry, file, options, code, name) {
  const start = performance.now();
  const run = spawnSync(process.execPath, [entry, '--config', config, '--policy', policy, ...options, file],
    {cwd: working, encoding: 'utf8', timeout: 60_000, windowsHide: true});
  coldStartMs[entry === gate ? 'portable' : 'pointGate'] ??= Number((performance.now() - start).toFixed(3));
  if (run.error) throw run.error;
  assert.equal(run.status, code, name + '\n' + run.stdout + run.stderr);
  return JSON.parse(run.stdout);
}
try {
  const before = await capsule('before');
  const {capsuleSha256: _, ...forged} = JSON.parse(before);
  const report = JSON.parse(forged.reportText);
  report.status = 'checked-compatible';
  report.modelDecision.status = 'checked-compatible';
  forged.reportText = JSON.stringify(report);
  forged.reportSha256 = hash(forged.reportText);
  const altered = JSON.stringify({...forged, capsuleSha256: hash(JSON.stringify(forged))}) + '\n';
  const noEnd = JSON.parse(forged.bundleText);
  delete noEnd.endInputText;
  const missing = makeConfiguredWindowCapsuleV4(JSON.stringify(noEnd), {
    config: await readFile(config, 'utf8'), policy: await readFile(policy, 'utf8'), maxPointChecks: 1_000_000,
  });
  const cases = [
    {name: 'ordered', text: await capsule('ordered'), code: 0, matches: true, status: 'checked-compatible'},
    {name: 'refutation', text: before, code: 1, matches: true, status: 'refuted'},
    {name: 'coverage-gap', text: await capsule('retry'), code: 2, matches: true, status: 'unknown'},
    {name: 'missing-source-snapshot', text: missing, code: 2, matches: true},
    {name: 'rehashed-verdict', text: altered, code: 2, matches: false},
    {name: 'wrong-budget', text: await capsule('ordered'), code: 2, matches: false, options: ['--max-point-checks', '0']},
  ];
  for (const {name, text, code, matches, status, options = []} of cases) {
    const file = join(working, `${name}.json`);
    await writeFile(file, text, {flag: 'wx'});
    written.push(file);
    const verdict = verdictFor(gate, file, options, code, name);
    assert.equal(verdict.accepted, code === 0, name);
    assert.equal(verdict.verifiedRefutation, code === 1, name);
    assert.equal(verdict.reportMatches, matches, name);
    if (status) assert.equal(verdict.status, status, name);
    if (candidate) assert.deepEqual(verdictFor(candidate, file, options, code, name), verdict, name);
  }
  console.log(JSON.stringify({passed: true, cases: cases.map(({name, code}) => ({name, code})),
    ...(candidate ? {sameVerdicts: true, coldStartMs} : {})}));
} finally {
  await Promise.all(written.map(filename => rm(filename, {force: true})));
  await rmdir(working);
}
