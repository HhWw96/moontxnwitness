# Existing-row server-token capture experiment

This v0.1.2 experimental slice is separate from the stable adapter. It connects
an explicitly generated SQL profile to the existing MoonBit
ingest/analyze/shrink/replay path. It is not automatic instrumentation of
arbitrary SQL. The output remains a unique-version point-register projection,
not a complete PostgreSQL isolation classification or an SQL semantic proof.

`ColumnPointProfile` generates exactly two business SQL templates: a one-column
primary-key SELECT and a one-column primary-key UPDATE. `ColumnCapture` matches
those exact strings. The observed SELECT appends the actual UUID column in the
same statement; the UPDATE adds `RETURNING uuid_column::text`, obtaining the
actual token assigned by the installed BEFORE trigger. Every successful update
emits its own token, including repeated values and intermediate writes. No
write token is reconstructed by querying audit/current rows afterward.

## Supported input and deployment assumptions

- PostgreSQL 18 and synchronous psycopg 3, standard `tuple_row`, unnamed cursors, one business
  value column, one immutable text primary key, existing rows only. The caller
  declares the entire fixed key set, which must exactly match the locked table;
  at most 10,000 keys are accepted. Wrapping/opening business connections before
  successful initialization is refused without sending rewritten SQL.
- An ordinary table with native scalar columns. RLS, other user triggers,
  inheritance parents/children, incoming/outgoing foreign keys, rewrite rules, CHECK/EXCLUDE constraints,
  generated columns, expression/partial indexes, domains and custom/non-scalar
  column types are refused during the locked initialization. These conservative
  restrictions avoid hidden SQL-bearing paths; this version does not parse
  constraint/function expressions to prove a wider safe subset.
- Negative reads, inserts/deletes, application RETURNING, ranges, custom SQL,
  savepoints, custom row factories, server cursors and low-level raw access are
  outside the profile. Unregistered SQL is executed unchanged with a coverage
  gap. A gap prevents complete-history export.
- Only an explicitly specified `mtw_provenance_*` schema is accepted. The
  installer adds a UUID column, two triggers/functions, an ownership marker,
  audit and absence-state tables. This changes the installation environment;
  ALTER TABLE also requires a stronger lock. It is not a zero-change migration.
- An independent idle autocommit setup connection performs BEGIN, SHARE lock,
  original table checks, generated DDL, nonce/OID and owned-object checks, and
  the **actual initial token snapshot in one transaction**. Only acknowledged
  setup COMMIT publishes the snapshot and enables capture. Workers must start
  after initialize returns. Setup failure rolls back newly created objects and
  the version column. Initial versions never come from first reads.
- Owned-object checks verify table identity, UUID column, exactly two user
  triggers, trigger function source/language/security/search path, metadata
  column types/nullability, exact PostgreSQL 18 `contype='n'` NOT NULL column
  sets (including primary-key columns), validated/enforced key constraints and absence of
  unexpected metadata triggers. They are initialization checks, not continuous
  defense against an administrator. During capture the deployment must prevent
  unobserved writers, DDL, trigger disabling, replication-role changes and direct
  metadata edits. `exclusive_writers=True` is an explicit deployment assertion.
- UUIDs identify versions. Neither UUID order nor response time is a version or
  commit order; the core receives no inferred `versionOrders` facts.

## Business cursor and raw evidence

Supported read rows retain only the original business column, and description
excludes the appended token. Fetch one/many/all and iteration use that projection.
The proxy consumes only its own added UPDATE RETURNING result and restores the
original no-result surface: description/rownumber are None; rowcount and
statusmessage come from the actual UPDATE.

Fetching that write raises the same ProgrammingError class/message/sqlstate as
pinned psycopg 3.3.6's UPDATE without RETURNING. This **local** error is explicitly
reconstructed because the observed statement really has a TUPLES_OK result; it
is not recorded as a server error. Closed-cursor fetch raises InterfaceError
first. Actual business execution, constraint, rollback and COMMIT errors retain
their original exception objects. Unknown COMMIT follows the stable adapter's
gap/unknown handling.

Custom row factories are unsupported. A factory change after an active generated
SELECT creates a gap, and the unsupported shape has no projection guarantee.
Low-level result access can expose actual metadata and is a coverage gap. This
is a restricted cursor surface, not full DB-API transparency.

`execute-request.sql` records business SQL. For rewritten queries,
`execute-ack.sql`/`execute-error.sql` records actual generated SQL from the single
underlying execute call. `fetch.rows` retains actual server rows, including hidden
token metadata. Existing `traceSchema:1` snapshot/op/end and gap contracts are
unchanged. There are no new phases/schema fields.

## Usage

The optional psycopg driver is required. Add `experiments/provenance` to the
application import path, then explicitly configure the controlled profile:

```python
import psycopg
from capture_profile import ColumnCapture, ColumnPointProfile
from prototype import uninstall

profile = ColumnPointProfile("mtw_provenance_demo", "items")
capture = ColumnCapture(profile, keys=("a", "b"), exclusive_writers=True)
with psycopg.connect(private_connection_string, autocommit=True) as setup:
    capture.initialize(setup)  # Existing table, exact key set; workers stopped.
with capture.connect(private_connection_string) as connection:
    (value,) = connection.execute(profile.read_sql, ("a",)).fetchone()
    connection.execute(profile.write_sql, (value, "a"))
    connection.execute(profile.write_sql, (value, "a"))  # A second actual token.
capture.close()
trace = capture.document()  # Existing ingest/check/shrink/replay accept this.
with psycopg.connect(private_connection_string, autocommit=True) as setup:
    uninstall(setup, capture.installation)  # Stop workers before uninstall.
```

