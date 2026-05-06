import asyncio
import base64
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.async_datalake import AsyncDatalake, SlowOperationDisabledError, SlowOpsPolicy
from mindtrace.datalake.pagination_types import (
    CursorPage,
    DatasetViewExpand,
    DatasetViewInfo,
    DatasetViewPage,
    DatasetViewRow,
    PageInfo,
    StructuredFilter,
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
from mindtrace.datalake.service import (
    DatalakeService,
    _dataset_import_session_status_output,
    _DatasetSyncJobState,
    _delete_import_session_bundle_blob,
    _import_session_expired,
    _ImportSessionProgressWriter,
    _load_import_session_bundle,
)
from mindtrace.datalake.service_types import (
    AddAliasInput,
    AddAnnotationRecordsInput,
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
    CopyObjectInput,
    CreateAnnotationSchemaInput,
    CreateAnnotationSetInput,
    CreateAssetFromObjectInput,
    CreateAssetFromUploadedObjectInput,
    CreateAssetInput,
    CreateAssetRetentionInput,
    CreateCollectionInput,
    CreateCollectionItemInput,
    CreateDatasetVersionInput,
    CreateDatumInput,
    CreateObjectUploadSessionInput,
    DatalakeHealthOutput,
    DatalakeSummaryOutput,
    DatalakeWipeInput,
    DatasetImportSessionCommitInput,
    DatasetIntegrityVerifyInput,
    DatasetStreamingImportStartInput,
    DatasetSyncBundleOutput,
    DatasetSyncCommitResultOutput,
    DatasetSyncImportPlanOutput,
    DatasetSyncJobResultOutput,
    DatasetSyncJobStartOutput,
    DatasetSyncJobStatusInput,
    DatasetSyncJobStatusOutput,
    DatasetVersionListOutput,
    DatasetVersionOutput,
    DatasetVersionPageOutput,
    DatasetViewPageOutput,
    DatumListOutput,
    DatumOutput,
    DatumPageOutput,
    ExportDatasetVersionInput,
    GetAnnotationSchemaByNameVersionInput,
    GetAssetByAliasInput,
    GetByIdInput,
    GetDatasetVersionInput,
    GetObjectInput,
    HeadObjectInput,
    ListAnnotationRecordsForAssetInput,
    ListAnnotationRecordsForAssetPageInput,
    ListDatasetVersionsInput,
    ListDatasetVersionsPageInput,
    ListInput,
    MountsOutput,
    ObjectDataOutput,
    ObjectHeadOutput,
    ObjectOutput,
    ObjectUploadSessionOutput,
    PageInput,
    PutObjectInput,
    ReplicationBatchResultOutput,
    ReplicationHydrateAssetPayloadInput,
    ReplicationMarkLocalDeleteEligibleInput,
    ReplicationReclaimResultOutput,
    ReplicationReconcileResultOutput,
    ReplicationStatusOutput,
    ResolvedCollectionItemOutput,
    ResolvedDatasetVersionOutput,
    ResolvedDatumOutput,
    UpdateAnnotationRecordInput,
    UpdateAnnotationSchemaInput,
    UpdateAnnotationSetInput,
    UpdateAssetMetadataInput,
    UpdateAssetRetentionInput,
    UpdateCollectionInput,
    UpdateCollectionItemInput,
    UpdateDatumInput,
    ViewDatasetVersionPageInput,
)
from mindtrace.datalake.sync_types import (
    DatasetSyncBundle,
    DatasetSyncCommitResult,
    DatasetSyncImportPlan,
    DatasetSyncImportRequest,
    DatasetSyncProgress,
)
from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    AssetAlias,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetImportSession,
    DatasetVersion,
    Datum,
    DirectUploadSession,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)
from mindtrace.registry.core.exceptions import RegistryObjectNotFound


@pytest.fixture(autouse=True)
def _set_minimal_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")

    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()


@pytest.fixture
def datalake_objects():
    storage_ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
    source_storage_ref = StorageRef(mount="raw", name="images/source.jpg", version="v0")
    copied_storage_ref = StorageRef(mount="archive", name="images/cat-copy.jpg", version="v2")
    subject_ref = SubjectRef(kind="asset", id="asset_subject_1")

    asset = Asset(
        kind="image",
        media_type="image/jpeg",
        storage_ref=storage_ref,
        checksum="sha256:abc",
        size_bytes=123,
        subject=subject_ref,
        metadata={"source": "unit"},
        created_by="tester",
    )
    asset_alias = AssetAlias(alias="friendly", asset_id=asset.asset_id, is_primary=False)
    collection = Collection(name="demo-collection", description="unit collection", metadata={"team": "qa"})
    collection_item = CollectionItem(
        collection_id=collection.collection_id,
        asset_id=asset.asset_id,
        split="train",
        metadata={"role": "input"},
        added_by="tester",
    )
    asset_retention = AssetRetention(
        asset_id=asset.asset_id,
        owner_type="manual_pin",
        owner_id="owner_1",
        retention_policy="retain",
        metadata={"reason": "keep"},
        created_by="tester",
    )
    annotation_schema = AnnotationSchema(
        name="demo-schema",
        version="1.0",
        task_type="detection",
        allowed_annotation_kinds=["bbox"],
        labels=[AnnotationLabelDefinition(name="cat", id=1)],
        metadata={"source": "unit"},
        created_by="tester",
    )
    annotation_set = AnnotationSet(
        name="ground-truth",
        purpose="ground_truth",
        source_type="human",
        metadata={"source": "unit"},
        created_by="tester",
        annotation_schema_id=annotation_schema.annotation_schema_id,
    )
    annotation_record = AnnotationRecord(
        kind="bbox",
        label="cat",
        source={"type": "human", "name": "annotator"},
        geometry={"x": 1, "y": 2, "w": 3, "h": 4},
        attributes={"occluded": False},
    )
    datum = Datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"source": "unit"},
        annotation_set_ids=[annotation_set.annotation_set_id],
    )
    dataset_version = DatasetVersion(
        dataset_name="demo-dataset",
        version="1.0",
        manifest=[datum.datum_id],
        metadata={"source": "unit"},
        created_by="tester",
    )
    resolved_collection_item = ResolvedCollectionItem(
        collection_item=collection_item,
        collection=collection,
        asset=asset,
    )
    resolved_datum = ResolvedDatum(
        datum=datum,
        assets={"image": asset},
        annotation_sets=[annotation_set],
        annotation_records={annotation_set.annotation_set_id: [annotation_record]},
    )
    resolved_dataset_version = ResolvedDatasetVersion(
        dataset_version=dataset_version,
        datums=[resolved_datum],
    )
    raw_bytes = b"payload-bytes"
    raw_text = "payload-text"
    encoded_bytes = base64.b64encode(raw_bytes).decode("utf-8")

    return SimpleNamespace(
        storage_ref=storage_ref,
        source_storage_ref=source_storage_ref,
        copied_storage_ref=copied_storage_ref,
        subject_ref=subject_ref,
        asset=asset,
        collection=collection,
        collection_item=collection_item,
        asset_retention=asset_retention,
        annotation_schema=annotation_schema,
        annotation_set=annotation_set,
        annotation_record=annotation_record,
        datum=datum,
        dataset_version=dataset_version,
        resolved_collection_item=resolved_collection_item,
        resolved_datum=resolved_datum,
        resolved_dataset_version=resolved_dataset_version,
        raw_bytes=raw_bytes,
        raw_text=raw_text,
        encoded_bytes=encoded_bytes,
        asset_alias=asset_alias,
    )


@pytest.fixture
def mock_datalake():
    datalake = Mock(spec=AsyncDatalake)
    datalake.slow_ops_policy = SlowOpsPolicy.WARN
    return datalake


@pytest.fixture
def service(mock_datalake):
    return DatalakeService(async_datalake=mock_datalake, live_service=False, initialize_on_startup=False)


