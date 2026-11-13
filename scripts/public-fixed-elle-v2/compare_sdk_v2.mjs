// Compare an already sealed upstream-only reference with an independently bound SDK.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { createWriteStream, existsSync, mkdirSync, readFileSync, realpathSync, statSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { finished, pipeline } from 'node:stream/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Worker } from 'node:worker_threads';
import { createGzip } from 'node:zlib';

export const JOB_SHA = '3b78df6d0eb7d74be56cd6946231d52778b3c0159ba40c9bb00a90ce3ac6b338';
export const REFERENCE_SHA = 'd3ebd816971668eb4b7347987b73bc05bf959bc93d2d58e789afc44892acae97';
export const CONTRACT = 'fixed-elle-serializable-original-capture-reference/v2';
export const ELLE = '4e359e597c52938b0afebb8bc42273914d68a424';
const MiB = 1024 * 1024;
export const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const textJson = value => JSON.stringify(value);

export function canonicalAscii(value) {
  const sorted = v => Array.isArray(v) ? v.map(sorted) : v && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])])) : v;
  return JSON.stringify(sorted(value)).replace(/[\u007f-\uffff]/g,
    c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}

export function callerOptions(dataModel) {
  assert(['point-register-v1', 'append-list-v1'].includes(dataModel), 'unsupported data model');
  const options = { models: ['serializable'], maxSourceChecks: 1000000, maxStates: 100000, maxEdgeChecks: 1000000 };
  if (dataModel === 'append-list-v1') options.listProfile = 'captured-list-original-serial/v1';
  return options;
}

export function validateReference(job, reference) {
  assert.equal(reference.semanticContract, CONTRACT);
  assert.equal(reference.fixedElleCommit, ELLE);
  assert.equal(reference.source.jobSha256, JOB_SHA);
  assert.equal(reference.upstreamElleReexecuted, false);
  assert.equal(reference.referenceGenerationPolicy.sdkVerdictsUsedToDeriveExpected, false);
  assert.equal(job.length, 2000);
  assert.equal(reference.cases.length, job.length);
  assert.equal(reference.options['consistency-models'].length, 1);
  assert.equal(reference.options['consistency-models'][0], 'serializable');
  const ids = new Set();
  for (const [index, row] of job.entries()) {
    const item = reference.cases[index];
    assert(!ids.has(row.id), 'duplicate case'); ids.add(row.id);
    assert.equal(item.id, row.id); assert.equal(item.inputSha256, row.inputSha256);
    assert.equal(sha(canonicalAscii(row.input)), row.inputSha256);
    assert.equal(item.dataModel, row.input.dataModel);
    assert.equal(item.targetModel, 'serializable');
    assert.equal(typeof item.comparisonEligible, 'boolean');
    if (item.comparisonEligible) {
      assert.equal(typeof item.validity, 'boolean');
      assert.equal(item.cycleSearchTimeout, false);
      assert.equal(item.originalValidity.kind, 'boolean');
      assert.equal(item.originalValidity.value, item.validity);
    }
  }
  assert.equal(reference.cases.filter(c => c.comparisonEligible).length, 1997);
  assert.equal(reference.counts.comparisonEligible, 1997);
}

export function loadPinnedBytes(bytes, expected) {
  assert.equal(sha(bytes), expected, 'pinned bytes differ');
  return JSON.parse(bytes);
}

export function loadPinned(path, expected) { return loadPinnedBytes(readFileSync(path), expected); }

export function runtimeSnapshot(dist, version, expectedCoreSha) {
  assert.match(expectedCoreSha, /^[a-f0-9]{64}$/);
  const files = {};
  for (const name of ['build-manifest.json', 'models-v4.mjs', 'core.mjs']) {
    const path = resolve(dist, name);
    assert(statSync(path).isFile()); assert(statSync(path).size <= 32 * MiB);
    files[name] = sha(readFileSync(path));
  }
  const build = JSON.parse(readFileSync(resolve(dist, 'build-manifest.json')));
  assert.equal(build.version, version, 'caller SDK version differs');
  assert.equal(files['core.mjs'], expectedCoreSha, 'caller SDK core differs');
  assert.equal(build.coreSha256, files['core.mjs'], 'build/core binding differs');
  return { files, version: build.version, sourceSha256: build.sourceSha256, toolchain: build.toolchain };
}

export function upstreamEvidence(root, item) {
  const read = binding => {
    assert.equal(typeof binding.path, 'string');
    assert(!isAbsolute(binding.path) && !binding.path.includes('\\') && !binding.path.includes(':'));
    assert(!binding.path.split('/').includes('..'));
    const base = realpathSync(root), path = realpathSync(resolve(base, binding.path));
    assert(path.startsWith(base + sep), 'evidence path escapes root');
    assert(statSync(path).size <= 8 * MiB);
    const data = readFileSync(path);
    assert.equal(data.length, binding.bytes); assert.equal(sha(data), binding.sha256);
    return data.toString('utf8');
  };
  return { rawEdn: read(item.raw), summaryText: read(item.summary) };
}

