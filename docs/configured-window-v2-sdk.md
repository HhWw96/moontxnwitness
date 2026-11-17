# Configured PostgreSQL window analysis

`analyzeConfiguredWindowV4` connects an explicitly installed PostgreSQL 18 source
window to the MoonBit relation analysis. It verifies the original installation
log, both effects snapshots, actual result deliveries, transaction identities,
commit responses and the source closure before checking `serializable`.

The V2 observation bundle remains original UTF-8 JSON text. The caller supplies
the SQL configuration, source policy and verification limits independently.
Embedded configuration and limits cannot authorize the analysis.

## SDK

```js
import {readFileSync} from 'node:fs';
import {
  analyzeConfiguredWindowV4,
  verifyConfiguredWindowV4,
} from './dist/sdk.mjs';

const bundleText = readFileSync('configured-window-input.json', 'utf8');
const options = {
  config: readFileSync('config.json', 'utf8'),
  policy: readFileSync('policy.json', 'utf8'),
  maxSourceChecks: 1_000_000,
  maxPointChecks: 1_000_000,
};
const report = analyzeConfiguredWindowV4(bundleText, options);
const verification = verifyConfiguredWindowV4(bundleText, report, options);
console.log(report.status, verification.valid);
```

Do not parse and re-encode the bundle before either call: its digest binds the
original bytes. `config` and `policy` accept original JSON text or ordinary JSON
objects. Use original JSON text when a document contains integers beyond
JavaScript's exact integer range. Verification also accepts original report text.

The default SDK shares its existing MoonBit core instance. Applications that
only need this API can import the same functions from
`dist/configured-window-v2-standalone.mjs`, which uses the dedicated V2 core.

## Source-closed model reduction

```js
import {reduceConfiguredWindowV4, verifyConfiguredWindowReductionV4,
  explainConfiguredWindowV4} from './dist/sdk.mjs';

const target = {
  config: options.config,
  policy: options.policy,
  preserveModel: 'serializable',
  windowOptions: {maxSourceChecks: 1_000_000, maxPointChecks: 1_000_000},
  reductionOptions: {
    maxChecks: 256,
    modelOptions: {maxSourceChecks: 1_000_000, maxStates: 100_000,
      maxEdgeChecks: 1_000_000},
  },
};
const reduction = reduceConfiguredWindowV4(bundleText, target);
const checked = verifyConfiguredWindowReductionV4(bundleText, reduction, target);
const html = explainConfiguredWindowV4(bundleText, report, options, {
  reduction, reductionOptions: target,
});
```

The adapter reconstructs the source window before selecting transactions from
its relation history. Original SQL, native observations, delivered results,
snapshots and source records remain in the unchanged original bundle. Every
candidate reruns original-event binding, source closure and the selected model
check; an omitted writer cannot become an invented initial version.

`preserveModel` is required and currently accepts `serializable`.
`reductionOptions.maxChecks` defaults to 256 and accepts 0–256. Nested
`modelOptions` accepts only `maxSourceChecks` (up to 1,000,000), `maxStates`
(100,000) and `maxEdgeChecks` (1,000,000). These use the existing relation
reducer's units and default maximums. The independent window budgets remain in
`windowOptions`. Models, source profiles, client declarations and real-time
assumptions cannot be supplied through the reduction budget object.

The original atomic-row result remains under the window contract. The selected
model reduction uses the separate `relation-predicate-models/v1` and
`relation-predicate-model-reduction/v1` contracts; it preserves a model refutation,
without promising to preserve a separately unselected anomaly category.
A completed original serial certificate that contradicts the new model
refutation causes an invalid composition with both reports retained.

`oneMinimal` requires a completed final pass over every remaining transaction
single deletion. Unknown, source-open or unfinished checks prevent that claim.
Verification returns separate flags:

- `reportMatches`: exact canonical recomputation of the supplied report.
- `valid`: a faithfully recomputed reduction report on a complete verified source
  window; this can also describe an unknown or not-refuted model result.
- `refutationVerified`: the selected model refutation was preserved.
- `oneMinimalVerified`: the preserved refutation completed the required final
  single-deletion checks.

Thus `valid: true` alone does not authorize an anomaly or minimality claim.
Reduction reports are bounded to 64 MiB and independent options to 512 KiB;
the existing 8 MiB derived-history and 32 MiB nested-report limits remain.
`CONFIGURED_WINDOW_REDUCTION_V4_LIMITS` exposes host maximums.

## Offline explanation

`explainConfiguredWindowV4(bundleText, report, options)` independently verifies
the original report before presenting it. Its optional fourth argument above
requires both a reduction report and independent reduction options, then verifies
that report too. A failed verifier produces no HTML.

