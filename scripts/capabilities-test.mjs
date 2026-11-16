import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const runtime = resolve(root, 'dist');
const declarationBytes = readFileSync(resolve(root, 'docs/feature-matrix-v4.json'));
const declaration = JSON.parse(declarationBytes);
const core = await import(pathToFileURL(resolve(runtime, 'core.mjs')));
const sdk = await import(pathToFileURL(resolve(runtime, 'sdk.mjs')));
const manifest = JSON.parse(readFileSync(resolve(runtime, 'build-manifest.json')));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
let checks = 0;
function check(action) { action(); checks++; }
function run(args, {folder = runtime, cwd = root, status = 0} = {}) {
  const result = spawnSync(process.execPath, [resolve(folder, 'moontxnwitness.mjs'), ...args], {
    cwd, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 1024 * 1024,
  });
  assert.ifError(result.error);
  assert.equal(result.status, status, result.stderr);
  return result;
}

check(() => assert.deepEqual(readFileSync(resolve(runtime, 'feature-matrix-v4.json')), declarationBytes));
for (const [name, source] of [['capabilities.mjs', 'cmd/capabilities.mjs'], ['feature-matrix-v4.json', 'docs/feature-matrix-v4.json']]) {
  check(() => assert.equal(manifest.runtimeAssetSha256[name], sha256(readFileSync(resolve(root, source)))));
}
const json = run(['capabilities', '--format', 'json']);
const report = JSON.parse(json.stdout);
check(() => assert.equal(json.stderr, ''));
check(() => assert.equal(report.format, 'moontxnwitness-capabilities/v1'));
check(() => assert.equal(report.version, core.version()));
check(() => assert.equal(report.analysisPerformed, false));
check(() => assert.equal(report.declaration.sha256, sha256(declarationBytes)));
check(() => assert.deepEqual(report.declaration, {asset: 'feature-matrix-v4.json', sha256: sha256(declarationBytes), ...declaration}));
check(() => assert.deepEqual(report.runtime.sdkFunctionExports, Object.keys(sdk).filter(name => typeof sdk[name] === 'function').sort()));
check(() => assert.deepEqual(report.runtime.modelNames, [...sdk.ELLE_CORE_MODELS_V4]));
check(() => assert.equal(report.runtime.declaredModelNamesMatchRuntime, true));
check(() => assert.ok(Object.values(report.runtime.declaredSdkApis).every(value => value === true)));
for (const [name, available] of Object.entries(report.runtime.nativeModelReportExports)) {
  check(() => assert.equal(available, typeof core[name] === 'function'));
}
const text = run(['capabilities']);
check(() => assert.equal(text.stderr, ''));
check(() => assert.equal(run(['capabilities', '--format', 'text']).stdout, text.stdout));
check(() => assert.ok(text.stdout.startsWith(`MoonTxnWitness v${core.version()} capabilities\n`)));
check(() => assert.ok(text.stdout.includes('General SQL/ORM instrumentation')));
check(() => assert.ok(text.stdout.includes('source-closed window')));
check(() => assert.ok(run(['--help']).stdout.includes('capabilities [--format json|text]')));
for (const args of [
  ['--format'], ['--format', '--format'], ['--format', 'yaml'], ['--format=json'],
  ['--format', 'json', '--format', 'text'], ['--output', 'report.json'], ['input.json'], ['--help'],
]) {
  const result = run(['capabilities', ...args], {status: 2});
  check(() => assert.equal(result.stdout, ''));
  check(() => assert.ok(result.stderr.startsWith('MoonTxnWitness: ')));
}

// A relocated discovery runtime has no cmd/docs/source checkout or historical
// payloads and is invoked from another cwd. It uses only the adjacent asset.
const work = mkdtempSync(join(tmpdir(), 'mtw-capabilities-'));
try {
  const portable = join(work, 'portable');
  mkdirSync(portable);
  for (const entry of readdirSync(runtime, {withFileTypes: true})) {
    if (entry.isFile() && (entry.name.endsWith('.mjs') || ['feature-matrix-v4.json', 'build-manifest.json'].includes(entry.name))) {
      copyFileSync(join(runtime, entry.name), join(portable, entry.name));
    }
  }
  const before = readdirSync(work).sort();
  check(() => assert.equal(run(['capabilities', '--format', 'json'], {folder: portable, cwd: work}).stdout, json.stdout));
  check(() => assert.equal(run(['capabilities'], {folder: portable, cwd: work}).stdout, text.stdout));
  check(() => assert.deepEqual(readdirSync(work).sort(), before));
} finally { rmSync(work, {recursive: true, force: true}); }
console.log(JSON.stringify({passed: true, checks, analysisPerformed: false, actualDatabaseExecution: false}));