export function outcomeFor(reference, sdkDisposition, sdkVerdict) {
  // Reference eligibility is immutable. SDK unknown/profile changes never add
  // a new exclusion or shrink the sealed 1,997-position denominator.
  if (sdkDisposition === 'failure') return 'failure';
  if (!reference.comparisonEligible) return reference.cycleSearchTimeout ? 'timeout' : 'upstreamNotComparable';
  if (sdkDisposition === 'timeout') return 'timeout';
  if (sdkDisposition === 'unknown') return 'sdkUnknown';
  return sdkVerdict === reference.validity ? 'match' : 'difference';
}

export function evaluateSdkCase(api, row, reference, onPhase = () => {}) {
  const sourceText = canonicalAscii(row.input), requestedOptions = callerOptions(row.input.dataModel);
  const result = { sourceText, callerOptions: structuredClone(requestedOptions),
    classificationAttempted: false, verificationAttempted: false,
    sdkDisposition: 'failure', reportText: null, verification: null };
  try {
    assert.equal(sha(sourceText), row.inputSha256, 'source/input binding');
    result.classificationAttempted = true; onPhase('classify-started');
    const report = api.classifyModelsV4(sourceText, requestedOptions);
    result.reportText = JSON.stringify(report);
    assert.equal(typeof result.reportText, 'string');
    assert(Buffer.byteLength(result.reportText) <= 32 * MiB, 'SDK report byte budget');
    onPhase('classify-returned', { reportText: result.reportText });
    result.verificationAttempted = true; onPhase('verify-started');
    // Fresh caller-authored options; never report.options or an embedded budget.
    result.verification = api.verifyModelsV4(sourceText, result.reportText, callerOptions(row.input.dataModel));
    onPhase('verify-returned');
    assert.equal(result.verification?.valid, true, 'independent caller-options verification rejected report');
    assert.equal(report?.format, 'moontxnwitness-model-composition/v4');
    assert.equal(report?.schemaVersion, 4);
    assert(Array.isArray(report.models) && report.models.length === 1, 'one model report required');
    assert.equal(report.models[0].model, 'serializable');
    result.sdkStatus = report.models[0].status; result.sourceProfile = report.sourceProfile;
    assert(['checked-compatible', 'refuted', 'unknown', 'pending'].includes(result.sdkStatus), 'unexpected model status');
    const expected = row.input.dataModel === 'point-register-v1'
      ? 'captured-register-full-program/v2' : 'captured-list-original-serial/v1';
    if (result.sourceProfile !== expected) {
      result.sdkDisposition = 'unknown'; result.reason = 'unexpected-sdk-source-profile';
    } else if (result.sdkStatus === 'unknown' || result.sdkStatus === 'pending') {
      result.sdkDisposition = 'unknown'; result.reason = 'sdk-model-undetermined';
    } else {
      result.sdkDisposition = 'complete'; result.sdkVerdict = result.sdkStatus === 'checked-compatible';
    }
  } catch (error) {
    result.sdkDisposition = error?.name === 'TimeoutError' ? 'timeout' : 'failure';
    result.reason = String(error?.message || error).slice(0, 4096);
    result.errorType = String(error?.name || 'Error');
  }
  result.outcome = outcomeFor(reference, result.sdkDisposition, result.sdkVerdict);
  return result;
}

