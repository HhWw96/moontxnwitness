import * as sdk from '../dist/sdk.mjs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {openSync, readSync, closeSync, writeFileSync, mkdirSync, mkdtempSync} from 'node:fs';
import {resolve, dirname, relative} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
let args = process.argv.slice(2);
const fixtures = resolve(root, 'fixtures/execution-v3/mlflow');
if (args.length === 0 || (args.length === 2 && args[0] === '--out-root')) {
  args = [resolve(fixtures, 'before/capture.json'), resolve(fixtures, 'fixed/capture.json'), args[1] ? resolve(args[1]) : resolve(root, 'verification/execution-roundtrip')];
}
if (args.length !== 3) throw new TypeError('Expected no arguments, --out-root NEW_OUTPUT_PARENT, or BEFORE_TRACE.json AFTER_TRACE.json NEW_OUTPUT_PARENT');
const hash = text => createHash('sha256').update(text).digest('hex');
function readTrace(path) {
  const fd = openSync(path, 'r'), chunks = [];
  let total = 0;
  try {
    for (;;) {
      const buffer = Buffer.alloc(Math.min(65536, 8 * 1024 * 1024 + 1 - total));
      const count = readSync(fd, buffer, 0, buffer.length, null);
      if (!count) break;
      total += count;
      if (total > 8 * 1024 * 1024) throw new RangeError('Capture exceeds 8 MiB UTF-8');
      chunks.push(buffer.subarray(0, count));
    }
  } finally {closeSync(fd);}
  return new TextDecoder('utf-8', {fatal: true}).decode(Buffer.concat(chunks));
}
const parent = resolve(args[2]);
mkdirSync(parent, {recursive: true});
const output = mkdtempSync(resolve(parent, 'execution-'));
const receipt = {schema: 1, kind: 'execution-diagnostic-offline-comparison', passed: false, runtimeVersion: sdk.version(),
  outputDirectory: relative(parent, output).replaceAll('\\', '/'),
  actualDatabaseExecution: false, databaseAuthenticityVerified: false,
  fixesEverySchedule: false, modelViolationClaim: false,
  certifiesFailureAbsence: false, fullApplicationIntegration: false, cases: []};
const retain = (name, text) => {
  writeFileSync(resolve(output, name), text, {flag: 'wx'});
  return {file: name, bytes: Buffer.byteLength(text, 'utf8'), sha256: hash(text)};
};
try {
  for (const [label, path] of [['before', args[0]], ['after', args[1]]]) {
    const traceText = readTrace(path);
    const capsuleText = sdk.makeExecutionCapsuleV3(traceText);
    const replay = sdk.replayExecutionCapsuleV3(capsuleText);
    assert.equal(replay.valid, true);
    assert.equal(JSON.parse(capsuleText).traceText, traceText);
    const report = sdk.analyzeV3(traceText), modelCapsule = sdk.makeCapsuleV3(traceText, report);
    const modelReplay = sdk.replayCapsuleV3(modelCapsule);
    assert.equal(modelReplay.valid, true);
    const files = [retain(label + '.trace.json', traceText),
      retain(label + '.execution-capsule.json', capsuleText),
      retain(label + '.execution-replay.json', JSON.stringify(replay, null, 2) + '\n'),
      retain(label + '.model-report.json', JSON.stringify(report, null, 2) + '\n'),
      retain(label + '.model-capsule.json', modelCapsule)];
    receipt.cases.push({label, originalTraceSha256: hash(traceText),
      observedFaultCount: replay.diagnostic.observedFaultCount,
      observedFaultKinds: replay.diagnostic.faults.map(fault => fault.kind),
      observedSqlstates: replay.diagnostic.faults.map(fault => fault.sqlstate),
      captureStatus: replay.diagnostic.captureStatus,
      captureCoverage: replay.diagnostic.captureCoverage,
      transactionOutcomes: replay.diagnostic.transactionOutcomes,
      modelStatus: report.status, modelCoverage: report.coverage,
      executionDiagnosticRecomputed: replay.valid, originalModelCapsuleReplayed: modelReplay.valid,
      files});
  }
  receipt.observedDifference = {
    beforeFaults: receipt.cases[0].observedFaultCount,
    afterFaults: receipt.cases[1].observedFaultCount,
    interpretation: 'Difference between two supplied recorded observation sets; not a new database reproduction, repair proof, failure absence certificate or isolation classification.',
  };
  receipt.passed = true;
} catch (error) {receipt.error = error.message;}
retain('receipt.json', JSON.stringify(receipt, null, 2) + '\n');
console.log(JSON.stringify({passed: receipt.passed, runtimeVersion: receipt.runtimeVersion,
  outputDirectory: receipt.outputDirectory, receiptFile: 'receipt.json', actualDatabaseExecution: false,
  observedDifference: receipt.observedDifference || null, error: receipt.error || null}));
if (!receipt.passed) process.exitCode = 1;
