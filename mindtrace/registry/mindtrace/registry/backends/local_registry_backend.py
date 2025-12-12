"""Local filesystem-based registry backend.

All object directories and registry files are stored under a configurable base directory.
"""

import json
import os
import platform
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Tuple, Union

import yaml

# Import appropriate locking mechanism based on OS
if platform.system() == "Windows":
    import msvcrt

    fcntl = None
else:

    msvcrt = None

from mindtrace.registry.backends.registry_backend import (
    MetadataArg,
    NameArg,
    PathArg,
    RegistryBackend,
    VersionArg,
)
from mindtrace.registry.core.exceptions import (
    LockAcquisitionError,
    RegistryObjectNotFound,
    RegistryVersionConflict,
)


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

    # ─────────────────────────────────────────────────────────────────────────
    # Path Helpers
    # ─────────────────────────────────────────────────────────────────────────

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

    def _lock_path(self, key: str) -> Path:
        """Get the path for a lock file."""
        return self._full_path(f"_lock_{key}")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Locking
    # ─────────────────────────────────────────────────────────────────────────

    def _acquire_internal_lock(self, key: str, lock_id: str, timeout: int) -> bool:
        """Acquire internal lock using atomic file operations.

        Uses atomic file creation with O_EXCL to ensure only one process can create the lock file.
        The lock file contains both the lock_id and expiration time in JSON format.

        Args:
            key: The key to acquire the lock for.
            lock_id: The ID of the lock to acquire.
            timeout: The timeout in seconds for the lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        lock_path = self._lock_path(key)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Try atomic file creation with O_EXCL
            if platform.system() == "Windows":
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            else:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)

            # File created - we have the lock
            with os.fdopen(fd, "r+") as f:
                metadata = {"lock_id": lock_id, "expires_at": time.time() + timeout}
                f.write(json.dumps(metadata))
                f.flush()
                os.fsync(f.fileno())
                return True

        except FileExistsError:
            # Check if existing lock is expired
            try:
                with open(lock_path, "r") as f:
                    content = f.read().strip()
                    if not content:
                        lock_path.unlink()
                        return self._acquire_internal_lock(key, lock_id, timeout)
                    meta = json.loads(content)

                if time.time() > meta.get("expires_at", 0):
                    # Expired - remove and retry
                    lock_path.unlink()
                    return self._acquire_internal_lock(key, lock_id, timeout)
                return False
            except (json.JSONDecodeError, IOError, FileNotFoundError):
                return False
        except Exception as e:
            self.logger.error(f"Error acquiring lock for {key}: {e}")
            return False

    def _release_internal_lock(self, key: str, lock_id: str) -> bool:
        """Release internal lock by verifying ownership and removing the file.

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

            with open(lock_path, "r") as f:
                meta = json.loads(f.read().strip())
                if meta.get("lock_id") != lock_id:
                    return False

            lock_path.unlink()
            return True
        except Exception as e:
            self.logger.error(f"Error releasing lock for {key}: {e}")
            return False

    @contextmanager
    def _internal_lock(self, key: str, timeout: int = 30):
        """Context manager for internal locking.

        Args:
            key: The key to acquire the lock for.
            timeout: The timeout in seconds for the lock.

        Yields:
            None

        Raises:
            LockAcquisitionError: If the lock cannot be acquired.
        """
        lock_id = str(uuid.uuid4())
        if not self._acquire_internal_lock(key, lock_id, timeout):
            raise LockAcquisitionError(f"Cannot acquire lock for {key}")
        try:
            yield
        finally:
            self._release_internal_lock(key, lock_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Artifact + Metadata Operations
    # ─────────────────────────────────────────────────────────────────────────

    def push(
        self,
        name: NameArg,
        version: VersionArg,
        local_path: PathArg,
        metadata: MetadataArg = None,
        on_conflict: str = "error",
    ) -> Dict[Tuple[str, str], str]:
        """Atomically push artifacts and metadata with rollback on failure.

        Args:
            name: Object name(s). Single string or list.
            version: Version string(s), None for auto-increment, or list.
            local_path: Local source directory/directories to upload from.
            metadata: Metadata dict(s) to store.
            on_conflict: Behavior when version exists. "error" raises RegistryVersionConflict,
                "skip" silently skips. Default is "error".

        Returns:
            Dict mapping (name, resolved_version) to "ok" or "skipped".
        """
        entries = self._normalize_inputs(name, version, local_path, metadata)
        results: Dict[Tuple[str, str], str] = {}

        for obj_name, obj_version, obj_path, obj_meta in entries:
            self.validate_object_name(obj_name)

            with self._internal_lock(f"{obj_name}@push"):
                # Resolve version (auto-increment if None)
                resolved_version = self._resolve_version(obj_name, obj_version)

                artifact_dst = self._full_path(self._object_key(obj_name, resolved_version))
                meta_path = self._object_metadata_path(obj_name, resolved_version)

                # Check for existing version
                if meta_path.exists():
                    if on_conflict == "skip":
                        results[(obj_name, resolved_version)] = "skipped"
                        continue
                    raise RegistryVersionConflict(f"Object {obj_name}@{resolved_version} already exists.")

                try:
                    # 1. Copy artifacts
                    self.logger.debug(f"Uploading directory from {obj_path} to {artifact_dst}")
                    shutil.copytree(obj_path, artifact_dst, dirs_exist_ok=True)
                    self.logger.debug(f"Upload complete. Contents: {list(artifact_dst.rglob('*'))}")

                    # 2. Write metadata (commit point)
                    if obj_meta is not None:
                        # Add path to metadata
                        obj_meta = dict(obj_meta)
                        obj_meta["path"] = str(artifact_dst)

                        self.logger.debug(f"Saving metadata to {meta_path}: {obj_meta}")
                        with open(meta_path, "w") as f:
                            yaml.safe_dump(obj_meta, f)

                    results[(obj_name, resolved_version)] = "ok"

                except Exception as e:
                    # Rollback: remove artifacts and metadata
                    if artifact_dst.exists():
                        shutil.rmtree(artifact_dst, ignore_errors=True)
                    if meta_path.exists():
                        meta_path.unlink(missing_ok=True)
                    raise RuntimeError(f"Push failed for {obj_name}@{resolved_version}: {e}") from e

        return results

    def pull(
        self,
        name: NameArg,
        version: NameArg,
        local_path: PathArg,
    ) -> None:
        """Copy a directory from the backend store to a local path.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            local_path: Destination directory path(s) to copy to.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)
        paths = self._normalize_paths(local_path, len(names))

        if len(names) != len(versions) or len(names) != len(paths):
            raise ValueError("Input list lengths must match")

        for obj_name, obj_version, dest_path in zip(names, versions, paths):
            src = self._full_path(self._object_key(obj_name, obj_version))

            if not src.exists():
                raise RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found.")

            self.logger.debug(f"Downloading directory from {src} to {dest_path}")
            shutil.copytree(src, dest_path, dirs_exist_ok=True)
            self.logger.debug(f"Download complete. Contents: {list(Path(dest_path).rglob('*'))}")

    def delete(
        self,
        name: NameArg,
        version: NameArg,
    ) -> None:
        """Delete a directory from the backend store.

        Also removes empty parent directories.

        Args:
            name: Name of the object(s).
            version: Version string(s).
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        for obj_name, obj_version in zip(names, versions):
            with self._internal_lock(f"{obj_name}@{obj_version}"):
                target = self._full_path(self._object_key(obj_name, obj_version))
                self.logger.debug(f"Deleting directory: {target}")
                shutil.rmtree(target, ignore_errors=True)

                # Delete metadata
                meta_path = self._object_metadata_path(obj_name, obj_version)
                self.logger.debug(f"Deleting metadata file: {meta_path}")
                if meta_path.exists():
                    meta_path.unlink()

                # Cleanup parent if empty
                parent = target.parent
                if parent.exists() and not any(parent.iterdir()):
                    self.logger.debug(f"Removing empty parent directory: {parent}")
                    try:
                        parent.rmdir()
                    except Exception:
                        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata-Only Operations
    # ─────────────────────────────────────────────────────────────────────────

    def save_metadata(
        self,
        name: NameArg,
        version: NameArg,
        metadata: Union[dict, List[dict]],
    ) -> None:
        """Save metadata for a object version.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).
            metadata: Metadata to save.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)
        metadatas = self._normalize_metadata(metadata, len(names))

        if not (len(names) == len(versions) == len(metadatas)):
            raise ValueError("Input list lengths must match")

        for obj_name, obj_version, obj_meta in zip(names, versions, metadatas):
            self.validate_object_name(obj_name)
            meta_path = self._object_metadata_path(obj_name, obj_version)

            if meta_path.exists():
                raise RegistryVersionConflict(f"Object {obj_name}@{obj_version} already exists.")

            self.logger.debug(f"Saving metadata to {meta_path}: {obj_meta}")
            with open(meta_path, "w") as f:
                yaml.safe_dump(obj_meta, f)

    def fetch_metadata(
        self,
        name: NameArg,
        version: NameArg,
    ) -> Dict[Tuple[str, str], dict]:
        """Load metadata for a object version.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).

        Returns:
            Dict mapping (name, version) tuples to their metadata dicts.
            Missing entries are omitted from the result.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], dict] = {}

        for obj_name, obj_version in zip(names, versions):
            meta_path = self._object_metadata_path(obj_name, obj_version)
            self.logger.debug(f"Loading metadata from: {meta_path}")

            try:
                with open(meta_path, "r") as f:
                    meta = yaml.safe_load(f)

                # Handle case where yaml.safe_load returns None (empty file or whitespace only)
                if meta is None:
                    self.logger.warning(
                        f"Metadata file for {obj_name}@{obj_version} is empty or corrupted. "
                        f"This may indicate a race condition during concurrent writes."
                    )
                    continue

                # Add the path to the object directory to the metadata
                object_key = self._object_key(obj_name, obj_version)
                object_path = self._full_path(object_key)
                meta["path"] = str(object_path)

                self.logger.debug(f"Loaded metadata: {meta}")
                results[(obj_name, obj_version)] = meta

            except FileNotFoundError:
                continue  # Skip missing entries

        return results

    def delete_metadata(
        self,
        name: NameArg,
        version: NameArg,
    ) -> None:
        """Delete metadata for a object version.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        for obj_name, obj_version in zip(names, versions):
            meta_path = self._object_metadata_path(obj_name, obj_version)
            self.logger.debug(f"Deleting metadata file: {meta_path}")
            if meta_path.exists():
                meta_path.unlink()

    # ─────────────────────────────────────────────────────────────────────────
    # Registry-Level Metadata
    # ─────────────────────────────────────────────────────────────────────────

    def save_registry_metadata(self, metadata: dict) -> None:
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

    # ─────────────────────────────────────────────────────────────────────────
    # Discovery
    # ─────────────────────────────────────────────────────────────────────────

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

    def list_versions(self, name: NameArg) -> Dict[str, List[str]]:
        """List all versions available for the given object(s).

        Args:
            name: Name of the object(s)

        Returns:
            Dict mapping object names to sorted lists of version strings.
        """
        names = self._normalize_to_list(name)
        results: Dict[str, List[str]] = {}

        for obj_name in names:
            # Build the prefix used in metadata filenames for this object.
            prefix = self._object_metadata_prefix(obj_name)
            versions = []

            # Search for metadata files matching the prefix pattern in the base directory.
            for meta_file in self.uri.glob(f"{prefix}*.yaml"):
                # Extract the version from the filename by removing the prefix and the '.yaml' extension.
                version = meta_file.name[len(prefix) : -5]
                versions.append(version)

            # Semantic sort
            def version_key(v):
                try:
                    return [int(x) for x in v.split(".")]
                except ValueError:
                    return [0]

            results[obj_name] = sorted(versions, key=version_key)

        return results

    def has_object(
        self,
        name: NameArg,
        version: NameArg,
    ) -> Dict[Tuple[str, str], bool]:
        """Check if a specific object version exists in the backend.

        This method uses direct existence checks instead of listing all objects
        for better performance, especially with large registries.

        Args:
            name: Name of the object(s).
            version: Version string(s).

        Returns:
            Dict mapping (name, version) tuples to existence booleans.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], bool] = {}

        for obj_name, obj_version in zip(names, versions):
            # Check if metadata file exists directly (much faster than listing all objects)
            meta_path = self._object_metadata_path(obj_name, obj_version)
            results[(obj_name, obj_version)] = meta_path.exists()

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Materializer Registry
    # ─────────────────────────────────────────────────────────────────────────

    def register_materializer(
        self,
        object_class: NameArg,
        materializer_class: NameArg,
    ) -> None:
        """Register a materializer for an object class.

        Args:
            object_class: Object class(es) to register the materializer for.
            materializer_class: Materializer class(es) to register.
        """
        obj_classes = self._normalize_to_list(object_class)
        mat_classes = self._normalize_to_list(materializer_class)

        if len(obj_classes) != len(mat_classes):
            raise ValueError("object_class and materializer_class list lengths must match")

        try:
            if not self._metadata_path.exists():
                metadata = {"materializers": {}}
            else:
                with open(self._metadata_path, "r") as f:
                    metadata = json.load(f)

            if "materializers" not in metadata:
                metadata["materializers"] = {}

            for obj_cls, mat_cls in zip(obj_classes, mat_classes):
                metadata["materializers"][obj_cls] = mat_cls

            with open(self._metadata_path, "w") as f:
                json.dump(metadata, f)

        except Exception as e:
            self.logger.error(f"Error registering materializers: {e}")
            raise e
        else:
            self.logger.debug(f"Registered {len(obj_classes)} materializer(s)")

    def registered_materializer(self, object_class: str) -> str | None:
        """Get the registered materializer for an object class.

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        return self.registered_materializers().get(object_class, None)

    def registered_materializers(
        self,
        object_class: Union[str, None, List[str]] = None,
    ) -> Dict[str, str]:
        """Get all registered materializers.

        Args:
            object_class: If None, return all materializers.
                If string or list, return only matching object classes.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
        """
        try:
            if not self._metadata_path.exists():
                return {}
            with open(self._metadata_path, "r") as f:
                all_materializers = json.load(f).get("materializers", {})
        except Exception as e:
            self.logger.error(f"Error loading materializers: {e}")
            raise e

        if object_class is None:
            return all_materializers

        if isinstance(object_class, str):
            obj_classes = [object_class]
        else:
            obj_classes = object_class

        return {k: v for k, v in all_materializers.items() if k in obj_classes}
