from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
from typing import Any

from fastapi import HTTPException

from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.replication import ReplicationManager
from mindtrace.datalake.replication_types import ReplicationReclaimRequest, ReplicationReconcileRequest
from mindtrace.datalake.service_types import (
    AddAliasInput,
    AddAliasSchema,
    AddAnnotationRecordsInput,
    AddAnnotationRecordsSchema,
    AddedAnnotationRecordsOutput,
    AnnotationRecordListOutput,
    AnnotationRecordOutput,
    AnnotationSchemaListOutput,
    AnnotationSchemaOutput,
    AnnotationSetListOutput,
    AnnotationSetOutput,
    AssetAliasOutput,
    AssetListOutput,
    AssetOutput,
    AssetRetentionListOutput,
    AssetRetentionOutput,
    CollectionItemListOutput,
    CollectionItemOutput,
    CollectionListOutput,
    CollectionOutput,
    CompleteObjectUploadSessionInput,
    CompleteObjectUploadSessionSchema,
    CopyObjectInput,
    CopyObjectSchema,
    CreateAnnotationSchemaInput,
    CreateAnnotationSchemaSchema,
    CreateAnnotationSetInput,
    CreateAnnotationSetSchema,
    CreateAssetFromObjectInput,
    CreateAssetFromObjectSchema,
    CreateAssetFromUploadedObjectInput,
    CreateAssetFromUploadedObjectSchema,
    CreateAssetInput,
    CreateAssetRetentionInput,
    CreateAssetRetentionSchema,
    CreateAssetSchema,
    CreateCollectionInput,
    CreateCollectionItemInput,
    CreateCollectionItemSchema,
    CreateCollectionSchema,
    CreateDatasetVersionInput,
    CreateDatasetVersionSchema,
    CreateDatumInput,
    CreateDatumSchema,
    CreateObjectUploadSessionInput,
    CreateObjectUploadSessionSchema,
    DatalakeHealthOutput,
    DatalakeHealthSchema,
    DatalakeSummaryOutput,
    DatalakeSummarySchema,
    DatasetSyncBundleOutput,
    DatasetSyncCommitResultOutput,
    DatasetSyncImportCommitSchema,
    DatasetSyncImportPlanOutput,
    DatasetSyncImportPrepareSchema,
    DatasetSyncImportRequest,
    DatasetVersionListOutput,
    DatasetVersionOutput,
    DatumListOutput,
    DatumOutput,
    DeleteAnnotationRecordSchema,
    DeleteAnnotationSchemaSchema,
    DeleteAssetRetentionSchema,
    DeleteAssetSchema,
    DeleteCollectionItemSchema,
    DeleteCollectionSchema,
    ExportDatasetVersionInput,
    ExportDatasetVersionSchema,
    GetAnnotationRecordSchema,
    GetAnnotationSchemaByNameVersionInput,
    GetAnnotationSchemaByNameVersionSchema,
    GetAnnotationSchemaSchema,
    GetAnnotationSetSchema,
    GetAssetByAliasInput,
    GetAssetByAliasSchema,
    GetAssetRetentionSchema,
    GetAssetSchema,
    GetByIdInput,
    GetCollectionItemSchema,
    GetCollectionSchema,
    GetDatasetVersionInput,
    GetDatasetVersionSchema,
    GetDatumSchema,
    GetObjectInput,
    GetObjectSchema,
    HeadObjectInput,
    HeadObjectSchema,
    ListAnnotationRecordsForAssetInput,
    ListAnnotationRecordsForAssetSchema,
    ListAnnotationRecordsSchema,
    ListAnnotationSchemasSchema,
    ListAnnotationSetsSchema,
    ListAssetRetentionsSchema,
    ListAssetsSchema,
    ListCollectionItemsSchema,
    ListCollectionsSchema,
    ListDatasetVersionsInput,
    ListDatasetVersionsSchema,
    ListDatumsSchema,
    ListInput,
    MountsOutput,
    MountsSchema,
    ObjectDataOutput,
    ObjectHeadOutput,
    ObjectOutput,
    ObjectUploadSessionOutput,
    PutObjectInput,
    PutObjectSchema,
    ReplicationBatchRequest,
    ReplicationBatchResultOutput,
    ReplicationBatchUpsertSchema,
    ReplicationDeleteLocalPayloadSchema,
    ReplicationHydrateAssetPayloadInput,
    ReplicationHydrateAssetPayloadSchema,
    ReplicationMarkLocalDeleteEligibleInput,
    ReplicationMarkLocalDeleteEligibleSchema,
    ReplicationReclaimResultOutput,
    ReplicationReclaimSchema,
    ReplicationReconcileResultOutput,
    ReplicationReconcileSchema,
    ReplicationStatusOutput,
    ReplicationStatusSchema,
    ResolveCollectionItemSchema,
    ResolveDatasetVersionSchema,
    ResolveDatumSchema,
    ResolvedCollectionItemOutput,
    ResolvedDatasetVersionOutput,
    ResolvedDatumOutput,
    UpdateAnnotationRecordInput,
    UpdateAnnotationRecordSchema,
    UpdateAnnotationSchemaInput,
    UpdateAnnotationSchemaSchema,
    UpdateAnnotationSetInput,
    UpdateAnnotationSetSchema,
    UpdateAssetMetadataInput,
    UpdateAssetMetadataSchema,
    UpdateAssetRetentionInput,
    UpdateAssetRetentionSchema,
    UpdateCollectionInput,
    UpdateCollectionItemInput,
    UpdateCollectionItemSchema,
    UpdateCollectionSchema,
    UpdateDatumInput,
    UpdateDatumSchema,
)
from mindtrace.datalake.sync import DatasetSyncManager
from mindtrace.registry import Mount
from mindtrace.services import Service, endpoint


