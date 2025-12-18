from abc import abstractmethod
from enum import Enum
from typing import Type

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
    def find(self, *args, **kwargs) -> list[BaseModel]:
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
