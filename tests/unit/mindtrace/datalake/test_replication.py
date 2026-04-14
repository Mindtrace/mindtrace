import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.replication import MetadataFirstReplicationManager, _head_object_size_bytes
from mindtrace.datalake.replication_types import (
    ReplicationBatchRequest,
    ReplicationReclaimRequest,
    ReplicationReconcileRequest,
)
from mindtrace.datalake.types import AnnotationRecord, AnnotationSchema, AnnotationSet, Asset, Datum, StorageRef


@pytest.fixture
def replication_objects():
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
    return SimpleNamespace(
        storage_ref=storage_ref,
        asset=asset,
        schema=schema,
        annotation_record=annotation_record,
        annotation_set=annotation_set,
        datum=datum,
    )


@pytest.fixture
def source_datalake(replication_objects):
    datalake = Mock()
    datalake.mongo_db_name = "source_db"
    datalake.get_asset = AsyncMock(return_value=replication_objects.asset)
    datalake.get_object = AsyncMock(return_value=b"payload-bytes")
    datalake.store = Mock()
    datalake.store.build_key = Mock(side_effect=lambda mount, name, version: f"{mount}/{name}@{version}")
    datalake.store.delete = Mock()
    datalake.asset_database = SimpleNamespace(
        insert=AsyncMock(side_effect=lambda obj: obj),
        update=AsyncMock(),
        find=AsyncMock(return_value=[]),
    )
    return datalake


@pytest.fixture
def target_datalake():
    datalake = Mock()
    datalake.mongo_db_name = "target_db"
    datalake.get_asset = AsyncMock(side_effect=DocumentNotFoundError("asset missing"))
    datalake.get_annotation_schema = AsyncMock(side_effect=DocumentNotFoundError("schema missing"))
    datalake.get_annotation_record = AsyncMock(side_effect=DocumentNotFoundError("record missing"))
    datalake.get_annotation_set = AsyncMock(side_effect=DocumentNotFoundError("set missing"))
    datalake.get_datum = AsyncMock(side_effect=DocumentNotFoundError("datum missing"))
    datalake.create_object_upload_session = AsyncMock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path="/tmp/replication-upload.bin",
            upload_url=None,
            upload_headers={},
        )
    )
    datalake.complete_object_upload_session = AsyncMock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="remote", name="images/cat.jpg", version="v1"))
    )
    datalake.head_object = AsyncMock(return_value={"size_bytes": len(b"payload-bytes")})
    datalake.asset_database = SimpleNamespace(
        insert=AsyncMock(side_effect=lambda obj: obj),
        update=AsyncMock(),
        find=AsyncMock(return_value=[]),
    )
    datalake.annotation_schema_database = SimpleNamespace(
        insert=AsyncMock(side_effect=lambda obj: obj),
        update=AsyncMock(),
        find=AsyncMock(return_value=[]),
    )
    datalake.annotation_record_database = SimpleNamespace(
        insert=AsyncMock(side_effect=lambda obj: obj),
        update=AsyncMock(),
        find=AsyncMock(return_value=[]),
    )
    datalake.annotation_set_database = SimpleNamespace(
        insert=AsyncMock(side_effect=lambda obj: obj),
        update=AsyncMock(),
        find=AsyncMock(return_value=[]),
    )
    datalake.datum_database = SimpleNamespace(
        insert=AsyncMock(side_effect=lambda obj: obj),
        update=AsyncMock(),
        find=AsyncMock(return_value=[]),
    )
    return datalake


