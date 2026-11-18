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
connections. The control connection stays on its caller's thread. Pool leases,
SQLAlchemy DBAPI adapters, binary/custom decoders and pipeline mode require
additional evidence. Explicit rollbacks, failed or cancelled statements and
unconfirmed COMMITs remain visible and make a window inconclusive. Retrying on
the same connection creates a new transaction identity.

The PostgreSQL workflow runs the original SQL for all three key types with
`scripts/configured-source-v2-postgres.py --with-window --with-analysis --with-async`.
The fixtures cover CRUD with negative and transaction-local reads, Repeatable
Read write skew, an actual Serializable `40001` followed by rollback and retry,
a cancelled factory and cancellation while PostgreSQL is waiting on a row lock.
The source-window verifier also rejects a lifecycle with a mismatched connection
mode after its outer digest has been recomputed.
