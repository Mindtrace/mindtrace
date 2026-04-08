from pathlib import Path

import pytest

from mindtrace.datalake import AsyncDatalake
from mindtrace.datalake.types import SubjectRef


@pytest.mark.asyncio
async def test_async_datalake_end_to_end(async_datalake: AsyncDatalake):
    hopper_path = Path("tests/resources/hopper.png")
    image_bytes = hopper_path.read_bytes()

    health = await async_datalake.get_health()
    mounts = async_datalake.get_mounts()
    storage_ref = await async_datalake.put_object(
        name="async-hopper.png",
        obj=image_bytes,
        metadata={"source_path": str(hopper_path)},
    )
    loaded = await async_datalake.get_object(storage_ref)
    info = await async_datalake.head_object(storage_ref)
    copied_ref = await async_datalake.copy_object(
        storage_ref,
        target_mount="local",
        target_name="async-hopper-copy.png",
    )

    asset = await async_datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=storage_ref,
        checksum="sha256:async",
        size_bytes=len(image_bytes),
        metadata={"source": "integration"},
        created_by="pytest",
    )
    fetched_asset = await async_datalake.get_asset(asset.asset_id)
    listed_assets = await async_datalake.list_assets({"kind": "image"})
    updated_asset = await async_datalake.update_asset_metadata(asset.asset_id, {"stage": "updated"})

    datum = await async_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"batch": "async"},
    )
    fetched_datum = await async_datalake.get_datum(datum.datum_id)
    listed_datums = await async_datalake.list_datums({"split": "train"})
    updated_datum = await async_datalake.update_datum(datum.datum_id, metadata={"batch": "updated"})

    annotation_set = await async_datalake.create_annotation_set(
        name="ground-truth",
        purpose="ground_truth",
        source_type="human",
        datum_id=datum.datum_id,
        metadata={"tool": "pytest"},
        created_by="pytest",
    )
    fetched_annotation_set = await async_datalake.get_annotation_set(annotation_set.annotation_set_id)
    listed_annotation_sets = await async_datalake.list_annotation_sets({"purpose": "ground_truth"})

    inserted_records = await async_datalake.add_annotation_records(
        annotation_set.annotation_set_id,
        [
            {
                "kind": "bbox",
                "label": "hopper",
                "source": {"type": "human", "name": "pytest", "version": "1.0"},
                "subject": SubjectRef(kind="asset", id=asset.asset_id),
                "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                "attributes": {"quality": "high"},
            }
        ],
    )
    annotation_record = inserted_records[0]
    fetched_annotation_record = await async_datalake.get_annotation_record(annotation_record.annotation_id)
    listed_annotation_records = await async_datalake.list_annotation_records({"label": "hopper"})
    updated_annotation_record = await async_datalake.update_annotation_record(
        annotation_record.annotation_id,
        score=0.99,
        source={"type": "machine", "name": "pytest-updated", "version": "2.0"},
    )

    dataset_version = await async_datalake.create_dataset_version(
        dataset_name="integration-dataset",
        version="0.1.0",
        manifest=[datum.datum_id],
        description="async integration test",
        metadata={"suite": "integration"},
        created_by="pytest",
    )
    fetched_dataset_version = await async_datalake.get_dataset_version("integration-dataset", "0.1.0")
    listed_dataset_versions = await async_datalake.list_dataset_versions(dataset_name="integration-dataset")

    resolved_datum = await async_datalake.resolve_datum(datum.datum_id)
    resolved_dataset = await async_datalake.resolve_dataset_version("integration-dataset", "0.1.0")
    summary = await async_datalake.summary()

    created_from_object = await async_datalake.create_asset_from_object(
        name="async-hopper-derived.png",
        obj=image_bytes,
        kind="image",
        media_type="image/png",
        object_metadata={"source_path": str(hopper_path)},
        asset_metadata={"derived": True},
        checksum="sha256:derived",
        size_bytes=len(image_bytes),
        subject=SubjectRef(kind="asset", id=asset.asset_id),
        created_by="pytest",
        on_conflict="overwrite",
    )

    assert health["status"] == "ok"
    assert mounts["default_mount"] == "local"
    assert loaded == image_bytes
    assert info.get("exists", True) is True
    assert "path" in info or "hash" in info
    assert copied_ref.mount == "local"
    assert fetched_asset.asset_id == asset.asset_id
    assert any(item.asset_id == asset.asset_id for item in listed_assets)
    assert updated_asset.metadata == {"stage": "updated"}
    assert fetched_datum.datum_id == datum.datum_id
    assert any(item.datum_id == datum.datum_id for item in listed_datums)
    assert updated_datum.metadata == {"batch": "updated"}
    assert fetched_annotation_set.annotation_set_id == annotation_set.annotation_set_id
    assert any(item.annotation_set_id == annotation_set.annotation_set_id for item in listed_annotation_sets)
    assert fetched_annotation_record.annotation_id == annotation_record.annotation_id
    assert any(item.annotation_id == annotation_record.annotation_id for item in listed_annotation_records)
    assert updated_annotation_record.score == 0.99
    assert updated_annotation_record.source.name == "pytest-updated"
    assert fetched_dataset_version.dataset_version_id == dataset_version.dataset_version_id
    assert len(listed_dataset_versions) == 1
    assert resolved_datum.datum.datum_id == datum.datum_id
    assert resolved_datum.assets["image"].asset_id == asset.asset_id
    assert resolved_dataset.dataset_version.dataset_version_id == dataset_version.dataset_version_id
    assert len(resolved_dataset.datums) == 1
    assert "assets=" in summary and "dataset_versions=" in summary
    assert created_from_object.subject.id == asset.asset_id

    await async_datalake.delete_annotation_record(annotation_record.annotation_id)
    await async_datalake.delete_asset(created_from_object.asset_id)
    await async_datalake.delete_asset(asset.asset_id)
