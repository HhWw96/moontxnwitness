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
- `classify_v4(history, categories~, max_states~, max_edge_checks~, list_graph~,
  max_list_graph_checks~)` produces
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
| Classification | `categories: ['G0', 'G1c', 'G2-item']`, `maxStates: 100000`, `maxEdgeChecks: 1000000`; optional `listGraph: 'effective-v1'`, `maxListGraphChecks: 1000000` |
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
defaults to register and bounded list `G0`, `G1c`, `G2-item` checks;
`G-single` is an additional explicit category as described below.
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

## Explicit G-single category

The default classification request stays `['G0', 'G1c', 'G2-item']`, with the
original `v4-source-bound-category-bfs-1` algorithm and
`v4-category-seed-bfs-counters-1` counter contract. Existing default and explicit
old-category capsules retain their meaning.

Request `classifyV4(source, { categories: ['G-single'] })` to search for a cycle
with exactly one item RW edge and only WW/WR edges in the remaining path. A
request can explicitly include any distinct subset of all four supported names.
With the legacy graph, the new request uses algorithm
`v4-source-bound-category-g-single-1` and counter
contract `v4-category-g-single-seed-bfs-counters-1`. A witness records
`requestedCategory: 'G-single'`, `specificCategory: 'G-single-item'`,
`rwScope: 'item'` and `rwEdgeCount: 1`. The older G2-item category definition is
unchanged. Category checks do not accept complete isolation models.

The corresponding capsule requires independently supplied expected categories:

```js
const requested = { categories: ['G-single'] };
const capsule = makeClassificationCapsuleV4(source, requested);
console.log(replayCapsuleV4(capsule, requested).valid);
```

## Source anomaly inspection

`inspect_anomalies_v4(history, max_checks~)` and
`verify_anomalies_v4(history, report, max_checks~)` are separate MoonBit APIs.
They accept a validated `HistoryV4`. They do not change `analyze_v4`, old category
checks, or the meaning of existing reports. Invalid source structure and
duplicate write identities rejected by the history constructor remain outside
this typed inspection API; the JSON wrapper returns an invalid input result.

JavaScript exports `inspectAnomaliesV4`, `verifyAnomaliesV4` and
`makeAnomaliesCapsuleV4`. The matching capsule uses the generic
`replayCapsuleV4` function with operation `inspection`:

```js
import { inspectAnomaliesV4, verifyAnomaliesV4, makeAnomaliesCapsuleV4,
  replayCapsuleV4 } from './dist/sdk.mjs';

const report = inspectAnomaliesV4(source);
console.log(report.status, report.findings, report.coverage);
console.log(verifyAnomaliesV4(source, report).valid);
console.log(replayCapsuleV4(makeAnomaliesCapsuleV4(source)).valid);
```

Supported register/list checks distinguish:

- A committed transaction reading its own later write/append identity, with
  transaction-local operation positions. A later observation on a different
  connection is a source-order gap and never proves a future read.
- A missing source, an existing writer with unknown outcome, and a conflicting
  list identity/key/value. Missing sources retain their coverage gaps and do not
  become G1a or proven unwritten reads.
- Contradictory supplied version-order facts. List witnesses can use complete
  source-valid observations, captured initial list order and effective append
  order within the same transaction. Reverted effects do not impose committed
  append order. Each cycle edge identifies its original fact; this diagnostic
  does not automatically label the cycle G0/G1a.

Original source data and business values are retained once in
`observations.document`. Evidence references identify transaction, zero-based
**data-operation** position, original event seq and returned item position.
Control events keep their original identities. This avoids repeatedly embedding
large list results in every finding.

Reports use format `moontxnwitness-anomaly-inspection/v4`, semantic contract
`moontxnwitness-source-anomalies-v4-1`, algorithm
`v4-source-index-and-order-witness-1`, and counter contract
`v4-anomaly-source-checks-1`. The sole option is `maxChecks`, an integer from
0 to 1,000,000, defaulting to 1,000,000. Unknown fields and duplicate JSON keys
are rejected. Budgets, coverage gaps and truncation remain visible; transport
limits remain those of v4. Internal limits are 10,000 data operations, 10,000
order constraints, 256 reported findings/gaps and 4,096 total witness constraints.

`checked` means the supported diagnostic checks completed under the supplied
coverage. It does not accept any isolation model. `findings` can coexist with
incomplete coverage; a reliable finding is retained when other work cannot
finish. Relation inspection is explicitly unsupported. Reproduction does not
authenticate the collector or server.

```text
node dist/moontxnwitness.mjs inspect-anomalies-v4 SOURCE.json --output REPORT.json --capsule CAPSULE.json
node dist/moontxnwitness.mjs inspect-anomalies-v4 SOURCE.json --max-checks 0
node dist/moontxnwitness.mjs verify-anomalies-v4 SOURCE.json REPORT.json --options EXPECTED.json
node dist/moontxnwitness.mjs replay-v4 CAPSULE.json --options EXPECTED.json
```

A custom inspection budget requires the same independently supplied expected
options for verification and replay. CLI exit 1 means concrete diagnostic
findings, not an assertion that a full isolation model was checked; exit 3
covers gaps, exhausted budgets and unsupported inputs. Existing output path
protection applies. CLI option files are guarded by MoonBit before host parsing
so duplicate keys, including Unicode-escaped aliases, cannot disappear silently.

`node scripts/v033-sdk-test.mjs` checks the new category and inspection paths;
the original `scripts/v4-sdk-test.mjs` remains the default-interface regression.

When the shared findings/gaps output bound is full, a new proved witness takes
priority over an earlier gap. The report retains `findingsTruncated: true` and
incomplete coverage so evicted details cannot turn unknown work into acceptance.