The report links original SQL and parameters, executed SQL, native metadata,
actual business deliveries, row versions, source effects and model witnesses.
It follows explicit `historySeq`/`originalStatementSeq` bindings; reduced witness
references pass through the verified `originalEventSequence` map. Missing
references fail instead of being reconstructed from array positions. Native rows
and business-delivered cells are displayed separately.

The HTML escapes input values and uses an offline content policy. Its output
limit is 64 MiB. Rendering does not run SQL, contact a service, authenticate an
observer or infer a repair result. Reduction verification, model refutation and
single-minimality are displayed as separate flags.

## CLI

```sh
node dist/moontxnwitness.mjs analyze-configured-window-v4 \
  configured-window-input.json --config config.json --policy policy.json \
  --options limits.json --output report.json

node dist/moontxnwitness.mjs verify-configured-window-v4 \
  configured-window-input.json report.json --config config.json --policy policy.json \
  --options limits.json --output verified.json

node dist/moontxnwitness.mjs reduce-configured-window-v4 \
  configured-window-input.json --config config.json --policy policy.json \
  --options target.json --output reduction.json

node dist/moontxnwitness.mjs verify-configured-window-reduction-v4 \
  configured-window-input.json reduction.json --config config.json --policy policy.json \
  --options target.json --output reduction-verified.json

node dist/moontxnwitness.mjs explain-configured-window-v4 \
  configured-window-input.json report.json --config config.json --policy policy.json \
  --options limits.json --reduction reduction.json --reduction-options target.json \
  --output explanation.html
```

`--config` and `--policy` are required. `--options` defaults to `{}` and is read
verbatim by the strict MoonBit parser. Output files must be new files. One input
may be `-` for standard input. Analysis exit codes are 0 for checked-compatible,
1 for refuted, 2 for invalid input, and 3 for unknown; verification returns 0
only when the report matches a recomputation with complete coverage.
Reduction requires `--options` with an explicit `preserveModel`. Its exit codes
are 1 for reduced/unchanged preserved refutations, 0 for not-refuted, 2 for
invalid and 3 for unknown, budget or undetermined. Verification exit 0 means
faithful report recomputation; inspect its separate refutation/minimality flags.
Explanation exit 0 means verified offline rendering. `--reduction` and
`--reduction-options` must appear together.

## Scope and limits

The source contract is
`postgres18-source-bound-point-crud-row-slots/v2`. It covers the configured,
controlled single-table point CRUD window and does not change earlier point
window or capsule semantics. Raw SQL, executed SQL, native results and actual
business delivery remain separate observations. Row effects must match the same
transaction, predecessor and commit response. UPDATE effects are not invented
SELECT observations. Partial fetches, unobserved operations, incomplete sources,
unknown SQL and unconfirmed transactions preserve a coverage gap.

The initial window limits are 32 transactions and 128 business statements.
Limits are independently selected for analysis and verification:

| Option | Default | Maximum |
| --- | ---: | ---: |
| `maxSourceChecks` | 1,000,000 | 1,000,000 |
| `maxPointChecks` | 1,000,000 | 1,000,000 |
| `maxRows` | 4,096 | 16,384 |
| `maxEffects` | 4,096 | 16,384 |
| `maxStates` | 100,000 | 100,000 |
| `maxEdgeChecks` | 1,000,000 | 1,000,000 |
| `maxModelSourceChecks` | 1,000,000 | 1,000,000 |
| `maxSerialOperationChecks` | 1,000,000 | 1,000,000 |

`projectionOptions` selects the independent configuration-bound projection
options. A zero budget is allowed; exhaustion returns unknown rather than
granting coverage. Bundle and report limits are 32 MiB each; configuration and
options are 256 KiB each; policy is 8 KiB. The SDK exports
`CONFIGURED_WINDOW_V4_LIMITS` for these maximums.

The report retains installation and snapshot checks, operation source references,
the projected relation history, model evidence, category evidence and serial
replay. A graph refutation and a completed serial replay are distinct evidence
paths; both are included unchanged. `sourceAuthenticated` remains false: checking
supplied evidence does not authenticate the database server or collector.

## Consumer checks

The [reduction contract](configured-window-reduction-v2.md) describes independent
source closure, selection mappings and the three separate verification flags.

```sh
node scripts/configured-window-v2-host-test.mjs
node scripts/configured-window-v2-runtime-test.mjs
node scripts/configured-window-v2-runtime-test.mjs --receipt /path/to/original-receipt.json
```

The first command tests host boundaries with a fake core. The second uses the
current compiled SDK and standalone core without a database. The optional receipt
rechecks external original database bundles; it does not execute a new database
workload. Build manifests bind the new runtime closure separately under
`configuredWindowRuntimeSha256`, preserving the previous four-slot
`configuredCoreSha256` inventory.
