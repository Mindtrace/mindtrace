from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import AnnotationSet, Asset, DatasetVersion, Datum, StorageRef


class TestDatalakeV3Unit:
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
        return store

    @pytest.fixture
    def datalake(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.datalake.MongoMindtraceODM", return_value=mock_odm):
            return Datalake("mongodb://test:27017", "test_db", store=mock_store)

    @pytest.mark.asyncio
    async def test_initialize_initializes_all_odms(self, datalake, mock_odm):
        await datalake.initialize()
        assert mock_odm.initialize.await_count == 5

    @pytest.mark.asyncio
    async def test_put_object_returns_storage_ref(self, datalake, mock_store):
        ref = await datalake.put_object(name="images/cat.jpg", obj=b"bytes", mount="nas")

        assert isinstance(ref, StorageRef)
        assert ref.mount == "nas"
        assert ref.name == "images/cat.jpg"
        assert ref.version == "v1"
        mock_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_asset_inserts_asset_model(self, datalake, mock_odm):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")

        asset = await datalake.create_asset(kind="image", media_type="image/jpeg", storage_ref=ref)

        assert isinstance(asset, Asset)
        assert asset.kind == "image"
        assert asset.storage_ref.mount == "nas"
        mock_odm.insert.assert_awaited()

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