class RuntimeWorker {
  constructor(options) { this.options = options; this.worker = null; this.nextId = 0; }
  async start() {
    this.worker = new Worker(new URL('./compare_sdk_v2_worker.mjs', import.meta.url), { workerData: this.options });
    const worker = this.worker;
    await new Promise((resolveReady, reject) => {
      const timer = setTimeout(() => reject(new Error('SDK worker initialization timed out')), 30000);
      const fail = error => { clearTimeout(timer); reject(error); };
      worker.once('error', fail);
      worker.once('exit', code => { if (code !== 0) fail(new Error('SDK worker initialization exit ' + code)); });
      worker.once('message', message => {
        clearTimeout(timer); worker.off('error', fail);
        if (message.kind !== 'ready') reject(new Error('SDK worker initialization failed: ' + JSON.stringify(message)));
        else {
          try { assert.deepEqual(message.snapshot, this.options.snapshot); resolveReady(); }
          catch (error) { reject(error); }
        }
      });
    });
  }
  async run(row, reference, timeoutMs) {
    if (!this.worker) await this.start();
    const worker = this.worker, id = ++this.nextId;
    return await new Promise(resolveCase => {
      let done = false;
      const observed = { classificationAttempted: false, verificationAttempted: false, reportText: null };
      const finish = result => {
        if (done) return; done = true; clearTimeout(timer);
        worker.off('message', message); worker.off('error', failed); worker.off('exit', exited);
        resolveCase(result);
      };
      const failed = error => {
        this.worker = null; void worker.terminate();
        finish({ ...observed, sdkDisposition: 'failure', reason: String(error.message),
          outcome: outcomeFor(reference, 'failure'), verification: null });
      };
      const exited = code => failed(new Error('SDK worker exited during case: ' + code));
      const message = data => {
        if (data.id !== id) return;
        if (data.kind === 'phase') {
          if (data.phase === 'classify-started') observed.classificationAttempted = true;
          if (data.phase === 'verify-started') observed.verificationAttempted = true;
          if (data.payload?.reportText) observed.reportText = data.payload.reportText;
        } else if (data.kind === 'result') finish(data.result);
      };
      const timer = setTimeout(() => {
        this.worker = null; void worker.terminate();
        finish({ ...observed, sdkDisposition: 'timeout', reason: 'sdk-case-wall-clock-timeout',
          outcome: outcomeFor(reference, 'timeout'), verification: null });
      }, timeoutMs);
      worker.on('message', message); worker.once('error', failed); worker.once('exit', exited);
      worker.postMessage({ id, row, reference });
    });
  }
  async close() { if (this.worker) { const worker = this.worker; this.worker = null; await worker.terminate(); } }
}

const outcomes = ['match', 'difference', 'sdkUnknown', 'upstreamNotComparable', 'timeout', 'failure'];
const counts = () => Object.fromEntries(outcomes.map(name => [name, 0]));
const write = async (stream, line) => { if (!stream.write(line)) await once(stream, 'drain'); };