class TestMetadataFirstReplicationManager:
    @pytest.mark.asyncio
    async def test_upsert_metadata_batch_creates_placeholder_graph(self, source_datalake, target_datalake, replication_objects):
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        result = await manager.upsert_metadata_batch(
            ReplicationBatchRequest(
                assets=[replication_objects.asset],
                annotation_schemas=[replication_objects.schema],
                annotation_sets=[replication_objects.annotation_set],
                annotation_records=[replication_objects.annotation_record],
                datums=[replication_objects.datum],
                origin_lake_id="source-lake",
                mount_map={"source": "remote"},
            )
        )

        assert result.created_assets == 1
        assert result.created_annotation_schemas == 1
        assert result.created_annotation_sets == 1
        assert result.created_annotation_records == 1
        assert result.created_datums == 1

        inserted_asset = target_datalake.asset_database.insert.await_args.args[0]
        assert inserted_asset.storage_ref.mount == "remote"
        assert inserted_asset.metadata["origin"]["lake_id"] == "source-lake"
        assert inserted_asset.metadata["origin"]["asset_id"] == "asset_1"
        assert inserted_asset.metadata["replication"]["replication_mode"] == "metadata_first"
        assert inserted_asset.metadata["replication"]["payload_status"] == "pending"
        assert inserted_asset.metadata["replication"]["payload_available"] is False

        inserted_datum = target_datalake.datum_database.insert.await_args.args[0]
        assert inserted_datum.metadata["origin"]["entity_kind"] == "datum"

    @pytest.mark.asyncio
    async def test_upsert_metadata_batch_updates_existing_graph(self, source_datalake, target_datalake, replication_objects):
        existing_asset = Asset(
            asset_id=replication_objects.asset.asset_id,
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="legacy", name="old.jpg", version="v0"),
            metadata={"legacy": True},
        )
        target_datalake.get_asset = AsyncMock(return_value=existing_asset)
        target_datalake.get_annotation_schema = AsyncMock(return_value=replication_objects.schema)
        target_datalake.get_annotation_record = AsyncMock(return_value=replication_objects.annotation_record)
        target_datalake.get_annotation_set = AsyncMock(return_value=replication_objects.annotation_set)
        target_datalake.get_datum = AsyncMock(return_value=replication_objects.datum)

        target_datalake.asset_database.find = AsyncMock(return_value=[existing_asset])
        target_datalake.annotation_schema_database.find = AsyncMock(return_value=[replication_objects.schema])
        target_datalake.annotation_record_database.find = AsyncMock(return_value=[replication_objects.annotation_record])
        target_datalake.annotation_set_database.find = AsyncMock(return_value=[replication_objects.annotation_set])
        target_datalake.datum_database.find = AsyncMock(return_value=[replication_objects.datum])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        result = await manager.upsert_metadata_batch(
            ReplicationBatchRequest(
                assets=[replication_objects.asset],
                annotation_schemas=[replication_objects.schema],
                annotation_sets=[replication_objects.annotation_set],
                annotation_records=[replication_objects.annotation_record],
                datums=[replication_objects.datum],
                origin_lake_id="source-lake",
                mount_map={"source": "remote"},
            )
        )

        assert result.updated_assets == 1
        assert result.updated_annotation_schemas == 1
        assert result.updated_annotation_sets == 1
        assert result.updated_annotation_records == 1
        assert result.updated_datums == 1
        target_datalake.asset_database.update.assert_awaited()
        assert existing_asset.storage_ref.mount == "remote"
        assert existing_asset.metadata["replication"]["payload_status"] == "pending"

    @pytest.mark.asyncio
    async def test_status_counts_payload_states(self, source_datalake, target_datalake, replication_objects):
        pending_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "replication": {
                        "origin_lake_id": "source-lake",
                        "origin_asset_id": replication_objects.asset.asset_id,
                        "replication_mode": "metadata_first",
                        "payload_status": "pending",
                        "payload_available": False,
                    }
                },
            }
        )
        failed_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "asset_2",
                "metadata": {
                    "replication": {
                        "origin_lake_id": "source-lake",
                        "origin_asset_id": "asset_2",
                        "replication_mode": "metadata_first",
                        "payload_status": "failed",
                        "payload_available": False,
                    }
                },
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[pending_asset, failed_asset])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        status = await manager.status()

        assert status.asset_counts_by_payload_status["pending"] == 1
        assert status.asset_counts_by_payload_status["failed"] == 1
        assert status.pending_asset_ids == [pending_asset.asset_id]
        assert status.failed_asset_ids == [failed_asset.asset_id]

    @pytest.mark.asyncio
    async def test_status_skips_non_replicated_and_unknown_payload_status(self, source_datalake, target_datalake, replication_objects):
        plain = Asset.model_validate({**replication_objects.asset.model_dump(), "metadata": {}})
        weird = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "asset_weird",
                "metadata": {"replication": {"payload_status": "not_a_real_status"}},
            }
        )
        bad_type = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "asset_bad",
                "metadata": {"replication": "oops"},
            }
        )
        transferring = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "asset_xfer",
                "metadata": {"replication": {"payload_status": "transferring", "payload_available": False}},
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[plain, weird, bad_type, transferring])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        status = await manager.status()

        assert status.asset_counts_by_payload_status["transferring"] == 1
        assert sum(status.asset_counts_by_payload_status.values()) == 1

    @pytest.mark.asyncio
    async def test_update_asset_inserts_when_find_returns_empty(self, source_datalake, target_datalake, replication_objects):
        target_datalake.get_asset = AsyncMock(return_value=replication_objects.asset)
        target_datalake.asset_database.find = AsyncMock(return_value=[])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        replicated = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "storage_ref": replication_objects.storage_ref.model_dump(),
                "metadata": {"replication": {"payload_status": "pending"}},
            }
        )
        await manager._update_asset(replicated)

        target_datalake.asset_database.insert.assert_awaited_once()
        target_datalake.asset_database.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_annotation_schema_inserts_when_find_empty(self, source_datalake, target_datalake, replication_objects):
        target_datalake.annotation_schema_database.find = AsyncMock(return_value=[])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        await manager._update_annotation_schema(replication_objects.schema, "lake")

        target_datalake.annotation_schema_database.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_annotation_record_inserts_when_find_empty(self, source_datalake, target_datalake, replication_objects):
        target_datalake.annotation_record_database.find = AsyncMock(return_value=[])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        await manager._update_annotation_record(replication_objects.annotation_record, "lake")

        target_datalake.annotation_record_database.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_annotation_set_inserts_when_find_empty(self, source_datalake, target_datalake, replication_objects):
        target_datalake.annotation_set_database.find = AsyncMock(return_value=[])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        await manager._update_annotation_set(replication_objects.annotation_set, "lake")

        target_datalake.annotation_set_database.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_datum_inserts_when_find_empty(self, source_datalake, target_datalake, replication_objects):
        target_datalake.datum_database.find = AsyncMock(return_value=[])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        await manager._update_datum(replication_objects.datum, "lake")

        target_datalake.datum_database.insert.assert_awaited_once()


