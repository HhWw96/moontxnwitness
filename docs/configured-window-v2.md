# Configured point-window input producer v2

`ConfiguredCaptureWindowV2` combines an explicit V2 installation, a synchronous
local connection factory, two read-only PostgreSQL snapshots and the original
bounded capture journal. Business code supplies its normal SQL and parameters.
It does not create transaction histories or issue manual writer checkpoints.

```python
from moontxnwitness_capture.configured_window_v2 import (
    ConfiguredCaptureWindowV2, SourceInputsV2,
)

window = ConfiguredCaptureWindowV2(
    "new-window-directory", config, control_connection, policy,
    SourceInputsV2.from_directory("source-install-directory"), opt_in=True,
)
connect = window.psycopg_factory(original_writer_connection_factory)
with connect() as connection:
    row = connection.execute(original_point_query, original_parameters).fetchone()
bundle_path = window.seal()
```

Install sources explicitly first. The control connection must be a dedicated,
idle, autocommit psycopg 3.3.6 connection using the selected source-owner role.
Writer factories return new idle non-autocommit connections. Close all enrolled
connections before sealing; up to 32 participants can be enrolled. The original
point producer supplies automatic writer probes and actual commit observation.

## Snapshot and durability contract

Each boundary uses an acknowledged `REPEATABLE READ READ ONLY` transaction. It
records the actual database snapshot and server peer, rechecks environment,
catalogs, permissions and source scope, and independently enumerates:

- every current row with its installed version;
- every retained source-ledger entry, including INITIAL and DELETE events.

Visible rows must match their retained source entry and full business values.
Enumeration starts at zero **in each snapshot**. A version is an allocation
identity, not commit order: an earlier allocated write can commit after a later
allocated one. A later analysis must compare full identity sets rather than use
the previous maximum as a cross-snapshot watermark.

The default boundary limits are 4,096 rows and 4,096 retained effects, each
independently selectable from 0 to 16,384. Logs have the selected source policy's
byte budget and retain original native text plus actual control deliveries.
Budget exhaustion, missing sources, changed catalogs, failed control responses
and unsealed logs fail explicitly; they never return a partial successful input.

The start/end inputs are digest-bound into the original lifecycle log. Sealing
waits for the capture journal and tail synchronization, rereads original files,
checks their seals, and produces a bounded 32 MiB bundle containing installation,
start/end snapshots, lifecycle and original diagnostic trace. The producer does
not silently delete retained logs or sources.

Snapshot and trace inputs are checked against their original export digests
before packaging. The success receipt is published exclusively only after its
pending file synchronizes. Pending files and `window-failure.json` are diagnostic
failure evidence; consumers must require the formal receipt and reject a failure
marker. A file whose name merely ends in `.pending.json` never grants success.

## Independent analysis

`analyzeConfiguredWindowV4(bundleText, {config, policy, ...limits})` replays the
original installation, both boundary snapshots, lifecycle and native results in
MoonBit. Supply `config` and `policy` independently; the bundle cannot select its
own admission policy. The input must be the original UTF-8 bundle text. The
result binds its exact bytes, derived history, operation references and selected
budgets. `verifyConfiguredWindowV4(bundleText, report, options)` recomputes the
complete result using the same caller-selected policy and budgets.
See the [SDK and CLI reference](configured-window-v2-sdk.md) for text-preserving
command-line input, exit codes and standalone loading.

```js
import {readFileSync} from 'node:fs';
import {analyzeConfiguredWindowV4, verifyConfiguredWindowV4} from './dist/sdk.mjs';
const bundleText = readFileSync('window/configured-window-input.json', 'utf8');
const options = {
  config: JSON.parse(readFileSync('config.json', 'utf8')),
  policy: JSON.parse(readFileSync('source-policy.json', 'utf8')),
  maxSourceChecks: 1_000_000,
  maxPointChecks: 1_000_000,
};
const report = analyzeConfiguredWindowV4(bundleText, options);
const verified = verifyConfiguredWindowV4(bundleText, report, options);
console.log(report.status, verified.valid);
```

Each actual write must consume exactly one new retained effect belonging to the
confirmed transaction/backend. The verifier matches key, predecessor, complete
OLD/NEW values and original assignment. Every delivered read must resolve to a
starting row or a verified write, with transaction and observation order checked.
Native field identities are bound to the independently checked catalog. UUIDs
retain canonical equality identity; complete typed business rows become opaque
row bodies in the derived `relation-set-v1` history.

The main formal target is `serializable` under atomic full-row point semantics.
`model` retains the original row-graph report and `itemCategory` retains its
`G2-item` check. `serialReplay` is a separate bounded complete-program serial
certificate. A complete serial order can establish compatibility even when a
graph absence source remains ambiguous; it never rewrites that graph result.
`modelDecision` identifies the actual basis. A graph refutation and a valid
serial certificate must not coexist; contradictory evidence is rejected.

The initial full-window path covers confirmed commits, complete point SELECT,
one-row INSERT/UPDATE/DELETE and transaction-local reads. Zero-row writes,
rollback/unknown outcomes, savepoints, incomplete fetches and unsupported SQL
remain `unknown`. A zero-row UPDATE is an observed conditional result, not an
operation that may be silently omitted or fabricated as a SELECT. No connection
pool identity or client BEGIN time creates a session/snapshot fact.

## Limits and evidence boundary

