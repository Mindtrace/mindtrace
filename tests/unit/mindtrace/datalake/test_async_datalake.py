import asyncio
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError
from mindtrace.datalake import AsyncDatalake
from mindtrace.datalake.async_datalake import (
    AnnotationSchemaInUseError,
    AnnotationSchemaValidationError,
    DuplicateAnnotationSchemaError,
    SlowOperationDisabledError,
    SlowOperationWarning,
    SlowOpsPolicy,
)
from mindtrace.datalake.pagination_types import (
    MAX_PAGE_LIMIT,
    CursorEnvelope,
    DatasetViewExpand,
    DatasetViewRow,
    PageInfo,
    StructuredFilter,
)
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
    DirectUploadSession,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)
from mindtrace.registry.core.exceptions import RegistryObjectNotFound


class TestAsyncDatalakeUnit:
    @staticmethod
    def _async_iterable(items):
        async def generator():
            for item in items:
                yield item

        return generator()

    @staticmethod
    def _patch_datum_find_for_annotation_set_merge(mock_odm, annotation_set_id: str, *, image_asset_id: str) -> None:
        """Return a linked Datum when AsyncDatalake looks up datums by ``annotation_set_ids``."""

        async def find_side_effect(query=None):
            q = query or {}
            if q.get("annotation_set_ids") == annotation_set_id:
                return [
                    Datum(
                        datum_id="datum_merge",
                        asset_refs={"image": image_asset_id},
                        annotation_set_ids=[annotation_set_id],
                    )
                ]
            return []

        mock_odm.find = AsyncMock(side_effect=find_side_effect)

    def test_default_datalake_store_path_uses_cache_directory(self):
        from mindtrace.datalake.async_datalake import _default_datalake_store_path

        path = _default_datalake_store_path("mongodb://example:27017", "demo")

        assert path == Path("~/.cache/mindtrace/temp").expanduser() / f"datalake-{path.name.split('datalake-')[1]}"
        assert path.parent == Path("~/.cache/mindtrace/temp").expanduser()
        assert path.name.startswith("datalake-")

    @pytest.fixture
    def mock_odm(self):
        mock = AsyncMock()
        mock.initialize = AsyncMock()
        mock.insert = AsyncMock(side_effect=lambda obj: obj)
        mock.find = AsyncMock(return_value=[])
        mock.find_iter = AsyncMock()
        mock.find_window = AsyncMock(return_value=[])
        mock.count_documents = AsyncMock(return_value=0)
        mock.update = AsyncMock(side_effect=lambda obj: obj)
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.default_mount = "temp"
        store.list_mount_info.return_value = {
            "temp": {
                "read_only": False,
                "backend": "file:///tmp/mindtrace-store-test",
                "version_objects": False,
                "mutable": True,
                "version_digits": 6,
            }
        }
        store.build_key.side_effect = lambda mount, name, version=None: (
            f"{mount}/{name}" if version is None else f"{mount}/{name}@{version}"
        )
        store.save.return_value = "v1"
        store.copy.return_value = "v2"
        store.load.return_value = b"payload"
        store.info.return_value = {"size": 123}
        store.has_object.return_value = True
        store.create_direct_upload_target.return_value = {
            "upload_method": "local_path",
            "upload_url": None,
            "upload_path": "/tmp/direct-upload/data.txt",
            "upload_headers": {},
            "staged_target": {"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
        }
        store.inspect_direct_upload_target.return_value = {"exists": True, "size_bytes": 7}
        store.commit_direct_upload.return_value = "v5"
        store.cleanup_direct_upload_target.return_value = True
        return store

    @pytest.fixture
    def async_datalake(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            return AsyncDatalake(
                "mongodb://test:27017",
                "test_db",
                store=mock_store,
                slow_ops_policy=SlowOpsPolicy.ALLOW,
            )

    def test_init_raises_when_store_and_mounts_both_provided(self, mock_store):
        with pytest.raises(ValueError, match="Provide either store or mounts, not both"):
            AsyncDatalake("mongodb://test:27017", "test_db", store=mock_store, mounts=[MagicMock()])

    def test_init_builds_store_from_mounts(self, mock_odm):
        fake_store = MagicMock()
        with (
            patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm),
            patch("mindtrace.datalake.async_datalake.Store.from_mounts", return_value=fake_store) as from_mounts,
        ):
            datalake = AsyncDatalake("mongodb://test:27017", "test_db", mounts=[MagicMock()], default_mount="nas")
        assert datalake.store == fake_store
        from_mounts.assert_called_once()

    def test_init_builds_default_cache_backed_store_when_not_provided(self, mock_odm):
        fake_store = MagicMock()
        fake_path = MagicMock()
        with (
            patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm),
            patch(
                "mindtrace.datalake.async_datalake._default_datalake_store_path", return_value=fake_path
            ) as default_path,
            patch("mindtrace.datalake.async_datalake.Store.from_mounts", return_value=fake_store) as from_mounts,
        ):
            datalake = AsyncDatalake("mongodb://test:27017", "test_db", default_mount="nas")
        assert datalake.store == fake_store
        default_path.assert_called_once_with("mongodb://test:27017", "test_db")
        fake_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        from_mounts.assert_called_once()
        mounts = from_mounts.call_args.args[0]
        assert len(mounts) == 1
        assert mounts[0].name == "nas"
        assert from_mounts.call_args.kwargs["default_mount"] == "nas"

    @pytest.mark.asyncio
    async def test_initialize_initializes_all_odms(self, async_datalake, mock_odm):
        await async_datalake.initialize()
        assert mock_odm.initialize.await_count == 11

    @pytest.mark.asyncio
    async def test_create_classmethod_initializes_instance(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            created = await AsyncDatalake.create("mongodb://test:27017", "test_db", store=mock_store)
        assert isinstance(created, AsyncDatalake)
        assert created.store == mock_store
        assert mock_odm.initialize.await_count == 11

    def test_init_defaults_slow_ops_policy_to_warn(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            datalake = AsyncDatalake("mongodb://test:27017", "test_db", store=mock_store)

        assert datalake.slow_ops_policy == SlowOpsPolicy.WARN

    @pytest.mark.asyncio
    async def test_guard_slow_list_operation_warns_or_forbids(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            warn_datalake = AsyncDatalake(
                "mongodb://test:27017",
                "test_db",
                store=mock_store,
                slow_ops_policy=SlowOpsPolicy.WARN,
            )
            forbid_datalake = AsyncDatalake(
                "mongodb://test:27017",
                "test_db",
                store=mock_store,
                slow_ops_policy=SlowOpsPolicy.FORBID,
            )

        with pytest.warns(SlowOperationWarning, match="list_assets\\(\\).*iter_assets\\(\\) or list_assets_page\\(\\)"):
            assert await warn_datalake.list_assets() == []

        with pytest.raises(SlowOperationDisabledError, match="list_assets\\(\\).*iter_assets\\(\\) or list_assets_page\\(\\)"):
            await forbid_datalake.list_assets()

    @pytest.mark.asyncio
    async def test_resolve_dataset_version_is_not_guarded_by_slow_ops_policy(self, async_datalake):
        dataset_version = DatasetVersion(dataset_name="demo", version="v1", manifest=["datum_1"])
        resolved_datum = ResolvedDatum(datum=Datum(), assets={}, annotation_sets=[], annotation_records={})
        async_datalake.get_dataset_version = AsyncMock(return_value=dataset_version)
        async_datalake.resolve_datum = AsyncMock(return_value=resolved_datum)
        async_datalake._guard_slow_list_operation = MagicMock(side_effect=AssertionError("unexpected guard"))

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            resolved = await async_datalake.resolve_dataset_version("demo", "v1")

        assert resolved == ResolvedDatasetVersion(dataset_version=dataset_version, datums=[resolved_datum])
        assert caught == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "args", "kwargs"),
        [
            ("list_assets", (), {}),
            ("list_collections", (), {}),
            ("list_collection_items", (), {}),
            ("list_asset_retentions", (), {}),
            ("list_annotation_schemas", (), {}),
            ("list_annotation_sets", (), {}),
            ("list_annotation_records_for_asset", ("asset_123",), {}),
            ("list_annotation_records", (), {}),
            ("list_datums", (), {}),
            ("list_dataset_versions", (), {}),
        ],
    )
    async def test_eager_list_methods_invoke_slow_op_guard(self, async_datalake, method_name, args, kwargs):
        async_datalake._guard_slow_list_operation = MagicMock()

        await getattr(async_datalake, method_name)(*args, **kwargs)

        async_datalake._guard_slow_list_operation.assert_called()

    def test_utc_now_returns_timezone_aware_datetime(self, async_datalake):
        now = async_datalake._utc_now()
        assert now.tzinfo is not None

    def test_coerce_utc_attaches_timezone_to_naive_datetime(self, async_datalake):
        naive = datetime(2026, 1, 1, 12, 0, 0)

        coerced = async_datalake._coerce_utc(naive)

        assert coerced.tzinfo is not None

    def test_build_document_uses_model_construct(self, async_datalake):
        class Dummy:
            @classmethod
            def model_construct(cls, **data):
                return data

        assert async_datalake._build_document(Dummy, a=1) == {"a": 1}

    @pytest.mark.asyncio
    async def test_get_health_returns_expected_payload(self, async_datalake):
        health = await async_datalake.get_health()
        assert health == {"status": "ok", "database": "test_db", "default_mount": "temp"}
        assert str(async_datalake) == "AsyncDatalake(database=test_db, default_mount=temp)"

    @pytest.mark.asyncio
    async def test_summary_returns_counts(self, async_datalake, mock_odm):
        mock_odm.count_documents = AsyncMock(side_effect=[2, 1, 3, 1, 2, 1, 3, 1, 0])

        summary = await async_datalake.summary()

        assert summary == (
            "AsyncDatalake(database=test_db, default_mount=temp, assets=2, collections=1, collection_items=3, "
            "asset_retentions=1, annotation_schemas=2, annotation_sets=1, annotation_records=3, datums=1, dataset_versions=0)"
        )

    def test_cursor_encode_and_decode_round_trip(self, async_datalake):
        envelope = CursorEnvelope(
            resource="assets",
            sort="created_desc",
            filter_fingerprint=async_datalake._cursor_filter_fingerprint({"kind": "image"}),
            last_key={
                "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                "asset_id": "asset_1",
            },
        )
        cursor = async_datalake._encode_cursor(envelope)

        decoded = async_datalake._decode_cursor(
            cursor,
            expected_resource="assets",
            expected_sort="created_desc",
            expected_filters={"kind": "image"},
        )

        assert decoded == envelope

        with pytest.raises(ValueError, match="Cursor filters do not match this request"):
            async_datalake._decode_cursor(
                cursor,
                expected_resource="assets",
                expected_sort="created_desc",
                expected_filters={"kind": "video"},
            )

    def test_cursor_decode_rejects_resource_and_sort_mismatches(self, async_datalake):
        cursor = async_datalake._encode_cursor(
            CursorEnvelope(
                resource="assets",
                sort="created_desc",
                filter_fingerprint=async_datalake._cursor_filter_fingerprint({"kind": "image"}),
                last_key={"asset_id": "asset_1"},
            )
        )

        with pytest.raises(ValueError, match="Cursor resource mismatch"):
            async_datalake._decode_cursor(
                cursor,
                expected_resource="collections",
                expected_sort="created_desc",
                expected_filters={"kind": "image"},
            )

        with pytest.raises(ValueError, match="Cursor sort mismatch"):
            async_datalake._decode_cursor(
                cursor,
                expected_resource="assets",
                expected_sort="created_asc",
                expected_filters={"kind": "image"},
            )

    def test_pagination_helper_branches(self, async_datalake):
        class Dumpable:
            def model_dump(self, mode="json"):
                assert mode == "json"
                return {"kind": "image"}

        assert async_datalake._cursor_filter_fingerprint(Dumpable()) == async_datalake._cursor_filter_fingerprint(
            {"kind": "image"}
        )
        assert async_datalake._get_value_by_path({"a": {"b": 1}}, "a.b") == 1
        assert async_datalake._get_value_by_path({"a": {}}, "a.b") is None
        assert async_datalake._merge_query({}, {"x": 1}) == {"x": 1}
        assert async_datalake._merge_query({"x": 1}, {}) == {"x": 1}
        snapshot_token = async_datalake._encode_snapshot_token(
            resource="assets",
            field="created_at",
            cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert async_datalake._decode_snapshot_token(snapshot_token, expected_resource="assets") == (
            "created_at",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert async_datalake._build_snapshot_query(resource="assets", snapshot_token=snapshot_token) == {
            "created_at": {"$lte": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        }
        assert async_datalake._decode_snapshot_token(None, expected_resource="assets") is None
        assert async_datalake._build_snapshot_query(resource="assets", snapshot_token=None) == {}
        assert async_datalake._snapshot_field_for("missing") is None

        with pytest.raises(ValueError, match="Unsupported pagination resource"):
            async_datalake._sort_specs_for("missing")
        with pytest.raises(ValueError, match="Unsupported sort"):
            async_datalake._resolve_sort_spec("assets", "missing")
        with pytest.raises(ValueError, match="Invalid snapshot token"):
            async_datalake._decode_snapshot_token("not-json", expected_resource="assets")
        with pytest.raises(ValueError, match="Snapshot token resource mismatch"):
            async_datalake._decode_snapshot_token(
                async_datalake._encode_snapshot_token(
                    resource="collections",
                    field="created_at",
                    cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
                expected_resource="assets",
            )
        with pytest.raises(ValueError, match="Unsupported snapshot token kind"):
            async_datalake._decode_snapshot_token(
                json.dumps({"kind": "other", "resource": "assets", "field": "created_at", "cutoff": "x"}),
                expected_resource="assets",
            )
        with pytest.raises(ValueError, match="Snapshot token missing field"):
            async_datalake._decode_snapshot_token(
                json.dumps({"kind": "temporal_cutoff", "resource": "assets", "field": "", "cutoff": "x"}),
                expected_resource="assets",
            )
        with pytest.raises(ValueError, match="Snapshot token field mismatch for resource"):
            async_datalake._build_snapshot_query(
                resource="assets",
                snapshot_token=async_datalake._encode_snapshot_token(
                    resource="assets",
                    field="updated_at",
                    cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
            )

    @pytest.mark.parametrize(
        ("filter_item", "item", "expected"),
        [
            pytest.param(StructuredFilter(field="kind", op="eq", value="image"), {"kind": "image"}, True, id="eq"),
            pytest.param(StructuredFilter(field="kind", op="ne", value="video"), {"kind": "image"}, True, id="ne"),
            pytest.param(StructuredFilter(field="score", op="gt", value=2), {"score": 3}, True, id="gt"),
            pytest.param(StructuredFilter(field="score", op="gte", value=3), {"score": 3}, True, id="gte"),
            pytest.param(StructuredFilter(field="score", op="lt", value=5), {"score": 3}, True, id="lt"),
            pytest.param(StructuredFilter(field="score", op="lte", value=3), {"score": 3}, True, id="lte"),
            pytest.param(StructuredFilter(field="tag", op="in", value=["a", "b"]), {"tag": "a"}, True, id="in"),
            pytest.param(
                StructuredFilter(field="name", op="contains", value="hop"),
                {"name": "hopper"},
                True,
                id="contains-str",
            ),
            pytest.param(
                StructuredFilter(field="tags", op="contains", value="blue"),
                {"tags": ["blue", "green"]},
                True,
                id="contains-list",
            ),
            pytest.param(StructuredFilter(field="kind", op="exists", value=True), {"kind": "image"}, True, id="exists"),
            pytest.param(StructuredFilter(field="kind", op="eq", value="video"), {"kind": "image"}, False, id="eq-false"),
            pytest.param(StructuredFilter(field="kind", op="ne", value="image"), {"kind": "image"}, False, id="ne-false"),
            pytest.param(StructuredFilter(field="score", op="gt", value=3), {"score": 3}, False, id="gt-false"),
            pytest.param(StructuredFilter(field="score", op="gte", value=4), {"score": 3}, False, id="gte-false"),
            pytest.param(StructuredFilter(field="score", op="lt", value=3), {"score": 3}, False, id="lt-false"),
            pytest.param(StructuredFilter(field="score", op="lte", value=2), {"score": 3}, False, id="lte-false"),
            pytest.param(
                StructuredFilter(field="tag", op="in", value=["b", "c"]),
                {"tag": "a"},
                False,
                id="in-false",
            ),
            pytest.param(
                StructuredFilter(field="name", op="contains", value="dog"),
                {"name": "hopper"},
                False,
                id="contains-str-false",
            ),
            pytest.param(
                StructuredFilter(field="tags", op="contains", value="dog"),
                {"tags": ["blue", "green"]},
                False,
                id="contains-list-false",
            ),
            pytest.param(
                StructuredFilter(field="meta", op="contains", value="x"),
                {"meta": {"x": 1}},
                False,
                id="contains-unsupported",
            ),
            pytest.param(
                StructuredFilter(field="kind", op="exists", value=False),
                {"kind": "image"},
                False,
                id="exists-false",
            ),
        ],
    )
    def test_matches_structured_filters_variants(self, async_datalake, filter_item, item, expected):
        assert async_datalake._matches_structured_filters(item, [filter_item]) is expected

    def test_matches_structured_filters_accepts_empty_filters(self, async_datalake):
        assert async_datalake._matches_structured_filters({"kind": "image"}, []) is True

    @pytest.mark.asyncio
    async def test_list_assets_page_builds_and_consumes_cursor(self, async_datalake, mock_odm):
        asset_1 = Asset(
            asset_id="asset_1",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="asset-1.png"),
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        asset_2 = Asset(
            asset_id="asset_2",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="asset-2.png"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        cutoff = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)

        async def find_window_side_effect(query, *, sort=None, limit=None):
            assert sort == [("created_at", -1), ("asset_id", -1)]
            assert limit == 2
            snapshot_query = {"created_at": {"$lte": cutoff}}
            if "$and" in query.get("$and", [{}])[0]:
                assert snapshot_query == query["$and"][1]
                assert query["$and"][0]["$and"][0] == {"kind": "image"}
                assert "$or" in query["$and"][0]["$and"][1]
                return [asset_2]
            assert snapshot_query in query["$and"]
            return [asset_1, asset_2]

        mock_odm.find_window = AsyncMock(side_effect=find_window_side_effect)
        mock_odm.count_documents = AsyncMock(return_value=2)

        with patch.object(async_datalake, "_utc_now", return_value=cutoff):
            first_page = await async_datalake.list_assets_page(
                filters={"kind": "image"},
                limit=1,
                include_total=True,
            )

        assert [asset.asset_id for asset in first_page.items] == ["asset_1"]
        assert first_page.page.has_more is True
        assert first_page.page.total_count == 2
        assert first_page.page.next_cursor is not None

        decoded = async_datalake._decode_cursor(
            first_page.page.next_cursor,
            expected_resource="assets",
            expected_sort="created_desc",
            expected_filters={"kind": "image"},
        )
        assert decoded.last_key["asset_id"] == "asset_1"
        assert decoded.last_key["created_at"] == asset_1.created_at
        assert decoded.snapshot_token is not None

        second_page = await async_datalake.list_assets_page(
            filters={"kind": "image"},
            limit=1,
            cursor=first_page.page.next_cursor,
        )

        assert [asset.asset_id for asset in second_page.items] == ["asset_2"]
        assert second_page.page.has_more is False
        second_query = mock_odm.find_window.await_args_list[1].args[0]
        assert second_query["$and"][0]["$and"][0] == {"kind": "image"}
        assert "$or" in second_query["$and"][0]["$and"][1]
        count_query = mock_odm.count_documents.await_args.args[0]
        assert {"created_at": {"$lte": cutoff}} in count_query["$and"]

    @pytest.mark.asyncio
    async def test_list_assets_page_rejects_invalid_snapshot_token(self, async_datalake, mock_odm):
        asset_1 = Asset(
            asset_id="asset_1",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="asset-1.png"),
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        asset_2 = Asset(
            asset_id="asset_2",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="asset-2.png"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        mock_odm.find_window = AsyncMock(return_value=[asset_1, asset_2])

        page = await async_datalake.list_assets_page(filters={"kind": "image"}, limit=1)
        envelope = async_datalake._decode_cursor(
            page.page.next_cursor,
            expected_resource="assets",
            expected_sort="created_desc",
            expected_filters={"kind": "image"},
        )
        bad_cursor = async_datalake._encode_cursor(envelope.model_copy(update={"snapshot_token": "not-json"}))

        with pytest.raises(ValueError, match="Invalid snapshot token"):
            await async_datalake.list_assets_page(
                filters={"kind": "image"},
                limit=1,
                cursor=bad_cursor,
            )

    @pytest.mark.asyncio
    async def test_list_assets_page_rejects_invalid_page_limits_before_query(self, async_datalake, mock_odm):
        with pytest.raises(ValueError, match=f"between 1 and {MAX_PAGE_LIMIT}"):
            await async_datalake.list_assets_page(limit=0)

        with pytest.raises(ValueError, match=f"between 1 and {MAX_PAGE_LIMIT}"):
            await async_datalake.list_assets_page(limit=MAX_PAGE_LIMIT + 1)

        mock_odm.find_window.assert_not_awaited()
        mock_odm.count_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_iter_assets_uses_lazy_database_iterator(self, async_datalake, mock_odm):
        asset_1 = Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="a.png"))
        asset_2 = Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="b.png"))
        captured: dict[str, object] = {}

        def find_iter(query, *, sort=None, batch_size=None):
            captured["query"] = query
            captured["sort"] = sort
            captured["batch_size"] = batch_size

            async def generator():
                yield asset_1
                yield asset_2

            return generator()

        mock_odm.find_iter = find_iter

        results = [asset async for asset in async_datalake.iter_assets(filters={"kind": "image"}, batch_size=25)]

        assert results == [asset_1, asset_2]
        assert captured["query"] == {"kind": "image"}
        assert captured["sort"] == [("created_at", -1), ("asset_id", -1)]
        assert captured["batch_size"] == 25

    @pytest.mark.asyncio
    async def test_page_and_iterator_wrappers_delegate_to_generic_helpers(self, async_datalake):
        async_datalake._paginate_database = AsyncMock(return_value="page")

        async def iter_records(*, database, resource, filters, sort, batch_size):
            assert resource in {"annotation_records", "datums"}
            assert sort == "created_desc"
            assert batch_size == 11
            yield resource

        async_datalake._iter_database = iter_records

        assert (
            await async_datalake.list_collections_page(filters={"status": "active"}, limit=5, include_total=True) == "page"
        )
        assert await async_datalake.list_collection_items_page(filters={"collection_id": "c1"}) == "page"
        assert await async_datalake.list_asset_retentions_page(filters={"asset_id": "a1"}) == "page"
        assert await async_datalake.list_annotation_schemas_page(filters={"task_type": "detection"}) == "page"
        assert await async_datalake.list_annotation_sets_page(filters={"purpose": "ground_truth"}) == "page"
        assert await async_datalake.list_annotation_records_page(filters={"label": "dent"}) == "page"
        assert await async_datalake.list_annotation_records_for_asset_page("asset_1") == "page"
        assert await async_datalake.list_datums_page(filters={"split": "train"}) == "page"
        assert await async_datalake.list_dataset_versions_page(dataset_name="demo", filters={"version": "1.0.0"}) == "page"

        annotation_records = [
            record
            async for record in async_datalake.iter_annotation_records(filters={"label": "dent"}, batch_size=11)
        ]
        datums = [datum async for datum in async_datalake.iter_datums(filters={"split": "train"}, batch_size=11)]

        assert annotation_records == ["annotation_records"]
        assert datums == ["datums"]
        assert async_datalake._paginate_database.await_count == 9

        dataset_call = async_datalake._paginate_database.await_args_list[-1]
        assert dataset_call.kwargs["filters"] == {"version": "1.0.0", "dataset_name": "demo"}

        asset_call = async_datalake._paginate_database.await_args_list[6]
        assert asset_call.kwargs["resource"] == "annotation_records"
        assert asset_call.kwargs["filters"] == {"subject.kind": "asset", "subject.id": "asset_1"}

    @pytest.mark.asyncio
    async def test_view_dataset_version_page_paginates_manifest_rows(self, async_datalake):
        dataset_version = DatasetVersion(
            dataset_name="demo",
            version="1.0.0",
            manifest=["datum_1", "datum_2"],
        )
        datum_1 = Datum(
            datum_id="datum_1",
            asset_refs={"image": "asset_1"},
            split="train",
            metadata={"rank": 1},
        )
        datum_2 = Datum(
            datum_id="datum_2",
            asset_refs={"image": "asset_2"},
            split="train",
            metadata={"rank": 2},
        )
        asset_1 = Asset(
            asset_id="asset_1",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="asset-1.png"),
        )
        asset_2 = Asset(
            asset_id="asset_2",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="temp", name="asset-2.png"),
        )

        async_datalake.get_dataset_version = AsyncMock(return_value=dataset_version)
        async_datalake.datum_database = MagicMock()
        async_datalake.datum_database.find = AsyncMock(return_value=[datum_2, datum_1])
        async_datalake.asset_database = MagicMock()
        async_datalake.asset_database.find = AsyncMock(return_value=[asset_2, asset_1])

        filters = [StructuredFilter(field="split", op="eq", value="train")]
        first_page = await async_datalake.view_dataset_version_page(
            "demo",
            "1.0.0",
            limit=1,
            filters=filters,
            expand=DatasetViewExpand(assets=True, annotation_sets=False, annotation_records=False),
            include_total=True,
        )

        assert first_page.view.dataset_name == "demo"
        assert first_page.page.total_count == 2
        assert first_page.page.has_more is True
        assert first_page.items[0].datum_id == "datum_1"
        assert first_page.items[0].assets == {"image": asset_1}
        assert async_datalake.datum_database.find.await_count == 2
        async_datalake.asset_database.find.assert_awaited_once_with({"asset_id": {"$in": ["asset_1"]}})

        decoded = async_datalake._decode_cursor(
            first_page.page.next_cursor,
            expected_resource="dataset_version_view:demo:1.0.0",
            expected_sort="manifest_order",
            expected_filters=[f.model_dump(mode="json") for f in filters],
        )
        assert decoded.last_key == {"ordinal": 0, "datum_id": "datum_1"}

        second_page = await async_datalake.view_dataset_version_page(
            "demo",
            "1.0.0",
            limit=1,
            cursor=first_page.page.next_cursor,
            filters=filters,
            expand=DatasetViewExpand(assets=False, annotation_sets=False, annotation_records=False),
        )

        assert second_page.items[0].datum_id == "datum_2"
        assert second_page.items[0].assets is None
        assert second_page.page.has_more is False
        assert async_datalake.datum_database.find.await_count == 3

    @pytest.mark.asyncio
    async def test_view_dataset_version_page_supports_annotation_expansion_and_filter_skips(self, async_datalake):
        dataset_version = DatasetVersion(
            dataset_name="demo",
            version="1.0.0",
            manifest=["datum_skip", "datum_keep"],
        )
        skipped = Datum(datum_id="datum_skip", asset_refs={"image": "asset_skip"}, split="val")
        kept = Datum(
            datum_id="datum_keep",
            asset_refs={"image": "asset_keep"},
            split="train",
            annotation_set_ids=["set_1"],
        )
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set_1"
        annotation_set.annotation_record_ids = ["ann_1"]
        annotation_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={},
        )
        annotation_record.annotation_id = "ann_1"

        async_datalake.get_dataset_version = AsyncMock(return_value=dataset_version)
        async_datalake.datum_database = MagicMock()
        async_datalake.datum_database.find = AsyncMock(return_value=[kept, skipped])
        async_datalake.annotation_set_database = MagicMock()
        async_datalake.annotation_set_database.find = AsyncMock(return_value=[annotation_set])
        async_datalake.annotation_record_database = MagicMock()
        async_datalake.annotation_record_database.find = AsyncMock(return_value=[annotation_record])

        page = await async_datalake.view_dataset_version_page(
            "demo",
            "1.0.0",
            limit=5,
            filters=[StructuredFilter(field="split", op="eq", value="train")],
            expand=DatasetViewExpand(assets=False, annotation_sets=True, annotation_records=True),
            include_total=False,
        )

        assert [row.datum_id for row in page.items] == ["datum_keep"]
        assert page.items[0].annotation_sets == [annotation_set]
        assert page.items[0].annotation_records == {"set_1": [annotation_record]}
        assert page.page.total_count is None
        async_datalake.annotation_set_database.find.assert_awaited_once_with({"annotation_set_id": {"$in": ["set_1"]}})
        async_datalake.annotation_record_database.find.assert_awaited_once_with({"annotation_id": {"$in": ["ann_1"]}})

    @pytest.mark.asyncio
    async def test_build_dataset_view_rows_returns_empty_list_for_empty_input(self, async_datalake):
        assert await async_datalake._build_dataset_view_rows(
            datums=[],
            expand=DatasetViewExpand(assets=True, annotation_sets=True, annotation_records=True),
        ) == []

    @pytest.mark.asyncio
    async def test_view_dataset_version_page_scans_manifest_in_chunks_for_sparse_filters(self, async_datalake):
        skipped_datums = [
            Datum(datum_id=f"datum_skip_{index}", split="val")
            for index in range(100)
        ]
        kept_datum = Datum(datum_id="datum_keep", split="train", metadata={"rank": 101})
        manifest = [datum.datum_id for datum in skipped_datums] + [kept_datum.datum_id]
        dataset_version = DatasetVersion(dataset_name="demo", version="1.0.0", manifest=manifest)
        datums_by_id = {datum.datum_id: datum for datum in [*skipped_datums, kept_datum]}

        async_datalake.get_dataset_version = AsyncMock(return_value=dataset_version)
        async_datalake.datum_database = MagicMock()

        async def datum_find_side_effect(query):
            ids = query["datum_id"]["$in"]
            return [datums_by_id[datum_id] for datum_id in reversed(ids)]

        async_datalake.datum_database.find = AsyncMock(side_effect=datum_find_side_effect)

        page = await async_datalake.view_dataset_version_page(
            "demo",
            "1.0.0",
            limit=1,
            filters=[StructuredFilter(field="split", op="eq", value="train")],
        )

        assert [row.datum_id for row in page.items] == ["datum_keep"]
        assert page.page.has_more is False
        assert async_datalake.datum_database.find.await_count == 2

    @pytest.mark.asyncio
    async def test_view_dataset_version_page_rejects_unsupported_sort(self, async_datalake):
        with pytest.raises(ValueError, match="currently support only sort='manifest_order'"):
            await async_datalake.view_dataset_version_page("demo", "1.0.0", sort="created_desc")

    @pytest.mark.asyncio
    async def test_iter_dataset_version_view_walks_all_pages(self, async_datalake):
        first_page = MagicMock(
            items=[DatasetViewRow(datum_id="datum_1")],
            page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True, total_count=None),
        )
        second_page = MagicMock(
            items=[DatasetViewRow(datum_id="datum_2")],
            page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=None),
        )
        async_datalake.view_dataset_version_page = AsyncMock(side_effect=[first_page, second_page])

        rows = [row async for row in async_datalake.iter_dataset_version_view("demo", "1.0.0", page_size=1)]

        assert [row.datum_id for row in rows] == ["datum_1", "datum_2"]
        assert async_datalake.view_dataset_version_page.await_args_list[1].kwargs["cursor"] == "cursor-1"

    def test_get_mounts_returns_named_mounts(self, async_datalake):
        mounts = async_datalake.get_mounts()
        assert mounts["default_mount"] == "temp"
        assert mounts["mounts"][0]["name"] == "temp"

    @pytest.mark.asyncio
    async def test_put_get_head_copy_object(self, async_datalake, mock_store):
        ref = await async_datalake.put_object(name="images/cat.jpg", obj=b"bytes", mount="nas")
        assert ref.version == "v1"
        mock_store.save.return_value = None
        ref2 = await async_datalake.put_object(name="images/cat.jpg", obj=b"bytes")
        assert ref2.version == "latest"
        payload = await async_datalake.get_object(
            StorageRef(mount="nas", name="images/cat.jpg", version="v1"), verify="none"
        )
        info = await async_datalake.head_object(StorageRef(mount="nas", name="images/cat.jpg", version="v1"))
        assert await async_datalake.object_exists(StorageRef(mount="nas", name="images/cat.jpg", version="v1")) is True
        copied = await async_datalake.copy_object(
            StorageRef(mount="nas", name="images/cat.jpg", version="v1"),
            target_mount="archive",
            target_name="cat.jpg",
            target_version="v2",
        )
        assert payload == b"payload"
        assert info == {"size": 123}
        assert copied.version == "v2"

    @pytest.mark.asyncio
    async def test_object_exists_returns_false_when_store_has_object_false(self, async_datalake):
        async_datalake.store.has_object.return_value = False

        exists = await async_datalake.object_exists(StorageRef(mount="nas", name="missing", version="v1"))

        assert exists is False

    @pytest.mark.asyncio
    async def test_object_exists_returns_false_when_has_object_raises_registry_not_found(self, async_datalake):
        async_datalake.store.has_object.side_effect = RegistryObjectNotFound("Object x@1.0.0 not found.")

        exists = await async_datalake.object_exists(StorageRef(mount="nas", name="gone.bin", version="v1"))

        assert exists is False

    @pytest.mark.asyncio
    async def test_object_exists_propagates_unexpected_store_errors(self, async_datalake):
        async_datalake.store.has_object.side_effect = RuntimeError("infra")

        with pytest.raises(RuntimeError, match="infra"):
            await async_datalake.object_exists(StorageRef(mount="nas", name="any", version="v1"))

    def test_dataset_sync_returns_manager(self, async_datalake):
        manager = async_datalake.dataset_sync()

        from mindtrace.datalake.sync import DatasetSyncManager

        assert isinstance(manager, DatasetSyncManager)
        assert manager.source is async_datalake
        assert manager.target is async_datalake

    def test_replication_returns_manager(self, async_datalake):
        manager = async_datalake.replication()

        from mindtrace.datalake.replication import ReplicationManager

        assert isinstance(manager, ReplicationManager)
        assert manager.source is async_datalake
        assert manager.target is async_datalake

    @pytest.mark.asyncio
    async def test_create_object_upload_session(self, async_datalake, mock_store):
        session = await async_datalake.create_object_upload_session(
            name="images/cat.jpg",
            mount="nas",
            version="v9",
            metadata={"source": "unit"},
            content_type="image/jpeg",
            expires_in_minutes=15,
            created_by="tester",
        )

        assert isinstance(session, DirectUploadSession)
        assert session.mount == "nas"
        assert session.requested_version == "v9"
        assert session.upload_method == "local_path"
        assert session.staged_reference == {"kind": "local_file", "path": "/tmp/direct-upload/data.txt"}
        mock_store.create_direct_upload_target.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_object_upload_session_rejects_nonpositive_expiry(self, async_datalake):
        with pytest.raises(ValueError, match="expires_in_minutes must be positive"):
            await async_datalake.create_object_upload_session(name="images/cat.jpg", expires_in_minutes=0)

    @pytest.mark.asyncio
    async def test_get_object_upload_session_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError, match="Upload session with upload_session_id missing not found"):
            await async_datalake.get_object_upload_session("missing")

    @pytest.mark.asyncio
    async def test_complete_object_upload_session(self, async_datalake, mock_odm, mock_store):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            requested_version=None,
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]

        completed = await async_datalake.complete_object_upload_session(
            "upload_session_1",
            finalize_token="token-1",
            metadata={"source": "verified"},
        )

        assert completed.status == "completed"
        assert completed.storage_ref == StorageRef(mount="nas", name="images/cat.jpg", version="v5")
        mock_store.commit_direct_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_object_upload_session_raises_for_invalid_finalize_token(self, async_datalake, mock_odm):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]

        with pytest.raises(ValueError, match="Invalid finalize token"):
            await async_datalake.complete_object_upload_session("upload_session_1", finalize_token="wrong-token")

    @pytest.mark.asyncio
    async def test_complete_object_upload_session_raises_when_staged_payload_missing(
        self, async_datalake, mock_odm, mock_store
    ):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]
        mock_store.inspect_direct_upload_target.return_value = {"exists": False}

        with pytest.raises(FileNotFoundError, match="Staged upload not found"):
            await async_datalake.complete_object_upload_session("upload_session_1", finalize_token="token-1")

        assert session.status == "pending"
        assert session.verification_attempts == 1

    @pytest.mark.asyncio
    async def test_reconcile_upload_sessions_marks_expired_when_upload_never_arrives(
        self, async_datalake, mock_odm, mock_store
    ):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]
        mock_store.inspect_direct_upload_target.return_value = {"exists": False}

        reconciled = await async_datalake.reconcile_upload_sessions()

        assert reconciled[0].status == "expired"
        assert reconciled[0].failure_reason == "Upload did not complete before expiry."

    @pytest.mark.asyncio
    async def test_verify_finalize_returns_existing_completed_session(self, async_datalake, mock_store):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            status="completed",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )

        completed = await async_datalake._verify_and_finalize_upload_session(
            session,
            metadata={"verified": True},
            allow_pending_missing=False,
        )

        assert completed is session
        mock_store.inspect_direct_upload_target.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_object_upload_session_marks_failed_when_commit_raises(
        self, async_datalake, mock_odm, mock_store
    ):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]
        mock_store.commit_direct_upload.side_effect = RuntimeError("commit failed")
        mock_store.cleanup_direct_upload_target.return_value = True

        with pytest.raises(RuntimeError, match="commit failed"):
            await async_datalake.complete_object_upload_session("upload_session_1", finalize_token="token-1")

        assert session.status == "failed"
        assert session.failure_reason == "commit failed"
        assert session.cleanup_completed_at is not None
        mock_odm.update.assert_awaited()

    @pytest.mark.asyncio
    async def test_asset_crud_async(self, async_datalake, mock_odm):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        asset = await async_datalake.create_asset(
            kind="image",
            media_type="image/jpeg",
            storage_ref=ref,
            checksum="sha256:abc",
            size_bytes=123,
            subject=SubjectRef(kind="asset", id="asset_0"),
            metadata={"source": "demo"},
            created_by="tester",
        )
        assert isinstance(asset, Asset)
        asset.id = "db-id"
        mock_odm.find.return_value = [asset]
        assert await async_datalake.get_asset(asset.asset_id) is asset
        assert await async_datalake.list_assets({"kind": "image"}) == [asset]
        updated = await async_datalake.update_asset_metadata(asset.asset_id, {"source": "demo"})
        assert updated.metadata == {"source": "demo"}
        async_datalake.get_asset = AsyncMock(return_value=asset)
        async_datalake.datum_database.find_iter = lambda *_a, **_kw: self._async_iterable([])
        async_datalake.collection_item_database.find = AsyncMock(return_value=[])
        await async_datalake.delete_asset(asset.asset_id)
        mock_odm.delete.assert_awaited_with("db-id")

    @pytest.mark.asyncio
    async def test_get_asset_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError, match="Asset with asset_id missing not found"):
            await async_datalake.get_asset("missing")

    @pytest.mark.asyncio
    async def test_annotation_set_and_records_async(self, async_datalake, mock_odm):
        datum = Datum(asset_refs={"image": "asset_123"})
        async_datalake.get_datum = AsyncMock(return_value=datum)
        created_set = await async_datalake.create_annotation_set(
            name="gt", purpose="ground_truth", source_type="human", datum_id=datum.datum_id
        )
        assert created_set.annotation_set_id in datum.annotation_set_ids
        created_no_parent = await async_datalake.create_annotation_set(
            name="pred", purpose="prediction", source_type="machine"
        )
        assert isinstance(created_no_parent, AnnotationSet)

        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_record_ids = []
        self._patch_datum_find_for_annotation_set_merge(mock_odm, annotation_set.annotation_set_id, image_asset_id="asset_123")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        inserted_model = AnnotationRecord(
            kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}
        )
        inserted_model.annotation_id = "annotation_model"
        inserted_dict = AnnotationRecord(
            kind="bbox", label="crack", source={"type": "machine", "name": "detector"}, geometry={}
        )
        inserted_dict.annotation_id = "annotation_dict"
        mock_odm.insert = AsyncMock(side_effect=[inserted_model, inserted_dict])
        record_instance = AnnotationRecord(
            kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}
        )
        inserted = await async_datalake.add_annotation_records(
            [record_instance, {"kind": "bbox", "label": "crack", "source": {"type": "machine", "name": "detector"}}],
            annotation_set_id=annotation_set.annotation_set_id,
        )
        assert inserted == [inserted_model, inserted_dict]
        assert annotation_set.annotation_record_ids == ["annotation_model", "annotation_dict"]

    @pytest.mark.asyncio
    async def test_create_annotation_set_rolls_back_when_datum_update_fails(self, async_datalake, mock_odm):
        datum = Datum(asset_refs={"image": "asset_123"})
        datum.annotation_set_ids = []
        async_datalake.get_datum = AsyncMock(return_value=datum)
        async_datalake.annotation_set_database.delete = AsyncMock()
        async_datalake.datum_database.update = AsyncMock(side_effect=RuntimeError("datum update failed"))

        with pytest.raises(RuntimeError, match="datum update failed"):
            await async_datalake.create_annotation_set(
                name="gt",
                purpose="ground_truth",
                source_type="human",
                datum_id=datum.datum_id,
            )

        async_datalake.annotation_set_database.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_annotation_set_rollback_ignores_delete_errors(self, async_datalake):
        datum = Datum(asset_refs={"image": "asset_123"})
        datum.annotation_set_ids = []
        async_datalake.get_datum = AsyncMock(return_value=datum)
        async_datalake.annotation_set_database.delete = AsyncMock(side_effect=RuntimeError("delete failed"))
        async_datalake.datum_database.update = AsyncMock(side_effect=RuntimeError("datum update failed"))

        with pytest.raises(RuntimeError, match="datum update failed"):
            await async_datalake.create_annotation_set(
                name="gt",
                purpose="ground_truth",
                source_type="human",
                datum_id=datum.datum_id,
            )

        async_datalake.annotation_set_database.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_annotation_records_without_set_requires_asset_subject(self, async_datalake, mock_odm):
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            subject=SubjectRef(kind="asset", id="asset_abc"),
            source={"type": "human", "name": "review-ui"},
            geometry={},
        )
        inserted_record.annotation_id = "ann_free"
        mock_odm.insert = AsyncMock(return_value=inserted_record)

        inserted = await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "subject": {"kind": "asset", "id": "asset_abc"},
                    "source": {"type": "human", "name": "review-ui"},
                    "geometry": {},
                }
            ],
        )
        assert inserted == [inserted_record]
        mock_odm.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_annotation_records_without_set_rejects_missing_subject(self, async_datalake):
        with pytest.raises(ValueError, match="subject=SubjectRef"):
            await async_datalake.add_annotation_records(
                [{"kind": "bbox", "label": "x", "source": {"type": "human", "name": "a"}, "geometry": {}}],
            )

    @pytest.mark.asyncio
    async def test_list_annotation_records_for_asset_delegates_to_list(self, async_datalake):
        record = AnnotationRecord(
            kind="bbox",
            label="dent",
            subject=SubjectRef(kind="asset", id="asset_123"),
            source={"type": "human", "name": "review-ui"},
            geometry={},
        )
        async_datalake.list_annotation_records = AsyncMock(return_value=[record])
        result = await async_datalake.list_annotation_records_for_asset("asset_123")
        assert result == [record]
        async_datalake.list_annotation_records.assert_awaited_once_with(
            filters={"subject.kind": "asset", "subject.id": "asset_123"},
        )

    @pytest.mark.asyncio
    async def test_add_annotation_records_set_less_rejects_non_asset_subject_kind(self, async_datalake):
        with pytest.raises(ValueError, match="subject.kind must be 'asset'"):
            await async_datalake.add_annotation_records(
                [
                    {
                        "kind": "bbox",
                        "label": "x",
                        "subject": {"kind": "annotation", "id": "subj_1"},
                        "source": {"type": "human", "name": "a"},
                        "geometry": {},
                    }
                ],
            )

    @pytest.mark.asyncio
    async def test_add_annotation_records_set_less_rejects_blank_subject_id(self, async_datalake):
        with pytest.raises(ValueError, match="non-empty asset id"):
            await async_datalake.add_annotation_records(
                [
                    {
                        "kind": "bbox",
                        "label": "x",
                        "subject": {"kind": "asset", "id": "   "},
                        "source": {"type": "human", "name": "a"},
                        "geometry": {},
                    }
                ],
            )

    @pytest.mark.asyncio
    async def test_add_annotation_records_empty_iterable_returns_without_insert(self, async_datalake):
        async_datalake.annotation_record_database.insert = AsyncMock()
        assert await async_datalake.add_annotation_records([]) == []
        async_datalake.annotation_record_database.insert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_annotation_records_free_standing_uses_annotation_schema_id(self, async_datalake, mock_odm):
        schema = AnnotationSchema(
            name="solo",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[AnnotationLabelDefinition(name="dent", id=7)],
        )
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            label_id=7,
            subject=SubjectRef(kind="asset", id="asset_solo"),
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record.annotation_id = "ann_solo"
        mock_odm.insert = AsyncMock(return_value=inserted_record)

        inserted = await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "label_id": 7,
                    "subject": {"kind": "asset", "id": "asset_solo"},
                    "source": {"type": "human", "name": "review-ui"},
                    "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                }
            ],
            annotation_schema_id=schema.annotation_schema_id,
        )

        assert inserted == [inserted_record]
        async_datalake.get_annotation_schema.assert_awaited_once_with(schema.annotation_schema_id)

    @pytest.mark.asyncio
    async def test_annotation_record_crud_async(self, async_datalake, mock_odm):
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        record.id = "db-rec"
        annotation_set_1 = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set_1.annotation_record_ids = [record.annotation_id]
        annotation_set_2 = AnnotationSet(name="review", purpose="review", source_type="human")
        annotation_set_2.annotation_record_ids = [record.annotation_id, "other_annotation"]
        mock_odm.find.return_value = [record]
        assert await async_datalake.get_annotation_record(record.annotation_id) is record
        assert await async_datalake.list_annotation_records({"label": "dent"}) == [record]
        async_datalake.get_annotation_record = AsyncMock(return_value=record)
        updated = await async_datalake.update_annotation_record(
            record.annotation_id, source={"type": "machine", "name": "det"}
        )
        assert updated.source.type == "machine"
        async_datalake.annotation_set_database = MagicMock()
        async_datalake.annotation_set_database.find = AsyncMock(return_value=[annotation_set_1, annotation_set_2])
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=lambda obj: obj)
        await async_datalake.delete_annotation_record(record.annotation_id)
        assert annotation_set_1.annotation_record_ids == []
        assert annotation_set_2.annotation_record_ids == ["other_annotation"]

    @pytest.mark.asyncio
    async def test_delete_annotation_record_still_works_when_slow_lists_are_forbidden(self, async_datalake):
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        record.id = "db-rec"
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_record_ids = [record.annotation_id]
        async_datalake.slow_ops_policy = SlowOpsPolicy.FORBID
        async_datalake.get_annotation_record = AsyncMock(return_value=record)
        async_datalake.annotation_set_database = MagicMock()
        async_datalake.annotation_set_database.find = AsyncMock(return_value=[annotation_set])
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=lambda obj: obj)
        async_datalake.annotation_record_database = MagicMock()
        async_datalake.annotation_record_database.delete = AsyncMock()

        await async_datalake.delete_annotation_record(record.annotation_id)

        assert annotation_set.annotation_record_ids == []
        async_datalake.annotation_set_database.find.assert_awaited_once_with({"annotation_record_ids": record.annotation_id})
        async_datalake.annotation_record_database.delete.assert_awaited_once_with("db-rec")

    @pytest.mark.asyncio
    async def test_annotation_getters_and_listing(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        mock_odm.find.return_value = [annotation_set]
        assert await async_datalake.get_annotation_set(annotation_set.annotation_set_id) is annotation_set
        assert await async_datalake.list_annotation_sets() == [annotation_set]
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_annotation_set("missing")
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_annotation_record("missing")

    @pytest.mark.asyncio
    async def test_collection_and_asset_retention_crud_async(self, async_datalake, mock_odm):
        collection = await async_datalake.create_collection(
            name="demo-collection",
            description="demo",
            metadata={"source": "demo"},
            created_by="tester",
        )
        assert isinstance(collection, Collection)
        collection.id = "db-collection"
        mock_odm.find.return_value = [collection]
        assert await async_datalake.get_collection(collection.collection_id) is collection
        assert await async_datalake.list_collections({"status": "active"}) == [collection]
        updated_collection = await async_datalake.update_collection(collection.collection_id, status="archived")
        assert updated_collection.status == "archived"
        await async_datalake.delete_collection(collection.collection_id)
        mock_odm.delete.assert_awaited_with("db-collection")

        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        async_datalake.get_collection = AsyncMock(return_value=collection)
        async_datalake.get_asset = AsyncMock(return_value=asset)
        collection_item = await async_datalake.create_collection_item(
            collection_id=collection.collection_id,
            asset_id=asset.asset_id,
            split="train",
            metadata={"tag": "a"},
            added_by="tester",
        )
        assert isinstance(collection_item, CollectionItem)
        collection_item.id = "db-collection-item"
        mock_odm.find.return_value = [collection_item]
        assert await async_datalake.get_collection_item(collection_item.collection_item_id) is collection_item
        assert await async_datalake.list_collection_items({"collection_id": collection.collection_id}) == [
            collection_item
        ]
        async_datalake.get_collection_item = AsyncMock(return_value=collection_item)
        resolved_item = await async_datalake.resolve_collection_item(collection_item.collection_item_id)
        assert isinstance(resolved_item, ResolvedCollectionItem)
        updated_item = await async_datalake.update_collection_item(collection_item.collection_item_id, status="hidden")
        assert updated_item.status == "hidden"
        await async_datalake.delete_collection_item(collection_item.collection_item_id)

        asset_retention = await async_datalake.create_asset_retention(
            asset_id=asset.asset_id,
            owner_type="manual_pin",
            owner_id="owner_1",
            metadata={"source": "demo"},
            created_by="tester",
        )
        assert isinstance(asset_retention, AssetRetention)
        asset_retention.id = "db-asset-retention"
        mock_odm.find.return_value = [asset_retention]
        assert await async_datalake.get_asset_retention(asset_retention.asset_retention_id) is asset_retention
        assert await async_datalake.list_asset_retentions({"asset_id": asset.asset_id}) == [asset_retention]
        async_datalake.get_asset_retention = AsyncMock(return_value=asset_retention)
        updated_retention = await async_datalake.update_asset_retention(
            asset_retention.asset_retention_id,
            retention_policy="archive_when_unreferenced",
        )
        assert updated_retention.retention_policy == "archive_when_unreferenced"
        await async_datalake.delete_asset_retention(asset_retention.asset_retention_id)

    @pytest.mark.asyncio
    async def test_delete_collection_removes_linked_collection_items(self, async_datalake, mock_odm):
        collection = Collection(name="demo")
        collection.id = "db-collection"
        collection_item = CollectionItem(collection_id=collection.collection_id, asset_id="asset_1")
        collection_item.id = "db-item"
        async_datalake.get_collection = AsyncMock(return_value=collection)
        mock_odm.find = AsyncMock(return_value=[collection_item])
        mock_odm.delete = AsyncMock()

        await async_datalake.delete_collection(collection.collection_id)

        assert mock_odm.delete.await_args_list[0].args == ("db-item",)
        assert mock_odm.delete.await_args_list[1].args == ("db-collection",)

    @pytest.mark.asyncio
    async def test_collection_and_retention_missing_paths_raise(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_collection("missing")

        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_collection_item("missing")

        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_asset_retention("missing")

    @pytest.mark.asyncio
    async def test_update_collection_item_validates_changed_relationships(self, async_datalake):
        collection_item = CollectionItem(collection_id="collection_1", asset_id="asset_1")
        async_datalake.get_collection_item = AsyncMock(return_value=collection_item)
        async_datalake.get_collection = AsyncMock()
        async_datalake.get_asset = AsyncMock()
        async_datalake.collection_item_database.update = AsyncMock(side_effect=lambda obj: obj)

        updated = await async_datalake.update_collection_item(
            collection_item.collection_item_id,
            collection_id="collection_2",
            asset_id="asset_2",
            status="hidden",
        )

        async_datalake.get_collection.assert_awaited_once_with("collection_2")
        async_datalake.get_asset.assert_awaited_once_with("asset_2")
        assert updated.collection_id == "collection_2"
        assert updated.asset_id == "asset_2"
        assert updated.status == "hidden"

    @pytest.mark.asyncio
    async def test_update_asset_retention_validates_changed_asset(self, async_datalake):
        asset_retention = AssetRetention(asset_id="asset_1", owner_type="manual_pin", owner_id="owner_1")
        async_datalake.get_asset_retention = AsyncMock(return_value=asset_retention)
        async_datalake.get_asset = AsyncMock()
        async_datalake.asset_retention_database.update = AsyncMock(side_effect=lambda obj: obj)

        updated = await async_datalake.update_asset_retention(
            asset_retention.asset_retention_id,
            asset_id="asset_2",
            retention_policy="archive_when_unreferenced",
        )

        async_datalake.get_asset.assert_awaited_once_with("asset_2")
        assert updated.asset_id == "asset_2"
        assert updated.retention_policy == "archive_when_unreferenced"

    @pytest.mark.asyncio
    async def test_datum_crud_async(self, async_datalake, mock_odm):
        async_datalake.get_asset = AsyncMock(
            return_value=Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="x"))
        )
        async_datalake.get_annotation_set = AsyncMock(
            return_value=AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        )
        datum = await async_datalake.create_datum(
            asset_refs={"image": "asset_1"}, split="train", metadata={"source": "demo"}, annotation_set_ids=["set_1"]
        )
        assert isinstance(datum, Datum)
        datum.id = "db-datum"
        mock_odm.find.return_value = [datum]
        assert await async_datalake.get_datum(datum.datum_id) is datum
        assert await async_datalake.list_datums({"split": "train"}) == [datum]
        updated = await async_datalake.update_datum(datum.datum_id, metadata={"source": "updated"})
        assert updated.metadata == {"source": "updated"}

    @pytest.mark.asyncio
    async def test_update_datum_validates_asset_refs(self, async_datalake):
        datum = Datum(asset_refs={"image": "asset_1"})
        async_datalake.get_datum = AsyncMock(return_value=datum)
        async_datalake.get_asset = AsyncMock(
            return_value=Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="x"))
        )

        await async_datalake.update_datum(datum.datum_id, asset_refs={"image": "asset_2"})

        async_datalake.get_asset.assert_awaited_once_with("asset_2")

    @pytest.mark.asyncio
    async def test_update_datum_validates_annotation_set_ids(self, async_datalake):
        datum = Datum(asset_refs={"image": "asset_1"})
        async_datalake.get_datum = AsyncMock(return_value=datum)
        async_datalake.get_annotation_set = AsyncMock(
            return_value=AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        )

        await async_datalake.update_datum(datum.datum_id, annotation_set_ids=["set_2"])

        async_datalake.get_annotation_set.assert_awaited_once_with("set_2")

    @pytest.mark.asyncio
    async def test_validate_asset_refs_rejects_blank_ids(self, async_datalake):
        with pytest.raises(ValueError, match="non-empty asset ids"):
            await async_datalake._validate_asset_refs_exist({"image": "   "})

    @pytest.mark.asyncio
    async def test_delete_asset_raises_when_still_referenced_by_datum(self, async_datalake):
        asset = Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="x"))
        asset.id = "db-asset"
        datum = Datum(asset_refs={"image": asset.asset_id})
        async_datalake.get_asset = AsyncMock(return_value=asset)
        async_datalake.datum_database.find_iter = lambda *_a, **_kw: self._async_iterable([datum])

        with pytest.raises(ValueError, match="still referenced"):
            await async_datalake.delete_asset(asset.asset_id)

    @pytest.mark.asyncio
    async def test_delete_asset_handles_collection_item_and_alias_rows(self, async_datalake, mock_odm):
        asset = Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="x"))
        asset.id = "db-asset"
        async_datalake.get_asset = AsyncMock(return_value=asset)
        async_datalake.datum_database.find_iter = lambda *_a, **_kw: self._async_iterable([])
        mock_odm.find = AsyncMock(return_value=[MagicMock(id="item-row")])

        with pytest.raises(ValueError, match="collection items"):
            await async_datalake.delete_asset(asset.asset_id)

        async def find_side_effect(query=None):
            if query == {"asset_id": asset.asset_id}:
                if not hasattr(find_side_effect, "seen"):
                    find_side_effect.seen = True
                    return []
                return [MagicMock(id="alias-row")]
            return []

        mock_odm.find = AsyncMock(side_effect=find_side_effect)
        mock_odm.delete = AsyncMock()

        await async_datalake.delete_asset(asset.asset_id)

        assert mock_odm.delete.await_args_list[0].args == ("alias-row",)
        assert mock_odm.delete.await_args_list[1].args == ("db-asset",)

    @pytest.mark.asyncio
    async def test_delete_asset_still_works_when_slow_lists_are_forbidden(self, async_datalake):
        asset = Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="x"))
        asset.id = "db-asset"
        async_datalake.slow_ops_policy = SlowOpsPolicy.FORBID
        async_datalake.get_asset = AsyncMock(return_value=asset)
        async_datalake.datum_database = MagicMock()
        async_datalake.datum_database.find_iter = lambda *_a, **_kw: self._async_iterable([])
        async_datalake.collection_item_database = MagicMock()
        async_datalake.collection_item_database.find = AsyncMock(return_value=[])
        async_datalake.asset_alias_database = MagicMock()
        async_datalake.asset_alias_database.find = AsyncMock(return_value=[])
        async_datalake.asset_alias_database.delete = AsyncMock()
        async_datalake.asset_database = MagicMock()
        async_datalake.asset_database.delete = AsyncMock()

        await async_datalake.delete_asset(asset.asset_id)

        async_datalake.asset_database.delete.assert_awaited_once_with("db-asset")

    @pytest.mark.asyncio
    async def test_get_datum_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_datum("missing")

    @pytest.mark.asyncio
    async def test_dataset_version_async(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        async_datalake.get_datum = AsyncMock(
            side_effect=[
                Datum(asset_refs={"image": "asset_1"}),
                Datum(asset_refs={"image": "asset_2"}),
            ]
        )
        created = await async_datalake.create_dataset_version(
            dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"]
        )
        assert isinstance(created, DatasetVersion)
        existing = DatasetVersion(dataset_name="demo", version="0.1.0")
        mock_odm.find.return_value = [existing]
        with pytest.raises(ValueError):
            await async_datalake.create_dataset_version(dataset_name="demo", version="0.1.0", manifest=[])

    @pytest.mark.asyncio
    async def test_create_dataset_version_rejects_duplicate_manifest_ids(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(ValueError, match="must not contain duplicate datum ids"):
            await async_datalake.create_dataset_version(
                dataset_name="demo",
                version="0.1.0",
                manifest=["datum_1", "datum_1"],
            )

    @pytest.mark.asyncio
    async def test_dataset_version_get_list_and_resolve(self, async_datalake, mock_odm):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"])
        mock_odm.find.return_value = [dataset_version]
        assert await async_datalake.get_dataset_version("demo", "0.1.0") is dataset_version
        assert await async_datalake.list_dataset_versions(filters={"metadata.stage": "initial"}) == [dataset_version]
        assert await async_datalake.list_dataset_versions(
            dataset_name="demo", filters={"metadata.stage": "initial"}
        ) == [dataset_version]
        resolved_datum_1 = ResolvedDatum(datum=Datum(asset_refs={"image": "asset_1"}))
        resolved_datum_2 = ResolvedDatum(datum=Datum(asset_refs={"image": "asset_2"}))
        async_datalake.get_dataset_version = AsyncMock(return_value=dataset_version)
        async_datalake.resolve_datum = AsyncMock(side_effect=[resolved_datum_1, resolved_datum_2])
        resolved = await async_datalake.resolve_dataset_version("demo", "0.1.0")
        assert isinstance(resolved, ResolvedDatasetVersion)
        assert resolved.datums == [resolved_datum_1, resolved_datum_2]

    @pytest.mark.asyncio
    async def test_get_dataset_version_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_dataset_version("demo", "0.1.0")

    @pytest.mark.asyncio
    async def test_resolve_datum_collects_assets_and_annotations(self, async_datalake):
        datum = Datum(asset_refs={"image": "asset_1"}, annotation_set_ids=["set_1"])
        datum.datum_id = "datum_1"
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set_1"
        annotation_set.annotation_record_ids = ["annotation_1"]
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        async_datalake.get_datum = AsyncMock(return_value=datum)
        async_datalake.get_asset = AsyncMock(return_value=asset)
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_record = AsyncMock(return_value=record)
        resolved = await async_datalake.resolve_datum("datum_1")
        assert isinstance(resolved, ResolvedDatum)
        assert resolved.assets == {"image": asset}

    @pytest.mark.asyncio
    async def test_create_asset_from_object_chains_put_and_create(self, async_datalake):
        storage_ref = StorageRef(mount="temp", name="images/example.jpg", version="v1")
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)
        async_datalake.put_object = AsyncMock(return_value=storage_ref)
        async_datalake.create_asset = AsyncMock(return_value=asset)
        created = await async_datalake.create_asset_from_object(
            name="images/example.jpg",
            obj=b"bytes",
            kind="image",
            media_type="image/jpeg",
            mount="temp",
            version="v1",
            object_metadata={"filename": "example.jpg"},
            asset_metadata={"source": "demo"},
            checksum="sha256:abc",
            size_bytes=12,
            subject=SubjectRef(kind="asset", id="asset_0"),
            created_by="tester",
            on_conflict="overwrite",
        )
        assert created is asset
        async_datalake.put_object.assert_awaited_once()
        async_datalake.create_asset.assert_awaited_once_with(
            kind="image",
            media_type="image/jpeg",
            storage_ref=storage_ref,
            checksum="sha256:abc",
            size_bytes=12,
            subject=SubjectRef(kind="asset", id="asset_0"),
            metadata={"source": "demo"},
            created_by="tester",
        )

    @pytest.mark.asyncio
    async def test_annotation_schema_crud_async(self, async_datalake, mock_odm):
        schema = await async_datalake.create_annotation_schema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[{"name": "cat", "id": 1}],
            created_by="tester",
        )
        assert isinstance(schema, AnnotationSchema)
        schema.id = "db-schema"
        mock_odm.find.return_value = [schema]
        assert await async_datalake.get_annotation_schema(schema.annotation_schema_id) is schema
        assert await async_datalake.get_annotation_schema_by_name_version("demo", "1.0.0") is schema
        assert await async_datalake.list_annotation_schemas({"task_type": "classification"}) == [schema]
        updated = await async_datalake.update_annotation_schema(
            schema.annotation_schema_id,
            labels=[{"name": "dog", "id": 2}],
            allow_scores=True,
        )
        assert updated.labels[0].name == "dog"
        assert updated.allow_scores is True
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        async_datalake.annotation_set_database.find = AsyncMock(return_value=[])
        await async_datalake.delete_annotation_schema(schema.annotation_schema_id)
        mock_odm.delete.assert_awaited_with("db-schema")

    @pytest.mark.asyncio
    async def test_create_annotation_set_validates_schema_reference(self, async_datalake):
        schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        created = await async_datalake.create_annotation_set(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        assert created.annotation_schema_id == schema.annotation_schema_id

    @pytest.mark.asyncio
    async def test_add_annotation_records_validates_schema_bound_sets(self, async_datalake, mock_odm):
        schema = AnnotationSchema(
            name="bbox-demo",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[AnnotationLabelDefinition(name="dent", id=7)],
            required_attributes=["quality"],
            optional_attributes=["reviewed"],
        )
        annotation_set = AnnotationSet(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        self._patch_datum_find_for_annotation_set_merge(
            mock_odm, annotation_set.annotation_set_id, image_asset_id="asset_schema_merge"
        )
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            label_id=7,
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
            attributes={"quality": "high"},
        )
        inserted_record.annotation_id = "annotation_1"
        mock_odm.insert = AsyncMock(side_effect=[inserted_record])

        inserted = await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "label_id": 7,
                    "source": {"type": "human", "name": "review-ui"},
                    "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    "attributes": {"quality": "high"},
                }
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )

        assert inserted == [inserted_record]
        assert annotation_set.annotation_record_ids == ["annotation_1"]

    @pytest.mark.asyncio
    async def test_add_annotation_records_coerces_subject_dicts(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            subject=SubjectRef(kind="asset", id="asset_123"),
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record.annotation_id = "annotation_1"
        mock_odm.insert = AsyncMock(return_value=inserted_record)

        inserted = await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "subject": {"kind": "asset", "id": "asset_123"},
                    "source": {"type": "human", "name": "review-ui"},
                    "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                }
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )

        coerced_record = mock_odm.insert.await_args.args[0]
        assert isinstance(coerced_record.subject, SubjectRef)
        assert coerced_record.subject.kind == "asset"
        assert coerced_record.subject.id == "asset_123"
        assert inserted == [inserted_record]

    @pytest.mark.asyncio
    async def test_add_annotation_records_rejects_invalid_schema_payloads(self, async_datalake, mock_odm):
        schema = AnnotationSchema(
            name="classification-demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        annotation_set = AnnotationSet(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        self._patch_datum_find_for_annotation_set_merge(
            mock_odm, annotation_set.annotation_set_id, image_asset_id="asset_schema_val"
        )

        with pytest.raises(AnnotationSchemaValidationError, match="not defined in schema"):
            await async_datalake.add_annotation_records(
                [
                    {
                        "kind": "classification",
                        "label": "dog",
                        "source": {"type": "human", "name": "review-ui"},
                    }
                ],
                annotation_set_id=annotation_set.annotation_set_id,
            )

        with pytest.raises(AnnotationSchemaValidationError, match="must not include geometry"):
            await async_datalake.add_annotation_records(
                [
                    {
                        "kind": "classification",
                        "label": "cat",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1},
                    }
                ],
                annotation_set_id=annotation_set.annotation_set_id,
            )

    @pytest.mark.asyncio
    async def test_add_annotation_records_is_atomic_when_schema_validation_fails_mid_batch(self, async_datalake, mock_odm):
        schema = AnnotationSchema(
            name="bbox-demo",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[AnnotationLabelDefinition(name="dent", id=7)],
        )
        annotation_set = AnnotationSet(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        self._patch_datum_find_for_annotation_set_merge(
            mock_odm, annotation_set.annotation_set_id, image_asset_id="asset_atomic_batch"
        )
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            label_id=7,
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record.annotation_id = "annotation_1"
        async_datalake.annotation_record_database.insert = AsyncMock(return_value=inserted_record)
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=lambda obj: obj)

        with pytest.raises(AnnotationSchemaValidationError, match="not defined in schema"):
            await async_datalake.add_annotation_records(
                [
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "label_id": 7,
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    },
                    {
                        "kind": "bbox",
                        "label": "unknown",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 5, "y": 6, "width": 7, "height": 8},
                    },
                ],
                annotation_set_id=annotation_set.annotation_set_id,
            )

        assert async_datalake.annotation_record_database.insert.await_count == 0
        async_datalake.annotation_set_database.update.assert_not_awaited()
        assert annotation_set.annotation_record_ids == []

    @pytest.mark.asyncio
    async def test_create_annotation_schema_prevents_concurrent_duplicate_name_version(self, async_datalake):
        race_gate = asyncio.Event()
        lookup_count = 0
        insert_count = 0

        async def racing_find(filters):
            nonlocal lookup_count
            assert filters == {"name": "demo", "version": "1.0.0"}
            lookup_count += 1
            if lookup_count == 2:
                race_gate.set()
            await race_gate.wait()
            return []

        async def racing_insert(obj):
            nonlocal insert_count
            insert_count += 1
            if insert_count == 2:
                raise DuplicateInsertError("Duplicate key error")
            return obj

        async_datalake.annotation_schema_database.find = AsyncMock(side_effect=racing_find)
        async_datalake.annotation_schema_database.insert = AsyncMock(side_effect=racing_insert)

        results = await asyncio.gather(
            async_datalake.create_annotation_schema(
                name="demo",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[{"name": "cat"}],
            ),
            async_datalake.create_annotation_schema(
                name="demo",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[{"name": "cat"}],
            ),
            return_exceptions=True,
        )

        successes = [result for result in results if isinstance(result, AnnotationSchema)]
        errors = [result for result in results if isinstance(result, Exception)]

        assert len(successes) == 1
        assert len(errors) == 1
        assert isinstance(errors[0], DuplicateAnnotationSchemaError)
        assert async_datalake.annotation_schema_database.insert.await_count == 2

    @pytest.mark.asyncio
    async def test_delete_annotation_schema_rejects_referenced_schema(self, async_datalake):
        schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        schema.id = "db-schema"
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        async_datalake.annotation_set_database.find = AsyncMock(
            return_value=[
                AnnotationSet(
                    name="gt",
                    purpose="ground_truth",
                    source_type="human",
                    annotation_schema_id=schema.annotation_schema_id,
                )
            ]
        )

        with pytest.raises(AnnotationSchemaInUseError, match="still referenced"):
            await async_datalake.delete_annotation_schema(schema.annotation_schema_id)

        async_datalake.annotation_schema_database.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_annotation_set_validates_schema_reference(self, async_datalake):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=lambda obj: obj)

        updated = await async_datalake.update_annotation_set(
            annotation_set.annotation_set_id,
            annotation_schema_id=schema.annotation_schema_id,
            status="active",
        )

        async_datalake.get_annotation_schema.assert_awaited_once_with(schema.annotation_schema_id)
        assert updated.annotation_schema_id == schema.annotation_schema_id
        assert updated.status == "active"

    @pytest.mark.asyncio
    async def test_annotation_schema_lookup_and_duplicate_paths_raise_expected_errors(self, async_datalake):
        existing_schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        async_datalake.annotation_schema_database.find = AsyncMock(return_value=[existing_schema])

        with pytest.raises(DuplicateAnnotationSchemaError, match="demo@1.0.0"):
            await async_datalake.create_annotation_schema(
                name="demo",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
            )

        async_datalake.annotation_schema_database.find = AsyncMock(return_value=[])
        with pytest.raises(DocumentNotFoundError, match="annotation_schema_id missing"):
            await async_datalake.get_annotation_schema("missing")
        with pytest.raises(DocumentNotFoundError, match="AnnotationSchema demo@missing not found"):
            await async_datalake.get_annotation_schema_by_name_version("demo", "missing")

    def test_annotation_schema_validation_helpers_cover_remaining_error_branches(self, async_datalake):
        classification_schema = AnnotationSchema(
            name="classification-demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat", id=1)],
        )
        classification_record = AnnotationRecord(
            kind="classification",
            label="cat",
            label_id=1,
            source={"type": "human", "name": "review-ui"},
            geometry={},
        )
        async_datalake._validate_annotation_geometry_for_schema(classification_record, classification_schema)

        with pytest.raises(AnnotationSchemaValidationError, match="kind 'bbox' is not allowed"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="bbox",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                ),
                classification_schema,
            )

        with pytest.raises(AnnotationSchemaValidationError, match="label_id 99 does not match"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    label_id=99,
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                ),
                classification_schema,
            )

        detection_schema = AnnotationSchema(
            name="bbox-demo",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[AnnotationLabelDefinition(name="dent")],
        )
        with pytest.raises(AnnotationSchemaValidationError, match="missing required geometry fields"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="bbox",
                    label="dent",
                    source={"type": "human", "name": "review-ui"},
                    geometry={"x": 1, "y": 2, "width": 3},
                ),
                detection_schema,
            )

        segmentation_schema = AnnotationSchema(
            name="mask-demo",
            version="1.0.0",
            task_type="segmentation",
            allowed_annotation_kinds=["mask"],
            labels=[AnnotationLabelDefinition(name="dent")],
        )
        with pytest.raises(AnnotationSchemaValidationError, match="must include non-empty geometry"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="mask",
                    label="dent",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                ),
                segmentation_schema,
            )
        with pytest.raises(AnnotationSchemaValidationError, match="must include at least one of"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="mask",
                    label="dent",
                    source={"type": "human", "name": "review-ui"},
                    geometry={"x": 1},
                ),
                segmentation_schema,
            )

        attribute_schema = AnnotationSchema(
            name="attribute-demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
            required_attributes=["quality"],
            optional_attributes=["reviewed"],
        )
        with pytest.raises(AnnotationSchemaValidationError, match="missing required fields: quality"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                    attributes={},
                ),
                attribute_schema,
            )
        with pytest.raises(
            AnnotationSchemaValidationError, match="not allowed by schema 'attribute-demo@1.0.0': extra"
        ):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                    attributes={"quality": "high", "extra": True},
                ),
                attribute_schema,
            )
        with pytest.raises(AnnotationSchemaValidationError, match="scores are not allowed"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                    score=0.5,
                ),
                classification_schema,
            )

    @pytest.mark.asyncio
    async def test_annotation_record_rollbacks_handle_delete_errors_and_update_failures(self, async_datalake, mock_odm):
        record_without_id = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record.id = "db-inserted"
        async_datalake.annotation_record_database.delete = AsyncMock(side_effect=RuntimeError("delete failed"))
        await async_datalake._rollback_inserted_annotation_records([record_without_id, inserted_record])
        async_datalake.annotation_record_database.delete.assert_awaited_once_with("db-inserted")

        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        self._patch_datum_find_for_annotation_set_merge(
            mock_odm, annotation_set.annotation_set_id, image_asset_id="asset_rollback"
        )
        successful_insert = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        successful_insert.id = "db-success"
        successful_insert.annotation_id = "annotation_success"
        async_datalake.annotation_record_database.insert = AsyncMock(
            side_effect=[successful_insert, RuntimeError("insert failed")]
        )
        async_datalake.annotation_record_database.delete = AsyncMock()

        with pytest.raises(RuntimeError, match="insert failed"):
            await async_datalake.add_annotation_records(
                [
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    },
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 5, "y": 6, "width": 7, "height": 8},
                    },
                ],
                annotation_set_id=annotation_set.annotation_set_id,
            )
        async_datalake.annotation_record_database.delete.assert_awaited_once_with("db-success")

        async_datalake.annotation_record_database.delete.reset_mock()
        async_datalake.annotation_record_database.insert = AsyncMock(return_value=successful_insert)
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=RuntimeError("set update failed"))

        with pytest.raises(RuntimeError, match="set update failed"):
            await async_datalake.add_annotation_records(
                [
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    }
                ],
                annotation_set_id=annotation_set.annotation_set_id,
            )

        assert annotation_set.annotation_record_ids == []
        async_datalake.annotation_record_database.delete.assert_awaited_once_with("db-success")

    @pytest.mark.asyncio
    async def test_add_annotation_records_set_without_datum_link_requires_explicit_subject(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        mock_odm.find = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="No Datum references this annotation set"):
            await async_datalake.add_annotation_records(
                [{"kind": "bbox", "label": "x", "source": {"type": "human", "name": "a"}, "geometry": {}}],
                annotation_set_id=annotation_set.annotation_set_id,
            )

    @pytest.mark.asyncio
    async def test_add_annotation_records_merge_rejects_conflicting_image_datums(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        sid = annotation_set.annotation_set_id

        async def find_side_effect(query=None):
            q = query or {}
            if q.get("annotation_set_ids") == sid:
                return [
                    Datum(asset_refs={"image": "a1"}, annotation_set_ids=[sid]),
                    Datum(asset_refs={"image": "a2"}, annotation_set_ids=[sid]),
                ]
            return []

        mock_odm.find = AsyncMock(side_effect=find_side_effect)

        with pytest.raises(ValueError, match="multiple datums whose asset_refs"):
            await async_datalake.add_annotation_records(
                [{"kind": "bbox", "label": "x", "source": {"type": "human", "name": "t"}, "geometry": {}}],
                annotation_set_id=sid,
            )

    @pytest.mark.asyncio
    async def test_merge_non_dict_annotation_needs_subject_uses_getattr_branch(self, async_datalake, mock_odm):
        """`_needs_subject` must evaluate the non-dict branch (no short-circuit from a dict first)."""
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        self._patch_datum_find_for_annotation_set_merge(
            mock_odm, annotation_set.annotation_set_id, image_asset_id="asset_getattr_merge"
        )

        async def insert_echo(record):
            return record

        mock_odm.insert = AsyncMock(side_effect=insert_echo)
        out = await async_datalake.add_annotation_records(
            [
                AnnotationRecord(
                    kind="bbox",
                    label="only-model",
                    source={"type": "human", "name": "t"},
                    geometry={},
                ),
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )
        assert out[0].subject == SubjectRef(kind="asset", id="asset_getattr_merge")

    @pytest.mark.asyncio
    async def test_merge_datums_without_image_allowed_when_subjects_explicit(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        sid = annotation_set.annotation_set_id

        async def find_side_effect(query=None):
            q = query or {}
            if q.get("annotation_set_ids") == sid:
                return [Datum(datum_id="d1", asset_refs={"depth": "other"}, annotation_set_ids=[sid])]
            return []

        mock_odm.find = AsyncMock(side_effect=find_side_effect)
        subj = SubjectRef(kind="asset", id="explicit_asset")
        inserted = AnnotationRecord(
            kind="bbox",
            label="x",
            subject=subj,
            source={"type": "human", "name": "t"},
            geometry={},
        )
        inserted.annotation_id = "ann1"
        mock_odm.insert = AsyncMock(return_value=inserted)
        rec = AnnotationRecord(
            kind="bbox",
            label="x",
            subject=subj,
            source={"type": "human", "name": "t"},
            geometry={},
        )
        out = await async_datalake.add_annotation_records(
            [rec],
            annotation_set_id=sid,
        )
        assert out == [inserted]
        assert out[0].subject == subj

    @pytest.mark.asyncio
    async def test_merge_rejects_missing_subject_when_datums_lack_image_ref(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        sid = annotation_set.annotation_set_id

        async def find_side_effect(query=None):
            q = query or {}
            if q.get("annotation_set_ids") == sid:
                return [Datum(datum_id="d1", asset_refs={"depth": "other"}, annotation_set_ids=[sid])]
            return []

        mock_odm.find = AsyncMock(side_effect=find_side_effect)

        with pytest.raises(ValueError, match=r"no asset_refs\['image'\]"):
            await async_datalake.add_annotation_records(
                [{"kind": "bbox", "label": "x", "source": {"type": "human", "name": "t"}, "geometry": {}}],
                annotation_set_id=sid,
            )

    @pytest.mark.asyncio
    async def test_merge_preserves_explicit_dict_and_record_subjects(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        self._patch_datum_find_for_annotation_set_merge(
            mock_odm, annotation_set.annotation_set_id, image_asset_id="datum_default_image",
        )
        explicit = SubjectRef(kind="asset", id="user_chosen")
        inserted_dict = AnnotationRecord(
            kind="bbox",
            label="d",
            subject=explicit,
            source={"type": "human", "name": "t"},
            geometry={},
        )
        inserted_dict.annotation_id = "a_dict"
        inserted_rec = AnnotationRecord(
            kind="bbox",
            label="r",
            subject=explicit,
            source={"type": "human", "name": "t"},
            geometry={},
        )
        inserted_rec.annotation_id = "a_rec"
        mock_odm.insert = AsyncMock(side_effect=[inserted_dict, inserted_rec])
        out = await async_datalake.add_annotation_records(
            [
                {
                    "kind": "bbox",
                    "label": "d",
                    "subject": {"kind": "asset", "id": "user_chosen"},
                    "source": {"type": "human", "name": "t"},
                    "geometry": {},
                },
                AnnotationRecord(
                    kind="bbox",
                    label="r",
                    subject=explicit,
                    source={"type": "human", "name": "t"},
                    geometry={},
                ),
            ],
            annotation_set_id=annotation_set.annotation_set_id,
        )
        assert out[0].subject == explicit
        assert out[1].subject == explicit
