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

Both vaults expose ``save_image`` / ``load_image`` (async counterparts on :class:`AsyncDataVault`)
for **PIL** images using **lossless PNG** as the canonical encoded form, and
``add_annotations`` / ``load_annotations`` for batch typed annotations
(:mod:`~mindtrace.datalake.annotations`).

Typical async usage::

    vault = AsyncDataVault(datalake)
    asset = await vault.save("my-key", image_bytes, kind="image", media_type="image/png")
    data = await vault.load("my-key")

Typical sync usage::

    vault = DataVault(datalake)
    asset = vault.save("my-key", image_bytes, kind="image", media_type="image/png")
    data = vault.load("my-key")

Remote service (blocking), after ``DatalakeService`` is running (URL must match the deployed service)::

    from PIL import Image
    from mindtrace.datalake import DataVault

    hopper = Image.open("tests/resources/hopper.png")
    vault = DataVault.from_url("http://localhost:8080")
    vault.save_image("images:hopper", hopper)
    image = vault.load_image("images:hopper")

This is equivalent to calling :meth:`~mindtrace.datalake.service.DatalakeService.connect` and
passing the connection manager to :class:`DataVault` — see :meth:`DataVault.from_url` and
:meth:`AsyncDataVault.from_url`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.datalake.annotations import AnnotationVariants, annotation_from_record
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
from mindtrace.datalake.service import DatalakeService
from mindtrace.datalake.types import AnnotationRecord, Asset, DuplicateAliasError, SubjectRef
from mindtrace.datalake.vault_serialization import (
    augment_asset_metadata_for_vault_save,
    extract_serialization_block,
    materialize_payload_with_hints,
)
from mindtrace.registry import Registry

_SYNC_VAULT_METHODS = _SYNC_VAULT_METHOD_NAMES


def _pil_image_to_png_bytes(image: Image.Image) -> bytes:
    """Encode a PIL image as lossless PNG bytes (Mindtrace canonical wire format for images)."""
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _pil_image_from_payload(payload: Any) -> Image.Image:
    """Decode PNG bytes (or pass through an existing ``Image.Image``) for :meth:`load_image`."""
    if isinstance(payload, Image.Image):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        im = Image.open(BytesIO(bytes(payload)))
        im.load()
        return im
    raise TypeError(
        "load_image expected PNG bytes or PIL.Image.Image after load; got "
        f"{type(payload).__name__}. Use load() for non-image payloads."
    )


