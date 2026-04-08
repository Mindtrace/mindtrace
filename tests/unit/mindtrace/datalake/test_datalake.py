import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
)


class TestDatalakeSyncFacade:
    @pytest.fixture
    def mock_backend(self):
        backend = MagicMock()
        backend.store = MagicMock()
        backend.store.default_mount = "temp"
        backend.store.list_mount_info.return_value = {"temp": {"backend": "file:///tmp", "mutable": True}}
        backend.mongo_db_uri = "mongodb://test:27017"
        backend.mongo_db_name = "test_db"
        for name, value in {
            "initialize": None,
            "get_health": {"status": "ok", "database": "test_db", "default_mount": "temp"},
            "put_object": StorageRef(mount="temp", name="hopper.png", version="v1"),
            "get_object": b"payload",
            "head_object": {"size": 123},
            "copy_object": StorageRef(mount="archive", name="hopper.png", version="v2"),
            "create_asset": Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")),
            "get_asset": Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")),
            "list_assets": [],
            "update_asset_metadata": Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")),
            "delete_asset": None,
            "create_annotation_set": AnnotationSet(name="gt", purpose="ground_truth", source_type="human"),
            "get_annotation_set": AnnotationSet(name="gt", purpose="ground_truth", source_type="human"),
            "list_annotation_sets": [],
            "add_annotation_records": [],
            "get_annotation_record": AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}),
            "list_annotation_records": [],
            "update_annotation_record": AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}),
            "delete_annotation_record": None,
            "create_datum": Datum(asset_refs={"image": "asset_1"}),
            "get_datum": Datum(asset_refs={"image": "asset_1"}),
            "list_datums": [],
            "update_datum": Datum(asset_refs={"image": "asset_1"}),
            "create_dataset_version": DatasetVersion(dataset_name="demo", version="0.1.0"),
            "get_dataset_version": DatasetVersion(dataset_name="demo", version="0.1.0"),
            "list_dataset_versions": [],
            "resolve_datum": ResolvedDatum(datum=Datum(asset_refs={"image": "asset_1"})),
            "resolve_dataset_version": ResolvedDatasetVersion(dataset_version=DatasetVersion(dataset_name="demo", version="0.1.0"), datums=[]),
            "create_asset_from_object": Asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")),
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

    def test_sync_facade_basic_methods(self, datalake, mock_backend):
        datalake.initialize()
        assert datalake.get_health()["status"] == "ok"
        assert datalake.get_mounts()["default_mount"] == "temp"
        assert datalake.put_object(name="hopper.png", obj=b"bytes").version == "v1"
        assert datalake.get_object(StorageRef(mount="temp", name="hopper.png", version="v1")) == b"payload"
        assert datalake.head_object(StorageRef(mount="temp", name="hopper.png", version="v1")) == {"size": 123}
        assert datalake.copy_object(StorageRef(mount="temp", name="hopper.png", version="v1"), target_mount="archive", target_name="hopper.png").version == "v2"
        assert isinstance(datalake.create_asset(kind="image", media_type="image/png", storage_ref=StorageRef(mount="temp", name="hopper.png")), Asset)
        assert isinstance(datalake.get_asset("asset_1"), Asset)
        assert datalake.list_assets() == []
        assert isinstance(datalake.update_asset_metadata("asset_1", {"source": "demo"}), Asset)
        datalake.delete_asset("asset_1")
        assert isinstance(datalake.create_annotation_set(name="gt", purpose="ground_truth", source_type="human"), AnnotationSet)
        assert isinstance(datalake.get_annotation_set("set_1"), AnnotationSet)
        assert datalake.list_annotation_sets() == []
        assert datalake.add_annotation_records("set_1", []) == []
        assert isinstance(datalake.get_annotation_record("ann_1"), AnnotationRecord)
        assert datalake.list_annotation_records() == []
        assert isinstance(datalake.update_annotation_record("ann_1", label="dent"), AnnotationRecord)
        datalake.delete_annotation_record("ann_1")
        assert isinstance(datalake.create_datum(asset_refs={"image": "asset_1"}), Datum)
        assert isinstance(datalake.get_datum("datum_1"), Datum)
        assert datalake.list_datums() == []
        assert isinstance(datalake.update_datum("datum_1", split="train"), Datum)
        assert isinstance(datalake.create_dataset_version(dataset_name="demo", version="0.1.0", manifest=[]), DatasetVersion)
        assert isinstance(datalake.get_dataset_version("demo", "0.1.0"), DatasetVersion)
        assert datalake.list_dataset_versions() == []
        assert isinstance(datalake.resolve_datum("datum_1"), ResolvedDatum)
        assert isinstance(datalake.resolve_dataset_version("demo", "0.1.0"), ResolvedDatasetVersion)
        assert isinstance(datalake.create_asset_from_object(name="hopper.png", obj=b"bytes", kind="image", media_type="image/png"), Asset)
        mock_backend.initialize.assert_awaited_once()
