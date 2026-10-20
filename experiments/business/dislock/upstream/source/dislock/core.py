from __future__ import annotations

import logging
import random
import subprocess
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import wraps
from threading import Event, Thread
from time import monotonic, sleep
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Iterator,
    Literal,
    ParamSpec,
    Sequence,
    TypeVar,
)

if TYPE_CHECKING:
    from psycopg import Connection

from ._queries import (
    acquire_lock_query,
    acquire_run_lock_query,
    expire_lock_query,
    psycopg,
    read_current_query,
    renew_lease_query,
    require_psycopg,
)
from .exceptions import ConfigurationError, LeaseLostError, LockNotAcquiredError

MIN_LEASE_INTERVAL_SECONDS = 1.0
MAX_LEASE_INTERVAL_SECONDS = 10.0
LEASE_RATIO = 0.3
LEASE_TTL = 60.0
LOCK_ORDER = ("schedule", "lease")
LEASE_LOST_EXIT_CODE = 75
COMMAND_POLL_INTERVAL_SECONDS = 0.5
TERMINATE_GRACE_SECONDS = 10.0
LEASE_RETRY_BASE_DELAY_SECONDS = 0.1
LEASE_RETRY_MAX_DELAY_SECONDS = 2.0

logging.getLogger("dislock").addHandler(logging.NullHandler())
logger = logging.getLogger(__name__)


class RenewOutcome(Enum):
    """Result of one renewal attempt. `FAILED` is transient, `LOST` is definitive."""

    EXTENDED = "extended"
    LOST = "lost"
    FAILED = "failed"


def resolve_retry_delay(attempt: int, remaining_seconds: float) -> float | None:
    """Backoff for a 0-based attempt, truncated to the lease deadline. None when no time is left."""
    if remaining_seconds <= 0.0:
        return None
    delay = min(LEASE_RETRY_BASE_DELAY_SECONDS * 2**attempt, LEASE_RETRY_MAX_DELAY_SECONDS)
    return min(delay, remaining_seconds)


class LeaseLossPolicy(str, Enum):
    """What happens to the wrapped command when the lease can no longer be held."""

    TERMINATE = "terminate"
    CONTINUE = "continue"


def raise_on_lease_loss(context: LockContext) -> None:
    if context.lease_loss_policy is LeaseLossPolicy.CONTINUE:
        logger.warning("Lease was lost during the guarded block: key=%s", context.lease_key)
        return
    raise LeaseLostError(
        f"Lease {context.lease_key} was lost while the guarded block was running; "
        "another process may have owned it concurrently."
    )


def terminate_command(process: subprocess.Popen[bytes]) -> int:
    logger.error("Lease lost; terminating command: pid=%d", process.pid)
    process.terminate()
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        logger.error(
            "Command still alive %.1fs after SIGTERM; killing: pid=%d",
            TERMINATE_GRACE_SECONDS,
            process.pid,
        )
        process.kill()
        process.wait()
    return LEASE_LOST_EXIT_CODE


def wait_for_command(process: subprocess.Popen[bytes], abort: Event | None) -> int:
    if abort is None:
        return process.wait()

    while not abort.is_set():
        try:
            return process.wait(timeout=COMMAND_POLL_INTERVAL_SECONDS)
        except subprocess.TimeoutExpired:
            continue
    return terminate_command(process)


def execute_command(cmd_parts: list[str], abort: Event | None = None) -> int:
    try:
        logger.info("Executing command: %s", " ".join(cmd_parts))
        with subprocess.Popen(cmd_parts) as process:
            returncode = wait_for_command(process, abort)
    except OSError as exc:
        logger.error("Could not start command: %s", exc, exc_info=True)
        return 1

    if returncode == 0:
        logger.info("Command completed with return code %d", returncode)
    else:
        logger.error("Command failed with return code %d", returncode)
    return returncode


def parse_table_name(raw: str | None) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return ["key_value"]
    return raw.split(".")


def normalize_lock_strategies(strategies: Iterable[str]) -> tuple[str, ...]:
    strategy_set = set(strategies)
    return tuple(strategy for strategy in LOCK_ORDER if strategy in strategy_set)


def resolve_jitter_delay(max_seconds: float, sample: float) -> float:
    """Map a uniform sample in [0, 1) to a startup delay in [0, max_seconds]."""
    if max_seconds <= 0.0:
        return 0.0
    return max_seconds * sample


def apply_startup_jitter(max_seconds: float) -> float:
    delay = resolve_jitter_delay(max_seconds, random.random())
    if delay > 0.0:
        logger.info("Applying startup jitter: %.3fs", delay)
        sleep(delay)
    return delay


def get_db_time(conn: Any) -> datetime:
    with conn.cursor() as cur:
        cur.execute("SELECT NOW();")
        row = cur.fetchone()
        return row[0]


