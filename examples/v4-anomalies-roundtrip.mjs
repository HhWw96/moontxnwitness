import assert from 'node:assert/strict';
import {
  classifyV4, verifyClassificationV4, makeClassificationCapsuleV4,
  inspectLostUpdatesV4, verifyLostUpdatesV4, makeLostUpdatesCapsuleV4,
  replayCapsuleV4,
} from '../dist/sdk.mjs';

const single = {
  schemaVersion: 1, model: 'serializable', initial: { x: 'x0', y: 'y0' },
  versionOrders: { x: ['x0', 'x1'], y: ['y0', 'y1'] },
  transactions: [
    { id: 'reader', status: 'committed', ops: [
      { type: 'read', key: 'x', version: 'x0' },
      { type: 'read', key: 'y', version: 'y1' },
    ] },
    { id: 'writer', status: 'committed', ops: [
      { type: 'write', key: 'x', version: 'x1' },
      { type: 'write', key: 'y', version: 'y1' },
    ] },
  ],
};
const categoryOptions = { categories: ['G-single'] };
const category = classifyV4(single, categoryOptions);
assert.equal(category.judgment.status, 'refuted');
assert.equal(verifyClassificationV4(single, category, categoryOptions).valid, true);
assert.equal(replayCapsuleV4(makeClassificationCapsuleV4(single, categoryOptions), categoryOptions).valid, true);

const update = {
  schemaVersion: 1, model: 'serializable', initial: { x: 'x0' },
  transactions: ['A', 'B'].map(id => ({ id, status: 'committed', ops: [
    { type: 'read', key: 'x', version: 'x0' },
    { type: 'write', key: 'x', version: id + '1' },
  ] })),
};
const lost = inspectLostUpdatesV4(update);
assert(lost.findings.some(finding => finding.kind === 'lost-update'));
assert.equal(verifyLostUpdatesV4(update, lost).valid, true);
assert.equal(replayCapsuleV4(makeLostUpdatesCapsuleV4(update)).valid, true);
console.log(JSON.stringify({ passed: true, checks: 6, category: 'G-single', lostUpdate: true, replayValid: true }));
