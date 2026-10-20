from __future__ import annotations

import asyncio
import logging
import random
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from time import monotonic
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Iterable,
    ParamSpec,
    Sequence,
    TypeVar,
)

if TYPE_CHECKING:
    pass

from ._queries import (
    acquire_lock_query,
    acquire_run_lock_query,
    expire_lock_query,
    psycopg,
    read_current_query,
    renew_lease_query,
    require_psycopg,
)
from .core import (
    LeaseLossPolicy,
    LockContext,
    RenewOutcome,
    normalize_lock_strategies,
    raise_on_lease_loss,
    resolve_jitter_delay,
    resolve_retry_delay,
)
from .exceptions import ConfigurationError, LeaseLostError, LockNotAcquiredError

LEASE_RENEWER_SHUTDOWN_TIMEOUT = 3.0

logger = logging.getLogger(__name__)


async def try_acquire_lock(
    conn: Any,
    table_parts: list[str],
    key: str,
    expire_at: datetime,
    value: str,
) -> tuple[bool, datetime | None]:
    async with conn.cursor() as cur:
        await cur.execute(acquire_lock_query(table_parts), (key, value, expire_at))
        row = await cur.fetchone()
        if row:
            logger.info("Lock acquired", extra={"key": key, "expire_at": row[1], "value": value})
            return True, row[1]
        return await _read_current(cur, table_parts, key)


async def try_acquire_run_lock(
    conn: Any,
    table_parts: list[str],
    key: str,
    ttl_seconds: float,
    value: str,
) -> tuple[bool, datetime | None]:
    async with conn.cursor() as cur:
        await cur.execute(acquire_run_lock_query(table_parts), (key, value, ttl_seconds))
        row = await cur.fetchone()
        if row:
            logger.info("Run-lock acquired", extra={"key": key, "expire_at": row[1], "value": value})
            return True, row[1]
        return await _read_current(cur, table_parts, key)


async def _read_current(cur: Any, table_parts: list[str], key: str) -> tuple[bool, datetime | None]:
    await cur.execute(read_current_query(table_parts), (key,))
    current_row = await cur.fetchone()
    if current_row:
        logger.warning(
            "Lock busy",
            extra={"key": key, "expire_at": current_row[0], "current_value": current_row[1]},
        )
        return False, current_row[0]

    logger.warning("Lock busy (row not found after conflict)", extra={"key": key})
    return False, None


async def renew_lease(
    conn: Any,
    table_parts: list[str],
    key: str,
    ttl_seconds: float,
    owner_value: str,
) -> bool:
    async with conn.cursor() as cur:
        await cur.execute(renew_lease_query(table_parts), (ttl_seconds, key, owner_value))
        row = await cur.fetchone()
        if row:
            logger.info("Lease renew extended", extra={"key": key, "new_expire_at": row[0]})
            return True
        return False


async def expire_lock_now(conn: Any, table_parts: list[str], key: str, owner_value: str) -> bool:
    async with conn.cursor() as cur:
        await cur.execute(expire_lock_query(table_parts), (key, owner_value))
        row = await cur.fetchone()
        if row:
            logger.info("Expired lock NOW", extra={"key": key})
            return True
        return False


async def close_connection(conn: Any) -> None:
    if conn is None:
        return
    try:
        await conn.rollback()
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to roll back connection", extra={"error": str(exc)}, exc_info=True)
    try:
        await conn.close()
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to close connection", extra={"error": str(exc)}, exc_info=True)