SERVICE_CASES = [
    {
        "service_method": "health",
        "payload_factory": lambda o: None,
        "datalake_method": "get_health",
        "datalake_return_factory": lambda o: {"status": "ok", "database": "unit_db", "default_mount": "nas"},
        "expected_output_type": DatalakeHealthOutput,
        "expected_output_field": "status",
        "expected_output_factory": lambda o: "ok",
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "summary",
        "payload_factory": lambda o: None,
        "datalake_method": "summary",
        "datalake_return_factory": lambda o: "summary text",
        "expected_output_type": DatalakeSummaryOutput,
        "expected_output_field": "summary",
        "expected_output_factory": lambda o: "summary text",
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "mounts_info",
        "payload_factory": lambda o: None,
        "datalake_method": "get_mounts",
        "datalake_return_factory": lambda o: {"default_mount": "nas", "mounts": [{"name": "nas"}]},
        "expected_output_type": MountsOutput,
        "expected_output_field": "mounts",
        "expected_output_factory": lambda o: [{"name": "nas"}],
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {},
        "sync_mock": True,
    },
    {
        "service_method": "put_object",
        "payload_factory": lambda o: PutObjectInput(
            name="images/cat.jpg",
            data_base64=o.encoded_bytes,
            mount="nas",
            version="v1",
            metadata={"source": "unit"},
            on_conflict="replace",
        ),
        "datalake_method": "put_object",
        "datalake_return_factory": lambda o: o.storage_ref,
        "expected_output_type": ObjectOutput,
        "expected_output_field": "storage_ref",
        "expected_output_factory": lambda o: o.storage_ref,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {
            "name": "images/cat.jpg",
            "obj": o.raw_bytes,
            "mount": "nas",
            "version": "v1",
            "metadata": {"source": "unit"},
            "on_conflict": "replace",
        },
    },
    {
        "service_method": "get_object",
        "payload_factory": lambda o: GetObjectInput(storage_ref=o.storage_ref),
        "datalake_method": "get_object",
        "datalake_return_factory": lambda o: o.raw_bytes,
        "expected_output_type": ObjectDataOutput,
        "expected_output_field": "data_base64",
        "expected_output_factory": lambda o: o.encoded_bytes,
        "expected_args_factory": lambda o: (o.storage_ref,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "head_object",
        "payload_factory": lambda o: HeadObjectInput(storage_ref=o.storage_ref),
        "datalake_method": "head_object",
        "datalake_return_factory": lambda o: {"size": 123},
        "expected_output_type": ObjectHeadOutput,
        "expected_output_field": "metadata",
        "expected_output_factory": lambda o: {"size": 123},
        "expected_args_factory": lambda o: (o.storage_ref,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "copy_object",
        "payload_factory": lambda o: CopyObjectInput(
            source=o.source_storage_ref,
            target_mount="archive",
            target_name="images/cat-copy.jpg",
            target_version="v2",
        ),
        "datalake_method": "copy_object",
        "datalake_return_factory": lambda o: o.copied_storage_ref,
        "expected_output_type": ObjectOutput,
        "expected_output_field": "storage_ref",
        "expected_output_factory": lambda o: o.copied_storage_ref,
        "expected_args_factory": lambda o: (o.source_storage_ref,),
        "expected_kwargs_factory": lambda o: {
            "target_mount": "archive",
            "target_name": "images/cat-copy.jpg",
            "target_version": "v2",
        },
    },
    {
        "service_method": "create_object_upload_session",
        "payload_factory": lambda o: CreateObjectUploadSessionInput(
            name="images/cat.jpg",
            mount="nas",
            version="v1",
            metadata={"source": "unit"},
            on_conflict="skip",
            content_type="image/jpeg",
            expires_in_minutes=60,
            created_by="tester",
        ),
        "datalake_method": "create_object_upload_session",
        "datalake_return_factory": lambda o: DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            requested_version="v1",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            content_type="image/jpeg",
            metadata={"source": "unit"},
            expires_at=o.asset.created_at,
            created_by="tester",
        ),
        "expected_output_type": ObjectUploadSessionOutput,
        "expected_output_field": "upload_session_id",
        "expected_output_factory": lambda o: "upload_session_1",
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {
            "name": "images/cat.jpg",
            "mount": "nas",
            "version": "v1",
            "metadata": {"source": "unit"},
            "on_conflict": "skip",
            "content_type": "image/jpeg",
            "expires_in_minutes": 60,
            "created_by": "tester",
        },
    },
    {
        "service_method": "complete_object_upload_session",
        "payload_factory": lambda o: CompleteObjectUploadSessionInput(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            metadata={"source": "verified"},
        ),
        "datalake_method": "complete_object_upload_session",
        "datalake_return_factory": lambda o: DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            requested_version="v1",
            resolved_version="v1",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            content_type="image/jpeg",
            metadata={"source": "verified"},
            status="completed",
            storage_ref=o.storage_ref,
            expires_at=o.asset.created_at,
            completed_at=o.asset.created_at,
            created_by="tester",
        ),
        "expected_output_type": ObjectUploadSessionOutput,
        "expected_output_field": "status",
        "expected_output_factory": lambda o: "completed",
        "expected_args_factory": lambda o: ("upload_session_1",),
        "expected_kwargs_factory": lambda o: {
            "finalize_token": "token-1",
            "metadata": {"source": "verified"},
        },
    },
    {
        "service_method": "create_asset",
        "payload_factory": lambda o: CreateAssetInput(
            kind="image",
            media_type="image/jpeg",
            storage_ref=o.storage_ref,
            checksum="sha256:abc",
            size_bytes=123,
            subject=o.subject_ref,
            metadata={"source": "unit"},
            created_by="tester",
        ),
        "datalake_method": "create_asset",
        "datalake_return_factory": lambda o: o.asset,
        "expected_output_type": AssetOutput,
        "expected_output_field": "asset",
        "expected_output_factory": lambda o: o.asset,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {
            "kind": "image",
            "media_type": "image/jpeg",
            "storage_ref": o.storage_ref,
            "checksum": "sha256:abc",
            "size_bytes": 123,
            "subject": o.subject_ref,
            "metadata": {"source": "unit"},
            "created_by": "tester",
        },
    },
    {
        "service_method": "get_asset",
        "payload_factory": lambda o: GetByIdInput(id=o.asset.asset_id),
        "datalake_method": "get_asset",
        "datalake_return_factory": lambda o: o.asset,
        "expected_output_type": AssetOutput,
        "expected_output_field": "asset",
        "expected_output_factory": lambda o: o.asset,
        "expected_args_factory": lambda o: (o.asset.asset_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "get_asset_by_alias",
        "payload_factory": lambda o: GetAssetByAliasInput(alias="friendly"),
        "datalake_method": "get_asset_by_alias",
        "datalake_return_factory": lambda o: o.asset,
        "expected_output_type": AssetOutput,
        "expected_output_field": "asset",
        "expected_output_factory": lambda o: o.asset,
        "expected_args_factory": lambda o: ("friendly",),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "add_alias",
        "payload_factory": lambda o: AddAliasInput(asset_id=o.asset.asset_id, alias=o.asset_alias.alias),
        "datalake_method": "add_alias",
        "datalake_return_factory": lambda o: o.asset_alias,
        "expected_output_type": AssetAliasOutput,
        "expected_output_field": "asset_alias",
        "expected_output_factory": lambda o: o.asset_alias,
        "expected_args_factory": lambda o: (o.asset.asset_id, o.asset_alias.alias),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_assets",
        "payload_factory": lambda o: ListInput(filters={"kind": "image"}),
        "datalake_method": "list_assets",
        "datalake_return_factory": lambda o: [o.asset],
        "expected_output_type": AssetListOutput,
        "expected_output_field": "assets",
        "expected_output_factory": lambda o: [o.asset],
        "expected_args_factory": lambda o: ({"kind": "image"},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_asset_metadata",
        "payload_factory": lambda o: UpdateAssetMetadataInput(
            asset_id=o.asset.asset_id, metadata={"source": "updated"}
        ),
        "datalake_method": "update_asset_metadata",
        "datalake_return_factory": lambda o: o.asset,
        "expected_output_type": AssetOutput,
        "expected_output_field": "asset",
        "expected_output_factory": lambda o: o.asset,
        "expected_args_factory": lambda o: (o.asset.asset_id, {"source": "updated"}),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "delete_asset",
        "payload_factory": lambda o: GetByIdInput(id=o.asset.asset_id),
        "datalake_method": "delete_asset",
        "datalake_return_factory": lambda o: None,
        "expected_output_type": None,
        "expected_output_field": None,
        "expected_output_factory": lambda o: None,
        "expected_args_factory": lambda o: (o.asset.asset_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "create_asset_from_object",
        "payload_factory": lambda o: CreateAssetFromObjectInput(
            name="images/cat.jpg",
            data_base64=o.encoded_bytes,
            kind="image",
            media_type="image/jpeg",
            mount="nas",
            version="v1",
            object_metadata={"compression": "none"},
            asset_metadata={"source": "unit"},
            checksum="sha256:abc",
            size_bytes=123,
            subject=o.subject_ref,
            created_by="tester",
            on_conflict="replace",
        ),
        "datalake_method": "create_asset_from_object",
        "datalake_return_factory": lambda o: o.asset,
        "expected_output_type": AssetOutput,
        "expected_output_field": "asset",
        "expected_output_factory": lambda o: o.asset,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {
            "name": "images/cat.jpg",
            "obj": o.raw_bytes,
            "kind": "image",
            "media_type": "image/jpeg",
            "mount": "nas",
            "version": "v1",
            "object_metadata": {"compression": "none"},
            "asset_metadata": {"source": "unit"},
            "checksum": "sha256:abc",
            "size_bytes": 123,
            "subject": o.subject_ref,
            "created_by": "tester",
            "on_conflict": "replace",
        },
    },
    {
        "service_method": "create_asset_from_uploaded_object",
        "payload_factory": lambda o: CreateAssetFromUploadedObjectInput(
            kind="image",
            media_type="image/jpeg",
            storage_ref=o.storage_ref,
            checksum="sha256:abc",
            size_bytes=123,
            subject=o.subject_ref,
            metadata={"source": "unit"},
            created_by="tester",
        ),
        "datalake_method": "create_asset",
        "datalake_return_factory": lambda o: o.asset,
        "expected_output_type": AssetOutput,
        "expected_output_field": "asset",
        "expected_output_factory": lambda o: o.asset,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {
            "kind": "image",
            "media_type": "image/jpeg",
            "storage_ref": o.storage_ref,
            "checksum": "sha256:abc",
            "size_bytes": 123,
            "subject": o.subject_ref,
            "metadata": {"source": "unit"},
            "created_by": "tester",
        },
    },
    {
        "service_method": "create_collection",
        "payload_factory": lambda o: CreateCollectionInput(
            name="demo-collection",
            description="unit collection",
            status="active",
            metadata={"team": "qa"},
            created_by="tester",
        ),
        "datalake_method": "create_collection",
        "datalake_return_factory": lambda o: o.collection,
        "expected_output_type": CollectionOutput,
        "expected_output_field": "collection",
        "expected_output_factory": lambda o: o.collection,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: CreateCollectionInput(
            name="demo-collection",
            description="unit collection",
            status="active",
            metadata={"team": "qa"},
            created_by="tester",
        ).model_dump(),
    },
    {
        "service_method": "get_collection",
        "payload_factory": lambda o: GetByIdInput(id=o.collection.collection_id),
        "datalake_method": "get_collection",
        "datalake_return_factory": lambda o: o.collection,
        "expected_output_type": CollectionOutput,
        "expected_output_field": "collection",
        "expected_output_factory": lambda o: o.collection,
        "expected_args_factory": lambda o: (o.collection.collection_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_collections",
        "payload_factory": lambda o: ListInput(filters={"status": "active"}),
        "datalake_method": "list_collections",
        "datalake_return_factory": lambda o: [o.collection],
        "expected_output_type": CollectionListOutput,
        "expected_output_field": "collections",
        "expected_output_factory": lambda o: [o.collection],
        "expected_args_factory": lambda o: ({"status": "active"},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_collection",
        "payload_factory": lambda o: UpdateCollectionInput(
            collection_id=o.collection.collection_id,
            changes={"status": "archived"},
        ),
        "datalake_method": "update_collection",
        "datalake_return_factory": lambda o: o.collection,
        "expected_output_type": CollectionOutput,
        "expected_output_field": "collection",
        "expected_output_factory": lambda o: o.collection,
        "expected_args_factory": lambda o: (o.collection.collection_id,),
        "expected_kwargs_factory": lambda o: {"status": "archived"},
    },
    {
        "service_method": "delete_collection",
        "payload_factory": lambda o: GetByIdInput(id=o.collection.collection_id),
        "datalake_method": "delete_collection",
        "datalake_return_factory": lambda o: None,
        "expected_output_type": None,
        "expected_output_field": None,
        "expected_output_factory": lambda o: None,
        "expected_args_factory": lambda o: (o.collection.collection_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "create_collection_item",
        "payload_factory": lambda o: CreateCollectionItemInput(
            collection_id=o.collection.collection_id,
            asset_id=o.asset.asset_id,
            split="train",
            status="active",
            metadata={"role": "input"},
            added_by="tester",
        ),
        "datalake_method": "create_collection_item",
        "datalake_return_factory": lambda o: o.collection_item,
        "expected_output_type": CollectionItemOutput,
        "expected_output_field": "collection_item",
        "expected_output_factory": lambda o: o.collection_item,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: CreateCollectionItemInput(
            collection_id=o.collection.collection_id,
            asset_id=o.asset.asset_id,
            split="train",
            status="active",
            metadata={"role": "input"},
            added_by="tester",
        ).model_dump(),
    },
    {
        "service_method": "get_collection_item",
        "payload_factory": lambda o: GetByIdInput(id=o.collection_item.collection_item_id),
        "datalake_method": "get_collection_item",
        "datalake_return_factory": lambda o: o.collection_item,
        "expected_output_type": CollectionItemOutput,
        "expected_output_field": "collection_item",
        "expected_output_factory": lambda o: o.collection_item,
        "expected_args_factory": lambda o: (o.collection_item.collection_item_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_collection_items",
        "payload_factory": lambda o: ListInput(filters={"collection_id": o.collection.collection_id}),
        "datalake_method": "list_collection_items",
        "datalake_return_factory": lambda o: [o.collection_item],
        "expected_output_type": CollectionItemListOutput,
        "expected_output_field": "collection_items",
        "expected_output_factory": lambda o: [o.collection_item],
        "expected_args_factory": lambda o: ({"collection_id": o.collection.collection_id},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "resolve_collection_item",
        "payload_factory": lambda o: GetByIdInput(id=o.collection_item.collection_item_id),
        "datalake_method": "resolve_collection_item",
        "datalake_return_factory": lambda o: o.resolved_collection_item,
        "expected_output_type": ResolvedCollectionItemOutput,
        "expected_output_field": "resolved_collection_item",
        "expected_output_factory": lambda o: o.resolved_collection_item,
        "expected_args_factory": lambda o: (o.collection_item.collection_item_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_collection_item",
        "payload_factory": lambda o: UpdateCollectionItemInput(
            collection_item_id=o.collection_item.collection_item_id,
            changes={"status": "hidden"},
        ),
        "datalake_method": "update_collection_item",
        "datalake_return_factory": lambda o: o.collection_item,
        "expected_output_type": CollectionItemOutput,
        "expected_output_field": "collection_item",
        "expected_output_factory": lambda o: o.collection_item,
        "expected_args_factory": lambda o: (o.collection_item.collection_item_id,),
        "expected_kwargs_factory": lambda o: {"status": "hidden"},
    },
    {
        "service_method": "delete_collection_item",
        "payload_factory": lambda o: GetByIdInput(id=o.collection_item.collection_item_id),
        "datalake_method": "delete_collection_item",
        "datalake_return_factory": lambda o: None,
        "expected_output_type": None,
        "expected_output_field": None,
        "expected_output_factory": lambda o: None,
        "expected_args_factory": lambda o: (o.collection_item.collection_item_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "create_asset_retention",
        "payload_factory": lambda o: CreateAssetRetentionInput(
            asset_id=o.asset.asset_id,
            owner_type="manual_pin",
            owner_id="owner_1",
            retention_policy="retain",
            metadata={"reason": "keep"},
            created_by="tester",
        ),
        "datalake_method": "create_asset_retention",
        "datalake_return_factory": lambda o: o.asset_retention,
        "expected_output_type": AssetRetentionOutput,
        "expected_output_field": "asset_retention",
        "expected_output_factory": lambda o: o.asset_retention,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: CreateAssetRetentionInput(
            asset_id=o.asset.asset_id,
            owner_type="manual_pin",
            owner_id="owner_1",
            retention_policy="retain",
            metadata={"reason": "keep"},
            created_by="tester",
        ).model_dump(),
    },
    {
        "service_method": "get_asset_retention",
        "payload_factory": lambda o: GetByIdInput(id=o.asset_retention.asset_retention_id),
        "datalake_method": "get_asset_retention",
        "datalake_return_factory": lambda o: o.asset_retention,
        "expected_output_type": AssetRetentionOutput,
        "expected_output_field": "asset_retention",
        "expected_output_factory": lambda o: o.asset_retention,
        "expected_args_factory": lambda o: (o.asset_retention.asset_retention_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_asset_retentions",
        "payload_factory": lambda o: ListInput(filters={"asset_id": o.asset.asset_id}),
        "datalake_method": "list_asset_retentions",
        "datalake_return_factory": lambda o: [o.asset_retention],
        "expected_output_type": AssetRetentionListOutput,
        "expected_output_field": "asset_retentions",
        "expected_output_factory": lambda o: [o.asset_retention],
        "expected_args_factory": lambda o: ({"asset_id": o.asset.asset_id},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_asset_retention",
        "payload_factory": lambda o: UpdateAssetRetentionInput(
            asset_retention_id=o.asset_retention.asset_retention_id,
            changes={"retention_policy": "archive_when_unreferenced"},
        ),
        "datalake_method": "update_asset_retention",
        "datalake_return_factory": lambda o: o.asset_retention,
        "expected_output_type": AssetRetentionOutput,
        "expected_output_field": "asset_retention",
        "expected_output_factory": lambda o: o.asset_retention,
        "expected_args_factory": lambda o: (o.asset_retention.asset_retention_id,),
        "expected_kwargs_factory": lambda o: {"retention_policy": "archive_when_unreferenced"},
    },
    {
        "service_method": "delete_asset_retention",
        "payload_factory": lambda o: GetByIdInput(id=o.asset_retention.asset_retention_id),
        "datalake_method": "delete_asset_retention",
        "datalake_return_factory": lambda o: None,
        "expected_output_type": None,
        "expected_output_field": None,
        "expected_output_factory": lambda o: None,
        "expected_args_factory": lambda o: (o.asset_retention.asset_retention_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "create_annotation_schema",
        "payload_factory": lambda o: CreateAnnotationSchemaInput(
            name="demo-schema",
            version="1.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[{"name": "cat", "id": 1}],
            allow_scores=False,
            required_attributes=["occluded"],
            optional_attributes=["confidence"],
            allow_additional_attributes=True,
            metadata={"source": "unit"},
            created_by="tester",
        ),
        "datalake_method": "create_annotation_schema",
        "datalake_return_factory": lambda o: o.annotation_schema,
        "expected_output_type": AnnotationSchemaOutput,
        "expected_output_field": "annotation_schema",
        "expected_output_factory": lambda o: o.annotation_schema,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: CreateAnnotationSchemaInput(
            name="demo-schema",
            version="1.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[{"name": "cat", "id": 1}],
            allow_scores=False,
            required_attributes=["occluded"],
            optional_attributes=["confidence"],
            allow_additional_attributes=True,
            metadata={"source": "unit"},
            created_by="tester",
        ).model_dump(),
    },
    {
        "service_method": "get_annotation_schema",
        "payload_factory": lambda o: GetByIdInput(id=o.annotation_schema.annotation_schema_id),
        "datalake_method": "get_annotation_schema",
        "datalake_return_factory": lambda o: o.annotation_schema,
        "expected_output_type": AnnotationSchemaOutput,
        "expected_output_field": "annotation_schema",
        "expected_output_factory": lambda o: o.annotation_schema,
        "expected_args_factory": lambda o: (o.annotation_schema.annotation_schema_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "get_annotation_schema_by_name_version",
        "payload_factory": lambda o: GetAnnotationSchemaByNameVersionInput(name="demo-schema", version="1.0"),
        "datalake_method": "get_annotation_schema_by_name_version",
        "datalake_return_factory": lambda o: o.annotation_schema,
        "expected_output_type": AnnotationSchemaOutput,
        "expected_output_field": "annotation_schema",
        "expected_output_factory": lambda o: o.annotation_schema,
        "expected_args_factory": lambda o: ("demo-schema", "1.0"),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_annotation_schemas",
        "payload_factory": lambda o: ListInput(filters={"task_type": "detection"}),
        "datalake_method": "list_annotation_schemas",
        "datalake_return_factory": lambda o: [o.annotation_schema],
        "expected_output_type": AnnotationSchemaListOutput,
        "expected_output_field": "annotation_schemas",
        "expected_output_factory": lambda o: [o.annotation_schema],
        "expected_args_factory": lambda o: ({"task_type": "detection"},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_annotation_schema",
        "payload_factory": lambda o: UpdateAnnotationSchemaInput(
            annotation_schema_id=o.annotation_schema.annotation_schema_id,
            changes={"metadata": {"source": "updated"}},
        ),
        "datalake_method": "update_annotation_schema",
        "datalake_return_factory": lambda o: o.annotation_schema,
        "expected_output_type": AnnotationSchemaOutput,
        "expected_output_field": "annotation_schema",
        "expected_output_factory": lambda o: o.annotation_schema,
        "expected_args_factory": lambda o: (o.annotation_schema.annotation_schema_id,),
        "expected_kwargs_factory": lambda o: {"metadata": {"source": "updated"}},
    },
    {
        "service_method": "delete_annotation_schema",
        "payload_factory": lambda o: GetByIdInput(id=o.annotation_schema.annotation_schema_id),
        "datalake_method": "delete_annotation_schema",
        "datalake_return_factory": lambda o: None,
        "expected_output_type": None,
        "expected_output_field": None,
        "expected_output_factory": lambda o: None,
        "expected_args_factory": lambda o: (o.annotation_schema.annotation_schema_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "create_annotation_set",
        "payload_factory": lambda o: CreateAnnotationSetInput(
            name="ground-truth",
            purpose="ground_truth",
            source_type="human",
            status="draft",
            metadata={"source": "unit"},
            created_by="tester",
            datum_id=o.datum.datum_id,
            annotation_schema_id=o.annotation_schema.annotation_schema_id,
        ),
        "datalake_method": "create_annotation_set",
        "datalake_return_factory": lambda o: o.annotation_set,
        "expected_output_type": AnnotationSetOutput,
        "expected_output_field": "annotation_set",
        "expected_output_factory": lambda o: o.annotation_set,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: CreateAnnotationSetInput(
            name="ground-truth",
            purpose="ground_truth",
            source_type="human",
            status="draft",
            metadata={"source": "unit"},
            created_by="tester",
            datum_id=o.datum.datum_id,
            annotation_schema_id=o.annotation_schema.annotation_schema_id,
        ).model_dump(),
    },
    {
        "service_method": "get_annotation_set",
        "payload_factory": lambda o: GetByIdInput(id=o.annotation_set.annotation_set_id),
        "datalake_method": "get_annotation_set",
        "datalake_return_factory": lambda o: o.annotation_set,
        "expected_output_type": AnnotationSetOutput,
        "expected_output_field": "annotation_set",
        "expected_output_factory": lambda o: o.annotation_set,
        "expected_args_factory": lambda o: (o.annotation_set.annotation_set_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_annotation_sets",
        "payload_factory": lambda o: ListInput(filters={"purpose": "ground_truth"}),
        "datalake_method": "list_annotation_sets",
        "datalake_return_factory": lambda o: [o.annotation_set],
        "expected_output_type": AnnotationSetListOutput,
        "expected_output_field": "annotation_sets",
        "expected_output_factory": lambda o: [o.annotation_set],
        "expected_args_factory": lambda o: ({"purpose": "ground_truth"},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_annotation_set",
        "payload_factory": lambda o: UpdateAnnotationSetInput(
            annotation_set_id=o.annotation_set.annotation_set_id,
            changes={"status": "active"},
        ),
        "datalake_method": "update_annotation_set",
        "datalake_return_factory": lambda o: o.annotation_set,
        "expected_output_type": AnnotationSetOutput,
        "expected_output_field": "annotation_set",
        "expected_output_factory": lambda o: o.annotation_set,
        "expected_args_factory": lambda o: (o.annotation_set.annotation_set_id,),
        "expected_kwargs_factory": lambda o: {"status": "active"},
    },
    {
        "service_method": "add_annotation_records",
        "payload_factory": lambda o: AddAnnotationRecordsInput(
            annotations=[
                {
                    "kind": "bbox",
                    "label": "cat",
                    "source": {"type": "human", "name": "annotator"},
                    "geometry": {"x": 1, "y": 2, "w": 3, "h": 4},
                }
            ],
            annotation_set_id=o.annotation_set.annotation_set_id,
        ),
        "datalake_method": "add_annotation_records",
        "datalake_return_factory": lambda o: [o.annotation_record],
        "expected_output_type": AddedAnnotationRecordsOutput,
        "expected_output_field": "annotation_records",
        "expected_output_factory": lambda o: [o.annotation_record],
        "expected_args_factory": lambda o: (
            [
                {
                    "kind": "bbox",
                    "label": "cat",
                    "source": {"type": "human", "name": "annotator"},
                    "geometry": {"x": 1, "y": 2, "w": 3, "h": 4},
                }
            ],
        ),
        "expected_kwargs_factory": lambda o: {
            "annotation_set_id": o.annotation_set.annotation_set_id,
            "annotation_schema_id": None,
        },
    },
    {
        "service_method": "get_annotation_record",
        "payload_factory": lambda o: GetByIdInput(id=o.annotation_record.annotation_id),
        "datalake_method": "get_annotation_record",
        "datalake_return_factory": lambda o: o.annotation_record,
        "expected_output_type": AnnotationRecordOutput,
        "expected_output_field": "annotation_record",
        "expected_output_factory": lambda o: o.annotation_record,
        "expected_args_factory": lambda o: (o.annotation_record.annotation_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_annotation_records",
        "payload_factory": lambda o: ListInput(filters={"label": "cat"}),
        "datalake_method": "list_annotation_records",
        "datalake_return_factory": lambda o: [o.annotation_record],
        "expected_output_type": AnnotationRecordListOutput,
        "expected_output_field": "annotation_records",
        "expected_output_factory": lambda o: [o.annotation_record],
        "expected_args_factory": lambda o: ({"label": "cat"},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_annotation_records_for_asset",
        "payload_factory": lambda o: ListAnnotationRecordsForAssetInput(asset_id=o.asset.asset_id),
        "datalake_method": "list_annotation_records_for_asset",
        "datalake_return_factory": lambda o: [o.annotation_record],
        "expected_output_type": AnnotationRecordListOutput,
        "expected_output_field": "annotation_records",
        "expected_output_factory": lambda o: [o.annotation_record],
        "expected_args_factory": lambda o: (o.asset.asset_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_annotation_record",
        "payload_factory": lambda o: UpdateAnnotationRecordInput(
            annotation_id=o.annotation_record.annotation_id,
            changes={"label": "kitten"},
        ),
        "datalake_method": "update_annotation_record",
        "datalake_return_factory": lambda o: o.annotation_record,
        "expected_output_type": AnnotationRecordOutput,
        "expected_output_field": "annotation_record",
        "expected_output_factory": lambda o: o.annotation_record,
        "expected_args_factory": lambda o: (o.annotation_record.annotation_id,),
        "expected_kwargs_factory": lambda o: {"label": "kitten"},
    },
    {
        "service_method": "delete_annotation_record",
        "payload_factory": lambda o: GetByIdInput(id=o.annotation_record.annotation_id),
        "datalake_method": "delete_annotation_record",
        "datalake_return_factory": lambda o: None,
        "expected_output_type": None,
        "expected_output_field": None,
        "expected_output_factory": lambda o: None,
        "expected_args_factory": lambda o: (o.annotation_record.annotation_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "create_datum",
        "payload_factory": lambda o: CreateDatumInput(
            asset_refs={"image": o.asset.asset_id},
            split="train",
            metadata={"source": "unit"},
            annotation_set_ids=[o.annotation_set.annotation_set_id],
        ),
        "datalake_method": "create_datum",
        "datalake_return_factory": lambda o: o.datum,
        "expected_output_type": DatumOutput,
        "expected_output_field": "datum",
        "expected_output_factory": lambda o: o.datum,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: CreateDatumInput(
            asset_refs={"image": o.asset.asset_id},
            split="train",
            metadata={"source": "unit"},
            annotation_set_ids=[o.annotation_set.annotation_set_id],
        ).model_dump(),
    },
    {
        "service_method": "get_datum",
        "payload_factory": lambda o: GetByIdInput(id=o.datum.datum_id),
        "datalake_method": "get_datum",
        "datalake_return_factory": lambda o: o.datum,
        "expected_output_type": DatumOutput,
        "expected_output_field": "datum",
        "expected_output_factory": lambda o: o.datum,
        "expected_args_factory": lambda o: (o.datum.datum_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_datums",
        "payload_factory": lambda o: ListInput(filters={"split": "train"}),
        "datalake_method": "list_datums",
        "datalake_return_factory": lambda o: [o.datum],
        "expected_output_type": DatumListOutput,
        "expected_output_field": "datums",
        "expected_output_factory": lambda o: [o.datum],
        "expected_args_factory": lambda o: ({"split": "train"},),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "update_datum",
        "payload_factory": lambda o: UpdateDatumInput(datum_id=o.datum.datum_id, changes={"split": "val"}),
        "datalake_method": "update_datum",
        "datalake_return_factory": lambda o: o.datum,
        "expected_output_type": DatumOutput,
        "expected_output_field": "datum",
        "expected_output_factory": lambda o: o.datum,
        "expected_args_factory": lambda o: (o.datum.datum_id,),
        "expected_kwargs_factory": lambda o: {"split": "val"},
    },
    {
        "service_method": "resolve_datum",
        "payload_factory": lambda o: GetByIdInput(id=o.datum.datum_id),
        "datalake_method": "resolve_datum",
        "datalake_return_factory": lambda o: o.resolved_datum,
        "expected_output_type": ResolvedDatumOutput,
        "expected_output_field": "resolved_datum",
        "expected_output_factory": lambda o: o.resolved_datum,
        "expected_args_factory": lambda o: (o.datum.datum_id,),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "create_dataset_version",
        "payload_factory": lambda o: CreateDatasetVersionInput(
            dataset_name="demo-dataset",
            version="1.0",
            manifest=[o.datum.datum_id],
            description="unit dataset",
            source_dataset_version_id=None,
            metadata={"source": "unit"},
            created_by="tester",
        ),
        "datalake_method": "create_dataset_version",
        "datalake_return_factory": lambda o: o.dataset_version,
        "expected_output_type": DatasetVersionOutput,
        "expected_output_field": "dataset_version",
        "expected_output_factory": lambda o: o.dataset_version,
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: CreateDatasetVersionInput(
            dataset_name="demo-dataset",
            version="1.0",
            manifest=[o.datum.datum_id],
            description="unit dataset",
            source_dataset_version_id=None,
            metadata={"source": "unit"},
            created_by="tester",
        ).model_dump(),
    },
    {
        "service_method": "get_dataset_version",
        "payload_factory": lambda o: GetDatasetVersionInput(dataset_name="demo-dataset", version="1.0"),
        "datalake_method": "get_dataset_version",
        "datalake_return_factory": lambda o: o.dataset_version,
        "expected_output_type": DatasetVersionOutput,
        "expected_output_field": "dataset_version",
        "expected_output_factory": lambda o: o.dataset_version,
        "expected_args_factory": lambda o: ("demo-dataset", "1.0"),
        "expected_kwargs_factory": lambda o: {},
    },
    {
        "service_method": "list_dataset_versions",
        "payload_factory": lambda o: ListDatasetVersionsInput(
            dataset_name="demo-dataset",
            filters={"version": "1.0"},
        ),
        "datalake_method": "list_dataset_versions",
        "datalake_return_factory": lambda o: [o.dataset_version],
        "expected_output_type": DatasetVersionListOutput,
        "expected_output_field": "dataset_versions",
        "expected_output_factory": lambda o: [o.dataset_version],
        "expected_args_factory": lambda o: (),
        "expected_kwargs_factory": lambda o: {"dataset_name": "demo-dataset", "filters": {"version": "1.0"}},
    },
    {
        "service_method": "resolve_dataset_version",
        "payload_factory": lambda o: GetDatasetVersionInput(dataset_name="demo-dataset", version="1.0"),
        "datalake_method": "resolve_dataset_version",
        "datalake_return_factory": lambda o: o.resolved_dataset_version,
        "expected_output_type": ResolvedDatasetVersionOutput,
        "expected_output_field": "resolved_dataset_version",
        "expected_output_factory": lambda o: o.resolved_dataset_version,
        "expected_args_factory": lambda o: ("demo-dataset", "1.0"),
        "expected_kwargs_factory": lambda o: {},
    },
]


class TestDatalakeServiceInitialization:
    def test_initialization_registers_endpoints_and_startup_hook(self, mock_datalake):
        service = DatalakeService(async_datalake=mock_datalake, live_service=True, initialize_on_startup=True)

        assert service._datalake is mock_datalake
        assert service._initialized is True
        assert service.app.router.on_startup[-1] == service._startup_initialize
        # Shutdown cleanup is invoked via the base Service's ``combined_lifespan`` override of
        # ``shutdown_cleanup``; we no longer register it on the deprecated ``on_shutdown`` list.
        assert "objects.put" in service.endpoints
        assert "objects.upload_session.create" in service.endpoints
        assert "assets.create_from_uploaded_object" in service.endpoints
        assert "annotation_records.add" in service.endpoints
        assert "annotation_records.list_for_asset" in service.endpoints
        assert "dataset_versions.resolve" in service.endpoints

    def test_initialization_skips_startup_hook_when_not_live(self, mock_datalake):
        service = DatalakeService(async_datalake=mock_datalake, live_service=False, initialize_on_startup=True)

        assert service.app.router.on_startup == []

    @pytest.mark.asyncio
    async def test_startup_initialize_delegates_to_ensure_datalake(self, service):
        service._ensure_datalake = AsyncMock()
        service._run_upload_reconciler = AsyncMock()

        with patch("mindtrace.datalake.service.asyncio.create_task") as create_task:
            await service._startup_initialize()

        service._ensure_datalake.assert_awaited_once_with()
        create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_cancels_reconciler_task(self, service):
        task = asyncio.Future()
        cancel = Mock()

        def _cancel():
            cancel()
            task.set_exception(asyncio.CancelledError())

        task.cancel = _cancel
        service._upload_reconciler_task = task

        await service.shutdown_cleanup()

        cancel.assert_called_once_with()
        assert service._upload_reconciler_task is None

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_returns_when_no_reconciler_task(self, service):
        service._upload_reconciler_task = None

        await service.shutdown_cleanup()

        assert service._upload_reconciler_task is None

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_closes_owned_datalake(self, service, mock_datalake):
        service._datalake = mock_datalake
        service._owns_datalake = True  # service-created datalakes are owned, thus closed on shutdown
        mock_datalake.close = AsyncMock()
        service._upload_reconciler_task = None

        await service.shutdown_cleanup()

        mock_datalake.close.assert_awaited_once()
        assert service._datalake is None
        assert service._initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_does_not_close_externally_owned_datalake(self, service, mock_datalake):
        """A datalake passed via ``async_datalake=`` belongs to the caller and must not be closed here."""
        # ``service`` fixture already passes ``async_datalake=mock_datalake`` → ``_owns_datalake is False``.
        assert service._owns_datalake is False
        mock_datalake.close = AsyncMock()
        service._upload_reconciler_task = None

        await service.shutdown_cleanup()

        mock_datalake.close.assert_not_called()
        assert service._datalake is mock_datalake

    @pytest.mark.asyncio
    async def test_run_upload_reconciler_logs_warning_on_iteration_failure(self, service):
        datalake = Mock()
        datalake.reconcile_upload_sessions = AsyncMock(side_effect=RuntimeError("boom"))
        service._ensure_datalake = AsyncMock(return_value=datalake)
        service.logger.warning = Mock()

        async def _stop_after_first_sleep(_: float):
            raise asyncio.CancelledError()

        with (
            patch("mindtrace.datalake.service.asyncio.sleep", side_effect=_stop_after_first_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await service._run_upload_reconciler()

        service.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_upload_reconciler_propagates_cancellation(self, service):
        datalake = Mock()
        datalake.reconcile_upload_sessions = AsyncMock(side_effect=asyncio.CancelledError())
        service._ensure_datalake = AsyncMock(return_value=datalake)
        service.logger.warning = Mock()

        with pytest.raises(asyncio.CancelledError):
            await service._run_upload_reconciler()

        service.logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_datalake_raises_without_mongo_config(self):
        service = DatalakeService(live_service=False, initialize_on_startup=False)

        with pytest.raises(HTTPException, match="missing mongo_db_uri and/or mongo_db_name") as exc_info:
            await service._ensure_datalake()

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_ensure_datalake_builds_and_initializes_async_datalake(self):
        created_datalake = Mock(spec=AsyncDatalake)
        created_datalake.initialize = AsyncMock()
        created_datalake.slow_ops_policy = SlowOpsPolicy.FORBID

        service = DatalakeService(
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="mindtrace",
            mounts=["mount-a"],
            default_mount="nas",
            slow_ops_policy=SlowOpsPolicy.FORBID,
            live_service=False,
            initialize_on_startup=False,
        )

        with patch("mindtrace.datalake.service.AsyncDatalake", return_value=created_datalake) as mock_async_datalake:
            result = await service._ensure_datalake()

        assert result is created_datalake
        assert service._datalake is created_datalake
        assert service._initialized is True
        mock_async_datalake.assert_called_once_with(
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="mindtrace",
            mounts=["mount-a"],
            default_mount="nas",
            slow_ops_policy=SlowOpsPolicy.FORBID,
        )
        created_datalake.initialize.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_ensure_datalake_initializes_existing_instance_once(self, mock_datalake):
        service = DatalakeService(
            async_datalake=mock_datalake,
            live_service=False,
            initialize_on_startup=False,
        )
        service._initialized = False

        result = await service._ensure_datalake()

        assert result is mock_datalake
        assert service._initialized is True
        mock_datalake.initialize.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_ensure_datalake_returns_initialized_instance_without_reinitializing(self, mock_datalake):
        service = DatalakeService(
            async_datalake=mock_datalake,
            live_service=False,
            initialize_on_startup=False,
        )

        result = await service._ensure_datalake()

        assert result is mock_datalake
        mock_datalake.initialize.assert_not_called()


class TestDatalakeServiceUtilities:
    def test_decode_base64_round_trip(self, datalake_objects):
        assert DatalakeService._decode_base64(datalake_objects.encoded_bytes) == datalake_objects.raw_bytes

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            pytest.param("payload-text", base64.b64encode(b"payload-text").decode("utf-8"), id="str"),
            pytest.param(b"payload-bytes", base64.b64encode(b"payload-bytes").decode("utf-8"), id="bytes"),
            pytest.param(
                bytearray(b"payload-bytearray"), base64.b64encode(b"payload-bytearray").decode("utf-8"), id="bytearray"
            ),
        ],
    )
    def test_encode_base64_supported_inputs(self, payload, expected):
        assert DatalakeService._encode_base64(payload) == expected

    def test_encode_base64_rejects_unsupported_input(self):
        with pytest.raises(HTTPException, match="not serializable to base64") as exc_info:
            DatalakeService._encode_base64(123)

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_await_client_safe_translates_disabled_slow_operation(self):
        async def fail():
            raise SlowOperationDisabledError("list_assets() eagerly materializes an unbounded result set.")

        with pytest.raises(HTTPException, match="disables eager list endpoints") as exc_info:
            await DatalakeService._await_client_safe(fail())

        assert exc_info.value.status_code == 400
        assert "list_assets()" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_await_pagination_client_safe_translates_value_error(self):
        async def fail():
            raise ValueError("Invalid snapshot token")

        with pytest.raises(HTTPException, match="Invalid pagination request") as exc_info:
            await DatalakeService._await_pagination_client_safe(fail())

        assert exc_info.value.status_code == 400
        assert "Invalid snapshot token" in exc_info.value.detail


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case["service_method"]) for case in SERVICE_CASES],
)
@pytest.mark.asyncio
async def test_service_methods_map_requests_to_async_datalake(case, service, mock_datalake, datalake_objects):
    payload = case["payload_factory"](datalake_objects)
    mock_method = getattr(mock_datalake, case["datalake_method"])
    mock_method.return_value = case["datalake_return_factory"](datalake_objects)

    service_method = getattr(service, case["service_method"])
    result = await service_method() if payload is None else await service_method(payload)

    expected_args = case["expected_args_factory"](datalake_objects)
    expected_kwargs = case["expected_kwargs_factory"](datalake_objects)
    if case.get("sync_mock", False):
        mock_method.assert_called_once_with(*expected_args, **expected_kwargs)
    else:
        mock_method.assert_awaited_once_with(*expected_args, **expected_kwargs)

    if case["expected_output_type"] is None:
        assert result is None
        return

    assert isinstance(result, case["expected_output_type"])
    assert getattr(result, case["expected_output_field"]) == case["expected_output_factory"](datalake_objects)


@pytest.mark.asyncio
async def test_service_list_assets_page_maps_page_contract(service, mock_datalake, datalake_objects):
    page = CursorPage(
        items=[datalake_objects.asset],
        page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True, total_count=2),
    )
    mock_datalake.list_assets_page.return_value = page

    result = await service.list_assets_page(PageInput(filters={"kind": "image"}, limit=1, include_total=True))

    mock_datalake.list_assets_page.assert_awaited_once_with(
        filters={"kind": "image"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=True,
    )
    assert isinstance(result, AssetPageOutput)
    assert result.items == [datalake_objects.asset]
    assert result.page.next_cursor == "cursor-1"
    assert result.page.total_count == 2


@pytest.mark.asyncio
async def test_service_list_assets_page_translates_invalid_cursor(service, mock_datalake):
    mock_datalake.list_assets_page.side_effect = ValueError("Invalid snapshot token")

    with pytest.raises(HTTPException, match="Invalid pagination request") as exc_info:
        await service.list_assets_page(PageInput(filters={"kind": "image"}, limit=1, cursor="bad-cursor"))

    assert exc_info.value.status_code == 400
    assert "Invalid snapshot token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_service_collection_pages_map_page_contracts(service, mock_datalake, datalake_objects):
    collection_page = CursorPage(
        items=[datalake_objects.collection],
        page=PageInfo(limit=1, next_cursor="collection-cursor", has_more=True, total_count=2),
    )
    collection_item_page = CursorPage(
        items=[datalake_objects.collection_item],
        page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1),
    )
    mock_datalake.list_collections_page.return_value = collection_page
    mock_datalake.list_collection_items_page.return_value = collection_item_page

    collection_result = await service.list_collections_page(PageInput(filters={"status": "active"}, limit=1))
    collection_item_result = await service.list_collection_items_page(
        PageInput(filters={"collection_id": datalake_objects.collection.collection_id}, limit=1, include_total=True)
    )

    mock_datalake.list_collections_page.assert_awaited_once_with(
        filters={"status": "active"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    mock_datalake.list_collection_items_page.assert_awaited_once_with(
        filters={"collection_id": datalake_objects.collection.collection_id},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=True,
    )
    assert isinstance(collection_result, CollectionPageOutput)
    assert collection_result.items == [datalake_objects.collection]
    assert isinstance(collection_item_result, CollectionItemPageOutput)
    assert collection_item_result.items == [datalake_objects.collection_item]


@pytest.mark.asyncio
async def test_service_metadata_pages_map_page_contracts(service, mock_datalake, datalake_objects):
    retention_page = CursorPage(
        items=[datalake_objects.asset_retention],
        page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1),
    )
    schema_page = CursorPage(
        items=[datalake_objects.annotation_schema],
        page=PageInfo(limit=1, next_cursor="schema-cursor", has_more=True, total_count=2),
    )
    set_page = CursorPage(
        items=[datalake_objects.annotation_set],
        page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1),
    )
    mock_datalake.list_asset_retentions_page.return_value = retention_page
    mock_datalake.list_annotation_schemas_page.return_value = schema_page
    mock_datalake.list_annotation_sets_page.return_value = set_page

    retention_result = await service.list_asset_retentions_page(
        PageInput(filters={"asset_id": datalake_objects.asset.asset_id}, limit=1)
    )
    schema_result = await service.list_annotation_schemas_page(
        PageInput(filters={"task_type": "detection"}, limit=1, include_total=True)
    )
    set_result = await service.list_annotation_sets_page(PageInput(filters={"purpose": "ground_truth"}, limit=1))

    mock_datalake.list_asset_retentions_page.assert_awaited_once_with(
        filters={"asset_id": datalake_objects.asset.asset_id},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    mock_datalake.list_annotation_schemas_page.assert_awaited_once_with(
        filters={"task_type": "detection"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=True,
    )
    mock_datalake.list_annotation_sets_page.assert_awaited_once_with(
        filters={"purpose": "ground_truth"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    assert isinstance(retention_result, AssetRetentionPageOutput)
    assert isinstance(schema_result, AnnotationSchemaPageOutput)
    assert isinstance(set_result, AnnotationSetPageOutput)


@pytest.mark.asyncio
async def test_service_annotation_and_datum_pages_map_page_contracts(service, mock_datalake, datalake_objects):
    record_page = CursorPage(
        items=[datalake_objects.annotation_record],
        page=PageInfo(limit=1, next_cursor="record-cursor", has_more=True, total_count=2),
    )
    datum_page = CursorPage(
        items=[datalake_objects.datum],
        page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1),
    )
    mock_datalake.list_annotation_records_for_asset_page.return_value = record_page
    mock_datalake.list_annotation_records_page.return_value = record_page
    mock_datalake.list_datums_page.return_value = datum_page

    asset_record_result = await service.list_annotation_records_for_asset_page(
        ListAnnotationRecordsForAssetPageInput(
            asset_id=datalake_objects.asset.asset_id,
            limit=1,
            include_total=True,
            sort="subject_created_desc",
        )
    )
    record_result = await service.list_annotation_records_page(PageInput(filters={"label": "cat"}, limit=1))
    datum_result = await service.list_datums_page(PageInput(filters={"split": "train"}, limit=1))

    mock_datalake.list_annotation_records_for_asset_page.assert_awaited_once_with(
        datalake_objects.asset.asset_id,
        sort="subject_created_desc",
        limit=1,
        cursor=None,
        include_total=True,
    )
    mock_datalake.list_annotation_records_page.assert_awaited_once_with(
        filters={"label": "cat"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    mock_datalake.list_datums_page.assert_awaited_once_with(
        filters={"split": "train"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    assert isinstance(asset_record_result, AnnotationRecordPageOutput)
    assert isinstance(record_result, AnnotationRecordPageOutput)
    assert isinstance(datum_result, DatumPageOutput)


@pytest.mark.asyncio
async def test_service_list_dataset_versions_page_includes_dataset_name(service, mock_datalake, datalake_objects):
    page = CursorPage(
        items=[datalake_objects.dataset_version],
        page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1),
    )
    mock_datalake.list_dataset_versions_page.return_value = page

    result = await service.list_dataset_versions_page(
        ListDatasetVersionsPageInput(dataset_name="demo-dataset", filters={"version": "1.0"}, limit=1)
    )

    mock_datalake.list_dataset_versions_page.assert_awaited_once_with(
        dataset_name="demo-dataset",
        filters={"version": "1.0"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    assert isinstance(result, DatasetVersionPageOutput)
    assert result.items == [datalake_objects.dataset_version]
    assert result.page.has_more is False


@pytest.mark.asyncio
async def test_service_view_dataset_version_page_maps_expand_and_filters(service, mock_datalake):
    page = DatasetViewPage(
        items=[DatasetViewRow(datum_id="datum_1", split="train", metadata={"rank": 1})],
        page=PageInfo(limit=1, next_cursor="cursor-2", has_more=True, total_count=2),
        view=DatasetViewInfo(dataset_name="demo", version="1.0.0", sort="manifest_order"),
    )
    mock_datalake.view_dataset_version_page.return_value = page

    payload = ViewDatasetVersionPageInput(
        dataset_name="demo",
        version="1.0.0",
        limit=1,
        include_total=True,
        filters=[StructuredFilter(field="split", op="eq", value="train")],
        expand=DatasetViewExpand(assets=False, annotation_sets=False, annotation_records=False),
    )
    result = await service.view_dataset_version_page(payload)

    mock_datalake.view_dataset_version_page.assert_awaited_once_with(
        "demo",
        "1.0.0",
        limit=1,
        cursor=None,
        sort="manifest_order",
        filters=[StructuredFilter(field="split", op="eq", value="train")],
        expand=DatasetViewExpand(assets=False, annotation_sets=False, annotation_records=False),
        include_total=True,
    )
    assert isinstance(result, DatasetViewPageOutput)
    assert result.items[0].datum_id == "datum_1"
    assert result.page.next_cursor == "cursor-2"
    assert result.view.dataset_name == "demo"


@pytest.mark.asyncio
async def test_service_view_dataset_version_page_translates_invalid_cursor(service, mock_datalake):
    mock_datalake.view_dataset_version_page.side_effect = ValueError("Cursor filters do not match this request")

    payload = ViewDatasetVersionPageInput(
        dataset_name="demo",
        version="1.0.0",
        limit=1,
        cursor="bad-cursor",
    )

    with pytest.raises(HTTPException, match="Invalid pagination request") as exc_info:
        await service.view_dataset_version_page(payload)

    assert exc_info.value.status_code == 400
    assert "Cursor filters do not match this request" in exc_info.value.detail


@pytest.mark.asyncio
async def test_service_export_dataset_version_uses_sync_manager(service, datalake_objects):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    with patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls:
        manager = manager_cls.return_value
        manager.export_dataset_version = AsyncMock(return_value=bundle)

        result = await service.export_dataset_version(ExportDatasetVersionInput(dataset_name="demo", version="1.0"))

    assert isinstance(result, DatasetSyncBundleOutput)
    assert result.bundle == bundle
    manager.export_dataset_version.assert_awaited_once_with("demo", "1.0")


@pytest.mark.asyncio
async def test_service_export_sync_graph_and_payload_manifest_delegate(service, datalake_objects):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    with patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls:
        manager = manager_cls.return_value
        manager.export_dataset_version = AsyncMock(return_value=bundle)

        graph_out = await service.export_sync_graph(
            ExportDatasetVersionInput(dataset_name="demo-dataset", version="1.0"),
        )
        mf_out = await service.export_sync_payload_manifest(
            ExportDatasetVersionInput(dataset_name="demo-dataset", version="1.0"),
        )

    assert graph_out.bundle == bundle
    assert mf_out.payloads == []
    assert manager.export_dataset_version.await_count == 2


@pytest.mark.asyncio
async def test_service_streaming_import_start_inserts_dataset_import_session(service, mock_datalake):
    mock_datalake.dataset_import_session_database = SimpleNamespace(insert=AsyncMock())

    out = await service.streaming_import_start(
        DatasetStreamingImportStartInput(
            dataset_name="streaming-ds",
            version="2.0.0",
            manifest_total=3,
            source_alias="edge",
        ),
    )

    assert out.session_id
    assert out.expires_at is not None
    mock_datalake.dataset_import_session_database.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_import_dataset_version_prepare_uses_sync_manager(service, datalake_objects):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    request = DatasetSyncImportRequest(bundle=bundle)
    plan = DatasetSyncImportPlan(
        dataset_name="demo",
        version="1.0",
        transfer_policy="copy_if_missing",
        ready_to_commit=True,
    )
    with patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls:
        manager = manager_cls.return_value
        manager.plan_import = AsyncMock(return_value=plan)

        result = await service.import_dataset_version_prepare(request)

    assert isinstance(result, DatasetSyncImportPlanOutput)
    assert result.plan == plan
    manager.plan_import.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_service_import_dataset_version_commit_uses_sync_manager(service, datalake_objects):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    request = DatasetSyncImportRequest(bundle=bundle)
    commit_result = DatasetSyncCommitResult(dataset_version=datalake_objects.dataset_version, created_assets=1)
    with patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls:
        manager = manager_cls.return_value
        manager.commit_import = AsyncMock(return_value=commit_result)

        result = await service.import_dataset_version_commit(request)

    assert isinstance(result, DatasetSyncCommitResultOutput)
    assert result.result == commit_result
    manager.commit_import.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_service_import_session_commit_metadata_uses_single_lake_manager(service, datalake_objects):
    session = Mock()
    session.metadata_graph_committed = False
    session.transfer_policy = "copy_if_missing"
    session.target_object_match_policy = "checksum"
    session.origin_lake_id = "lake-a"
    session.preserve_ids = True
    session.mount_map = {}
    session.planning_batch_size = 500
    session.planning_concurrency = 8
    session.transfer_batch_size = 250
    session.transfer_concurrency = 8
    session.greenfield_skip_target_object_probes = True
    session.greenfield_skip_target_metadata_probes = True
    session.commit_progress_every_items = 100
    session.commit_progress_every_seconds = 1.0
    session.required_asset_ids = []
    session.import_session_id = "session-1"
    session.expires_at = "2099-01-01T00:00:00Z"

    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    commit_result = DatasetSyncCommitResult(dataset_version=datalake_objects.dataset_version, created_assets=1)
    service._datalake.dataset_import_session_database = SimpleNamespace(update=AsyncMock())
    with (
        patch("mindtrace.datalake.service._import_session_expired", return_value=False),
        patch("mindtrace.datalake.service._load_import_session_bundle", new=AsyncMock(return_value=bundle)),
        patch.object(service, "_require_open_import_session", new=AsyncMock(return_value=session)),
        patch.object(service, "_ensure_datalake", new=AsyncMock(return_value=service._datalake)),
        patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls,
    ):
        manager = manager_cls.return_value
        manager.commit_import = AsyncMock(return_value=commit_result)

        result = await service.import_session_commit_metadata(DatasetImportSessionCommitInput(session_id="session-1"))

    assert isinstance(result, DatasetSyncCommitResultOutput)
    assert result.result == commit_result
    manager_cls.assert_called_once_with(service._datalake)
    manager.commit_import.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_import_prepare_start_runs_background_job(service, datalake_objects):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    request = DatasetSyncImportRequest(bundle=bundle)
    plan = DatasetSyncImportPlan(
        dataset_name="demo",
        version="1.0",
        transfer_policy="copy_if_missing",
        ready_to_commit=True,
    )
    with patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls:
        manager = manager_cls.return_value
        manager.plan_import = AsyncMock(return_value=plan)

        started = await service.import_dataset_version_prepare_start(request)
        await service._dataset_sync_jobs[started.job_id].task
        status = await service.import_dataset_version_job_status(DatasetSyncJobStatusInput(job_id=started.job_id))
        result = await service.import_dataset_version_job_result(DatasetSyncJobStatusInput(job_id=started.job_id))

    assert isinstance(started, DatasetSyncJobStartOutput)
    assert isinstance(status, DatasetSyncJobStatusOutput)
    assert isinstance(result, DatasetSyncJobResultOutput)
    assert status.status == "completed"
    assert status.progress.phase == "complete"
    assert result.plan == plan
    assert result.result is None
    manager.plan_import.assert_awaited_once()
    assert manager.plan_import.await_args.args == (request,)
    assert "progress_callback" in manager.plan_import.await_args.kwargs


@pytest.mark.asyncio
async def test_service_import_start_runs_background_job(service, datalake_objects):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    request = DatasetSyncImportRequest(bundle=bundle)
    commit_result = DatasetSyncCommitResult(dataset_version=datalake_objects.dataset_version, created_assets=1)
    with patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls:
        manager = manager_cls.return_value
        manager.commit_import = AsyncMock(return_value=commit_result)

        started = await service.import_dataset_version_start(request)
        await service._dataset_sync_jobs[started.job_id].task
        result = await service.import_dataset_version_job_result(DatasetSyncJobStatusInput(job_id=started.job_id))

    assert started.mode == "import"
    assert result.status == "completed"
    assert result.result == commit_result
    assert result.plan is None
    manager.commit_import.assert_awaited_once()
    assert manager.commit_import.await_args.args == (request,)
    assert "progress_callback" in manager.commit_import.await_args.kwargs


@pytest.mark.asyncio
async def test_service_import_prepare_failure_surfaces_error_detail(service, datalake_objects):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    request = DatasetSyncImportRequest(bundle=bundle)
    with patch("mindtrace.datalake.service.DatasetSyncManager") as manager_cls:
        manager = manager_cls.return_value
        manager.plan_import = AsyncMock(side_effect=KeyError("minio"))

        started = await service.import_dataset_version_prepare_start(request)
        await service._dataset_sync_jobs[started.job_id].task
        status = await service.import_dataset_version_job_status(DatasetSyncJobStatusInput(job_id=started.job_id))
        result = await service.import_dataset_version_job_result(DatasetSyncJobStatusInput(job_id=started.job_id))

    assert result.status == "failed"
    assert status.status == "failed"
    assert status.error_detail is not None
    assert status.error_detail.traceback == result.error_detail.traceback
    assert result.error is not None
    assert "KeyError" in result.error
    assert "minio" in result.error
    assert result.error_detail is not None
    assert result.error_detail.exception_type.endswith("KeyError")
    assert "minio" in result.error_detail.exception_repr
    assert result.error_detail.traceback is not None
    assert "_run_dataset_sync_job" in result.error_detail.traceback


@pytest.mark.asyncio
async def test_service_import_job_status_raises_for_unknown_job(service):
    with pytest.raises(HTTPException) as exc_info:
        await service.import_dataset_version_job_status(DatasetSyncJobStatusInput(job_id="missing"))

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_service_replication_upsert_batch_uses_replication_manager(service, datalake_objects):
    request = ReplicationBatchRequest(
        assets=[datalake_objects.asset], datums=[datalake_objects.datum], origin_lake_id="source"
    )
    batch_result = ReplicationBatchResult(created_assets=1, created_datums=1)
    with patch("mindtrace.datalake.service.ReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.upsert_metadata_batch = AsyncMock(return_value=batch_result)

        result = await service.replication_upsert_batch(request)

    assert isinstance(result, ReplicationBatchResultOutput)
    assert result.result == batch_result
    manager.upsert_metadata_batch.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_service_replication_hydrate_asset_payload_uses_replication_manager(service, datalake_objects):
    request = ReplicationHydrateAssetPayloadInput(asset_id=datalake_objects.asset.asset_id, mount_map={"raw": "minio"})
    with patch("mindtrace.datalake.service.ReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.hydrate_asset_payload = AsyncMock(return_value=datalake_objects.asset)

        result = await service.replication_hydrate_asset_payload(request)

    assert isinstance(result, AssetOutput)
    assert result.asset == datalake_objects.asset
    manager.hydrate_asset_payload.assert_awaited_once_with(datalake_objects.asset.asset_id, mount_map={"raw": "minio"})


@pytest.mark.asyncio
async def test_service_replication_reconcile_uses_replication_manager(service):
    request = ReplicationReconcileRequest(
        asset_ids=["asset_1"], limit=5, include_failed=False, mount_map={"raw": "minio"}
    )
    reconcile_result = ReplicationReconcileResult(
        attempted_asset_ids=["asset_1"],
        verified_asset_ids=["asset_1"],
        failed_asset_ids=[],
        skipped_asset_ids=[],
    )
    with patch("mindtrace.datalake.service.ReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.reconcile_pending_payloads = AsyncMock(return_value=reconcile_result)

        result = await service.replication_reconcile(request)

    assert isinstance(result, ReplicationReconcileResultOutput)
    assert result.result == reconcile_result
    manager.reconcile_pending_payloads.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_service_replication_mark_local_delete_eligible_uses_replication_manager(service, datalake_objects):
    request = ReplicationMarkLocalDeleteEligibleInput(asset_id=datalake_objects.asset.asset_id)
    with patch("mindtrace.datalake.service.ReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.mark_local_delete_eligible = AsyncMock(return_value=datalake_objects.asset)

        result = await service.replication_mark_local_delete_eligible(request)

    assert isinstance(result, AssetOutput)
    assert result.asset == datalake_objects.asset
    manager.mark_local_delete_eligible.assert_awaited_once_with(datalake_objects.asset.asset_id, when=None)


@pytest.mark.asyncio
async def test_service_replication_delete_local_payload_uses_replication_manager(service, datalake_objects):
    request = GetByIdInput(id=datalake_objects.asset.asset_id)
    with patch("mindtrace.datalake.service.ReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.delete_local_payload = AsyncMock(return_value=datalake_objects.asset)

        result = await service.replication_delete_local_payload(request)

    assert isinstance(result, AssetOutput)
    assert result.asset == datalake_objects.asset
    manager.delete_local_payload.assert_awaited_once_with(datalake_objects.asset.asset_id)


@pytest.mark.asyncio
async def test_service_replication_reclaim_verified_payloads_uses_replication_manager(service):
    request = ReplicationReclaimRequest(asset_ids=["asset_1"], limit=5, require_verified_payload=True)
    reclaim_result = ReplicationReclaimResult(
        attempted_asset_ids=["asset_1"],
        reclaimed_asset_ids=["asset_1"],
        failed_asset_ids=[],
        skipped_asset_ids=[],
    )
    with patch("mindtrace.datalake.service.ReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.reclaim_verified_payloads = AsyncMock(return_value=reclaim_result)

        result = await service.replication_reclaim_verified_payloads(request)

    assert isinstance(result, ReplicationReclaimResultOutput)
    assert result.result == reclaim_result
    manager.reclaim_verified_payloads.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_service_replication_status_uses_replication_manager(service):
    status_result = ReplicationStatusResult(
        asset_counts_by_payload_status={"missing": 1, "uploading": 0, "present": 0, "corrupt": 0},
        pending_asset_ids=["asset_1"],
        failed_asset_ids=[],
    )
    with patch("mindtrace.datalake.service.ReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.status = AsyncMock(return_value=status_result)

        result = await service.replication_status()

    assert isinstance(result, ReplicationStatusOutput)
    assert result.status == status_result
    manager.status.assert_awaited_once_with()


class TestDatalakeServiceModuleHelpers:
    def test_import_session_expired_respects_naive_expiry_as_utc(self):
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        past_naive = datetime(2026, 1, 1)
        future_naive = datetime(2026, 6, 1)
        assert _import_session_expired(past_naive, now=now) is True
        assert _import_session_expired(future_naive, now=now) is False

    def test_import_session_expired_aware_deadline(self):
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        deadline = datetime(2026, 1, 3, tzinfo=timezone.utc)
        assert _import_session_expired(deadline, now=now) is False


@pytest.mark.asyncio
async def test_delete_import_session_bundle_blob_skips_when_no_storage_ref(mock_datalake):
    sess = DatasetImportSession(expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc), bundle_storage_ref=None)
    mock_datalake.delete_object = AsyncMock()
    await _delete_import_session_bundle_blob(mock_datalake, sess)
    mock_datalake.delete_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_import_session_bundle_blob_swallows_delete_errors(mock_datalake):
    ref = StorageRef(mount="temp", name="bundle.json", version="v1")
    sess = DatasetImportSession(expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc), bundle_storage_ref=ref)
    mock_datalake.delete_object = AsyncMock(side_effect=RuntimeError("network"))
    await _delete_import_session_bundle_blob(mock_datalake, sess)
    mock_datalake.delete_object.assert_awaited_once_with(ref)


@pytest.mark.asyncio
async def test_load_import_session_bundle_from_storage(mock_datalake, datalake_objects):
    dumped = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version).model_dump(mode="json")
    raw = json.dumps(dumped).encode("utf-8")
    ref = StorageRef(mount="temp", name="b.json", version="v1")
    sess = DatasetImportSession(
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        bundle_storage_ref=ref,
        bundle_data={},
    )
    mock_datalake.get_object = AsyncMock(return_value=bytearray(raw))

    bundle = await _load_import_session_bundle(mock_datalake, sess)

    assert bundle.dataset_version.dataset_name == datalake_objects.dataset_version.dataset_name
    mock_datalake.get_object.assert_awaited_once_with(ref)


@pytest.mark.asyncio
async def test_load_import_session_bundle_fallback_to_inline_data(mock_datalake, datalake_objects):
    dumped = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version).model_dump(mode="json")
    sess = DatasetImportSession(
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        bundle_storage_ref=None,
        bundle_data=dumped,
    )

    bundle = await _load_import_session_bundle(mock_datalake, sess)

    assert bundle.dataset_version.dataset_version_id == datalake_objects.dataset_version.dataset_version_id
    mock_datalake.get_object.assert_not_called()


@pytest.mark.asyncio
async def test_load_import_session_bundle_raises_when_empty(mock_datalake):
    sess = DatasetImportSession(
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        bundle_storage_ref=None,
        bundle_data={},
    )
    with pytest.raises(ValueError, match="neither bundle_storage_ref nor bundle_data"):
        await _load_import_session_bundle(mock_datalake, sess)


def test_dataset_import_session_status_output_shapes_progress_and_counts():
    expires = datetime(2099, 1, 1, tzinfo=timezone.utc)
    sess = DatasetImportSession(
        expires_at=expires,
        status="open",
        import_session_id="imp-1",
        required_asset_ids=["a", "b"],
        verified_asset_ids=["a"],
        import_progress_phase="transferring",
        import_progress_completed_items=1,
        import_progress_total_items=10,
        import_progress_message="copying",
    )
    out = _dataset_import_session_status_output(sess)
    assert out.session_id == "imp-1"
    assert out.required_asset_count == 2
    assert out.verified_asset_count == 1
    assert out.pending_asset_count == 1
    assert out.progress is not None
    assert out.progress.phase == "transferring"
    assert out.progress.completed_items == 1


@pytest.mark.asyncio
async def test_import_session_progress_writer_persists_and_throttles(monkeypatch):
    dl = MagicMock()
    dl.dataset_import_session_database = SimpleNamespace(update=AsyncMock())

    sess = DatasetImportSession(expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    writer = _ImportSessionProgressWriter(dl, sess, min_interval_s=100.0)

    ticks = {"t": 0.0}

    def mono():
        v = ticks["t"]
        ticks["t"] += 50.0
        return v

    monkeypatch.setattr("mindtrace.datalake.service.time.monotonic", mono)

    p1 = DatasetSyncProgress(phase="planning", message="plan")
    await writer.persist(p1, force=False)
    assert dl.dataset_import_session_database.update.await_count == 1
    assert sess.import_stage == "planning_metadata_commit"

    await writer.persist(p1, force=False)
    assert dl.dataset_import_session_database.update.await_count == 1

    await writer.persist(p1, force=True)
    assert dl.dataset_import_session_database.update.await_count == 2


@pytest.mark.asyncio
async def test_import_session_progress_writer_failed_truncates(monkeypatch):
    dl = MagicMock()
    dl.dataset_import_session_database = SimpleNamespace(update=AsyncMock())
    sess = DatasetImportSession(expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    writer = _ImportSessionProgressWriter(dl, sess)

    monkeypatch.setattr("mindtrace.datalake.service.time.monotonic", lambda: 0.0)
    detail = "x" * 9000
    await writer.persist_failed(detail)

    dl.dataset_import_session_database.update.assert_awaited_once()
    assert sess.import_progress_error is not None
    assert len(sess.import_progress_error) == 8192


@pytest.mark.asyncio
async def test_import_session_progress_writer_callable_aliases_persist(monkeypatch):
    dl = MagicMock()
    dl.dataset_import_session_database = SimpleNamespace(update=AsyncMock())
    sess = DatasetImportSession(expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    writer = _ImportSessionProgressWriter(dl, sess)
    monkeypatch.setattr("mindtrace.datalake.service.time.monotonic", lambda: 0.0)

    prog = DatasetSyncProgress(phase="failed", message="boom")
    await writer(prog)
    assert sess.import_progress_phase == "failed"


@pytest.mark.asyncio
async def test_service_shutdown_cleanup_swallows_errors_from_super(mock_datalake):
    svc = DatalakeService(async_datalake=mock_datalake, live_service=False, initialize_on_startup=False)
    svc._owns_datalake = False
    with patch(
        "mindtrace.services.Service.shutdown_cleanup", new=AsyncMock(side_effect=RuntimeError("base shutdown boom"))
    ):
        await svc.shutdown_cleanup()


@pytest.mark.asyncio
async def test_service_shutdown_cleanup_closes_even_when_close_raises(mock_datalake):
    svc = DatalakeService(async_datalake=mock_datalake, live_service=False, initialize_on_startup=False)
    svc._owns_datalake = True
    mock_datalake.close = AsyncMock(side_effect=RuntimeError("motor close boom"))
    await svc.shutdown_cleanup()
    mock_datalake.close.assert_awaited_once()
    assert svc._datalake is None
    assert svc._initialized is False


@pytest.mark.asyncio
async def test_service_shutdown_cleanup_cancels_dataset_sync_tasks(mock_datalake):
    svc = DatalakeService(async_datalake=mock_datalake, live_service=False, initialize_on_startup=False)
    svc._owns_datalake = False

    async def blocker():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

    t = asyncio.create_task(blocker())
    svc._dataset_sync_jobs["jid"] = _DatasetSyncJobState(job_id="jid", mode="prepare", task=t)

    with patch("mindtrace.services.Service.shutdown_cleanup", new=AsyncMock(side_effect=RuntimeError("ignore"))):
        await asyncio.wait_for(svc.shutdown_cleanup(), timeout=3.0)

    assert svc._dataset_sync_jobs["jid"].task is t
    assert t.cancelled()


@pytest.mark.asyncio
async def test_service_get_object_raises_409_when_unreadable(service, datalake_objects, mock_datalake):
    mock_datalake.get_object = AsyncMock(side_effect=RegistryObjectNotFound("missing"))

    with pytest.raises(HTTPException) as exc_info:
        await service.get_object(GetObjectInput(storage_ref=datalake_objects.storage_ref))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "OBJECT_NOT_READABLE"


@pytest.mark.asyncio
async def test_service_wipe_datalake_wraps_backend_response(service, mock_datalake):
    mock_datalake.wipe = AsyncMock(
        return_value={
            "database": "unit",
            "deleted_payloads": False,
            "deleted_metadata": True,
            "clear_registry_metadata": False,
            "cleared_mounts": ["temp"],
        }
    )

    out = await service.wipe_datalake(
        DatalakeWipeInput(delete_payloads=False, delete_metadata=True, clear_registry_metadata=False)
    )

    mock_datalake.wipe.assert_awaited_once_with(
        delete_payloads=False,
        delete_metadata=True,
        clear_registry_metadata=False,
    )
    assert out.database == "unit"


@pytest.mark.asyncio
async def test_service_verify_integrity_duplicate_manifest(service, datalake_objects, mock_datalake):
    dv = datalake_objects.dataset_version.model_copy(
        update={"manifest": [datalake_objects.datum.datum_id, datalake_objects.datum.datum_id]}
    )
    mock_datalake.get_dataset_version = AsyncMock(return_value=dv)
    mock_datalake.get_datum = AsyncMock(return_value=datalake_objects.datum)

    out = await service.verify_dataset_integrity(
        DatasetIntegrityVerifyInput(dataset_name="demo-dataset", version="1.0", mode="fast", sample_limit=5)
    )

    assert out.duplicate_manifest_count == 1
    assert out.ok is False


@pytest.mark.asyncio
async def test_service_verify_integrity_fast_mode_missing_manifest_datum(service, mock_datalake):
    dv = DatasetVersion(dataset_name="d", version="v", manifest=["missing-datum"])

    mock_datalake.get_dataset_version = AsyncMock(return_value=dv)
    mock_datalake.get_datum = AsyncMock(side_effect=DocumentNotFoundError("boom"))

    out = await service.verify_dataset_integrity(
        DatasetIntegrityVerifyInput(dataset_name="d", version="v", mode="fast"),
    )

    assert out.missing_manifest_datum_count == 1
    assert out.samples and out.samples[0].kind == "missing_manifest_datum"


@pytest.mark.asyncio
async def test_service_verify_integrity_full_db_missing_annotation_set(service, datalake_objects, mock_datalake):
    datum = datalake_objects.datum
    dv = datalake_objects.dataset_version.model_copy(update={"manifest": [datum.datum_id]})
    mock_datalake.get_dataset_version = AsyncMock(return_value=dv)
    mock_datalake.get_datum = AsyncMock(
        return_value=datum.model_copy(update={"annotation_set_ids": ["missing-set"]}),
    )
    mock_datalake.get_asset = AsyncMock(return_value=datalake_objects.asset)
    mock_datalake.get_annotation_set = AsyncMock(side_effect=DocumentNotFoundError("no set"))

    out = await service.verify_dataset_integrity(
        DatasetIntegrityVerifyInput(dataset_name="demo-dataset", version="1.0", mode="full-db"),
    )
    assert out.missing_annotation_set_count == 1


@pytest.mark.asyncio
async def test_service_verify_integrity_full_db_mask_and_schema_gaps(service, datalake_objects, mock_datalake):
    datum = datalake_objects.datum
    dv = datalake_objects.dataset_version.model_copy(update={"manifest": [datum.datum_id]})
    aset = datalake_objects.annotation_set.model_copy(
        update={"annotation_record_ids": [datalake_objects.annotation_record.annotation_id]}
    )
    record = datalake_objects.annotation_record.model_copy(update={"geometry": {"mask_asset_id": "mask-1"}})

    mock_datalake.get_dataset_version = AsyncMock(return_value=dv)
    mock_datalake.get_datum = AsyncMock(
        return_value=datum.model_copy(update={"annotation_set_ids": [aset.annotation_set_id]}),
    )
    mock_datalake.get_asset = AsyncMock(
        side_effect=[
            datalake_objects.asset,
            DocumentNotFoundError("mask missing"),
        ],
    )
    mock_datalake.get_annotation_set = AsyncMock(return_value=aset)
    mock_datalake.get_annotation_record = AsyncMock(return_value=record)
    mock_datalake.get_annotation_schema = AsyncMock(side_effect=DocumentNotFoundError("schema missing"))

    out = await service.verify_dataset_integrity(
        DatasetIntegrityVerifyInput(dataset_name="demo-dataset", version="1.0", mode="full-db", sample_limit=10),
    )
    assert out.missing_mask_asset_count == 1
    assert out.missing_annotation_schema_count == 1


@pytest.mark.asyncio
async def test_service_verify_integrity_full_lake_registry_and_mounts(service, datalake_objects, mock_datalake):
    datum = datalake_objects.datum
    dv = datalake_objects.dataset_version.model_copy(update={"manifest": [datum.datum_id]})

    mock_datalake.get_dataset_version = AsyncMock(return_value=dv)
    mock_datalake.get_datum = AsyncMock(return_value=datum)
    mock_datalake.get_asset = AsyncMock(return_value=datalake_objects.asset)

    mock_datalake.get_mounts.return_value = {
        "mounts": [{"name": datalake_objects.storage_ref.mount}],
        "default_mount": datalake_objects.storage_ref.mount,
    }
    mock_datalake.object_exists = AsyncMock(return_value=False)

    captured: list[tuple] = []

    def fake_print(*args, **kwargs):
        captured.append(args)

    with patch("builtins.print", side_effect=fake_print):
        out = await service.verify_dataset_integrity(
            DatasetIntegrityVerifyInput(dataset_name="demo-dataset", version="1.0", mode="full-lake"),
        )

        assert captured
        assert out.registry_missing_payload_count >= 1

        unknown_mount_asset = datalake_objects.asset.model_copy(
            update={"storage_ref": StorageRef(mount="unknown-mount", name="x", version="v1")},
        )
        mock_datalake.get_asset = AsyncMock(return_value=unknown_mount_asset)

        out2 = await service.verify_dataset_integrity(
            DatasetIntegrityVerifyInput(dataset_name="demo-dataset", version="1.0", mode="full-lake"),
        )
        assert out2.invalid_mount_count >= 1

        mock_datalake.object_exists = AsyncMock(side_effect=FileNotFoundError("registry"))

        mock_datalake.get_asset = AsyncMock(return_value=datalake_objects.asset)

        out3 = await service.verify_dataset_integrity(
            DatasetIntegrityVerifyInput(dataset_name="demo-dataset", version="1.0", mode="full-lake"),
        )
        assert out3.registry_missing_payload_count >= 1


@pytest.mark.asyncio
async def test_dataset_sync_job_not_found_raises(mock_datalake):
    svc = DatalakeService(async_datalake=mock_datalake, live_service=False, initialize_on_startup=False)
    with pytest.raises(HTTPException) as ei:
        svc._get_dataset_sync_job("nope")

    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_run_dataset_sync_job_fails_for_unsupported_mode(service, datalake_objects, mock_datalake):
    bundle = DatasetSyncBundle(dataset_version=datalake_objects.dataset_version)
    request = DatasetSyncImportRequest(bundle=bundle)
    job = _DatasetSyncJobState(job_id="jid", mode="not-a-real-mode")

    service._ensure_datalake = AsyncMock(return_value=mock_datalake)

    await service._run_dataset_sync_job(job, request)

    assert job.status == "failed"
    assert job.error_detail is not None
    assert "Unsupported dataset sync job mode" in (job.error or "")
