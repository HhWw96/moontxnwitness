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

## CLI

```sh
node dist/moontxnwitness.mjs analyze-configured-window-v4 \
  configured-window-input.json --config config.json --policy policy.json \
  --options limits.json --output report.json

node dist/moontxnwitness.mjs verify-configured-window-v4 \
  configured-window-input.json report.json --config config.json --policy policy.json \
  --options limits.json --output verified.json
```

`--config` and `--policy` are required. `--options` defaults to `{}` and is read
verbatim by the strict MoonBit parser. Output files must be new files. One input
may be `-` for standard input. Analysis exit codes are 0 for checked-compatible,
1 for refuted, 2 for invalid input, and 3 for unknown; verification returns 0
only when the report matches a recomputation with complete coverage.

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
