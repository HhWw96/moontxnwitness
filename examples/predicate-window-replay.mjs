import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {gunzipSync} from 'node:zlib';

const {values: args} = parseArgs({options: {output: {type: 'string'}, runtime: {type: 'string'}}});
const root = new URL('predicate-window-replay-data/', import.meta.url);
const entry = args.runtime
  ? pathToFileURL(resolve(args.runtime, 'configured-predicate-window-v1.mjs'))
  : new URL('../dist/configured-predicate-window-v1.mjs', import.meta.url);
const {analyzeConfiguredPredicateWindowV1, makeConfiguredPredicateCapsuleV1,
  replayConfiguredPredicateCapsuleV1} = await import(entry.href);
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const decode = bytes => new TextDecoder('utf-8', {fatal: true}).decode(bytes);
const manifest = JSON.parse(decode(await readFile(new URL('manifest.json', root))));
assert.equal(manifest.format, 'moontxnwitness-predicate-replay-inputs/v1');
assert.deepEqual(manifest.cases.map(item => item.name), ['before', 'ordered', 'retry']);
const results = [];

for (const {name, compressedSha256, originalSha256, bytes, config, policy} of manifest.cases) {
  const packed = await readFile(new URL(name + '.json.gz', root));
  assert.equal(sha256(packed), compressedSha256);
  const raw = gunzipSync(packed, {maxOutputLength: 1024 * 1024});
  assert.equal(raw.length, bytes);
  assert.equal(sha256(raw), originalSha256);
  const source = decode(raw);
  const options = {config, policy};
  const analysis = analyzeConfiguredPredicateWindowV1(source, options);
  const capsule = makeConfiguredPredicateCapsuleV1(source, options);
  const replay = replayConfiguredPredicateCapsuleV1(capsule, options);
  assert(replay.reportMatches);
  const expected = {before: 'refuted', ordered: 'checked-compatible', retry: 'unknown'}[name];
  assert.equal(analysis.status, expected);
  assert.equal(replay.valid, expected !== 'unknown');

  const transactions = JSON.parse(source).transactions;
  const statements = transactions.flatMap(tx => tx.logText.trimEnd().split('\n').map(JSON.parse));
  const range = statements.find(record => record.kind === 'control-request' && record.queryId === 'range' &&
    record.parameters[0] === '100' && record.parameters[1] === '110');
  assert(range, 'The original booking query is required');
  const execution = {rangeSql: range.sql, sampleParameters: range.parameters,
    sqlstates: statements.filter(record => record.kind === 'control-error').map(record => record.sqlstate),
    committedTransactions: transactions.filter(tx => tx.outcome === 'committed').length};
  const result = {name, rawExecution: execution, modelStatus: analysis.status,
    gateExit: {refuted: 1, 'checked-compatible': 0, unknown: 2}[analysis.status]};
  if (name === 'before') {
    const witness = analysis.g2.search.witness;
    assert.equal(analysis.g2Item.status, 'checked-compatible');
    assert.equal(witness.antiDependencies.item, 0);
    assert.equal(witness.antiDependencies.predicate, 2);
    const reduced = replayConfiguredPredicateCapsuleV1(
      makeConfiguredPredicateCapsuleV1(source, options, 'reduction'), options);
    assert(reduced.valid && reduced.report.reduction.oneMinimal);
    assert(reduced.report.reduction.sourceCoverage.reducedSourceClosed);
    const transactionCount = reduced.report.reduction.history.events.filter(event => event.kind === 'begin').length;
    assert.equal(analysis.admission.transactions, 5);
    assert.equal(transactionCount, 2);
    const dependencies = witness.steps.map(({from, to, kind, sources}) => ({
      from, to, kind, sources: sources.map(({query, identity, installedToggle}) => {
        const read = analysis.provenance.find(item => item.sequence === query.readSeq && item.tx === from);
        const write = analysis.provenance.find(item =>
          item.sequence === installedToggle.fact.sourceSeq && item.tx === to);
        assert(read && write, 'Both operands must reference original requests');
        return {key: identity.primaryKey, version: installedToggle.fact.version,
          readRequestSeq: read.requestSeq, readSnapshot: read.snapshot, writeRequestSeq: write.requestSeq};
      }),
    }));
    result.witness = {category: 'G2', scope: 'predicate', antiDependencies: witness.antiDependencies, dependencies,
      originalTransactions: 5, reducedTransactions: transactionCount, oneMinimal: true};
  } else if (name === 'retry') {
    assert(execution.sqlstates.includes('40001'));
  }
  results.push(result);
}

const report = {passed: true, offlineReplay: true, provenance: manifest.provenance, cases: results};
if (args.output) await writeFile(resolve(args.output), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify(report));
