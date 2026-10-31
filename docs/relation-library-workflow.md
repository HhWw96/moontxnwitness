# Relation point analysis and reproducible category reduction

The relation library adds independent point-history entry points for analysis, evidence verification and reduction. It also exposes raw register/list source checks and formal internal consistency checks. Existing `classifyV4` and history-capsule semantics remain unchanged.

## Run the offline examples

After building the package with the configured MoonBit toolchain:

```text
npm run build
node examples/source-rules-v4-roundtrip.mjs
node examples/relation-category-reduction.mjs
```

The first example checks a relation point history, a captured aborted-source read and an internal consistency counterexample, then replays their evidence. The second removes unrelated transactions while retaining a specifically selected `G2-item` counterexample. Its reduced history keeps a mapping to original event sequence numbers and is checked again before the result is returned.

## Library interface

| Operation | SDK entry |
|---|---|
| Relation point categories | `classifyRelationV4`, `verifyRelationClassificationV4` |
| Captured register/list source anomalies | `inspectCaptureAnomaliesV4`, `verifyCaptureAnomaliesV4` |
| Captured register/list formal INT | `inspectInternalConsistencyV4`, `verifyInternalConsistencyV4` |
| Relation category reduction | `reduceRelationCategoryV4`, `verifyRelationCategoryReductionV4` |

Relation point categories are `G0`, `G1a`, `G1b`, `G1c`, `G2-item` and `INT`. A direct source finding can remain reliable when cycle search exhausts its budget. Coverage and unknown rules remain visible. These point-category entry points do not claim complete predicate analysis or accept isolation model names. The formal INT definition is separate from a database product's named isolation level.

Each namespace has an explicit capsule maker. Use `replayRelationCapsuleV4` for the classification/source-rule capsules and `replayRelationCategoryReductionCapsuleV4` for category reduction. Producer versions are metadata; fixed semantic/algorithm/counter identities and the caller's expected options select verification. Hashes bind the supplied source/options/report bytes and do not authenticate the original observer.

```js
import {
  classifyRelationV4, verifyRelationClassificationV4,
  reduceRelationCategoryV4, verifyRelationCategoryReductionV4,
  makeRelationCategoryReductionCapsuleV4,
  replayRelationCategoryReductionCapsuleV4,
} from './dist/sdk.mjs';

const categories = {categories: ['G2-item'], maxGraphChecks: 100000};
const report = classifyRelationV4(originalSource, categories);
console.log(verifyRelationClassificationV4(originalSource, report, categories));
const options = {category: 'G2-item', maxChecks: 256};
const reduced = reduceRelationCategoryV4(originalSource, options);
console.log(verifyRelationCategoryReductionV4(originalSource, reduced, options));
const capsule = makeRelationCategoryReductionCapsuleV4(originalSource, options);
console.log(replayRelationCategoryReductionCapsuleV4(capsule, options));
```

Reduction requires an explicit category. A smaller unrelated anomaly cannot replace the selected category. Source-open deletions, unknown results and exhausted checks prevent `oneMinimal`. The original source window must be closed; deleting an unobserved statement cannot repair the original coverage. Only a completed check of every remaining single transaction deletion permits transaction single-minimality.

## CLI

```text
node dist/moontxnwitness.mjs classify-relation-v4 examples/relation-source-closure.json
node dist/moontxnwitness.mjs reduce-relation-category-v4 examples/relation-category-reduction.json --category G2-item --output report.json --source reduced.json --capsule capsule.json
node dist/moontxnwitness.mjs verify-relation-category-reduction-v4 examples/relation-category-reduction.json report.json --category G2-item
node dist/moontxnwitness.mjs replay-relation-category-reduction-v4 capsule.json --category G2-item
```

Custom budgets/category selections must also be supplied as the expected options when verifying or replaying. Duplicate flags and duplicate JSON option keys are rejected. Output paths cannot replace the source or existing files. Transport limits remain 8 MiB source, 8 KiB options, 32 MiB report and 64 MiB capsule. Detailed options and support boundaries are in [source-rules-v4.md](source-rules-v4.md) and [relation-category-reduction-v4.md](relation-category-reduction-v4.md).

## Maintained checks

`npm test` retains the existing core, compatibility, oracle and adapter checks and also runs:

- `scripts/v034-source-rules-sdk-test.mjs` for source-rule SDK/CLI and capsule boundaries.
- `scripts/relation-category-reduction-sdk-test.mjs` for category-preserving reduction, source closure, verification and CLI boundaries.
- `scripts/v034-maintenance-bindings-test.mjs` for build/source/runtime binding guards using tiny synthetic fixtures only.
- `scripts/v034-public-boundary-independent-test.mjs` for the retained 84 public-boundary semantic cases.
- Both offline examples above, validating their actual JSON output and replay result.

The maintained 84-case runner no longer depends on a private historical freeze file. It requires current `dist/build-manifest.json`, matches its source fingerprint and core/capture digests, verifies current command wrappers against their built copies, and records actual file hashes before and after the run. A missing dist produces an explicit `not-executed` result and exit 3; the full test flow builds first and rejects any unexecuted result. New evidence is placed under a unique `artifacts/v034-public-boundary-maintenance/run-*` directory. Historical independent 85-check receipts are not overwritten or relabelled as a new independent review.

The original semantic assertion body is retained unchanged apart from newline normalization and has its own SHA-256 guard. A fresh maintained run is a regression run, not an independent review or proof of public publication. Database runs, native execution and performance measurements are recorded separately.

## Source and portable consumers

Source downloads retain the complete current `src` tree, command wrappers and the SDK/audit helpers. Their fresh consumer rebuilds first, then actually runs both relation SDK/CLI suites, the build-binding guards and the retained 84 semantic cases. The source fingerprint requirement is unchanged: missing sources cannot be replaced by the report's own fingerprint or silently skipped.

Portable downloads have a separate `scripts/v034-portable-runtime-test.mjs` check. It imports the shipped SDK only, exercises real classification, raw source rules, INT, category reduction, CLI verification and both capsule formats, and checks supplied-evidence tampering. It does not import a source fingerprint helper, run a compiler or claim the 84 source audit. Both offline examples also run from the portable consumer. This probe can run with neither `src` nor `cmd` present. Existing compatibility audits can still require narrowly listed current source excerpts; those are separate from this runtime-only capability check and are not a complete source checkout.

The distribution inventory enables these requirements for version 0.3.4 and later, or while the current SDK already exposes both relation classification and category reduction before the version bump. Missing helpers, compiled host modules or the reduction example input fail closure validation. Fresh-consumer results record source audit and portable runtime checks separately. Public download verification and the original compatibility suites remain separate checks.
