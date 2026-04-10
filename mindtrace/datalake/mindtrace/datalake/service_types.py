from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)


class DatalakeHealthOutput(BaseModel):
    status: str
    database: str
    default_mount: str


DatalakeHealthSchema = TaskSchema(name="health", output_schema=DatalakeHealthOutput)


class DatalakeSummaryOutput(BaseModel):
    summary: str


DatalakeSummarySchema = TaskSchema(name="summary", output_schema=DatalakeSummaryOutput)


class MountsOutput(BaseModel):
    default_mount: str
    mounts: list[dict[str, Any]]


MountsSchema = TaskSchema(name="mounts", output_schema=MountsOutput)


class PutObjectInput(BaseModel):
    name: str
    data_base64: str
    mount: str | None = None
    version: str | None = None
    metadata: dict[str, Any] | None = None
    on_conflict: str | None = None


class GetObjectInput(BaseModel):
    storage_ref: StorageRef


class HeadObjectInput(BaseModel):
    storage_ref: StorageRef


class CopyObjectInput(BaseModel):
    source: StorageRef
    target_mount: str
    target_name: str
    target_version: str | None = None


class ObjectOutput(BaseModel):
    storage_ref: StorageRef


class ObjectDataOutput(BaseModel):
    storage_ref: StorageRef
    data_base64: str


class ObjectHeadOutput(BaseModel):
    storage_ref: StorageRef
    metadata: dict[str, Any]


PutObjectSchema = TaskSchema(name="objects.put", input_schema=PutObjectInput, output_schema=ObjectOutput)
GetObjectSchema = TaskSchema(name="objects.get", input_schema=GetObjectInput, output_schema=ObjectDataOutput)
HeadObjectSchema = TaskSchema(name="objects.head", input_schema=HeadObjectInput, output_schema=ObjectHeadOutput)
CopyObjectSchema = TaskSchema(name="objects.copy", input_schema=CopyObjectInput, output_schema=ObjectOutput)


class CreateAssetInput(BaseModel):
    kind: str
    media_type: str
    storage_ref: StorageRef
    checksum: str | None = None
    size_bytes: int | None = None
    subject: SubjectRef | None = None
    metadata: dict[str, Any] | None = None
    created_by: str | None = None


class GetByIdInput(BaseModel):
    id: str


class ListInput(BaseModel):
    filters: dict[str, Any] | None = None


class UpdateAssetMetadataInput(BaseModel):
    asset_id: str
    metadata: dict[str, Any]


class DeleteByIdInput(BaseModel):
    id: str


class CreateAssetFromObjectInput(BaseModel):
    name: str
    data_base64: str
    kind: str
    media_type: str
    mount: str | None = None
    version: str | None = None
    object_metadata: dict[str, Any] | None = None
    asset_metadata: dict[str, Any] | None = None
    checksum: str | None = None
    size_bytes: int | None = None
    subject: SubjectRef | None = None
    created_by: str | None = None
    on_conflict: str | None = None


class AssetOutput(BaseModel):
    asset: Asset


class AssetListOutput(BaseModel):
    assets: list[Asset]


CreateAssetSchema = TaskSchema(name="assets.create", input_schema=CreateAssetInput, output_schema=AssetOutput)
GetAssetSchema = TaskSchema(name="assets.get", input_schema=GetByIdInput, output_schema=AssetOutput)
ListAssetsSchema = TaskSchema(name="assets.list", input_schema=ListInput, output_schema=AssetListOutput)
UpdateAssetMetadataSchema = TaskSchema(
    name="assets.update_metadata", input_schema=UpdateAssetMetadataInput, output_schema=AssetOutput
)
DeleteAssetSchema = TaskSchema(name="assets.delete", input_schema=DeleteByIdInput, output_schema=None)
CreateAssetFromObjectSchema = TaskSchema(
    name="assets.create_from_object", input_schema=CreateAssetFromObjectInput, output_schema=AssetOutput
)


class CreateCollectionInput(BaseModel):
    name: str
    description: str | None = None
    status: str = "active"
    metadata: dict[str, Any] | None = None
    created_by: str | None = None


class UpdateCollectionInput(BaseModel):
    collection_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class CollectionOutput(BaseModel):
    collection: Collection


class CollectionListOutput(BaseModel):
    collections: list[Collection]


CreateCollectionSchema = TaskSchema(
    name="collections.create", input_schema=CreateCollectionInput, output_schema=CollectionOutput
)
GetCollectionSchema = TaskSchema(name="collections.get", input_schema=GetByIdInput, output_schema=CollectionOutput)
ListCollectionsSchema = TaskSchema(name="collections.list", input_schema=ListInput, output_schema=CollectionListOutput)
UpdateCollectionSchema = TaskSchema(
    name="collections.update", input_schema=UpdateCollectionInput, output_schema=CollectionOutput
)
DeleteCollectionSchema = TaskSchema(name="collections.delete", input_schema=DeleteByIdInput, output_schema=None)


