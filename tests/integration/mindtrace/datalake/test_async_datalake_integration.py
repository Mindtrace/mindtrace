import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError
from mindtrace.datalake import AsyncDatalake
from mindtrace.datalake.async_datalake import (
    AnnotationSchemaInUseError,
    AnnotationSchemaValidationError,
    DuplicateAnnotationSchemaError,
    _default_datalake_store_path,
)
from mindtrace.datalake.pagination_types import DatasetViewExpand, StructuredFilter
from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSet,
    AnnotationSource,
    SubjectRef,
)
from mindtrace.registry import LocalMountConfig, Mount, MountBackendKind

# Annotation sets created without a Datum still need an explicit asset subject per record
# until linked to a datum with asset_refs['image'].
_INTEGRATION_EXPLICIT_SUBJECT = {"kind": "asset", "id": "integration-annotation-subject-explicit"}


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
        annotation_set_id=annotation_set.annotation_set_id,
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
    await async_datalake.update_datum(datum.datum_id, asset_refs={})
    await async_datalake.delete_asset(created_from_object.asset_id)
    await async_datalake.delete_asset(asset.asset_id)


def test_async_datalake_constructor_variants_and_helpers(tmp_path):
    explicit_store = MagicMock()
    explicit_store.default_mount = "explicit"

    with pytest.raises(ValueError, match="Provide either store or mounts, not both"):
        AsyncDatalake("mongodb://localhost:27018", "both-provided", store=explicit_store, mounts=[])

    datalake_with_store = AsyncDatalake("mongodb://localhost:27018", "store-only", store=explicit_store)
    assert datalake_with_store.store is explicit_store

    mount_path = tmp_path / "mounted-store"
    mounts = [
        Mount(
            name="mounted",
            backend=MountBackendKind.LOCAL,
            config=LocalMountConfig(uri=mount_path),
            is_default=True,
        )
    ]
    datalake_with_mounts = AsyncDatalake(
        "mongodb://localhost:27018", "mounts-only", mounts=mounts, default_mount="mounted"
    )
    assert datalake_with_mounts.store.default_mount == "mounted"

    db_name = f"default-store-{uuid4().hex}"
    default_path = _default_datalake_store_path("mongodb://localhost:27018", db_name)
    default_datalake = AsyncDatalake("mongodb://localhost:27018", db_name)
    try:
        assert default_path.exists()
        assert default_datalake.store.default_mount == "default"
        assert str(default_datalake) == f"AsyncDatalake(database={db_name}, default_mount=default)"
    finally:
        shutil.rmtree(default_path, ignore_errors=True)


