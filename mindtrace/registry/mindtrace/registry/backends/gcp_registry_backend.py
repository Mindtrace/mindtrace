"""Google Cloud Storage-based registry backend.

Uses GCS for both artifact and metadata storage as well as locks.
"""

import json
import os
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple, Union

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
from mindtrace.registry.core.types import OnConflict, OpResult, OpResults
from mindtrace.storage import GCSStorageHandler, Status, StringResult


class GCPRegistryBackend(RegistryBackend):
    """A Google Cloud Storage-based registry backend.

    This backend stores objects and metadata in a GCS bucket, providing distributed
    storage capabilities with atomic operations via generation numbers.

    Locking strategy:
    - Writers (push/delete): Use exclusive locks when acquire_lock=True (mutable registries)
    - Readers (pull): No locking. Metadata is written LAST, so if readable, files exist.

    Atomicity for immutable registries (acquire_lock=False):
    - Files uploaded with generation_match=0 (fail if exists)
    - Metadata written LAST with generation_match=0 (the "commit point")

    Uses `_files` manifest from metadata to avoid expensive blob listing on pull.

    Usage Example::

        from mindtrace.registry import Registry, GCPRegistryBackend

        gcp_backend = GCPRegistryBackend(
            uri="gs://my-registry-bucket",
            project_id="my-project",
            bucket_name="my-registry-bucket",
            credentials_path="/path/to/service-account.json"
        )
        registry = Registry(backend=gcp_backend)
    """

    def __init__(
        self,
        uri: str | Path | None = None,
        *,
        project_id: str,
        bucket_name: str,
        credentials_path: str | None = None,
        prefix: str = "",
        max_workers: int = 4,
        **kwargs,
    ):
        """Initialize the GCPRegistryBackend.

        Args:
            uri: The base URI for the registry (e.g., "gs://my-bucket/prefix").
            project_id: GCP project ID.
            bucket_name: GCS bucket name.
            credentials_path: Optional path to service account JSON file.
            prefix: Optional prefix (subfolder) within the bucket for all registry objects.
            max_workers: Maximum number of parallel workers for batch operations. Default is 4.
            **kwargs: Additional keyword arguments for the RegistryBackend.
        """
        super().__init__(uri=uri, **kwargs)
        self._prefix = prefix.strip("/") if prefix else ""
        self._uri = Path(uri or f"gs://{bucket_name}/{self._prefix}".rstrip("/"))
        self._metadata_path = self._prefixed("registry_metadata.json")
        self._max_workers = max_workers
        self.logger.debug(f"Initializing GCPBackend with uri: {self._uri}, prefix: {self._prefix}")

        self.gcs = GCSStorageHandler(
            bucket_name=bucket_name,
            project_id=project_id,
            credentials_path=credentials_path,
            ensure_bucket=True,
            create_if_missing=True,
        )

        self._ensure_metadata_file()

    def _prefixed(self, path: str) -> str:
        """Add prefix to a path if prefix is set."""
        if self._prefix:
            return f"{self._prefix}/{path}"
        return path

    @property
    def uri(self) -> Path:
        """The resolved base URI for the backend."""
        return self._uri

    @property
    def metadata_path(self) -> Path:
        """The resolved metadata file path for the backend."""
        return Path(self._metadata_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Path Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_metadata_file(self):
        """Ensure the metadata file exists in the bucket."""
        try:
            exists = self.gcs.exists(self._metadata_path)
        except Exception:
            exists = False
        if not exists:
            data = json.dumps({"materializers": {}})
            self.gcs.upload_string(data, self._metadata_path)

    def _object_key(self, name: str, version: str) -> str:
        """Convert object name and version to a storage key."""
        return self._prefixed(f"objects/{name}/{version}")

    def _object_metadata_path(self, name: str, version: str) -> str:
        """Generate the metadata file path for an object version."""
        return self._prefixed(f"_meta_{name.replace(':', '_')}@{version}.json")

    def _object_metadata_prefix(self, name: str) -> str:
        """Generate the metadata file prefix for listing versions."""
        return self._prefixed(f"_meta_{name.replace(':', '_')}@")

    def _lock_path(self, key: str) -> str:
        """Get the path for a write lock file."""
        return self._prefixed(f"_lock_{key.replace('/', '_').replace('@', '_')}")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Locking (exclusive only, for mutable registry writes)
    # ─────────────────────────────────────────────────────────────────────────

    def _acquire_lock(self, key: str, lock_id: str, timeout: int = 30) -> bool:
        """Acquire exclusive lock using atomic GCS operations.

        Args:
            key: The key to acquire the lock for.
            lock_id: Unique identifier for this lock holder.
            timeout: Lock expiration in seconds.

        Returns:
            True if lock acquired, False otherwise.
        """
        lock_path = self._lock_path(key)
        expires_at = time.time() + timeout
        lock_data = json.dumps({"lock_id": lock_id, "expires_at": expires_at})

        try:
            # Try atomic create (generation_match=0 = only if doesn't exist)
            result = self.gcs.upload_string(lock_data, lock_path, if_generation_match=0)
            if result.ok:
                return True

            # Lock exists - check if expired
            download_result = self.gcs.download_string(lock_path)
            if download_result.status == Status.NOT_FOUND:
                # Lock deleted between our attempts, retry create
                retry_result = self.gcs.upload_string(lock_data, lock_path, if_generation_match=0)
                return retry_result.ok

            if not download_result.ok:
                return False

            existing = json.loads(download_result.content.decode("utf-8"))
            if time.time() < existing.get("expires_at", 0):
                return False  # Lock still valid

            # Lock expired - delete it and try to create a new one
            self.gcs.delete(lock_path)
            takeover_result = self.gcs.upload_string(lock_data, lock_path, if_generation_match=0)
            return takeover_result.ok

        except Exception as e:
            self.logger.error(f"Error acquiring lock for {key}: {e}")
            return False

    def _release_lock(self, key: str, lock_id: str) -> None:
        """Release write lock if we own it."""
        lock_path = self._lock_path(key)
        try:
            # Verify ownership before deleting
            result = self.gcs.download_string(lock_path)
            if result.ok:
                data = json.loads(result.content.decode("utf-8"))
                if data.get("lock_id") == lock_id:
                    self.gcs.delete(lock_path)
        except Exception:
            pass  # Best effort

    def _acquire_locks_batch(self, keys: List[str], timeout: int = 30) -> Dict[str, str | None]:
        """Acquire write locks for multiple keys in parallel."""
        if not keys:
            return {}

        def try_acquire(key: str) -> Tuple[str, str | None]:
            lock_id = str(uuid.uuid4())
            if self._acquire_lock(key, lock_id, timeout):
                return (key, lock_id)
            return (key, None)

        results: Dict[str, str | None] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            for key, lock_id in executor.map(try_acquire, keys):
                results[key] = lock_id
        return results

    def _release_locks_batch(self, locks: Dict[str, str]) -> None:
        """Release multiple locks in parallel."""
        if not locks:
            return
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda kv: self._release_lock(kv[0], kv[1]), locks.items()))

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _save_metadata_single(
        self, name: str, version: str, metadata: dict, on_conflict: str = OnConflict.SKIP
    ) -> StringResult:
        """Save a single metadata file atomically.

        Args:
            name: Object name.
            version: Object version.
            metadata: Metadata dict to write.
            on_conflict: "skip" or "overwrite".

        Returns:
            StringResult with status: ok, already_exists, overwritten, or error.
        """
        meta_path = self._object_metadata_path(name, version)
        data = json.dumps(metadata)

        if on_conflict == OnConflict.OVERWRITE:
            # Check if exists first to determine status
            existed = self.gcs.exists(meta_path)
            result = self.gcs.upload_string(data, meta_path)
            if result.ok:
                return StringResult(
                    remote_path=meta_path,
                    status=Status.OVERWRITTEN if existed else Status.OK,
                )
            return result
        else:
            # "skip" - atomic insert with generation_match=0
            result = self.gcs.upload_string(data, meta_path, if_generation_match=0)
            if result.status == Status.ALREADY_EXISTS:
                return StringResult(
                    remote_path=meta_path,
                    status=Status.ALREADY_EXISTS,
                    error_type="PreconditionFailed",
                    error_message=f"Object {name}@{version} already exists",
                )
            return result

    # ─────────────────────────────────────────────────────────────────────────
    # Artifact + Metadata Operations (atomic)
    # ─────────────────────────────────────────────────────────────────────────

    def _push_single_object(
        self,
        obj_name: str,
        obj_version: str,
        obj_path: Path,
        obj_meta: dict,
        on_conflict: str,
        fail_if_exists: bool,
        max_workers: int = 4,
    ) -> OpResult:
        """Push a single object's files and metadata.

        Args:
            obj_name: Object name.
            obj_version: Object version.
            obj_path: Local path to upload from.
            obj_meta: Metadata dict.
            on_conflict: "error", "skip", or "overwrite".
            fail_if_exists: If True, fail if files already exist.
            max_workers: Maximum parallel workers for file uploads.

        Returns:
            OpResult indicating success, skip, overwrite, or error.
        """
        try:
            remote_key = self._object_key(obj_name, obj_version)

            # Use _files manifest from metadata if available (built by Registry),
            files_manifest = obj_meta.get("_files") if obj_meta else None
            if files_manifest is not None:
                files = [(str(obj_path / f), f"{remote_key}/{f}".replace("\\", "/")) for f in files_manifest]
            else:
                # Fallback: collect files from directory
                files = []
                for file_path in obj_path.rglob("*"):
                    if file_path.is_file():
                        relative = file_path.relative_to(obj_path).as_posix()
                        files.append((str(file_path), f"{remote_key}/{relative}"))

            # Prepare metadata with path
            prepared_meta = dict(obj_meta) if obj_meta else {}
            prepared_meta["path"] = f"gs://{self.gcs.bucket_name}/{remote_key}"

            if files:
                batch_result = self.gcs.upload_batch(
                    files, on_error="skip", fail_if_exists=fail_if_exists, max_workers=max_workers
                )

                # Check for conflicts (already_exists) or errors
                conflict_files = [r for r in batch_result.results if r.status == Status.ALREADY_EXISTS]
                error_files = [r for r in batch_result.results if r.status == Status.ERROR]

                if conflict_files:
                    # Rollback any successful uploads
                    uploaded = [r.remote_path for r in batch_result.results if r.status == Status.OK]
                    if uploaded:
                        self.gcs.delete_batch(uploaded)

                    # Return failed result - caller decides whether to raise
                    return OpResult.failed(
                        obj_name,
                        obj_version,
                        RegistryVersionConflict(f"Object {obj_name}@{obj_version} already exists"),
                    )

                if error_files:
                    # Rollback any successful uploads
                    uploaded = [r.remote_path for r in batch_result.results if r.status == Status.OK]
                    if uploaded:
                        self.gcs.delete_batch(uploaded)
                    return OpResult.failed(
                        obj_name,
                        obj_version,
                        RuntimeError(f"Failed to upload {len(error_files)} file(s): {error_files[0].error_message}"),
                    )

            # Write metadata LAST (the "commit point")
            meta_result = self._save_metadata_single(obj_name, obj_version, prepared_meta, on_conflict)

            if meta_result.status == Status.ALREADY_EXISTS:
                # Rollback uploaded files
                uploaded = [remote for _, remote in files]
                if uploaded:
                    self.gcs.delete_batch(uploaded)

                # Return failed result - caller decides whether to raise
                return OpResult.failed(
                    obj_name,
                    obj_version,
                    RegistryVersionConflict(f"Object {obj_name}@{obj_version} already exists"),
                )
            elif meta_result.status == Status.ERROR:
                # Rollback uploaded files
                uploaded = [remote for _, remote in files]
                if uploaded:
                    self.gcs.delete_batch(uploaded)
                return OpResult.failed(
                    obj_name,
                    obj_version,
                    RuntimeError(meta_result.error_message or "Metadata write failed"),
                )
            elif meta_result.status == Status.OVERWRITTEN:
                return OpResult.overwritten(obj_name, obj_version)
            else:
                return OpResult.success(obj_name, obj_version)

        except Exception as e:
            return OpResult.failed(obj_name, obj_version, e)

    def push(
        self,
        name: NameArg,
        version: VersionArg,
        local_path: PathArg,
        metadata: MetadataArg = None,
        on_conflict: str = OnConflict.SKIP,
        acquire_lock: bool = False,
        max_workers: int | None = None,
    ) -> OpResults:
        """Push artifacts and metadata to the registry.

        Objects are processed in parallel for maximum efficiency. Each object's
        push is atomic with proper rollback on failure.

        Atomicity strategy depends on acquire_lock:
        - acquire_lock=False (immutable): Use generation_match=0 on files to detect conflicts.
          If any file exists, the push fails. Metadata written LAST with generation_match=0.
        - acquire_lock=True (mutable): Acquire locks first, then overwrite files freely.

        Single item operations raise exceptions on error/conflict.
        Batch operations return OpResults without raising, letting caller inspect results.

        Args:
            name: Object name(s). Single string or list.
            version: Version string(s). Registry must resolve versions before calling.
            local_path: Local source directory/directories to upload from.
            metadata: Metadata dict(s) to store.
            on_conflict: Behavior when version exists.
                "skip" (default): Single ops raise RegistryVersionConflict, batch ops return skipped result.
                "overwrite": Replace existing version.
            acquire_lock: If True, acquire locks before push (for mutable registries).
                If False, rely on generation_match=0 for atomicity (immutable registries).
            max_workers: Maximum parallel workers. Defaults to instance setting.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists (batch only)
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
            - OpResult.failed() on failure (batch only)

        Raises:
            RegistryVersionConflict: Single item with on_conflict="skip" and version exists.
            LockAcquisitionError: Single item and lock cannot be acquired.
        """
        # Normalize inputs
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)
        paths = self._normalize_paths(local_path, len(names))
        metadatas = self._normalize_metadata(metadata, len(names))

        if not (len(names) == len(versions) == len(paths) == len(metadatas)):
            raise ValueError("Input list lengths must match")

        # Validate on_conflict + acquire_lock combination
        if on_conflict == OnConflict.OVERWRITE and not acquire_lock:
            raise ValueError(
                "on_conflict='overwrite' requires acquire_lock=True. "
                "Overwriting without a lock is unsafe for concurrent access."
            )

        # Validate all names upfront
        for obj_name in names:
            self.validate_object_name(obj_name)

        is_single = len(names) == 1
        results = OpResults()
        acquired_locks: Dict[str, str] = {}
        failed_locks: set = set()  # Track which objects failed lock acquisition

        # Acquire locks if mutable registry
        if acquire_lock:
            lock_keys = [f"{n}@{v}" for n, v in zip(names, versions)]
            lock_results = self._acquire_locks_batch(lock_keys, timeout=30)

            for obj_name, obj_version in zip(names, versions):
                lock_key = f"{obj_name}@{obj_version}"
                lock_id = lock_results.get(lock_key)
                if lock_id:
                    acquired_locks[lock_key] = lock_id
                else:
                    # Single ops raise, batch ops record failure
                    if is_single:
                        self._release_locks_batch(acquired_locks)
                        raise LockAcquisitionError(f"Failed to acquire lock for {lock_key}")
                    failed_locks.add((obj_name, obj_version))
                    results.add(
                        OpResult.failed(
                            obj_name,
                            obj_version,
                            LockAcquisitionError(f"Failed to acquire lock for {lock_key}"),
                        )
                    )

        try:
            # Use provided max_workers or fall back to instance default
            workers = max_workers or self._max_workers

            # Limit file-level parallelism
            file_workers = min(2, workers)

            # Determine fail_if_exists based on lock and conflict settings
            fail_if_exists = not acquire_lock  # acquire_lock==mutable.

            # Prepare tasks for objects that haven't failed lock acquisition
            push_tasks = [
                (n, v, p, m) for n, v, p, m in zip(names, versions, paths, metadatas) if (n, v) not in failed_locks
            ]

            def push_one(args: Tuple[str, str, Path, dict]) -> OpResult:
                obj_name, obj_version, obj_path, obj_meta = args
                return self._push_single_object(
                    obj_name, obj_version, obj_path, obj_meta, on_conflict, fail_if_exists, file_workers
                )

            # Single operations: process and raise on error or conflict
            if is_single and push_tasks:
                result = push_one(push_tasks[0])
                results.add(result)
                if result.is_skipped or (result.is_error and result.error == "RegistryVersionConflict"):
                    raise RegistryVersionConflict(result.message or f"Object {names[0]}@{versions[0]} already exists")
                elif result.is_error:
                    raise RuntimeError(result.message or "Unknown error")
            else:
                # Batch operations: process in parallel, return results without raising
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    for result in executor.map(push_one, push_tasks):
                        results.add(result)

        finally:
            if acquired_locks:
                self._release_locks_batch(acquired_locks)

        return results

    def pull(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        acquire_lock: bool = False,
        metadata: MetadataArg = None,
        max_workers: int | None = None,
    ) -> OpResults:
        """Download artifacts to local path(s).

        Uses the `_files` manifest from metadata when available to avoid
        expensive blob storage listing operations. All files across all objects
        are downloaded in a single batch for maximum efficiency.

        Note: The acquire_lock parameter is accepted for API compatibility but
        ignored. Read locks are not implemented for GCS because:
        1. Listing shared locks is slow (requires API call)
        2. Metadata is written LAST, so if readable, files should exist
        3. Worst case during concurrent write: download fails, caller retries

        Single item operations raise exceptions on error.
        Batch operations return OpResults without raising, letting caller inspect results.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            local_path: Destination directory path(s) to copy to.
            acquire_lock: Ignored. Kept for API compatibility with local backend.
            metadata: Optional pre-fetched metadata dict(s) containing "_files" manifest.
                If provided, avoids re-fetching metadata. Single dict or list of dicts.
            max_workers: Maximum parallel workers. Defaults to instance setting.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure (batch only)

        Raises:
            RegistryObjectNotFound: Single item and object doesn't exist.
        """
        workers = max_workers or self._max_workers
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)
        paths = self._normalize_paths(local_path, len(names))

        if len(names) != len(versions) or len(names) != len(paths):
            raise ValueError("Input list lengths must match")

        is_single = len(names) == 1

        # Use pre-fetched metadata if provided, otherwise fetch it
        if metadata is not None:
            if isinstance(metadata, dict):
                raise ValueError(
                    "metadata must be a list of dicts (one per object), not a single dict. "
                    "Use metadata=[meta_dict] for single objects."
                )
            metadatas = list(metadata)
            if len(metadatas) != len(names):
                raise ValueError(f"metadata list length ({len(metadatas)}) must match number of objects ({len(names)})")
            # Build OpResults from pre-fetched metadata
            metadata_results = OpResults()
            for n, v, m in zip(names, versions, metadatas):
                metadata_results.add(OpResult.success(n, v, metadata=m))
        else:
            metadata_results = self.fetch_metadata(names, versions)

        results = OpResults()
        all_files_to_download: List[Tuple[str, str]] = []
        file_to_object: Dict[str, Tuple[str, str]] = {}
        objects_with_errors: set = set()

        for obj_name, obj_version, dest_path in zip(names, versions, paths):
            try:
                remote_key = self._object_key(obj_name, obj_version)
                meta_result = metadata_results.get((obj_name, obj_version))
                if not meta_result or not meta_result.ok:
                    raise RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found.")

                obj_metadata = meta_result.metadata or {}
                files_manifest = obj_metadata.get("_files")

                if files_manifest:
                    for relative_path in files_manifest:
                        remote_path = f"{remote_key}/{relative_path}".replace("\\", "/")
                        dest_file = dest_path / relative_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        all_files_to_download.append((remote_path, str(dest_file)))
                        file_to_object[str(dest_file)] = (obj_name, obj_version)
                else:
                    # Fallback to listing (expensive)
                    objects_list = self.gcs.list_objects(prefix=remote_key)
                    if not objects_list:
                        raise RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found.")
                    for obj in objects_list:
                        if not obj.endswith("/"):
                            relative_path = obj[len(remote_key) :].lstrip("/")
                            if relative_path:
                                dest_file = dest_path / relative_path
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                all_files_to_download.append((obj, str(dest_file)))
                                file_to_object[str(dest_file)] = (obj_name, obj_version)

            except Exception as e:
                objects_with_errors.add((obj_name, obj_version))
                if is_single:
                    raise
                results.add(OpResult.failed(obj_name, obj_version, e))

        # Batch download all files
        if all_files_to_download:
            download_result = self.gcs.download_batch(all_files_to_download, max_workers=workers, on_error="skip")

            for file_result in download_result.failed_results:
                dest_path_str = file_result.local_path
                if dest_path_str in file_to_object:
                    obj_key = file_to_object[dest_path_str]
                    if obj_key not in objects_with_errors:
                        objects_with_errors.add(obj_key)
                        if is_single:
                            raise RuntimeError(
                                f"Failed to download {file_result.remote_path}: {file_result.error_message}"
                            )
                        results.add(
                            OpResult.failed(
                                obj_key[0],
                                obj_key[1],
                                error_type=file_result.error_type or "DownloadError",
                                message=file_result.error_message or "Unknown error",
                            )
                        )

        # Mark successful objects
        for obj_name, obj_version in zip(names, versions):
            if (obj_name, obj_version) not in objects_with_errors and (obj_name, obj_version) not in results:
                results.add(OpResult.success(obj_name, obj_version))

        return results

    def _delete_single_object(
        self,
        obj_name: str,
        obj_version: str,
        max_workers: int = 4,
        metadata: dict | None = None,
    ) -> OpResult:
        """Delete a single object's files and metadata.

        Args:
            obj_name: Object name.
            obj_version: Object version.
            max_workers: Maximum parallel workers for batch delete.
            metadata: Optional pre-fetched metadata containing "_files" manifest.

        Returns:
            OpResult indicating success or error.
        """
        try:
            remote_key = self._object_key(obj_name, obj_version)

            # Use _files manifest if available, otherwise fallback to listing
            if metadata and "_files" in metadata:
                paths_to_delete = [f"{remote_key}/{f}".replace("\\", "/") for f in metadata["_files"]]
            else:
                # Fallback to listing (expensive)
                paths_to_delete = self.gcs.list_objects(prefix=remote_key)

            # Add metadata path
            meta_path = self._object_metadata_path(obj_name, obj_version)
            paths_to_delete.append(meta_path)

            # Batch delete all files
            self.gcs.delete_batch(paths_to_delete, max_workers=max_workers)

            return OpResult.success(obj_name, obj_version)

        except Exception as e:
            return OpResult.failed(obj_name, obj_version, e)

    def delete(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        acquire_lock: bool = False,
        max_workers: int | None = None,
    ) -> OpResults:
        """Delete artifact(s) and metadata.

        Objects are processed in parallel for maximum efficiency.

        Single item operations raise exceptions on error.
        Batch operations return OpResults without raising, letting caller inspect results.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            acquire_lock: If True, acquire locks before delete (for mutable registries).
                Default is False (no locking, for immutable registries).
            max_workers: Maximum parallel workers. Defaults to instance setting.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure (batch only)

        Raises:
            RegistryObjectNotFound: Single item and object doesn't exist.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        is_single = len(names) == 1
        workers = max_workers or self._max_workers
        results = OpResults()
        acquired_locks: Dict[str, str] = {}
        failed_locks: set = set()

        # Acquire locks if mutable registry
        if acquire_lock:
            lock_keys = [f"{n}@{v}" for n, v in zip(names, versions)]
            lock_results = self._acquire_locks_batch(lock_keys, timeout=30)

            for obj_name, obj_version in zip(names, versions):
                lock_key = f"{obj_name}@{obj_version}"
                lock_id = lock_results.get(lock_key)
                if lock_id:
                    acquired_locks[lock_key] = lock_id
                else:
                    # Single ops raise, batch ops record failure
                    if is_single:
                        self._release_locks_batch(acquired_locks)
                        raise LockAcquisitionError(f"Failed to acquire lock for {lock_key}")
                    failed_locks.add((obj_name, obj_version))
                    results.add(
                        OpResult.failed(
                            obj_name,
                            obj_version,
                            LockAcquisitionError(f"Failed to acquire lock for {lock_key}"),
                        )
                    )

        try:
            # Limit file-level parallelism to avoid thread explosion with nested pools
            file_workers = min(2, workers)

            # Prepare tasks for objects that haven't already failed (e.g., lock acquisition)
            delete_tasks = [(n, v) for n, v in zip(names, versions) if (n, v) not in failed_locks]

            # Fetch metadata for all objects to get _files manifests (avoids listing during delete)
            metadata_results = self.fetch_metadata(
                [n for n, v in delete_tasks],
                [v for n, v in delete_tasks],
            )

            def delete_one(args: Tuple[str, str]) -> OpResult:
                obj_name, obj_version = args
                # Get metadata for this object (may be None if not found)
                meta_result = metadata_results.get((obj_name, obj_version))
                obj_metadata = meta_result.metadata if meta_result and meta_result.ok else None
                return self._delete_single_object(obj_name, obj_version, file_workers, metadata=obj_metadata)

            # Single operations: process and raise on error
            if is_single and delete_tasks:
                result = delete_one(delete_tasks[0])
                results.add(result)
                if result.is_error:
                    raise RuntimeError(result.message or "Unknown error")
            else:
                # Batch operations: process in parallel, return results without raising
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    for result in executor.map(delete_one, delete_tasks):
                        results.add(result)

        finally:
            if acquired_locks:
                self._release_locks_batch(acquired_locks)

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

        Single item operations raise exceptions on error/conflict.
        Batch operations return OpResults without raising, letting caller inspect results.

        Args:
            name: Object name(s).
            version: Object version(s).
            metadata: Metadata dict(s) to save.
            on_conflict: Behavior when version exists.
                "skip" (default): Single ops raise RegistryVersionConflict, batch ops return skipped result.
                "overwrite": Replace existing version.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists (batch only)
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
            - OpResult.failed() on failure (batch only)

        Raises:
            RegistryVersionConflict: Single item with on_conflict="skip" and version exists.
            RuntimeError: Single item with unexpected error.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

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

        for obj_name in names:
            self.validate_object_name(obj_name)

        results = OpResults()

        def save_one(args: Tuple[str, str, dict]) -> OpResult:
            obj_name, obj_version, obj_meta = args
            result = self._save_metadata_single(obj_name, obj_version, obj_meta, on_conflict=on_conflict)

            if result.status == Status.OK:
                return OpResult.success(obj_name, obj_version)
            elif result.status == Status.OVERWRITTEN:
                return OpResult.overwritten(obj_name, obj_version)
            elif result.status == Status.ALREADY_EXISTS:
                # Return failed result - caller (is_single logic) decides whether to raise
                return OpResult.failed(
                    obj_name,
                    obj_version,
                    RegistryVersionConflict(result.error_message or f"Object {obj_name}@{obj_version} already exists"),
                )
            else:
                return OpResult.failed(obj_name, obj_version, RuntimeError(result.error_message or "Unknown error"))

        is_single = len(names) == 1

        if is_single:
            op_result = save_one((names[0], versions[0], metadatas[0]))
            results.add(op_result)
            # Single ops raise on error
            if op_result.is_error:
                if op_result.error == "RegistryVersionConflict":
                    raise RegistryVersionConflict(op_result.message or "Version conflict")
                else:
                    raise RuntimeError(op_result.message or "Unknown error")
        else:
            # Batch ops return results without raising
            with ThreadPoolExecutor(max_workers=4) as executor:
                for op_result in executor.map(save_one, zip(names, versions, metadatas)):
                    results.add(op_result)

        return results

    def fetch_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        """Fetch metadata for object version(s) using batch download.

        Single item operations raise exceptions if not found.
        Batch operations return OpResults without raising, letting caller inspect results.
        Missing entries (not found) are omitted from the batch result.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success(metadata=...) on success
            - OpResult.failed() on failure (batch only)

        Raises:
            RegistryObjectNotFound: Single item and metadata doesn't exist.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        is_single = len(names) == 1
        results = OpResults()

        # Prepare batch download - create temp files and mapping
        temp_dir = tempfile.mkdtemp()
        files_to_download: List[Tuple[str, str]] = []
        temp_to_key: Dict[str, Tuple[str, str]] = {}  # Maps temp_path to (name, version)

        try:
            for obj_name, obj_version in zip(names, versions):
                meta_path = self._object_metadata_path(obj_name, obj_version)
                temp_path = os.path.join(temp_dir, f"{obj_name.replace(':', '_')}@{obj_version}.json")
                files_to_download.append((meta_path, temp_path))
                temp_to_key[temp_path] = (obj_name, obj_version)

            # Batch download all metadata files
            batch_result = self.gcs.download_batch(files_to_download, on_error="skip")

            # Track not found for single ops
            not_found_keys: set = set()

            # Process successful downloads
            for file_result in batch_result.ok_results:
                obj_name, obj_version = temp_to_key[file_result.local_path]
                try:
                    with open(file_result.local_path, "r") as f:
                        meta = json.load(f)

                    object_key = self._object_key(obj_name, obj_version)
                    meta["path"] = f"gs://{self.gcs.bucket_name}/{object_key}"
                    results.add(OpResult.success(obj_name, obj_version, metadata=meta))

                except json.JSONDecodeError as e:
                    if is_single:
                        raise
                    self.logger.warning(f"Error parsing metadata for {obj_name}@{obj_version}: {e}")
                    results.add(OpResult.failed(obj_name, obj_version, e))

            # Process failures (not_found entries are omitted for batch, errors are reported)
            for file_result in batch_result.failed_results:
                if file_result.local_path not in temp_to_key:
                    continue
                obj_name, obj_version = temp_to_key[file_result.local_path]
                if file_result.status == Status.NOT_FOUND:
                    not_found_keys.add((obj_name, obj_version))
                    continue  # Skip missing entries (omit from results)
                if is_single:
                    raise RuntimeError(file_result.error_message or f"Failed to fetch {obj_name}@{obj_version}")
                results.add(
                    OpResult.failed(
                        obj_name,
                        obj_version,
                        error_type=file_result.error_type or "DownloadError",
                        message=file_result.error_message or "Unknown error",
                    )
                )

            # Single ops raise if not found
            if is_single and not_found_keys:
                obj_name, obj_version = list(not_found_keys)[0]
                raise RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return results

    def delete_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        """Delete metadata for object version(s) using batch delete.

        Single item operations raise exceptions on error.
        Batch operations return OpResults without raising, letting caller inspect results.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure (batch only)

        Raises:
            RuntimeError: Single item and deletion fails.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        is_single = len(names) == 1

        # Build mapping from path to (name, version)
        path_to_key: Dict[str, Tuple[str, str]] = {}
        paths_to_delete: List[str] = []
        for obj_name, obj_version in zip(names, versions):
            meta_path = self._object_metadata_path(obj_name, obj_version)
            paths_to_delete.append(meta_path)
            path_to_key[meta_path] = (obj_name, obj_version)

        # Batch delete all metadata files
        batch_result = self.gcs.delete_batch(paths_to_delete)

        # Process results
        results = OpResults()
        for file_result in batch_result.results:
            key = path_to_key.get(file_result.remote_path)
            if not key:
                continue
            obj_name, obj_version = key
            if file_result.status == Status.OK:
                results.add(OpResult.success(obj_name, obj_version))
            else:
                if is_single:
                    raise RuntimeError(file_result.error_message or f"Failed to delete metadata for {key}")
                results.add(
                    OpResult.failed(
                        obj_name,
                        obj_version,
                        error_type=file_result.error_type or "DeleteError",
                        message=file_result.error_message or "Unknown error",
                    )
                )

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Registry-Level Metadata
    # ─────────────────────────────────────────────────────────────────────────

    def save_registry_metadata(self, metadata: dict) -> None:
        """Save registry-level metadata."""
        data = json.dumps(metadata)
        self.gcs.upload_string(data, self._metadata_path)

    def fetch_registry_metadata(self) -> dict:
        """Fetch registry-level metadata."""
        result = self.gcs.download_string(self._metadata_path)
        if result.ok:
            return json.loads(result.content.decode("utf-8"))
        self.logger.debug(f"Could not load registry metadata: {result.error_message}")
        return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Discovery
    # ─────────────────────────────────────────────────────────────────────────

    def list_objects(self) -> List[str]:
        """List all objects in the registry."""
        objects = set()
        meta_prefix = self._prefixed("_meta_")
        for obj_path in self.gcs.list_objects(prefix=meta_prefix):
            if obj_path.endswith(".json"):
                # Extract just the filename part after prefix
                filename = obj_path[len(self._prefix) + 1 :] if self._prefix else obj_path
                name_part = Path(filename).stem.split("@")[0].replace("_meta_", "")
                name = name_part.replace("_", ":")
                objects.add(name)
        return sorted(list(objects))

    def list_versions(self, name: NameArg) -> Dict[str, List[str]]:
        """List available versions for object(s)."""
        names = self._normalize_to_list(name)
        results: Dict[str, List[str]] = {}

        for obj_name in names:
            prefix = self._object_metadata_prefix(obj_name)
            versions = []

            for obj in self.gcs.list_objects(prefix=prefix):
                if obj.endswith(".json"):
                    version = obj[len(prefix) : -5]  # Remove prefix and .json
                    versions.append(version)

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
        """Check if object version(s) exist using batch metadata fetch.

        Uses batch download to check existence in parallel rather than
        sequential exists() calls.
        """
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        # Use fetch_metadata - wrap in try/except since single item raises on not found
        try:
            metadata_results = self.fetch_metadata(names, versions)
        except RegistryObjectNotFound:
            # Single item not found - return False for that item
            metadata_results = OpResults()

        results: Dict[Tuple[str, str], bool] = {}
        for obj_name, obj_version in zip(names, versions):
            meta_result = metadata_results.get((obj_name, obj_version))
            results[(obj_name, obj_version)] = meta_result is not None and meta_result.ok

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Materializer Registry
    # ─────────────────────────────────────────────────────────────────────────

    def register_materializer(
        self,
        object_class: NameArg,
        materializer_class: NameArg,
    ) -> None:
        """Register materializer(s) for object class(es)."""
        obj_classes = self._normalize_to_list(object_class)
        mat_classes = self._normalize_to_list(materializer_class)

        if len(obj_classes) != len(mat_classes):
            raise ValueError("object_class and materializer_class list lengths must match")

        metadata = self.fetch_registry_metadata()
        if "materializers" not in metadata:
            metadata["materializers"] = {}

        for obj_cls, mat_cls in zip(obj_classes, mat_classes):
            metadata["materializers"][obj_cls] = mat_cls

        self.save_registry_metadata(metadata)

    def registered_materializers(
        self,
        object_class: Union[str, None, List[str]] = None,
    ) -> Dict[str, str]:
        """Get registered materializers."""
        metadata = self.fetch_registry_metadata()
        all_materializers = metadata.get("materializers", {})

        if object_class is None:
            return all_materializers

        if isinstance(object_class, str):
            obj_classes = [object_class]
        else:
            obj_classes = object_class

        return {k: v for k, v in all_materializers.items() if k in obj_classes}

    # ─────────────────────────────────────────────────────────────────────────
    # Legacy Support
    # ─────────────────────────────────────────────────────────────────────────
