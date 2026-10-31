# Python capture adapters

v0.1.2 adds `moontxnwitness_capture.presence` for controlled PostgreSQL 18
two-column tables and a fixed text-key universe. It installs source metadata and
supports synchronous generated point CRUD, negative reads and tombstones. See
[setup, limits and example](../../../docs/presence-capture.md). The package is
self-contained; copying this package does not require an experiments directory.

The existing version-column adapter below retains its v0.1.1 behavior and API.

v0.1.3 adds the explicit
`moontxnwitness_capture.orm` module for fixed FastAPI Users SQLAlchemy v7.0.0
base-user point-CRUD plans and an exact-match structural cache. Basic imports
need neither optional dependency; compiling a plan requires SQLAlchemy 2.0.55.
The helper does not execute SQL. See [templates, example and cache limits](../../../docs/orm-plans.md).

The cache defaults to 128 entries and 1 MiB accounted retained-entry bytes;
configuration permits 1–256 entries and 4 KiB–2 MiB. Oversized entries are
returned without retention. Keys isolate the complete declared UUID domain,
schema/table, SQL shape and immutable compiler/profile context. Business
parameters, fetched results and transaction state are never cache entries.
This accounting is not a process RSS limit. Use a new `registry_epoch` or
observer after installation, catalog assumptions or connection configuration change.

The standalone MoonBit [ORM source diagnostic](../../../docs/orm-source-v3.md)
checks supported source fragments and retains `analysisCoverageAccepted:false`
and `history:null`. The optional `ProvenanceObserver`, `SourceSink`, installation
and complete ORM capture remain experimental. The helper/cache's 21 mainline
offline checks and 32 independent candidate checks passed; the latter includes
the same 21 checks rerun plus 11 additions. Neither run executed a database.
Separately, a fresh PostgreSQL 18 run compared the original upstream business
with caching enabled/disabled, preserving CRUD, refresh, rollback, connection
reuse and original errors. MoonBit validated 21 local source facts per mode;
complete transaction coverage remains false. See the versioned release evidence.

This optional adapter supports psycopg 3 synchronous and asynchronous connections.
It records actual driver observations; the MoonBit core validates and normalizes
the resulting `traceSchema: 1` document. The stable v0.1.1 profile is
`CaptureSession` with existing version columns and explicit point-query mappings.
It does not analyze arbitrary SQL. The pinned driver environment uses psycopg 3.3.6.

## Supported profile

- Ordinary PostgreSQL tables with a declared, single-column primary key and an
  existing text version column. Each successful write must assign a new unique
  version for that key, even when the business value does not change.
- Explicitly registered, single-key point SELECT and UPDATE statements. A read
  returns the existing version column. A write assigns its version from a known
  parameter. Use the generated templates below when possible.
- Tuple or mapping read rows, with an explicit version-result selector. Setup
  uses a separate idle autocommit connection with the default tuple row factory.
- Implicit psycopg transactions and explicit BEGIN/COMMIT/ROLLBACK statements.
  Autocommit statements outside explicit transactions are marked incomplete.
- Fetch one, many, all, synchronous/async iteration and cursor/connection contexts.
  Fetch a mapped point result before issuing the next statement on that connection.

No SQL is rewritten, no business locks or retries are injected, and business
exceptions are re-raised. Initialization takes setup-only SHARE table locks to
obtain a consistent starting state. The current profile rejects RLS, partitions,
views, user triggers, zero-row reads, inserts/deletes, savepoints, COPY, pipelines,
server cursors, transaction contexts and other unregistered SQL/methods. These
operations still go to the driver unchanged, with explicit coverage gaps.

The custom `PointRead(sql, table, ...)` and `PointWrite(sql, table, ...)`
constructors are **trusted semantic mappings** supplied by the application. The
adapter matches the exact SQL string; it cannot prove that arbitrary supplied SQL
has the declared semantics. This declaration includes the SQL and its database
constraint/function semantics; this stable adapter does not comprehensively
audit arbitrary CHECK functions, expressions or database functions for hidden
reads/writes. Incoming/outgoing foreign keys, rewrite rules and inheritance
parents/children are conservatively rejected during initialization. Review and test custom mappings. Generated template
factories encode the supported primary-key SQL shape directly, including quoted
identifiers and parameter positions.

## Synchronous example

Add `integrations/python` to the import path and install the optional psycopg 3
driver in your application's environment. Connection credentials stay in the
application's own configuration.

