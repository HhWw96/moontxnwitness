# Explicit configured ORM SDK and offline replay

These entries consume the opt-in fixed base-user profile described in
`configured-user-profile.md` and `orm-profile-promotion.md`. They do not install
database metadata, attach a running application or upgrade the generic raw
diagnostic. The old v3 capsules and `inspectOrmSourceV3` retain their behavior.

The fixed scope is PostgreSQL18, psycopg3.3.6, SQLAlchemy2.0.55 and the pinned
FastAPI Users SQLAlchemy7.0.0 base-user ID get/create/declared update/delete
window. Exactly one engine must be attached before work and remain attached
through finalization, with returned leases. Arbitrary SQL, lower(email), OAuth
JOIN, custom cursor behavior and complete authentication-system coverage are
outside this entry. A local factory without the typed engine window remains
diagnostic. Independent recomputation is not database authentication.

## SDK

```javascript
import {readFileSync,writeFileSync} from 'node:fs';
import {analyzeOrmProfileV3,verifyOrmProfileV3,reduceOrmProfileV3,
  makeOrmProfileCapsuleV3,makeOrmProfileReductionCapsuleV3,
  replayOrmProfileCapsuleV3} from './dist/sdk.mjs';

const original=readFileSync('profile-source.json','utf8');
const report=analyzeOrmProfileV3(original,{maxAttempts:100000});
const checked=verifyOrmProfileV3(original,report,{maxAttempts:100000});
const capsule=makeOrmProfileCapsuleV3(original,{maxAttempts:100000});
writeFileSync('new-profile.capsule.json',capsule,{flag:'wx'});
const replay=replayOrmProfileCapsuleV3(capsule);

const reduction=reduceOrmProfileV3(original,{maxChecks:256,analysisOptions:{}});
const reducedCapsule=makeOrmProfileReductionCapsuleV3(original,{maxChecks:256});
```

Options must be plain objects. Analysis supports maxAttempts0..100000,
maxOperationChecks0..1000000 and maxCachedStates0..50000. Reduction supports
maxChecks0..256 and an analysisOptions object with those same limits. Exact
search keeps the existing 12-transaction/512-operation/128-key limit; graph
analysis capacity is not claimed to be an exact enumeration limit. The
reduction entry keeps the existing 512-transaction/10000-operation scope.
Budget exhaustion or unsupported source facts remain visible. A consistent
original source returns `skipped` with no fabricated reduced history.

Reports bind the original envelope SHA and each original trace, source journal,
lifecycle and index SHA. They record the exact requested options, current engine,
host/source algorithms, budgets and full core output. Original diagnostic gaps,
`sourceClosed:false`, unknown outcomes and the old local proof's null history
remain visible. Only the separate configured mapping can accept analysis
coverage. `verifyOrmProfileV3` recomputes the complete host/core report, including
counters, hashes and options; passing options explicitly also checks that
request. The report's compact SDK JSON and pretty CLI JSON are supported.

The new `moontxnwitness-orm-profile/v1` capsule retains the exact original
envelopeText and reportText, options, five source hashes and report/option hashes.
Replay accepts only its canonical outer JSON and the exact current engine and
algorithms. Unknown engines/algorithms, extra or missing fields, duplicate outer
fields, modified budgets, stale results and resealed source/result mutations
are refused. An old engine is never made current by rewriting version-like
business JSON. The original source text is not decoded/re-encoded during
packaging. Hashes bind supplied bytes; they do not prove a database or collector
was honest. Segment payloads absent from the source envelope are not rehashed.

## Source-closed transaction reduction

Reduction first reruns the complete independent source promotion and requires a
definite violation. The existing generic reducer proposes deletions from that
original derived history without changing its implementation or budgets. Its
exact original attempt remains in `genericAttempt`, including uncertainty.

The host restores required original writers for every retained read version and
asserted write-chain predecessor, transitively. An original initial version may
discharge that dependency; a new initial version is never manufactured. It then
rechecks that restored candidate and performs remaining single deletions within
the shared candidate budget. A candidate missing a source is recorded as
`unknown/missing-source`, rather than proof that the anomaly is absent.

