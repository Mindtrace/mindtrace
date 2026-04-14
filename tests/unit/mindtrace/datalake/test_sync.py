from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.sync import DatasetSyncManager
from mindtrace.datalake.sync_types import DatasetSyncImportRequest, ObjectPayloadDescriptor
from mindtrace.datalake.types import AnnotationRecord, AnnotationSchema, AnnotationSet, Asset, DatasetVersion, Datum, StorageRef


@pytest.fixture
def sync_objects():
    storage_ref = StorageRef(mount="source", name="images/cat.jpg", version="v1")
    asset = Asset(
        asset_id="asset_1",
        kind="image",
        media_type="image/jpeg",
        storage_ref=storage_ref,
        metadata={"a": 1},
    )
    schema = AnnotationSchema(
        annotation_schema_id="annotation_schema_1",
        name="schema",
        version="1.0",
        task_type="detection",
        allowed_annotation_kinds=["bbox"],
        metadata={"schema": True},
    )
    annotation_record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        source={"type": "human", "name": "tester"},
        metadata={"record": True},
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="gt",
        purpose="ground_truth",
        source_type="human",
        annotation_schema_id=schema.annotation_schema_id,
        annotation_record_ids=[annotation_record.annotation_id],
        metadata={"set": True},
    )
    datum = Datum(
        datum_id="datum_1",
        asset_refs={"image": asset.asset_id},
        annotation_set_ids=[annotation_set.annotation_set_id],
        metadata={"datum": True},
    )
    dataset_version = DatasetVersion(
        dataset_version_id="dataset_version_1",
        dataset_name="demo",
        version="1.0.0",
        manifest=[datum.datum_id],
        metadata={"dataset": True},
    )
    return SimpleNamespace(
        storage_ref=storage_ref,
        asset=asset,
        schema=schema,
        annotation_record=annotation_record,
        annotation_set=annotation_set,
        datum=datum,
        dataset_version=dataset_version,
    )


@pytest.fixture
def source_datalake(sync_objects):
    datalake = Mock()
    datalake.mongo_db_name = "source_db"
    datalake.get_dataset_version = AsyncMock(return_value=sync_objects.dataset_version)
    datalake.get_datum = AsyncMock(return_value=sync_objects.datum)
    datalake.get_asset = AsyncMock(return_value=sync_objects.asset)
    datalake.get_annotation_set = AsyncMock(return_value=sync_objects.annotation_set)
    datalake.get_annotation_record = AsyncMock(return_value=sync_objects.annotation_record)
    datalake.get_annotation_schema = AsyncMock(return_value=sync_objects.schema)
    datalake.get_object = AsyncMock(return_value=b"payload-bytes")
    return datalake


@pytest.fixture
def target_datalake(sync_objects):
    datalake = Mock()
    datalake.mongo_db_name = "target_db"
    datalake.object_exists = AsyncMock(return_value=False)
    datalake.create_object_upload_session = AsyncMock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path="/tmp/upload.bin",
            upload_url=None,
            upload_headers={},
        )
    )
    datalake.complete_object_upload_session = AsyncMock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="target", name="images/cat.jpg", version="v2"))
    )
    datalake.get_asset = AsyncMock(side_effect=DocumentNotFoundError("asset missing"))
    datalake.get_annotation_schema = AsyncMock(side_effect=DocumentNotFoundError("schema missing"))
    datalake.get_annotation_record = AsyncMock(side_effect=DocumentNotFoundError("record missing"))
    datalake.get_annotation_set = AsyncMock(side_effect=DocumentNotFoundError("set missing"))
    datalake.get_datum = AsyncMock(side_effect=DocumentNotFoundError("datum missing"))
    datalake.get_dataset_version = AsyncMock(side_effect=DocumentNotFoundError("dataset missing"))
    datalake.asset_database = SimpleNamespace(insert=AsyncMock(side_effect=lambda obj: obj))
    datalake.annotation_schema_database = SimpleNamespace(insert=AsyncMock(side_effect=lambda obj: obj))
    datalake.annotation_record_database = SimpleNamespace(insert=AsyncMock(side_effect=lambda obj: obj))
    datalake.annotation_set_database = SimpleNamespace(insert=AsyncMock(side_effect=lambda obj: obj))
    datalake.datum_database = SimpleNamespace(insert=AsyncMock(side_effect=lambda obj: obj))
    datalake.dataset_version_database = SimpleNamespace(insert=AsyncMock(side_effect=lambda obj: obj))
    return datalake


