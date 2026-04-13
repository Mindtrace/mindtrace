import base64
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo import MongoClient

from mindtrace.datalake import DatalakeService, StorageRef, SubjectRef
from mindtrace.datalake.service_types import (
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
    DatalakeHealthOutput,
    DatalakeSummaryOutput,
    DatasetVersionListOutput,
    DatasetVersionOutput,
    DatumListOutput,
    DatumOutput,
    MountsOutput,
    ObjectDataOutput,
    ObjectHeadOutput,
    ObjectOutput,
    ObjectUploadSessionOutput,
    ResolvedCollectionItemOutput,
    ResolvedDatasetVersionOutput,
    ResolvedDatumOutput,
)
from mindtrace.services.core.types import (
    ClassNameOutput,
    EndpointsOutput,
    HeartbeatOutput,
    ServerIDOutput,
    StatusOutput,
)

from .conftest import InProcessServiceConnectionManager

MONGO_URL = "mongodb://localhost:27018"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _cleanup_service_database(db_name: str) -> None:
    client = MongoClient(MONGO_URL)
    try:
        client.drop_database(db_name)
    finally:
        client.close()


class TestDatalakeServiceIntegration:
    def test_datalake_service_default_endpoints(self, datalake_service_local_manager):
        endpoints = datalake_service_local_manager.endpoints()
        status = datalake_service_local_manager.status()
        heartbeat = datalake_service_local_manager.heartbeat()
        server_id = datalake_service_local_manager.server_id()
        class_name = datalake_service_local_manager.class_name()

        assert isinstance(endpoints, EndpointsOutput)
        assert isinstance(status, StatusOutput)
        assert isinstance(heartbeat, HeartbeatOutput)
        assert isinstance(server_id, ServerIDOutput)
        assert isinstance(class_name, ClassNameOutput)

        assert class_name.class_name == "DatalakeService"
        assert "health" in endpoints.endpoints
        assert "objects.put" in endpoints.endpoints
        assert "annotation_records.add" in endpoints.endpoints
        assert "dataset_versions.resolve" in endpoints.endpoints
        assert heartbeat.heartbeat.server_id == server_id.server_id

    @pytest.mark.asyncio
    async def test_datalake_service_async_default_endpoints(self, datalake_service_local_manager):
        health = await datalake_service_local_manager.ahealth()
        endpoints = await datalake_service_local_manager.aendpoints()
        class_name = await datalake_service_local_manager.aclass_name()

        assert isinstance(health, DatalakeHealthOutput)
        assert isinstance(endpoints, EndpointsOutput)
        assert isinstance(class_name, ClassNameOutput)
        assert class_name.class_name == "DatalakeService"
        assert "assets.create" in endpoints.endpoints

    @pytest.mark.asyncio
    async def test_datalake_service_startup_initialize_creates_datalake(self, datalake_mounts):
        db_name = f"test_datalake_service_startup_{uuid4().hex}"
        service = DatalakeService(
            mongo_db_uri=MONGO_URL,
            mongo_db_name=db_name,
            mounts=datalake_mounts,
            default_mount="local",
            initialize_on_startup=False,
        )

        assert service._datalake is None
        assert service._initialized is False

        await service._startup_initialize()

        assert service._datalake is not None
        assert service._initialized is True

        _cleanup_service_database(db_name)

    @pytest.mark.asyncio
    async def test_datalake_service_requires_mongo_config_to_initialize(self):
        service = DatalakeService(live_service=False, initialize_on_startup=False)

        with pytest.raises(HTTPException, match="missing mongo_db_uri and/or mongo_db_name"):
            await service._ensure_datalake()

    def test_datalake_service_end_to_end(self, datalake_service_local_manager):
        hopper_path = Path("tests/resources/hopper.png")
        image_bytes = hopper_path.read_bytes()
        encoded_image = _b64(image_bytes)

        health = datalake_service_local_manager.health()
        mounts = datalake_service_local_manager.mounts()

        stored_object = datalake_service_local_manager.objects_put(
            name="service-hopper.png",
            data_base64=encoded_image,
            metadata={"source_path": str(hopper_path)},
        )
        loaded_object = datalake_service_local_manager.objects_get(storage_ref=stored_object.storage_ref)
        headed_object = datalake_service_local_manager.objects_head(storage_ref=stored_object.storage_ref)
        copied_object = datalake_service_local_manager.objects_copy(
            source=stored_object.storage_ref,
            target_mount="local",
            target_name="service-hopper-copy.png",
        )

        asset = datalake_service_local_manager.assets_create(
            kind="image",
            media_type="image/png",
            storage_ref=stored_object.storage_ref,
            checksum="sha256:service",
            size_bytes=len(image_bytes),
            metadata={"source": "integration"},
            created_by="pytest",
        )
        fetched_asset = datalake_service_local_manager.assets_get(id=asset.asset.asset_id)
        listed_assets = datalake_service_local_manager.assets_list(filters={"kind": "image"})
        updated_asset = datalake_service_local_manager.assets_update_metadata(
            asset_id=asset.asset.asset_id,
            metadata={"stage": "updated"},
        )

        collection = datalake_service_local_manager.collections_create(
            name="service-collection",
            description="service integration collection",
            metadata={"suite": "integration"},
            created_by="pytest",
        )
        fetched_collection = datalake_service_local_manager.collections_get(id=collection.collection.collection_id)
        listed_collections = datalake_service_local_manager.collections_list(filters={"status": "active"})
        updated_collection = datalake_service_local_manager.collections_update(
            collection_id=collection.collection.collection_id,
            changes={"status": "archived"},
        )

        collection_item = datalake_service_local_manager.collection_items_create(
            collection_id=collection.collection.collection_id,
            asset_id=asset.asset.asset_id,
            split="train",
            metadata={"role": "example"},
            added_by="pytest",
        )
        fetched_collection_item = datalake_service_local_manager.collection_items_get(
            id=collection_item.collection_item.collection_item_id
        )
        listed_collection_items = datalake_service_local_manager.collection_items_list(
            filters={"collection_id": collection.collection.collection_id}
        )
        resolved_collection_item = datalake_service_local_manager.collection_items_resolve(
            id=collection_item.collection_item.collection_item_id
        )
        updated_collection_item = datalake_service_local_manager.collection_items_update(
            collection_item_id=collection_item.collection_item.collection_item_id,
            changes={"status": "hidden"},
        )

        asset_retention = datalake_service_local_manager.asset_retentions_create(
            asset_id=asset.asset.asset_id,
            owner_type="manual_pin",
            owner_id=collection.collection.collection_id,
            metadata={"suite": "integration"},
            created_by="pytest",
        )
        fetched_asset_retention = datalake_service_local_manager.asset_retentions_get(
            id=asset_retention.asset_retention.asset_retention_id
        )
        listed_asset_retentions = datalake_service_local_manager.asset_retentions_list(
            filters={"asset_id": asset.asset.asset_id}
        )
        updated_asset_retention = datalake_service_local_manager.asset_retentions_update(
            asset_retention_id=asset_retention.asset_retention.asset_retention_id,
            changes={"retention_policy": "archive_when_unreferenced"},
        )

        annotation_schema = datalake_service_local_manager.annotation_schemas_create(
            name="service-schema",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[{"name": "hopper", "id": 1}],
            required_attributes=["quality"],
            created_by="pytest",
        )
        fetched_annotation_schema = datalake_service_local_manager.annotation_schemas_get(
            id=annotation_schema.annotation_schema.annotation_schema_id
        )
        fetched_annotation_schema_by_name = datalake_service_local_manager.annotation_schemas_get_by_name_version(
            name="service-schema",
            version="1.0.0",
        )
        listed_annotation_schemas = datalake_service_local_manager.annotation_schemas_list(
            filters={"task_type": "detection"}
        )
        updated_annotation_schema = datalake_service_local_manager.annotation_schemas_update(
            annotation_schema_id=annotation_schema.annotation_schema.annotation_schema_id,
            changes={"labels": [{"name": "hopper", "id": 1, "display_name": "Hopper"}], "allow_scores": True},
        )

        datum = datalake_service_local_manager.datums_create(
            asset_refs={"image": asset.asset.asset_id},
            split="train",
            metadata={"batch": "service"},
        )
        fetched_datum = datalake_service_local_manager.datums_get(id=datum.datum.datum_id)
        listed_datums = datalake_service_local_manager.datums_list(filters={"split": "train"})
        updated_datum = datalake_service_local_manager.datums_update(
            datum_id=datum.datum.datum_id,
            changes={"metadata": {"batch": "updated"}},
        )

        annotation_set = datalake_service_local_manager.annotation_sets_create(
            name="service-ground-truth",
            purpose="ground_truth",
            source_type="human",
            datum_id=datum.datum.datum_id,
            annotation_schema_id=annotation_schema.annotation_schema.annotation_schema_id,
            metadata={"tool": "pytest"},
            created_by="pytest",
        )
        fetched_annotation_set = datalake_service_local_manager.annotation_sets_get(
            id=annotation_set.annotation_set.annotation_set_id
        )
        listed_annotation_sets = datalake_service_local_manager.annotation_sets_list(
            filters={"purpose": "ground_truth"}
        )
        updated_annotation_set = datalake_service_local_manager.annotation_sets_update(
            annotation_set_id=annotation_set.annotation_set.annotation_set_id,
            changes={"status": "active"},
        )

        added_annotation_records = datalake_service_local_manager.annotation_records_add(
            annotation_set_id=annotation_set.annotation_set.annotation_set_id,
            annotations=[
                {
                    "kind": "bbox",
                    "label": "hopper",
                    "label_id": 1,
                    "score": 0.5,
                    "source": {"type": "human", "name": "pytest", "version": "1.0"},
                    "subject": SubjectRef(kind="asset", id=asset.asset.asset_id),
                    "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    "attributes": {"quality": "high"},
                }
            ],
        )
        annotation_record_id = added_annotation_records.annotation_records[0].annotation_id
        fetched_annotation_record = datalake_service_local_manager.annotation_records_get(id=annotation_record_id)
        listed_annotation_records = datalake_service_local_manager.annotation_records_list(filters={"label": "hopper"})
        updated_annotation_record = datalake_service_local_manager.annotation_records_update(
            annotation_id=annotation_record_id,
            changes={"score": 0.99, "source": {"type": "machine", "name": "pytest-updated", "version": "2.0"}},
        )

        resolved_datum = datalake_service_local_manager.datums_resolve(id=datum.datum.datum_id)

        dataset_version = datalake_service_local_manager.dataset_versions_create(
            dataset_name="service-dataset",
            version="0.1.0",
            manifest=[datum.datum.datum_id],
            description="service integration dataset",
            metadata={"suite": "integration"},
            created_by="pytest",
        )
        fetched_dataset_version = datalake_service_local_manager.dataset_versions_get(
            dataset_name="service-dataset",
            version="0.1.0",
        )
        listed_dataset_versions = datalake_service_local_manager.dataset_versions_list(
            dataset_name="service-dataset",
            filters={"version": "0.1.0"},
        )
        resolved_dataset_version = datalake_service_local_manager.dataset_versions_resolve(
            dataset_name="service-dataset",
            version="0.1.0",
        )

        summary = datalake_service_local_manager.summary()

        created_from_object = datalake_service_local_manager.assets_create_from_object(
            name="service-hopper-derived.png",
            data_base64=encoded_image,
            kind="image",
            media_type="image/png",
            object_metadata={"source_path": str(hopper_path)},
            asset_metadata={"derived": True},
            checksum="sha256:derived",
            size_bytes=len(image_bytes),
            subject=SubjectRef(kind="asset", id=asset.asset.asset_id),
            created_by="pytest",
        )

        assert isinstance(health, DatalakeHealthOutput)
        assert isinstance(mounts, MountsOutput)
        assert isinstance(stored_object, ObjectOutput)
        assert isinstance(loaded_object, ObjectDataOutput)
        assert isinstance(headed_object, ObjectHeadOutput)
        assert isinstance(copied_object, ObjectOutput)
        assert isinstance(asset, AssetOutput)
        assert isinstance(fetched_asset, AssetOutput)
        assert isinstance(listed_assets, AssetListOutput)
        assert isinstance(updated_asset, AssetOutput)
        assert isinstance(collection, CollectionOutput)
        assert isinstance(fetched_collection, CollectionOutput)
        assert isinstance(listed_collections, CollectionListOutput)
        assert isinstance(updated_collection, CollectionOutput)
        assert isinstance(collection_item, CollectionItemOutput)
        assert isinstance(fetched_collection_item, CollectionItemOutput)
        assert isinstance(listed_collection_items, CollectionItemListOutput)
        assert isinstance(resolved_collection_item, ResolvedCollectionItemOutput)
        assert isinstance(updated_collection_item, CollectionItemOutput)
        assert isinstance(asset_retention, AssetRetentionOutput)
        assert isinstance(fetched_asset_retention, AssetRetentionOutput)
        assert isinstance(listed_asset_retentions, AssetRetentionListOutput)
        assert isinstance(updated_asset_retention, AssetRetentionOutput)
        assert isinstance(annotation_schema, AnnotationSchemaOutput)
        assert isinstance(fetched_annotation_schema, AnnotationSchemaOutput)
        assert isinstance(fetched_annotation_schema_by_name, AnnotationSchemaOutput)
        assert isinstance(listed_annotation_schemas, AnnotationSchemaListOutput)
        assert isinstance(updated_annotation_schema, AnnotationSchemaOutput)
        assert isinstance(datum, DatumOutput)
        assert isinstance(fetched_datum, DatumOutput)
        assert isinstance(listed_datums, DatumListOutput)
        assert isinstance(updated_datum, DatumOutput)
        assert isinstance(annotation_set, AnnotationSetOutput)
        assert isinstance(fetched_annotation_set, AnnotationSetOutput)
        assert isinstance(listed_annotation_sets, AnnotationSetListOutput)
        assert isinstance(updated_annotation_set, AnnotationSetOutput)
        assert isinstance(added_annotation_records, AddedAnnotationRecordsOutput)
        assert isinstance(fetched_annotation_record, AnnotationRecordOutput)
        assert isinstance(listed_annotation_records, AnnotationRecordListOutput)
        assert isinstance(updated_annotation_record, AnnotationRecordOutput)
        assert isinstance(resolved_datum, ResolvedDatumOutput)
        assert isinstance(dataset_version, DatasetVersionOutput)
        assert isinstance(fetched_dataset_version, DatasetVersionOutput)
        assert isinstance(listed_dataset_versions, DatasetVersionListOutput)
        assert isinstance(resolved_dataset_version, ResolvedDatasetVersionOutput)
        assert isinstance(summary, DatalakeSummaryOutput)
        assert isinstance(created_from_object, AssetOutput)

        assert health.status == "ok"
        assert mounts.default_mount == "local"
        assert loaded_object.data_base64 == encoded_image
        assert headed_object.metadata.get("exists", True) is True
        assert copied_object.storage_ref.mount == "local"
        assert fetched_asset.asset.asset_id == asset.asset.asset_id
        assert any(item.asset_id == asset.asset.asset_id for item in listed_assets.assets)
        assert updated_asset.asset.metadata == {"stage": "updated"}
        assert fetched_collection.collection.collection_id == collection.collection.collection_id
        assert any(item.collection_id == collection.collection.collection_id for item in listed_collections.collections)
        assert updated_collection.collection.status == "archived"
        assert (
            fetched_collection_item.collection_item.collection_item_id
            == collection_item.collection_item.collection_item_id
        )
        assert any(
            item.collection_item_id == collection_item.collection_item.collection_item_id
            for item in listed_collection_items.collection_items
        )
        assert (
            resolved_collection_item.resolved_collection_item.collection.collection_id
            == collection.collection.collection_id
        )
        assert resolved_collection_item.resolved_collection_item.asset.asset_id == asset.asset.asset_id
        assert updated_collection_item.collection_item.status == "hidden"
        assert (
            fetched_asset_retention.asset_retention.asset_retention_id
            == asset_retention.asset_retention.asset_retention_id
        )
        assert any(
            item.asset_retention_id == asset_retention.asset_retention.asset_retention_id
            for item in listed_asset_retentions.asset_retentions
        )
        assert updated_asset_retention.asset_retention.retention_policy == "archive_when_unreferenced"
        assert (
            fetched_annotation_schema.annotation_schema.annotation_schema_id
            == annotation_schema.annotation_schema.annotation_schema_id
        )
        assert (
            fetched_annotation_schema_by_name.annotation_schema.annotation_schema_id
            == annotation_schema.annotation_schema.annotation_schema_id
        )
        assert any(
            item.annotation_schema_id == annotation_schema.annotation_schema.annotation_schema_id
            for item in listed_annotation_schemas.annotation_schemas
        )
        assert updated_annotation_schema.annotation_schema.labels[0].display_name == "Hopper"
        assert fetched_datum.datum.datum_id == datum.datum.datum_id
        assert any(item.datum_id == datum.datum.datum_id for item in listed_datums.datums)
        assert updated_datum.datum.metadata == {"batch": "updated"}
        assert (
            fetched_annotation_set.annotation_set.annotation_set_id == annotation_set.annotation_set.annotation_set_id
        )
        assert any(
            item.annotation_set_id == annotation_set.annotation_set.annotation_set_id
            for item in listed_annotation_sets.annotation_sets
        )
        assert updated_annotation_set.annotation_set.status == "active"
        assert fetched_annotation_record.annotation_record.annotation_id == annotation_record_id
        assert any(item.annotation_id == annotation_record_id for item in listed_annotation_records.annotation_records)
        assert updated_annotation_record.annotation_record.score == 0.99
        assert updated_annotation_record.annotation_record.source.name == "pytest-updated"
        assert resolved_datum.resolved_datum.datum.datum_id == datum.datum.datum_id
        assert resolved_datum.resolved_datum.assets["image"].asset_id == asset.asset.asset_id
        assert (
            fetched_dataset_version.dataset_version.dataset_version_id
            == dataset_version.dataset_version.dataset_version_id
        )
        assert len(listed_dataset_versions.dataset_versions) == 1
        assert (
            resolved_dataset_version.resolved_dataset_version.dataset_version.dataset_version_id
            == dataset_version.dataset_version.dataset_version_id
        )
        assert len(resolved_dataset_version.resolved_dataset_version.datums) == 1
        assert "assets=1" in summary.summary
        assert "collections=1" in summary.summary
        assert "collection_items=1" in summary.summary
        assert "asset_retentions=1" in summary.summary
        assert "annotation_schemas=1" in summary.summary
        assert "annotation_sets=1" in summary.summary
        assert "annotation_records=1" in summary.summary
        assert "datums=1" in summary.summary
        assert "dataset_versions=1" in summary.summary
        assert created_from_object.asset.subject is not None
        assert created_from_object.asset.subject.id == asset.asset.asset_id

        assert datalake_service_local_manager.annotation_records_delete(id=annotation_record_id) is None
        detached_annotation_set = datalake_service_local_manager.annotation_sets_update(
            annotation_set_id=annotation_set.annotation_set.annotation_set_id,
            changes={"annotation_schema_id": None},
        )
        assert detached_annotation_set.annotation_set.annotation_schema_id is None
        assert (
            datalake_service_local_manager.collection_items_delete(
                id=collection_item.collection_item.collection_item_id
            )
            is None
        )
        assert (
            datalake_service_local_manager.asset_retentions_delete(
                id=asset_retention.asset_retention.asset_retention_id
            )
            is None
        )
        assert datalake_service_local_manager.collections_delete(id=collection.collection.collection_id) is None
        assert (
            datalake_service_local_manager.annotation_schemas_delete(
                id=annotation_schema.annotation_schema.annotation_schema_id
            )
            is None
        )
        assert datalake_service_local_manager.assets_delete(id=created_from_object.asset.asset_id) is None
        assert datalake_service_local_manager.assets_delete(id=asset.asset.asset_id) is None

    def test_datalake_service_direct_upload_session_end_to_end(self, datalake_service_local_manager):
        session = datalake_service_local_manager.objects_upload_session_create(
            name="service-direct-upload.bin",
            mount="local",
            content_type="application/octet-stream",
            metadata={"source": "integration"},
            created_by="pytest",
        )
        assert isinstance(session, ObjectUploadSessionOutput)
        assert session.upload_method == "local_path"

        payload = b"direct-upload-payload"
        Path(session.upload_path).write_bytes(payload)

        completed = datalake_service_local_manager.objects_upload_session_complete(
            upload_session_id=session.upload_session_id,
            finalize_token=session.finalize_token,
            metadata={"verified": True},
        )
        assert completed.status == "completed"
        assert completed.storage_ref is not None

        loaded = datalake_service_local_manager.objects_get(storage_ref=completed.storage_ref)
        assert base64.b64decode(loaded.data_base64.encode("utf-8")) == payload

        asset = datalake_service_local_manager.assets_create_from_uploaded_object(
            kind="artifact",
            media_type="application/octet-stream",
            storage_ref=completed.storage_ref,
            size_bytes=len(payload),
            metadata={"source": "integration"},
            created_by="pytest",
        )
        assert isinstance(asset, AssetOutput)
        assert asset.asset.storage_ref == completed.storage_ref

    def test_datalake_service_reconciler_auto_finalizes_expired_upload(self, datalake_mounts):
        db_name = f"tds_direct_upload_reconciler_{uuid4().hex[:12]}"
        service = DatalakeService(
            mongo_db_uri=MONGO_URL,
            mongo_db_name=db_name,
            mounts=datalake_mounts,
            default_mount="local",
            upload_reconcile_interval_seconds=0.05,
        )

        with TestClient(service.app) as client:
            manager = InProcessServiceConnectionManager(service, client)
            session = manager.objects_upload_session_create(
                name="service-auto-finalize.bin",
                mount="local",
                content_type="application/octet-stream",
                expires_in_minutes=1,
            )
            Path(session.upload_path).write_bytes(b"background-finalize")

            mongo_client = MongoClient(MONGO_URL)
            try:
                collection = mongo_client[db_name]["datalake_direct_upload_sessions"]
                collection.update_one(
                    {"upload_session_id": session.upload_session_id},
                    {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
                )

                assert client.portal is not None
                assert service._datalake is not None
                client.portal.call(service._datalake.reconcile_upload_sessions)

                deadline = time.time() + 3
                completed_doc = None
                while time.time() < deadline:
                    candidate = collection.find_one({"upload_session_id": session.upload_session_id})
                    if candidate and candidate.get("status") == "completed":
                        completed_doc = candidate
                        break
                    time.sleep(0.05)
            finally:
                mongo_client.close()

            assert completed_doc is not None
            assert completed_doc["storage_ref"] is not None
            storage_ref = StorageRef(**completed_doc["storage_ref"])
            loaded = manager.objects_get(storage_ref=storage_ref)
            assert base64.b64decode(loaded.data_base64.encode("utf-8")) == b"background-finalize"

        _cleanup_service_database(db_name)

    def test_datalake_service_static_helper_branches(self):
        assert DatalakeService._encode_base64("hello") == base64.b64encode(b"hello").decode("utf-8")

        with pytest.raises(Exception):
            DatalakeService._encode_base64(object())
