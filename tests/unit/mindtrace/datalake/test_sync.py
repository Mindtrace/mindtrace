from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.sync import DatasetSyncManager, _head_object_size_bytes
from mindtrace.datalake.sync_types import DatasetSyncBundle, DatasetSyncImportRequest, ObjectPayloadDescriptor
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    DatasetVersion,
    Datum,
    StorageRef,
)


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
    datalake.object_exists = AsyncMock(return_value=False)
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
    datalake.head_object = AsyncMock(return_value={"size": len(b"payload-bytes")})
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
        assert plan.payloads[0].target_storage_ref == plan.payloads[0].source_storage_ref

    @pytest.mark.asyncio
    async def test_plan_import_mount_map_shifts_object_exists_probe(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(
            DatasetSyncImportRequest(
                bundle=bundle,
                transfer_policy="copy_if_missing",
                mount_map={"source": "remote"},
            )
        )

        assert plan.payloads[0].source_storage_ref.mount == "source"
        assert plan.payloads[0].target_storage_ref.mount == "remote"
        probed_ref = target_datalake.object_exists.await_args.args[0]
        assert probed_ref.mount == "remote"
        assert probed_ref.name == plan.payloads[0].source_storage_ref.name

    @pytest.mark.asyncio
    async def test_plan_import_handles_fail_if_missing_payload(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="fail_if_missing_payload"))

        assert plan.transfer_required_count == 0
        assert plan.ready_to_commit is False
        assert plan.payloads[0].reason == "missing_payload"

    @pytest.mark.asyncio
    async def test_plan_import_metadata_only_is_ready_without_transfer(self, source_datalake):
        manager = DatasetSyncManager(source_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="metadata_only"))

        assert plan.transfer_required_count == 0
        assert plan.ready_to_commit is True
        assert plan.payloads[0].reason == "metadata_only"

    @pytest.mark.asyncio
    async def test_plan_import_metadata_only_rejects_cross_lake(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        with pytest.raises(ValueError, match="metadata_only"):
            await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="metadata_only"))

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
    async def test_sync_dataset_version_passes_mount_map_to_import_request(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        manager.commit_import = AsyncMock()
        await manager.sync_dataset_version(
            "demo",
            "1.0.0",
            mount_map={"source": "remote"},
        )
        req = manager.commit_import.await_args.args[0]
        assert req.mount_map == {"source": "remote"}

    def test_map_storage_ref_for_target(self):
        ref = StorageRef(mount="src", name="a.bin", version="v1")
        assert DatasetSyncManager.map_storage_ref_for_target(ref, {}) is ref
        mapped = DatasetSyncManager.map_storage_ref_for_target(ref, {"src": "dst"})
        assert mapped.mount == "dst" and mapped.name == ref.name and mapped.version == ref.version
        assert DatasetSyncManager.map_storage_ref_for_target(ref, {"other": "x"}).mount == "src"

    @pytest.mark.asyncio
    async def test_transfer_payload_passes_mapped_mount_to_create_upload_session(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
        )
        with patch.object(Path, "write_bytes", return_value=None):
            await manager._transfer_payload(payload, {"source": "s3-dst"})

        kwargs = target_datalake.create_object_upload_session.await_args.kwargs
        assert kwargs["mount"] == "s3-dst"
        assert kwargs["name"] == "images/cat.jpg"

    @pytest.mark.asyncio
    async def test_commit_import_transfers_and_inserts_entities(self, source_datalake, target_datalake, sync_objects):
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
        target_datalake.create_object_upload_session.assert_awaited_once()
        assert target_datalake.create_object_upload_session.await_args.kwargs["mount"] == "source"
        inserted_asset = target_datalake.asset_database.insert.await_args.args[0]
        assert inserted_asset.storage_ref.mount == "target"
        assert inserted_asset.metadata["origin"]["lake_id"] == "lake-a"
        assert inserted_asset.metadata["origin"]["asset_id"] == sync_objects.asset.asset_id
        assert inserted_asset.metadata["origin"]["dataset_version_id"] == sync_objects.dataset_version.dataset_version_id
        inserted_record = target_datalake.annotation_record_database.insert.await_args.args[0]
        assert inserted_record.metadata["origin"]["entity_id"] == "annotation_1"
        assert inserted_record.metadata["origin"]["annotation_id"] == "annotation_1"
        inserted_dataset_version = target_datalake.dataset_version_database.insert.await_args.args[0]
        assert inserted_dataset_version.metadata["origin"]["entity_id"] == "dataset_version_1"
        assert inserted_dataset_version.metadata["origin"]["dataset_name"] == "demo"

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
    async def test_commit_import_skip_payload_persists_mapped_storage_ref(self, source_datalake, target_datalake):
        target_datalake.object_exists = AsyncMock(return_value=True)
        target_datalake.get_asset = AsyncMock(side_effect=DocumentNotFoundError("missing"))
        target_datalake.get_annotation_schema = AsyncMock(side_effect=DocumentNotFoundError("missing"))
        target_datalake.get_annotation_record = AsyncMock(side_effect=DocumentNotFoundError("missing"))
        target_datalake.get_annotation_set = AsyncMock(side_effect=DocumentNotFoundError("missing"))
        target_datalake.get_datum = AsyncMock(side_effect=DocumentNotFoundError("missing"))
        target_datalake.get_dataset_version = AsyncMock(side_effect=DocumentNotFoundError("missing"))
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        result = await manager.commit_import(
            DatasetSyncImportRequest(bundle=bundle, mount_map={"source": "target-vol"})
        )

        assert result.transferred_payloads == 0
        assert result.skipped_payloads == 1
        inserted_asset = target_datalake.asset_database.insert.await_args.args[0]
        assert inserted_asset.storage_ref.mount == "target-vol"
        assert inserted_asset.storage_ref.name == "images/cat.jpg"

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
            storage_ref = await manager._transfer_payload(payload, {})

        assert storage_ref.version == "v3"
        request_obj = urlopen.call_args.args[0]
        assert request_obj.full_url == "https://example.test/upload"
        target_datalake.head_object.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transfer_payload_post_upload_checksum_mismatch(self, source_datalake, target_datalake):
        import hashlib

        target_datalake.head_object = AsyncMock(return_value={"size": len(b"payload-bytes")})
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="upload_session_bad",
                finalize_token="token-bad",
                upload_method="local_path",
                upload_path="/tmp/upload-bad.bin",
                upload_url=None,
                upload_headers={},
            )
        )
        target_datalake.complete_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(storage_ref=StorageRef(mount="target", name="images/cat.jpg", version="v9"))
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bad_digest = hashlib.sha256(b"other-bytes").hexdigest()
        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
            checksum=bad_digest,
        )

        with patch.object(Path, "write_bytes", return_value=None):
            with pytest.raises(RuntimeError, match="checksum mismatch"):
                await manager._transfer_payload(payload, {})

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
            await manager._transfer_payload(payload, {})

    def test_merge_origin_metadata_and_guess_content_type(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = DatasetSyncBundle(
            dataset_version=DatasetVersion(
                dataset_version_id="dv-1",
                dataset_name="demo",
                version="1.0.0",
                manifest=[],
            )
        )

        merged = manager._merge_origin_metadata(
            {"origin": {"other": 1}},
            lake_id="lake-a",
            bundle=bundle,
            entity_id="entity-1",
            asset_id="asset-z",
        )

        assert merged["origin"]["lake_id"] == "lake-a"
        assert merged["origin"]["entity_id"] == "entity-1"
        assert merged["origin"]["dataset_version_id"] == "dv-1"
        assert merged["origin"]["dataset_name"] == "demo"
        assert merged["origin"]["version"] == "1.0.0"
        assert merged["origin"]["asset_id"] == "asset-z"
        assert merged["origin"]["other"] == 1
        assert manager._guess_content_type("image.jpg") == "image/jpeg"
        assert manager._guess_content_type("blob.unknownext") == "application/octet-stream"

    def test_merge_origin_metadata_coerces_non_dict_origin(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = DatasetSyncBundle(
            dataset_version=DatasetVersion(
                dataset_version_id="dv-2",
                dataset_name="d",
                version="1",
                manifest=[],
            )
        )
        merged = manager._merge_origin_metadata(
            {"origin": "broken"},
            lake_id="lake-x",
            bundle=bundle,
            entity_id="e1",
        )
        assert merged["origin"]["lake_id"] == "lake-x"
        assert merged["origin"]["entity_id"] == "e1"

    def test_head_object_size_bytes_parses_digit_strings(self):
        assert _head_object_size_bytes({"size": "42"}) == 42
        assert _head_object_size_bytes({"ContentLength": "7"}) == 7
        assert _head_object_size_bytes({}) is None

    def test_payload_checksum_matches_variants(self, source_datalake, target_datalake):
        import hashlib

        manager = DatasetSyncManager(source_datalake, target_datalake)
        data = b"hello-check"
        sha_hex = hashlib.sha256(data).hexdigest()
        md_hex = hashlib.md5(data).hexdigest()
        assert manager._payload_checksum_matches(data, sha_hex) is True
        assert manager._payload_checksum_matches(data, sha_hex.upper()) is True
        assert manager._payload_checksum_matches(data, f"sha256:{sha_hex}") is True
        assert manager._payload_checksum_matches(data, f"MD5:{md_hex}") is True
        assert manager._payload_checksum_matches(data, md_hex) is True

    def test_payload_checksum_matches_rejects_unknown_algo(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        with pytest.raises(ValueError, match="Unsupported checksum algorithm"):
            manager._payload_checksum_matches(b"x", "crc32:abcd")

    def test_payload_checksum_matches_rejects_bad_format(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        with pytest.raises(ValueError, match="Unrecognized payload checksum format"):
            manager._payload_checksum_matches(b"x", "not-a-valid-checksum")

    @pytest.mark.asyncio
    async def test_plan_import_copy_policy_always_requires_transfer(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        target_datalake.object_exists = AsyncMock(return_value=True)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="copy"))

        assert plan.payloads[0].transfer_required is True
        assert plan.payloads[0].reason == "policy_copy"

    @pytest.mark.asyncio
    async def test_plan_import_fail_if_missing_when_payload_present(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        target_datalake.object_exists = AsyncMock(return_value=True)
        bundle = await manager.export_dataset_version("demo", "1.0.0")

        plan = await manager.plan_import(
            DatasetSyncImportRequest(bundle=bundle, transfer_policy="fail_if_missing_payload")
        )

        assert plan.payloads[0].reason == "already_present"
        assert plan.ready_to_commit is True

    @pytest.mark.asyncio
    async def test_plan_import_rejects_unknown_policy(self, source_datalake, target_datalake):
        manager = DatasetSyncManager(source_datalake, target_datalake)
        bundle = await manager.export_dataset_version("demo", "1.0.0")
        bad = DatasetSyncImportRequest.model_construct(
            bundle=bundle,
            transfer_policy="not_a_policy",
            origin_lake_id=None,
            preserve_ids=True,
            mount_map={},
        )

        with pytest.raises(ValueError, match="Unsupported transfer policy"):
            await manager.plan_import(bad)

    @pytest.mark.asyncio
    async def test_commit_import_metadata_only_single_lake(self, source_datalake, target_datalake, sync_objects):
        bundle = await DatasetSyncManager(source_datalake).export_dataset_version("demo", "1.0.0")
        lake = source_datalake
        for attr in (
            "asset_database",
            "annotation_schema_database",
            "annotation_record_database",
            "annotation_set_database",
            "datum_database",
            "dataset_version_database",
        ):
            setattr(lake, attr, getattr(target_datalake, attr))
        lake.get_asset = AsyncMock(side_effect=DocumentNotFoundError("missing"))
        lake.get_annotation_schema = target_datalake.get_annotation_schema
        lake.get_annotation_record = target_datalake.get_annotation_record
        lake.get_annotation_set = target_datalake.get_annotation_set
        lake.get_datum = target_datalake.get_datum
        lake.get_dataset_version = target_datalake.get_dataset_version
        lake.create_object_upload_session = target_datalake.create_object_upload_session
        lake.complete_object_upload_session = target_datalake.complete_object_upload_session
        lake.head_object = target_datalake.head_object

        manager = DatasetSyncManager(lake)
        result = await manager.commit_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="metadata_only"))

        assert result.transferred_payloads == 0
        assert result.skipped_payloads == 1
        lake.asset_database.insert.assert_awaited()

    @pytest.mark.asyncio
    async def test_commit_import_resolves_asset_without_payload_plan(self, source_datalake, target_datalake, sync_objects):
        extra_ref = StorageRef(mount="source", name="images/extra.jpg", version="v1")
        extra_asset = Asset(
            asset_id="asset_extra",
            kind="image",
            media_type="image/jpeg",
            storage_ref=extra_ref,
            metadata={},
        )
        bundle = DatasetSyncBundle(
            dataset_version=sync_objects.dataset_version,
            datums=[sync_objects.datum],
            assets=[sync_objects.asset, extra_asset],
            annotation_sets=[sync_objects.annotation_set],
            annotation_records=[sync_objects.annotation_record],
            annotation_schemas=[sync_objects.schema],
            payloads=[
                ObjectPayloadDescriptor(
                    asset_id=sync_objects.asset.asset_id,
                    storage_ref=sync_objects.storage_ref,
                    media_type="image/jpeg",
                )
            ],
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)

        with patch.object(Path, "write_bytes", return_value=None):
            result = await manager.commit_import(DatasetSyncImportRequest(bundle=bundle))

        assert result.transferred_payloads == 1
        inserted = {call.args[0].asset_id for call in target_datalake.asset_database.insert.await_args_list}
        assert inserted == {sync_objects.asset.asset_id, extra_asset.asset_id}

    @pytest.mark.asyncio
    async def test_commit_import_asset_without_payload_descriptor_applies_mount_map(
        self, source_datalake, target_datalake, sync_objects
    ):
        extra_ref = StorageRef(mount="source", name="images/extra.jpg", version="v1")
        extra_asset = Asset(
            asset_id="asset_extra",
            kind="image",
            media_type="image/jpeg",
            storage_ref=extra_ref,
            metadata={},
        )
        bundle = DatasetSyncBundle(
            dataset_version=sync_objects.dataset_version,
            datums=[sync_objects.datum],
            assets=[sync_objects.asset, extra_asset],
            annotation_sets=[sync_objects.annotation_set],
            annotation_records=[sync_objects.annotation_record],
            annotation_schemas=[sync_objects.schema],
            payloads=[
                ObjectPayloadDescriptor(
                    asset_id=sync_objects.asset.asset_id,
                    storage_ref=sync_objects.storage_ref,
                    media_type="image/jpeg",
                )
            ],
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)

        with patch.object(Path, "write_bytes", return_value=None):
            await manager.commit_import(
                DatasetSyncImportRequest(bundle=bundle, mount_map={"source": "s3-target"})
            )

        by_id = {c.args[0].asset_id: c.args[0] for c in target_datalake.asset_database.insert.await_args_list}
        assert by_id["asset_extra"].storage_ref.mount == "s3-target"
        assert by_id[sync_objects.asset.asset_id].storage_ref.mount == "target"

    @pytest.mark.asyncio
    async def test_transfer_payload_rejects_descriptor_size_mismatch(self, source_datalake, target_datalake):
        source_datalake.get_object = AsyncMock(return_value=b"short")
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
            size_bytes=999,
        )

        with pytest.raises(ValueError, match="Source read size mismatch"):
            await manager._transfer_payload(payload, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_local_path_requires_upload_path(self, source_datalake, target_datalake):
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="s1",
                finalize_token="t1",
                upload_method="local_path",
                upload_path=None,
                upload_url=None,
                upload_headers={},
            )
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="a",
            storage_ref=StorageRef(mount="m", name="n", version="v"),
            media_type="image/jpeg",
        )

        with pytest.raises(ValueError, match="missing upload_path"):
            await manager._transfer_payload(payload, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_presigned_requires_upload_url(self, source_datalake, target_datalake):
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="s2",
                finalize_token="t2",
                upload_method="presigned_url",
                upload_path=None,
                upload_url=None,
                upload_headers={},
            )
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="a",
            storage_ref=StorageRef(mount="m", name="n", version="v"),
            media_type="image/jpeg",
        )

        with pytest.raises(ValueError, match="missing upload_url"):
            await manager._transfer_payload(payload, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_presigned_raises_on_http_error(self, source_datalake, target_datalake):
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="s3",
                finalize_token="t3",
                upload_method="presigned_url",
                upload_path=None,
                upload_url="https://example.test/up",
                upload_headers={},
            )
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="a",
            storage_ref=StorageRef(mount="m", name="n", version="v"),
            media_type="image/jpeg",
        )
        response = SimpleNamespace(status=500)

        with patch("mindtrace.datalake.sync.urllib_request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            with pytest.raises(RuntimeError, match="Presigned upload failed"):
                await manager._transfer_payload(payload, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_raises_when_finalize_has_no_storage_ref(self, source_datalake, target_datalake):
        target_datalake.complete_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(storage_ref=None)
        )
        manager = DatasetSyncManager(source_datalake, target_datalake)
        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
        )

        with patch.object(Path, "write_bytes", return_value=None):
            with pytest.raises(RuntimeError, match="did not produce a storage_ref"):
                await manager._transfer_payload(payload, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_post_upload_head_size_mismatch(self, source_datalake, target_datalake):
        target_datalake.head_object = AsyncMock(return_value={"size": 999})
        manager = DatasetSyncManager(source_datalake, target_datalake)
        import hashlib

        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
            checksum=hashlib.sha256(b"payload-bytes").hexdigest(),
        )

        with patch.object(Path, "write_bytes", return_value=None):
            with pytest.raises(RuntimeError, match="Post-upload size mismatch"):
                await manager._transfer_payload(payload, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_accepts_string_head_size(self, source_datalake, target_datalake):
        import hashlib

        target_datalake.head_object = AsyncMock(return_value={"size": str(len(b"payload-bytes"))})
        manager = DatasetSyncManager(source_datalake, target_datalake)
        digest = hashlib.sha256(b"payload-bytes").hexdigest()
        payload = ObjectPayloadDescriptor(
            asset_id="asset_1",
            storage_ref=StorageRef(mount="source", name="images/cat.jpg", version="v1"),
            media_type="image/jpeg",
            checksum=digest,
        )

        with patch.object(Path, "write_bytes", return_value=None):
            ref = await manager._transfer_payload(payload, {})

        assert ref.mount == "target"
