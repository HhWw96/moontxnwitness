#!/usr/bin/env node
// Synthetic point-register witness; no database, external checker or new search.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdtempSync} from 'node:fs';
import {resolve,basename} from 'node:path';
const hash = text => createHash('sha256').update(text, 'utf8').digest('hex');
let directory;
try {
  const args = process.argv.slice(2);
  if (args.length !== 0 && (args.length !== 2 || args[0] !== '--out-root'))
    throw new Error('Usage: node examples/register-cycle-roundtrip.mjs [--out-root existing-directory]');
  directory = mkdtempSync(resolve(args[1] || process.cwd(), 'moontxnwitness-register-cycle-'));
  const sdk = await import('../dist/sdk.mjs');
  const traceText = readFileSync(new URL('./register-cycle.json', import.meta.url), 'utf8');
  const report = sdk.analyzeV3(traceText);
  assert.equal(report.status, 'violation');
  const reportText = JSON.stringify(report, null, 2) + '\n';
  const explanation = sdk.explainRegisterCycleV3(traceText, reportText);
  assert.equal(explanation.status, 'explained');
  assert.equal(explanation.subtype, 'G2-item');
  assert.equal(explanation.scope.acceptsIsolationModels, false);
  assert.equal(explanation.scope.searchesOtherCategoryCycles, false);
  const capsule = sdk.makeCapsuleV3(traceText, reportText);
  const parsed = JSON.parse(capsule);
  assert.equal(parsed.traceText, traceText);
  assert.equal(parsed.reportText, reportText);
  const replay = sdk.replayCapsuleV3(capsule);
  const checked = sdk.verifyRegisterCycleExplanationV3(parsed.traceText, parsed.reportText, explanation);
  assert.equal(replay.valid, true); assert.equal(checked.valid, true);
  assert.equal(hash(traceText), explanation.traceTextSha256);
  assert.equal(hash(reportText), explanation.reportTextSha256);
  const artifacts = new Map([
    ['input.json', traceText], ['report.json', reportText],
    ['cycle-explanation.json', JSON.stringify(explanation, null, 2) + '\n'],
    ['original-v3.capsule.json', capsule], ['replay.json', JSON.stringify(replay, null, 2) + '\n'],
    ['explanation-verification.json', JSON.stringify(checked, null, 2) + '\n'],
  ]);
  const files = [];
  for (const [file, text] of artifacts) {
    writeFileSync(resolve(directory, file), text, {encoding:'utf8',flag:'wx'});
    files.push({file, bytes:Buffer.byteLength(text,'utf8'), sha256:hash(text)});
  }
  const receipt = {schema:1, kind:'verified-register-cycle-sdk-example', passed:true, version:sdk.version(),
    syntheticInput:true, actualDatabaseExecution:false, newElleExecution:false, performanceMeasurement:false,
    sourceReportStatus:report.status, selectedCycleSubtype:explanation.subtype,
    explanationVerified:checked.valid, originalCapsuleReplayed:replay.valid,
    acceptsIsolationModels:false, searchesOtherCategories:false,
    outputDirectory:basename(directory), files};
  writeFileSync(resolve(directory,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{encoding:'utf8',flag:'wx'});
  console.log(JSON.stringify(receipt));
} catch(error) {
  const receipt={schema:1,kind:'verified-register-cycle-sdk-example',passed:false,
    actualDatabaseExecution:false,newElleExecution:false,error:String(error.message)};
  if(directory)writeFileSync(resolve(directory,'failure.json'),JSON.stringify(receipt,null,2)+'\n',{encoding:'utf8',flag:'wx'});
  console.error(JSON.stringify(receipt)); process.exitCode=2;
}