@pytest.mark.asyncio
async def test_async_datalake_error_paths_and_instance_annotation_record(async_datalake: AsyncDatalake):
    with pytest.raises(DocumentNotFoundError, match="Asset with asset_id missing-asset not found"):
        await async_datalake.get_asset("missing-asset")
    with pytest.raises(DocumentNotFoundError, match="AnnotationSet with annotation_set_id missing-set not found"):
        await async_datalake.get_annotation_set("missing-set")
    with pytest.raises(DocumentNotFoundError, match="AnnotationRecord with annotation_id missing-record not found"):
        await async_datalake.get_annotation_record("missing-record")
    with pytest.raises(DocumentNotFoundError, match="Datum with datum_id missing-datum not found"):
        await async_datalake.get_datum("missing-datum")
    with pytest.raises(DocumentNotFoundError, match="DatasetVersion missing@0.0.1 not found"):
        await async_datalake.get_dataset_version("missing", "0.0.1")

    storage_ref = await async_datalake.put_object(
        name="error-paths-inst.png", obj=b"\x89PNG\r\n\x1a\n", metadata={}
    )
    img_asset = await async_datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=storage_ref,
        metadata={},
        created_by="pytest",
    )
    datum = await async_datalake.create_datum(asset_refs={"image": img_asset.asset_id}, split="train")
    annotation_set = await async_datalake.create_annotation_set(
        name="instance-records",
        purpose="ground_truth",
        source_type="human",
        datum_id=datum.datum_id,
    )
    record = AnnotationRecord(
        kind="bbox",
        label="hopper",
        source=AnnotationSource(type="human", name="pytest"),
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    inserted_records = await async_datalake.add_annotation_records([record], annotation_set_id=annotation_set.annotation_set_id)

    refreshed_annotation_set = await async_datalake.get_annotation_set(annotation_set.annotation_set_id)
    assert inserted_records[0].annotation_id in refreshed_annotation_set.annotation_record_ids
    assert inserted_records[0].updated_at is not None

    await async_datalake.create_dataset_version(
        dataset_name="duplicate-dataset",
        version="0.1.0",
        manifest=[datum.datum_id],
    )
    with pytest.raises(ValueError, match="Dataset version already exists: duplicate-dataset@0.1.0"):
        await async_datalake.create_dataset_version(
            dataset_name="duplicate-dataset",
            version="0.1.0",
            manifest=[datum.datum_id],
        )


@pytest.mark.asyncio
async def test_async_datalake_direct_upload_error_paths(async_datalake: AsyncDatalake):
    with pytest.raises(ValueError, match="expires_in_minutes must be positive"):
        await async_datalake.create_object_upload_session(name="invalid-expiry.bin", expires_in_minutes=0)

    with pytest.raises(DocumentNotFoundError, match="Upload session with upload_session_id missing-session not found"):
        await async_datalake.get_object_upload_session("missing-session")

    session = await async_datalake.create_object_upload_session(
        name="missing-direct-upload.bin",
        mount="local",
        content_type="application/octet-stream",
    )

    with pytest.raises(ValueError, match="Invalid finalize token"):
        await async_datalake.complete_object_upload_session(
            session.upload_session_id,
            finalize_token="wrong-token",
        )

    with pytest.raises(FileNotFoundError, match="Staged upload not found"):
        await async_datalake.complete_object_upload_session(
            session.upload_session_id,
            finalize_token=session.finalize_token,
        )


@pytest.mark.asyncio
async def test_async_datalake_annotation_schema_flow(async_datalake: AsyncDatalake):
    schema = await async_datalake.create_annotation_schema(
        name="integration-bbox",
        version="1.0.0",
        task_type="detection",
        allowed_annotation_kinds=["bbox"],
        labels=[AnnotationLabelDefinition(name="hopper", id=1)],
        required_attributes=["quality"],
    )

    fetched_schema = await async_datalake.get_annotation_schema(schema.annotation_schema_id)
    fetched_by_name = await async_datalake.get_annotation_schema_by_name_version("integration-bbox", "1.0.0")
    listed_schemas = await async_datalake.list_annotation_schemas({"task_type": "detection"})
    updated_schema = await async_datalake.update_annotation_schema(schema.annotation_schema_id, allow_scores=True)

    hopper_path = Path("tests/resources/hopper.png")
    image_bytes = hopper_path.read_bytes()
    sr = await async_datalake.put_object(name="schema-flow-hopper.png", obj=image_bytes, metadata={})
    flow_asset = await async_datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=sr,
        metadata={},
        created_by="pytest",
    )
    datum = await async_datalake.create_datum(asset_refs={"image": flow_asset.asset_id}, split="train")
    annotation_set = await async_datalake.create_annotation_set(
        name="schema-bound",
        purpose="ground_truth",
        source_type="human",
        datum_id=datum.datum_id,
        annotation_schema_id=schema.annotation_schema_id,
    )

    inserted = await async_datalake.add_annotation_records(
        [
            {
                "kind": "bbox",
                "label": "hopper",
                "label_id": 1,
                "source": {"type": "human", "name": "pytest"},
                "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                "attributes": {"quality": "high"},
                "score": 0.5,
            }
        ],
        annotation_set_id=annotation_set.annotation_set_id,
    )

    with pytest.raises(AnnotationSchemaValidationError, match="not defined in schema"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "unknown",
                    "source": {"type": "human", "name": "pytest"},
                    "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    "attributes": {"quality": "high"},
                }
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )

    assert fetched_schema.annotation_schema_id == schema.annotation_schema_id
    assert fetched_by_name.annotation_schema_id == schema.annotation_schema_id
    assert any(item.annotation_schema_id == schema.annotation_schema_id for item in listed_schemas)
    assert updated_schema.allow_scores is True
    assert inserted[0].label == "hopper"