class ScheduleLock:
    """One lock per schedule slot. Async context manager."""

    def __init__(self, context: LockContext) -> None:
        self.context = context
        self.connection: Any = None

    async def __aenter__(self) -> ScheduleLock:
        require_psycopg()
        if self.context.next_run_time is None:
            raise ConfigurationError("LockContext.next_run_time is required for ScheduleLock.")
        logger.info("Connecting to database for schedule-lock")
        self.connection = await psycopg.AsyncConnection.connect(self.context.url, autocommit=False)

        acquired_schedule, schedule_expire_at = await try_acquire_lock(
            conn=self.connection,
            table_parts=self.context.table_parts,
            key=self.context.schedule_key,
            expire_at=self.context.next_run_time,
            value=self.context.owner,
        )
        await self.connection.commit()

        if not acquired_schedule:
            await close_connection(self.connection)
            raise LockNotAcquiredError(
                f"Schedule already taken for {self.context.schedule_key} until {schedule_expire_at!s}."
            )
        return self

    async def __aexit__(self, *_: object) -> bool:
        await close_connection(self.connection)
        return False


class LeaseRenewer:
    """Renews a lease row on a fixed cadence using an asyncio task."""

    def __init__(
        self,
        dsn: str,
        table_parts: list[str],
        run_key: str,
        ttl_seconds: float,
        owner_value: str,
        interval_seconds: float,
        stop_event: asyncio.Event,
        lost_event: asyncio.Event,
    ) -> None:
        self.dsn = dsn
        self.table_parts = table_parts
        self.run_key = run_key
        self.ttl_seconds = ttl_seconds
        self.owner_value = owner_value
        self.interval_seconds = interval_seconds
        self.stop_event = stop_event
        self.lost_event = lost_event
        self.ok = True
        self._clock = monotonic
        self.lease_deadline = 0.0

    async def run(self) -> None:
        require_psycopg()
        connection = None
        try:
            logger.info(
                "Heartbeat task started",
                extra={
                    "key": self.run_key,
                    "interval": self.interval_seconds,
                    "ttl": self.ttl_seconds,
                },
            )
            connection = await psycopg.AsyncConnection.connect(self.dsn, autocommit=False)
            renewed_at = self._clock()
            self.lease_deadline = renewed_at + self.ttl_seconds
            next_renew_at = renewed_at + self.interval_seconds

            while not self.stop_event.is_set():
                wait_timeout = max(0.0, next_renew_at - self._clock())
                if await self._wait_stop(wait_timeout):
                    break

                outcome, connection = await self._renew_until_deadline(connection)
                renewed_at = self._clock()

                match outcome:
                    case RenewOutcome.EXTENDED:
                        if renewed_at >= self.lease_deadline:
                            logger.error(
                                "Lease renew completed after local monotonic deadline",
                                extra={
                                    "key": self.run_key,
                                    "deadline": self.lease_deadline,
                                    "now": renewed_at,
                                },
                            )
                            self.ok = False
                            break
                        self.lease_deadline = renewed_at + self.ttl_seconds
                        next_renew_at = renewed_at + self.interval_seconds
                    case RenewOutcome.LOST | RenewOutcome.FAILED:
                        self.ok = False
                        break
        except Exception as exc:  # pragma: no cover
            logger.error(
                "Lease renew task could not start/connect",
                extra={"error": str(exc)},
                exc_info=True,
            )
            self.ok = False
        finally:
            if not self.ok:
                self.lost_event.set()
            await close_connection(connection)
            logger.info("Lease renew task stopped", extra={"key": self.run_key, "ok": self.ok})

    async def _wait_stop(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return True

    async def _renew_once(self, connection: Any) -> RenewOutcome:
        try:
            extended = await renew_lease(
                conn=connection,
                table_parts=self.table_parts,
                key=self.run_key,
                ttl_seconds=self.ttl_seconds,
                owner_value=self.owner_value,
            )
            await connection.commit()
        except Exception as exc:
            try:
                await connection.rollback()
            except Exception as rollback_exc:  # pragma: no cover
                logger.error(
                    "Lease renew rollback failed",
                    extra={"key": self.run_key, "error": str(rollback_exc)},
                    exc_info=True,
                )
            logger.warning(
                "Lease renew attempt failed",
                extra={"key": self.run_key, "error": str(exc)},
                exc_info=True,
            )
            return RenewOutcome.FAILED

        if not extended:
            logger.error(
                "Lease renew rejected (ownership lost or row missing)",
                extra={"key": self.run_key},
            )
            return RenewOutcome.LOST
        return RenewOutcome.EXTENDED

    async def _reconnect(self) -> Any | None:
        try:
            return await psycopg.AsyncConnection.connect(self.dsn, autocommit=False)
        except Exception as exc:
            logger.warning(
                "Lease renew reconnect failed",
                extra={"key": self.run_key, "error": str(exc)},
                exc_info=True,
            )
            return None

    async def _renew_until_deadline(self, connection: Any) -> tuple[RenewOutcome, Any]:
        """Retry transient failures with backoff while the monotonic lease deadline allows it."""
        attempt = 0
        while True:
            now = self._clock()
            if now >= self.lease_deadline:
                logger.error(
                    "Lease renew abandoned at local monotonic deadline",
                    extra={"key": self.run_key, "deadline": self.lease_deadline, "now": now},
                )
                return RenewOutcome.LOST, connection

            if connection is None:
                connection = await self._reconnect()

            if connection is not None:
                outcome = await self._renew_once(connection)
                if outcome is not RenewOutcome.FAILED:
                    return outcome, connection
                # A failed statement usually leaves the connection unusable; drop it and redial.
                await close_connection(connection)
                connection = None

            delay = resolve_retry_delay(attempt, self.lease_deadline - self._clock())
            # Reached only after a failed attempt, so giving up here is a genuine renewal failure.
            if delay is None or await self._wait_stop(delay):
                return RenewOutcome.LOST, connection
            attempt += 1


class LeaseLock:
    """One lock for the whole runtime of the job. Async context manager."""

    def __init__(self, context: LockContext) -> None:
        if context.run_ttl_seconds is None:
            raise ValueError("LockContext.run_ttl_seconds is required for LeaseLock")
        if context.lease_interval_seconds is None:
            raise ValueError("LockContext.lease_interval_seconds is required for LeaseLock")
        self.context = context
        self.connection: Any = None
        self.stop_event = asyncio.Event()
        self.lease_lost = asyncio.Event()
        self.renewer = LeaseRenewer(
            dsn=context.url,
            table_parts=context.table_parts,
            run_key=context.lease_key,
            ttl_seconds=context.run_ttl_seconds,
            owner_value=context.owner,
            interval_seconds=context.lease_interval_seconds,
            stop_event=self.stop_event,
            lost_event=self.lease_lost,
        )
        self.renewer_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> LeaseLock:
        require_psycopg()
        logger.info("Connecting to database for run-lock")
        self.connection = await psycopg.AsyncConnection.connect(self.context.url, autocommit=False)

        acquired_run, run_expire_at = await try_acquire_run_lock(
            conn=self.connection,
            table_parts=self.context.table_parts,
            key=self.context.lease_key,
            ttl_seconds=self.renewer.ttl_seconds,
            value=self.context.owner,
        )
        await self.connection.commit()

        if not acquired_run:
            await close_connection(self.connection)
            raise LockNotAcquiredError(
                f"Run-lock busy for {self.context.lease_key} until {run_expire_at!s}."
            )

        self.renewer_task = asyncio.create_task(self.renewer.run())
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, *_: object) -> bool:
        self.stop_event.set()
        await self._join_renewer()
        if not self.renewer.ok:
            logger.warning(
                "Lease renew not OK (ownership may have been lost)",
                extra={"key": self.context.lease_key},
            )

        other_connection = None
        try:
            if self.renewer.ok:
                other_connection = await psycopg.AsyncConnection.connect(
                    self.context.url, autocommit=False
                )
                expired = await expire_lock_now(
                    other_connection,
                    self.context.table_parts,
                    self.context.lease_key,
                    self.context.owner,
                )
                await other_connection.commit()
                if not expired:
                    logger.warning(
                        "Could not expire run-lock on exit (not owner or already expired)",
                        extra={"key": self.context.lease_key},
                    )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to expire run-lock on exit", extra={"error": str(exc)}, exc_info=True)
        finally:
            await close_connection(self.connection)
            await close_connection(other_connection)

        # Only when the block itself succeeded: an in-flight exception is the more useful signal.
        if exc_type is None and self.lease_lost.is_set():
            raise_on_lease_loss(self.context)
        return False

    async def _join_renewer(self) -> None:
        if self.renewer_task is None:
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(self.renewer_task), timeout=LEASE_RENEWER_SHUTDOWN_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Lease renew task did not stop in time; cancelling",
                extra={"key": self.context.lease_key},
            )
            self.renewer_task.cancel()
            try:
                await self.renewer_task
            except (asyncio.CancelledError, Exception):  # pragma: no cover
                pass


