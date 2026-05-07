from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
import traceback
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from mindtrace.database.core.exceptions import DocumentNotFoundError, DocumentTooLargeError
from mindtrace.datalake.async_datalake import AsyncDatalake, SlowOperationDisabledError, SlowOpsPolicy
from mindtrace.datalake.replication import ReplicationManager
from mindtrace.datalake.replication_queue import ReplicationQueueManager
from mindtrace.datalake.replication_types import ReplicationReclaimRequest, ReplicationReconcileRequest
from mindtrace.datalake.service_types import (
    AddAliasInput,
    AddAliasSchema,
    AddAnnotationRecordsInput,
    AddAnnotationRecordsSchema,
    AddedAnnotationRecordsOutput,
    AnnotationRecordListOutput,
    AnnotationRecordOutput,
    AnnotationRecordPageOutput,
    AnnotationSchemaListOutput,
    AnnotationSchemaOutput,
    AnnotationSchemaPageOutput,
    AnnotationSetListOutput,
    AnnotationSetOutput,
    AnnotationSetPageOutput,
    AssetAliasOutput,
    AssetListOutput,
    AssetOutput,
    AssetPageOutput,
    AssetRetentionListOutput,
    AssetRetentionOutput,
    AssetRetentionPageOutput,
    CollectionItemListOutput,
    CollectionItemOutput,
    CollectionItemPageOutput,
    CollectionListOutput,
    CollectionOutput,
    CollectionPageOutput,
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
    DatalakeWipeInput,
    DatalakeWipeOutput,
    DatalakeWipeSchema,
    DatasetImportSessionCommitInput,
    DatasetImportSessionCommitMetadataSchema,
    DatasetImportSessionCommitSchema,
    DatasetImportSessionStartOutput,
    DatasetImportSessionStartSchema,
    DatasetImportSessionStatusInput,
    DatasetImportSessionStatusOutput,
    DatasetImportSessionStatusSchema,
    DatasetImportSessionUploadInput,
    DatasetImportSessionUploadOutput,
    DatasetImportSessionUploadSchema,
    DatasetIntegrityIssueSample,
    DatasetIntegrityVerifyInput,
    DatasetIntegrityVerifyOutput,
    DatasetIntegrityVerifySchema,
    DatasetStreamingImportFinalizeInput,
    DatasetStreamingImportFinalizeSchema,
    DatasetStreamingImportPushBatchInput,
    DatasetStreamingImportPushBatchOutput,
    DatasetStreamingImportPushBatchSchema,
    DatasetStreamingImportStartInput,
    DatasetStreamingImportStartOutput,
    DatasetStreamingImportStartSchema,
    DatasetSyncBundleOutput,
    DatasetSyncCommitResultOutput,
    DatasetSyncFinalizeGraphInput,
    DatasetSyncFinalizeGraphSchema,
    DatasetSyncGraphExportOutput,
    DatasetSyncGraphExportSchema,
    DatasetSyncHydratePayloadsInput,
    DatasetSyncHydratePayloadsOutput,
    DatasetSyncHydratePayloadsSchema,
    DatasetSyncImportCommitSchema,
    DatasetSyncImportGraphInput,
    DatasetSyncImportGraphOutput,
    DatasetSyncImportGraphSchema,
    DatasetSyncImportJobResultSchema,
    DatasetSyncImportJobStatusSchema,
    DatasetSyncImportPlanOutput,
    DatasetSyncImportPrepareSchema,
    DatasetSyncImportPrepareStartSchema,
    DatasetSyncImportRequest,
    DatasetSyncImportStartSchema,
    DatasetSyncJobErrorDetail,
    DatasetSyncJobResultOutput,
    DatasetSyncJobStartOutput,
    DatasetSyncJobStatusInput,
    DatasetSyncJobStatusOutput,
    DatasetSyncPayloadManifestOutput,
    DatasetSyncPayloadManifestSchema,
    DatasetVersionListOutput,
    DatasetVersionOutput,
    DatasetVersionPageOutput,
    DatasetViewPageOutput,
    DatumListOutput,
    DatumOutput,
    DatumPageOutput,
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
    ListAnnotationRecordsForAssetPageInput,
    ListAnnotationRecordsForAssetPageSchema,
    ListAnnotationRecordsForAssetSchema,
    ListAnnotationRecordsPageSchema,
    ListAnnotationRecordsSchema,
    ListAnnotationSchemasPageSchema,
    ListAnnotationSchemasSchema,
    ListAnnotationSetsPageSchema,
    ListAnnotationSetsSchema,
    ListAssetRetentionsPageSchema,
    ListAssetRetentionsSchema,
    ListAssetsPageSchema,
    ListAssetsSchema,
    ListCollectionItemsPageSchema,
    ListCollectionItemsSchema,
    ListCollectionsPageSchema,
    ListCollectionsSchema,
    ListDatasetVersionsInput,
    ListDatasetVersionsPageInput,
    ListDatasetVersionsPageSchema,
    ListDatasetVersionsSchema,
    ListDatumsPageSchema,
    ListDatumsSchema,
    ListInput,
    MountsOutput,
    MountsSchema,
    ObjectDataOutput,
    ObjectHeadOutput,
    ObjectOutput,
    ObjectUploadSessionOutput,
    PageInput,
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
    ReplicationTaskClaimInput,
    ReplicationTaskClaimOutput,
    ReplicationTaskClaimSchema,
    ReplicationTaskEnqueueInput,
    ReplicationTaskEnqueueOutput,
    ReplicationTaskEnqueueSchema,
    ReplicationTaskFailInput,
    ReplicationTaskFailSchema,
    ReplicationTaskGetSchema,
    ReplicationTaskIdInput,
    ReplicationTaskListInput,
    ReplicationTaskListOutput,
    ReplicationTaskListSchema,
    ReplicationTaskOutput,
    ReplicationTaskPurgeInput,
    ReplicationTaskPurgeOutput,
    ReplicationTaskPurgeSchema,
    ReplicationTaskRetrySchema,
    ReplicationTaskStatusUpdateInput,
    ReplicationTaskUpdateStatusSchema,
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
    ViewDatasetVersionPageInput,
    ViewDatasetVersionPageSchema,
)
from mindtrace.datalake.sync import DatasetSyncManager, _apply_mount_map_to_storage_ref
from mindtrace.datalake.sync_types import (
    DatasetSyncBundle,
    DatasetSyncCommitResult,
    DatasetSyncImportPlan,
    DatasetSyncProgress,
    ObjectPayloadDescriptor,
)
from mindtrace.datalake.types import Asset, DatasetImportSession, StorageRef, utc_now
from mindtrace.registry import Mount
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from mindtrace.services import Service

_LOGGER = logging.getLogger(__name__)


def _import_session_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    """Compare session expiry to current UTC time, treating naive datetimes as UTC (Mongo round-trip)."""
    current = now if now is not None else datetime.now(timezone.utc)
    deadline = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=timezone.utc)
    return current > deadline


class _ImportSessionProgressWriter:
    """Persists incremental ``DatasetSyncProgress`` onto ``DatasetImportSession`` (Mongo writes may be skipped)."""

    def __init__(
        self,
        datalake: AsyncDatalake,
        session: DatasetImportSession,
        *,
        min_interval_s: float = 0.25,
    ) -> None:
        self._datalake = datalake
        self._session = session
        self._min_interval_s = min_interval_s
        self._lock = asyncio.Lock()
        self._last_flush_mono = 0.0
        self._last_flushed_phase: str | None = None

    def _snapshot_to_session(self, progress: DatasetSyncProgress, *, error: str | None) -> None:
        sess = self._session
        sess.import_progress_phase = progress.phase
        sess.import_progress_batch_index = progress.batch_index
        sess.import_progress_total_batches = progress.total_batches
        sess.import_progress_completed_items = progress.completed_items
        sess.import_progress_total_items = progress.total_items
        sess.import_progress_message = progress.message
        sess.import_progress_entity_kind = progress.entity_kind
        sess.import_progress_phase_detail = progress.phase_detail
        sess.import_progress_entity_completed_items = progress.entity_completed_items
        sess.import_progress_entity_total_items = progress.entity_total_items
        sess.import_progress_bytes_completed = progress.bytes_completed
        sess.import_progress_bytes_total = progress.bytes_total
        sess.import_progress_skipped_items = progress.skipped_items
        sess.import_progress_failed_items = progress.failed_items
        sess.import_progress_updated_at = utc_now()
        sess.metadata_commit_cursor_entity_kind = progress.entity_kind
        sess.metadata_commit_cursor_completed_items = progress.entity_completed_items
        sess.metadata_commit_cursor_total_items = progress.entity_total_items
        if progress.phase == "planning":
            sess.import_stage = "planning_metadata_commit"
        elif progress.phase == "committing":
            sess.import_stage = "committing_metadata"
        elif progress.phase == "transferring":
            sess.import_stage = "awaiting_payload_uploads"
        elif progress.phase == "complete":
            if sess.metadata_graph_committed:
                verified = len(sess.verified_asset_ids)
                required = len(sess.required_asset_ids)
                sess.import_stage = "ready_to_finalize" if verified >= required else "awaiting_payload_uploads"
            else:
                sess.import_stage = "metadata_commit_complete"
        elif progress.phase == "failed":
            sess.import_stage = "failed"
        if progress.phase == "failed":
            sess.import_progress_error = error or progress.message
        else:
            sess.import_progress_error = None

    async def persist(self, progress: DatasetSyncProgress, *, error: str | None = None, force: bool = False) -> None:
        async with self._lock:
            terminal = progress.phase in ("complete", "failed")
            phase_changed = progress.phase != self._last_flushed_phase
            now_mono = time.monotonic()
            elapsed = now_mono - self._last_flush_mono
            stale = elapsed >= self._min_interval_s
            if not force and not terminal and not phase_changed and not stale:
                return
            self._snapshot_to_session(progress, error=error)
            await self._datalake.dataset_import_session_database.update(self._session)
            self._last_flush_mono = now_mono
            self._last_flushed_phase = progress.phase

    async def persist_failed(self, detail: str) -> None:
        truncated = detail[:8192]
        await self.persist(
            DatasetSyncProgress(phase="failed", message=truncated),
            error=truncated,
            force=True,
        )

    async def __call__(self, progress: DatasetSyncProgress) -> None:
        await self.persist(progress)


