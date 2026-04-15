"""High-level alias-based access to datalake assets and payloads.

Serialization uses the same registry/store stack as :class:`~mindtrace.datalake.AsyncDatalake`
(``put_object`` / ``get_object``), so ZenML materializers registered on ``Registry`` apply.

Facades:

- :class:`AsyncDataVault` — async API; supply :class:`~mindtrace.datalake.AsyncDatalake`, a client
  from :meth:`~mindtrace.datalake.service.DatalakeService.connect` (async task methods), an
  :class:`~mindtrace.datalake.data_vault_backends.AsyncDataVaultBackend`, or a duck-typed async
  object with the same methods as ``AsyncDatalake`` for vault operations.
- :class:`DataVault` — blocking API; supply :class:`~mindtrace.datalake.Datalake`, a client from
  :meth:`~mindtrace.datalake.service.DatalakeService.connect` (sync task methods), a
  :class:`~mindtrace.datalake.data_vault_backends.DataVaultBackend`, or a duck-typed sync object.

Typical async usage::

    vault = AsyncDataVault(datalake)
    asset = await vault.save("my-key", image_bytes, kind="image", media_type="image/png")
    data = await vault.load("my-key")

Typical sync usage::

    vault = DataVault(datalake)
    asset = vault.save("my-key", image_bytes, kind="image", media_type="image/png")
    data = vault.load("my-key")

Remote service (blocking), after ``DatalakeService`` is running::

    from mindtrace.datalake import DataVault, DatalakeService

    cm = DatalakeService.connect(url="http://localhost:8080")
    vault = DataVault(cm)
    vault.save("my-key", blob, kind="artifact", media_type="application/octet-stream")
    data = vault.load("my-key")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.data_vault_backends import (
    _ASYNC_VAULT_METHOD_NAMES,
    _SYNC_VAULT_METHOD_NAMES,
    AsyncDataVaultBackend,
    DatalakeServiceAsyncDataVaultBackend,
    DatalakeServiceDataVaultBackend,
    DataVaultBackend,
    LocalAsyncDataVaultBackend,
    LocalDataVaultBackend,
    looks_like_datalake_service_async_client,
    looks_like_datalake_service_sync_client,
)
from mindtrace.datalake.datalake import Datalake
from mindtrace.datalake.types import Asset, DuplicateAliasError

_SYNC_VAULT_METHODS = _SYNC_VAULT_METHOD_NAMES


def _sanitize_object_name_component(alias: str) -> str:
    """Avoid path injection in storage names (best-effort)."""
    cleaned = alias.replace("..", "_")
    return re.sub(r"[^a-zA-Z0-9._\-]+", "_", cleaned).strip("_") or "asset"


def _infer_kind_media(
    obj: Any,
    kind: str | None,
    media_type: str | None,
) -> tuple[str, str]:
    if kind is not None and media_type is not None:
        return kind, media_type
    if isinstance(obj, Path):
        try:
            suffix = obj.suffix.lower()
        except Exception:
            suffix = ""
        mt = "application/octet-stream"
        if suffix in {".png"}:
            mt = "image/png"
            k = "image"
        elif suffix in {".jpg", ".jpeg"}:
            mt = "image/jpeg"
            k = "image"
        elif suffix in {".gif"}:
            mt = "image/gif"
            k = "image"
        elif suffix in {".webp"}:
            mt = "image/webp"
            k = "image"
        else:
            k = "artifact"
        return (kind or k, media_type or mt)
    if isinstance(obj, (bytes, bytearray)):
        return (kind or "artifact", media_type or "application/octet-stream")
    return (kind or "artifact", media_type or "application/octet-stream")


def _normalize_async_backend(backend: Any) -> AsyncDataVaultBackend:
    if isinstance(backend, AsyncDatalake):
        return LocalAsyncDataVaultBackend(backend)
    if isinstance(backend, AsyncDataVaultBackend):
        return backend
    if looks_like_datalake_service_async_client(backend):
        return DatalakeServiceAsyncDataVaultBackend(backend)
    for name in _ASYNC_VAULT_METHOD_NAMES:
        if not callable(getattr(backend, name, None)):
            raise TypeError(
                f"AsyncDataVault requires AsyncDatalake, an AsyncDataVaultBackend, or an object with "
                f"callable async method {name!r}, got {type(backend)!r}"
            )
    return LocalAsyncDataVaultBackend(backend)


def _normalize_sync_backend(backend: Any) -> DataVaultBackend:
    if isinstance(backend, Datalake):
        return LocalDataVaultBackend(backend)
    if isinstance(backend, DataVaultBackend):
        return backend
    if looks_like_datalake_service_sync_client(backend):
        return DatalakeServiceDataVaultBackend(backend)
    for name in _SYNC_VAULT_METHOD_NAMES:
        if not callable(getattr(backend, name, None)):
            raise TypeError(
                f"DataVault requires Datalake, a DataVaultBackend, or an object with callable "
                f"method {name!r}, got {type(backend)!r}"
            )
    return LocalDataVaultBackend(backend)


class AsyncDataVault:
    """Alias-based save/load with a pluggable :class:`~mindtrace.datalake.data_vault_backends.AsyncDataVaultBackend`."""

    def __init__(
        self,
        backend: AsyncDatalake | AsyncDataVaultBackend | Any,
        *,
        object_name_prefix: str = "vault",
    ) -> None:
        self._backend = _normalize_async_backend(backend)
        self._object_name_prefix = object_name_prefix.strip("/").strip() or "vault"

    def _object_name(self, alias: str) -> str:
        safe = _sanitize_object_name_component(alias)
        return f"{self._object_name_prefix}/{safe}"

    async def load(self, alias: str, **get_object_kwargs: Any) -> Any:
        """Resolve ``alias`` to an asset and return the stored object (decoded by the store)."""
        asset = await self._backend.get_asset_by_alias(alias)
        return await self._backend.get_object(asset.storage_ref, **get_object_kwargs)

    async def save(
        self,
        alias: str,
        obj: Any,
        *,
        kind: str | None = None,
        media_type: str | None = None,
        mount: str | None = None,
        created_by: str | None = None,
        asset_metadata: dict[str, Any] | None = None,
        object_metadata: dict[str, Any] | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        """Store ``obj`` and register ``alias`` (unless it equals the new ``asset_id``)."""
        resolved_kind, resolved_media = _infer_kind_media(obj, kind, media_type)
        name = self._object_name(alias)
        asset = await self._backend.create_asset_from_object(
            name=name,
            obj=obj if not isinstance(obj, Path) else obj.read_bytes(),
            kind=resolved_kind,
            media_type=resolved_media,
            mount=mount,
            object_metadata=object_metadata,
            asset_metadata=asset_metadata,
            created_by=created_by,
            on_conflict=on_conflict,
        )
        if alias != asset.asset_id:
            try:
                await self._backend.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset


class DataVault:
    """Blocking alias-based save/load with a pluggable :class:`~mindtrace.datalake.data_vault_backends.DataVaultBackend`."""

    def __init__(
        self,
        backend: Datalake | DataVaultBackend | Any,
        *,
        object_name_prefix: str = "vault",
    ) -> None:
        self._backend = _normalize_sync_backend(backend)
        self._object_name_prefix = object_name_prefix.strip("/").strip() or "vault"

    def _object_name(self, alias: str) -> str:
        safe = _sanitize_object_name_component(alias)
        return f"{self._object_name_prefix}/{safe}"

    def load(self, alias: str, **get_object_kwargs: Any) -> Any:
        """Resolve ``alias`` to an asset and return the stored object (decoded by the store)."""
        asset = self._backend.get_asset_by_alias(alias)
        return self._backend.get_object(asset.storage_ref, **get_object_kwargs)

    def save(
        self,
        alias: str,
        obj: Any,
        *,
        kind: str | None = None,
        media_type: str | None = None,
        mount: str | None = None,
        created_by: str | None = None,
        asset_metadata: dict[str, Any] | None = None,
        object_metadata: dict[str, Any] | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        """Store ``obj`` and register ``alias`` (unless it equals the new ``asset_id``)."""
        resolved_kind, resolved_media = _infer_kind_media(obj, kind, media_type)
        name = self._object_name(alias)
        asset = self._backend.create_asset_from_object(
            name=name,
            obj=obj if not isinstance(obj, Path) else obj.read_bytes(),
            kind=resolved_kind,
            media_type=resolved_media,
            mount=mount,
            object_metadata=object_metadata,
            asset_metadata=asset_metadata,
            created_by=created_by,
            on_conflict=on_conflict,
        )
        if alias != asset.asset_id:
            try:
                self._backend.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset
