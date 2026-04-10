from __future__ import annotations

import base64
from typing import Any

from fastapi import HTTPException

from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.service_types import (
    AddAnnotationRecordsSchema,
    AddAnnotationRecordsInput,
    AddedAnnotationRecordsOutput,
    AnnotationRecordListOutput,
    AnnotationRecordOutput,
    AnnotationSchemaListOutput,
    AnnotationSchemaOutput,
    AnnotationSetListOutput,
    AnnotationSetOutput,
    AssetListOutput,
    AssetOutput,
    AssetRetentionListOutput,
    AssetRetentionOutput,
    CollectionItemListOutput,
    CollectionItemOutput,
    CollectionListOutput,
    CollectionOutput,
    CopyObjectInput,
    CopyObjectSchema,
    CreateAnnotationSchemaInput,
    CreateAnnotationSchemaSchema,
    CreateAnnotationSetInput,
    CreateAnnotationSetSchema,
    CreateAssetFromObjectInput,
    CreateAssetFromObjectSchema,
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
    DatalakeHealthOutput,
    DatalakeHealthSchema,
    DatalakeSummaryOutput,
    DatalakeSummarySchema,
    DatasetVersionListOutput,
    DatumOutput,
    DatumListOutput,
    DatasetVersionOutput,
    DeleteAnnotationRecordSchema,
    DeleteAnnotationSchemaSchema,
    DeleteAssetRetentionSchema,
    DeleteAssetSchema,
    DeleteCollectionItemSchema,
    DeleteCollectionSchema,
    GetAnnotationRecordSchema,
    GetAnnotationSchemaByNameVersionInput,
    GetAnnotationSchemaByNameVersionSchema,
    GetAnnotationSchemaSchema,
    GetAnnotationSetSchema,
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
    ListAnnotationRecordsSchema,
    ListAnnotationSchemasSchema,
    ListAnnotationSetsSchema,
    ListAssetsSchema,
    ListCollectionsSchema,
    ListCollectionItemsSchema,
    ListDatasetVersionsInput,
    ListDatasetVersionsSchema,
    ListDatumsSchema,
    ListInput,
    ListAssetRetentionsSchema,
    MountsOutput,
    MountsSchema,
    ObjectDataOutput,
    ObjectHeadOutput,
    ObjectOutput,
    PutObjectInput,
    PutObjectSchema,
    ResolveCollectionItemSchema,
    ResolvedCollectionItemOutput,
    ResolvedDatasetVersionOutput,
    ResolvedDatumOutput,
    ResolveDatasetVersionSchema,
    ResolveDatumSchema,
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
from mindtrace.registry import Mount
from mindtrace.services import Service


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
        **kwargs: Any,
    ) -> None:
        super().__init__(live_service=live_service, **kwargs)
        self.mongo_db_uri = mongo_db_uri
        self.mongo_db_name = mongo_db_name
        self.mounts = mounts
        self.default_mount = default_mount
        self._datalake: AsyncDatalake | None = async_datalake
        self._initialized = async_datalake is not None
        self.initialize_on_startup = initialize_on_startup

        if live_service and initialize_on_startup:
            self.app.router.on_startup.append(self._startup_initialize)

        self.add_endpoint("health", self.health, schema=DatalakeHealthSchema, as_tool=True)
        self.add_endpoint("summary", self.summary, schema=DatalakeSummarySchema, as_tool=True)
        self.add_endpoint("mounts", self.mounts_info, schema=MountsSchema)

        self.add_endpoint("objects.put", self.put_object, schema=PutObjectSchema)
        self.add_endpoint("objects.get", self.get_object, schema=GetObjectSchema)
        self.add_endpoint("objects.head", self.head_object, schema=HeadObjectSchema)
        self.add_endpoint("objects.copy", self.copy_object, schema=CopyObjectSchema)

        self.add_endpoint("assets.create", self.create_asset, schema=CreateAssetSchema)
        self.add_endpoint("assets.get", self.get_asset, schema=GetAssetSchema, as_tool=True)
        self.add_endpoint("assets.list", self.list_assets, schema=ListAssetsSchema)
        self.add_endpoint("assets.update_metadata", self.update_asset_metadata, schema=UpdateAssetMetadataSchema)
        self.add_endpoint("assets.delete", self.delete_asset, schema=DeleteAssetSchema)
        self.add_endpoint("assets.create_from_object", self.create_asset_from_object, schema=CreateAssetFromObjectSchema)

        self.add_endpoint("collections.create", self.create_collection, schema=CreateCollectionSchema)
        self.add_endpoint("collections.get", self.get_collection, schema=GetCollectionSchema)
        self.add_endpoint("collections.list", self.list_collections, schema=ListCollectionsSchema)
        self.add_endpoint("collections.update", self.update_collection, schema=UpdateCollectionSchema)
        self.add_endpoint("collections.delete", self.delete_collection, schema=DeleteCollectionSchema)

        self.add_endpoint("collection_items.create", self.create_collection_item, schema=CreateCollectionItemSchema)
        self.add_endpoint("collection_items.get", self.get_collection_item, schema=GetCollectionItemSchema)
        self.add_endpoint("collection_items.list", self.list_collection_items, schema=ListCollectionItemsSchema)
        self.add_endpoint("collection_items.resolve", self.resolve_collection_item, schema=ResolveCollectionItemSchema)
        self.add_endpoint("collection_items.update", self.update_collection_item, schema=UpdateCollectionItemSchema)
        self.add_endpoint("collection_items.delete", self.delete_collection_item, schema=DeleteCollectionItemSchema)

        self.add_endpoint("asset_retentions.create", self.create_asset_retention, schema=CreateAssetRetentionSchema)
        self.add_endpoint("asset_retentions.get", self.get_asset_retention, schema=GetAssetRetentionSchema)
        self.add_endpoint("asset_retentions.list", self.list_asset_retentions, schema=ListAssetRetentionsSchema)
        self.add_endpoint("asset_retentions.update", self.update_asset_retention, schema=UpdateAssetRetentionSchema)
        self.add_endpoint("asset_retentions.delete", self.delete_asset_retention, schema=DeleteAssetRetentionSchema)

        self.add_endpoint("annotation_schemas.create", self.create_annotation_schema, schema=CreateAnnotationSchemaSchema)
        self.add_endpoint("annotation_schemas.get", self.get_annotation_schema, schema=GetAnnotationSchemaSchema)
        self.add_endpoint(
            "annotation_schemas.get_by_name_version",
            self.get_annotation_schema_by_name_version,
            schema=GetAnnotationSchemaByNameVersionSchema,
            as_tool=True,
        )
        self.add_endpoint("annotation_schemas.list", self.list_annotation_schemas, schema=ListAnnotationSchemasSchema)
        self.add_endpoint("annotation_schemas.update", self.update_annotation_schema, schema=UpdateAnnotationSchemaSchema)
        self.add_endpoint("annotation_schemas.delete", self.delete_annotation_schema, schema=DeleteAnnotationSchemaSchema)

        self.add_endpoint("annotation_sets.create", self.create_annotation_set, schema=CreateAnnotationSetSchema)
        self.add_endpoint("annotation_sets.get", self.get_annotation_set, schema=GetAnnotationSetSchema)
        self.add_endpoint("annotation_sets.list", self.list_annotation_sets, schema=ListAnnotationSetsSchema)
        self.add_endpoint("annotation_sets.update", self.update_annotation_set, schema=UpdateAnnotationSetSchema)

        self.add_endpoint("annotation_records.add", self.add_annotation_records, schema=AddAnnotationRecordsSchema)
        self.add_endpoint("annotation_records.get", self.get_annotation_record, schema=GetAnnotationRecordSchema)
        self.add_endpoint("annotation_records.list", self.list_annotation_records, schema=ListAnnotationRecordsSchema)
        self.add_endpoint("annotation_records.update", self.update_annotation_record, schema=UpdateAnnotationRecordSchema)
        self.add_endpoint("annotation_records.delete", self.delete_annotation_record, schema=DeleteAnnotationRecordSchema)

        self.add_endpoint("datums.create", self.create_datum, schema=CreateDatumSchema)
        self.add_endpoint("datums.get", self.get_datum, schema=GetDatumSchema)
        self.add_endpoint("datums.list", self.list_datums, schema=ListDatumsSchema)
        self.add_endpoint("datums.update", self.update_datum, schema=UpdateDatumSchema)
        self.add_endpoint("datums.resolve", self.resolve_datum, schema=ResolveDatumSchema, as_tool=True)

        self.add_endpoint("dataset_versions.create", self.create_dataset_version, schema=CreateDatasetVersionSchema)
        self.add_endpoint("dataset_versions.get", self.get_dataset_version, schema=GetDatasetVersionSchema, as_tool=True)
        self.add_endpoint("dataset_versions.list", self.list_dataset_versions, schema=ListDatasetVersionsSchema, as_tool=True)
        self.add_endpoint("dataset_versions.resolve", self.resolve_dataset_version, schema=ResolveDatasetVersionSchema, as_tool=True)

    async def _startup_initialize(self) -> None:
        await self._ensure_datalake()

    async def _ensure_datalake(self) -> AsyncDatalake:
        if self._datalake is None:
            if not self.mongo_db_uri or not self.mongo_db_name:
                raise HTTPException(status_code=500, detail="DatalakeService is missing mongo_db_uri and/or mongo_db_name")
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
            raise HTTPException(status_code=500, detail=f"Object payload type is not serializable to base64: {type(data)!r}")
        return base64.b64encode(bytes(data)).decode("utf-8")

    async def health(self) -> DatalakeHealthOutput:
        datalake = await self._ensure_datalake()
        return DatalakeHealthOutput(**(await datalake.get_health()))

    async def summary(self) -> DatalakeSummaryOutput:
        datalake = await self._ensure_datalake()
        return DatalakeSummaryOutput(summary=await datalake.summary())

    async def mounts_info(self) -> MountsOutput:
        datalake = await self._ensure_datalake()
        return MountsOutput(**datalake.get_mounts())

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

    async def get_object(self, payload: GetObjectInput) -> ObjectDataOutput:
        datalake = await self._ensure_datalake()
        obj = await datalake.get_object(payload.storage_ref)
        return ObjectDataOutput(storage_ref=payload.storage_ref, data_base64=self._encode_base64(obj))

    async def head_object(self, payload: HeadObjectInput) -> ObjectHeadOutput:
        datalake = await self._ensure_datalake()
        metadata = await datalake.head_object(payload.storage_ref)
        return ObjectHeadOutput(storage_ref=payload.storage_ref, metadata=metadata)

    async def copy_object(self, payload: CopyObjectInput) -> ObjectOutput:
        datalake = await self._ensure_datalake()
        storage_ref = await datalake.copy_object(
            payload.source,
            target_mount=payload.target_mount,
            target_name=payload.target_name,
            target_version=payload.target_version,
        )
        return ObjectOutput(storage_ref=storage_ref)

    async def create_asset(self, payload: CreateAssetInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        asset = await datalake.create_asset(**payload.model_dump())
        return AssetOutput(asset=asset)

    async def get_asset(self, payload: GetByIdInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        return AssetOutput(asset=await datalake.get_asset(payload.id))

    async def list_assets(self, payload: ListInput) -> AssetListOutput:
        datalake = await self._ensure_datalake()
        return AssetListOutput(assets=await datalake.list_assets(payload.filters))

    async def update_asset_metadata(self, payload: UpdateAssetMetadataInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        asset = await datalake.update_asset_metadata(payload.asset_id, payload.metadata)
        return AssetOutput(asset=asset)

    async def delete_asset(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_asset(payload.id)

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

    async def create_collection(self, payload: CreateCollectionInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.create_collection(**payload.model_dump()))

    async def get_collection(self, payload: GetByIdInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.get_collection(payload.id))

    async def list_collections(self, payload: ListInput) -> CollectionListOutput:
        datalake = await self._ensure_datalake()
        return CollectionListOutput(collections=await datalake.list_collections(payload.filters))

    async def update_collection(self, payload: UpdateCollectionInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.update_collection(payload.collection_id, **payload.changes))

    async def delete_collection(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_collection(payload.id)

    async def create_collection_item(self, payload: CreateCollectionItemInput) -> CollectionItemOutput:
        datalake = await self._ensure_datalake()
        return CollectionItemOutput(collection_item=await datalake.create_collection_item(**payload.model_dump()))

    async def get_collection_item(self, payload: GetByIdInput) -> CollectionItemOutput:
        datalake = await self._ensure_datalake()
        return CollectionItemOutput(collection_item=await datalake.get_collection_item(payload.id))

    async def list_collection_items(self, payload: ListInput) -> CollectionItemListOutput:
        datalake = await self._ensure_datalake()
        return CollectionItemListOutput(collection_items=await datalake.list_collection_items(payload.filters))

    async def resolve_collection_item(self, payload: GetByIdInput) -> ResolvedCollectionItemOutput:
        datalake = await self._ensure_datalake()
        return ResolvedCollectionItemOutput(resolved_collection_item=await datalake.resolve_collection_item(payload.id))

    async def update_collection_item(self, payload: UpdateCollectionItemInput) -> CollectionItemOutput:
        datalake = await self._ensure_datalake()
        item = await datalake.update_collection_item(payload.collection_item_id, **payload.changes)
        return CollectionItemOutput(collection_item=item)

    async def delete_collection_item(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_collection_item(payload.id)

    async def create_asset_retention(self, payload: CreateAssetRetentionInput) -> AssetRetentionOutput:
        datalake = await self._ensure_datalake()
        retention = await datalake.create_asset_retention(**payload.model_dump())
        return AssetRetentionOutput(asset_retention=retention)

    async def get_asset_retention(self, payload: GetByIdInput) -> AssetRetentionOutput:
        datalake = await self._ensure_datalake()
        return AssetRetentionOutput(asset_retention=await datalake.get_asset_retention(payload.id))

    async def list_asset_retentions(self, payload: ListInput) -> AssetRetentionListOutput:
        datalake = await self._ensure_datalake()
        return AssetRetentionListOutput(asset_retentions=await datalake.list_asset_retentions(payload.filters))

    async def update_asset_retention(self, payload: UpdateAssetRetentionInput) -> AssetRetentionOutput:
        datalake = await self._ensure_datalake()
        retention = await datalake.update_asset_retention(payload.asset_retention_id, **payload.changes)
        return AssetRetentionOutput(asset_retention=retention)

    async def delete_asset_retention(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_asset_retention(payload.id)

    async def create_annotation_schema(self, payload: CreateAnnotationSchemaInput) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        schema = await datalake.create_annotation_schema(**payload.model_dump())
        return AnnotationSchemaOutput(annotation_schema=schema)

    async def get_annotation_schema(self, payload: GetByIdInput) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSchemaOutput(annotation_schema=await datalake.get_annotation_schema(payload.id))

    async def get_annotation_schema_by_name_version(
        self, payload: GetAnnotationSchemaByNameVersionInput
    ) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        schema = await datalake.get_annotation_schema_by_name_version(payload.name, payload.version)
        return AnnotationSchemaOutput(annotation_schema=schema)

    async def list_annotation_schemas(self, payload: ListInput) -> AnnotationSchemaListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSchemaListOutput(annotation_schemas=await datalake.list_annotation_schemas(payload.filters))

    async def update_annotation_schema(self, payload: UpdateAnnotationSchemaInput) -> AnnotationSchemaOutput:
        datalake = await self._ensure_datalake()
        schema = await datalake.update_annotation_schema(payload.annotation_schema_id, **payload.changes)
        return AnnotationSchemaOutput(annotation_schema=schema)

    async def delete_annotation_schema(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_annotation_schema(payload.id)

    async def create_annotation_set(self, payload: CreateAnnotationSetInput) -> AnnotationSetOutput:
        datalake = await self._ensure_datalake()
        annotation_set = await datalake.create_annotation_set(**payload.model_dump())
        return AnnotationSetOutput(annotation_set=annotation_set)

    async def get_annotation_set(self, payload: GetByIdInput) -> AnnotationSetOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSetOutput(annotation_set=await datalake.get_annotation_set(payload.id))

    async def list_annotation_sets(self, payload: ListInput) -> AnnotationSetListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationSetListOutput(annotation_sets=await datalake.list_annotation_sets(payload.filters))

    async def update_annotation_set(self, payload: UpdateAnnotationSetInput) -> AnnotationSetOutput:
        datalake = await self._ensure_datalake()
        annotation_set = await datalake.update_annotation_set(payload.annotation_set_id, **payload.changes)
        return AnnotationSetOutput(annotation_set=annotation_set)

    async def add_annotation_records(self, payload: AddAnnotationRecordsInput) -> AddedAnnotationRecordsOutput:
        datalake = await self._ensure_datalake()
        records = await datalake.add_annotation_records(payload.annotation_set_id, payload.annotations)
        return AddedAnnotationRecordsOutput(annotation_records=records)

    async def get_annotation_record(self, payload: GetByIdInput) -> AnnotationRecordOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordOutput(annotation_record=await datalake.get_annotation_record(payload.id))

    async def list_annotation_records(self, payload: ListInput) -> AnnotationRecordListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordListOutput(annotation_records=await datalake.list_annotation_records(payload.filters))

    async def update_annotation_record(self, payload: UpdateAnnotationRecordInput) -> AnnotationRecordOutput:
        datalake = await self._ensure_datalake()
        record = await datalake.update_annotation_record(payload.annotation_id, **payload.changes)
        return AnnotationRecordOutput(annotation_record=record)

    async def delete_annotation_record(self, payload: GetByIdInput) -> None:
        datalake = await self._ensure_datalake()
        await datalake.delete_annotation_record(payload.id)

    async def create_datum(self, payload: CreateDatumInput) -> DatumOutput:
        datalake = await self._ensure_datalake()
        return DatumOutput(datum=await datalake.create_datum(**payload.model_dump()))

    async def get_datum(self, payload: GetByIdInput) -> DatumOutput:
        datalake = await self._ensure_datalake()
        return DatumOutput(datum=await datalake.get_datum(payload.id))

    async def list_datums(self, payload: ListInput) -> DatumListOutput:
        datalake = await self._ensure_datalake()
        return DatumListOutput(datums=await datalake.list_datums(payload.filters))

    async def update_datum(self, payload: UpdateDatumInput) -> DatumOutput:
        datalake = await self._ensure_datalake()
        return DatumOutput(datum=await datalake.update_datum(payload.datum_id, **payload.changes))

    async def resolve_datum(self, payload: GetByIdInput) -> ResolvedDatumOutput:
        datalake = await self._ensure_datalake()
        return ResolvedDatumOutput(resolved_datum=await datalake.resolve_datum(payload.id))

    async def create_dataset_version(self, payload: CreateDatasetVersionInput) -> DatasetVersionOutput:
        datalake = await self._ensure_datalake()
        dataset_version = await datalake.create_dataset_version(**payload.model_dump())
        return DatasetVersionOutput(dataset_version=dataset_version)

    async def get_dataset_version(self, payload: GetDatasetVersionInput) -> DatasetVersionOutput:
        datalake = await self._ensure_datalake()
        dataset_version = await datalake.get_dataset_version(payload.dataset_name, payload.version)
        return DatasetVersionOutput(dataset_version=dataset_version)

    async def list_dataset_versions(self, payload: ListDatasetVersionsInput) -> DatasetVersionListOutput:
        datalake = await self._ensure_datalake()
        versions = await datalake.list_dataset_versions(dataset_name=payload.dataset_name, filters=payload.filters)
        return DatasetVersionListOutput(dataset_versions=versions)

    async def resolve_dataset_version(self, payload: GetDatasetVersionInput) -> ResolvedDatasetVersionOutput:
        datalake = await self._ensure_datalake()
        resolved = await datalake.resolve_dataset_version(payload.dataset_name, payload.version)
        return ResolvedDatasetVersionOutput(resolved_dataset_version=resolved)
