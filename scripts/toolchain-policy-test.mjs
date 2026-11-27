import assert from 'node:assert/strict';
import {assertCompilerVersion, assertPinnedCompilerVersion, PINNED_COMPILER} from './toolchain-policy.mjs';

const rejected = [
  'v0.10.21+06da1ed44 (2026-11-16)', '0.99.99', '1.0.0-alpha.3', '1.0.0-beta',
  '1.0.0-rc0', '1.0.0-rc1.01', '01.0.0', '1.0.0-rc1+', 'unknown',
  '0.999999999999999999999.0',
];
const accepted = [
  '1.0.0-rc1', 'v1.0.0-rc1+abc123 (2026-11-26)', '1.0.0-rc1.1',
  '1.0.0-rc2', '1.0.0', '1.0.1', 'v1.1.0+abc.def',
];
for (const version of rejected) assert.throws(() => assertCompilerVersion(version));
for (const version of accepted) assert.ok(assertCompilerVersion(version));
assert.equal(assertPinnedCompilerVersion(`v${PINNED_COMPILER} (2026-11-26)`), `v${PINNED_COMPILER}`);
assert.throws(() => assertPinnedCompilerVersion('1.0.0-rc1+different'));
assert.throws(() => assertPinnedCompilerVersion('1.0.0'));
console.log(JSON.stringify({passed: true, compilerVersionCases: rejected.length + accepted.length + 3}));
