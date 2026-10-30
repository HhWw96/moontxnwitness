# Structured v4 API

The v4 interfaces expose one typed boundary for declared point-register histories
and traceSchema 3 point-register, append-list and relation-set captures. They keep
raw observations, write effects, inference, judgment and execution information
separate. Existing v1/v2/v3 entry points and replay contracts remain separate.

## MoonBit

`parse_history_v4(text)` returns `Result[HistoryV4, String]`. The validated snapshot
is private and detached from the caller. `register_history_v4(history)` is the
constructor for a typed declared register history. `HistoryV4::data_model()`
identifies the model; `history_v4_json(history)` returns a detached JSON snapshot.

- `analyze_v4(history, options~)` produces `AnalysisV4`.
- `classify_v4(history, categories~, max_states~, max_edge_checks~)` produces
  `ClassificationV4` with independent category searches.
- `reduce_v4(history, preserve~, max_checks~, options~)` produces `ReductionV4`.
- `verify_v4`, `verify_classification_v4` and `verify_reduction_v4` recompute the
  supplied JSON using the caller's expected options.
- `analysis_v4_json`, `classification_v4_json` and `reduction_v4_json` return
  detached JSON. The corresponding `render_*_v4` functions serialize once at
  the transport boundary.

`preserve` is an explicit `Serializable` or `StrictSerializable` choice and must
match the original declared register model. Capture analysis currently supports
the serializable refutation target. A mismatching target returns `unsupported`
without changing the source or claiming a minimum.

## JavaScript

The portable distribution exports the functions from `dist/sdk.mjs`:

```js
import {
  analyzeV4, classifyV4, reduceV4, verifyV4,
  verifyClassificationV4, verifyReductionV4,
  makeCapsuleV4, makeClassificationCapsuleV4, makeReductionCapsuleV4,
  replayCapsuleV4,
} from './dist/sdk.mjs';

const source = {
  schemaVersion: 1,
  model: 'serializable',
  initial: { x: 'x0', y: 'y0' },
  versionOrders: { x: ['x0', 'x1'], y: ['y0', 'y1'] },
  transactions: [
    { id: 'A', status: 'committed', ops: [
      { type: 'read', key: 'x', version: 'x0' },
      { type: 'write', key: 'y', version: 'y1' },
    ] },
    { id: 'B', status: 'committed', ops: [
      { type: 'read', key: 'y', version: 'y0' },
      { type: 'write', key: 'x', version: 'x1' },
    ] },
  ],
};

const report = analyzeV4(source);
console.log(report.judgment.status); // violation
console.log(verifyV4(source, report).valid); // true

const classification = classifyV4(source, { categories: ['G2-item'] });
console.log(classification.judgment.status); // refuted
console.log(verifyClassificationV4(source, classification,
  { categories: ['G2-item'] }).valid); // true

const options = { preserve: 'serializable', maxChecks: 256 };
const reduction = reduceV4(source, options);
console.log(verifyReductionV4(source, reduction, options).valid); // true
console.log(replayCapsuleV4(makeReductionCapsuleV4(source, options), options).valid);
```

Sources and reports accept original JSON strings or serializable objects. A
source object is encoded once by the wrapper and then parsed by MoonBit. Text
input retains its original bytes for capsule binding. Inputs with malformed
Unicode, excessive UTF-8 size, duplicate JSON keys, excessive nesting or invalid
model structure are rejected. Wire parse failures have `status: 'invalid'`;
verification failures have `valid: false`. Unknown options and unknown model or
category names are errors rather than ignored configuration.

Current v4 operations use the current MoonBit runtime directly. They do not start
a compatibility worker. Historical replay continues through its existing APIs.

## Options and bounds

| Operation | Options and fixed ceilings |
| --- | --- |
| Analysis | `maxAttempts: 100000`, `maxStates: 100000`, `maxOperationChecks: 1000000`, `maxCachedStates: 50000` |
| Classification | `categories: ['G0', 'G1c', 'G2-item']`, `maxStates: 100000`, `maxEdgeChecks: 1000000` |
| Reduction | Required `preserve: 'serializable'` or `'strict-serializable'`; `maxChecks: 256`; optional `analysisOptions` with the analysis fields above |

