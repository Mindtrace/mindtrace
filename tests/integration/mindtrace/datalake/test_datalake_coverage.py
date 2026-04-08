import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from beanie.exceptions import CollectionWasNotInitialized

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.async_datalake import AsyncDatalake, _default_datalake_store_path
from mindtrace.datalake.datalake import Datalake
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    AnnotationSource,
    Asset,
    DatasetVersion,
    Datum,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)
from mindtrace.registry import LocalMountConfig, Mount, MountBackendKind

MONGO_URL = "mongodb://localhost:27018"


def _bare_datalake() -> Datalake:
    datalake = object.__new__(Datalake)
    datalake._owns_loop_thread = False
    datalake._loop_thread = None
    datalake._loop = asyncio.new_event_loop()
    return datalake


def test_types_string_representations_cover_model_fallback():
    subject = SubjectRef(kind="asset", id="asset_1")
    storage_ref = StorageRef(mount="local", name="hopper.png", version="1.0.0")
    source = AnnotationSource(type="machine", name="detector", version="1.0.0")

    asset = Asset(kind="image", media_type="image/png", storage_ref=storage_ref, subject=subject)
    record = AnnotationRecord(kind="bbox", label="hopper", source=source, geometry={})
    annotation_set = AnnotationSet(name="ground-truth", purpose="ground_truth", source_type="human")
    datum = Datum(asset_refs={"image": asset.asset_id}, split="train")
    dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=[datum.datum_id])
    resolved_datum = ResolvedDatum(
        datum=datum,
        assets={"image": asset},
        annotation_sets=[annotation_set],
        annotation_records={annotation_set.annotation_set_id: [record]},
    )
    resolved_dataset = ResolvedDatasetVersion(dataset_version=dataset_version, datums=[resolved_datum])

    assert str(subject) == "SubjectRef(kind=asset, id=asset_1)"
    assert str(storage_ref) == f"StorageRef({storage_ref.qualified_key})"
    assert str(source) == "AnnotationSource(type=machine, name=detector, version=1.0.0)"
    assert "Asset(asset_id=" in str(asset)
    assert "AnnotationRecord(annotation_id=" in str(record)
    assert "AnnotationSet(annotation_set_id=" in str(annotation_set)
    assert "Datum(datum_id=" in str(datum)
    assert "DatasetVersion(dataset=demo, version=0.1.0, datums=1)" == str(dataset_version)
    assert "ResolvedDatum(datum_id=" in str(resolved_datum)
    assert "ResolvedDatasetVersion(dataset=demo, version=0.1.0, datums=1)" == str(resolved_dataset)


def test_datalake_document_falls_back_to_pydantic_init_when_collection_is_uninitialized():
    with patch("mindtrace.datalake.types.MindtraceDocument.__init__", side_effect=CollectionWasNotInitialized()):
        asset = Asset(
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="local", name="fallback.png"),
        )

    assert asset.kind == "image"
    assert asset.media_type == "image/png"
    assert asset.storage_ref.name == "fallback.png"


def test_async_datalake_constructor_variants_and_helpers(tmp_path):
    explicit_store = MagicMock()
    explicit_store.default_mount = "explicit"

    with pytest.raises(ValueError, match="Provide either store or mounts, not both"):
        AsyncDatalake(MONGO_URL, "both-provided", store=explicit_store, mounts=[])

    datalake_with_store = AsyncDatalake(MONGO_URL, "store-only", store=explicit_store)
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
    datalake_with_mounts = AsyncDatalake(MONGO_URL, "mounts-only", mounts=mounts, default_mount="mounted")
    assert datalake_with_mounts.store.default_mount == "mounted"

    db_name = f"default-store-{uuid4().hex}"
    default_path = _default_datalake_store_path(MONGO_URL, db_name)
    default_datalake = AsyncDatalake(MONGO_URL, db_name)
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

    datum = await async_datalake.create_datum(asset_refs={}, split="train")
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
    inserted_records = await async_datalake.add_annotation_records(annotation_set.annotation_set_id, [record])

    assert inserted_records[0].annotation_set_id == annotation_set.annotation_set_id
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


def test_sync_datalake_init_branch_and_summary_variants():
    backend = MagicMock()
    backend.store = MagicMock()
    backend.mongo_db_uri = MONGO_URL
    backend.mongo_db_name = "sync-existing"

    loop = asyncio.new_event_loop()
    try:
        datalake = Datalake(async_datalake=backend, loop=loop, mongo_db_uri="ignored", mongo_db_name="ignored")
        assert datalake._backend is backend
        assert datalake._loop is loop
        assert datalake.store is backend.store
        assert datalake.mongo_db_uri == MONGO_URL
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
        with patch("mindtrace.datalake.datalake.asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("schedule failed")):
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