## Effective append-list graph

`listGraph: 'effective-v1'` explicitly selects a source-aware append-list graph.
It supports several appends to the same key in a transaction, distinct item
identities with equal business values, intermediate own reads and savepoint
rollback. It derives constraints only from actual source-valid reads, initial
order and effective write order. Unknown sources or incompatible item order
isolate the affected key; a proved witness from another covered key is retained.

```js
const options = {
  listGraph: 'effective-v1',
  maxListGraphChecks: 1000000,
  categories: ['G-single', 'G2-item'],
};
const report = classifyV4(listCapture, options);
console.log(verifyClassificationV4(listCapture, report, options).valid);
const capsule = makeClassificationCapsuleV4(listCapture, options);
console.log(replayCapsuleV4(capsule, options).valid);
```

The construction budget is an independent integer from zero to 1,000,000. Its
consumption and coverage appear in `execution.listGraphConstruction`;
`inferences.listGraph` keeps the provenance and isolated gaps. Exhaustion does
not become a compatible result. Non-list input returns `unsupported`.

This profile uses algorithm `v4-source-bound-category-list-effective-1` and
counter contract `v4-list-effective-category-counters-1`, including when
`G-single` is selected. The semantic contract remains
`moontxnwitness-category-classification-v4-1`. A capsule cannot select this
profile for its caller: verification and replay require the same independently
supplied expected options.

The default stays `listGraph: 'legacy'`, preserving old graph semantics and
report bytes. An explicit equivalent legacy/default construction budget is
accepted; a non-default construction budget with the legacy graph is rejected.
Use an options file with `classify-v4`, `verify-classification-v4` or `replay-v4`
for the same controls. Run `node scripts/list-effective-sdk-test.mjs` for the
profile, budget, evidence binding and compatibility checks.

## Register lost-update inspection

`inspect_lost_updates_v4(history, max_checks~)` and
`verify_lost_updates_v4(history, report, max_checks~)` add a separate direct
register diagnostic. The source-only inspector and default classification do
not implicitly enable it. The JavaScript exports are `inspectLostUpdatesV4`,
`verifyLostUpdatesV4` and `makeLostUpdatesCapsuleV4`.

```js
import { inspectLostUpdatesV4, verifyLostUpdatesV4,
  makeLostUpdatesCapsuleV4, replayCapsuleV4 } from './dist/sdk.mjs';

const history = {
  schemaVersion: 1, model: 'serializable', initial: { x: 'x0' },
  transactions: [
    { id: 'A', status: 'committed', ops: [
      { type: 'read', key: 'x', version: 'x0' },
      { type: 'write', key: 'x', version: 'a1' },
    ] },
    { id: 'B', status: 'committed', ops: [
      { type: 'read', key: 'x', version: 'x0' },
      { type: 'write', key: 'x', version: 'b1' },
    ] },
  ],
};
const report = inspectLostUpdatesV4(history);
console.log(report.findings.some(f => f.kind === 'lost-update')); // true
console.log(verifyLostUpdatesV4(history, report).valid); // true
console.log(replayCapsuleV4(makeLostUpdatesCapsuleV4(history)).valid); // true
```

Following the [fixed Elle lost-update checker](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/txn.clj#L191),
a witness groups committed transactions whose first actual external read of a
key observes the same unique version identity and precedes their final
effective write. The source can be an initial version or a confirmed committed
final version. Per-key identity, original read, source writer, final write and
program positions are retained. Business-value equality is not version identity;
blind writes, version adjacency and list prefixes do not supply a read.
Savepoint rollback removes undone write effects while retaining earlier reads.

For captures, actual final writes must also have a confirmed predecessor source
or valid own-write overlay. A same-statement captured predecessor is a write
source fact, distinct from a declared `versionOrders` constraint; it is not a
fabricated SELECT. Unknown or missing provenance remains a gap, and independent
reliable findings can coexist with such gaps. This profile does not implement
dirty-update checks. Lists and relations return `unsupported`.

The profile is `register-source-lost-update/v1`, with algorithm
`v4-register-source-lost-update-1` and counter contract
`v4-register-source-lost-update-checks-1`. It shares the source-inspection
format, semantic contract, transport bounds and `maxChecks` ceiling. Custom
budgets again need independent caller expectations. A lost-update witness lists
`lost-update`, `write-skew`, `G2-item` and `G2` implications; a completed direct
diagnostic does not accept an isolation model or authenticate captured facts.

```text
node dist/moontxnwitness.mjs inspect-lost-updates-v4 SOURCE.json --output REPORT.json --capsule CAPSULE.json
node dist/moontxnwitness.mjs verify-lost-updates-v4 SOURCE.json REPORT.json --options EXPECTED.json
node dist/moontxnwitness.mjs replay-v4 CAPSULE.json --options EXPECTED.json
```

The CLI uses the same bounded options, duplicate-key guard, diagnostic exit codes
and safe output reservation as source inspection. Run
`node scripts/lost-update-sdk-test.mjs` for source-bound proofs, independent
budgets, capsule tampering and CLI checks.

### 读取自身未来写入的分类依据

`inspectAnomaliesV4` 的 `future-read` 证明使用已提交事务内的原始操作位置与唯一写入身份；跨事务的客户端事件先后不构成此证明。它沿用固定 Elle 提交 [4e359e5 的异常蕴含定义](https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/consistency_model.clj#L142-L147)：读取本事务稍后才执行的写入视为退化的事务自 WR 依赖，映射到 `G1c`、`G1`。这与类别搜索返回的多事务环证据分别记录；来源诊断不表示已完成全部隔离模型检查，也不表示运行过 Elle 的寄存器检查器。
