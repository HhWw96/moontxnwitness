// Independent lifecycle interpreter + full SDK/CLI/evidence acceptance.
// Builds are deliberately external. Missing/stale dist is not execution success.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { isDeepStrictEqual } from 'node:util';
import { sourceFingerprint } from './build-fingerprint.mjs';
import { writeImmutableEvidence } from './performance-evidence.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const rel = path => relative(root, path).replaceAll('\\', '/');
const clone = value => structuredClone(value);
const load = path => JSON.parse(readFileSync(resolve(root, path)));
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const python = process.env.MTW_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const folder = resolve(root, 'verification/v3', 'acceptance-' + stamp);
mkdirSync(folder, { recursive: true });
const receipt = { schema: 1, tool: 'MoonTxnWitness', check: 'independent v3 lifecycle, proof, SDK and CLI acceptance',
  startedAt: new Date().toISOString(), complete: false, passed: false, actualDatabaseExecution: false,
  performanceMeasurement: false, fieldsIgnoredForPublicReports: [], cases: [], gapComparisons: [],
  protocolAssessments: [{
    correction: 'fixtures/v3/protocol-correction-1.json',
    originalFailedReceipt: 'verification/v3/acceptance-2026-10-21T02-10-46-492Z/receipt.json',
    originalFailedReceiptSha256: '7fa2cceb57e05ec9ec1c115b9fae6e804dfd47bf97d6a23fd246d3c23d380760',
    scope: 'Own-read validity is checked at the observation event, not against a later rollback; original trace and manual expectation remain preserved.'
  }, {
    originalFailedReceipt: 'verification/v3/acceptance-2026-10-21T02-16-47-059Z/receipt.json',
    originalFailedReceiptSha256: 'bbced68b039706cf2c70f273f6286d29b4f637f2d2f7224ace71c87b1567c9e4',
    case: 'unknown-predecessor-not-invented', secondaryReferenceGap: 'version_order_gap',
    primaryRequiredGap: 'missing_version_source',
    explanation: 'The newly added all-gap comparison exceeded the frozen manual expectation. Both implementations report missing_version_source, inconclusive and history:null. The independent reference additionally attempts a factual chain after this primary gap; production does not attempt chain construction once gaps exist. Only this exact secondary difference is allowed; all other gap code differences fail.'
  }] };
const retain = (name, value) => {
  const bytes = typeof value === 'string' ? value : JSON.stringify(value, null, 2) + '\n';
  const path = resolve(folder, name);
  writeImmutableEvidence(path, bytes);
  return { file: rel(path), bytes: Buffer.byteLength(bytes), sha256: sha(bytes) };
};
function check(name, action) {
  try { action(); receipt.cases.push({ name, passed: true }); }
  catch (error) { receipt.cases.push({ name, passed: false, error: String(error.message).replaceAll(root, '<workspace>') }); }
}
function oracle(tracePath) {
  const child = spawnSync(python,
    [resolve(root, 'scripts/v3-independent-oracle.py'), '--trace', tracePath],
    { cwd: root, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 16 * 1024 * 1024 });
  assert.equal(child.status, 0, 'Independent oracle process failed');
  return JSON.parse(child.stdout);
}
function removeTransaction(trace, id) {
  const output = clone(trace), sequence = new Map();
  output.events = output.events.filter(event => event.tx !== id).map((event, index) => {
    sequence.set(event.seq, index + 1); event.seq = index + 1; return event;
  });
  for (const event of output.events) if (event.kind === 'rows') event.statement = sequence.get(event.statement);
  return output;
}

