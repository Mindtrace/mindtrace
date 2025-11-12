import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List

from google.api_core import exceptions as gexc

from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.exceptions import LockAcquisitionError
from mindtrace.storage.gcs import GCSStorageHandler


class GCPRegistryBackend(RegistryBackend):
    """A Google Cloud Storage-based registry backend.

    This backend stores objects and metadata in a GCS bucket, providing distributed
    storage capabilities with atomic operations and distributed locking.

    Usage Example::

        from mindtrace.registry import Registry, GCPRegistryBackend

        # Connect to a GCS-based registry
        gcp_backend = GCPRegistryBackend(
            uri="gs://my-registry-bucket",
            project_id="my-project",
            bucket_name="my-registry-bucket",
            credentials_path="/path/to/service-account.json"
        )
        registry = Registry(backend=gcp_backend)

        # Save some objects to the registry
        registry.save("test:int", 42)
        registry.save("test:float", 3.14)
        registry.save("test:str", "Hello, World!")
    """

    def __init__(
        self,
        uri: str | Path | None = None,
        *,
        project_id: str,
        bucket_name: str,
        credentials_path: str | None = None,
        **kwargs,
    ):
        """Initialize the GCPRegistryBackend.

        Args:
            uri: The base URI for the registry (e.g., "gs://my-bucket").
            project_id: GCP project ID.
            bucket_name: GCS bucket name.
            credentials_path: Optional path to service account JSON file.
            **kwargs: Additional keyword arguments for the RegistryBackend.
        """
        super().__init__(uri=uri, **kwargs)
        self._uri = Path(uri or f"gs://{bucket_name}")
        self._metadata_path = "registry_metadata.json"
        self.logger.debug(f"Initializing GCPBackend with uri: {self._uri}")

        # Initialize GCS storage handler
        self.gcs = GCSStorageHandler(
            bucket_name=bucket_name,
            project_id=project_id,
            credentials_path=credentials_path,
            ensure_bucket=True,
            create_if_missing=True,
        )

        # Initialize metadata file if it doesn't exist
        self._ensure_metadata_file()

    @property
    def uri(self) -> Path:
        """The resolved base URI for the backend."""
        return self._uri

    @property
    def metadata_path(self) -> Path:
        """The resolved metadata file path for the backend."""
        return Path(self._metadata_path)

    def _ensure_metadata_file(self):
        """Ensure the metadata file exists in the bucket."""
        try:
            exists = self.gcs.exists(self._metadata_path)
        except Exception:
            exists = False
        if not exists:
            # Create empty metadata file if it doesn't exist
            data = json.dumps({"materializers": {}}).encode()
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
                f.write(data)
                temp_path = f.name

            try:
                self.gcs.upload(temp_path, self._metadata_path)
            finally:
                os.unlink(temp_path)

    def _object_key(self, name: str, version: str) -> str:
        """Convert object name and version to a storage key.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Storage key for the object version.
        """
        return f"objects/{name}/{version}"

    def _lock_key(self, key: str) -> str:
        """Convert a key to a lock file key.

        Args:
            key: The key to convert.

        Returns:
            Lock file key.
        """
        return f"_lock_{key}"

    def push(self, name: str, version: str, local_path: str | Path):
        """Upload a local directory to GCS.

        Args:
            name: Name of the object.
            version: Version string.
            local_path: Path to the local directory to upload.
        """
        self.validate_object_name(name)
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Uploading directory from {local_path} to {remote_key}")

        local_path = Path(local_path)
        uploaded_files = []
        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_path)
                remote_path = f"{remote_key}/{relative_path}".replace("\\", "/")
                self.logger.debug(f"Uploading file {file_path} to {remote_path}")
                self.gcs.upload(str(file_path), remote_path)
                uploaded_files.append(remote_path)

        self.logger.debug(f"Upload complete. Files uploaded: {uploaded_files}")

    def pull(self, name: str, version: str, local_path: str | Path):
        """Download a directory from GCS.

        Args:
            name: Name of the object.
            version: Version string.
            local_path: Path to the local directory to download to.
        """
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Downloading directory from {remote_key} to {local_path}")

        local_path = Path(local_path)
        downloaded_files = []

        # List all objects with the prefix
        objects = self.gcs.list_objects(prefix=remote_key)
        for obj_name in objects:
            if not obj_name.endswith("/"):  # Skip directory markers
                relative_path = obj_name[len(remote_key) :].lstrip("/")
                if relative_path:
                    dest_path = local_path / relative_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    self.logger.debug(f"Downloading {obj_name} to {dest_path}")
                    self.gcs.download(obj_name, str(dest_path))
                    downloaded_files.append(str(dest_path))

        self.logger.debug(f"Download complete. Files downloaded: {downloaded_files}")

    def delete(self, name: str, version: str):
        """Delete a version directory from GCS.

        Args:
            name: Name of the object.
            version: Version string.
        """
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Deleting directory: {remote_key}")

        objects = self.gcs.list_objects(prefix=remote_key)
        for obj_name in objects:
            self.gcs.delete(obj_name)

    def save_metadata(self, name: str, version: str, metadata: dict):
        """Save object metadata to GCS.

        Args:
            name: Name of the object.
            version: Version string.
            metadata: Dictionary containing object metadata.
        """
        self.validate_object_name(name)
        meta_path = f"_meta_{name.replace(':', '_')}@{version}.json"
        self.logger.debug(f"Saving metadata to {meta_path}: {metadata}")

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(metadata, f)
            temp_path = f.name

        try:
            self.gcs.upload(temp_path, meta_path)
        finally:
            os.unlink(temp_path)

    def fetch_metadata(self, name: str, version: str) -> dict:
        """Fetch object metadata from GCS.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Dictionary containing object metadata.
        """
        meta_path = f"_meta_{name.replace(':', '_')}@{version}.json"
        self.logger.debug(f"Loading metadata from: {meta_path}")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            self.gcs.download(meta_path, temp_path)
            with open(temp_path, "r") as f:
                metadata = json.load(f)

            # Add the GCS path to the metadata
            object_key = self._object_key(name, version)
            metadata["path"] = f"gs://{self.gcs.bucket_name}/{object_key}"

            self.logger.debug(f"Loaded metadata: {metadata}")
            return metadata
        finally:
            os.unlink(temp_path)

    def delete_metadata(self, name: str, version: str):
        """Delete object metadata from GCS.

        Args:
            name: Name of the object.
            version: Version of the object.
        """
        meta_path = f"_meta_{name.replace(':', '_')}@{version}.json"
        self.logger.debug(f"Deleting metadata file: {meta_path}")
        self.gcs.delete(meta_path)

    def list_objects(self) -> List[str]:
        """List all objects in the registry.

        Returns:
            List of object names.
        """
        objects = set()
        for obj_name in self.gcs.list_objects(prefix="_meta_"):
            if obj_name.endswith(".json"):
                name_part = Path(obj_name).stem.split("@")[0].replace("_meta_", "")
                name = name_part.replace("_", ":")
                objects.add(name)
        return sorted(list(objects))

    def list_versions(self, name: str) -> List[str]:
        """List available versions for a given object.

        Args:
            name: Name of the object.

        Returns:
            Sorted list of version strings available for the object.
        """
        prefix = f"_meta_{name.replace(':', '_')}@"
        versions = []

        for obj_name in self.gcs.list_objects(prefix=prefix):
            if obj_name.endswith(".json"):
                version = obj_name[len(prefix) : -5]  # Remove prefix and .json
                versions.append(version)
        return sorted(versions)

    def has_object(self, name: str, version: str) -> bool:
        """Check if a specific object version exists in the backend.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            True if the object version exists, False otherwise.
        """
        if name not in self.list_objects():
            return False
        else:
            return version in self.list_versions(name)

    def register_materializer(self, object_class: str, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        try:
            # Download current metadata
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                temp_path = f.name

            try:
                self.gcs.download(self._metadata_path, temp_path)
                with open(temp_path, "r") as f:
                    metadata = json.load(f)
            except Exception:
                # If metadata doesn't exist, create new metadata
                metadata = {"materializers": {}}

            # Update metadata with new materializer
            metadata["materializers"][object_class] = materializer_class

            # Upload updated metadata
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(metadata, f)
                temp_path = f.name

            try:
                self.gcs.upload(temp_path, self._metadata_path)
            finally:
                os.unlink(temp_path)

        except Exception as e:
            self.logger.error(f"Error registering materializer for {object_class}: {e}")
            raise e
        else:
            self.logger.debug(f"Registered materializer for {object_class}: {materializer_class}")

    def register_materializers_batch(self, materializers: Dict[str, str]):
        """Register multiple materializers in a single operation for better performance.

        Args:
            materializers: Dictionary mapping object classes to materializer classes.
        """
        try:
            # Download current metadata
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                temp_path = f.name

            try:
                self.gcs.download(self._metadata_path, temp_path)
                with open(temp_path, "r") as f:
                    metadata = json.load(f)
            except Exception:
                # If metadata doesn't exist, create new metadata
                metadata = {"materializers": {}}

            # Update metadata with all materializers
            metadata["materializers"].update(materializers)

            # Upload updated metadata
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(metadata, f)
                temp_path = f.name

            try:
                self.gcs.upload(temp_path, self._metadata_path)
            finally:
                os.unlink(temp_path)

        except Exception as e:
            self.logger.error(f"Error registering materializers batch: {e}")
            raise e
        else:
            self.logger.debug(f"Registered {len(materializers)} materializers in batch")

    def registered_materializer(self, object_class: str) -> str | None:
        """Get the registered materializer for an object class.

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                temp_path = f.name

            try:
                self.gcs.download(self._metadata_path, temp_path)
                with open(temp_path, "r") as f:
                    metadata = json.load(f)
                return metadata.get("materializers", {}).get(object_class)
            except Exception as e:
                self.logger.debug(f"Could not load materializer for {object_class}: {e}")
                return None
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        except Exception as e:
            self.logger.error(f"Error getting registered materializer for {object_class}: {e}")
            return None

    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
        """
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                temp_path = f.name

            try:
                self.gcs.download(self._metadata_path, temp_path)
                with open(temp_path, "r") as f:
                    metadata = json.load(f)
                return metadata.get("materializers", {})
            except Exception as e:
                self.logger.debug(f"Could not load materializers: {e}")
                return {}
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        except Exception as e:
            self.logger.error(f"Error loading materializers: {e}")
            return {}

    def acquire_lock(self, key: str, lock_id: str, timeout: int, shared: bool = False) -> bool:
        """Acquire a lock using GCS object generation numbers.

        Args:
            key: The key to acquire the lock for.
            lock_id: The ID of the lock to acquire.
            timeout: The timeout in seconds for the lock.
            shared: Whether to acquire a shared (read) lock. If False, acquires an exclusive (write) lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        lock_key = self._lock_key(key)

        try:
            # Check if lock exists and is not expired
            try:
                with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                    temp_path = f.name

                try:
                    self.gcs.download(lock_key, temp_path)
                    with open(temp_path, "r") as f:
                        metadata = json.load(f)

                    if time.time() < metadata.get("expires_at", 0):
                        # If there's an active exclusive lock, we can't acquire a shared lock
                        if shared and not metadata.get("shared", False):
                            raise LockAcquisitionError(f"Lock {key} is currently held exclusively")
                        # If there are active shared locks, we can't acquire an exclusive lock
                        if not shared and metadata.get("shared", False):
                            raise LockAcquisitionError(f"Lock {key} is currently held as shared")
                        # If there's already a shared lock and we want a shared lock, we can share it
                        if shared and metadata.get("shared", False):
                            return True
                        # Otherwise, lock is held exclusively
                        raise LockAcquisitionError(f"Lock {key} is currently held exclusively")
                    else:
                        # Stale/expired lock -> proactively clear it so conditional create can succeed
                        try:
                            self.gcs.delete(lock_key)
                        except Exception as e:
                            # Best-effort: if someone else deleted it or we lack perms, we'll try create below
                            self.logger.warning(f"Error deleting stale lock {key}: {e}")
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
            except Exception:
                # Lock doesn't exist or is invalid, we can proceed
                pass

            # Create lock metadata
            metadata = {"lock_id": lock_id, "expires_at": time.time() + timeout, "shared": shared}

            # Try to create lock object atomically using if_generation_match=0
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(metadata, f)
                temp_path = f.name

            try:
                blob = self.gcs._bucket().blob(lock_key)
                blob.upload_from_filename(temp_path, if_generation_match=0)
                return True
            except gexc.PreconditionFailed:
                # Lock already exists
                return False
            except Exception as e:
                self.logger.debug(f"Lock acquisition failed: {e}")
                return False
            finally:
                os.unlink(temp_path)

        except LockAcquisitionError:
            # Re-raise LockAcquisitionError
            raise
        except Exception as e:
            self.logger.error(f"Error acquiring {'shared ' if shared else ''}lock for {key}: {e}")
            return False

    def release_lock(self, key: str, lock_id: str) -> bool:
        """Release a lock by verifying ownership and removing the lock object.

        Args:
            key: The key to unlock.
            lock_id: The lock ID that was used to acquire the lock.

        Returns:
            True if lock was released, False otherwise.
        """
        lock_key = self._lock_key(key)

        try:
            # Verify lock ownership
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                temp_path = f.name

            try:
                self.gcs.download(lock_key, temp_path)
                with open(temp_path, "r") as f:
                    lock_data = json.load(f)
                if lock_data.get("lock_id") != lock_id:
                    return False  # Not our lock
            except Exception:
                return True  # Lock doesn't exist

            # Remove the lock
            self.gcs.delete(lock_key)
            return True
        finally:
            if "temp_path" in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)

    def check_lock(self, key: str) -> tuple[bool, str | None]:
        """Check if a key is currently locked.

        Args:
            key: The key to check.

        Returns:
            Tuple of (is_locked, lock_id). If locked, lock_id will be the current lock holder's ID.
            If not locked, lock_id will be None.
        """
        lock_key = self._lock_key(key)

        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                temp_path = f.name

            try:
                self.gcs.download(lock_key, temp_path)
                with open(temp_path, "r") as f:
                    lock_data = json.load(f)

                # Check if lock is expired
                if time.time() > lock_data.get("expires_at", 0):
                    return False, None

                return True, lock_data.get("lock_id")
            finally:
                os.unlink(temp_path)

        except Exception:
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
        try:
            # Get the source and target object keys
            source_key = self._object_key(source_name, source_version)
            target_key = self._object_key(target_name, target_version)

            # Get the source and target metadata keys
            source_meta_key = f"_meta_{source_name.replace(':', '_')}@{source_version}.json"
            target_meta_key = f"_meta_{target_name.replace(':', '_')}@{target_version}.json"

            self.logger.debug(f"Overwriting {source_name}@{source_version} to {target_name}@{target_version}")

            # List source objects before any operations
            source_objects = self.gcs.list_objects(prefix=source_key)

            # If target exists, delete it first
            try:
                target_objects = self.gcs.list_objects(prefix=target_key)
                if target_objects:
                    for obj_name in target_objects:
                        self.gcs.delete(obj_name)
                self.gcs.delete(target_meta_key)
            except Exception:
                self.logger.debug("No existing target objects to delete")

            # Copy all objects from source to target using GCS copy operations
            if not source_objects:
                raise ValueError(f"No source objects found for {source_name}@{source_version}")

            for obj_name in source_objects:
                # Skip directory markers
                if not obj_name.endswith("/"):
                    # Create target object name by replacing source prefix with target prefix
                    target_obj_name = obj_name.replace(source_key, target_key)
                    self.logger.debug(f"Copying {obj_name} to {target_obj_name}")

                    # Copy the object using GCS rewrite operation
                    source_blob = self.gcs._bucket().blob(obj_name)
                    target_blob = self.gcs._bucket().blob(target_obj_name)
                    target_blob.rewrite(source_blob)

            # Copy metadata file if it exists
            try:
                self.logger.debug(f"Copying metadata from {source_meta_key} to {target_meta_key}")

                with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                    temp_path = f.name

                try:
                    self.gcs.download(source_meta_key, temp_path)
                    with open(temp_path, "r") as f:
                        metadata = json.load(f)

                    # Update the path in metadata
                    metadata["path"] = f"gs://{self.gcs.bucket_name}/{target_key}"

                    # Save updated metadata
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f2:
                        json.dump(metadata, f2)
                        temp_path2 = f2.name

                    try:
                        self.gcs.upload(temp_path2, target_meta_key)
                    finally:
                        os.unlink(temp_path2)
                finally:
                    os.unlink(temp_path)
            except Exception as e:
                if "not found" in str(e).lower():
                    raise ValueError(f"No source metadata found for {source_name}@{source_version}")
                raise

            # Delete source objects
            for obj_name in source_objects:
                if not obj_name.endswith("/"):
                    self.gcs.delete(obj_name)

            # Delete source metadata
            self.gcs.delete(source_meta_key)

            self.logger.debug(f"Successfully completed overwrite operation for {target_name}@{target_version}")

        except Exception as e:
            self.logger.error(f"Error during overwrite operation: {e}")
            raise e