def try_acquire_lock(
    conn: Any,
    table_parts: list[str],
    key: str,
    expire_at: datetime,
    value: str,
) -> tuple[bool, datetime | None]:
    with conn.cursor() as cur:
        cur.execute(acquire_lock_query(table_parts), (key, value, expire_at))
        row = cur.fetchone()
        if row:
            logger.info("Lock acquired: key=%s expire_at=%s value=%s", key, row[1], value)
            return True, row[1]

        cur.execute(read_current_query(table_parts), (key,))
        current_row = cur.fetchone()
        if current_row:
            logger.warning(
                "Lock busy: key=%s expire_at=%s current_value=%s",
                key,
                current_row[0],
                current_row[1],
            )
            return False, current_row[0]

        logger.warning("Lock busy: key=%s (row not found after conflict?)", key)
        return False, None


def try_acquire_run_lock(
    conn: Any,
    table_parts: list[str],
    key: str,
    ttl_seconds: float,
    value: str,
) -> tuple[bool, datetime | None]:
    with conn.cursor() as cur:
        cur.execute(acquire_run_lock_query(table_parts), (key, value, ttl_seconds))
        row = cur.fetchone()
        if row:
            logger.info("Run-lock acquired: key=%s expire_at=%s value=%s", key, row[1], value)
            return True, row[1]

        cur.execute(read_current_query(table_parts), (key,))
        current_row = cur.fetchone()
        if current_row:
            logger.warning(
                "Run-lock busy: key=%s expire_at=%s current_value=%s",
                key,
                current_row[0],
                current_row[1],
            )
            return False, current_row[0]

        logger.warning("Run-lock busy: key=%s (row not found after conflict?)", key)
        return False, None


def renew_lease(
    conn: Any,
    table_parts: list[str],
    key: str,
    ttl_seconds: float,
    owner_value: str,
) -> bool:
    with conn.cursor() as cur:
        cur.execute(renew_lease_query(table_parts), (ttl_seconds, key, owner_value))
        row = cur.fetchone()
        if row:
            logger.info("Lease renew extended: key=%s new_expire_at=%s", key, row[0])
            return True
        return False


