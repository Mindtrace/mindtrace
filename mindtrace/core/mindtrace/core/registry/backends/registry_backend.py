from abc import abstractmethod
from pathlib import Path
from typing import Any, List

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import MindtraceABC


class RegistryBackend(MindtraceABC):
    @property
    @abstractmethod
    def uri(self) -> Path:
        pass

    @abstractmethod
    def push(self, name: str, obj: Any, materializer: BaseMaterializer | None = None, version: str | None = None):
        """Upload a local object version to the remote backend.

        Args:
            name: Name of the object (e.g., "yolo8:x").
            obj: Object to upload.
            materializer: Materializer to use for the object.
            version: Version string (e.g., "1.0.0").
        """
        pass

    @abstractmethod
    def download(self, name: str, version: str, local_path: str):
        """Download a remote object version into a local path.

        Args:
            name: Name of the object.
            version: Version string.
            local_path: Local target directory to download into.
        """
        pass
    
    def pull(self, name: str, version: str, materializer: BaseMaterializer | None = None) -> Any:
        """Pull and load a remote object version into memory.

        This method is optional and not all backends may support it.

        Args:
            name: Name of the object.
            version: Version string.
            materializer: Materializer to use to instantiate the object.

        Raises:
            NotImplementedError: If the backend does not support pulling.
        """
        raise NotImplementedError("Pull is not implemented for this backend.")
    
    @abstractmethod
    def delete(self, name: str, version: str = "all"):
        """Delete an object version from the backend.

        Args:
            name: Name of the object.
            version: Version string.
        """
        pass

    @abstractmethod
    def save_metadata(self, name: str, version: str, metadata: dict):
        """Upload metadata for a specific object version.

        Args:
            name: Name of the object.
            version: Version string.
            metadata: Dictionary of object metadata.
        """
        pass

    @abstractmethod
    def fetch_metadata(self, name: str, version: str) -> dict:
        """Fetch metadata for a specific object version.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Metadata dictionary.
        """
        pass

    @abstractmethod
    def delete_metadata(self, model_name: str, version: str) -> dict:
        """Delete metadata for a specific model version.

        Args:
            model_name: Name of the model.
            version: Version string.

        Returns:
            Metadata dictionary.
        """
        pass

    @abstractmethod
    def list_objects(self) -> List[str]:
        """List all objects in the backend.

        Returns:
            List of object names.
        """
        pass

    @abstractmethod
    def list_versions(self, name: str) -> List[str]:
        """List all versions for an object in the backend.

        Args:
            name: Optional object name to filter results.

        Returns:
            List of versions for the given object.
        """
        pass

    @abstractmethod
    def has_object(self, name: str, version: str) -> bool:
        """Check if a specific object version exists in the backend.

        Args:
            model_name: Name of the model.
            version: Version string.

        Returns:
            True if the object version exists, False otherwise.
        """
        pass
    
    def validate_object_name(self, name: str) -> None:
        """Validate that the object name contains only allowed characters.

        This method is to be used by subclasses to validate object names, ensuring a unified naming convention is
        followed between all backends.

        Args:
            name: Name of the object to validate

        Raises:
            ValueError: If the object name contains invalid characters
        """
        if "_" in name:
            raise ValueError("Object names cannot contain underscores. Use colons (':') for namespacing.")
