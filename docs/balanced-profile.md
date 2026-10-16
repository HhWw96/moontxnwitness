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

## Balanced transaction reduction

`shrinkWithOptions(history, {maxChecks:256, analysisOptions:{...}})` and
`shrink --profile balanced` support 512 transactions / 10,000 operations.
MoonBit uses `reduction_options(...)`, `reduce_with_options(...)`, and
`reduction_result_json(...)`. The typed result contains `reduction` and `analysis`;
the JSON result retains the familiar reducedHistory/report/oneMinimal fields.

The reducer seeds candidates from an actual cycle/direct finding and closes
recorded read sources. It remaps an immutable original writer index for each
subset, prunes only original asserted version orders, and caches rejected subsets
using a collision-free original-membership bit string. Every accepted subset is
reanalyzed. Validation invariants inherited by deletion are reused internally;
full final diagnostics are restored and checked against fresh analysis by tests.
Only a completed singleton pass permits `oneMinimal: true`; that is still the
fixed analyzer/options predicate, not global or operation minimality.

Valid balanced JSON input takes a schema-directed typed parsing path. Plain ASCII
strings are sliced only after quote/control/escape checks; escaped and Unicode
strings and all numbers use official scalar decoding. Legacy decoding supplies
the exact error path. Differential tests compare against the legacy duplicate-key
guard and official JSON parser, including malformed, duplicate, Unicode and
numeric mutations. Default compat parsing remains available unchanged.

Internal singleton checks omit unused initial-only keys: with at most one
committed transaction no cycle or multi-writer search can occur, and unused keys
cannot change a direct read/source finding. Retained histories keep the complete
initial state, and accepted singletons receive full final analysis. Tests compare
both predicates and final reports, including aborted/unknown sources.

All output strings use official JSON escaping. The JS backend uses a tiny
string-fragment `join` primitive to flatten the final
output once. Model inference, parsing, graph/search/reduction and JSON field
selection remain MoonBit; other backends use the standard StringBuilder.
Official string encodings are cached across calls, bounded by 2,048 entries and
131,072 UTF-16 units including original and encoded strings. Saturation disables
insertion; it changes neither encoding nor a conclusion. No analysis verdict is
cached by this serializer. Tests compare reports before and after saturation.
