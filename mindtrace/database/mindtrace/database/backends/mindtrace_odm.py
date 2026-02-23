from abc import abstractmethod
from enum import Enum
from typing import Any, Literal, Type

from pydantic import BaseModel

from mindtrace.core import MindtraceABC


class InitMode(Enum):
    """Initialization mode for database backends."""

    SYNC = "sync"
    ASYNC = "async"


class MindtraceODM(MindtraceABC):
    """
    Abstract base class for all Mindtrace Object Document Mapping (ODM) backends.

    This class defines the common interface that all database backends must implement
    to provide consistent data persistence operations across different storage engines
    like MongoDB, Redis, and local storage.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.mindtrace_odm import MindtraceODM

            class CustomBackend(MindtraceODM):
                def is_async(self) -> bool:
                    return False

                def insert(self, obj):
                    # Implementation here
                    pass
    """

    @abstractmethod
    def is_async(self) -> bool:
        """
        Determine if this backend operates asynchronously.

        Returns:
            bool: True if the backend uses async operations, False otherwise.

        Example:
            .. code-block:: python

                backend = SomeBackend()
                if backend.is_async():
                    result = await backend.insert(document)
                else:
                    result = backend.insert(document)
        """

    @abstractmethod
    def insert(self, obj: BaseModel):
        """
        Insert a new document into the database.

        Args:
            obj (BaseModel): The document object to insert into the database.

        Returns:
            The inserted document with any generated fields (like ID) populated.

        Raises:
            DuplicateInsertError: If the document violates unique constraints.

        Example:
            .. code-block:: python

                from pydantic import BaseModel

                class User(BaseModel):
                    name: str
                    email: str

                user = User(name="John", email="john@example.com")
                inserted_user = backend.insert(user)
        """

    @abstractmethod
    def get(self, id: str) -> BaseModel:
        """
        Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            BaseModel: The document if found.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    user = backend.get("user_123")
                    print(f"Found user: {user.name}")
                except DocumentNotFoundError:
                    print("User not found")
        """

    @abstractmethod
    def update(self, obj: BaseModel):
        """
        Update an existing document in the database.

        The document object should have been retrieved from the database,
        modified, and then passed to this method to save the changes.

        Args:
            obj (BaseModel): The document object with modified fields to save.

        Returns:
            BaseModel: The updated document.

        Raises:
            DocumentNotFoundError: If the document doesn't exist in the database.

        Example:
            .. code-block:: python

                # Get the document
                user = backend.get("user_123")
                # Modify it
                user.age = 31
                user.name = "John Updated"
                # Save the changes
                updated_user = backend.update(user)
        """

    @abstractmethod
    def delete(self, id: str):
        """
        Delete a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If no document with the given ID exists.

        Example:
            .. code-block:: python

                try:
                    backend.delete("user_123")
                    print("User deleted successfully")
                except DocumentNotFoundError:
                    print("User not found")
        """

    @abstractmethod
    def all(self) -> list[BaseModel]:
        """
        Retrieve all documents from the collection.

        Returns:
            list[BaseModel]: A list of all documents in the collection.

        Example:
            .. code-block:: python

                all_users = backend.all()
                print(f"Found {len(all_users)} users")
                for user in all_users:
                    print(f"- {user.name}")
        """

    @abstractmethod
    def find(
        self,
        where: dict | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int | None = None,
        **kwargs,
    ) -> list[BaseModel]:
        """
        Find documents matching the specified criteria.

        Args:
            *args: Query conditions and filters. The exact format depends on the backend.
            **kwargs: Additional query parameters.

        Returns:
            list[BaseModel]: A list of documents matching the query criteria.

        Example:
            .. code-block:: python

                # Find users with specific email (backend-specific syntax)
                users = backend.find(User.email == "john@example.com")

                # Find all users if no criteria specified
                all_users = backend.find()
        """

    def insert_one(self, doc: BaseModel | dict):
        """Insert one document (canonical alias for insert)."""
        return self.insert(doc)

    def find_one(self, where: dict, **kwargs) -> BaseModel | None:
        """Find first document matching where.

        Backends should override with native single-doc query.
        """
        results = self.find(where=where, limit=1, **kwargs)
        return results[0] if results else None

    @abstractmethod
    def update_one(
        self,
        where: dict,
        set_fields: dict,
        upsert: bool = False,
        return_document: Literal["none", "before", "after"] = "none",
    ) -> Any:
        """Update exactly one matching document."""

    @abstractmethod
    def delete_many(self, where: dict) -> int:
        """Delete all documents matching the filter.

        Returns:
            int: Number of documents deleted.
        """

    @abstractmethod
    def delete_one(self, where: dict) -> int:
        """Delete exactly one document matching the filter.

        Returns:
            int: Number of documents deleted (0 or 1).
        """

    @abstractmethod
    def distinct(self, field: str, where: dict | None = None) -> list[Any]:
        """Return distinct values for a field among matching documents."""

    @abstractmethod
    def get_raw_model(self) -> Type[BaseModel]:
        """
        Get the raw document model class used by this backend.

        Returns:
            Type[BaseModel]: The document model class used by this backend.
                For backends that don't use a specific model class, this may
                return the base BaseModel type or None.

        Example:
            .. code-block:: python

                model_class = backend.get_raw_model()
                print(f"Using model: {model_class.__name__}")
        """
