# Explicit category evidence and reduction

The new SDK functions are exported by dist/sdk.mjs:

- classifyV3(source, options = {})
- reduceClassificationV3(source, {category, maxChecks = 256, classificationOptions = {}})
- verifyClassificationV3(source, report, optionalOriginalOptions)
- makeClassificationCapsuleV3(source, options = {})
- makeClassificationReductionCapsuleV3(source, reductionOptions)
- replayClassificationCapsuleV3(originalCapsuleText)

These entry points leave the existing analyze, v3 replay and generic reducer
unchanged. This slice supports unique-version point-register observations.
G0 checks WW cycles. G1c checks WW/WR cycles and includes the G0 logical closure.
G2-item requires an item anti-dependency. Each category has its own search and
budget; a globally shortest cycle does not replace those searches. A witness
makes no category-shortest claim. checked-compatible concerns only the
requested categories, and is not acceptance of a full isolation model or of a
database configuration.

## Use the supplied offline example

After building, run:

    node examples/classification-roundtrip.mjs

The example uses synthetic raw captures, clearly marked in
fixtures/classification-v3/manifest.json. It proves a G2-item witness, reduces
four transactions to three, and replays both full-source capsules. The source
writer S must remain; N is the only unrelated transaction. This is a host
workflow and not a real database run.

Direct commands:

    node dist/moontxnwitness.mjs classify-v3 fixtures/classification-v3/source-closed-noisy-g2.json --capsule classification.capsule.json
    node dist/moontxnwitness.mjs shrink-classification-v3 fixtures/classification-v3/source-closed-noisy-g2.json --category G2-item --max-checks 256 --capture reduced.json --capsule reduced.capsule.json
    node dist/moontxnwitness.mjs replay-classification-v3 reduced.capsule.json

Use --options with a JSON object containing categories, maxStates and
maxEdgeChecks for classification. Reduction uses a separate JSON object with
category, maxChecks and classificationOptions. The category is mandatory,
must be one of G0/G1c/G2-item, and must also be requested by its nested
classificationOptions. Repeated CLI category or budget specifications are
rejected. Existing inputs/outputs are never overwritten.

Classification exits 1 for a refuted category, 0 for requested-category
compatibility, 2 for invalid input, and 3 for unsupported/inconclusive results.
Completed category reductions also exit 1 because their counterexample
persists. Budget-limited reduction exits 3. Replay/verification exits 0 only
when the exact current engine reproduces the saved result; a matching unknown
result stays unknown.

## Source and budget contract

Each candidate is re-normalized and searched for the fixed requested category.
The host also checks the final transaction-deletion subset, original sequence
mapping and statement/COMMIT references. Original root facts are unchanged.
A missing writer never becomes a manufactured initial value. The final
classification is recomputed and core-verified. A remaining single-delete pass
is required for oneMinimal under this source-checked category predicate; this
does not claim operation minimality or minimality without source closure.

Candidate checks are limited to 0..256. Final classification and report replay
are fixed verification overhead reported separately in verificationPasses and
are not included in that candidate budget. Zero candidate budget performs no
deletion and never claims oneMinimal. Missing sources, unsupported SQL/data
models and search exhaustion remain visible. A reliable refutation by another
requested category remains visible even when a category is unknown.

Limits are 8 MiB UTF-8 source, 4 KiB classification options, 8 KiB reduction
options, 32 MiB core result, 64 MiB host report and 128 MiB capsule. Graph limits
are 128 transactions, 4,096 operations and 50,000 edges; each requested category
has at most 100,000 states and 1,000,000 edge checks. These capacities do not
guarantee search completion.

## Exact report and capsule replay

The independent format is moontxnwitness-classification/v1. It binds the
original source text, report, original request options, actual core and host
bytes, algorithms, budgets, runtime version and source SHA-256. Unknown
algorithms/engines, extra/missing fields, and correctly re-signed changed
conclusions, counters, original observations or options are refused by exact
recomputation. Current replay is deliberately tied to the exact current
runtime; future compatibility needs an explicit reviewed migration.

Source hashes bind supplied bytes; they do not authenticate the collector or
turn assertions into SQL provenance. The full original source remains in the
host report and capsule; derived sequence changes never overwrite that source.
No automatic database run, independent release acceptance or formal performance
result is asserted by this development integration.
