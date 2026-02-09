"""DB+GCP hybrid registry backend.

Delegates metadata/catalogue operations to MongoDB (via mindtrace-database)
and artifact (blob) operations to GCS (via mindtrace-storage).

Requires the ``db`` extra: ``pip install mindtrace-registry[db]``
"""

import json
import uuid as _uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pymongo import ASCENDING, IndexModel, UpdateOne

from mindtrace.database.backends.mongo_odm import MindtraceDocument, MongoMindtraceODM
from mindtrace.database.backends.unified_odm import UnifiedMindtraceDocument
from mindtrace.database.core.exceptions import DuplicateInsertError
from mindtrace.registry.backends.registry_backend import (
    ConcreteVersionArg,
    MetadataArg,
    NameArg,
    PathArg,
    RegistryBackend,
)
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from mindtrace.registry.core.types import CleanupState, OnConflict, OpResult, OpResults
from mindtrace.storage import GCSStorageHandler, Status

# ──────────────────────────────────────────────────────────────────────────────
# Document Models
# ──────────────────────────────────────────────────────────────────────────────


class RegistryObjectMeta(UnifiedMindtraceDocument):
    """Stores per-object-version metadata in MongoDB."""

    registry_uri: str
    name: str
    version: str
    metadata: dict
    created_at: Optional[datetime] = None

    class Meta:
        collection_name = "registry_object_metadata"
        indexed_fields = ["registry_uri", "name"]
        compound_indexes = [{"fields": ["registry_uri", "name", "version"], "unique": True}]


class RegistryMeta(UnifiedMindtraceDocument):
    """Stores registry-level metadata (materializers, settings)."""

    registry_uri: str
    metadata: dict

    class Meta:
        collection_name = "registry_metadata"
        unique_fields = ["registry_uri"]


class RegistryCommitPlan(UnifiedMindtraceDocument):
    """Tracks in-progress operations for janitor cleanup."""

    registry_uri: str
    name: str
    version: str
    uuid: str
    expires_at: Optional[datetime] = None

    class Meta:
        collection_name = "registry_commit_plans"
        indexed_fields = ["registry_uri", "expires_at"]


# ──────────────────────────────────────────────────────────────────────────────
# Backend
# ──────────────────────────────────────────────────────────────────────────────


