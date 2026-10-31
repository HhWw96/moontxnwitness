# Relation categories and captured-source rules

These are independent v4 entrypoints. `classifyV4` retains its register/list category contract and continues to return unsupported for relation classification. Existing history capsules still use `replayCapsuleV4`.

The new APIs expose three separate checks:

| Entry | Input and result |
|---|---|
| `classifyRelationV4` | Captured relation point reads and writes; selected `G0`, `G1a`, `G1b`, `G1c`, `G2-item`, `INT` rules |
| `inspectCaptureAnomaliesV4` | Raw captured register/list observations and effective write sources; supported `G1a`, `G1b` and register dirty-update diagnostics |
| `inspectInternalConsistencyV4` | Raw captured register/list program observations and reversible own-write overlays; the pinned formal `INT` rule |

These entries do not accept isolation model names or establish complete model compatibility. Relation predicates remain outside the point-category contract. Known unsupported input models return unsupported reports; malformed or unknown input models are rejected. Coverage gaps and exhausted budgets remain visible. A reliable finding remains usable when another check is unknown.

## SDK

```javascript
import {readFileSync} from 'node:fs';
import {
  classifyRelationV4, verifyRelationClassificationV4,
  makeRelationClassificationCapsuleV4, replayRelationCapsuleV4,
} from './dist/sdk.mjs';

const source = readFileSync('examples/relation-source-closure.json', 'utf8');
const options = {categories: ['G0', 'G1a', 'G1b', 'G1c', 'G2-item', 'INT']};
const report = classifyRelationV4(source, options);
console.log(report.judgment);
console.log(verifyRelationClassificationV4(source, report, options));
const capsule = makeRelationClassificationCapsuleV4(source, options);
console.log(replayRelationCapsuleV4(capsule, options));
```

The other pairs are `inspectCaptureAnomaliesV4` / `verifyCaptureAnomaliesV4` and `inspectInternalConsistencyV4` / `verifyInternalConsistencyV4`. Their capsule constructors are `makeCaptureAnomaliesCapsuleV4` and `makeInternalConsistencyCapsuleV4`. All three capsule operations use `replayRelationCapsuleV4` and the independent format `moontxnwitness-source-rules-replay/v4`.

Source, report and capsule inputs accept JSON text or serializable objects. Options accept a plain object or JSON text. Text passes through the MoonBit duplicate-key and depth guard before host inspection, including Unicode-escaped duplicate keys. Unknown options are rejected.

The runnable offline example is:

```text
node examples/source-rules-v4-roundtrip.mjs
```

## Options and limits

Relation defaults select all six named rules, `maxStates: 100000`, `maxEdgeChecks: 1000000`, and `maxGraphChecks: 1000000`. The state and edge budgets apply per cycle category. Graph/source validation has a separate budget; exhausting a cycle budget does not erase independently verified direct evidence. Categories must be distinct names from the table; no model inference or version completion is added by this interface.

Both diagnostics accept only `maxChecks`, defaulting to `1000000`. Each numeric budget may be zero and cannot exceed its stated default maximum. A zero budget normally produces unknown coverage, never a successful absence proof.

Transport limits are 8 MiB UTF-8 source, 8 KiB options, 32 MiB report and 64 MiB capsule. Limits include every source fact, finding and coverage field; oversized results are rejected rather than silently shortened by the transport. The helpers' own finding/gap caps and truncation flags remain part of their reports.

## Evidence and replay

The capsule binds the exact source text, requested options text and report text with separate SHA-256 digests. Semantic contract, algorithm, counter contract, operation and profile are fixed independently of producer version. The producer version is informational metadata.

Verification and replay recompute using caller-supplied expected options. Omitting that argument selects fixed defaults. A capsule made with custom budgets or a custom category set requires those same choices to be supplied independently during replay. A report cannot authorize its own budget by changing its execution fields.

Replay success means the supplied report was reproduced under those options. It does not authenticate the person or system that supplied the observations, prove a capture window complete, or turn an unknown/unsupported report into complete isolation analysis. Raw reads remain delivered observations across rollback; only effective writes are undone. The formal `INT` label is not a PostgreSQL product isolation-level assertion.

Pinned report identities:

| Operation | Semantic contract | Algorithm | Counter contract |
|---|---|---|---|
| Relation point categories | `moontxnwitness-relation-point-category-classification-v4-5` | `v4-relation-point-category-5` | `v4-relation-point-category-counters-5` |
| Raw captured source anomalies | `moontxnwitness-captured-source-anomalies-v4-2` | `v4-capture-effective-source-anomalies-2` | `v4-capture-source-reference-checks-2` |
| Internal consistency | `moontxnwitness-internal-consistency-v4-2` | `v4-effective-overlay-internal-consistency-2` | `v4-internal-overlay-reference-checks-2` |

## Command line

```text
node dist/moontxnwitness.mjs classify-relation-v4 SOURCE.json --options OPTIONS.json --output REPORT.json --capsule CAPSULE.json
node dist/moontxnwitness.mjs verify-relation-classification-v4 SOURCE.json REPORT.json --options EXPECTED.json
node dist/moontxnwitness.mjs inspect-capture-anomalies-v4 SOURCE.json --max-checks 1000000
node dist/moontxnwitness.mjs verify-capture-anomalies-v4 SOURCE.json REPORT.json --options EXPECTED.json
node dist/moontxnwitness.mjs inspect-internal-consistency-v4 SOURCE.json --max-checks 1000000
node dist/moontxnwitness.mjs verify-internal-consistency-v4 SOURCE.json REPORT.json --options EXPECTED.json
node dist/moontxnwitness.mjs replay-relation-v4 CAPSULE.json --options EXPECTED.json
```

`--options` is optional. Inspection and classification may write a capsule with `--capsule`; existing files and input paths are never overwritten. Verification/replay exit 0 only when valid, and 2 otherwise. Classification/inspection use 1 for refuted, 0 for checked within their stated rule scope, 2 for invalid input, and 3 for unknown or unsupported.

Category-preserving relation reduction is not part of these entries.


## Capture window and proof boundaries

Raw source-anomaly and formal-INT profiles use counter/semantic revision 2. The normalized observation sequence is checked without renumbering. A sequence hole, an unlocated input gap, or an unprojected SQL/condition operation prevents later final-effect and own-state claims for the affected transaction window. A complete local prefix can still retain an already established INT proof or a confirmed savepoint revocation. A later unknown operation cannot erase that earlier evidence.

A confirmed whole-transaction abort is separate from a revocation inferred from the effective-write journal. A uniquely identified delivered read of a confirmed aborted producer can prove G1a even when other producer events are missing; this does not establish a final committed effect. An actual write using that source also needs its own surviving write-effect window to prove dirty-update. G1b requires a complete producer window, because a missing rollback could change which write is final. Evidence exposes `writeJournalComplete`, `revocationKnown`, trusted `revertedBy` and the separate untrusted `observedLedgerRevertedBy` reference.

The standalone formal-INT entry applies the same unknown-program boundary to register and list overlays. Missing rollback observations are not replaced with invented rollback facts. Source and relation-category reductions keep the original capture sequence-window requirement, so candidate renumbering cannot repair an already incomplete input.
