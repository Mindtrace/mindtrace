from pydantic import BaseModel

from mindtrace.database.backends.mindtrace_odm_backend import MindtraceODMBackend


class LocalMindtraceODMBackend(MindtraceODMBackend):
    """
    Local implementation of the Mindtrace ODM backend for placeholder/testing purposes.
    
    This backend is designed as a stub implementation and does not provide actual
    data persistence functionality. All operations raise NotImplementedError to
    indicate that this backend is not meant for production use.
    
    Args:
        **kwargs: Additional configuration parameters (currently unused).
        
    Example:
        .. code-block:: python
        
            from mindtrace.database.backends.local_odm_backend import LocalMindtraceODMBackend
            
            # Create backend instance (for testing/development only)
            backend = LocalMindtraceODMBackend()
            
            # All operations will raise NotImplementedError
            try:
                backend.insert(some_document)
            except NotImplementedError:
                print("Local backend does not support actual operations")
    """
    
    def __init__(self, **kwargs):
        """
        Initialize the local ODM backend.
        
        Args:
            **kwargs: Additional configuration parameters (currently unused).
        """
        super().__init__(**kwargs)

    def is_async(self) -> bool:
        """
        Determine if this backend operates asynchronously.
        
        Returns:
            bool: Always returns False as this is a synchronous stub implementation.
            
        Example:
            .. code-block:: python
            
                backend = LocalMindtraceODMBackend()
                print(backend.is_async())  # Output: False
        """
        return False

    def insert(self, obj: BaseModel):
        """
        Insert a new document into the database.
        
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
        raise NotImplementedError("LocalMindtraceODMBackend does not support insert")

    def get(self, id: str) -> BaseModel:
        """
        Retrieve a document by its unique identifier.
        
        Args:
            id (str): The unique identifier of the document to retrieve.
            
        Returns:
            BaseModel: This method never returns as it always raises NotImplementedError.
            
        Raises:
            NotImplementedError: Always raised as this backend doesn't support get operations.
            
        Example:
            .. code-block:: python
            
                backend = LocalMindtraceODMBackend()
                try:
                    document = backend.get("some_id")
                except NotImplementedError:
                    print("Get not supported in local backend")
        """
        raise NotImplementedError("LocalMindtraceODMBackend does not support get")

    def delete(self, id: str):
        """
        Delete a document by its unique identifier.
        
        Args:
            id (str): The unique identifier of the document to delete.
            
        Raises:
            NotImplementedError: Always raised as this backend doesn't support delete operations.
            
        Example:
            .. code-block:: python
            
                backend = LocalMindtraceODMBackend()
                try:
                    backend.delete("some_id")
                except NotImplementedError:
                    print("Delete not supported in local backend")
        """
        raise NotImplementedError("LocalMindtraceODMBackend does not support delete")

    def all(self) -> list[BaseModel]:
        """
        Retrieve all documents from the collection.
        
        Returns:
            list[BaseModel]: This method never returns as it always raises NotImplementedError.
            
        Raises:
            NotImplementedError: Always raised as this backend doesn't support all operations.
            
        Example:
            .. code-block:: python
            
                backend = LocalMindtraceODMBackend()
                try:
                    documents = backend.all()
                except NotImplementedError:
                    print("All not supported in local backend")
        """
        raise NotImplementedError("LocalMindtraceODMBackend does not support all")