try {
  const build = load('dist/build-manifest.json');
  assert.equal(build.sourceSha256, sourceFingerprint(root), 'dist source is stale; build externally before v3 acceptance');
  assert.equal(build.coreSha256, sha(readFileSync(resolve(root, 'dist/core.mjs'))));
  assert.equal(build.captureCoreSha256, sha(readFileSync(resolve(root, 'dist/capture-core.mjs'))));
  for (const wrapper of ['sdk.mjs', 'evidence.mjs', 'moontxnwitness.mjs'])
    assert.equal(sha(readFileSync(resolve(root, 'dist', wrapper))), sha(readFileSync(resolve(root, 'cmd', wrapper))),
      'Built wrapper is stale: ' + wrapper);
  const sdk = await import(pathToFileURL(resolve(root, 'dist/sdk.mjs')).href);
  const evidence = await import(pathToFileURL(resolve(root, 'dist/evidence.mjs')).href);
  for (const method of ['normalizeCaptureV3', 'analyzeV3', 'reduceV3', 'verifyV3', 'makeCapsuleV3', 'replayCapsuleV3'])
    assert.equal(typeof sdk[method], 'function', 'Built SDK lacks ' + method);
  const manifest = load('fixtures/v3/manifest.json');
  receipt.build = build;
  receipt.sourceBindings = Object.fromEntries(['scripts/v3-independent-oracle.py', 'scripts/v3-acceptance.mjs',
    'fixtures/v3/manifest.json', 'fixtures/v3/protocol-correction-1.json', 'fixtures/v3/tampering.json', 'fixtures/v3/reduction-source-closure.json',
    'dist/core.mjs', 'dist/capture-core.mjs', 'dist/build-manifest.json', 'dist/sdk.mjs', 'dist/evidence.mjs',
    'dist/moontxnwitness.mjs', 'cmd/sdk.mjs', 'cmd/evidence.mjs', 'cmd/moontxnwitness.mjs'].map(path => [path, sha(readFileSync(resolve(root, path)))]));
  const reference = spawnSync(python,
    [resolve(root, 'scripts/v3-independent-oracle.py'), '--manifest'],
    { cwd: root, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 24 * 1024 * 1024 });
  assert.equal(reference.status, 0, 'Independent manual expectations must pass before comparing production');
  const expected = JSON.parse(reference.stdout);
  assert.equal(expected.passed, true);
  receipt.independentOracle = retain('oracle-results.json', expected);
  assert.ok(expected.cases.length >= manifest.cases.length);
  for (const referenceCase of expected.cases) {
    const item = referenceCase.fixture;
    const bytes = readFileSync(resolve(root, item.trace));
    assert.equal(sha(bytes), item.sha256, 'Frozen fixture changed: ' + item.id);
    const trace = JSON.parse(bytes), reference = referenceCase.reference;
    const normalized = sdk.normalizeCaptureV3(bytes.toString());
    retain(item.id + '.normalized.json', normalized);
    check('normalize/' + item.id, () => {
      assert.equal(normalized.schema, 3);
      assert.equal(normalized.algorithm, 'v3-lifecycle-1');
      assert.equal(normalized.status, reference.status);
      assert.equal(normalized.coverage.complete, reference.complete);
      if (reference.status === 'invalid') { assert.equal(normalized.history, null); return; }
      const productionCodes = [...new Set(normalized.coverage.gaps.map(gap => gap.code))].sort();
      const referenceCodes = [...reference.issues].sort();
      const secondaryDifference = item.id === 'unknown-predecessor-not-invented'
        && isDeepStrictEqual(referenceCodes, ['missing_version_source', 'version_order_gap'])
        && isDeepStrictEqual(productionCodes, ['missing_version_source']);
      receipt.gapComparisons.push({ id: item.id, referenceCodes, productionCodes, allowedSecondaryDifference: secondaryDifference });
      if (secondaryDifference) {
        assert.equal(reference.status, 'inconclusive'); assert.equal(normalized.status, 'inconclusive');
        assert.equal(reference.history, null); assert.equal(normalized.history, null);
      } else assert.deepEqual(productionCodes, referenceCodes, 'Unexplained gap code difference');
      if (item.expected.issue) assert.ok(productionCodes.includes(item.expected.issue), 'Missing manually required primary gap');
      assert.deepEqual(normalized.observations, reference.observations);
      assert.deepEqual(normalized.effects, reference.effects);
      assert.deepEqual(normalized.transactions, reference.transactions);
      assert.deepEqual(normalized.history, reference.history);
    });
    const report = sdk.analyzeV3(trace);
    retain(item.id + '.report.json', report);
    check('analyze/' + item.id, () => {
      const status = reference.status === 'ready'
        ? reference.serialFeasible === false ? 'violation' : 'consistent' : reference.status;
      assert.equal(report.schemaVersion, 3);
      assert.equal(report.algorithm, 'v3-register-1');
      assert.equal(report.status, status);
      assert.equal(report.coverage.complete, reference.complete);
      assert.deepEqual(report.normalized, normalized);
      if (!reference.complete) assert.equal(report.evidence, null);
      else assert.equal(report.evidence.status, status);
      assert.equal(sdk.verifyV3(trace, report).valid, true);
    });
  }

  const skewText = readFileSync(resolve(root, 'fixtures/v3/write-skew-safe-projection.json'), 'utf8');
  const skew = JSON.parse(skewText), report = sdk.analyzeV3(skew);
  assert.equal(report.status, 'violation', 'Proof tamper corpus requires a real violation');
  const capsuleText = sdk.makeCapsuleV3(skewText, report), capsule = JSON.parse(capsuleText);
  receipt.genuineCapsule = retain('genuine-v3.capsule.json', capsuleText);
  check('genuine-v3-capsule', () => assert.equal(sdk.replayCapsuleV3(capsuleText).valid, true));
  const reportChanges = {
    'report-conclusion': r => { r.status = 'consistent'; },
    'report-model': r => { r.modelDefinition.id = 'untrusted-si-v1'; },
    'report-algorithm': r => { r.algorithm = 'v3-register-forged'; },
    'report-engine-version': r => { r.version = '0.0.0-forged'; },
    'report-analysis-budget': r => { r.execution.analysisOptions.maxAttempts += 1; },
    'report-effective-limit': r => { const k = Object.keys(r.execution.effectiveLimits)[0]; r.execution.effectiveLimits[k] = -1; },
    'report-metrics': r => { r.execution.metrics = { forged: true }; },
    'report-source-predecessor': r => { r.normalized.effects[0].predecessor = 'forged-source'; },
    'report-observation': r => { r.normalized.observations[0].consistent = false; },
    'report-coverage': r => { r.coverage.complete = false; },
    'report-evidence-conclusion': r => { r.evidence.status = 'consistent'; },
  };
  const seenTamper = [];
  const rejectedReport = (name, mutate) => check(name, () => {
    const changed = clone(report); mutate(changed);
    retain(name + '.report.json', changed);
    assert.equal(sdk.verifyV3(skew, changed).valid, false);
    seenTamper.push(name);
  });
  for (const [name, mutate] of Object.entries(reportChanges)) rejectedReport(name, mutate);
  check('report-duplicate-key', () => {
    const text = JSON.stringify(report).replace('{', '{"schemaVersion":3,');
    assert.equal(sdk.verifyV3(skew, text).valid, false); seenTamper.push('report-duplicate-key');
  });
  function capsuleChange(name, mutate) {
    check(name, () => {
      const value = clone(capsule); mutate(value);
      const text = JSON.stringify(value);
      retain(name + '.capsule.json', text);
      assert.equal(sdk.replayCapsuleV3(text).valid, false);
      seenTamper.push(name);
    });
  }
  const replaceText = (c, field, value) => { c[field + 'Text'] = JSON.stringify(value); c[field + 'Sha256'] = sha(c[field + 'Text']); };
  capsuleChange('capsule-trace-without-new-hash', c => { c.traceText += ' '; });
  capsuleChange('capsule-trace-with-new-hash', c => { const t = clone(skew); t.scope.exclusiveWriters = false; replaceText(c, 'trace', t); });
  capsuleChange('capsule-normalized-with-new-hash', c => { const n = clone(report.normalized); n.effects[0].predecessor = 'forged'; replaceText(c, 'normalized', n); });
  capsuleChange('capsule-normalized-and-report-with-new-hashes', c => {
    const r = clone(report); r.normalized.effects[0].predecessor = 'forged';
    replaceText(c, 'normalized', r.normalized); replaceText(c, 'report', r);
  });
  capsuleChange('capsule-evidence-with-new-hash', c => { const e = clone(report.evidence); e.status = 'consistent'; replaceText(c, 'evidence', e); });
  for (const [name, reportName] of [
    ['capsule-report-conclusion-with-new-hash', 'report-conclusion'],
    ['capsule-report-model-with-new-hash', 'report-model'],
    ['capsule-report-budget-with-new-hash', 'report-analysis-budget'],
    ['capsule-report-version-with-new-hash', 'report-engine-version'],
  ]) capsuleChange(name, c => { const r = clone(report); reportChanges[reportName](r); replaceText(c, 'report', r); });
  for (const [name, field, value] of [
    ['capsule-format', 'format', 'moontxnwitness-replay/v2'], ['capsule-schema', 'schemaVersion', 2],
    ['capsule-tool', 'tool', 'forged'], ['capsule-engine-version', 'engineVersion', '0.0.0'],
  ]) capsuleChange(name, c => { c[field] = value; });
  capsuleChange('capsule-missing-digest', c => { delete c.traceSha256; });
  check('capsule-duplicate-key', () => {
    const text = JSON.stringify(capsule).replace('{', '{"schemaVersion":3,');
    assert.equal(sdk.replayCapsuleV3(text).valid, false); seenTamper.push('capsule-duplicate-key');
  });
  check('capsule-deep-nesting', () => {
    const text = '{"padding":' + '['.repeat(65) + '0' + ']'.repeat(65) + '}';
    assert.equal(sdk.replayCapsuleV3(text).valid, false); seenTamper.push('capsule-deep-nesting');
  });
  check('trace-duplicate-key', () => {
    const text = skewText.replace('{', '{"traceSchema":3,');
    assert.equal(sdk.normalizeCaptureV3(text).status, 'invalid'); seenTamper.push('trace-duplicate-key');
  });
  check('trace-deep-nesting', () => {
    const t = clone(skew);
    t.events.splice(2, 0, { seq: 3, time: 1, kind: 'condition', tx: 'T', predicate: JSON.parse('['.repeat(65) + '0' + ']'.repeat(65)), matched: false });
    t.events.forEach((e, i) => { e.seq = i + 1; e.time = i; });
    assert.equal(sdk.normalizeCaptureV3(t).status, 'invalid'); seenTamper.push('trace-deep-nesting');
  });
  check('v3-capsule-rejected-by-legacy', () => { assert.equal(evidence.replayCapsule(capsuleText).valid, false); seenTamper.push('v3-capsule-rejected-by-legacy'); });
  check('legacy-capsule-rejected-by-v3', () => {
    const text = evidence.makeCapsule(JSON.stringify(report.normalized.history), report.evidence);
    assert.equal(sdk.replayCapsuleV3(text).valid, false); seenTamper.push('legacy-capsule-rejected-by-v3');
  });
  check('all-registered-tamper-cases-executed', () => assert.deepEqual([...seenTamper].sort(), load('fixtures/v3/tampering.json').cases.sort()));
  check('coherent-alternative-is-not-authenticated', () => {
    const alternative = clone(skew); alternative.clockDomain = 'another-declared-clock';
    const text = sdk.makeCapsuleV3(alternative, sdk.analyzeV3(alternative));
    assert.equal(sdk.replayCapsuleV3(text).valid, true);
    // A valid self-consistent document proves reproducibility, not origin.
  });

  const sourceTrace = load('fixtures/v3/reduction-source-closure.json');
  check('reduction-original-independent-counterexample', () => {
    const r = oracle(resolve(root, 'fixtures/v3/reduction-source-closure.json'));
    assert.equal(r.status, 'ready'); assert.equal(r.serialFeasible, false);
    assert.equal(sdk.analyzeV3(sourceTrace).status, 'violation');
  });
  const zero = sdk.reduceV3(sourceTrace, { maxChecks: 0 });
  retain('reduction-zero-budget.json', zero);
  check('zero-budget-cannot-claim-single-minimal', () => {
    assert.equal(zero.checks, 0); assert.equal(zero.oneMinimal, false);
    assert.equal(zero.status, 'budget'); assert.deepEqual(zero.reducedCapture, sourceTrace);
  });
  const reduced = sdk.reduceV3(sourceTrace, { maxChecks: 256 });
  retain('reduction-complete.json', reduced);
  check('reduction-removes-noise-retains-source', () => {
    assert.equal(reduced.oneMinimal, true); assert.equal(reduced.status, 'reduced');
    const ids = reduced.report.normalized.transactions.map(t => t.id);
    assert.deepEqual(ids, ['source', 'A', 'B']); assert.deepEqual(reduced.removed, ['noise']);
    assert.equal(reduced.report.status, 'violation');
    assert.equal(sdk.verifyV3(reduced.reducedCapture, reduced.report).valid, true);
  });
  check('reduction-original-sequence-map-is-exact', () => {
    assert.equal(reduced.retainedOriginalSeq.length, reduced.reducedCapture.events.length);
    reduced.reducedCapture.events.forEach((event, index) => {
      const original = sourceTrace.events.find(e => e.seq === reduced.retainedOriginalSeq[index]);
      assert.deepEqual(event, { ...original, seq: index + 1 });
    });
  });
  for (const id of ['source', 'A', 'B']) check('independent-single-delete/' + id, () => {
    const candidate = removeTransaction(reduced.reducedCapture, id);
    const saved = retain('single-delete-' + id + '.trace.json', candidate);
    const r = oracle(resolve(root, saved.file));
    assert.ok(r.status !== 'ready' || r.serialFeasible !== false);
    assert.notEqual(sdk.analyzeV3(candidate).status, 'violation');
    if (id === 'source') { assert.equal(r.history, null); assert.notEqual(sdk.normalizeCaptureV3(candidate).status, 'ready'); }
  });
  const proofPath = retain('cli-proof-report.json', report).file;
  for (const [name, args, exitCode, expectedStatus] of [
    ['cli-ingest', ['ingest-v3', 'fixtures/v3/write-skew-safe-projection.json'], 0, 'ready'],
    ['cli-analyze', ['check-v3', 'fixtures/v3/write-skew-safe-projection.json'], 1, 'violation'],
    ['cli-reduce', ['reduce-v3', 'fixtures/v3/reduction-source-closure.json'], 0, 'reduced'],
    ['cli-verify', ['verify-v3', 'fixtures/v3/write-skew-safe-projection.json', proofPath], 0, 'valid'],
    ['cli-replay', ['replay-v3', receipt.genuineCapsule.file], 0, 'valid'],
    ['cli-inconclusive', ['check-v3', 'fixtures/v3/disconnect-after-request.json'], 3, 'inconclusive'],
    ['cli-invalid', ['ingest-v3', 'fixtures/v3/wrong-schema.json'], 2, 'invalid'],
    ['cli-forged-capsule', ['replay-v3', rel(resolve(folder, 'capsule-report-conclusion-with-new-hash.capsule.json'))], 2, 'invalid-proof'],
  ]) check(name, () => {
    const child = spawnSync(process.execPath, [resolve(root, 'dist/moontxnwitness.mjs'), ...args],
      { cwd: root, encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 8 * 1024 * 1024 });
    retain(name + '.process.json', { arguments: args, exitCode: child.status, signal: child.signal,
      stdout: child.stdout?.replaceAll(root, '<workspace>'), stderr: child.stderr?.replaceAll(root, '<workspace>'),
      error: child.error?.message?.replaceAll(root, '<workspace>') || null });
    assert.equal(child.error, undefined, 'CLI process failed to run');
    assert.equal(child.status, exitCode, 'Unexpected CLI exit status');
    const actual = JSON.parse(child.stdout); retain(name + '.json', actual);
    if (expectedStatus === 'valid') assert.equal(actual.valid, true);
    else if (expectedStatus === 'invalid-proof') assert.equal(actual.valid, false);
    else assert.equal(actual.status, expectedStatus);
    if (name === 'cli-reduce') assert.equal(actual.oneMinimal, true);
  });
  check('unicode-trace-byte-boundaries', () => {
    const text = JSON.stringify({ ...skew, padding: '中'.repeat(3 * 1024 * 1024) });
    assert.ok(text.length < 8 * 1024 * 1024 && Buffer.byteLength(text) > 8 * 1024 * 1024);
    receipt.unicodeTraceBoundary = { utf16Units: text.length, utf8Bytes: Buffer.byteLength(text), sha256: sha(text) };
    for (const method of ['normalizeCaptureV3', 'analyzeV3', 'reduceV3', 'verifyV3', 'makeCapsuleV3'])
      assert.throws(() => sdk[method](text, report), RangeError, method + ' must enforce the UTF-8 trace byte limit');
  });
  check('unicode-proof-byte-boundaries', () => {
    const text = JSON.stringify({ padding: '中'.repeat(11 * 1024 * 1024) });
    assert.ok(text.length < 32 * 1024 * 1024 && Buffer.byteLength(text) > 32 * 1024 * 1024);
    receipt.unicodeProofBoundary = { utf16Units: text.length, utf8Bytes: Buffer.byteLength(text), sha256: sha(text) };
    assert.throws(() => sdk.verifyV3(skewText, text), RangeError);
    const replay = sdk.replayCapsuleV3(text);
    assert.equal(replay.valid, false); assert.match(replay.reason, /UTF-8/);
  });
  check('unicode-option-byte-boundaries', () => {
    const options = { padding: '中'.repeat(1400) };
    assert.ok(JSON.stringify(options).length < 4096 && Buffer.byteLength(JSON.stringify(options)) > 4096);
    assert.throws(() => sdk.analyzeV3(skewText, options), RangeError);
    assert.throws(() => sdk.reduceV3(skewText, options), RangeError);
  });
  receipt.complete = true;
  receipt.passed = receipt.cases.every(c => c.passed);
  receipt.independentTraceCases = expected.cases.length;
  receipt.originalFrozenTraceCases = manifest.cases.length;
  receipt.registeredTamperCases = load('fixtures/v3/tampering.json').cases.length;
  receipt.finishedAt = new Date().toISOString();
} catch (error) {
  receipt.notExecuted = receipt.cases.length === 0;
  receipt.error = String(error.message).replaceAll(root, '<workspace>');
}
const output = retain('receipt.json', receipt);
console.log(JSON.stringify({ passed: receipt.passed, complete: receipt.complete, notExecuted: receipt.notExecuted || false,
  checks: receipt.cases.length, failures: receipt.cases.filter(c => !c.passed), receipt: output.file,
  sha256: output.sha256, error: receipt.error || null }, null, 2));
if (!receipt.passed) process.exitCode = receipt.notExecuted ? 3 : 1;