def expire_lock_now(conn: Any, table_parts: list[str], key: str, owner_value: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(expire_lock_query(table_parts), (key, owner_value))
        row = cur.fetchone()
        if row:
            logger.info("Expired lock NOW: key=%s", key)
            return True
        return False


def close_connection(conn: Any) -> None:
    try:
        if conn is not None:
            conn.rollback()
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to roll back connection: %s", exc, exc_info=True)

    try:
        if conn is not None:
            conn.close()
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to close connection: %s", exc, exc_info=True)


@dataclass(frozen=True, kw_only=True, repr=False)
class LockContext:
    url: str
    table_parts: list[str]
    lock_key: str
    owner: str
    schedule: str | None = None
    run_ttl_seconds: float | None = None
    lease_interval_seconds: float | None = None
    next_run_time: datetime | None = None
    jitter_max_seconds: float = 0.0
    lease_loss_policy: LeaseLossPolicy = LeaseLossPolicy.TERMINATE

    @property
    def schedule_key(self) -> str:
        return f"cronjob-lock:schedule:{self.lock_key}"

    @property
    def lease_key(self) -> str:
        return f"cronjob-lock:lease:{self.lock_key}"

    def __repr__(self) -> str:
        return (
            "LockContext("
            "url='<redacted>', "
            f"table_parts={self.table_parts!r}, "
            f"lock_key={self.lock_key!r}, "
            f"owner={self.owner!r}, "
            f"schedule={self.schedule!r}, "
            f"run_ttl_seconds={self.run_ttl_seconds!r}, "
            f"lease_interval_seconds={self.lease_interval_seconds!r}, "
            f"next_run_time={self.next_run_time!r}, "
            f"jitter_max_seconds={self.jitter_max_seconds!r}, "
            f"lease_loss_policy={self.lease_loss_policy.value!r}"
            ")"
        )


class BaseLock:
    def __init__(self, context: LockContext) -> None:
        self.context = context
        self.connection: Connection[Any] | None = None


class ScheduleLock(BaseLock):
    """One lock per schedule slot."""

    def __enter__(self) -> ScheduleLock:
        require_psycopg()
        if self.context.next_run_time is None:
            raise ConfigurationError("LockContext.next_run_time is required for ScheduleLock.")
        logger.info("Connecting to database for schedule-lock...")
        self.connection = psycopg.connect(self.context.url, autocommit=False)

        acquired_schedule, schedule_expire_at = try_acquire_lock(
            conn=self.connection,
            table_parts=self.context.table_parts,
            key=self.context.schedule_key,
            expire_at=self.context.next_run_time,
            value=self.context.owner,
        )
        self.connection.commit()

        if not acquired_schedule:
            close_connection(self.connection)
            raise LockNotAcquiredError(
                f"Schedule already taken for {self.context.schedule_key} until {schedule_expire_at!s}."
            )
        return self

    def __exit__(self, *_: object) -> Literal[False]:
        close_connection(self.connection)
        return False


class LeaseRenewer(Thread):
    def __init__(
        self,
        dsn: str,
        table_parts: list[str],
        run_key: str,
        ttl_seconds: float,
        owner_value: str,
        interval_seconds: float,
        stop_event: Event,
        lost_event: Event,
    ) -> None:
        super().__init__(daemon=True)
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

    def run(self) -> None:
        require_psycopg()
        connection = None
        try:
            logger.info(
                "Heartbeat thread started: key=%s interval=%.2fs ttl=%.2fs",
                self.run_key,
                self.interval_seconds,
                self.ttl_seconds,
            )
            connection = psycopg.connect(self.dsn, autocommit=False)
            renewed_at = self._clock()
            self.lease_deadline = renewed_at + self.ttl_seconds
            next_renew_at = renewed_at + self.interval_seconds

            while not self.stop_event.is_set():
                wait_timeout = max(0.0, next_renew_at - self._clock())
                if self.stop_event.wait(wait_timeout):
                    break

                outcome, connection = self._renew_until_deadline(connection)
                renewed_at = self._clock()

                match outcome:
                    case RenewOutcome.EXTENDED:
                        if renewed_at >= self.lease_deadline:
                            logger.error(
                                "Lease renew completed after local monotonic deadline: key=%s deadline=%.6f now=%.6f",
                                self.run_key,
                                self.lease_deadline,
                                renewed_at,
                            )
                            self.ok = False
                            break
                        self.lease_deadline = renewed_at + self.ttl_seconds
                        next_renew_at = renewed_at + self.interval_seconds
                    case RenewOutcome.LOST | RenewOutcome.FAILED:
                        self.ok = False
                        break
        except Exception as exc:  # pragma: no cover
            logger.error("Lease renew thread could not start/connect: %s", exc, exc_info=True)
            self.ok = False
        finally:
            if not self.ok:
                self.lost_event.set()
            close_connection(connection)
            logger.info("Lease renew thread stopped: key=%s ok=%s", self.run_key, self.ok)

    def _renew_once(self, connection: Any) -> RenewOutcome:
        try:
            extended = renew_lease(
                conn=connection,
                table_parts=self.table_parts,
                key=self.run_key,
                ttl_seconds=self.ttl_seconds,
                owner_value=self.owner_value,
            )
            connection.commit()
        except Exception as exc:
            try:
                connection.rollback()
            except Exception as rollback_exc:  # pragma: no cover
                logger.error(
                    "Lease renew rollback failed: key=%s error=%s",
                    self.run_key,
                    rollback_exc,
                    exc_info=True,
                )
            logger.warning(
                "Lease renew attempt failed: key=%s error=%s",
                self.run_key,
                exc,
                exc_info=True,
            )
            return RenewOutcome.FAILED

        if not extended:
            logger.error(
                "Lease renew rejected (ownership lost or row missing): key=%s",
                self.run_key,
            )
            return RenewOutcome.LOST
        return RenewOutcome.EXTENDED

    def _reconnect(self) -> Any | None:
        try:
            return psycopg.connect(self.dsn, autocommit=False)
        except Exception as exc:
            logger.warning(
                "Lease renew reconnect failed: key=%s error=%s",
                self.run_key,
                exc,
                exc_info=True,
            )
            return None

    def _renew_until_deadline(self, connection: Any) -> tuple[RenewOutcome, Any]:
        """Retry transient failures with backoff while the monotonic lease deadline allows it."""
        attempt = 0
        while True:
            now = self._clock()
            if now >= self.lease_deadline:
                logger.error(
                    "Lease renew abandoned at local monotonic deadline: key=%s deadline=%.6f now=%.6f",
                    self.run_key,
                    self.lease_deadline,
                    now,
                )
                return RenewOutcome.LOST, connection

            if connection is None:
                connection = self._reconnect()

            if connection is not None:
                outcome = self._renew_once(connection)
                if outcome is not RenewOutcome.FAILED:
                    return outcome, connection
                # A failed statement usually leaves the connection unusable; drop it and redial.
                close_connection(connection)
                connection = None

            delay = resolve_retry_delay(attempt, self.lease_deadline - self._clock())
            # Reached only after a failed attempt, so giving up here is a genuine renewal failure.
            if delay is None or self.stop_event.wait(delay):
                return RenewOutcome.LOST, connection
            attempt += 1


class LeaseLock(BaseLock):
    """One lock for the whole runtime of the job."""

    def __init__(self, context: LockContext) -> None:
        super().__init__(context)
        if context.run_ttl_seconds is None:
            raise ValueError("LockContext.run_ttl_seconds is required for LeaseLock")
        if context.lease_interval_seconds is None:
            raise ValueError("LockContext.lease_interval_seconds is required for LeaseLock")
        self.stop_event = Event()
        self.lease_lost = Event()
        self.lease_renewer = LeaseRenewer(
            dsn=context.url,
            table_parts=context.table_parts,
            run_key=context.lease_key,
            ttl_seconds=context.run_ttl_seconds,
            owner_value=context.owner,
            interval_seconds=context.lease_interval_seconds,
            stop_event=self.stop_event,
            lost_event=self.lease_lost,
        )

    def __enter__(self) -> LeaseLock:
        require_psycopg()
        logger.info("Connecting to database for run-lock...")
        self.connection = psycopg.connect(self.context.url, autocommit=False)

        acquired_run, run_expire_at = try_acquire_run_lock(
            conn=self.connection,
            table_parts=self.context.table_parts,
            key=self.context.lease_key,
            ttl_seconds=self.lease_renewer.ttl_seconds,
            value=self.context.owner,
        )
        self.connection.commit()

        if not acquired_run:
            close_connection(self.connection)
            raise LockNotAcquiredError(
                f"Run-lock busy for {self.context.lease_key} until {run_expire_at!s}."
            )

        self.lease_renewer.start()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *_: object) -> Literal[False]:
        self.stop_event.set()
        self.lease_renewer.join(timeout=3.0)
        if not self.lease_renewer.ok:
            logger.warning("Lease renew not OK (ownership may have been lost): key=%s", self.context.lease_key)

        other_connection = None
        try:
            other_connection = psycopg.connect(self.context.url, autocommit=False)
            if self.lease_renewer.ok:
                expired = expire_lock_now(
                    other_connection,
                    self.context.table_parts,
                    self.context.lease_key,
                    self.context.owner,
                )
                other_connection.commit()
                if not expired:
                    logger.warning(
                        "Could not expire run-lock on exit (not owner or already expired): key=%s",
                        self.context.lease_key,
                    )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to expire run-lock on exit: %s", exc, exc_info=True)
        finally:
            close_connection(self.connection)
            close_connection(other_connection)

        # Only when the block itself succeeded: an in-flight exception is the more useful signal.
        if exc_type is None and self.lease_lost.is_set():
            raise_on_lease_loss(self.context)
        return False


