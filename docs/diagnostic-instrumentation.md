# Scoped automatic diagnostic instrumentation

Use this entry to record an existing PostgreSQL/psycopg application without
handwriting a transaction history. It changes no SQL, database schema or global
driver. This first entry records diagnostic observations; it does not infer
versions, predicates, a complete model history or an isolation verdict.

## Existing SQLAlchemy engine

Install the optional pinned SQLAlchemy 2.0.55 and psycopg 3.3.6 dependencies.
Add `integrations/python` to the Python module path, then attach before the first
business checkout:

```python
from moontxnwitness_capture.instrumentation import instrument_engine

capture = instrument_engine(engine, "new-diagnostic-directory")
# Run the original application using this engine, including its normal pool.
# Stop its workers before closing this diagnostic window.
capture.close()
capture.export_diagnostic("new-diagnostic-directory/trace.json")
```

Both synchronous and asynchronous PostgreSQL psycopg engines are supported by
this entry. The async engine's original adapter may prefetch driver rows during
execute. Instrumentation adds no fetch and records result delivery at the outer
DBAPI adapter boundary, not when that internal prefetch happens. This is DBAPI
consumer delivery, not proof that an ORM object or HTTP response was consumed.

Pool connect/checkout/checkin/reset/soft-invalidation/invalidation/close are
recorded separately. They do not manufacture transaction begin/commit events.
Pre-existing pooled connections that bypassed the connect listener remain
unobserved with a visible gap. Stop workers and dispose/recreate an already used
pool before starting a new capture. A detach with borrowed connections records
a gap; capture never closes a business connection or stops a worker.

## Local psycopg factory

```python
import psycopg
from moontxnwitness_capture.instrumentation import instrument_psycopg

capture, connect = instrument_psycopg(psycopg.connect, "new-driver-diagnostics")
with connect(application_dsn) as connection:
    connection.execute("SELECT 1").fetchone()
capture.close()
capture.export_diagnostic("new-driver-diagnostics/trace.json")
```

For asyncio pass `psycopg.AsyncConnection.connect` and `asynchronous=True`, await
the returned local factory and use normal async driver calls. No process-global
`psycopg.connect` or SQLAlchemy registry is patched. Connection arguments and
credentials are passed through without being added to diagnostic metadata.

## Preserved observations and limits

- Original SQL, actual fetch batches, original exception class/SQLSTATE, savepoint
  instances, retry/reconnect identities and native COMMIT responses use the
  existing bounded v3 segmented journal.
- `executemany` records one original batch statement. A bounded sidecar records
  each parameter only when the original driver consumes it; no generator is
  prefetched, retried or drained by capture. Returned sets remain separate
  diagnostic observations. Actual consumed parameters are not a claim that all
  corresponding writes succeeded.
- Only an actual native `COMMIT` response confirms success. Request, normal
  return, idle status, pool checkin/reset and later idle rollback do not substitute
  for that response. Lost responses remain unknown. Unsupported driver response
  hooks retain a gap. An actual `ROLLBACK` response is preserved distinctly.
- The v3 journal uses its existing bounded queue/group synchronization. Separate
  `lifecycle.jsonl` is limited to 8 MiB/65,536 records and synchronized on close.
  It has a seal and SHA-256 bound by `instrumentation.json`. Accepted lifecycle
  metadata before close is not claimed durable; IO/budget failures remain gaps.
- Unknown SQL and unsupported APIs still run with original driver behavior and
  retain gaps. Named/server/custom cursors, pipeline, COPY/stream, two-phase and
  direct driver transaction-context APIs do not gain complete observation.
- Detach removes only this engine's listeners. Existing wrapped connections remain
  usable outside the ended diagnostic window. Export is always partial; no read,
  write, condition, initial-state or exclusivity facts are invented.

The portable CLI can inspect exported raw traces using `failures-v3`. Keep the
whole diagnostic directory when batch parameters and pool lifecycle are needed;
those sidecar records are not silently promoted into the v3 model vocabulary.

## Verification and example

