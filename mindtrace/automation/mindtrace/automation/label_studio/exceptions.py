"""
Label Studio Automation Exception Hierarchy

Defines exceptions for Label Studio automation utilities to allow
callers to distinguish common failure scenarios programmatically.

Exception Hierarchy:
    LabelStudioError (base)
    ├── ProjectNotFoundError
    ├── ProjectFetchError
    ├── StorageError (base for storage operations)
    │   ├── StorageAlreadyExistsError
    │   ├── StorageCreationError
    │   ├── CredentialsNotFoundError
    │   └── CredentialsReadError
"""


class LabelStudioError(Exception):
    """Base exception for Label Studio automation errors."""

    pass


class ProjectNotFoundError(LabelStudioError):
    """Raised when a Label Studio project is not found by id or name."""

    pass


class ProjectAlreadyExistsError(LabelStudioError):
    """Raised when a Label Studio project already exists by id or name."""

    pass


class ProjectFetchError(LabelStudioError):
    """Raised when fetching a Label Studio project fails for non-404 reasons."""

    pass


class StorageError(LabelStudioError):
    """Base exception for storage-related operations."""

    pass


class StorageAlreadyExistsError(StorageError):
    """Raised when trying to create a storage that already exists."""

    pass


class StorageCreationError(StorageError):
    """Raised when creating a storage fails."""

    pass


class StorageNotFoundError(StorageError):
    """Raised when a storage is not found."""

    pass


class CredentialsNotFoundError(StorageError):
    """Raised when credentials path is missing or invalid."""

    pass


class CredentialsReadError(StorageError):
    """Raised when credentials file can't be read or parsed."""

    pass