def build_locks(context: LockContext, strategies: Iterable[str]) -> list[ScheduleLock | LeaseLock]:
    lock_mapping: dict[str, type[ScheduleLock] | type[LeaseLock]] = {
        "schedule": ScheduleLock,
        "lease": LeaseLock,
    }
    return [lock_mapping[strategy](context) for strategy in normalize_lock_strategies(strategies)]


@dataclass(frozen=True, kw_only=True)
class LockSession:
    """Handle yielded by `acquire_locks`. `lease_lost` is set when the lease can no longer be held."""

    lease_lost: Event | None = None


def resolve_lease_lost_event(
    locks: Sequence[ScheduleLock | LeaseLock], policy: LeaseLossPolicy
) -> Event | None:
    if policy is LeaseLossPolicy.CONTINUE:
        return None
    return next((lock.lease_lost for lock in locks if isinstance(lock, LeaseLock)), None)


@contextmanager
def acquire_locks(context: LockContext, strategies: Iterable[str]) -> Iterator[LockSession]:
    apply_startup_jitter(context.jitter_max_seconds)
    with ExitStack() as stack:
        locks = build_locks(context, strategies)
        for lock in locks:
            stack.enter_context(lock)
        yield LockSession(
            lease_lost=resolve_lease_lost_event(locks, context.lease_loss_policy)
        )


def run_with_locks(cmd_parts: list[str], context: LockContext, strategies: Iterable[str]) -> int:
    try:
        with acquire_locks(context, strategies) as session:
            return execute_command(cmd_parts, session.lease_lost)
    except LeaseLostError as exc:
        logger.error("%s", exc)
        return LEASE_LOST_EXIT_CODE


P = ParamSpec("P")
R = TypeVar("R")


def with_locks(
    context: LockContext, strategies: Iterable[str]
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Guard a function so it runs only while the configured locks are held.

    Raises `LockNotAcquiredError` if the slot is already taken, and `LeaseLostError` on exit
    when the lease dropped during a call that otherwise completed (see `LeaseLossPolicy`).
    A running synchronous call cannot be pre-empted, so mutual exclusion is best-effort.
    """
    strategies = tuple(strategies)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with acquire_locks(context, strategies):
                return func(*args, **kwargs)

        return wrapper

    return decorator