class TestDatasetSyncManager:
    @pytest.mark.asyncio
    async def test_export_dataset_version_collects_flat_bundle(self, source_datalake, sync_objects):
        manager = DatasetSyncManager(source_datalake)

        bundle = await manager.export_dataset_version("demo", "1.0.0")

        assert bundle.dataset_version == sync_objects.dataset_version
        assert bundle.datums == [sync_objects.datum]
        assert bundle.assets == [sync_objects.asset]
        assert bundle.annotation_sets == [sync_objects.annotation_set]
        assert bundle.annotation_records == [sync_objects.annotation_record]
        assert bundle.annotation_schemas == [sync_objects.schema]
        assert bundle.payloads[0].asset_id == sync_objects.asset.asset_id
        assert bundle.metadata["source_dataset_version_id"] == sync_objects.dataset_version.dataset_version_id

    @pytest.mark.asyncio
    async def test_plan_import_marks_missing_payloads_for_copy_if_missing(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="copy_if_missing"))

        assert plan.dataset_name == "demo"
        assert plan.transfer_required_count == 1
        assert plan.missing_payload_count == 1
        assert plan.payloads[0].reason == "missing_on_target"
        assert plan.ready_to_commit is True

    @pytest.mark.asyncio
    async def test_plan_import_handles_fail_if_missing_payload(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="fail_if_missing_payload"))

        assert plan.transfer_required_count == 0
        assert plan.ready_to_commit is False
        assert plan.payloads[0].reason == "missing_payload"

    @pytest.mark.asyncio
    async def test_plan_import_metadata_only_is_ready_without_transfer(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="metadata_only"))

        assert plan.transfer_required_count == 0
        assert plan.ready_to_commit is True
        assert plan.payloads[0].reason == "metadata_only"

    @pytest.mark.asyncio
    async def test_sync_dataset_version_delegates_to_commit(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        expected = SimpleNamespace(ok=True)
        manager.commit_import = AsyncMock(return_value=expected)

        result = await manager.sync_dataset_version("demo", "1.0.0", origin_lake_id="lake-a")

        assert result is expected
        manager.commit_import.assert_awaited_once()
        request = manager.commit_import.await_args.args[0]
        assert request.origin_lake_id == "lake-a"
        assert request.bundle.dataset_version.dataset_name == "demo"

    @pytest.mark.asyncio
    async def test_commit_import_transfers_and_inserts_entities(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        with patch.object(Path, "write_bytes", return_value=None) as write_bytes:
            result = await manager.commit_import(DatasetSyncImportRequest(bundle=bundle, origin_lake_id="lake-a"))

        write_bytes.assert_called_once_with(b"payload-bytes")
        target_datalake.create_object_upload_session.assert_awaited_once()
        target_datalake.complete_object_upload_session.assert_awaited_once_with("upload_session_1", finalize_token="token-1")
        assert result.transferred_payloads == 1
        assert result.created_assets == 1
        assert result.created_annotation_schemas == 1
        assert result.created_annotation_records == 1
        assert result.created_annotation_sets == 1
        assert result.created_datums == 1
        inserted_asset = target_datalake.asset_database.insert.await_args.args[0]
        assert inserted_asset.storage_ref.mount == "target"
        assert inserted_asset.metadata["origin"]["lake_id"] == "lake-a"
        inserted_record = target_datalake.annotation_record_database.insert.await_args.args[0]
        assert inserted_record.metadata["origin"]["entity_id"] == "annotation_1"
        inserted_dataset_version = target_datalake.dataset_version_database.insert.await_args.args[0]
        assert inserted_dataset_version.metadata["origin"]["entity_id"] == "dataset_version_1"

    @pytest.mark.asyncio
    async def test_commit_import_skips_when_target_entities_exist(self, source_datalake, target_datalake, sync_objects):
        target_datalake.object_exists = AsyncMock(return_value=True)
        target_datalake.get_asset = AsyncMock(return_value=sync_objects.asset)
        target_datalake.get_annotation_schema = AsyncMock(return_value=sync_objects.schema)
        target_datalake.get_annotation_record = AsyncMock(return_value=sync_objects.annotation_record)
        target_datalake.get_annotation_set = AsyncMock(return_value=sync_objects.annotation_set)
        target_datalake.get_datum = AsyncMock(return_value=sync_objects.datum)
        target_datalake.get_dataset_version = AsyncMock(return_value=sync_objects.dataset_version)
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        result = await manager.commit_import(DatasetSyncImportRequest(bundle=bundle))

        assert result.transferred_payloads == 0
        assert result.skipped_payloads == 1
        assert result.dataset_version == sync_objects.dataset_version
        target_datalake.asset_database.insert.assert_not_awaited()
        target_datalake.dataset_version_database.insert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_commit_import_raises_when_plan_not_ready(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        with pytest.raises(ValueError, match="not ready to commit"):
            await manager.commit_import(
                DatasetSyncImportRequest(bundle=bundle, transfer_policy="fail_if_missing_payload")
            )

    @pytest.mark.asyncio
    async def test_transfer_payload_uses_presigned_upload(self, source_datalake, target_datalake):
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="upload_session_2",
                finalize_token="token-2",
                upload_method="presigned_url",
                upload_path=None,
                upload_url="https://example.test/upload",
                upload_headers={"Content-Type": "image/jpeg"},
            )
        )
        target_datalake.complete_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(storage_ref=StorageRef(mount="target", name="images/cat.jpg", version="v3"))
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
        )

        response = SimpleNamespace(status=200)
        with patch("mindtrace.datalake.sync.urllib_request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            storage_ref = await manager._transfer_payload(payload)

        assert storage_ref.version == "v3"
        request_obj = urlopen.call_args.args[0]
        assert request_obj.full_url == "https://example.test/upload"

    @pytest.mark.asyncio
    async def test_transfer_payload_rejects_unknown_upload_method(self, source_datalake, target_datalake):
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="upload_session_3",
                finalize_token="token-3",
                upload_method="weird",
                upload_path=None,
                upload_url=None,
                upload_headers={},
            )
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
        )

        with pytest.raises(ValueError, match="Unsupported upload method"):
            await manager._transfer_payload(payload)

    def test_merge_origin_metadata_and_guess_content_type(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)

        merged = manager._merge_origin_metadata({"origin": {"other": 1}}, "lake-a", "entity-1")

        assert merged["origin"]["lake_id"] == "lake-a"
        assert merged["origin"]["entity_id"] == "entity-1"
        assert merged["origin"]["other"] == 1
        assert manager._guess_content_type("image.jpg") == "image/jpeg"
        assert manager._guess_content_type("blob.unknownext") == "application/octet-stream"
