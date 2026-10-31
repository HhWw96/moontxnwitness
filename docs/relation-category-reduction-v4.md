# Relation category reduction (v4 prototype)

This namespace reduces a `relation-set-v1` point-history while preserving one explicitly selected category: `G0`, `G1a`, `G1b`, `G1c`, `G2-item`, or `INT`. It does not substitute a shorter unrelated anomaly, classify full isolation models or claim a global/operation minimum.

```js
import {reduceRelationCategoryV4, makeRelationCategoryReductionCapsuleV4,
  replayRelationCategoryReductionCapsuleV4} from './dist/sdk.mjs';
const options = {category: 'G2-item', maxChecks: 256};
const report = reduceRelationCategoryV4(originalSource, options);
const capsule = makeRelationCategoryReductionCapsuleV4(originalSource, options);
const checked = replayRelationCategoryReductionCapsuleV4(capsule, options);
```

`category` is mandatory for reduction, verification and replay. Caller options also specify `maxStates` (0..100000), `maxEdgeChecks` and `maxGraphChecks` (0..1000000 each). Candidate checks are bounded at 256. Every candidate is parsed and source-checked again, with a final independent classification always performed outside the candidate-count budget.

`oneMinimal` is true only after every remaining single transaction deletion finishes and proves the selected category absent with a closed source. Unknown, invalid or source-open deletions prevent that claim. A budget exactly sufficient for that complete pass is permitted; zero or an interrupted pass cannot be minimal. Known G1a/G1b examples can remain non-minimal because deleting their necessary producer would leave a missing source. The recorded audit exposes every attempted deletion and its outcome.

Reduction uses deletion of the original events. It neither fills version orders nor synthesizes database reads. `originalEventSequence` maps every retained snapshot, data and lifecycle event back to its original sequence. Renumbering cannot heal an original missing-event window. Reports include original/reduced source closure, original sequence-window status and actual checks. Getters and SDK outputs cannot mutate retained original histories.

## CLI and runnable example

```text
node examples/relation-category-reduction.mjs
node dist/moontxnwitness.mjs reduce-relation-category-v4 examples/relation-category-reduction.json --category G2-item --output report.json --source reduced.json --capsule capsule.json
node dist/moontxnwitness.mjs verify-relation-category-reduction-v4 examples/relation-category-reduction.json report.json --category G2-item
node dist/moontxnwitness.mjs replay-relation-category-reduction-v4 capsule.json --category G2-item
```

The example removes an unrelated transaction and preserves a two-transaction item anti-dependency cycle. CLI exits are 1 for a completed retained counterexample, 0 for a non-refuted input or matching replay, 3 for unknown/unsupported/budget-limited work, and 2 for invalid inputs or failed verification. Existing files and input paths cannot be overwritten.

The new reduction capsule format is `moontxnwitness-relation-category-replay/v4`. It binds exact source/options/report bytes, the reduction contracts and expected caller category/budgets. Rehashing false evidence cannot pass core recomputation. A producer version is descriptive metadata, not an algorithm selector. Hashes do not authenticate the original observer. Source/options/report/capsule limits are 8 MiB/8 KiB/32 MiB/64 MiB of UTF-8 transport.

## Incomplete event windows

The point classification prototype now uses category semantic/algorithm/counter revision 5, graph revision 5 and journal revision 4. A normalizer-derived `sequence_gap` makes the original window incomplete: final effects, complete journals and dependency graphs are not asserted. No missing rollback event is invented.

Independent must-direct checks can retain an actual read of an exactly identified producer whose whole transaction has a confirmed aborted outcome. That G1a proof does not depend on whether an unobserved savepoint rollback occurred, and its effect/finality audit fields remain unproven. INT is retained only from a known local prefix: no sequence hole or unproved SQL/condition/write source may intervene between the observed begin and the proof. Later gaps cannot erase an already established prefix proof. G1b finality and savepoint-derived revocation remain unknown when their required window is incomplete.

The two concrete missing-rollback false positives and their legal controls are retained in `artifacts/relation-point-sequence-gap-before-fix.json`; corrected results are in `artifacts/relation-point-sequence-gap-counterexamples.json`. The original frozen prototype directory is unchanged.

This is a technical prototype checkpoint. It does not signify that every planned relation capability or the complete product release has been delivered.

The adjacent raw source and formal-INT namespaces use capture-window revision 2. They distinguish confirmed whole abort from derived savepoint revocation and block final-effect claims across missing or unprojected operations; see [source rule contracts](source-rules-v4.md#capture-window-and-proof-boundaries).

Reduction semantic/algorithm revision 2 additionally requires the original normalized source to be closed before attempting any deletion. An unprojected SQL transaction or another original coverage gap cannot be removed to upgrade the remaining record into a complete original window. The original history and reliable selected refutation remain visible with `undetermined` / `oneMinimal:false`; no candidate is accepted. Candidate counting remains revision 1.

For the current library/test workflow and runnable examples, see [relation-library-workflow.md](relation-library-workflow.md).
