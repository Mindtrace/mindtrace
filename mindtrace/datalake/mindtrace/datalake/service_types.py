from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mindtrace.core import TaskSchema
from mindtrace.datalake.pagination_types import (
    CursorPage,
    DatasetViewPage,
    DatasetViewRequest,
    PageRequest,
)
from mindtrace.datalake.replication_types import (
    ReplicationBatchRequest,
    ReplicationBatchResult,
    ReplicationReclaimRequest,
    ReplicationReclaimResult,
    ReplicationReconcileRequest,
    ReplicationReconcileResult,
    ReplicationStatusResult,
)
from mindtrace.datalake.sync_types import (
    DatasetSyncBundle,
    DatasetSyncCommitResult,
    DatasetSyncImportPlan,
    DatasetSyncImportRequest,
    DatasetSyncProgress,
    ObjectPayloadDescriptor,
)
from mindtrace.datalake.types import (
    REPLICATION_TASK_PURGEABLE_STATUSES,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    AssetAlias,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    DirectUploadSession,
    ReplicationEntityKind,
    ReplicationHydratePolicy,
    ReplicationTask,
    ReplicationTaskStatus,
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


class DatalakeWipeInput(BaseModel):
    delete_payloads: bool = True
    delete_metadata: bool = True
    clear_registry_metadata: bool = False


class DatalakeWipeOutput(BaseModel):
    database: str
    deleted_payloads: bool
    deleted_metadata: bool
    clear_registry_metadata: bool
    cleared_mounts: list[str] = Field(default_factory=list)


MountsSchema = TaskSchema(name="mounts", output_schema=MountsOutput)
DatalakeWipeSchema = TaskSchema(
    name="datalake.wipe",
    input_schema=DatalakeWipeInput,
    output_schema=DatalakeWipeOutput,
)


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


class CreateObjectUploadSessionInput(BaseModel):
    name: str
    mount: str | None = None
    version: str | None = None
    metadata: dict[str, Any] | None = None
    on_conflict: str | None = None
    content_type: str = "application/octet-stream"
    expires_in_minutes: int = 60
    created_by: str | None = None


class CompleteObjectUploadSessionInput(BaseModel):
    upload_session_id: str
    finalize_token: str
    metadata: dict[str, Any] | None = None


class ObjectUploadSessionOutput(BaseModel):
    upload_session_id: str
    finalize_token: str
    name: str
    mount: str
    requested_version: str | None = None
    resolved_version: str | None = None
    upload_method: str
    upload_url: str | None = None
    upload_path: str | None = None
    upload_headers: dict[str, str] = Field(default_factory=dict)
    content_type: str
    status: str
    storage_ref: StorageRef | None = None
    failure_reason: str | None = None
    verification_attempts: int = 0
    last_verified_at: datetime | None = None
    expires_at: datetime
    completed_at: datetime | None = None
    cleanup_completed_at: datetime | None = None

    @classmethod
    def from_session(cls, session: DirectUploadSession) -> "ObjectUploadSessionOutput":
        return cls(
            upload_session_id=session.upload_session_id,
            finalize_token=session.finalize_token,
            name=session.name,
            mount=session.mount,
            requested_version=session.requested_version,
            resolved_version=session.resolved_version,
            upload_method=session.upload_method,
            upload_url=session.upload_url,
            upload_path=session.upload_path,
            upload_headers=session.upload_headers,
            content_type=session.content_type,
            status=session.status,
            storage_ref=session.storage_ref,
            failure_reason=session.failure_reason,
            verification_attempts=session.verification_attempts,
            last_verified_at=session.last_verified_at,
            expires_at=session.expires_at,
            completed_at=session.completed_at,
            cleanup_completed_at=session.cleanup_completed_at,
        )


PutObjectSchema = TaskSchema(name="objects.put", input_schema=PutObjectInput, output_schema=ObjectOutput)
GetObjectSchema = TaskSchema(name="objects.get", input_schema=GetObjectInput, output_schema=ObjectDataOutput)
HeadObjectSchema = TaskSchema(name="objects.head", input_schema=HeadObjectInput, output_schema=ObjectHeadOutput)
CopyObjectSchema = TaskSchema(name="objects.copy", input_schema=CopyObjectInput, output_schema=ObjectOutput)
CreateObjectUploadSessionSchema = TaskSchema(
    name="objects.upload_session.create",
    input_schema=CreateObjectUploadSessionInput,
    output_schema=ObjectUploadSessionOutput,
)
CompleteObjectUploadSessionSchema = TaskSchema(
    name="objects.upload_session.complete",
    input_schema=CompleteObjectUploadSessionInput,
    output_schema=ObjectUploadSessionOutput,
)


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


class GetAssetByAliasInput(BaseModel):
    alias: str


class AddAliasInput(BaseModel):
    asset_id: str
    alias: str


class ListInput(BaseModel):
    filters: dict[str, Any] | None = None


class PageInput(PageRequest):
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


class AssetAliasOutput(BaseModel):
    asset_alias: AssetAlias


class AssetListOutput(BaseModel):
    assets: list[Asset]


class AssetPageOutput(CursorPage[Asset]):
    pass


class CreateAssetFromUploadedObjectInput(BaseModel):
    kind: str
    media_type: str
    storage_ref: StorageRef
    checksum: str | None = None
    size_bytes: int | None = None
    subject: SubjectRef | None = None
    metadata: dict[str, Any] | None = None
    created_by: str | None = None


CreateAssetSchema = TaskSchema(name="assets.create", input_schema=CreateAssetInput, output_schema=AssetOutput)
GetAssetSchema = TaskSchema(name="assets.get", input_schema=GetByIdInput, output_schema=AssetOutput)
GetAssetByAliasSchema = TaskSchema(
    name="assets.get_by_alias", input_schema=GetAssetByAliasInput, output_schema=AssetOutput
)
AddAliasSchema = TaskSchema(name="aliases.add", input_schema=AddAliasInput, output_schema=AssetAliasOutput)
ListAssetsSchema = TaskSchema(name="assets.list", input_schema=ListInput, output_schema=AssetListOutput)
ListAssetsPageSchema = TaskSchema(name="assets.list_page", input_schema=PageInput, output_schema=AssetPageOutput)
UpdateAssetMetadataSchema = TaskSchema(
    name="assets.update_metadata", input_schema=UpdateAssetMetadataInput, output_schema=AssetOutput
)
DeleteAssetSchema = TaskSchema(name="assets.delete", input_schema=DeleteByIdInput, output_schema=None)
CreateAssetFromObjectSchema = TaskSchema(
    name="assets.create_from_object", input_schema=CreateAssetFromObjectInput, output_schema=AssetOutput
)
CreateAssetFromUploadedObjectSchema = TaskSchema(
    name="assets.create_from_uploaded_object",
    input_schema=CreateAssetFromUploadedObjectInput,
    output_schema=AssetOutput,
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


class CollectionPageOutput(CursorPage[Collection]):
    pass


CreateCollectionSchema = TaskSchema(
    name="collections.create", input_schema=CreateCollectionInput, output_schema=CollectionOutput
)
GetCollectionSchema = TaskSchema(name="collections.get", input_schema=GetByIdInput, output_schema=CollectionOutput)
ListCollectionsSchema = TaskSchema(name="collections.list", input_schema=ListInput, output_schema=CollectionListOutput)
ListCollectionsPageSchema = TaskSchema(
    name="collections.list_page", input_schema=PageInput, output_schema=CollectionPageOutput
)
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


class CollectionItemPageOutput(CursorPage[CollectionItem]):
    pass


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
ListCollectionItemsPageSchema = TaskSchema(
    name="collection_items.list_page", input_schema=PageInput, output_schema=CollectionItemPageOutput
)
ResolveCollectionItemSchema = TaskSchema(
    name="collection_items.resolve", input_schema=GetByIdInput, output_schema=ResolvedCollectionItemOutput
)
UpdateCollectionItemSchema = TaskSchema(
    name="collection_items.update", input_schema=UpdateCollectionItemInput, output_schema=CollectionItemOutput
)
DeleteCollectionItemSchema = TaskSchema(
    name="collection_items.delete", input_schema=DeleteByIdInput, output_schema=None
)


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


class AssetRetentionPageOutput(CursorPage[AssetRetention]):
    pass


CreateAssetRetentionSchema = TaskSchema(
    name="asset_retentions.create", input_schema=CreateAssetRetentionInput, output_schema=AssetRetentionOutput
)
GetAssetRetentionSchema = TaskSchema(
    name="asset_retentions.get", input_schema=GetByIdInput, output_schema=AssetRetentionOutput
)
ListAssetRetentionsSchema = TaskSchema(
    name="asset_retentions.list", input_schema=ListInput, output_schema=AssetRetentionListOutput
)
ListAssetRetentionsPageSchema = TaskSchema(
    name="asset_retentions.list_page", input_schema=PageInput, output_schema=AssetRetentionPageOutput
)
UpdateAssetRetentionSchema = TaskSchema(
    name="asset_retentions.update", input_schema=UpdateAssetRetentionInput, output_schema=AssetRetentionOutput
)
DeleteAssetRetentionSchema = TaskSchema(
    name="asset_retentions.delete", input_schema=DeleteByIdInput, output_schema=None
)


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


class AnnotationSchemaPageOutput(CursorPage[AnnotationSchema]):
    pass


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
ListAnnotationSchemasPageSchema = TaskSchema(
    name="annotation_schemas.list_page", input_schema=PageInput, output_schema=AnnotationSchemaPageOutput
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


class AnnotationSetPageOutput(CursorPage[AnnotationSet]):
    pass


CreateAnnotationSetSchema = TaskSchema(
    name="annotation_sets.create", input_schema=CreateAnnotationSetInput, output_schema=AnnotationSetOutput
)
GetAnnotationSetSchema = TaskSchema(
    name="annotation_sets.get", input_schema=GetByIdInput, output_schema=AnnotationSetOutput
)
ListAnnotationSetsSchema = TaskSchema(
    name="annotation_sets.list", input_schema=ListInput, output_schema=AnnotationSetListOutput
)
ListAnnotationSetsPageSchema = TaskSchema(
    name="annotation_sets.list_page", input_schema=PageInput, output_schema=AnnotationSetPageOutput
)
UpdateAnnotationSetSchema = TaskSchema(
    name="annotation_sets.update", input_schema=UpdateAnnotationSetInput, output_schema=AnnotationSetOutput
)


class AddAnnotationRecordsInput(BaseModel):
    annotations: list[dict[str, Any]]
    annotation_set_id: str | None = None
    annotation_schema_id: str | None = None


class ListAnnotationRecordsForAssetInput(BaseModel):
    asset_id: str


class ListAnnotationRecordsForAssetPageInput(PageRequest):
    asset_id: str


class UpdateAnnotationRecordInput(BaseModel):
    annotation_id: str
    changes: dict[str, Any] = Field(default_factory=dict)


class AnnotationRecordOutput(BaseModel):
    annotation_record: AnnotationRecord


class AnnotationRecordListOutput(BaseModel):
    annotation_records: list[AnnotationRecord]


class AnnotationRecordPageOutput(CursorPage[AnnotationRecord]):
    pass


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
ListAnnotationRecordsPageSchema = TaskSchema(
    name="annotation_records.list_page", input_schema=PageInput, output_schema=AnnotationRecordPageOutput
)
ListAnnotationRecordsForAssetSchema = TaskSchema(
    name="annotation_records.list_for_asset",
    input_schema=ListAnnotationRecordsForAssetInput,
    output_schema=AnnotationRecordListOutput,
)
ListAnnotationRecordsForAssetPageSchema = TaskSchema(
    name="annotation_records.list_for_asset_page",
    input_schema=ListAnnotationRecordsForAssetPageInput,
    output_schema=AnnotationRecordPageOutput,
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


class DatumPageOutput(CursorPage[Datum]):
    pass


class ResolvedDatumOutput(BaseModel):
    resolved_datum: ResolvedDatum


CreateDatumSchema = TaskSchema(name="datums.create", input_schema=CreateDatumInput, output_schema=DatumOutput)
GetDatumSchema = TaskSchema(name="datums.get", input_schema=GetByIdInput, output_schema=DatumOutput)
ListDatumsSchema = TaskSchema(name="datums.list", input_schema=ListInput, output_schema=DatumListOutput)
ListDatumsPageSchema = TaskSchema(name="datums.list_page", input_schema=PageInput, output_schema=DatumPageOutput)
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


class ListDatasetVersionsPageInput(PageInput):
    dataset_name: str | None = None


class ViewDatasetVersionPageInput(DatasetViewRequest):
    dataset_name: str
    version: str


class DatasetVersionOutput(BaseModel):
    dataset_version: DatasetVersion


class DatasetVersionListOutput(BaseModel):
    dataset_versions: list[DatasetVersion]


class DatasetVersionPageOutput(CursorPage[DatasetVersion]):
    pass


class ResolvedDatasetVersionOutput(BaseModel):
    resolved_dataset_version: ResolvedDatasetVersion


class DatasetViewPageOutput(DatasetViewPage):
    pass


CreateDatasetVersionSchema = TaskSchema(
    name="dataset_versions.create", input_schema=CreateDatasetVersionInput, output_schema=DatasetVersionOutput
)
GetDatasetVersionSchema = TaskSchema(
    name="dataset_versions.get", input_schema=GetDatasetVersionInput, output_schema=DatasetVersionOutput
)
ListDatasetVersionsSchema = TaskSchema(
    name="dataset_versions.list", input_schema=ListDatasetVersionsInput, output_schema=DatasetVersionListOutput
)
ListDatasetVersionsPageSchema = TaskSchema(
    name="dataset_versions.list_page",
    input_schema=ListDatasetVersionsPageInput,
    output_schema=DatasetVersionPageOutput,
)
ResolveDatasetVersionSchema = TaskSchema(
    name="dataset_versions.resolve",
    input_schema=GetDatasetVersionInput,
    output_schema=ResolvedDatasetVersionOutput,
)
ViewDatasetVersionPageSchema = TaskSchema(
    name="dataset_versions.view_page",
    input_schema=ViewDatasetVersionPageInput,
    output_schema=DatasetViewPageOutput,
)


class ExportDatasetVersionInput(BaseModel):
    dataset_name: str
    version: str


class DatasetSyncBundleOutput(BaseModel):
    bundle: DatasetSyncBundle


class DatasetSyncGraphExportOutput(BaseModel):
    bundle: DatasetSyncBundle


class DatasetSyncPayloadManifestOutput(BaseModel):
    payloads: list[ObjectPayloadDescriptor] = Field(default_factory=list)


class DatasetSyncImportGraphInput(BaseModel):
    session_id: str


class DatasetSyncImportGraphOutput(BaseModel):
    result: DatasetSyncCommitResult


class DatasetSyncHydratePayloadsInput(BaseModel):
    session_id: str
    asset_id: str
    data_base64: str


class DatasetSyncHydratePayloadsOutput(BaseModel):
    storage_ref: StorageRef


class DatasetSyncFinalizeGraphInput(BaseModel):
    session_id: str


class DatasetSyncImportPlanOutput(BaseModel):
    plan: DatasetSyncImportPlan


class DatasetSyncCommitResultOutput(BaseModel):
    result: DatasetSyncCommitResult


class DatasetImportSessionStartOutput(BaseModel):
    session_id: str
    required_asset_ids: list[str] = Field(
        default_factory=list,
        description="Asset ids whose payload bytes must be uploaded before import_session_commit.",
    )
    expires_at: datetime


class DatasetImportSessionUploadInput(BaseModel):
    session_id: str
    asset_id: str
    data_base64: str


class DatasetImportSessionUploadOutput(BaseModel):
    storage_ref: StorageRef


class DatasetImportSessionCommitInput(BaseModel):
    session_id: str


class DatasetImportSessionStatusInput(BaseModel):
    """Poll import session lifecycle and persisted progress."""

    session_id: str


class DatasetImportSessionStatusOutput(BaseModel):
    """Thin projection for callers (bundles omit large payloads)."""

    session_id: str
    status: Literal["open", "committed", "failed"]
    expires_at: datetime
    metadata_graph_committed: bool = False
    session_stage: str | None = None
    required_asset_ids: list[str] = Field(default_factory=list)
    verified_asset_ids: list[str] = Field(default_factory=list)
    required_asset_count: int = 0
    verified_asset_count: int = 0
    pending_asset_count: int = 0
    progress: DatasetSyncProgress | None = None
    import_progress_updated_at: datetime | None = None
    import_progress_error: str | None = None
    metadata_commit_cursor_entity_kind: str | None = None
    metadata_commit_cursor_completed_items: int | None = None
    metadata_commit_cursor_total_items: int | None = None


class DatasetStreamingImportStartInput(BaseModel):
    dataset_name: str
    version: str
    manifest_total: int = Field(default=0, ge=0)
    source_alias: str | None = None
    transfer_policy: str = "copy_if_missing"
    mount_map: dict[str, str] = Field(default_factory=dict)
    preserve_ids: bool = True
    origin_lake_id: str | None = None

    @model_validator(mode="after")
    def _validate_preserve_ids(self) -> DatasetStreamingImportStartInput:
        """Match :class:`~mindtrace.datalake.sync_types.DatasetSyncImportRequest` until ID remapping exists."""
        if not self.preserve_ids:
            raise ValueError(
                "preserve_ids=False is not supported yet; streaming imports preserve source identifiers. "
                "Omit preserve_ids or set it to True."
            )
        return self


class DatasetStreamingImportStartOutput(BaseModel):
    session_id: str
    expires_at: datetime


class DatasetStreamingAssetPayloadInput(BaseModel):
    asset_id: str
    data_base64: str


class DatasetStreamingImportDatumBatchItem(BaseModel):
    manifest_index: int = Field(ge=0)
    datum: Datum
    assets: list[Asset] = Field(default_factory=list)
    annotation_schemas: list[AnnotationSchema] = Field(default_factory=list)
    annotation_records: list[AnnotationRecord] = Field(default_factory=list)
    annotation_sets: list[AnnotationSet] = Field(default_factory=list)
    payloads: list[DatasetStreamingAssetPayloadInput] = Field(default_factory=list)


class DatasetStreamingImportPushBatchInput(BaseModel):
    session_id: str
    items: list[DatasetStreamingImportDatumBatchItem] = Field(default_factory=list)


class DatasetStreamingImportPushBatchOutput(BaseModel):
    session_id: str
    processed_manifest_items: int = 0
    required_asset_count: int = 0
    verified_asset_count: int = 0
    pending_asset_count: int = 0
    progress: DatasetSyncProgress | None = None


class DatasetStreamingImportFinalizeInput(BaseModel):
    session_id: str


class DatasetIntegrityVerifyInput(BaseModel):
    dataset_name: str
    version: str
    mode: Literal["fast", "full-db", "full-lake"] = "fast"
    sample_limit: int = Field(default=25, ge=1, le=500)


class DatasetIntegrityIssueSample(BaseModel):
    kind: str
    id: str
    detail: str | None = None


class DatasetIntegrityVerifyOutput(BaseModel):
    ok: bool
    dataset_name: str
    version: str
    mode: Literal["fast", "full-db", "full-lake"]
    manifest_count: int = 0
    resolved_manifest_count: int = 0
    duplicate_manifest_count: int = 0
    missing_manifest_datum_count: int = 0
    missing_asset_count: int = 0
    missing_annotation_set_count: int = 0
    missing_annotation_record_count: int = 0
    missing_annotation_schema_count: int = 0
    missing_mask_asset_count: int = 0
    registry_missing_payload_count: int = 0
    invalid_mount_count: int = 0
    samples: list[DatasetIntegrityIssueSample] = Field(default_factory=list)


DatasetSyncJobMode = Literal["prepare", "import", "fast_sync"]
DatasetSyncJobStatus = Literal["queued", "running", "completed", "failed"]


class DatasetSyncJobStartOutput(BaseModel):
    job_id: str
    mode: DatasetSyncJobMode
    status: DatasetSyncJobStatus
    progress: DatasetSyncProgress


class DatasetSyncJobStatusInput(BaseModel):
    job_id: str


class DatasetSyncJobErrorDetail(BaseModel):
    """Structured failure diagnostics for dataset sync/async import jobs."""

    exception_type: str = Field(description="Fully qualified exception class name when helpful, else simple name.")
    exception_repr: str = Field(description="repr(exc)", max_length=32_768)
    traceback: str | None = Field(default=None, description="traceback.format_exc() from the failing task.")


class DatasetSyncJobStatusOutput(BaseModel):
    job_id: str
    mode: DatasetSyncJobMode
    status: DatasetSyncJobStatus
    progress: DatasetSyncProgress
    error: str | None = Field(
        default=None,
        description="Short failure summary (exception type plus repr(exc), not bare str(exc) alone).",
    )
    error_detail: DatasetSyncJobErrorDetail | None = None


class DatasetSyncJobResultOutput(BaseModel):
    job_id: str
    mode: DatasetSyncJobMode
    status: DatasetSyncJobStatus
    progress: DatasetSyncProgress
    plan: DatasetSyncImportPlan | None = None
    result: DatasetSyncCommitResult | None = None
    error: str | None = None
    error_detail: DatasetSyncJobErrorDetail | None = None


class ReplicationHydrateAssetPayloadInput(BaseModel):
    asset_id: str
    mount_map: dict[str, str] = Field(default_factory=dict)


class ReplicationMarkLocalDeleteEligibleInput(BaseModel):
    asset_id: str
    when: datetime | None = None


class ReplicationTaskOutput(BaseModel):
    task: ReplicationTask


class ReplicationTaskListInput(BaseModel):
    status: ReplicationTaskStatus | None = None
    target_lake_id: str | None = None
    root_kind: ReplicationEntityKind | None = None
    rule_id: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class ReplicationTaskListOutput(BaseModel):
    tasks: list[ReplicationTask] = Field(default_factory=list)


class ReplicationTaskEnqueueInput(BaseModel):
    target_lake_id: str
    root_kind: ReplicationEntityKind
    root_id: str
    rule_id: str | None = None
    dedupe_key: str | None = None
    source_version: str | None = None
    hydrate_policy: ReplicationHydratePolicy = "async"
    mount_map: dict[str, str] = Field(default_factory=dict)
    include_graph: bool = True
    max_attempts: int = Field(default=5, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplicationTaskEnqueueOutput(BaseModel):
    task: ReplicationTask
    created: bool


class ReplicationTaskClaimInput(BaseModel):
    worker_id: str
    limit: int = Field(default=10, ge=1, le=100)
    lease_seconds: int = Field(default=300, ge=1)


class ReplicationTaskClaimOutput(BaseModel):
    tasks: list[ReplicationTask] = Field(default_factory=list)


class ReplicationTaskStatusUpdateInput(BaseModel):
    task_id: str
    status: ReplicationTaskStatus
    worker_id: str | None = None
    error: str | None = None
    progress_phase: str | None = None
    progress_message: str | None = None
    completed_items: int | None = None
    total_items: int | None = None
    bytes_completed: int | None = None
    bytes_total: int | None = None


class ReplicationTaskFailInput(BaseModel):
    task_id: str
    error: str
    worker_id: str | None = None
    retry_delay_seconds: int = Field(default=60, ge=0)


class ReplicationTaskIdInput(BaseModel):
    task_id: str


class ReplicationTaskPurgeInput(BaseModel):
    older_than_seconds: int = Field(
        default=86_400,
        ge=3600,
        le=366 * 24 * 3600,
        description="Only purge tasks whose completed_at is at least this many seconds before evaluation time.",
    )
    statuses: list[ReplicationTaskStatus] | None = Field(
        default=None,
        description="Archival statuses to remove; default complete, dead, cancelled.",
    )
    limit: int = Field(default=500, ge=1, le=5000)
    dry_run: bool = Field(default=False, description="If true, report matches without deleting.")
    purge_secret: str | None = Field(
        default=None,
        description="When the service is constructed with replication_task_purge_secret, this must match.",
    )

    @field_validator("statuses")
    @classmethod
    def _statuses_archival_only(cls, v: list[ReplicationTaskStatus] | None) -> list[ReplicationTaskStatus] | None:
        if v is None:
            return None
        for s in v:
            if s not in REPLICATION_TASK_PURGEABLE_STATUSES:
                raise ValueError(
                    f"Purge only supports archival statuses {sorted(REPLICATION_TASK_PURGEABLE_STATUSES)}; got {s!r}"
                )
        return v


class ReplicationTaskPurgeOutput(BaseModel):
    dry_run: bool
    cutoff: datetime
    total_candidates: int
    selected_count: int
    deleted_count: int
    deleted_task_ids: list[str] = Field(default_factory=list)


class ReplicationBatchResultOutput(BaseModel):
    result: ReplicationBatchResult


class ReplicationReconcileResultOutput(BaseModel):
    result: ReplicationReconcileResult


class ReplicationReclaimResultOutput(BaseModel):
    result: ReplicationReclaimResult


class ReplicationStatusOutput(BaseModel):
    status: ReplicationStatusResult


ExportDatasetVersionSchema = TaskSchema(
    name="dataset_versions.export",
    input_schema=ExportDatasetVersionInput,
    output_schema=DatasetSyncBundleOutput,
)
DatasetSyncGraphExportSchema = TaskSchema(
    name="dataset_versions.export_sync_graph",
    input_schema=ExportDatasetVersionInput,
    output_schema=DatasetSyncGraphExportOutput,
)
DatasetSyncPayloadManifestSchema = TaskSchema(
    name="dataset_versions.export_sync_payload_manifest",
    input_schema=ExportDatasetVersionInput,
    output_schema=DatasetSyncPayloadManifestOutput,
)
DatasetSyncImportGraphSchema = TaskSchema(
    name="dataset_sync.import_graph",
    input_schema=DatasetSyncImportGraphInput,
    output_schema=DatasetSyncImportGraphOutput,
)
DatasetSyncHydratePayloadsSchema = TaskSchema(
    name="dataset_sync.hydrate_payload",
    input_schema=DatasetSyncHydratePayloadsInput,
    output_schema=DatasetSyncHydratePayloadsOutput,
)
DatasetSyncFinalizeGraphSchema = TaskSchema(
    name="dataset_sync.finalize_graph",
    input_schema=DatasetSyncFinalizeGraphInput,
    output_schema=DatasetSyncCommitResultOutput,
)
DatasetSyncImportPrepareSchema = TaskSchema(
    name="dataset_versions.import_prepare",
    input_schema=DatasetSyncImportRequest,
    output_schema=DatasetSyncImportPlanOutput,
)
DatasetSyncImportCommitSchema = TaskSchema(
    name="dataset_versions.import_commit",
    input_schema=DatasetSyncImportRequest,
    output_schema=DatasetSyncCommitResultOutput,
)
DatasetSyncImportPrepareStartSchema = TaskSchema(
    name="dataset_versions.import_prepare_start",
    input_schema=DatasetSyncImportRequest,
    output_schema=DatasetSyncJobStartOutput,
)
DatasetSyncImportStartSchema = TaskSchema(
    name="dataset_versions.import_start",
    input_schema=DatasetSyncImportRequest,
    output_schema=DatasetSyncJobStartOutput,
)
DatasetSyncImportJobStatusSchema = TaskSchema(
    name="dataset_versions.import_job_status",
    input_schema=DatasetSyncJobStatusInput,
    output_schema=DatasetSyncJobStatusOutput,
)
DatasetSyncImportJobResultSchema = TaskSchema(
    name="dataset_versions.import_job_result",
    input_schema=DatasetSyncJobStatusInput,
    output_schema=DatasetSyncJobResultOutput,
)
DatasetImportSessionStartSchema = TaskSchema(
    name="dataset_versions.import_session_start",
    input_schema=DatasetSyncImportRequest,
    output_schema=DatasetImportSessionStartOutput,
)
DatasetImportSessionUploadSchema = TaskSchema(
    name="dataset_versions.import_session_upload_payload",
    input_schema=DatasetImportSessionUploadInput,
    output_schema=DatasetImportSessionUploadOutput,
)
DatasetImportSessionCommitSchema = TaskSchema(
    name="dataset_versions.import_session_commit",
    input_schema=DatasetImportSessionCommitInput,
    output_schema=DatasetSyncCommitResultOutput,
)
DatasetImportSessionCommitMetadataSchema = TaskSchema(
    name="dataset_versions.import_session_commit_metadata",
    input_schema=DatasetImportSessionCommitInput,
    output_schema=DatasetSyncCommitResultOutput,
)
DatasetImportSessionStatusSchema = TaskSchema(
    name="dataset_versions.import_session_status",
    input_schema=DatasetImportSessionStatusInput,
    output_schema=DatasetImportSessionStatusOutput,
)
DatasetStreamingImportStartSchema = TaskSchema(
    name="dataset_versions.streaming_import_start",
    input_schema=DatasetStreamingImportStartInput,
    output_schema=DatasetStreamingImportStartOutput,
)
DatasetStreamingImportPushBatchSchema = TaskSchema(
    name="dataset_versions.streaming_import_push_batch",
    input_schema=DatasetStreamingImportPushBatchInput,
    output_schema=DatasetStreamingImportPushBatchOutput,
)
DatasetStreamingImportFinalizeSchema = TaskSchema(
    name="dataset_versions.streaming_import_finalize",
    input_schema=DatasetStreamingImportFinalizeInput,
    output_schema=DatasetSyncCommitResultOutput,
)
DatasetIntegrityVerifySchema = TaskSchema(
    name="dataset_versions.verify_integrity",
    input_schema=DatasetIntegrityVerifyInput,
    output_schema=DatasetIntegrityVerifyOutput,
)
ReplicationBatchUpsertSchema = TaskSchema(
    name="replication.upsert_batch",
    input_schema=ReplicationBatchRequest,
    output_schema=ReplicationBatchResultOutput,
)
ReplicationHydrateAssetPayloadSchema = TaskSchema(
    name="replication.hydrate_asset_payload",
    input_schema=ReplicationHydrateAssetPayloadInput,
    output_schema=AssetOutput,
)
ReplicationReconcileSchema = TaskSchema(
    name="replication.reconcile",
    input_schema=ReplicationReconcileRequest,
    output_schema=ReplicationReconcileResultOutput,
)
ReplicationMarkLocalDeleteEligibleSchema = TaskSchema(
    name="replication.mark_local_delete_eligible",
    input_schema=ReplicationMarkLocalDeleteEligibleInput,
    output_schema=AssetOutput,
)
ReplicationDeleteLocalPayloadSchema = TaskSchema(
    name="replication.delete_local_payload",
    input_schema=GetByIdInput,
    output_schema=AssetOutput,
)
ReplicationReclaimSchema = TaskSchema(
    name="replication.reclaim_verified_payloads",
    input_schema=ReplicationReclaimRequest,
    output_schema=ReplicationReclaimResultOutput,
)
ReplicationStatusSchema = TaskSchema(
    name="replication.status",
    output_schema=ReplicationStatusOutput,
)

ReplicationTaskEnqueueSchema = TaskSchema(
    name="replication.tasks.enqueue",
    input_schema=ReplicationTaskEnqueueInput,
    output_schema=ReplicationTaskEnqueueOutput,
)

ReplicationTaskListSchema = TaskSchema(
    name="replication.tasks.list",
    input_schema=ReplicationTaskListInput,
    output_schema=ReplicationTaskListOutput,
)

ReplicationTaskGetSchema = TaskSchema(
    name="replication.tasks.get",
    input_schema=ReplicationTaskIdInput,
    output_schema=ReplicationTaskOutput,
)

ReplicationTaskClaimSchema = TaskSchema(
    name="replication.tasks.claim",
    input_schema=ReplicationTaskClaimInput,
    output_schema=ReplicationTaskClaimOutput,
)

ReplicationTaskUpdateStatusSchema = TaskSchema(
    name="replication.tasks.update_status",
    input_schema=ReplicationTaskStatusUpdateInput,
    output_schema=ReplicationTaskOutput,
)

ReplicationTaskFailSchema = TaskSchema(
    name="replication.tasks.fail",
    input_schema=ReplicationTaskFailInput,
    output_schema=ReplicationTaskOutput,
)

ReplicationTaskRetrySchema = TaskSchema(
    name="replication.tasks.retry",
    input_schema=ReplicationTaskIdInput,
    output_schema=ReplicationTaskOutput,
)

ReplicationTaskPurgeSchema = TaskSchema(
    name="replication.tasks.purge",
    input_schema=ReplicationTaskPurgeInput,
    output_schema=ReplicationTaskPurgeOutput,
)
