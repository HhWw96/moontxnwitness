# PostgreSQL point windows with async psycopg

`ConfiguredAsyncCaptureWindowV2` captures business statements on owned native
psycopg 3.3.6 async connections. The dedicated idle autocommit controller takes
the two source snapshots synchronously on its owner thread. Open the window
before running the business event loop and seal it after the participants close.
Use the [V2 source installer](configured-source-v2.md) and the same independent
configuration and source policy as for a synchronous window.

```python
import asyncio
import sys

import psycopg
from moontxnwitness_capture.configured_async_window_v2 import ConfiguredAsyncCaptureWindowV2

# control, config, policy and installation come from the explicit V2 install.
window = ConfiguredAsyncCaptureWindowV2(
    "async-window", config, control, policy, installation, opt_in=True,
)
connect = window.psycopg_factory(psycopg.AsyncConnection.connect)

async def run():
    async with await connect(writer_dsn) as connection:
        cursor = await connection.execute(
            "SELECT identity,balance,enabled FROM app.rows WHERE identity=%s", (7,),
        )
        return await cursor.fetchone()

with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
    result = runner.run(run())
bundle = window.seal()
```

Use `analyzeConfiguredWindowV4` and `verifyConfiguredWindowV4` on the sealed
bundle with independently provided config, policy and budgets. The lifecycle
uses `moontxnwitness-async-point-producer/v2` and records async enrollment.
MoonBit checks the producer and connection modes, native buffers, delivered
values, writer checkpoints and original commit responses before using any row
fact. Async connections use the same configured SQL, scalar types and limits as
the synchronous adapter.

The adapter supports one business loop, default tuple cursors and owned
connections. The control connection stays on its caller's thread. Reused pool
leases, streaming cursors, binary/custom decoders and pipeline mode require
additional evidence. Explicit rollbacks, failed or cancelled statements and
unconfirmed COMMITs remain visible and make a window inconclusive. Retrying on
the same connection creates a new transaction identity.

## Scoped asynchronous SQLAlchemy

Use `window.sqlalchemy_engine(factory)` to create an owned SQLAlchemy 2.0.55
async engine. The factory opens a fresh idle psycopg 3.3.6 connection on each
call. Each `NullPool` checkout uses a distinct physical connection, which
closes on return. Pass the scoped engine to your existing session factory.

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

async def run_orm():
    async def connect():
        return await psycopg.AsyncConnection.connect(writer_dsn)

    async with window.sqlalchemy_engine(connect) as engine:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = await session.get(User, user_id)
            # Finish the transaction explicitly in a committed-window analysis.
            await session.commit()
            return user
```

Finish sessions before leaving the engine scope and seal the window afterward.
The PostgreSQL adapter's internal libpq prefetch supplies a native buffer.
The scoped cursor records delivery when SQLAlchemy fetches from that buffer,
and strips source metadata before returning the business result. Closing a
pending result leaves a coverage gap. [SQLAlchemy asyncio events](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-events-with-the-asyncio-extension)

The real database fixture compares ORM CRUD and refresh with capture enabled
and disabled. An optional `--fastapi-users-checkout` argument also runs the
unchanged FastAPI Users v7.0.0 base-user adapter from a verified source checkout.
It exercises by-ID lookup, create, update, delete and the adapter's own refresh
calls. The fixture commits its final read-only transaction and independently
replays the report. Email search and OAuth joins remain outside the point SQL
grammar. The fixture requires `--with-window --with-analysis --with-async
--with-sqlalchemy`, the [business dependency list](../experiments/business/fastapi_users/requirements-lock.txt),
and the pinned upstream commit `6397ace506d829a2ee12786da5d724c3f4c6b634`.

Pass `--fastapi-users-seed-campaign` with that checkout to record 30 fixed
workloads. The fixture writes the seed plan before running the original CRUD
and refresh methods on the uncaptured table, then repeats them through the
capture engine. A paired duplicate-email attempt must retain PostgreSQL
SQLSTATE `23505` and the same final rows, while the aborted capture window stays
`unknown`. The window verifier checks the plan digest and every case bundle.

From a source checkout with the optional dependencies and a built runtime, run
the database and replay steps together with the pinned upstream checkout:

```sh
node scripts/configured-business-window-demo.mjs --bin PG_BIN --upstream PINNED_CHECKOUT --runtime dist --output NEW_RUN
```

Use `--dsn-env` in place of `--bin` for a separately owned PostgreSQL 18.6
test service. To replay previously collected evidence without PostgreSQL, use
`--receipt NEW_RUN/database/receipt.json --runtime dist --output NEW_REPLAY`.

The PostgreSQL workflow runs the original SQL for all three key types with
`scripts/configured-source-v2-postgres.py --with-window --with-analysis --with-async`.
The fixtures cover CRUD with negative and transaction-local reads, Repeatable
Read write skew, an actual Serializable `40001` followed by rollback and retry,
a cancelled factory and cancellation while PostgreSQL is waiting on a row lock.
The source-window verifier also rejects a lifecycle with a mismatched connection
mode after its outer digest has been recomputed.

### Reusing the physical connections

Set `sqlalchemy_pool_size` to an integer from 1 to 8 when constructing
`ConfiguredAsyncCaptureWindowV2` to opt into reuse with its owned async engine.
The engine uses a bounded `AsyncAdaptedQueuePool` without overflow. The default
continues to open and close a fresh connection per lease via `NullPool`.

The producer and MoonBit verifier check checkout and return against physical
backend identity, an increasing lease number and idle transaction state.
Every observed transaction must start and finish within one lease. A returned
connection can be borrowed again with a fresh transaction identity. Complete
the transaction before returning the session or connection. Invalidations and
unconfirmed or rolled back transactions leave the source decision unknown.

The PostgreSQL fixture uses a one-connection pool for multiple committed
transactions and compares ORM CRUD and refresh with the uncaptured routine.
The verifier rejects rehashed changes to the lease generation or PostgreSQL
backend identity. This scope covers the window-owned SQLAlchemy engine on a
single event loop.
