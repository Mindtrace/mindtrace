class DocumentNotFoundError(Exception):
    """
    Exception raised when a requested document cannot be found in the database.

    This exception is thrown by database backends when attempting to retrieve,
    update, or delete a document that doesn't exist in the underlying storage.

    Args:
        message (str): Human-readable description of the error.

    Example:
        .. code-block:: python

            from mindtrace.database.core.exceptions import DocumentNotFoundError

            try:
                doc = backend.get("non_existent_id")
            except DocumentNotFoundError as e:
                print(f"Document not found: {e}")
    """

    pass


class DuplicateInsertError(Exception):
    """
    Exception raised when attempting to insert a document that violates uniqueness constraints.

    This exception is thrown by database backends when trying to insert a document
    that would create a duplicate entry based on unique field constraints.

    Args:
        message (str): Human-readable description of the duplicate constraint violation.

    Example:
        .. code-block:: python

            from mindtrace.database.core.exceptions import DuplicateInsertError

            try:
                backend.insert(user_with_existing_email)
            except DuplicateInsertError as e:
                print(f"Duplicate entry error: {e}")
    """

    pass