def _annotations_bound_to_asset(annotations: list[Any], asset_id: str) -> list[Any]:
    """Force each annotation payload to reference ``asset_id`` as its ``subject``."""
    out: list[Any] = []
    for a in annotations:
        if isinstance(a, dict):
            merged = dict(a)
            merged["subject"] = {"kind": "asset", "id": asset_id}
            out.append(merged)
        elif isinstance(a, AnnotationRecord):
            out.append(a.model_copy(update={"subject": SubjectRef(kind="asset", id=asset_id)}))
        else:
            raise TypeError(
                f"annotations must contain only dicts or AnnotationRecord instances; got {type(a).__name__}"
            )
    return out


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
        registry: Registry | None = None,
    ) -> None:
        self._backend = _normalize_async_backend(backend)
        self._object_name_prefix = object_name_prefix.strip("/").strip() or "vault"
        self._registry = registry

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        timeout: int = 60,
        object_name_prefix: str = "vault",
        registry: Registry | None = None,
    ) -> AsyncDataVault:
        """Connect to a running :class:`~mindtrace.datalake.service.DatalakeService` and return a vault.

        Uses the same connection manager as :meth:`~mindtrace.datalake.service.DatalakeService.connect`
        (including async task methods when exposed by the client).
        """
        cm = DatalakeService.connect(url=url, timeout=timeout)
        return cls(cm, object_name_prefix=object_name_prefix, registry=registry)

    def _object_name(self, alias: str) -> str:
        safe = _sanitize_object_name_component(alias)
        return f"{self._object_name_prefix}/{safe}"

    async def load(
        self,
        alias: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Any:
        """Resolve ``alias`` to an asset and return the payload.

        When ``materialize`` is True and a :class:`~mindtrace.registry.Registry` is provided (via
        ``registry=`` or the vault constructor), byte payloads are passed through ZenML materializers
        using hints stored under ``Asset.metadata["mindtrace.serialization"]`` (see
        :mod:`mindtrace.datalake.vault_serialization`). In-process datalake backends may already
        return materialized objects; in that case this step is skipped for non-bytes results.
        """
        asset = await self._backend.get_asset_by_alias(alias)
        payload = await self._backend.get_object(asset.storage_ref, **get_object_kwargs)
        reg = registry if registry is not None else self._registry
        if not materialize or reg is None:
            return payload
        hints = extract_serialization_block(asset)
        if hints is None or not isinstance(payload, (bytes, bytearray)):
            return payload
        return materialize_payload_with_hints(reg, payload, hints)

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
        materializer: type[BaseMaterializer] | None = None,
    ) -> Asset:
        """Store ``obj`` and register ``alias`` (unless it equals the new ``asset_id``)."""
        resolved_kind, resolved_media = _infer_kind_media(obj, kind, media_type)
        name = self._object_name(alias)
        merged_asset_metadata = augment_asset_metadata_for_vault_save(
            obj,
            asset_metadata,
            registry=self._registry,
            materializer=materializer,
        )
        asset = await self._backend.create_asset_from_object(
            name=name,
            obj=obj if not isinstance(obj, Path) else obj.read_bytes(),
            kind=resolved_kind,
            media_type=resolved_media,
            mount=mount,
            object_metadata=object_metadata,
            asset_metadata=merged_asset_metadata,
            created_by=created_by,
            on_conflict=on_conflict,
        )
        if alias != asset.asset_id:
            try:
                await self._backend.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset

    async def save_image(
        self,
        alias: str,
        image: Image.Image,
        *,
        mount: str | None = None,
        created_by: str | None = None,
        asset_metadata: dict[str, Any] | None = None,
        object_metadata: dict[str, Any] | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        """Store a :class:`PIL.Image.Image` as **lossless PNG** (``kind=image``, ``media_type=image/png``)."""
        if not isinstance(image, Image.Image):
            raise TypeError(f"save_image expected PIL.Image.Image, got {type(image).__name__}")
        png_bytes = _pil_image_to_png_bytes(image)
        merged_asset_metadata = augment_asset_metadata_for_vault_save(
            png_bytes,
            asset_metadata,
            registry=self._registry,
            materializer=None,
        )
        name = self._object_name(alias)
        asset = await self._backend.create_asset_from_object(
            name=name,
            obj=png_bytes,
            kind="image",
            media_type="image/png",
            mount=mount,
            object_metadata=object_metadata,
            asset_metadata=merged_asset_metadata,
            created_by=created_by,
            on_conflict=on_conflict,
        )
        if alias != asset.asset_id:
            try:
                await self._backend.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset

    async def load_image(
        self,
        alias: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Image.Image:
        """Load an asset saved via :meth:`save_image` and return a :class:`PIL.Image.Image`."""
        payload = await self.load(
            alias,
            materialize=materialize,
            registry=registry,
            **get_object_kwargs,
        )
        return _pil_image_from_payload(payload)

    async def add_annotations_for_asset(
        self,
        alias: str,
        annotations: list[Any],
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        """Resolve ``alias`` to an asset and insert annotations with ``subject`` set to that asset."""
        asset = await self._backend.get_asset_by_alias(alias)
        merged = _annotations_bound_to_asset(annotations, asset.asset_id)
        return await self._backend.add_annotation_records(
            merged,
            annotation_set_id=annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )

    async def list_annotations_for_asset(self, alias: str) -> list[AnnotationRecord]:
        """List annotation records whose subject is the asset resolved from ``alias``."""
        asset = await self._backend.get_asset_by_alias(alias)
        return await self._backend.list_annotation_records_for_asset(asset.asset_id)

    async def add_annotations(
        self,
        alias: str,
        annotations: Sequence[AnnotationVariants],
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        """Insert Pydantic annotation models (see :mod:`~mindtrace.datalake.annotations`) on the asset at ``alias``."""
        asset = await self._backend.get_asset_by_alias(alias)
        payloads = [a.to_payload() for a in annotations]
        merged = _annotations_bound_to_asset(payloads, asset.asset_id)
        return await self._backend.add_annotation_records(
            merged,
            annotation_set_id=annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )

    async def load_annotations(self, alias: str) -> list[AnnotationVariants]:
        """Load annotations as discriminated-union Pydantic models for the asset at ``alias``."""
        asset = await self._backend.get_asset_by_alias(alias)
        records = await self._backend.list_annotation_records_for_asset(asset.asset_id)
        return [annotation_from_record(r) for r in records]


class DataVault:
    """Blocking alias-based save/load with a pluggable :class:`~mindtrace.datalake.data_vault_backends.DataVaultBackend`."""

    def __init__(
        self,
        backend: Datalake | DataVaultBackend | Any,
        *,
        object_name_prefix: str = "vault",
        registry: Registry | None = None,
    ) -> None:
        self._backend = _normalize_sync_backend(backend)
        self._object_name_prefix = object_name_prefix.strip("/").strip() or "vault"
        self._registry = registry

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        timeout: int = 60,
        object_name_prefix: str = "vault",
        registry: Registry | None = None,
    ) -> DataVault:
        """Connect to a running :class:`~mindtrace.datalake.service.DatalakeService` and return a vault.

        Equivalent to ``DataVault(DatalakeService.connect(url=url, timeout=timeout), ...)``.
        """
        cm = DatalakeService.connect(url=url, timeout=timeout)
        return cls(cm, object_name_prefix=object_name_prefix, registry=registry)

    def _object_name(self, alias: str) -> str:
        safe = _sanitize_object_name_component(alias)
        return f"{self._object_name_prefix}/{safe}"

    def load(
        self,
        alias: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Any:
        """Resolve ``alias`` to an asset and return the payload.

        When ``materialize`` is True and a :class:`~mindtrace.registry.Registry` is provided (via
        ``registry=`` or the vault constructor), byte payloads are passed through ZenML materializers
        using hints stored under ``Asset.metadata["mindtrace.serialization"]`` (see
        :mod:`mindtrace.datalake.vault_serialization`). In-process datalake backends may already
        return materialized objects; in that case this step is skipped for non-bytes results.
        """
        asset = self._backend.get_asset_by_alias(alias)
        payload = self._backend.get_object(asset.storage_ref, **get_object_kwargs)
        reg = registry if registry is not None else self._registry
        if not materialize or reg is None:
            return payload
        hints = extract_serialization_block(asset)
        if hints is None or not isinstance(payload, (bytes, bytearray)):
            return payload
        return materialize_payload_with_hints(reg, payload, hints)

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
        materializer: type[BaseMaterializer] | None = None,
    ) -> Asset:
        """Store ``obj`` and register ``alias`` (unless it equals the new ``asset_id``)."""
        resolved_kind, resolved_media = _infer_kind_media(obj, kind, media_type)
        name = self._object_name(alias)
        merged_asset_metadata = augment_asset_metadata_for_vault_save(
            obj,
            asset_metadata,
            registry=self._registry,
            materializer=materializer,
        )
        asset = self._backend.create_asset_from_object(
            name=name,
            obj=obj if not isinstance(obj, Path) else obj.read_bytes(),
            kind=resolved_kind,
            media_type=resolved_media,
            mount=mount,
            object_metadata=object_metadata,
            asset_metadata=merged_asset_metadata,
            created_by=created_by,
            on_conflict=on_conflict,
        )
        if alias != asset.asset_id:
            try:
                self._backend.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset

    def save_image(
        self,
        alias: str,
        image: Image.Image,
        *,
        mount: str | None = None,
        created_by: str | None = None,
        asset_metadata: dict[str, Any] | None = None,
        object_metadata: dict[str, Any] | None = None,
        on_conflict: str | None = None,
    ) -> Asset:
        """Store a :class:`PIL.Image.Image` as **lossless PNG** (``kind=image``, ``media_type=image/png``)."""
        if not isinstance(image, Image.Image):
            raise TypeError(f"save_image expected PIL.Image.Image, got {type(image).__name__}")
        png_bytes = _pil_image_to_png_bytes(image)
        merged_asset_metadata = augment_asset_metadata_for_vault_save(
            png_bytes,
            asset_metadata,
            registry=self._registry,
            materializer=None,
        )
        name = self._object_name(alias)
        asset = self._backend.create_asset_from_object(
            name=name,
            obj=png_bytes,
            kind="image",
            media_type="image/png",
            mount=mount,
            object_metadata=object_metadata,
            asset_metadata=merged_asset_metadata,
            created_by=created_by,
            on_conflict=on_conflict,
        )
        if alias != asset.asset_id:
            try:
                self._backend.add_alias(asset.asset_id, alias)
            except DuplicateAliasError:
                raise
        return asset

    def load_image(
        self,
        alias: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Image.Image:
        """Load an asset saved via :meth:`save_image` and return a :class:`PIL.Image.Image`."""
        payload = self.load(
            alias,
            materialize=materialize,
            registry=registry,
            **get_object_kwargs,
        )
        return _pil_image_from_payload(payload)

    def add_annotations_for_asset(
        self,
        alias: str,
        annotations: list[Any],
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        """Resolve ``alias`` to an asset and insert annotations with ``subject`` set to that asset."""
        asset = self._backend.get_asset_by_alias(alias)
        merged = _annotations_bound_to_asset(annotations, asset.asset_id)
        return self._backend.add_annotation_records(
            merged,
            annotation_set_id=annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )

    def list_annotations_for_asset(self, alias: str) -> list[AnnotationRecord]:
        """List annotation records whose subject is the asset resolved from ``alias``."""
        asset = self._backend.get_asset_by_alias(alias)
        return self._backend.list_annotation_records_for_asset(asset.asset_id)

    def add_annotations(
        self,
        alias: str,
        annotations: Sequence[AnnotationVariants],
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ) -> list[AnnotationRecord]:
        """Insert Pydantic annotation models (see :mod:`~mindtrace.datalake.annotations`) on the asset at ``alias``."""
        asset = self._backend.get_asset_by_alias(alias)
        payloads = [a.to_payload() for a in annotations]
        merged = _annotations_bound_to_asset(payloads, asset.asset_id)
        return self._backend.add_annotation_records(
            merged,
            annotation_set_id=annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )

    def load_annotations(self, alias: str) -> list[AnnotationVariants]:
        """Load annotations as discriminated-union Pydantic models for the asset at ``alias``."""
        asset = self._backend.get_asset_by_alias(alias)
        records = self._backend.list_annotation_records_for_asset(asset.asset_id)
        return [annotation_from_record(r) for r in records]
