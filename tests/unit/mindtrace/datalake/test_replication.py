from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.replication import MetadataFirstReplicationManager
from mindtrace.datalake.replication_types import ReplicationBatchRequest
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
def source_datalake():
    datalake = Mock()
    datalake.mongo_db_name = "source_db"
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
