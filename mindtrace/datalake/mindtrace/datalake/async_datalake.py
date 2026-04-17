from __future__ import annotations

import base64
import hashlib
import json
import warnings
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from mindtrace.core import Mindtrace
from mindtrace.database import MongoMindtraceODM
from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError
from mindtrace.datalake.pagination_types import (
    CursorEnvelope,
    CursorPage,
    DatasetViewExpand,
    DatasetViewInfo,
    DatasetViewPage,
    DatasetViewRow,
    PageInfo,
    StructuredFilter,
)
from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    AnnotationSource,
    Asset,
    AssetAlias,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    DirectUploadSession,
    DuplicateAliasError,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)
from mindtrace.registry import LocalMountConfig, Mount, MountBackendKind, Store
from mindtrace.registry.core.exceptions import RegistryObjectNotFound, StoreLocationNotFound

DocumentT = TypeVar("DocumentT")


class AnnotationSchemaValidationError(ValueError):
    """Raised when an annotation record violates a schema-bound set contract."""


class DuplicateAnnotationSchemaError(ValueError):
    """Raised when an annotation schema name/version pair already exists."""


class AnnotationSchemaInUseError(ValueError):
    """Raised when attempting to delete an annotation schema still referenced by a set."""


class SlowOpsPolicy(StrEnum):
    """How eager collection-list operations should behave."""

    ALLOW = "allow"
    WARN = "warn"
    FORBID = "forbid"


class SlowOperationWarning(UserWarning):
    """Raised when callers use an eager collection operation that may not scale."""


class SlowOperationDisabledError(RuntimeError):
    """Raised when eager collection operations are disabled by policy."""


def _default_datalake_store_path(mongo_db_uri: str, mongo_db_name: str) -> Path:
    digest = hashlib.sha1(f"{mongo_db_uri}|{mongo_db_name}".encode()).hexdigest()[:12]
    return Path("~/.cache/mindtrace/temp").expanduser() / f"datalake-{digest}"


