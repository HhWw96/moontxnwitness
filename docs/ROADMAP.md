# Roadmap and delivery history

## Next delivery v0.1.1 through v0.2.0

The [implementation plan](roadmap-v0.2.0.md) proposes eight small releases for
driver capture, ordinary-table version provenance, ORM and transaction lifecycle,
list append, bounded relational predicates, anomaly/model classification, real
business debugging, and performance/scale. It preserves the v0.1.0 contract and
uses v0.1.0 as the direct regression baseline. The proposed work is not yet
implemented or released; v0.2.0 requires its explicit correctness and evidence gates.

## v0.0.7 through v0.1.0 delivery history

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
development hooks, not stable SDK interfaces. Rendering in v0.0.7 uses its original
structured serializer; later versions measure their shipped streaming serializer.
Phase results on a no-cycle report
measure the specified isolated operation, not a complete user-visible result.

Targets: graph group geometric mean >=2x and RSS ratio <=0.7; search and
reduction >=2x; control P95 regression <=max(10%,2ms). Summary output must not
be compared with a full baseline report. A correctness pass does not mean all
performance targets passed. Raw failed measurements are retained.

## Stable boundary in v0.1.0

Versioned point reads/writes only. Preserve existing default budgets and v1
evidence traversal. Advanced profiles and v2 evidence carry explicit effective
budgets and algorithm identifiers. Exhaustion and a negative proof are distinct.
The author must still perform the documented installation/demo/explanation
exercise; registration, group membership and organizer decisions remain separate.

## v0.0.8 implementation

Edge equality and hashing cover every provenance field, including the reason.
No transitive dependencies are dropped. SCC and BFS use integer endpoints with
stable adjacency/root order and epoch-marked reusable buffers. Coverage and
model comparisons reuse the writer index. Full dependency arrays, per-key
coverage and version maps are streamed with official JSON string escaping and
a per-report escaped-string cache. Duplicate-key scanning still decodes escaped
keys and uses the official JSON parser for syntax validation.

The v0.0.7 exhaustive-failure capsule is retained as a legacy compatibility sample.
Performance receipts include intermediate attempts that missed the target; do not
select the older smoke receipt as final release evidence.

## v0.0.9 results

The full balanced search group is 3.69x faster than v0.0.6 in this local measurement;
the 8-transaction hard case is 10.36x. All 10,320 histories are independently
checked through both legacy and balanced entry points, plus eight 9-12 transaction
proof fixtures. This search release does not claim all roadmap performance goals
are complete; its balanced graph group measured 1.92x, and large reduction comes next.

## v0.0.10 accepted measurement

The final full protocol in `verification/releases/0.0.10/release-gate-v010.json`
measured graph 2.665x, search 5.023x and reduction 2.178x geometric-mean speedup
against v0.0.6, with graph peak RSS ratio 0.6972 (30.28% lower). Control P95
regressions stayed within the stated allowance. All full semantic comparisons
passed. Earlier misses are retained, including the initial ASCII-encoder attempt;
it was removed rather than using that attempt as successful release evidence.

RT ordered pairs are unique by validated transaction IDs and no longer allocate
redundant hash-set entries. SCC, shortest cycle and topological order share one
immutable integer adjacency. Unchanged initial-only reads skip unnecessary local
maps, while all transactions remain in graph and RT accounting.

## v0.0.11 actual-database acceptance

The local PostgreSQL 18 suite completed 20 RR rounds and 20 Serializable
server-abort/fresh-retry rounds, including a second run on a newly initialized
cluster with a clean hash-verified optional driver. Both histories, 100 observed
transactions, SQL events, two-transaction reduction and three v2 capsules were
checked. The owned temporary cluster was stopped afterward. Independent Linux
PostgreSQL CI is a required separate public release check. The analyzer algorithms
are unchanged from v0.0.10; this version includes a smoke-only benchmark and
references the accepted v0.0.10 full protocol rather than claiming a new full run.

## v0.1.0 convergence

The frozen balanced profile passed the full protocol: graph 2.820x, search
5.557x and reduction 2.215x; graph peak RSS ratio 0.69977. Full scenario tables
and limits are in performance.md. Legacy entry points remain unchanged; the
portable demo recommends balanced and exports v2. Fixed fixture JSON, pinned
public baseline fetching and immutable timestamped measurement receipts make
retesting self-contained after the documented toolchain setup.

All five small versions have public download and registry-consumer proof. The
v0.0.11 first Linux workflow initialization failed; its immutable source was
subsequently tested by a repaired workflow with separately attested source and
workflow commits. This history is retained. The current publisher waits for
Windows/Linux, Native and PostgreSQL CI before package publication. Participant
installation/explanation and organizer states remain independent requirements.