```python
import json
import psycopg
from moontxnwitness_capture import CaptureSession, Table, PointRead, PointWrite

table = Table("public", "registers", "id", "version")
read = PointRead.for_table(table, value_columns=("value",))
write = PointWrite.for_table(table, value_columns=("value",))
capture = CaptureSession([read, write], jsonl_path="raw-events.jsonl",
                         exclusive_writers=True)

# Begin capture before application workers or in-flight transactions exist.
# The setup connection has no custom row factory.
with psycopg.connect(connection_string, autocommit=True) as setup:
    capture.initialize(setup)

# This connection factory is the application integration point.
with capture.connect(connection_string) as connection:
    value, version = connection.execute(read.sql, (1,)).fetchone()
    connection.execute(write.sql, (value - 1, "unique-version-id", 1))

# Stop application activity before finalizing evidence. Does not close or change
# any business connection and never silently commits an outstanding transaction.
capture.close()
with open("capture-trace.json", "w", encoding="utf-8") as output:
    json.dump(capture.document(), output, ensure_ascii=False)
```

An existing application may retain its SQL by registering explicit mappings:

```python
read = PointRead("SELECT balance,version FROM accounts WHERE id=%s", table,
                 key_parameter=0, version_result=1)
write = PointWrite("UPDATE accounts SET balance=%s,version=%s WHERE id=%s", table,
                   key_parameter=2, version_parameter=1)
```

The table declaration must refer to the actual table used by those statements.
This example is a mapping declaration, not a claim that the adapter parsed it.

## Asynchronous example

```python
setup = await psycopg.AsyncConnection.connect(connection_string, autocommit=True)
try:
    await capture.ainitialize(setup)
finally:
    await setup.close()

async with await capture.aconnect(connection_string) as connection:
    cursor = await connection.execute(read.sql, (1,))
    value, version = await cursor.fetchone()
    await connection.execute(write.sql, (value - 1, "another-unique-id", 1))
capture.close()
```

Create a fresh `CaptureSession` for the async example; initialization is once per
session. `wrap(raw_connection)` and `awrap(raw_async_connection)` are also available.
Do not mix sync and async wrappers around the same underlying connection.
On Windows, psycopg requires a selector event loop; configure the application's
event-loop policy before creating connections. The adapter does not change the
application's global loop policy automatically.

## Scope, outcomes and evidence

`exclusive_writers=True` is an explicit deployment assumption: all relevant
writers belong to this controlled, captured application window. The wrapper
cannot discover arbitrary clients elsewhere in the database. It reports detected
bypass paths; if the deployment scope is unknown, keep this flag false. No
database-wide isolation certificate follows from a trace.

Initialization locks the declared tables in deterministic order, inspects the
supported table profile, reads keys and versions, and then releases locks. Start
business workers only after initialization returns. It does not infer initial
versions from first reads. It fetches at most 64 snapshot rows per adapter batch,
limits the SQL result to the remaining 10,000-key allowance plus one detection
row, and checks a shared byte/node budget before adding each key/version. An
oversized initial state fails setup with a coverage gap. Configure finite setup statement/lock timeouts through
the setup connection if required by your environment. No commit order is inferred
from version IDs, timestamps, sequence numbers or client return order.

Raw events preserve SQL, parameters, fetched results, row counts, SQLSTATE and
error class. Common binary, Decimal and date/time values have tagged encodings.
Unsupported or over-budget values create a gap. Business exception messages are
not copied because they can contain credentials or private data. Raw captures can
still contain application data and should be reviewed before publication.

Commit/rollback acknowledgement produces a known outcome. A COMMIT error normally
remains `unknown`. For SQLSTATE 40001/40P01, matching server error diagnostics and
an idle libpq transaction state establish an acknowledged server rollback, so
the recorded outcome is `aborted`; the original exception is still re-raised.
A lost reply or unknown connection state remains `unknown`; this adapter does not resolve it from missing
markers. Closing an active connection does not invent a rollback acknowledgement.
Unconsumed reads, unsupported SQL, discarded active connections, outstanding
transactions, full event budgets and persistence errors make the evidence
incomplete. The adapter does not attempt to flatten savepoints into a transaction.

Connection context exit preserves psycopg 3.3.6's commit-then-close order. If
commit raises, that exception propagates and the later close step is not run;
the caller retains responsibility for cleanup, just as with the pinned driver.
On a body exception, rollback errors do not replace the original body exception.