class AsyncDatalake(Mindtrace):
    """Async canonical data facade for payload storage, metadata, and dataset composition.

    The ``AsyncDatalake`` coordinates two lower-level Mindtrace subsystems:

    - ``Store`` / ``Registry`` for payload-bearing objects such as images, masks, artifacts, and other large blobs.
    - ``MongoMindtraceODM`` for canonical metadata records such as assets, annotations, datums, and dataset versions.

    Use this class directly in async code. For synchronous code, use :class:`mindtrace.datalake.Datalake`,
    which provides a blocking facade over an ``AsyncDatalake`` running on a dedicated background event loop.
    """

    def __init__(
        self,
        mongo_db_uri: str,
        mongo_db_name: str,
        *,
        store: Store | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
        slow_ops_policy: SlowOpsPolicy = SlowOpsPolicy.WARN,
    ) -> None:
        super().__init__()
        self.mongo_db_uri = mongo_db_uri
        self.mongo_db_name = mongo_db_name
        self.slow_ops_policy = SlowOpsPolicy(slow_ops_policy)

        if store is not None and mounts is not None:
            raise ValueError("Provide either store or mounts, not both")

        if store is not None:
            self.store = store
        elif mounts is not None:
            self.store = Store.from_mounts(mounts, default_mount=default_mount)
        else:
            default_path = _default_datalake_store_path(mongo_db_uri, mongo_db_name)
            default_path.mkdir(parents=True, exist_ok=True)
            effective_default_mount = default_mount or "default"
            self.store = Store.from_mounts(
                [
                    Mount(
                        name=effective_default_mount,
                        backend=MountBackendKind.LOCAL,
                        config=LocalMountConfig(uri=default_path),
                        is_default=True,
                    )
                ],
                default_mount=effective_default_mount,
            )

        self.asset_database = MongoMindtraceODM(model_cls=Asset, db_name=mongo_db_name, db_uri=mongo_db_uri)
        self.collection_database = MongoMindtraceODM(model_cls=Collection, db_name=mongo_db_name, db_uri=mongo_db_uri)
        self.collection_item_database = MongoMindtraceODM(
            model_cls=CollectionItem,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.asset_retention_database = MongoMindtraceODM(
            model_cls=AssetRetention,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.annotation_record_database = MongoMindtraceODM(
            model_cls=AnnotationRecord,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.annotation_schema_database = MongoMindtraceODM(
            model_cls=AnnotationSchema,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.annotation_set_database = MongoMindtraceODM(
            model_cls=AnnotationSet,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.datum_database = MongoMindtraceODM(model_cls=Datum, db_name=mongo_db_name, db_uri=mongo_db_uri)
        self.dataset_version_database = MongoMindtraceODM(
            model_cls=DatasetVersion,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.direct_upload_session_database = MongoMindtraceODM(
            model_cls=DirectUploadSession,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )
        self.asset_alias_database = MongoMindtraceODM(
            model_cls=AssetAlias,
            db_name=mongo_db_name,
            db_uri=mongo_db_uri,
        )

    async def initialize(self) -> None:
        await self.asset_database.initialize()
        await self.collection_database.initialize()
        await self.collection_item_database.initialize()
        await self.asset_retention_database.initialize()
        await self.annotation_record_database.initialize()
        await self.annotation_schema_database.initialize()
        await self.annotation_set_database.initialize()
        await self.datum_database.initialize()
        await self.dataset_version_database.initialize()
        await self.direct_upload_session_database.initialize()
        await self.asset_alias_database.initialize()

    @classmethod
    async def create(
        cls,
        mongo_db_uri: str,
        mongo_db_name: str,
        *,
        store: Store | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
        slow_ops_policy: SlowOpsPolicy = SlowOpsPolicy.WARN,
    ) -> "AsyncDatalake":
        datalake = cls(
            mongo_db_uri=mongo_db_uri,
            mongo_db_name=mongo_db_name,
            store=store,
            mounts=mounts,
            default_mount=default_mount,
            slow_ops_policy=slow_ops_policy,
        )
        await datalake.initialize()
        return datalake

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _coerce_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _normalize_storage_ref(storage_ref: StorageRef) -> StorageRef:
        return StorageRef(
            mount=storage_ref.mount,
            name=storage_ref.name,
            version=storage_ref.version,
        )

    @staticmethod
    def _build_document(model_cls: type[DocumentT], **data: Any) -> DocumentT:
        return model_cls.model_construct(**data)

    @staticmethod
    def _serialize_cursor_value(value: Any) -> Any:
        if isinstance(value, datetime):
            return {"__mindtrace_type__": "datetime", "value": value.isoformat()}
        return value

    @classmethod
    def _deserialize_cursor_value(cls, value: Any) -> Any:
        if (
            isinstance(value, dict)
            and value.get("__mindtrace_type__") == "datetime"
            and isinstance(value.get("value"), str)
        ):
            return datetime.fromisoformat(value["value"])
        return value

    @staticmethod
    def _cursor_filter_fingerprint(filters: Any) -> str:
        if isinstance(filters, list):
            payload = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in filters]
        elif hasattr(filters, "model_dump"):
            payload = filters.model_dump(mode="json")
        else:
            payload = filters or {}
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()

    @classmethod
    def _encode_cursor(cls, envelope: CursorEnvelope) -> str:
        payload = envelope.model_dump(mode="json")
        payload["last_key"] = {key: cls._serialize_cursor_value(value) for key, value in envelope.last_key.items()}
        encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii")
        return encoded.rstrip("=")

    @classmethod
    def _decode_cursor(
        cls,
        cursor: str,
        *,
        expected_resource: str,
        expected_sort: str,
        expected_filters: Any,
    ) -> CursorEnvelope:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(f"{cursor}{padding}".encode("ascii")).decode("utf-8"))
        payload["last_key"] = {
            key: cls._deserialize_cursor_value(value) for key, value in payload.get("last_key", {}).items()
        }
        envelope = CursorEnvelope.model_validate(payload)
        if envelope.resource != expected_resource:
            raise ValueError(f"Cursor resource mismatch: expected {expected_resource!r}, got {envelope.resource!r}")
        if envelope.sort != expected_sort:
            raise ValueError(f"Cursor sort mismatch: expected {expected_sort!r}, got {envelope.sort!r}")
        expected_fingerprint = cls._cursor_filter_fingerprint(expected_filters)
        if envelope.filter_fingerprint != expected_fingerprint:
            raise ValueError("Cursor filters do not match this request")
        return envelope

    @staticmethod
    def _get_value_by_path(obj: Any, path: str) -> Any:
        current = obj
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
            if current is None:
                return None
        return current

    @classmethod
    def _build_cursor_query(cls, sort_fields: list[tuple[str, int]], last_key: dict[str, Any]) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = []
        for idx, (field, direction) in enumerate(sort_fields):
            comparison = "$gt" if direction > 0 else "$lt"
            clause: dict[str, Any] = {}
            for prev_field, _ in sort_fields[:idx]:
                clause[prev_field] = last_key[prev_field]
            clause[field] = {comparison: last_key[field]}
            clauses.append(clause)
        return {"$or": clauses}

    @staticmethod
    def _merge_query(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        if not base:
            return extra
        if not extra:
            return base
        return {"$and": [base, extra]}

    @staticmethod
    def _sort_specs_for(resource: str) -> dict[str, tuple[list[tuple[str, int]], list[str]]]:
        specs: dict[str, dict[str, tuple[list[tuple[str, int]], list[str]]]] = {
            "assets": {
                "created_desc": ([("created_at", -1), ("asset_id", -1)], ["created_at", "asset_id"]),
                "created_asc": ([("created_at", 1), ("asset_id", 1)], ["created_at", "asset_id"]),
            },
            "collections": {
                "created_desc": ([("created_at", -1), ("collection_id", -1)], ["created_at", "collection_id"]),
                "created_asc": ([("created_at", 1), ("collection_id", 1)], ["created_at", "collection_id"]),
            },
            "collection_items": {
                "created_desc": ([("added_at", -1), ("collection_item_id", -1)], ["added_at", "collection_item_id"]),
                "created_asc": ([("added_at", 1), ("collection_item_id", 1)], ["added_at", "collection_item_id"]),
            },
            "asset_retentions": {
                "created_desc": (
                    [("created_at", -1), ("asset_retention_id", -1)],
                    ["created_at", "asset_retention_id"],
                ),
                "created_asc": (
                    [("created_at", 1), ("asset_retention_id", 1)],
                    ["created_at", "asset_retention_id"],
                ),
            },
            "annotation_schemas": {
                "created_desc": (
                    [("created_at", -1), ("annotation_schema_id", -1)],
                    ["created_at", "annotation_schema_id"],
                ),
                "created_asc": (
                    [("created_at", 1), ("annotation_schema_id", 1)],
                    ["created_at", "annotation_schema_id"],
                ),
            },
            "annotation_sets": {
                "created_desc": (
                    [("created_at", -1), ("annotation_set_id", -1)],
                    ["created_at", "annotation_set_id"],
                ),
                "created_asc": (
                    [("created_at", 1), ("annotation_set_id", 1)],
                    ["created_at", "annotation_set_id"],
                ),
            },
            "annotation_records": {
                "created_desc": (
                    [("created_at", -1), ("annotation_id", -1)],
                    ["created_at", "annotation_id"],
                ),
                "subject_created_desc": (
                    [("subject.kind", 1), ("subject.id", 1), ("created_at", -1), ("annotation_id", -1)],
                    ["subject.kind", "subject.id", "created_at", "annotation_id"],
                ),
            },
            "datums": {
                "created_desc": ([("created_at", -1), ("datum_id", -1)], ["created_at", "datum_id"]),
                "split_created_desc": (
                    [("split", 1), ("created_at", -1), ("datum_id", -1)],
                    ["split", "created_at", "datum_id"],
                ),
            },
            "dataset_versions": {
                "created_desc": (
                    [("created_at", -1), ("dataset_version_id", -1)],
                    ["created_at", "dataset_version_id"],
                ),
                "dataset_version_desc": (
                    [("dataset_name", 1), ("version", -1), ("dataset_version_id", -1)],
                    ["dataset_name", "version", "dataset_version_id"],
                ),
            },
        }
        if resource not in specs:
            raise ValueError(f"Unsupported pagination resource: {resource}")
        return specs[resource]

    @classmethod
    def _resolve_sort_spec(cls, resource: str, sort: str) -> tuple[list[tuple[str, int]], list[str]]:
        specs = cls._sort_specs_for(resource)
        if sort not in specs:
            raise ValueError(f"Unsupported sort {sort!r} for resource {resource!r}")
        return specs[sort]

    async def _paginate_database(
        self,
        *,
        database: MongoMindtraceODM[Any],
        resource: str,
        filters: dict[str, Any] | None,
        sort: str,
        limit: int,
        cursor: str | None,
        include_total: bool,
    ) -> CursorPage[Any]:
        query = dict(filters or {})
        sort_spec, cursor_fields = self._resolve_sort_spec(resource, sort)
        if cursor is not None:
            envelope = self._decode_cursor(
                cursor,
                expected_resource=resource,
                expected_sort=sort,
                expected_filters=query,
            )
            query = self._merge_query(query, self._build_cursor_query(sort_spec, envelope.last_key))

        window = await database.find_window(query, sort=sort_spec, limit=limit + 1)
        items = window[:limit]
        has_more = len(window) > limit
        next_cursor: str | None = None
        if has_more and items:
            last_item = items[-1]
            last_key = {field: self._get_value_by_path(last_item, field) for field in cursor_fields}
            next_cursor = self._encode_cursor(
                CursorEnvelope(
                    resource=resource,
                    sort=sort,
                    filter_fingerprint=self._cursor_filter_fingerprint(filters or {}),
                    last_key=last_key,
                )
            )

        total_count = await database.count_documents(filters or {}) if include_total else None
        return CursorPage(
            items=items,
            page=PageInfo(limit=limit, next_cursor=next_cursor, has_more=has_more, total_count=total_count),
        )

    async def _iter_database(
        self,
        *,
        database: MongoMindtraceODM[Any],
        resource: str,
        filters: dict[str, Any] | None,
        sort: str,
        batch_size: int | None = None,
    ) -> AsyncIterator[Any]:
        sort_spec, _ = self._resolve_sort_spec(resource, sort)
        async for item in database.find_iter(filters or {}, sort=sort_spec, batch_size=batch_size):
            yield item

    @classmethod
    def _matches_structured_filters(cls, item: Any, filters: list[StructuredFilter]) -> bool:
        if not filters:
            return True
        data = item.model_dump(mode="python") if hasattr(item, "model_dump") else item
        for filter_item in filters:
            actual = cls._get_value_by_path(data, filter_item.field)
            expected = filter_item.value
            op = filter_item.op
            if op == "eq" and actual != expected:
                return False
            if op == "ne" and actual == expected:
                return False
            if op == "gt" and not (actual is not None and actual > expected):
                return False
            if op == "gte" and not (actual is not None and actual >= expected):
                return False
            if op == "lt" and not (actual is not None and actual < expected):
                return False
            if op == "lte" and not (actual is not None and actual <= expected):
                return False
            if op == "in" and not (expected is not None and actual in expected):
                return False
            if op == "contains":
                if isinstance(actual, str):
                    if not isinstance(expected, str) or expected not in actual:
                        return False
                elif isinstance(actual, (list, tuple, set)):
                    if expected not in actual:
                        return False
                else:
                    return False
            if op == "exists":
                exists = actual is not None
                if bool(expected) != exists:
                    return False
        return True

    def _guard_slow_list_operation(self, operation_name: str, *, alternatives: str) -> None:
        if self.slow_ops_policy == SlowOpsPolicy.ALLOW:
            return

        message = (
            f"{operation_name}() eagerly materializes an unbounded result set and may not scale. "
            f"Use {alternatives} instead."
        )
        if self.slow_ops_policy == SlowOpsPolicy.WARN:
            warnings.warn(message, SlowOperationWarning, stacklevel=2)
            return
        raise SlowOperationDisabledError(message)

    async def get_health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "database": self.mongo_db_name,
            "default_mount": self.store.default_mount,
        }

    async def summary(self) -> str:
        asset_count = await self.asset_database.count_documents()
        collection_count = await self.collection_database.count_documents()
        collection_item_count = await self.collection_item_database.count_documents()
        asset_retention_count = await self.asset_retention_database.count_documents()
        annotation_schema_count = await self.annotation_schema_database.count_documents()
        annotation_set_count = await self.annotation_set_database.count_documents()
        annotation_record_count = await self.annotation_record_database.count_documents()
        datum_count = await self.datum_database.count_documents()
        dataset_version_count = await self.dataset_version_database.count_documents()
        return (
            f"AsyncDatalake(database={self.mongo_db_name}, default_mount={self.store.default_mount}, "
            f"assets={asset_count}, collections={collection_count}, collection_items={collection_item_count}, "
            f"asset_retentions={asset_retention_count}, annotation_schemas={annotation_schema_count}, "
            f"annotation_sets={annotation_set_count}, annotation_records={annotation_record_count}, datums={datum_count}, "
            f"dataset_versions={dataset_version_count})"
        )

    def __str__(self) -> str:
        return f"AsyncDatalake(database={self.mongo_db_name}, default_mount={self.store.default_mount})"

    def get_mounts(self) -> dict[str, Any]:
        mount_info = self.store.list_mount_info()
        mounts = [{"name": name, **info} for name, info in mount_info.items()]
        return {"default_mount": self.store.default_mount, "mounts": mounts}

    async def put_object(
        self,
        *,
        name: str,
        obj: Any,
        mount: str | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
        on_conflict: str | None = None,
    ) -> StorageRef:
        target_mount = mount or self.store.default_mount
        key = self.store.build_key(target_mount, name, version)
        saved_version = self.store.save(key, obj, version=version, metadata=metadata, on_conflict=on_conflict)
        resolved_version = saved_version if isinstance(saved_version, str) else version or "latest"
        return StorageRef(mount=target_mount, name=name, version=resolved_version)

    async def get_object(self, storage_ref: StorageRef, **kwargs) -> Any:
        storage_ref = self._normalize_storage_ref(storage_ref)
        key = self.store.build_key(storage_ref.mount, storage_ref.name, storage_ref.version)
        return self.store.load(key, version=storage_ref.version, **kwargs)

    async def head_object(self, storage_ref: StorageRef) -> dict[str, Any]:
        storage_ref = self._normalize_storage_ref(storage_ref)
        key = self.store.build_key(storage_ref.mount, storage_ref.name, storage_ref.version)
        return self.store.info(key, version=storage_ref.version)

    async def object_exists(self, storage_ref: StorageRef) -> bool:
        """Return True if the object version exists on this lake's store.

        Uses :meth:`Store.has_object` so existence matches registry metadata (including nested
        object names). :meth:`Registry.info` can return an empty dict for missing objects without
        raising, so ``head_object`` alone would falsely report existence.
        """
        storage_ref = self._normalize_storage_ref(storage_ref)
        key = self.store.build_key(storage_ref.mount, storage_ref.name, storage_ref.version)
        version = storage_ref.version if storage_ref.version is not None else "latest"
        try:
            return self.store.has_object(key, version=version)
        except (RegistryObjectNotFound, StoreLocationNotFound, FileNotFoundError, KeyError, OSError):
            return False

    def dataset_sync(self, target: "AsyncDatalake" | None = None):
        from mindtrace.datalake.sync import DatasetSyncManager

        return DatasetSyncManager(self, target=target)

    def replication(self, target: "AsyncDatalake" | None = None):
        from mindtrace.datalake.replication import ReplicationManager

        return ReplicationManager(self, target=target)

    async def copy_object(
        self,
        source: StorageRef,
        *,
        target_mount: str,
        target_name: str,
        target_version: str | None = None,
    ) -> StorageRef:
        source = self._normalize_storage_ref(source)
        source_key = self.store.build_key(source.mount, source.name, source.version)
        target_key = self.store.build_key(target_mount, target_name, target_version)
        saved_version = self.store.copy(
            source_key,
            target=target_key,
            source_version=source.version or "latest",
            target_version=target_version,
        )
        return StorageRef(mount=target_mount, name=target_name, version=saved_version)

    async def create_object_upload_session(
        self,
        *,
        name: str,
        mount: str | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
        on_conflict: str | None = None,
        content_type: str = "application/octet-stream",
        expires_in_minutes: int = 60,
        created_by: str | None = None,
    ) -> DirectUploadSession:
        if expires_in_minutes <= 0:
            raise ValueError("expires_in_minutes must be positive")

        target_mount = mount or self.store.default_mount
        session = self._build_document(
            DirectUploadSession,
            name=name,
            mount=target_mount,
            requested_version=version,
            metadata=metadata or {},
            on_conflict=on_conflict,
            upload_method="local_path",
            content_type=content_type,
            expires_at=self._utc_now() + timedelta(minutes=expires_in_minutes),
            created_by=created_by,
        )
        key = self.store.build_key(target_mount, name, version)
        target = self.store.create_direct_upload_target(
            key,
            content_type=content_type,
            expiration_minutes=expires_in_minutes,
            upload_id=session.upload_session_id,
        )
        session.upload_method = target["upload_method"]
        session.upload_url = target.get("upload_url")
        session.upload_path = target.get("upload_path")
        session.upload_headers = target.get("upload_headers", {})
        session.staged_reference = target.get("staged_target", {})
        return await self.direct_upload_session_database.insert(session)

    async def get_object_upload_session(self, upload_session_id: str) -> DirectUploadSession:
        sessions = await self.direct_upload_session_database.find({"upload_session_id": upload_session_id})
        if not sessions:
            raise DocumentNotFoundError(f"Upload session with upload_session_id {upload_session_id} not found")
        return sessions[0]

    async def complete_object_upload_session(
        self,
        upload_session_id: str,
        *,
        finalize_token: str,
        metadata: dict[str, Any] | None = None,
    ) -> DirectUploadSession:
        session = await self.get_object_upload_session(upload_session_id)
        if session.finalize_token != finalize_token:
            raise ValueError("Invalid finalize token")
        return await self._verify_and_finalize_upload_session(session, metadata=metadata, allow_pending_missing=False)

    async def reconcile_upload_sessions(self, limit: int = 100) -> list[DirectUploadSession]:
        pending = await self.direct_upload_session_database.find({"status": "pending"})
        now = self._utc_now()
        reconciled: list[DirectUploadSession] = []
        for session in pending[:limit]:
            session.expires_at = self._coerce_utc(session.expires_at)
            if session.expires_at <= now:
                reconciled.append(
                    await self._verify_and_finalize_upload_session(
                        session,
                        metadata=None,
                        allow_pending_missing=True,
                    )
                )
        return reconciled

    async def _verify_and_finalize_upload_session(
        self,
        session: DirectUploadSession,
        *,
        metadata: dict[str, Any] | None,
        allow_pending_missing: bool,
    ) -> DirectUploadSession:
        if session.status in {"completed", "cleaned"}:
            return session

        key = self.store.build_key(session.mount, session.name, session.requested_version)
        session.verification_attempts += 1
        session.last_verified_at = self._utc_now()
        session.expires_at = self._coerce_utc(session.expires_at)

        inspection = self.store.inspect_direct_upload_target(key, staged_target=session.staged_reference)
        if not inspection.get("exists"):
            if allow_pending_missing and session.expires_at <= self._utc_now():
                session.status = "expired"
                session.failure_reason = "Upload did not complete before expiry."
                session.cleanup_completed_at = self._utc_now()
            await self.direct_upload_session_database.update(session)
            if allow_pending_missing:
                return session
            raise FileNotFoundError(f"Staged upload not found for session {session.upload_session_id}")

        try:
            resolved_version = self.store.commit_direct_upload(
                key,
                staged_target=session.staged_reference,
                version=session.requested_version,
                metadata={**session.metadata, **(metadata or {})},
                on_conflict=session.on_conflict,
            )
        except Exception as e:
            cleanup_ok = self.store.cleanup_direct_upload_target(key, staged_target=session.staged_reference)
            session.status = "failed"
            session.failure_reason = str(e)
            if cleanup_ok:
                session.cleanup_completed_at = self._utc_now()
            await self.direct_upload_session_database.update(session)
            raise

        session.metadata = {**session.metadata, **(metadata or {})}
        session.resolved_version = resolved_version
        session.storage_ref = StorageRef(
            mount=session.mount,
            name=session.name,
            version=resolved_version,
        )
        session.status = "completed"
        session.failure_reason = None
        session.completed_at = self._utc_now()
        session.cleanup_completed_at = session.completed_at
        return await self.direct_upload_session_database.update(session)

    async def create_asset(
        self,
        *,
        kind: str,
        media_type: str,
        storage_ref: StorageRef,
        checksum: str | None = None,
        size_bytes: int | None = None,
        subject: SubjectRef | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Asset:
        asset = self._build_document(
            Asset,
            kind=kind,
            media_type=media_type,
            storage_ref=self._normalize_storage_ref(storage_ref),
            checksum=checksum,
            size_bytes=size_bytes,
            subject=subject,
            metadata=metadata or {},
            created_by=created_by,
            updated_at=self._utc_now(),
        )
        inserted = await self.asset_database.insert(asset)
        await self.ensure_primary_asset_alias(inserted)
        return inserted

    async def ensure_primary_asset_alias(self, asset: Asset) -> AssetAlias:
        """Ensure a primary alias row exists with ``alias == asset.asset_id`` (idempotent)."""
        existing = await self.asset_alias_database.find({"alias": asset.asset_id})
        if existing:
            row = existing[0]
            if row.asset_id != asset.asset_id:
                raise DuplicateAliasError(f"Alias {asset.asset_id!r} is already mapped to asset_id {row.asset_id!r}")
            return row
        doc = self._build_document(
            AssetAlias,
            alias=asset.asset_id,
            asset_id=asset.asset_id,
            is_primary=True,
            created_at=self._utc_now(),
        )
        return await self.asset_alias_database.insert(doc)

    async def resolve_alias(self, alias: str) -> str:
        """Return ``asset_id`` for a string alias, or raise :class:`~mindtrace.database.core.exceptions.DocumentNotFoundError`."""
        rows = await self.asset_alias_database.find({"alias": alias})
        if not rows:
            raise DocumentNotFoundError(f"No asset alias {alias!r}")
        return rows[0].asset_id

    async def add_alias(self, asset_id: str, alias: str) -> AssetAlias:
        """Register an additional alias for ``asset_id``. Raises :class:`~mindtrace.datalake.types.DuplicateAliasError` on conflict."""
        await self.get_asset(asset_id)
        if alias == asset_id:
            return await self.ensure_primary_asset_alias(await self.get_asset(asset_id))
        existing = await self.asset_alias_database.find({"alias": alias})
        if existing:
            if existing[0].asset_id == asset_id:
                return existing[0]
            raise DuplicateAliasError(f"Alias {alias!r} is already mapped to asset_id {existing[0].asset_id!r}")
        doc = self._build_document(
            AssetAlias,
            alias=alias,
            asset_id=asset_id,
            is_primary=False,
            created_at=self._utc_now(),
        )
        try:
            return await self.asset_alias_database.insert(doc)
        except DuplicateInsertError as e:
            raise DuplicateAliasError(f"Alias {alias!r} already exists") from e

    async def remove_alias(self, alias: str) -> None:
        """Remove an alias mapping. Refuses to remove the primary alias where ``alias == asset_id``."""
        rows = await self.asset_alias_database.find({"alias": alias})
        if not rows:
            raise DocumentNotFoundError(f"No asset alias {alias!r}")
        row = rows[0]
        if row.is_primary and row.alias == row.asset_id:
            raise ValueError("Cannot remove the primary alias (alias equal to asset_id); delete the asset instead")
        await self.asset_alias_database.delete(row.id)

    async def list_aliases_for_asset(self, asset_id: str) -> list[str]:
        """Return all alias strings registered for ``asset_id``."""
        rows = await self.asset_alias_database.find({"asset_id": asset_id})
        return [r.alias for r in rows]

    async def get_asset_by_alias(self, alias: str) -> Asset:
        """Load :class:`Asset` by alias string."""
        return await self.get_asset(await self.resolve_alias(alias))

    async def get_asset(self, asset_id: str) -> Asset:
        results = await self.asset_database.find({"asset_id": asset_id})
        if not results:
            raise DocumentNotFoundError(f"Asset with asset_id {asset_id} not found")
        return results[0]

    async def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        self._guard_slow_list_operation("list_assets", alternatives="iter_assets() or list_assets_page()")
        return await self.asset_database.find(filters or {})

    async def iter_assets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Asset]:
        async for asset in self._iter_database(
            database=self.asset_database,
            resource="assets",
            filters=filters,
            sort=sort,
            batch_size=batch_size,
        ):
            yield asset

    async def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        return await self._paginate_database(
            database=self.asset_database,
            resource="assets",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def update_asset_metadata(self, asset_id: str, metadata: dict[str, Any]) -> Asset:
        asset = await self.get_asset(asset_id)
        asset.metadata = metadata
        asset.updated_at = self._utc_now()
        return await self.asset_database.update(asset)

    async def delete_asset(self, asset_id: str) -> None:
        asset = await self.get_asset(asset_id)
        datums = await self.list_datums()
        if any(asset_id in getattr(datum, "asset_refs", {}).values() for datum in datums):
            raise ValueError(f"Asset {asset_id} is still referenced by one or more datums")
        collection_items = await self.collection_item_database.find({"asset_id": asset_id})
        if collection_items:
            raise ValueError(f"Asset {asset_id} is still referenced by one or more collection items")
        alias_rows = await self.asset_alias_database.find({"asset_id": asset_id})
        for row in alias_rows:
            await self.asset_alias_database.delete(row.id)
        await self.asset_database.delete(asset.id)

    async def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Collection:
        collection = self._build_document(
            Collection,
            name=name,
            description=description,
            status=status,
            metadata=metadata or {},
            created_by=created_by,
            updated_at=self._utc_now(),
        )
        return await self.collection_database.insert(collection)

    async def get_collection(self, collection_id: str) -> Collection:
        results = await self.collection_database.find({"collection_id": collection_id})
        if not results:
            raise DocumentNotFoundError(f"Collection with collection_id {collection_id} not found")
        return results[0]

    async def list_collections(self, filters: dict[str, Any] | None = None) -> list[Collection]:
        self._guard_slow_list_operation("list_collections", alternatives="list_collections_page()")
        return await self.collection_database.find(filters or {})

    async def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Collection]:
        return await self._paginate_database(
            database=self.collection_database,
            resource="collections",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def update_collection(self, collection_id: str, **changes: Any) -> Collection:
        collection = await self.get_collection(collection_id)
        for key, value in changes.items():
            setattr(collection, key, value)
        collection.updated_at = self._utc_now()
        return await self.collection_database.update(collection)

    async def delete_collection(self, collection_id: str) -> None:
        collection = await self.get_collection(collection_id)
        collection_items = await self.collection_item_database.find({"collection_id": collection_id})
        for collection_item in collection_items:
            await self.collection_item_database.delete(collection_item.id)
        await self.collection_database.delete(collection.id)

    async def create_collection_item(
        self,
        *,
        collection_id: str,
        asset_id: str,
        split: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> CollectionItem:
        await self.get_collection(collection_id)
        await self.get_asset(asset_id)
        collection_item = self._build_document(
            CollectionItem,
            collection_id=collection_id,
            asset_id=asset_id,
            split=split,
            status=status,
            metadata=metadata or {},
            added_by=added_by,
            updated_at=self._utc_now(),
        )
        return await self.collection_item_database.insert(collection_item)

    async def get_collection_item(self, collection_item_id: str) -> CollectionItem:
        results = await self.collection_item_database.find({"collection_item_id": collection_item_id})
        if not results:
            raise DocumentNotFoundError(f"CollectionItem with collection_item_id {collection_item_id} not found")
        return results[0]

    async def list_collection_items(self, filters: dict[str, Any] | None = None) -> list[CollectionItem]:
        self._guard_slow_list_operation("list_collection_items", alternatives="list_collection_items_page()")
        return await self.collection_item_database.find(filters or {})

    async def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[CollectionItem]:
        return await self._paginate_database(
            database=self.collection_item_database,
            resource="collection_items",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def resolve_collection_item(self, collection_item_id: str) -> ResolvedCollectionItem:
        collection_item = await self.get_collection_item(collection_item_id)
        collection = await self.get_collection(collection_item.collection_id)
        asset = await self.get_asset(collection_item.asset_id)
        return ResolvedCollectionItem(
            collection_item=collection_item,
            collection=collection,
            asset=asset,
        )

    async def update_collection_item(self, collection_item_id: str, **changes: Any) -> CollectionItem:
        collection_item = await self.get_collection_item(collection_item_id)
        if "collection_id" in changes and changes["collection_id"] is not None:
            await self.get_collection(changes["collection_id"])
        if "asset_id" in changes and changes["asset_id"] is not None:
            await self.get_asset(changes["asset_id"])
        for key, value in changes.items():
            setattr(collection_item, key, value)
        collection_item.updated_at = self._utc_now()
        return await self.collection_item_database.update(collection_item)

    async def delete_collection_item(self, collection_item_id: str) -> None:
        collection_item = await self.get_collection_item(collection_item_id)
        await self.collection_item_database.delete(collection_item.id)

    async def create_asset_retention(
        self,
        *,
        asset_id: str,
        owner_type: str,
        owner_id: str,
        retention_policy: str = "retain",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> AssetRetention:
        await self.get_asset(asset_id)
        asset_retention = self._build_document(
            AssetRetention,
            asset_id=asset_id,
            owner_type=owner_type,
            owner_id=owner_id,
            retention_policy=retention_policy,
            metadata=metadata or {},
            created_by=created_by,
            updated_at=self._utc_now(),
        )
        return await self.asset_retention_database.insert(asset_retention)

    async def get_asset_retention(self, asset_retention_id: str) -> AssetRetention:
        results = await self.asset_retention_database.find({"asset_retention_id": asset_retention_id})
        if not results:
            raise DocumentNotFoundError(f"AssetRetention with asset_retention_id {asset_retention_id} not found")
        return results[0]

    async def list_asset_retentions(self, filters: dict[str, Any] | None = None) -> list[AssetRetention]:
        self._guard_slow_list_operation("list_asset_retentions", alternatives="list_asset_retentions_page()")
        return await self.asset_retention_database.find(filters or {})

    async def list_asset_retentions_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[AssetRetention]:
        return await self._paginate_database(
            database=self.asset_retention_database,
            resource="asset_retentions",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def update_asset_retention(self, asset_retention_id: str, **changes: Any) -> AssetRetention:
        asset_retention = await self.get_asset_retention(asset_retention_id)
        if "asset_id" in changes and changes["asset_id"] is not None:
            await self.get_asset(changes["asset_id"])
        for key, value in changes.items():
            setattr(asset_retention, key, value)
        asset_retention.updated_at = self._utc_now()
        return await self.asset_retention_database.update(asset_retention)

    async def delete_asset_retention(self, asset_retention_id: str) -> None:
        asset_retention = await self.get_asset_retention(asset_retention_id)
        await self.asset_retention_database.delete(asset_retention.id)

    async def create_annotation_schema(
        self,
        *,
        name: str,
        version: str,
        task_type: str,
        allowed_annotation_kinds: list[str],
        labels: list[AnnotationLabelDefinition | dict[str, Any]] | None = None,
        allow_scores: bool = False,
        required_attributes: list[str] | None = None,
        optional_attributes: list[str] | None = None,
        allow_additional_attributes: bool = False,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> AnnotationSchema:
        existing = await self.annotation_schema_database.find({"name": name, "version": version})
        if existing:
            raise DuplicateAnnotationSchemaError(f"Annotation schema already exists: {name}@{version}")
        normalized_labels = [
            label if isinstance(label, AnnotationLabelDefinition) else AnnotationLabelDefinition(**label)
            for label in (labels or [])
        ]
        schema = self._build_document(
            AnnotationSchema,
            name=name,
            version=version,
            task_type=task_type,
            allowed_annotation_kinds=allowed_annotation_kinds,
            labels=normalized_labels,
            allow_scores=allow_scores,
            required_attributes=required_attributes or [],
            optional_attributes=optional_attributes or [],
            allow_additional_attributes=allow_additional_attributes,
            metadata=metadata or {},
            created_by=created_by,
            updated_at=self._utc_now(),
        )
        try:
            return await self.annotation_schema_database.insert(schema)
        except DuplicateInsertError as exc:
            raise DuplicateAnnotationSchemaError(f"Annotation schema already exists: {name}@{version}") from exc

    async def get_annotation_schema(self, annotation_schema_id: str) -> AnnotationSchema:
        results = await self.annotation_schema_database.find({"annotation_schema_id": annotation_schema_id})
        if not results:
            raise DocumentNotFoundError(f"AnnotationSchema with annotation_schema_id {annotation_schema_id} not found")
        return results[0]

    async def get_annotation_schema_by_name_version(self, name: str, version: str) -> AnnotationSchema:
        results = await self.annotation_schema_database.find({"name": name, "version": version})
        if not results:
            raise DocumentNotFoundError(f"AnnotationSchema {name}@{version} not found")
        return results[0]

    async def list_annotation_schemas(self, filters: dict[str, Any] | None = None) -> list[AnnotationSchema]:
        self._guard_slow_list_operation("list_annotation_schemas", alternatives="list_annotation_schemas_page()")
        return await self.annotation_schema_database.find(filters or {})

    async def list_annotation_schemas_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[AnnotationSchema]:
        return await self._paginate_database(
            database=self.annotation_schema_database,
            resource="annotation_schemas",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def update_annotation_schema(self, annotation_schema_id: str, **changes: Any) -> AnnotationSchema:
        schema = await self.get_annotation_schema(annotation_schema_id)
        if "labels" in changes and changes["labels"] is not None:
            changes["labels"] = [
                label if isinstance(label, AnnotationLabelDefinition) else AnnotationLabelDefinition(**label)
                for label in changes["labels"]
            ]
        for key, value in changes.items():
            setattr(schema, key, value)
        schema.updated_at = self._utc_now()
        return await self.annotation_schema_database.update(schema)

    async def delete_annotation_schema(self, annotation_schema_id: str) -> None:
        schema = await self.get_annotation_schema(annotation_schema_id)
        referencing_sets = await self.annotation_set_database.find({"annotation_schema_id": annotation_schema_id})
        if referencing_sets:
            raise AnnotationSchemaInUseError(
                f"Annotation schema {annotation_schema_id} is still referenced by {len(referencing_sets)} annotation set(s)"
            )
        await self.annotation_schema_database.delete(schema.id)

    def _validate_annotation_kind_for_schema(self, record: AnnotationRecord, schema: AnnotationSchema) -> None:
        if record.kind not in schema.allowed_annotation_kinds:
            raise AnnotationSchemaValidationError(
                f"Annotation kind '{record.kind}' is not allowed by schema '{schema.name}@{schema.version}'"
            )

    def _validate_annotation_label_for_schema(self, record: AnnotationRecord, schema: AnnotationSchema) -> None:
        labels_by_name = {label.name: label for label in schema.labels}
        if record.label not in labels_by_name:
            raise AnnotationSchemaValidationError(
                f"Annotation label '{record.label}' is not defined in schema '{schema.name}@{schema.version}'"
            )
        label_definition = labels_by_name[record.label]
        if record.label_id is not None and label_definition.id is not None and record.label_id != label_definition.id:
            raise AnnotationSchemaValidationError(
                f"Annotation label_id {record.label_id} does not match schema label id {label_definition.id} for label '{record.label}'"
            )

    def _validate_annotation_geometry_for_schema(self, record: AnnotationRecord, schema: AnnotationSchema) -> None:
        geometry = record.geometry or {}
        if schema.task_type == "classification":
            if geometry:
                raise AnnotationSchemaValidationError("Classification annotations must not include geometry")
            return
        if schema.task_type == "detection":
            missing = [field for field in ("x", "y", "width", "height") if field not in geometry]
            if missing:
                raise AnnotationSchemaValidationError(
                    f"BBox annotation is missing required geometry fields: {', '.join(missing)}"
                )
            return
        if schema.task_type == "segmentation":
            if not geometry:
                raise AnnotationSchemaValidationError("Mask annotation must include non-empty geometry")
            if not any(key in geometry for key in ("storage_ref", "mask_asset_id", "encoding")):
                raise AnnotationSchemaValidationError(
                    "Mask annotation geometry must include at least one of: storage_ref, mask_asset_id, encoding"
                )

    def _validate_annotation_attributes_for_schema(self, record: AnnotationRecord, schema: AnnotationSchema) -> None:
        attributes = record.attributes or {}
        missing_required = [name for name in schema.required_attributes if name not in attributes]
        if missing_required:
            raise AnnotationSchemaValidationError(
                f"Annotation attributes missing required fields: {', '.join(missing_required)}"
            )
        if not schema.allow_additional_attributes:
            allowed_attributes = set(schema.required_attributes) | set(schema.optional_attributes)
            unknown = sorted(set(attributes) - allowed_attributes)
            if unknown:
                raise AnnotationSchemaValidationError(
                    f"Annotation attributes not allowed by schema '{schema.name}@{schema.version}': {', '.join(unknown)}"
                )

    def _validate_annotation_record_against_schema(self, record: AnnotationRecord, schema: AnnotationSchema) -> None:
        self._validate_annotation_kind_for_schema(record, schema)
        self._validate_annotation_label_for_schema(record, schema)
        self._validate_annotation_geometry_for_schema(record, schema)
        self._validate_annotation_attributes_for_schema(record, schema)
        if record.score is not None and not schema.allow_scores:
            raise AnnotationSchemaValidationError(
                f"Annotation scores are not allowed by schema '{schema.name}@{schema.version}'"
            )

    def _coerce_annotation_record(self, annotation: AnnotationRecord | dict[str, Any]) -> AnnotationRecord:
        if isinstance(annotation, AnnotationRecord):
            annotation.updated_at = self._utc_now()
            return annotation

        source = annotation.get("source")
        if isinstance(source, dict):
            source = AnnotationSource(**source)
        subject = annotation.get("subject")
        if isinstance(subject, dict):
            subject = SubjectRef(**subject)
        return self._build_document(
            AnnotationRecord,
            subject=subject,
            kind=annotation["kind"],
            label=annotation["label"],
            label_id=annotation.get("label_id"),
            score=annotation.get("score"),
            source=source,
            geometry=annotation.get("geometry", {}),
            attributes=annotation.get("attributes", {}),
            metadata=annotation.get("metadata", {}),
            updated_at=self._utc_now(),
        )

    async def _rollback_inserted_annotation_records(self, inserted_records: list[AnnotationRecord]) -> None:
        for record in reversed(inserted_records):
            if getattr(record, "id", None) is None:
                continue
            try:
                await self.annotation_record_database.delete(record.id)
            except Exception:
                pass

    async def create_annotation_set(
        self,
        *,
        name: str,
        purpose: str,
        source_type: str,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
        datum_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> AnnotationSet:
        if annotation_schema_id is not None:
            await self.get_annotation_schema(annotation_schema_id)
        datum = None
        if datum_id is not None:
            datum = await self.get_datum(datum_id)
        annotation_set = self._build_document(
            AnnotationSet,
            name=name,
            purpose=purpose,
            source_type=source_type,
            status=status,
            annotation_schema_id=annotation_schema_id,
            metadata=metadata or {},
            created_by=created_by,
            updated_at=self._utc_now(),
        )
        inserted = await self.annotation_set_database.insert(annotation_set)
        if datum is not None:
            if inserted.annotation_set_id not in datum.annotation_set_ids:
                datum.annotation_set_ids.append(inserted.annotation_set_id)
                datum.updated_at = self._utc_now()
                try:
                    await self.datum_database.update(datum)
                except Exception:
                    try:
                        await self.annotation_set_database.delete(inserted.id)
                    except Exception:
                        pass
                    raise
        return inserted

    async def get_annotation_set(self, annotation_set_id: str) -> AnnotationSet:
        results = await self.annotation_set_database.find({"annotation_set_id": annotation_set_id})
        if not results:
            raise DocumentNotFoundError(f"AnnotationSet with annotation_set_id {annotation_set_id} not found")
        return results[0]

    async def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]:
        self._guard_slow_list_operation("list_annotation_sets", alternatives="list_annotation_sets_page()")
        return await self.annotation_set_database.find(filters or {})

    async def list_annotation_sets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[AnnotationSet]:
        return await self._paginate_database(
            database=self.annotation_set_database,
            resource="annotation_sets",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def update_annotation_set(self, annotation_set_id: str, **changes: Any) -> AnnotationSet:
        annotation_set = await self.get_annotation_set(annotation_set_id)
        if "annotation_schema_id" in changes and changes["annotation_schema_id"] is not None:
            await self.get_annotation_schema(changes["annotation_schema_id"])
        for key, value in changes.items():
            setattr(annotation_set, key, value)
        annotation_set.updated_at = self._utc_now()
        return await self.annotation_set_database.update(annotation_set)

    def _assert_asset_subject_for_set_less_records(self, records: list[AnnotationRecord]) -> None:
        """When inserting without an :class:`AnnotationSet`, each record must target an asset."""
        for record in records:
            sub = record.subject
            if sub is None:
                raise ValueError(
                    "When annotation_set_id is omitted, each annotation must include "
                    "subject=SubjectRef(kind='asset', id=<asset_id>)."
                )
            if sub.kind != "asset":
                raise ValueError(f"When annotation_set_id is omitted, subject.kind must be 'asset', got {sub.kind!r}.")
            if not str(sub.id).strip():
                raise ValueError("When annotation_set_id is omitted, subject.id must be a non-empty asset id.")

    async def _schema_for_annotation_insert(
        self,
        *,
        annotation_set_id: str | None,
        annotation_schema_id: str | None,
    ) -> AnnotationSchema | None:
        if annotation_set_id is not None:
            annotation_set = await self.get_annotation_set(annotation_set_id)
            if annotation_set.annotation_schema_id is None:
                return None
            return await self.get_annotation_schema(annotation_set.annotation_schema_id)
        if annotation_schema_id is not None:
            return await self.get_annotation_schema(annotation_schema_id)
        return None

    async def _datums_referencing_annotation_set(self, annotation_set_id: str) -> list[Datum]:
        return await self.datum_database.find({"annotation_set_ids": annotation_set_id})

    async def _merge_asset_subjects_from_datum_links(
        self,
        annotation_set_id: str,
        annotations: list[Any],
    ) -> list[Any]:
        """When inserting into an annotation set, ensure ``subject`` targets the image asset.

        ``Datum.annotation_set_ids`` links sets to datums; ``datum.asset_refs['image']`` supplies the
        canonical image asset id for dataset / importer rows. Callers may still pass an explicit
        ``subject``; those values are preserved.
        """
        datums = await self._datums_referencing_annotation_set(annotation_set_id)

        def _needs_subject(a: Any) -> bool:
            if isinstance(a, dict):
                return a.get("subject") is None
            return getattr(a, "subject", None) is None

        def _any_missing_subject() -> bool:
            return any(_needs_subject(a) for a in annotations)

        if not datums:
            if _any_missing_subject():
                raise ValueError(
                    "No Datum references this annotation set (Datum.annotation_set_ids does not "
                    "include this set). Either link the AnnotationSet to a Datum via "
                    "create_annotation_set(..., datum_id=...), or provide an explicit asset subject "
                    "on each annotation record."
                )
            return annotations

        image_ids = [d.asset_refs.get("image") for d in datums if d.asset_refs.get("image")]
        if not image_ids:
            if _any_missing_subject():
                raise ValueError(
                    "Datums linked to this annotation set have no asset_refs['image']. "
                    "Add an 'image' role to datum.asset_refs, or provide an explicit asset subject "
                    "on each annotation record."
                )
            return annotations

        unique_images = set(image_ids)
        if len(unique_images) > 1:
            raise ValueError(
                "Annotation set is linked to multiple datums whose asset_refs['image'] disagree. "
                "Provide an explicit asset subject on each annotation record."
            )
        default_image = image_ids[0]

        merged: list[Any] = []
        for a in annotations:
            if isinstance(a, dict):
                if a.get("subject") is None:
                    merged.append({**a, "subject": {"kind": "asset", "id": default_image}})
                else:
                    merged.append(a)
            elif getattr(a, "subject", None) is None:
                merged.append(
                    a.model_copy(update={"subject": SubjectRef(kind="asset", id=default_image)}),
                )
            else:
                merged.append(a)
        return merged

    async def add_annotation_records(
        self,
        annotations: Iterable[AnnotationRecord | dict[str, Any]],
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        """Insert annotation records.

        If ``annotation_set_id`` is set, records are registered on that set and validated against
        its bound schema when present. For sets linked from at least one :class:`Datum` whose
        ``annotation_set_ids`` contains this set, any record without a ``subject`` is given
        ``subject=SubjectRef(kind='asset', id=datum.asset_refs['image'])`` when that image ref is
        unambiguous across linked datums—so asset-scoped queries stay consistent with datum-scoped
        grouping without callers manually duplicating subjects.

        If ``annotation_set_id`` is omitted, records are stored without belonging to any set; each
        must have ``subject`` referencing an asset (``kind='asset'``). Optional
        ``annotation_schema_id`` enables schema validation for that free-standing insert.
        """
        annotations_list = list(annotations)
        if not annotations_list:
            return []

        if annotation_set_id is not None:
            annotations_list = await self._merge_asset_subjects_from_datum_links(
                annotation_set_id,
                annotations_list,
            )

        candidate_records = [self._coerce_annotation_record(a) for a in annotations_list]

        if annotation_set_id is None:
            self._assert_asset_subject_for_set_less_records(candidate_records)

        schema = await self._schema_for_annotation_insert(
            annotation_set_id=annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )
        for record in candidate_records:
            if schema is not None:
                self._validate_annotation_record_against_schema(record, schema)

        inserted_records: list[AnnotationRecord] = []
        try:
            for record in candidate_records:
                inserted = await self.annotation_record_database.insert(record)
                inserted_records.append(inserted)
        except Exception:
            await self._rollback_inserted_annotation_records(inserted_records)
            raise

        if annotation_set_id is None:
            return inserted_records

        annotation_set = await self.get_annotation_set(annotation_set_id)
        previous_record_ids = list(annotation_set.annotation_record_ids)
        next_record_ids = list(previous_record_ids)
        for inserted in inserted_records:
            if inserted.annotation_id not in next_record_ids:
                next_record_ids.append(inserted.annotation_id)

        annotation_set.annotation_record_ids = next_record_ids
        annotation_set.updated_at = self._utc_now()
        try:
            await self.annotation_set_database.update(annotation_set)
        except Exception:
            annotation_set.annotation_record_ids = previous_record_ids
            await self._rollback_inserted_annotation_records(inserted_records)
            raise
        return inserted_records

    async def list_annotation_records_for_asset(self, asset_id: str) -> list[AnnotationRecord]:
        """Return annotation records whose subject is the given asset."""
        self._guard_slow_list_operation(
            "list_annotation_records_for_asset",
            alternatives="list_annotation_records_for_asset_page()",
        )
        return await self.list_annotation_records(
            filters={"subject.kind": "asset", "subject.id": asset_id},
        )

    async def list_annotation_records_for_asset_page(
        self,
        asset_id: str,
        *,
        sort: str = "subject_created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[AnnotationRecord]:
        return await self._paginate_database(
            database=self.annotation_record_database,
            resource="annotation_records",
            filters={"subject.kind": "asset", "subject.id": asset_id},
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def get_annotation_record(self, annotation_id: str) -> AnnotationRecord:
        results = await self.annotation_record_database.find({"annotation_id": annotation_id})
        if not results:
            raise DocumentNotFoundError(f"AnnotationRecord with annotation_id {annotation_id} not found")
        return results[0]

    async def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]:
        self._guard_slow_list_operation(
            "list_annotation_records",
            alternatives="iter_annotation_records() or list_annotation_records_page()",
        )
        return await self.annotation_record_database.find(filters or {})

    async def iter_annotation_records(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[AnnotationRecord]:
        async for record in self._iter_database(
            database=self.annotation_record_database,
            resource="annotation_records",
            filters=filters,
            sort=sort,
            batch_size=batch_size,
        ):
            yield record

    async def list_annotation_records_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[AnnotationRecord]:
        return await self._paginate_database(
            database=self.annotation_record_database,
            resource="annotation_records",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def update_annotation_record(self, annotation_id: str, **changes: Any) -> AnnotationRecord:
        record = await self.get_annotation_record(annotation_id)
        for key, value in changes.items():
            if key == "source" and isinstance(value, dict):
                value = AnnotationSource(**value)
            setattr(record, key, value)
        record.updated_at = self._utc_now()
        return await self.annotation_record_database.update(record)

    async def delete_annotation_record(self, annotation_id: str) -> None:
        record = await self.get_annotation_record(annotation_id)
        annotation_sets = await self.list_annotation_sets()
        for annotation_set in annotation_sets:
            if annotation_id in annotation_set.annotation_record_ids:
                annotation_set.annotation_record_ids = [
                    existing_id for existing_id in annotation_set.annotation_record_ids if existing_id != annotation_id
                ]
                annotation_set.updated_at = self._utc_now()
                await self.annotation_set_database.update(annotation_set)
        await self.annotation_record_database.delete(record.id)

    async def create_datum(
        self,
        *,
        asset_refs: dict[str, str],
        split: str | None = None,
        metadata: dict[str, Any] | None = None,
        annotation_set_ids: list[str] | None = None,
    ) -> Datum:
        await self._validate_asset_refs_exist(asset_refs)
        await self._validate_annotation_set_ids_exist(annotation_set_ids or [])
        datum = self._build_document(
            Datum,
            split=split,
            asset_refs=asset_refs,
            metadata=metadata or {},
            annotation_set_ids=annotation_set_ids or [],
            updated_at=self._utc_now(),
        )
        return await self.datum_database.insert(datum)

    async def get_datum(self, datum_id: str) -> Datum:
        results = await self.datum_database.find({"datum_id": datum_id})
        if not results:
            raise DocumentNotFoundError(f"Datum with datum_id {datum_id} not found")
        return results[0]

    async def list_datums(self, filters: dict[str, Any] | None = None) -> list[Datum]:
        self._guard_slow_list_operation("list_datums", alternatives="iter_datums() or list_datums_page()")
        return await self.datum_database.find(filters or {})

    async def iter_datums(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Datum]:
        async for datum in self._iter_database(
            database=self.datum_database,
            resource="datums",
            filters=filters,
            sort=sort,
            batch_size=batch_size,
        ):
            yield datum

    async def list_datums_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Datum]:
        return await self._paginate_database(
            database=self.datum_database,
            resource="datums",
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def _validate_asset_refs_exist(self, asset_refs: dict[str, str]) -> None:
        for asset_id in asset_refs.values():
            if not str(asset_id).strip():
                raise ValueError("Datum asset_refs must contain non-empty asset ids")
            await self.get_asset(asset_id)

    async def _validate_annotation_set_ids_exist(self, annotation_set_ids: list[str]) -> None:
        for annotation_set_id in annotation_set_ids:
            await self.get_annotation_set(annotation_set_id)

    async def update_datum(self, datum_id: str, **changes: Any) -> Datum:
        datum = await self.get_datum(datum_id)
        if "asset_refs" in changes and changes["asset_refs"] is not None:
            await self._validate_asset_refs_exist(changes["asset_refs"])
        if "annotation_set_ids" in changes and changes["annotation_set_ids"] is not None:
            await self._validate_annotation_set_ids_exist(changes["annotation_set_ids"])
        for key, value in changes.items():
            setattr(datum, key, value)
        datum.updated_at = self._utc_now()
        return await self.datum_database.update(datum)

    async def create_dataset_version(
        self,
        *,
        dataset_name: str,
        version: str,
        manifest: list[str],
        description: str | None = None,
        source_dataset_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> DatasetVersion:
        existing = await self.dataset_version_database.find({"dataset_name": dataset_name, "version": version})
        if existing:
            raise ValueError(f"Dataset version already exists: {dataset_name}@{version}")
        if len(manifest) != len(set(manifest)):
            raise ValueError("Dataset version manifest must not contain duplicate datum ids")
        for datum_id in manifest:
            await self.get_datum(datum_id)
        dataset_version = self._build_document(
            DatasetVersion,
            dataset_name=dataset_name,
            version=version,
            description=description,
            manifest=manifest,
            source_dataset_version_id=source_dataset_version_id,
            metadata=metadata or {},
            created_by=created_by,
        )
        return await self.dataset_version_database.insert(dataset_version)

    async def get_dataset_version(self, dataset_name: str, version: str) -> DatasetVersion:
        results = await self.dataset_version_database.find({"dataset_name": dataset_name, "version": version})
        if not results:
            raise DocumentNotFoundError(f"DatasetVersion {dataset_name}@{version} not found")
        return results[0]

    async def list_dataset_versions(
        self,
        dataset_name: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[DatasetVersion]:
        self._guard_slow_list_operation("list_dataset_versions", alternatives="list_dataset_versions_page()")
        query = dict(filters or {})
        if dataset_name is not None:
            query["dataset_name"] = dataset_name
        return await self.dataset_version_database.find(query)

    async def list_dataset_versions_page(
        self,
        *,
        dataset_name: str | None = None,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[DatasetVersion]:
        query = dict(filters or {})
        if dataset_name is not None:
            query["dataset_name"] = dataset_name
        return await self._paginate_database(
            database=self.dataset_version_database,
            resource="dataset_versions",
            filters=query,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def view_dataset_version_page(
        self,
        dataset_name: str,
        version: str,
        *,
        limit: int = 100,
        cursor: str | None = None,
        sort: str = "manifest_order",
        filters: list[StructuredFilter] | None = None,
        expand: DatasetViewExpand | None = None,
        include_total: bool = False,
    ) -> DatasetViewPage:
        """Page through a dataset version manifest.

        This can still be a heavy operation for large manifests, especially when filters force
        per-row inspection or when expansions require loading linked assets or annotations.
        """
        if sort != "manifest_order":
            raise ValueError("dataset version views currently support only sort='manifest_order'")

        dataset_version = await self.get_dataset_version(dataset_name, version)
        expand = expand or DatasetViewExpand()
        filter_list = filters or []
        resource = f"dataset_version_view:{dataset_name}:{version}"
        start_index = 0
        if cursor is not None:
            envelope = self._decode_cursor(
                cursor,
                expected_resource=resource,
                expected_sort=sort,
                expected_filters=[f.model_dump(mode="json") for f in filter_list],
            )
            start_index = int(envelope.last_key.get("ordinal", -1)) + 1

        rows: list[DatasetViewRow] = []
        row_ordinals: list[int] = []
        total_count = 0
        next_cursor: str | None = None

        for ordinal in range(start_index, len(dataset_version.manifest)):
            datum_id = dataset_version.manifest[ordinal]
            datum = await self.get_datum(datum_id)
            if not self._matches_structured_filters(datum, filter_list):
                continue

            total_count += 1
            row = DatasetViewRow(
                datum_id=datum.datum_id,
                split=datum.split,
                metadata=dict(datum.metadata or {}),
            )

            include_sets = expand.annotation_sets or expand.annotation_records
            if expand.assets:
                row.assets = {role: await self.get_asset(asset_id) for role, asset_id in datum.asset_refs.items()}
            if include_sets:
                row.annotation_sets = [
                    await self.get_annotation_set(annotation_set_id) for annotation_set_id in datum.annotation_set_ids
                ]
            if expand.annotation_records:
                annotation_records: dict[str, list[AnnotationRecord]] = {}
                annotation_sets = row.annotation_sets or []
                for annotation_set in annotation_sets:
                    annotation_records[annotation_set.annotation_set_id] = [
                        await self.get_annotation_record(annotation_id)
                        for annotation_id in annotation_set.annotation_record_ids
                    ]
                row.annotation_records = annotation_records

            rows.append(row)
            row_ordinals.append(ordinal)
            if len(rows) == limit + 1:
                last_row = rows[limit - 1]
                last_ordinal = row_ordinals[limit - 1]
                next_cursor = self._encode_cursor(
                    CursorEnvelope(
                        resource=resource,
                        sort=sort,
                        filter_fingerprint=self._cursor_filter_fingerprint(
                            [f.model_dump(mode="json") for f in filter_list]
                        ),
                        last_key={"ordinal": last_ordinal, "datum_id": last_row.datum_id},
                    )
                )
                rows = rows[:limit]
                row_ordinals = row_ordinals[:limit]
                break

        if include_total:
            total_count_value = 0
            for datum_id in dataset_version.manifest:
                datum = await self.get_datum(datum_id)
                if self._matches_structured_filters(datum, filter_list):
                    total_count_value += 1
        else:
            total_count_value = None

        has_more = next_cursor is not None
        return DatasetViewPage(
            items=rows,
            page=PageInfo(limit=limit, next_cursor=next_cursor, has_more=has_more, total_count=total_count_value),
            view=DatasetViewInfo(dataset_name=dataset_name, version=version, sort=sort),
        )

    async def iter_dataset_version_view(
        self,
        dataset_name: str,
        version: str,
        *,
        page_size: int = 100,
        sort: str = "manifest_order",
        filters: list[StructuredFilter] | None = None,
        expand: DatasetViewExpand | None = None,
    ) -> AsyncIterator[DatasetViewRow]:
        cursor: str | None = None
        while True:
            page = await self.view_dataset_version_page(
                dataset_name,
                version,
                limit=page_size,
                cursor=cursor,
                sort=sort,
                filters=filters,
                expand=expand,
                include_total=False,
            )
            for row in page.items:
                yield row
            if not page.page.has_more:
                break
            cursor = page.page.next_cursor

    async def resolve_datum(self, datum_id: str) -> ResolvedDatum:
        """Fully materialize the datum graph for one datum.

        This is an explicit heavy operation intended for bounded use, not for bulk traversal.
        """
        datum = await self.get_datum(datum_id)
        assets: dict[str, Asset] = {}
        for role, asset_id in datum.asset_refs.items():
            assets[role] = await self.get_asset(asset_id)

        annotation_sets: list[AnnotationSet] = []
        annotation_records: dict[str, list[AnnotationRecord]] = {}
        for annotation_set_id in datum.annotation_set_ids:
            annotation_set = await self.get_annotation_set(annotation_set_id)
            annotation_sets.append(annotation_set)
            records: list[AnnotationRecord] = []
            for annotation_id in annotation_set.annotation_record_ids:
                records.append(await self.get_annotation_record(annotation_id))
            annotation_records[annotation_set.annotation_set_id] = records

        return ResolvedDatum(
            datum=datum,
            assets=assets,
            annotation_sets=annotation_sets,
            annotation_records=annotation_records,
        )

    async def resolve_dataset_version(self, dataset_name: str, version: str) -> ResolvedDatasetVersion:
        """Fully materialize every datum in a dataset version.

        This is an explicit heavy operation intended for bounded use, not for bulk traversal.
        """
        dataset_version = await self.get_dataset_version(dataset_name, version)
        datums = [await self.resolve_datum(datum_id) for datum_id in dataset_version.manifest]
        return ResolvedDatasetVersion(dataset_version=dataset_version, datums=datums)

    async def create_asset_from_object(
        self,
        *,
        name: str,
        obj: Any,
        kind: str,
        media_type: str,
        mount: str | None = None,
        version: str | None = None,
        object_metadata: dict[str, Any] | None = None,
        asset_metadata: dict[str, Any] | None = None,
        checksum: str | None = None,
        size_bytes: int | None = None,
        subject: SubjectRef | None = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        storage_ref = await self.put_object(
            name=name,
            obj=obj,
            mount=mount,
            version=version,
            metadata=object_metadata,
            on_conflict=on_conflict,
        )
        return await self.create_asset(
            kind=kind,
            media_type=media_type,
            storage_ref=storage_ref,
            checksum=checksum,
            size_bytes=size_bytes,
            subject=subject,
            metadata=asset_metadata,
            created_by=created_by,
        )
