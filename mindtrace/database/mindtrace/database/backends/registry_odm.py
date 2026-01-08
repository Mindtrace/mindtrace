import uuid
from typing import Dict, Optional, Type

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
        model_cls: Optional[Type[BaseModel]] = None,
        models: Optional[Dict[str, Type[BaseModel]]] = None,
        backend: RegistryBackend | None = None,
        init_mode: InitMode | None = None,
        **kwargs,
    ):
        """Initialize the registry ODM backend.

        Args:
            model_cls (Type[BaseModel], optional): The document model class to use for operations (single model mode).
            models (Dict[str, Type[BaseModel]], optional): Dictionary of model names to model classes (multi-model mode).
                Example: {'user': User, 'address': Address}. When provided, access models via db.user, db.address, etc.
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
        self._model_odms: Dict[str, "RegistryMindtraceODM"] = {}

        # Support both single model and multi-model modes
        if models is not None:
            # Multi-model mode
            if model_cls is not None:
                raise ValueError("Cannot specify both model_cls and models. Use one or the other.")
            if not isinstance(models, dict) or len(models) == 0:
                raise ValueError("models must be a non-empty dictionary")
            self._models = models
            self.model_cls = None  # No single model in multi-model mode
            # Create ODM instances for each model (they share the same registry)
            for name, model in models.items():
                odm = RegistryMindtraceODM(
                    model_cls=model,
                    backend=backend,
                    init_mode=init_mode,
                    **kwargs,
                )
                # Share the same registry instance
                odm.registry = self.registry
                self._model_odms[name] = odm
        elif model_cls is not None:
            # Single model mode (backward compatible)
            self.model_cls = model_cls
            self._models = None
        else:
            # No model specified - Registry can work without a specific model
            self.model_cls = None
            self._models = None

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

    def __getattr__(self, name: str):
        """Support attribute-based access to model-specific ODMs in multi-model mode.

        Example:
            db = RegistryMindtraceODM(models={'user': User, 'address': Address}, ...)
            db.user.get(user_id)
            db.address.insert(address)
        """
        if self._models is not None and name in self._model_odms:
            return self._model_odms[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def insert(self, obj: BaseModel) -> BaseModel:
        """Insert a new document into the database.

        Args:
            obj (BaseModel): The document object to insert.

        Returns:
            BaseModel: The inserted document with an 'id' attribute set.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.insert() instead).

        Example:
            .. code-block:: python

                from pydantic import BaseModel

                class MyDocument(BaseModel):
                    name: str

                backend = RegistryMindtraceODM()
                inserted_doc = backend.insert(MyDocument(name="example"))
                print(f"Inserted document with ID: {inserted_doc.id}")
        """
        if self._models is not None:
            raise ValueError("Cannot use insert() in multi-model mode. Use db.model_name.insert() instead.")
        unique_id = str(uuid.uuid1())
        self.registry[unique_id] = obj
        # Set id attribute on the document for consistency
        if not hasattr(obj, "id"):
            object.__setattr__(obj, "id", unique_id)
        return obj

    def update(self, obj: BaseModel) -> BaseModel:
        """Update an existing document in the database.

        The document object should have been retrieved from the database,
        modified, and then passed to this method to save the changes.

        Args:
            obj (BaseModel): The document object with modified fields to save.

        Returns:
            BaseModel: The updated document.

        Raises:
            DocumentNotFoundError: If the document doesn't exist in the database
                or if the object doesn't have an 'id' attribute.
            ValueError: If in multi-model mode (use db.model_name.update() instead).

        Example:
            .. code-block:: python

                # Get the document
                doc = backend.get("some_id")
                # Modify it
                doc.name = "Updated Name"
                # Save the changes
                updated_doc = backend.update(doc)
        """
        if self._models is not None:
            raise ValueError("Cannot use update() in multi-model mode. Use db.model_name.update() instead.")

        # Check if object has an id attribute
        if not hasattr(obj, "id") or not obj.id:
            raise DocumentNotFoundError("Document must have an 'id' attribute to be updated")

        doc_id = str(obj.id)
        if doc_id not in self.registry:
            raise DocumentNotFoundError(f"Object with id {doc_id} not found")

        self.registry[doc_id] = obj
        return obj

    def get(self, id: str, fetch_links: bool = False) -> BaseModel:
        """Retrieve a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to retrieve.
            fetch_links (bool): Ignored for Registry backend (kept for API consistency). Defaults to False.

        Returns:
            BaseModel: The retrieved document with an 'id' attribute set.

        Raises:
            DocumentNotFoundError: If the document with the given ID doesn't exist.
            ValueError: If in multi-model mode (use db.model_name.get() instead).

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                try:
                    document = backend.get("some_id")
                except DocumentNotFoundError:
                    print("Document not found")
        """
        if self._models is not None:
            raise ValueError("Cannot use get() in multi-model mode. Use db.model_name.get() instead.")
        try:
            doc = self.registry[id]
            # Set id attribute (Registry deserializes documents, so id is lost)
            object.__setattr__(doc, "id", id)
            return doc
        except KeyError:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    def delete(self, id: str):
        """Delete a document by its unique identifier.

        Args:
            id (str): The unique identifier of the document to delete.

        Raises:
            DocumentNotFoundError: If the document with the given ID doesn't exist.
            ValueError: If in multi-model mode (use db.model_name.delete() instead).

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                try:
                    backend.delete("some_id")
                except DocumentNotFoundError:
                    print("Document not found")
        """
        if self._models is not None:
            raise ValueError("Cannot use delete() in multi-model mode. Use db.model_name.delete() instead.")
        try:
            del self.registry[id]
        except KeyError:
            raise DocumentNotFoundError(f"Object with id {id} not found")

    def all(self) -> list[BaseModel]:
        """Retrieve all documents from the collection.

        Returns:
            list[BaseModel]: List of all documents in the registry, each with an 'id' attribute set.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.all() instead).

        Example:
            .. code-block:: python

                backend = RegistryMindtraceODM()
                documents = backend.all()
                for doc in documents:
                    print(f"Document ID: {doc.id}")
        """
        if self._models is not None:
            raise ValueError("Cannot use all() in multi-model mode. Use db.model_name.all() instead.")
        # Use items() to get both ID and document, set id on each (Registry deserializes, so id is lost)
        results = []
        for doc_id, doc in self.registry.items():
            object.__setattr__(doc, "id", doc_id)
            results.append(doc)
        return results

    def find(self, *args, fetch_links: bool = False, **kwargs) -> list[BaseModel]:
        """Find documents matching the specified criteria.

        Args:
            *args: Query conditions. Currently not supported in Registry backend.
            fetch_links (bool): Ignored for Registry backend (kept for API consistency). Defaults to False.
            **kwargs: Field-value pairs to match against documents.

        Returns:
            list[BaseModel]: A list of documents matching the query criteria, each with an 'id' attribute set.
                If no criteria are provided, returns all documents.

        Raises:
            ValueError: If in multi-model mode (use db.model_name.find() instead).

        Example:
            .. code-block:: python

                # Find documents with specific field values
                users = backend.find(name="John", email="john@example.com")
                for user in users:
                    print(f"User ID: {user.id}")

                # Find all documents if no criteria specified
                all_docs = backend.find()
        """
        if self._models is not None:
            raise ValueError("Cannot use find() in multi-model mode. Use db.model_name.find() instead.")

        # Get all documents with their IDs (Registry deserializes, so we need to set id)
        all_docs_with_ids = []
        for doc_id, doc in self.registry.items():
            object.__setattr__(doc, "id", doc_id)
            all_docs_with_ids.append(doc)

        # If no criteria provided, return all documents
        if not args and not kwargs:
            return all_docs_with_ids

        # Filter documents based on kwargs (field-value pairs)
        # Remove fetch_links from kwargs if present
        kwargs_without_fetch_links = {k: v for k, v in kwargs.items() if k != "fetch_links"}

        if kwargs_without_fetch_links:
            results = []
            for doc in all_docs_with_ids:
                match = True
                for field, value in kwargs_without_fetch_links.items():
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
            Type[BaseModel]: The model class (if single model mode) or BaseModel (if no model specified).

        Raises:
            ValueError: If in multi-model mode (use db.model_name.get_raw_model() instead).

        Example:
            .. code-block:: python

                model_class = backend.get_raw_model()
                print(f"Using model: {model_class.__name__}")
        """
        if self._models is not None:
            raise ValueError(
                "Cannot use get_raw_model() in multi-model mode. Use db.model_name.get_raw_model() instead."
            )
        return self.model_cls if self.model_cls is not None else BaseModel
