"""Unit tests for :mod:`mindtrace.datalake.data_vault`."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.data_vault import (
    AsyncDataVault,
    DataVault,
    VaultDataset,
    _annotation_id,
    _annotation_source_type,
    _annotations_bound_to_asset,
    _coerce_annotation_payload,
    _dataset_annotation_set_filters,
    _extract_annotation_asset_id,
    _pil_image_to_png_bytes,
)
from mindtrace.datalake.pagination_types import CursorPage, PageInfo
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    Collection,
    CollectionItem,
    StorageRef,
    SubjectRef,
)
from mindtrace.datalake.vault_serialization import (
    SERIALIZATION_METADATA_KEY,
    direct_bytes_serialization_block,
)
from mindtrace.registry import Registry


def test_annotations_bound_to_asset_rejects_non_dict_non_record():
    with pytest.raises(TypeError, match="dicts or AnnotationRecord"):
        _annotations_bound_to_asset([object()], "asset_1")


def test_annotations_bound_to_asset_copies_dict_and_annotation_record():
    merged_dict = _annotations_bound_to_asset(
        [{"kind": "bbox", "label": "a", "source": {"type": "human", "name": "n"}, "geometry": {}}],
        "asset_z",
    )
    assert merged_dict[0]["subject"] == {"kind": "asset", "id": "asset_z"}

    rec = AnnotationRecord(
        kind="bbox",
        label="b",
        source={"type": "human", "name": "n"},
        geometry={},
    )
    merged_rec = _annotations_bound_to_asset([rec], "asset_z")
    assert merged_rec[0].subject == SubjectRef(kind="asset", id="asset_z")


@pytest.mark.asyncio
async def test_async_data_vault_add_and_list_annotations_for_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a_target",
    )
    stored = AnnotationRecord(
        kind="bbox",
        label="x",
        subject=SubjectRef(kind="asset", id="a_target"),
        source={"type": "human", "name": "t"},
        geometry={},
    )
    dl = AsyncMock()
    dl.get_asset_by_alias = AsyncMock(return_value=asset)
    dl.add_annotation_records = AsyncMock(return_value=[stored])
    dl.list_annotation_records_for_asset = AsyncMock(return_value=[stored])

    vault = AsyncDataVault(dl)
    out = await vault.add_annotations_for_asset(
        "my-alias",
        [{"kind": "bbox", "label": "x", "source": {"type": "human", "name": "t"}, "geometry": {}}],
        annotation_set_id="set_42",
    )
    assert out == [stored]
    dl.add_annotation_records.assert_awaited_once()
    args, kwargs = dl.add_annotation_records.await_args
    assert kwargs["annotation_set_id"] == "set_42"
    assert args[0][0]["subject"]["id"] == "a_target"

    listed = await vault.list_annotations_for_asset("my-alias")
    assert listed == [stored]
    dl.list_annotation_records_for_asset.assert_awaited_once_with("a_target")


def test_sync_data_vault_add_and_list_annotations_for_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a_target",
    )
    stored = AnnotationRecord(
        kind="bbox",
        label="x",
        subject=SubjectRef(kind="asset", id="a_target"),
        source={"type": "human", "name": "t"},
        geometry={},
    )
    dl = Mock()
    dl.get_asset_by_alias = Mock(return_value=asset)
    dl.add_annotation_records = Mock(return_value=[stored])
    dl.list_annotation_records_for_asset = Mock(return_value=[stored])

    vault = DataVault(dl)
    out = vault.add_annotations_for_asset(
        "my-alias",
        [{"kind": "bbox", "label": "x", "source": {"type": "human", "name": "t"}, "geometry": {}}],
        annotation_schema_id="sch_1",
    )
    assert out == [stored]
    dl.add_annotation_records.assert_called_once()
    args, kwargs = dl.add_annotation_records.call_args
    assert kwargs["annotation_schema_id"] == "sch_1"
    assert args[0][0]["subject"]["id"] == "a_target"

    listed = vault.list_annotations_for_asset("my-alias")
    assert listed == [stored]
    dl.list_annotation_records_for_asset.assert_called_once_with("a_target")


class _FakeSyncServiceCM:
    """Minimal surface so :func:`looks_like_datalake_service_sync_client` accepts the CM."""

    def assets_get(self, *a, **k):
        raise NotImplementedError

    def assets_list(self, *a, **k):
        raise NotImplementedError

    def assets_list_page(self, *a, **k):
        raise NotImplementedError

    def assets_get_by_alias(self, *a, **k):
        raise NotImplementedError

    def objects_get(self, *a, **k):
        raise NotImplementedError

    def assets_create_from_object(self, *a, **k):
        raise NotImplementedError

    def aliases_add(self, *a, **k):
        raise NotImplementedError


class _FakeAsyncServiceCM:
    """Minimal surface so :func:`looks_like_datalake_service_async_client` accepts the CM."""

    async def aassets_get(self, *a, **k):
        raise NotImplementedError

    async def aassets_list(self, *a, **k):
        raise NotImplementedError

    async def aassets_list_page(self, *a, **k):
        raise NotImplementedError

    async def aassets_get_by_alias(self, *a, **k):
        raise NotImplementedError

    async def aobjects_get(self, *a, **k):
        raise NotImplementedError

    async def aassets_create_from_object(self, *a, **k):
        raise NotImplementedError

    async def aaliases_add(self, *a, **k):
        raise NotImplementedError


def test_data_vault_from_url(monkeypatch):
    fake_cm = _FakeSyncServiceCM()
    captured: dict[str, object] = {}

    def fake_connect(cls, url=None, timeout=60):
        captured["url"] = url
        captured["timeout"] = timeout
        return fake_cm

    monkeypatch.setattr(
        "mindtrace.datalake.data_vault.DatalakeService.connect",
        classmethod(fake_connect),
    )
    vault = DataVault.from_url("http://example:8080", timeout=30, object_name_prefix="prefix")
    assert isinstance(vault, DataVault)
    assert vault._object_name_prefix == "prefix"
    assert captured == {"url": "http://example:8080", "timeout": 30}


def test_async_data_vault_from_url(monkeypatch):
    fake_cm = _FakeAsyncServiceCM()
    captured: dict[str, object] = {}

    def fake_connect(cls, url=None, timeout=60):
        captured["url"] = url
        captured["timeout"] = timeout
        return fake_cm

    monkeypatch.setattr(
        "mindtrace.datalake.data_vault.DatalakeService.connect",
        classmethod(fake_connect),
    )
    vault = AsyncDataVault.from_url("http://async:9090", timeout=45, object_name_prefix="av")
    assert isinstance(vault, AsyncDataVault)
    assert vault._object_name_prefix == "av"
    assert captured == {"url": "http://async:9090", "timeout": 45}


@pytest.mark.asyncio
async def test_async_data_vault_delegates_list_and_get_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="listed",
    )
    backend = AsyncMock()
    backend.list_assets = AsyncMock(return_value=[asset])
    backend.get_asset = AsyncMock(return_value=asset)
    vault = AsyncDataVault(backend)
    assert await vault.list_assets({"kind": "image"}) == [asset]
    backend.list_assets.assert_awaited_once_with({"kind": "image"})
    assert await vault.list_image_assets() == [asset]
    assert backend.list_assets.await_args_list[1].args[0] == {"kind": "image"}
    assert await vault.get_asset("listed") is asset
    backend.get_asset.assert_awaited_once_with("listed")


@pytest.mark.asyncio
async def test_async_data_vault_paged_and_streaming_asset_discovery():
    asset_page = CursorPage(
        items=[
            Asset(
                kind="image",
                media_type="image/png",
                storage_ref=StorageRef(mount="m", name="n-1", version="1"),
                asset_id="listed-1",
            )
        ],
        page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True, total_count=2),
    )
    image_asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n-2", version="1"),
        asset_id="listed-2",
    )
    backend = AsyncMock()
    backend.list_assets_page = AsyncMock(return_value=asset_page)

    async def iter_assets(**kwargs):
        assert kwargs == {"filters": {"kind": "image"}, "sort": "created_desc", "batch_size": 10}
        yield image_asset

    backend.iter_assets = iter_assets

    vault = AsyncDataVault(backend)
    assert await vault.list_assets_page(filters={"kind": "image"}, limit=1, include_total=True) == asset_page
    backend.list_assets_page.assert_awaited_once_with(
        filters={"kind": "image"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=True,
    )

    assert await vault.list_image_assets_page(limit=1) == asset_page
    assert backend.list_assets_page.await_args_list[1].kwargs == {
        "filters": {"kind": "image"},
        "sort": "created_desc",
        "limit": 1,
        "cursor": None,
        "include_total": False,
    }

    assert [asset async for asset in vault.iter_image_assets(batch_size=10)] == [image_asset]


@pytest.mark.asyncio
async def test_async_data_vault_load_by_asset_id_materializes_bytes(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="by-id",
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=b"by-asset-id-payload")
    vault = AsyncDataVault(backend, registry=reg)
    assert await vault.load_by_asset_id("by-id") == b"by-asset-id-payload"
    backend.get_asset.assert_awaited_once_with("by-id")


@pytest.mark.asyncio
async def test_async_data_vault_load_by_asset_id_skips_materialize_when_disabled(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=b"raw")
    vault = AsyncDataVault(backend, registry=reg)
    assert await vault.load_by_asset_id("id-1", materialize=False) == b"raw"


@pytest.mark.asyncio
async def test_async_data_vault_load_by_asset_id_skips_materialize_without_hints(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={},
    )
    backend = Mock()
    backend.get_asset = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=b"nop")
    vault = AsyncDataVault(backend, registry=reg)
    assert await vault.load_by_asset_id("id-2") == b"nop"


@pytest.mark.asyncio
async def test_async_data_vault_load_image_by_asset_id():
    im = Image.new("RGB", (1, 1), color=(3, 4, 5))
    png = _pil_image_to_png_bytes(im)
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="obj", version="1"),
        asset_id="img-async",
    )
    backend = Mock()
    backend.get_asset = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=png)
    vault = AsyncDataVault(backend)
    out = await vault.load_image_by_asset_id("img-async")
    assert out.tobytes() == im.tobytes()


def test_sync_data_vault_delegates_list_and_get_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="listed",
    )
    backend = Mock()
    backend.list_assets = Mock(return_value=[asset])
    backend.get_asset = Mock(return_value=asset)
    vault = DataVault(backend)
    assert vault.list_assets({"kind": "image"}) == [asset]
    backend.list_assets.assert_called_once_with({"kind": "image"})
    assert vault.list_image_assets() == [asset]
    assert backend.list_assets.call_args_list[1].args[0] == {"kind": "image"}
    assert vault.get_asset("listed") is asset
    backend.get_asset.assert_called_once_with("listed")


def test_sync_data_vault_paged_and_streaming_asset_discovery():
    asset_page = CursorPage(
        items=[
            Asset(
                kind="image",
                media_type="image/png",
                storage_ref=StorageRef(mount="m", name="n-1", version="1"),
                asset_id="listed-1",
            )
        ],
        page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True, total_count=2),
    )
    image_asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n-2", version="1"),
        asset_id="listed-2",
    )
    backend = Mock()
    backend.list_assets_page = Mock(return_value=asset_page)
    backend.iter_assets = Mock(return_value=iter([image_asset]))

    vault = DataVault(backend)
    assert vault.list_assets_page(filters={"kind": "image"}, limit=1, include_total=True) == asset_page
    backend.list_assets_page.assert_called_once_with(
        filters={"kind": "image"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=True,
    )

    assert vault.list_image_assets_page(limit=1) == asset_page
    assert backend.list_assets_page.call_args_list[1].kwargs == {
        "filters": {"kind": "image"},
        "sort": "created_desc",
        "limit": 1,
        "cursor": None,
        "include_total": False,
    }

    assert list(vault.iter_image_assets(batch_size=10)) == [image_asset]
    backend.iter_assets.assert_called_once_with(filters={"kind": "image"}, sort="created_desc", batch_size=10)


def test_sync_data_vault_load_image_by_asset_id():
    im = Image.new("RGB", (1, 1), color=(9, 8, 7))
    png = _pil_image_to_png_bytes(im)
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="obj", version="1"),
        asset_id="img-1",
    )
    backend = Mock()
    backend.get_asset = Mock(return_value=asset)
    backend.get_object = Mock(return_value=png)
    vault = DataVault(backend)
    out = vault.load_image_by_asset_id("img-1")
    assert out.tobytes() == im.tobytes()
    backend.get_asset.assert_called_once_with("img-1")


def test_sync_data_vault_load_by_asset_id_skips_materialize_when_disabled(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset = Mock(return_value=asset)
    backend.get_object = Mock(return_value=b"raw")
    vault = DataVault(backend, registry=reg)
    assert vault.load_by_asset_id("id-1", materialize=False) == b"raw"


def test_sync_data_vault_load_by_asset_id_skips_materialize_without_hints(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={},
    )
    backend = Mock()
    backend.get_asset = Mock(return_value=asset)
    backend.get_object = Mock(return_value=b"nop")
    vault = DataVault(backend, registry=reg)
    assert vault.load_by_asset_id("id-2") == b"nop"


def test_sync_data_vault_load_by_asset_id_materializes_bytes(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="by-id",
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset = Mock(return_value=asset)
    backend.get_object = Mock(return_value=b"sync-payload")
    vault = DataVault(backend, registry=reg)
    assert vault.load_by_asset_id("by-id") == b"sync-payload"


def test_data_vault_dataset_helpers_cover_annotation_shapes():
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="x",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    typed = Mock()
    typed.to_payload.return_value = {
        "kind": "bbox",
        "label": "y",
        "subject": {"kind": "asset", "id": "asset_2"},
        "source": {"type": "machine", "name": "model"},
        "geometry": {},
    }

    assert _coerce_annotation_payload(record)["annotation_id"] == "annotation_1"
    assert _coerce_annotation_payload({"kind": "bbox"}) == {"kind": "bbox"}
    assert _coerce_annotation_payload(typed)["label"] == "y"
    with pytest.raises(TypeError, match="annotation must be a dict"):
        _coerce_annotation_payload(object())

    assert _extract_annotation_asset_id({"subject": SubjectRef(kind="asset", id="asset_1")}) == "asset_1"
    assert _extract_annotation_asset_id({"subject": {"kind": "asset", "id": 7}}) == "7"
    assert _extract_annotation_asset_id({"subject": {"kind": "dataset", "id": "d1"}}) is None
    assert _annotation_source_type({"source": {"type": "human"}}) == "human"
    assert _annotation_source_type({"source": {"type": "other"}}) == "mixed"
    assert _annotation_id(record) == "annotation_1"
    assert _annotation_id("annotation_2") == "annotation_2"
    assert _dataset_annotation_set_filters("collection_1", asset_id="asset_1") == {
        "metadata.mindtrace.data_vault.dataset_collection_id": "collection_1",
        "metadata.mindtrace.data_vault.asset_id": "asset_1",
        "status": "active",
    }


def test_sync_data_vault_get_dataset_errors():
    backend = Mock()
    backend.list_collections = Mock(side_effect=[[], [Collection(name="x"), Collection(name="x")]])
    vault = DataVault(backend)

    with pytest.raises(DocumentNotFoundError, match="Dataset 'missing' not found"):
        vault.get_dataset("missing")
    with pytest.raises(ValueError, match="Multiple active datasets matched"):
        vault.get_dataset("duplicate")


def test_sync_data_vault_add_asset_uses_alias_and_updates_existing_item():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    existing = CollectionItem(
        collection_id="collection_1",
        asset_id="asset_1",
        collection_item_id="ci_1",
        split="val",
        metadata={"old": True},
    )
    updated = existing.model_copy(update={"split": "train", "metadata": {"old": True, "new": True}})
    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.get_asset = Mock(side_effect=[DocumentNotFoundError("no direct asset"), asset])
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.list_collection_items = Mock(return_value=[existing])
    backend.update_collection_item = Mock(return_value=updated)

    vault = DataVault(backend)
    out = vault.add_asset("training", "friendly-alias", split="train", metadata={"new": True})

    assert out == asset
    backend.get_asset_by_alias.assert_called_once_with("friendly-alias")
    backend.update_collection_item.assert_called_once_with("ci_1", split="train", metadata={"old": True, "new": True})


def test_sync_data_vault_add_asset_reactivates_existing_item():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    inactive = CollectionItem(
        collection_id="collection_1",
        asset_id="asset_1",
        collection_item_id="ci_1",
        status="removed",
        metadata={"old": True},
    )
    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.get_asset = Mock(return_value=asset)
    backend.list_collection_items = Mock(return_value=[inactive])
    backend.update_collection_item = Mock(return_value=inactive.model_copy(update={"status": "active"}))

    vault = DataVault(backend)
    vault.add_asset("training", "asset_1", metadata={"new": True})

    backend.update_collection_item.assert_called_once_with(
        "ci_1",
        status="active",
        split=None,
        metadata={"old": True, "new": True},
    )


def test_sync_data_vault_add_annotation_from_record_and_missing_subject_error():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
    )
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.get_asset = Mock(return_value=asset)
    backend.list_collection_items = Mock(return_value=[])
    backend.create_collection_item = Mock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    )
    backend.list_annotation_sets = Mock(return_value=[annotation_set])
    backend.add_annotation_records = Mock(return_value=[record])

    vault = DataVault(backend)
    assert vault.add_annotation("training", record) == record
    add_payload = backend.add_annotation_records.call_args.args[0][0]
    assert add_payload["subject"] == {"kind": "asset", "id": "asset_1"}

    with pytest.raises(ValueError, match="must reference an asset subject"):
        vault.add_annotation(
            "training",
            {"kind": "bbox", "label": "cat", "source": {"type": "human", "name": "review"}, "geometry": {}},
        )


def test_sync_data_vault_remove_annotation_missing_ok_and_filtered_annotation_listing():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
    )
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    backend = Mock()
    backend.list_collections = Mock(side_effect=[[collection], [collection], [collection]])
    backend.get_asset = Mock(side_effect=DocumentNotFoundError("no direct asset"))
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.list_annotation_sets = Mock(side_effect=[[], [annotation_set], [annotation_set]])
    backend.get_annotation_record = Mock(return_value=record)
    backend.delete_annotation_record = Mock()

    vault = DataVault(backend)
    vault.remove_annotation("training", "annotation_2", missing_ok=True)
    assert vault.list_dataset_annotations("training", asset="friendly-alias") == [record]
    vault.remove_annotation("training", record)
    backend.delete_annotation_record.assert_called_once_with("annotation_1")


def test_sync_data_vault_duplicate_create_and_missing_remove_errors():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    backend = Mock()
    backend.list_collections = Mock(side_effect=[[collection], [collection], [collection]])
    backend.get_asset = Mock(return_value=asset)
    backend.list_collection_items = Mock(return_value=[])
    backend.list_annotation_sets = Mock(return_value=[])
    vault = DataVault(backend)

    with pytest.raises(ValueError, match="already exists"):
        vault.create_dataset("training")
    with pytest.raises(DocumentNotFoundError, match="not part of dataset"):
        vault.remove_asset("training", "asset_1")
    with pytest.raises(DocumentNotFoundError, match="not part of dataset"):
        vault.remove_annotation("training", "annotation_1")


def test_sync_data_vault_internal_asset_and_dataset_shortcuts():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    vault = DataVault(backend)
    dataset = VaultDataset(
        dataset_id="collection_1",
        name="training",
        description=None,
        status="active",
        metadata={},
        asset_count=0,
        created_at=collection.created_at,
        created_by=None,
        updated_at=collection.updated_at,
    )

    assert vault._resolve_asset_id(asset) == "asset_1"
    assert vault._get_dataset_collection(dataset) == collection


@pytest.mark.asyncio
async def test_async_data_vault_dataset_edge_cases_and_internal_paths():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    existing = CollectionItem(
        collection_id="collection_1",
        asset_id="asset_1",
        collection_item_id="ci_1",
        split="val",
    )
    backend = Mock()
    backend.get_asset = AsyncMock(side_effect=DocumentNotFoundError("no direct asset"))
    backend.get_asset_by_alias = AsyncMock(return_value=asset)
    backend.list_collections = AsyncMock(side_effect=[[collection], [], [collection, collection]])
    backend.list_collection_items = AsyncMock(return_value=[existing])
    backend.update_collection_item = AsyncMock(return_value=existing.model_copy(update={"split": "train"}))

    vault = AsyncDataVault(backend)
    assert await vault._resolve_asset_id("friendly") == "asset_1"
    assert await vault.get_dataset("training") == VaultDataset(
        dataset_id="collection_1",
        name="training",
        description=None,
        status="active",
        metadata={},
        asset_count=1,
        created_at=collection.created_at,
        created_by=None,
        updated_at=collection.updated_at,
    )
    with pytest.raises(DocumentNotFoundError, match="Dataset 'missing' not found"):
        await vault._get_dataset_collection("missing")
    with pytest.raises(ValueError, match="Multiple active datasets matched"):
        await vault._get_dataset_collection("duplicate")
    item = await vault._ensure_collection_item(collection, "asset_1", split="train")
    assert item.split == "train"


@pytest.mark.asyncio
async def test_async_data_vault_internal_shortcuts_and_reuse_paths():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    active_item = CollectionItem(
        collection_id="collection_1",
        asset_id="asset_1",
        collection_item_id="ci_1",
        status="active",
        metadata={"old": True},
    )
    inactive_item = CollectionItem(
        collection_id="collection_1",
        asset_id="asset_2",
        collection_item_id="ci_2",
        status="removed",
        metadata={"old": True},
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
    )
    backend = Mock()
    backend.list_collections = AsyncMock(return_value=[collection])
    backend.list_collection_items = AsyncMock(side_effect=[[active_item], [inactive_item]])
    backend.update_collection_item = AsyncMock(
        side_effect=[
            active_item.model_copy(update={"metadata": {"old": True, "new": True}}),
            inactive_item.model_copy(update={"status": "active"}),
        ]
    )
    backend.list_annotation_sets = AsyncMock(return_value=[annotation_set])
    vault = AsyncDataVault(backend)
    dataset = VaultDataset(
        dataset_id="collection_1",
        name="training",
        description=None,
        status="active",
        metadata={},
        asset_count=0,
        created_at=collection.created_at,
        created_by=None,
        updated_at=collection.updated_at,
    )

    assert await vault._resolve_asset_id(asset) == "asset_1"
    assert await vault._get_dataset_collection(dataset) == collection
    updated_active = await vault._ensure_collection_item(collection, "asset_1", metadata={"new": True})
    assert updated_active.metadata == {"old": True, "new": True}
    reactivated = await vault._ensure_collection_item(collection, "asset_2")
    assert reactivated.status == "active"
    reused = await vault._get_or_create_dataset_annotation_set(collection, "asset_1")
    assert reused == annotation_set


@pytest.mark.asyncio
async def test_async_data_vault_list_assets_dedupes_and_remove_annotation_missing_ok():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    item = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    backend = Mock()
    backend.list_collections = AsyncMock(side_effect=[[collection], [collection]])
    backend.list_collection_items = AsyncMock(side_effect=[[item, item], []])
    backend.get_asset = AsyncMock(return_value=asset)
    backend.list_annotation_sets = AsyncMock(return_value=[])
    backend.delete_annotation_record = AsyncMock(return_value=None)

    vault = AsyncDataVault(backend)
    assert await vault.list_dataset_assets("training") == [asset]
    await vault.remove_annotation("training", "annotation_1", missing_ok=True)
    backend.delete_annotation_record.assert_not_awaited()


def test_sync_data_vault_create_and_list_datasets():
    collection = Collection(name="training", collection_id="collection_1")
    backend = Mock()
    backend.list_collections = Mock(side_effect=[[], [collection], [collection]])
    backend.create_collection = Mock(return_value=collection)
    backend.list_collection_items = Mock(return_value=[])
    backend.iter_collections = Mock(return_value=iter([collection]))
    page = CursorPage(items=[collection], page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1))
    backend.list_collections_page = Mock(return_value=page)

    vault = DataVault(backend)
    created = vault.create_dataset("training", description="demo")
    assert created == VaultDataset(
        dataset_id="collection_1",
        name="training",
        description=None,
        status="active",
        metadata={},
        asset_count=0,
        created_at=collection.created_at,
        created_by=None,
        updated_at=collection.updated_at,
    )
    backend.create_collection.assert_called_once_with(
        name="training",
        description="demo",
        status="active",
        metadata=None,
        created_by=None,
    )

    assert vault.list_datasets() == [created]
    dataset_page = vault.list_datasets_page(limit=1, include_total=True)
    assert dataset_page.items == [created]
    backend.list_collections_page.assert_called_once_with(
        filters={"status": "active"},
        sort="updated_desc",
        limit=1,
        cursor=None,
        include_total=True,
    )
    assert list(vault.iter_datasets()) == [created]


def test_sync_data_vault_add_annotation_brings_asset_into_dataset():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
    )
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.get_asset = Mock(return_value=asset)
    backend.list_collection_items = Mock(return_value=[])
    backend.create_collection_item = Mock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    )
    backend.list_annotation_sets = Mock(return_value=[])
    backend.create_annotation_set = Mock(return_value=annotation_set)
    backend.add_annotation_records = Mock(return_value=[record])

    vault = DataVault(backend)
    out = vault.add_annotation(
        "training",
        {"kind": "bbox", "label": "cat", "source": {"type": "human", "name": "review"}, "geometry": {}},
        asset="asset_1",
    )

    assert out == record
    backend.create_collection_item.assert_called_once_with(
        collection_id="collection_1",
        asset_id="asset_1",
        split=None,
        status="active",
        metadata=None,
        added_by=None,
    )
    create_set_kwargs = backend.create_annotation_set.call_args.kwargs
    assert create_set_kwargs["name"] == "training:asset_1"
    assert create_set_kwargs["metadata"]["mindtrace"]["data_vault"]["dataset_collection_id"] == "collection_1"
    add_args, add_kwargs = backend.add_annotation_records.call_args
    assert add_kwargs["annotation_set_id"] == "annotation_set_1"
    assert add_args[0][0]["subject"] == {"kind": "asset", "id": "asset_1"}


def test_sync_data_vault_list_assets_and_annotations_and_remove_membership():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    item = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
    )
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.list_collection_items = Mock(side_effect=[[item, item], [item]])
    backend.get_asset = Mock(return_value=asset)
    backend.list_annotation_sets = Mock(return_value=[annotation_set, annotation_set])
    backend.get_annotation_record = Mock(return_value=record)
    backend.delete_annotation_record = Mock()
    backend.delete_collection_item = Mock()

    vault = DataVault(backend)
    assert vault.list_dataset_assets("training") == [asset]
    assert vault.list_dataset_annotations("training") == [record, record]

    vault.remove_annotation("training", "annotation_1")
    backend.delete_annotation_record.assert_called_once_with("annotation_1")

    vault.remove_asset("training", "asset_1")
    backend.delete_collection_item.assert_called_once_with("ci_1")


@pytest.mark.asyncio
async def test_async_data_vault_add_annotation_brings_asset_into_dataset():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
    )
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    backend = Mock()
    backend.list_collections = AsyncMock(return_value=[collection])
    backend.get_asset = AsyncMock(return_value=asset)
    backend.list_collection_items = AsyncMock(return_value=[])
    backend.create_collection_item = AsyncMock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    )
    backend.list_annotation_sets = AsyncMock(return_value=[])
    backend.create_annotation_set = AsyncMock(return_value=annotation_set)
    backend.add_annotation_records = AsyncMock(return_value=[record])

    vault = AsyncDataVault(backend)
    out = await vault.add_annotation(
        "training",
        {"kind": "bbox", "label": "cat", "source": {"type": "human", "name": "review"}, "geometry": {}},
        asset="asset_1",
    )

    assert out == record
    backend.create_collection_item.assert_awaited_once()
    backend.create_annotation_set.assert_awaited_once()
    backend.add_annotation_records.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_data_vault_public_dataset_workflows():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    item = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
    )
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    dataset_page = CursorPage(
        items=[collection], page=PageInfo(limit=1, next_cursor=None, has_more=False, total_count=1)
    )
    backend = Mock()
    backend.list_collections = AsyncMock(
        side_effect=[
            [collection],
            [collection],
            [],
            [collection],
            [collection],
            [collection],
            [collection],
            [collection],
        ]
    )
    backend.list_collections_page = AsyncMock(return_value=dataset_page)

    async def iter_collections(**kwargs):
        assert kwargs == {"filters": {"status": "active"}, "sort": "updated_desc", "batch_size": 5}
        yield collection

    backend.iter_collections = iter_collections
    backend.create_collection = AsyncMock(return_value=collection)
    backend.get_asset = AsyncMock(side_effect=[asset, asset, asset, asset, asset])
    backend.list_collection_items = AsyncMock(side_effect=[[item], [item], [item], [item], [item], [item], [item]])
    backend.update_collection_item = AsyncMock(return_value=item)
    backend.delete_collection_item = AsyncMock(return_value=None)
    backend.list_annotation_sets = AsyncMock(side_effect=[[annotation_set], [annotation_set], []])
    backend.get_annotation_record = AsyncMock(return_value=record)
    backend.delete_annotation_record = AsyncMock(return_value=None)

    vault = AsyncDataVault(backend)
    summary = await vault.get_dataset("training")
    assert summary.asset_count == 1
    assert await vault.list_datasets() == [summary]
    page = await vault.list_datasets_page(limit=1, include_total=True)
    assert page.items == [summary]
    assert [dataset async for dataset in vault.iter_datasets(batch_size=5)] == [summary]
    created = await vault.create_dataset("new-dataset")
    assert created.name == "training"
    assert await vault.add_asset("training", "asset_1", split="train") == asset
    assert await vault.list_dataset_assets("training") == [asset]
    assert await vault.list_dataset_annotations("training", asset="asset_1") == [record]
    await vault.remove_annotation("training", "annotation_1")
    backend.delete_annotation_record.assert_awaited_once_with("annotation_1")
    await vault.remove_asset("training", "asset_1")
    backend.delete_collection_item.assert_awaited_once_with("ci_1")


@pytest.mark.asyncio
async def test_async_data_vault_public_dataset_error_paths():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    backend = Mock()
    backend.list_collections = AsyncMock(side_effect=[[collection], [collection], [collection], [collection]])
    backend.get_asset = AsyncMock(return_value=asset)
    backend.list_collection_items = AsyncMock(return_value=[])
    backend.list_annotation_sets = AsyncMock(return_value=[])

    vault = AsyncDataVault(backend)
    with pytest.raises(ValueError, match="already exists"):
        await vault.create_dataset("training")
    with pytest.raises(DocumentNotFoundError, match="not part of dataset"):
        await vault.remove_asset("training", "asset_1")
    with pytest.raises(DocumentNotFoundError, match="not part of dataset"):
        await vault.remove_annotation("training", "annotation_1")
    with pytest.raises(ValueError, match="must reference an asset subject"):
        await vault.add_annotation(
            "training",
            {"kind": "bbox", "label": "cat", "source": {"type": "human", "name": "review"}, "geometry": {}},
        )
