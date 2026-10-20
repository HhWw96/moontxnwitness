# dislock

[![CI](https://github.com/Actticus/dislock/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Actticus/dislock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dislock.svg)](https://pypi.org/project/dislock/)
[![Python](https://img.shields.io/pypi/pyversions/dislock.svg)](https://pypi.org/project/dislock/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-2a6db2.svg)](https://mypy-lang.org/)

**PostgreSQL-backed distributed locks for cron jobs and one-off commands.**

`dislock` prevents the same job from running twice across machines using a single Postgres table. It ships as both a Python library (sync and async) and a CLI wrapper for any shell command.

## Lock modes

Two complementary modes, usable alone or together:

| Mode | Behavior | Use when |
|------|----------|----------|
| **schedule** | One lock per schedule slot. Acquired at start, held until the next cron boundary. Long runs may overlap across slots, but duplicate starts within the same slot are rejected. | You want at most one start per scheduled tick. |
| **lease** | One renewable lock held for the entire runtime of the job (heartbeat-renewed TTL). Released when the command exits. | You want to keep concurrent runs out for the whole duration of the job. |

Combining `schedule,lease` gives both guarantees: `schedule` is acquired first (outermost) and released last.

### Mutual exclusion is best-effort, not a hard guarantee

The lease is a TTL row in Postgres, not a fence around the wrapped command. Between the moment this process stops renewing and the moment its lock row expires, another process can legitimately acquire the lease. `dislock` cannot make the already-running command stop instantaneously, so a brief overlap is possible in these cases:

- The renewer loses the `value` guard (another owner took the row), misses its local monotonic deadline, or its connection fails.
- The whole process is `SIGKILL`ed or the machine dies — the row then expires on its own after `RUN_LOCK_TTL_SECONDS`.
- The command ignores `SIGTERM` and keeps running through the kill grace period.

By default (`LeaseLossPolicy.TERMINATE`) `dislock` narrows the window and never reports a clean success on a lock it no longer held:

- **Wrapped subprocess** (`run_with_locks`, CLI) — the command is sent `SIGTERM`, then `SIGKILL` after 10 s, and `dislock` exits with code `75`.
- **Guarded Python block** (`LeaseLock`, `acquire_locks`) — the block is *not* interrupted; arbitrary Python code cannot be preempted from outside. On exit `LeaseLostError` is raised, so a block that finished on a lost lease fails loudly instead of looking successful. An exception already propagating from the block is never masked.

Set `LOCK_ON_LEASE_LOSS=continue` (library: `lease_loss_policy=LeaseLossPolicy.CONTINUE`) to only log the loss: the command runs to completion and no `LeaseLostError` is raised.

If your workload requires strict correctness under overlap, make the work itself idempotent or transactionally guarded — do not rely on the lock alone.

### Startup jitter

Before any lock is acquired, `dislock` can sleep for a random delay in `[0, jitter_max_seconds]`. This spreads the thundering herd of identical cron jobs firing on the same boundary across many machines. Disabled by default (`0.0`); set `LOCK_JITTER_SECONDS` (CLI) or `LockContext.jitter_max_seconds` (library). It applies to both the sync and async `acquire_locks`.

## Installation

```bash
pip install dislock
```

From the repository:

```bash
uv sync
```

Requires Python ≥ 3.10. Runtime dependencies: `psycopg[binary]>=3.1`, `croniter>=2.0.5`.

## Required PostgreSQL schema

```sql
CREATE TABLE key_value (
    key text PRIMARY KEY,
    value text NOT NULL,
    expire_at timestamptz NOT NULL
);
```

Lock rows use prefixed keys: `cronjob-lock:schedule:<lock_key>` and `cronjob-lock:lease:<lock_key>`. The `value` column holds `hostname:pid` (the owner), used as the optimistic-concurrency guard for renewals and expiry.

Point `dislock` at a different table via `LOCK_TABLE` (library: `table_parts`). Both `table` and `schema.table` are supported.

---

## 1. CLI usage

Wrap any command. The first argument is the **name of the env var** that holds the database URL; the rest is the command to run.

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/app"
export LOCK_KEY="daily-report"
export CRON_SCHEDULE="0 3 * * *"

dislock DATABASE_URL python3 worker.py
```

### Schedule only (default)

```bash
LOCK_KEY=daily-report CRON_SCHEDULE="0 3 * * *" \
  dislock DATABASE_URL python3 worker.py
```

### Lease only

```bash
LOCK_KEY=importer LOCK_STRATEGY=lease RUN_LOCK_TTL_SECONDS=120 \
  dislock DATABASE_URL python3 importer.py
```

### Schedule + lease combined

```bash
LOCK_KEY=etl LOCK_STRATEGY=schedule,lease \
  CRON_SCHEDULE="*/15 * * * *" RUN_LOCK_TTL_SECONDS=60 \
  dislock DATABASE_URL python3 etl.py
```

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| *(first CLI arg)* | yes | — | Name of the env var holding the DB URL |
| `LOCK_KEY` | yes | — | Logical lock namespace |
| `CRON_SCHEDULE` | for `schedule` | — | Cron expression used to compute the next slot boundary |
| `LOCK_STRATEGY` | no | `schedule` | `schedule`, `lease`, or `schedule,lease` |
| `LOCK_TABLE` | no | `key_value` | Lock table; `table` or `schema.table` |
| `RUN_LOCK_TTL_SECONDS` | for `lease` | `60` | Lease TTL in seconds |
| `LOCK_LEASE_INTERVAL` | no | derived¹ | Heartbeat interval in seconds (must be ≤ TTL) |
| `LOCK_JITTER_SECONDS` | no | `0.0` | Max startup delay; actual delay is uniform in `[0, value]` |
| `LOCK_ON_LEASE_LOSS` | no | `terminate` | `terminate` (SIGTERM → SIGKILL the command, exit `75`) or `continue` (log only) |
| `CRONJOB_LOCK_LOG_LEVEL` | no | `WARNING` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; an unrecognized value falls back to `WARNING` with a warning |

¹ Derived as `clamp(TTL × 0.3, 1.0s, 10.0s)`.

`RUN_LOCK_TTL_SECONDS` and `LOCK_LEASE_INTERVAL` are read only when `lease` is among the strategies; `CRON_SCHEDULE` only when `schedule` is. A negative or non-numeric `LOCK_JITTER_SECONDS`, or an interval greater than the TTL, is a `ConfigurationError` (exit code `2`).

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Command succeeded, **or** the lock was already held by another process (expected) |
| `1` | Unexpected runtime failure |
| `2` | Invalid configuration or CLI usage |
| `75` | Lease was lost and the command was terminated (`LOCK_ON_LEASE_LOSS=terminate`) |

The wrapped command's own non-zero exit code is propagated as-is.

---

## 2. Python API — high level

`run_with_locks` builds the locks, enters them, runs the command, and returns its exit code.

```python
from datetime import datetime, timedelta, UTC

from dislock import LockContext, run_with_locks

context = LockContext(
    url="postgresql://user:pass@localhost:5432/app",
    table_parts=["key_value"],
    lock_key="daily-report",
    owner="host:12345",
    next_run_time=datetime.now(UTC) + timedelta(hours=1),
)

exit_code = run_with_locks(
    ["python3", "worker.py"],
    context=context,
    strategies=("schedule",),
)
```

`strategies` is normalized to `("schedule", "lease")` order regardless of input.

---

## 3. Python API — direct context managers (sync)

Use the locks directly to guard arbitrary Python code instead of a subprocess.

### ScheduleLock

```python
from datetime import datetime, timedelta, UTC

from dislock import LockContext, ScheduleLock
from dislock import LockNotAcquiredError

context = LockContext(
    url="postgresql://user:pass@localhost:5432/app",
    table_parts=["key_value"],
    lock_key="daily-report",
    owner="host:12345",
    next_run_time=datetime.now(UTC) + timedelta(hours=1),
)

try:
    with ScheduleLock(context):
        run_my_job()
except LockNotAcquiredError:
    pass  # another process already owns this schedule slot
```

### LeaseLock

`run_ttl_seconds` and `lease_interval_seconds` are required; a daemon thread renews the lease until the block exits.

```python
from dislock import LockContext, LeaseLock

context = LockContext(
    url="postgresql://user:pass@localhost:5432/app",
    table_parts=["key_value"],
    lock_key="importer",
    owner="host:12345",
    run_ttl_seconds=120.0,
    lease_interval_seconds=30.0,
)

with LeaseLock(context):
    run_long_job()
```

### Combining via acquire_locks

`acquire_locks` is a single context manager that enters every requested lock in the correct order (`schedule` outermost) and releases them on exit — no `ExitStack` boilerplate.

```python
from dislock import LockContext, acquire_locks

with acquire_locks(context, strategies=("schedule", "lease")) as session:
    run_my_job()
```

`run_with_locks` is just `acquire_locks` wrapped around a subprocess.

When you guard Python code rather than a subprocess, nothing can interrupt your own loop for you — check `session.lease_lost` at safe points and bail out yourself:

```python
with acquire_locks(context, strategies=("lease",)) as session:
    for item in items:
        if session.lease_lost is not None and session.lease_lost.is_set():
            break  # another process may already own the lease
        process(item)
```

The same field exists on the `LockSession` yielded by `dislock.aio.acquire_locks`, as an `asyncio.Event`.

---

## 4. Python API — async context managers

The async API lives in `dislock.aio` and mirrors the sync names one-to-one
(`ScheduleLock`, `LeaseLock`, `acquire_locks`, `build_locks`) — no `Async` prefix,
the module is the namespace. It uses `psycopg.AsyncConnection`; the lease is
renewed by an asyncio task.

```python
import asyncio

from dislock import LockContext
from dislock.aio import LeaseLock


async def main() -> None:
    context = LockContext(
        url="postgresql://user:pass@localhost:5432/app",
        table_parts=["key_value"],
        lock_key="importer",
        owner="host:12345",
        run_ttl_seconds=120.0,
        lease_interval_seconds=30.0,
    )

    async with LeaseLock(context):
        await run_long_job()


asyncio.run(main())
```

`dislock.aio.ScheduleLock` requires `next_run_time` and raises `LockNotAcquiredError` on conflict, same as the sync variant.

To combine modes, use `dislock.aio.acquire_locks`:

```python
from dislock import LockContext
from dislock import aio

async with aio.acquire_locks(context, strategies=("schedule", "lease")):
    await run_my_job()
```

---

## `LockContext` fields

| Field | Type | Required for | Description |
|-------|------|--------------|-------------|
| `url` | `str` | all | Postgres DSN (redacted in `repr`) |
| `table_parts` | `list[str]` | all | Table name parts, e.g. `["public", "key_value"]` |
| `lock_key` | `str` | all | Logical lock namespace |
| `owner` | `str` | all | Owner token, e.g. `hostname:pid` |
| `next_run_time` | `datetime \| None` | schedule | Slot expiry (next cron boundary) |
| `run_ttl_seconds` | `float \| None` | lease | Lease TTL |
| `lease_interval_seconds` | `float \| None` | lease | Heartbeat cadence (≤ TTL) |
| `schedule` | `str \| None` | — | Cron expression (informational) |
| `jitter_max_seconds` | `float` | — | Max startup delay before acquisition; defaults to `0.0` (no delay) |
| `lease_loss_policy` | `LeaseLossPolicy` | — | `TERMINATE` (default) or `CONTINUE`; only affects `run_with_locks` |

The dataclass is `frozen=True, kw_only=True`. Constructing `LeaseLock` (sync or async) without `run_ttl_seconds` and `lease_interval_seconds` raises `ValueError` at construction time, before any connection is opened.

## Exceptions

All exported from `dislock`:

- `DislockError` — base class
- `ConfigurationError` — invalid lock configuration
- `LockNotAcquiredError` — lock already owned by another process
- `LeaseLostError` — the lease stopped being held while the guarded block was running; raised by `LeaseLock.__exit__` / `__aexit__` under `LeaseLossPolicy.TERMINATE` when the block itself completed without error

## Public API

**`dislock`** (sync): `ScheduleLock`, `LeaseLock`, `LockContext`, `LockSession`, `LeaseLossPolicy`, `LEASE_LOST_EXIT_CODE`, `acquire_locks`, `build_locks`, `run_with_locks`, `ConfigurationError`, `DislockError`, `LeaseLostError`, `LockNotAcquiredError`.

**`dislock.aio`** (async): `ScheduleLock`, `LeaseLock`, `LockSession`, `acquire_locks`, `build_locks` — same names, same signatures, async context managers.

## How it works

- Acquisition is a single atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE expire_at <= NOW()` — no SELECT before INSERT.
- Lease renewal runs `UPDATE ... WHERE key = %s AND value = %s` at `lease_interval_seconds` cadence; ownership is verified by the `value` guard.
- The renewer uses a monotonic local deadline, independent of wall-clock or DB-time drift. If a renewal lands after that deadline, loses the `value` guard, or raises, the renewer marks itself not-OK and stops.
- On exit, the lease is expired via a **second** connection so cleanup never mixes with the main connection's commit state. Expiry is skipped when the renewer is not OK — the row may already belong to another process, so the `value` guard must not be overridden.
- The renewer is given 3 s to stop on exit (thread `join` in sync, `wait_for` then `cancel` in async).
- When the renewer marks itself not-OK it sets a `lease_lost` event. `acquire_locks` yields a `LockSession` carrying that event (`None` when there is no lease lock, or when the policy is `CONTINUE`), and `run_with_locks` polls it every 0.5 s alongside the subprocess.
- Schedule slot expiry uses the **database** clock: `next_run_time` is computed by `croniter` from `SELECT NOW()`, not from local time.

## Development

```bash
# Install the package and the dev dependency group
uv sync

# Unit tests
pytest -v tests/unit

# A single test
pytest tests/unit/test_core.py::test_normalize_lock_strategies_puts_schedule_before_lease

# Integration tests against a real PostgreSQL (Docker)
docker compose -f docker-compose.tests.yml up --abort-on-container-exit --exit-code-from tests

# Integration tests only (requires TEST_DATABASE_URL)
pytest -m integration tests/integration
```

## License

MIT
