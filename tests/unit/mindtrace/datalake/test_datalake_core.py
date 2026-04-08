import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import Datalake
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


class TestDatalakeUnit:
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
    def datalake(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_odm):
            return Datalake("mongodb://test:27017", "test_db", store=mock_store)

    def test_init_raises_when_store_and_mounts_both_provided(self, mock_store):
        with pytest.raises(ValueError, match="Provide either store or mounts, not both"):
            Datalake(
                "mongodb://test:27017",
                "test_db",
                store=mock_store,
                mounts=[MagicMock()],
            )

    def test_init_builds_store_from_mounts(self, mock_odm):
        fake_store = MagicMock()
        with (
            patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_odm),
            patch("mindtrace.datalake.datalake.Store.from_mounts", return_value=fake_store) as from_mounts,
        ):
            datalake = Datalake("mongodb://test:27017", "test_db", mounts=[MagicMock()], default_mount="nas")

        assert datalake.store == fake_store
        from_mounts.assert_called_once()

    def test_init_builds_default_store_when_not_provided(self, mock_odm):
        fake_store = MagicMock()
        with (
            patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_odm),
            patch("mindtrace.datalake.datalake.Store", return_value=fake_store) as store_cls,
        ):
            datalake = Datalake("mongodb://test:27017", "test_db", default_mount="nas")

        assert datalake.store == fake_store
        store_cls.assert_called_once_with(default_mount="nas")

    def test_run_async_raises_inside_event_loop(self, datalake):
        async def inner():
            with pytest.raises(RuntimeError, match="use the async 'a...' variant"):
                datalake.initialize()

        asyncio.run(inner())

    @pytest.mark.asyncio
    async def test_ainitialize_initializes_all_odms(self, datalake, mock_odm):
        await datalake.ainitialize()
        assert mock_odm.initialize.await_count == 5

    def test_initialize_sync_wrapper(self, datalake, mock_odm):
        datalake.initialize()
        assert mock_odm.initialize.await_count == 5

    @pytest.mark.asyncio
    async def test_acreate_classmethod_initializes_instance(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_odm):
            created = await Datalake.acreate(
                "mongodb://test:27017",
                "test_db",
                store=mock_store,
            )

        assert isinstance(created, Datalake)
        assert created.store == mock_store
        assert mock_odm.initialize.await_count == 5

    def test_create_sync_wrapper(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_odm):
            created = Datalake.create(
                "mongodb://test:27017",
                "test_db",
                store=mock_store,
            )

        assert isinstance(created, Datalake)
        assert created.store == mock_store

    def test_utc_now_returns_timezone_aware_datetime(self, datalake):
        now = datalake._utc_now()
        assert now.tzinfo is not None

    def test_build_document_uses_model_construct(self, datalake):
        class Dummy:
            @classmethod
            def model_construct(cls, **data):
                return data

        assert datalake._build_document(Dummy, a=1) == {"a": 1}

    @pytest.mark.asyncio
    async def test_aget_health_returns_expected_payload(self, datalake):
        health = await datalake.aget_health()
        assert health == {"status": "ok", "database": "test_db", "default_mount": "temp"}

    def test_get_health_sync_wrapper(self, datalake):
        health = datalake.get_health()
        assert health == {"status": "ok", "database": "test_db", "default_mount": "temp"}

    def test_get_mounts_returns_named_mounts(self, datalake):
        mounts = datalake.get_mounts()
        assert mounts["default_mount"] == "temp"
        assert mounts["mounts"][0]["name"] == "temp"
        assert mounts["mounts"][0]["backend"] == "file:///tmp/mindtrace-store-test"

    @pytest.mark.asyncio
    async def test_aput_object_returns_storage_ref(self, datalake, mock_store):
        ref = await datalake.aput_object(name="images/cat.jpg", obj=b"bytes", mount="nas")
        assert isinstance(ref, StorageRef)
        assert ref.mount == "nas"
        assert ref.name == "images/cat.jpg"
        assert ref.version == "v1"
        mock_store.save.assert_called_once()

    def test_put_object_sync_wrapper(self, datalake):
        ref = datalake.put_object(name="images/cat.jpg", obj=b"bytes", mount="nas")
        assert ref.mount == "nas"

    @pytest.mark.asyncio
    async def test_aput_object_uses_default_mount_and_falls_back_to_latest(self, datalake, mock_store):
        mock_store.save.return_value = None
        ref = await datalake.aput_object(name="images/cat.jpg", obj=b"bytes")
        assert ref.mount == "temp"
        assert ref.version == "latest"

    @pytest.mark.asyncio
    async def test_aget_object_loads_from_store(self, datalake, mock_store):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        payload = await datalake.aget_object(ref, verify="none")
        assert payload == b"payload"
        mock_store.load.assert_called_once_with("nas/images/cat.jpg@v1", version="v1", verify="none")

    def test_get_object_sync_wrapper(self, datalake):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        payload = datalake.get_object(ref, verify="none")
        assert payload == b"payload"

    @pytest.mark.asyncio
    async def test_ahead_object_returns_store_info(self, datalake, mock_store):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        info = await datalake.ahead_object(ref)
        assert info == {"size": 123}
        mock_store.info.assert_called_once_with("nas/images/cat.jpg@v1", version="v1")

    def test_head_object_sync_wrapper(self, datalake):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        info = datalake.head_object(ref)
        assert info == {"size": 123}

    @pytest.mark.asyncio
    async def test_acopy_object_returns_new_storage_ref(self, datalake, mock_store):
        source = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        copied = await datalake.acopy_object(source, target_mount="archive", target_name="cat.jpg", target_version="v2")
        assert copied.mount == "archive"
        assert copied.name == "cat.jpg"
        assert copied.version == "v2"

    def test_copy_object_sync_wrapper(self, datalake):
        source = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        copied = datalake.copy_object(source, target_mount="archive", target_name="cat.jpg", target_version="v2")
        assert copied.mount == "archive"
        assert copied.version == "v2"

    @pytest.mark.asyncio
    async def test_acreate_asset_inserts_asset_model(self, datalake, mock_odm):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        asset = await datalake.acreate_asset(
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
        assert asset.kind == "image"
        assert asset.storage_ref.mount == "nas"
        assert asset.checksum == "sha256:abc"
        assert asset.size_bytes == 123
        assert asset.subject == SubjectRef(kind="asset", id="asset_0")
        assert asset.metadata == {"source": "demo"}
        assert asset.created_by == "tester"
        mock_odm.insert.assert_awaited()

    def test_create_asset_sync_wrapper(self, datalake):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        asset = datalake.create_asset(kind="image", media_type="image/jpeg", storage_ref=ref)
        assert isinstance(asset, Asset)

    @pytest.mark.asyncio
    async def test_aget_asset_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError, match="Asset with asset_id missing not found"):
            await datalake.aget_asset("missing")

    @pytest.mark.asyncio
    async def test_asset_crud_async(self, datalake, mock_odm):
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        asset.id = "db-id"
        mock_odm.find.return_value = [asset]
        fetched = await datalake.aget_asset(asset.asset_id)
        listed = await datalake.alist_assets({"kind": "image"})
        updated = await datalake.aupdate_asset_metadata(asset.asset_id, {"source": "demo"})
        await datalake.adelete_asset(asset.asset_id)
        assert fetched is asset
        assert listed == [asset]
        assert updated.metadata == {"source": "demo"}
        mock_odm.delete.assert_awaited_once_with("db-id")

    def test_asset_crud_sync_wrappers(self, datalake, mock_odm):
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        asset.id = "db-id"
        mock_odm.find.return_value = [asset]
        assert datalake.get_asset(asset.asset_id) is asset
        assert datalake.list_assets({"kind": "image"}) == [asset]
        updated = datalake.update_asset_metadata(asset.asset_id, {"source": "demo"})
        assert updated.metadata == {"source": "demo"}
        datalake.delete_asset(asset.asset_id)
        mock_odm.delete.assert_awaited_with("db-id")

    @pytest.mark.asyncio
    async def test_acreate_annotation_set_for_datum_updates_parent(self, datalake, mock_odm):
        datum = Datum(asset_refs={"image": "asset_123"})
        datalake.aget_datum = AsyncMock(return_value=datum)
        inserted_set = await datalake.acreate_annotation_set(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            datum_id=datum.datum_id,
        )
        assert isinstance(inserted_set, AnnotationSet)
        assert inserted_set.datum_id == datum.datum_id
        assert inserted_set.annotation_set_id in datum.annotation_set_ids
        mock_odm.update.assert_awaited()

    @pytest.mark.asyncio
    async def test_acreate_annotation_set_without_datum_does_not_update_parent(self, datalake, mock_odm):
        created = await datalake.acreate_annotation_set(name="predictions", purpose="prediction", source_type="machine")
        assert created.datum_id is None
        assert mock_odm.update.await_count == 0

    def test_create_annotation_set_sync_wrapper(self, datalake):
        created = datalake.create_annotation_set(name="predictions", purpose="prediction", source_type="machine")
        assert isinstance(created, AnnotationSet)

    @pytest.mark.asyncio
    async def test_aget_annotation_set_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError, match="AnnotationSet with annotation_set_id missing not found"):
            await datalake.aget_annotation_set("missing")

    @pytest.mark.asyncio
    async def test_alist_annotation_sets_returns_matches(self, datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        mock_odm.find.return_value = [annotation_set]
        results = await datalake.alist_annotation_sets({"purpose": "ground_truth"})
        assert results == [annotation_set]

    def test_annotation_set_get_and_list_sync_wrappers(self, datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        mock_odm.find.return_value = [annotation_set]
        assert datalake.get_annotation_set(annotation_set.annotation_set_id) is annotation_set
        assert datalake.list_annotation_sets({"purpose": "ground_truth"}) == [annotation_set]

    @pytest.mark.asyncio
    async def test_aadd_annotation_records_supports_dict_and_model_instances(self, datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_record_ids = []
        datalake.aget_annotation_set = AsyncMock(return_value=annotation_set)
        inserted_model = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1})
        inserted_model.annotation_id = "annotation_model"
        inserted_dict = AnnotationRecord(kind="bbox", label="crack", source={"type": "machine", "name": "detector"}, geometry={"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4})
        inserted_dict.annotation_id = "annotation_dict"
        mock_odm.insert = AsyncMock(side_effect=[inserted_model, inserted_dict])
        record_instance = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1})
        inserted = await datalake.aadd_annotation_records(
            annotation_set.annotation_set_id,
            [record_instance, {"kind": "bbox", "label": "crack", "source": {"type": "machine", "name": "detector"}, "geometry": {"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4}, "attributes": {"severity": "high"}}],
        )
        assert inserted == [inserted_model, inserted_dict]
        assert record_instance.annotation_set_id == annotation_set.annotation_set_id
        assert annotation_set.annotation_record_ids == ["annotation_model", "annotation_dict"]
        mock_odm.update.assert_awaited()

    def test_add_annotation_records_sync_wrapper(self, datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_record_ids = []
        datalake.aget_annotation_set = AsyncMock(return_value=annotation_set)
        inserted = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1})
        inserted.annotation_id = "annotation_sync"
        mock_odm.insert = AsyncMock(return_value=inserted)
        result = datalake.add_annotation_records(annotation_set.annotation_set_id, [{"kind": "bbox", "label": "dent", "source": {"type": "human", "name": "review-ui"}}])
        assert result == [inserted]

    @pytest.mark.asyncio
    async def test_annotation_record_crud_async(self, datalake, mock_odm):
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1})
        record.id = "db-rec"
        record.annotation_set_id = "set-1"
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set-1"
        annotation_set.annotation_record_ids = [record.annotation_id]
        mock_odm.find.return_value = [record]
        datalake.aget_annotation_record = AsyncMock(return_value=record)
        datalake.aget_annotation_set = AsyncMock(return_value=annotation_set)
        listed = await datalake.alist_annotation_records({"label": "dent"})
        updated = await datalake.aupdate_annotation_record(record.annotation_id, source={"type": "machine", "name": "det"})
        await datalake.adelete_annotation_record(record.annotation_id)
        assert listed == [record]
        assert updated.source.type == "machine"
        assert annotation_set.annotation_record_ids == []
        mock_odm.delete.assert_awaited_once_with("db-rec")

    def test_annotation_record_sync_wrappers(self, datalake, mock_odm):
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1})
        record.id = "db-rec"
        record.annotation_set_id = "set-1"
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set-1"
        annotation_set.annotation_record_ids = [record.annotation_id]
        mock_odm.find.return_value = [record]
        datalake.aget_annotation_record = AsyncMock(return_value=record)
        datalake.aget_annotation_set = AsyncMock(return_value=annotation_set)
        assert datalake.get_annotation_record(record.annotation_id) is record
        assert datalake.list_annotation_records({"label": "dent"}) == [record]
        updated = datalake.update_annotation_record(record.annotation_id, source={"type": "machine", "name": "det"})
        assert updated.source.type == "machine"
        datalake.delete_annotation_record(record.annotation_id)
        mock_odm.delete.assert_awaited_with("db-rec")

    @pytest.mark.asyncio
    async def test_adelete_annotation_record_without_annotation_set_only_deletes_record(self, datalake, mock_odm):
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1})
        record.id = "db-rec"
        record.annotation_set_id = None
        datalake.aget_annotation_record = AsyncMock(return_value=record)
        await datalake.adelete_annotation_record(record.annotation_id)
        mock_odm.delete.assert_awaited_once_with("db-rec")

    @pytest.mark.asyncio
    async def test_datum_crud_async(self, datalake, mock_odm):
        datum = await datalake.acreate_datum(asset_refs={"image": "asset_1"}, split="train", metadata={"source": "demo"}, annotation_set_ids=["set_1"])
        assert isinstance(datum, Datum)
        assert datum.asset_refs == {"image": "asset_1"}
        datum.id = "db-datum"
        mock_odm.find.return_value = [datum]
        fetched = await datalake.aget_datum(datum.datum_id)
        listed = await datalake.alist_datums({"split": "train"})
        updated = await datalake.aupdate_datum(datum.datum_id, metadata={"source": "updated"})
        assert fetched is datum
        assert listed == [datum]
        assert updated.metadata == {"source": "updated"}

    def test_datum_sync_wrappers(self, datalake, mock_odm):
        datum = datalake.create_datum(asset_refs={"image": "asset_1"}, split="train", metadata={"source": "demo"})
        assert isinstance(datum, Datum)
        datum.id = "db-datum"
        mock_odm.find.return_value = [datum]
        assert datalake.get_datum(datum.datum_id) is datum
        assert datalake.list_datums({"split": "train"}) == [datum]
        updated = datalake.update_datum(datum.datum_id, metadata={"source": "updated"})
        assert updated.metadata == {"source": "updated"}

    @pytest.mark.asyncio
    async def test_aget_datum_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError, match="Datum with datum_id missing not found"):
            await datalake.aget_datum("missing")

    @pytest.mark.asyncio
    async def test_dataset_version_async(self, datalake, mock_odm):
        mock_odm.find.return_value = []
        dataset_version = await datalake.acreate_dataset_version(dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"])
        assert isinstance(dataset_version, DatasetVersion)
        assert dataset_version.dataset_name == "demo"
        assert dataset_version.manifest == ["datum_1", "datum_2"]

    @pytest.mark.asyncio
    async def test_acreate_dataset_version_raises_when_duplicate_exists(self, datalake, mock_odm):
        existing = DatasetVersion(dataset_name="demo", version="0.1.0")
        mock_odm.find.return_value = [existing]
        with pytest.raises(ValueError, match="Dataset version already exists: demo@0.1.0"):
            await datalake.acreate_dataset_version(dataset_name="demo", version="0.1.0", manifest=[])

    @pytest.mark.asyncio
    async def test_dataset_version_list_get_async(self, datalake, mock_odm):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0")
        mock_odm.find.return_value = [dataset_version]
        fetched = await datalake.aget_dataset_version("demo", "0.1.0")
        listed_all = await datalake.alist_dataset_versions(filters={"metadata.stage": "initial"})
        listed_named = await datalake.alist_dataset_versions(dataset_name="demo", filters={"metadata.stage": "initial"})
        assert fetched is dataset_version
        assert listed_all == [dataset_version]
        assert listed_named == [dataset_version]

    def test_dataset_version_sync_wrappers(self, datalake, mock_odm):
        mock_odm.find.return_value = []
        created = datalake.create_dataset_version(dataset_name="demo", version="0.1.0", manifest=["datum_1"])
        assert isinstance(created, DatasetVersion)
        mock_odm.find.return_value = [created]
        assert datalake.get_dataset_version("demo", "0.1.0") is created
        assert datalake.list_dataset_versions(dataset_name="demo", filters={"metadata.stage": "initial"}) == [created]

    @pytest.mark.asyncio
    async def test_aget_dataset_version_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError, match="DatasetVersion demo@0.1.0 not found"):
            await datalake.aget_dataset_version("demo", "0.1.0")

    @pytest.mark.asyncio
    async def test_aresolve_datum_collects_assets_and_annotations(self, datalake):
        datum = Datum(asset_refs={"image": "asset_1"}, annotation_set_ids=["set_1"])
        datum.datum_id = "datum_1"
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set_1"
        annotation_set.annotation_record_ids = ["annotation_1"]
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1})
        datalake.aget_datum = AsyncMock(return_value=datum)
        datalake.aget_asset = AsyncMock(return_value=asset)
        datalake.aget_annotation_set = AsyncMock(return_value=annotation_set)
        datalake.aget_annotation_record = AsyncMock(return_value=record)
        resolved = await datalake.aresolve_datum("datum_1")
        assert isinstance(resolved, ResolvedDatum)
        assert resolved.assets == {"image": asset}
        assert resolved.annotation_sets == [annotation_set]
        assert resolved.annotation_records == {"set_1": [record]}

    def test_resolve_datum_sync_wrapper(self, datalake):
        datum = Datum(asset_refs={"image": "asset_1"}, annotation_set_ids=[])
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        datalake.aget_datum = AsyncMock(return_value=datum)
        datalake.aget_asset = AsyncMock(return_value=asset)
        resolved = datalake.resolve_datum("datum_1")
        assert isinstance(resolved, ResolvedDatum)
        assert resolved.assets == {"image": asset}

    @pytest.mark.asyncio
    async def test_aresolve_dataset_version_builds_resolved_dataset(self, datalake):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"])
        resolved_datum_1 = ResolvedDatum(datum=Datum(asset_refs={"image": "asset_1"}))
        resolved_datum_2 = ResolvedDatum(datum=Datum(asset_refs={"image": "asset_2"}))
        datalake.aget_dataset_version = AsyncMock(return_value=dataset_version)
        datalake.aresolve_datum = AsyncMock(side_effect=[resolved_datum_1, resolved_datum_2])
        resolved = await datalake.aresolve_dataset_version("demo", "0.1.0")
        assert isinstance(resolved, ResolvedDatasetVersion)
        assert resolved.dataset_version is dataset_version
        assert resolved.datums == [resolved_datum_1, resolved_datum_2]

    def test_resolve_dataset_version_sync_wrapper(self, datalake):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=["datum_1"])
        resolved_datum = ResolvedDatum(datum=Datum(asset_refs={"image": "asset_1"}))
        datalake.aget_dataset_version = AsyncMock(return_value=dataset_version)
        datalake.aresolve_datum = AsyncMock(return_value=resolved_datum)
        resolved = datalake.resolve_dataset_version("demo", "0.1.0")
        assert isinstance(resolved, ResolvedDatasetVersion)
        assert resolved.datums == [resolved_datum]

    @pytest.mark.asyncio
    async def test_acreate_asset_from_object_chains_put_and_create(self, datalake):
        storage_ref = StorageRef(mount="temp", name="images/example.jpg", version="v1")
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)
        datalake.aput_object = AsyncMock(return_value=storage_ref)
        datalake.acreate_asset = AsyncMock(return_value=asset)
        created = await datalake.acreate_asset_from_object(
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
        datalake.aput_object.assert_awaited_once()
        datalake.acreate_asset.assert_awaited_once_with(
            kind="image",
            media_type="image/jpeg",
            storage_ref=storage_ref,
            checksum="sha256:abc",
            size_bytes=12,
            subject=SubjectRef(kind="asset", id="asset_0"),
            metadata={"source": "demo"},
            created_by="tester",
        )

    def test_create_asset_from_object_sync_wrapper(self, datalake):
        storage_ref = StorageRef(mount="temp", name="images/example.jpg", version="v1")
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)
        datalake.aput_object = AsyncMock(return_value=storage_ref)
        datalake.acreate_asset = AsyncMock(return_value=asset)
        created = datalake.create_asset_from_object(name="images/example.jpg", obj=b"bytes", kind="image", media_type="image/jpeg")
        assert created is asset
