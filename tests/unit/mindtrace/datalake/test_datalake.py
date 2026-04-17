import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.datalake import Datalake
from mindtrace.datalake.async_datalake import SlowOpsPolicy
from mindtrace.datalake.pagination_types import CursorPage, DatasetViewInfo, DatasetViewPage, DatasetViewRow, PageInfo
from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    AssetAlias,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    DirectUploadSession,
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
        backend.slow_ops_policy = SlowOpsPolicy.FORBID
        loop = asyncio.new_event_loop()
        try:
            datalake = Datalake(async_datalake=backend, loop=loop, mongo_db_uri="ignored", mongo_db_name="ignored")
            assert datalake._backend is backend
            assert datalake._loop is loop
            assert datalake.store is backend.store
            assert datalake.mongo_db_uri == "mongodb://test:27017"
            assert datalake.mongo_db_name == "test_db"
            assert datalake.slow_ops_policy == SlowOpsPolicy.FORBID
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
            slow_ops_policy=SlowOpsPolicy.WARN,
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
        upload_session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="hopper.png",
            mount="temp",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=datetime.now(timezone.utc),
        )
        for name, value in {
            "initialize": None,
            "get_health": {"status": "ok", "database": "test_db", "default_mount": "temp"},
            "put_object": StorageRef(mount="temp", name="hopper.png", version="v1"),
            "get_object": b"payload",
            "head_object": {"size": 123},
            "copy_object": StorageRef(mount="archive", name="hopper.png", version="v2"),
            "create_object_upload_session": upload_session,
            "get_object_upload_session": upload_session,
            "complete_object_upload_session": upload_session.model_copy(update={"status": "completed"}),
            "reconcile_upload_sessions": [upload_session.model_copy(update={"status": "completed"})],
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
                asset=Asset(
                    kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")
                ),
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
            "list_annotation_records_for_asset": [],
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
            "ensure_primary_asset_alias": AssetAlias.model_construct(
                alias_id="alias_row",
                alias="asset_1",
                asset_id="asset_1",
                is_primary=True,
                created_at=datetime.now(timezone.utc),
            ),
            "resolve_alias": "resolved_asset_id",
            "add_alias": AssetAlias.model_construct(
                alias_id="alias_row2",
                alias="nick",
                asset_id="asset_1",
                is_primary=False,
                created_at=datetime.now(timezone.utc),
            ),
            "remove_alias": None,
            "list_aliases_for_asset": ["asset_1", "nick"],
            "get_asset_by_alias": Asset(
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

    def test_sync_alias_methods_delegate_to_async_backend(self, datalake, mock_backend):
        asset = Asset(
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="hopper.png"),
            asset_id="asset_1",
        )
        datalake.ensure_primary_asset_alias(asset)
        mock_backend.ensure_primary_asset_alias.assert_awaited_once_with(asset)

        assert datalake.resolve_alias("nick") == "resolved_asset_id"
        mock_backend.resolve_alias.assert_awaited_once_with("nick")

        datalake.add_alias("asset_1", "nick")
        mock_backend.add_alias.assert_awaited_once_with("asset_1", "nick")

        datalake.remove_alias("nick")
        mock_backend.remove_alias.assert_awaited_once_with("nick")

        assert datalake.list_aliases_for_asset("asset_1") == ["asset_1", "nick"]
        mock_backend.list_aliases_for_asset.assert_awaited_once_with("asset_1")

        got = datalake.get_asset_by_alias("nick")
        assert got.kind == "image"
        mock_backend.get_asset_by_alias.assert_awaited_once_with("nick")

    def test_sync_facade_basic_methods(self, datalake, mock_backend):
        mock_backend.summary = AsyncMock(
            return_value=(
                "Datalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
                "asset_retentions=0, annotation_schemas=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
            )
        )
        datalake.initialize()
        assert datalake.get_health()["status"] == "ok"
        assert datalake.summary() == (
            "Datalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
            "asset_retentions=0, annotation_schemas=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
        )
        assert str(datalake) == (
            "Datalake(database=test_db, default_mount=temp, assets=0, collections=0, collection_items=0, "
            "asset_retentions=0, annotation_schemas=0, annotation_sets=0, annotation_records=0, datums=0, dataset_versions=0)"
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
        assert datalake.create_object_upload_session(name="hopper.png").upload_session_id == "upload_session_1"
        assert datalake.get_object_upload_session("upload_session_1").finalize_token == "token-1"
        assert (
            datalake.complete_object_upload_session("upload_session_1", finalize_token="token-1").status == "completed"
        )
        assert datalake.reconcile_upload_sessions()[0].status == "completed"
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
        assert datalake.add_annotation_records([], annotation_set_id="set_1") == []
        assert datalake.list_annotation_records_for_asset("asset_1") == []
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
        assert isinstance(
            datalake.create_asset_from_uploaded_object(
                kind="image",
                media_type="image/png",
                storage_ref=StorageRef(mount="temp", name="hopper.png"),
            ),
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

    def test_sync_pagination_methods_delegate_to_async_backend(self, datalake, mock_backend):
        asset_page = CursorPage(
            items=[Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png"))],
            page=PageInfo(limit=1, next_cursor="asset-cursor", has_more=True, total_count=2),
        )
        collection_page = CursorPage(items=[Collection(name="demo")], page=PageInfo(limit=1, next_cursor=None, has_more=False))
        collection_item_page = CursorPage(
            items=[CollectionItem(collection_id="collection_1", asset_id="asset_1")],
            page=PageInfo(limit=1, next_cursor=None, has_more=False),
        )
        retention_page = CursorPage(
            items=[AssetRetention(asset_id="asset_1", owner_type="manual_pin", owner_id="owner_1")],
            page=PageInfo(limit=1, next_cursor=None, has_more=False),
        )
        annotation_schema_page = CursorPage(
            items=[
                AnnotationSchema(
                    name="demo-schema",
                    version="1.0.0",
                    task_type="classification",
                    allowed_annotation_kinds=["classification"],
                    labels=[AnnotationLabelDefinition(name="cat")],
                )
            ],
            page=PageInfo(limit=1, next_cursor=None, has_more=False),
        )
        annotation_set_page = CursorPage(
            items=[AnnotationSet(name="gt", purpose="ground_truth", source_type="human")],
            page=PageInfo(limit=1, next_cursor=None, has_more=False),
        )
        annotation_record_page = CursorPage(
            items=[AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})],
            page=PageInfo(limit=1, next_cursor=None, has_more=False),
        )
        datum_page = CursorPage(
            items=[Datum(asset_refs={"image": "asset_1"})],
            page=PageInfo(limit=1, next_cursor=None, has_more=False),
        )
        dataset_page = CursorPage(
            items=[DatasetVersion(dataset_name="demo", version="0.1.0")],
            page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1),
        )
        view_page = DatasetViewPage(
            items=[DatasetViewRow(datum_id="datum_1", split="train", metadata={"rank": 1})],
            page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1),
            view=DatasetViewInfo(dataset_name="demo", version="0.1.0", sort="manifest_order"),
        )
        mock_backend.list_assets_page = AsyncMock(return_value=asset_page)
        mock_backend.list_collections_page = AsyncMock(return_value=collection_page)
        mock_backend.list_collection_items_page = AsyncMock(return_value=collection_item_page)
        mock_backend.list_asset_retentions_page = AsyncMock(return_value=retention_page)
        mock_backend.list_annotation_schemas_page = AsyncMock(return_value=annotation_schema_page)
        mock_backend.list_annotation_sets_page = AsyncMock(return_value=annotation_set_page)
        mock_backend.list_annotation_records_page = AsyncMock(return_value=annotation_record_page)
        mock_backend.list_annotation_records_for_asset_page = AsyncMock(return_value=annotation_record_page)
        mock_backend.list_datums_page = AsyncMock(return_value=datum_page)
        mock_backend.list_dataset_versions_page = AsyncMock(return_value=dataset_page)
        mock_backend.view_dataset_version_page = AsyncMock(return_value=view_page)

        assert datalake.list_assets_page(filters={"kind": "image"}, limit=1).page.next_cursor == "asset-cursor"
        assert datalake.list_collections_page(limit=1).items[0].name == "demo"
        assert datalake.list_collection_items_page(limit=1).items[0].collection_id == "collection_1"
        assert datalake.list_asset_retentions_page(limit=1).items[0].owner_id == "owner_1"
        assert datalake.list_annotation_schemas_page(limit=1).items[0].name == "demo-schema"
        assert datalake.list_annotation_sets_page(limit=1).items[0].name == "gt"
        assert datalake.list_annotation_records_page(limit=1).items[0].label == "dent"
        assert datalake.list_annotation_records_for_asset_page("asset_1", limit=1).items[0].label == "dent"
        assert datalake.list_datums_page(limit=1).items[0].asset_refs == {"image": "asset_1"}
        assert datalake.list_dataset_versions_page(dataset_name="demo", limit=1).items[0].dataset_name == "demo"
        assert datalake.view_dataset_version_page("demo", "0.1.0", limit=1).view.sort == "manifest_order"

    def test_sync_iterator_methods_stream_without_submit_coro(self, datalake, mock_backend):
        asset = Asset(
            asset_id="asset_1",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="asset_1.png"),
        )
        annotation_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={},
        )
        datum = Datum(datum_id="datum_1", asset_refs={"image": "asset_1"})

        mock_backend.asset_database = MagicMock()
        mock_backend.asset_database.find_iter_sync = MagicMock(return_value=iter([asset]))
        mock_backend.annotation_record_database = MagicMock()
        mock_backend.annotation_record_database.find_iter_sync = MagicMock(return_value=iter([annotation_record]))
        mock_backend.datum_database = MagicMock()
        mock_backend.datum_database.find_iter_sync = MagicMock(return_value=iter([datum]))

        datalake._submit_coro = MagicMock(side_effect=AssertionError("unexpected async bridge"))

        assert list(datalake.iter_assets(filters={"kind": "image"}, batch_size=10)) == [asset]
        assert list(datalake.iter_annotation_records(filters={"label": "dent"}, batch_size=20)) == [annotation_record]
        assert list(datalake.iter_datums(filters={"split": "train"}, batch_size=30)) == [datum]

        mock_backend.asset_database.find_iter_sync.assert_called_once_with(
            {"kind": "image"},
            sort=[("created_at", -1), ("asset_id", -1)],
            batch_size=10,
        )
        mock_backend.annotation_record_database.find_iter_sync.assert_called_once_with(
            {"label": "dent"},
            sort=[("created_at", -1), ("annotation_id", -1)],
            batch_size=20,
        )
        mock_backend.datum_database.find_iter_sync.assert_called_once_with(
            {"split": "train"},
            sort=[("created_at", -1), ("datum_id", -1)],
            batch_size=30,
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
