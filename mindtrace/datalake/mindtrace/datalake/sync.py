from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError
from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.replication import ReplicationManager
from mindtrace.datalake.sync_types import (
    DatasetSyncBundle,
    DatasetSyncCommitResult,
    DatasetSyncImportPlan,
    DatasetSyncImportRequest,
    DatasetSyncPayloadPlan,
    DatasetSyncProgress,
    ObjectPayloadDescriptor,
)
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    DatasetVersion,
    Datum,
    StorageRef,
    utc_now,
)

_METADATA_ONLY_CROSS_LAKE = (
    "transfer_policy='metadata_only' is only supported when source and target are the same AsyncDatalake instance. "
    "For cross-lake imports, materialize payloads first (for example copy_if_missing) so asset StorageRefs "
    "resolve on the target store."
)
_logger = logging.getLogger(__name__)
ProgressCallback = Callable[[DatasetSyncProgress], Awaitable[None] | None]


def _storage_refs_equivalent(a: StorageRef, b: StorageRef) -> bool:
    av = a.version if a.version is not None else "latest"
    bv = b.version if b.version is not None else "latest"
    return a.mount == b.mount and a.name == b.name and av == bv


def _apply_mount_map_to_storage_ref(storage_ref: StorageRef, mount_map: dict[str, str]) -> StorageRef:
    if not mount_map:
        return storage_ref
    mapped = mount_map.get(storage_ref.mount)
    if mapped is None:
        return storage_ref
    return StorageRef(mount=mapped, name=storage_ref.name, version=storage_ref.version)


def _head_object_size_bytes(meta: dict[str, Any]) -> int | None:
    for key in ("size_bytes", "size", "content_length", "ContentLength"):
        val = meta.get(key)
        if val is None:
            continue
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


def _head_object_checksum(meta: dict[str, Any]) -> str | None:
    for key in ("checksum", "sha256", "etag", "ETag"):
        val = meta.get(key)
        if isinstance(val, str) and val:
            return val.strip('\"')
    metadata = meta.get("metadata")
    if isinstance(metadata, dict):
        for key in ("checksum", "sha256", "etag", "ETag"):
            val = metadata.get(key)
            if isinstance(val, str) and val:
                return val.strip('\"')
    return None


