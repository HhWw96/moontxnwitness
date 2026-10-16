# Balanced analysis and v2 evidence

The default `analyze` / `analyze_json`, CLI `check`, and `shrink` keep the original
8-transaction completion / 64-transaction reduction behavior. Use an explicit
advanced entry point when its larger, bounded search is useful:

```javascript
import {analyzeWithOptions, replayReport} from '../dist/sdk.mjs';
const report = analyzeWithOptions(history, {
  maxAttempts: 100000, maxOperationChecks: 1000000, maxCachedStates: 50000
});
console.log(report.status, report.search, report.metrics);
console.log(replayReport(history, report));
```

```powershell
node dist/moontxnwitness.mjs check examples/fractured-observation.json --profile balanced --format json --capsule new-balanced.capsule.json
node dist/moontxnwitness.mjs replay new-balanced.capsule.json
```

MoonBit: `analysis_options(...)`, `analyze_with_options(history, options=...)`,
and `analysis_result_json(result)`. All budgets are nonnegative, with the maxima
shown above; zero cache capacity disables memoization. Invalid/fractional/unknown
options are rejected. The size ceiling is 12 committed transactions, 512 operations,
128 initial keys. Other uncertainty, unknown outcomes and absent common clocks
are never filled in by search.

The optimized search compiles integer keys/versions and predecessor masks once.
Writes and final-write positions are rolled back after each candidate. A failed
state includes the selected mask, current versions on every key, and declared
order positions. Only completely exhausted states enter the cache. Cache
saturation disables further insertion; computation still obeys the attempt and
operation budgets. Reaching a budget is `inconclusive`, not a negative proof.

## Evidence contract

Schema 2 uses `bounded-register-v2.1`. `analysisOptions` and `effectiveLimits`
must agree. Replay recomputes the result under those budgets and compares the
verdict, completeness, model, findings, dependency provenance, shortest witness,
concrete serial order, possible version orders, provenance and search conclusion.
Counters/blocker samples live in `metrics`, outside the semantic claim; a capsule's
SHA-256 still detects any accidental change to its stored text. Hashes and replay
do not authenticate a collector or distinguish a correctly regenerated alternative
report from its original author. Changing both options and their limits describes
a new replay request, which must itself reproduce the stated conclusion.

Schema 1 retains its original traversal, budgets and exact search-count comparison.
The v0.0.7 no-serial-execution capsule is an immutable legacy sample. V1 and V2
capsule headers must match their contained report schema. Compact cycle certificates
continue to use schema 1 and independently check edge provenance and closure.
