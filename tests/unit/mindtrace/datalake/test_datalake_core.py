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

    @pytest.mark.asyncio
    async def test_initialize_initializes_all_odms(self, datalake, mock_odm):
        await datalake.initialize()
        assert mock_odm.initialize.await_count == 5

    @pytest.mark.asyncio
    async def test_create_classmethod_initializes_instance(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_odm):
            created = await Datalake.create(
                "mongodb://test:27017",
                "test_db",
                store=mock_store,
            )

        assert isinstance(created, Datalake)
        assert created.store == mock_store
        assert mock_odm.initialize.await_count == 5

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
    async def test_get_health_returns_expected_payload(self, datalake):
        health = await datalake.get_health()

        assert health == {
            "status": "ok",
            "database": "test_db",
            "default_mount": "temp",
        }

    def test_get_mounts_returns_named_mounts(self, datalake):
        mounts = datalake.get_mounts()

        assert mounts["default_mount"] == "temp"
        assert mounts["mounts"][0]["name"] == "temp"
        assert mounts["mounts"][0]["backend"] == "file:///tmp/mindtrace-store-test"

    @pytest.mark.asyncio
    async def test_put_object_returns_storage_ref(self, datalake, mock_store):
        ref = await datalake.put_object(name="images/cat.jpg", obj=b"bytes", mount="nas")

        assert isinstance(ref, StorageRef)
        assert ref.mount == "nas"
        assert ref.name == "images/cat.jpg"
        assert ref.version == "v1"
        mock_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_put_object_uses_default_mount_and_falls_back_to_latest(self, datalake, mock_store):
        mock_store.save.return_value = None

        ref = await datalake.put_object(name="images/cat.jpg", obj=b"bytes")

        assert ref.mount == "temp"
        assert ref.version == "latest"

    @pytest.mark.asyncio
    async def test_get_object_loads_from_store(self, datalake, mock_store):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")

        payload = await datalake.get_object(ref, verify="none")

        assert payload == b"payload"
        mock_store.load.assert_called_once_with("nas/images/cat.jpg@v1", version="v1", verify="none")

    @pytest.mark.asyncio
    async def test_head_object_returns_store_info(self, datalake, mock_store):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")

        info = await datalake.head_object(ref)

        assert info == {"size": 123}
        mock_store.info.assert_called_once_with("nas/images/cat.jpg@v1", version="v1")

    @pytest.mark.asyncio
    async def test_copy_object_returns_new_storage_ref(self, datalake, mock_store):
        source = StorageRef(mount="nas", name="images/cat.jpg", version="v1")

        copied = await datalake.copy_object(source, target_mount="archive", target_name="cat.jpg", target_version="v2")

        assert copied.mount == "archive"
        assert copied.name == "cat.jpg"
        assert copied.version == "v2"
        mock_store.copy.assert_called_once_with(
            "nas/images/cat.jpg@v1",
            target="archive/cat.jpg@v2",
            source_version="v1",
            target_version="v2",
        )

    @pytest.mark.asyncio
    async def test_create_asset_inserts_asset_model(self, datalake, mock_odm):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")

        asset = await datalake.create_asset(kind="image", media_type="image/jpeg", storage_ref=ref)

        assert isinstance(asset, Asset)
        assert asset.kind == "image"
        assert asset.storage_ref.mount == "nas"
        mock_odm.insert.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_asset_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError, match="Asset with asset_id missing not found"):
            await datalake.get_asset("missing")

    @pytest.mark.asyncio
    async def test_get_and_list_update_delete_asset(self, datalake, mock_odm):
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        asset.id = "db-id"
        mock_odm.find.return_value = [asset]

        fetched = await datalake.get_asset(asset.asset_id)
        listed = await datalake.list_assets({"kind": "image"})
        updated = await datalake.update_asset_metadata(asset.asset_id, {"source": "demo"})
        await datalake.delete_asset(asset.asset_id)

        assert fetched is asset
        assert listed == [asset]
        assert updated.metadata == {"source": "demo"}
        mock_odm.delete.assert_awaited_once_with("db-id")

    @pytest.mark.asyncio
    async def test_create_annotation_set_for_datum_updates_parent(self, datalake, mock_odm):
        datum = Datum(asset_refs={"image": "asset_123"})
        datalake.get_datum = AsyncMock(return_value=datum)

        inserted_set = await datalake.create_annotation_set(
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
    async def test_create_annotation_set_without_datum_does_not_update_parent(self, datalake, mock_odm):
        created = await datalake.create_annotation_set(
            name="predictions",
            purpose="prediction",
            source_type="machine",
        )

        assert created.datum_id is None
        assert mock_odm.update.await_count == 0

    @pytest.mark.asyncio
    async def test_get_annotation_set_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError, match="AnnotationSet with annotation_set_id missing not found"):
            await datalake.get_annotation_set("missing")

    @pytest.mark.asyncio
    async def test_list_annotation_sets_returns_matches(self, datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        mock_odm.find.return_value = [annotation_set]

        results = await datalake.list_annotation_sets({"purpose": "ground_truth"})

        assert results == [annotation_set]

    @pytest.mark.asyncio
    async def test_add_annotation_records_supports_dict_and_model_instances(self, datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_record_ids = []
        datalake.get_annotation_set = AsyncMock(return_value=annotation_set)

        inserted_model = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
        )
        inserted_model.annotation_id = "annotation_model"
        inserted_dict = AnnotationRecord(
            kind="bbox",
            label="crack",
            source={"type": "machine", "name": "detector"},
            geometry={"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_dict.annotation_id = "annotation_dict"

        mock_odm.insert = AsyncMock(side_effect=[inserted_model, inserted_dict])

        record_instance = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
        )

        inserted = await datalake.add_annotation_records(
            annotation_set.annotation_set_id,
            [
                record_instance,
                {
                    "kind": "bbox",
                    "label": "crack",
                    "source": {"type": "machine", "name": "detector"},
                    "geometry": {"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4},
                    "attributes": {"severity": "high"},
                },
            ],
        )

        assert inserted == [inserted_model, inserted_dict]
        assert record_instance.annotation_set_id == annotation_set.annotation_set_id
        assert annotation_set.annotation_record_ids == ["annotation_model", "annotation_dict"]
        mock_odm.update.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_annotation_record_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError, match="AnnotationRecord with annotation_id missing not found"):
            await datalake.get_annotation_record("missing")

    @pytest.mark.asyncio
    async def test_list_update_delete_annotation_record(self, datalake, mock_odm):
        record = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
        )
        record.id = "db-rec"
        record.annotation_set_id = "set-1"
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set-1"
        annotation_set.annotation_record_ids = [record.annotation_id]
        datalake.get_annotation_record = AsyncMock(return_value=record)
        datalake.get_annotation_set = AsyncMock(return_value=annotation_set)

        listed = await datalake.list_annotation_records({"label": "dent"})
        updated = await datalake.update_annotation_record(record.annotation_id, source={"type": "machine", "name": "det"})
        await datalake.delete_annotation_record(record.annotation_id)

        assert listed == []
        assert updated.source.type == "machine"
        assert annotation_set.annotation_record_ids == []
        mock_odm.delete.assert_awaited_once_with("db-rec")

    @pytest.mark.asyncio
    async def test_delete_annotation_record_without_annotation_set_only_deletes_record(self, datalake, mock_odm):
        record = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
        )
        record.id = "db-rec"
        record.annotation_set_id = None
        datalake.get_annotation_record = AsyncMock(return_value=record)

        await datalake.delete_annotation_record(record.annotation_id)

        mock_odm.delete.assert_awaited_once_with("db-rec")

    @pytest.mark.asyncio
    async def test_create_get_list_update_datum(self, datalake, mock_odm):
        datum = await datalake.create_datum(
            asset_refs={"image": "asset_1"},
            split="train",
            metadata={"source": "demo"},
            annotation_set_ids=["set_1"],
        )

        assert isinstance(datum, Datum)
        assert datum.asset_refs == {"image": "asset_1"}
        assert datum.annotation_set_ids == ["set_1"]

        datum.id = "db-datum"
        mock_odm.find.return_value = [datum]
        fetched = await datalake.get_datum(datum.datum_id)
        listed = await datalake.list_datums({"split": "train"})
        updated = await datalake.update_datum(datum.datum_id, metadata={"source": "updated"})

        assert fetched is datum
        assert listed == [datum]
        assert updated.metadata == {"source": "updated"}

    @pytest.mark.asyncio
    async def test_get_datum_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError, match="Datum with datum_id missing not found"):
            await datalake.get_datum("missing")

    @pytest.mark.asyncio
    async def test_create_dataset_version_returns_immutable_manifest_record(self, datalake, mock_odm):
        mock_odm.find.return_value = []
        dataset_version = await datalake.create_dataset_version(
            dataset_name="demo",
            version="0.1.0",
            manifest=["datum_1", "datum_2"],
        )

        assert isinstance(dataset_version, DatasetVersion)
        assert dataset_version.dataset_name == "demo"
        assert dataset_version.manifest == ["datum_1", "datum_2"]

    @pytest.mark.asyncio
    async def test_create_dataset_version_raises_when_duplicate_exists(self, datalake, mock_odm):
        existing = DatasetVersion(dataset_name="demo", version="0.1.0")
        mock_odm.find.return_value = [existing]

        with pytest.raises(ValueError, match="Dataset version already exists: demo@0.1.0"):
            await datalake.create_dataset_version(
                dataset_name="demo",
                version="0.1.0",
                manifest=[],
            )

    @pytest.mark.asyncio
    async def test_get_list_dataset_versions(self, datalake, mock_odm):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0")
        mock_odm.find.return_value = [dataset_version]

        fetched = await datalake.get_dataset_version("demo", "0.1.0")
        listed_all = await datalake.list_dataset_versions(filters={"metadata.stage": "initial"})
        listed_named = await datalake.list_dataset_versions(dataset_name="demo", filters={"metadata.stage": "initial"})

        assert fetched is dataset_version
        assert listed_all == [dataset_version]
        assert listed_named == [dataset_version]
        assert mock_odm.find.await_args_list[-1].args[0]["dataset_name"] == "demo"

    @pytest.mark.asyncio
    async def test_get_dataset_version_raises_when_missing(self, datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError, match="DatasetVersion demo@0.1.0 not found"):
            await datalake.get_dataset_version("demo", "0.1.0")

    @pytest.mark.asyncio
    async def test_resolve_datum_collects_assets_and_annotations(self, datalake):
        datum = Datum(asset_refs={"image": "asset_1"}, annotation_set_ids=["set_1"])
        datum.datum_id = "datum_1"
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set_1"
        annotation_set.annotation_record_ids = ["annotation_1"]
        record = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
        )

        datalake.get_datum = AsyncMock(return_value=datum)
        datalake.get_asset = AsyncMock(return_value=asset)
        datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        datalake.get_annotation_record = AsyncMock(return_value=record)

        resolved = await datalake.resolve_datum("datum_1")

        assert isinstance(resolved, ResolvedDatum)
        assert resolved.assets == {"image": asset}
        assert resolved.annotation_sets == [annotation_set]
        assert resolved.annotation_records == {"set_1": [record]}

    @pytest.mark.asyncio
    async def test_resolve_dataset_version_builds_resolved_dataset(self, datalake):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"])
        resolved_datum_1 = MagicMock()
        resolved_datum_2 = MagicMock()
        datalake.get_dataset_version = AsyncMock(return_value=dataset_version)
        datalake.resolve_datum = AsyncMock(side_effect=[resolved_datum_1, resolved_datum_2])

        resolved = await datalake.resolve_dataset_version("demo", "0.1.0")

        assert isinstance(resolved, ResolvedDatasetVersion)
        assert resolved.dataset_version is dataset_version
        assert resolved.datums == [resolved_datum_1, resolved_datum_2]

    @pytest.mark.asyncio
    async def test_create_asset_from_object_chains_put_and_create(self, datalake):
        storage_ref = StorageRef(mount="temp", name="images/example.jpg", version="v1")
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)
        datalake.put_object = AsyncMock(return_value=storage_ref)
        datalake.create_asset = AsyncMock(return_value=asset)

        created = await datalake.create_asset_from_object(
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
        datalake.put_object.assert_awaited_once()
        datalake.create_asset.assert_awaited_once_with(
            kind="image",
            media_type="image/jpeg",
            storage_ref=storage_ref,
            checksum="sha256:abc",
            size_bytes=12,
            subject=SubjectRef(kind="asset", id="asset_0"),
            metadata={"source": "demo"},
            created_by="tester",
        )