class TestMetadataFirstReplicationStaticHelpers:
    def test_map_storage_ref_for_target_noop_when_unmapped(self, replication_objects):
        ref = replication_objects.storage_ref
        out = MetadataFirstReplicationManager.map_storage_ref_for_target(ref, {"other": "x"})
        assert out is ref

    def test_get_payload_status_and_is_payload_available(self, replication_objects):
        asset_no_meta = replication_objects.asset
        assert MetadataFirstReplicationManager.get_payload_status(asset_no_meta) is None
        assert MetadataFirstReplicationManager.is_payload_available(asset_no_meta) is False

        asset_bad_rep = Asset.model_validate(
            {**replication_objects.asset.model_dump(), "metadata": {"replication": []}}
        )
        assert MetadataFirstReplicationManager.get_payload_status(asset_bad_rep) is None
        assert MetadataFirstReplicationManager.is_payload_available(asset_bad_rep) is False

        asset_bad_status = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {"replication": {"payload_status": 123}},
            }
        )
        assert MetadataFirstReplicationManager.get_payload_status(asset_bad_status) is None

        asset_ok = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {"replication": {"payload_status": "verified", "payload_available": True}},
            }
        )
        assert MetadataFirstReplicationManager.get_payload_status(asset_ok) == "verified"
        assert MetadataFirstReplicationManager.is_payload_available(asset_ok) is True

    def test_build_asset_replication_metadata_coerces_origin_and_replication(self, replication_objects):
        manager = MetadataFirstReplicationManager(Mock(), Mock())
        meta = manager.build_asset_replication_metadata(
            {
                "origin": "not-a-dict",
                "replication": "also-not",
                "keep": 1,
            },
            origin_lake_id="L",
            origin_asset_id="A1",
            replication_mode="metadata_first",
            payload_status="verified",
        )
        assert meta["keep"] == 1
        assert meta["origin"]["lake_id"] == "L"
        assert meta["origin"]["asset_id"] == "A1"
        assert meta["replication"]["payload_status"] == "verified"
        assert meta["replication"]["payload_available"] is True

    def test_build_asset_replication_metadata_preserves_replication_timestamps(self, replication_objects):
        manager = MetadataFirstReplicationManager(Mock(), Mock())
        meta = manager.build_asset_replication_metadata(
            {
                "replication": {
                    "payload_last_error": "boom",
                    "payload_last_attempt_at": None,
                    "payload_verified_at": None,
                    "local_delete_eligible_at": None,
                    "local_deleted_at": None,
                }
            },
            origin_lake_id="L",
            origin_asset_id="A1",
            replication_mode="metadata_first",
            payload_status="pending",
        )
        assert meta["replication"]["payload_last_error"] == "boom"
        assert meta["replication"]["payload_status"] == "pending"
        assert meta["replication"]["payload_available"] is False


@pytest.mark.asyncio
async def test_existence_helpers_return_false_on_document_not_found(source_datalake, target_datalake):
    target_datalake.get_asset = AsyncMock(side_effect=DocumentNotFoundError("missing"))
    target_datalake.get_annotation_schema = AsyncMock(side_effect=DocumentNotFoundError("missing"))
    target_datalake.get_annotation_record = AsyncMock(side_effect=DocumentNotFoundError("missing"))
    target_datalake.get_annotation_set = AsyncMock(side_effect=DocumentNotFoundError("missing"))
    target_datalake.get_datum = AsyncMock(side_effect=DocumentNotFoundError("missing"))

    manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
    assert await manager._asset_exists("x") is False
    assert await manager._annotation_schema_exists("x") is False
    assert await manager._annotation_record_exists("x") is False
    assert await manager._annotation_set_exists("x") is False
    assert await manager._datum_exists("x") is False