`maxChecks` limits semantic candidate checks: generic semantic checks, a restored
candidate when checked, and further single-deletion checks, at most256.
`semanticCandidateChecks`, `cachedCandidateLookups` and their sum
`candidateAttempts` are reported separately. A cache lookup reuses an already
checked negative candidate; it is not a new semantic check. Total attempts are
not claimed to be limited to256. If no candidate budget remains
for restoration, the already verified original history is retained. Exhaustion
sets `oneMinimal:false`. With a zero budget only the initial complete source
promotion runs: no generic shrink, candidate reanalysis or candidate replay is
invoked. The original history/report is retained; no new mini is exported.
A true single-minimum claim requires checking every
remaining single deletion under the declared source-closed definite-violation
predicate and analysis budgets; a source-closed candidate left inconclusive
prevents that claim. Original transactions and operations remain
unchanged and ordered as a subsequence; version orders only prune original
facts. Search-completed orders are not written into collection facts.

For a nonzero candidate budget the final result reruns the full original promotion, checks original-fact
subset/source closure, reanalyzes the reduced history and independently replays
that report. Its final analysis must have complete source coverage and a definite
violation. `verificationPasses` lists the exported host-boundary input promotion,
generic call, final promotion, fresh final analysis and final report replay.
These fixed verification passes do not propose extra candidates and are separate
from `maxChecks`; the total computation cost is not claimed to be bounded by that
candidate number. The unchanged generic call also performs its own legacy
baseline/finalization work, not separately instrumented as host passes. The result
retains the original envelope, history hash, original sequence references, actual
candidate records and raw generic attempt. This does not produce a new shortened
database capture or a new source window.

## CLI and size limits

```text
node dist/moontxnwitness.mjs orm-profile-v3 profile-source.json --output NEW_REPORT.json --capsule NEW_CAPSULE.json
node dist/moontxnwitness.mjs verify-orm-profile-v3 profile-source.json NEW_REPORT.json
node dist/moontxnwitness.mjs replay-orm-profile-v3 NEW_CAPSULE.json --output NEW_REPLAY.json
node dist/moontxnwitness.mjs shrink-orm-profile-v3 profile-source.json --max-checks 256 --output NEW_REDUCTION.json --history NEW_MINI.json --capsule NEW_REDUCED_CAPSULE.json
node examples/orm-profile-roundtrip.mjs --out-root NEW_WORK_ROOT
```

`--options` reads a JSON object from a bounded file; reduction can instead supply
maxChecks with `--max-checks`. Duplicate options, existing output files, output
paths equal to any input, invalid UTF-8 and more than one stdin input are refused.
All requested output paths are reserved before any artifact is written. `--history`
requires an actual source-closed reverified reduced history.

UTF-8 limits are64MiB for the source envelope,8/16/8/2MiB for its four texts,
4KiB for options,64MiB for reports and128MiB for capsules and CLI replay output.
An escaped aggregate may hit its separate outer limit before all inner limits.
No truncation is accepted. Analysis exits0 for consistent,1 for violation,2 for
invalid execution/input and3 for inconclusive. Reduction budget/skipped results
exit3. Replay/verification exit0 only for matching recomputation, including an
inconclusive recorded result; this is not a completeness or absence-of-failure
claim.

## Evidence and delivery state

The initial producer evidence remains unchanged under
`verification/configured-user-profile/v024-initial`, including its first wrapper
failure and the first independent promotion failures. The corrected dedicated
core passed the independent original54 expectations over both unchanged real
producer packets. The new SDK/CLI has separate author development checks; it
does not replace that independent audit or claim public package acceptance.

The standalone example replays both retained real producer packets and an
explicitly synthetic nonrepeatable-read fixture derived from their actual SQL,
parameters, UUIDs and known versions. The changed wire observations were not
executed on PostgreSQL. Its generator and manifest record the exact copied read,
source reseal and segment/index changes. It provides an independently checked
serial-replay counterexample and source-closed4→3 reduction. The retained first
generic1-transaction attempt has incomplete source coverage and is not presented
as a closed result. The example and its fixed inputs are included in source and
portable consumer checks; actual package publication remains a separate gate.
