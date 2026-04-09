import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
)


class TestDatalakeSyncFacade:
    @staticmethod
    def _bare_datalake() -> Datalake:
        datalake = object.__new__(Datalake)
        datalake._owns_loop_thread = False
        datalake._loop_thread = None
        datalake._loop = asyncio.new_event_loop()
        return datalake

    def test_init_with_existing_async_datalake_and_loop(self):
        backend = MagicMock()
        backend.store = MagicMock()
        backend.mongo_db_uri = "mongodb://test:27017"
        backend.mongo_db_name = "test_db"
        loop = asyncio.new_event_loop()
        try:
            datalake = Datalake(async_datalake=backend, loop=loop, mongo_db_uri="ignored", mongo_db_name="ignored")
            assert datalake._backend is backend
            assert datalake._loop is loop
            assert datalake.store is backend.store
            assert datalake.mongo_db_uri == "mongodb://test:27017"
            assert datalake.mongo_db_name == "test_db"
        finally:
            loop.close()

    def test_create_classmethod_initializes_sync_instance(self):
        with (
            patch.object(Datalake, "__init__", return_value=None) as init_mock,
            patch.object(Datalake, "initialize", return_value=None) as initialize_mock,
        ):
            result = Datalake.create("mongodb://test:27017", "test_db")

        init_mock.assert_called_once_with(
            mongo_db_uri="mongodb://test:27017",
            mongo_db_name="test_db",
            store=None,
            mounts=None,
            default_mount=None,
        )
        initialize_mock.assert_called_once()
        assert isinstance(result, Datalake)

    @pytest.fixture
    def mock_backend(self):
        backend = MagicMock()
        backend.store = MagicMock()
        backend.store.default_mount = "temp"
        backend.store.list_mount_info.return_value = {"temp": {"backend": "file:///tmp", "mutable": True}}
        backend.get_mounts.return_value = {
            "default_mount": "temp",
            "mounts": [{"name": "temp", "backend": "file:///tmp", "mutable": True}],
        }
        backend.mongo_db_uri = "mongodb://test:27017"
        backend.mongo_db_name = "test_db"
        for name, value in {
            "initialize": None,
            "get_health": {"status": "ok", "database": "test_db", "default_mount": "temp"},
            "put_object": StorageRef(mount="temp", name="hopper.png", version="v1"),
            "get_object": b"payload",
            "head_object": {"size": 123},
            "copy_object": StorageRef(mount="archive", name="hopper.png", version="v2"),
            "create_asset": Asset(
                kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")
            ),
            "get_asset": Asset(
                kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")
            ),
            "list_assets": [],
            "update_asset_metadata": Asset(
                kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")
            ),
            "delete_asset": None,
            "create_collection": Collection(name="demo-collection"),
            "get_collection": Collection(name="demo-collection"),
            "list_collections": [],
            "update_collection": Collection(name="demo-collection"),
            "delete_collection": None,
            "create_collection_item": CollectionItem(collection_id="collection_1", asset_id="asset_1"),
            "get_collection_item": CollectionItem(collection_id="collection_1", asset_id="asset_1"),
            "list_collection_items": [],
            "resolve_collection_item": ResolvedCollectionItem(
                collection_item=CollectionItem(collection_id="collection_1", asset_id="asset_1"),
                collection=Collection(name="demo-collection"),
                asset=Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")),
            ),
            "update_collection_item": CollectionItem(collection_id="collection_1", asset_id="asset_1"),
            "delete_collection_item": None,
            "create_asset_retention": AssetRetention(asset_id="asset_1", owner_type="manual_pin", owner_id="owner_1"),
            "get_asset_retention": AssetRetention(asset_id="asset_1", owner_type="manual_pin", owner_id="owner_1"),
            "list_asset_retentions": [],
            "update_asset_retention": AssetRetention(asset_id="asset_1", owner_type="manual_pin", owner_id="owner_1"),
            "delete_asset_retention": None,
            "create_annotation_schema": AnnotationSchema(
                name="demo-schema",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[AnnotationLabelDefinition(name="cat")],
            ),
            "get_annotation_schema": AnnotationSchema(
                name="demo-schema",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[AnnotationLabelDefinition(name="cat")],
            ),
            "get_annotation_schema_by_name_version": AnnotationSchema(
                name="demo-schema",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[AnnotationLabelDefinition(name="cat")],
            ),
            "list_annotation_schemas": [],
            "update_annotation_schema": AnnotationSchema(
                name="demo-schema",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[AnnotationLabelDefinition(name="cat")],
            ),
            "delete_annotation_schema": None,
            "create_annotation_set": AnnotationSet(name="gt", purpose="ground_truth", source_type="human"),
            "get_annotation_set": AnnotationSet(name="gt", purpose="ground_truth", source_type="human"),
            "list_annotation_sets": [],
            "update_annotation_set": AnnotationSet(name="gt", purpose="ground_truth", source_type="human"),
            "add_annotation_records": [],
            "get_annotation_record": AnnotationRecord(
                kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}
            ),
            "list_annotation_records": [],
            "update_annotation_record": AnnotationRecord(
                kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}
            ),
            "delete_annotation_record": None,
            "create_datum": Datum(asset_refs={"image": "asset_1"}),
            "get_datum": Datum(asset_refs={"image": "asset_1"}),
            "list_datums": [],
            "update_datum": Datum(asset_refs={"image": "asset_1"}),
            "create_dataset_version": DatasetVersion(dataset_name="demo", version="0.1.0"),
            "get_dataset_version": DatasetVersion(dataset_name="demo", version="0.1.0"),
            "list_dataset_versions": [],
            "resolve_datum": ResolvedDatum(datum=Datum(asset_refs={"image": "asset_1"})),
            "resolve_dataset_version": ResolvedDatasetVersion(
                dataset_version=DatasetVersion(dataset_name="demo", version="0.1.0"), datums=[]
            ),
            "create_asset_from_object": Asset(
                kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")
            ),
        }.items():
            setattr(backend, name, AsyncMock(return_value=value))
        return backend

    @pytest.fixture
    def datalake(self, mock_backend):
        with patch("mindtrace.datalake.datalake.AsyncDatalake", return_value=mock_backend):
            dl = Datalake("mongodb://test:27017", "test_db")
            yield dl
            dl.close()

    def test_sync_facade_rejects_calls_inside_running_loop(self, datalake):
        async def inner():
            with pytest.raises(RuntimeError, match="use AsyncDatalake instead"):
                datalake.list_assets()

        asyncio.run(inner())

    def test_run_loop_helper_executes_forever_loop(self):
        datalake = self._bare_datalake()
        loop = datalake._loop
        try:
            with patch("mindtrace.datalake.datalake.asyncio.set_event_loop") as set_event_loop:
                with patch.object(loop, "run_forever") as run_forever:
                    datalake._run_loop()
            set_event_loop.assert_called_once_with(loop)
            run_forever.assert_called_once()
        finally:
            loop.close()

    def test_call_in_loop_with_coroutine_function(self, datalake):
        async def sample(value):
            return value

        fake_future = MagicMock()
        fake_future.result.return_value = "ok"
        with patch("mindtrace.datalake.datalake.asyncio.run_coroutine_threadsafe", return_value=fake_future) as submit:
            result = datalake._call_in_loop(sample, "ok")
        submit.assert_called_once()
        assert result == "ok"

    def test_call_in_loop_propagates_constructor_exception(self):
        datalake = self._bare_datalake()
        try:

            def boom():
                raise ValueError("boom")

            datalake._loop.call_soon_threadsafe = lambda fn: fn()
            with pytest.raises(ValueError, match="boom"):
                datalake._call_in_loop(boom)
        finally:
            datalake._loop.close()

    def test_submit_coro_closes_coro_when_scheduling_fails(self, datalake):
        async def sample():
            return 1

        coro = sample()
        with patch(
            "mindtrace.datalake.datalake.asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("schedule failed")
        ):
            with pytest.raises(RuntimeError, match="schedule failed"):
                datalake._submit_coro(coro)
        assert coro.cr_frame is None

    def test_submit_coro_cancels_future_when_result_raises(self, datalake):
        async def sample():
            return 1

        future = MagicMock()
        future.result.side_effect = RuntimeError("future failed")
        with patch("mindtrace.datalake.datalake.asyncio.run_coroutine_threadsafe", return_value=future):
            with pytest.raises(RuntimeError, match="future failed"):
                datalake._submit_coro(sample())
        future.cancel.assert_called_once()

    def test_submit_coro_ignores_cancel_failure_and_reraises_original_error(self, datalake):
        async def sample():
            return 1

        future = MagicMock()
        future.result.side_effect = RuntimeError("future failed")
        future.cancel.side_effect = RuntimeError("cancel failed")
        with patch("mindtrace.datalake.datalake.asyncio.run_coroutine_threadsafe", return_value=future):
            with pytest.raises(RuntimeError, match="future failed"):
                datalake._submit_coro(sample())
        future.cancel.assert_called_once()

    def test_sync_facade_basic_methods(self, datalake, mock_backend):
        mock_backend.summary = AsyncMock(
            return_value=(
                "Datalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
                "asset_retentions=0, annotation_schemas=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
            )
        )
        datalake.initialize()
        assert datalake.get_health()["status"] == "ok"
        assert (
            datalake.summary()
            == (
                "Datalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
                "asset_retentions=0, annotation_schemas=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
            )
        )
        assert (
            str(datalake)
            == (
                "Datalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
                "asset_retentions=0, annotation_schemas=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
            )
        )
        assert datalake.get_mounts()["default_mount"] == "temp"
        assert datalake.put_object(name="hopper.png", obj=b"bytes").version == "v1"
        assert datalake.get_object(StorageRef(mount="temp", name="hopper.png", version="v1")) == b"payload"
        assert datalake.head_object(StorageRef(mount="temp", name="hopper.png", version="v1")) == {"size": 123}
        assert (
            datalake.copy_object(
                StorageRef(mount="temp", name="hopper.png", version="v1"),
                target_mount="archive",
                target_name="hopper.png",
            ).version
            == "v2"
        )
        assert isinstance(
            datalake.create_asset(
                kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")
            ),
            Asset,
        )
        assert isinstance(datalake.get_asset("asset_1"), Asset)
        assert datalake.list_assets() == []
        assert isinstance(datalake.update_asset_metadata("asset_1", {"source": "demo"}), Asset)
        datalake.delete_asset("asset_1")
        assert isinstance(datalake.create_collection(name="demo-collection"), Collection)
        assert isinstance(datalake.get_collection("collection_1"), Collection)
        assert datalake.list_collections() == []
        assert isinstance(datalake.update_collection("collection_1", status="archived"), Collection)
        datalake.delete_collection("collection_1")
        assert isinstance(
            datalake.create_collection_item(collection_id="collection_1", asset_id="asset_1"),
            CollectionItem,
        )
        assert isinstance(datalake.get_collection_item("collection_item_1"), CollectionItem)
        assert datalake.list_collection_items() == []
        assert isinstance(datalake.resolve_collection_item("collection_item_1"), ResolvedCollectionItem)
        assert isinstance(datalake.update_collection_item("collection_item_1", status="hidden"), CollectionItem)
        datalake.delete_collection_item("collection_item_1")
        assert isinstance(
            datalake.create_asset_retention(asset_id="asset_1", owner_type="manual_pin", owner_id="owner_1"),
            AssetRetention,
        )
        assert isinstance(datalake.get_asset_retention("asset_retention_1"), AssetRetention)
        assert datalake.list_asset_retentions() == []
        assert isinstance(
            datalake.update_asset_retention("asset_retention_1", retention_policy="archive_when_unreferenced"),
            AssetRetention,
        )
        datalake.delete_asset_retention("asset_retention_1")
        assert isinstance(
            datalake.create_annotation_schema(
                name="demo-schema",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[{"name": "cat"}],
            ),
            AnnotationSchema,
        )
        assert isinstance(datalake.get_annotation_schema("schema_1"), AnnotationSchema)
        assert isinstance(datalake.get_annotation_schema_by_name_version("demo-schema", "1.0.0"), AnnotationSchema)
        assert datalake.list_annotation_schemas() == []
        assert isinstance(datalake.update_annotation_schema("schema_1", allow_scores=True), AnnotationSchema)
        datalake.delete_annotation_schema("schema_1")
        assert isinstance(
            datalake.create_annotation_set(name="gt", purpose="ground_truth", source_type="human"), AnnotationSet
        )
        assert isinstance(datalake.get_annotation_set("set_1"), AnnotationSet)
        assert datalake.list_annotation_sets() == []
        assert isinstance(datalake.update_annotation_set("set_1", status="active"), AnnotationSet)
        assert datalake.add_annotation_records("set_1", []) == []
        assert isinstance(datalake.get_annotation_record("ann_1"), AnnotationRecord)
        assert datalake.list_annotation_records() == []
        assert isinstance(datalake.update_annotation_record("ann_1", label="dent"), AnnotationRecord)
        datalake.delete_annotation_record("ann_1")
        assert isinstance(datalake.create_datum(asset_refs={"image": "asset_1"}), Datum)
        assert isinstance(datalake.get_datum("datum_1"), Datum)
        assert datalake.list_datums() == []
        assert isinstance(datalake.update_datum("datum_1", split="train"), Datum)
        assert isinstance(
            datalake.create_dataset_version(dataset_name="demo", version="0.1.0", manifest=[]), DatasetVersion
        )
        assert isinstance(datalake.get_dataset_version("demo", "0.1.0"), DatasetVersion)
        assert datalake.list_dataset_versions() == []
        assert isinstance(datalake.resolve_datum("datum_1"), ResolvedDatum)
        assert isinstance(datalake.resolve_dataset_version("demo", "0.1.0"), ResolvedDatasetVersion)
        assert isinstance(
            datalake.create_asset_from_object(name="hopper.png", obj=b"bytes", kind="image", media_type="image/png"),
            Asset,
        )
        mock_backend.initialize.assert_awaited_once()

    def test_summary_rewrites_async_prefix(self, datalake, mock_backend):
        mock_backend.summary = AsyncMock(
            return_value=(
                "AsyncDatalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
                "asset_retentions=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
            )
        )

        assert datalake.summary() == (
            "Datalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
            "asset_retentions=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
        )

    def test_close_handles_cleanup_exceptions_and_context_manager(self, datalake):
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