class CreateCollectionItemInput(BaseModel):
    collection_id: str
    asset_id: str
    split: str | None = None
    status: str = "active"
    metadata: dict[str, Any] | None = None
    added_by: str | None = None


class UpdateCollectionItemInput(BaseModel):
    collection_item_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class CollectionItemOutput(BaseModel):
    collection_item: CollectionItem


class CollectionItemListOutput(BaseModel):
    collection_items: list[CollectionItem]


class ResolvedCollectionItemOutput(BaseModel):
    resolved_collection_item: ResolvedCollectionItem


CreateCollectionItemSchema = TaskSchema(
    name="collection_items.create", input_schema=CreateCollectionItemInput, output_schema=CollectionItemOutput
)
GetCollectionItemSchema = TaskSchema(
    name="collection_items.get", input_schema=GetByIdInput, output_schema=CollectionItemOutput
)
ListCollectionItemsSchema = TaskSchema(
    name="collection_items.list", input_schema=ListInput, output_schema=CollectionItemListOutput
)
ResolveCollectionItemSchema = TaskSchema(
    name="collection_items.resolve", input_schema=GetByIdInput, output_schema=ResolvedCollectionItemOutput
)
UpdateCollectionItemSchema = TaskSchema(
    name="collection_items.update", input_schema=UpdateCollectionItemInput, output_schema=CollectionItemOutput
)
DeleteCollectionItemSchema = TaskSchema(name="collection_items.delete", input_schema=DeleteByIdInput, output_schema=None)


class CreateAssetRetentionInput(BaseModel):
    asset_id: str
    owner_type: str
    owner_id: str
    retention_policy: str = "retain"
    metadata: dict[str, Any] | None = None
    created_by: str | None = None


class UpdateAssetRetentionInput(BaseModel):
    asset_retention_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class AssetRetentionOutput(BaseModel):
    asset_retention: AssetRetention


class AssetRetentionListOutput(BaseModel):
    asset_retentions: list[AssetRetention]


CreateAssetRetentionSchema = TaskSchema(
    name="asset_retentions.create", input_schema=CreateAssetRetentionInput, output_schema=AssetRetentionOutput
)
GetAssetRetentionSchema = TaskSchema(
    name="asset_retentions.get", input_schema=GetByIdInput, output_schema=AssetRetentionOutput
)
ListAssetRetentionsSchema = TaskSchema(
    name="asset_retentions.list", input_schema=ListInput, output_schema=AssetRetentionListOutput
)
UpdateAssetRetentionSchema = TaskSchema(
    name="asset_retentions.update", input_schema=UpdateAssetRetentionInput, output_schema=AssetRetentionOutput
)
DeleteAssetRetentionSchema = TaskSchema(name="asset_retentions.delete", input_schema=DeleteByIdInput, output_schema=None)


class CreateAnnotationSchemaInput(BaseModel):
    name: str
    version: str
    task_type: str
    allowed_annotation_kinds: list[str]
    labels: list[dict[str, Any]] | None = None
    allow_scores: bool = False
    required_attributes: list[str] | None = None
    optional_attributes: list[str] | None = None
    allow_additional_attributes: bool = False
    metadata: dict[str, Any] | None = None
    created_by: str | None = None


class GetAnnotationSchemaByNameVersionInput(BaseModel):
    name: str
    version: str


class UpdateAnnotationSchemaInput(BaseModel):
    annotation_schema_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class AnnotationSchemaOutput(BaseModel):
    annotation_schema: AnnotationSchema


class AnnotationSchemaListOutput(BaseModel):
    annotation_schemas: list[AnnotationSchema]


CreateAnnotationSchemaSchema = TaskSchema(
    name="annotation_schemas.create", input_schema=CreateAnnotationSchemaInput, output_schema=AnnotationSchemaOutput
)
GetAnnotationSchemaSchema = TaskSchema(
    name="annotation_schemas.get", input_schema=GetByIdInput, output_schema=AnnotationSchemaOutput
)
GetAnnotationSchemaByNameVersionSchema = TaskSchema(
    name="annotation_schemas.get_by_name_version",
    input_schema=GetAnnotationSchemaByNameVersionInput,
    output_schema=AnnotationSchemaOutput,
)
ListAnnotationSchemasSchema = TaskSchema(
    name="annotation_schemas.list", input_schema=ListInput, output_schema=AnnotationSchemaListOutput
)
UpdateAnnotationSchemaSchema = TaskSchema(
    name="annotation_schemas.update", input_schema=UpdateAnnotationSchemaInput, output_schema=AnnotationSchemaOutput
)
DeleteAnnotationSchemaSchema = TaskSchema(
    name="annotation_schemas.delete", input_schema=DeleteByIdInput, output_schema=None
)


class CreateAnnotationSetInput(BaseModel):
    name: str
    purpose: str
    source_type: str
    status: str = "draft"
    metadata: dict[str, Any] | None = None
    created_by: str | None = None
    datum_id: str | None = None
    annotation_schema_id: str | None = None