def _dataset_import_session_status_output(session: DatasetImportSession) -> DatasetImportSessionStatusOutput:
    progress_model: DatasetSyncProgress | None = None
    if session.import_progress_phase is not None:
        progress_model = DatasetSyncProgress.model_validate(
            {
                "phase": session.import_progress_phase,
                "batch_index": session.import_progress_batch_index,
                "total_batches": session.import_progress_total_batches,
                "completed_items": session.import_progress_completed_items or 0,
                "total_items": session.import_progress_total_items or 0,
                "message": session.import_progress_message or "",
                "entity_kind": session.import_progress_entity_kind,
                "phase_detail": session.import_progress_phase_detail,
                "entity_completed_items": session.import_progress_entity_completed_items,
                "entity_total_items": session.import_progress_entity_total_items,
                "bytes_completed": session.import_progress_bytes_completed,
                "bytes_total": session.import_progress_bytes_total,
                "skipped_items": session.import_progress_skipped_items,
                "failed_items": session.import_progress_failed_items,
            }
        )

    required_asset_ids = list(session.required_asset_ids)
    verified_asset_ids = list(session.verified_asset_ids)
    pending_asset_count = max(len(required_asset_ids) - len(verified_asset_ids), 0)

    return DatasetImportSessionStatusOutput(
        session_id=session.import_session_id,
        status=session.status,
        expires_at=session.expires_at,
        metadata_graph_committed=session.metadata_graph_committed,
        session_stage=session.import_stage,
        required_asset_ids=required_asset_ids,
        verified_asset_ids=verified_asset_ids,
        required_asset_count=len(required_asset_ids),
        verified_asset_count=len(verified_asset_ids),
        pending_asset_count=pending_asset_count,
        progress=progress_model,
        import_progress_updated_at=session.import_progress_updated_at,
        import_progress_error=session.import_progress_error,
        metadata_commit_cursor_entity_kind=session.metadata_commit_cursor_entity_kind,
        metadata_commit_cursor_completed_items=session.metadata_commit_cursor_completed_items,
        metadata_commit_cursor_total_items=session.metadata_commit_cursor_total_items,
    )


async def _delete_import_session_bundle_blob(datalake: AsyncDatalake, session: DatasetImportSession) -> None:
    if session.bundle_storage_ref is None:
        return
    with suppress(Exception):
        await datalake.delete_object(session.bundle_storage_ref)


async def _load_import_session_bundle(datalake: AsyncDatalake, session: DatasetImportSession) -> DatasetSyncBundle:
    if session.bundle_storage_ref is not None:
        data = await datalake.get_object(session.bundle_storage_ref)
        raw = data if isinstance(data, (bytes, bytearray)) else bytes(data)
        return DatasetSyncBundle.model_validate(json.loads(raw.decode("utf-8")))
    if not session.bundle_data:
        raise ValueError("import session has neither bundle_storage_ref nor bundle_data")
    return DatasetSyncBundle.model_validate(session.bundle_data)


@dataclass
class _DatasetSyncJobState:
    job_id: str
    mode: str
    status: str = "queued"
    progress: DatasetSyncProgress = field(
        default_factory=lambda: DatasetSyncProgress(phase="planning", message="Queued dataset sync job")
    )
    plan: DatasetSyncImportPlan | None = None
    result: DatasetSyncCommitResult | None = None
    error: str | None = None
    error_detail: DatasetSyncJobErrorDetail | None = None
    task: asyncio.Task[None] | None = None


