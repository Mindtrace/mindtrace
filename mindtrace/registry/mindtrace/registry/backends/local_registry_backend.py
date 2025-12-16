import json
import os
import platform
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List

import yaml

# Import appropriate locking mechanism based on OS
if platform.system() == "Windows":
    import msvcrt

    fcntl = None
else:
    import fcntl

    msvcrt = None

from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.exceptions import LockAcquisitionError


class LocalRegistryBackend(RegistryBackend):
    """A simple local filesystem-based registry backend.

    All object directories and registry files are stored under a configurable base directory. The backend provides
    methods for uploading, downloading, and managing object files and metadata.
    """

    def __init__(self, uri: str | Path, **kwargs):
        """Initialize the LocalRegistryBackend.

        Args:
            uri (str | Path): The base directory path where all object files and metadata will be stored.
                              Supports "file://" URI scheme which will be automatically stripped.
            **kwargs: Additional keyword arguments for the RegistryBackend.
        """
        if isinstance(uri, str) and uri.startswith("file://"):
            uri = uri[len("file://") :]
        super().__init__(uri=uri, **kwargs)
        self._uri = Path(uri).expanduser().resolve()
        self._uri.mkdir(parents=True, exist_ok=True)
        self._metadata_path = self._uri / "registry_metadata.json"
        self.logger.debug(f"Initializing LocalBackend with uri: {self._uri}")

    @property
    def uri(self) -> Path:
        """The resolved base directory path for the backend."""
        return self._uri

    @property
    def metadata_path(self) -> Path:
        """The resolved metadata file path for the backend."""
        return self._metadata_path

    def _full_path(self, remote_key: str) -> Path:
        """Convert a remote key to a full filesystem path.

        Args:
            remote_key (str): The remote key (relative path) to resolve.

        Returns:
            Path: The full resolved filesystem path.
        """
        return self.uri / remote_key

    def _object_key(self, name: str, version: str) -> str:
        """Convert object name and version to a storage key.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Storage key for the object version.
        """
        return f"{name}/{version}"

    def _object_metadata_path(self, name: str, version: str) -> Path:
        """Generate the metadata file path for an object version.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Metadata file path (e.g., Path("_meta_object_name@1.0.0.yaml")).
        """
        return self.uri / f"_meta_{name.replace(':', '_')}@{version}.yaml"

    def _object_metadata_prefix(self, name: str) -> str:
        """Generate the metadata file prefix for listing versions of an object.

        Args:
            name: Name of the object.

        Returns:
            Metadata file prefix (e.g., "_meta_object_name@").
        """
        return f"_meta_{name.replace(':', '_')}@"

    def push(self, name: str, version: str, local_path: str | Path):
        """Upload a local directory to the remote backend.

        Args:
            name: Name of the object.
            version: Version string.
            local_path: Path to the local directory to upload.
        """
        self.validate_object_name(name)
        dst = self._full_path(self._object_key(name, version))
        self.logger.debug(f"Uploading directory from {local_path} to {dst}")
        shutil.copytree(local_path, dst, dirs_exist_ok=True)
        self.logger.debug(f"Upload complete. Contents: {list(dst.rglob('*'))}")

    def pull(self, name: str, version: str, local_path: str | Path):
        """Copy a directory from the backend store to a local path.

        Args:
            name: Name of the object.
            version: Version string.
            local_path: Destination directory path to copy to.
        """
        src = self._full_path(self._object_key(name, version))
        self.logger.debug(f"Downloading directory from {src} to {local_path}")
        shutil.copytree(src, local_path, dirs_exist_ok=True)
        self.logger.debug(f"Download complete. Contents: {list(Path(local_path).rglob('*'))}")

    def delete(self, name: str, version: str):
        """Delete a directory from the backend store.

        Also removes empty parent directories.

        Args:
            name: Name of the object.
            version: Version string.
        """
        target = self._full_path(self._object_key(name, version))
        self.logger.debug(f"Deleting directory: {target}")
        shutil.rmtree(target, ignore_errors=True)

        # Cleanup parent if empty
        parent = target.parent

        # Use a lock file for the parent directory
        lock_path = self._lock_path(f"{name}@parent")
        with open(lock_path, "w") as f:
            if self._acquire_file_lock(f):
                try:
                    if parent.exists() and not any(parent.iterdir()):
                        self.logger.debug(f"Removing empty parent directory: {parent}")
                        try:
                            parent.rmdir()
                        except Exception as e:
                            if parent.exists():
                                self.logger.error(f"Error deleting parent directory: {e}")
                                raise
                finally:
                    self._release_file_lock(f)

    def save_metadata(self, name: str, version: str, metadata: dict):
        """Save metadata for a object version.

        Args:
            name: Name of the object.
            version: Version of the object.
            metadata: Metadata to save.
        """
        self.validate_object_name(name)
        meta_path = self._object_metadata_path(name, version)
        self.logger.debug(f"Saving metadata to {meta_path}: {metadata}")

        # Use atomic write: write to temp file with unique name, then rename
        temp_path = meta_path.parent / f".tmp_{uuid.uuid4().hex}_{meta_path.name}"
        try:
            with open(temp_path, "w") as f:
                yaml.safe_dump(metadata, f)
                f.flush()
                os.fsync(f.fileno())

            # rename is atomic on POSIX systems if source and dest are on same filesystem
            temp_path.rename(meta_path)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise

    def fetch_metadata(self, name: str, version: str) -> dict:
        """Load metadata for a object version.

        Args:
            name: Name of the object.
            version: Version of the object.

        Returns:
            dict: The loaded metadata.

        Raises:
            ValueError: If the metadata file is empty or corrupted.
        """
        meta_path = self._object_metadata_path(name, version)
        self.logger.debug(f"Loading metadata from: {meta_path}")
        with open(meta_path, "r") as f:
            metadata = yaml.safe_load(f)

        # Handle case where yaml.safe_load returns None (empty file or whitespace only)
        if metadata is None:
            raise ValueError(
                f"Metadata file for {name}@{version} is empty or corrupted. "
                f"This may indicate a race condition during concurrent writes."
            )

        # Add the path to the object directory to the metadata:
        object_key = self._object_key(name, version)
        object_path = self._full_path(object_key)
        metadata.update({"path": str(object_path)})

        self.logger.debug(f"Loaded metadata: {metadata}")
        return metadata

    def delete_metadata(self, name: str, version: str):
        """Delete metadata for a object version.

        Args:
            name: Name of the object.
            version: Version of the object.
        """
        meta_path = self._object_metadata_path(name, version)
        self.logger.debug(f"Deleting metadata file: {meta_path}")
        if meta_path.exists():
            meta_path.unlink()

    def list_objects(self) -> List[str]:
        """List all objects in the backend.

        Returns:
            List of object names sorted alphabetically.
        """
        objects = set()
        # Look for metadata files that follow the pattern _meta_objectname@version.yaml
        for meta_file in self.uri.glob("_meta_*.yaml"):
            # Extract the object name from the metadata filename
            # Remove '_meta_' prefix and split at '@' to get the object name part
            name_part = meta_file.stem.split("@")[0].replace("_meta_", "")
            # Convert back from filesystem-safe format to original object name
            name = name_part.replace("_", ":")
            objects.add(name)

        return sorted(list(objects))

    def list_versions(self, name: str) -> List[str]:
        """List all versions available for the given object.

        Args:
            name: Name of the object

        Returns:
            Sorted list of version strings available for the object
        """
        # Build the prefix used in metadata filenames for this object.
        prefix = self._object_metadata_prefix(name)
        versions = []

        # Search for metadata files matching the prefix pattern in the base directory.
        for meta_file in self.uri.glob(f"{prefix}*.yaml"):
            # Extract the version from the filename by removing the prefix and the '.yaml' extension.
            version = meta_file.name[len(prefix) : -5]
            versions.append(version)
        return sorted(versions)

    def has_object(self, name: str, version: str) -> bool:
        """Check if a specific object version exists in the backend.

        This method uses direct existence checks instead of listing all objects
        for better performance, especially with large registries.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            True if the object version exists, False otherwise.
        """
        # Check if metadata file exists directly (much faster than listing all objects)
        meta_path = self._object_metadata_path(name, version)
        return meta_path.exists()

    def register_materializer(self, object_class: str, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        try:
            if not self._metadata_path.exists():
                metadata = {"materializers": {}}
            else:
                with open(self._metadata_path, "r") as f:
                    metadata = json.load(f)
            metadata["materializers"][object_class] = materializer_class
            with open(self._metadata_path, "w") as f:
                json.dump(metadata, f)
        except Exception as e:
            self.logger.error(f"Error registering materializer for {object_class}: {e}")
            raise e
        else:
            self.logger.debug(f"Registered materializer for {object_class}: {materializer_class}")

    def registered_materializer(self, object_class: str) -> str | None:
        """Get the registered materializer for an object class.

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        return self.registered_materializers().get(object_class, None)

    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
        """
        try:
            if not self._metadata_path.exists():
                return {}
            with open(self._metadata_path, "r") as f:
                materializers = json.load(f).get("materializers", {})
        except Exception as e:
            self.logger.error(f"Error loading materializers: {e}")
            raise e
        return materializers

    def save_registry_metadata(self, metadata: dict):
        """Save registry-level metadata to the backend.

        Args:
            metadata: Dictionary containing registry metadata to save.
        """
        try:
            with open(self._metadata_path, "w") as f:
                json.dump(metadata, f)
        except Exception as e:
            self.logger.error(f"Error saving registry metadata: {e}")
            raise e

    def fetch_registry_metadata(self) -> dict:
        """Fetch registry-level metadata from the backend.

        Returns:
            Dictionary containing registry metadata. Returns empty dict if no metadata exists.
        """
        try:
            if not self._metadata_path.exists():
                return {}
            with open(self._metadata_path, "r") as f:
                return json.load(f)
        except Exception as e:
            self.logger.debug(f"Could not load registry metadata: {e}")
            return {}

    def _lock_path(self, key: str) -> Path:
        """Get the path for a lock file."""
        return self._full_path(f"_lock_{key}")

    def _get_key_from_path(self, lock_path: Path) -> str:
        """Extract the key from a lock file path."""
        # Remove the _lock_ prefix and convert back to original key
        key_part = lock_path.name.replace("_lock_", "")
        return key_part

    def _acquire_file_lock(self, file_obj) -> bool:
        """Acquire a file lock using the appropriate mechanism for the OS."""
        try:
            if platform.system() == "Windows":
                # Windows: Try to lock the file using msvcrt
                assert msvcrt is not None, "Platform is Windows but msvcrt is not available"
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            else:
                # Unix: Try to acquire an exclusive file lock
                assert fcntl is not None, "Platform is not Windows but fcntl is not available"
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
        except (IOError, OSError):
            return False

    def _release_file_lock(self, file_obj) -> None:
        """Release a file lock using the appropriate mechanism for the OS."""
        try:
            if platform.system() == "Windows":
                # Windows: Unlock the file
                assert msvcrt is not None, "Platform is Windows but msvcrt is not available"
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                # Unix: Release the file lock
                assert fcntl is not None, "Platform is not Windows but fcntl is not available"
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError) as e:
            self.logger.warning(f"Error releasing file lock: {e}")

    def _acquire_shared_lock(self, file_obj) -> bool:
        """Acquire a shared (read) lock using the appropriate mechanism for the OS."""
        try:
            if platform.system() == "Windows":
                # Windows: Try to lock the file using msvcrt
                assert msvcrt is not None, "Platform is Windows but msvcrt is not available"
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            else:
                # Unix: Try to acquire a shared file lock
                # Use blocking mode for shared locks since multiple readers should be able to share
                assert fcntl is not None, "Platform is not Windows but fcntl is not available"
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_SH)
                return True
        except (IOError, OSError):
            return False

    def acquire_lock(self, key: str, lock_id: str, timeout: int, shared: bool = False) -> bool:
        """Acquire a lock using atomic file operations.

        Uses atomic file creation with O_EXCL to ensure only one process can create the lock file.
        The lock file contains both the lock_id and expiration time in JSON format.

        Args:
            key: The key to acquire the lock for.
            lock_id: The ID of the lock to acquire.
            timeout: The timeout in seconds for the lock.
            shared: Whether to acquire a shared (read) lock. If False, acquires an exclusive (write) lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        lock_path = self._lock_path(key)

        try:
            # Ensure parent directory exists
            lock_path.parent.mkdir(parents=True, exist_ok=True)

            # Try atomic file creation first - only one process can create the file
            try:
                # Use O_EXCL flag to ensure atomic creation
                if platform.system() == "Windows":
                    # Windows: Use exclusive creation
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                else:
                    # Unix: Use O_EXCL for atomic creation
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)

                # File created successfully - we have the lock
                with os.fdopen(fd, "r+") as f:
                    # Write our lock information
                    metadata = {"lock_id": lock_id, "expires_at": time.time() + timeout, "shared": shared}
                    f.write(json.dumps(metadata))
                    f.flush()
                    os.fsync(fd)  # Ensure data is written to disk
                    return True

            except FileExistsError:
                # File already exists - try to acquire existing lock
                if not self._acquire_existing_lock(lock_path, lock_id, timeout, shared):
                    raise LockAcquisitionError(f"Lock {key} is currently in use")
                return True

        except LockAcquisitionError:
            # Re-raise LockAcquisitionError
            raise
        except Exception as e:
            self.logger.error(f"Error acquiring {'shared ' if shared else ''}lock for {key}: {e}")
            return False

    def _acquire_existing_lock(self, lock_path: Path, lock_id: str, timeout: int, shared: bool = False) -> bool:
        """Acquire a lock on an existing lock file.

        This method handles the case where the lock file already exists and we need to
        check if the existing lock is expired and potentially acquire it.

        Args:
            lock_path: Path to the lock file.
            lock_id: The ID of the lock to acquire.
            timeout: The timeout in seconds for the lock.
            shared: Whether to acquire a shared (read) lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        try:
            # Check if lock file exists and read current lock info
            if not lock_path.exists():
                return False

            try:
                with open(lock_path, "r") as f:
                    content = f.read().strip()
                    if not content:
                        return False
                    metadata = json.loads(content)
            except (json.JSONDecodeError, IOError):
                # Corrupted lock file - remove it and retry
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                return False

            # Check if existing lock is expired
            if time.time() > metadata.get("expires_at", 0):
                # Lock is expired - remove it and retry acquisition
                lock_path.unlink()

                # Retry acquisition with the original key
                return self.acquire_lock(self._get_key_from_path(lock_path), lock_id, timeout, shared)

            # Lock is still valid - check if we can acquire it
            existing_shared = metadata.get("shared", False)

            if shared:
                # For shared locks, we can acquire if existing lock is also shared
                if existing_shared:
                    return True
                else:
                    return False
            else:
                # For exclusive locks, we can only acquire if no lock exists
                return False

        except Exception as e:
            self.logger.error(f"Error acquiring existing lock for {lock_path}: {e}")
            return False

    def release_lock(self, key: str, lock_id: str) -> bool:
        """Release a lock by verifying ownership and removing the file.

        Uses platform-specific file locking to ensure atomic operations during release.

        Args:
            key: The key to release the lock for.
            lock_id: The ID of the lock to release.

        Returns:
            True if the lock was released, False otherwise.
        """
        lock_path = self._lock_path(key)

        try:
            if not lock_path.exists():
                return True

            with open(lock_path, "r+") as f:
                # Try to acquire an exclusive file lock
                if not self._acquire_file_lock(f):
                    return False

                try:
                    # Verify lock ownership
                    try:
                        metadata = json.loads(f.read().strip())
                        if metadata.get("lock_id") != lock_id:
                            self._release_file_lock(f)  # Release lock if not ours
                            return False
                    except (json.JSONDecodeError, IOError):
                        self._release_file_lock(f)  # Release lock on error
                        return False

                    # Remove the lock file - use unlink with missing_ok=True to handle race conditions
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        # File was already deleted by another thread, which is fine
                        pass
                    return True

                except Exception as e:
                    self._release_file_lock(f)  # Release lock on any other error
                    self.logger.error(f"Error releasing lock for {key}: {e}")
                    return False

        except Exception as e:
            self.logger.error(f"Error releasing lock for {key}: {e}")
            return False

    def check_lock(self, key: str) -> tuple[bool, str | None]:
        """Check if a key is currently locked.

        Uses platform-specific file locking to ensure atomic read operations.

        Args:
            key: The key to check the lock for.

        Returns:
            Tuple containing a boolean indicating if the key is locked and the lock ID if it is, or None if it is not.
        """
        lock_path = self._lock_path(key)

        try:
            if not lock_path.exists():
                return False, None

            with open(lock_path, "r") as f:
                # Try to acquire a shared file lock
                if not self._acquire_shared_lock(f):
                    # File is locked by someone else
                    return True, None

                try:
                    # Check if lock is expired
                    try:
                        metadata = json.loads(f.read().strip())
                        if time.time() > metadata.get("expires_at", 0):
                            return False, None
                        return True, metadata.get("lock_id")
                    except (json.JSONDecodeError, IOError):
                        return False, None

                finally:
                    self._release_file_lock(f)

        except Exception as e:
            self.logger.error(f"Error checking lock for {key}: {e}")
            return False, None

    def overwrite(self, source_name: str, source_version: str, target_name: str, target_version: str):
        """Overwrite an object.

        This method supports saving objects to a temporary source location first, and then moving it to a target
        object in a single atomic operation.

        After the overwrite method completes, the source object should be deleted, and the target object should be
        updated to be the new source version.

        Args:
            source_name: Name of the source object.
            source_version: Version of the source object.
            target_name: Name of the target object.
            target_version: Version of the target object.
        """
        # Get the source and target paths
        source_path = self._full_path(self._object_key(source_name, source_version))
        target_path = self._full_path(self._object_key(target_name, target_version))

        # Get the source and target metadata paths
        source_meta_path = self._object_metadata_path(source_name, source_version)
        target_meta_path = self._object_metadata_path(target_name, target_version)

        self.logger.debug(f"Overwriting {target_name}@{target_version} with {source_name}@{source_version}")

        try:
            # If target exists, delete it first
            if target_path.exists():
                shutil.rmtree(target_path)
            if target_meta_path.exists():
                target_meta_path.unlink()

            # Move source to target using atomic rename
            source_path.rename(target_path)

            # Move metadata file
            if source_meta_path.exists():
                source_meta_path.rename(target_meta_path)

            # Update metadata to reflect new name/version
            if target_meta_path.exists():
                with open(target_meta_path, "r") as f:
                    metadata = yaml.safe_load(f)

                # Update the path in metadata
                metadata["path"] = str(target_path)

                with open(target_meta_path, "w") as f:
                    yaml.dump(metadata, f)

            self.logger.debug(f"Successfully overwrote {target_name}@{target_version}")

        except Exception as e:
            self.logger.error(f"Error during overwrite operation: {e}")
            # Cleanup any partial state
            if target_path.exists() and not source_path.exists():
                shutil.rmtree(target_path)
            raise e
