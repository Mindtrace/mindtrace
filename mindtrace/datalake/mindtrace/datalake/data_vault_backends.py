"""Pluggable backends for :class:`~mindtrace.datalake.AsyncDataVault` and :class:`~mindtrace.datalake.DataVault`.

Local backends delegate to :class:`~mindtrace.datalake.AsyncDatalake` / :class:`~mindtrace.datalake.Datalake`
(or duck-typed facades with the same methods). Service backends call a generated
``DatalakeService`` connection manager (``assets.get_by_alias``, ``objects.get``,
``assets.create_from_object``, ``aliases.add``).
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import Any
from unittest.mock import Mock as _UnitTestMock

from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.datalake import Datalake
from mindtrace.datalake.service_types import (
    AddAliasInput,
    AddAnnotationRecordsInput,
    CreateAssetFromObjectInput,
    GetAssetByAliasInput,
    GetObjectInput,
    ListAnnotationRecordsForAssetInput,
)
from mindtrace.datalake.types import AnnotationRecord, Asset, AssetAlias, StorageRef
from mindtrace.services.core.connection_manager import ConnectionManager

_SYNC_VAULT_METHOD_NAMES = ("get_asset_by_alias", "get_object", "create_asset_from_object", "add_alias")
_ASYNC_VAULT_METHOD_NAMES = _SYNC_VAULT_METHOD_NAMES

# Sync/async method names on a ``DatalakeService`` client from ``Service.connect`` /
# ``generate_connection_manager(DatalakeService)``.
_SYNC_DATALAKE_SERVICE_CLIENT_METHODS = (
    "assets_get_by_alias",
    "objects_get",
    "assets_create_from_object",
    "aliases_add",
)
_ASYNC_DATALAKE_SERVICE_CLIENT_METHODS = (
    "aassets_get_by_alias",
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
        return all(callable(getattr(obj, name, None)) for name in _SYNC_DATALAKE_SERVICE_CLIENT_METHODS)
    if _is_unittest_mock(obj):
        return False
    return all(callable(getattr(obj, name, None)) for name in _SYNC_DATALAKE_SERVICE_CLIENT_METHODS)


def looks_like_datalake_service_async_client(obj: Any) -> bool:
    """Return True if ``obj`` exposes async ``a``-prefixed ``DatalakeService`` task methods."""

    if isinstance(obj, ConnectionManager):
        return all(callable(getattr(obj, name, None)) for name in _ASYNC_DATALAKE_SERVICE_CLIENT_METHODS)
    if _is_unittest_mock(obj):
        return False
    return all(callable(getattr(obj, name, None)) for name in _ASYNC_DATALAKE_SERVICE_CLIENT_METHODS)


class AsyncDataVaultBackend(ABC):
    """Async backend contract for :class:`~mindtrace.datalake.AsyncDataVault`."""

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


class DataVaultBackend(ABC):
    """Blocking backend contract for :class:`~mindtrace.datalake.DataVault`."""

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


class LocalAsyncDataVaultBackend(AsyncDataVaultBackend):
    """Delegates to :class:`~mindtrace.datalake.AsyncDatalake` (or a compatible async facade)."""

    def __init__(self, datalake: AsyncDatalake | Any) -> None:
        self._datalake = datalake

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


class LocalDataVaultBackend(DataVaultBackend):
    """Delegates to :class:`~mindtrace.datalake.Datalake` (or a compatible sync facade)."""

    def __init__(self, datalake: Datalake | Any) -> None:
        self._datalake = datalake

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
        raise AttributeError(
            f"connection_manager {type(self._cm)!r} has none of: {', '.join(method_names)}"
        )

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


class DatalakeServiceDataVaultBackend(DataVaultBackend):
    """Calls a ``DatalakeService`` connection manager's sync task methods (``assets_*``, ``objects_*``, ``aliases_*``)."""

    def __init__(self, connection_manager: Any) -> None:
        self._cm = connection_manager

    def _call(self, *method_names: str, input_obj: Any) -> Any:
        for name in method_names:
            method = getattr(self._cm, name, None)
            if method is not None:
                return method(input_obj)
        raise AttributeError(
            f"connection_manager {type(self._cm)!r} has none of: {', '.join(method_names)}"
        )

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
