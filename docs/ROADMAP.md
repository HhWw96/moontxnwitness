# Roadmap and delivery history

## Current source — v0.5.9

The current source base provides `classifyModelsV4`, registered inference modules,
`classifyRelationModelsV4` and `reduceRelationModelsV4`, with independent verification
and source-bound replay. The [feature matrix](feature-matrix-v4.md) and its
[machine-readable declaration](feature-matrix-v4.json) define the supported inputs,
model obligations and limits. Fourteen selectable definitions are conditional
checks, not a complete arbitrary-SQL or Elle-equivalence claim.

v0.5.0 reuses immutable original-source/order indexes and one full relation graph
per model call while retaining complete reports, provenance, budgets and counters.
Its actual measurements and limits are recorded in the
[v0.5.0 full-call results](model-performance-v050.md) and
[dated changelog](../CHANGELOG.md). Earlier performance numbers apply to their
original entry points and workloads.

## v0.5.1 — native reports and capability discovery

Implementation scope:

- Add JavaScript native object-report exports for register/list/atomic-row model
  classification and relation-predicate model classification. SDK entry points
  retain the JSON path for cores without those exports and preserve existing
  reports, evidence identity, counters, budgets and replay contracts.
- Add `capabilities [--format json|text]` for local discovery of the loaded version,
  actual SDK/native exports and declared model/source requirements. Discovery
  performs no analysis, database/network access, migration or file write. Its
  adjacent declaration and module are packaged and digest-bound; see
  [capability discovery](capabilities.md).
- Validate complete native/JSON results, independently selected verification
  options, unchanged capsules and strict CLI/portable asset behavior. New
  performance measurements must compare complete calls under the same workload;
  v0.5.0 measurements do not establish v0.5.1 performance.

Broader automatic SQL/ORM coverage, mixed data models and larger exact searches
require explicit source, validity and completion contracts. General execution
diagnosis alone does not supply a closed source window or a model conclusion.
Source/profile gaps and exhausted budgets continue to produce `unknown`.

## Configured-window delivery and subsequent increments

The v0.5.5 source includes independently reconstructed point SQL
and native/delivery consistency checks, explicit source-installation components,
bounded original window-input sealing, independent source/snapshot admission and
source-bound automatic relation-history analysis. The three-key PostgreSQL
campaign preserves out-of-order commits through complete ledger scans and runs
normal CRUD, RR write skew, ordered Serializable and zero-row-write boundaries.
See [window analysis](configured-window-v2.md), [source admission](source-admission-v2.md),
[snapshot admission](snapshot-admission-v2.md) and [projected result verification](projected-result-v2.md).
The v0.5.5 package consolidates the synchronous v0.5.2–v0.5.5 development increments.

| Version | Scope | Evidence before promotion |
| --- | --- | --- |
| v0.5.2 | Configurable synchronous full-row point CRUD, including dynamic int64, text and UUID primary keys, with an independent source-window contract | One parser across three table layouts; original SQL, bindings, delivered results, writer identities and committed effects independently aligned; missing facts remain explicit |
| v0.5.3 | Source-closed model-preserving reduction and offline explanations | Actual five-to-two-transaction PostgreSQL reduction, independent replay, source mappings and retained original windows |
| v0.5.4 | Explicit structured verification profile, with the original default retained | Full-output comparison and cross-profile verification; both formal measurement runs failed a common P95 control, so this profile remains experimental |
| v0.5.5 | Synchronous factory lifecycle and offline window transport | Factory failures preserve the original exception and controller ownership; in-flight factories prevent premature sealing; capsules require independent configuration, policy and budgets |
| v0.5.6 | MoonBit 0.10.21, native async psycopg, synchronous SQLAlchemy `NullPool`, and projection cache | Cross-target regression, paired ORM results, actual PostgreSQL writer and retry checks, and clean installation |
| v0.5.7 | Scoped async SQLAlchemy `NullPool` and original FastAPI Users base-user CRUD and refresh | Paired original-business runs, actual result consumption, confirmed outcomes and retry identity |
| v0.5.8 | Bounded paging of source snapshots and faster window sealing | Complete snapshot coverage, stable model results, and stage timings on the same inputs |
| v0.5.9 | Optional asynchronous pool reuse, full capture-cost measurements and integrated regression | Pool lease and reset evidence, complete A/B/C logs, reference checks, source-closed replay and fresh package consumers |
| v0.6.0 | Freeze recommended APIs, source contracts, budgets, support matrix and reproducible examples | Cross-target regression, reference comparisons, clean public installation and source-bound replay |

The synchronous CRUD work has its own contract; it does not relabel the earlier
point-window or diagnostic formats. Candidate SQL recognition is only an input
description until the core verifies execution, source closure and model mapping.
Stable subsets retain explicit capabilities and do not promote unexecuted
database or performance work to completed results.

