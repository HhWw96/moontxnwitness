#!/usr/bin/env node
// Synthetic relation-set source-closure example. It does not connect to a database.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdtempSync} from 'node:fs';
import {resolve, basename} from 'node:path';

const hash = text => createHash('sha256').update(text, 'utf8').digest('hex');
let directory;
try {
  const args = process.argv.slice(2);
  if (args.length !== 0 && (args.length !== 2 || args[0] !== '--out-root')) {
    throw new Error('Usage: node examples/relation-roundtrip.mjs [--out-root existing-directory]');
  }
  directory = mkdtempSync(resolve(args[1] || process.cwd(), 'moontxnwitness-relation-'));
  const sdk = await import('../dist/sdk.mjs');
  const traceText = readFileSync(new URL('./relation-source-closure.json', import.meta.url), 'utf8');
  const original = sdk.analyzeRelationV3(traceText);
  assert.equal(original.status, 'violation');
  assert.equal(original.modelDefinition.id, 'relation-set-serializable-v1');
  assert.equal(original.evidence.kind, 'bounded-serial-exhaustion');
  const reduction = sdk.reduceRelationV3(traceText);
  assert.equal(reduction.status, 'reduced');
  assert.equal(reduction.oneMinimal, true);
  assert.deepEqual(reduction.removed, ['N']);
  assert.equal(reduction.report.normalized.transactions.length, 3);
  assert.equal(sdk.verifyRelationV3(reduction.reducedCapture, reduction.report).valid, true);
  const reducedText = JSON.stringify(reduction.reducedCapture, null, 2) + '\n';
  const capsule = sdk.makeRelationCapsuleV3(reducedText, reduction.report);
  const replay = sdk.replayRelationCapsuleV3(capsule);
  assert.equal(replay.valid, true);
  const artifacts = new Map([
    ['input.json', traceText],
    ['analysis.json', JSON.stringify(original, null, 2) + '\n'],
    ['reduction.json', JSON.stringify(reduction, null, 2) + '\n'],
    ['reduced.json', reducedText],
    ['case.capsule.json', capsule],
    ['replay.json', JSON.stringify(replay, null, 2) + '\n'],
  ]);
  const files = [];
  for (const [file, text] of artifacts) {
    writeFileSync(resolve(directory, file), text, {encoding: 'utf8', flag: 'wx'});
    files.push({file, bytes: Buffer.byteLength(text, 'utf8'), sha256: hash(text)});
  }
  const receipt = {
    schema: 1, kind: 'relation-set-v3-sdk-example', passed: true,
    version: sdk.version(), dataModel: 'relation-set-v1',
    actualDatabaseExecution: false, performanceMeasurement: false,
    isolationClassification: false, syntheticInput: true,
    originalTransactions: original.normalized.transactions.length,
    reducedTransactions: reduction.report.normalized.transactions.length,
    oneMinimal: reduction.oneMinimal, replayValid: replay.valid,
    scope: 'Bounded relation-set serializability; oneMinimal is transaction single-deletion under the same predicate. Source authenticity is not certified.',
    outputDirectory: basename(directory), files,
  };
  writeFileSync(resolve(directory, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n', {encoding: 'utf8', flag: 'wx'});
  console.log(JSON.stringify(receipt));
} catch (error) {
  const receipt = {schema: 1, kind: 'relation-set-v3-sdk-example', passed: false, actualDatabaseExecution: false, error: String(error.message)};
  if (directory) writeFileSync(resolve(directory, 'failure.json'), JSON.stringify(receipt, null, 2) + '\n', {encoding: 'utf8', flag: 'wx'});
  console.error(JSON.stringify(receipt));
  process.exitCode = 2;
}
