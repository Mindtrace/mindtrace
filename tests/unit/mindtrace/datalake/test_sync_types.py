from mindtrace.datalake.sync_types import (
    DatasetSyncBundle,
    DatasetSyncCommitResult,
    DatasetSyncImportPlan,
    DatasetSyncImportRequest,
    DatasetSyncPayloadPlan,
    ObjectPayloadDescriptor,
)
from mindtrace.datalake.types import AnnotationRecord, AnnotationSet, Asset, DatasetVersion, Datum, StorageRef


def test_sync_type_defaults_and_nested_models():
    storage_ref = StorageRef(mount="source", name="images/cat.jpg", version="v1")
    asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)
    datum = Datum(asset_refs={"image": asset.asset_id}, annotation_set_ids=["annotation_set_1"])
    annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
    annotation_record = AnnotationRecord(kind="bbox", label="cat", source={"type": "human", "name": "qa"})
    dataset_version = DatasetVersion(dataset_name="demo", version="1.0.0", manifest=[datum.datum_id])
    payload = ObjectPayloadDescriptor(
        asset_id=asset.asset_id,
        storage_ref=storage_ref,
        media_type="image/jpeg",
        checksum="sha256:abc",
    )

    bundle = DatasetSyncBundle(
        dataset_version=dataset_version,
        datums=[datum],
        assets=[asset],
        annotation_sets=[annotation_set],
        annotation_records=[annotation_record],
        payloads=[payload],
    )
    request = DatasetSyncImportRequest(bundle=bundle)
    plan = DatasetSyncImportPlan(
        dataset_name="demo",
        version="1.0.0",
        transfer_policy="copy_if_missing",
        payloads=[
            DatasetSyncPayloadPlan(
                asset_id=asset.asset_id,
                source_storage_ref=storage_ref,
                target_exists=False,
                transfer_required=True,
                reason="missing_on_target",
            )
        ],
        missing_payload_count=1,
        transfer_required_count=1,
        ready_to_commit=True,
    )
    result = DatasetSyncCommitResult(dataset_version=dataset_version)

    assert payload.metadata == {}
    assert bundle.annotation_schemas == []
    assert bundle.metadata == {}
    assert request.transfer_policy == "copy_if_missing"
    assert request.origin_lake_id is None
    assert request.preserve_ids is True
    assert plan.payloads[0].reason == "missing_on_target"
    assert result.created_assets == 0
    assert result.dataset_version.dataset_name == "demo"
