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

from mindtrace.core import Timeout
from mindtrace.registry.backends.registry_backend import (
    ConcreteVersionArg,
    MetadataArg,
    NameArg,
    PathArg,
    RegistryBackend,
)
from mindtrace.registry.core.exceptions import (
    LockAcquisitionError,
    RegistryObjectNotFound,
)
from mindtrace.registry.core.types import OnConflict, OpResult, OpResults


class LocalRegistryBackend(RegistryBackend):
    """A simple local filesystem-based registry backend.

    All object directories and registry files are stored under a configurable base directory. The backend provides
    methods for uploading, downloading, and managing object files and metadata.
    """

    def __init__(self, uri: str | Path, lock_timeout: int = 30, **kwargs):
        """Initialize the LocalRegistryBackend.

        Args:
            uri (str | Path): The base directory path where all object files and metadata will be stored.
                              Supports "file://" URI scheme which will be automatically stripped.
            lock_timeout: Timeout in seconds for acquiring locks. Default 30. Use shorter values in tests.
            **kwargs: Additional keyword arguments for the RegistryBackend.
        """
        if isinstance(uri, str) and uri.startswith("file://"):
            uri = uri[len("file://") :]
        super().__init__(uri=uri, **kwargs)
        self._uri = Path(uri).expanduser().resolve()
        self._uri.mkdir(parents=True, exist_ok=True)
        self._metadata_path = self._uri / "registry_metadata.json"
        self._lock_timeout = lock_timeout
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
        return self.uri / f"_meta_{name.replace(':', '%3A')}@{version}.yaml"

    def _object_metadata_prefix(self, name: str) -> str:
        """Generate the metadata file prefix for listing versions of an object.

        Args:
            name: Name of the object.

        Returns:
            Metadata file prefix (e.g., "_meta_object_name@").
        """
        return f"_meta_{name.replace(':', '%3A')}@"

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
        try:
            lock_dir = self._lock_dir(key)
            lock_dir.mkdir(parents=True, exist_ok=True)

            exclusive_path = self._exclusive_lock_path(key)
            expires_at = time.time() + timeout

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
                except FileNotFoundError:
                    pass
                except (json.JSONDecodeError, IOError):
                    return False
                else:
                    if meta.get("lock_id") != lock_id:
                        return False
                    exclusive_path.unlink()
                    self._cleanup_lock_dir(key)
                    return True

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
    def _internal_lock(self, key: str, timeout: int | None = None, shared: bool = False):
        """Context manager for internal locking.

        Args:
            key: The key to acquire the lock for.
            timeout: The timeout in seconds for the lock. If None, uses self._lock_timeout.
            shared: If True, acquire a shared (read) lock. If False, acquire an exclusive (write) lock.

        Yields:
            None

        Raises:
            LockAcquisitionError: If the lock cannot be acquired within the timeout period.
        """
        if timeout is None:
            timeout = self._lock_timeout
        timeout_handler = Timeout(
            timeout=timeout,
            retry_delay=0.1,  # Short retry delay for lock acquisition
            exceptions=(LockAcquisitionError,),  # Only retry on LockAcquisitionError
            progress_bar=False,  # Don't show progress bar for lock acquisition
            desc=f"Acquiring {'shared ' if shared else ''}lock for {key}",
        )
        lock_id = str(uuid.uuid4())

        def acquire_lock_with_retry():
            if not self._acquire_internal_lock(key, lock_id, timeout, shared=shared):
                lock_type = "shared" if shared else "exclusive"
                raise LockAcquisitionError(f"Cannot acquire {lock_type} lock for {key}")
            return True

        try:
            timeout_handler.run(acquire_lock_with_retry)
        except TimeoutError as e:
            # Convert TimeoutError to LockAcquisitionError for semantic clarity
            lock_type = "shared" if shared else "exclusive"
            raise LockAcquisitionError(f"Timed out acquiring {lock_type} lock for {key} after {timeout}s") from e
        try:
            yield
        finally:
            self._release_internal_lock(key, lock_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Artifact + Metadata Operations
    # ─────────────────────────────────────────────────────────────────────────

    def create_direct_upload_target(
        self,
        upload_id: str,
        *,
        content_type: str = "application/octet-stream",
        expiration_minutes: int = 60,
    ) -> dict[str, Any]:
        staging_dir = self.uri / "_direct_uploads" / upload_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        upload_path = staging_dir / "data.txt"
        return {
            "upload_method": "local_path",
            "upload_url": None,
            "upload_path": str(upload_path),
            "upload_headers": {},
            "staged_target": {"kind": "local_file", "path": str(upload_path)},
            "content_type": content_type,
            "expiration_minutes": expiration_minutes,
        }

    def inspect_direct_upload_target(self, staged_target: dict[str, Any]) -> dict[str, Any]:
        upload_path = Path(staged_target.get("path", ""))
        exists = staged_target.get("kind") == "local_file" and upload_path.exists()
        return {
            "exists": exists,
            "size_bytes": upload_path.stat().st_size if exists else None,
            "path": str(upload_path) if upload_path else None,
        }

    def cleanup_direct_upload_target(self, staged_target: dict[str, Any]) -> bool:
        upload_path = Path(staged_target.get("path", ""))
        if staged_target.get("kind") != "local_file":
            return False
        try:
            if upload_path.exists():
                upload_path.unlink()
            if upload_path.parent.exists():
                shutil.rmtree(upload_path.parent, ignore_errors=True)
            return True
        except Exception:
            return False

    def commit_direct_upload(
        self,
        name: str,
        version: str,
        staged_target: dict[str, Any],
        metadata: dict[str, Any],
        on_conflict: str = OnConflict.SKIP,
    ) -> OpResult:
        upload_path = Path(staged_target.get("path", ""))
        if staged_target.get("kind") != "local_file" or not upload_path.exists():
            return OpResult.failed(name, version, FileNotFoundError(f"Staged upload not found for {name}@{version}"))

        try:
            self.validate_object_name(name)
            with self._internal_lock(f"{name}@{version}"):
                artifact_dst = self._full_path(self._object_key(name, version))
                meta_path = self._object_metadata_path(name, version)

                is_overwrite = False
                if meta_path.exists():
                    if on_conflict == OnConflict.OVERWRITE:
                        if artifact_dst.exists():
                            shutil.rmtree(artifact_dst, ignore_errors=True)
                        meta_path.unlink(missing_ok=True)
                        is_overwrite = True
                    else:
                        return OpResult.skipped(name, version)

                artifact_dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(upload_path, artifact_dst / "data.txt")

                prepared_metadata = dict(metadata)
                prepared_metadata["path"] = str(artifact_dst)
                with open(meta_path, "w") as f:
                    yaml.safe_dump(prepared_metadata, f)

                self.cleanup_direct_upload_target(staged_target)
                if is_overwrite:
                    return OpResult.overwritten(name, version)
                return OpResult.success(name, version)
        except Exception as e:
            return OpResult.failed(name, version, e)

    def push(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        metadata: MetadataArg,
        on_conflict: str = OnConflict.SKIP,
        acquire_lock: bool = False,
    ) -> OpResults:
        """Atomically push artifacts and metadata with rollback on failure.

        Single item operations raise exceptions on error/conflict.
        Batch operations return OpResults without raising, letting caller inspect results.

        Args:
            name: Object name(s). Single string or list.
            version: Version string(s), None for auto-increment, or list.
            local_path: Local source directory/directories to upload from.
            metadata: Metadata dict(s) to store.
            on_conflict: Behavior when version exists.
                "skip" (default): Single ops raise RegistryVersionConflict, batch ops return skipped result.
                "overwrite": Replace existing version.
            acquire_lock: Accepted for API compatibility. Local backend always uses
                internal locking regardless of this parameter.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
            - OpResult.failed() on failure
        """
        names, versions, paths, metadatas = self._prepare_inputs(name, version, local_path, metadata)
        results = OpResults()

        for obj_name, obj_version, obj_path, obj_meta in zip(names, versions, paths, metadatas):
            try:
                self.validate_object_name(obj_name)

                # Lock on the specific object@version for proper coordination with pull() and delete()
                # Registry resolves versions before calling backend, so obj_version is always concrete
                with self._internal_lock(f"{obj_name}@{obj_version}"):
                    artifact_dst = self._full_path(self._object_key(obj_name, obj_version))
                    meta_path = self._object_metadata_path(obj_name, obj_version)

                    # Check for existing version
                    is_overwrite = False
                    if meta_path.exists():
                        if on_conflict == OnConflict.OVERWRITE:
                            # Remove existing artifacts and metadata before overwriting
                            if artifact_dst.exists():
                                shutil.rmtree(artifact_dst, ignore_errors=True)
                            meta_path.unlink(missing_ok=True)
                            is_overwrite = True
                        else:
                            # on_conflict == "skip" - return skipped result
                            results.add(OpResult.skipped(obj_name, obj_version))
                            continue

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

                        if is_overwrite:
                            results.add(OpResult.overwritten(obj_name, obj_version))
                        else:
                            results.add(OpResult.success(obj_name, obj_version))

                    except Exception as e:
                        # Rollback: remove artifacts and metadata
                        if artifact_dst.exists():
                            shutil.rmtree(artifact_dst, ignore_errors=True)
                        if meta_path.exists():
                            meta_path.unlink(missing_ok=True)
                        raise RuntimeError(f"Push failed for {obj_name}@{obj_version}: {e}") from e

            except Exception as e:
                results.add(OpResult.failed(obj_name, obj_version, e))

        return results

    def pull(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        acquire_lock: bool = False,
        metadata: MetadataArg = None,
    ) -> OpResults:
        """Copy a directory from the backend store to a local path.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            local_path: Destination directory path(s) to copy to.
            acquire_lock: If True, acquire a shared (read) lock before pulling.
                This is needed for mutable registries to prevent read-write races.
                Default is False (no locking, for immutable registries).
            metadata: Optional pre-fetched metadata (unused for local backend,
                but accepted for API compatibility with remote backends).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        # Validate inputs (metadata required for API consistency, but not used by local backend)
        names, versions, paths, _ = self._prepare_inputs(name, version, local_path, metadata)

        results = OpResults()

        for obj_name, obj_version, dest_path in zip(names, versions, paths):
            try:
                # No name validation needed - Registry already fetched metadata,
                # so the object exists with this name (name was validated at push time)

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

                results.add(OpResult.success(obj_name, obj_version))

            except Exception as e:
                results.add(OpResult.failed(obj_name, obj_version, e))

        return results

    def delete(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        acquire_lock: bool = False,
    ) -> OpResults:
        """Delete a directory from the backend store.

        Also removes empty parent directories.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            acquire_lock: Accepted for API compatibility. Local backend always uses
                internal locking regardless of this parameter.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        names = self._to_list(name)
        versions = self._to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results = OpResults()

        for obj_name, obj_version in zip(names, versions):
            try:
                with self._internal_lock(f"{obj_name}@{obj_version}"):
                    target = self._full_path(self._object_key(obj_name, obj_version))
                    meta_path = self._object_metadata_path(obj_name, obj_version)
                    # Delete directory
                    self.logger.debug(f"Deleting directory: {target}")
                    if target.exists():
                        shutil.rmtree(target)

                    # Delete metadata
                    self.logger.debug(f"Deleting metadata file: {meta_path}")
                    if meta_path.exists():
                        meta_path.unlink()

                    # Cleanup parent if empty (race-safe under concurrent deletes).
                    # Another thread/process may remove `parent` between checks/iteration.
                    parent = target.parent
                    try:
                        if not any(parent.iterdir()):
                            self.logger.debug(f"Removing empty parent directory: {parent}")
                            try:
                                parent.rmdir()
                            except Exception:
                                pass
                    except FileNotFoundError:
                        # Parent already removed by a concurrent delete; this is fine.
                        pass

                results.add(OpResult.success(obj_name, obj_version))
            except Exception as e:
                results.add(OpResult.failed(obj_name, obj_version, e))

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata-Only Operations
    # ─────────────────────────────────────────────────────────────────────────

    def save_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        metadata: Union[dict, List[dict]],
        on_conflict: str = OnConflict.SKIP,
    ) -> OpResults:
        """Save metadata for object version(s).

        Args:
            name: Name of the object(s).
            version: Version of the object(s).
            metadata: Metadata to save (single dict for one object, or list of dicts).
            on_conflict: Behavior when version exists.
                "skip" (default): Return skipped result.
                "overwrite": Replace existing version.

        Returns:
            OpResults with status for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
        """
        names = self._to_list(name)
        versions = self._to_list(version)
        metadatas = [metadata] if isinstance(metadata, dict) else list(metadata)

        n = len(names)
        if not (len(versions) == len(metadatas) == n):
            raise ValueError(
                f"Input lengths must match: names={n}, versions={len(versions)}, metadata={len(metadatas)}"
            )

        results = OpResults()

        for obj_name, obj_version, obj_meta in zip(names, versions, metadatas):
            self.validate_object_name(obj_name)
            meta_path = self._object_metadata_path(obj_name, obj_version)

            if meta_path.exists():
                if on_conflict == OnConflict.OVERWRITE:
                    self.logger.debug(f"Overwriting metadata at {meta_path}: {obj_meta}")
                    with open(meta_path, "w") as f:
                        yaml.safe_dump(obj_meta, f)
                    results.add(OpResult.overwritten(obj_name, obj_version))
                else:
                    # on_conflict == "skip" - return skipped result
                    results.add(OpResult.skipped(obj_name, obj_version))
            else:
                self.logger.debug(f"Saving metadata to {meta_path}: {obj_meta}")
                with open(meta_path, "w") as f:
                    yaml.safe_dump(obj_meta, f)
                results.add(OpResult.success(obj_name, obj_version))

        return results

    def fetch_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        """Load metadata for object version(s).

        Args:
            name: Name of the object(s).
            version: Version of the object(s).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success(metadata=...) on success
            - OpResult.failed() on failure (not found or error)
        """
        names = self._to_list(name)
        versions = self._to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results = OpResults()

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
                    results.add(
                        OpResult.failed(
                            obj_name,
                            obj_version,
                            RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found (empty metadata)"),
                        )
                    )
                    continue

                # Add the path to the object directory to the metadata
                object_key = self._object_key(obj_name, obj_version)
                object_path = self._full_path(object_key)
                meta["path"] = str(object_path)

                self.logger.debug(f"Loaded metadata: {meta}")
                results.add(OpResult.success(obj_name, obj_version, metadata=meta))

            except FileNotFoundError:
                results.add(
                    OpResult.failed(
                        obj_name,
                        obj_version,
                        RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found"),
                    )
                )
            except Exception as e:
                self.logger.warning(f"Error fetching metadata for {obj_name}@{obj_version}: {e}")
                results.add(OpResult.failed(obj_name, obj_version, e))

        return results

    def delete_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        """Delete metadata for object version(s).

        Args:
            name: Name of the object(s).
            version: Version of the object(s).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        names = self._to_list(name)
        versions = self._to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results = OpResults()

        for obj_name, obj_version in zip(names, versions):
            try:
                meta_path = self._object_metadata_path(obj_name, obj_version)
                self.logger.debug(f"Deleting metadata file: {meta_path}")
                if meta_path.exists():
                    meta_path.unlink()
                results.add(OpResult.success(obj_name, obj_version))
            except Exception as e:
                results.add(OpResult.failed(obj_name, obj_version, e))

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
            name = name_part.replace("%3A", ":")
            objects.add(name)

        return sorted(list(objects))

    def list_versions(self, name: NameArg) -> Dict[str, List[str]]:
        """List all versions available for the given object(s).

        Args:
            name: Name of the object(s)

        Returns:
            Dict mapping object names to sorted lists of version strings.
        """
        names = self._to_list(name)
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
        names = self._to_list(name)
        versions = self._to_list(version)

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

        Uses a file lock to prevent concurrent read-modify-write races
        on the shared registry metadata file.

        Args:
            object_class: Object class(es) to register the materializer for.
            materializer_class: Materializer class(es) to register.
        """
        obj_classes = self._to_list(object_class)
        mat_classes = self._to_list(materializer_class)

        if len(obj_classes) != len(mat_classes):
            raise ValueError("object_class and materializer_class list lengths must match")

        with self._internal_lock("_materializer_registry"):
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
