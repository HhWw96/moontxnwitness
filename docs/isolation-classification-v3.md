# Isolation classification v3 contract

The v0.2.6 integration adds the explicit six-model SDK and CLI described in
[classification-models-sdk.md](classification-models-sdk.md). Its current support
boundaries are in [stable-scope.md](stable-scope.md). The records below describe
earlier development candidates, including original failures; their historical
runtime version and test totals are not current release results. The separately
reproduced handoff has 51 selected tests, while earlier author records below
retain their original 52-test count. Final current-engine checks are recorded in
`verification/summary.json` and the versioned release receipts when executed.

## Historical development and repairs

This module is a draft following the separately validated category-search slice.
The first v026 source check and the first selected category/model run failed;
their original diagnostics and expectations remain in `verification/classification-v3/v026/`.
After correcting two list finding references to `readSeq`, the inherited handoff
selection passed 38/38 without changing its assertions. Two additional immutable
initial-prefix counterexamples then failed against that draft. The repaired JS
candidate passes the same 38 tests plus four separate audit regressions (42/42).
A subsequent independent audit found false G1b labels in that candidate. The
last-version/source-applicability repair retains those same 42 assertions, adds
ten separate regressions, and passes strict JS plus 52/52 tests. Nine frozen raw
SDK captures pass the pre-recorded semantic checks and self-verification. These
are author results; cross-target and independent semantic acceptance are still
pending. It is not a released six-model implementation.

`classify_v3_json` keeps the old category-only behavior for a raw capture with
category options. An explicit `models` array selects the new model engine;
`normalizationOptions.sqlProof` can explicitly select the existing dislock SQL
proof profile. No SQL provenance is guessed from returned values. Relation-model
classification is unsupported in this slice.

The graph definitions remain those in `roadmap-v0.2.0.md`. G0 is included in the
G1c logical closure, and complete G1c searching includes WW-only cycles. PL1
checks G0; PL2 checks G1a/G1b/G1c; PL2.99 adds item anti-dependency cycles;
generalized SI checks INT and G-nonadjacent in addition to G1; PL3 checks G1/G2;
strict adds proven real-time relationships to the graph. G0 may also be checked
explicitly, without changing the implications. Point/list profiles have only
item anti-dependencies, so G2-item is the applicable G2 category there. Predicate
anti-dependencies and relation six-model coverage are not implemented here.

PL3 and strict preserve their frozen graph definitions and expose `graphStatus`.
Before an operational serial claim can use graph compatibility, an independent
`internalValidity` applicability precondition must be satisfied. A failed or
unknown precondition keeps that operational result inconclusive; a known graph
refutation remains a refutation. Generalized SI retains its explicit INT rule.
This distinction must not silently redefine existing model identifiers.

Register G1a/G1b proofs retain committed reader, original effect, confirmed writer
outcome and final-write evidence. Reads of revoked savepoint effects are not
silently assigned a broader anomaly class. Internal checks preserve delivered
reads and restore own-write state on savepoint rollback. List source identities
and business values are distinct. The initial list graph profile is limited to
at most six committed transactions, 128 operations, one append per transaction
per key, no savepoints, and complete observed order for same-key append identities.
Broader raw models can yield supported direct evidence, but missing order does
not become an inferred capture fact or a compatible graph result. A complete
list observation must preserve the captured immutable initial prefix and match
its unique identities and values. Invalid observations are listed separately in
`validityGaps`; they supply no WR/RW/WW or complete-version G1b/INT evidence.
They are not themselves classified as an isolation violation. An independently
matched aborted item may still prove G1a, and another independent valid cycle
may refute a model while the full graph remains incomplete.

Each cycle rule has its own 100,000 state/1,000,000 edge-check budget, with register
structure bounded at 128 transactions/4,096 operations/50,000 edges. Searches for
G0, G1c, G2-item and nonadjacent anti-dependencies are separate; a global shortest
cycle does not stand in for them. A nonadjacent witness must satisfy the cyclic
wrap condition as well as every adjacent edge pair. An exhausted rule is unknown;
another reliable rule refutation remains visible.

