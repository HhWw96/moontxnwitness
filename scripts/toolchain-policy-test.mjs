import assert from 'node:assert/strict';
import {assertCompilerVersion} from './toolchain-policy.mjs';
for(const value of ['v0.10.14+7d59c7ec9','0.9.99','0.10.15','0.10.16-dev','unknown','0.999999999999999999999.0'])
  assert.throws(()=>assertCompilerVersion(value));
for(const value of ['v0.10.16+b1a0e846e (2026-10-16)','0.10.17','v0.11.0','1.0.0'])
  assert.ok(assertCompilerVersion(value));
console.log(JSON.stringify({passed:true,compilerVersionCases:10}));