def test_head_object_size_bytes_parsing():
    assert _head_object_size_bytes({"size_bytes": None, "size": "42"}) == 42
    assert _head_object_size_bytes({"content_length": "100"}) == 100
    assert _head_object_size_bytes({"ContentLength": 7}) == 7
    assert _head_object_size_bytes({"other": None}) is None


def test_manager_defaults_target_to_source(source_datalake):
    manager = MetadataFirstReplicationManager(source_datalake)
    assert manager.target is source_datalake


def test_local_delete_helpers(replication_objects):
    eligible = Asset.model_validate(
        {
            **replication_objects.asset.model_dump(),
            "metadata": {"replication": {"local_delete_eligible_at": "2026-01-01T00:00:00Z"}},
        }
    )
    deleted = Asset.model_validate(
        {
            **replication_objects.asset.model_dump(),
            "asset_id": "deleted",
            "metadata": {"replication": {"local_deleted_at": "2026-01-01T00:00:00Z"}},
        }
    )
    assert MetadataFirstReplicationManager.is_local_delete_eligible(eligible) is True
    assert MetadataFirstReplicationManager.is_local_deleted(eligible) is False
    assert MetadataFirstReplicationManager.is_local_deleted(deleted) is True


class TestReplicationTransferAndVerify:
    @pytest.mark.asyncio
    async def test_hydrate_falls_back_to_target_asset_id_without_origin_asset_id(
        self, source_datalake, target_datalake, replication_objects
    ):
        target_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "origin": {"lake_id": "source-lake"},
                    "replication": {"payload_status": "pending", "payload_available": False},
                },
            }
        )
        source_datalake.get_object = AsyncMock(return_value=b"payload-bytes")
        source_datalake.get_asset = AsyncMock(return_value=replication_objects.asset)
        target_datalake.get_asset = AsyncMock(side_effect=[target_asset, target_asset, target_asset])
        target_datalake.asset_database.find = AsyncMock(return_value=[target_asset])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        await manager.hydrate_asset_payload(replication_objects.asset.asset_id, mount_map={"source": "remote"})
        source_datalake.get_asset.assert_awaited_once_with(replication_objects.asset.asset_id)

    @pytest.mark.asyncio
    async def test_hydrate_asset_payload_marks_verified(self, source_datalake, target_datalake, replication_objects):
        target_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "storage_ref": {"mount": "remote", "name": "images/cat.jpg", "version": "v1"},
                "metadata": {
                    "origin": {"lake_id": "source-lake", "asset_id": replication_objects.asset.asset_id},
                    "replication": {
                        "origin_lake_id": "source-lake",
                        "origin_asset_id": replication_objects.asset.asset_id,
                        "replication_mode": "metadata_first",
                        "payload_status": "pending",
                        "payload_available": False,
                    },
                },
            }
        )
        source_datalake.get_object = AsyncMock(return_value=b"payload-bytes")
        source_datalake.get_asset = AsyncMock(return_value=replication_objects.asset)
        target_datalake.get_asset = AsyncMock(side_effect=[target_asset, target_asset, target_asset])
        target_datalake.asset_database.find = AsyncMock(return_value=[target_asset])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        result = await manager.hydrate_asset_payload(replication_objects.asset.asset_id, mount_map={"source": "remote"})

        assert result.metadata["replication"]["payload_status"] == "verified"
        assert result.metadata["replication"]["payload_available"] is True
        target_datalake.create_object_upload_session.assert_awaited_once()
        target_datalake.complete_object_upload_session.assert_awaited_once_with("upload_session_1", finalize_token="token-1")

    @pytest.mark.asyncio
    async def test_hydrate_asset_payload_marks_failed_on_transfer_error(self, source_datalake, target_datalake, replication_objects):
        target_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "origin": {"lake_id": "source-lake", "asset_id": replication_objects.asset.asset_id},
                    "replication": {
                        "origin_lake_id": "source-lake",
                        "origin_asset_id": replication_objects.asset.asset_id,
                        "replication_mode": "metadata_first",
                        "payload_status": "pending",
                        "payload_available": False,
                    },
                },
            }
        )
        source_datalake.get_object = AsyncMock(side_effect=RuntimeError("boom"))
        source_datalake.get_asset = AsyncMock(return_value=replication_objects.asset)
        target_datalake.get_asset = AsyncMock(side_effect=[target_asset, target_asset])
        target_datalake.asset_database.find = AsyncMock(return_value=[target_asset])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(RuntimeError, match="boom"):
            await manager.hydrate_asset_payload(replication_objects.asset.asset_id)

        assert target_asset.metadata["replication"]["payload_status"] == "failed"
        assert target_asset.metadata["replication"]["payload_last_error"] == "boom"

    @pytest.mark.asyncio
    async def test_hydrate_asset_payload_marks_failed_when_verify_raises(self, source_datalake, target_datalake, replication_objects):
        target_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "origin": {"lake_id": "source-lake", "asset_id": replication_objects.asset.asset_id},
                    "replication": {"payload_status": "pending", "payload_available": False},
                },
            }
        )
        source_datalake.get_object = AsyncMock(return_value=b"payload-bytes")
        source_datalake.get_asset = AsyncMock(return_value=replication_objects.asset)
        target_datalake.get_asset = AsyncMock(side_effect=[target_asset, target_asset])
        target_datalake.head_object = AsyncMock(return_value={"size_bytes": 999})
        target_datalake.asset_database.find = AsyncMock(return_value=[target_asset])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(RuntimeError, match="Post-upload size mismatch"):
            await manager.hydrate_asset_payload(replication_objects.asset.asset_id)

        assert target_asset.metadata["replication"]["payload_status"] == "failed"

    @pytest.mark.asyncio
    async def test_reconcile_pending_payloads_processes_pending_and_failed(self, source_datalake, target_datalake, replication_objects):
        pending_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "origin": {"lake_id": "source-lake", "asset_id": replication_objects.asset.asset_id},
                    "replication": {"payload_status": "pending", "payload_available": False},
                },
            }
        )
        failed_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "asset_failed",
                "metadata": {
                    "origin": {"lake_id": "source-lake", "asset_id": replication_objects.asset.asset_id},
                    "replication": {"payload_status": "failed", "payload_available": False},
                },
            }
        )
        verified_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "asset_verified",
                "metadata": {
                    "origin": {"lake_id": "source-lake", "asset_id": replication_objects.asset.asset_id},
                    "replication": {"payload_status": "verified", "payload_available": True},
                },
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[pending_asset, failed_asset, verified_asset])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.hydrate_asset_payload = AsyncMock(side_effect=[pending_asset, RuntimeError("x")])

        result = await manager.reconcile_pending_payloads(ReplicationReconcileRequest(include_failed=True))

        assert result.attempted_asset_ids == [pending_asset.asset_id, failed_asset.asset_id]
        assert result.verified_asset_ids == [pending_asset.asset_id]
        assert result.failed_asset_ids == [failed_asset.asset_id]
        assert verified_asset.asset_id in result.skipped_asset_ids

    @pytest.mark.asyncio
    async def test_reconcile_records_failed_when_hydrate_raises(self, source_datalake, target_datalake, replication_objects):
        pending_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {"replication": {"payload_status": "pending"}},
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[pending_asset])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.hydrate_asset_payload = AsyncMock(side_effect=RuntimeError("hydrate failed"))

        result = await manager.reconcile_pending_payloads()

        assert result.attempted_asset_ids == [pending_asset.asset_id]
        assert result.failed_asset_ids == [pending_asset.asset_id]
        assert result.verified_asset_ids == []

    @pytest.mark.asyncio
    async def test_reconcile_skips_non_pending_failed_status(self, source_datalake, target_datalake, replication_objects):
        transferring = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "xfer1",
                "metadata": {"replication": {"payload_status": "transferring"}},
            }
        )
        pending_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {"replication": {"payload_status": "pending"}},
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[transferring, pending_asset])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.hydrate_asset_payload = AsyncMock(return_value=pending_asset)

        result = await manager.reconcile_pending_payloads()

        assert transferring.asset_id in result.skipped_asset_ids
        assert pending_asset.asset_id in result.attempted_asset_ids

    @pytest.mark.asyncio
    async def test_reconcile_filters_by_asset_ids(self, source_datalake, target_datalake, replication_objects):
        pending_a = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "a1",
                "metadata": {"replication": {"payload_status": "pending"}},
            }
        )
        pending_b = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "b2",
                "metadata": {"replication": {"payload_status": "pending"}},
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[pending_a, pending_b])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.hydrate_asset_payload = AsyncMock(side_effect=[pending_a, pending_b])

        result = await manager.reconcile_pending_payloads(ReplicationReconcileRequest(asset_ids=["a1"]))

        assert result.attempted_asset_ids == ["a1"]
        assert "b2" not in result.attempted_asset_ids
        manager.hydrate_asset_payload.assert_awaited_once_with("a1", mount_map={})

    @pytest.mark.asyncio
    async def test_reconcile_skips_failed_when_include_failed_false(self, source_datalake, target_datalake, replication_objects):
        failed = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "failed1",
                "metadata": {"replication": {"payload_status": "failed"}},
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[failed])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.hydrate_asset_payload = AsyncMock()

        result = await manager.reconcile_pending_payloads(ReplicationReconcileRequest(include_failed=False))

        assert result.attempted_asset_ids == []
        assert failed.asset_id in result.skipped_asset_ids
        manager.hydrate_asset_payload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_respects_limit(self, source_datalake, target_datalake, replication_objects):
        assets = [
            Asset.model_validate(
                {
                    **replication_objects.asset.model_dump(),
                    "asset_id": f"id{i}",
                    "metadata": {"replication": {"payload_status": "pending"}},
                }
            )
            for i in range(3)
        ]
        target_datalake.asset_database.find = AsyncMock(return_value=assets)
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.hydrate_asset_payload = AsyncMock(side_effect=assets)

        result = await manager.reconcile_pending_payloads(ReplicationReconcileRequest(limit=1))

        assert len(result.attempted_asset_ids) == 1

    @pytest.mark.asyncio
    async def test_set_asset_replication_state_coerces_bad_origin_and_replication(self, source_datalake, target_datalake, replication_objects):
        asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {"origin": "x", "replication": "y"},
            }
        )
        target_datalake.asset_database.find = AsyncMock(return_value=[asset])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        await manager._set_asset_replication_state(asset, payload_status="pending", payload_last_error=None)
        assert isinstance(asset.metadata["origin"], dict)
        assert isinstance(asset.metadata["replication"], dict)

    @pytest.mark.asyncio
    async def test_transfer_payload_raises_on_source_size_mismatch(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"ab")
        bad = Asset.model_validate(
            {**replication_objects.asset.model_dump(), "size_bytes": 99},
        )
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(ValueError, match="Source read size mismatch"):
            await manager._transfer_payload(bad, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_local_path_requires_upload_path(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"x")
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="u",
                finalize_token="t",
                upload_method="local_path",
                upload_path=None,
                upload_headers={},
            )
        )
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(ValueError, match="missing upload_path"):
            await manager._transfer_payload(replication_objects.asset, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_presigned_requires_upload_url(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"x")
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="u",
                finalize_token="t",
                upload_method="presigned_url",
                upload_url=None,
                upload_headers={},
            )
        )
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(ValueError, match="missing upload_url"):
            await manager._transfer_payload(replication_objects.asset, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_presigned_success(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"payload-bytes")
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="u1",
                finalize_token="t1",
                upload_method="presigned_url",
                upload_url="https://example/upload",
                upload_headers={"X-Test": "1"},
            )
        )
        target_datalake.complete_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(storage_ref=StorageRef(mount="m", name="n", version="v"))
        )
        response = MagicMock()
        response.status = 200
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = response
        mock_cm.__exit__.return_value = None
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with patch("mindtrace.datalake.replication.urllib_request.urlopen", return_value=mock_cm) as urlopen_mock:
            ref = await manager._transfer_payload(replication_objects.asset, {})
        assert ref.name == "n"
        urlopen_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_transfer_payload_presigned_put_failure_status(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"x")
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="u1",
                finalize_token="t1",
                upload_method="presigned_url",
                upload_url="https://example/upload",
                upload_headers={},
            )
        )
        response = MagicMock()
        response.status = 500
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = response
        mock_cm.__exit__.return_value = None
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with patch("mindtrace.datalake.replication.urllib_request.urlopen", return_value=mock_cm):
            with pytest.raises(RuntimeError, match="Presigned upload failed"):
                await manager._transfer_payload(replication_objects.asset, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_unsupported_upload_method(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"x")
        target_datalake.create_object_upload_session = AsyncMock(
            return_value=SimpleNamespace(
                upload_session_id="u1",
                finalize_token="t1",
                upload_method="multipart",
                upload_path=None,
                upload_url=None,
                upload_headers={},
            )
        )
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(ValueError, match="Unsupported upload method"):
            await manager._transfer_payload(replication_objects.asset, {})

    @pytest.mark.asyncio
    async def test_transfer_payload_requires_storage_ref_after_complete(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"x")
        target_datalake.complete_object_upload_session = AsyncMock(return_value=SimpleNamespace(storage_ref=None))
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(RuntimeError, match="did not produce a storage_ref"):
            await manager._transfer_payload(replication_objects.asset, {})

    @pytest.mark.asyncio
    async def test_verify_transferred_payload_size_mismatch(self, source_datalake, target_datalake, replication_objects):
        source_datalake.get_object = AsyncMock(return_value=b"1234567890")
        target_datalake.head_object = AsyncMock(return_value={"size_bytes": 99})
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        ref = StorageRef(mount="m", name="n", version="v")
        with pytest.raises(RuntimeError, match="Post-upload size mismatch"):
            await manager._verify_transferred_payload(replication_objects.asset, ref)

    @pytest.mark.asyncio
    async def test_verify_transferred_payload_checksum_mismatch(self, source_datalake, target_datalake, replication_objects):
        data = b"payload-bytes"
        source_datalake.get_object = AsyncMock(return_value=data)
        target_datalake.head_object = AsyncMock(return_value={"size_bytes": len(data)})
        bad_checksum_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "checksum": "sha256:" + "0" * 64,
            }
        )
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        ref = StorageRef(mount="m", name="n", version="v")
        with pytest.raises(RuntimeError, match="Post-upload checksum mismatch"):
            await manager._verify_transferred_payload(bad_checksum_asset, ref)

    def test_payload_checksum_matches_formats(self, replication_objects):
        manager = MetadataFirstReplicationManager(Mock(), Mock())
        data = b"hello"
        sha_hex = hashlib.sha256(data).hexdigest()
        md_hex = hashlib.md5(data).hexdigest()
        assert manager._payload_checksum_matches(data, f"sha256:{sha_hex}")
        assert manager._payload_checksum_matches(data, f"MD5:{md_hex}")
        assert manager._payload_checksum_matches(data, sha_hex)
        assert manager._payload_checksum_matches(data, md_hex)
        with pytest.raises(ValueError, match="Unsupported checksum algorithm"):
            manager._payload_checksum_matches(data, "crc32:abcd")
        with pytest.raises(ValueError, match="Unrecognized payload checksum format"):
            manager._payload_checksum_matches(data, "not-hex!!!")

    def test_guess_content_type_known_extension(self, replication_objects):
        manager = MetadataFirstReplicationManager(Mock(), Mock())
        ct = manager._guess_content_type("photo.jpeg")
        assert ct == "image/jpeg"

    def test_get_origin_asset_id_edge_cases(self, replication_objects):
        manager = MetadataFirstReplicationManager(Mock(), Mock())
        a1 = Asset.model_validate({**replication_objects.asset.model_dump(), "metadata": {"origin": []}})
        assert manager._get_origin_asset_id(a1) is None
        a2 = Asset.model_validate(
            {**replication_objects.asset.model_dump(), "metadata": {"origin": {"asset_id": 123}}}
        )
        assert manager._get_origin_asset_id(a2) is None


