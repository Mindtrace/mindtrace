import uuid
from typing import Type

from pydantic import BaseModel

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.registry import Registry, RegistryBackend


class RegistryMindtraceODM(MindtraceODM):
    """Implementation of the Mindtrace ODM backend that uses the Registry backend.

    Pass in a RegistryBackend to select the storage source. By default, a local directory store will be used.

    Args:
        backend (RegistryBackend | None): Optional registry backend to use for storage.
        **kwargs: Additional configuration parameters.

    Example:
        .. code-block:: python

            from mindtrace.database.backends.registry_odm import RegistryMindtraceODM
            from pydantic import BaseModel

            class MyDocument(BaseModel):
                name: str
                value: int

            # Create backend instance
            backend = RegistryMindtraceODM()

            # Insert a document
            doc = MyDocument(name="test", value=42)
            doc_id = backend.insert(doc)
    """

    def __init__(
        self,
        backend: RegistryBackend | None = None,
        init_mode: InitMode | None = None,
        **kwargs,
    ):
        """Initialize the registry ODM backend.

        Args:
            backend (RegistryBackend | None): Optional registry backend to use for storage.
            init_mode (InitMode | None): Initialization mode. If None, defaults to InitMode.SYNC
                for Registry. Note: Registry is always synchronous and doesn't require initialization.
            **kwargs: Additional configuration parameters.
        """
        super().__init__(**kwargs)
        # Default to sync for Registry if not specified (Registry is sync by nature)
        if init_mode is None:
            init_mode = InitMode.SYNC
        # Store init_mode for consistency, though Registry doesn't use it
        self._init_mode = init_mode
        self.registry = Registry(backend=backend, version_objects=False)

    def is_async(self) -> bool:
        """Determine if this backend operates asynchronously.

        Returns:
            bool: Always returns False as this is a synchronous implementation.

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                print(backend.is_async())  # Output: False
        """
        return False

    def insert(self, obj: BaseModel) -> BaseModel:
        """Insert a new document into the database.

        Args:
            obj (BaseModel): The document object to insert.

        Returns:
            BaseModel: The inserted document with an 'id' attribute set.

        Example:
            .. code-block:: python

                from pydantic import BaseModel

                class MyDocument(BaseModel):
                    name: str

                backend = RegistryMindtraceODM()
                inserted_doc = backend.insert(MyDocument(name="example"))
                print(f"Inserted document with ID: {inserted_doc.id}")
        """
        unique_id = str(uuid.uuid1())
        self.registry[unique_id] = obj
        # Set id attribute on the document for consistency
        if not hasattr(obj, "id"):
            object.__setattr__(obj, "id", unique_id)
        return obj

    def update(self, id_or_obj, obj: BaseModel | None = None) -> BaseModel | bool:
        """Update an existing document in the database.

        Supports two calling conventions for backward compatibility:
        1. update(id: str, obj: BaseModel) -> bool  (legacy)
        2. update(obj: BaseModel) -> BaseModel      (new, matches abstract interface)

        Args:
            id_or_obj: Either a document ID (str) for legacy calls, or a BaseModel object (new style).
            obj: Optional BaseModel object (only used in legacy calls).

        Returns:
            BaseModel: The updated document (new style), or bool (legacy style: True if updated, False if not found).

        Raises:
            DocumentNotFoundError: If the document doesn't exist in the database
                or if the object doesn't have an 'id' attribute (new style only).

        Example:
            .. code-block:: python

                # Legacy style
                backend.update("some_id", updated_user)

                # New style (matches abstract interface)
                doc = backend.get("some_id")
                doc.name = "Updated Name"
                updated_doc = backend.update(doc)
        """
        # Legacy style: update(id: str, obj: BaseModel) -> bool
        if isinstance(id_or_obj, str) and obj is not None:
            doc_id = id_or_obj
            if doc_id not in self.registry:
                return False
            # Set id attribute on the document so it's available for future operations
            if not hasattr(obj, "id"):
                object.__setattr__(obj, "id", doc_id)
            self.registry[doc_id] = obj
            return True

        # New style: update(obj: BaseModel) -> BaseModel
        if isinstance(id_or_obj, BaseModel):
            obj = id_or_obj
            # Check if object has an id attribute
            if not hasattr(obj, "id") or not obj.id:
                raise DocumentNotFoundError("Document must have an 'id' attribute to be updated")

            doc_id = str(obj.id)
            if doc_id not in self.registry:
                raise DocumentNotFoundError(f"Object with id {doc_id} not found")

            self.registry[doc_id] = obj
            return obj

        raise TypeError("update() requires either (id: str, obj: BaseModel) or (obj: BaseModel)")

    def get(self, id: str) -> BaseModel:
        """Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            BaseModel: The retrieved document with an 'id' attribute set.

        Raises:
            KeyError: If the document with the given ID doesn't exist.

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                try:
                    document = backend.get("some_id")
                except KeyError:
                    print("Document not found")
        """
        doc = self.registry[id]
        # Set id attribute (Registry deserializes documents, so id is lost)
        object.__setattr__(doc, "id", id)
        return doc

    def delete(self, id: str):
        """Delete a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            KeyError: If the document with the given ID doesn't exist.

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                try:
                    backend.delete("some_id")
                except KeyError:
                    print("Document not found")
        """
        del self.registry[id]

    def all(self) -> list[BaseModel]:
        """Retrieve all documents from the collection.

        Returns:
            list[BaseModel]: List of all documents in the registry, each with an 'id' attribute set.

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                documents = backend.all()
                for doc in documents:
                    print(f"Document ID: {doc.id}")
        """
        # Use items() to get both ID and document, set id on each (Registry deserializes, so id is lost)
        results = []
        for doc_id, doc in self.registry.items():
            object.__setattr__(doc, "id", doc_id)
            results.append(doc)
        return results

    def find(self, *args, **kwargs) -> list[BaseModel]:
        """Find documents matching the specified criteria.

        Args:
            *args: Query conditions. Currently not supported in Registry backend.
            **kwargs: Field-value pairs to match against documents.

        Returns:
            list[BaseModel]: A list of documents matching the query criteria, each with an 'id' attribute set.
                If no criteria are provided, returns all documents.

        Example:
            .. code-block:: python

                # Find documents with specific field values
                users = backend.find(name="John", email="john@example.com")
                for user in users:
                    print(f"User ID: {user.id}")

                # Find all documents if no criteria specified
                all_docs = backend.find()
        """
        # Get all documents with their IDs (Registry deserializes, so we need to set id)
        all_docs_with_ids = []
        for doc_id, doc in self.registry.items():
            object.__setattr__(doc, "id", doc_id)
            all_docs_with_ids.append(doc)

        # If no criteria provided, return all documents
        if not args and not kwargs:
            return all_docs_with_ids

        # Filter documents based on kwargs (field-value pairs)
        if kwargs:
            results = []
            for doc in all_docs_with_ids:
                match = True
                for field, value in kwargs.items():
                    if not hasattr(doc, field) or getattr(doc, field) != value:
                        match = False
                        break
                if match:
                    results.append(doc)
            return results

        # If args are provided but not supported, return empty list
        # (Registry backend doesn't support complex query syntax)
        if args:
            self.logger.warning(
                "Registry backend does not support complex query syntax via *args. "
                "Use **kwargs for field-value matching instead."
            )

        # Return empty list if only args provided (without kwargs)
        return []

    def get_raw_model(self) -> Type[BaseModel]:
        """Get the raw document model class used by this backend.

        Returns:
            Type[BaseModel]: The base BaseModel class, as Registry backend
                doesn't use a specific model class but accepts any BaseModel.

        Example:
            .. code-block:: python

                model_class = backend.get_raw_model()
                print(f"Using model: {model_class.__name__}")  # Output: BaseModel
        """
        return BaseModel
