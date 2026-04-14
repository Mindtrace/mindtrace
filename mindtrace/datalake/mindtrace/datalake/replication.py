from __future__ import annotations

from typing import Any

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.replication_types import (
    PayloadStatus,
    ReplicatedAssetState,
    ReplicationBatchRequest,
    ReplicationBatchResult,
    ReplicationStatusResult,
)
from mindtrace.datalake.types import AnnotationRecord, AnnotationSchema, AnnotationSet, Asset, Datum, StorageRef


def _apply_mount_map_to_storage_ref(storage_ref: StorageRef, mount_map: dict[str, str]) -> StorageRef:
    mapped = mount_map.get(storage_ref.mount)
    if mapped is None:
        return storage_ref
    return StorageRef(mount=mapped, name=storage_ref.name, version=storage_ref.version)


class MetadataFirstReplicationManager:
    """Metadata-first replication manager for one-way source -> target mirroring.

    MVP-A intentionally implements only the lightweight control-plane portion:

    - upsert placeholder assets on the target
    - mirror annotation schemas / sets / records / datums
    - preserve source identifiers for idempotency
    - attach explicit replication metadata showing payload availability is pending
    """

    def __init__(self, source: AsyncDatalake, target: AsyncDatalake | None = None) -> None:
        self.source = source
        self.target = target or source

    @staticmethod
    def map_storage_ref_for_target(storage_ref: StorageRef, mount_map: dict[str, str]) -> StorageRef:
        return _apply_mount_map_to_storage_ref(storage_ref, mount_map)

    @staticmethod
    def get_payload_status(asset: Asset) -> PayloadStatus | None:
        replication = (asset.metadata or {}).get("replication")
        if not isinstance(replication, dict):
            return None
        status = replication.get("payload_status")
        return status if isinstance(status, str) else None

    @staticmethod
    def is_payload_available(asset: Asset) -> bool:
        replication = (asset.metadata or {}).get("replication")
        if not isinstance(replication, dict):
            return False
        available = replication.get("payload_available")
        return bool(available)

    def build_asset_replication_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        origin_lake_id: str,
        origin_asset_id: str,
        replication_mode: str,
        payload_status: PayloadStatus = "pending",
    ) -> dict[str, Any]:
        merged = dict(metadata or {})

        origin = merged.get("origin")
        if not isinstance(origin, dict):
            origin = {}
        origin.setdefault("lake_id", origin_lake_id)
        origin.setdefault("asset_id", origin_asset_id)
        merged["origin"] = origin

        replication = merged.get("replication")
        if not isinstance(replication, dict):
            replication = {}
        state = ReplicatedAssetState(
            origin_lake_id=origin_lake_id,
            origin_asset_id=origin_asset_id,
            replication_mode=replication_mode,
            payload_status=payload_status,
            payload_available=payload_status == "verified",
            payload_last_error=replication.get("payload_last_error"),
            payload_last_attempt_at=replication.get("payload_last_attempt_at"),
            payload_verified_at=replication.get("payload_verified_at"),
            local_delete_eligible_at=replication.get("local_delete_eligible_at"),
            local_deleted_at=replication.get("local_deleted_at"),
        )
        merged["replication"] = state.model_dump(mode="json")
        return merged

    async def upsert_metadata_batch(self, request: ReplicationBatchRequest) -> ReplicationBatchResult:
        result = ReplicationBatchResult()

        for schema in request.annotation_schemas:
            if await self._annotation_schema_exists(schema.annotation_schema_id):
                await self._update_annotation_schema(schema, request.origin_lake_id)
                result.updated_annotation_schemas += 1
            else:
                await self.target.annotation_schema_database.insert(
                    AnnotationSchema.model_validate(
                        {
                            **schema.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                schema.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=schema.annotation_schema_id,
                                entity_kind="annotation_schema",
                            ),
                        }
                    )
                )
                result.created_annotation_schemas += 1

        for asset in request.assets:
            mapped_storage_ref = _apply_mount_map_to_storage_ref(asset.storage_ref, request.mount_map)
            replicated = Asset.model_validate(
                {
                    **asset.model_dump(),
                    "storage_ref": mapped_storage_ref.model_dump(),
                    "metadata": self.build_asset_replication_metadata(
                        asset.metadata,
                        origin_lake_id=request.origin_lake_id,
                        origin_asset_id=asset.asset_id,
                        replication_mode=request.replication_mode,
                        payload_status="pending",
                    ),
                }
            )
            if await self._asset_exists(asset.asset_id):
                await self._update_asset(replicated)
                result.updated_assets += 1
            else:
                await self.target.asset_database.insert(replicated)
                result.created_assets += 1

        for record in request.annotation_records:
            if await self._annotation_record_exists(record.annotation_id):
                await self._update_annotation_record(record, request.origin_lake_id)
                result.updated_annotation_records += 1
            else:
                await self.target.annotation_record_database.insert(
                    AnnotationRecord.model_validate(
                        {
                            **record.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                record.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=record.annotation_id,
                                entity_kind="annotation_record",
                            ),
                        }
                    )
                )
                result.created_annotation_records += 1

        for annotation_set in request.annotation_sets:
            if await self._annotation_set_exists(annotation_set.annotation_set_id):
                await self._update_annotation_set(annotation_set, request.origin_lake_id)
                result.updated_annotation_sets += 1
            else:
                await self.target.annotation_set_database.insert(
                    AnnotationSet.model_validate(
                        {
                            **annotation_set.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                annotation_set.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=annotation_set.annotation_set_id,
                                entity_kind="annotation_set",
                            ),
                        }
                    )
                )
                result.created_annotation_sets += 1

        for datum in request.datums:
            if await self._datum_exists(datum.datum_id):
                await self._update_datum(datum, request.origin_lake_id)
                result.updated_datums += 1
            else:
                await self.target.datum_database.insert(
                    Datum.model_validate(
                        {
                            **datum.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                datum.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=datum.datum_id,
                                entity_kind="datum",
                            ),
                        }
                    )
                )
                result.created_datums += 1

        return result

    async def status(self) -> ReplicationStatusResult:
        assets = await self.target.asset_database.find({})
        counts: dict[PayloadStatus, int] = {
            "pending": 0,
            "transferring": 0,
            "uploaded": 0,
            "verified": 0,
            "failed": 0,
        }
        pending_asset_ids: list[str] = []
        failed_asset_ids: list[str] = []
        for asset in assets:
            status = self.get_payload_status(asset)
            if status is None:
                continue
            counts[status] += 1
            if status == "pending":
                pending_asset_ids.append(asset.asset_id)
            elif status == "failed":
                failed_asset_ids.append(asset.asset_id)
        return ReplicationStatusResult(
            asset_counts_by_payload_status=counts,
            pending_asset_ids=pending_asset_ids,
            failed_asset_ids=failed_asset_ids,
        )

    def _merge_origin_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        origin_lake_id: str,
        entity_id: str,
        entity_kind: str,
    ) -> dict[str, Any]:
        merged = dict(metadata or {})
        origin = merged.get("origin")
        if not isinstance(origin, dict):
            origin = {}
        origin.setdefault("lake_id", origin_lake_id)
        origin.setdefault("entity_id", entity_id)
        origin.setdefault("entity_kind", entity_kind)
        merged["origin"] = origin
        return merged

    async def _update_asset(self, new_asset: Asset) -> None:
        existing = await self.target.asset_database.find({"asset_id": new_asset.asset_id})
        if not existing:
            await self.target.asset_database.insert(new_asset)
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

    async def _update_annotation_schema(self, schema: AnnotationSchema, origin_lake_id: str) -> None:
        existing = await self.target.annotation_schema_database.find({"annotation_schema_id": schema.annotation_schema_id})
        if not existing:
            await self.target.annotation_schema_database.insert(schema)
            return
        current = existing[0]
        current.name = schema.name
        current.version = schema.version
        current.task_type = schema.task_type
        current.allowed_annotation_kinds = schema.allowed_annotation_kinds
        current.labels = schema.labels
        current.required_attributes = schema.required_attributes
        current.metadata = self._merge_origin_metadata(
            schema.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=schema.annotation_schema_id,
            entity_kind="annotation_schema",
        )
        current.updated_at = schema.updated_at
        await self.target.annotation_schema_database.update(current)

    async def _update_annotation_record(self, record: AnnotationRecord, origin_lake_id: str) -> None:
        existing = await self.target.annotation_record_database.find({"annotation_id": record.annotation_id})
        if not existing:
            await self.target.annotation_record_database.insert(record)
            return
        current = existing[0]
        current.kind = record.kind
        current.label = record.label
        current.label_id = record.label_id
        current.source = record.source
        current.geometry = record.geometry
        current.attributes = record.attributes
        current.metadata = self._merge_origin_metadata(
            record.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=record.annotation_id,
            entity_kind="annotation_record",
        )
        current.updated_at = record.updated_at
        await self.target.annotation_record_database.update(current)

    async def _update_annotation_set(self, annotation_set: AnnotationSet, origin_lake_id: str) -> None:
        existing = await self.target.annotation_set_database.find({"annotation_set_id": annotation_set.annotation_set_id})
        if not existing:
            await self.target.annotation_set_database.insert(annotation_set)
            return
        current = existing[0]
        current.name = annotation_set.name
        current.purpose = annotation_set.purpose
        current.source_type = annotation_set.source_type
        current.datum_id = annotation_set.datum_id
        current.annotation_schema_id = annotation_set.annotation_schema_id
        current.annotation_record_ids = annotation_set.annotation_record_ids
        current.metadata = self._merge_origin_metadata(
            annotation_set.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=annotation_set.annotation_set_id,
            entity_kind="annotation_set",
        )
        current.updated_at = annotation_set.updated_at
        await self.target.annotation_set_database.update(current)

    async def _update_datum(self, datum: Datum, origin_lake_id: str) -> None:
        existing = await self.target.datum_database.find({"datum_id": datum.datum_id})
        if not existing:
            await self.target.datum_database.insert(datum)
            return
        current = existing[0]
        current.asset_refs = datum.asset_refs
        current.split = datum.split
        current.annotation_set_ids = datum.annotation_set_ids
        current.metadata = self._merge_origin_metadata(
            datum.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=datum.datum_id,
            entity_kind="datum",
        )
        current.updated_at = datum.updated_at
        await self.target.datum_database.update(current)

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
