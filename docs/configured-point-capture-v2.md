# Synchronous configured point-CRUD producer v2

The development producer `PointCaptureV2` wraps an explicitly supplied psycopg
3.3.6 connection factory. One structural parser handles configured int64, text
and UUID identities and arbitrary supported table/column names. It retains the
original SQL and typed arguments, independently reconstructible projection,
completed native buffer, actual business deliveries and transaction observations.

This is the producer layer for the next source-window contract. Its output is
diagnostic until the core independently accepts the installation, native
projection, complete writer window and model mapping. A successfully sealed log
or consistent projection descriptor does not establish those obligations.

## Use

Configure one table with a single non-NULL primary key and 1–16 non-NULL business
columns. Supported business scalars are int64, boolean and explicitly declared
PostgreSQL C / UTF-8 text. PostgreSQL 18's OLD/NEW RETURNING syntax supplies write
images in the same statement. Install the configured bigint version column and
source triggers explicitly before using projection; construction performs no
database migration or connection operation.

The [explicit V2 installer](configured-source-v2.md) produces separately retained
installation components. Its component checks do not grant writer-window or
model admission to this producer.

```python
from moontxnwitness_capture.configured_sql_v2 import (
    ColumnConfig, PrimaryKeyConfigV2, TableConfigV2, SQLCaptureConfigV2,
)
from moontxnwitness_capture.configured_point_capture_v2 import PointCaptureV2

config = SQLCaptureConfigV2(TableConfigV2(
    "bank", "accounts", PrimaryKeyConfigV2("number", "int64"),
    (ColumnConfig("balance", "int64"), ColumnConfig("enabled", "bool")),
))
capture = PointCaptureV2("new-capture-directory", config, opt_in=True)
connect = capture.psycopg_factory(original_connection_factory)
with connect() as connection:
    row = connection.execute(
        "SELECT number, balance, enabled FROM bank.accounts WHERE number=%s",
        (7,),
    ).fetchone()
capture.close()
```

The supported statements are full-row primary-key equality SELECT, one-row
explicit-column INSERT, single-row non-key UPDATE and primary-key DELETE. The
builder separately retains the original parameter objects and their typed
observations, uses bound values in generated SQL and preserves UUID identities.
SQL outside the grammar executes unchanged and records a coverage gap.

`SELECT *` and `RETURNING *` require explicit
`PointProjectionOptionsV2(..., star_contract="preinstallation-business-schema/v1",
business_star_columns=...)`. This declares the original business view; it does
not prove that view existed. Before/after catalog evidence must independently
establish that installing metadata added exactly the configured version column.
See [projection construction](configured-point-projection-v2.md) and
[independent MoonBit reconstruction](point-projection-verifier-v2.md).

## Business behavior and observations

- Native buffers are inspected without fetching business rows. `fetchone`,
  `fetchmany`, `fetchall` and iteration deliver only the original business
  projection. Description names/types, row counts and command tags remain
  available. DML with no original RETURNING remains non-fetchable.
- `nextset`, `results` and `set_result` keep the wrapper and metadata projection
  when the current result remains active. A failed replacement that leaves the
  old buffer intact preserves its projection. Scrolls remain observable gaps,
  with subsequent deliveries retaining the actual buffer position.
- Pinned psycopg resolves `fetchmany(0)` through its actual `arraysize`; both the
  requested and resolved sizes are recorded. No extra EOF fetch is performed.
- COMMIT results use the existing pinned instance-local response observer.
  Automatic writer probes execute in a private savepoint. A failed probe is
  rolled back to that savepoint before commit continues; failed recovery is
  surfaced instead of acknowledging an aborted transaction as successful.
- Unsupported modes, incomplete results, missing log frames and writer-probe
  failures leave explicit gaps. Native `pgresult`, private driver APIs, changed
  decoders, async connections and engine integration are outside this producer's
  stable business interface. Direct native buffers include diagnostic metadata.

Only raw observation relationships are recorded here. In particular an UPDATE
write image is not a SELECT, a DELETE OLD image is not a new row version, a
zero-row command is not an absence proof, and a transaction request is not a
confirmed commit. v1 source and replay contracts remain unchanged.

## Development validation

The retained PostgreSQL 18.6 driver campaign executes three distinct layouts
with int64, C-text and UUID primary keys. Its current 105 checks cover actual
CRUD returns, negative results, in-transaction self-reads, commit/rollback,
original error class/SQLSTATE, partial consumption, result helpers and a real
`SELECT 1/0` observer failure followed by confirmation of the business commit.
The harness installs only its owned test metadata; it is not a complete source
ledger/window acceptance test. Prior failures are retained separately.

Run `scripts/configured-point-capture-v2-postgres.py --help` for the Windows
owned-cluster harness. Supply PostgreSQL 18.6 binaries and a new directory under
`D:\CodexScratch`; the harness starts and stops only that newly created cluster.
Raw database state and evidence stay outside the source tree. No formal capture
cost or model-coverage result is inferred from these correctness checks.