class UpdateAnnotationSetInput(BaseModel):
    annotation_set_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class AnnotationSetOutput(BaseModel):
    annotation_set: AnnotationSet


class AnnotationSetListOutput(BaseModel):
    annotation_sets: list[AnnotationSet]


CreateAnnotationSetSchema = TaskSchema(
    name="annotation_sets.create", input_schema=CreateAnnotationSetInput, output_schema=AnnotationSetOutput
)
GetAnnotationSetSchema = TaskSchema(
    name="annotation_sets.get", input_schema=GetByIdInput, output_schema=AnnotationSetOutput
)
ListAnnotationSetsSchema = TaskSchema(
    name="annotation_sets.list", input_schema=ListInput, output_schema=AnnotationSetListOutput
)
UpdateAnnotationSetSchema = TaskSchema(
    name="annotation_sets.update", input_schema=UpdateAnnotationSetInput, output_schema=AnnotationSetOutput
)


class AddAnnotationRecordsInput(BaseModel):
    annotation_set_id: str
    annotations: list[dict[str, Any]]


class UpdateAnnotationRecordInput(BaseModel):
    annotation_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class AnnotationRecordOutput(BaseModel):
    annotation_record: AnnotationRecord


class AnnotationRecordListOutput(BaseModel):
    annotation_records: list[AnnotationRecord]


class AddedAnnotationRecordsOutput(BaseModel):
    annotation_records: list[AnnotationRecord]


AddAnnotationRecordsSchema = TaskSchema(
    name="annotation_records.add", input_schema=AddAnnotationRecordsInput, output_schema=AddedAnnotationRecordsOutput
)
GetAnnotationRecordSchema = TaskSchema(
    name="annotation_records.get", input_schema=GetByIdInput, output_schema=AnnotationRecordOutput
)
ListAnnotationRecordsSchema = TaskSchema(
    name="annotation_records.list", input_schema=ListInput, output_schema=AnnotationRecordListOutput
)
UpdateAnnotationRecordSchema = TaskSchema(
    name="annotation_records.update", input_schema=UpdateAnnotationRecordInput, output_schema=AnnotationRecordOutput
)
DeleteAnnotationRecordSchema = TaskSchema(
    name="annotation_records.delete", input_schema=DeleteByIdInput, output_schema=None
)


class CreateDatumInput(BaseModel):
    asset_refs: dict[str, str]
    split: str | None = None
    metadata: dict[str, Any] | None = None
    annotation_set_ids: list[str] | None = None


class UpdateDatumInput(BaseModel):
    datum_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class DatumOutput(BaseModel):
    datum: Datum


class DatumListOutput(BaseModel):
    datums: list[Datum]


class ResolvedDatumOutput(BaseModel):
    resolved_datum: ResolvedDatum


CreateDatumSchema = TaskSchema(name="datums.create", input_schema=CreateDatumInput, output_schema=DatumOutput)
GetDatumSchema = TaskSchema(name="datums.get", input_schema=GetByIdInput, output_schema=DatumOutput)
ListDatumsSchema = TaskSchema(name="datums.list", input_schema=ListInput, output_schema=DatumListOutput)
UpdateDatumSchema = TaskSchema(name="datums.update", input_schema=UpdateDatumInput, output_schema=DatumOutput)
ResolveDatumSchema = TaskSchema(name="datums.resolve", input_schema=GetByIdInput, output_schema=ResolvedDatumOutput)


class CreateDatasetVersionInput(BaseModel):
    dataset_name: str
    version: str
    manifest: list[str]
    description: str | None = None
    source_dataset_version_id: str | None = None
    metadata: dict[str, Any] | None = None
    created_by: str | None = None


class GetDatasetVersionInput(BaseModel):
    dataset_name: str
    version: str


class ListDatasetVersionsInput(BaseModel):
    dataset_name: str | None = None
    filters: dict[str, Any] | None = None


class DatasetVersionOutput(BaseModel):
    dataset_version: DatasetVersion


class DatasetVersionListOutput(BaseModel):
    dataset_versions: list[DatasetVersion]


class ResolvedDatasetVersionOutput(BaseModel):
    resolved_dataset_version: ResolvedDatasetVersion


CreateDatasetVersionSchema = TaskSchema(
    name="dataset_versions.create", input_schema=CreateDatasetVersionInput, output_schema=DatasetVersionOutput
)
GetDatasetVersionSchema = TaskSchema(
    name="dataset_versions.get", input_schema=GetDatasetVersionInput, output_schema=DatasetVersionOutput
)
ListDatasetVersionsSchema = TaskSchema(
    name="dataset_versions.list", input_schema=ListDatasetVersionsInput, output_schema=DatasetVersionListOutput
)
ResolveDatasetVersionSchema = TaskSchema(
    name="dataset_versions.resolve",
    input_schema=GetDatasetVersionInput,
    output_schema=ResolvedDatasetVersionOutput,
)
