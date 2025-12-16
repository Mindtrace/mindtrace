import uuid
from typing import Type

from pydantic import BaseModel

from mindtrace.database.backends.mindtrace_odm import InitMode, MindtraceODM
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

    def insert(self, obj: BaseModel) -> str:
        """Insert a new document into the database.

        Args:
            obj (BaseModel): The document object to insert.

        Returns:
            str: The unique identifier assigned to the inserted document.

        Example:
            .. code-block:: python

                from pydantic import BaseModel

                class MyDocument(BaseModel):
                    name: str

                backend = RegistryMindtraceODM()
                doc_id = backend.insert(MyDocument(name="example"))
                print(f"Inserted document with ID: {doc_id}")
        """
        unique_id = str(uuid.uuid1())
        self.registry[unique_id] = obj
        return unique_id

    def update(self, id: str, obj: BaseModel) -> bool:
        """Update an existing document in the database.

        Args:
            id (str): The unique identifier of the document to update.
            obj (BaseModel): The updated document object.

        Returns:
            bool: True if the document was successfully updated, False if the document doesn't exist.

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                try:
                    success = backend.update("some_id", updated_document)
                    if success:
                        print("Document updated successfully")
                    else:
                        print("Document not found")
                except Exception as e:
                    print(f"Update failed: {e}")
        """
        if id in self.registry:
            self.registry[id] = obj
            return True
        return False

    def get(self, id: str) -> BaseModel:
        """Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            BaseModel: The retrieved document.

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
        return self.registry[id]

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
            list[BaseModel]: List of all documents in the registry.

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                documents = backend.all()
                print(f"Found {len(documents)} documents")
        """
        return list(self.registry.values())

    def find(self, *args, **kwargs) -> list[BaseModel]:
        """Find documents matching the specified criteria.

        Args:
            *args: Query conditions. Currently not supported in Registry backend.
            **kwargs: Field-value pairs to match against documents.

        Returns:
            list[BaseModel]: A list of documents matching the query criteria.
                If no criteria are provided, returns all documents.

        Example:
            .. code-block:: python

                # Find documents with specific field values
                users = backend.find(name="John", email="john@example.com")

                # Find all documents if no criteria specified
                all_docs = backend.find()
        """
        all_docs = list(self.registry.values())

        # If no criteria provided, return all documents
        if not args and not kwargs:
            return all_docs

        # Filter documents based on kwargs (field-value pairs)
        if kwargs:
            results = []
            for doc in all_docs:
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