class GCPDBRegistryBackend(RegistryBackend):
    """Hybrid backend: MongoDB for metadata, GCS for blobs.

    Constructor mirrors ``GCPRegistryBackend`` with additional ``db_uri``
    and ``db_name`` parameters for the MongoDB connection.

    Usage::

        from mindtrace.registry import Registry
        from mindtrace.registry.backends.gcp_db_registry_backend import GCPDBRegistryBackend

        backend = GCPDBRegistryBackend(
            uri="gs://my-bucket/prefix",
            project_id="my-project",
            bucket_name="my-bucket",
            credentials_path="/path/to/creds.json",
            db_uri="mongodb://localhost:27017",
            db_name="mindtrace",
        )
        registry = Registry(backend=backend)
    """

    def __init__(
        self,
        uri: str | Path | None = None,
        *,
        project_id: str,
        bucket_name: str,
        credentials_path: str | None = None,
        prefix: str = "",
        db_uri: str,
        db_name: str,
        max_workers: int = 4,
        lock_timeout: int = 5,
        allow_index_dropping: bool = False,
        **kwargs,
    ):
        super().__init__(uri=uri, **kwargs)
        self._prefix = prefix.strip("/") if prefix else ""
        self._uri = Path(uri or f"gs://{bucket_name}/{self._prefix}".rstrip("/"))
        self._max_workers = max_workers
        self._lock_timeout = lock_timeout
        self._registry_uri_key = str(self._uri)

        # ── GCS (blobs only) ────────────────────────────────────────────────
        self.gcs = GCSStorageHandler(
            bucket_name=bucket_name,
            project_id=project_id,
            credentials_path=credentials_path,
            ensure_bucket=True,
            create_if_missing=True,
        )

        # ── MongoDB (metadata) ──────────────────────────────────────────────
        obj_meta_model = RegistryObjectMeta._auto_generate_mongo_model()
        reg_meta_model = RegistryMeta._auto_generate_mongo_model()
        commit_plan_model = RegistryCommitPlan._auto_generate_mongo_model()

        self._db = MongoMindtraceODM(
            models={
                "obj_meta": obj_meta_model,
                "reg_meta": reg_meta_model,
                "commit_plan": commit_plan_model,
            },
            db_uri=db_uri,
            db_name=db_name,
            allow_index_dropping=allow_index_dropping,
            auto_init=False,
        )
        self._db.initialize_sync(allow_index_dropping=allow_index_dropping)

        # Expose sub-ODMs for convenience
        self._obj_meta: MongoMindtraceODM = self._db.obj_meta
        self._reg_meta: MongoMindtraceODM = self._db.reg_meta
        self._commit_plan: MongoMindtraceODM = self._db.commit_plan

        # Ensure registry metadata doc exists
        self._ensure_registry_metadata()

    # ─────────────────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def uri(self) -> Path:
        return self._uri

    # ─────────────────────────────────────────────────────────────────────────
    # Path / Key Helpers (same layout as GCPRegistryBackend for blob compat)
    # ─────────────────────────────────────────────────────────────────────────

    def _prefixed(self, path: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{path}"
        return path

    def _object_key_with_uuid(self, name: str, version: str, uuid_str: str) -> str:
        return self._prefixed(f"objects/{name}/{version}/{uuid_str}")

    # ─────────────────────────────────────────────────────────────────────────
    # MongoDB Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_registry_metadata(self):
        """Ensure a registry metadata doc exists in MongoDB."""
        docs = self._reg_meta.find_sync({"registry_uri": self._registry_uri_key})
        if not docs:
            try:
                self._reg_meta.insert_sync({"registry_uri": self._registry_uri_key, "metadata": {"materializers": {}}})
            except DuplicateInsertError:
                pass  # Race: another process created it

    def _query_filter(self, **extra) -> dict:
        """Build a query filter scoped to this registry."""
        return {"registry_uri": self._registry_uri_key, **extra}

    # ─────────────────────────────────────────────────────────────────────────
    # Commit Plan Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _create_commit_plan(self, name: str, version: str, uuid_str: str) -> bool:
        try:
            self._commit_plan.insert_sync({
                "registry_uri": self._registry_uri_key,
                "name": name,
                "version": version,
                "uuid": uuid_str,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            })
            return True
        except Exception as e:
            self.logger.warning(f"Failed to create commit plan {uuid_str}: {e}")
            return False

    def _delete_commit_plan(self, name: str, version: str, uuid_str: str) -> bool:
        try:
            self._commit_plan.find_one_and_delete_sync(
                self._query_filter(name=name, version=version, uuid=uuid_str)
            )
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # UUID Folder Helpers (GCS blob ops)
    # ─────────────────────────────────────────────────────────────────────────

    def _delete_uuid_folder(self, name: str, version: str, uuid_str: str, files_manifest: list | None = None) -> bool:
        folder_prefix = self._object_key_with_uuid(name, version, uuid_str)
        try:
            if files_manifest is not None:
                files = [f"{folder_prefix}/{f}" for f in files_manifest]
                if not files:
                    return True
            else:
                files = self.gcs.list_objects(prefix=folder_prefix)
                if not files:
                    return False
            batch_result = self.gcs.delete_batch(files)
            if batch_result.failed_results:
                return False
            return True
        except Exception as e:
            self.logger.warning(f"Failed to delete UUID folder {folder_prefix}: {e}")
            return False

    def _attempt_rollback(self, name: str, version: str, uuid_str: str) -> bool:
        cleanup_ok = self._delete_uuid_folder(name, version, uuid_str)
        if cleanup_ok:
            self._delete_commit_plan(name, version, uuid_str)
        return cleanup_ok

    # ─────────────────────────────────────────────────────────────────────────
    # Push
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
        uuid_str: str | None = None
        is_overwrite = on_conflict == OnConflict.OVERWRITE

        try:
            # Step 1: SKIP early-exit —
            if not is_overwrite:
                existing = self._obj_meta.find_sync(
                    self._query_filter(name=obj_name, version=obj_version)
                )
                if existing:
                    return OpResult.skipped(obj_name, obj_version, cleanup=CleanupState.NOT_APPLICABLE)

            # Step 2: Generate UUID and create commit plan
            uuid_str = str(_uuid.uuid4())
            if not self._create_commit_plan(obj_name, obj_version, uuid_str):
                return OpResult.failed(
                    obj_name, obj_version, RuntimeError("Failed to create commit plan"),
                    cleanup=CleanupState.NOT_APPLICABLE,
                )

            # Step 3: Build file list
            remote_key = self._object_key_with_uuid(obj_name, obj_version, uuid_str)
            files_manifest = obj_meta.get("_files") if obj_meta else None
            if files_manifest is not None:
                files = [(str(obj_path / f), f"{remote_key}/{f}".replace("\\", "/")) for f in files_manifest]
            else:
                files = []
                for file_path in obj_path.rglob("*"):
                    if file_path.is_file():
                        relative = file_path.relative_to(obj_path).as_posix()
                        files.append((str(file_path), f"{remote_key}/{relative}"))

            # Step 4: Upload files to UUID folder
            if files:
                batch_result = self.gcs.upload_batch(files, fail_if_exists=False, max_workers=max_workers)
                if batch_result.failed_results:
                    rollback_ok = self._attempt_rollback(obj_name, obj_version, uuid_str)
                    first_error = batch_result.failed_results[0]
                    return OpResult.failed(
                        obj_name, obj_version,
                        RuntimeError(f"Failed to upload {len(batch_result.failed_results)} file(s): {first_error.error_message}"),
                        cleanup=CleanupState.OK if rollback_ok else CleanupState.ORPHANED,
                    )

            # Step 5: Prepare metadata with _storage info
            prepared_meta = dict(obj_meta) if obj_meta else {}
            prepared_meta["path"] = f"gs://{self.gcs.bucket_name}/{remote_key}"
            prepared_meta["_storage"] = {
                "uuid": uuid_str,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Step 6: Write metadata to MongoDB (the "commit point")
            if is_overwrite:
                # Atomic upsert — returns the old doc (before update) for cleanup
                old_doc = self._obj_meta.find_one_and_update_sync(
                    {"registry_uri": self._registry_uri_key, "name": obj_name, "version": obj_version},
                    {"$set": {
                        "metadata": prepared_meta,
                        "created_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                    return_old=True,
                )

                # Extract old UUID for cleanup (old_doc is None on fresh insert)
                old_uuid = None
                old_files = None
                if old_doc:
                    old_meta = old_doc.get("metadata", {})
                    old_uuid = old_meta.get("_storage", {}).get("uuid")
                    old_files = old_meta.get("_files")

                # Cleanup old UUID folder
                if old_uuid and old_uuid != uuid_str:
                    cleanup_ok = self._delete_uuid_folder(obj_name, obj_version, old_uuid, old_files)
                    if cleanup_ok:
                        plan_deleted = self._delete_commit_plan(obj_name, obj_version, uuid_str)
                        cleanup_state = CleanupState.OK if plan_deleted else CleanupState.UNKNOWN
                    else:
                        cleanup_state = CleanupState.ORPHANED
                    return OpResult.overwritten(obj_name, obj_version, cleanup=cleanup_state)
                return OpResult.success(obj_name, obj_version, cleanup=CleanupState.UNKNOWN)
            else:
                # SKIP mode: insert — compound unique index rejects duplicates
                try:
                    self._obj_meta.insert_sync({
                        "registry_uri": self._registry_uri_key,
                        "name": obj_name,
                        "version": obj_version,
                        "metadata": prepared_meta,
                        "created_at": datetime.now(timezone.utc),
                    })
                except DuplicateInsertError:
                    # Race: another writer inserted between our early-exit check and here
                    rollback_ok = self._attempt_rollback(obj_name, obj_version, uuid_str)
                    return OpResult.skipped(
                        obj_name, obj_version,
                        cleanup=CleanupState.OK if rollback_ok else CleanupState.ORPHANED,
                    )

                plan_deleted = self._delete_commit_plan(obj_name, obj_version, uuid_str)
                cleanup_state = CleanupState.NOT_APPLICABLE if plan_deleted else CleanupState.UNKNOWN
                return OpResult.success(obj_name, obj_version, cleanup=cleanup_state)

        except Exception as e:
            if uuid_str:
                rollback_ok = self._attempt_rollback(obj_name, obj_version, uuid_str)
                return OpResult.failed(
                    obj_name, obj_version, e,
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
        names, versions, paths, metadatas = self._prepare_inputs(name, version, local_path, metadata)
        results = OpResults()
        workers = max_workers or self._max_workers
        file_workers = min(2, workers)
        push_tasks = list(zip(names, versions, paths, metadatas))

        def push_one(args):
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

    # ─────────────────────────────────────────────────────────────────────────
    # Pull
    # ─────────────────────────────────────────────────────────────────────────

    def pull(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        acquire_lock: bool = False,
        metadata: MetadataArg = None,
        max_workers: int | None = None,
    ) -> OpResults:
        workers = max_workers or self._max_workers
        names, versions, paths, metadatas = self._prepare_inputs(name, version, local_path, metadata)

        results = OpResults()
        all_files_to_download: List[Tuple[str, str]] = []
        file_to_object: Dict[str, Tuple[str, str]] = {}
        objects_with_errors: set = set()

        for obj_name, obj_version, dest_path, obj_metadata in zip(names, versions, paths, metadatas):
            try:
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
                    objects_list = self.gcs.list_objects(prefix=remote_key)
                    if not objects_list:
                        raise RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found.")
                    for obj in objects_list:
                        if not obj.endswith("/"):
                            relative_path = obj[len(remote_key):].lstrip("/")
                            if relative_path:
                                dest_file = dest_path / relative_path
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                all_files_to_download.append((obj, str(dest_file)))
                                file_to_object[str(dest_file)] = (obj_name, obj_version)
            except Exception as e:
                objects_with_errors.add((obj_name, obj_version))
                results.add(OpResult.failed(obj_name, obj_version, e))

        if all_files_to_download:
            download_result = self.gcs.download_batch(all_files_to_download, max_workers=workers)
            for file_result in download_result.failed_results:
                dest_path_str = file_result.local_path
                if dest_path_str in file_to_object:
                    obj_key = file_to_object[dest_path_str]
                    if obj_key not in objects_with_errors:
                        objects_with_errors.add(obj_key)
                        results.add(OpResult.failed(
                            obj_key[0], obj_key[1],
                            error_type=file_result.error_type or "DownloadError",
                            message=file_result.error_message or "Unknown error",
                        ))

        for obj_name, obj_version in zip(names, versions):
            if (obj_name, obj_version) not in objects_with_errors and (obj_name, obj_version) not in results:
                results.add(OpResult.success(obj_name, obj_version))

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Delete
    # ─────────────────────────────────────────────────────────────────────────

    def _delete_single_object(
        self,
        obj_name: str,
        obj_version: str,
        max_workers: int = 4,
        metadata: dict | None = None,
    ) -> OpResult:
        uuid_str: str | None = None

        try:
            if not metadata:
                return OpResult.success(obj_name, obj_version)

            uuid_str = metadata.get("_storage", {}).get("uuid")
            if not uuid_str:
                uuid_str = str(_uuid.uuid4())

            if not self._create_commit_plan(obj_name, obj_version, uuid_str):
                return OpResult.failed(obj_name, obj_version, RuntimeError("Failed to create commit plan"))

            # Delete metadata from MongoDB (the "commit point")
            self._obj_meta.delete_many_sync(self._query_filter(name=obj_name, version=obj_version))

            # Best-effort UUID folder cleanup
            files_manifest = metadata.get("_files")
            cleanup_ok = self._delete_uuid_folder(obj_name, obj_version, uuid_str, files_manifest)
            if cleanup_ok:
                self._delete_commit_plan(obj_name, obj_version, uuid_str)
                return OpResult.success(obj_name, obj_version, cleanup=CleanupState.OK)

            return OpResult.success(obj_name, obj_version, cleanup=CleanupState.ORPHANED)

        except Exception as e:
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
        names = self._to_list(name)
        versions = self._to_list(version)
        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        workers = max_workers or self._max_workers
        file_workers = min(2, workers)
        results = OpResults()

        # Fetch metadata for all objects to get UUIDs
        metadata_results = self.fetch_metadata(
            [n for n in names],
            [v for v in versions],
        )

        delete_tasks = list(zip(names, versions))

        def delete_one(args):
            obj_name, obj_version = args
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

        if on_conflict == OnConflict.OVERWRITE:
            operations = []
            for obj_name, obj_version, obj_meta in zip(names, versions, metadatas):
                operations.append(UpdateOne(
                    {"registry_uri": self._registry_uri_key, "name": obj_name, "version": obj_version},
                    {"$set": {
                        "metadata": obj_meta,
                        "created_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                ))

            # Check which ones exist beforehand for overwrite status
            existing_keys = set()
            or_clauses = [{"name": n, "version": v} for n, v in zip(names, versions)]
            if or_clauses:
                existing_docs = self._obj_meta.find_sync(
                    {"registry_uri": self._registry_uri_key, "$or": or_clauses}
                )
                for doc in existing_docs:
                    existing_keys.add((doc.name, doc.version))

            self._obj_meta.bulk_write_sync(operations)

            for obj_name, obj_version in zip(names, versions):
                if (obj_name, obj_version) in existing_keys:
                    results.add(OpResult.overwritten(obj_name, obj_version))
                else:
                    results.add(OpResult.success(obj_name, obj_version))
        else:
            # SKIP mode: attempt insert for every item. The compound unique
            # index rejects duplicates atomically — no pre-check needed.
            for obj_name, obj_version, obj_meta in zip(names, versions, metadatas):
                try:
                    self._obj_meta.insert_sync({
                        "registry_uri": self._registry_uri_key,
                        "name": obj_name,
                        "version": obj_version,
                        "metadata": obj_meta,
                        "created_at": datetime.now(timezone.utc),
                    })
                    results.add(OpResult.success(obj_name, obj_version))
                except DuplicateInsertError:
                    results.add(OpResult.skipped(obj_name, obj_version))

        return results

    def fetch_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        names = self._to_list(name)
        versions = self._to_list(version)
        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results = OpResults()
        requested = set(zip(names, versions))

        # Single query for all items
        or_clauses = [{"name": n, "version": v} for n, v in zip(names, versions)]
        if not or_clauses:
            return results

        docs = self._obj_meta.find_sync({"registry_uri": self._registry_uri_key, "$or": or_clauses})

        found = set()
        for doc in docs:
            n = doc.name
            v = doc.version
            found.add((n, v))
            results.add(OpResult.success(n, v, metadata=doc.metadata))

        # Mark missing as failed
        for n, v in requested:
            if (n, v) not in found:
                results.add(OpResult.failed(n, v, RegistryObjectNotFound(f"Object {n}@{v} not found")))

        return results

    def delete_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        names = self._to_list(name)
        versions = self._to_list(version)
        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results = OpResults()
        or_clauses = [{"name": n, "version": v} for n, v in zip(names, versions)]
        if or_clauses:
            try:
                self._obj_meta.delete_many_sync(
                    {"registry_uri": self._registry_uri_key, "$or": or_clauses}
                )
            except Exception as e:
                for n, v in zip(names, versions):
                    results.add(OpResult.failed(n, v, e))
                return results

        for n, v in zip(names, versions):
            results.add(OpResult.success(n, v))
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Registry-Level Metadata
    # ─────────────────────────────────────────────────────────────────────────

    def save_registry_metadata(self, metadata: dict) -> None:
        self._reg_meta.update_one_sync(
            {"registry_uri": self._registry_uri_key},
            {"$set": {"metadata": metadata}},
            upsert=True,
        )

    def fetch_registry_metadata(self) -> dict:
        docs = self._reg_meta.find_sync({"registry_uri": self._registry_uri_key})
        if docs:
            return docs[0].metadata
        return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Discovery
    # ─────────────────────────────────────────────────────────────────────────

    def list_objects(self) -> List[str]:
        pipeline = [
            {"$match": {"registry_uri": self._registry_uri_key}},
            {"$group": {"_id": "$name"}},
            {"$sort": {"_id": 1}},
        ]
        results = self._obj_meta.aggregate_sync(pipeline)
        return [r["_id"] for r in results]

    def list_versions(self, name: NameArg) -> Dict[str, List[str]]:
        names = self._to_list(name)

        def version_key(v):
            try:
                return [int(x) for x in v.split(".")]
            except ValueError:
                return [0]

        # Single aggregation for all requested names — project only version field
        pipeline = [
            {"$match": {"registry_uri": self._registry_uri_key, "name": {"$in": names}}},
            {"$project": {"name": 1, "version": 1, "_id": 0}},
        ]
        docs = self._obj_meta.aggregate_sync(pipeline)

        result: Dict[str, List[str]] = {n: [] for n in names}
        for doc in docs:
            result[doc["name"]].append(doc["version"])

        for n in names:
            result[n].sort(key=version_key)

        return result

    def has_object(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> Dict[Tuple[str, str], bool]:
        names = self._to_list(name)
        versions = self._to_list(version)
        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], bool] = {}

        or_clauses = [{"name": n, "version": v} for n, v in zip(names, versions)]
        if not or_clauses:
            return results

        docs = self._obj_meta.find_sync({"registry_uri": self._registry_uri_key, "$or": or_clauses})
        found = {(doc.name, doc.version) for doc in docs}

        for n, v in zip(names, versions):
            results[(n, v)] = (n, v) in found

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Materializer Registry
    # ─────────────────────────────────────────────────────────────────────────

    def register_materializer(
        self,
        object_class: NameArg,
        materializer_class: NameArg,
    ) -> None:
        obj_classes = self._to_list(object_class)
        mat_classes = self._to_list(materializer_class)
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
        metadata = self.fetch_registry_metadata()
        all_materializers = metadata.get("materializers", {})

        if object_class is None:
            return all_materializers

        if isinstance(object_class, str):
            obj_classes = [object_class]
        else:
            obj_classes = object_class

        return {k: v for k, v in all_materializers.items() if k in obj_classes}
