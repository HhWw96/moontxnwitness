import os
import sys
from datetime import datetime
from typing import Sequence

from .core import (
    LEASE_RATIO,
    LEASE_TTL,
    MAX_LEASE_INTERVAL_SECONDS,
    MIN_LEASE_INTERVAL_SECONDS,
    LeaseLossPolicy,
    LockContext,
    close_connection,
    get_db_time,
    logger,
    normalize_lock_strategies,
    parse_table_name,
    run_with_locks,
)
from .exceptions import ConfigurationError, LockNotAcquiredError
from .logging import configure_cli_logging

USAGE = "Usage: dislock <URL_ENV_NAME> <command...>"

try:  # pragma: no cover - exercised indirectly in runtime environments
    import croniter
except ModuleNotFoundError:  # pragma: no cover
    # Optional runtime dependency; guarded by the "schedule" strategy branch below.
    croniter = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised indirectly in runtime environments
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]


def require_env(name: str) -> str:
    try:
        return os.environ[name]
    except KeyError as exc:
        raise ConfigurationError(f"Environment variable {name} not set.") from exc


def require_cli_dependencies() -> None:
    missing: list[str] = []
    if croniter is None:
        missing.append("croniter")
    if psycopg is None:
        missing.append("psycopg")
    if missing:
        raise ConfigurationError(
            "Missing runtime dependencies: " + ", ".join(missing) + ". Install the package dependencies first."
        )


def parse_lock_strategies(raw: str | None) -> tuple[str, ...]:
    strategies = frozenset((raw or "schedule").strip().lower().split(","))
    if not strategies.issubset({"schedule", "lease"}):
        raise ConfigurationError(f"LOCK_STRATEGY must contain only 'schedule' or 'lease' (got {raw!r}).")
    return normalize_lock_strategies(strategies)


def parse_jitter_seconds(raw: str | None) -> float:
    raw = (raw or "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"LOCK_JITTER_SECONDS must be a number (got {raw!r}).") from exc
    if value < 0.0:
        raise ConfigurationError(f"LOCK_JITTER_SECONDS must be non-negative (got {value}).")
    return value


def parse_lease_loss_policy(raw: str | None) -> LeaseLossPolicy:
    value = (raw or "").strip().lower() or LeaseLossPolicy.TERMINATE.value
    try:
        return LeaseLossPolicy(value)
    except ValueError as exc:
        raise ConfigurationError(
            f"LOCK_ON_LEASE_LOSS must be 'terminate' or 'continue' (got {raw!r})."
        ) from exc


def build_context_from_env(url_env_name: str) -> tuple[tuple[str, ...], LockContext]:
    require_cli_dependencies()
    lock_table_raw = os.environ.get("LOCK_TABLE", "key_value")
    url = require_env(url_env_name)
    lock_strategies = parse_lock_strategies(os.environ.get("LOCK_STRATEGY", "schedule"))
    jitter_max_seconds = parse_jitter_seconds(os.environ.get("LOCK_JITTER_SECONDS"))
    lease_loss_policy = parse_lease_loss_policy(os.environ.get("LOCK_ON_LEASE_LOSS"))

    lease_ttl_seconds = None
    lease_interval_seconds = None
    if "lease" in lock_strategies:
        lease_ttl_seconds = float(os.environ.get("RUN_LOCK_TTL_SECONDS", LEASE_TTL))
        lease_interval_default = max(
            MIN_LEASE_INTERVAL_SECONDS,
            min(MAX_LEASE_INTERVAL_SECONDS, lease_ttl_seconds * LEASE_RATIO),
        )
        lease_interval_seconds = float(os.environ.get("LOCK_LEASE_INTERVAL", str(lease_interval_default)))

        if lease_interval_seconds > lease_ttl_seconds:
            raise ConfigurationError(
                "LOCK_LEASE_INTERVAL must be less than or equal to RUN_LOCK_TTL_SECONDS "
                f"(got interval={lease_interval_seconds} ttl={lease_ttl_seconds})."
            )

    schedule = None
    next_run_time = None
    if "schedule" in lock_strategies:
        schedule = require_env("CRON_SCHEDULE")
        connection = None
        try:
            connection = psycopg.connect(url, autocommit=False)
            next_run_time = croniter.croniter(schedule, get_db_time(connection)).get_next(datetime)
        except Exception as exc:
            raise ConfigurationError("Failed to calculate next run time from CRON_SCHEDULE.") from exc
        finally:
            close_connection(connection)

    context = LockContext(
        url=url,
        table_parts=parse_table_name(lock_table_raw),
        lock_key=require_env("LOCK_KEY"),
        owner=f"{os.uname().nodename}:{os.getpid()}",
        schedule=schedule,
        run_ttl_seconds=lease_ttl_seconds,
        lease_interval_seconds=lease_interval_seconds,
        next_run_time=next_run_time,
        jitter_max_seconds=jitter_max_seconds,
        lease_loss_policy=lease_loss_policy,
    )

    logger.info("Lock strategies: %s", ", ".join(lock_strategies))
    logger.info("Lock context: %s", context)
    return lock_strategies, context


def main(argv: Sequence[str] | None = None) -> int:
    configure_cli_logging()
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) < 2:
        logger.error(USAGE)
        return 2

    url_env_name, *cmd_parts = args

    try:
        strategies, context = build_context_from_env(url_env_name)
        return run_with_locks(cmd_parts, context, strategies)
    except LockNotAcquiredError as exc:
        logger.info("%s", exc)
        return 0
    except ConfigurationError as exc:
        logger.error("%s", exc)
        return 2
    except Exception as exc:  # pragma: no cover
        logger.error("Unexpected dislock failure: %s", exc, exc_info=True)
        return 1