JSONL files use a header, events, gaps and a footer with counts and a SHA-256
digest. `load_jsonl(path)` recovers valid prefixes and marks absent/corrupt footers
as gaps. Its defaults separately bound raw logs to 32 MiB, individual lines to
1 MiB and events/gaps to 65,536 each. It uses bounded line reads before JSON
decoding; size/record exhaustion yields `log_budget_exhausted` with the valid
prefix preserved. This is an integrity check, not authentication of the event producer.
The root document contains only `traceSchema`, `clockDomain`, `scope`, `events`
and `gaps`; snapshot/begin/op/end are interpreted by MoonBit and SQL metadata is
retained as raw evidence. A gap must prevent a complete no-violation conclusion.
Defaults allow 65,536 events; core history/transaction/operation and input-size
budgets still apply independently (currently 8 Mi UTF-16 code units per trace
document, with a smaller normalized history budget). Raw framing is deliberately
allowed more bytes and does not enlarge the core budget. Do not truncate
histories to fit those budgets.

## Observer resource budgets

`CaptureSession` accepts the following independently enforced budgets. Byte
accounting uses compact JSON encoded as UTF-8, including string escaping.

| Setting | Default | Scope |
| --- | --- | --- |
| `max_value_nodes` | 16,384 | One complete parameters or returned-rows tree, across all nested containers |
| `max_value_bytes` | 256 KiB | The same tree, including typed encodings and base64 expansion |
| `max_event_bytes` | 512 KiB | One retained event; it also has a 65,536-node bound |
| `max_events` | 65,536 | Retained events in one session |
| `max_session_bytes` | 8 MiB | Retained event/gap compact JSON accounting, with envelope/terminal-gap reserve |
| `max_session_nodes` | 262,144 | Retained event/gap nodes, with terminal-gap reserve |
| `max_gaps` | 64 | Distinct ordinary gaps, plus at most one terminal exhaustion marker |

Value traversal is incremental: nesting is limited to 8, each list/dictionary to
10,000 entries and each raw string or binary buffer to 65,536 characters/bytes.
Binary views are checked with `memoryview.nbytes` before base64 allocation;
non-contiguous views produce an unsupported-value gap without a capture copy.
Typed large integers preserve their exact decimal digits. SQL text has a
65,536-character capture limit, and gap codes/messages are bounded to 128/512
characters. Snapshot retention is additionally capped at 10,000 keys and shares
the available event/session budget. These bounds are checked before building a
complete encoded copy of a large subtree.

An over-budget value produces a gap and omits its raw representation. Exhausting
event/session storage stops further event retention with an explicit gap.
Underlying business SQL still executes with its original parameters, and
original returned objects and business exceptions are preserved. These are
observer-evidence bounds, **not a process RSS limit**: original application
objects, driver/libpq result buffers, configured mappings and simultaneous
in-flight callers are outside them. In particular, snapshot batching does not
bound a single database field or the driver's result buffer. `document()` makes
a copy of bounded retained evidence; JSON serialization may transiently hold
another copy. Pretty-printed exports and raw JSONL framing have separate sizes
and must still satisfy the MoonBit core's independent input limits.

The test command is `python scripts/capture-unit-test.py`. These are driver
interface unit tests, with `actualDatabaseExecution: false`; real PostgreSQL
execution is a separate acceptance step.

## Experimental profiles

Extended ordinary-table provenance and v3 journal/lifecycle/model APIs use
separate experimental entry points. The optional ORM observer still requires
a compatible controlled installation; it does not establish complete ORM
analysis. These capabilities do not widen the stable `CaptureSession`, presence
or fixed-template profiles above. See the
[extended provenance profile](../../../experiments/provenance/PRESENCE_PROFILE.md)
and [v3 journal](../../../docs/capture-journal-v3.md) for their current scopes.

## API sources

- [psycopg connection API](https://www.psycopg.org/psycopg3/docs/api/connections.html)
- [psycopg cursor API](https://www.psycopg.org/psycopg3/docs/api/cursors.html)
- [psycopg async usage](https://www.psycopg.org/psycopg3/docs/advanced/async.html)
- [PostgreSQL explicit table locks](https://www.postgresql.org/docs/18/explicit-locking.html)


## Optional configured SQL recognition

The independent `configured_sql` module recognizes configured PostgreSQL single-table SQL into immutable candidate descriptions. It preserves the original SQL, never executes or rewrites it, and produces no transaction facts. The optional parser is hash-pinned SQLGlot 30.26.0 (MIT); existing fixed source profiles retain their original contracts. See [configuration, supported structures and required source verification](../../../docs/configured-sql-candidate.md).
