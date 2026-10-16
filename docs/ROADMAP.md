# Performance and real-database delivery

Accepted scope: v0.0.7 performance evidence, v0.0.8 graph/allocation improvements,
v0.0.9 bounded optimized completion and v2 evidence, v0.0.10 large reduction,
v0.0.11 actual PostgreSQL capture, then v0.1.0 API stabilization.

The October 2026 official public page requires MoonBit as the primary language,
traceable public development, runnable examples/tests, substantive new work,
open-source compliance and explainable AI assistance:
https://moonbitlang.github.io/Hackathon2026/

These performance goals are our engineering goals, not organizer scoring weights.
No award, organizer acceptance or registration is inferred from a release.

## Reproduce measurements

`npm run benchmark -- --baseline PATH_TO_V006_CORE` measures the same fixture
with full JSON input and full JSON output on both engines, with five warmups,
30 observations and three independent process batches in alternating order.
The original compiled v0.0.6 core can be extracted from its public portable ZIP.
The local default is `artifacts/baseline-v0.0.6/core.mjs` (not redistributed).
`--quick` is a smoke check and cannot satisfy the performance release gate.

Receipts in `verification/releases/VERSION/` record fixture hashes, raw samples,
runtime/CPU/OS, cold module load, first analysis, P95 and process peak RSS.
Phase hooks time parse, dependency inference (including validation/coverage),
SCC/shortest cycle, legacy completion, reduction, and full report serialization
independently, with already-prepared input outside each timed section. They are
development hooks, not stable SDK interfaces. Phase results on a no-cycle report
measure the specified isolated operation, not a complete user-visible result.

Targets: graph group geometric mean >=2x and RSS ratio <=0.7; search and
reduction >=2x; control P95 regression <=max(10%,2ms). Summary output must not
be compared with a full baseline report. A correctness pass does not mean all
performance targets passed. Raw failed measurements are retained.

## Stable boundary

Versioned point reads/writes only. Preserve existing default budgets and v1
evidence traversal. Advanced profiles and v2 evidence carry explicit effective
budgets and algorithm identifiers. Exhaustion and a negative proof are distinct.
The author must still perform the documented installation/demo/explanation
exercise; registration, group membership and organizer decisions remain separate.