Omitted numeric fields use the listed defaults. Integers from zero to the fixed
ceiling are accepted. Zero is an explicit zero-work budget, not an unlimited
request. Exhausted searches remain inconclusive; exhausted reductions do not
claim transaction one-minimality. `oneMinimal` is a transaction single-deletion
result under the chosen model-refutation predicate, not a global or operation
minimum. Reduction does not yet preserve a caller-selected anomaly category.

Sources are limited to 8 MiB UTF-8, options to 8 KiB, reports to 32 MiB and
capsules to 64 MiB. `V4_LIMITS` exports these transport bounds. Register exact
analysis retains its 12 committed-transaction bound and 512-operation bound;
list/relation exact analysis retains 6 committed transactions and 128 operations.
Graph classification and exact enumeration have separate limits. Classification
currently supports register and bounded list `G0`, `G1c`, `G2-item` checks only.
Relation classification returns `unsupported`. A completed category check does
not accept a full isolation model or certify a database. The planned expanded
Elle model set is not part of this interface's current support claim.

## Evidence identity and replay

Every report includes explicit `format`, `schemaVersion`, `semanticContract`,
`algorithm` and `execution.counterContract`. These identities describe the
meaning and work-counting rules independently of the product version.

The capsule format is `moontxnwitness-replay/v4` with schema 4. It binds the exact
`sourceText`, serialized requested `optionsText` and MoonBit `reportText` to
individual SHA-256 values. Its semantic, algorithm and counter identities must
match the recognized report identities. `producer.version` is outer metadata;
it does not authorize a different algorithm, budget or model.

```js
const capsule = makeCapsuleV4(source);
console.log(replayCapsuleV4(capsule).valid); // fixed default options

const expected = { maxAttempts: 0 };
const limited = makeCapsuleV4(source, expected);
console.log(replayCapsuleV4(limited).valid); // false: defaults differ
console.log(replayCapsuleV4(limited, expected).valid); // true
```

Analysis and classification replay use fixed default options when the caller
omits the second argument. Custom budgets/categories require independently
supplied expected options. Reduction replay always needs an explicit
preservation target; it cannot obtain that authority from the capsule. Reports
are fully recomputed under the expected options, including observations,
effects, inference, judgment, budgets and counters. Unknown contracts, duplicate
keys, altered content or hashes, and changed source/model/budget are rejected.

A valid replay means semantic reproduction under supplied facts. It does not
authenticate the collector or server, prove that observations are genuine, or
turn incomplete coverage into a complete history. An unsupported or inconclusive
report can be faithfully reproduced and remains unsupported or inconclusive.

## Command line

```text
node dist/moontxnwitness.mjs analyze-v4 SOURCE.json --output REPORT.json --capsule CAPSULE.json
node dist/moontxnwitness.mjs classify-v4 SOURCE.json --options CATEGORIES.json
node dist/moontxnwitness.mjs reduce-v4 SOURCE.json --preserve serializable --max-checks 256 --source MINI.json
node dist/moontxnwitness.mjs verify-v4 SOURCE.json REPORT.json --options EXPECTED.json
node dist/moontxnwitness.mjs verify-classification-v4 SOURCE.json REPORT.json --options EXPECTED.json
node dist/moontxnwitness.mjs verify-reduction-v4 SOURCE.json REDUCTION.json --preserve serializable
node dist/moontxnwitness.mjs replay-v4 CAPSULE.json --options EXPECTED.json
```

`--options` reads a JSON file. Its shape is the matching SDK operation's options
object; replay uses the original operation's shape. For reductions, `--preserve`
and `--max-checks` may be used instead of those JSON fields. Specifying a field in
both places is rejected. At most one input may use `-` for standard input.
Output paths must differ from every input and other output, and must not exist;
files are reserved before writing and existing files are never overwritten.

Exit codes are 0 for a completed compatible analysis/category check or a valid
verification/replay, 1 for a definite refutation, 2 for invalid input/output or
failed verification, and 3 for inconclusive, unsupported or budget-limited work.
Successful replay of an inconclusive report still exits 0 because reproduction
succeeded; the reproduced report remains inconclusive.

Run `node scripts/v4-sdk-test.mjs` after building for transport, capsule, explicit
budget, three-model, legacy-worker and CLI output-protection checks. MoonBit
white-box tests prefixed `v4 wire` cover the corresponding core JSON boundaries.