def build_locks(context: LockContext, strategies: Iterable[str]) -> list[ScheduleLock | LeaseLock]:
    lock_mapping: dict[str, type[ScheduleLock] | type[LeaseLock]] = {
        "schedule": ScheduleLock,
        "lease": LeaseLock,
    }
    return [lock_mapping[strategy](context) for strategy in normalize_lock_strategies(strategies)]


async def apply_startup_jitter(max_seconds: float) -> float:
    delay = resolve_jitter_delay(max_seconds, random.random())
    if delay > 0.0:
        logger.info("Applying startup jitter", extra={"delay": delay})
        await asyncio.sleep(delay)
    return delay


@dataclass(frozen=True, kw_only=True)
class LockSession:
    """Handle yielded by `acquire_locks`. `lease_lost` is set when the lease can no longer be held."""

    lease_lost: asyncio.Event | None = None


def resolve_lease_lost_event(
    locks: Sequence[ScheduleLock | LeaseLock], policy: LeaseLossPolicy
) -> asyncio.Event | None:
    if policy is LeaseLossPolicy.CONTINUE:
        return None
    return next((lock.lease_lost for lock in locks if isinstance(lock, LeaseLock)), None)


@asynccontextmanager
async def acquire_locks(
    context: LockContext, strategies: Iterable[str]
) -> AsyncIterator[LockSession]:
    await apply_startup_jitter(context.jitter_max_seconds)
    async with AsyncExitStack() as stack:
        locks = build_locks(context, strategies)
        for lock in locks:
            await stack.enter_async_context(lock)
        yield LockSession(
            lease_lost=resolve_lease_lost_event(locks, context.lease_loss_policy)
        )