Each session currently owns a fresh installation; a new session requires explicit
uninstall/reinstall. A lost setup COMMIT acknowledgement requires inspection of
the controlled schema rather than guessing whether DDL committed. Audit storage,
retention, contended lock cost and application migration remain prototype
limitations. Capture budgets limit observer evidence, not database audit growth,
driver buffers or total process RSS.

## Verification

Database-free checks, explicitly not actual database execution:

```text
python experiments/provenance/test_capture_profile.py
```

After other measurements stop, configure `MTW_PG_CONNECTION_FILE` (private JSON)
or `MTW_PG_DSN`, and `MTW_PYTHON` for the environment with psycopg. From repo root:

```text
node experiments/provenance/capture_profile_e2e.mjs --schema mtw_provenance_profile_run1 --output artifacts/provenance-profile-run1
```

The PostgreSQL 18 schema and output directory must be new. Only this fixture's
new schema is cleaned up; `--keep-schema` retains it. Credentials and driver
messages are excluded from receipts; no external installer is run. Four traces
cover same-value intermediate writes, self-read/rollback, two-connection RR write
skew, unsupported SQL/savepoint gaps and unconsumed-result gaps. A parallel plain
table independently checks the supported cursor surface and final values.
Additional actual checks reject foreign keys/rules and other unsupported schema
features, nonce/trigger/function tampering, and inject a post-DDL verification
failure to prove rollback leaves no new installation objects or UUID column.

Python writes `profile-database.json` with `driver-passed-core-pending`. Node
normalizes all traces, requires history:null for gaps, analyzes complete
histories, creates/replays capsules and shrinks skew to two transactions with a
completed single-delete check. Only then does `profile-receipt.json` say passed.
Failures preserve `profile-failure.json`/`profile-core-failure.json` and any traces
already written. Older provenance-only/B/A measurements do not validate this
new capture path. Full C/A performance, CPU/RSS, contended locks, Linux coverage,
external application adoption and release acceptance remain separate gates.

## Actual local result (2026-10-20)

The second actual run passed on Windows PostgreSQL 18.6 with psycopg 3.3.6 and
Python 3.12.5. Its unmodified receipt is
`verification/provenance-profile/run-e89d7a34b1d74e48bd98950d44555564/profile-receipt.json`.

- All four traces passed their expected MoonBit coverage status. The complete
  repeated-value/intermediate-write/rollback trace was consistent; the complete
  RR trace exposed write skew. Unsupported SQL and unfinished results stayed
  inconclusive with no exported history.
- Both complete histories produced capsules that independently replayed. Write
  skew shrank to two transactions with `oneMinimal=true`.
- Eleven unsupported-schema or injected-installation-failure cases were
  rejected. Five also checked the stable adapter's foreign-key/rule/inheritance
  rejection. Failed installation left no added UUID column, metadata table or
  function, and retained original business rows. Separate nonce, disabled
  trigger and function-body tampering checks rejected all three changes.
- Supported rows/description/rowcount/statusmessage and no-result/closed-cursor
  fetch errors matched the plain-table comparison. Aborted versions disappeared
  from committed audit state; successful intermediate versions remained distinct.
  Uninstall retained business values. The owned test instance was then stopped.
- Current database-free interface/catalog checks are 22/22 passed. The first
  actual run's failure remains separately recorded below; it was not overwritten.

The harness now also records `captureSource` before the database run: stable
adapter, analysis/capture core and build-manifest SHA-256 values, plus the build
manifest's `sourceSha256`. Existing Python source hashes and the E2E hash remain.
These extra metadata fields apply to subsequent runs; the second run above
predates them and is not rewritten to claim otherwise. No full C/A performance,
external-application adoption or production-release claim follows from this
controlled fixture result.

Sources: pinned local psycopg 3.3.6 `_cursor_base.py` no-result fetch behavior;
[psycopg cursor API](https://www.psycopg.org/psycopg3/docs/api/cursors.html),
[PostgreSQL RETURNING](https://www.postgresql.org/docs/18/dml-returning.html),
[trigger row semantics](https://www.postgresql.org/docs/18/plpgsql-trigger.html),
[explicit locks](https://www.postgresql.org/docs/18/explicit-locking.html).

PostgreSQL 18's [pg_constraint catalog](https://www.postgresql.org/docs/18/catalog-pg-constraint.html)
stores NOT NULL constraints as separate rows. The first actual fixture run
rejected that valid directory shape; its failure receipt remains at
`verification/provenance-profile/run-29a2743ab45744df80acadddfd6ab99f/profile-failure.json`.
The fixed verifier requires exactly installation columns {1,2,3}, audit
{1,2,3,4}, and state {1,2,3}, with no missing/duplicate/extra NOT NULL constraints;
it retains the original primary/foreign-key checks and refuses PostgreSQL 17's
different catalog contract. This failure is not a passing database result.