export async function runComparison(args) {
  assert(!existsSync(args.output), 'fresh output directory required');
  const job = loadPinned(args.job, JOB_SHA), reference = loadPinned(args.reference, REFERENCE_SHA);
  validateReference(job, reference);
  const snapshot = runtimeSnapshot(args.runtime, args.expectedVersion, args.expectedCoreSha);
  const client = new RuntimeWorker({ dist: realpathSync(args.runtime), expectedVersion: args.expectedVersion,
    expectedCoreSha: args.expectedCoreSha, snapshot });
  mkdirSync(args.output);
  const gzip = createGzip({ level: 6 });
  const reportPath = resolve(args.output, 'reports.jsonl.gz'), itemPath = resolve(args.output, 'items.jsonl');
  const reportSink = createWriteStream(reportPath, { flags: 'wx' });
  const reportDone = pipeline(gzip, reportSink); reportDone.catch(() => {});
  const items = createWriteStream(itemPath, { flags: 'wx' });
  const itemDone = finished(items); itemDone.catch(() => {});
  const itemDigest = createHash('sha256'), reportDigest = createHash('sha256');
  const totals = counts(), eligibleOutcomes = counts();
  const byDataModel = { 'point-register-v1': counts(), 'append-list-v1': counts() };
  let classifications = 0, verifications = 0, reportBytes = 0, completed = 0, fatal = null;
  const sdkDispositions = { complete: 0, unknown: 0, timeout: 0, failure: 0 };
  try {
    for (const [index, row] of job.entries()) {
      const ref = reference.cases[index], upstream = upstreamEvidence(dirname(args.reference), ref);
      const result = await client.run(row, ref, args.caseTimeoutMs);
      classifications += Number(result.classificationAttempted);
      verifications += Number(result.verificationAttempted);
      const item = { id: row.id, dataModel: row.input.dataModel, inputSha256: row.inputSha256,
        referenceEligible: ref.comparisonEligible, upstreamValidity: ref.validity,
        upstreamCycleSearchTimeout: ref.cycleSearchTimeout, sdkDisposition: result.sdkDisposition,
        sdkStatus: result.sdkStatus ?? null, sourceProfile: result.sourceProfile ?? null,
        outcome: result.outcome, reason: result.reason ?? null,
        classificationAttempted: result.classificationAttempted, verificationAttempted: result.verificationAttempted,
        reportSha256: result.reportText === null ? null : sha(result.reportText),
        callerOptions: callerOptions(row.input.dataModel) };
      const reportLine = textJson({ item, input: row.input, sourceText: result.sourceText ?? canonicalAscii(row.input),
        upstreamReference: ref, upstreamRawEdn: upstream.rawEdn, upstreamSummaryText: upstream.summaryText,
        sdkReportText: result.reportText, sdkVerification: result.verification ?? null,
        errorType: result.errorType ?? null }) + '\n';
      reportBytes += Buffer.byteLength(reportLine);
      assert(reportBytes <= 1024 * MiB, 'uncompressed retained-report budget exceeded; incomplete run');
      reportDigest.update(reportLine); await write(gzip, reportLine);
      const itemLine = textJson(item) + '\n'; itemDigest.update(itemLine); await write(items, itemLine);
      totals[item.outcome]++; byDataModel[item.dataModel][item.outcome]++;
      if (ref.comparisonEligible) eligibleOutcomes[item.outcome]++;
      sdkDispositions[result.sdkDisposition]++; completed++;
    }
  } catch (error) { fatal = String(error?.stack || error); }
  finally {
    await client.close(); gzip.end(); items.end();
    try { await reportDone; await itemDone; } catch (error) { fatal ??= String(error.stack || error); }
  }
  let runtimeUnchanged = false;
  try { assert.deepEqual(runtimeSnapshot(args.runtime, args.expectedVersion, args.expectedCoreSha), snapshot); runtimeUnchanged = true; }
  catch (error) { fatal ??= String(error.stack || error); }
  const summary = { format: 'moontxnwitness-fixed-elle-serializable-comparison/v2',
    jobSha256: JOB_SHA, referenceSha256: REFERENCE_SHA, referenceContract: CONTRACT,
    fixedElleCommit: ELLE, sourceReferenceCasesSha256: reference.casesContentSha256,
    version: snapshot.version, runtime: snapshot, runtimeFilesUnchanged: runtimeUnchanged,
    runtimeOrigin: args.runtimeOrigin, packageTransportVerifiedByThisRunner: false,
    models: ['serializable'], listProfile: 'captured-list-original-serial/v1',
    callerOptions: { register: callerOptions('point-register-v1'), list: callerOptions('append-list-v1') },
    caseTimeoutMs: args.caseTimeoutMs, classifications, verifications, completed,
    upstreamEligible: reference.cases.filter(c => c.comparisonEligible).length,
    upstreamNotComparable: reference.cases.filter(c => !c.comparisonEligible).length,
    totals, eligibleOutcomes, sdkDispositions, byDataModel, fatal,
    upstreamElleReexecuted: false, referenceDerivedFromSdk: false,
    itemSha256: itemDigest.digest('hex'), reportStreamSha256: reportDigest.digest('hex'),
    reportUncompressedBytes: reportBytes, reportsGzipSha256: sha(readFileSync(reportPath)),
    completedAllInputs: completed === 2000 && classifications === 2000 && verifications === 2000 && runtimeUnchanged && !fatal,
    runnerSha256: sha(readFileSync(fileURLToPath(import.meta.url))),
    workerSha256: sha(readFileSync(new URL('./compare_sdk_v2_worker.mjs', import.meta.url))) };
  summary.passed = summary.completedAllInputs && !totals.failure && !totals.difference && !totals.timeout && !totals.sdkUnknown;
  writeFileSync(resolve(args.output, 'summary.json'), JSON.stringify(summary, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(summary));
  return summary;
}

export function parseArgs(argv) {
  const keys = new Set(['job', 'reference', 'runtime', 'expected-version', 'expected-core-sha', 'output', 'case-timeout-ms', 'runtime-origin']);
  const raw = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.slice(2), value = argv[index + 1];
    assert(argv[index]?.startsWith('--') && keys.has(key) && value && !Object.hasOwn(raw, key), 'unknown/duplicate/missing CLI option');
    raw[key] = value;
  }
  for (const key of ['job', 'reference', 'runtime', 'expected-version', 'expected-core-sha', 'output']) assert(raw[key], 'required --' + key);
  const caseTimeoutMs = raw['case-timeout-ms'] === undefined ? 30000 : Number(raw['case-timeout-ms']);
  assert(Number.isInteger(caseTimeoutMs) && caseTimeoutMs >= 1000 && caseTimeoutMs <= 60000, 'case timeout range');
  const runtimeOrigin = raw['runtime-origin'] ?? 'frozen-local-build';
  assert(['frozen-local-build', 'public-download'].includes(runtimeOrigin));
  return { job: resolve(raw.job), reference: resolve(raw.reference), runtime: resolve(raw.runtime),
    output: resolve(raw.output), expectedVersion: raw['expected-version'], expectedCoreSha: raw['expected-core-sha'],
    caseTimeoutMs, runtimeOrigin };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  runComparison(parseArgs(process.argv.slice(2))).then(result => { if (!result.passed) process.exitCode = 1; })
    .catch(error => { console.error(error.stack || error); process.exitCode = 1; });
}
