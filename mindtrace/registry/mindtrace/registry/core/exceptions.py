"""Registry lock-related exceptions."""


class LockTimeoutError(Exception):
    """Exception raised when a lock cannot be acquired within the timeout period."""

    pass


class LockAcquisitionError(Exception):
    """Exception raised when a lock cannot be acquired immediately (lock is in use)."""

    pass
