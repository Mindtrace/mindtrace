import io
import json
import os
import time
from pathlib import Path
from typing import Dict, List, TypeVar

from minio import Minio
from minio.api import CopySource
from minio.error import S3Error

from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.exceptions import LockAcquisitionError

T = TypeVar("T")


class MinioRegistryBackend(RegistryBackend):
    """Handles syncing object version directories and registry metadata with a remote MinIO server.

    Expects the same logical registry layout in a given MinIO bucket.

    Local Docker Example:
        To run a local MinIO registry, first start a MinIO server using docker:

        .. code-block:: bash

            $ docker run --rm --name minio \\
                -p 9000:9000 \\
                -p 9001:9001 \\
                -e MINIO_ROOT_USER=minioadmin \\
                -e MINIO_ROOT_PASSWORD=minioadmin \\
                -v ~/.cache/mindtrace/minio_data:/data \\
                minio/minio server /data --console-address ":9001"

        =============================  ===============================================
        Option                         Description
        =============================  ===============================================
        -p 9000:9000                   API access (S3-compatible)
        -p 9001:9001                   Web UI (access at http://localhost:9001)
        -v ~/minio_data:/data          Persistent volume for object storage
        MINIO_ROOT_USER/PASSWORD       Admin credentials (change in production)
        minio server /data             Starts the object server
        =============================  ===============================================

    Usage Example::

        from mindtrace.registry import Registry, MinioRegistryBackend

        # Connect to a remote MinIO registry (expected to be non-local in practice)
        minio_backend = MinioRegistryBackend(
            uri="~/.cache/mindtrace/minio_registry",
            endpoint="localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="minio-registry",
            secure=False
        )
        registry = Registry(backend=minio_backend)

        # Save some objects to the registry
        registry.save("test:int", 42)
        registry.save("test:float", 3.14)
        registry.save("test:str", "Hello, World!")
        registry.save("test:list", [1, 2, 3])
        registry.save("test:dict", {"a": 1, "b": 2})

        # Print the contents of the registry
        print(registry)

        Registry at /Users/jeremywurbs/.cache/mindtrace/minio_registry   
        ┏━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
        ┃ Object     ┃ Version ┃ Class          ┃ Value         ┃ Metadata ┃
        ┡━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
        │ test:dict  │ v1      │ builtins.dict  │ <dict>        │ (none)   │
        │ test:float │ v1      │ builtins.float │ 3.14          │ (none)   │
        │ test:int   │ v1      │ builtins.int   │ 42            │ (none)   │
        │ test:list  │ v1      │ builtins.list  │ <list>        │ (none)   │
        │ test:str   │ v1      │ builtins.str   │ Hello, World! │ (none)   │
        └────────────┴─────────┴────────────────┴───────────────┴──────────┘    
    """

    def __init__(
        self,
        uri: str | Path | None = None,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = "minio-registry",
        secure: bool = True,
        **kwargs,
    ):
        """Initialize the MinioRegistryBackend.

        Args:
            uri: The base directory path where all object files and metadata will be stored.
            endpoint: MinIO server endpoint.
            access_key: MinIO access key.
            secret_key: MinIO secret key.
            bucket: MinIO bucket name.
            secure: Whether to use HTTPS.
            **kwargs: Additional keyword arguments for the RegistryBackend.
        """
        super().__init__(uri=uri, **kwargs)
        self._uri = Path(uri or self.config["MINDTRACE_MINIO"]["MINIO_REGISTRY_URI"]).expanduser().resolve()
        self._uri.mkdir(parents=True, exist_ok=True)
        self._metadata_path = "registry_metadata.json"
        self.logger.debug(f"Initializing MinioBackend with uri: {self._uri}")

        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

        # Create bucket if it doesn't exist
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
        self.bucket = bucket

        # Check if metadata file exists
        try:
            self.client.stat_object(self.bucket, str(self._metadata_path))
        except S3Error as e:
            if e.code == "NoSuchKey":
                # Create empty metadata file if it doesn't exist
                data = json.dumps({"materializers": {}}).encode()
                data_io = io.BytesIO(data)
                self.client.put_object(
                    self.bucket, str(self._metadata_path), data_io, len(data), content_type="application/json"
                )
            else:
                # Re-raise other S3 errors
                raise

    @property
    def uri(self) -> Path:
        return self._uri

    @property
    def metadata_path(self) -> Path:
        """The resolved metadata file path for the backend."""
        return Path(self._metadata_path)

    def push(self, name: str, version: str, local_path: str | Path):
        """Upload a local directory to MinIO.

        Args:
            local_path: Path to local directory to upload
            name: Name of the object
            version: Version string
        """
        self.validate_object_name(name)
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Uploading directory from {local_path} to {remote_key}.")

        local_path = Path(local_path)
        uploaded_files = []
        for file in local_path.rglob("*"):
            if file.is_file():
                obj_key = os.path.join(remote_key, file.relative_to(local_path)).replace("\\", "/")
                self.logger.debug(f"Uploading file {file} to {obj_key}")
                self.client.fput_object(self.bucket, obj_key, str(file))
                uploaded_files.append(obj_key)

        self.logger.debug(f"Upload complete. Files uploaded: {uploaded_files}")

        # Verify upload
        try:
            objects = list(self.client.list_objects(self.bucket, prefix=remote_key))
            self.logger.debug(f"Verification - Objects in {remote_key}: {[obj.object_name for obj in objects]}")
        except Exception as e:
            self.logger.error(f"Error verifying upload: {e}")

    def pull(self, name: str, version: str, local_path: str | Path):
        """Download a directory from MinIO.

        Args:
            name: Name of the object
            version: Version string
            local_path: Path to local directory to download
        """
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Downloading directory from {remote_key} to {local_path}.")

        # List objects before download
        try:
            objects = list(self.client.list_objects(self.bucket, prefix=remote_key))
            self.logger.debug(f"Objects found in {remote_key}: {[obj.object_name for obj in objects]}")
        except Exception as e:
            self.logger.error(f"Error listing objects before download: {e}")

        local_path = Path(local_path)
        downloaded_files = []
        for obj in self.client.list_objects(self.bucket, prefix=remote_key, recursive=True):
            # Skip directory markers
            if not obj.object_name or obj.object_name.endswith("/"):
                continue

            # Get the relative path by removing the remote_key prefix
            relative_path = obj.object_name[len(remote_key) :].lstrip("/")
            if not relative_path:  # Skip if it's the root directory
                continue

            dest_path = local_path / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Downloading {obj.object_name} to {dest_path}")
            self.client.fget_object(self.bucket, obj.object_name, str(dest_path))
            downloaded_files.append(str(dest_path))

        self.logger.debug(f"Download complete. Files downloaded: {downloaded_files}")

        # Verify download
        try:
            local_files = list(local_path.rglob("*"))
            self.logger.debug(f"Verification - Local files after download: {[str(f) for f in local_files]}")
        except Exception as e:
            self.logger.error(f"Error verifying download: {e}")

    def delete(self, name: str, version: str):
        """Delete a version directory from MinIO.

        Args:
            name: Name of the object
            version: Version string
        """
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Deleting directory: {remote_key}")

        for obj in self.client.list_objects(self.bucket, prefix=remote_key, recursive=True):
            if obj.object_name:
                self.client.remove_object(self.bucket, obj.object_name)

    def save_metadata(self, name: str, version: str, metadata: dict):
        """Save object metadata to MinIO.

        Args:
            name: Name of the object
            version: Version string
            metadata: Dictionary containing object metadata
        """
        self.validate_object_name(name)
        meta_path = self._object_metadata_path(name, version)
        self.logger.debug(f"Saving metadata to {meta_path}: {metadata}")

        # Convert metadata to bytes and wrap in BytesIO
        data = json.dumps(metadata).encode()
        data_io = io.BytesIO(data)

        self.client.put_object(self.bucket, meta_path, data_io, len(data), content_type="application/json")

    def fetch_metadata(self, name: str, version: str) -> dict:
        """Fetch object metadata from MinIO.

        Args:
            name: Name of the object
            version: Version string

        Returns:
            Dictionary containing object metadata
        """
        meta_path = self._object_metadata_path(name, version)
        self.logger.debug(f"Loading metadata from: {meta_path}")

        response = self.client.get_object(self.bucket, meta_path)
        metadata = json.loads(response.data.decode())

        # Add the path to the object directory to the metadata:
        object_key = self._object_key(name, version)
        metadata.update({"path": str(self._uri / object_key)})

        self.logger.debug(f"Loaded metadata: {metadata}")
        return metadata

    def delete_metadata(self, name: str, version: str):
        """Delete object metadata from MinIO.

        Args:
            name: Name of the object.
            version: Version of the object.
        """
        meta_path = self._object_metadata_path(name, version)
        self.logger.debug(f"Deleting metadata file: {meta_path}")
        try:
            self.client.remove_object(self.bucket, meta_path)
        except S3Error as e:
            if e.code != "NoSuchKey":
                raise

    def register_materializer(self, object_class: str, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        try:
            try:
                response = self.client.get_object(self.bucket, str(self._metadata_path))
                metadata = json.loads(response.data.decode())
            except S3Error as e:
                if e.code == "NoSuchKey":
                    # If metadata doesn't exist, create new metadata
                    metadata = {"materializers": {}}
                else:
                    # Re-raise any other S3 errors
                    raise

            # Update metadata with new materializer
            metadata["materializers"][object_class] = materializer_class

            # Convert metadata to bytes and wrap in BytesIO
            data = json.dumps(metadata).encode()
            data_io = io.BytesIO(data)

            # Save updated metadata
            self.client.put_object(
                self.bucket, str(self._metadata_path), data_io, len(data), content_type="application/json"
            )
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
        try:
            response = self.client.get_object(self.bucket, str(self._metadata_path))
            metadata = json.loads(response.data.decode())
            return metadata.get("materializers", {}).get(object_class)
        except S3Error as e:
            if e.code == "NoSuchKey":
                # No metadata file exists, so no materializers are registered
                return None
            # Re-raise any other S3 errors
            raise
        except Exception as e:
            # Re-raise any other errors
            self.logger.error(f"Error getting registered materializer for {object_class}: {e}")
            raise

    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
        """
        try:
            response = self.client.get_object(self.bucket, str(self._metadata_path))
            metadata = json.loads(response.data.decode())
            return metadata.get("materializers", {})
        except S3Error as e:
            if e.code == "NoSuchKey":
                # No metadata file exists, so no materializers are registered
                return {}
            # Re-raise any other S3 errors
            raise
        except Exception as e:
            # Re-raise any other errors
            self.logger.error(f"Error loading materializers: {e}")
            raise

    def save_registry_metadata(self, metadata: dict):
        """Save registry-level metadata to the backend.

        Args:
            metadata: Dictionary containing registry metadata to save.
        """
        try:
            data = json.dumps(metadata).encode()
            data_io = io.BytesIO(data)
            self.client.put_object(
                self.bucket, str(self._metadata_path), data_io, len(data), content_type="application/json"
            )
        except Exception as e:
            self.logger.error(f"Error saving registry metadata: {e}")
            raise e

    def fetch_registry_metadata(self) -> dict:
        """Fetch registry-level metadata from the backend.

        Returns:
            Dictionary containing registry metadata. Returns empty dict if no metadata exists.
        """
        try:
            response = self.client.get_object(self.bucket, str(self._metadata_path))
            return json.loads(response.data.decode())
        except S3Error as e:
            if e.code == "NoSuchKey":
                # No metadata file exists
                return {}
            # Re-raise any other S3 errors
            raise
        except Exception as e:
            self.logger.debug(f"Could not load registry metadata: {e}")
            return {}

    def list_objects(self) -> List[str]:
        """List all objects in the registry.

        Returns:
            List of object names
        """
        objects = set()
        prefix = "_meta_"
        for obj in self.client.list_objects(self.bucket, prefix=prefix):
            if obj.object_name and obj.object_name.endswith(".json"):
                # Extract object name from metadata filename
                name_part = Path(obj.object_name).stem.split("@")[0].replace("_meta_", "")
                name = name_part.replace("_", ":")
                objects.add(name)
        return sorted(list(objects))

    def list_versions(self, name: str) -> List[str]:
        """List available versions for a given object.

        Args:
            name: Name of the object

        Returns:
            Sorted list of version strings available for the object
        """
        prefix = f"_meta_{name.replace(':', '_')}@"
        versions = []

        for obj in self.client.list_objects(self.bucket, prefix=prefix):
            if obj.object_name and obj.object_name.endswith(".json"):
                version = obj.object_name[len(prefix) : -5]
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
        try:
            # Try to stat the object to check existence
            self.client.stat_object(self.bucket, meta_path)
            # If stat_object succeeds, verify by trying to fetch metadata
            # This handles cases where stat_object doesn't raise but object doesn't exist (e.g., in mocks)
            try:
                self.fetch_metadata(name, version)
                return True
            except (S3Error, Exception):
                # If fetch_metadata fails, object doesn't exist
                return False
        except S3Error as e:
            if e.code == "NoSuchKey" or e.code == "404":
                return False
            # For other S3Error codes, fall back to checking if metadata can be fetched
            try:
                self.fetch_metadata(name, version)
                return True
            except Exception:
                return False
        except Exception:
            # For non-S3Error exceptions, fall back to checking if metadata can be fetched
            try:
                self.fetch_metadata(name, version)
                return True
            except Exception:
                return False

    def _object_key(self, name: str, version: str) -> str:
        """Convert object name and version to a storage key.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Storage key for the object version.
        """
        return f"objects/{name}/{version}"

    def _object_metadata_path(self, name: str, version: str) -> str:
        """Generate the metadata file path for an object version.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Metadata file path (e.g., "_meta_object_name@1.0.0.json").
        """
        return f"_meta_{name.replace(':', '_')}@{version}.json"

    def _object_metadata_prefix(self, name: str) -> str:
        """Generate the metadata file prefix for listing versions of an object.

        Args:
            name: Name of the object.

        Returns:
            Metadata file prefix (e.g., "_meta_object_name@").
        """
        return f"_meta_{name.replace(':', '_')}@"

    def _lock_key(self, key: str) -> str:
        """Convert a key to a lock file key.

        Args:
            key: The key to convert.

        Returns:
            Lock file key.
        """
        return f"_lock_{key}"

    def acquire_lock(self, key: str, lock_id: str, timeout: int, shared: bool = False) -> bool:
        """Acquire a lock using Minio's object locking features.

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
                response = self.client.get_object(self.bucket, lock_key)
                metadata = json.loads(response.data.decode())
                if time.time() < metadata.get("expires_at", 0):
                    # If there's an active exclusive lock, we can't acquire a shared lock
                    if shared and not metadata.get("shared", False):
                        raise LockAcquisitionError(f"Lock {key} is currently held exclusively")
                    # If there are active shared locks, we can't acquire an exclusive lock
                    if not shared and metadata.get("shared", False):
                        raise LockAcquisitionError(f"Lock {key} is currently held as shared")
            except S3Error as e:
                if e.code == "NoSuchKey":
                    # Lock doesn't exist, we can proceed
                    pass
                else:
                    # Unexpected S3 error
                    raise
            except LockAcquisitionError:
                # Re-raise LockAcquisitionError
                raise
            except Exception:
                # Lock doesn't exist or is invalid, we can proceed
                pass

            # Create lock metadata
            metadata = {"lock_id": lock_id, "expires_at": time.time() + timeout, "shared": shared}

            # Convert metadata to bytes and wrap in BytesIO
            data = json.dumps(metadata).encode()
            data_io = io.BytesIO(data)

            # Upload lock file with metadata
            self.client.put_object(self.bucket, lock_key, data_io, len(data), content_type="application/json")

            return True

        except LockAcquisitionError:
            # Re-raise LockAcquisitionError
            raise
        except Exception as e:
            self.logger.error(f"Error acquiring {'shared ' if shared else ''}lock for {key}: {e}")
            return False

    def release_lock(self, key: str, lock_id: str) -> bool:
        """Release a lock by verifying ownership and removing the lock object.

        Args:
            key: The key to unlock
            lock_id: The lock ID that was used to acquire the lock

        Returns:
            True if lock was released, False otherwise
        """
        lock_key = self._lock_key(key)

        try:
            # Verify lock ownership
            try:
                response = self.client.get_object(self.bucket, lock_key)
                lock_data = json.loads(response.data.decode())
                if lock_data.get("lock_id") != lock_id:
                    return False  # Not our lock
            except S3Error as e:
                if e.code == "NoSuchKey":
                    return True  # Lock doesn't exist
                raise  # Unexpected error

            # Remove the lock
            self.client.remove_object(self.bucket, lock_key)
            return True

        except Exception as e:
            self.logger.error(f"Error releasing lock for {key}: {e}")
            return False

    def check_lock(self, key: str) -> tuple[bool, str | None]:
        """Check if a key is currently locked.

        Args:
            key: The key to check

        Returns:
            Tuple of (is_locked, lock_id). If locked, lock_id will be the current lock holder's ID.
            If not locked, lock_id will be None.
        """
        lock_key = self._lock_key(key)

        try:
            response = self.client.get_object(self.bucket, lock_key)
            lock_data = json.loads(response.data.decode())

            # Check if lock is expired
            if time.time() > lock_data.get("expires_at", 0):
                return False, None

            return True, lock_data.get("lock_id")

        except S3Error as e:
            if e.code == "NoSuchKey":
                return False, None
            raise  # Unexpected error

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
            source_meta_key = self._object_metadata_path(source_name, source_version)
            target_meta_key = self._object_metadata_path(target_name, target_version)

            self.logger.debug(f"Overwriting {source_name}@{source_version} to {target_name}@{target_version}")

            # List source objects before any operations
            try:
                source_objects = list(self.client.list_objects(self.bucket, prefix=source_key, recursive=True))
            except Exception as e:
                self.logger.error(f"Error listing source objects: {e}")
                raise

            # If target exists, delete it first
            try:
                target_objects = list(self.client.list_objects(self.bucket, prefix=target_key, recursive=True))
                if target_objects:
                    for obj in target_objects:
                        if obj.object_name:
                            self.client.remove_object(self.bucket, obj.object_name)
                self.client.remove_object(self.bucket, target_meta_key)
            except S3Error as e:
                if e.code != "NoSuchKey":
                    self.logger.error(f"Error deleting target objects: {e}")
                    raise
                self.logger.debug("No existing target objects to delete")

            # Copy all objects from source to target
            if not source_objects:
                raise ValueError(f"No source objects found for {source_name}@{source_version}")

            for obj in source_objects:
                # Skip directory markers (objects ending with /)
                if not obj.object_name or obj.object_name.endswith("/"):
                    continue

                # Create target object name by replacing source prefix with target prefix
                target_obj_name = obj.object_name.replace(source_key, target_key)
                self.logger.debug(f"Copying {obj.object_name} to {target_obj_name}")

                # Copy the object
                self.client.copy_object(self.bucket, target_obj_name, CopySource(self.bucket, obj.object_name))

            # Copy metadata file if it exists
            try:
                self.logger.debug(f"Copying metadata from {source_meta_key} to {target_meta_key}")
                source_meta = self.client.get_object(self.bucket, source_meta_key)
                metadata = json.loads(source_meta.data.decode())

                # Update the path in metadata
                metadata["path"] = f"s3://{self.bucket}/{target_key}"

                # Save updated metadata
                data = json.dumps(metadata).encode()
                data_io = io.BytesIO(data)
                self.client.put_object(
                    self.bucket, target_meta_key, data_io, len(data), content_type="application/json"
                )
            except S3Error as e:
                if e.code == "NoSuchKey":
                    raise ValueError(f"No source metadata found for {source_name}@{source_version}")
                raise

            # Delete source objects
            for obj in source_objects:
                # Skip directory markers
                if not obj.object_name or obj.object_name.endswith("/"):
                    continue
                self.client.remove_object(self.bucket, obj.object_name)

            # Delete source metadata
            self.client.remove_object(self.bucket, source_meta_key)

            self.logger.debug(f"Successfully completed overwrite operation for {target_name}@{target_version}")

        except Exception as e:
            self.logger.error(f"Error during overwrite operation: {e}")
            raise e
