import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.replication_types import ReplicationBatchRequest, ReplicationBatchResult, ReplicationStatusResult
from mindtrace.datalake.service import DatalakeService
from mindtrace.datalake.service_types import (
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
    DatasetSyncBundleOutput,
    DatasetSyncCommitResultOutput,
    DatasetSyncImportPlanOutput,
    DatasetVersionListOutput,
    ReplicationBatchResultOutput,
    ReplicationStatusOutput,
    DatasetVersionOutput,
    DatumListOutput,
    DatumOutput,
    ExportDatasetVersionInput,
    GetAnnotationSchemaByNameVersionInput,
    GetByIdInput,
    GetDatasetVersionInput,
    GetObjectInput,
    HeadObjectInput,
    ListDatasetVersionsInput,
    ListInput,
    MountsOutput,
    ObjectDataOutput,
    ObjectHeadOutput,
    ObjectOutput,
    ObjectUploadSessionOutput,
    PutObjectInput,
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
)
from mindtrace.datalake.sync_types import DatasetSyncBundle, DatasetSyncCommitResult, DatasetSyncImportPlan, DatasetSyncImportRequest
from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    DirectUploadSession,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)


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
    )


@pytest.fixture
def mock_datalake():
    return Mock(spec=AsyncDatalake)


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
            annotation_set_id=o.annotation_set.annotation_set_id,
            annotations=[
                {
                    "kind": "bbox",
                    "label": "cat",
                    "source": {"type": "human", "name": "annotator"},
                    "geometry": {"x": 1, "y": 2, "w": 3, "h": 4},
                }
            ],
        ),
        "datalake_method": "add_annotation_records",
        "datalake_return_factory": lambda o: [o.annotation_record],
        "expected_output_type": AddedAnnotationRecordsOutput,
        "expected_output_field": "annotation_records",
        "expected_output_factory": lambda o: [o.annotation_record],
        "expected_args_factory": lambda o: (
            o.annotation_set.annotation_set_id,
            [
                {
                    "kind": "bbox",
                    "label": "cat",
                    "source": {"type": "human", "name": "annotator"},
                    "geometry": {"x": 1, "y": 2, "w": 3, "h": 4},
                }
            ],
        ),
        "expected_kwargs_factory": lambda o: {},
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
        assert service.app.router.on_shutdown[-1] == service._shutdown_cleanup
        assert "objects.put" in service.endpoints
        assert "objects.upload_session.create" in service.endpoints
        assert "assets.create_from_uploaded_object" in service.endpoints
        assert "annotation_records.add" in service.endpoints
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

        await service._shutdown_cleanup()

        cancel.assert_called_once_with()
        assert service._upload_reconciler_task is None

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_returns_when_no_reconciler_task(self, service):
        service._upload_reconciler_task = None

        await service._shutdown_cleanup()

        assert service._upload_reconciler_task is None

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

        service = DatalakeService(
            mongo_db_uri="mongodb://localhost:27017",
            mongo_db_name="mindtrace",
            mounts=["mount-a"],
            default_mount="nas",
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
async def test_service_replication_upsert_batch_uses_replication_manager(service, datalake_objects):
    request = ReplicationBatchRequest(assets=[datalake_objects.asset], datums=[datalake_objects.datum], origin_lake_id="source")
    batch_result = ReplicationBatchResult(created_assets=1, created_datums=1)
    with patch("mindtrace.datalake.service.MetadataFirstReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.upsert_metadata_batch = AsyncMock(return_value=batch_result)

        result = await service.replication_upsert_batch(request)

    assert isinstance(result, ReplicationBatchResultOutput)
    assert result.result == batch_result
    manager.upsert_metadata_batch.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_service_replication_status_uses_replication_manager(service):
    status_result = ReplicationStatusResult(
        asset_counts_by_payload_status={"pending": 1, "transferring": 0, "uploaded": 0, "verified": 0, "failed": 0},
        pending_asset_ids=["asset_1"],
        failed_asset_ids=[],
    )
    with patch("mindtrace.datalake.service.MetadataFirstReplicationManager") as manager_cls:
        manager = manager_cls.return_value
        manager.status = AsyncMock(return_value=status_result)

        result = await service.replication_status()

    assert isinstance(result, ReplicationStatusOutput)
    assert result.status == status_result
    manager.status.assert_awaited_once_with()
