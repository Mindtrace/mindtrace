"""High-level alias-based access to datalake assets and payloads.

Serialization uses the same registry/store stack as :class:`~mindtrace.datalake.AsyncDatalake`
(``put_object`` / ``get_object``), so ZenML materializers registered on ``Registry`` apply.

- :class:`AsyncDataVault` -- use with :class:`AsyncDatalake` (``async`` / ``await``).
- :class:`DataVault` -- use with :class:`Datalake` (blocking, same thread as other sync datalake APIs).

Typical async usage::

    vault = AsyncDataVault(datalake)
    asset = await vault.save("my-key", image_bytes, kind="image", media_type="image/png")
    data = await vault.load("my-key")

Typical sync usage::

    vault = DataVault(datalake)
    asset = vault.save("my-key", image_bytes, kind="image", media_type="image/png")
    data = vault.load("my-key")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.types import Asset, DuplicateAliasError

_SYNC_VAULT_METHODS = ("get_asset_by_alias", "get_object", "create_asset_from_object", "add_alias")


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


class AsyncDataVault:
    """Alias-based save/load on top of :class:`AsyncDatalake`."""

    def __init__(
        self,
        datalake: AsyncDatalake,
        *,
        object_name_prefix: str = "vault",
    ) -> None:
        self._datalake = datalake
        self._object_name_prefix = object_name_prefix.strip("/").strip() or "vault"

    def _object_name(self, alias: str) -> str:
        safe = _sanitize_object_name_component(alias)
        return f"{self._object_name_prefix}/{safe}"

    async def load(self, alias: str, **get_object_kwargs: Any) -> Any:
        """Resolve ``alias`` to an asset and return the stored object (decoded by the store)."""
        asset = await self._datalake.get_asset_by_alias(alias)
        return await self._datalake.get_object(asset.storage_ref, **get_object_kwargs)

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
        asset = await self._datalake.create_asset_from_object(
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
                await self._datalake.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset


class DataVault:
    """Blocking alias-based save/load on top of :class:`~mindtrace.datalake.Datalake`.

    The constructor accepts any object exposing the same sync methods as ``Datalake``:
    ``get_asset_by_alias``, ``get_object``, ``create_asset_from_object``, ``add_alias``.
    """

    def __init__(
        self,
        datalake: Any,
        *,
        object_name_prefix: str = "vault",
    ) -> None:
        for name in _SYNC_VAULT_METHODS:
            if not callable(getattr(datalake, name, None)):
                raise TypeError(
                    f"DataVault requires a sync datalake with callable {name!r}, got {type(datalake)!r}"
                )
        self._dl = datalake
        self._object_name_prefix = object_name_prefix.strip("/").strip() or "vault"

    def _object_name(self, alias: str) -> str:
        safe = _sanitize_object_name_component(alias)
        return f"{self._object_name_prefix}/{safe}"

    def load(self, alias: str, **get_object_kwargs: Any) -> Any:
        """Resolve ``alias`` to an asset and return the stored object (decoded by the store)."""
        asset = self._dl.get_asset_by_alias(alias)
        return self._dl.get_object(asset.storage_ref, **get_object_kwargs)

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
        asset = self._dl.create_asset_from_object(
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
                self._dl.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset
