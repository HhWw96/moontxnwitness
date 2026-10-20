class DislockError(Exception):
    """Base exception for the library."""


class ConfigurationError(DislockError):
    """Raised when the lock configuration is invalid."""


class LockNotAcquiredError(DislockError):
    """Raised when a lock is already owned by another process."""


class LeaseLostError(DislockError):
    """Raised on exit when the lease stopped being held while the guarded block was running."""