class TestReplicationReclaim:
    @pytest.mark.asyncio
    async def test_mark_local_delete_eligible_requires_verified_remote(self, source_datalake, target_datalake, replication_objects):
        source_asset = Asset.model_validate({**replication_objects.asset.model_dump(), "metadata": {}})
        target_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "origin": {"asset_id": replication_objects.asset.asset_id},
                    "replication": {"payload_status": "pending", "payload_available": False},
                },
            }
        )
        source_datalake.get_asset = AsyncMock(return_value=source_asset)
        source_datalake.asset_database.find = AsyncMock(return_value=[source_asset])
        target_datalake.asset_database.find = AsyncMock(return_value=[target_asset])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        with pytest.raises(RuntimeError, match="not delete-eligible"):
            await manager.mark_local_delete_eligible(replication_objects.asset.asset_id)

    @pytest.mark.asyncio
    async def test_mark_local_delete_eligible_sets_timestamp(self, source_datalake, target_datalake, replication_objects):
        source_asset = Asset.model_validate({**replication_objects.asset.model_dump(), "metadata": {}})
        target_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "origin": {"asset_id": replication_objects.asset.asset_id},
                    "replication": {"payload_status": "verified", "payload_available": True},
                },
            }
        )
        source_datalake.get_asset = AsyncMock(return_value=source_asset)
        source_datalake.asset_database.find = AsyncMock(return_value=[source_asset])
        target_datalake.asset_database.find = AsyncMock(return_value=[target_asset])

        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        updated = await manager.mark_local_delete_eligible(replication_objects.asset.asset_id)

        assert updated.metadata["replication"]["local_delete_eligible_at"] is not None
        assert MetadataFirstReplicationManager.is_local_delete_eligible(updated) is True

    @pytest.mark.asyncio
    async def test_delete_local_payload_requires_eligibility(self, source_datalake, target_datalake, replication_objects):
        source_asset = Asset.model_validate({**replication_objects.asset.model_dump(), "metadata": {"replication": {}}})
        source_datalake.get_asset = AsyncMock(return_value=source_asset)
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)

        with pytest.raises(RuntimeError, match="not delete-eligible"):
            await manager.delete_local_payload(replication_objects.asset.asset_id)

    @pytest.mark.asyncio
    async def test_delete_local_payload_marks_deleted_and_calls_store(self, source_datalake, target_datalake, replication_objects):
        source_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {"replication": {"local_delete_eligible_at": "2026-01-01T00:00:00Z", "payload_available": True}},
            }
        )
        source_datalake.get_asset = AsyncMock(return_value=source_asset)
        source_datalake.asset_database.find = AsyncMock(return_value=[source_asset])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)

        updated = await manager.delete_local_payload(replication_objects.asset.asset_id)

        source_datalake.store.delete.assert_called_once()
        assert updated.metadata["replication"]["local_deleted_at"] is not None
        assert updated.metadata["replication"]["payload_available"] is False
        assert MetadataFirstReplicationManager.is_local_deleted(updated) is True

    @pytest.mark.asyncio
    async def test_delete_local_payload_is_idempotent_when_already_deleted(self, source_datalake, target_datalake, replication_objects):
        source_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {"replication": {"local_delete_eligible_at": "2026-01-01T00:00:00Z", "local_deleted_at": "2026-01-01T00:01:00Z"}},
            }
        )
        source_datalake.get_asset = AsyncMock(return_value=source_asset)
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)

        updated = await manager.delete_local_payload(replication_objects.asset.asset_id)

        source_datalake.store.delete.assert_not_called()
        assert updated is source_asset

    @pytest.mark.asyncio
    async def test_reclaim_verified_payloads_reclaims_verified_assets(self, source_datalake, target_datalake, replication_objects):
        source_asset = Asset.model_validate({**replication_objects.asset.model_dump(), "metadata": {"replication": {}}})
        target_asset = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "metadata": {
                    "origin": {"asset_id": replication_objects.asset.asset_id},
                    "replication": {"payload_status": "verified", "payload_available": True},
                },
            }
        )
        source_datalake.asset_database.find = AsyncMock(return_value=[source_asset])
        source_datalake.get_asset = AsyncMock(return_value=source_asset)
        target_datalake.asset_database.find = AsyncMock(return_value=[target_asset])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.mark_local_delete_eligible = AsyncMock(return_value=source_asset)
        manager.delete_local_payload = AsyncMock(return_value=source_asset)

        result = await manager.reclaim_verified_payloads()

        assert result.attempted_asset_ids == [source_asset.asset_id]
        assert result.reclaimed_asset_ids == [source_asset.asset_id]

    @pytest.mark.asyncio
    async def test_reclaim_verified_payloads_skips_unverified_and_deleted_assets(self, source_datalake, target_datalake, replication_objects):
        unverified = Asset.model_validate({**replication_objects.asset.model_dump(), "asset_id": "u1", "metadata": {"replication": {}}})
        deleted = Asset.model_validate(
            {
                **replication_objects.asset.model_dump(),
                "asset_id": "d1",
                "metadata": {"replication": {"local_deleted_at": "2026-01-01T00:00:00Z"}},
            }
        )
        source_datalake.asset_database.find = AsyncMock(return_value=[unverified, deleted])
        target_datalake.asset_database.find = AsyncMock(return_value=[])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)

        result = await manager.reclaim_verified_payloads()

        assert result.attempted_asset_ids == []
        assert set(result.skipped_asset_ids) == {"u1", "d1"}

    @pytest.mark.asyncio
    async def test_reclaim_verified_payloads_respects_limit_and_asset_ids(self, source_datalake, target_datalake, replication_objects):
        a1 = Asset.model_validate({**replication_objects.asset.model_dump(), "asset_id": "a1", "metadata": {"replication": {}}})
        a2 = Asset.model_validate({**replication_objects.asset.model_dump(), "asset_id": "a2", "metadata": {"replication": {}}})
        t1 = Asset.model_validate({**replication_objects.asset.model_dump(), "asset_id": "ta1", "metadata": {"origin": {"asset_id": "a1"}, "replication": {"payload_status": "verified", "payload_available": True}}})
        t2 = Asset.model_validate({**replication_objects.asset.model_dump(), "asset_id": "ta2", "metadata": {"origin": {"asset_id": "a2"}, "replication": {"payload_status": "verified", "payload_available": True}}})
        source_datalake.asset_database.find = AsyncMock(return_value=[a1, a2])
        target_datalake.asset_database.find = AsyncMock(return_value=[t1, t2])
        manager = MetadataFirstReplicationManager(source_datalake, target_datalake)
        manager.mark_local_delete_eligible = AsyncMock(side_effect=[a1, a2])
        manager.delete_local_payload = AsyncMock(side_effect=[a1, a2])

        result = await manager.reclaim_verified_payloads(ReplicationReclaimRequest(asset_ids=["a2"], limit=1))

        assert result.attempted_asset_ids == ["a2"]
        assert result.reclaimed_asset_ids == ["a2"]