def _chunked[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _commit_import_phase_item_count(bundle: DatasetSyncBundle) -> int:
    """Units for granular ``committing`` progress: each bundle row examined plus dataset version."""

    return (
        len(bundle.annotation_schemas)
        + len(bundle.assets)
        + len(bundle.annotation_records)
        + len(bundle.annotation_sets)
        + len(bundle.datums)
        + 1
    )


def collect_bundle_mount_names(bundle: DatasetSyncBundle) -> set[str]:
    """Unique ``storage_ref.mount`` values from bundled assets and payload descriptors."""
    mounts: set[str] = set()
    for asset in bundle.assets:
        mounts.add(asset.storage_ref.mount)
    for payload in bundle.payloads:
        mounts.add(payload.storage_ref.mount)
    return mounts


def validate_cross_lake_target_mount_resolution(
    target: AsyncDatalake,
    bundle: DatasetSyncBundle,
    mount_map: dict[str, str],
) -> None:
    """Raise ``ValueError`` when a bundle mount resolves to an unknown mount on ``target``.

    After ``mount_map`` is applied via :func:`_apply_mount_map_to_storage_ref`, the effective
    target-side mount must exist on ``target``. Surfaces misconfiguration earlier than opaque
    ``StoreLocationNotFound(<mount>)`` /
    ``KeyError`` during probing.
    """

    configured = frozenset(target.store.list_mount_info().keys())
    for src_mount in sorted(collect_bundle_mount_names(bundle)):
        resolved = mount_map.get(src_mount, src_mount)
        if resolved not in configured:
            raise ValueError(
                "After applying mount_map, target datalake has no store mount "
                f"{resolved!r} (configured: {sorted(configured)}) for bundle mount {src_mount!r}. "
                "Map bundle mounts to mounts that exist on the target datalake; unmapped mounts pass through "
                "when source and mount names match on both sides."
            )


class DatasetSyncManager:
    """Orchestrates export/import of a single immutable :class:`DatasetVersion` graph.

    Cross-lake imports always preserve source row identifiers today; ``preserve_ids=False`` is rejected on
    :class:`~mindtrace.datalake.sync_types.DatasetSyncImportRequest` until ID remapping is implemented.

    ``metadata_only`` skips payload bytes and keeps descriptor ``StorageRef`` values verbatim, which is only
    safe when ``source`` and ``target`` are the same lake (shared registry); cross-lake ``metadata_only``
    requests are rejected in :meth:`plan_import`.

    For cross-lake imports where source and target use different mount names, pass ``mount_map`` on
    :class:`~mindtrace.datalake.sync_types.DatasetSyncImportRequest` (source mount → target mount). Object
    existence checks, upload sessions, skipped-transfer refs, and assets without payload descriptors all
    use the mapped target coordinates; bytes are still read from the **source** using the original ref.
    """

    def __init__(self, source: AsyncDatalake, target: AsyncDatalake | None = None) -> None:
        self.source = source
        self.target = target or source

    @staticmethod
    def map_storage_ref_for_target(storage_ref: StorageRef, mount_map: dict[str, str]) -> StorageRef:
        """Return ``storage_ref`` with ``mount`` rewritten via ``mount_map`` when the source mount is listed."""
        return _apply_mount_map_to_storage_ref(storage_ref, mount_map)

    async def export_dataset_version(self, dataset_name: str, version: str) -> DatasetSyncBundle:
        dataset_version = await self.source.get_dataset_version(dataset_name, version)

        datums: dict[str, Datum] = {}
        assets: dict[str, Asset] = {}
        annotation_sets: dict[str, AnnotationSet] = {}
        annotation_records: dict[str, AnnotationRecord] = {}
        annotation_schemas: dict[str, AnnotationSchema] = {}

        for datum_id in dataset_version.manifest:
            datum = await self.source.get_datum(datum_id)
            datums[datum.datum_id] = datum
            for asset_id in datum.asset_refs.values():
                asset = await self.source.get_asset(asset_id)
                assets[asset.asset_id] = asset
            for annotation_set_id in datum.annotation_set_ids:
                annotation_set = await self.source.get_annotation_set(annotation_set_id)
                annotation_sets[annotation_set.annotation_set_id] = annotation_set
                if annotation_set.annotation_schema_id:
                    schema = await self.source.get_annotation_schema(annotation_set.annotation_schema_id)
                    annotation_schemas[schema.annotation_schema_id] = schema
                for annotation_id in annotation_set.annotation_record_ids:
                    record = await self.source.get_annotation_record(annotation_id)
                    annotation_records[record.annotation_id] = record

        payloads = [
            ObjectPayloadDescriptor(
                asset_id=asset.asset_id,
                storage_ref=asset.payload_storage_ref or asset.storage_ref,
                media_type=asset.media_type,
                size_bytes=asset.payload_size_bytes if asset.payload_size_bytes is not None else asset.size_bytes,
                checksum=asset.payload_checksum if asset.payload_checksum is not None else asset.checksum,
                content_type=asset.media_type,
                metadata={
                    **dict(asset.metadata or {}),
                    "payload_status": asset.payload_status,
                    "payload_status_reason": asset.payload_status_reason,
                },
            )
            for asset in assets.values()
        ]

        return DatasetSyncBundle(
            dataset_version=dataset_version,
            datums=list(datums.values()),
            assets=list(assets.values()),
            annotation_sets=list(annotation_sets.values()),
            annotation_records=list(annotation_records.values()),
            annotation_schemas=list(annotation_schemas.values()),
            payloads=payloads,
            metadata={
                "source_dataset_version_id": dataset_version.dataset_version_id,
                "dataset_name": dataset_version.dataset_name,
                "version": dataset_version.version,
            },
        )

    async def plan_import(
        self,
        request: DatasetSyncImportRequest,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> DatasetSyncImportPlan:
        if request.transfer_policy == "metadata_only" and self.source is not self.target:
            raise ValueError(_METADATA_ONLY_CROSS_LAKE)

        bundle = request.bundle
        mount_map = request.mount_map
        validate_cross_lake_target_mount_resolution(self.target, bundle, mount_map)
        greenfield_skip = (
            request.transfer_policy == "copy_if_missing"
            and request.greenfield_skip_target_object_probes
            and await self._get_existing_dataset_version(
                bundle.dataset_version.dataset_name, bundle.dataset_version.version
            )
            is None
        )
        payload_plans: list[DatasetSyncPayloadPlan] = []

        payloads = bundle.payloads
        total_payloads = len(payloads)
        total_payload_bytes = sum(payload.size_bytes or 0 for payload in payloads)
        planned_payload_bytes = 0
        batches = _chunked(payloads, request.planning_batch_size)
        total_batches = len(batches)
        semaphore = asyncio.Semaphore(request.planning_concurrency)
        for batch_index, batch in enumerate(batches, start=1):
            batch_start = (batch_index - 1) * request.planning_batch_size
            _logger.info(
                "Planning dataset import batch %s/%s (%s/%s payloads checked)",
                batch_index,
                total_batches,
                batch_start,
                total_payloads,
            )
            batch_plans = await asyncio.gather(
                *[
                    self._plan_payload(
                        payload,
                        transfer_policy=request.transfer_policy,
                        mount_map=mount_map,
                        semaphore=semaphore,
                        skip_target_probe=greenfield_skip,
                        match_policy=request.target_object_match_policy,
                    )
                    for payload in batch
                ]
            )
            payload_plans.extend(batch_plans)

            completed_items = min(batch_index * request.planning_batch_size, total_payloads)
            planned_payload_bytes += sum(payload.size_bytes or 0 for payload in batch)
            progress = DatasetSyncProgress(
                phase="planning",
                batch_index=batch_index,
                total_batches=total_batches,
                completed_items=completed_items,
                total_items=total_payloads,
                message=f"Planning import batch {batch_index}/{total_batches}",
                bytes_completed=planned_payload_bytes,
                bytes_total=total_payload_bytes,
            )
            _logger.info(
                "%s: checked %s/%s payloads",
                progress.message,
                progress.completed_items,
                progress.total_items,
            )
            await self._emit_progress(progress_callback, progress)

        missing_payload_count = sum(1 for plan in payload_plans if not plan.target_exists)
        transfer_required_count = sum(1 for plan in payload_plans if plan.transfer_required)
        transfer_required_bytes = sum(
            payload.size_bytes or 0
            for payload, row in zip(payloads, payload_plans, strict=True)
            if row.transfer_required
        )
        embedded_blocked = False
        if self.source is self.target:
            for payload, row in zip(payloads, payload_plans, strict=True):
                if row.transfer_required:
                    target_mount = _apply_mount_map_to_storage_ref(payload.storage_ref, mount_map).mount
                    if not self.target.store.has_mount(target_mount):
                        embedded_blocked = True
                        break
        if request.target_metadata_commit:
            # Phase A: caller will stage bytes; target must not be gated on reading bundle source mount names.
            embedded_blocked = False
        if request.transfer_policy == "metadata_only":
            ready_to_commit = True
        elif request.transfer_policy == "fail_if_missing_payload":
            ready_to_commit = missing_payload_count == 0
        else:
            ready_to_commit = True
        if embedded_blocked:
            ready_to_commit = False

        return DatasetSyncImportPlan(
            dataset_name=bundle.dataset_version.dataset_name,
            version=bundle.dataset_version.version,
            transfer_policy=request.transfer_policy,
            payloads=payload_plans,
            missing_payload_count=missing_payload_count,
            transfer_required_count=transfer_required_count,
            ready_to_commit=ready_to_commit,
            total_payload_bytes=total_payload_bytes,
            transfer_required_bytes=transfer_required_bytes,
        )

    @staticmethod
    def _staged_covers_required_transfers(
        plan: DatasetSyncImportPlan,
        staged: dict[str, StorageRef],
    ) -> bool:
        for row in plan.payloads:
            if row.transfer_required and row.asset_id not in staged:
                return False
        return True

    async def _plan_payload(
        self,
        payload: ObjectPayloadDescriptor,
        *,
        transfer_policy: str,
        mount_map: dict[str, str],
        semaphore: asyncio.Semaphore,
        skip_target_probe: bool = False,
        match_policy: str = "exists",
    ) -> DatasetSyncPayloadPlan:
        del semaphore, skip_target_probe, match_policy
        target_storage_ref = _apply_mount_map_to_storage_ref(payload.storage_ref, mount_map)
        if transfer_policy == "copy":
            return DatasetSyncPayloadPlan(
                asset_id=payload.asset_id,
                source_storage_ref=payload.storage_ref,
                target_storage_ref=target_storage_ref,
                target_exists=False,
                transfer_required=True,
                reason="policy_copy",
            )

        target_asset = await self._get_existing_asset(payload.asset_id)
        payload_checksum = payload.checksum
        payload_size = payload.size_bytes
        status = getattr(target_asset, "payload_status", None) if target_asset is not None else None
        target_payload_ref = None
        if target_asset is not None:
            target_payload_ref = target_asset.payload_storage_ref or target_asset.storage_ref

        db_says_present = (
            target_asset is not None
            and status == "present"
            and (payload_checksum is None or target_asset.payload_checksum == payload_checksum or target_asset.checksum == payload_checksum)
            and (payload_size is None or target_asset.payload_size_bytes == payload_size or target_asset.size_bytes == payload_size)
            and target_payload_ref is not None
            and _storage_refs_equivalent(target_payload_ref, target_storage_ref)
        )

        if transfer_policy == "copy_if_missing":
            transfer_required = not db_says_present
            if target_asset is None:
                reason = "missing_asset_in_db"
            elif db_says_present:
                reason = "db_payload_present"
            else:
                reason = f"db_payload_status_{status or 'unknown'}"
        elif transfer_policy == "metadata_only":
            transfer_required = False
            reason = "metadata_only"
        elif transfer_policy == "fail_if_missing_payload":
            transfer_required = False
            reason = "db_payload_present" if db_says_present else "missing_payload"
        else:
            raise ValueError(f"Unsupported transfer policy: {transfer_policy}")

        return DatasetSyncPayloadPlan(
            asset_id=payload.asset_id,
            source_storage_ref=payload.storage_ref,
            target_storage_ref=target_storage_ref,
            target_exists=db_says_present,
            transfer_required=transfer_required,
            reason=reason,
        )

    async def _get_existing_asset(self, asset_id: str) -> Asset | None:
        try:
            return await self.target.get_asset(asset_id)
        except DocumentNotFoundError:
            return None

    @staticmethod
    async def _emit_progress(
        progress_callback: ProgressCallback | None,
        progress: DatasetSyncProgress,
    ) -> None:
        if progress_callback is None:
            return
        result = progress_callback(progress)
        if result is not None:
            await result

    async def sync_dataset_version(
        self,
        dataset_name: str,
        version: str,
        *,
        transfer_policy: str = "copy_if_missing",
        origin_lake_id: str | None = None,
        preserve_ids: bool = True,
        mount_map: dict[str, str] | None = None,
    ) -> DatasetSyncCommitResult:
        bundle = await self.export_dataset_version(dataset_name, version)
        return await self.commit_import(
            DatasetSyncImportRequest(
                bundle=bundle,
                transfer_policy=transfer_policy,
                origin_lake_id=origin_lake_id,
                preserve_ids=preserve_ids,
                mount_map=mount_map or {},
            )
        )

    async def commit_import(
        self,
        request: DatasetSyncImportRequest,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> DatasetSyncCommitResult:
        plan = await self.plan_import(request, progress_callback=progress_callback)
        if request.metadata_first:
            if self.source is self.target:
                raise ValueError("metadata_first=True requires distinct source and target AsyncDatalake instances.")
            if request.staged_payload_storage_refs is not None:
                raise ValueError(
                    "metadata_first cannot be combined with staged_payload_storage_refs on the same request."
                )
        if request.target_metadata_commit:
            if self.source is not self.target:
                raise ValueError(
                    "target_metadata_commit=True commits pending payloads on one lake only "
                    "(source and target AsyncDatalake instances must be the same)."
                )
            if request.staged_payload_storage_refs is not None:
                raise ValueError(
                    "target_metadata_commit cannot be combined with staged_payload_storage_refs on the same request."
                )
        staged = request.staged_payload_storage_refs
        if staged is not None and not request.metadata_first and not request.target_metadata_commit:
            if not self._staged_covers_required_transfers(plan, staged):
                raise ValueError(
                    "staged_payload_storage_refs must include a StorageRef for every import-plan payload with "
                    "transfer_required=True."
                )

        if not plan.ready_to_commit:
            if request.transfer_policy == "fail_if_missing_payload":
                raise ValueError(
                    f"Import plan for {plan.dataset_name}@{plan.version} is not ready to commit under policy "
                    f"{plan.transfer_policy}"
                )
            if staged is None:
                raise ValueError(
                    "Import plan is not ready to commit without caller-staged payload bytes. Use "
                    "dataset_versions.import_session_start, import_session_upload_payload, and "
                    "import_session_commit when this datalake cannot read the bundle's original StorageRef mounts."
                )

        bundle = request.bundle
        origin_lake_id = request.origin_lake_id or self.source.mongo_db_name
        mount_map = request.mount_map
        payload_by_asset_id = {payload.asset_id: payload for payload in bundle.payloads}
        plan_by_asset_id = {plan.asset_id: plan for plan in plan.payloads}

        replication_manager: ReplicationManager | None = None
        if request.metadata_first:
            replication_manager = ReplicationManager(self.source, self.target)
        elif request.target_metadata_commit:
            replication_manager = ReplicationManager(self.target)

        defer_inline_transfers = request.metadata_first or request.target_metadata_commit

        resolved_storage_refs, transferred_payloads, skipped_payloads = await self._resolve_payload_transfers(
            bundle.assets,
            payload_by_asset_id=payload_by_asset_id,
            plan_by_asset_id=plan_by_asset_id,
            request=request,
            progress_callback=progress_callback,
            defer_inline_transfers=defer_inline_transfers,
        )

        commit_phase_total = _commit_import_phase_item_count(bundle)
        commit_done = 0
        last_commit_progress_mono = 0.0

        existing_dataset_version = await self._get_existing_dataset_version(
            bundle.dataset_version.dataset_name, bundle.dataset_version.version
        )
        greenfield_metadata = (
            request.greenfield_skip_target_metadata_probes and existing_dataset_version is None
        )
        existing_annotation_schema_ids = await self._prefetch_existing_annotation_schema_ids(
            [schema.annotation_schema_id for schema in bundle.annotation_schemas],
            skip_lookup=greenfield_metadata,
        )
        existing_asset_ids = await self._prefetch_existing_asset_ids(
            [asset.asset_id for asset in bundle.assets],
            skip_lookup=greenfield_metadata,
        )
        existing_annotation_record_ids = await self._prefetch_existing_annotation_record_ids(
            [record.annotation_id for record in bundle.annotation_records],
            skip_lookup=greenfield_metadata,
        )
        existing_annotation_set_ids = await self._prefetch_existing_annotation_set_ids(
            [annotation_set.annotation_set_id for annotation_set in bundle.annotation_sets],
            skip_lookup=greenfield_metadata,
        )
        existing_datum_ids = await self._prefetch_existing_datum_ids(
            [datum.datum_id for datum in bundle.datums],
            skip_lookup=greenfield_metadata,
        )

        async def emit_commit_progress(
            *,
            entity_kind: str,
            message: str,
            entity_completed_items: int,
            entity_total_items: int,
            force: bool = False,
        ) -> None:
            nonlocal last_commit_progress_mono
            now_mono = time.monotonic()
            should_emit = force
            if not should_emit:
                if commit_done == 0:
                    should_emit = True
                elif commit_done == commit_phase_total:
                    should_emit = True
                elif commit_done % request.commit_progress_every_items == 0:
                    should_emit = True
                elif (now_mono - last_commit_progress_mono) >= request.commit_progress_every_seconds:
                    should_emit = True
            if not should_emit:
                return
            await self._emit_progress(
                progress_callback,
                DatasetSyncProgress(
                    phase="committing",
                    completed_items=commit_done,
                    total_items=commit_phase_total,
                    message=message,
                    entity_kind=entity_kind,
                    entity_completed_items=entity_completed_items,
                    entity_total_items=entity_total_items,
                    phase_detail=entity_kind,
                ),
            )
            last_commit_progress_mono = now_mono

        await emit_commit_progress(
            entity_kind="metadata",
            message="Persisting import metadata",
            entity_completed_items=0,
            entity_total_items=commit_phase_total,
            force=True,
        )

        created_annotation_schemas = 0
        processed_annotation_schemas = 0
        for schema in bundle.annotation_schemas:
            try:
                if schema.annotation_schema_id in existing_annotation_schema_ids:
                    continue
                created = AnnotationSchema.model_validate(
                    {
                        **schema.model_dump(),
                        "metadata": self._merge_origin_metadata(
                            schema.metadata,
                            lake_id=origin_lake_id,
                            bundle=bundle,
                            entity_id=schema.annotation_schema_id,
                            annotation_schema_id=schema.annotation_schema_id,
                        ),
                    }
                )
                try:
                    await self.target.annotation_schema_database.insert(created)
                    created_annotation_schemas += 1
                    existing_annotation_schema_ids.add(schema.annotation_schema_id)
                except DuplicateInsertError:
                    existing_annotation_schema_ids.add(schema.annotation_schema_id)
            finally:
                processed_annotation_schemas += 1
                commit_done += 1
                await emit_commit_progress(
                    entity_kind="annotation_schema",
                    message="Persisting annotation schemas",
                    entity_completed_items=processed_annotation_schemas,
                    entity_total_items=len(bundle.annotation_schemas),
                )

        created_assets = 0
        processed_assets = 0
        inserted_assets: list[Asset] = []
        for asset in bundle.assets:
            try:
                storage_ref = _apply_mount_map_to_storage_ref(
                    resolved_storage_refs.get(asset.asset_id, asset.storage_ref),
                    mount_map,
                )
                merged_origin = self._merge_origin_metadata(
                    asset.metadata,
                    lake_id=origin_lake_id,
                    bundle=bundle,
                    entity_id=asset.asset_id,
                    asset_id=asset.asset_id,
                )
                payload_status = "present"
                payload_status_reason = None
                payload_verified_at = utc_now()
                if replication_manager is not None:
                    merged_origin = replication_manager.build_asset_replication_metadata(
                        merged_origin,
                        origin_lake_id=origin_lake_id,
                        origin_asset_id=asset.asset_id,
                        replication_mode="metadata_first",
                        payload_status="missing",
                    )
                    payload_status = "missing"
                    payload_status_reason = "metadata_first_pending_payload"
                    payload_verified_at = None
                created = Asset.model_validate(
                    {
                        **asset.model_dump(),
                        "storage_ref": storage_ref.model_dump(),
                        "payload_status": payload_status,
                        "payload_status_updated_at": utc_now(),
                        "payload_status_reason": payload_status_reason,
                        "payload_storage_ref": storage_ref.model_dump(),
                        "payload_checksum": asset.checksum,
                        "payload_size_bytes": asset.size_bytes,
                        "payload_verified_at": payload_verified_at,
                        "metadata": merged_origin,
                    }
                )
                if self.source is self.target:
                    if asset.asset_id in existing_asset_ids:
                        continue
                    try:
                        await self.target.asset_database.insert(created)
                        inserted_assets.append(created)
                        created_assets += 1
                        existing_asset_ids.add(asset.asset_id)
                    except DuplicateInsertError:
                        existing_asset_ids.add(asset.asset_id)
                    continue

                if asset.asset_id in existing_asset_ids:
                    existing = await self.target.get_asset(asset.asset_id)
                    if _storage_refs_equivalent(existing.storage_ref, created.storage_ref):
                        continue
                    await self._refresh_target_asset_for_cross_lake_import(created)
                    continue

                try:
                    await self.target.asset_database.insert(created)
                    inserted_assets.append(created)
                    created_assets += 1
                    existing_asset_ids.add(asset.asset_id)
                except DuplicateInsertError:
                    existing_asset_ids.add(asset.asset_id)
                    await self._refresh_target_asset_for_cross_lake_import(created)
            finally:
                processed_assets += 1
                commit_done += 1
                await emit_commit_progress(
                    entity_kind="asset",
                    message="Persisting assets",
                    entity_completed_items=processed_assets,
                    entity_total_items=len(bundle.assets),
                )

        if inserted_assets:
            await self.target.ensure_primary_asset_aliases(inserted_assets)

        created_annotation_records = 0
        processed_annotation_records = 0
        for record in bundle.annotation_records:
            try:
                if record.annotation_id in existing_annotation_record_ids:
                    continue
                created = AnnotationRecord.model_validate(
                    {
                        **record.model_dump(),
                        "metadata": self._merge_origin_metadata(
                            record.metadata,
                            lake_id=origin_lake_id,
                            bundle=bundle,
                            entity_id=record.annotation_id,
                            annotation_id=record.annotation_id,
                        ),
                    }
                )
                try:
                    await self.target.annotation_record_database.insert(created)
                    created_annotation_records += 1
                    existing_annotation_record_ids.add(record.annotation_id)
                except DuplicateInsertError:
                    existing_annotation_record_ids.add(record.annotation_id)
            finally:
                processed_annotation_records += 1
                commit_done += 1
                await emit_commit_progress(
                    entity_kind="annotation_record",
                    message="Persisting annotation records",
                    entity_completed_items=processed_annotation_records,
                    entity_total_items=len(bundle.annotation_records),
                )

        created_annotation_sets = 0
        processed_annotation_sets = 0
        for annotation_set in bundle.annotation_sets:
            try:
                if annotation_set.annotation_set_id in existing_annotation_set_ids:
                    continue
                created = AnnotationSet.model_validate(
                    {
                        **annotation_set.model_dump(),
                        "metadata": self._merge_origin_metadata(
                            annotation_set.metadata,
                            lake_id=origin_lake_id,
                            bundle=bundle,
                            entity_id=annotation_set.annotation_set_id,
                            annotation_set_id=annotation_set.annotation_set_id,
                        ),
                    }
                )
                try:
                    await self.target.annotation_set_database.insert(created)
                    created_annotation_sets += 1
                    existing_annotation_set_ids.add(annotation_set.annotation_set_id)
                except DuplicateInsertError:
                    existing_annotation_set_ids.add(annotation_set.annotation_set_id)
            finally:
                processed_annotation_sets += 1
                commit_done += 1
                await emit_commit_progress(
                    entity_kind="annotation_set",
                    message="Persisting annotation sets",
                    entity_completed_items=processed_annotation_sets,
                    entity_total_items=len(bundle.annotation_sets),
                )

        created_datums = 0
        processed_datums = 0
        for datum in bundle.datums:
            try:
                if datum.datum_id in existing_datum_ids:
                    continue
                mapped_asset_refs = {role: asset_id for role, asset_id in datum.asset_refs.items()}
                created = Datum.model_validate(
                    {
                        **datum.model_dump(),
                        "asset_refs": mapped_asset_refs,
                        "metadata": self._merge_origin_metadata(
                            datum.metadata,
                            lake_id=origin_lake_id,
                            bundle=bundle,
                            entity_id=datum.datum_id,
                            datum_id=datum.datum_id,
                        ),
                    }
                )
                try:
                    await self.target.datum_database.insert(created)
                    created_datums += 1
                    existing_datum_ids.add(datum.datum_id)
                except DuplicateInsertError:
                    existing_datum_ids.add(datum.datum_id)
            finally:
                processed_datums += 1
                commit_done += 1
                await emit_commit_progress(
                    entity_kind="datum",
                    message="Persisting datums",
                    entity_completed_items=processed_datums,
                    entity_total_items=len(bundle.datums),
                )

        if existing_dataset_version is None:
            dataset_version = DatasetVersion.model_validate(
                {
                    **bundle.dataset_version.model_dump(),
                    "metadata": self._merge_origin_metadata(
                        bundle.dataset_version.metadata,
                        lake_id=origin_lake_id,
                        bundle=bundle,
                        entity_id=bundle.dataset_version.dataset_version_id,
                    ),
                }
            )
            dataset_version = await self.target.dataset_version_database.insert(dataset_version)
        else:
            dataset_version = existing_dataset_version
        commit_done += 1
        await emit_commit_progress(
            entity_kind="dataset_version",
            message="Persisting dataset version",
            entity_completed_items=1,
            entity_total_items=1,
            force=True,
        )

        result = DatasetSyncCommitResult(
            dataset_version=dataset_version,
            created_assets=created_assets,
            created_annotation_schemas=created_annotation_schemas,
            created_annotation_records=created_annotation_records,
            created_annotation_sets=created_annotation_sets,
            created_datums=created_datums,
            transferred_payloads=transferred_payloads,
            skipped_payloads=skipped_payloads,
        )
        await self._emit_progress(
            progress_callback,
            DatasetSyncProgress(
                phase="complete",
                completed_items=commit_phase_total,
                total_items=commit_phase_total,
                message=f"Completed dataset import {result.dataset_version.dataset_name}@{result.dataset_version.version}",
                entity_kind="dataset_version",
                entity_completed_items=1,
                entity_total_items=1,
                bytes_completed=plan.transfer_required_bytes,
                bytes_total=plan.transfer_required_bytes,
                skipped_items=skipped_payloads,
            ),
        )
        return result

    async def finalize_pending_import_asset_payload(
        self,
        *,
        asset_id: str,
        payload_descriptor: ObjectPayloadDescriptor,
        staged_storage_ref: StorageRef,
        payload_bytes: bytes,
    ) -> Asset:
        """After caller-staged bytes land on the target store, verify and mark the asset payload verified.

        Used with :data:`DatasetSyncImportRequest.target_metadata_commit` imports (e.g. ``import_session_*`` flow)
        where Phase A committed graph rows with pending replication state.
        """

        await self._verify_transferred_payload(payload_descriptor, payload_bytes, staged_storage_ref)
        asset = await self.target.get_asset(asset_id)
        now = utc_now()
        asset.storage_ref = staged_storage_ref
        asset.size_bytes = len(payload_bytes)
        if payload_descriptor.checksum:
            asset.checksum = payload_descriptor.checksum
        asset.payload_status = "present"
        asset.payload_status_updated_at = now
        asset.payload_status_reason = None
        asset.payload_storage_ref = staged_storage_ref
        asset.payload_size_bytes = len(payload_bytes)
        asset.payload_checksum = payload_descriptor.checksum or asset.checksum
        asset.payload_verified_at = now
        asset.media_type = payload_descriptor.media_type or asset.media_type
        asset.updated_at = now
        rm = ReplicationManager(self.target)
        await rm._set_asset_replication_state(
            asset,
            payload_status="present",
            payload_verified_at=utc_now(),
            payload_last_error=None,
        )
        return await self.target.get_asset(asset_id)

    async def _target_payload_matches(
        self,
        payload: ObjectPayloadDescriptor,
        target_storage_ref: StorageRef,
        *,
        match_policy: str,
    ) -> tuple[bool, str]:
        exists = await self.target.object_exists(target_storage_ref)
        if not exists:
            return False, "missing_on_target"
        if match_policy == "exists":
            return True, "already_present"

        meta = await self.target.head_object(target_storage_ref)
        if match_policy in {"size", "checksum"} and payload.size_bytes is not None:
            target_size = _head_object_size_bytes(meta)
            if target_size is None or target_size != payload.size_bytes:
                return False, "size_mismatch"
            if match_policy == "size":
                return True, "already_present_size_match"

        if match_policy == "checksum" and payload.checksum:
            target_checksum = _head_object_checksum(meta)
            if not target_checksum or target_checksum != payload.checksum:
                return False, "checksum_mismatch"
            return True, "already_present_checksum_match"

        return True, "already_present"

    async def _prefetch_existing_ids(
        self,
        database: Any,
        field: str,
        ids: Sequence[str],
        *,
        skip_lookup: bool = False,
    ) -> set[str]:
        if skip_lookup or not ids:
            return set()
        rows = await database.find({field: {"$in": list(dict.fromkeys(ids))}})
        found: set[str] = set()
        for row in rows:
            value = getattr(row, field, None)
            if isinstance(value, str):
                found.add(value)
        return found

    async def _prefetch_existing_asset_ids(self, asset_ids: Sequence[str], *, skip_lookup: bool = False) -> set[str]:
        return await self._prefetch_existing_ids(
            self.target.asset_database,
            "asset_id",
            asset_ids,
            skip_lookup=skip_lookup,
        )

    async def _prefetch_existing_annotation_schema_ids(
        self,
        annotation_schema_ids: Sequence[str],
        *,
        skip_lookup: bool = False,
    ) -> set[str]:
        return await self._prefetch_existing_ids(
            self.target.annotation_schema_database,
            "annotation_schema_id",
            annotation_schema_ids,
            skip_lookup=skip_lookup,
        )

    async def _prefetch_existing_annotation_record_ids(
        self,
        annotation_ids: Sequence[str],
        *,
        skip_lookup: bool = False,
    ) -> set[str]:
        return await self._prefetch_existing_ids(
            self.target.annotation_record_database,
            "annotation_id",
            annotation_ids,
            skip_lookup=skip_lookup,
        )

    async def _prefetch_existing_annotation_set_ids(
        self,
        annotation_set_ids: Sequence[str],
        *,
        skip_lookup: bool = False,
    ) -> set[str]:
        return await self._prefetch_existing_ids(
            self.target.annotation_set_database,
            "annotation_set_id",
            annotation_set_ids,
            skip_lookup=skip_lookup,
        )

    async def _prefetch_existing_datum_ids(self, datum_ids: Sequence[str], *, skip_lookup: bool = False) -> set[str]:
        return await self._prefetch_existing_ids(
            self.target.datum_database,
            "datum_id",
            datum_ids,
            skip_lookup=skip_lookup,
        )

    async def _resolve_payload_transfers(
        self,
        assets: Sequence[Asset],
        *,
        payload_by_asset_id: dict[str, ObjectPayloadDescriptor],
        plan_by_asset_id: dict[str, DatasetSyncPayloadPlan],
        request: DatasetSyncImportRequest,
        progress_callback: ProgressCallback | None,
        defer_inline_transfers: bool = False,
    ) -> tuple[dict[str, StorageRef], int, int]:
        mount_map = request.mount_map
        resolved_storage_refs: dict[str, StorageRef] = {}

        if defer_inline_transfers:
            for asset in assets:
                payload = payload_by_asset_id.get(asset.asset_id)
                if payload is not None:
                    resolved_storage_refs[asset.asset_id] = self.map_storage_ref_for_target(
                        payload.storage_ref, mount_map
                    )
                else:
                    resolved_storage_refs[asset.asset_id] = self.map_storage_ref_for_target(
                        asset.storage_ref, mount_map
                    )
            pending = sum(1 for a in assets if payload_by_asset_id.get(a.asset_id) is not None)
            pending_bytes = sum(
                (payload_by_asset_id[a.asset_id].size_bytes or 0)
                for a in assets
                if payload_by_asset_id.get(a.asset_id) is not None
            )
            if pending:
                await self._emit_progress(
                    progress_callback,
                    DatasetSyncProgress(
                        phase="transferring",
                        completed_items=0,
                        total_items=pending,
                        message="Payload transfer deferred; metadata-first import marked payloads pending",
                        bytes_completed=0,
                        bytes_total=pending_bytes,
                        phase_detail="deferred",
                    ),
                )
            return resolved_storage_refs, 0, pending

        transfer_items: list[tuple[ObjectPayloadDescriptor, DatasetSyncPayloadPlan]] = []

        for asset in assets:
            payload = payload_by_asset_id.get(asset.asset_id)
            asset_plan = plan_by_asset_id.get(asset.asset_id)
            if payload is None or asset_plan is None:
                resolved_storage_refs[asset.asset_id] = _apply_mount_map_to_storage_ref(asset.storage_ref, mount_map)
                continue
            transfer_items.append((payload, asset_plan))

        total_payload_items = len(transfer_items)
        if total_payload_items == 0:
            return resolved_storage_refs, 0, 0

        total_payload_bytes = sum((payload.size_bytes or 0) for payload, row in transfer_items if row.transfer_required)
        transferred_payloads = 0
        skipped_payloads = 0
        processed_payload_items = 0
        processed_payload_bytes = 0
        batches = _chunked(transfer_items, request.transfer_batch_size)
        total_transfer_batches = len(batches)
        semaphore = asyncio.Semaphore(request.transfer_concurrency)
        transfer_started_mono = time.monotonic()

        for batch_index, batch in enumerate(batches, start=1):
            batch_results = await asyncio.gather(
                *[
                    self._resolve_payload_transfer_item(
                        payload,
                        asset_plan,
                        transfer_policy=request.transfer_policy,
                        mount_map=mount_map,
                        semaphore=semaphore,
                        request=request,
                    )
                    for payload, asset_plan in batch
                ]
            )
            for payload, (asset_id, storage_ref, transferred) in zip(batch, batch_results, strict=True):
                payload_desc, _asset_plan = payload
                resolved_storage_refs[asset_id] = storage_ref
                if transferred:
                    transferred_payloads += 1
                    processed_payload_bytes += payload_desc.size_bytes or 0
                else:
                    skipped_payloads += 1

            processed_payload_items += len(batch)
            elapsed = max(time.monotonic() - transfer_started_mono, 1e-9)
            progress = DatasetSyncProgress(
                phase="transferring",
                batch_index=batch_index,
                total_batches=total_transfer_batches,
                completed_items=processed_payload_items,
                total_items=total_payload_items,
                message=f"Transferring import payload batch {batch_index}/{total_transfer_batches}",
                bytes_completed=processed_payload_bytes,
                bytes_total=total_payload_bytes,
                skipped_items=skipped_payloads,
                items_per_second=processed_payload_items / elapsed,
                bytes_per_second=processed_payload_bytes / elapsed,
            )
            _logger.info(
                "%s: processed %s/%s payloads",
                progress.message,
                progress.completed_items,
                progress.total_items,
            )
            await self._emit_progress(progress_callback, progress)

        return resolved_storage_refs, transferred_payloads, skipped_payloads

    async def _resolve_payload_transfer_item(
        self,
        payload: ObjectPayloadDescriptor,
        asset_plan: DatasetSyncPayloadPlan,
        *,
        transfer_policy: str,
        mount_map: dict[str, str],
        semaphore: asyncio.Semaphore,
        request: DatasetSyncImportRequest,
    ) -> tuple[str, StorageRef, bool]:
        staged = request.staged_payload_storage_refs
        if staged is not None and payload.asset_id in staged:
            return payload.asset_id, staged[payload.asset_id], True

        if transfer_policy == "metadata_only" or not asset_plan.transfer_required:
            return payload.asset_id, _apply_mount_map_to_storage_ref(payload.storage_ref, mount_map), False

        async with semaphore:
            if self.source is self.target and not self.source.store.has_mount(payload.storage_ref.mount):
                raise ValueError(
                    "Cannot read payload bytes on this datalake: bundle StorageRef mount "
                    f"{payload.storage_ref.mount!r} is not configured. "
                    "Use caller-orchestrated import (dataset_versions.import_session_start, "
                    "import_session_upload_payload, import_session_commit) when importing bundles whose "
                    "original object mounts are not available in this process."
                )
            storage_ref = await self._transfer_payload(payload, mount_map)
        return payload.asset_id, storage_ref, True

    async def ingest_import_payload_bytes(
        self,
        payload: ObjectPayloadDescriptor,
        mount_map: dict[str, str],
        data: bytes,
    ) -> StorageRef:
        """Write pre-read payload bytes to the target store (same logic as :meth:`_transfer_payload`).

        Used by import-session upload APIs so callers read from the origin lake and the target only ever
        opens its own mounts.
        """
        if payload.size_bytes is not None and len(data) != payload.size_bytes:
            raise ValueError(
                f"Payload byte size mismatch for asset {payload.asset_id}: "
                f"descriptor declares {payload.size_bytes} bytes, received {len(data)}"
            )
        return await self._finalize_payload_write(payload, mount_map, data)

    async def _transfer_payload(self, payload: ObjectPayloadDescriptor, mount_map: dict[str, str]) -> StorageRef:
        data = await self.source.get_object(payload.storage_ref)
        if payload.size_bytes is not None and len(data) != payload.size_bytes:
            raise ValueError(
                f"Source read size mismatch for asset {payload.asset_id}: "
                f"descriptor declares {payload.size_bytes} bytes, read {len(data)}"
            )
        return await self._finalize_payload_write(payload, mount_map, data)

    async def _finalize_payload_write(
        self,
        payload: ObjectPayloadDescriptor,
        mount_map: dict[str, str],
        data: bytes,
    ) -> StorageRef:
        target_write_ref = _apply_mount_map_to_storage_ref(payload.storage_ref, mount_map)
        session = await self.target.create_object_upload_session(
            name=target_write_ref.name,
            mount=target_write_ref.mount,
            version=target_write_ref.version,
            metadata=payload.metadata,
            on_conflict="skip",
            content_type=payload.content_type
            or payload.media_type
            or self._guess_content_type(payload.storage_ref.name),
        )
        if session.upload_method == "local_path":
            if not session.upload_path:
                raise ValueError(f"Upload session {session.upload_session_id} is missing upload_path")
            upload_path = Path(session.upload_path)
            upload_path.parent.mkdir(parents=True, exist_ok=True)
            upload_path.write_bytes(data)
        elif session.upload_method == "presigned_url":
            if not session.upload_url:
                raise ValueError(f"Upload session {session.upload_session_id} is missing upload_url")
            req = urllib_request.Request(session.upload_url, data=data, method="PUT")
            for key, value in session.upload_headers.items():
                req.add_header(key, value)
            with urllib_request.urlopen(req) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Presigned upload failed with status {response.status}")
        else:
            raise ValueError(f"Unsupported upload method: {session.upload_method}")
        completed = await self.target.complete_object_upload_session(
            session.upload_session_id,
            finalize_token=session.finalize_token,
        )
        if completed.storage_ref is None:
            raise RuntimeError(f"Upload session {session.upload_session_id} did not produce a storage_ref")
        await self._verify_transferred_payload(payload, data, completed.storage_ref)
        return completed.storage_ref

    async def _refresh_target_asset_for_cross_lake_import(self, new_asset: Asset) -> None:
        """Persist payload metadata for an asset row that already exists on the target.

        When multiple ``AsyncDatalake`` instances share one Beanie database binding (last
        ``init_beanie`` wins), the source graph can appear to already exist on the target before
        import. In that case we must still align ``storage_ref`` (and related fields) with the
        target store after payload transfer.
        """
        existing = await self.target.asset_database.find({"asset_id": new_asset.asset_id})
        if not existing:
            await self.target.asset_database.insert(new_asset)
            await self.target.ensure_primary_asset_alias(new_asset)
            return
        current = existing[0]
        current.storage_ref = new_asset.storage_ref
        current.checksum = new_asset.checksum
        current.size_bytes = new_asset.size_bytes
        current.media_type = new_asset.media_type
        current.kind = new_asset.kind
        current.metadata = new_asset.metadata
        current.updated_at = new_asset.updated_at
        await self.target.asset_database.update(current)

    async def _asset_exists(self, asset_id: str) -> bool:
        try:
            await self.target.get_asset(asset_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _annotation_schema_exists(self, annotation_schema_id: str) -> bool:
        try:
            await self.target.get_annotation_schema(annotation_schema_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _annotation_record_exists(self, annotation_id: str) -> bool:
        try:
            await self.target.get_annotation_record(annotation_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _annotation_set_exists(self, annotation_set_id: str) -> bool:
        try:
            await self.target.get_annotation_set(annotation_set_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _datum_exists(self, datum_id: str) -> bool:
        try:
            await self.target.get_datum(datum_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _get_existing_dataset_version(self, dataset_name: str, version: str) -> DatasetVersion | None:
        try:
            return await self.target.get_dataset_version(dataset_name, version)
        except DocumentNotFoundError:
            return None

    def _merge_origin_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        lake_id: str,
        bundle: DatasetSyncBundle,
        entity_id: str,
        annotation_schema_id: str | None = None,
        asset_id: str | None = None,
        datum_id: str | None = None,
        annotation_set_id: str | None = None,
        annotation_id: str | None = None,
    ) -> dict[str, Any]:
        merged = dict(metadata or {})
        merged.setdefault("origin", {})
        origin = merged["origin"]
        if not isinstance(origin, dict):
            origin = {}
            merged["origin"] = origin
        dv = bundle.dataset_version
        origin.setdefault("lake_id", lake_id)
        origin.setdefault("entity_id", entity_id)
        origin.setdefault("dataset_version_id", dv.dataset_version_id)
        origin.setdefault("dataset_name", dv.dataset_name)
        origin.setdefault("version", dv.version)
        if annotation_schema_id is not None:
            origin.setdefault("annotation_schema_id", annotation_schema_id)
        if asset_id is not None:
            origin.setdefault("asset_id", asset_id)
        if datum_id is not None:
            origin.setdefault("datum_id", datum_id)
        if annotation_set_id is not None:
            origin.setdefault("annotation_set_id", annotation_set_id)
        if annotation_id is not None:
            origin.setdefault("annotation_id", annotation_id)
        return merged

    async def _verify_transferred_payload(
        self,
        payload: ObjectPayloadDescriptor,
        source_bytes: bytes,
        target_ref: StorageRef,
    ) -> None:
        head = await self.target.head_object(target_ref)
        remote_size = _head_object_size_bytes(head)
        if remote_size is not None and remote_size != len(source_bytes):
            raise RuntimeError(
                f"Post-upload size mismatch for asset {payload.asset_id}: "
                f"target head reports {remote_size} bytes, transferred {len(source_bytes)}"
            )
        if payload.checksum and not self._payload_checksum_matches(source_bytes, payload.checksum):
            raise RuntimeError(f"Post-upload checksum mismatch for asset {payload.asset_id}")

    def _payload_checksum_matches(self, data: bytes, declared: str) -> bool:
        declared_stripped = declared.strip()
        lowered = declared_stripped.lower()
        if ":" in lowered:
            algo, _, digest = lowered.partition(":")
            digest = digest.strip()
            algo = algo.strip()
            if algo == "sha256":
                return hashlib.sha256(data).hexdigest() == digest
            if algo == "md5":
                return hashlib.md5(data).hexdigest() == digest
            raise ValueError(f"Unsupported checksum algorithm in payload descriptor: {algo!r}")
        hex_body = lowered.replace("-", "")
        if len(hex_body) == 64 and set(hex_body) <= set("0123456789abcdef"):
            return hashlib.sha256(data).hexdigest() == hex_body
        if len(hex_body) == 32 and set(hex_body) <= set("0123456789abcdef"):
            return hashlib.md5(data).hexdigest() == hex_body
        raise ValueError(f"Unrecognized payload checksum format: {declared_stripped!r}")

    def _guess_content_type(self, name: str) -> str:
        guessed, _ = mimetypes.guess_type(name)
        return guessed or "application/octet-stream"
