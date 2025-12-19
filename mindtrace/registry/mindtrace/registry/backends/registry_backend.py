from abc import abstractmethod
from pathlib import Path
from typing import Dict, List

from mindtrace.core import MindtraceABC


class RegistryBackend(MindtraceABC):  # pragma: no cover
    @property
    @abstractmethod
    def uri(self) -> Path:
        pass

    @abstractmethod
    def __init__(self, uri: str | Path, **kwargs):
        super().__init__(**kwargs)

    @abstractmethod
    def push(self, name: str, version: str, local_path: str | Path):
        """Upload a local object version to the remote backend.

        Args:
            name: Name of the object (e.g., "yolo8:x").
            version: Version string (e.g., "1.0.0").
            local_path: Local source directory to upload from.
        """
        pass

    @abstractmethod
    def pull(self, name: str, version: str, local_path: str | Path):
        """Download a remote object version into a local path.

        Args:
            name: Name of the object.
            version: Version string.
            local_path: Local target directory to download into.
        """
        pass

    @abstractmethod
    def delete(self, name: str, version: str):
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
    def delete_metadata(self, name: str, version: str):
        """Delete metadata for a specific model version.

        Args:
            name: Name of the model.
            version: Version string.
        """
        pass

    @abstractmethod
    def save_registry_metadata(self, metadata: dict):
        """Save registry-level metadata to the backend.

        This method saves metadata that applies to the entire registry (e.g., version_objects setting,
        materializers registry). This is distinct from object-level metadata which is stored per object version.

        Args:
            metadata: Dictionary containing registry metadata to save. Should include keys like
                "version_objects" and "materializers".
        """
        pass

    @abstractmethod
    def fetch_registry_metadata(self) -> dict:
        """Fetch registry-level metadata from the backend.

        This method retrieves metadata that applies to the entire registry (e.g., version_objects setting,
        materializers registry). This is distinct from object-level metadata which is stored per object version.

        Returns:
            Dictionary containing registry metadata. Should include keys like "version_objects" and
            "materializers". Returns empty dict if no metadata exists.
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
            name: Name of the object.
            version: Version string.

        Returns:
            True if the object version exists, False otherwise.
        """
        pass

    @abstractmethod
    def register_materializer(self, object_class: str, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        pass

    def register_materializers_batch(self, materializers: Dict[str, str]):
        """Register multiple materializers in a single operation for better performance.

        Default implementation loops through and calls register_materializer for each. Subclasses can override this
        method to provide optimized batch operations.

        Args:
            materializers: Dictionary mapping object classes to materializer classes.
        """
        for object_class, materializer_class in materializers.items():
            self.register_materializer(object_class, materializer_class)

    @abstractmethod
    def registered_materializer(self, object_class: str) -> str | None:
        """Get the registered materializer for an object class.

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        pass

    @abstractmethod
    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
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
        if not name or not name.strip():
            raise ValueError("Object names cannot be empty.")
        elif "_" in name:
            raise ValueError("Object names cannot contain underscores. Use colons (':') for namespacing.")
        elif "@" in name:
            raise ValueError("Object names cannot contain '@'.")

    @abstractmethod
    def acquire_lock(self, key: str, lock_id: str, timeout: int, shared: bool = False) -> bool:
        """Atomically acquire a lock for the given key.

        This method should be implemented to provide atomic lock acquisition. The implementation should ensure that
        only one client can acquire an exclusive lock at a time, or multiple clients can acquire a shared lock,
        even in a distributed environment.

        Args:
            key: The key to lock
            lock_id: Unique identifier for this lock attempt
            timeout: Lock timeout in seconds
            shared: Whether to acquire a shared (read) lock. If False, acquires an exclusive (write) lock.

        Returns:
            True if lock was acquired, False otherwise
        """
        pass

    @abstractmethod
    def release_lock(self, key: str, lock_id: str) -> bool:
        """Atomically release a lock for the given key.

        This method should be implemented to provide atomic lock release. The implementation should ensure that only
        the lock owner can release it.

        Args:
            key: The key to unlock
            lock_id: The lock ID that was used to acquire the lock

        Returns:
            True if lock was released, False otherwise
        """
        pass

    @abstractmethod
    def check_lock(self, key: str) -> tuple[bool, str | None]:
        """Check if a key is currently locked.

        Args:
            key: The key to check

        Returns:
            Tuple of (is_locked, lock_id). If locked, lock_id will be the current lock holder's ID. If not locked,
            lock_id will be None.
        """
        pass

    @abstractmethod
    def overwrite(self, source_name: str, source_version: str, target_name: str, target_version: str):
        """Overwrite an object.

        This method should support saving objects to a temporary source location first, and then moving it to a target
        object in a single atomic operation.

        After the overwrite method completes, the source object should be deleted, and the target object should be
        updated to be the new source version.

        Args:
            source_name: Name of the source object.
            source_version: Version of the source object.
            target_name: Name of the target object.
            target_version: Version of the target object.
        """
        pass
