import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pymongo import MongoClient

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import Datalake, DatalakeDirectUploadClient
from mindtrace.datalake.types import AnnotationLabelDefinition, SubjectRef


def _bare_datalake() -> Datalake:
    datalake = object.__new__(Datalake)
    datalake._owns_loop_thread = False
    datalake._loop_thread = None
    datalake._loop = asyncio.new_event_loop()
    return datalake


def _skip_if_presign_unavailable(exc: Exception) -> None:
    message = str(exc).lower()
    if "private key" in message or "sign credentials" in message or "unable to generate a pre-signed url" in message:
        pytest.skip(f"Unable to generate a pre-signed URL: {exc}")


def test_datalake_end_to_end(sync_datalake: Datalake):
    hopper_path = Path("tests/resources/hopper.png")
    image_bytes = hopper_path.read_bytes()

    health = sync_datalake.get_health()
    mounts = sync_datalake.get_mounts()
    storage_ref = sync_datalake.put_object(
        name="sync-hopper.png",
        obj=image_bytes,
        metadata={"source_path": str(hopper_path)},
    )
    loaded = sync_datalake.get_object(storage_ref)
    info = sync_datalake.head_object(storage_ref)
    copied_ref = sync_datalake.copy_object(
        storage_ref,
        target_mount="local",
        target_name="sync-hopper-copy.png",
    )

    asset = sync_datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=storage_ref,
        checksum="sha256:sync",
        size_bytes=len(image_bytes),
        metadata={"source": "integration"},
        created_by="pytest",
    )
    fetched_asset = sync_datalake.get_asset(asset.asset_id)
    listed_assets = sync_datalake.list_assets({"kind": "image"})
    updated_asset = sync_datalake.update_asset_metadata(asset.asset_id, {"stage": "updated"})

    datum = sync_datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={"batch": "sync"},
    )
    fetched_datum = sync_datalake.get_datum(datum.datum_id)
    listed_datums = sync_datalake.list_datums({"split": "train"})
    updated_datum = sync_datalake.update_datum(datum.datum_id, metadata={"batch": "updated"})

    annotation_set = sync_datalake.create_annotation_set(
        name="ground-truth",
        purpose="ground_truth",
        source_type="human",
        datum_id=datum.datum_id,
        metadata={"tool": "pytest"},
        created_by="pytest",
    )
    fetched_annotation_set = sync_datalake.get_annotation_set(annotation_set.annotation_set_id)
    listed_annotation_sets = sync_datalake.list_annotation_sets({"purpose": "ground_truth"})

    inserted_records = sync_datalake.add_annotation_records(
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
    fetched_annotation_record = sync_datalake.get_annotation_record(annotation_record.annotation_id)
    listed_annotation_records = sync_datalake.list_annotation_records({"label": "hopper"})
    updated_annotation_record = sync_datalake.update_annotation_record(
        annotation_record.annotation_id,
        score=0.99,
        source={"type": "machine", "name": "pytest-updated", "version": "2.0"},
    )

    dataset_version = sync_datalake.create_dataset_version(
        dataset_name="integration-dataset-sync",
        version="0.1.0",
        manifest=[datum.datum_id],
        description="sync integration test",
        metadata={"suite": "integration"},
        created_by="pytest",
    )
    fetched_dataset_version = sync_datalake.get_dataset_version("integration-dataset-sync", "0.1.0")
    listed_dataset_versions = sync_datalake.list_dataset_versions(dataset_name="integration-dataset-sync")

    resolved_datum = sync_datalake.resolve_datum(datum.datum_id)
    resolved_dataset = sync_datalake.resolve_dataset_version("integration-dataset-sync", "0.1.0")
    summary = sync_datalake.summary()

    created_from_object = sync_datalake.create_asset_from_object(
        name="sync-hopper-derived.png",
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

    sync_datalake.delete_annotation_record(annotation_record.annotation_id)
    sync_datalake.delete_asset(created_from_object.asset_id)
    sync_datalake.delete_asset(asset.asset_id)


def test_sync_datalake_direct_upload_wrappers(sync_datalake: Datalake):
    payload = b"sync-direct-upload"

    session = sync_datalake.create_object_upload_session(
        name="sync-direct-upload.bin",
        mount="local",
        content_type="application/octet-stream",
        metadata={"source": "integration"},
        created_by="pytest",
    )
    assert session.upload_method == "local_path"
    assert session.upload_path is not None

    Path(session.upload_path).write_bytes(payload)

    fetched = sync_datalake.get_object_upload_session(session.upload_session_id)
    assert fetched.upload_session_id == session.upload_session_id

    completed = sync_datalake.complete_object_upload_session(
        session.upload_session_id,
        finalize_token=session.finalize_token,
        metadata={"verified": True},
    )
    assert completed.status == "completed"
    assert completed.storage_ref is not None

    loaded = sync_datalake.get_object(completed.storage_ref)
    assert loaded == payload

    asset = sync_datalake.create_asset_from_uploaded_object(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=completed.storage_ref,
        size_bytes=len(payload),
        metadata={"source": "integration"},
        created_by="pytest",
    )
    assert asset.storage_ref == completed.storage_ref

    sync_datalake.delete_asset(asset.asset_id)


def test_sync_datalake_reconcile_upload_sessions(sync_datalake: Datalake):
    payload = b"sync-reconcile-upload"
    session = sync_datalake.create_object_upload_session(
        name="sync-reconcile-upload.bin",
        mount="local",
        content_type="application/octet-stream",
        expires_in_minutes=1,
    )
    assert session.upload_path is not None

    Path(session.upload_path).write_bytes(payload)

    mongo_client = MongoClient(sync_datalake.mongo_db_uri)
    try:
        collection = mongo_client[sync_datalake.mongo_db_name]["datalake_direct_upload_sessions"]
        collection.update_one(
            {"upload_session_id": session.upload_session_id},
            {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
        )
    finally:
        mongo_client.close()

    reconciled = sync_datalake.reconcile_upload_sessions()

    assert len(reconciled) == 1
    assert reconciled[0].status == "completed"
    assert reconciled[0].storage_ref is not None
    assert sync_datalake.get_object(reconciled[0].storage_ref) == payload


def test_sync_datalake_direct_upload_client_works_with_datalake(sync_datalake: Datalake):
    client = DatalakeDirectUploadClient(sync_datalake)
    payload = b"sync-direct-upload-client"

    asset = client.create_asset_from_bytes(
        name="sync-direct-upload-client.bin",
        data=payload,
        kind="artifact",
        media_type="application/octet-stream",
        mount="local",
        content_type="application/octet-stream",
        asset_metadata={"source": "integration"},
        size_bytes=len(payload),
        created_by="pytest",
    )

    assert sync_datalake.get_object(asset.storage_ref) == payload
    assert asset.metadata["source"] == "integration"

    sync_datalake.delete_asset(asset.asset_id)


def test_sync_datalake_direct_upload_client_uploads_file_to_gcs(sync_datalake_gcs: Datalake):
    client = DatalakeDirectUploadClient(sync_datalake_gcs)
    hopper_path = Path("tests/resources/hopper.png")
    payload = hopper_path.read_bytes()

    try:
        asset = client.create_asset_from_file(
            path=hopper_path,
            kind="image",
            media_type="image/png",
            mount="gcs",
            content_type="image/png",
            asset_metadata={"source": "integration"},
            created_by="pytest",
        )
    except Exception as exc:
        _skip_if_presign_unavailable(exc)
        raise

    assert sync_datalake_gcs.get_object(asset.storage_ref) == payload
    assert asset.metadata["source"] == "integration"

    sync_datalake_gcs.delete_asset(asset.asset_id)


def test_sync_datalake_init_branch_and_summary_variants():
    backend = MagicMock()
    backend.store = MagicMock()
    backend.mongo_db_uri = "mongodb://localhost:27018"
    backend.mongo_db_name = "sync-existing"

    loop = asyncio.new_event_loop()
    try:
        datalake = Datalake(async_datalake=backend, loop=loop, mongo_db_uri="ignored", mongo_db_name="ignored")
        assert datalake._backend is backend
        assert datalake._loop is loop
        assert datalake.store is backend.store
        assert datalake.mongo_db_uri == "mongodb://localhost:27018"
        assert datalake.mongo_db_name == "sync-existing"
        datalake._submit_coro = MagicMock(
            side_effect=[
                "plain summary",
                "AsyncDatalake(database=sync-existing, default_mount=temp, assets=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)",
                "AsyncDatalake(database=sync-existing, default_mount=temp, assets=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)",
            ]
        )
        assert datalake.summary() == "plain summary"
        assert datalake.summary().startswith("Datalake(database=sync-existing")
        assert str(datalake).startswith("Datalake(database=sync-existing")
    finally:
        loop.close()


def test_sync_datalake_internal_helpers_cover_error_branches():
    datalake = _bare_datalake()
    loop = datalake._loop
    try:

        async def assert_running_loop_guard():
            with pytest.raises(RuntimeError, match="use AsyncDatalake instead"):
                datalake._ensure_not_in_running_loop()

        asyncio.run(assert_running_loop_guard())

        with patch("mindtrace.datalake.datalake.asyncio.set_event_loop") as set_event_loop:
            with patch.object(loop, "run_forever") as run_forever:
                datalake._run_loop()
        set_event_loop.assert_called_once_with(loop)
        run_forever.assert_called_once()

        def boom():
            raise ValueError("boom")

        datalake._loop.call_soon_threadsafe = lambda fn: fn()
        with pytest.raises(ValueError, match="boom"):
            datalake._call_in_loop(boom)

        async def sample():
            return 1

        coro = sample()
        with patch(
            "mindtrace.datalake.datalake.asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("schedule failed")
        ):
            with pytest.raises(RuntimeError, match="schedule failed"):
                datalake._submit_coro(coro)
        assert coro.cr_frame is None

        future = MagicMock()
        future.result.side_effect = RuntimeError("future failed")
        future.cancel.side_effect = RuntimeError("cancel failed")
        with patch("mindtrace.datalake.datalake.asyncio.run_coroutine_threadsafe", return_value=future):
            with pytest.raises(RuntimeError, match="future failed"):
                datalake._submit_coro(sample())
        future.cancel.assert_called_once()
    finally:
        loop.close()


def test_sync_datalake_close_context_manager_handles_cleanup_failures():
    datalake = _bare_datalake()
    failing_loop = MagicMock()
    failing_loop.call_soon_threadsafe.side_effect = RuntimeError("stop failed")
    failing_loop.close.side_effect = RuntimeError("close failed")
    failing_thread = MagicMock()
    failing_thread.join.side_effect = RuntimeError("join failed")
    datalake._loop = failing_loop
    datalake._loop_thread = failing_thread
    datalake._owns_loop_thread = True

    assert datalake.__enter__() is datalake
    assert datalake.__exit__(None, None, None) is False
    assert datalake._owns_loop_thread is False


def test_datalake_collection_and_retention_lifecycle(sync_datalake: Datalake):
    hopper_path = Path("tests/resources/hopper.png")
    image_bytes = hopper_path.read_bytes()

    storage_ref = sync_datalake.put_object(
        name="collection-hopper.png",
        obj=image_bytes,
        metadata={"source_path": str(hopper_path)},
    )
    asset = sync_datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=storage_ref,
        checksum="sha256:collection",
        size_bytes=len(image_bytes),
        metadata={"source": "integration"},
        created_by="pytest",
    )

    collection = sync_datalake.create_collection(
        name="integration-collection",
        description="collection integration test",
        metadata={"suite": "integration"},
        created_by="pytest",
    )
    fetched_collection = sync_datalake.get_collection(collection.collection_id)
    listed_collections = sync_datalake.list_collections({"status": "active"})
    updated_collection = sync_datalake.update_collection(collection.collection_id, status="archived")

    collection_item = sync_datalake.create_collection_item(
        collection_id=collection.collection_id,
        asset_id=asset.asset_id,
        split="train",
        metadata={"role": "example"},
        added_by="pytest",
    )
    fetched_collection_item = sync_datalake.get_collection_item(collection_item.collection_item_id)
    listed_collection_items = sync_datalake.list_collection_items({"collection_id": collection.collection_id})
    resolved_collection_item = sync_datalake.resolve_collection_item(collection_item.collection_item_id)
    updated_collection_item = sync_datalake.update_collection_item(
        collection_item.collection_item_id,
        collection_id=collection.collection_id,
        asset_id=asset.asset_id,
        status="hidden",
    )

    asset_retention = sync_datalake.create_asset_retention(
        asset_id=asset.asset_id,
        owner_type="manual_pin",
        owner_id=collection.collection_id,
        metadata={"suite": "integration"},
        created_by="pytest",
    )
    fetched_asset_retention = sync_datalake.get_asset_retention(asset_retention.asset_retention_id)
    listed_asset_retentions = sync_datalake.list_asset_retentions({"asset_id": asset.asset_id})
    updated_asset_retention = sync_datalake.update_asset_retention(
        asset_retention.asset_retention_id,
        asset_id=asset.asset_id,
        retention_policy="archive_when_unreferenced",
    )

    assert fetched_collection.collection_id == collection.collection_id
    assert any(item.collection_id == collection.collection_id for item in listed_collections)
    assert updated_collection.status == "archived"
    assert fetched_collection_item.collection_item_id == collection_item.collection_item_id
    assert any(item.collection_item_id == collection_item.collection_item_id for item in listed_collection_items)
    assert resolved_collection_item.collection.collection_id == collection.collection_id
    assert resolved_collection_item.asset.asset_id == asset.asset_id
    assert updated_collection_item.status == "hidden"
    assert fetched_asset_retention.asset_retention_id == asset_retention.asset_retention_id
    assert any(item.asset_retention_id == asset_retention.asset_retention_id for item in listed_asset_retentions)
    assert updated_asset_retention.retention_policy == "archive_when_unreferenced"

    sync_datalake.delete_collection_item(collection_item.collection_item_id)
    sync_datalake.delete_asset_retention(asset_retention.asset_retention_id)
    sync_datalake.delete_collection(collection.collection_id)
    sync_datalake.delete_asset(asset.asset_id)

    with pytest.raises(DocumentNotFoundError):
        sync_datalake.get_collection("missing")
    with pytest.raises(DocumentNotFoundError):
        sync_datalake.get_collection_item("missing")
    with pytest.raises(DocumentNotFoundError):
        sync_datalake.get_asset_retention("missing")


def test_sync_datalake_schema_wrappers_and_annotation_set_updates(sync_datalake: Datalake):
    schema = sync_datalake.create_annotation_schema(
        name="sync-schema",
        version="1.0.0",
        task_type="classification",
        allowed_annotation_kinds=["classification"],
        labels=[AnnotationLabelDefinition(name="cat", id=1)],
    )

    fetched_schema = sync_datalake.get_annotation_schema(schema.annotation_schema_id)
    fetched_by_name = sync_datalake.get_annotation_schema_by_name_version("sync-schema", "1.0.0")
    listed_schemas = sync_datalake.list_annotation_schemas({"task_type": "classification"})
    updated_schema = sync_datalake.update_annotation_schema(
        schema.annotation_schema_id,
        labels=[{"name": "cat", "id": 1, "display_name": "Cat"}],
    )

    annotation_set = sync_datalake.create_annotation_set(
        name="schema-rebind",
        purpose="ground_truth",
        source_type="human",
    )
    rebound_set = sync_datalake.update_annotation_set(
        annotation_set.annotation_set_id,
        annotation_schema_id=schema.annotation_schema_id,
        status="active",
    )
    detached_set = sync_datalake.update_annotation_set(annotation_set.annotation_set_id, annotation_schema_id=None)
    sync_datalake.delete_annotation_schema(schema.annotation_schema_id)

    assert fetched_schema.annotation_schema_id == schema.annotation_schema_id
    assert fetched_by_name.annotation_schema_id == schema.annotation_schema_id
    assert any(item.annotation_schema_id == schema.annotation_schema_id for item in listed_schemas)
    assert updated_schema.labels[0].display_name == "Cat"
    assert rebound_set.annotation_schema_id == schema.annotation_schema_id
    assert rebound_set.status == "active"
    assert detached_set.annotation_schema_id is None