@pytest.mark.asyncio
async def test_async_datalake_annotation_schema_error_paths(async_datalake: AsyncDatalake):
    schema = await async_datalake.create_annotation_schema(
        name="classification-errors",
        version="1.0.0",
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="cat", id=1)],
        required_attributes=["quality"],
        optional_attributes=["reviewed"],
    )

    with pytest.raises(DuplicateAnnotationSchemaError, match="classification-errors@1.0.0"):
        await async_datalake.create_annotation_schema(
            name="classification-errors",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
        )

    with pytest.raises(DocumentNotFoundError, match="annotation_schema_id missing-schema not found"):
        await async_datalake.get_annotation_schema("missing-schema")
    with pytest.raises(DocumentNotFoundError, match="AnnotationSchema missing@0.0.1 not found"):
        await async_datalake.get_annotation_schema_by_name_version("missing", "0.0.1")

    updated_schema = await async_datalake.update_annotation_schema(
        schema.annotation_schema_id,
        labels=[{"name": "cat", "id": 1, "display_name": "Cat"}],
    )
    assert updated_schema.labels[0].display_name == "Cat"

    datum = await async_datalake.create_datum(asset_refs={}, split="train")
    annotation_set = await async_datalake.create_annotation_set(
        name="classification-set",
        purpose="ground_truth",
        source_type="human",
        datum_id=datum.datum_id,
        annotation_schema_id=schema.annotation_schema_id,
    )

    with pytest.raises(AnnotationSchemaInUseError, match="still referenced"):
        await async_datalake.delete_annotation_schema(schema.annotation_schema_id)

    updated_set = await async_datalake.update_annotation_set(
        annotation_set.annotation_set_id,
        annotation_schema_id=schema.annotation_schema_id,
        status="active",
    )
    assert updated_set.status == "active"
    detached_set = await async_datalake.update_annotation_set(
        annotation_set.annotation_set_id, annotation_schema_id=None
    )
    assert detached_set.annotation_schema_id is None

    invalid_classification_set = await async_datalake.create_annotation_set(
        name="classification-validation",
        purpose="ground_truth",
        source_type="human",
        annotation_schema_id=updated_schema.annotation_schema_id,
    )

    with pytest.raises(AnnotationSchemaValidationError, match="must not include geometry"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "classification",
                    "label": "cat",
                    "label_id": 1,
                    "source": {"type": "human", "name": "pytest"},
                    "geometry": {"x": 1},
                    "attributes": {"quality": "high"},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=invalid_classification_set.annotation_set_id,
        )

    with pytest.raises(AnnotationSchemaValidationError, match="kind 'bbox' is not allowed"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "cat",
                    "label_id": 1,
                    "source": {"type": "human", "name": "pytest"},
                    "geometry": {},
                    "attributes": {"quality": "high"},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=invalid_classification_set.annotation_set_id,
        )

    with pytest.raises(AnnotationSchemaValidationError, match="label_id 9 does not match"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "classification",
                    "label": "cat",
                    "label_id": 9,
                    "source": {"type": "human", "name": "pytest"},
                    "attributes": {"quality": "high"},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=invalid_classification_set.annotation_set_id,
        )

    with pytest.raises(AnnotationSchemaValidationError, match="missing required fields: quality"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "classification",
                    "label": "cat",
                    "label_id": 1,
                    "source": {"type": "human", "name": "pytest"},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=invalid_classification_set.annotation_set_id,
        )

    with pytest.raises(
        AnnotationSchemaValidationError, match="not allowed by schema 'classification-errors@1.0.0': extra"
    ):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "classification",
                    "label": "cat",
                    "label_id": 1,
                    "source": {"type": "human", "name": "pytest"},
                    "attributes": {"quality": "high", "extra": True},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=invalid_classification_set.annotation_set_id,
        )

    with pytest.raises(AnnotationSchemaValidationError, match="scores are not allowed"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "classification",
                    "label": "cat",
                    "label_id": 1,
                    "source": {"type": "human", "name": "pytest"},
                    "attributes": {"quality": "high"},
                    "score": 0.5,
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=invalid_classification_set.annotation_set_id,
        )
    await async_datalake.update_annotation_set(
        invalid_classification_set.annotation_set_id,
        annotation_schema_id=None,
    )
    await async_datalake.delete_annotation_schema(schema.annotation_schema_id)

    detection_schema = await async_datalake.create_annotation_schema(
        name="detection-errors",
        version="1.0.0",
        task_type="detection",
        allowed_annotation_kinds=["bbox"],
        labels=[AnnotationLabelDefinition(name="dent")],
    )
    detection_set = await async_datalake.create_annotation_set(
        name="detection-set",
        purpose="ground_truth",
        source_type="human",
        annotation_schema_id=detection_schema.annotation_schema_id,
    )
    with pytest.raises(AnnotationSchemaValidationError, match="missing required geometry fields"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "source": {"type": "human", "name": "pytest"},
                    "geometry": {"x": 1, "y": 2, "width": 3},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=detection_set.annotation_set_id,
        )

    segmentation_schema = await async_datalake.create_annotation_schema(
        name="segmentation-errors",
        version="1.0.0",
        task_type="segmentation",
        allowed_annotation_kinds=["mask"],
        labels=[AnnotationLabelDefinition(name="dent")],
    )
    segmentation_set = await async_datalake.create_annotation_set(
        name="segmentation-set",
        purpose="ground_truth",
        source_type="human",
        annotation_schema_id=segmentation_schema.annotation_schema_id,
    )
    with pytest.raises(AnnotationSchemaValidationError, match="must include non-empty geometry"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "mask",
                    "label": "dent",
                    "source": {"type": "human", "name": "pytest"},
                    "geometry": {},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=segmentation_set.annotation_set_id,
        )
    with pytest.raises(AnnotationSchemaValidationError, match="must include at least one of"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "mask",
                    "label": "dent",
                    "source": {"type": "human", "name": "pytest"},
                    "geometry": {"x": 1},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=segmentation_set.annotation_set_id,
        )


