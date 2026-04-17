"""Pluggable backends for :class:`~mindtrace.datalake.AsyncDataVault` and :class:`~mindtrace.datalake.DataVault`.

Local backends delegate to :class:`~mindtrace.datalake.AsyncDatalake` / :class:`~mindtrace.datalake.Datalake`
(or duck-typed facades with the same methods). Service backends call a generated
``DatalakeService`` connection manager (``assets.get_by_alias``, ``objects.get``,
``assets.create_from_object``, ``aliases.add``).
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import Mock as _UnitTestMock

from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.datalake import Datalake
from mindtrace.datalake.pagination_types import CursorPage
from mindtrace.datalake.service_types import (
    AddAliasInput,
    AddAnnotationRecordsInput,
    CreateAnnotationSetInput,
    CreateAssetFromObjectInput,
    CreateCollectionInput,
    CreateCollectionItemInput,
    DeleteByIdInput,
    GetAssetByAliasInput,
    GetByIdInput,
    GetObjectInput,
    ListAnnotationRecordsForAssetInput,
    ListInput,
    PageInput,
    UpdateCollectionItemInput,
)
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    AssetAlias,
    Collection,
    CollectionItem,
    StorageRef,
)
from mindtrace.services.core.connection_manager import ConnectionManager

_SYNC_VAULT_METHOD_NAMES = (
    "list_assets",
    "list_assets_page",
    "iter_assets",
    "get_asset",
    "get_asset_by_alias",
    "get_object",
    "create_asset_from_object",
    "add_alias",
    "add_annotation_records",
    "list_annotation_records_for_asset",
    "list_collections",
    "list_collections_page",
    "iter_collections",
    "create_collection",
    "list_collection_items",
    "list_collection_items_page",
    "create_collection_item",
    "update_collection_item",
    "delete_collection_item",
    "list_annotation_sets",
    "create_annotation_set",
    "get_annotation_record",
    "list_annotation_records",
    "delete_annotation_record",
)
_ASYNC_VAULT_METHOD_NAMES = _SYNC_VAULT_METHOD_NAMES

# Sync/async method names on a ``DatalakeService`` client from ``Service.connect`` /
# ``generate_connection_manager(DatalakeService)``.
_SYNC_DATALAKE_SERVICE_CLIENT_METHODS = (
    "assets_get",
    "assets_get_by_alias",
    "assets_list",
    "assets_list_page",
    "objects_get",
    "assets_create_from_object",
    "aliases_add",
)
_ASYNC_DATALAKE_SERVICE_CLIENT_METHODS = (
    "aassets_get",
    "aassets_get_by_alias",
    "aassets_list",
    "aassets_list_page",
    "aobjects_get",
    "aassets_create_from_object",
    "aaliases_add",
)


def _is_unittest_mock(obj: Any) -> bool:
    return isinstance(obj, _UnitTestMock)


def looks_like_datalake_service_sync_client(obj: Any) -> bool:
    """Return True if ``obj`` exposes sync ``DatalakeService`` task methods (``assets_get_by_alias``, …).

    Accepts a :class:`~mindtrace.services.ConnectionManager` or a non-mock facade with the same
    callables (e.g. an in-process HTTP test client). ``unittest.mock.Mock`` / ``MagicMock`` are
    rejected so generic mocks are not mistaken for service clients.
    """

    if isinstance(obj, ConnectionManager):
        return True
    if _is_unittest_mock(obj):
        return False
    return all(callable(getattr(obj, name, None)) for name in _SYNC_DATALAKE_SERVICE_CLIENT_METHODS)


def looks_like_datalake_service_async_client(obj: Any) -> bool:
    """Return True if ``obj`` exposes async ``a``-prefixed ``DatalakeService`` task methods."""

    if isinstance(obj, ConnectionManager):
        return True
    if _is_unittest_mock(obj):
        return False
    return all(callable(getattr(obj, name, None)) for name in _ASYNC_DATALAKE_SERVICE_CLIENT_METHODS)


class AsyncDataVaultBackend(ABC):
    """Async backend contract for :class:`~mindtrace.datalake.AsyncDataVault`."""

    @abstractmethod
    async def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]: ...

    @abstractmethod
    async def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]: ...

    @abstractmethod
    async def iter_assets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Asset]: ...

    @abstractmethod
    async def get_asset(self, asset_id: str) -> Asset: ...

    @abstractmethod
    async def get_asset_by_alias(self, alias: str) -> Asset: ...

    @abstractmethod
    async def get_object(self, storage_ref: StorageRef, **kwargs: Any) -> Any: ...

    @abstractmethod
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
        subject: Any = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset: ...

    @abstractmethod
    async def add_alias(self, asset_id: str, alias: str) -> AssetAlias: ...

    @abstractmethod
    async def add_annotation_records(
        self,
        annotations: Any,
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]: ...

    @abstractmethod
    async def list_annotation_records_for_asset(self, asset_id: str) -> list[AnnotationRecord]: ...

    @abstractmethod
    async def list_collections(self, filters: dict[str, Any] | None = None) -> list[Collection]: ...

    @abstractmethod
    async def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Collection]: ...

    @abstractmethod
    async def iter_collections(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Collection]: ...

    @abstractmethod
    async def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Collection: ...

    @abstractmethod
    async def list_collection_items(self, filters: dict[str, Any] | None = None) -> list[CollectionItem]: ...

    @abstractmethod
    async def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[CollectionItem]: ...

    @abstractmethod
    async def create_collection_item(
        self,
        *,
        collection_id: str,
        asset_id: str,
        split: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> CollectionItem: ...

    @abstractmethod
    async def update_collection_item(self, collection_item_id: str, **changes: Any) -> CollectionItem: ...

    @abstractmethod
    async def delete_collection_item(self, collection_item_id: str) -> None: ...

    @abstractmethod
    async def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]: ...

    @abstractmethod
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
    ) -> AnnotationSet: ...

    @abstractmethod
    async def get_annotation_record(self, annotation_id: str) -> AnnotationRecord: ...

    @abstractmethod
    async def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]: ...

    @abstractmethod
    async def delete_annotation_record(self, annotation_id: str) -> None: ...


class DataVaultBackend(ABC):
    """Blocking backend contract for :class:`~mindtrace.datalake.DataVault`."""

    @abstractmethod
    def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]: ...

    @abstractmethod
    def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]: ...

    @abstractmethod
    def iter_assets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> Iterator[Asset]: ...

    @abstractmethod
    def get_asset(self, asset_id: str) -> Asset: ...

    @abstractmethod
    def get_asset_by_alias(self, alias: str) -> Asset: ...

    @abstractmethod
    def get_object(self, storage_ref: StorageRef, **kwargs: Any) -> Any: ...

    @abstractmethod
    def create_asset_from_object(
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
        subject: Any = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset: ...

    @abstractmethod
    def add_alias(self, asset_id: str, alias: str) -> AssetAlias: ...

    @abstractmethod
    def add_annotation_records(
        self,
        annotations: Any,
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]: ...

    @abstractmethod
    def list_annotation_records_for_asset(self, asset_id: str) -> list[AnnotationRecord]: ...

    @abstractmethod
    def list_collections(self, filters: dict[str, Any] | None = None) -> list[Collection]: ...

    @abstractmethod
    def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Collection]: ...

    @abstractmethod
    def iter_collections(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> Iterator[Collection]: ...

    @abstractmethod
    def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Collection: ...

    @abstractmethod
    def list_collection_items(self, filters: dict[str, Any] | None = None) -> list[CollectionItem]: ...

    @abstractmethod
    def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[CollectionItem]: ...

    @abstractmethod
    def create_collection_item(
        self,
        *,
        collection_id: str,
        asset_id: str,
        split: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> CollectionItem: ...

    @abstractmethod
    def update_collection_item(self, collection_item_id: str, **changes: Any) -> CollectionItem: ...

    @abstractmethod
    def delete_collection_item(self, collection_item_id: str) -> None: ...

    @abstractmethod
    def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]: ...

    @abstractmethod
    def create_annotation_set(
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
    ) -> AnnotationSet: ...

    @abstractmethod
    def get_annotation_record(self, annotation_id: str) -> AnnotationRecord: ...

    @abstractmethod
    def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]: ...

    @abstractmethod
    def delete_annotation_record(self, annotation_id: str) -> None: ...


class LocalAsyncDataVaultBackend(AsyncDataVaultBackend):
    """Delegates to :class:`~mindtrace.datalake.AsyncDatalake` (or a compatible async facade)."""

    def __init__(self, datalake: AsyncDatalake | Any) -> None:
        self._datalake = datalake

    async def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        return await self._datalake.list_assets(filters)

    async def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        return await self._datalake.list_assets_page(
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def iter_assets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Asset]:
        async for asset in self._datalake.iter_assets(filters=filters, sort=sort, batch_size=batch_size):
            yield asset

    async def get_asset(self, asset_id: str) -> Asset:
        return await self._datalake.get_asset(asset_id)

    async def get_asset_by_alias(self, alias: str) -> Asset:
        return await self._datalake.get_asset_by_alias(alias)

    async def get_object(self, storage_ref: StorageRef, **kwargs: Any) -> Any:
        return await self._datalake.get_object(storage_ref, **kwargs)

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
        subject: Any = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        return await self._datalake.create_asset_from_object(
            name=name,
            obj=obj,
            kind=kind,
            media_type=media_type,
            mount=mount,
            version=version,
            object_metadata=object_metadata,
            asset_metadata=asset_metadata,
            checksum=checksum,
            size_bytes=size_bytes,
            subject=subject,
            created_by=created_by,
            on_conflict=on_conflict,
        )

    async def add_alias(self, asset_id: str, alias: str) -> AssetAlias:
        return await self._datalake.add_alias(asset_id, alias)

    async def add_annotation_records(
        self,
        annotations: Any,
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        return await self._datalake.add_annotation_records(
            annotations,
            annotation_set_id=annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )

    async def list_annotation_records_for_asset(self, asset_id: str) -> list[AnnotationRecord]:
        return await self._datalake.list_annotation_records_for_asset(asset_id)

    async def list_collections(self, filters: dict[str, Any] | None = None) -> list[Collection]:
        return await self._datalake.list_collections(filters)

    async def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Collection]:
        return await self._datalake.list_collections_page(
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def iter_collections(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Collection]:
        async for collection in self._datalake.iter_collections(filters=filters, sort=sort, batch_size=batch_size):
            yield collection

    async def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Collection:
        return await self._datalake.create_collection(
            name=name,
            description=description,
            status=status,
            metadata=metadata,
            created_by=created_by,
        )

    async def list_collection_items(self, filters: dict[str, Any] | None = None) -> list[CollectionItem]:
        return await self._datalake.list_collection_items(filters)

    async def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[CollectionItem]:
        return await self._datalake.list_collection_items_page(
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

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
        return await self._datalake.create_collection_item(
            collection_id=collection_id,
            asset_id=asset_id,
            split=split,
            status=status,
            metadata=metadata,
            added_by=added_by,
        )

    async def update_collection_item(self, collection_item_id: str, **changes: Any) -> CollectionItem:
        return await self._datalake.update_collection_item(collection_item_id, **changes)

    async def delete_collection_item(self, collection_item_id: str) -> None:
        await self._datalake.delete_collection_item(collection_item_id)

    async def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]:
        return await self._datalake.list_annotation_sets(filters)

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
        return await self._datalake.create_annotation_set(
            name=name,
            purpose=purpose,
            source_type=source_type,
            status=status,
            metadata=metadata,
            created_by=created_by,
            datum_id=datum_id,
            annotation_schema_id=annotation_schema_id,
        )

    async def get_annotation_record(self, annotation_id: str) -> AnnotationRecord:
        return await self._datalake.get_annotation_record(annotation_id)

    async def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]:
        return await self._datalake.list_annotation_records(filters)

    async def delete_annotation_record(self, annotation_id: str) -> None:
        await self._datalake.delete_annotation_record(annotation_id)


class LocalDataVaultBackend(DataVaultBackend):
    """Delegates to :class:`~mindtrace.datalake.Datalake` (or a compatible sync facade)."""

    def __init__(self, datalake: Datalake | Any) -> None:
        self._datalake = datalake

    def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        return self._datalake.list_assets(filters)

    def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        return self._datalake.list_assets_page(
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    def iter_assets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> Iterator[Asset]:
        yield from self._datalake.iter_assets(filters=filters, sort=sort, batch_size=batch_size)

    def get_asset(self, asset_id: str) -> Asset:
        return self._datalake.get_asset(asset_id)

    def get_asset_by_alias(self, alias: str) -> Asset:
        return self._datalake.get_asset_by_alias(alias)

    def get_object(self, storage_ref: StorageRef, **kwargs: Any) -> Any:
        return self._datalake.get_object(storage_ref, **kwargs)

    def create_asset_from_object(
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
        subject: Any = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        return self._datalake.create_asset_from_object(
            name=name,
            obj=obj,
            kind=kind,
            media_type=media_type,
            mount=mount,
            version=version,
            object_metadata=object_metadata,
            asset_metadata=asset_metadata,
            checksum=checksum,
            size_bytes=size_bytes,
            subject=subject,
            created_by=created_by,
            on_conflict=on_conflict,
        )

    def add_alias(self, asset_id: str, alias: str) -> AssetAlias:
        return self._datalake.add_alias(asset_id, alias)

    def add_annotation_records(
        self,
        annotations: Any,
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        return self._datalake.add_annotation_records(
            annotations,
            annotation_set_id=annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )

    def list_annotation_records_for_asset(self, asset_id: str) -> list[AnnotationRecord]:
        return self._datalake.list_annotation_records_for_asset(asset_id)

    def list_collections(self, filters: dict[str, Any] | None = None) -> list[Collection]:
        return self._datalake.list_collections(filters)

    def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Collection]:
        return self._datalake.list_collections_page(
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    def iter_collections(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> Iterator[Collection]:
        yield from self._datalake.iter_collections(filters=filters, sort=sort, batch_size=batch_size)

    def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Collection:
        return self._datalake.create_collection(
            name=name,
            description=description,
            status=status,
            metadata=metadata,
            created_by=created_by,
        )

    def list_collection_items(self, filters: dict[str, Any] | None = None) -> list[CollectionItem]:
        return self._datalake.list_collection_items(filters)

    def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[CollectionItem]:
        return self._datalake.list_collection_items_page(
            filters=filters,
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    def create_collection_item(
        self,
        *,
        collection_id: str,
        asset_id: str,
        split: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> CollectionItem:
        return self._datalake.create_collection_item(
            collection_id=collection_id,
            asset_id=asset_id,
            split=split,
            status=status,
            metadata=metadata,
            added_by=added_by,
        )

    def update_collection_item(self, collection_item_id: str, **changes: Any) -> CollectionItem:
        return self._datalake.update_collection_item(collection_item_id, **changes)

    def delete_collection_item(self, collection_item_id: str) -> None:
        self._datalake.delete_collection_item(collection_item_id)

    def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]:
        return self._datalake.list_annotation_sets(filters)

    def create_annotation_set(
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
        return self._datalake.create_annotation_set(
            name=name,
            purpose=purpose,
            source_type=source_type,
            status=status,
            metadata=metadata,
            created_by=created_by,
            datum_id=datum_id,
            annotation_schema_id=annotation_schema_id,
        )

    def get_annotation_record(self, annotation_id: str) -> AnnotationRecord:
        return self._datalake.get_annotation_record(annotation_id)

    def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]:
        return self._datalake.list_annotation_records(filters)

    def delete_annotation_record(self, annotation_id: str) -> None:
        self._datalake.delete_annotation_record(annotation_id)


def _encode_obj_for_service(obj: Any) -> str:
    if isinstance(obj, str):
        raw = obj.encode("utf-8")
    elif isinstance(obj, (bytes, bytearray)):
        raw = bytes(obj)
    else:
        raise TypeError(
            "DatalakeServiceDataVaultBackend requires bytes, bytearray, or str payloads for remote "
            "create_asset_from_object; serialize via your materializer first."
        )
    return base64.b64encode(raw).decode("ascii")


class DatalakeServiceAsyncDataVaultBackend(AsyncDataVaultBackend):
    """Calls a ``DatalakeService`` connection manager's async task methods (``aassets_*``, ``aobjects_*``, ``aaliases_*``)."""

    def __init__(self, connection_manager: Any) -> None:
        self._cm = connection_manager

    async def _call(self, *method_names: str, input_obj: Any) -> Any:
        for name in method_names:
            method = getattr(self._cm, name, None)
            if method is not None:
                return await method(input_obj)
        raise TypeError(
            "This AsyncDataVault service client does not support the required ConnectionManager "
            f"method(s): {', '.join(method_names)}"
        )

    async def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        out = await self._call("aassets_list", input_obj=ListInput(filters=filters))
        return out.assets

    async def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        return await self._call(
            "aassets_list_page",
            input_obj=PageInput(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            ),
        )

    async def iter_assets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Asset]:
        cursor: str | None = None
        page_limit = batch_size
        while True:
            page = await self.list_assets_page(
                filters=filters,
                sort=sort,
                limit=page_limit,
                cursor=cursor,
            )
            for asset in page.items:
                yield asset
            if not page.page.has_more or page.page.next_cursor is None:
                break
            cursor = page.page.next_cursor

    async def get_asset(self, asset_id: str) -> Asset:
        out = await self._call("aassets_get", input_obj=GetByIdInput(id=asset_id))
        return out.asset

    async def get_asset_by_alias(self, alias: str) -> Asset:
        out = await self._call(
            "aassets_get_by_alias",
            input_obj=GetAssetByAliasInput(alias=alias),
        )
        return out.asset

    async def get_object(self, storage_ref: StorageRef, **kwargs: Any) -> Any:
        if kwargs:
            raise TypeError(
                "DatalakeServiceAsyncDataVaultBackend.get_object does not support extra kwargs; "
                "use the in-process datalake for advanced store.load options."
            )
        out = await self._call("aobjects_get", input_obj=GetObjectInput(storage_ref=storage_ref))
        return base64.b64decode(out.data_base64.encode("ascii"))

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
        subject: Any = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        data_base64 = _encode_obj_for_service(obj)
        out = await self._call(
            "aassets_create_from_object",
            input_obj=CreateAssetFromObjectInput(
                name=name,
                data_base64=data_base64,
                kind=kind,
                media_type=media_type,
                mount=mount,
                version=version,
                object_metadata=object_metadata,
                asset_metadata=asset_metadata,
                checksum=checksum,
                size_bytes=size_bytes,
                subject=subject,
                created_by=created_by,
                on_conflict=on_conflict,
            ),
        )
        return out.asset

    async def add_alias(self, asset_id: str, alias: str) -> AssetAlias:
        out = await self._call("aaliases_add", input_obj=AddAliasInput(asset_id=asset_id, alias=alias))
        return out.asset_alias

    async def add_annotation_records(
        self,
        annotations: Any,
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        out = await self._call(
            "aannotation_records_add",
            input_obj=AddAnnotationRecordsInput(
                annotations=list(annotations),
                annotation_set_id=annotation_set_id,
                annotation_schema_id=annotation_schema_id,
            ),
        )
        return out.annotation_records

    async def list_annotation_records_for_asset(self, asset_id: str) -> list[AnnotationRecord]:
        out = await self._call(
            "aannotation_records_list_for_asset",
            input_obj=ListAnnotationRecordsForAssetInput(asset_id=asset_id),
        )
        return out.annotation_records

    async def list_collections(self, filters: dict[str, Any] | None = None) -> list[Collection]:
        out = await self._call("acollections_list", input_obj=ListInput(filters=filters))
        return out.collections

    async def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Collection]:
        return await self._call(
            "acollections_list_page",
            input_obj=PageInput(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            ),
        )

    async def iter_collections(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Collection]:
        cursor: str | None = None
        page_limit = batch_size
        while True:
            page = await self.list_collections_page(
                filters=filters,
                sort=sort,
                limit=page_limit,
                cursor=cursor,
            )
            for collection in page.items:
                yield collection
            if not page.page.has_more or page.page.next_cursor is None:
                break
            cursor = page.page.next_cursor

    async def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Collection:
        out = await self._call(
            "acollections_create",
            input_obj=CreateCollectionInput(
                name=name,
                description=description,
                status=status,
                metadata=metadata,
                created_by=created_by,
            ),
        )
        return out.collection

    async def list_collection_items(self, filters: dict[str, Any] | None = None) -> list[CollectionItem]:
        out = await self._call("acollection_items_list", input_obj=ListInput(filters=filters))
        return out.collection_items

    async def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[CollectionItem]:
        return await self._call(
            "acollection_items_list_page",
            input_obj=PageInput(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            ),
        )

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
        out = await self._call(
            "acollection_items_create",
            input_obj=CreateCollectionItemInput(
                collection_id=collection_id,
                asset_id=asset_id,
                split=split,
                status=status,
                metadata=metadata,
                added_by=added_by,
            ),
        )
        return out.collection_item

    async def update_collection_item(self, collection_item_id: str, **changes: Any) -> CollectionItem:
        out = await self._call(
            "acollection_items_update",
            input_obj=UpdateCollectionItemInput(collection_item_id=collection_item_id, changes=changes),
        )
        return out.collection_item

    async def delete_collection_item(self, collection_item_id: str) -> None:
        await self._call("acollection_items_delete", input_obj=DeleteByIdInput(id=collection_item_id))

    async def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]:
        out = await self._call("aannotation_sets_list", input_obj=ListInput(filters=filters))
        return out.annotation_sets

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
        out = await self._call(
            "aannotation_sets_create",
            input_obj=CreateAnnotationSetInput(
                name=name,
                purpose=purpose,
                source_type=source_type,
                status=status,
                metadata=metadata,
                created_by=created_by,
                datum_id=datum_id,
                annotation_schema_id=annotation_schema_id,
            ),
        )
        return out.annotation_set

    async def get_annotation_record(self, annotation_id: str) -> AnnotationRecord:
        out = await self._call("aannotation_records_get", input_obj=GetByIdInput(id=annotation_id))
        return out.annotation_record

    async def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]:
        out = await self._call("aannotation_records_list", input_obj=ListInput(filters=filters))
        return out.annotation_records

    async def delete_annotation_record(self, annotation_id: str) -> None:
        await self._call("aannotation_records_delete", input_obj=DeleteByIdInput(id=annotation_id))


