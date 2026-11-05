// Recompute the MoonBit side of the original register/list comparison.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [jobPath, referencePath, outputPath, runtimePath, ...extra] = process.argv.slice(2);
if (!jobPath || !referencePath || !outputPath || !runtimePath || extra.length) {
  throw new Error('Usage: compare-fixed-elle-serializable.mjs ORIGINAL_JOB.json FROZEN_REFERENCE.json NEW_OUTPUT_DIR DIST_DIR');
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const jobSha256 = '3b78df6d0eb7d74be56cd6946231d52778b3c0159ba40c9bb00a90ce3ac6b338';
const referenceSha256 = 'cd03c00a5c14c8ede612fdc1e15c40d35e0229c980ba2d08c651a15b7f2dc860';
const fixedElleCommit = '4e359e597c52938b0afebb8bc42273914d68a424';
function loadPinned(file, digest) {
  const bytes = readFileSync(file);
  assert.equal(sha(bytes), digest, 'Frozen input bytes differ');
  return JSON.parse(bytes);
}
const job = loadPinned(jobPath, jobSha256);
const reference = loadPinned(referencePath, referenceSha256);
assert.equal(reference.fixedElleCommit, fixedElleCommit);
assert.equal(reference.originalInputJob.sha256, jobSha256);
assert.equal(reference.operationConversionAudit.preparedEDNAndOriginalSourceFactsMatch, true);
assert.equal(job.length, 2000);
assert.equal(reference.cases.length, job.length);
assert.equal(new Set(job.map(row => row.id)).size, job.length);

const runtimeFiles = ['build-manifest.json', 'models-v4.mjs', 'core.mjs'];
const runtimeDigests = () => Object.fromEntries(runtimeFiles.map(name => [name, sha(readFileSync(resolve(runtimePath, name)))]));
const runtime = runtimeDigests();
const build = JSON.parse(readFileSync(resolve(runtimePath, 'build-manifest.json')));
assert.equal(build.coreSha256, runtime['core.mjs']);
const api = await import(pathToFileURL(resolve(runtimePath, 'models-v4.mjs')));
mkdirSync(outputPath);

const rows = [];
const emptyCounts = () => ({ matched: 0, difference: 0, unknown: 0, notComparable: 0, failed: 0 });
const totals = emptyCounts();
const byModel = { 'point-register-v1': emptyCounts(), 'append-list-v1': emptyCounts() };
const retained = new Set();
const registerProfile = 'captured-register-full-program/v2';
const listProfile = 'captured-list-original-serial/v1';
const listProfiles = [listProfile, 'captured-list-prefix-state/v2', 'effective-list-appends/v1'];
let classifications = 0, verifications = 0;
for (const [index, row] of job.entries()) {
  const old = reference.cases[index];
  const source = JSON.stringify(row.input);
  const dataModel = row.input.dataModel;
  assert(Object.hasOwn(byModel, dataModel));
  assert.equal(row.id, old.id);
  assert.equal(sha(source), row.inputSha256);
  assert.equal(row.inputSha256, old.inputSha256);
  const eligible = old.Elle.comparisonEligible;
  const upstream = old.Elle.validity;
  if (eligible) {
    assert.equal(typeof upstream, 'boolean');
    assert.equal(old.Elle.cycleSearchTimeout, false);
  }
  const options = { models: ['serializable'] };
  if (dataModel === 'append-list-v1') options.listProfile = listProfile;
  const item = { id: row.id, dataModel, inputSha256: row.inputSha256, options, eligible, upstream };
  let report;
  try {
    classifications++;
    report = api.classifyModelsV4(source, options);
    const reportText = JSON.stringify(report);
    verifications++;
    assert.equal(api.verifyModelsV4(source, reportText, options).valid, true);
    assert.equal(report.models.length, 1);
    assert.equal(report.models[0].model, 'serializable');
    const status = report.models[0].status;
    assert(['checked-compatible', 'refuted', 'unknown', 'pending'].includes(status));
    Object.assign(item, { status, profile: report.sourceProfile, reportSha256: sha(reportText) });
    const commonScope = dataModel === 'point-register-v1' ? report.sourceProfile === registerProfile : listProfiles.includes(report.sourceProfile);
    if (!eligible || !commonScope) {
      item.outcome = 'notComparable';
      item.reason = eligible ? 'current-source-profile-outside-shared-scope' : 'original-elle-result-ineligible';
    } else if (status === 'unknown' || status === 'pending') {
      item.outcome = 'unknown';
    } else {
      item.outcome = (status === 'checked-compatible') === upstream ? 'matched' : 'difference';
    }
  } catch (error) {
    item.outcome = 'failed';
    item.reason = error.message;
  }
  if (item.outcome !== 'matched' && !retained.has(item.outcome)) {
    retained.add(item.outcome);
    writeFileSync(resolve(outputPath, `first-${item.outcome}.json`), JSON.stringify({ item, report }, null, 2) + '\n', { flag: 'wx' });
  }
  totals[item.outcome]++;
  byModel[dataModel][item.outcome]++;
  rows.push(JSON.stringify(item));
}
assert.deepEqual(runtimeDigests(), runtime);
const items = rows.join('\n') + '\n';
const summary = {
  format: 'moontxnwitness-fixed-elle-serializable-comparison/v1',
  fixedElleCommit, upstreamRunId: reference.actualOldRunId, jobSha256, referenceSha256,
  upstreamArtifactSha256: reference.originalArtifact.sha256,
  version: build.version, sourceFingerprint: build.sourceSha256, runtime,
  classifications, verifications, upstreamElleReexecuted: false,
  models: ['serializable'], totals, byModel, itemsSha256: sha(items),
};
writeFileSync(resolve(outputPath, 'items.jsonl'), items, { flag: 'wx' });
writeFileSync(resolve(outputPath, 'summary.json'), JSON.stringify(summary, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify(summary));
if (totals.failed || totals.difference) process.exitCode = 1;
