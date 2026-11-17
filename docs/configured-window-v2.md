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

## Analysis boundary

The input format is `moontxnwitness-configured-window-input/v2`, with the separate
`postgres18-configured-point-window-observations/v2` contract. Python component
checks and durable input seals establish observations for independent replay.
They do not authenticate a collector or grant a model conclusion. The receipt's
`completeWindow`, `moonbitSourceVerified` and `modelCoverageAccepted` remain false
until a separate core admission path validates all source and lifecycle facts.
Unknown SQL, incomplete reads and unresolved commits remain in the original
journal. Existing V1 point windows and analysis APIs keep their original rules.

## Validation

The offline suite covers installation byte/config bindings, boolean sequence
tampering, row/effect budgets, missing or changed sources, independent full-ledger
rescans, original errors, failed synchronization and participant closure.

The real PostgreSQL 18.6 campaign runs int64, C-text and UUID primary keys. Each
captures committed CRUD and then holds version **5** uncommitted while version
**6** commits. An intermediate snapshot sees 6 but not 5; after 5 commits, the
ending snapshot includes both. All three complete-ledger comparisons pass.
These are raw-window correctness checks, with model admission tracked separately.

Run the existing owned-cluster harness with `--with-window`:

```text
python -B scripts/configured-source-v2-postgres.py --bin <postgres18.6-bin> --output D:\CodexScratch\new-window-run --with-window
```

Supply a new output directory. Database files, native logs and original failures
stay outside the repository. No performance comparison is inferred from this run.