@pytest.mark.asyncio
async def test_async_datalake_mocked_duplicate_and_rollback_paths(async_datalake: AsyncDatalake):
    async_datalake.annotation_schema_database.find = AsyncMock(return_value=[])
    async_datalake.annotation_schema_database.insert = AsyncMock(side_effect=DuplicateInsertError("duplicate"))

    with pytest.raises(DuplicateAnnotationSchemaError, match="duplicate-schema@1.0.0"):
        await async_datalake.create_annotation_schema(
            name="duplicate-schema",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
        )

    record_without_id = AnnotationRecord(
        kind="bbox",
        label="dent",
        source={"type": "human", "name": "pytest"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    record_with_id = AnnotationRecord(
        kind="bbox",
        label="dent",
        source={"type": "human", "name": "pytest"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    record_with_id.id = "db-record"
    async_datalake.annotation_record_database.delete = AsyncMock(side_effect=RuntimeError("delete failed"))
    await async_datalake._rollback_inserted_annotation_records([record_without_id, record_with_id])

    annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
    async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
    inserted = AnnotationRecord(
        kind="bbox",
        label="dent",
        source={"type": "human", "name": "pytest"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    inserted.id = "db-inserted"
    inserted.annotation_id = "annotation_1"

    async_datalake.annotation_record_database.insert = AsyncMock(side_effect=[inserted, RuntimeError("insert failed")])
    async_datalake.annotation_record_database.delete = AsyncMock()
    with pytest.raises(RuntimeError, match="insert failed"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "source": {"type": "human", "name": "pytest"},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                },
                {
                    "kind": "bbox",
                    "label": "dent",
                    "source": {"type": "human", "name": "pytest"},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                },
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )

    async_datalake.annotation_record_database.insert = AsyncMock(return_value=inserted)
    async_datalake.annotation_record_database.delete.reset_mock()
    async_datalake.annotation_set_database.update = AsyncMock(side_effect=RuntimeError("update failed"))
    with pytest.raises(RuntimeError, match="update failed"):
        await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "source": {"type": "human", "name": "pytest"},
                    "subject": _INTEGRATION_EXPLICIT_SUBJECT,
                }
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )


@pytest.mark.asyncio
async def test_async_datalake_pagination_end_to_end(async_datalake: AsyncDatalake):
    hopper_path = Path("tests/resources/hopper.png")
    image_bytes = hopper_path.read_bytes()
    created_assets = []
    created_datums = []

    for index in range(3):
        storage_ref = await async_datalake.put_object(name=f"page-asset-{index}.png", obj=image_bytes, metadata={})
        asset = await async_datalake.create_asset(
            kind="image",
            media_type="image/png",
            storage_ref=storage_ref,
            checksum=f"sha256:page-{index}",
            size_bytes=len(image_bytes),
            metadata={"page_index": index},
            created_by="pytest",
        )
        datum = await async_datalake.create_datum(
            asset_refs={"image": asset.asset_id},
            split="train",
            metadata={"page_index": index},
        )
        created_assets.append(asset)
        created_datums.append(datum)

    dataset_version = await async_datalake.create_dataset_version(
        dataset_name="pagination-dataset",
        version="0.1.0",
        manifest=[datum.datum_id for datum in created_datums],
        metadata={"suite": "pagination"},
        created_by="pytest",
    )

    first_asset_page = await async_datalake.list_assets_page(filters={"kind": "image"}, limit=2, include_total=True)
    second_asset_page = await async_datalake.list_assets_page(
        filters={"kind": "image"},
        limit=2,
        cursor=first_asset_page.page.next_cursor,
    )

    assert len(first_asset_page.items) == 2
    assert first_asset_page.page.total_count >= 3
    assert first_asset_page.page.has_more is True
    assert first_asset_page.page.next_cursor is not None
    assert len(second_asset_page.items) >= 1

    filters = [StructuredFilter(field="split", op="eq", value="train")]
    first_view_page = await async_datalake.view_dataset_version_page(
        dataset_version.dataset_name,
        dataset_version.version,
        limit=2,
        filters=filters,
        expand=DatasetViewExpand(assets=True, annotation_sets=False, annotation_records=False),
        include_total=True,
    )
    second_view_page = await async_datalake.view_dataset_version_page(
        dataset_version.dataset_name,
        dataset_version.version,
        limit=2,
        cursor=first_view_page.page.next_cursor,
        filters=filters,
        expand=DatasetViewExpand(assets=False, annotation_sets=False, annotation_records=False),
    )

    assert [row.datum_id for row in first_view_page.items] == [datum.datum_id for datum in created_datums[:2]]
    assert first_view_page.items[0].assets is not None
    assert first_view_page.page.total_count == 3
    assert first_view_page.page.has_more is True
    assert second_view_page.items[0].datum_id == created_datums[2].datum_id
    assert second_view_page.items[0].assets is None
    assert second_view_page.page.has_more is False
