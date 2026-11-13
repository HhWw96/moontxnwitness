# Model-preserving relation reduction

`reduce_relation_models_v4` selects a smaller transaction history while preserving a caller-selected model refutation from [`relation-predicate-models/v1`](relation-models-v4.md). A serializability failure cannot replace an RC refutation, and a refutation of any other requested model is not a successful candidate.

```moonbit
let options = @witness.model_options_v4().unwrap()
let reduced = @witness.reduce_relation_models_v4(
  facts,
  @witness.ElleSerializable,
  options,
  max_checks=256,
)
let record = @witness.relation_model_reduction_v4_json(reduced)
assert_true(@witness.verify_relation_model_reduction_v4(
  facts,
  record,
  @witness.ElleSerializable,
  options,
  max_checks=256,
))
```

The target model is an independent argument. The classifier uses only that target while retaining the caller's source, state and edge budgets. The report records both the supplied options and the target-specific classification options. Verification independently receives the original facts, target, options and candidate budget, then repeats the entire reduction.

The typed reducer/verifier also accept `realtime_known=false`; the SDK envelope uses `modelOptions: {realtimeKnown: false}`. The same source policy is applied to the initial, every candidate and final classification, and is bound in `sourcePolicy`. A strict-model candidate with no data refutation and unknown real-time facts stays unknown and cannot complete a minimality claim. Existing mandatory trace clock syntax is retained.

## Source and candidate protocol

The report retains `originalFacts` unchanged: original trace, complete snapshot, gaps, declared logical clients and their completeness declaration. `selectedOriginalEvents` contains the exact retained original events with their original sequence numbers, timestamps, versions, outcomes and source references. No writer, initial version, version order or inferred snapshot is fabricated.

The existing relation normalizer requires dense local event indices. A candidate therefore has an explicitly derived `analysisView`, made with the existing transaction-subset helper. `originalEventSequence` is a checked bijection from those local indices to retained original events. Before classifying a candidate, the reducer restores each local sequence/reference through this map and compares the whole event with its original. Every other root field, including the initial snapshot and gaps, must match. The dense index is a property of the analysis view and is never an additional collection fact.

Original sequence loss prevents candidate deletion: reindexing cannot heal an already incomplete window. Each deletion reruns parsing, lifecycle normalization, source closure and the selected model classifier. Removing a producer that a retained read or write still references makes that candidate source-open; the reducer neither invents an initial source nor accepts an undecided result. Logical client selections filter only the original declared memberships and retain their IDs and relative member order. Physical connection IDs never supply new logical sessions.

Only a source-closed candidate with an independently recomputed **`refuted`** result for the selected model is accepted. The original and final classifications are always computed. Final full revalidation also runs when the candidate budget is zero or exhausted.

## Budgets and minimality

The candidate-check budget is an integer in **0–256**. Each attempted single transaction deletion spends one check, including invalid, source-open and undecided candidates. Initial and final revalidation are reported separately and do not spend candidate checks. The model classifier retains its independently reported graph and exact-search limits.

`oneMinimal` is true only when a complete final pass has checked every remaining single transaction deletion and all these candidates are source-closed and conclusively not refuted under the selected model. A missing source, unsupported scope, unknown result or unfinished candidate budget prevents that claim. The reducer does not claim an operation minimum or a global minimum.

Result statuses are `reduced`, `unchanged`, `budget`, `undetermined`, `not-refuted`, `unknown`, `unsupported` or `invalid`. A useful retained refutation may still have `oneMinimal: false`; the report keeps the unresolved candidates and their reasons.

The report uses `moontxnwitness-relation-model-reduction/v4`, semantic contract `relation-predicate-model-reduction/v1`, algorithm `source-closed-single-delete-fixed-relation-model-1` and counter contract `relation-model-single-delete-candidate-checks-1`. It contains the initial/final classifications, original-event mapping, removed/selected transaction IDs, source-closure results and each attempted candidate's selected-model outcome.

Focused tests cover noise removal, exact and exhausted budgets, producer-deletion gaps, model selection, complete source retention, original sequence loss, logical-client projection, invalid/non-relation inputs and independent target/source/budget/report tampering.

## SDK and CLI

```javascript
import {reduceRelationModelsV4, verifyRelationModelReductionV4,
  makeRelationModelReductionCapsuleV4, replayRelationModelReductionCapsuleV4} from './dist/sdk.mjs';
const policy = {model: 'serializable', maxChecks: 256,
  modelOptions: {maxStates: 100000, realtimeKnown: true}};
const reduced = reduceRelationModelsV4(originalHistory, policy);
const verified = verifyRelationModelReductionV4(originalHistory, reduced, policy);
const capsule = makeRelationModelReductionCapsuleV4(originalHistory, policy);
const replay = replayRelationModelReductionCapsuleV4(capsule, policy);
```

`model` is mandatory and selects one canonical definition. `modelOptions` carries independently selected source/graph budgets, logical clients and `realtimeKnown`; `maxChecks` bounds candidate deletions. Changing the target or budget requires a new analysis, rather than accepting the embedded options from a report.

```text
node dist/moontxnwitness.mjs reduce-relation-models-v4 source.json --options target.json --output reduced.json --capsule case.json
node dist/moontxnwitness.mjs verify-relation-model-reduction-v4 source.json reduced.json --options target.json
node dist/moontxnwitness.mjs replay-relation-model-reduction-v4 case.json --options target.json
node examples/relation-model-reduction-v4-roundtrip.mjs
```

The round trip removes an unrelated transaction, retains the two-transaction Serializable refutation, independently verifies minimality, and rejects a replacement RC target. The original input remains in the capsule alongside the derived view and its event mapping.
