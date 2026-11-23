import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';

const {values: args} = parseArgs({options: {
  core: {type: 'string'}, input: {type: 'string'}, output: {type: 'string'},
}});
assert(args.core && args.input && args.output, 'Use --core CORE --input ORIGINAL_DIR --output NEW_FILE');
const {admit_configured_predicate_window_v1_json: admit} = await import(pathToFileURL(resolve(args.core)).href);
const read = file => readFile(join(args.input, file), 'utf8');
const config = await read('config.json');
const policy = await read('policy.json');
const receipt = JSON.parse(await read('receipt.json'));
assert(receipt.passed && receipt.actualDatabaseExecution && receipt.postgres === '18.6');
const results = [];
function verify(raw, options = {}) {
  return JSON.parse(admit(config, policy, raw, JSON.stringify(options)));
}
function incomplete(name, report, reason) {
  assert.equal(report.status, 'unknown', name + ': ' + report.reason);
  assert.equal(report.coverageComplete, false);
  assert.match(report.reason, reason);
  results.push({name, status: report.status, reason: report.reason});
}
for (const test of receipt.cases) {
  const original = await read(test.file);
  const report = verify(original);
  if (test.status === 'unknown') {
    incomplete(test.case, report, new RegExp(test.reason));
    continue;
  }
  assert.equal(report.status, 'admitted', report.reason);
  assert.equal(report.coverageComplete, true);
  assert.equal(report.rangeReads, test.reads);
  const ranges = report.events.filter(event => event.kind === 'row_read');
  assert.deepEqual(ranges.map(event => event.rows.map(row => String(row.key))),
    [['0'], [], ['0', '5'], ['0'], ['0', '5'], ['9223372036854775806']]);
  const changed = JSON.parse(original);
  changed.transactions[0].calls[0].delivered.pop();
  incomplete('partial delivery', verify(JSON.stringify(changed)), /predicate-delivery-count/);
  const absent = JSON.parse(original);
  delete absent.startInputText;
  incomplete('missing boundary source', verify(JSON.stringify(absent)), /startInputText|field/i);
  incomplete('independent budget', verify(original, {maxChecks: 0}), /budget|unverified/);
  results.push({name: test.case, status: report.status, rangeReads: report.rangeReads,
    originalSha256: report.bundleSha256, events: report.events.length});
}
const proof = {passed: true, actualPostgresInputs: true, postgres: receipt.postgres, cases: results};
await writeFile(args.output, JSON.stringify(proof, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify(proof));
