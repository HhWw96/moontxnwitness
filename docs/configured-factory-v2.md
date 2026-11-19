# Configured local factory lifecycle

The source-bound V2 producer accepts an **owned, newly opened synchronous psycopg
3.3.6 connection** from a local factory. Explicit source installation, the start
snapshot and the existing independent MoonBit window verification are still
required. The factory wrapper does not provide asynchronous or pool-lease
capture.

```python
connect = window.psycopg_factory(original_sync_connection_factory)
with connect() as connection:
    row = connection.execute(original_point_sql, parameters).fetchone()
# Finish and close every enrolled connection before calling window.seal().
```

## Synchronous SQLAlchemy recipe

For a fresh SQLAlchemy 2.0.55 `Engine` using psycopg, a connection listener can
enroll the native connection after the dialect initializes it. The following
recipe uses an owned `NullPool`, with each physical connection closed on return.
Complete the source installation and open the configured window before use.

```python
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

engine = sa.create_engine('postgresql+psycopg://',
    creator=original_sync_connection_factory, poolclass=NullPool,
    pool_reset_on_return=None)

@sa.event.listens_for(engine, 'connect')
def enroll(raw_connection, record):
    record.dbapi_connection = window.wrap_connection(raw_connection)
```

Use the engine for full-row point operations, explicitly finish each
transaction, dispose the engine and seal the window. The PostgreSQL workflow
runs the same ORM routine with and without this listener and compares create,
refresh, update, query, delete and the final data. Use the separately verified
[scoped async engine](configured-async-window-v2.md#scoped-asynchronous-sqlalchemy)
for async sessions. Physical pool reuse requires separate lifecycle proof.
[SQLAlchemy pool events](https://docs.sqlalchemy.org/en/20/core/events.html)

The wrapper now checks known async functions, async callable objects and async
generators before invoking the factory. A synchronous callable that returns an
awaitable, future, asynchronous connection or async context lease is rejected
before enrollment. It does not await, cancel, run an event loop or invoke async
cleanup. Unsupported async work remains the factory/caller's responsibility.

Successful synchronous calls retain their original positional/keyword arguments,
connection identity and result. When admission fails, cleanup of a newly owned
synchronous result is best effort: its failure cannot replace the original
factory/admission exception. The dedicated control connection and existing
observer wrappers are protected from this cleanup.

Each executing window factory reserves a bounded in-flight slot. There can be at
most 32 in-flight calls, separately from the existing 32-participant limit.
Sealing refuses while a call is still pending; it does not race the end snapshot
against a connection that has not yet been enrolled. Factories invoked after the
window leaves the open state are rejected before calling user code. No factory
timeout or cancellation is added.

A runtime factory/admission failure records the single fixed
`configured_factory_unobserved` coverage gap. Arguments, connection strings and
exception text are not added to that gap. The existing core treats this gap as
incomplete coverage, so it cannot become a complete source-window conclusion.
If the gap cannot be retained, the producer also refuses sealing.

## Validation

`test_configured_factory_v2.py` contains 18 fake-connection tests and five real
local-journal lifecycle tests. They cover
async admission, coroutine/future ownership, ordinary argument/result identity,
original exceptions, failed cleanup, protected controls, foreign observers,
bounded concurrent acquisition, failed gap recording and factory/seal races.
The journal tests verify that a silent journal-gap loss remains present in the
actual diagnostic export, and that an asynchronous writer IO failure prevents
sealing/publishing a success receipt even when the gap call itself does not throw.
Deterministic schedules check failures before and after the writer marks itself
closed: reference publication, checkpoint and observer close retain the original
IO cause. Repeated close preserves the same fatal error; a healthy reference
argument error remains retryable.
These tests execute no database workload or performance measurement.

```sh
PYTHONPATH=integrations/python python -B -m unittest \
  moontxnwitness_capture.test_configured_factory_v2 -v
```

The existing source and window unit tests must continue to run alongside these
checks. A real PostgreSQL capture regression is a separate integration check.

## Asynchronous capture

Use the [native async adapter](configured-async-window-v2.md) for owned
psycopg business connections. It retains synchronous control snapshots.
The items below describe the remaining requirements for a fully asynchronous
controller and connection pool support.

An asynchronous adapter needs its own explicit interface and lifecycle proof:

1. Provide an independently named `AsyncConfiguredCaptureWindowV2.open()` and
   awaited local factory, using the caller's event loop and a dedicated pinned
   async control connection. Preserve the existing original installation,
   snapshot, native-result and commit-response evidence; do not move an existing
   synchronous connection between worker threads.
2. Reserve acquisition slots under an async lock before awaiting the factory.
   Track acquiring, enrolled, closing and closed participants explicitly. Seal
   only after all acquisition and participant tasks finish. Physical pool reuse
   must not create logical sessions or reuse transaction identities.
3. Implement async point connection/cursor wrappers. Await each native execute or
   fetch exactly once, inspect the completed libpq buffer without consuming extra
   rows, preserve business result shape, and serialize operations on one
   connection with an async lock. The native observation and actual delivery
   remain separate records.
4. Treat cancellation as an observed outcome. Cancellation while COMMIT is in
   flight stays unknown unless a native acknowledgement was actually retained.
   Rollback and retry must be explicit observed operations; a reconnect gets a
   fresh connection/transaction identity. A task exception cannot silently close
   another participant's connection or erase an already delivered read.
5. Implement async snapshot and durable-tail handling before exporting a source
   window. Reuse a wire contract only if its original facts and ordering meanings
   are unchanged; otherwise introduce a separate protocol identity and verifier.
   An async function name does not authorize reuse of the synchronous proof.
6. Validate actual PostgreSQL 18.6 execution for all three key layouts: point
   CRUD and negative reads, RR write skew, ordered Serializable, actual `40001`
   rollback/retry, transaction-local reads, cancellation at execute/fetch/commit,
   failed acquisition and seal races. Compare raw results with capture disabled
   and independently replay the produced evidence.
7. Add async pool leases and SQLAlchemy only after direct-driver ownership and
   cancellation pass. Engine hooks/greenlet DBAPI adapters need their own
   borrow/reset/return mapping; they must not be treated as native async
   connections or as already proved transactions.

These are follow-up implementation steps. The current synchronous lifecycle
improvements do not claim those asynchronous capabilities.
