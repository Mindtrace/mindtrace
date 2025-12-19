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
from typing import Any, Dict, List, Tuple, Union

import yaml

# Import appropriate locking mechanism based on OS
if platform.system() == "Windows":
    import msvcrt

    fcntl = None
else:
    msvcrt = None

from mindtrace.registry.backends.registry_backend import (
    ConcreteVersionArg,
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

    def _lock_dir(self, key: str) -> Path:
        """Get the directory for lock files for a given key."""
        return self._full_path(f"_locks_{key}")

    def _exclusive_lock_path(self, key: str) -> Path:
        """Get the path for an exclusive lock file."""
        return self._lock_dir(key) / "_exclusive"

    def _shared_lock_path(self, key: str, lock_id: str) -> Path:
        """Get the path for a shared lock file."""
        return self._lock_dir(key) / f"_shared_{lock_id}"

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Locking
    # ─────────────────────────────────────────────────────────────────────────

    def _acquire_internal_lock(self, key: str, lock_id: str, timeout: int, shared: bool = False) -> bool:
        """Acquire internal lock using one-file-per-holder approach.

        Supports both shared (read) and exclusive (write) locks:
        - Shared locks: Multiple readers can hold shared locks simultaneously
        - Exclusive locks: Only one writer can hold an exclusive lock, and no readers

        Lock files are stored in a directory per key:
        - _locks_{key}/_exclusive           - exclusive lock file
        - _locks_{key}/_shared_{lock_id}    - shared lock file per holder

        Args:
            key: The key to acquire the lock for.
            lock_id: The ID of the lock to acquire.
            timeout: The timeout in seconds for the lock.
            shared: If True, acquire a shared (read) lock. If False, acquire an exclusive (write) lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        lock_dir = self._lock_dir(key)
        lock_dir.mkdir(parents=True, exist_ok=True)

        exclusive_path = self._exclusive_lock_path(key)
        expires_at = time.time() + timeout

        try:
            if shared:
                # For shared lock: check no exclusive lock exists, then create shared lock file
                # First, clean up expired exclusive lock if any
                if exclusive_path.exists():
                    try:
                        with open(exclusive_path, "r") as f:
                            meta = json.loads(f.read().strip())
                        if time.time() > meta.get("expires_at", 0):
                            exclusive_path.unlink()
                        else:
                            # Valid exclusive lock exists - cannot acquire shared
                            return False
                    except (json.JSONDecodeError, IOError, FileNotFoundError):
                        # Corrupted or deleted - try to clean up
                        try:
                            exclusive_path.unlink()
                        except FileNotFoundError:
                            pass

                # Create shared lock file atomically
                shared_path = self._shared_lock_path(key, lock_id)
                try:
                    if platform.system() == "Windows":
                        fd = os.open(shared_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    else:
                        fd = os.open(shared_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)

                    with os.fdopen(fd, "w") as f:
                        f.write(json.dumps({"lock_id": lock_id, "expires_at": expires_at}))
                        f.flush()
                        os.fsync(f.fileno())

                    # Double-check no exclusive lock was created while we were writing
                    if exclusive_path.exists():
                        try:
                            with open(exclusive_path, "r") as f:
                                meta = json.loads(f.read().strip())
                            if time.time() <= meta.get("expires_at", 0):
                                # Exclusive lock appeared - rollback our shared lock
                                shared_path.unlink()
                                return False
                        except (json.JSONDecodeError, IOError, FileNotFoundError):
                            pass

                    return True
                except FileExistsError:
                    # Our lock file already exists (shouldn't happen with UUID)
                    return True

            else:
                # For exclusive lock: check no locks exist, then create exclusive lock file
                # First, clean up expired locks
                self._cleanup_expired_locks(key)

                # Check for any existing shared locks
                for f in lock_dir.glob("_shared_*"):
                    try:
                        with open(f, "r") as fp:
                            meta = json.loads(fp.read().strip())
                        if time.time() <= meta.get("expires_at", 0):
                            # Valid shared lock exists - cannot acquire exclusive
                            return False
                    except (json.JSONDecodeError, IOError, FileNotFoundError):
                        pass

                # Try to create exclusive lock atomically
                try:
                    if platform.system() == "Windows":
                        fd = os.open(exclusive_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    else:
                        fd = os.open(exclusive_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)

                    with os.fdopen(fd, "w") as f:
                        f.write(json.dumps({"lock_id": lock_id, "expires_at": expires_at}))
                        f.flush()
                        os.fsync(f.fileno())
                    return True

                except FileExistsError:
                    # Exclusive lock exists - check if expired
                    try:
                        with open(exclusive_path, "r") as f:
                            meta = json.loads(f.read().strip())
                        if time.time() > meta.get("expires_at", 0):
                            # Expired - remove and retry
                            exclusive_path.unlink()
                            return self._acquire_internal_lock(key, lock_id, timeout, shared=False)
                    except (json.JSONDecodeError, IOError, FileNotFoundError):
                        pass
                    return False

        except Exception as e:
            self.logger.error(f"Error acquiring {'shared' if shared else 'exclusive'} lock for {key}: {e}")
            return False

    def _cleanup_expired_locks(self, key: str) -> None:
        """Remove expired lock files for a key."""
        lock_dir = self._lock_dir(key)
        if not lock_dir.exists():
            return

        now = time.time()
        for lock_file in lock_dir.iterdir():
            try:
                with open(lock_file, "r") as f:
                    meta = json.loads(f.read().strip())
                if now > meta.get("expires_at", 0):
                    lock_file.unlink()
            except (json.JSONDecodeError, IOError, FileNotFoundError):
                # Corrupted or already deleted - try to clean up
                try:
                    lock_file.unlink()
                except FileNotFoundError:
                    pass

    def _release_internal_lock(self, key: str, lock_id: str) -> bool:
        """Release internal lock by removing the appropriate lock file.

        For exclusive locks: removes _exclusive file if we own it.
        For shared locks: removes our _shared_{lock_id} file.

        Args:
            key: The key to release the lock for.
            lock_id: The ID of the lock to release.

        Returns:
            True if the lock was released, False otherwise.
        """
        try:
            # Try to release exclusive lock first
            exclusive_path = self._exclusive_lock_path(key)
            if exclusive_path.exists():
                try:
                    with open(exclusive_path, "r") as f:
                        meta = json.loads(f.read().strip())
                    if meta.get("lock_id") == lock_id:
                        exclusive_path.unlink()
                        self._cleanup_lock_dir(key)
                        return True
                except (json.JSONDecodeError, IOError, FileNotFoundError):
                    pass

            # Try to release shared lock
            shared_path = self._shared_lock_path(key, lock_id)
            if shared_path.exists():
                shared_path.unlink()
                self._cleanup_lock_dir(key)
                return True

            # Lock file doesn't exist - consider it released
            return True

        except Exception as e:
            self.logger.error(f"Error releasing lock for {key}: {e}")
            return False

    def _cleanup_lock_dir(self, key: str) -> None:
        """Remove lock directory if empty."""
        lock_dir = self._lock_dir(key)
        try:
            if lock_dir.exists() and not any(lock_dir.iterdir()):
                lock_dir.rmdir()
        except (OSError, FileNotFoundError):
            pass

    @contextmanager
    def _internal_lock(self, key: str, timeout: int = 30, shared: bool = False):
        """Context manager for internal locking.

        Args:
            key: The key to acquire the lock for.
            timeout: The timeout in seconds for the lock.
            shared: If True, acquire a shared (read) lock. If False, acquire an exclusive (write) lock.

        Yields:
            None

        Raises:
            LockAcquisitionError: If the lock cannot be acquired.
        """
        lock_id = str(uuid.uuid4())
        if not self._acquire_internal_lock(key, lock_id, timeout, shared=shared):
            lock_type = "shared" if shared else "exclusive"
            raise LockAcquisitionError(f"Cannot acquire {lock_type} lock for {key}")
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
        on_error: str = "raise",
        acquire_lock: bool = False,
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Atomically push artifacts and metadata with rollback on failure.

        Args:
            name: Object name(s). Single string or list.
            version: Version string(s), None for auto-increment, or list.
            local_path: Local source directory/directories to upload from.
            metadata: Metadata dict(s) to store.
            on_conflict: Behavior when version exists. "error" raises RegistryVersionConflict,
                "skip" silently skips, "overwrite" replaces existing. Default is "error".
            on_error: Error handling strategy.
                "raise" (default): First error stops and raises exception.
                "skip": Continue on errors, report status in return dict.
            acquire_lock: Accepted for API compatibility. Local backend always uses
                internal locking regardless of this parameter.

        Returns:
            Dict mapping (name, resolved_version) to status dict:
            - {"status": "ok"} on success
            - {"status": "skipped"} when on_conflict="skip" and version exists
            - {"status": "overwritten"} when on_conflict="overwrite" and version existed
            - {"status": "error", "error": "<ErrorType>", "message": "..."} on failure
        """
        entries = self._normalize_inputs(name, version, local_path, metadata)
        results: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for obj_name, obj_version, obj_path, obj_meta in entries:
            resolved_version = None
            try:
                self.validate_object_name(obj_name)

                # Resolve version first (outside lock to avoid deadlock with list_versions)
                resolved_version = self._resolve_version(obj_name, obj_version)

                # Lock on the specific object@version for proper coordination with pull() and delete()
                with self._internal_lock(f"{obj_name}@{resolved_version}"):
                    artifact_dst = self._full_path(self._object_key(obj_name, resolved_version))
                    meta_path = self._object_metadata_path(obj_name, resolved_version)

                    # Check for existing version
                    is_overwrite = False
                    if meta_path.exists():
                        if on_conflict == "skip":
                            results[(obj_name, resolved_version)] = {"status": "skipped"}
                            continue
                        elif on_conflict == "overwrite":
                            # Remove existing artifacts and metadata before overwriting
                            if artifact_dst.exists():
                                shutil.rmtree(artifact_dst, ignore_errors=True)
                            meta_path.unlink(missing_ok=True)
                            is_overwrite = True
                        else:
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

                        results[(obj_name, resolved_version)] = {"status": "overwritten" if is_overwrite else "ok"}

                    except Exception as e:
                        # Rollback: remove artifacts and metadata
                        if artifact_dst.exists():
                            shutil.rmtree(artifact_dst, ignore_errors=True)
                        if meta_path.exists():
                            meta_path.unlink(missing_ok=True)
                        raise RuntimeError(f"Push failed for {obj_name}@{resolved_version}: {e}") from e

            except Exception as e:
                if on_error == "raise":
                    raise
                key = (obj_name, resolved_version or obj_version or "unknown")
                results[key] = {
                    "status": "error",
                    "error": type(e).__name__,
                    "message": str(e),
                }

        return results

    def pull(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        acquire_lock: bool = False,
        on_error: str = "raise",
        metadata: MetadataArg = None,
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Copy a directory from the backend store to a local path.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            local_path: Destination directory path(s) to copy to.
            acquire_lock: If True, acquire a shared (read) lock before pulling.
                This is needed for mutable registries to prevent read-write races.
                Default is False (no locking, for immutable registries).
            on_error: Error handling strategy.
                "raise" (default): First error stops and raises exception.
                "skip": Continue on errors, report status in return dict.
            metadata: Optional pre-fetched metadata (unused for local backend,
                but accepted for API compatibility with remote backends).

        Returns:
            Dict mapping (name, version) to status dict:
            - {"status": "ok"} on success
            - {"status": "error", "error": "<ErrorType>", "message": "..."} on failure
        """
        # Note: metadata parameter is ignored for local backend since we copy
        # the entire directory. Remote backends use it for _files manifest.
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)
        paths = self._normalize_paths(local_path, len(names))

        if len(names) != len(versions) or len(names) != len(paths):
            raise ValueError("Input list lengths must match")

        results: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for obj_name, obj_version, dest_path in zip(names, versions, paths):
            try:
                src = self._full_path(self._object_key(obj_name, obj_version))

                if not src.exists():
                    raise RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found.")

                if acquire_lock:
                    # Acquire shared lock for read operation in mutable registries
                    with self._internal_lock(f"{obj_name}@{obj_version}", shared=True):
                        self.logger.debug(f"Downloading directory from {src} to {dest_path} (with shared lock)")
                        shutil.copytree(src, dest_path, dirs_exist_ok=True)
                        self.logger.debug(f"Download complete. Contents: {list(Path(dest_path).rglob('*'))}")
                else:
                    # No locking for immutable registries (fast path)
                    self.logger.debug(f"Downloading directory from {src} to {dest_path}")
                    shutil.copytree(src, dest_path, dirs_exist_ok=True)
                    self.logger.debug(f"Download complete. Contents: {list(Path(dest_path).rglob('*'))}")

                results[(obj_name, obj_version)] = {"status": "ok"}

            except Exception as e:
                if on_error == "raise":
                    raise
                results[(obj_name, obj_version)] = {
                    "status": "error",
                    "error": type(e).__name__,
                    "message": str(e),
                }

        return results

    def delete(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        on_error: str = "raise",
        acquire_lock: bool = False,
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Delete a directory from the backend store.

        Also removes empty parent directories.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            on_error: Error handling strategy.
                "raise" (default): First error stops and raises exception.
                "skip": Continue on errors, report status in return dict.
            acquire_lock: Accepted for API compatibility. Local backend always uses
                internal locking regardless of this parameter.

        Returns:
            Dict mapping (name, version) to status dict:
            - {"status": "ok"} on success
            - {"status": "error", "error": "<ErrorType>", "message": "..."} on failure
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for obj_name, obj_version in zip(names, versions):
            try:
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

                results[(obj_name, obj_version)] = {"status": "ok"}
            except Exception as e:
                if on_error == "raise":
                    raise
                results[(obj_name, obj_version)] = {
                    "status": "error",
                    "error": type(e).__name__,
                    "message": str(e),
                }

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata-Only Operations
    # ─────────────────────────────────────────────────────────────────────────

    def save_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        metadata: Union[dict, List[dict]],
    ) -> None:
        """Save metadata for a object version.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).
            metadata: Metadata to save (single dict for one object, or list of dicts).
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        # Validate metadata - must be list with matching length for multiple objects
        if isinstance(metadata, dict):
            if len(names) != 1:
                raise ValueError(
                    "metadata must be a list of dicts when saving multiple objects. "
                    "Use metadata=[meta_dict, ...] with one dict per object."
                )
            metadatas = [metadata]
        else:
            metadatas = list(metadata)
            if len(metadatas) != len(names):
                raise ValueError(f"metadata list length ({len(metadatas)}) must match number of objects ({len(names)})")

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
        version: ConcreteVersionArg,
        on_error: str = "skip",
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Load metadata for a object version.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).
            on_error: Behavior when fetching individual metadata fails.
                "skip" (default): Skip failed entries, return partial results.
                "raise": Raise the exception immediately.

        Returns:
            Dict mapping (name, version) tuples to status dicts:
            - {"status": "ok", "metadata": {...}} on success
            - {"status": "error", "error": "<ErrorType>", "message": "..."} on failure
            Missing entries (FileNotFoundError) are omitted from the result.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], Dict[str, Any]] = {}

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
                results[(obj_name, obj_version)] = {"status": "ok", "metadata": meta}

            except FileNotFoundError:
                continue  # Always skip missing entries
            except Exception as e:
                if on_error == "raise":
                    raise
                # on_error == "skip": log and continue
                self.logger.warning(f"Error fetching metadata for {obj_name}@{obj_version}: {e}")
                results[(obj_name, obj_version)] = {
                    "status": "error",
                    "error": type(e).__name__,
                    "message": str(e),
                }

        return results

    def delete_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        on_error: str = "raise",
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Delete metadata for a object version.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).
            on_error: Error handling strategy.
                "raise" (default): First error stops and raises exception.
                "skip": Continue on errors, report status in return dict.

        Returns:
            Dict mapping (name, version) to status dict:
            - {"status": "ok"} on success
            - {"status": "error", "error": "<ErrorType>", "message": "..."} on failure
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for obj_name, obj_version in zip(names, versions):
            try:
                meta_path = self._object_metadata_path(obj_name, obj_version)
                self.logger.debug(f"Deleting metadata file: {meta_path}")
                if meta_path.exists():
                    meta_path.unlink()
                results[(obj_name, obj_version)] = {"status": "ok"}
            except Exception as e:
                if on_error == "raise":
                    raise
                results[(obj_name, obj_version)] = {
                    "status": "error",
                    "error": type(e).__name__,
                    "message": str(e),
                }

        return results

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
        version: ConcreteVersionArg,
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