P = ParamSpec("P")
R = TypeVar("R")


async def _run_until_lease_lost(
    coro: Awaitable[R], lease_lost: asyncio.Event | None, lease_key: str
) -> R:
    """Await the guarded coroutine; cancel and raise `LeaseLostError` if the lease drops first."""
    task = asyncio.ensure_future(coro)
    if lease_lost is None:
        return await task

    lost_waiter = asyncio.ensure_future(lease_lost.wait())
    try:
        await asyncio.wait({task, lost_waiter}, return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            return task.result()

        logger.error("Lease lost; cancelling guarded coroutine", extra={"key": lease_key})
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise LeaseLostError(
            f"Lease {lease_key} was lost while the guarded coroutine was running; "
            "another process may have owned it concurrently."
        )
    finally:
        lost_waiter.cancel()


def with_locks(
    context: LockContext, strategies: Iterable[str]
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Guard a coroutine function so it runs only while the configured locks are held.

    Raises `LockNotAcquiredError` if the slot is already taken. Under `LeaseLossPolicy.TERMINATE`
    a lost lease cancels the in-flight coroutine and raises `LeaseLostError`; under `CONTINUE`
    the coroutine runs to completion.
    """
    strategies = tuple(strategies)

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            async with acquire_locks(context, strategies) as session:
                return await _run_until_lease_lost(
                    func(*args, **kwargs), session.lease_lost, context.lease_key
                )

        return wrapper

    return decorator