The next integration also includes model-preserving source-closed reduction and
offline explanations over verified synchronous windows. Original bundles remain
required; selections carry checked original-event mappings. The real PostgreSQL
campaign includes three source-dependent read-only noise transactions around a
two-transaction RR anomaly, rather than claiming a reduction from an already
minimal pair. The scoped async ORM producer shares the committed point-window
contract. The
[structured-profile measurements](window-structured-verification.md) retain both
failed P95 controls and do not qualify the profile for default promotion.

The [native asynchronous adapter](configured-async-window-v2.md) captures owned
psycopg connections on a single business event loop. The controller takes
snapshots on its owner thread. SQLAlchemy and pool leases still require their
own enrollment and result-delivery checks.

## Historical records

The records below retain their original version-specific plans and measurements.
Their descriptions of future work describe those historical versions. Current
interfaces and scope are defined above and in the maintained feature matrix.

### v0.2.0 bounded convergence

The [stable support matrix](stable-scope.md) defines the declared register, fixed-key presence, SQL-template/cache, list, relation, selected-cycle and execution-capsule interfaces. Each capability retains explicit inputs, budgets, coverage gaps and replay rules. Actual release acceptance comes from its versioned receipts; a source candidate or old database replay is not a new database execution.

The [current iteration arrangement](remaining-execution-plan.md) allows installable stable subsets. Full automatic SQL/ORM, six-model classification, complete production integrations and broader performance/scale remain future work. The [original 30–40 day plan](remaining-execution-plan-2026-10-21.md) is retained as a technical reference, rather than a joint prerequisite for every stable release. No unmeasured speedup or RSS result is claimed for v0.2.0.

### Historical v0.0.7–v0.1.0 notes

The following text describes its original versions, engineering targets and evidence. Dated engineering targets and measurements remain linked to their original records.

### v0.0.7 through v0.1.0 delivery history

Accepted scope: v0.0.7 performance evidence, v0.0.8 graph/allocation improvements,
v0.0.9 bounded optimized completion and v2 evidence, v0.0.10 large reduction,
v0.0.11 actual PostgreSQL capture, then v0.1.0 API stabilization.

These measurements track implementation behavior, reproducibility, correctness and open-source compatibility. Performance targets remain engineering goals.

### Reproduce historical measurements

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

Historical targets for that development series: graph group geometric mean >=2x and RSS ratio <=0.7; search and
reduction >=2x; control P95 regression <=max(10%,2ms). Summary output must not
be compared with a full baseline report. A correctness pass does not mean all
performance targets passed. Raw failed measurements are retained.

### Stable boundary in v0.1.0

Versioned point reads/writes only. Preserve existing default budgets and v1
evidence traversal. Advanced profiles and v2 evidence carry explicit effective
budgets and algorithm identifiers. Exhaustion and a negative proof are distinct.
Installation and demonstration checks use the documented consumer procedure.

### v0.0.8 implementation

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

### v0.0.9 results

The full balanced search group is 3.69x faster than v0.0.6 in this local measurement;
the 8-transaction hard case is 10.36x. All 10,320 histories are independently
checked through both legacy and balanced entry points, plus eight 9-12 transaction
proof fixtures. This search release does not claim all roadmap performance goals
are complete; its balanced graph group measured 1.92x, and large reduction comes next.

### v0.0.10 accepted measurement

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

### v0.0.11 actual-database acceptance

The local PostgreSQL 18 suite completed 20 RR rounds and 20 Serializable
server-abort/fresh-retry rounds, including a second run on a newly initialized
cluster with a clean hash-verified optional driver. Both histories, 100 observed
transactions, SQL events, two-transaction reduction and three v2 capsules were
checked. The owned temporary cluster was stopped afterward. Independent Linux
PostgreSQL CI is a required separate public release check. The analyzer algorithms
are unchanged from v0.0.10; this version includes a smoke-only benchmark and
references the accepted v0.0.10 full protocol rather than claiming a new full run.

### v0.1.0 convergence

The frozen balanced profile passed the full protocol: graph 2.820x, search
5.557x and reduction 2.215x; graph peak RSS ratio 0.69977. Full scenario tables
and limits are in performance.md. Legacy entry points remain unchanged; the
portable demo recommends balanced and exports v2. Fixed fixture JSON, pinned
public baseline fetching and immutable timestamped measurement receipts make
retesting self-contained after the documented toolchain setup.

All five small versions have public download and registry-consumer proof. The
v0.0.11 first Linux workflow initialization failed; its immutable source was
subsequently tested by a repaired workflow with separately attested source and
workflow commits. This history is retained. The publisher procedure recorded for
this development series required Windows/Linux, Native and PostgreSQL CI before
package publication, with separate installation and explanation checks.