Optional strict evidence uses a separate
`moontxnwitness-classification-source/v1` envelope containing exact trace,
client-interval evidence, lifecycle JSONL and journal-index text. The existing
vector-tested SHA-256 implementation binds the three source byte streams; the
lifecycle header, contiguous sequences, terminal prefix seal, paired calls,
transaction/connection identities, and original journal event references are
checked. Only a confirmed native COMMIT response permits a transaction end.
Only same-process monotonic `end < start` establishes real-time order. Equal
samples establish no order. BEGIN is not a server snapshot and raw trace time
or sequence does not automatically become trusted real-time evidence.

Current diagnostic observer journals with sourceClosed=false or missing source
closure stay unknown for complete strict checks. Hashes bind source bytes and do
not certify collector authenticity. Journal segment payloads are not recomputed
by this optional module. Original v3 trace semantics are not changed by the new
input envelope. The SDK capsules and CLI were pending at the time of these historical records;
the v0.2.6 integration is documented in the current SDK guide.

At that historical checkpoint, pending independent checks included cross-target compilation, model fixtures,
list initial-prefix validity, full common-range replay comparison, real collector
sidecars, database cases, end-user installation and performance. No new scale or
performance guarantee is claimed by this draft.

## Preserved prefix counterexamples

`prefix-audit-before/` freezes the raw captures, original false-refutation SDK
reports, compiler/test failures and a pre-fix runtime binding. The two invalid
initial-prefix captures previously generated two RW edges and refuted PL2.99,
PL3 and strict. `prefix-audit-after/` binds the same raw captures to the repaired
reports: no dependency edges, explicit validity gaps and inconclusive models.
The valid-prefix control retains its actual write-skew refutation. A fourth test
checks that a valid cycle remains visible alongside an unrelated invalid read.
None of these are database runs, production evidence or performance results.

The cyclic non-adjacency condition follows the published
[G-nonadjacent definition](https://jepsen.io/consistency/phenomena/g-nonadjacent),
including the closing/first edge pair. The original 4,096 three-node typed-graph
oracle and all original INT applicability assertions remain unchanged.

## Direct list version evidence

The first independent review found three false G1b labels in the 42-test
candidate. Their original reports and the unchanged independent first/addon
expectations remain frozen under `g1b-source-audit-before/`. The source-based
semantic decision was recorded before the repair; it does not change any formal
model identifier or inherited test assertion.

G1b identifies the version actually read. For a source-valid append-list value,
only its final item identifies that version's append. If W appends `a` and later
`b`, while R reads `[a,c]` ending in another writer's final `c` (or R's own `c`),
merely containing `a` does not prove that R read W's intermediate version. The
specific G1b witness now binds the actual final item and its external non-final
same-key source. This follows the fixed
[Elle list G1b implementation](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/list_append.clj#L114-L144)
and [G1b definition](https://jepsen.io/consistency/phenomena/g1b). Propagation
through an intervening transformation is a separate phenomenon; this repair
does not add an intermediate-update classifier.

A complete read must also preserve each external producer's captured append
prefix. Reads `[b]` or `[b,a]` from W's `a` then `b` record an explicit
`list_external_producer_prefix_invalid` applicability gap. Such reads cannot
supply graph edges or complete-version G1b/INT claims in this scope. Savepoint
writers are excluded from this flat prefix inference.

G1a is checked independently per observed item, following
[Elle's aborted-read rule](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/list_append.clj#L83-L112).
A same-key, same-value, unique earlier source from a confirmed aborted writer
remains a reliable G1a proof despite another shape gap or unrelated bad item.
Wrong-key or wrong-value items do not establish that proof. An incomplete rule
cannot erase this specific refutation, and malformed values are never declared
fully compatible merely because a graph could not be built.