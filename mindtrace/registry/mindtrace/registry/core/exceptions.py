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


class RegistryCleanupRequired(Exception):
    """Raised when an operation succeeds but follow-up cleanup is still required."""

    pass


class StoreLocationNotFound(Exception):
    """Raised when a store location/mount is unknown."""

    pass


class StoreKeyFormatError(ValueError):
    """Raised when a store key format is invalid for the requested operation."""

    pass


class StoreAmbiguousObjectError(Exception):
    """Raised when an unqualified load finds an object in multiple locations."""

    pass
