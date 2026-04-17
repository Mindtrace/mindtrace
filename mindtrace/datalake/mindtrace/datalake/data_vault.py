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
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.database.core.exceptions import DocumentNotFoundError
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
from mindtrace.datalake.pagination_types import CursorPage
from mindtrace.datalake.service import DatalakeService
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    Collection,
    CollectionItem,
    DuplicateAliasError,
    SubjectRef,
)
from mindtrace.datalake.vault_serialization import (
    augment_asset_metadata_for_vault_save,
    extract_serialization_block,
    materialize_payload_with_hints,
)
from mindtrace.registry import Registry

_SYNC_VAULT_METHODS = _SYNC_VAULT_METHOD_NAMES
_DATA_VAULT_METADATA_QUERY_PREFIX = "metadata.mindtrace.data_vault"


class VaultDataset(BaseModel):
    """Human-facing mutable dataset descriptor backed by a datalake collection."""

    dataset_id: str
    name: str
    description: str | None = None
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    asset_count: int = 0
    created_at: datetime
    created_by: str | None = None
    updated_at: datetime


def _dataset_filters(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(filters or {})
    merged.setdefault("status", "active")
    return merged


def _build_vault_dataset(collection: Collection, *, asset_count: int) -> VaultDataset:
    return VaultDataset(
        dataset_id=collection.collection_id,
        name=collection.name,
        description=collection.description,
        status=collection.status,
        metadata=dict(collection.metadata or {}),
        asset_count=asset_count,
        created_at=collection.created_at,
        created_by=collection.created_by,
        updated_at=collection.updated_at,
    )


def _dataset_annotation_set_metadata(collection: Collection, asset_id: str) -> dict[str, Any]:
    return {
        "mindtrace": {
            "data_vault": {
                "dataset_collection_id": collection.collection_id,
                "dataset_name": collection.name,
                "asset_id": asset_id,
            }
        }
    }


def _dataset_annotation_set_filters(collection_id: str, *, asset_id: str | None = None) -> dict[str, Any]:
    filters: dict[str, Any] = {
        f"{_DATA_VAULT_METADATA_QUERY_PREFIX}.dataset_collection_id": collection_id,
        "status": "active",
    }
    if asset_id is not None:
        filters[f"{_DATA_VAULT_METADATA_QUERY_PREFIX}.asset_id"] = asset_id
    return filters


def _coerce_annotation_payload(annotation: AnnotationRecord | AnnotationVariants | dict[str, Any]) -> dict[str, Any]:
    if isinstance(annotation, AnnotationRecord):
        return annotation.model_dump(mode="json")
    if isinstance(annotation, dict):
        return dict(annotation)
    if hasattr(annotation, "to_payload"):
        return dict(annotation.to_payload())
    raise TypeError("annotation must be a dict, AnnotationRecord, or typed annotation model with to_payload()")


def _extract_annotation_asset_id(payload: dict[str, Any]) -> str | None:
    subject = payload.get("subject")
    if isinstance(subject, SubjectRef):
        return subject.id if subject.kind == "asset" else None
    if isinstance(subject, dict) and subject.get("kind") == "asset":
        asset_id = subject.get("id")
        return str(asset_id) if asset_id is not None else None
    return None


def _annotation_source_type(payload: dict[str, Any]) -> str:
    source = payload.get("source")
    if isinstance(source, dict):
        source_type = source.get("type")
        if source_type in {"human", "machine", "mixed"}:
            return str(source_type)
    return "mixed"


def _annotation_id(annotation: str | AnnotationRecord) -> str:
    if isinstance(annotation, AnnotationRecord):
        return annotation.annotation_id
    return annotation


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

    async def _resolve_asset_id(self, asset: str | Asset) -> str:
        if isinstance(asset, Asset):
            return asset.asset_id
        try:
            return (await self._backend.get_asset(asset)).asset_id
        except DocumentNotFoundError:
            return (await self._backend.get_asset_by_alias(asset)).asset_id

    async def _get_dataset_collection(self, dataset: str | VaultDataset) -> Collection:
        if isinstance(dataset, VaultDataset):
            matches = await self._backend.list_collections({"collection_id": dataset.dataset_id})
        else:
            matches = await self._backend.list_collections(_dataset_filters({"name": dataset}))
        if not matches:
            raise DocumentNotFoundError(f"Dataset {dataset!r} not found")
        if len(matches) > 1:
            raise ValueError(f"Multiple active datasets matched {dataset!r}; use a unique dataset name.")
        return matches[0]

    async def _dataset_asset_count(self, collection_id: str) -> int:
        items = await self._backend.list_collection_items({"collection_id": collection_id, "status": "active"})
        return len({item.asset_id for item in items})

    async def _build_dataset_summary(self, collection: Collection) -> VaultDataset:
        return _build_vault_dataset(collection, asset_count=await self._dataset_asset_count(collection.collection_id))

    async def _ensure_collection_item(
        self,
        collection: Collection,
        asset_id: str,
        *,
        split: str | None = None,
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> CollectionItem:
        items = await self._backend.list_collection_items(
            {"collection_id": collection.collection_id, "asset_id": asset_id}
        )
        active_items = [item for item in items if item.status == "active"]
        if active_items:
            item = active_items[0]
            changes: dict[str, Any] = {}
            if split is not None and item.split != split:
                changes["split"] = split
            if metadata:
                changes["metadata"] = {**item.metadata, **metadata}
            if changes:
                item = await self._backend.update_collection_item(item.collection_item_id, **changes)
            return item
        if items:
            item = items[0]
            return await self._backend.update_collection_item(
                item.collection_item_id,
                status="active",
                split=split if split is not None else item.split,
                metadata={**item.metadata, **(metadata or {})},
            )
        return await self._backend.create_collection_item(
            collection_id=collection.collection_id,
            asset_id=asset_id,
            split=split,
            status="active",
            metadata=metadata,
            added_by=added_by,
        )

    async def _get_or_create_dataset_annotation_set(
        self,
        collection: Collection,
        asset_id: str,
        *,
        created_by: str | None = None,
        annotation_schema_id: str | None = None,
        source_type: str = "mixed",
    ) -> AnnotationSet:
        filters = _dataset_annotation_set_filters(collection.collection_id, asset_id=asset_id)
        matches = await self._backend.list_annotation_sets(filters)
        if matches:
            return matches[0]
        return await self._backend.create_annotation_set(
            name=f"{collection.name}:{asset_id}",
            purpose="other",
            source_type=source_type,
            status="active",
            metadata=_dataset_annotation_set_metadata(collection, asset_id),
            created_by=created_by,
            annotation_schema_id=annotation_schema_id,
        )

    async def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        """List assets eagerly; prefer :meth:`iter_assets` or :meth:`list_assets_page` for scalable discovery."""
        return await self._backend.list_assets(filters)

    async def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        """Return one cursor-based page of assets visible to the backing store."""
        return await self._backend.list_assets_page(
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
        """Stream assets lazily from the backing store."""
        async for asset in self._backend.iter_assets(filters=filters, sort=sort, batch_size=batch_size):
            yield asset

    async def list_image_assets(self) -> list[Asset]:
        """List image assets eagerly; prefer :meth:`iter_image_assets` or :meth:`list_image_assets_page`."""
        return await self._backend.list_assets({"kind": "image"})

    async def list_image_assets_page(
        self,
        *,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        """Return one cursor-based page of image assets."""
        return await self.list_assets_page(
            filters={"kind": "image"},
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    async def iter_image_assets(
        self,
        *,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[Asset]:
        """Stream image assets lazily from the backing store."""
        async for asset in self.iter_assets(filters={"kind": "image"}, sort=sort, batch_size=batch_size):
            yield asset

    async def get_asset(self, asset_id: str) -> Asset:
        """Load :class:`~mindtrace.datalake.types.Asset` metadata by canonical ``asset_id``."""
        return await self._backend.get_asset(asset_id)

    async def list_datasets(self, filters: dict[str, Any] | None = None) -> list[VaultDataset]:
        """List mutable human-facing datasets backed by active datalake collections."""
        collections = await self._backend.list_collections(_dataset_filters(filters))
        return [await self._build_dataset_summary(collection) for collection in collections]

    async def list_datasets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "updated_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[VaultDataset]:
        page = await self._backend.list_collections_page(
            filters=_dataset_filters(filters),
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )
        return CursorPage(items=[await self._build_dataset_summary(item) for item in page.items], page=page.page)

    async def iter_datasets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "updated_desc",
        batch_size: int | None = None,
    ) -> AsyncIterator[VaultDataset]:
        async for collection in self._backend.iter_collections(
            filters=_dataset_filters(filters),
            sort=sort,
            batch_size=batch_size,
        ):
            yield await self._build_dataset_summary(collection)

    async def get_dataset(self, name: str) -> VaultDataset:
        """Return one mutable dataset by its human-readable name."""
        return await self._build_dataset_summary(await self._get_dataset_collection(name))

    async def create_dataset(
        self,
        name: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> VaultDataset:
        """Create a new mutable dataset backed by a datalake collection."""
        existing = await self._backend.list_collections(_dataset_filters({"name": name}))
        if existing:
            raise ValueError(f"Dataset {name!r} already exists")
        collection = await self._backend.create_collection(
            name=name,
            description=description,
            status="active",
            metadata=metadata,
            created_by=created_by,
        )
        return _build_vault_dataset(collection, asset_count=0)

    async def add_asset(
        self,
        dataset: str | VaultDataset,
        asset: str | Asset,
        *,
        split: str | None = None,
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> Asset:
        """Ensure an asset belongs to a dataset, creating or reactivating membership as needed."""
        collection = await self._get_dataset_collection(dataset)
        asset_id = await self._resolve_asset_id(asset)
        await self._ensure_collection_item(collection, asset_id, split=split, metadata=metadata, added_by=added_by)
        return await self._backend.get_asset(asset_id)

    async def remove_asset(self, dataset: str | VaultDataset, asset: str | Asset, *, missing_ok: bool = False) -> None:
        """Remove an asset from a dataset without deleting the asset itself."""
        collection = await self._get_dataset_collection(dataset)
        asset_id = await self._resolve_asset_id(asset)
        items = await self._backend.list_collection_items(
            {"collection_id": collection.collection_id, "asset_id": asset_id}
        )
        if not items and not missing_ok:
            raise DocumentNotFoundError(f"Asset {asset_id!r} is not part of dataset {collection.name!r}")
        for item in items:
            await self._backend.delete_collection_item(item.collection_item_id)

    async def list_dataset_assets(self, dataset: str | VaultDataset) -> list[Asset]:
        """List unique active assets that belong to a dataset."""
        collection = await self._get_dataset_collection(dataset)
        items = await self._backend.list_collection_items(
            {"collection_id": collection.collection_id, "status": "active"}
        )
        assets: list[Asset] = []
        seen: set[str] = set()
        for item in items:
            if item.asset_id in seen:
                continue
            seen.add(item.asset_id)
            assets.append(await self._backend.get_asset(item.asset_id))
        return assets

    async def add_annotation(
        self,
        dataset: str | VaultDataset,
        annotation: AnnotationRecord | AnnotationVariants | dict[str, Any],
        *,
        asset: str | Asset | None = None,
        annotation_schema_id: str | None = None,
        created_by: str | None = None,
    ) -> AnnotationRecord:
        """Add one annotation to a dataset, implicitly adding its asset membership when needed."""
        collection = await self._get_dataset_collection(dataset)
        payload = _coerce_annotation_payload(annotation)
        asset_id = await self._resolve_asset_id(asset) if asset is not None else _extract_annotation_asset_id(payload)
        if asset_id is None:
            raise ValueError("Annotation must reference an asset subject, or asset= must be provided.")
        await self._ensure_collection_item(collection, asset_id)
        payload["subject"] = {"kind": "asset", "id": asset_id}
        annotation_set = await self._get_or_create_dataset_annotation_set(
            collection,
            asset_id,
            created_by=created_by,
            annotation_schema_id=annotation_schema_id,
            source_type=_annotation_source_type(payload),
        )
        records = await self._backend.add_annotation_records(
            [payload],
            annotation_set_id=annotation_set.annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )
        return records[0]

    async def remove_annotation(
        self,
        dataset: str | VaultDataset,
        annotation: str | AnnotationRecord,
        *,
        missing_ok: bool = False,
    ) -> None:
        """Remove a dataset-scoped annotation record from the dataset without removing its asset."""
        collection = await self._get_dataset_collection(dataset)
        annotation_id = _annotation_id(annotation)
        annotation_sets = await self._backend.list_annotation_sets(
            _dataset_annotation_set_filters(collection.collection_id)
        )
        if not any(annotation_id in annotation_set.annotation_record_ids for annotation_set in annotation_sets):
            if missing_ok:
                return
            raise DocumentNotFoundError(f"Annotation {annotation_id!r} is not part of dataset {collection.name!r}")
        await self._backend.delete_annotation_record(annotation_id)

    async def list_dataset_annotations(
        self,
        dataset: str | VaultDataset,
        *,
        asset: str | Asset | None = None,
    ) -> list[AnnotationRecord]:
        """List dataset-scoped annotations, optionally filtered to one asset."""
        collection = await self._get_dataset_collection(dataset)
        asset_id = await self._resolve_asset_id(asset) if asset is not None else None
        annotation_sets = await self._backend.list_annotation_sets(
            _dataset_annotation_set_filters(collection.collection_id, asset_id=asset_id)
        )
        annotations: list[AnnotationRecord] = []
        for annotation_set in annotation_sets:
            for annotation_id in annotation_set.annotation_record_ids:
                annotations.append(await self._backend.get_annotation_record(annotation_id))
        return annotations

    async def load(
        self,
        alias: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Any:
        """Resolve a registered **alias** string to an asset and return the stored payload.

        Aliases are rows in the asset-alias table; they are not always identical to ``asset_id``.
        To load by ``asset_id`` from :meth:`list_assets`, use :meth:`load_by_asset_id`.

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

    async def load_by_asset_id(
        self,
        asset_id: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Any:
        """Load payload bytes for ``asset_id`` without resolving an alias."""
        asset = await self._backend.get_asset(asset_id)
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
        """Load an image using a registered **alias** (see :meth:`load`)."""
        payload = await self.load(
            alias,
            materialize=materialize,
            registry=registry,
            **get_object_kwargs,
        )
        return _pil_image_from_payload(payload)

    async def load_image_by_asset_id(
        self,
        asset_id: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Image.Image:
        """Decode image bytes for ``asset_id`` (no alias lookup)."""
        payload = await self.load_by_asset_id(
            asset_id,
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

    def _resolve_asset_id(self, asset: str | Asset) -> str:
        if isinstance(asset, Asset):
            return asset.asset_id
        try:
            return self._backend.get_asset(asset).asset_id
        except DocumentNotFoundError:
            return self._backend.get_asset_by_alias(asset).asset_id

    def _get_dataset_collection(self, dataset: str | VaultDataset) -> Collection:
        if isinstance(dataset, VaultDataset):
            matches = self._backend.list_collections({"collection_id": dataset.dataset_id})
        else:
            matches = self._backend.list_collections(_dataset_filters({"name": dataset}))
        if not matches:
            raise DocumentNotFoundError(f"Dataset {dataset!r} not found")
        if len(matches) > 1:
            raise ValueError(f"Multiple active datasets matched {dataset!r}; use a unique dataset name.")
        return matches[0]

    def _dataset_asset_count(self, collection_id: str) -> int:
        items = self._backend.list_collection_items({"collection_id": collection_id, "status": "active"})
        return len({item.asset_id for item in items})

    def _build_dataset_summary(self, collection: Collection) -> VaultDataset:
        return _build_vault_dataset(collection, asset_count=self._dataset_asset_count(collection.collection_id))

    def _ensure_collection_item(
        self,
        collection: Collection,
        asset_id: str,
        *,
        split: str | None = None,
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> CollectionItem:
        items = self._backend.list_collection_items({"collection_id": collection.collection_id, "asset_id": asset_id})
        active_items = [item for item in items if item.status == "active"]
        if active_items:
            item = active_items[0]
            changes: dict[str, Any] = {}
            if split is not None and item.split != split:
                changes["split"] = split
            if metadata:
                changes["metadata"] = {**item.metadata, **metadata}
            if changes:
                item = self._backend.update_collection_item(item.collection_item_id, **changes)
            return item
        if items:
            item = items[0]
            return self._backend.update_collection_item(
                item.collection_item_id,
                status="active",
                split=split if split is not None else item.split,
                metadata={**item.metadata, **(metadata or {})},
            )
        return self._backend.create_collection_item(
            collection_id=collection.collection_id,
            asset_id=asset_id,
            split=split,
            status="active",
            metadata=metadata,
            added_by=added_by,
        )

    def _get_or_create_dataset_annotation_set(
        self,
        collection: Collection,
        asset_id: str,
        *,
        created_by: str | None = None,
        annotation_schema_id: str | None = None,
        source_type: str = "mixed",
    ) -> AnnotationSet:
        filters = _dataset_annotation_set_filters(collection.collection_id, asset_id=asset_id)
        matches = self._backend.list_annotation_sets(filters)
        if matches:
            return matches[0]
        return self._backend.create_annotation_set(
            name=f"{collection.name}:{asset_id}",
            purpose="other",
            source_type=source_type,
            status="active",
            metadata=_dataset_annotation_set_metadata(collection, asset_id),
            created_by=created_by,
            annotation_schema_id=annotation_schema_id,
        )

    def list_assets(self, filters: dict[str, Any] | None = None) -> list[Asset]:
        """List assets eagerly; prefer :meth:`iter_assets` or :meth:`list_assets_page` for scalable discovery."""
        return self._backend.list_assets(filters)

    def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        """Return one cursor-based page of assets visible to the backing store."""
        return self._backend.list_assets_page(
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
        """Stream assets lazily from the backing store."""
        yield from self._backend.iter_assets(filters=filters, sort=sort, batch_size=batch_size)

    def list_image_assets(self) -> list[Asset]:
        """List image assets eagerly; prefer :meth:`iter_image_assets` or :meth:`list_image_assets_page`."""
        return self._backend.list_assets({"kind": "image"})

    def list_image_assets_page(
        self,
        *,
        sort: str = "created_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[Asset]:
        """Return one cursor-based page of image assets."""
        return self.list_assets_page(
            filters={"kind": "image"},
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )

    def iter_image_assets(
        self,
        *,
        sort: str = "created_desc",
        batch_size: int | None = None,
    ) -> Iterator[Asset]:
        """Stream image assets lazily from the backing store."""
        yield from self.iter_assets(filters={"kind": "image"}, sort=sort, batch_size=batch_size)

    def get_asset(self, asset_id: str) -> Asset:
        """Load :class:`~mindtrace.datalake.types.Asset` metadata by canonical ``asset_id``."""
        return self._backend.get_asset(asset_id)

    def list_datasets(self, filters: dict[str, Any] | None = None) -> list[VaultDataset]:
        """List mutable human-facing datasets backed by active datalake collections."""
        collections = self._backend.list_collections(_dataset_filters(filters))
        return [self._build_dataset_summary(collection) for collection in collections]

    def list_datasets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "updated_desc",
        limit: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> CursorPage[VaultDataset]:
        page = self._backend.list_collections_page(
            filters=_dataset_filters(filters),
            sort=sort,
            limit=limit,
            cursor=cursor,
            include_total=include_total,
        )
        return CursorPage(items=[self._build_dataset_summary(item) for item in page.items], page=page.page)

    def iter_datasets(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "updated_desc",
        batch_size: int | None = None,
    ) -> Iterator[VaultDataset]:
        for collection in self._backend.iter_collections(
            filters=_dataset_filters(filters),
            sort=sort,
            batch_size=batch_size,
        ):
            yield self._build_dataset_summary(collection)

    def get_dataset(self, name: str) -> VaultDataset:
        """Return one mutable dataset by its human-readable name."""
        return self._build_dataset_summary(self._get_dataset_collection(name))

    def create_dataset(
        self,
        name: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> VaultDataset:
        """Create a new mutable dataset backed by a datalake collection."""
        existing = self._backend.list_collections(_dataset_filters({"name": name}))
        if existing:
            raise ValueError(f"Dataset {name!r} already exists")
        collection = self._backend.create_collection(
            name=name,
            description=description,
            status="active",
            metadata=metadata,
            created_by=created_by,
        )
        return _build_vault_dataset(collection, asset_count=0)

    def add_asset(
        self,
        dataset: str | VaultDataset,
        asset: str | Asset,
        *,
        split: str | None = None,
        metadata: dict[str, Any] | None = None,
        added_by: str | None = None,
    ) -> Asset:
        """Ensure an asset belongs to a dataset, creating or reactivating membership as needed."""
        collection = self._get_dataset_collection(dataset)
        asset_id = self._resolve_asset_id(asset)
        self._ensure_collection_item(collection, asset_id, split=split, metadata=metadata, added_by=added_by)
        return self._backend.get_asset(asset_id)

    def remove_asset(self, dataset: str | VaultDataset, asset: str | Asset, *, missing_ok: bool = False) -> None:
        """Remove an asset from a dataset without deleting the asset itself."""
        collection = self._get_dataset_collection(dataset)
        asset_id = self._resolve_asset_id(asset)
        items = self._backend.list_collection_items({"collection_id": collection.collection_id, "asset_id": asset_id})
        if not items and not missing_ok:
            raise DocumentNotFoundError(f"Asset {asset_id!r} is not part of dataset {collection.name!r}")
        for item in items:
            self._backend.delete_collection_item(item.collection_item_id)

    def list_dataset_assets(self, dataset: str | VaultDataset) -> list[Asset]:
        """List unique active assets that belong to a dataset."""
        collection = self._get_dataset_collection(dataset)
        items = self._backend.list_collection_items({"collection_id": collection.collection_id, "status": "active"})
        assets: list[Asset] = []
        seen: set[str] = set()
        for item in items:
            if item.asset_id in seen:
                continue
            seen.add(item.asset_id)
            assets.append(self._backend.get_asset(item.asset_id))
        return assets

    def add_annotation(
        self,
        dataset: str | VaultDataset,
        annotation: AnnotationRecord | AnnotationVariants | dict[str, Any],
        *,
        asset: str | Asset | None = None,
        annotation_schema_id: str | None = None,
        created_by: str | None = None,
    ) -> AnnotationRecord:
        """Add one annotation to a dataset, implicitly adding its asset membership when needed."""
        collection = self._get_dataset_collection(dataset)
        payload = _coerce_annotation_payload(annotation)
        asset_id = self._resolve_asset_id(asset) if asset is not None else _extract_annotation_asset_id(payload)
        if asset_id is None:
            raise ValueError("Annotation must reference an asset subject, or asset= must be provided.")
        self._ensure_collection_item(collection, asset_id)
        payload["subject"] = {"kind": "asset", "id": asset_id}
        annotation_set = self._get_or_create_dataset_annotation_set(
            collection,
            asset_id,
            created_by=created_by,
            annotation_schema_id=annotation_schema_id,
            source_type=_annotation_source_type(payload),
        )
        records = self._backend.add_annotation_records(
            [payload],
            annotation_set_id=annotation_set.annotation_set_id,
            annotation_schema_id=annotation_schema_id,
        )
        return records[0]

    def remove_annotation(
        self,
        dataset: str | VaultDataset,
        annotation: str | AnnotationRecord,
        *,
        missing_ok: bool = False,
    ) -> None:
        """Remove a dataset-scoped annotation record from the dataset without removing its asset."""
        collection = self._get_dataset_collection(dataset)
        annotation_id = _annotation_id(annotation)
        annotation_sets = self._backend.list_annotation_sets(_dataset_annotation_set_filters(collection.collection_id))
        if not any(annotation_id in annotation_set.annotation_record_ids for annotation_set in annotation_sets):
            if missing_ok:
                return
            raise DocumentNotFoundError(f"Annotation {annotation_id!r} is not part of dataset {collection.name!r}")
        self._backend.delete_annotation_record(annotation_id)

    def list_dataset_annotations(
        self,
        dataset: str | VaultDataset,
        *,
        asset: str | Asset | None = None,
    ) -> list[AnnotationRecord]:
        """List dataset-scoped annotations, optionally filtered to one asset."""
        collection = self._get_dataset_collection(dataset)
        asset_id = self._resolve_asset_id(asset) if asset is not None else None
        annotation_sets = self._backend.list_annotation_sets(
            _dataset_annotation_set_filters(collection.collection_id, asset_id=asset_id)
        )
        annotations: list[AnnotationRecord] = []
        for annotation_set in annotation_sets:
            for annotation_id in annotation_set.annotation_record_ids:
                annotations.append(self._backend.get_annotation_record(annotation_id))
        return annotations

    def load(
        self,
        alias: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Any:
        """Resolve a registered **alias** string to an asset and return the stored payload.

        Aliases are rows in the asset-alias table; they are not always identical to ``asset_id``.
        To load by ``asset_id`` from :meth:`list_assets`, use :meth:`load_by_asset_id`.

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

    def load_by_asset_id(
        self,
        asset_id: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Any:
        """Load payload bytes for ``asset_id`` without resolving an alias."""
        asset = self._backend.get_asset(asset_id)
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
        """Load an image using a registered **alias** (see :meth:`load`)."""
        payload = self.load(
            alias,
            materialize=materialize,
            registry=registry,
            **get_object_kwargs,
        )
        return _pil_image_from_payload(payload)

    def load_image_by_asset_id(
        self,
        asset_id: str,
        *,
        materialize: bool = True,
        registry: Registry | None = None,
        **get_object_kwargs: Any,
    ) -> Image.Image:
        """Decode image bytes for ``asset_id`` (no alias lookup)."""
        payload = self.load_by_asset_id(
            asset_id,
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