The input format is `moontxnwitness-configured-window-input/v2`, with the separate
`postgres18-configured-point-window-observations/v2` contract. Python component
checks and durable input seals establish observations for independent replay.
They do not authenticate a collector or grant a model conclusion. The receipt's
`completeWindow`, `moonbitSourceVerified` and `modelCoverageAccepted` remain false
in the producer receipt. The independent core sets `coverageComplete`,
`sourceMappingVerified` and `writerWindowVerified` only after replaying those
obligations. `sourceAuthenticated` remains false: hashes detect record changes
but do not authenticate an observer or make fabricated observations genuine.
Unknown SQL, incomplete reads and unresolved commits remain in the original
journal. Existing V1 point windows and analysis APIs keep their original rules.

The hard window limits are 32 transactions and 128 business statements. Source,
point, model-source, edge and serial-operation checks each have independently
selected limits of at most 1,000,000. Exact serial replay retains the existing
6-committed-transaction/128-operation limit and at most 100,000 states; graph
capacity does not raise exact-search capacity. Exhaustion cannot grant a
certificate. Original boundary row/effect limits are separate. The report is
bounded to 32 MiB.

## Validation

The offline suite covers installation byte/config bindings, boolean sequence
tampering, row/effect budgets, missing or changed sources, independent full-ledger
rescans, original errors, failed synchronization and participant closure.

The real PostgreSQL 18.6 campaign runs int64, C-text and UUID primary keys. Each
captures committed CRUD and then holds version **5** uncommitted while version
**6** commits. An intermediate snapshot sees 6 but not 5; after 5 commits, the
ending snapshot includes both. All three complete-ledger comparisons pass.
These raw-window checks are separate from model admission. With `--with-analysis`,
the harness additionally executes original SQL for full CRUD with negative reads
and transaction-local reads, real RR write skew, ordered Serializable and a
zero-row-write skew boundary. For each primary-key type, independent replay must
produce a compatible serial certificate, `G2-item` refutation, compatible control
and explicit unknown respectively. No model history is handwritten by the harness.

Run the existing owned-cluster harness with `--with-window`:

```text
python -B scripts/configured-source-v2-postgres.py --bin <postgres18.6-bin> --output D:\CodexScratch\new-window-run --with-window --with-analysis
node scripts/configured-window-v2-check.mjs --core dist/sql-projection-v2-core.mjs --receipt D:\CodexScratch\new-window-run\receipt.json --output D:\CodexScratch\new-window-run\analysis-checks.json
```

Linux CI uses the same harness with `--dsn-env` and an explicit
`--owned-database` acknowledgement for its disposable PostgreSQL 18.6 service.
The original bundle, native logs, compiled core and rehashed-tamper results are
retained as job artifacts.

Supply a new output directory. Database files, native logs and original failures
stay outside the repository. No performance comparison is inferred from this run.
## Paged source snapshots

Pass `snapshot_profile="paged-v1"` when creating a configured window to read
visible rows and retained effects in ordered pages of up to 128 observations.
The verifier checks the original native delivery, cursor progression and final
empty page inside the same repeatable read transaction. Every page uses the
existing raw byte budget. Page-budget exhaustion is a source coverage gap.

Paged analysis verifies the complete source inventories and restricts the
model's initial row state to keys referenced by independently verified point
statements. Set `pointFootprintOnly: true` to apply the same projection to
row-by-row snapshots for a comparison. Paged windows require the projection.
Replay requires the
same independently selected options. The source logs retain every row and
effect. Use the original row reader for existing v2 replay and historical reports.

### Snapshot and sealing measurements

In the PostgreSQL 18.6 fixture with 260 initialized rows, paging reduces the SQL
statements for each boundary snapshot from 522 to 8. The complete raw window
is 2,026,192 bytes with paging and 3,673,961 bytes with one-row observations.
The MoonBit verifier checks the full source inventory in both windows.

The producer revalidates each original sealed log one record at a time. On
identical saved boundaries, three independent Python processes per version
each used five warmups and 30 measured calls. The one-row log stage went from
18.65 to 13.13 ms median and from 25.71 to 15.24 ms P95. The paged log stage
went from 2.47 to 1.76 ms median and from 4.32 to 2.67 ms P95. These figures
cover local log revalidation. Database latency, SDK analysis time and process
RSS require separate measurements.

### Capture cost pilot

The small cost pilot runs the same 24 point read-update transactions in three
orders. A uses the direct driver. B adds source tracking. C adds native result
and transaction capture, both paged snapshots and durable window sealing. The
complete-window throughput includes the snapshot and sealing work. Transaction
P95 measures the business statements and commit acknowledgement.

```sh
python -B scripts/configured-window-cost-pilot.py --dsn-env MTW_PG_DSN --owned-database --output NEW_RUN
node scripts/configured-window-cost-pilot-verify.mjs --receipt NEW_RUN/receipt.json --core dist/sql-projection-v2-core.mjs --output NEW_RUN/independent-check.json
```

Use a disposable PostgreSQL 18.6 instance. The verifier compares the final
business data and checks all captured operations and writer bindings. The pilot
uses the synchronous point producer and retains raw timings for a single small
workload. The final three checked windows had identical business outcomes.
Complete-window throughput for C ranged from 8.9% to 16.2% of A, and transaction
P95 was 8.68–11.82 times A. Opening and sealing together took 55%–63% of the
complete captured-window time. A full workload campaign is needed to assess
capture throughput and tail latency at scale.