`python -B integrations/python/moontxnwitness_capture/test_instrumentation.py`
runs fake-driver tests, including the actual SQLAlchemy async adapter without a
database. They establish protocol behavior, not database or production evidence.

`examples/instrumentation_psycopg.py --output NEW_DIRECTORY --mode sync` is a
SELECT-only optional live example. Modes `async`, `engine` and `async-engine`
exercise the other entry paths. It requires `MTW_PG_DSN`, performs no migration,
and reports missing configuration/dependencies as not executed. Actual live
integration and capture cost must have separate recorded results before a
release claims them.


The v0.2.2 integration run separately executed PostgreSQL 18.6 for native
sync/async factories, synchronous/asynchronous SQLAlchemy engines and both
lost-COMMIT-response paths. All six cases passed; a protocol proxy discarded
the native COMMIT response after the database stored the value, and capture
kept the client outcome unknown. Original SQL, fetched results, lifecycle,
journals and exact implementation bindings are retained in
[the integration evidence](../verification/capture-instrumentation/v022-integrated-first/adoption.json).
These are bounded integration fixtures, not a full application, source-promotion
or collection-throughput result.
On Windows the executable async example and regression harness use a local
`asyncio.SelectorEventLoop` runner, as required by psycopg. They do not replace
the application's global event-loop policy; an existing application supplies
its own compatible event loop.

## Bound client call intervals

The lifecycle sidecar now records actual `execute`, `executemany`, `commit` and
`rollback` method start/end pairs. Each pair has a unique `callId`, process-wide
`processMonotonicDomain`, connection and transaction identity, decimal-string
`monotonicNs`, the actual statement sequence and observed v3 event references.
A COMMIT response is a separate original observation inside the call; only its
actual `COMMIT` command tag can confirm an interval end. BEGIN observation time
is not a database snapshot or a substitute for the first real SQL call.

After close and diagnostic export, preserve a bound copy of the lifecycle
observations for the independent classifier:

```python
capture.export_call_intervals(
    "new-diagnostic-directory/trace.json",
    "new-diagnostic-directory/interval-evidence.json",
)
```

This requires this observer's exact freshly exported trace and a valid sealed
journal/sidecar. The interval evidence contains all original sidecar records,
including header and seal, and SHA-256 of the original trace, lifecycle JSONL
and journal-index bytes. It derives no order or model facts. A verifier also
needs those original three texts. Journal index binding alone does not claim
that an unprovided event segment was independently revalidated. Missing calls,
missing/unknown COMMIT acknowledgements, a different monotonic domain or budget
gaps prevent a complete client interval. Concurrent sidecar line order need
not match timestamp order; equal timestamps do not imply real-time precedence.

## Actual PostgreSQL regression harness

`scripts/instrumentation-postgres-test.py --output NEW_DIRECTORY --commit-loss`
uses the private `MTW_PG_CONNECTION_FILE` with an owned PostgreSQL 18 instance.
It requires the pinned optional drivers already installed, creates a new
retained fixture schema and performs no application-table migration or download.
It checks native and engine sync/async paths, actual result delivery, consumed
batch parameters, same-name savepoints, pool reuse/invalidation/reconnect and
server-confirmed commit/rollback behavior.

`--commit-loss` adds a loopback-only fault proxy that forwards actual PostgreSQL
traffic and discards the actual server `COMMIT` completion. An independent
connection must observe the committed write while the collector retains the
lost client outcome as unknown. It records a completion-frame digest, not
credentials or raw authentication traffic. These are database integration
checks, separate from production adoption and formal performance measurements.
Keep the first failed output directory; do not replace it with a passing run.

To create and stop a separate bounded fixture cluster using an already installed
complete PostgreSQL tree, run `scripts/instrumentation-owned-postgres.py --bin
EXISTING_PG18_BIN --output NEW_DIRECTORY`. It retains its own cluster, private
connection file, server log, first outcomes and executable hashes, limits
`shared_buffers` to 32 MiB and uses an isolated dynamic loopback port. The private
connection/password files must not be published with verification receipts.

For optional grouped source storage and a full A/B/C cost protocol, see
[grouped-source-persistence.md](grouped-source-persistence.md).
