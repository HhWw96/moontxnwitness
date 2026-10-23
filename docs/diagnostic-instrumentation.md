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