class DatalakeServiceDataVaultBackend(DataVaultBackend):
    """Calls a ``DatalakeService`` connection manager's sync task methods (``assets_*``, ``objects_*``, ``aliases_*``)."""

    def __init__(self, connection_manager: Any) -> None:
        self._cm = connection_manager

    def _call(self, *method_names: str, input_obj: Any) -> Any:
        for name in method_names:
            method = getattr(self._cm, name, None)
            if method is not None:
                return method(input_obj)
        raise TypeError(
            "This DataVault service client does not support the required ConnectionManager "
            f"method(s): {', '.join(method_names)}"
        )

    def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        out = self._call("assets_list", input_obj=ListInput(filters=filters))
        return out.assets

    def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        return self._call(
            "assets_list_page",
            input_obj=PageInput(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            ),
        )

    def iter_assets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> Iterator[Asset]:
        cursor: str | None = None
        page_limit = batch_size
        while True:
            page = self.list_assets_page(
                filters=filters,
                sort=sort,
                limit=page_limit,
                cursor=cursor,
            )
            yield from page.items
            if not page.page.has_more or page.page.next_cursor is None:
                break
            cursor = page.page.next_cursor

    def get_asset(self, asset_id: str) -> Asset:
        out = self._call("assets_get", input_obj=GetByIdInput(id=asset_id))
        return out.asset

    def get_asset_by_alias(self, alias: str) -> Asset:
        out = self._call("assets_get_by_alias", input_obj=GetAssetByAliasInput(alias=alias))
        return out.asset

    def get_object(self, storage_ref: StorageRef, **kwargs: Any) -> Any:
        if kwargs:
            raise TypeError(
                "DatalakeServiceDataVaultBackend.get_object does not support extra kwargs; "
                "use the in-process datalake for advanced store.load options."
            )
        out = self._call("objects_get", input_obj=GetObjectInput(storage_ref=storage_ref))
        return base64.b64decode(out.data_base64.encode("ascii"))

    def create_asset_from_object(
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
        subject: Any = None,
        created_by: str | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        data_base64 = _encode_obj_for_service(obj)
        out = self._call(
            "assets_create_from_object",
            input_obj=CreateAssetFromObjectInput(
                name=name,
                data_base64=data_base64,
                kind=kind,
                media_type=media_type,
                mount=mount,
                version=version,
                object_metadata=object_metadata,
                asset_metadata=asset_metadata,
                checksum=checksum,
                size_bytes=size_bytes,
                subject=subject,
                created_by=created_by,
                on_conflict=on_conflict,
            ),
        )
        return out.asset

    def add_alias(self, asset_id: str, alias: str) -> AssetAlias:
        out = self._call("aliases_add", input_obj=AddAliasInput(asset_id=asset_id, alias=alias))
        return out.asset_alias

    def add_annotation_records(
        self,
        annotations: Any,
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        out = self._call(
            "annotation_records_add",
            input_obj=AddAnnotationRecordsInput(
                annotations=list(annotations),
                annotation_set_id=annotation_set_id,
                annotation_schema_id=annotation_schema_id,
            ),
        )
        return out.annotation_records

    def list_annotation_records_for_asset(self, asset_id: str) -> list[AnnotationRecord]:
        out = self._call(
            "annotation_records_list_for_asset",
            input_obj=ListAnnotationRecordsForAssetInput(asset_id=asset_id),
        )
        return out.annotation_records

    def list_collections(self, filters: dict[str, Any] | None = None) -> list[Collection]:
        out = self._call("collections_list", input_obj=ListInput(filters=filters))
        return out.collections

    def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Collection]:
        return self._call(
            "collections_list_page",
            input_obj=PageInput(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            ),
        )

    def iter_collections(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> Iterator[Collection]:
        cursor: str | None = None
        page_limit = batch_size
        while True:
            page = self.list_collections_page(
                filters=filters,
                sort=sort,
                limit=page_limit,
                cursor=cursor,
            )
            yield from page.items
            if not page.page.has_more or page.page.next_cursor is None:
                break
            cursor = page.page.next_cursor

    def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> Collection:
        out = self._call(
            "collections_create",
            input_obj=CreateCollectionInput(
                name=name,
                description=description,
                status=status,
                metadata=metadata,
                created_by=created_by,
            ),
        )
        return out.collection

    def list_collection_items(self, filters: dict[str, Any] | None = None) -> list[CollectionItem]:
        out = self._call("collection_items_list", input_obj=ListInput(filters=filters))
        return out.collection_items

    def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[CollectionItem]:
        return self._call(
            "collection_items_list_page",
            input_obj=PageInput(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            ),
        )

    def create_collection_item(
        self,
        *,
        collection_id: str,
        asset_id: str,
        split: str | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> CollectionItem:
        out = self._call(
            "collection_items_create",
            input_obj=CreateCollectionItemInput(
                collection_id=collection_id,
                asset_id=asset_id,
                split=split,
                status=status,
                metadata=metadata,
                added_by=added_by,
            ),
        )
        return out.collection_item

    def update_collection_item(self, collection_item_id: str, **changes: Any) -> CollectionItem:
        out = self._call(
            "collection_items_update",
            input_obj=UpdateCollectionItemInput(collection_item_id=collection_item_id, changes=changes),
        )
        return out.collection_item

    def delete_collection_item(self, collection_item_id: str) -> None:
        self._call("collection_items_delete", input_obj=DeleteByIdInput(id=collection_item_id))

    def list_annotation_sets(self, filters: dict[str, Any] | None = None) -> list[AnnotationSet]:
        out = self._call("annotation_sets_list", input_obj=ListInput(filters=filters))
        return out.annotation_sets

    def create_annotation_set(
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
        out = self._call(
            "annotation_sets_create",
            input_obj=CreateAnnotationSetInput(
                name=name,
                purpose=purpose,
                source_type=source_type,
                status=status,
                metadata=metadata,
                created_by=created_by,
                datum_id=datum_id,
                annotation_schema_id=annotation_schema_id,
            ),
        )
        return out.annotation_set

    def get_annotation_record(self, annotation_id: str) -> AnnotationRecord:
        out = self._call("annotation_records_get", input_obj=GetByIdInput(id=annotation_id))
        return out.annotation_record

    def list_annotation_records(self, filters: dict[str, Any] | None = None) -> list[AnnotationRecord]:
        out = self._call("annotation_records_list", input_obj=ListInput(filters=filters))
        return out.annotation_records

    def delete_annotation_record(self, annotation_id: str) -> None:
        self._call("annotation_records_delete", input_obj=DeleteByIdInput(id=annotation_id))
