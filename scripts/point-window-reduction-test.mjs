// Uses original supplied PostgreSQL observations, not a hand-written history.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const [runtime, ...paths] = process.argv.slice(2);
assert.equal(paths.length, 3, 'Supply SDK and original start/end/session files');
const sdk = await import(pathToFileURL(resolve(runtime)).href);
const originals = paths.map(path => readFileSync(path, 'utf8'));
const options = {category: 'G2-item'};
let checks = 0;
const notExecuted = [];
const check = (name, fn) => {fn(); checks++;};
const result = sdk.reduceConfiguredPointWindowV4(...originals, options);
check('verified refutation and complete final reduction', () => {
  assert.equal(result.window.status, 'refuted');
  assert.equal(result.window.coverageComplete, true);
  assert.ok(['reduced', 'unchanged'].includes(result.status));
  assert.equal(result.oneMinimal, true);
  assert.equal(result.originalWindowRetained, true);
  assert.equal(result.reduction.execution.finalRevalidation, true);
  assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, result, options).valid, true);
});
const originalTransactions = result.window.history.events.filter(event => event.kind === 'begin').length;
if (originalTransactions > 2) {
  check('actual captured read noise is removable', () => {
    assert.equal(result.status, 'reduced');
    assert.equal(result.reduction.history.events.filter(event => event.kind === 'begin').length, 2);
    assert.equal(result.reduction.removedTransactions.length, originalTransactions - 2);
  });
} else notExecuted.push('noise removal: supplied window has only two transactions');
for (const [name, edit] of [
  ['window conclusion', value => value.window.status = 'checked-compatible'],
  ['authentication', value => value.sourceAuthenticated = true],
  ['missing original window', value => delete value.window],
  ['changed selection', value => value.reduction.removedTransactions.push('forged')],
  ['minimality', value => value.oneMinimal = false],
  ['authority field', value => value.trusted = true],
  ['category', value => value.preserveCategory = 'G0'],
]) {
  check('rejects ' + name, () => {
    const changed = structuredClone(result);edit(changed);
    assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, changed, options).valid, false);
  });
}
check('rejects duplicate report fields', () => {
  const text = JSON.stringify(result).replace('{', '{"status":"forged",');
  assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, text, options).valid, false);
});
check('independent candidate budget', () => {
  assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, result, {...options, maxChecks: 0}).valid, false);
});
check('rehashing does not legitimize a new budget', () => {
  const changed = structuredClone(result), caller = {...options, maxChecks: 0};
  changed.optionsSha256 = createHash('sha256').update(JSON.stringify(caller)).digest('hex');
  assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, changed, caller).valid, false);
});
check('candidate exhaustion does not claim minimality', () => {
  const bounded = {...options, maxChecks: 0};
  const value = sdk.reduceConfiguredPointWindowV4(...originals, bounded);
  assert.equal(value.window.status, 'refuted');
  assert.equal(value.oneMinimal, false);
  assert.equal(value.reduction.execution.candidateBudgetExhausted, true);
  assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, value, bounded).valid, true);
  value.oneMinimal = true;
  assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, value, bounded).valid, false);
});
check('window budget cannot become a complete reduction', () => {
  const bounded = {...options, windowOptions: {maxPointChecks: 0}};
  const value = sdk.reduceConfiguredPointWindowV4(...originals, bounded);
  assert.equal(value.status, 'unknown');
  assert.equal(value.oneMinimal, false);
  assert.equal(value.reduction, null);
  assert.equal(sdk.verifyConfiguredPointReductionV4(...originals, value, bounded).valid, true);
});
check('category must be explicitly supported', () => {
  const value = sdk.reduceConfiguredPointWindowV4(...originals, {category: 'G0'});
  assert.equal(value.status, 'invalid');assert.equal(value.oneMinimal, false);
});
check('exact original window is retained', () => {
  const altered = [...originals];altered[0] += ' ';
  assert.equal(sdk.verifyConfiguredPointReductionV4(...altered, result, options).valid, false);
});
const capsule = sdk.makeConfiguredPointReductionCapsuleV4(...originals, options);
check('capsule replays the entire reduction under independent options', () => {
  const replay = sdk.replayConfiguredPointReductionCapsuleV4(capsule, options);
  assert.equal(replay.valid, true);
  assert.equal(replay.sourceAuthenticated, false);
  assert.deepEqual(replay.report, result);
});
check('capsule requires independent options', () => {
  assert.equal(sdk.replayConfiguredPointReductionCapsuleV4(capsule).valid, false);
  assert.equal(sdk.replayConfiguredPointReductionCapsuleV4(capsule, {...options, maxChecks: 0}).valid, false);
});
check('capsule rejects digest and rehashed report changes', () => {
  const changed = JSON.parse(capsule);
  const report = JSON.parse(changed[1][4]);
  report.oneMinimal = false;
  changed[1][4] = JSON.stringify(report);
  assert.equal(sdk.replayConfiguredPointReductionCapsuleV4(changed, options).valid, false);
  changed[2][4] = createHash('sha256').update(changed[1][4]).digest('hex');
  assert.equal(sdk.replayConfiguredPointReductionCapsuleV4(changed, options).valid, false);
});
check('capsule rejects an invalid or incompatible envelope', () => {
  assert.throws(() => sdk.makeConfiguredPointReductionCapsuleV4(...originals, {category: 'G0'}));
  assert.equal(sdk.replayConfiguredPointReductionCapsuleV4([capsule], options).valid, false);
});
check('capsule preserves an unresolved window', () => {
  const bounded = {...options, windowOptions: {maxPointChecks: 0}};
  const unknown = sdk.makeConfiguredPointReductionCapsuleV4(...originals, bounded);
  const replay = sdk.replayConfiguredPointReductionCapsuleV4(unknown, bounded);
  assert.equal(replay.valid, true);
  assert.equal(replay.report.status, 'unknown');
  assert.equal(replay.report.oneMinimal, false);
});
console.log(JSON.stringify({passed: true, checks, notExecuted, originalTransactions,
retainedTransactions: result.reduction.history.events.filter(event => event.kind === 'begin').length,
originalWindowRetained: true, sourceAuthenticated: false}));