class DatalakeService(Service):
    """FastAPI/MCP service wrapper over ``AsyncDatalake``."""

    def __init__(
        self,
        *,
        mongo_db_uri: str | None = None,
        mongo_db_name: str | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
        async_datalake: AsyncDatalake | None = None,
        initialize_on_startup: bool = True,
        live_service: bool = True,
        upload_reconcile_interval_seconds: float = 30.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.mongo_db_uri = mongo_db_uri
        self.mongo_db_name = mongo_db_name
        self.mounts = mounts
        self.default_mount = default_mount
        self._datalake: AsyncDatalake | None = async_datalake
        self._initialized = async_datalake is not None
        self.initialize_on_startup = initialize_on_startup
        self.upload_reconcile_interval_seconds = upload_reconcile_interval_seconds
        self._upload_reconciler_task: asyncio.Task[None] | None = None

        if live_service and initialize_on_startup:
            self.app.router.on_startup.append(self._startup_initialize)
            self.app.router.on_shutdown.append(self._shutdown_cleanup)

    async def _startup_initialize(self) -> None:
        await self._ensure_datalake()
        if self._upload_reconciler_task is None:
            self._upload_reconciler_task = asyncio.create_task(self._run_upload_reconciler())

    async def _shutdown_cleanup(self) -> None:
        if self._upload_reconciler_task is None:
            return
        self._upload_reconciler_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._upload_reconciler_task
        self._upload_reconciler_task = None

    async def _ensure_datalake(self) -> AsyncDatalake:
        if self._datalake is None:
            if not self.mongo_db_uri or not self.mongo_db_name:
                raise HTTPException(
                    status_code=500, detail="DatalakeService is missing mongo_db_uri and/or mongo_db_name"
                )
            self._datalake = AsyncDatalake(
                mongo_db_uri=self.mongo_db_uri,
                mongo_db_name=self.mongo_db_name,
                mounts=self.mounts,
                default_mount=self.default_mount,
            )
        if not self._initialized:
            await self._datalake.initialize()
            self._initialized = True
        return self._datalake

    @staticmethod
    def _decode_base64(data_base64: str) -> bytes:
        return base64.b64decode(data_base64.encode("utf-8"))

    @staticmethod
    def _encode_base64(data: Any) -> str:
        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not isinstance(data, (bytes, bytearray)):
            raise HTTPException(
                status_code=500, detail=f"Object payload type is not serializable to base64: {type(data)!r}"
            )
        return base64.b64encode(bytes(data)).decode("utf-8")

    @endpoint("health", schema=DatalakeHealthSchema, as_tool=True)
    async def health(self) -> DatalakeHealthOutput:
        datalake = await self._ensure_datalake()
        return DatalakeHealthOutput(**(await datalake.get_health()))

    @endpoint("summary", schema=DatalakeSummarySchema, as_tool=True)
    async def summary(self) -> DatalakeSummaryOutput:
        datalake = await self._ensure_datalake()
        return DatalakeSummaryOutput(summary=await datalake.summary())

    @endpoint("mounts", schema=MountsSchema)
    async def mounts_info(self) -> MountsOutput:
        datalake = await self._ensure_datalake()
        return MountsOutput(**datalake.get_mounts())

    @endpoint("objects.put", schema=PutObjectSchema)
    async def put_object(self, payload: PutObjectInput) -> ObjectOutput:
        datalake = await self._ensure_datalake()
        storage_ref = await datalake.put_object(
            name=payload.name,
            obj=self._decode_base64(payload.data_base64),
            mount=payload.mount,
            version=payload.version,
            metadata=payload.metadata,
            on_conflict=payload.on_conflict,
        )
        return ObjectOutput(storage_ref=storage_ref)

    @endpoint("objects.get", schema=GetObjectSchema)
    async def get_object(self, payload: GetObjectInput) -> ObjectDataOutput:
        datalake = await self._ensure_datalake()
        obj = await datalake.get_object(payload.storage_ref)
        return ObjectDataOutput(storage_ref=payload.storage_ref, data_base64=self._encode_base64(obj))

    @endpoint("objects.head", schema=HeadObjectSchema)
    async def head_object(self, payload: HeadObjectInput) -> ObjectHeadOutput:
        datalake = await self._ensure_datalake()
        metadata = await datalake.head_object(payload.storage_ref)
        return ObjectHeadOutput(storage_ref=payload.storage_ref, metadata=metadata)

    @endpoint("objects.copy", schema=CopyObjectSchema)
    async def copy_object(self, payload: CopyObjectInput) -> ObjectOutput:
        datalake = await self._ensure_datalake()
        storage_ref = await datalake.copy_object(
            payload.source,
            target_mount=payload.target_mount,
            target_name=payload.target_name,
            target_version=payload.target_version,
        )
        return ObjectOutput(storage_ref=storage_ref)

    @endpoint("objects.upload_session.create", schema=CreateObjectUploadSessionSchema)
    async def create_object_upload_session(self, payload: CreateObjectUploadSessionInput) -> ObjectUploadSessionOutput:
        datalake = await self._ensure_datalake()
        session = await datalake.create_object_upload_session(
            name=payload.name,
            mount=payload.mount,
            version=payload.version,
            metadata=payload.metadata,
            on_conflict=payload.on_conflict,
            content_type=payload.content_type,
            expires_in_minutes=payload.expires_in_minutes,
            created_by=payload.created_by,
        )
        return ObjectUploadSessionOutput.from_session(session)

    @endpoint("objects.upload_session.complete", schema=CompleteObjectUploadSessionSchema)
    async def complete_object_upload_session(
        self, payload: CompleteObjectUploadSessionInput
    ) -> ObjectUploadSessionOutput:
        datalake = await self._ensure_datalake()
        session = await datalake.complete_object_upload_session(
            payload.upload_session_id,
            finalize_token=payload.finalize_token,
            metadata=payload.metadata,
        )
        return ObjectUploadSessionOutput.from_session(session)

    @endpoint("assets.create", schema=CreateAssetSchema)
    async def create_asset(self, payload: CreateAssetInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        asset = await datalake.create_asset(
            kind=payload.kind,
            media_type=payload.media_type,
            storage_ref=payload.storage_ref,
            checksum=payload.checksum,
            size_bytes=payload.size_bytes,
            subject=payload.subject,
            metadata=payload.metadata,
            created_by=payload.created_by,
        )
        return AssetOutput(asset=asset)

    @endpoint("assets.get", schema=GetAssetSchema, as_tool=True)
    async def get_asset(self, payload: GetByIdInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        return AssetOutput(asset=await datalake.get_asset(payload.id))

    @endpoint("assets.get_by_alias", schema=GetAssetByAliasSchema, as_tool=True)
    async def get_asset_by_alias(self, payload: GetAssetByAliasInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        return AssetOutput(asset=await datalake.get_asset_by_alias(payload.alias))

    @endpoint("aliases.add", schema=AddAliasSchema)
    async def add_alias(self, payload: AddAliasInput) -> AssetAliasOutput:
        datalake = await self._ensure_datalake()
        row = await datalake.add_alias(payload.asset_id, payload.alias)
        return AssetAliasOutput(asset_alias=row)

    @endpoint("assets.list", schema=ListAssetsSchema)
    async def list_assets(self, payload: ListInput) -> AssetListOutput:
        datalake = await self._ensure_datalake()
        return AssetListOutput(assets=await datalake.list_assets(payload.filters))

    @endpoint("assets.update_metadata", schema=UpdateAssetMetadataSchema)
    async def update_asset_metadata(self, payload: UpdateAssetMetadataInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        asset = await datalake.update_asset_metadata(payload.asset_id, payload.metadata)
        return AssetOutput(asset=asset)

    @endpoint("assets.delete", schema=DeleteAssetSchema)
    async def delete_asset(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_asset(payload.id)

    @endpoint("assets.create_from_object", schema=CreateAssetFromObjectSchema)
    async def create_asset_from_object(self, payload: CreateAssetFromObjectInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        asset = await datalake.create_asset_from_object(
            name=payload.name,
            obj=self._decode_base64(payload.data_base64),
            kind=payload.kind,
            media_type=payload.media_type,
            mount=payload.mount,
            version=payload.version,
            object_metadata=payload.object_metadata,
            asset_metadata=payload.asset_metadata,
            checksum=payload.checksum,
            size_bytes=payload.size_bytes,
            subject=payload.subject,
            created_by=payload.created_by,
            on_conflict=payload.on_conflict,
        )
        return AssetOutput(asset=asset)

    @endpoint("assets.create_from_uploaded_object", schema=CreateAssetFromUploadedObjectSchema)
    async def create_asset_from_uploaded_object(self, payload: CreateAssetFromUploadedObjectInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        asset = await datalake.create_asset(
            kind=payload.kind,
            media_type=payload.media_type,
            storage_ref=payload.storage_ref,
            checksum=payload.checksum,
            size_bytes=payload.size_bytes,
            subject=payload.subject,
            metadata=payload.metadata,
            created_by=payload.created_by,
        )
        return AssetOutput(asset=asset)

    async def _run_upload_reconciler(self) -> None:
        while True:
            try:
                datalake = await self._ensure_datalake()
                await datalake.reconcile_upload_sessions()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning(f"Upload reconciler iteration failed: {exc}")
            await asyncio.sleep(self.upload_reconcile_interval_seconds)

    @endpoint("collections.create", schema=CreateCollectionSchema)
    async def create_collection(self, payload: CreateCollectionInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.create_collection(**payload.model_dump()))

    @endpoint("collections.get", schema=GetCollectionSchema)
    async def get_collection(self, payload: GetByIdInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.get_collection(payload.id))

    @endpoint("collections.list", schema=ListCollectionsSchema)
    async def list_collections(self, payload: ListInput) -> CollectionListOutput:
        datalake = await self._ensure_datalake()
        return CollectionListOutput(collections=await datalake.list_collections(payload.filters))

    @endpoint("collections.update", schema=UpdateCollectionSchema)
    async def update_collection(self, payload: UpdateCollectionInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.update_collection(payload.collection_id, **payload.changes))

    @endpoint("collections.delete", schema=DeleteCollectionSchema)
    async def delete_collection(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_collection(payload.id)

    @endpoint("collection_items.create", schema=CreateCollectionItemSchema)
    async def create_collection_item(self, payload: CreateCollectionItemInput) -> CollectionItemOutput:
        datalake = await self._ensure_datalake()
        return CollectionItemOutput(collection_item=await datalake.create_collection_item(**payload.model_dump()))

    @endpoint("collection_items.get", schema=GetCollectionItemSchema)
    async def get_collection_item(self, payload: GetByIdInput) -> CollectionItemOutput:
        datalake = await self._ensure_datalake()
        return CollectionItemOutput(collection_item=await datalake.get_collection_item(payload.id))

    @endpoint("collection_items.list", schema=ListCollectionItemsSchema)
    async def list_collection_items(self, payload: ListInput) -> CollectionItemListOutput:
        datalake = await self._ensure_datalake()
        return CollectionItemListOutput(collection_items=await datalake.list_collection_items(payload.filters))

    @endpoint("collection_items.resolve", schema=ResolveCollectionItemSchema)
    async def resolve_collection_item(self, payload: GetByIdInput) -> ResolvedCollectionItemOutput:
        datalake = await self._ensure_datalake()
        return ResolvedCollectionItemOutput(resolved_collection_item=await datalake.resolve_collection_item(payload.id))

    @endpoint("collection_items.update", schema=UpdateCollectionItemSchema)
    async def update_collection_item(self, payload: UpdateCollectionItemInput) -> CollectionItemOutput:
        datalake = await self._ensure_datalake()
        item = await datalake.update_collection_item(payload.collection_item_id, **payload.changes)
        return CollectionItemOutput(collection_item=item)

    @endpoint("collection_items.delete", schema=DeleteCollectionItemSchema)
    async def delete_collection_item(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_collection_item(payload.id)

    @endpoint("asset_retentions.create", schema=CreateAssetRetentionSchema)
    async def create_asset_retention(self, payload: CreateAssetRetentionInput) -> AssetRetentionOutput:
        datalake = await self._ensure_datalake()
        retention = await datalake.create_asset_retention(**payload.model_dump())
        return AssetRetentionOutput(asset_retention=retention)

    @endpoint("asset_retentions.get", schema=GetAssetRetentionSchema)
    async def get_asset_retention(self, payload: GetByIdInput) -> AssetRetentionOutput:
        datalake = await self._ensure_datalake()
        return AssetRetentionOutput(asset_retention=await datalake.get_asset_retention(payload.id))

    @endpoint("asset_retentions.list", schema=ListAssetRetentionsSchema)
    async def list_asset_retentions(self, payload: ListInput) -> AssetRetentionListOutput:
        datalake = await self._ensure_datalake()
        return AssetRetentionListOutput(asset_retentions=await datalake.list_asset_retentions(payload.filters))

    @endpoint("asset_retentions.update", schema=UpdateAssetRetentionSchema)
    async def update_asset_retention(self, payload: UpdateAssetRetentionInput) -> AssetRetentionOutput:
        datalake = await self._ensure_datalake()
        retention = await datalake.update_asset_retention(payload.asset_retention_id, **payload.changes)
        return AssetRetentionOutput(asset_retention=retention)

    @endpoint("asset_retentions.delete", schema=DeleteAssetRetentionSchema)
    async def delete_asset_retention(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_asset_retention(payload.id)

    @endpoint("annotation_schemas.create", schema=CreateAnnotationSchemaSchema)
    async def create_annotation_schema(self, payload: CreateAnnotationSchemaInput) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        schema = await datalake.create_annotation_schema(**payload.model_dump())
        return AnnotationSchemaOutput(annotation_schema=schema)

    @endpoint("annotation_schemas.get", schema=GetAnnotationSchemaSchema)
    async def get_annotation_schema(self, payload: GetByIdInput) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSchemaOutput(annotation_schema=await datalake.get_annotation_schema(payload.id))

    @endpoint("annotation_schemas.get_by_name_version", schema=GetAnnotationSchemaByNameVersionSchema, as_tool=True)
    async def get_annotation_schema_by_name_version(
        self, payload: GetAnnotationSchemaByNameVersionInput
    ) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        schema = await datalake.get_annotation_schema_by_name_version(payload.name, payload.version)
        return AnnotationSchemaOutput(annotation_schema=schema)

    @endpoint("annotation_schemas.list", schema=ListAnnotationSchemasSchema)
    async def list_annotation_schemas(self, payload: ListInput) -> AnnotationSchemaListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSchemaListOutput(annotation_schemas=await datalake.list_annotation_schemas(payload.filters))

    @endpoint("annotation_schemas.update", schema=UpdateAnnotationSchemaSchema)
    async def update_annotation_schema(self, payload: UpdateAnnotationSchemaInput) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        schema = await datalake.update_annotation_schema(payload.annotation_schema_id, **payload.changes)
        return AnnotationSchemaOutput(annotation_schema=schema)

    @endpoint("annotation_schemas.delete", schema=DeleteAnnotationSchemaSchema)
    async def delete_annotation_schema(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_annotation_schema(payload.id)

    @endpoint("annotation_sets.create", schema=CreateAnnotationSetSchema)
    async def create_annotation_set(self, payload: CreateAnnotationSetInput) -> AnnotationSetOutput:
        datalake = await self._ensure_datalake()
        annotation_set = await datalake.create_annotation_set(**payload.model_dump())
        return AnnotationSetOutput(annotation_set=annotation_set)

    @endpoint("annotation_sets.get", schema=GetAnnotationSetSchema)
    async def get_annotation_set(self, payload: GetByIdInput) -> AnnotationSetOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSetOutput(annotation_set=await datalake.get_annotation_set(payload.id))

    @endpoint("annotation_sets.list", schema=ListAnnotationSetsSchema)
    async def list_annotation_sets(self, payload: ListInput) -> AnnotationSetListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSetListOutput(annotation_sets=await datalake.list_annotation_sets(payload.filters))

    @endpoint("annotation_sets.update", schema=UpdateAnnotationSetSchema)
    async def update_annotation_set(self, payload: UpdateAnnotationSetInput) -> AnnotationSetOutput:
        datalake = await self._ensure_datalake()
        annotation_set = await datalake.update_annotation_set(payload.annotation_set_id, **payload.changes)
        return AnnotationSetOutput(annotation_set=annotation_set)

    @endpoint("annotation_records.add", schema=AddAnnotationRecordsSchema)
    async def add_annotation_records(self, payload: AddAnnotationRecordsInput) -> AddedAnnotationRecordsOutput:
        datalake = await self._ensure_datalake()
        records = await datalake.add_annotation_records(
            payload.annotations,
            annotation_set_id=payload.annotation_set_id,
            annotation_schema_id=payload.annotation_schema_id,
        )
        return AddedAnnotationRecordsOutput(annotation_records=records)

    @endpoint("annotation_records.list_for_asset", schema=ListAnnotationRecordsForAssetSchema)
    async def list_annotation_records_for_asset(
        self, payload: ListAnnotationRecordsForAssetInput
    ) -> AnnotationRecordListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordListOutput(
            annotation_records=await datalake.list_annotation_records_for_asset(payload.asset_id),
        )

    @endpoint("annotation_records.get", schema=GetAnnotationRecordSchema)
    async def get_annotation_record(self, payload: GetByIdInput) -> AnnotationRecordOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordOutput(annotation_record=await datalake.get_annotation_record(payload.id))

    @endpoint("annotation_records.list", schema=ListAnnotationRecordsSchema)
    async def list_annotation_records(self, payload: ListInput) -> AnnotationRecordListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordListOutput(annotation_records=await datalake.list_annotation_records(payload.filters))

    @endpoint("annotation_records.update", schema=UpdateAnnotationRecordSchema)
    async def update_annotation_record(self, payload: UpdateAnnotationRecordInput) -> AnnotationRecordOutput:
        datalake = await self._ensure_datalake()
        record = await datalake.update_annotation_record(payload.annotation_id, **payload.changes)
        return AnnotationRecordOutput(annotation_record=record)

    @endpoint("annotation_records.delete", schema=DeleteAnnotationRecordSchema)
    async def delete_annotation_record(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_annotation_record(payload.id)

    @endpoint("datums.create", schema=CreateDatumSchema)
    async def create_datum(self, payload: CreateDatumInput) -> DatumOutput:
        datalake = await self._ensure_datalake()
        return DatumOutput(datum=await datalake.create_datum(**payload.model_dump()))

    @endpoint("datums.get", schema=GetDatumSchema)
    async def get_datum(self, payload: GetByIdInput) -> DatumOutput:
        datalake = await self._ensure_datalake()
        return DatumOutput(datum=await datalake.get_datum(payload.id))

    @endpoint("datums.list", schema=ListDatumsSchema)
    async def list_datums(self, payload: ListInput) -> DatumListOutput:
        datalake = await self._ensure_datalake()
        return DatumListOutput(datums=await datalake.list_datums(payload.filters))

    @endpoint("datums.update", schema=UpdateDatumSchema)
    async def update_datum(self, payload: UpdateDatumInput) -> DatumOutput:
        datalake = await self._ensure_datalake()
        return DatumOutput(datum=await datalake.update_datum(payload.datum_id, **payload.changes))

    @endpoint("datums.resolve", schema=ResolveDatumSchema, as_tool=True)
    async def resolve_datum(self, payload: GetByIdInput) -> ResolvedDatumOutput:
        datalake = await self._ensure_datalake()
        return ResolvedDatumOutput(resolved_datum=await datalake.resolve_datum(payload.id))

    @endpoint("dataset_versions.create", schema=CreateDatasetVersionSchema)
    async def create_dataset_version(self, payload: CreateDatasetVersionInput) -> DatasetVersionOutput:
        datalake = await self._ensure_datalake()
        dataset_version = await datalake.create_dataset_version(**payload.model_dump())
        return DatasetVersionOutput(dataset_version=dataset_version)

    @endpoint("dataset_versions.get", schema=GetDatasetVersionSchema, as_tool=True)
    async def get_dataset_version(self, payload: GetDatasetVersionInput) -> DatasetVersionOutput:
        datalake = await self._ensure_datalake()
        dataset_version = await datalake.get_dataset_version(payload.dataset_name, payload.version)
        return DatasetVersionOutput(dataset_version=dataset_version)

    @endpoint("dataset_versions.list", schema=ListDatasetVersionsSchema, as_tool=True)
    async def list_dataset_versions(self, payload: ListDatasetVersionsInput) -> DatasetVersionListOutput:
        datalake = await self._ensure_datalake()
        versions = await datalake.list_dataset_versions(dataset_name=payload.dataset_name, filters=payload.filters)
        return DatasetVersionListOutput(dataset_versions=versions)

    @endpoint("dataset_versions.resolve", schema=ResolveDatasetVersionSchema, as_tool=True)
    async def resolve_dataset_version(self, payload: GetDatasetVersionInput) -> ResolvedDatasetVersionOutput:
        datalake = await self._ensure_datalake()
        resolved = await datalake.resolve_dataset_version(payload.dataset_name, payload.version)
        return ResolvedDatasetVersionOutput(resolved_dataset_version=resolved)

    @endpoint("dataset_versions.export", schema=ExportDatasetVersionSchema)
    async def export_dataset_version(self, payload: ExportDatasetVersionInput) -> DatasetSyncBundleOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        bundle = await manager.export_dataset_version(payload.dataset_name, payload.version)
        return DatasetSyncBundleOutput(bundle=bundle)

    @endpoint("dataset_versions.import_prepare", schema=DatasetSyncImportPrepareSchema)
    async def import_dataset_version_prepare(self, payload: DatasetSyncImportRequest) -> DatasetSyncImportPlanOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        plan = await manager.plan_import(payload)
        return DatasetSyncImportPlanOutput(plan=plan)

    @endpoint("dataset_versions.import_commit", schema=DatasetSyncImportCommitSchema)
    async def import_dataset_version_commit(self, payload: DatasetSyncImportRequest) -> DatasetSyncCommitResultOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        result = await manager.commit_import(payload)
        return DatasetSyncCommitResultOutput(result=result)

    @endpoint("replication.upsert_batch", schema=ReplicationBatchUpsertSchema)
    async def replication_upsert_batch(self, payload: ReplicationBatchRequest) -> ReplicationBatchResultOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        result = await manager.upsert_metadata_batch(payload)
        return ReplicationBatchResultOutput(result=result)

    @endpoint("replication.hydrate_asset_payload", schema=ReplicationHydrateAssetPayloadSchema)
    async def replication_hydrate_asset_payload(self, payload: ReplicationHydrateAssetPayloadInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        asset = await manager.hydrate_asset_payload(payload.asset_id, mount_map=payload.mount_map)
        return AssetOutput(asset=asset)

    @endpoint("replication.reconcile", schema=ReplicationReconcileSchema)
    async def replication_reconcile(self, payload: ReplicationReconcileRequest) -> ReplicationReconcileResultOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        result = await manager.reconcile_pending_payloads(payload)
        return ReplicationReconcileResultOutput(result=result)

    @endpoint("replication.mark_local_delete_eligible", schema=ReplicationMarkLocalDeleteEligibleSchema)
    async def replication_mark_local_delete_eligible(
        self, payload: ReplicationMarkLocalDeleteEligibleInput
    ) -> AssetOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        asset = await manager.mark_local_delete_eligible(payload.asset_id, when=payload.when)
        return AssetOutput(asset=asset)

    @endpoint("replication.delete_local_payload", schema=ReplicationDeleteLocalPayloadSchema)
    async def replication_delete_local_payload(self, payload: GetByIdInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        asset = await manager.delete_local_payload(payload.id)
        return AssetOutput(asset=asset)

    @endpoint("replication.reclaim_verified_payloads", schema=ReplicationReclaimSchema)
    async def replication_reclaim_verified_payloads(
        self, payload: ReplicationReclaimRequest
    ) -> ReplicationReclaimResultOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        result = await manager.reclaim_verified_payloads(payload)
        return ReplicationReclaimResultOutput(result=result)

    @endpoint("replication.status", schema=ReplicationStatusSchema)
    async def replication_status(self) -> ReplicationStatusOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        status = await manager.status()
        return ReplicationStatusOutput(status=status)
