import pytest

from mindtrace.datalake.replication_types import (
    ReplicatedAssetState,
    ReplicationBatchRequest,
    ReplicationBatchResult,
    ReplicationReconcileRequest,
    ReplicationReconcileResult,
)
from mindtrace.datalake.types import Asset, Datum, StorageRef


def test_replication_types_defaults():
    storage_ref = StorageRef(mount="src", name="images/cat.jpg", version="v1")
    asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)
    datum = Datum(asset_refs={"image": asset.asset_id}, annotation_set_ids=[])

    req = ReplicationBatchRequest(assets=[asset], datums=[datum], origin_lake_id="source-lake")
    state = ReplicatedAssetState(origin_lake_id="source-lake", origin_asset_id=asset.asset_id)
    result = ReplicationBatchResult()
    reconcile_request = ReplicationReconcileRequest()
    reconcile_result = ReplicationReconcileResult()

    assert req.replication_mode == "metadata_first"
    assert req.mount_map == {}
    assert state.payload_status == "pending"
    assert state.payload_available is False
    assert result.created_assets == 0
    assert result.updated_datums == 0
    assert reconcile_request.include_failed is True
    assert reconcile_result.attempted_asset_ids == []


def test_replication_batch_request_rejects_empty_mount_map_value():
    storage_ref = StorageRef(mount="src", name="images/cat.jpg", version="v1")
    asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)

    with pytest.raises(ValueError, match="mount_map"):
        ReplicationBatchRequest(assets=[asset], origin_lake_id="source-lake", mount_map={"src": ""})


def test_replication_reconcile_request_rejects_empty_mount_map_value():
    with pytest.raises(ValueError, match="mount_map"):
        ReplicationReconcileRequest(mount_map={"src": ""})
