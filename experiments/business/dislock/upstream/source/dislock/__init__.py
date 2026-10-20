"""Public package interface for dislock."""

import logging

from .core import (
    LEASE_LOST_EXIT_CODE,
    LeaseLock,
    LeaseLossPolicy,
    LockContext,
    LockSession,
    ScheduleLock,
    acquire_locks,
    build_locks,
    run_with_locks,
    with_locks,
)
from .exceptions import (
    ConfigurationError,
    DislockError,
    LeaseLostError,
    LockNotAcquiredError,
)

logging.getLogger("dislock").addHandler(logging.NullHandler())

__all__ = [
    "LEASE_LOST_EXIT_CODE",
    "ConfigurationError",
    "DislockError",
    "LeaseLock",
    "LeaseLossPolicy",
    "LeaseLostError",
    "LockContext",
    "LockNotAcquiredError",
    "LockSession",
    "ScheduleLock",
    "acquire_locks",
    "build_locks",
    "run_with_locks",
    "with_locks",
]


def main() -> int:
    from .cli import main as cli_main

    return cli_main()
