from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import AsyncDatalake
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    DatasetVersion,
    Datum,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)


class TestAsyncDatalakeUnit:
    @pytest.fixture
    def mock_odm(self):
        mock = AsyncMock()
        mock.initialize = AsyncMock()
        mock.insert = AsyncMock(side_effect=lambda obj: obj)
        mock.find = AsyncMock(return_value=[])
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
        return store

    @pytest.fixture
    def async_datalake(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            return AsyncDatalake("mongodb://test:27017", "test_db", store=mock_store)

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

    def test_init_builds_default_store_when_not_provided(self, mock_odm):
        fake_store = MagicMock()
        with (
            patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm),
            patch("mindtrace.datalake.async_datalake.Store", return_value=fake_store) as store_cls,
        ):
            datalake = AsyncDatalake("mongodb://test:27017", "test_db", default_mount="nas")
        assert datalake.store == fake_store
        store_cls.assert_called_once_with(default_mount="nas")

    @pytest.mark.asyncio
    async def test_initialize_initializes_all_odms(self, async_datalake, mock_odm):
        await async_datalake.initialize()
        assert mock_odm.initialize.await_count == 5

    @pytest.mark.asyncio
    async def test_create_classmethod_initializes_instance(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            created = await AsyncDatalake.create("mongodb://test:27017", "test_db", store=mock_store)
        assert isinstance(created, AsyncDatalake)
        assert created.store == mock_store
        assert mock_odm.initialize.await_count == 5

    def test_utc_now_returns_timezone_aware_datetime(self, async_datalake):
        now = async_datalake._utc_now()
        assert now.tzinfo is not None

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
        payload = await async_datalake.get_object(StorageRef(mount="nas", name="images/cat.jpg", version="v1"), verify="none")
        info = await async_datalake.head_object(StorageRef(mount="nas", name="images/cat.jpg", version="v1"))
        copied = await async_datalake.copy_object(StorageRef(mount="nas", name="images/cat.jpg", version="v1"), target_mount="archive", target_name="cat.jpg", target_version="v2")
        assert payload == b"payload"
        assert info == {"size": 123}
        assert copied.version == "v2"

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
        created_no_parent = await async_datalake.create_annotation_set(name="pred", purpose="prediction", source_type="machine")
        assert created_no_parent.datum_id is None

        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_record_ids = []
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        inserted_model = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        inserted_model.annotation_id = "annotation_model"
        inserted_dict = AnnotationRecord(kind="bbox", label="crack", source={"type": "machine", "name": "detector"}, geometry={})
        inserted_dict.annotation_id = "annotation_dict"
        mock_odm.insert = AsyncMock(side_effect=[inserted_model, inserted_dict])
        record_instance = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        inserted = await async_datalake.add_annotation_records(
            annotation_set.annotation_set_id,
            [record_instance, {"kind": "bbox", "label": "crack", "source": {"type": "machine", "name": "detector"}}],
        )
        assert inserted == [inserted_model, inserted_dict]

    @pytest.mark.asyncio
    async def test_annotation_record_crud_async(self, async_datalake, mock_odm):
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        record.id = "db-rec"
        record.annotation_set_id = "set-1"
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set-1"
        annotation_set.annotation_record_ids = [record.annotation_id]
        mock_odm.find.return_value = [record]
        assert await async_datalake.get_annotation_record(record.annotation_id) is record
        assert await async_datalake.list_annotation_records({"label": "dent"}) == [record]
        async_datalake.get_annotation_record = AsyncMock(return_value=record)
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        updated = await async_datalake.update_annotation_record(record.annotation_id, source={"type": "machine", "name": "det"})
        assert updated.source.type == "machine"
        await async_datalake.delete_annotation_record(record.annotation_id)
        assert annotation_set.annotation_record_ids == []
        record.annotation_set_id = None
        await async_datalake.delete_annotation_record(record.annotation_id)

    @pytest.mark.asyncio
    async def test_annotation_getters_raise_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_annotation_set("missing")
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_annotation_record("missing")

    @pytest.mark.asyncio
    async def test_datum_crud_async(self, async_datalake, mock_odm):
        datum = await async_datalake.create_datum(asset_refs={"image": "asset_1"}, split="train", metadata={"source": "demo"}, annotation_set_ids=["set_1"])
        assert isinstance(datum, Datum)
        datum.id = "db-datum"
        mock_odm.find.return_value = [datum]
        assert await async_datalake.get_datum(datum.datum_id) is datum
        assert await async_datalake.list_datums({"split": "train"}) == [datum]
        updated = await async_datalake.update_datum(datum.datum_id, metadata={"source": "updated"})
        assert updated.metadata == {"source": "updated"}

    @pytest.mark.asyncio
    async def test_get_datum_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_datum("missing")

    @pytest.mark.asyncio
    async def test_dataset_version_async(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        created = await async_datalake.create_dataset_version(dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"])
        assert isinstance(created, DatasetVersion)
        existing = DatasetVersion(dataset_name="demo", version="0.1.0")
        mock_odm.find.return_value = [existing]
        with pytest.raises(ValueError):
            await async_datalake.create_dataset_version(dataset_name="demo", version="0.1.0", manifest=[])

    @pytest.mark.asyncio
    async def test_dataset_version_get_list_and_resolve(self, async_datalake, mock_odm):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"])
        mock_odm.find.return_value = [dataset_version]
        assert await async_datalake.get_dataset_version("demo", "0.1.0") is dataset_version
        assert await async_datalake.list_dataset_versions(filters={"metadata.stage": "initial"}) == [dataset_version]
        assert await async_datalake.list_dataset_versions(dataset_name="demo", filters={"metadata.stage": "initial"}) == [dataset_version]
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
