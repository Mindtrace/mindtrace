"""Registry exceptions."""


class LockTimeoutError(Exception):
    """Exception raised when a lock cannot be acquired within the timeout period."""

    pass


class LockAcquisitionError(Exception):
    """Exception raised when a lock cannot be acquired immediately (lock is in use)."""

    pass


class RegistryObjectNotFound(Exception):
    """Exception raised when an object is not found in the registry."""

    pass


class RegistryVersionConflict(Exception):
    """Exception raised when attempting to save an object with a version that already exists."""

    pass
