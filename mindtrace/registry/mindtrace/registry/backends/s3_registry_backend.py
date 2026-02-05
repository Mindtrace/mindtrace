"""S3-compatible registry backend.

Uses S3-compatible storage (AWS S3, Minio, etc.) for both artifact and metadata storage.

"""

import json
import os
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Union
from urllib.parse import quote

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
from mindtrace.registry.core.types import CleanupState, OnConflict, OpResult, OpResults
from mindtrace.storage import S3StorageHandler, Status, StringResult


class S3RegistryBackend(RegistryBackend):
    """An S3-compatible registry backend.

    Works with AWS S3, Minio, DigitalOcean Spaces, and other S3-compatible services.
    Stores objects and metadata in an S3 bucket with lock-free concurrency via UUID isolation.

    Lock-free concurrency model:
    - Each push writes files to a unique UUID folder: objects/{name}/{version}/{uuid}/
    - Commit plans in _staging/ track in-progress operations for janitor cleanup
    - Metadata write is the atomic "commit point" (points to active UUID)
    - For immutable: IfNoneMatch='*' on metadata ensures first-write-wins
    - For mutable: last metadata write wins, orphaned UUIDs cleaned by janitor

    Storage structure:
        {prefix}/
          objects/{name}/{version}/{uuid}/    # UUID-namespaced artifact folder
            file1.bin
            file2.json
          _meta_{name}@{version}.json         # Metadata pointing to active UUID
          _staging/{name}/{version}/{uuid}.json   # Commit plans for janitor cleanup
          registry_metadata.json              # Global registry config

    Uses `_files` manifest from metadata to avoid expensive blob listing on pull.

    Local Docker Example (Minio):
        To run a local MinIO registry, first start a MinIO server using docker:

        .. code-block:: bash

            $ docker run --rm --name minio \\
                -p 9000:9000 \\
                -p 9001:9001 \\
                -e MINIO_ROOT_USER=minioadmin \\
                -e MINIO_ROOT_PASSWORD=minioadmin \\
                -v ~/.cache/mindtrace/minio_data:/data \\
                minio/minio server /data --console-address ":9001"

    Usage Example::

        from mindtrace.registry import Registry, S3RegistryBackend

        s3_backend = S3RegistryBackend(
            endpoint="localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="my-registry",
            secure=False
        )
        registry = Registry(backend=s3_backend)
    """

    def __init__(
        self,
        uri: str | Path | None = None,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = "s3-registry",
        secure: bool = True,
        prefix: str = "",
        max_workers: int = 4,
        lock_timeout: int = 30,
        **kwargs,
    ):
        """Initialize the S3RegistryBackend.

        Args:
            uri: The base directory path where local cache will be stored.
            endpoint: S3-compatible server endpoint (e.g., "localhost:9000", "s3.amazonaws.com").
            access_key: Access key for authentication.
            secret_key: Secret key for authentication.
            bucket: S3 bucket name.
            secure: Whether to use HTTPS.
            prefix: Optional prefix (subfolder) within the bucket for all registry objects.
            max_workers: Maximum number of parallel workers for batch operations.
            lock_timeout: Timeout in seconds for acquiring locks. Default 30.
            **kwargs: Additional keyword arguments for the RegistryBackend.
        """
        super().__init__(uri=uri, **kwargs)
        self._prefix = prefix.strip("/") if prefix else ""
        # URI includes bucket and prefix for unique cache directory per backend
        self._uri = Path(uri or f"s3://{bucket}/{self._prefix}".rstrip("/"))

        self._metadata_path = self._prefixed("registry_metadata.json")
        self._max_workers = max_workers
        self._lock_timeout = lock_timeout
        self._bucket = bucket
        self.logger.debug(f"Initializing S3Backend with uri: {self._uri}, prefix: {self._prefix}")

        self.storage = S3StorageHandler(
            bucket_name=bucket,
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
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
        if not self.storage.exists(self._metadata_path):
            data = json.dumps({"materializers": {}})
            self.storage.upload_string(data, self._metadata_path)

    def _object_key(self, name: str, version: str) -> str:
        """Convert object name and version to a storage key.

        .. deprecated::
            Use :meth:`_object_key_with_uuid` instead. With MVCC, all object
            storage uses UUID-based paths for isolation.
        """
        import warnings

        warnings.warn(
            "_object_key is deprecated. Use _object_key_with_uuid for MVCC-based storage.",
            DeprecationWarning,
            stacklevel=2,
        )
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

    def _object_key_with_uuid(self, name: str, version: str, uuid_str: str) -> str:
        """Convert object name, version, and UUID to a storage key."""
        return self._prefixed(f"objects/{name}/{version}/{uuid_str}")

    def _staging_path(self, name: str, version: str, uuid_str: str) -> str:
        """Get the namespaced staging path for a commit plan."""
        safe_name = quote(name, safe="")
        safe_version = quote(str(version), safe="")
        return self._prefixed(f"_staging/{safe_name}/{safe_version}/{uuid_str}.json")

    # ─────────────────────────────────────────────────────────────────────────
    # Commit Plan Helpers (for lock-free MVCC)
    # ─────────────────────────────────────────────────────────────────────────

    def _create_commit_plan(
        self,
        name: str,
        version: str,
        uuid_str: str,
        expires_hours: int = 1,
    ) -> bool:
        """Create a commit plan to track an in-progress operation.

        Commit plans allow janitor to clean up failed/incomplete operations.
        The uuid_str serves as both the artifact folder name and the plan filename.

        Args:
            name: Object name.
            version: Object version.
            uuid_str: UUID for the artifact folder (also used as plan filename).
            expires_hours: Hours until this plan expires (for janitor).

        Returns:
            True if commit plan was created successfully.

        Janitor behavior:
            - Aggregates expired plans by (name, version)
            - Uses list_blobs to find all UUID folders for that object
            - Deletes UUIDs not matching current metadata's _storage.uuid
        """
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

        plan = {
            "name": name,
            "version": version,
            "uuid": uuid_str,
            "expires_at": expires_at.isoformat(),
        }

        staging_path = self._staging_path(name, version, uuid_str)
        data = json.dumps(plan)

        try:
            result = self.storage.upload_string(data, staging_path)
            return result.ok
        except Exception as e:
            self.logger.warning(f"Failed to create commit plan {uuid_str}: {e}")
            return False

    def _delete_commit_plan(self, name: str, version: str, uuid_str: str) -> bool:
        """Delete a commit plan after successful completion.

        Args:
            name: Object name.
            version: Object version.
            uuid_str: The UUID of the commit plan to delete (same as folder UUID).

        Returns:
            True if deleted successfully, False otherwise.
        """
        staging_path = self._staging_path(name, version, uuid_str)
        result = self.storage.delete(staging_path)
        if result.status == Status.NOT_FOUND:
            return True
        if not result.ok:
            self.logger.warning(f"Failed to delete commit plan {uuid_str}: {result.error_message}")
            return False
        return True

    def _delete_uuid_folder(self, name: str, version: str, uuid_str: str, files_manifest: list | None = None) -> bool:
        """Delete all files in a UUID folder.

        Args:
            name: Object name.
            version: Object version.
            uuid_str: UUID of the folder to delete.
            files_manifest: Optional list of relative file paths from metadata's _files.
                If provided, deletes exactly these files (no list_objects needed).
                If None, falls back to listing objects in the folder.

        Returns:
            True if ALL files deleted successfully.
            False if any file failed (including not found - indicates race condition).
        """
        folder_prefix = self._object_key_with_uuid(name, version, uuid_str)
        try:
            if files_manifest is not None:
                # Use manifest - backend delete status surfaces races (NOT_FOUND).
                files = [f"{folder_prefix}/{f}" for f in files_manifest]
                if not files:
                    return True  # Nothing to delete
            else:
                # Fallback: list objects (for janitor or legacy data without _files)
                files = self.storage.list_objects(prefix=folder_prefix)
                if not files:
                    return False  # No files found - someone else deleted them (race)

            batch_result = self.storage.delete_batch(files)
            # Any failure (including not found) indicates potential race
            if batch_result.failed_results:
                failed_count = len(batch_result.failed_results)
                self.logger.debug(f"Delete had {failed_count} failures in {folder_prefix} - possible race")
                return False
            return True
        except Exception as e:
            self.logger.warning(f"Failed to delete UUID folder {folder_prefix}: {e}")
            return False

    def _attempt_rollback(
        self,
        name: str,
        version: str,
        uuid_str: str,
    ) -> bool:
        """Attempt to clean up after a failed push operation.

        Best-effort cleanup of UUID folder and commit plan. If cleanup fails,
        the commit plan remains for janitor to handle later.

        Args:
            name: Object name.
            version: Object version.
            uuid_str: UUID of the folder to clean up (also used as plan filename).

        Returns:
            True if cleanup succeeded, False otherwise.
        """
        cleanup_ok = self._delete_uuid_folder(name, version, uuid_str)
        if cleanup_ok:
            self._delete_commit_plan(name, version, uuid_str)
        return cleanup_ok

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Locking (exclusive only, for mutable registry writes)
    # NOTE: Locks are being phased out in favor of UUID-based isolation.
    # Kept for delete operations and backward compatibility.
    # ─────────────────────────────────────────────────────────────────────────

    def _acquire_lock(self, key: str, lock_id: str, timeout: int = 30) -> bool:
        """Acquire exclusive lock using atomic S3 operations.

        Retries until *timeout* seconds elapse. The lock TTL is also set to
        *timeout* so stale locks are automatically reclaimable.

        Args:
            key: The key to acquire the lock for.
            lock_id: Unique identifier for this lock holder.
            timeout: Acquisition deadline **and** lock TTL in seconds.

        Returns:
            True if lock acquired, False if timed out.
        """
        lock_path = self._lock_path(key)
        deadline = time.time() + timeout

        while True:
            expires_at = time.time() + timeout
            lock_data = json.dumps({"lock_id": lock_id, "expires_at": expires_at})

            try:
                # Try atomic create (if_generation_match=0 = only if doesn't exist)
                result = self.storage.upload_string(lock_data, lock_path, if_generation_match=0)
                if result.ok:
                    return True

                # Lock exists - check if expired
                download_result = self.storage.download_string(lock_path)
                if download_result.status == Status.NOT_FOUND:
                    # Lock deleted between our attempts, retry create
                    retry_result = self.storage.upload_string(lock_data, lock_path, if_generation_match=0)
                    if retry_result.ok:
                        return True

                elif download_result.ok:
                    existing = json.loads(download_result.content.decode("utf-8"))
                    if time.time() >= existing.get("expires_at", 0):
                        # Lock expired - delete it and try to create a new one
                        self.storage.delete(lock_path)
                        takeover_result = self.storage.upload_string(lock_data, lock_path, if_generation_match=0)
                        if takeover_result.ok:
                            return True

            except Exception as e:
                self.logger.error(f"Error acquiring lock for {key}: {e}")

            if time.time() >= deadline:
                return False
            time.sleep(0.1)

    def _release_lock(self, key: str, lock_id: str) -> None:
        """Release write lock if we own it."""
        lock_path = self._lock_path(key)
        try:
            # Verify ownership before deleting
            result = self.storage.download_string(lock_path)
            if result.ok:
                data = json.loads(result.content.decode("utf-8"))
                if data.get("lock_id") == lock_id:
                    self.storage.delete(lock_path)
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
        self,
        name: str,
        version: str,
        metadata: dict,
        on_conflict: str = OnConflict.SKIP,
        check_exists_for_overwrite: bool = True,
    ) -> StringResult:
        """Save a single metadata file atomically.

        Args:
            name: Object name.
            version: Object version.
            metadata: Metadata dict to write.
            on_conflict: "error", "skip", or "overwrite".
            check_exists_for_overwrite: If True, does a pre-check in overwrite mode
                to report OVERWRITTEN vs OK. Set False when caller already resolved
                overwrite semantics to avoid TOCTOU contradictions.

        Returns:
            StringResult with status: ok, already_exists, overwritten, or error.
        """
        meta_path = self._object_metadata_path(name, version)
        data = json.dumps(metadata)

        if on_conflict == OnConflict.OVERWRITE:
            existed = self.storage.exists(meta_path) if check_exists_for_overwrite else False
            result = self.storage.upload_string(data, meta_path)
            if result.ok:
                return StringResult(
                    remote_path=meta_path,
                    status=Status.OVERWRITTEN if existed else Status.OK,
                )
            return result
        else:
            # "error" or "skip" - atomic insert with if_generation_match=0
            result = self.storage.upload_string(data, meta_path, if_generation_match=0)
            if result.status == Status.ALREADY_EXISTS:
                return StringResult(
                    remote_path=meta_path,
                    status=Status.ALREADY_EXISTS,
                    error_type="PreconditionFailed",
                    error_message=f"Object {name}@{version} already exists",
                )
            return result

    # ─────────────────────────────────────────────────────────────────────────
    # Artifact + Metadata Operations
    # ─────────────────────────────────────────────────────────────────────────

    def _push_single_object(
        self,
        obj_name: str,
        obj_version: str,
        obj_path: Path,
        obj_meta: dict,
        on_conflict: str,
        max_workers: int = 4,
    ) -> OpResult:
        """Push a single object's files and metadata using UUID-based MVCC.

        Lock-free concurrency:
        - Files are uploaded to a unique UUID folder: objects/{name}/{version}/{uuid}/
        - Commit plan tracks the operation for janitor cleanup on failure
        - Metadata write is the atomic "commit point"
        - For immutable (skip): if_generation_match=0 ensures first-write-wins
        - For mutable (overwrite): last metadata write wins

        Args:
            obj_name: Object name.
            obj_version: Object version.
            obj_path: Local path to upload from.
            obj_meta: Metadata dict.
            on_conflict: "skip" or "overwrite".
            max_workers: Maximum parallel workers for file uploads.

        Returns:
            OpResult indicating success, skip, overwrite, or error.
        """
        uuid_str: str | None = None
        is_overwrite = on_conflict == OnConflict.OVERWRITE

        try:
            # Step 1: For SKIP mode - check early, exit if exists (avoid wasted upload)
            if not is_overwrite:
                try:
                    result = self.fetch_metadata(obj_name, obj_version).first()
                    if result and result.ok:
                        return OpResult.skipped(obj_name, obj_version, cleanup=CleanupState.NOT_APPLICABLE)
                except Exception:
                    pass

            # Step 2: Generate UUID and create commit plan
            # Single UUID serves as both folder name and plan filename
            uuid_str = str(uuid.uuid4())
            if not self._create_commit_plan(obj_name, obj_version, uuid_str):
                return OpResult.failed(
                    obj_name,
                    obj_version,
                    RuntimeError("Failed to create commit plan"),
                    cleanup=CleanupState.NOT_APPLICABLE,
                )

            # Step 3: Build file list for UUID folder
            remote_key = self._object_key_with_uuid(obj_name, obj_version, uuid_str)

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

            # Step 4: Upload files to UUID folder (no conflict possible - UUID is unique)
            if files:
                batch_result = self.storage.upload_batch(files, fail_if_exists=False, max_workers=max_workers)

                # Check for failures
                if batch_result.failed_results:
                    rollback_ok = self._attempt_rollback(obj_name, obj_version, uuid_str)
                    first_error = batch_result.failed_results[0]
                    return OpResult.failed(
                        obj_name,
                        obj_version,
                        RuntimeError(
                            f"Failed to upload {len(batch_result.failed_results)} file(s): {first_error.error_message}"
                        ),
                        cleanup=CleanupState.OK if rollback_ok else CleanupState.ORPHANED,
                    )

            # Step 5: For OVERWRITE mode - check late for old_uuid and old_files (shorter race window)
            old_uuid = None
            old_files = None
            if is_overwrite:
                try:
                    result = self.fetch_metadata(obj_name, obj_version).first()
                    if result and result.ok and result.metadata:
                        old_uuid = result.metadata.get("_storage", {}).get("uuid")
                        old_files = result.metadata.get("_files")
                except Exception:
                    pass

            # Step 6: Prepare metadata with _storage info
            prepared_meta = dict(obj_meta) if obj_meta else {}
            prepared_meta["path"] = f"s3://{self._bucket}/{remote_key}"
            prepared_meta["_storage"] = {
                "uuid": uuid_str,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Step 7: Write metadata (the "commit point")
            meta_result = self._save_metadata_single(
                obj_name,
                obj_version,
                prepared_meta,
                on_conflict,
                check_exists_for_overwrite=False,
            )

            # Handle conflict (immutable mode - another writer won the race)
            if meta_result.status == Status.ALREADY_EXISTS:
                rollback_ok = self._attempt_rollback(obj_name, obj_version, uuid_str)
                return OpResult.skipped(
                    obj_name,
                    obj_version,
                    cleanup=CleanupState.OK if rollback_ok else CleanupState.ORPHANED,
                )

            # Handle any error (.ok checks for OK or OVERWRITTEN)
            if not meta_result.ok:
                rollback_ok = self._attempt_rollback(obj_name, obj_version, uuid_str)
                return OpResult.failed(
                    obj_name,
                    obj_version,
                    RuntimeError(meta_result.error_message or f"Metadata write failed: {meta_result.status}"),
                    cleanup=CleanupState.OK if rollback_ok else CleanupState.ORPHANED,
                )

            # Step 8: Success - handle plan deletion based on mode
            if is_overwrite:
                # OVERWRITE mode: clean up old UUID folder if exists
                if old_uuid:
                    # Use old_files manifest if available (avoids list_objects)
                    # If any file deletion fails (including not found), cleanup_ok=False
                    # which means we keep plan for janitor (race detection)
                    cleanup_ok = self._delete_uuid_folder(obj_name, obj_version, old_uuid, old_files)
                    if cleanup_ok:
                        plan_deleted = self._delete_commit_plan(obj_name, obj_version, uuid_str)
                        cleanup_state = CleanupState.OK if plan_deleted else CleanupState.UNKNOWN
                    else:
                        cleanup_state = CleanupState.ORPHANED
                    return OpResult.overwritten(obj_name, obj_version, cleanup=cleanup_state)
                # else: no old_uuid - keep plan for janitor (possible race created orphan)
                return OpResult.success(obj_name, obj_version, cleanup=CleanupState.UNKNOWN)
            else:
                # SKIP mode: we're guaranteed current (immutable), safe to delete plan
                self._delete_commit_plan(obj_name, obj_version, uuid_str)
                return OpResult.success(
                    obj_name,
                    obj_version,
                    cleanup=CleanupState.NOT_APPLICABLE,
                )

        except Exception as e:
            # Attempt cleanup if we created a commit plan
            if uuid_str:
                rollback_ok = self._attempt_rollback(obj_name, obj_version, uuid_str)
                return OpResult.failed(
                    obj_name,
                    obj_version,
                    e,
                    cleanup=CleanupState.OK if rollback_ok else CleanupState.ORPHANED,
                )
            return OpResult.failed(obj_name, obj_version, e, cleanup=CleanupState.NOT_APPLICABLE)

    def push(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        metadata: MetadataArg,
        on_conflict: str = OnConflict.SKIP,
        acquire_lock: bool = False,
        max_workers: int | None = None,
    ) -> OpResults:
        """Push artifacts and metadata to the registry.

        Objects are processed in parallel for maximum efficiency. Uses lock-free
        UUID-based MVCC for concurrent safety.

        Lock-free concurrency model:
        - Each push writes files to a unique UUID folder
        - Commit plans track operations for janitor cleanup on failure
        - Metadata write is the atomic "commit point"
        - For immutable (skip): if_generation_match=0 ensures first-write-wins
        - For mutable (overwrite): last metadata write wins

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
            acquire_lock: Ignored. Kept for API compatibility. Lock-free model used.
            max_workers: Maximum parallel workers. Defaults to instance setting.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists (batch only)
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
            - OpResult.failed() on failure (batch only)

        Raises:
            RegistryVersionConflict: Single item with on_conflict="skip" and version exists.
        """
        names, versions, paths, metadatas = self._prepare_inputs(name, version, local_path, metadata)

        results = OpResults()

        # Use provided max_workers or fall back to instance default
        workers = max_workers or self._max_workers

        # Limit file-level parallelism
        file_workers = min(2, workers)

        # Prepare all tasks
        push_tasks = list(zip(names, versions, paths, metadatas))

        def push_one(args: Tuple[str, str, Path, dict]) -> OpResult:
            obj_name, obj_version, obj_path, obj_meta = args
            try:
                self.validate_object_name(obj_name)
            except ValueError as e:
                return OpResult.failed(obj_name, obj_version, e)
            return self._push_single_object(obj_name, obj_version, obj_path, obj_meta, on_conflict, file_workers)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(push_one, push_tasks):
                results.add(result)

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
        expensive object listing operations. All files across all objects
        are downloaded in a single batch for maximum efficiency.

        This is a batch-only method - it never raises exceptions for individual
        object failures. The caller (Registry) handles single vs batch semantics.

        Note: The acquire_lock parameter is accepted for API compatibility but
        ignored. Read locks are not implemented because:
        1. Listing shared locks is slow
        2. Metadata is written LAST, so if readable, files should exist
        3. Worst case during concurrent write: download fails, caller retries

        Args:
            name: Name of the object(s).
            version: Version string(s).
            local_path: Destination directory path(s) to copy to.
            acquire_lock: Ignored. Kept for API compatibility.
            metadata: Optional pre-fetched metadata dict(s) containing "_files" manifest.
            max_workers: Maximum parallel workers. Defaults to instance setting.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        workers = max_workers or self._max_workers

        # Validate inputs (metadata required - Registry must pre-fetch)
        names, versions, paths, metadatas = self._prepare_inputs(name, version, local_path, metadata)

        results = OpResults()
        all_files_to_download: List[Tuple[str, str]] = []
        file_to_object: Dict[str, Tuple[str, str]] = {}
        objects_with_errors: set = set()

        for obj_name, obj_version, dest_path, obj_metadata in zip(names, versions, paths, metadatas):
            try:
                # No name validation needed - Registry already fetched metadata,
                # so the object exists with this name (name was validated at push time)

                # Get remote key from _storage.uuid
                storage_info = obj_metadata.get("_storage", {})
                uuid_str = storage_info.get("uuid")
                if not uuid_str:
                    raise RegistryObjectNotFound(
                        f"Object {obj_name}@{obj_version} has corrupted metadata (missing _storage.uuid)"
                    )
                remote_key = self._object_key_with_uuid(obj_name, obj_version, uuid_str)

                files_manifest = obj_metadata.get("_files")

                if files_manifest:
                    for relative_path in files_manifest:
                        remote_path = f"{remote_key}/{relative_path}".replace("\\", "/")
                        dest_file = dest_path / relative_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        all_files_to_download.append((remote_path, str(dest_file)))
                        file_to_object[str(dest_file)] = (obj_name, obj_version)
                else:
                    # Fallback to listing (not preferred)
                    objects_list = self.storage.list_objects(prefix=remote_key)
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
                results.add(OpResult.failed(obj_name, obj_version, e))

        # Batch download all files
        if all_files_to_download:
            download_result = self.storage.download_batch(all_files_to_download, max_workers=workers)

            for file_result in download_result.failed_results:
                dest_path_str = file_result.local_path
                if dest_path_str in file_to_object:
                    obj_key = file_to_object[dest_path_str]
                    if obj_key not in objects_with_errors:
                        objects_with_errors.add(obj_key)
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
        """Delete a single object's files and metadata using MVCC pattern.

        MVCC delete flow:
        1. Get UUID from metadata (if available)
        2. Create commit plan (for janitor cleanup - uses uuid as plan filename)
        3. Delete metadata (the "commit point" - object becomes invisible)
        4. Keep commit plan for janitor to clean up UUID folder

        Args:
            obj_name: Object name.
            obj_version: Object version.
            max_workers: Maximum parallel workers for batch delete.
            metadata: Optional pre-fetched metadata containing "_files" manifest and "_storage.uuid".

        Returns:
            OpResult indicating success or error.
        """
        uuid_str: str | None = None

        try:
            # Step 1: Extract UUID from metadata (caller fetches metadata in delete())
            # If no metadata, object doesn't exist - nothing to delete
            if not metadata:
                return OpResult.success(obj_name, obj_version)  # Idempotent delete

            uuid_str = metadata.get("_storage", {}).get("uuid")
            if not uuid_str:
                self.logger.warning(f"Metadata for {obj_name}@{obj_version} missing _storage.uuid")
                # Generate a UUID for the plan so janitor knows to check this object
                uuid_str = str(uuid.uuid4())

            # Step 2: Create commit plan (uuid serves as both identifier and plan filename)
            # The plan marks this name/version as needing cleanup - janitor will
            # list all UUID folders and delete them (since metadata will be gone)
            if not self._create_commit_plan(obj_name, obj_version, uuid_str):
                return OpResult.failed(obj_name, obj_version, RuntimeError("Failed to create commit plan"))

            # Step 3: Delete metadata (the "commit point")
            # After this, readers no longer see the object
            meta_path = self._object_metadata_path(obj_name, obj_version)
            meta_result = self.storage.delete(meta_path)

            if not meta_result.ok:
                self._delete_commit_plan(obj_name, obj_version, uuid_str)
                return OpResult.failed(
                    obj_name,
                    obj_version,
                    RuntimeError(f"Failed to delete metadata: {meta_result.error_message}"),
                )

            # Step 4: Best-effort UUID folder cleanup.
            # If cleanup fails, keep the plan for janitor.
            files_manifest = metadata.get("_files")
            cleanup_ok = self._delete_uuid_folder(obj_name, obj_version, uuid_str, files_manifest)
            if cleanup_ok:
                self._delete_commit_plan(obj_name, obj_version, uuid_str)

            return OpResult.success(obj_name, obj_version)

        except Exception as e:
            # Best-effort cleanup of commit plan on failure
            if uuid_str:
                self._delete_commit_plan(obj_name, obj_version, uuid_str)
            return OpResult.failed(obj_name, obj_version, e)

    def delete(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        acquire_lock: bool = False,
        max_workers: int | None = None,
    ) -> OpResults:
        """Delete artifact(s) and metadata using lock-free MVCC.

        Objects are processed in parallel for maximum efficiency. Uses MVCC
        for concurrent safety - metadata deletion is the atomic "commit point"
        that makes objects invisible to readers.

        This is a batch-only method - it never raises exceptions for individual
        object failures. The caller (Registry) handles single vs batch semantics.

        Delete is idempotent - succeeds even if object doesn't exist.

        Args:
            name: Name of the object(s).
            version: Version string(s).
            acquire_lock: Ignored. Kept for API compatibility. Lock-free MVCC used.
            max_workers: Maximum parallel workers.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        names = self._to_list(name)
        versions = self._to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        workers = max_workers or self._max_workers
        results = OpResults()

        # Limit file-level parallelism to avoid thread explosion with nested pools
        file_workers = min(2, workers)

        # Prepare all delete tasks
        delete_tasks = list(zip(names, versions))

        # Fetch metadata for all objects to get _storage.uuid (for MVCC cleanup)
        metadata_results = self.fetch_metadata(
            [n for n, _ in delete_tasks],
            [v for _, v in delete_tasks],
        )

        def delete_one(args: Tuple[str, str]) -> OpResult:
            obj_name, obj_version = args
            # Get metadata for this object (may be None if not found)
            meta_result = metadata_results.get((obj_name, obj_version))
            obj_metadata = meta_result.metadata if meta_result and meta_result.ok else None
            return self._delete_single_object(obj_name, obj_version, file_workers, metadata=obj_metadata)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(delete_one, delete_tasks):
                results.add(result)

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

        This is a batch-only method - it never raises exceptions for individual
        object failures. The caller (Registry) handles single vs batch semantics.

        Args:
            name: Object name(s).
            version: Object version(s).
            metadata: Metadata dict(s) to save.
            on_conflict: Behavior when version exists.
                "skip": Return skipped result.
                "overwrite": Replace existing version.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
            - OpResult.failed() on failure
        """
        names = self._to_list(name)
        versions = self._to_list(version)
        metadatas = [metadata] if isinstance(metadata, dict) else list(metadata)

        n = len(names)
        if not (len(versions) == len(metadatas) == n):
            raise ValueError(
                f"Input lengths must match: names={n}, versions={len(versions)}, metadata={len(metadatas)}"
            )

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
                return OpResult.skipped(obj_name, obj_version)
            else:
                return OpResult.failed(obj_name, obj_version, RuntimeError(result.error_message or "Unknown error"))

        # Process all tasks in parallel
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

        This is a batch-only method - it never raises exceptions for individual
        object failures. The caller (Registry) handles single vs batch semantics.
        Not found entries are returned as failed OpResults.

        Args:
            name: Name of the object(s).
            version: Version of the object(s).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() with metadata on success
            - OpResult.failed() on failure (including not found)
        """
        names = self._to_list(name)
        versions = self._to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results = OpResults()
        temp_dir = tempfile.mkdtemp()
        files_to_download: List[Tuple[str, str]] = []
        temp_to_key: Dict[str, Tuple[str, str]] = {}

        try:
            for obj_name, obj_version in zip(names, versions):
                meta_path = self._object_metadata_path(obj_name, obj_version)
                temp_path = os.path.join(temp_dir, f"{obj_name.replace(':', '_')}@{obj_version}.json")
                files_to_download.append((meta_path, temp_path))
                temp_to_key[temp_path] = (obj_name, obj_version)

            batch_result = self.storage.download_batch(files_to_download)

            for file_result in batch_result.ok_results:
                obj_name, obj_version = temp_to_key[file_result.local_path]
                try:
                    with open(file_result.local_path, "r") as f:
                        meta = json.load(f)
                    # Path is already in metadata from push (includes UUID folder)
                    results.add(OpResult.success(obj_name, obj_version, metadata=meta))

                except json.JSONDecodeError as e:
                    self.logger.warning(f"Error parsing metadata for {obj_name}@{obj_version}: {e}")
                    results.add(OpResult.failed(obj_name, obj_version, e))

            for file_result in batch_result.failed_results:
                if file_result.local_path not in temp_to_key:
                    continue
                obj_name, obj_version = temp_to_key[file_result.local_path]
                if file_result.status == Status.NOT_FOUND:
                    results.add(
                        OpResult.failed(
                            obj_name,
                            obj_version,
                            RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found"),
                        )
                    )
                    continue
                results.add(
                    OpResult.failed(
                        obj_name,
                        obj_version,
                        error_type=file_result.error_type or "DownloadError",
                        message=file_result.error_message or "Unknown error",
                    )
                )

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return results

    def delete_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        """Delete metadata for object version(s).

        This is a batch-only method - it never raises exceptions for individual
        object failures. The caller (Registry) handles single vs batch semantics.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        names = self._to_list(name)
        versions = self._to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        path_to_key: Dict[str, Tuple[str, str]] = {}
        paths_to_delete: List[str] = []
        for obj_name, obj_version in zip(names, versions):
            meta_path = self._object_metadata_path(obj_name, obj_version)
            paths_to_delete.append(meta_path)
            path_to_key[meta_path] = (obj_name, obj_version)

        batch_result = self.storage.delete_batch(paths_to_delete)

        results = OpResults()
        for file_result in batch_result.results:
            key = path_to_key.get(file_result.remote_path)
            if not key:
                continue
            obj_name, obj_version = key
            if file_result.status in (Status.OK, Status.NOT_FOUND):
                results.add(OpResult.success(obj_name, obj_version))
            else:
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
        self.storage.upload_string(data, self._metadata_path)

    def fetch_registry_metadata(self) -> dict:
        """Fetch registry-level metadata."""
        result = self.storage.download_string(self._metadata_path)

        if result.status == Status.NOT_FOUND:
            return {}
        if result.status == Status.ERROR:
            raise RuntimeError(f"Failed to fetch registry metadata,: {result.error_message}")
        return json.loads(result.content.decode("utf-8"))

    # ─────────────────────────────────────────────────────────────────────────
    # Discovery
    # ─────────────────────────────────────────────────────────────────────────

    def list_objects(self) -> List[str]:
        """List all objects in the registry."""
        objects = set()
        meta_prefix = self._prefixed("_meta_")
        for obj_path in self.storage.list_objects(prefix=meta_prefix):
            if obj_path.endswith(".json"):
                filename = obj_path[len(self._prefix) + 1 :] if self._prefix else obj_path
                name_part = Path(filename).stem.split("@")[0].replace("_meta_", "")
                name = name_part.replace("_", ":")
                objects.add(name)
        return sorted(list(objects))

    def list_versions(self, name: NameArg) -> Dict[str, List[str]]:
        """List available versions for object(s)."""
        names = self._to_list(name)
        results: Dict[str, List[str]] = {}

        for obj_name in names:
            prefix = self._object_metadata_prefix(obj_name)
            versions = []

            for obj in self.storage.list_objects(prefix=prefix):
                if obj.endswith(".json"):
                    version = obj[len(prefix) : -5]
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
        """Check if object version(s) exist using batch metadata fetch."""
        names = self._to_list(name)
        versions = self._to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        metadata_results = self.fetch_metadata(names, versions)

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
        """Register materializer(s) for object class(es).

        Uses a distributed lock to prevent concurrent read-modify-write races
        on the shared registry metadata file.
        """
        obj_classes = self._to_list(object_class)
        mat_classes = self._to_list(materializer_class)

        if len(obj_classes) != len(mat_classes):
            raise ValueError("object_class and materializer_class list lengths must match")

        lock_key = "_materializer_registry"
        lock_id = str(uuid.uuid4())
        if not self._acquire_lock(lock_key, lock_id, timeout=self._lock_timeout):
            raise LockAcquisitionError("Could not acquire lock for materializer registration")
        try:
            metadata = self.fetch_registry_metadata()
            if "materializers" not in metadata:
                metadata["materializers"] = {}

            for obj_cls, mat_cls in zip(obj_classes, mat_classes):
                metadata["materializers"][obj_cls] = mat_cls

            self.save_registry_metadata(metadata)
        finally:
            self._release_lock(lock_key, lock_id)

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


# Backwards compatibility alias
MinioRegistryBackend = S3RegistryBackend
