from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.sync_types import (
    DatasetSyncBundle,
    DatasetSyncCommitResult,
    DatasetSyncImportPlan,
    DatasetSyncImportRequest,
    DatasetSyncPayloadPlan,
    ObjectPayloadDescriptor,
)
from mindtrace.datalake.types import AnnotationRecord, AnnotationSchema, AnnotationSet, Asset, DatasetVersion, Datum, StorageRef


class DatasetSyncManager:
    def __init__(self, source: AsyncDatalake, target: AsyncDatalake | None = None) -> None:
        self.source = source
        self.target = target or source

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
                storage_ref=asset.storage_ref,
                media_type=asset.media_type,
                size_bytes=asset.size_bytes,
                checksum=asset.checksum,
                content_type=asset.media_type,
                metadata=dict(asset.metadata or {}),
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

    async def plan_import(self, request: DatasetSyncImportRequest) -> DatasetSyncImportPlan:
        bundle = request.bundle
        payload_plans: list[DatasetSyncPayloadPlan] = []

        for payload in bundle.payloads:
            target_exists = await self.target.object_exists(payload.storage_ref)
            if request.transfer_policy == "copy":
                transfer_required = True
                reason = "policy_copy"
            elif request.transfer_policy == "copy_if_missing":
                transfer_required = not target_exists
                reason = "missing_on_target" if transfer_required else "already_present"
            elif request.transfer_policy == "metadata_only":
                transfer_required = False
                reason = "metadata_only"
            elif request.transfer_policy == "fail_if_missing_payload":
                transfer_required = False
                reason = "already_present" if target_exists else "missing_payload"
            else:
                raise ValueError(f"Unsupported transfer policy: {request.transfer_policy}")
            payload_plans.append(
                DatasetSyncPayloadPlan(
                    asset_id=payload.asset_id,
                    source_storage_ref=payload.storage_ref,
                    target_exists=target_exists,
                    transfer_required=transfer_required,
                    reason=reason,
                )
            )

        missing_payload_count = sum(1 for plan in payload_plans if not plan.target_exists)
        transfer_required_count = sum(1 for plan in payload_plans if plan.transfer_required)
        if request.transfer_policy == "metadata_only":
            ready_to_commit = True
        elif request.transfer_policy == "fail_if_missing_payload":
            ready_to_commit = missing_payload_count == 0
        else:
            ready_to_commit = True

        return DatasetSyncImportPlan(
            dataset_name=bundle.dataset_version.dataset_name,
            version=bundle.dataset_version.version,
            transfer_policy=request.transfer_policy,
            payloads=payload_plans,
            missing_payload_count=missing_payload_count,
            transfer_required_count=transfer_required_count,
            ready_to_commit=ready_to_commit,
        )

    async def sync_dataset_version(
        self,
        dataset_name: str,
        version: str,
        *,
        transfer_policy: str = "copy_if_missing",
        origin_lake_id: str | None = None,
        preserve_ids: bool = True,
    ) -> DatasetSyncCommitResult:
        bundle = await self.export_dataset_version(dataset_name, version)
        return await self.commit_import(
            DatasetSyncImportRequest(
                bundle=bundle,
                transfer_policy=transfer_policy,
                origin_lake_id=origin_lake_id,
                preserve_ids=preserve_ids,
            )
        )

    async def commit_import(self, request: DatasetSyncImportRequest) -> DatasetSyncCommitResult:
        plan = await self.plan_import(request)
        if not plan.ready_to_commit:
            raise ValueError(
                f"Import plan for {plan.dataset_name}@{plan.version} is not ready to commit under policy {plan.transfer_policy}"
            )

        bundle = request.bundle
        origin_lake_id = request.origin_lake_id or self.source.mongo_db_name
        payload_by_asset_id = {payload.asset_id: payload for payload in bundle.payloads}
        plan_by_asset_id = {plan.asset_id: plan for plan in plan.payloads}

        transferred_payloads = 0
        skipped_payloads = 0
        resolved_storage_refs: dict[str, StorageRef] = {}

        for asset in bundle.assets:
            payload = payload_by_asset_id.get(asset.asset_id)
            asset_plan = plan_by_asset_id.get(asset.asset_id)
            if payload is None or asset_plan is None:
                resolved_storage_refs[asset.asset_id] = asset.storage_ref
                continue
            if request.transfer_policy == "metadata_only":
                resolved_storage_refs[asset.asset_id] = asset.storage_ref
                skipped_payloads += 1
                continue
            if asset_plan.transfer_required:
                resolved_storage_refs[asset.asset_id] = await self._transfer_payload(payload)
                transferred_payloads += 1
            else:
                resolved_storage_refs[asset.asset_id] = payload.storage_ref
                skipped_payloads += 1

        created_annotation_schemas = 0
        for schema in bundle.annotation_schemas:
            if await self._annotation_schema_exists(schema.annotation_schema_id):
                continue
            created = AnnotationSchema.model_validate(
                {
                    **schema.model_dump(),
                    "metadata": self._merge_origin_metadata(schema.metadata, origin_lake_id, schema.annotation_schema_id),
                }
            )
            await self.target.annotation_schema_database.insert(created)
            created_annotation_schemas += 1

        created_assets = 0
        for asset in bundle.assets:
            if await self._asset_exists(asset.asset_id):
                continue
            storage_ref = resolved_storage_refs.get(asset.asset_id, asset.storage_ref)
            created = Asset.model_validate(
                {
                    **asset.model_dump(),
                    "storage_ref": storage_ref.model_dump(),
                    "metadata": self._merge_origin_metadata(asset.metadata, origin_lake_id, asset.asset_id),
                }
            )
            await self.target.asset_database.insert(created)
            created_assets += 1

        created_annotation_records = 0
        for record in bundle.annotation_records:
            if await self._annotation_record_exists(record.annotation_id):
                continue
            created = AnnotationRecord.model_validate(
                {
                    **record.model_dump(),
                    "metadata": self._merge_origin_metadata(record.metadata, origin_lake_id, record.annotation_id),
                }
            )
            await self.target.annotation_record_database.insert(created)
            created_annotation_records += 1

        created_annotation_sets = 0
        for annotation_set in bundle.annotation_sets:
            if await self._annotation_set_exists(annotation_set.annotation_set_id):
                continue
            created = AnnotationSet.model_validate(
                {
                    **annotation_set.model_dump(),
                    "metadata": self._merge_origin_metadata(
                        annotation_set.metadata, origin_lake_id, annotation_set.annotation_set_id
                    ),
                }
            )
            await self.target.annotation_set_database.insert(created)
            created_annotation_sets += 1

        created_datums = 0
        for datum in bundle.datums:
            if await self._datum_exists(datum.datum_id):
                continue
            mapped_asset_refs = {
                role: asset_id
                for role, asset_id in datum.asset_refs.items()
            }
            created = Datum.model_validate(
                {
                    **datum.model_dump(),
                    "asset_refs": mapped_asset_refs,
                    "metadata": self._merge_origin_metadata(datum.metadata, origin_lake_id, datum.datum_id),
                }
            )
            await self.target.datum_database.insert(created)
            created_datums += 1

        existing_dataset_version = await self._get_existing_dataset_version(
            bundle.dataset_version.dataset_name, bundle.dataset_version.version
        )
        if existing_dataset_version is None:
            dataset_version = DatasetVersion.model_validate(
                {
                    **bundle.dataset_version.model_dump(),
                    "metadata": self._merge_origin_metadata(
                        bundle.dataset_version.metadata,
                        origin_lake_id,
                        bundle.dataset_version.dataset_version_id,
                    ),
                }
            )
            dataset_version = await self.target.dataset_version_database.insert(dataset_version)
        else:
            dataset_version = existing_dataset_version

        return DatasetSyncCommitResult(
            dataset_version=dataset_version,
            created_assets=created_assets,
            created_annotation_schemas=created_annotation_schemas,
            created_annotation_records=created_annotation_records,
            created_annotation_sets=created_annotation_sets,
            created_datums=created_datums,
            transferred_payloads=transferred_payloads,
            skipped_payloads=skipped_payloads,
        )

    async def _transfer_payload(self, payload: ObjectPayloadDescriptor) -> StorageRef:
        data = await self.source.get_object(payload.storage_ref)
        session = await self.target.create_object_upload_session(
            name=payload.storage_ref.name,
            mount=payload.storage_ref.mount,
            version=payload.storage_ref.version,
            metadata=payload.metadata,
            on_conflict="skip",
            content_type=payload.content_type or payload.media_type or self._guess_content_type(payload.storage_ref.name),
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
        return completed.storage_ref

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

    def _merge_origin_metadata(self, metadata: dict[str, Any] | None, lake_id: str, entity_id: str) -> dict[str, Any]:
        merged = dict(metadata or {})
        merged.setdefault("origin", {})
        origin = merged["origin"]
        if not isinstance(origin, dict):
            origin = {}
            merged["origin"] = origin
        origin.setdefault("lake_id", lake_id)
        origin.setdefault("entity_id", entity_id)
        return merged

    def _guess_content_type(self, name: str) -> str:
        guessed, _ = mimetypes.guess_type(name)
        return guessed or "application/octet-stream"
