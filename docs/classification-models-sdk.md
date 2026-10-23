# Explicit isolation-model checks

This SDK entry is separate from category classification:

- classifyModelsV3(source, options = {})
- verifyModelsClassificationV3(source, report, optionalOriginalOptions)
- makeModelsClassificationCapsuleV3(source, options = {})
- replayModelsClassificationCapsuleV3(originalCapsuleText)

The category-only classifyV3 and its fixed-category point-register reduction
retain their previous options and meaning. Model-preserving reduction and
relation six-model classification are not available in this slice.

The six frozen definition identifiers are adya-pl-1-v1, adya-pl-2-v1,
adya-pl-2.99-v1, elle-generalized-si-v1, adya-pl-3-v1 and strict-pl-ss-v1.
The SDK selects all six by default; models accepts a nonempty unique subset.
maxStates and maxEdgeChecks apply separately to each core rule, at maxima
100,000 and 1,000,000. normalizationOptions may explicitly request only the
existing dislock-f9946f0-sql-proof-1 SQL profile; the host does not guess SQL
provenance.

## Run

    node examples/classification-models-roundtrip.mjs
    node dist/moontxnwitness.mjs classify-models-v3 fixtures/classification-models-v3/list-skew.json --capsule models.capsule.json
    node dist/moontxnwitness.mjs replay-models-classification-v3 models.capsule.json

The example is synthetic and performs no database operations. It demonstrates
write skew which is compatible with the stated generalized SI definition and
refutes the serial graph definition. It also contrasts missing client intervals
with a separately bound synthetic interval source. Synthetic confirmation does
not establish any real collector or database acceptance.

An options file for a subset can contain:

    {"models":["adya-pl-2-v1","adya-pl-3-v1"],"maxStates":100000}

Use --options for that file, --output for a new report, and --capsule for a
self-contained new capsule. verify-models-classification-v3 accepts source and
report paths. Outputs never overwrite original files. Exit 1 means at least one
requested model has a reliable refutation; 0 means the requested model checks
are compatible within their scope; 3 means unsupported or incomplete; 2 means
invalid. Replay exit 0 means exact reproduction and preserves an unknown result.

## Scope and source evidence

The core supports versioned point registers and its declared append-list graph
profile: six committed transactions, 128 operations, at most one append per
transaction per key, no savepoints, and complete captured same-key order.
Register limits are 128 transactions, 4,096 operations and 50,000 edges.
Broader list observations may provide a reliable direct source-specific
refutation while leaving graph compatibility unknown. Missing order is not a
searched order copied into the capture.

Reports retain each required rule, graph status, validity gaps and the internal
validity applicability precondition. For example, a graph-compatible PL3 result
cannot become an operational serial compatibility claim when INT is refuted
or unknown. Relation and predicate six-model coverage remain unsupported.
A reliable refutation remains visible even when another check is incomplete.

Raw v3 time or sequence does not prove real-time order. The optional
moontxnwitness-classification-source/v1 envelope carries traceText,
intervalEvidenceText, lifecycleText and journalIndexText. The core verifies
their existing byte bindings, sealed lifecycle records, transaction/call
references and native COMMIT confirmation. Same-domain end < start is required;
equal samples create no edge. BEGIN does not establish a server snapshot.
Journals with sourceClosed=false or missing source closure stay incomplete.
Journal segment payloads are not rehashed by this module. Hashes do not
authenticate the collector.

The host independently binds the entire original envelope plus all four exact
component SHA values. Its distinct capsule format is
moontxnwitness-isolation-models/v1 and its host algorithm is isolation-model-host-1.
Verification reproduces original options, the explicit effective model options,
all source text, model/rule results, budgets, counters and actual core/host bytes.
Extra/missing fields, unknown engines/algorithms and correctly re-signed changed
conclusions or source evidence are refused. Current capsules require the exact
current runtime; any future cross-version migration needs separate review.
Existing v1/v2/v3 and category capsule formats retain their original behavior.

Limits are raw trace 8 MiB, strict source envelope 32 MiB with each component
8 MiB, options 8 KiB, core report 32 MiB, host report 96 MiB and capsule 192 MiB.
These are independent bounds, not a promise every maximum-sized combination
fits or finishes. Core report verification is fixed overhead disclosed in
verificationPasses.

The development tests also read four exact previously retained PostgreSQL
collector packets and nine pre-recorded list evidence regressions. No database
is rerun by these host checks. Original diagnostic gaps are preserved; the
collector packets are not presented as complete model acceptance. Full release
consumers, cross-target checks, independent review and formal performance remain
separate acceptance work.