class DatalakeService(Service):
    """FastAPI/MCP service wrapper over ``AsyncDatalake``."""

    def __init__(
        self,
        *,
        mongo_db_uri: str | None = None,
        mongo_db_name: str | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
        slow_ops_policy: SlowOpsPolicy = SlowOpsPolicy.WARN,
        async_datalake: AsyncDatalake | None = None,
        initialize_on_startup: bool = True,
        live_service: bool = True,
        upload_reconcile_interval_seconds: float = 30.0,
        replication_task_purge_secret: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(live_service=live_service, **kwargs)
        self.mongo_db_uri = mongo_db_uri
        self.mongo_db_name = mongo_db_name
        self.mounts = mounts
        self.default_mount = default_mount
        self.slow_ops_policy = (
            async_datalake.slow_ops_policy if async_datalake is not None else SlowOpsPolicy(slow_ops_policy)
        )
        self._datalake: AsyncDatalake | None = async_datalake
        # Only the datalake we construct internally is ours to close.
        # One passed via ``async_datalake=`` is the caller's responsibility.
        self._owns_datalake = async_datalake is None
        self._initialized = async_datalake is not None
        self.initialize_on_startup = initialize_on_startup
        self.upload_reconcile_interval_seconds = upload_reconcile_interval_seconds
        self._upload_reconciler_task: asyncio.Task[None] | None = None
        self._dataset_sync_jobs: dict[str, _DatasetSyncJobState] = {}
        self._replication_task_purge_secret: str | None = replication_task_purge_secret

        if live_service and initialize_on_startup:
            self.app.router.on_startup.append(self._startup_initialize)

        self.add_endpoint("health", self.health, schema=DatalakeHealthSchema, as_tool=True)
        self.add_endpoint("summary", self.summary, schema=DatalakeSummarySchema, as_tool=True)
        self.add_endpoint("mounts", self.mounts_info, schema=MountsSchema)
        self.add_endpoint("datalake.wipe", self.wipe_datalake, schema=DatalakeWipeSchema)

        self.add_endpoint("objects.put", self.put_object, schema=PutObjectSchema)
        self.add_endpoint("objects.get", self.get_object, schema=GetObjectSchema)
        self.add_endpoint("objects.head", self.head_object, schema=HeadObjectSchema)
        self.add_endpoint("objects.copy", self.copy_object, schema=CopyObjectSchema)
        self.add_endpoint(
            "objects.upload_session.create", self.create_object_upload_session, schema=CreateObjectUploadSessionSchema
        )
        self.add_endpoint(
            "objects.upload_session.complete",
            self.complete_object_upload_session,
            schema=CompleteObjectUploadSessionSchema,
        )

        self.add_endpoint("assets.create", self.create_asset, schema=CreateAssetSchema)
        self.add_endpoint("assets.get", self.get_asset, schema=GetAssetSchema, as_tool=True)
        self.add_endpoint("assets.get_by_alias", self.get_asset_by_alias, schema=GetAssetByAliasSchema, as_tool=True)
        self.add_endpoint("assets.list", self.list_assets, schema=ListAssetsSchema)
        self.add_endpoint("assets.list_page", self.list_assets_page, schema=ListAssetsPageSchema)
        self.add_endpoint("assets.update_metadata", self.update_asset_metadata, schema=UpdateAssetMetadataSchema)
        self.add_endpoint("assets.delete", self.delete_asset, schema=DeleteAssetSchema)
        self.add_endpoint("aliases.add", self.add_alias, schema=AddAliasSchema)
        self.add_endpoint(
            "assets.create_from_object", self.create_asset_from_object, schema=CreateAssetFromObjectSchema
        )
        self.add_endpoint(
            "assets.create_from_uploaded_object",
            self.create_asset_from_uploaded_object,
            schema=CreateAssetFromUploadedObjectSchema,
        )

        self.add_endpoint("collections.create", self.create_collection, schema=CreateCollectionSchema)
        self.add_endpoint("collections.get", self.get_collection, schema=GetCollectionSchema)
        self.add_endpoint("collections.list", self.list_collections, schema=ListCollectionsSchema)
        self.add_endpoint("collections.list_page", self.list_collections_page, schema=ListCollectionsPageSchema)
        self.add_endpoint("collections.update", self.update_collection, schema=UpdateCollectionSchema)
        self.add_endpoint("collections.delete", self.delete_collection, schema=DeleteCollectionSchema)

        self.add_endpoint("collection_items.create", self.create_collection_item, schema=CreateCollectionItemSchema)
        self.add_endpoint("collection_items.get", self.get_collection_item, schema=GetCollectionItemSchema)
        self.add_endpoint("collection_items.list", self.list_collection_items, schema=ListCollectionItemsSchema)
        self.add_endpoint(
            "collection_items.list_page", self.list_collection_items_page, schema=ListCollectionItemsPageSchema
        )
        self.add_endpoint("collection_items.resolve", self.resolve_collection_item, schema=ResolveCollectionItemSchema)
        self.add_endpoint("collection_items.update", self.update_collection_item, schema=UpdateCollectionItemSchema)
        self.add_endpoint("collection_items.delete", self.delete_collection_item, schema=DeleteCollectionItemSchema)

        self.add_endpoint("asset_retentions.create", self.create_asset_retention, schema=CreateAssetRetentionSchema)
        self.add_endpoint("asset_retentions.get", self.get_asset_retention, schema=GetAssetRetentionSchema)
        self.add_endpoint("asset_retentions.list", self.list_asset_retentions, schema=ListAssetRetentionsSchema)
        self.add_endpoint(
            "asset_retentions.list_page", self.list_asset_retentions_page, schema=ListAssetRetentionsPageSchema
        )
        self.add_endpoint("asset_retentions.update", self.update_asset_retention, schema=UpdateAssetRetentionSchema)
        self.add_endpoint("asset_retentions.delete", self.delete_asset_retention, schema=DeleteAssetRetentionSchema)

        self.add_endpoint(
            "annotation_schemas.create", self.create_annotation_schema, schema=CreateAnnotationSchemaSchema
        )
        self.add_endpoint("annotation_schemas.get", self.get_annotation_schema, schema=GetAnnotationSchemaSchema)
        self.add_endpoint(
            "annotation_schemas.get_by_name_version",
            self.get_annotation_schema_by_name_version,
            schema=GetAnnotationSchemaByNameVersionSchema,
            as_tool=True,
        )
        self.add_endpoint("annotation_schemas.list", self.list_annotation_schemas, schema=ListAnnotationSchemasSchema)
        self.add_endpoint(
            "annotation_schemas.list_page", self.list_annotation_schemas_page, schema=ListAnnotationSchemasPageSchema
        )
        self.add_endpoint(
            "annotation_schemas.update", self.update_annotation_schema, schema=UpdateAnnotationSchemaSchema
        )
        self.add_endpoint(
            "annotation_schemas.delete", self.delete_annotation_schema, schema=DeleteAnnotationSchemaSchema
        )

        self.add_endpoint("annotation_sets.create", self.create_annotation_set, schema=CreateAnnotationSetSchema)
        self.add_endpoint("annotation_sets.get", self.get_annotation_set, schema=GetAnnotationSetSchema)
        self.add_endpoint("annotation_sets.list", self.list_annotation_sets, schema=ListAnnotationSetsSchema)
        self.add_endpoint(
            "annotation_sets.list_page", self.list_annotation_sets_page, schema=ListAnnotationSetsPageSchema
        )
        self.add_endpoint("annotation_sets.update", self.update_annotation_set, schema=UpdateAnnotationSetSchema)

        self.add_endpoint("annotation_records.add", self.add_annotation_records, schema=AddAnnotationRecordsSchema)
        self.add_endpoint("annotation_records.get", self.get_annotation_record, schema=GetAnnotationRecordSchema)
        self.add_endpoint("annotation_records.list", self.list_annotation_records, schema=ListAnnotationRecordsSchema)
        self.add_endpoint(
            "annotation_records.list_page", self.list_annotation_records_page, schema=ListAnnotationRecordsPageSchema
        )
        self.add_endpoint(
            "annotation_records.list_for_asset",
            self.list_annotation_records_for_asset,
            schema=ListAnnotationRecordsForAssetSchema,
        )
        self.add_endpoint(
            "annotation_records.list_for_asset_page",
            self.list_annotation_records_for_asset_page,
            schema=ListAnnotationRecordsForAssetPageSchema,
        )
        self.add_endpoint(
            "annotation_records.update", self.update_annotation_record, schema=UpdateAnnotationRecordSchema
        )
        self.add_endpoint(
            "annotation_records.delete", self.delete_annotation_record, schema=DeleteAnnotationRecordSchema
        )

        self.add_endpoint("datums.create", self.create_datum, schema=CreateDatumSchema)
        self.add_endpoint("datums.get", self.get_datum, schema=GetDatumSchema)
        self.add_endpoint("datums.list", self.list_datums, schema=ListDatumsSchema)
        self.add_endpoint("datums.list_page", self.list_datums_page, schema=ListDatumsPageSchema)
        self.add_endpoint("datums.update", self.update_datum, schema=UpdateDatumSchema)
        self.add_endpoint("datums.resolve", self.resolve_datum, schema=ResolveDatumSchema, as_tool=True)

        self.add_endpoint("dataset_versions.create", self.create_dataset_version, schema=CreateDatasetVersionSchema)
        self.add_endpoint(
            "dataset_versions.get", self.get_dataset_version, schema=GetDatasetVersionSchema, as_tool=True
        )
        self.add_endpoint(
            "dataset_versions.list", self.list_dataset_versions, schema=ListDatasetVersionsSchema, as_tool=True
        )
        self.add_endpoint(
            "dataset_versions.list_page",
            self.list_dataset_versions_page,
            schema=ListDatasetVersionsPageSchema,
            as_tool=True,
        )
        self.add_endpoint(
            "dataset_versions.resolve", self.resolve_dataset_version, schema=ResolveDatasetVersionSchema, as_tool=True
        )
        self.add_endpoint(
            "dataset_versions.view_page",
            self.view_dataset_version_page,
            schema=ViewDatasetVersionPageSchema,
            as_tool=True,
        )
        self.add_endpoint("dataset_versions.export", self.export_dataset_version, schema=ExportDatasetVersionSchema)
        self.add_endpoint(
            "dataset_versions.export_sync_graph", self.export_sync_graph, schema=DatasetSyncGraphExportSchema
        )
        self.add_endpoint(
            "dataset_versions.export_sync_payload_manifest",
            self.export_sync_payload_manifest,
            schema=DatasetSyncPayloadManifestSchema,
        )
        self.add_endpoint(
            "dataset_sync.import_graph", self.dataset_sync_import_graph, schema=DatasetSyncImportGraphSchema
        )
        self.add_endpoint(
            "dataset_sync.hydrate_payload", self.dataset_sync_hydrate_payload, schema=DatasetSyncHydratePayloadsSchema
        )
        self.add_endpoint(
            "dataset_sync.finalize_graph", self.dataset_sync_finalize_graph, schema=DatasetSyncFinalizeGraphSchema
        )
        self.add_endpoint(
            "dataset_versions.import_prepare",
            self.import_dataset_version_prepare,
            schema=DatasetSyncImportPrepareSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_commit",
            self.import_dataset_version_commit,
            schema=DatasetSyncImportCommitSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_prepare_start",
            self.import_dataset_version_prepare_start,
            schema=DatasetSyncImportPrepareStartSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_start",
            self.import_dataset_version_start,
            schema=DatasetSyncImportStartSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_job_status",
            self.import_dataset_version_job_status,
            schema=DatasetSyncImportJobStatusSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_job_result",
            self.import_dataset_version_job_result,
            schema=DatasetSyncImportJobResultSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_session_start",
            self.import_session_start,
            schema=DatasetImportSessionStartSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_session_commit_metadata",
            self.import_session_commit_metadata,
            schema=DatasetImportSessionCommitMetadataSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_session_status",
            self.import_session_status,
            schema=DatasetImportSessionStatusSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_session_upload_payload",
            self.import_session_upload_payload,
            schema=DatasetImportSessionUploadSchema,
        )
        self.add_endpoint(
            "dataset_versions.import_session_commit",
            self.import_session_commit,
            schema=DatasetImportSessionCommitSchema,
        )
        self.add_endpoint(
            "dataset_versions.streaming_import_start",
            self.streaming_import_start,
            schema=DatasetStreamingImportStartSchema,
        )
        self.add_endpoint(
            "dataset_versions.streaming_import_push_batch",
            self.streaming_import_push_batch,
            schema=DatasetStreamingImportPushBatchSchema,
        )
        self.add_endpoint(
            "dataset_versions.streaming_import_finalize",
            self.streaming_import_finalize,
            schema=DatasetStreamingImportFinalizeSchema,
        )
        self.add_endpoint(
            "dataset_versions.verify_integrity",
            self.verify_dataset_integrity,
            schema=DatasetIntegrityVerifySchema,
        )
        self.add_endpoint(
            "replication.upsert_batch", self.replication_upsert_batch, schema=ReplicationBatchUpsertSchema
        )
        self.add_endpoint(
            "replication.hydrate_asset_payload",
            self.replication_hydrate_asset_payload,
            schema=ReplicationHydrateAssetPayloadSchema,
        )
        self.add_endpoint("replication.reconcile", self.replication_reconcile, schema=ReplicationReconcileSchema)
        self.add_endpoint(
            "replication.mark_local_delete_eligible",
            self.replication_mark_local_delete_eligible,
            schema=ReplicationMarkLocalDeleteEligibleSchema,
        )
        self.add_endpoint(
            "replication.delete_local_payload",
            self.replication_delete_local_payload,
            schema=ReplicationDeleteLocalPayloadSchema,
        )
        self.add_endpoint(
            "replication.reclaim_verified_payloads",
            self.replication_reclaim_verified_payloads,
            schema=ReplicationReclaimSchema,
        )
        self.add_endpoint("replication.status", self.replication_status, schema=ReplicationStatusSchema)
        self.add_endpoint(
            "replication.tasks.enqueue",
            self.replication_task_enqueue,
            schema=ReplicationTaskEnqueueSchema,
        )
        self.add_endpoint("replication.tasks.list", self.replication_task_list, schema=ReplicationTaskListSchema)
        self.add_endpoint("replication.tasks.get", self.replication_task_get, schema=ReplicationTaskGetSchema)
        self.add_endpoint("replication.tasks.claim", self.replication_task_claim, schema=ReplicationTaskClaimSchema)
        self.add_endpoint(
            "replication.tasks.update_status",
            self.replication_task_update_status,
            schema=ReplicationTaskUpdateStatusSchema,
        )
        self.add_endpoint("replication.tasks.fail", self.replication_task_fail, schema=ReplicationTaskFailSchema)
        self.add_endpoint("replication.tasks.retry", self.replication_task_retry, schema=ReplicationTaskRetrySchema)
        self.add_endpoint("replication.tasks.purge", self.replication_task_purge, schema=ReplicationTaskPurgeSchema)

    async def _startup_initialize(self) -> None:
        await self._ensure_datalake()
        if self._upload_reconciler_task is None:
            self._upload_reconciler_task = asyncio.create_task(self._run_upload_reconciler())

    async def shutdown_cleanup(self) -> None:
        """Release resources: cancel sync/reconciler tasks and close the datalake.

        Overrides :meth:`mindtrace.services.Service.shutdown_cleanup`, which the
        base ``combined_lifespan`` invokes during FastAPI shutdown. The old
        ``on_shutdown.append`` registration is obsolete because FastAPI's
        ``lifespan=`` parameter takes precedence over Starlette's ``on_shutdown``
        handlers; overriding here is the documented extension point.
        """
        try:
            await super().shutdown_cleanup()
        except Exception:
            pass

        running_sync_tasks = [job.task for job in self._dataset_sync_jobs.values() if job.task is not None]
        for task in running_sync_tasks:
            task.cancel()
        if running_sync_tasks:
            await asyncio.gather(*running_sync_tasks, return_exceptions=True)

        if self._upload_reconciler_task is not None:
            self._upload_reconciler_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._upload_reconciler_task
            self._upload_reconciler_task = None
        if self._datalake is not None and self._owns_datalake:
            try:
                await self._datalake.close()
            except Exception:
                pass
            self._datalake = None
            self._initialized = False

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
                slow_ops_policy=self.slow_ops_policy,
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

    @staticmethod
    async def _await_client_safe(coro: Awaitable[Any]) -> Any:
        try:
            return await coro
        except SlowOperationDisabledError as exc:
            raise HTTPException(
                status_code=400,
                detail=(f"This deployment disables eager list endpoints because they do not scale safely. {exc}"),
            ) from exc

    @staticmethod
    async def _await_pagination_client_safe(coro: Awaitable[Any]) -> Any:
        try:
            return await DatalakeService._await_client_safe(coro)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pagination request. {exc}",
            ) from exc

    async def health(self) -> DatalakeHealthOutput:
        datalake = await self._ensure_datalake()
        return DatalakeHealthOutput(**(await datalake.get_health()))

    async def summary(self) -> DatalakeSummaryOutput:
        datalake = await self._ensure_datalake()
        return DatalakeSummaryOutput(summary=await datalake.summary())

    async def mounts_info(self) -> MountsOutput:
        datalake = await self._ensure_datalake()
        return MountsOutput(**datalake.get_mounts())

    async def wipe_datalake(self, payload: DatalakeWipeInput) -> DatalakeWipeOutput:
        datalake = await self._ensure_datalake()
        return DatalakeWipeOutput(**(await datalake.wipe(**payload.model_dump())))

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
        try:
            obj = await datalake.get_object(payload.storage_ref)
        except (RegistryObjectNotFound, FileNotFoundError, KeyError, OSError) as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "OBJECT_NOT_READABLE",
                    "message": str(exc),
                    "storage_ref": payload.storage_ref.model_dump(mode="json"),
                },
            ) from exc
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

    async def get_asset(self, payload: GetByIdInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        return AssetOutput(asset=await datalake.get_asset(payload.id))

    async def get_asset_by_alias(self, payload: GetAssetByAliasInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        return AssetOutput(asset=await datalake.get_asset_by_alias(payload.alias))

    async def add_alias(self, payload: AddAliasInput) -> AssetAliasOutput:
        datalake = await self._ensure_datalake()
        row = await datalake.add_alias(payload.asset_id, payload.alias)
        return AssetAliasOutput(asset_alias=row)

    async def list_assets(self, payload: ListInput) -> AssetListOutput:
        datalake = await self._ensure_datalake()
        return AssetListOutput(assets=await self._await_client_safe(datalake.list_assets(payload.filters)))

    async def list_assets_page(self, payload: PageInput) -> AssetPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_assets_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return AssetPageOutput(items=page.items, page=page.page)

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

    async def create_collection(self, payload: CreateCollectionInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.create_collection(**payload.model_dump()))

    async def get_collection(self, payload: GetByIdInput) -> CollectionOutput:
        datalake = await self._ensure_datalake()
        return CollectionOutput(collection=await datalake.get_collection(payload.id))

    async def list_collections(self, payload: ListInput) -> CollectionListOutput:
        datalake = await self._ensure_datalake()
        return CollectionListOutput(
            collections=await self._await_client_safe(datalake.list_collections(payload.filters))
        )

    async def list_collections_page(self, payload: PageInput) -> CollectionPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_collections_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return CollectionPageOutput(items=page.items, page=page.page)

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
        return CollectionItemListOutput(
            collection_items=await self._await_client_safe(datalake.list_collection_items(payload.filters))
        )

    async def list_collection_items_page(self, payload: PageInput) -> CollectionItemPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_collection_items_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return CollectionItemPageOutput(items=page.items, page=page.page)

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
        return AssetRetentionListOutput(
            asset_retentions=await self._await_client_safe(datalake.list_asset_retentions(payload.filters))
        )

    async def list_asset_retentions_page(self, payload: PageInput) -> AssetRetentionPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_asset_retentions_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return AssetRetentionPageOutput(items=page.items, page=page.page)

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
        return AnnotationSchemaListOutput(
            annotation_schemas=await self._await_client_safe(datalake.list_annotation_schemas(payload.filters))
        )

    async def list_annotation_schemas_page(self, payload: PageInput) -> AnnotationSchemaPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_annotation_schemas_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return AnnotationSchemaPageOutput(items=page.items, page=page.page)

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
        return AnnotationSetListOutput(
            annotation_sets=await self._await_client_safe(datalake.list_annotation_sets(payload.filters))
        )

    async def list_annotation_sets_page(self, payload: PageInput) -> AnnotationSetPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_annotation_sets_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return AnnotationSetPageOutput(items=page.items, page=page.page)

    async def update_annotation_set(self, payload: UpdateAnnotationSetInput) -> AnnotationSetOutput:
        datalake = await self._ensure_datalake()
        annotation_set = await datalake.update_annotation_set(payload.annotation_set_id, **payload.changes)
        return AnnotationSetOutput(annotation_set=annotation_set)

    async def add_annotation_records(self, payload: AddAnnotationRecordsInput) -> AddedAnnotationRecordsOutput:
        datalake = await self._ensure_datalake()
        records = await datalake.add_annotation_records(
            payload.annotations,
            annotation_set_id=payload.annotation_set_id,
            annotation_schema_id=payload.annotation_schema_id,
        )
        return AddedAnnotationRecordsOutput(annotation_records=records)

    async def list_annotation_records_for_asset(
        self, payload: ListAnnotationRecordsForAssetInput
    ) -> AnnotationRecordListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordListOutput(
            annotation_records=await self._await_client_safe(
                datalake.list_annotation_records_for_asset(payload.asset_id)
            ),
        )

    async def list_annotation_records_for_asset_page(
        self, payload: ListAnnotationRecordsForAssetPageInput
    ) -> AnnotationRecordPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_annotation_records_for_asset_page(
                payload.asset_id,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return AnnotationRecordPageOutput(items=page.items, page=page.page)

    async def get_annotation_record(self, payload: GetByIdInput) -> AnnotationRecordOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordOutput(annotation_record=await datalake.get_annotation_record(payload.id))

    async def list_annotation_records(self, payload: ListInput) -> AnnotationRecordListOutput:
        datalake = await self._ensure_datalake()
        return AnnotationRecordListOutput(
            annotation_records=await self._await_client_safe(datalake.list_annotation_records(payload.filters))
        )

    async def list_annotation_records_page(self, payload: PageInput) -> AnnotationRecordPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_annotation_records_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return AnnotationRecordPageOutput(items=page.items, page=page.page)

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
        return DatumListOutput(datums=await self._await_client_safe(datalake.list_datums(payload.filters)))

    async def list_datums_page(self, payload: PageInput) -> DatumPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_datums_page(
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return DatumPageOutput(items=page.items, page=page.page)

    async def update_datum(self, payload: UpdateDatumInput) -> DatumOutput:
        datalake = await self._ensure_datalake()
        return DatumOutput(datum=await datalake.update_datum(payload.datum_id, **payload.changes))

    async def resolve_datum(self, payload: GetByIdInput) -> ResolvedDatumOutput:
        datalake = await self._ensure_datalake()
        return ResolvedDatumOutput(resolved_datum=await datalake.resolve_datum(payload.id))

    async def verify_dataset_integrity(self, payload: DatasetIntegrityVerifyInput) -> DatasetIntegrityVerifyOutput:
        datalake = await self._ensure_datalake()
        dataset_version = await datalake.get_dataset_version(payload.dataset_name, payload.version)
        manifest_ids = [str(v) for v in dataset_version.manifest]
        sample_limit = int(payload.sample_limit)
        samples: list[DatasetIntegrityIssueSample] = []

        def add_sample(kind: str, id_: str, detail: str | None = None) -> None:
            if len(samples) < sample_limit:
                samples.append(DatasetIntegrityIssueSample(kind=kind, id=id_, detail=detail))

        duplicate_manifest_count = len(manifest_ids) - len(set(manifest_ids))
        missing_manifest_datum_count = 0
        missing_asset_count = 0
        missing_annotation_set_count = 0
        missing_annotation_record_count = 0
        missing_annotation_schema_count = 0
        missing_mask_asset_count = 0
        registry_missing_payload_count = 0
        invalid_mount_count = 0

        datums_by_id: dict[str, Any] = {}
        asset_ids: set[str] = set()
        annotation_set_ids: set[str] = set()

        for datum_id in manifest_ids:
            try:
                datum = await datalake.get_datum(datum_id)
                datums_by_id[datum_id] = datum
                for asset_id in (datum.asset_refs or {}).values():
                    asset_ids.add(str(asset_id))
                for annotation_set_id in datum.annotation_set_ids or []:
                    annotation_set_ids.add(str(annotation_set_id))
            except Exception as exc:
                missing_manifest_datum_count += 1
                add_sample("missing_manifest_datum", datum_id, str(exc))

        assets_by_id: dict[str, Any] = {}
        if payload.mode in {"fast", "full-db", "full-lake"}:
            for asset_id in sorted(asset_ids):
                try:
                    asset = await datalake.get_asset(asset_id)
                    assets_by_id[asset_id] = asset
                except Exception as exc:
                    missing_asset_count += 1
                    add_sample("missing_asset", asset_id, str(exc))

        annotation_sets_by_id: dict[str, Any] = {}
        annotation_record_ids: set[str] = set()
        annotation_schema_ids: set[str] = set()
        if payload.mode in {"full-db", "full-lake"}:
            for annotation_set_id in sorted(annotation_set_ids):
                try:
                    annotation_set = await datalake.get_annotation_set(annotation_set_id)
                    annotation_sets_by_id[annotation_set_id] = annotation_set
                    if annotation_set.annotation_schema_id:
                        annotation_schema_ids.add(str(annotation_set.annotation_schema_id))
                    for annotation_record_id in annotation_set.annotation_record_ids or []:
                        annotation_record_ids.add(str(annotation_record_id))
                except Exception as exc:
                    missing_annotation_set_count += 1
                    add_sample("missing_annotation_set", annotation_set_id, str(exc))

            for annotation_record_id in sorted(annotation_record_ids):
                try:
                    record = await datalake.get_annotation_record(annotation_record_id)
                    geometry = record.geometry or {}
                    if isinstance(geometry, dict):
                        mask_asset_id = geometry.get("mask_asset_id")
                        if mask_asset_id and str(mask_asset_id) not in assets_by_id:
                            try:
                                mask_asset = await datalake.get_asset(str(mask_asset_id))
                                assets_by_id[str(mask_asset_id)] = mask_asset
                            except Exception as exc:
                                missing_mask_asset_count += 1
                                add_sample("missing_mask_asset", str(mask_asset_id), str(exc))
                except Exception as exc:
                    missing_annotation_record_count += 1
                    add_sample("missing_annotation_record", annotation_record_id, str(exc))

            for annotation_schema_id in sorted(annotation_schema_ids):
                try:
                    await datalake.get_annotation_schema(annotation_schema_id)
                except Exception as exc:
                    missing_annotation_schema_count += 1
                    add_sample("missing_annotation_schema", annotation_schema_id, str(exc))

        if payload.mode == "full-lake":
            mount_snapshot = datalake.get_mounts()
            mount_entries = mount_snapshot.get("mounts", []) if isinstance(mount_snapshot, dict) else []
            known_mounts = {
                str(entry.get("name")) for entry in mount_entries if isinstance(entry, dict) and entry.get("name")
            }
            sample_asset_mounts: list[dict[str, Any]] = []
            for asset_id, asset in list(assets_by_id.items())[: min(5, len(assets_by_id))]:
                payload_ref = asset.payload_storage_ref or asset.storage_ref
                sample_asset_mounts.append(
                    {
                        "asset_id": asset_id,
                        "mount": None if payload_ref is None else str(payload_ref.mount or ""),
                        "name": None if payload_ref is None else str(payload_ref.name or ""),
                    }
                )
            print(
                "[dataset-integrity] full-lake mount snapshot",
                {
                    "dataset": f"{payload.dataset_name}@{payload.version}",
                    "mount_snapshot": mount_snapshot,
                    "known_mounts": sorted(known_mounts),
                    "sample_asset_mounts": sample_asset_mounts,
                },
                flush=True,
            )
            for asset_id, asset in assets_by_id.items():
                payload_ref = asset.payload_storage_ref or asset.storage_ref
                if payload_ref is None:
                    continue
                mount_name = str(payload_ref.mount or "")
                if mount_name not in known_mounts:
                    invalid_mount_count += 1
                    add_sample("invalid_mount", asset_id, mount_name)
                    continue
                try:
                    exists = await datalake.object_exists(payload_ref)
                except (RegistryObjectNotFound, FileNotFoundError, KeyError, OSError) as exc:
                    registry_missing_payload_count += 1
                    add_sample("registry_missing_payload", asset_id, str(exc))
                    continue
                if not exists:
                    registry_missing_payload_count += 1
                    add_sample("registry_missing_payload", asset_id, payload_ref.qualified_key)

        ok = (
            duplicate_manifest_count == 0
            and missing_manifest_datum_count == 0
            and missing_asset_count == 0
            and missing_annotation_set_count == 0
            and missing_annotation_record_count == 0
            and missing_annotation_schema_count == 0
            and missing_mask_asset_count == 0
            and registry_missing_payload_count == 0
            and invalid_mount_count == 0
        )
        return DatasetIntegrityVerifyOutput(
            ok=ok,
            dataset_name=payload.dataset_name,
            version=payload.version,
            mode=payload.mode,
            manifest_count=len(manifest_ids),
            resolved_manifest_count=len(datums_by_id),
            duplicate_manifest_count=duplicate_manifest_count,
            missing_manifest_datum_count=missing_manifest_datum_count,
            missing_asset_count=missing_asset_count,
            missing_annotation_set_count=missing_annotation_set_count,
            missing_annotation_record_count=missing_annotation_record_count,
            missing_annotation_schema_count=missing_annotation_schema_count,
            missing_mask_asset_count=missing_mask_asset_count,
            registry_missing_payload_count=registry_missing_payload_count,
            invalid_mount_count=invalid_mount_count,
            samples=samples,
        )

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
        versions = await self._await_client_safe(
            datalake.list_dataset_versions(dataset_name=payload.dataset_name, filters=payload.filters)
        )
        return DatasetVersionListOutput(dataset_versions=versions)

    async def list_dataset_versions_page(self, payload: ListDatasetVersionsPageInput) -> DatasetVersionPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.list_dataset_versions_page(
                dataset_name=payload.dataset_name,
                filters=payload.filters,
                sort=payload.sort,
                limit=payload.limit,
                cursor=payload.cursor,
                include_total=payload.include_total,
            )
        )
        return DatasetVersionPageOutput(items=page.items, page=page.page)

    async def resolve_dataset_version(self, payload: GetDatasetVersionInput) -> ResolvedDatasetVersionOutput:
        datalake = await self._ensure_datalake()
        resolved = await datalake.resolve_dataset_version(payload.dataset_name, payload.version)
        return ResolvedDatasetVersionOutput(resolved_dataset_version=resolved)

    async def view_dataset_version_page(self, payload: ViewDatasetVersionPageInput) -> DatasetViewPageOutput:
        datalake = await self._ensure_datalake()
        page = await self._await_pagination_client_safe(
            datalake.view_dataset_version_page(
                payload.dataset_name,
                payload.version,
                limit=payload.limit,
                cursor=payload.cursor,
                sort=payload.sort,
                filters=payload.filters,
                expand=payload.expand,
                include_total=payload.include_total,
            )
        )
        return DatasetViewPageOutput(items=page.items, page=page.page, view=page.view)

    async def export_dataset_version(self, payload: ExportDatasetVersionInput) -> DatasetSyncBundleOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        bundle = await manager.export_dataset_version(payload.dataset_name, payload.version)
        return DatasetSyncBundleOutput(bundle=bundle)

    async def export_sync_graph(self, payload: ExportDatasetVersionInput) -> DatasetSyncGraphExportOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        bundle = await manager.export_dataset_version(payload.dataset_name, payload.version)
        return DatasetSyncGraphExportOutput(bundle=bundle)

    async def export_sync_payload_manifest(
        self, payload: ExportDatasetVersionInput
    ) -> DatasetSyncPayloadManifestOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        bundle = await manager.export_dataset_version(payload.dataset_name, payload.version)
        return DatasetSyncPayloadManifestOutput(payloads=list(bundle.payloads))

    async def dataset_sync_import_graph(self, payload: DatasetSyncImportGraphInput) -> DatasetSyncImportGraphOutput:
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        bundle = await _load_import_session_bundle(datalake, session)
        manager = DatasetSyncManager(datalake, datalake)
        progress_writer = _ImportSessionProgressWriter(datalake, session)
        default_commit_batch_size = DatasetSyncImportRequest.model_fields["commit_batch_size"].default
        default_commit_progress_every_items = DatasetSyncImportRequest.model_fields[
            "commit_progress_every_items"
        ].default
        default_commit_progress_every_seconds = DatasetSyncImportRequest.model_fields[
            "commit_progress_every_seconds"
        ].default
        try:
            result = await manager.fast_import_graph(
                DatasetSyncImportRequest(
                    bundle=bundle,
                    transfer_policy=session.transfer_policy,
                    origin_lake_id=session.origin_lake_id,
                    preserve_ids=session.preserve_ids,
                    mount_map=dict(session.mount_map),
                    commit_batch_size=getattr(session, "commit_batch_size", default_commit_batch_size),
                    commit_progress_every_items=getattr(
                        session,
                        "commit_progress_every_items",
                        default_commit_progress_every_items,
                    ),
                    commit_progress_every_seconds=getattr(
                        session,
                        "commit_progress_every_seconds",
                        default_commit_progress_every_seconds,
                    ),
                    target_metadata_commit=True,
                ),
                progress_callback=progress_writer,
            )
        except ValueError as exc:
            await progress_writer.persist_failed(str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            await progress_writer.persist_failed(f"{type(exc).__name__}: {exc!s}")
            raise
        session.metadata_graph_committed = True
        session.import_stage = "hydrating_payloads" if session.required_asset_ids else "ready_to_finalize"
        await datalake.dataset_import_session_database.update(session)
        return DatasetSyncImportGraphOutput(result=result)

    async def dataset_sync_hydrate_payload(
        self, payload: DatasetSyncHydratePayloadsInput
    ) -> DatasetSyncHydratePayloadsOutput:
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        bundle = await _load_import_session_bundle(datalake, session)
        desc = next((p for p in bundle.payloads if p.asset_id == payload.asset_id), None)
        if desc is None:
            raise HTTPException(status_code=400, detail="asset_id not found in session bundle")
        data = self._decode_base64(payload.data_base64)
        manager = DatasetSyncManager(datalake, datalake)
        ref = await manager.ingest_import_payload_bytes(desc, session.mount_map, data)
        session.staged_refs[payload.asset_id] = ref.model_dump(mode="json")
        await manager.finalize_pending_import_asset_payload(
            asset_id=payload.asset_id,
            payload_descriptor=desc,
            staged_storage_ref=ref,
            payload_bytes=data,
        )
        session.verified_asset_ids = sorted(set(session.verified_asset_ids) | {payload.asset_id})
        session.import_stage = (
            "ready_to_finalize"
            if len(session.verified_asset_ids) >= len(session.required_asset_ids)
            else "hydrating_payloads"
        )
        await datalake.dataset_import_session_database.update(session)
        return DatasetSyncHydratePayloadsOutput(storage_ref=ref)

    async def dataset_sync_finalize_graph(
        self, payload: DatasetSyncFinalizeGraphInput
    ) -> DatasetSyncCommitResultOutput:
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        bundle = await _load_import_session_bundle(datalake, session)
        missing: list[str] = []
        for aid in session.required_asset_ids:
            asset = await datalake.get_asset(aid)
            if asset.payload_status != "present":
                missing.append(aid)
        if missing:
            raise HTTPException(status_code=400, detail=f"Payload hydration still pending for asset ids: {missing}")
        dv = await datalake.get_dataset_version(bundle.dataset_version.dataset_name, bundle.dataset_version.version)
        result = DatasetSyncCommitResult(
            dataset_version=dv,
            created_assets=0,
            created_annotation_schemas=0,
            created_annotation_records=0,
            created_annotation_sets=0,
            created_datums=0,
            transferred_payloads=len(session.verified_asset_ids),
            skipped_payloads=0,
        )
        await _delete_import_session_bundle_blob(datalake, session)
        session.bundle_storage_ref = None
        session.bundle_data = {}
        session.status = "committed"
        session.import_stage = "committed"
        await datalake.dataset_import_session_database.update(session)
        return DatasetSyncCommitResultOutput(result=result)

    async def _streaming_upsert_model(self, database: Any, field: str, incoming: Any) -> tuple[Any, bool]:
        rows = await database.find({field: getattr(incoming, field)})
        if not rows:
            inserted = await database.insert(incoming)
            return inserted, True
        existing = rows[0]
        payload = incoming.model_dump()
        for key, value in payload.items():
            if key in {"id", "_id"}:
                continue
            setattr(existing, key, value)
        if hasattr(existing, "updated_at"):
            existing.updated_at = utc_now()
        updated = await database.update(existing)
        return updated, False

    async def _streaming_upsert_asset(self, datalake: AsyncDatalake, asset: Asset) -> tuple[Asset, bool]:
        rows = await datalake.asset_database.find({"asset_id": asset.asset_id})
        if not rows:
            inserted = await datalake.asset_database.insert(asset)
            return inserted, True
        existing = rows[0]
        payload = asset.model_dump()
        for key, value in payload.items():
            if key in {"id", "_id"}:
                continue
            setattr(existing, key, value)
        existing.updated_at = utc_now()
        updated = await datalake.asset_database.update(existing)
        return updated, False

    async def streaming_import_start(
        self, payload: DatasetStreamingImportStartInput
    ) -> DatasetStreamingImportStartOutput:
        datalake = await self._ensure_datalake()
        now = utc_now()
        session = DatasetImportSession(
            bundle_data={},
            transfer_policy=payload.transfer_policy,
            preserve_ids=payload.preserve_ids,
            mount_map=dict(payload.mount_map),
            origin_lake_id=payload.origin_lake_id or payload.source_alias,
            required_asset_ids=[],
            verified_asset_ids=[],
            dataset_name=payload.dataset_name,
            dataset_version=payload.version,
            expected_manifest_total=payload.manifest_total,
            ordered_manifest_ids=[],
            import_stage="streaming",
            expires_at=now + timedelta(hours=24),
        )
        session.metadata_graph_committed = False
        session.import_progress_phase = "committing"
        session.import_progress_phase_detail = "importing_schemas"
        session.import_progress_message = "Starting streaming import"
        session.import_progress_total_items = payload.manifest_total
        session.import_progress_completed_items = 0
        session.import_progress_updated_at = now
        await datalake.dataset_import_session_database.insert(session)
        return DatasetStreamingImportStartOutput(session_id=session.import_session_id, expires_at=session.expires_at)

    async def streaming_import_push_batch(
        self, payload: DatasetStreamingImportPushBatchInput
    ) -> DatasetStreamingImportPushBatchOutput:
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        if _import_session_expired(session.expires_at):
            raise HTTPException(status_code=400, detail="import session expired")
        manager = DatasetSyncManager(datalake, datalake)

        bytes_completed = int(session.import_progress_bytes_completed or 0)
        required_asset_ids = set(session.required_asset_ids)
        verified_asset_ids = set(session.verified_asset_ids)
        ordered_manifest_ids = list(session.ordered_manifest_ids)
        processed_total = int(session.import_progress_completed_items or 0)

        total_batches = max(len(payload.items), 1)
        writer = _ImportSessionProgressWriter(datalake, session)
        last_progress: DatasetSyncProgress | None = None
        schema_seconds = 0.0
        asset_seconds = 0.0
        payload_seconds = 0.0
        record_seconds = 0.0
        annotation_set_seconds = 0.0
        datum_seconds = 0.0

        for batch_index, item in enumerate(payload.items, start=1):
            schema_started_at = time.time()
            for schema in item.annotation_schemas:
                await self._streaming_upsert_model(datalake.annotation_schema_database, "annotation_schema_id", schema)
            schema_seconds += max(0.0, time.time() - schema_started_at)
            last_progress = DatasetSyncProgress(
                phase="committing",
                phase_detail="importing_schemas",
                entity_kind="annotation_schema",
                message=f"Streaming annotation schemas for datum {item.manifest_index + 1}",
                completed_items=processed_total,
                total_items=session.expected_manifest_total,
                entity_completed_items=batch_index,
                entity_total_items=total_batches,
                batch_index=batch_index,
                total_batches=total_batches,
                bytes_completed=bytes_completed,
            )
            await writer.persist(last_progress, force=True)

            def _batch_payload_satisfied(batch_asset: Asset, target_asset: Asset) -> bool:
                return bool(
                    target_asset.payload_status == "present"
                    and (
                        batch_asset.payload_checksum is None
                        or target_asset.payload_checksum == batch_asset.payload_checksum
                        or target_asset.checksum == batch_asset.payload_checksum
                    )
                    and (
                        batch_asset.payload_size_bytes is None
                        or target_asset.payload_size_bytes == batch_asset.payload_size_bytes
                        or target_asset.size_bytes == batch_asset.payload_size_bytes
                    )
                )

            asset_started_at = time.time()
            asset_rows: list[Asset] = []
            for asset in item.assets:
                mapped_storage_ref = _apply_mount_map_to_storage_ref(asset.storage_ref, session.mount_map)
                mapped_payload_ref = _apply_mount_map_to_storage_ref(
                    asset.payload_storage_ref or asset.storage_ref, session.mount_map
                )
                rows_existing = await datalake.asset_database.find({"asset_id": asset.asset_id})
                existing_asset = rows_existing[0] if rows_existing else None

                resolved_payload_updates: dict[str, Any]
                if existing_asset is not None and _batch_payload_satisfied(asset, existing_asset):
                    resolved_payload_updates = {
                        "payload_status": existing_asset.payload_status,
                        "payload_status_reason": existing_asset.payload_status_reason,
                        "payload_verified_at": existing_asset.payload_verified_at,
                        "payload_checksum": existing_asset.payload_checksum,
                        "payload_size_bytes": existing_asset.payload_size_bytes,
                        "payload_storage_ref": (
                            existing_asset.payload_storage_ref.model_dump(mode="python")
                            if existing_asset.payload_storage_ref is not None
                            else mapped_payload_ref.model_dump(mode="python")
                        ),
                    }
                else:
                    resolved_payload_updates = {
                        "payload_status": "missing",
                        "payload_status_reason": "streaming_import_pending_payload",
                        "payload_verified_at": None,
                    }

                mapped_asset = Asset.model_validate(
                    {
                        **asset.model_dump(),
                        "storage_ref": mapped_storage_ref.model_dump(),
                        "payload_storage_ref": mapped_payload_ref.model_dump(),
                        **resolved_payload_updates,
                        "updated_at": utc_now(),
                    }
                )
                row, _ = await self._streaming_upsert_asset(datalake, mapped_asset)
                asset_rows.append(row)
                required_asset_ids.add(asset.asset_id)
            if asset_rows:
                await datalake.ensure_primary_asset_aliases(asset_rows)
            asset_seconds += max(0.0, time.time() - asset_started_at)
            last_progress = DatasetSyncProgress(
                phase="committing",
                phase_detail="importing_assets",
                entity_kind="asset",
                message=f"Streaming assets for datum {item.manifest_index + 1}",
                completed_items=processed_total,
                total_items=session.expected_manifest_total,
                entity_completed_items=batch_index,
                entity_total_items=total_batches,
                batch_index=batch_index,
                total_batches=total_batches,
                bytes_completed=bytes_completed,
            )
            await writer.persist(last_progress, force=True)

            payload_started_at = time.time()
            payloads_by_asset = {entry.asset_id: entry for entry in item.payloads}

            async def process_payload(asset: Asset) -> tuple[str, int, dict[str, Any] | None, bool]:
                payload_entry = payloads_by_asset.get(asset.asset_id)
                if payload_entry is None:
                    target_asset = await datalake.get_asset(asset.asset_id)
                    if _batch_payload_satisfied(asset, target_asset):
                        return asset.asset_id, 0, None, True
                    return asset.asset_id, 0, None, False
                target_asset = await datalake.get_asset(asset.asset_id)
                if _batch_payload_satisfied(asset, target_asset):
                    return asset.asset_id, 0, None, True
                data = self._decode_base64(payload_entry.data_base64)
                payload_descriptor = ObjectPayloadDescriptor(
                    asset_id=asset.asset_id,
                    storage_ref=asset.payload_storage_ref or asset.storage_ref,
                    media_type=asset.media_type,
                    size_bytes=asset.payload_size_bytes if asset.payload_size_bytes is not None else asset.size_bytes,
                    checksum=asset.payload_checksum if asset.payload_checksum is not None else asset.checksum,
                    content_type=asset.media_type,
                    metadata=dict(asset.metadata or {}),
                )
                ref = await manager.ingest_import_payload_bytes(payload_descriptor, session.mount_map, data)
                await manager.finalize_pending_import_asset_payload(
                    asset_id=asset.asset_id,
                    payload_descriptor=payload_descriptor,
                    staged_storage_ref=ref,
                    payload_bytes=data,
                )
                return asset.asset_id, len(data), ref.model_dump(mode="json"), True

            payload_results = await asyncio.gather(*(process_payload(asset) for asset in item.assets))
            for asset_id, added_bytes, staged_ref, verified in payload_results:
                if verified:
                    verified_asset_ids.add(asset_id)
                bytes_completed += added_bytes
                if staged_ref is not None:
                    session.staged_refs[asset_id] = staged_ref
            payload_seconds += max(0.0, time.time() - payload_started_at)
            last_progress = DatasetSyncProgress(
                phase="transferring",
                phase_detail="hydrating_payloads",
                entity_kind="asset",
                message=f"Streaming payloads for datum {item.manifest_index + 1}",
                completed_items=processed_total,
                total_items=session.expected_manifest_total,
                entity_completed_items=batch_index,
                entity_total_items=total_batches,
                batch_index=batch_index,
                total_batches=total_batches,
                bytes_completed=bytes_completed,
            )
            await writer.persist(last_progress, force=True)

            record_started_at = time.time()
            for record in item.annotation_records:
                await self._streaming_upsert_model(datalake.annotation_record_database, "annotation_id", record)
            record_seconds += max(0.0, time.time() - record_started_at)
            last_progress = DatasetSyncProgress(
                phase="committing",
                phase_detail="importing_annotation_records",
                entity_kind="annotation_record",
                message=f"Streaming annotation records for datum {item.manifest_index + 1}",
                completed_items=processed_total,
                total_items=session.expected_manifest_total,
                entity_completed_items=batch_index,
                entity_total_items=total_batches,
                batch_index=batch_index,
                total_batches=total_batches,
                bytes_completed=bytes_completed,
            )
            await writer.persist(last_progress, force=True)

            annotation_set_started_at = time.time()
            for annotation_set in item.annotation_sets:
                await self._streaming_upsert_model(
                    datalake.annotation_set_database, "annotation_set_id", annotation_set
                )
            annotation_set_seconds += max(0.0, time.time() - annotation_set_started_at)
            last_progress = DatasetSyncProgress(
                phase="committing",
                phase_detail="importing_annotation_sets",
                entity_kind="annotation_set",
                message=f"Streaming annotation sets for datum {item.manifest_index + 1}",
                completed_items=processed_total,
                total_items=session.expected_manifest_total,
                entity_completed_items=batch_index,
                entity_total_items=total_batches,
                batch_index=batch_index,
                total_batches=total_batches,
                bytes_completed=bytes_completed,
            )
            await writer.persist(last_progress, force=True)

            datum_started_at = time.time()
            await self._streaming_upsert_model(datalake.datum_database, "datum_id", item.datum)
            datum_seconds += max(0.0, time.time() - datum_started_at)
            if item.datum.datum_id not in ordered_manifest_ids:
                ordered_manifest_ids.append(item.datum.datum_id)
            processed_total += 1
            last_progress = DatasetSyncProgress(
                phase="committing",
                phase_detail="importing_datums",
                entity_kind="datum",
                message=(
                    f"Streaming datums batch item {batch_index}/{total_batches}"
                    f" · target timings schema={schema_seconds:.2f}s assets={asset_seconds:.2f}s"
                    f" payloads={payload_seconds:.2f}s records={record_seconds:.2f}s"
                    f" sets={annotation_set_seconds:.2f}s datums={datum_seconds:.2f}s"
                ),
                completed_items=processed_total,
                total_items=session.expected_manifest_total,
                entity_completed_items=batch_index,
                entity_total_items=total_batches,
                batch_index=batch_index,
                total_batches=total_batches,
                bytes_completed=bytes_completed,
            )
            await writer.persist(last_progress, force=True)

        session.required_asset_ids = sorted(required_asset_ids)
        session.verified_asset_ids = sorted(verified_asset_ids)
        session.ordered_manifest_ids = ordered_manifest_ids
        session.import_stage = "streaming"
        session.metadata_graph_committed = False
        session.import_progress_completed_items = processed_total
        session.import_progress_total_items = session.expected_manifest_total
        session.import_progress_bytes_completed = bytes_completed
        session.import_progress_updated_at = utc_now()
        await datalake.dataset_import_session_database.update(session)
        return DatasetStreamingImportPushBatchOutput(
            session_id=session.import_session_id,
            processed_manifest_items=processed_total,
            required_asset_count=len(session.required_asset_ids),
            verified_asset_count=len(session.verified_asset_ids),
            pending_asset_count=max(len(session.required_asset_ids) - len(session.verified_asset_ids), 0),
            progress=last_progress,
        )

    async def streaming_import_finalize(
        self, payload: DatasetStreamingImportFinalizeInput
    ) -> DatasetSyncCommitResultOutput:
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        if _import_session_expired(session.expires_at):
            raise HTTPException(status_code=400, detail="import session expired")
        if not session.dataset_name or not session.dataset_version:
            raise HTTPException(status_code=400, detail="streaming import session is missing dataset identity")
        if session.expected_manifest_total and len(session.ordered_manifest_ids) != session.expected_manifest_total:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Streaming import manifest incomplete: got {len(session.ordered_manifest_ids)} / {session.expected_manifest_total} datums"
                ),
            )

        if session.required_asset_ids and session.transfer_policy != "metadata_only":
            missing_payload_assets: list[str] = []
            for asset_id in sorted(set(session.required_asset_ids)):
                row = await datalake.get_asset(asset_id)
                if row.payload_status != "present":
                    missing_payload_assets.append(asset_id)
            if missing_payload_assets:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Streaming import cannot finalize while required assets lack verified payloads: "
                        f"{missing_payload_assets}"
                    ),
                )

        writer = _ImportSessionProgressWriter(datalake, session)
        await writer.persist(
            DatasetSyncProgress(
                phase="committing",
                phase_detail="finalizing_graph",
                entity_kind="dataset_version",
                message="Finalizing streaming graph import",
                completed_items=len(session.ordered_manifest_ids),
                total_items=session.expected_manifest_total,
                entity_completed_items=0,
                entity_total_items=1,
                batch_index=1,
                total_batches=1,
                bytes_completed=session.import_progress_bytes_completed,
            ),
            force=True,
        )

        rows = await datalake.dataset_version_database.find(
            {"dataset_name": session.dataset_name, "version": session.dataset_version}
        )
        if rows:
            dataset_version = rows[0]
            dataset_version.manifest = list(session.ordered_manifest_ids)
            dataset_version.updated_at = utc_now()
            dataset_version = await datalake.dataset_version_database.update(dataset_version)
        else:
            dataset_version = await datalake.create_dataset_version(
                dataset_name=session.dataset_name,
                version=session.dataset_version,
                manifest=list(session.ordered_manifest_ids),
                source_dataset_version_id=None,
                metadata={"streaming_import": True, "origin_lake_id": session.origin_lake_id},
            )
        await writer.persist(
            DatasetSyncProgress(
                phase="complete",
                phase_detail="finalizing_graph",
                entity_kind="dataset_version",
                message="Finalized streaming graph import",
                completed_items=len(session.ordered_manifest_ids),
                total_items=session.expected_manifest_total,
                entity_completed_items=1,
                entity_total_items=1,
                batch_index=1,
                total_batches=1,
                bytes_completed=session.import_progress_bytes_completed,
            ),
            force=True,
        )
        session.status = "committed"
        session.import_stage = "committed"
        session.metadata_graph_committed = True
        await datalake.dataset_import_session_database.update(session)
        required_n = len(session.required_asset_ids)
        if session.transfer_policy == "metadata_only":
            transferred_payloads = len(session.verified_asset_ids)
            skipped_payloads = max(required_n - transferred_payloads, 0)
        else:
            transferred_payloads = required_n
            skipped_payloads = 0
        return DatasetSyncCommitResultOutput(
            result=DatasetSyncCommitResult(
                dataset_version=dataset_version,
                created_assets=0,
                created_annotation_schemas=0,
                created_annotation_records=0,
                created_annotation_sets=0,
                created_datums=len(session.ordered_manifest_ids),
                transferred_payloads=transferred_payloads,
                skipped_payloads=skipped_payloads,
            )
        )

    async def import_dataset_version_prepare(self, payload: DatasetSyncImportRequest) -> DatasetSyncImportPlanOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        plan = await manager.plan_import(payload)
        return DatasetSyncImportPlanOutput(plan=plan)

    async def import_dataset_version_commit(self, payload: DatasetSyncImportRequest) -> DatasetSyncCommitResultOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake)
        result = await manager.commit_import(payload)
        return DatasetSyncCommitResultOutput(result=result)

    async def import_dataset_version_prepare_start(
        self, payload: DatasetSyncImportRequest
    ) -> DatasetSyncJobStartOutput:
        return self._start_dataset_sync_job(payload, mode="prepare")

    async def import_dataset_version_start(self, payload: DatasetSyncImportRequest) -> DatasetSyncJobStartOutput:
        return self._start_dataset_sync_job(payload, mode="import")

    async def import_dataset_version_job_status(self, payload: DatasetSyncJobStatusInput) -> DatasetSyncJobStatusOutput:
        job = self._get_dataset_sync_job(payload.job_id)
        return self._dataset_sync_job_status_output(job)

    async def import_dataset_version_job_result(self, payload: DatasetSyncJobStatusInput) -> DatasetSyncJobResultOutput:
        job = self._get_dataset_sync_job(payload.job_id)
        return DatasetSyncJobResultOutput(
            job_id=job.job_id,
            mode=job.mode,
            status=job.status,
            progress=job.progress,
            plan=job.plan,
            result=job.result,
            error=job.error,
            error_detail=job.error_detail,
        )

    async def _require_open_import_session(self, datalake: AsyncDatalake, session_id: str) -> DatasetImportSession:
        rows = await datalake.dataset_import_session_database.find({"import_session_id": session_id})
        if not rows:
            raise HTTPException(status_code=404, detail=f"import session not found: {session_id}")
        session = rows[0]
        if session.status != "open":
            raise HTTPException(
                status_code=400,
                detail=f"import session is not open (status={session.status!r})",
            )
        return session

    async def import_session_start(self, payload: DatasetSyncImportRequest) -> DatasetImportSessionStartOutput:
        datalake = await self._ensure_datalake()
        manager = DatasetSyncManager(datalake, datalake)
        try:
            plan = await manager.plan_import(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if payload.transfer_policy == "fail_if_missing_payload" and not plan.ready_to_commit:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Import plan is not ready under fail_if_missing_payload for {plan.dataset_name}@{plan.version}"
                ),
            )

        required = [row.asset_id for row in plan.payloads if row.transfer_required]
        now = utc_now()
        session = DatasetImportSession(
            bundle_data={},
            transfer_policy=payload.transfer_policy,
            target_object_match_policy=payload.target_object_match_policy,
            preserve_ids=payload.preserve_ids,
            mount_map=dict(payload.mount_map),
            origin_lake_id=payload.origin_lake_id,
            planning_batch_size=payload.planning_batch_size,
            planning_concurrency=payload.planning_concurrency,
            transfer_batch_size=payload.transfer_batch_size,
            transfer_concurrency=payload.transfer_concurrency,
            greenfield_skip_target_object_probes=payload.greenfield_skip_target_object_probes,
            greenfield_skip_target_metadata_probes=payload.greenfield_skip_target_metadata_probes,
            commit_progress_every_items=payload.commit_progress_every_items,
            commit_progress_every_seconds=payload.commit_progress_every_seconds,
            required_asset_ids=required,
            import_stage="awaiting_metadata_commit",
            expires_at=now + timedelta(hours=24),
        )
        bundle_bytes = json.dumps(payload.bundle.model_dump(mode="json")).encode("utf-8")
        session.bundle_sha256 = hashlib.sha256(bundle_bytes).hexdigest()
        try:
            bundle_ref = await datalake.put_object(
                name=f"datalake_import_bundles/{session.import_session_id}/bundle.json",
                obj=bundle_bytes,
                metadata={"content_type": "application/json", "kind": "dataset_import_bundle"},
                on_conflict="overwrite",
            )
            session.bundle_storage_ref = bundle_ref
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to persist import bundle to object storage: {exc!s}",
            ) from exc

        try:
            await datalake.dataset_import_session_database.insert(session)
        except DocumentTooLargeError as exc:
            await _delete_import_session_bundle_blob(datalake, session)
            raise HTTPException(
                status_code=413,
                detail={"message": str(exc), "code": "DOCUMENT_TOO_LARGE"},
            ) from exc
        except Exception:
            await _delete_import_session_bundle_blob(datalake, session)
            raise
        return DatasetImportSessionStartOutput(
            session_id=session.import_session_id,
            required_asset_ids=required,
            expires_at=session.expires_at,
        )

    async def import_session_commit_metadata(
        self, payload: DatasetImportSessionCommitInput
    ) -> DatasetSyncCommitResultOutput:
        """Phase A on the target lake: persist dataset graph with pending payload replication state (caller push Phase B).

        When callers uploaded bytes via ``import_session_upload_payload`` before metadata commit, staged
        ``StorageRef`` values are finalized here (read + verify + ``payload_status=present``) alongside
        Phase A so those early uploads are usable without a second upload.

        Subsequent ``import_session_upload_payload`` verifies each staged asset and transitions ``pending→verified``.
        Closing the session requires ``import_session_commit`` once all ``required_asset_ids`` are verified.

        Import progress snapshots are mirrored onto Mongo (throttled) and polled via ``dataset_versions.import_session_status``.
        """
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        if _import_session_expired(session.expires_at):
            raise HTTPException(status_code=400, detail="import session expired")
        if session.metadata_graph_committed:
            raise HTTPException(
                status_code=400,
                detail="Metadata graph was already committed for this import session",
            )
        bundle = await _load_import_session_bundle(datalake, session)
        req = DatasetSyncImportRequest(
            bundle=bundle,
            transfer_policy=session.transfer_policy,
            target_object_match_policy=session.target_object_match_policy,
            origin_lake_id=session.origin_lake_id,
            preserve_ids=session.preserve_ids,
            mount_map=session.mount_map,
            planning_batch_size=session.planning_batch_size,
            planning_concurrency=session.planning_concurrency,
            transfer_batch_size=session.transfer_batch_size,
            transfer_concurrency=session.transfer_concurrency,
            greenfield_skip_target_object_probes=session.greenfield_skip_target_object_probes,
            greenfield_skip_target_metadata_probes=session.greenfield_skip_target_metadata_probes,
            commit_progress_every_items=session.commit_progress_every_items,
            commit_progress_every_seconds=session.commit_progress_every_seconds,
            staged_payload_storage_refs=None,
            target_metadata_commit=True,
        )
        manager = DatasetSyncManager(datalake)
        progress_writer = _ImportSessionProgressWriter(datalake, session)
        try:
            result = await manager.commit_import(req, progress_callback=progress_writer)
        except ValueError as exc:
            await progress_writer.persist_failed(str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            await progress_writer.persist_failed(f"{type(exc).__name__}: {exc!s}")
            raise

        payload_by_id = {p.asset_id: p for p in bundle.payloads}
        preflight_verified: list[str] = []
        for asset_id in sorted(session.required_asset_ids):
            raw = session.staged_refs.get(asset_id)
            if raw is None:
                continue
            desc = payload_by_id.get(asset_id)
            if desc is None:
                detail = f"Staged payload for asset {asset_id!r} has no matching bundle descriptor"
                await progress_writer.persist_failed(detail)
                raise HTTPException(status_code=400, detail=detail)
            ref = StorageRef.model_validate(raw)
            try:
                payload_bytes = await datalake.get_object(ref)
            except Exception as exc:
                await progress_writer.persist_failed(f"read staged payload {asset_id}: {exc!s}")
                raise HTTPException(
                    status_code=400, detail=f"Failed to read staged payload for asset {asset_id!r}"
                ) from exc
            try:
                await manager.finalize_pending_import_asset_payload(
                    asset_id=asset_id,
                    payload_descriptor=desc,
                    staged_storage_ref=ref,
                    payload_bytes=payload_bytes,
                )
            except (RuntimeError, ValueError) as exc:
                await progress_writer.persist_failed(f"finalize {asset_id}: {exc!s}")
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            preflight_verified.append(asset_id)

        session.metadata_graph_committed = True
        session.verified_asset_ids = sorted(set(preflight_verified))
        if session.required_asset_ids:
            outstanding = len(session.required_asset_ids) - len(session.verified_asset_ids)
            session.import_stage = "ready_to_finalize" if outstanding <= 0 else "awaiting_payload_uploads"
        else:
            session.import_stage = "ready_to_finalize"
        await datalake.dataset_import_session_database.update(session)
        return DatasetSyncCommitResultOutput(result=result)

    async def import_session_status(self, payload: DatasetImportSessionStatusInput) -> DatasetImportSessionStatusOutput:
        datalake = await self._ensure_datalake()
        rows = await datalake.dataset_import_session_database.find({"import_session_id": payload.session_id})
        if not rows:
            raise HTTPException(status_code=404, detail=f"import session not found: {payload.session_id}")
        return _dataset_import_session_status_output(rows[0])

    async def import_session_upload_payload(
        self, payload: DatasetImportSessionUploadInput
    ) -> DatasetImportSessionUploadOutput:
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        if _import_session_expired(session.expires_at):
            raise HTTPException(status_code=400, detail="import session expired")
        if payload.asset_id not in session.required_asset_ids:
            raise HTTPException(
                status_code=400,
                detail=f"asset_id {payload.asset_id!r} is not required for this import session",
            )
        bundle = await _load_import_session_bundle(datalake, session)
        desc = next((p for p in bundle.payloads if p.asset_id == payload.asset_id), None)
        if desc is None:
            raise HTTPException(status_code=400, detail="asset_id not found in session bundle")
        data = self._decode_base64(payload.data_base64)
        manager = DatasetSyncManager(datalake, datalake)
        try:
            ref = await manager.ingest_import_payload_bytes(desc, session.mount_map, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.staged_refs[payload.asset_id] = ref.model_dump(mode="json")
        if session.metadata_graph_committed:
            if payload.asset_id in session.verified_asset_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"asset_id {payload.asset_id!r} was already verified for this import session",
                )
            try:
                await manager.finalize_pending_import_asset_payload(
                    asset_id=payload.asset_id,
                    payload_descriptor=desc,
                    staged_storage_ref=ref,
                    payload_bytes=data,
                )
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            verified = sorted(set(session.verified_asset_ids) | {payload.asset_id})
            session.verified_asset_ids = verified
            session.import_stage = (
                "ready_to_finalize" if len(verified) >= len(session.required_asset_ids) else "awaiting_payload_uploads"
            )
        await datalake.dataset_import_session_database.update(session)
        return DatasetImportSessionUploadOutput(storage_ref=ref)

    async def import_session_commit(self, payload: DatasetImportSessionCommitInput) -> DatasetSyncCommitResultOutput:
        datalake = await self._ensure_datalake()
        session = await self._require_open_import_session(datalake, payload.session_id)
        if _import_session_expired(session.expires_at):
            raise HTTPException(status_code=400, detail="import session expired")

        bundle = await _load_import_session_bundle(datalake, session)

        if session.metadata_graph_committed:
            if session.required_asset_ids:
                missing: list[str] = []
                for aid in session.required_asset_ids:
                    asset = await datalake.get_asset(aid)
                    if asset.payload_status != "present":
                        missing.append(aid)
                if missing:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Payload verification still pending for asset ids: {missing}",
                    )
            try:
                dv = await datalake.get_dataset_version(
                    bundle.dataset_version.dataset_name,
                    bundle.dataset_version.version,
                )
            except DocumentNotFoundError as exc:
                raise HTTPException(
                    status_code=404,
                    detail="Dataset version not found after metadata commit",
                ) from exc
            result = DatasetSyncCommitResult(
                dataset_version=dv,
                created_assets=0,
                created_annotation_schemas=0,
                created_annotation_records=0,
                created_annotation_sets=0,
                created_datums=0,
                transferred_payloads=len(session.verified_asset_ids),
                skipped_payloads=0,
            )
            await _delete_import_session_bundle_blob(datalake, session)
            session.bundle_storage_ref = None
            session.bundle_data = {}
            session.status = "committed"
            session.import_stage = "committed"
            await datalake.dataset_import_session_database.update(session)
            return DatasetSyncCommitResultOutput(result=result)

        staged: dict[str, StorageRef] | None = None
        if session.required_asset_ids:
            missing = [aid for aid in session.required_asset_ids if aid not in session.staged_refs]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing staged payloads for asset ids: {missing}",
                )
            staged = {aid: StorageRef.model_validate(session.staged_refs[aid]) for aid in session.required_asset_ids}

        req = DatasetSyncImportRequest(
            bundle=bundle,
            transfer_policy=session.transfer_policy,
            target_object_match_policy=session.target_object_match_policy,
            origin_lake_id=session.origin_lake_id,
            preserve_ids=session.preserve_ids,
            mount_map=session.mount_map,
            planning_batch_size=session.planning_batch_size,
            planning_concurrency=session.planning_concurrency,
            transfer_batch_size=session.transfer_batch_size,
            transfer_concurrency=session.transfer_concurrency,
            greenfield_skip_target_object_probes=session.greenfield_skip_target_object_probes,
            greenfield_skip_target_metadata_probes=session.greenfield_skip_target_metadata_probes,
            commit_progress_every_items=session.commit_progress_every_items,
            commit_progress_every_seconds=session.commit_progress_every_seconds,
            staged_payload_storage_refs=staged,
        )
        manager = DatasetSyncManager(datalake, datalake)
        try:
            result = await manager.commit_import(req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _delete_import_session_bundle_blob(datalake, session)
        session.bundle_storage_ref = None
        session.bundle_data = {}
        session.status = "committed"
        session.import_stage = "committed"
        await datalake.dataset_import_session_database.update(session)
        return DatasetSyncCommitResultOutput(result=result)

    def _start_dataset_sync_job(self, request: DatasetSyncImportRequest, *, mode: str) -> DatasetSyncJobStartOutput:
        job = _DatasetSyncJobState(job_id=uuid4().hex, mode=mode)
        self._dataset_sync_jobs[job.job_id] = job
        job.task = asyncio.create_task(self._run_dataset_sync_job(job, request))
        return DatasetSyncJobStartOutput(
            job_id=job.job_id,
            mode=job.mode,
            status=job.status,
            progress=job.progress,
        )

    async def _run_dataset_sync_job(self, job: _DatasetSyncJobState, request: DatasetSyncImportRequest) -> None:
        job.status = "running"

        async def update_progress(progress: DatasetSyncProgress) -> None:
            job.progress = progress

        try:
            datalake = await self._ensure_datalake()
            manager = DatasetSyncManager(datalake)
            if job.mode == "prepare":
                job.plan = await manager.plan_import(request, progress_callback=update_progress)
            elif job.mode == "import":
                job.result = await manager.commit_import(request, progress_callback=update_progress)
            else:
                raise ValueError(f"Unsupported dataset sync job mode: {job.mode}")
            job.status = "completed"
            if job.progress.phase != "complete":
                job.progress = DatasetSyncProgress(
                    phase="complete",
                    completed_items=job.progress.total_items,
                    total_items=job.progress.total_items,
                    message="Completed dataset sync job",
                )
        except Exception as exc:
            job.status = "failed"
            summary = f"{type(exc).__name__}: {exc!r}"
            job.error = summary
            job.error_detail = DatasetSyncJobErrorDetail(
                exception_type=f"{exc.__class__.__module__}.{exc.__class__.__qualname__}",
                exception_repr=repr(exc),
                traceback=traceback.format_exc(),
            )
            job.progress = DatasetSyncProgress(phase="failed", message=summary)
            _LOGGER.exception(
                "Dataset sync job failed (job_id=%s, mode=%s)",
                job.job_id,
                job.mode,
            )

    def _get_dataset_sync_job(self, job_id: str) -> _DatasetSyncJobState:
        try:
            return self._dataset_sync_jobs[job_id]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Dataset sync job not found: {job_id}") from exc

    @staticmethod
    def _dataset_sync_job_status_output(job: _DatasetSyncJobState) -> DatasetSyncJobStatusOutput:
        return DatasetSyncJobStatusOutput(
            job_id=job.job_id,
            mode=job.mode,
            status=job.status,
            progress=job.progress,
            error=job.error,
            error_detail=job.error_detail,
        )

    async def replication_upsert_batch(self, payload: ReplicationBatchRequest) -> ReplicationBatchResultOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        result = await manager.upsert_metadata_batch(payload)
        return ReplicationBatchResultOutput(result=result)

    async def replication_hydrate_asset_payload(self, payload: ReplicationHydrateAssetPayloadInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        asset = await manager.hydrate_asset_payload(payload.asset_id, mount_map=payload.mount_map)
        return AssetOutput(asset=asset)

    async def replication_reconcile(self, payload: ReplicationReconcileRequest) -> ReplicationReconcileResultOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        result = await manager.reconcile_pending_payloads(payload)
        return ReplicationReconcileResultOutput(result=result)

    async def replication_mark_local_delete_eligible(
        self, payload: ReplicationMarkLocalDeleteEligibleInput
    ) -> AssetOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        asset = await manager.mark_local_delete_eligible(payload.asset_id, when=payload.when)
        return AssetOutput(asset=asset)

    async def replication_delete_local_payload(self, payload: GetByIdInput) -> AssetOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        asset = await manager.delete_local_payload(payload.id)
        return AssetOutput(asset=asset)

    async def replication_reclaim_verified_payloads(
        self, payload: ReplicationReclaimRequest
    ) -> ReplicationReclaimResultOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        result = await manager.reclaim_verified_payloads(payload)
        return ReplicationReclaimResultOutput(result=result)

    async def replication_status(self) -> ReplicationStatusOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationManager(datalake)
        status = await manager.status()
        return ReplicationStatusOutput(status=status)

    async def replication_task_enqueue(self, payload: ReplicationTaskEnqueueInput) -> ReplicationTaskEnqueueOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        task, created = await manager.enqueue_task(
            target_lake_id=payload.target_lake_id,
            root_kind=payload.root_kind,
            root_id=payload.root_id,
            rule_id=payload.rule_id,
            dedupe_key=payload.dedupe_key,
            source_version=payload.source_version,
            hydrate_policy=payload.hydrate_policy,
            mount_map=payload.mount_map,
            include_graph=payload.include_graph,
            max_attempts=payload.max_attempts,
            metadata=payload.metadata,
        )
        return ReplicationTaskEnqueueOutput(task=task, created=created)

    async def replication_task_list(self, payload: ReplicationTaskListInput) -> ReplicationTaskListOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        tasks = await manager.list_tasks(
            status=payload.status,
            target_lake_id=payload.target_lake_id,
            root_kind=payload.root_kind,
            rule_id=payload.rule_id,
            limit=payload.limit,
        )
        return ReplicationTaskListOutput(tasks=tasks)

    async def replication_task_get(self, payload: ReplicationTaskIdInput) -> ReplicationTaskOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        try:
            task = await manager.get_task(payload.task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ReplicationTaskOutput(task=task)

    async def replication_task_claim(self, payload: ReplicationTaskClaimInput) -> ReplicationTaskClaimOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        tasks = await manager.claim_due_tasks(
            worker_id=payload.worker_id,
            limit=payload.limit,
            lease_seconds=payload.lease_seconds,
        )
        return ReplicationTaskClaimOutput(tasks=tasks)

    async def replication_task_update_status(self, payload: ReplicationTaskStatusUpdateInput) -> ReplicationTaskOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        try:
            task = await manager.mark_status(
                payload.task_id,
                status=payload.status,
                worker_id=payload.worker_id,
                error=payload.error,
                progress_phase=payload.progress_phase,
                progress_message=payload.progress_message,
                completed_items=payload.completed_items,
                total_items=payload.total_items,
                bytes_completed=payload.bytes_completed,
                bytes_total=payload.bytes_total,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ReplicationTaskOutput(task=task)

    async def replication_task_fail(self, payload: ReplicationTaskFailInput) -> ReplicationTaskOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        try:
            task = await manager.fail_task(
                payload.task_id,
                worker_id=payload.worker_id,
                error=payload.error,
                retry_delay_seconds=payload.retry_delay_seconds,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ReplicationTaskOutput(task=task)

    async def replication_task_retry(self, payload: ReplicationTaskIdInput) -> ReplicationTaskOutput:
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        try:
            task = await manager.retry_task(payload.task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ReplicationTaskOutput(task=task)

    async def replication_task_purge(self, payload: ReplicationTaskPurgeInput) -> ReplicationTaskPurgeOutput:
        if self._replication_task_purge_secret is not None:
            if payload.purge_secret != self._replication_task_purge_secret:
                raise HTTPException(status_code=403, detail="Replication task purge is not authorized")
        datalake = await self._ensure_datalake()
        manager = ReplicationQueueManager(datalake)
        try:
            result = await manager.purge_terminal_tasks(
                older_than_seconds=payload.older_than_seconds,
                statuses=payload.statuses,
                limit=payload.limit,
                dry_run=payload.dry_run,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ReplicationTaskPurgeOutput(
            dry_run=result.dry_run,
            cutoff=result.cutoff,
            total_candidates=result.total_candidates,
            selected_count=result.selected_count,
            deleted_count=result.deleted_count,
            deleted_task_ids=list(result.deleted_task_ids),
        )
