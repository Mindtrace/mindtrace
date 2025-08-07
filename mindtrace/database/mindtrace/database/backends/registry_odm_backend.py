from pydantic import BaseModel
import uuid

from mindtrace.database import MindtraceODMBackend
from mindtrace.registry import Registry, RegistryBackend


class RegistryMindtraceODMBackend(MindtraceODMBackend):
    """Implementation of the Mindtrace ODM backend that uses the Registry backend.

    Pass in a RegistryBackend to select the storage source. By default, a local directory store will be used.
        
    Args:
        **kwargs: Additional configuration parameters (currently unused).
        
    Example:
        .. code-block:: python
        
            from mindtrace.database.backends.local_odm_backend import LocalMindtraceODMBackend
            
            # Create backend instance (for testing/development only)
            backend = RegistryMindtraceODMBackend()
            
            try:
                backend.insert(some_document)
            except NotImplementedError:
                print("Local backend does not support actual operations")
    """
    
    def __init__(self, backend: RegistryBackend | None = None, **kwargs):
        """Initialize the local ODM backend.
        
        Args:
            **kwargs: Additional configuration parameters (currently unused).
        """
        super().__init__(**kwargs)
        self.registry = Registry(backend=backend, version_objects=False)

    def is_async(self) -> bool:
        """Determine if this backend operates asynchronously.
        
        Returns:
            bool: Always returns False as this is a synchronous stub implementation.
            
        Example:
            .. code-block:: python
            
                backend = LocalMindtraceODMBackend()
                print(backend.is_async())  # Output: False
        """
        return False

    def insert(self, obj: BaseModel) -> str:
        """Insert a new document into the database.
        
        Args:
            obj (BaseModel): The document object to insert.
            
        Raises:
            NotImplementedError: Always raised as this backend doesn't support insert operations.

        Example:
            .. code-block:: python

                backend = LocalMindtraceODMBackend()
                try:
                    backend.insert(document)
                except NotImplementedError:
                    print("Insert not supported in local backend")
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
            
                backend = RegistryMindtraceODMBackend()
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
            
                backend = RegistryMindtraceODMBackend()
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
            
                backend = RegistryMindtraceODMBackend()
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
            
                backend = RegistryMindtraceODMBackend()
                documents = backend.all()
                print(f"Found {len(documents)} documents")
        """
        return self.registry.values()
