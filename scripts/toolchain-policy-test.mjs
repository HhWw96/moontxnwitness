import assert from 'node:assert/strict';
import {assertCompilerVersion, assertPinnedCompilerVersion, PINNED_COMPILER} from './toolchain-policy.mjs';
for(const value of ['v0.10.16+b1a0e846e','0.9.99','0.10.20','0.10.21-dev','unknown','0.999999999999999999999.0'])
  assert.throws(()=>assertCompilerVersion(value));
for(const value of ['v0.10.21+06da1ed44 (2026-11-16)','0.10.22','v0.11.0','1.0.0'])
  assert.ok(assertCompilerVersion(value));
assert.equal(assertPinnedCompilerVersion(`v${PINNED_COMPILER} (2026-11-16)`), `v${PINNED_COMPILER}`);
assert.throws(()=>assertPinnedCompilerVersion('0.10.21+abc123'));
assert.throws(()=>assertPinnedCompilerVersion('0.10.22'));
console.log(JSON.stringify({passed:true,compilerVersionCases:13}));
