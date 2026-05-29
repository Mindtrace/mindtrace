"""Unit tests for :mod:`mindtrace.datalake.data_vault`."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from PIL import Image
from urllib3.util import parse_url

from mindtrace.core import CoreConfig
from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake import AsyncDatalake, DatalakeService
from mindtrace.datalake.annotations import BboxAnnotation, ClassificationAnnotation, PolygonAnnotation
from mindtrace.datalake.async_datalake import SlowOperationDisabledError, SlowOperationWarning, SlowOpsPolicy
from mindtrace.datalake.data_vault import (
    _DATASET_ANNOTATIONS_CURSOR_KIND,
    _DATASET_ASSETS_CURSOR_KIND,
    AsyncDataVault,
    DataVault,
    VaultDataset,
    _annotation_id,
    _annotation_matches_asset,
    _annotation_source_type,
    _annotations_bound_to_asset,
    _coerce_annotation_payload,
    _dataset_annotation_set_filters,
    _decode_dataset_cursor,
    _encode_dataset_cursor,
    _extract_annotation_asset_id,
    _guard_slow_list_operation,
    _normalize_async_backend,
    _normalize_sync_backend,
    _pil_image_to_png_bytes,
    _resolve_slow_ops_policy,
    _resolved_primary_asset,
    _sanitize_object_name_component,
)
from mindtrace.datalake.data_vault_backends import (
    AsyncDataVaultBackend,
    DatalakeServiceAsyncDataVaultBackend,
    DatalakeServiceDataVaultBackend,
    DataVaultBackend,
    LocalAsyncDataVaultBackend,
    LocalDataVaultBackend,
)
from mindtrace.datalake.datalake import Datalake
from mindtrace.datalake.pagination_types import CursorPage, PageInfo
from mindtrace.datalake.service_types import (
    AddedAnnotationRecordsOutput,
    AnnotationSetOutput,
    AnnotationSetPageOutput,
    AssetOutput,
    CollectionItemListOutput,
    CollectionListOutput,
    CollectionOutput,
    DatasetVersionOutput,
    DatumOutput,
    ObjectDataOutput,
    ResolvedDatasetVersionOutput,
)
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    DuplicateAliasError,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)
from mindtrace.datalake.vault_serialization import (
    SERIALIZATION_METADATA_KEY,
    direct_bytes_serialization_block,
)
from mindtrace.registry import Registry
from mindtrace.services import Service
from mindtrace.services.core.utils import generate_connection_manager


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


def test_data_vault_private_paging_helpers_and_policy_resolution():
    backend = SimpleNamespace(slow_ops_policy="allow")
    wrapped = SimpleNamespace(_datalake=SimpleNamespace(slow_ops_policy="forbid"))

    assert _resolve_slow_ops_policy(backend, None) == SlowOpsPolicy.ALLOW
    assert _resolve_slow_ops_policy(wrapped, None) == SlowOpsPolicy.FORBID
    assert _resolve_slow_ops_policy(SimpleNamespace(slow_ops_policy=Mock()), None) == SlowOpsPolicy.WARN
    assert _resolve_slow_ops_policy(object(), SlowOpsPolicy.ALLOW) == SlowOpsPolicy.ALLOW

    payload = {"kind": _DATASET_ASSETS_CURSOR_KIND, "collection_id": "collection_1", "sort": "created_desc"}
    cursor = _encode_dataset_cursor(payload)
    assert _decode_dataset_cursor(cursor, expected_kind=_DATASET_ASSETS_CURSOR_KIND) == payload

    with pytest.raises(ValueError, match="Invalid dataset page cursor"):
        _decode_dataset_cursor("not-base64", expected_kind=_DATASET_ASSETS_CURSOR_KIND)
    with pytest.raises(ValueError, match="Invalid dataset page cursor"):
        _decode_dataset_cursor(
            _encode_dataset_cursor({"kind": _DATASET_ANNOTATIONS_CURSOR_KIND}),
            expected_kind=_DATASET_ASSETS_CURSOR_KIND,
        )

    _guard_slow_list_operation(SlowOpsPolicy.ALLOW, "list_dataset_assets", alternatives="iter_dataset_assets()")
    with pytest.warns(SlowOperationWarning, match="list_dataset_assets"):
        _guard_slow_list_operation(SlowOpsPolicy.WARN, "list_dataset_assets", alternatives="iter_dataset_assets()")
    with pytest.raises(SlowOperationDisabledError, match="list_dataset_assets"):
        _guard_slow_list_operation(SlowOpsPolicy.FORBID, "list_dataset_assets", alternatives="iter_dataset_assets()")


@pytest.mark.asyncio
async def test_async_data_vault_count_helpers_continue_across_pages():
    item_1 = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    item_2 = CollectionItem(collection_id="collection_1", asset_id="asset_2", collection_item_id="ci_2")
    asset_page_1 = CursorPage(items=[item_1], page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True))
    asset_page_2 = CursorPage(items=[item_2], page=PageInfo(limit=1, next_cursor=None, has_more=False))
    annotation_page_1 = AnnotationSetPageOutput(
        items=[
            AnnotationSet(
                annotation_set_id="annotation_set_1",
                name="training:asset_1",
                purpose="other",
                source_type="human",
                annotation_record_ids=["annotation_1", "annotation_2"],
            )
        ],
        page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True),
    )
    annotation_page_2 = AnnotationSetPageOutput(
        items=[
            AnnotationSet(
                annotation_set_id="annotation_set_2",
                name="training:asset_2",
                purpose="other",
                source_type="human",
                annotation_record_ids=["annotation_3"],
            )
        ],
        page=PageInfo(limit=1, next_cursor=None, has_more=False),
    )
    backend = Mock()
    backend.list_collection_items_page = AsyncMock(
        side_effect=lambda **kwargs: asset_page_1 if kwargs.get("cursor") is None else asset_page_2
    )
    backend.list_annotation_sets_page = AsyncMock(
        side_effect=lambda **kwargs: annotation_page_1 if kwargs.get("cursor") is None else annotation_page_2
    )

    vault = AsyncDataVault(backend)
    assert await vault._count_dataset_assets("collection_1") == 2
    assert await vault._count_dataset_annotations("collection_1", None) == 3


def test_sync_data_vault_count_annotations_continue_across_pages():
    annotation_page_1 = AnnotationSetPageOutput(
        items=[
            AnnotationSet(
                annotation_set_id="annotation_set_1",
                name="training:asset_1",
                purpose="other",
                source_type="human",
                annotation_record_ids=["annotation_1", "annotation_2"],
            )
        ],
        page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True),
    )
    annotation_page_2 = AnnotationSetPageOutput(
        items=[
            AnnotationSet(
                annotation_set_id="annotation_set_2",
                name="training:asset_2",
                purpose="other",
                source_type="human",
                annotation_record_ids=["annotation_3"],
            )
        ],
        page=PageInfo(limit=1, next_cursor=None, has_more=False),
    )
    backend = Mock()
    backend.list_annotation_sets_page = Mock(
        side_effect=lambda **kwargs: annotation_page_1 if kwargs.get("cursor") is None else annotation_page_2
    )

    assert DataVault(backend)._count_dataset_annotations("collection_1", None) == 3


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
        "mindtrace.datalake.service.DatalakeService.connect",
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
        "mindtrace.datalake.service.DatalakeService.connect",
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
    backend.get_asset_payload = AsyncMock(return_value=b"by-asset-id-payload")
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
    backend.get_asset_payload = AsyncMock(return_value=b"raw")
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
    backend.get_asset_payload = AsyncMock(return_value=b"nop")
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
    backend.get_asset_payload = AsyncMock(return_value=png)
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
    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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
    backend.get_asset_payload = Mock(return_value=png)
    backend.get_object = Mock(return_value=png)
    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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
    backend.get_asset_payload = Mock(return_value=b"raw")
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
    backend.get_asset_payload = Mock(return_value=b"nop")
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
    backend.get_asset_payload = Mock(return_value=b"sync-payload")
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
    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)

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

    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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
    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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

    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
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


def test_sync_data_vault_dataset_assets_page_iter_and_total():
    collection = Collection(name="training", collection_id="collection_1")
    asset_1 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n1", version="1"),
        asset_id="asset_1",
    )
    asset_2 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n2", version="1"),
        asset_id="asset_2",
    )
    page_1 = CursorPage(
        items=[CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")],
        page=PageInfo(limit=1, next_cursor="raw-2", has_more=True),
    )
    page_2 = CursorPage(
        items=[CollectionItem(collection_id="collection_1", asset_id="asset_2", collection_item_id="ci_2")],
        page=PageInfo(limit=1, next_cursor=None, has_more=False),
    )
    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.list_collection_items_page = Mock(side_effect=[page_1, page_1, page_2, page_1, page_2])
    backend.get_asset = Mock(side_effect=lambda asset_id: {"asset_1": asset_1, "asset_2": asset_2}[asset_id])
    vault = DataVault(backend)

    first_page = vault.list_dataset_assets_page("training", limit=1, include_total=True)
    second_page = vault.list_dataset_assets_page("training", limit=1, cursor=first_page.page.next_cursor)

    assert [asset.asset_id for asset in first_page.items] == ["asset_1"]
    assert first_page.page.total_count == 2
    assert first_page.page.has_more is True
    assert [asset.asset_id for asset in second_page.items] == ["asset_2"]
    assert second_page.page.has_more is False

    backend.list_collection_items_page.reset_mock()
    backend.list_collection_items_page.side_effect = [page_1, page_2]
    assert [asset.asset_id for asset in vault.iter_dataset_assets("training", batch_size=1)] == ["asset_1", "asset_2"]


@pytest.mark.asyncio
async def test_async_data_vault_dataset_assets_page_resume_validation_and_total():
    collection = Collection(name="training", collection_id="collection_1")
    asset_1 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n1", version="1"),
        asset_id="asset_1",
    )
    asset_2 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n2", version="1"),
        asset_id="asset_2",
    )
    item_1 = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    item_2 = CollectionItem(collection_id="collection_1", asset_id="asset_2", collection_item_id="ci_2")
    page = CursorPage(items=[item_1, item_2], page=PageInfo(limit=5, next_cursor=None, has_more=False))

    backend = Mock()
    backend.list_collections = AsyncMock(return_value=[collection])
    backend.list_collection_items_page = AsyncMock(side_effect=lambda **kwargs: page)
    backend.get_asset = AsyncMock(side_effect=lambda asset_id: {"asset_1": asset_1, "asset_2": asset_2}[asset_id])
    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)

    asset_page = await vault.list_dataset_assets_page("training", limit=5, include_total=True)
    assert [asset.asset_id for asset in asset_page.items] == ["asset_1", "asset_2"]
    assert asset_page.page.total_count == 2
    assert [asset.asset_id async for asset in vault.iter_dataset_assets("training", batch_size=5)] == [
        "asset_1",
        "asset_2",
    ]

    resume_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ASSETS_CURSOR_KIND,
            "collection_id": "collection_1",
            "sort": "created_desc",
            "limit": 2,
            "items_cursor": None,
            "seen_asset_ids": [],
            "pending_asset_ids": ["asset_1"],
        }
    )
    resumed = await vault.list_dataset_assets_page("training", cursor=resume_cursor)
    assert [asset.asset_id for asset in resumed.items] == ["asset_1"]
    assert resumed.page.has_more is False

    limited_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ASSETS_CURSOR_KIND,
            "collection_id": "collection_1",
            "sort": "created_desc",
            "limit": 1,
            "items_cursor": None,
            "seen_asset_ids": [],
            "pending_asset_ids": ["asset_1", "asset_2"],
        }
    )
    limited = await vault.list_dataset_assets_page("training", cursor=limited_cursor)
    assert [asset.asset_id for asset in limited.items] == ["asset_1"]
    assert limited.page.has_more is True
    assert limited.page.next_cursor is not None

    with pytest.raises(ValueError, match="requested dataset"):
        await vault.list_dataset_assets_page(
            "training",
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ASSETS_CURSOR_KIND,
                    "collection_id": "other_collection",
                    "sort": "created_desc",
                }
            ),
        )
    with pytest.raises(ValueError, match="sort order"):
        await vault.list_dataset_assets_page(
            "training",
            sort="updated_desc",
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ASSETS_CURSOR_KIND,
                    "collection_id": "collection_1",
                    "sort": "created_desc",
                }
            ),
        )


@pytest.mark.asyncio
async def test_async_data_vault_dataset_assets_page_empty_duplicate_and_iter_edges():
    collection = Collection(name="training", collection_id="collection_1")
    asset_1 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n1", version="1"),
        asset_id="asset_1",
    )
    asset_2 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n2", version="1"),
        asset_id="asset_2",
    )
    item_1 = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    item_2 = CollectionItem(collection_id="collection_1", asset_id="asset_2", collection_item_id="ci_2")
    duplicate_page = CursorPage(items=[item_1, item_1], page=PageInfo(limit=5, next_cursor=None, has_more=False))
    empty_page = CursorPage(items=[], page=PageInfo(limit=2, next_cursor=None, has_more=False))
    iter_page_1 = CursorPage(items=[item_1], page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True))
    iter_page_2 = CursorPage(items=[item_2], page=PageInfo(limit=1, next_cursor=None, has_more=False))

    duplicate_backend = Mock()
    duplicate_backend.list_collections = AsyncMock(return_value=[collection])
    duplicate_backend.get_asset = AsyncMock(return_value=asset_1)
    duplicate_backend.list_collection_items_page = AsyncMock(return_value=duplicate_page)
    duplicate_vault = AsyncDataVault(duplicate_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)

    duplicate_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ASSETS_CURSOR_KIND,
            "collection_id": "collection_1",
            "sort": "created_desc",
            "limit": 5,
            "items_cursor": None,
            "seen_asset_ids": [],
            "pending_asset_ids": ["asset_1", "asset_1"],
        }
    )
    duplicate_resumed = await duplicate_vault.list_dataset_assets_page("training", cursor=duplicate_cursor)
    assert [asset.asset_id for asset in duplicate_resumed.items] == ["asset_1"]
    duplicate_page = await duplicate_vault.list_dataset_assets_page("training")
    assert [asset.asset_id for asset in duplicate_page.items] == ["asset_1"]

    empty_backend = Mock()
    empty_backend.list_collections = AsyncMock(return_value=[collection])
    empty_backend.list_collection_items_page = AsyncMock(return_value=empty_page)
    empty_backend.get_asset = AsyncMock()
    empty_vault = AsyncDataVault(empty_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
    assert (await empty_vault.list_dataset_assets_page("training")).items == []

    iter_backend = Mock()
    iter_backend.list_collections = AsyncMock(return_value=[collection])
    iter_backend.list_collection_items_page = AsyncMock(side_effect=[iter_page_1, iter_page_2])
    iter_backend.get_asset = AsyncMock(side_effect=lambda asset_id: {"asset_1": asset_1, "asset_2": asset_2}[asset_id])
    iter_vault = AsyncDataVault(iter_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
    assert [asset.asset_id async for asset in iter_vault.iter_dataset_assets("training", batch_size=1)] == [
        "asset_1",
        "asset_2",
    ]


@pytest.mark.asyncio
async def test_async_data_vault_dataset_annotations_page_iter_and_asset_filter():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n1", version="1"),
        asset_id="asset_1",
    )
    set_1 = AnnotationSet(
        annotation_set_id="set_1",
        name="set-1",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1", "annotation_2"],
    )
    set_2 = AnnotationSet(
        annotation_set_id="set_2",
        name="set-2",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_3"],
    )
    record_1 = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    record_2 = AnnotationRecord(
        annotation_id="annotation_2",
        kind="bbox",
        label="dog",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    record_3 = AnnotationRecord(
        annotation_id="annotation_3",
        kind="bbox",
        label="bird",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    page_1 = AnnotationSetPageOutput(items=[set_1], page=PageInfo(limit=1, next_cursor="set-cursor-2", has_more=True))
    page_2 = AnnotationSetPageOutput(items=[set_2], page=PageInfo(limit=1, next_cursor=None, has_more=False))
    backend = Mock()
    backend.list_collections = AsyncMock(return_value=[collection])
    backend.get_asset = AsyncMock(return_value=asset)
    backend.get_asset_by_alias = AsyncMock(return_value=asset)
    backend.list_annotation_sets_page = AsyncMock(side_effect=[page_1, page_2, page_1, page_2])
    backend.get_annotation_record = AsyncMock(
        side_effect=lambda annotation_id: {
            "annotation_1": record_1,
            "annotation_2": record_2,
            "annotation_3": record_3,
        }[annotation_id]
    )
    vault = AsyncDataVault(backend)

    first_page = await vault.list_dataset_annotations_page("training", asset=asset, limit=2)
    second_page = await vault.list_dataset_annotations_page(
        "training",
        asset=asset,
        limit=2,
        cursor=first_page.page.next_cursor,
    )

    assert [record.annotation_id for record in first_page.items] == ["annotation_1", "annotation_2"]
    assert first_page.page.has_more is True
    assert [record.annotation_id for record in second_page.items] == ["annotation_3"]
    assert second_page.page.has_more is False
    assert (
        backend.list_annotation_sets_page.await_args_list[0].kwargs["filters"]["metadata.mindtrace.data_vault.asset_id"]
        == "asset_1"
    )

    backend.list_annotation_sets_page.reset_mock()
    backend.list_annotation_sets_page.side_effect = [page_1, page_2]
    assert [
        record.annotation_id async for record in vault.iter_dataset_annotations("training", asset=asset, batch_size=2)
    ] == ["annotation_1", "annotation_2", "annotation_3"]


@pytest.mark.asyncio
async def test_async_data_vault_dataset_annotations_page_resume_validation_and_total():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    record_1 = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    record_2 = AnnotationRecord(
        annotation_id="annotation_2",
        kind="bbox",
        label="dog",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1", "annotation_2"],
        metadata={"mindtrace": {"data_vault": {"dataset_collection_id": "collection_1", "asset_id": "asset_1"}}},
    )
    page = AnnotationSetPageOutput(items=[annotation_set], page=PageInfo(limit=5, next_cursor=None, has_more=False))

    backend = Mock()
    backend.list_collections = AsyncMock(return_value=[collection])
    backend.list_annotation_sets_page = AsyncMock(side_effect=lambda **kwargs: page)
    backend.get_annotation_record = AsyncMock(
        side_effect=lambda annotation_id: {"annotation_1": record_1, "annotation_2": record_2}[annotation_id]
    )
    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)

    annotation_page = await vault.list_dataset_annotations_page("training", asset=asset, limit=5, include_total=True)
    assert [record.annotation_id for record in annotation_page.items] == ["annotation_1", "annotation_2"]
    assert annotation_page.page.total_count == 2

    resume_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
            "collection_id": "collection_1",
            "asset_id": "asset_1",
            "sort": "created_desc",
            "limit": 3,
            "annotation_sets_cursor": None,
            "pending_annotation_ids": ["annotation_1"],
        }
    )
    resumed = await vault.list_dataset_annotations_page("training", asset=asset, cursor=resume_cursor)
    assert [record.annotation_id for record in resumed.items] == ["annotation_1"]
    assert resumed.page.has_more is False

    limited_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
            "collection_id": "collection_1",
            "asset_id": "asset_1",
            "sort": "created_desc",
            "limit": 1,
            "annotation_sets_cursor": None,
            "pending_annotation_ids": ["annotation_1", "annotation_2"],
        }
    )
    limited = await vault.list_dataset_annotations_page("training", asset=asset, cursor=limited_cursor)
    assert [record.annotation_id for record in limited.items] == ["annotation_1"]
    assert limited.page.has_more is True
    assert limited.page.next_cursor is not None

    with pytest.raises(ValueError, match="requested dataset"):
        await vault.list_dataset_annotations_page(
            "training",
            asset=asset,
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
                    "collection_id": "other_collection",
                    "asset_id": "asset_1",
                    "sort": "created_desc",
                }
            ),
        )
    with pytest.raises(ValueError, match="sort order"):
        await vault.list_dataset_annotations_page(
            "training",
            asset=asset,
            sort="updated_desc",
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
                    "collection_id": "collection_1",
                    "asset_id": "asset_1",
                    "sort": "created_desc",
                }
            ),
        )
    with pytest.raises(ValueError, match="asset filter"):
        await vault.list_dataset_annotations_page(
            "training",
            asset=asset,
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
                    "collection_id": "collection_1",
                    "asset_id": "asset_2",
                    "sort": "created_desc",
                }
            ),
        )


@pytest.mark.asyncio
async def test_async_data_vault_dataset_annotations_page_empty_page_edge():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    empty_page = AnnotationSetPageOutput(items=[], page=PageInfo(limit=2, next_cursor=None, has_more=False))
    backend = Mock()
    backend.list_collections = AsyncMock(return_value=[collection])
    backend.list_annotation_sets_page = AsyncMock(return_value=empty_page)
    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)

    page = await vault.list_dataset_annotations_page("training", asset=asset)
    assert page.items == []
    assert page.page.has_more is False


def test_sync_data_vault_dataset_assets_page_resume_and_validation():
    collection = Collection(name="training", collection_id="collection_1")
    asset_1 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n1", version="1"),
        asset_id="asset_1",
    )
    asset_2 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n2", version="1"),
        asset_id="asset_2",
    )
    item_1 = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    item_2 = CollectionItem(collection_id="collection_1", asset_id="asset_2", collection_item_id="ci_2")
    page = CursorPage(items=[item_1, item_2], page=PageInfo(limit=5, next_cursor=None, has_more=False))

    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.list_collection_items_page = Mock(side_effect=lambda **kwargs: page)
    backend.get_asset = Mock(side_effect=lambda asset_id: {"asset_1": asset_1, "asset_2": asset_2}[asset_id])
    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)

    resume_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ASSETS_CURSOR_KIND,
            "collection_id": "collection_1",
            "sort": "created_desc",
            "limit": 2,
            "items_cursor": None,
            "seen_asset_ids": [],
            "pending_asset_ids": ["asset_1"],
        }
    )
    resumed = vault.list_dataset_assets_page("training", cursor=resume_cursor)
    assert [asset.asset_id for asset in resumed.items] == ["asset_1"]
    assert resumed.page.has_more is False

    asset_page = vault.list_dataset_assets_page("training", limit=5, include_total=True)
    assert [asset.asset_id for asset in asset_page.items] == ["asset_1", "asset_2"]
    assert asset_page.page.total_count == 2

    with pytest.raises(ValueError, match="requested dataset"):
        vault.list_dataset_assets_page(
            "training",
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ASSETS_CURSOR_KIND,
                    "collection_id": "other_collection",
                    "sort": "created_desc",
                }
            ),
        )
    with pytest.raises(ValueError, match="sort order"):
        vault.list_dataset_assets_page(
            "training",
            sort="updated_desc",
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ASSETS_CURSOR_KIND,
                    "collection_id": "collection_1",
                    "sort": "created_desc",
                }
            ),
        )


def test_sync_data_vault_dataset_assets_page_empty_and_duplicate_edges():
    collection = Collection(name="training", collection_id="collection_1")
    asset_1 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n1", version="1"),
        asset_id="asset_1",
    )
    item_1 = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1")
    duplicate_page = CursorPage(items=[item_1, item_1], page=PageInfo(limit=5, next_cursor=None, has_more=False))
    empty_page = CursorPage(items=[], page=PageInfo(limit=2, next_cursor=None, has_more=False))

    duplicate_backend = Mock()
    duplicate_backend.list_collections = Mock(return_value=[collection])
    duplicate_backend.list_collection_items_page = Mock(return_value=duplicate_page)
    duplicate_backend.get_asset = Mock(return_value=asset_1)
    duplicate_vault = DataVault(duplicate_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
    assert [asset.asset_id for asset in duplicate_vault.list_dataset_assets_page("training").items] == ["asset_1"]

    empty_backend = Mock()
    empty_backend.list_collections = Mock(return_value=[collection])
    empty_backend.list_collection_items_page = Mock(return_value=empty_page)
    empty_backend.get_asset = Mock()
    empty_vault = DataVault(empty_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
    assert empty_vault.list_dataset_assets_page("training").items == []


def test_sync_data_vault_dataset_annotations_page_iter_total_and_validation():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    record_1 = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    record_2 = AnnotationRecord(
        annotation_id="annotation_2",
        kind="bbox",
        label="dog",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1", "annotation_2"],
        metadata={"mindtrace": {"data_vault": {"dataset_collection_id": "collection_1", "asset_id": "asset_1"}}},
    )
    page = AnnotationSetPageOutput(items=[annotation_set], page=PageInfo(limit=5, next_cursor=None, has_more=False))

    backend = Mock()
    backend.list_collections = Mock(return_value=[collection])
    backend.list_annotation_sets_page = Mock(side_effect=lambda **kwargs: page)
    backend.get_annotation_record = Mock(
        side_effect=lambda annotation_id: {"annotation_1": record_1, "annotation_2": record_2}[annotation_id]
    )
    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.ALLOW)

    annotation_page = vault.list_dataset_annotations_page("training", asset=asset, limit=5, include_total=True)
    assert [record.annotation_id for record in annotation_page.items] == ["annotation_1", "annotation_2"]
    assert annotation_page.page.total_count == 2
    assert [
        record.annotation_id for record in vault.iter_dataset_annotations("training", asset=asset, batch_size=5)
    ] == [
        "annotation_1",
        "annotation_2",
    ]

    resume_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
            "collection_id": "collection_1",
            "asset_id": "asset_1",
            "sort": "created_desc",
            "limit": 3,
            "annotation_sets_cursor": None,
            "pending_annotation_ids": ["annotation_1"],
        }
    )
    resumed = vault.list_dataset_annotations_page("training", asset=asset, cursor=resume_cursor)
    assert [record.annotation_id for record in resumed.items] == ["annotation_1"]
    assert resumed.page.has_more is False

    with pytest.raises(ValueError, match="requested dataset"):
        vault.list_dataset_annotations_page(
            "training",
            asset=asset,
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
                    "collection_id": "other_collection",
                    "asset_id": "asset_1",
                    "sort": "created_desc",
                }
            ),
        )
    with pytest.raises(ValueError, match="sort order"):
        vault.list_dataset_annotations_page(
            "training",
            asset=asset,
            sort="updated_desc",
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
                    "collection_id": "collection_1",
                    "asset_id": "asset_1",
                    "sort": "created_desc",
                }
            ),
        )
    with pytest.raises(ValueError, match="asset filter"):
        vault.list_dataset_annotations_page(
            "training",
            asset=asset,
            cursor=_encode_dataset_cursor(
                {
                    "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
                    "collection_id": "collection_1",
                    "asset_id": "asset_2",
                    "sort": "created_desc",
                }
            ),
        )


def test_sync_data_vault_dataset_annotations_page_limit_empty_and_iter_edges():
    collection = Collection(name="training", collection_id="collection_1")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    record_1 = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    record_2 = AnnotationRecord(
        annotation_id="annotation_2",
        kind="bbox",
        label="dog",
        subject=SubjectRef(kind="asset", id="asset_1"),
        source={"type": "human", "name": "review"},
        geometry={},
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="training:asset_1",
        purpose="other",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
        metadata={"mindtrace": {"data_vault": {"dataset_collection_id": "collection_1", "asset_id": "asset_1"}}},
    )
    empty_page = AnnotationSetPageOutput(items=[], page=PageInfo(limit=2, next_cursor=None, has_more=False))
    iter_page_1 = AnnotationSetPageOutput(
        items=[annotation_set], page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True)
    )
    iter_page_2 = AnnotationSetPageOutput(items=[], page=PageInfo(limit=1, next_cursor=None, has_more=False))

    limit_backend = Mock()
    limit_backend.list_collections = Mock(return_value=[collection])
    limit_backend.get_annotation_record = Mock(
        side_effect=lambda annotation_id: {"annotation_1": record_1, "annotation_2": record_2}[annotation_id]
    )
    limit_vault = DataVault(limit_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
    limited_cursor = _encode_dataset_cursor(
        {
            "kind": _DATASET_ANNOTATIONS_CURSOR_KIND,
            "collection_id": "collection_1",
            "asset_id": "asset_1",
            "sort": "created_desc",
            "limit": 1,
            "annotation_sets_cursor": None,
            "pending_annotation_ids": ["annotation_1", "annotation_2"],
        }
    )
    limited = limit_vault.list_dataset_annotations_page("training", asset=asset, cursor=limited_cursor)
    assert [record.annotation_id for record in limited.items] == ["annotation_1"]
    assert limited.page.has_more is True

    empty_backend = Mock()
    empty_backend.list_collections = Mock(return_value=[collection])
    empty_backend.list_annotation_sets_page = Mock(return_value=empty_page)
    empty_vault = DataVault(empty_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
    assert empty_vault.list_dataset_annotations_page("training", asset=asset).items == []

    iter_backend = Mock()
    iter_backend.list_collections = Mock(return_value=[collection])
    iter_backend.list_annotation_sets_page = Mock(side_effect=[iter_page_1, iter_page_2])
    iter_backend.get_annotation_record = Mock(return_value=record_1)
    iter_vault = DataVault(iter_backend, slow_ops_policy=SlowOpsPolicy.ALLOW)
    assert [
        record.annotation_id for record in iter_vault.iter_dataset_annotations("training", asset=asset, batch_size=1)
    ] == ["annotation_1"]


def test_sync_data_vault_eager_dataset_methods_obey_slow_ops_policy_forbid():
    backend = Mock()
    vault = DataVault(backend, slow_ops_policy=SlowOpsPolicy.FORBID)

    with pytest.raises(SlowOperationDisabledError, match="list_dataset_assets"):
        vault.list_dataset_assets("training")
    with pytest.raises(SlowOperationDisabledError, match="list_dataset_annotations"):
        vault.list_dataset_annotations("training")


@pytest.mark.asyncio
async def test_async_data_vault_eager_dataset_methods_obey_slow_ops_policy_warn():
    collection = Collection(name="training", collection_id="collection_1")
    backend = Mock()
    backend.list_collections = AsyncMock(return_value=[collection])
    backend.list_collection_items = AsyncMock(return_value=[])
    backend.list_annotation_sets_page = AsyncMock(
        return_value=AnnotationSetPageOutput(items=[], page=PageInfo(limit=1, next_cursor=None, has_more=False))
    )
    backend.list_annotation_sets = AsyncMock(return_value=[])
    vault = AsyncDataVault(backend, slow_ops_policy=SlowOpsPolicy.WARN)

    with pytest.warns(SlowOperationWarning, match="list_dataset_assets"):
        assert await vault.list_dataset_assets("training") == []
    with pytest.warns(SlowOperationWarning, match="list_dataset_annotations"):
        assert await vault.list_dataset_annotations("training") == []


def test_sync_data_vault_freeze_dataset_persists_snapshot():
    collection = Collection(name="training", collection_id="collection_1")
    item = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1", split="train")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    source_set = AnnotationSet(
        annotation_set_id="source_set_1",
        name="training:asset_1",
        purpose="ground_truth",
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
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="training", version="1.2.3"), datums=[]
    )
    datalake = Mock()
    datalake.list_collections = Mock(return_value=[collection])
    datalake.list_collection_items = Mock(return_value=[item])
    datalake.get_asset = Mock(return_value=asset)
    datalake.list_annotation_sets = Mock(return_value=[source_set])
    datalake.get_annotation_record = Mock(return_value=record)
    datalake.create_datum = Mock(return_value=SimpleNamespace(datum_id="datum_1"))
    datalake.create_annotation_set = Mock(
        return_value=AnnotationSet(
            annotation_set_id="snapshot_set_1",
            name="training:asset_1",
            purpose="ground_truth",
            source_type="human",
            status="active",
        )
    )
    datalake.add_annotation_records = Mock(return_value=[])
    datalake.create_dataset_version = Mock(return_value=DatasetVersion(dataset_name="training", version="1.2.3"))
    datalake.resolve_dataset_version = Mock(return_value=resolved)

    snapshot = DataVault(datalake)._freeze_dataset("training", persist_snapshot=True, snapshot_version="1.2.3")

    assert snapshot == resolved
    datalake.create_datum.assert_called_once()
    datalake.create_annotation_set.assert_called_once()
    datalake.add_annotation_records.assert_called_once()
    datalake.create_dataset_version.assert_called_once()
    assert datalake.create_dataset_version.call_args.kwargs["dataset_name"] == "training"
    assert datalake.create_dataset_version.call_args.kwargs["version"] == "1.2.3"
    assert datalake.create_dataset_version.call_args.kwargs["manifest"] == ["datum_1"]
    assert (
        datalake.create_dataset_version.call_args.kwargs["metadata"]["mindtrace"]["data_vault"]["source_dataset_id"]
        == "collection_1"
    )


@pytest.mark.asyncio
async def test_async_data_vault_freeze_dataset_persists_snapshot():
    collection = Collection(name="training", collection_id="collection_1")
    item = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1", split="train")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    source_set = AnnotationSet(
        annotation_set_id="source_set_1",
        name="training:asset_1",
        purpose="ground_truth",
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
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="training", version="1.2.3"), datums=[]
    )
    datalake = Mock()
    datalake.list_collections = AsyncMock(return_value=[collection])
    datalake.list_collection_items = AsyncMock(return_value=[item])
    datalake.get_asset = AsyncMock(return_value=asset)
    datalake.list_annotation_sets = AsyncMock(return_value=[source_set])
    datalake.get_annotation_record = AsyncMock(return_value=record)
    datalake.create_datum = AsyncMock(return_value=SimpleNamespace(datum_id="datum_1"))
    datalake.create_annotation_set = AsyncMock(
        return_value=AnnotationSet(
            annotation_set_id="snapshot_set_1",
            name="training:asset_1",
            purpose="ground_truth",
            source_type="human",
            status="active",
        )
    )
    datalake.add_annotation_records = AsyncMock(return_value=[])
    datalake.create_dataset_version = AsyncMock(return_value=DatasetVersion(dataset_name="training", version="1.2.3"))
    datalake.resolve_dataset_version = AsyncMock(return_value=resolved)

    snapshot = await AsyncDataVault(datalake)._freeze_dataset(
        "training", persist_snapshot=True, snapshot_version="1.2.3"
    )

    assert snapshot == resolved
    datalake.create_datum.assert_awaited_once()
    datalake.create_annotation_set.assert_awaited_once()
    datalake.add_annotation_records.assert_awaited_once()
    datalake.create_dataset_version.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_data_vault_freeze_dataset_persists_snapshot_remote_backend():
    collection = Collection(name="training", collection_id="collection_1")
    item = CollectionItem(collection_id="collection_1", asset_id="asset_1", collection_item_id="ci_1", split="train")
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    source_set = AnnotationSet(
        annotation_set_id="source_set_1",
        name="training:asset_1",
        purpose="ground_truth",
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
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    datum = Datum(datum_id="datum_1", asset_refs={"image": "asset_1"})
    dataset_version = DatasetVersion(dataset_name="training", version="1.2.3")
    resolved = ResolvedDatasetVersion(dataset_version=dataset_version, datums=[])
    cm = Mock()
    cm.acollections_list = AsyncMock(return_value=CollectionListOutput(collections=[collection]))
    cm.acollection_items_list = AsyncMock(return_value=CollectionItemListOutput(collection_items=[item]))
    cm.aassets_get = AsyncMock(return_value=AssetOutput(asset=asset))
    cm.aannotation_sets_list = AsyncMock(return_value=SimpleNamespace(annotation_sets=[source_set]))
    cm.aannotation_records_get = AsyncMock(return_value=SimpleNamespace(annotation_record=record))
    cm.adatums_create = AsyncMock(return_value=DatumOutput(datum=datum))
    cm.aannotation_sets_create = AsyncMock(
        return_value=AnnotationSetOutput(
            annotation_set=AnnotationSet(
                annotation_set_id="snapshot_set_1",
                name="training:asset_1",
                purpose="ground_truth",
                source_type="human",
                status="active",
            )
        )
    )
    cm.aannotation_records_add = AsyncMock(return_value=AddedAnnotationRecordsOutput(annotation_records=[]))
    cm.adataset_versions_create = AsyncMock(return_value=DatasetVersionOutput(dataset_version=dataset_version))
    cm.adataset_versions_resolve = AsyncMock(
        return_value=ResolvedDatasetVersionOutput(resolved_dataset_version=resolved)
    )

    snapshot = await AsyncDataVault(DatalakeServiceAsyncDataVaultBackend(cm))._freeze_dataset(
        "training",
        persist_snapshot=True,
        snapshot_version="1.2.3",
    )

    assert snapshot == resolved
    cm.adatums_create.assert_awaited_once()
    cm.aannotation_sets_create.assert_awaited_once()
    cm.aannotation_records_add.assert_awaited_once()
    cm.adataset_versions_create.assert_awaited_once()


def test_sync_data_vault_export_dataset_uses_service_backend(tmp_path: Path):
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    source_set = AnnotationSet(
        annotation_set_id="source_set_1",
        name="training:asset_1",
        purpose="ground_truth",
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
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="training", version="1.2.3"),
        datums=[
            ResolvedDatum(
                datum=Datum(datum_id="datum_1", asset_refs={"image": "asset_1"}, split="train"),
                assets={"image": asset},
                annotation_sets=[source_set],
                annotation_records={source_set.annotation_set_id: [record]},
            )
        ],
    )
    png_b64 = base64.b64encode(_pil_image_to_png_bytes(Image.new("RGB", (1, 1), color=(255, 0, 0)))).decode("ascii")
    cm = Mock()
    cm.assets_get = Mock(return_value=SimpleNamespace(asset=asset))
    cm.objects_get = Mock(
        return_value=ObjectDataOutput(
            storage_ref=asset.storage_ref,
            data_base64=png_b64,
        )
    )
    vault = DataVault(DatalakeServiceDataVaultBackend(cm))
    vault._freeze_dataset = Mock(return_value=resolved)

    result = vault.export_dataset("training", format="coco", destination=tmp_path / "coco-export", overwrite=True)

    assert result.asset_count == 1
    assert (tmp_path / "coco-export" / "annotations" / "train.json").exists()
    cm.objects_get.assert_called_once()


def test_sync_data_vault_prepare_import_target_dataset_archives_existing_collection_remote_backend():
    existing = Collection(name="training", collection_id="collection_existing")
    created = Collection(name="training", collection_id="collection_new")
    cm = Mock()
    cm.collections_list = Mock(
        side_effect=[
            CollectionListOutput(collections=[existing]),
            CollectionListOutput(collections=[]),
        ]
    )
    cm.collections_update = Mock(return_value=CollectionOutput(collection=existing))
    cm.collections_create = Mock(return_value=CollectionOutput(collection=created))

    dataset = DataVault(DatalakeServiceDataVaultBackend(cm))._prepare_import_target_dataset(
        dataset_name="training",
        description="Imported",
        metadata={"source": "snapshot"},
        overwrite=True,
        created_by="tester",
    )

    assert dataset.dataset_id == "collection_new"
    cm.collections_update.assert_called_once()


@pytest.mark.asyncio
async def test_async_data_vault_prepare_import_target_dataset_archives_existing_collection_remote_backend():
    existing = Collection(name="training", collection_id="collection_existing")
    created = Collection(name="training", collection_id="collection_new")
    cm = Mock()
    cm.acollections_list = AsyncMock(
        side_effect=[
            CollectionListOutput(collections=[existing]),
            CollectionListOutput(collections=[]),
        ]
    )
    cm.acollections_update = AsyncMock(return_value=CollectionOutput(collection=existing))
    cm.acollections_create = AsyncMock(return_value=CollectionOutput(collection=created))

    dataset = await AsyncDataVault(DatalakeServiceAsyncDataVaultBackend(cm))._prepare_import_target_dataset(
        dataset_name="training",
        description="Imported",
        metadata={"source": "snapshot"},
        overwrite=True,
        created_by="tester",
    )

    assert dataset.dataset_id == "collection_new"
    cm.acollections_update.assert_awaited_once()


def test_data_vault_import_helpers_handle_asset_selection_and_unbound_annotations():
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_1",
    )
    resolved = ResolvedDatum(
        datum=Datum(asset_refs={"other": "asset_1"}),
        assets={"other": asset},
        annotation_sets=[],
        annotation_records={},
    )
    record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        source={"type": "human", "name": "review"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )

    assert _resolved_primary_asset(resolved) == asset
    assert (
        _resolved_primary_asset(
            ResolvedDatum(datum=Datum(asset_refs={}), assets={}, annotation_sets=[], annotation_records={})
        )
        is None
    )
    assert _annotation_matches_asset(record, "asset_1") is True


def test_sync_data_vault_prepare_import_target_dataset_archives_existing_collection():
    existing = Collection(name="training", collection_id="collection_existing")
    created = Collection(name="training", collection_id="collection_new")
    datalake = Mock()
    datalake.list_collections = Mock(side_effect=[[existing], []])
    datalake.update_collection = Mock(return_value=existing)
    datalake.create_collection = Mock(return_value=created)

    dataset = DataVault(datalake)._prepare_import_target_dataset(
        dataset_name="training",
        description="Imported",
        metadata={"source": "snapshot"},
        overwrite=True,
        created_by="tester",
    )

    assert dataset.dataset_id == "collection_new"
    datalake.update_collection.assert_called_once_with("collection_existing", status="archived")


def test_sync_data_vault_prepare_import_target_dataset_rejects_existing_name_without_overwrite():
    existing = Collection(name="training", collection_id="collection_existing")
    datalake = Mock()
    datalake.list_collections = Mock(return_value=[existing])

    with pytest.raises(ValueError, match="already exists"):
        DataVault(datalake)._prepare_import_target_dataset(
            dataset_name="training",
            description="Imported",
            metadata={"source": "snapshot"},
            overwrite=False,
            created_by="tester",
        )


@pytest.mark.asyncio
async def test_async_data_vault_prepare_import_target_dataset_archives_existing_collection():
    existing = Collection(name="training", collection_id="collection_existing")
    created = Collection(name="training", collection_id="collection_new")
    datalake = Mock()
    datalake.list_collections = AsyncMock(side_effect=[[existing], []])
    datalake.update_collection = AsyncMock(return_value=existing)
    datalake.create_collection = AsyncMock(return_value=created)

    dataset = await AsyncDataVault(datalake)._prepare_import_target_dataset(
        dataset_name="training",
        description="Imported",
        metadata={"source": "snapshot"},
        overwrite=True,
        created_by="tester",
    )

    assert dataset.dataset_id == "collection_new"
    datalake.update_collection.assert_awaited_once_with("collection_existing", status="archived")


@pytest.mark.asyncio
async def test_async_data_vault_prepare_import_target_dataset_rejects_existing_name_without_overwrite():
    existing = Collection(name="training", collection_id="collection_existing")
    datalake = Mock()
    datalake.list_collections = AsyncMock(return_value=[existing])

    with pytest.raises(ValueError, match="already exists"):
        await AsyncDataVault(datalake)._prepare_import_target_dataset(
            dataset_name="training",
            description="Imported",
            metadata={"source": "snapshot"},
            overwrite=False,
            created_by="tester",
        )


def test_sync_data_vault_import_dataset_version_materializes_mutable_dataset():
    source_dataset = DatasetVersion(
        dataset_name="source-dataset", version="1.0.0", dataset_version_id="dataset_version_1"
    )
    image_asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="image", version="1"),
        asset_id="asset_image",
    )
    mask_asset = Asset(
        kind="mask",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="mask", version="1"),
        asset_id="asset_mask",
    )
    image_record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_image"),
        source={"type": "human", "name": "review"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    mask_record = AnnotationRecord(
        annotation_id="annotation_2",
        kind="bbox",
        label="mask",
        subject=SubjectRef(kind="asset", id="asset_mask"),
        source={"type": "human", "name": "review"},
        geometry={"x": 5, "y": 6, "width": 7, "height": 8},
    )
    source_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1", "annotation_2"],
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=source_dataset,
        datums=[
            ResolvedDatum(
                datum=Datum(asset_refs={"image": "asset_image"}, split="train", metadata={"row": 1}),
                assets={"image": image_asset, "mask": mask_asset},
                annotation_sets=[source_set],
                annotation_records={source_set.annotation_set_id: [image_record, mask_record]},
            )
        ],
    )
    imported_dataset = VaultDataset(
        dataset_id="collection_1",
        name="training-copy",
        created_at=Collection(name="training-copy").created_at,
        updated_at=Collection(name="training-copy").updated_at,
    )
    imported_set = AnnotationSet(
        annotation_set_id="imported_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
    )
    datalake = Mock()
    vault = DataVault(datalake)
    vault._prepare_import_target_dataset = Mock(return_value=imported_dataset)
    vault._get_dataset_collection = Mock(return_value=Collection(name="training-copy", collection_id="collection_1"))
    vault._ensure_collection_item = Mock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_image")
    )
    vault.get_dataset = Mock(return_value=imported_dataset)
    datalake.resolve_dataset_version = Mock(return_value=resolved)
    datalake.create_annotation_set = Mock(return_value=imported_set)
    datalake.add_annotation_records = Mock(return_value=[image_record])

    result = vault.import_dataset_version("source-dataset", "1.0.0", target_name="training-copy")

    assert result == imported_dataset
    vault._ensure_collection_item.assert_called_once()
    datalake.create_annotation_set.assert_called_once()
    added_payloads = datalake.add_annotation_records.call_args.args[0]
    assert len(added_payloads) == 1
    assert added_payloads[0]["subject"]["id"] == "asset_image"


def test_sync_data_vault_import_dataset_version_skips_empty_datums_and_non_primary_records():
    source_dataset = DatasetVersion(
        dataset_name="source-dataset", version="1.0.0", dataset_version_id="dataset_version_1"
    )
    image_asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="image", version="1"),
        asset_id="asset_image",
    )
    other_asset = Asset(
        kind="mask",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="mask", version="1"),
        asset_id="asset_mask",
    )
    source_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
    )
    foreign_record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="mask",
        subject=SubjectRef(kind="asset", id="asset_mask"),
        source={"type": "human", "name": "review"},
        geometry={"x": 5, "y": 6, "width": 7, "height": 8},
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=source_dataset,
        datums=[
            ResolvedDatum(
                datum=Datum(asset_refs={}),
                assets={},
                annotation_sets=[],
                annotation_records={},
            ),
            ResolvedDatum(
                datum=Datum(asset_refs={"image": "asset_image"}, split="train"),
                assets={"image": image_asset, "mask": other_asset},
                annotation_sets=[source_set],
                annotation_records={source_set.annotation_set_id: [foreign_record]},
            ),
        ],
    )
    imported_dataset = VaultDataset(
        dataset_id="collection_1",
        name="training-copy",
        created_at=Collection(name="training-copy").created_at,
        updated_at=Collection(name="training-copy").updated_at,
    )
    datalake = Mock()
    vault = DataVault(datalake)
    vault._prepare_import_target_dataset = Mock(return_value=imported_dataset)
    vault._get_dataset_collection = Mock(return_value=Collection(name="training-copy", collection_id="collection_1"))
    vault._ensure_collection_item = Mock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_image")
    )
    vault.get_dataset = Mock(return_value=imported_dataset)
    datalake.resolve_dataset_version = Mock(return_value=resolved)
    datalake.create_annotation_set = Mock()
    datalake.add_annotation_records = Mock()

    result = vault.import_dataset_version("source-dataset", "1.0.0", target_name="training-copy")

    assert result == imported_dataset
    vault._ensure_collection_item.assert_called_once()
    datalake.create_annotation_set.assert_not_called()
    datalake.add_annotation_records.assert_not_called()


def test_sync_data_vault_import_dataset_version_materializes_mutable_dataset_remote_backend():
    source_dataset = DatasetVersion(
        dataset_name="source-dataset", version="1.0.0", dataset_version_id="dataset_version_1"
    )
    image_asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="image", version="1"),
        asset_id="asset_image",
    )
    image_record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_image"),
        source={"type": "human", "name": "review"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    source_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=source_dataset,
        datums=[
            ResolvedDatum(
                datum=Datum(asset_refs={"image": "asset_image"}, split="train", metadata={"row": 1}),
                assets={"image": image_asset},
                annotation_sets=[source_set],
                annotation_records={source_set.annotation_set_id: [image_record]},
            )
        ],
    )
    imported_dataset = VaultDataset(
        dataset_id="collection_1",
        name="training-copy",
        created_at=Collection(name="training-copy").created_at,
        updated_at=Collection(name="training-copy").updated_at,
    )
    imported_set = AnnotationSet(
        annotation_set_id="imported_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
    )
    cm = Mock()
    cm.dataset_versions_resolve = Mock(return_value=ResolvedDatasetVersionOutput(resolved_dataset_version=resolved))
    cm.annotation_sets_create = Mock(return_value=AnnotationSetOutput(annotation_set=imported_set))
    cm.annotation_records_add = Mock(return_value=AddedAnnotationRecordsOutput(annotation_records=[image_record]))
    vault = DataVault(DatalakeServiceDataVaultBackend(cm))
    vault._prepare_import_target_dataset = Mock(return_value=imported_dataset)
    vault._get_dataset_collection = Mock(return_value=Collection(name="training-copy", collection_id="collection_1"))
    vault._ensure_collection_item = Mock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_image")
    )
    vault.get_dataset = Mock(return_value=imported_dataset)

    result = vault.import_dataset_version("source-dataset", "1.0.0", target_name="training-copy")

    assert result == imported_dataset
    vault._ensure_collection_item.assert_called_once()
    cm.annotation_sets_create.assert_called_once()
    added_payloads = cm.annotation_records_add.call_args.args[0].annotations
    assert len(added_payloads) == 1
    assert added_payloads[0]["subject"]["id"] == "asset_image"


@pytest.mark.asyncio
async def test_async_data_vault_import_dataset_version_materializes_mutable_dataset():
    source_dataset = DatasetVersion(
        dataset_name="source-dataset", version="1.0.0", dataset_version_id="dataset_version_1"
    )
    image_asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="image", version="1"),
        asset_id="asset_image",
    )
    image_record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="cat",
        subject=SubjectRef(kind="asset", id="asset_image"),
        source={"type": "human", "name": "review"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    source_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=source_dataset,
        datums=[
            ResolvedDatum(
                datum=Datum(asset_refs={"image": "asset_image"}, split="train", metadata={"row": 1}),
                assets={"image": image_asset},
                annotation_sets=[source_set],
                annotation_records={source_set.annotation_set_id: [image_record]},
            )
        ],
    )
    imported_dataset = VaultDataset(
        dataset_id="collection_1",
        name="training-copy",
        created_at=Collection(name="training-copy").created_at,
        updated_at=Collection(name="training-copy").updated_at,
    )
    imported_set = AnnotationSet(
        annotation_set_id="imported_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
    )
    datalake = Mock()
    vault = AsyncDataVault(datalake)
    vault._prepare_import_target_dataset = AsyncMock(return_value=imported_dataset)
    vault._get_dataset_collection = AsyncMock(
        return_value=Collection(name="training-copy", collection_id="collection_1")
    )
    vault._ensure_collection_item = AsyncMock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_image")
    )
    vault.get_dataset = AsyncMock(return_value=imported_dataset)
    datalake.resolve_dataset_version = AsyncMock(return_value=resolved)
    datalake.create_annotation_set = AsyncMock(return_value=imported_set)
    datalake.add_annotation_records = AsyncMock(return_value=[image_record])

    result = await vault.import_dataset_version("source-dataset", "1.0.0", target_name="training-copy")

    assert result == imported_dataset
    vault._ensure_collection_item.assert_awaited_once()
    datalake.create_annotation_set.assert_awaited_once()
    added_payloads = datalake.add_annotation_records.await_args.args[0]
    assert len(added_payloads) == 1
    assert added_payloads[0]["subject"]["id"] == "asset_image"


@pytest.mark.asyncio
async def test_async_data_vault_import_dataset_version_skips_empty_datums_and_non_primary_records():
    source_dataset = DatasetVersion(
        dataset_name="source-dataset", version="1.0.0", dataset_version_id="dataset_version_1"
    )
    image_asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="image", version="1"),
        asset_id="asset_image",
    )
    other_asset = Asset(
        kind="mask",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="mask", version="1"),
        asset_id="asset_mask",
    )
    source_set = AnnotationSet(
        annotation_set_id="annotation_set_1",
        name="source-set",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1"],
    )
    foreign_record = AnnotationRecord(
        annotation_id="annotation_1",
        kind="bbox",
        label="mask",
        subject=SubjectRef(kind="asset", id="asset_mask"),
        source={"type": "human", "name": "review"},
        geometry={"x": 5, "y": 6, "width": 7, "height": 8},
    )
    resolved = ResolvedDatasetVersion(
        dataset_version=source_dataset,
        datums=[
            ResolvedDatum(datum=Datum(asset_refs={}), assets={}, annotation_sets=[], annotation_records={}),
            ResolvedDatum(
                datum=Datum(asset_refs={"image": "asset_image"}, split="train"),
                assets={"image": image_asset, "mask": other_asset},
                annotation_sets=[source_set],
                annotation_records={source_set.annotation_set_id: [foreign_record]},
            ),
        ],
    )
    imported_dataset = VaultDataset(
        dataset_id="collection_1",
        name="training-copy",
        created_at=Collection(name="training-copy").created_at,
        updated_at=Collection(name="training-copy").updated_at,
    )
    datalake = Mock()
    vault = AsyncDataVault(datalake)
    vault._prepare_import_target_dataset = AsyncMock(return_value=imported_dataset)
    vault._get_dataset_collection = AsyncMock(
        return_value=Collection(name="training-copy", collection_id="collection_1")
    )
    vault._ensure_collection_item = AsyncMock(
        return_value=CollectionItem(collection_id="collection_1", asset_id="asset_image")
    )
    vault.get_dataset = AsyncMock(return_value=imported_dataset)
    datalake.resolve_dataset_version = AsyncMock(return_value=resolved)
    datalake.create_annotation_set = AsyncMock()
    datalake.add_annotation_records = AsyncMock()

    result = await vault.import_dataset_version("source-dataset", "1.0.0", target_name="training-copy")

    assert result == imported_dataset
    vault._ensure_collection_item.assert_awaited_once()
    datalake.create_annotation_set.assert_not_called()
    datalake.add_annotation_records.assert_not_called()


def test_sync_data_vault_freeze_dataset_returns_dataset_version_when_persisting():
    resolved = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="training", version="1.2.3"), datums=[]
    )
    vault = object.__new__(DataVault)
    vault._freeze_dataset = Mock(return_value=resolved)

    result = vault.freeze_dataset("training", persist=True, snapshot_version="1.2.3")

    assert result == resolved.dataset_version
    vault._freeze_dataset.assert_called_once()


@pytest.mark.asyncio
async def test_async_data_vault_freeze_dataset_returns_resolved_snapshot_when_not_persisting():
    resolved = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="training", version="1.2.3"), datums=[]
    )
    vault = object.__new__(AsyncDataVault)
    vault._freeze_dataset = AsyncMock(return_value=resolved)

    result = await vault.freeze_dataset("training", persist=False, snapshot_version="1.2.3")

    assert result == resolved
    vault._freeze_dataset.assert_awaited_once()


# --- Normalization and alias-indexing behavior (``data_vault`` + backends) ---


@pytest.fixture
def datalake_service_connection_manager(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")
    Service.config = CoreConfig()
    CM = generate_connection_manager(DatalakeService)
    return CM(url=parse_url("http://127.0.0.1:8080"))


@pytest.fixture
def mock_async_datalake_for_alias_indexing():
    dl = Mock(spec=AsyncDatalake)
    dl.ensure_primary_asset_alias = AsyncMock()
    dl.resolve_alias = AsyncMock(return_value="asset_target")
    dl.get_asset_by_alias = AsyncMock()
    dl.get_asset = AsyncMock()
    dl.add_alias = AsyncMock()
    dl.create_asset_from_object = AsyncMock()
    dl.get_object = AsyncMock(return_value=b"payload")
    dl.get_asset_payload = AsyncMock(return_value=b"payload")
    return dl


@pytest.fixture
def mock_sync_datalake_for_alias_indexing():
    dl = Mock()
    dl.get_asset_by_alias = Mock()
    dl.get_object = Mock(return_value=b"sync-payload")
    dl.get_asset_payload = Mock(return_value=b"sync-payload")
    dl.create_asset_from_object = Mock()
    dl.add_alias = Mock()
    return dl


@pytest.mark.asyncio
async def test_async_data_vault_load_delegates(mock_async_datalake_for_alias_indexing):
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_target",
    )
    mock_async_datalake_for_alias_indexing.get_asset_by_alias = AsyncMock(return_value=asset)

    vault = AsyncDataVault(mock_async_datalake_for_alias_indexing)
    out = await vault.load("my-alias")

    mock_async_datalake_for_alias_indexing.get_asset_by_alias.assert_awaited_once_with("my-alias")
    mock_async_datalake_for_alias_indexing.get_asset_payload.assert_awaited_once_with(asset.asset_id)
    assert out == b"payload"


@pytest.mark.asyncio
async def test_async_data_vault_save_registers_secondary_alias(mock_async_datalake_for_alias_indexing):
    created = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="asset_new123",
    )
    mock_async_datalake_for_alias_indexing.create_asset_from_object = AsyncMock(return_value=created)

    vault = AsyncDataVault(mock_async_datalake_for_alias_indexing)
    asset = await vault.save("friendly", b"data", kind="image", media_type="image/png")

    assert asset.asset_id == "asset_new123"
    mock_async_datalake_for_alias_indexing.create_asset_from_object.assert_awaited()
    mock_async_datalake_for_alias_indexing.add_alias.assert_awaited_once_with("asset_new123", "friendly")


@pytest.mark.asyncio
async def test_async_data_vault_save_image_records_png_size(mock_async_datalake_for_alias_indexing):
    created = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/image", version="1"),
        asset_id="asset_img",
    )
    mock_async_datalake_for_alias_indexing.create_asset_from_object = AsyncMock(return_value=created)

    image = Image.new("RGB", (2, 2), color=(12, 34, 56))
    expected_size = len(_pil_image_to_png_bytes(image))

    vault = AsyncDataVault(mock_async_datalake_for_alias_indexing)
    await vault.save_image("friendly-image", image)

    kwargs = mock_async_datalake_for_alias_indexing.create_asset_from_object.await_args.kwargs
    assert kwargs["media_type"] == "image/png"
    assert kwargs["size_bytes"] == expected_size


@pytest.mark.asyncio
async def test_async_data_vault_save_skips_add_alias_when_same_as_asset_id(mock_async_datalake_for_alias_indexing):
    created = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="same_id",
    )
    mock_async_datalake_for_alias_indexing.create_asset_from_object = AsyncMock(return_value=created)

    vault = AsyncDataVault(mock_async_datalake_for_alias_indexing)
    await vault.save("same_id", b"data", kind="artifact", media_type="application/octet-stream")

    mock_async_datalake_for_alias_indexing.add_alias.assert_not_called()


def test_data_vault_load(mock_sync_datalake_for_alias_indexing):
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    mock_sync_datalake_for_alias_indexing.get_asset_by_alias.return_value = asset

    vault = DataVault(mock_sync_datalake_for_alias_indexing)
    out = vault.load("alias1")

    mock_sync_datalake_for_alias_indexing.get_asset_by_alias.assert_called_once_with("alias1")
    mock_sync_datalake_for_alias_indexing.get_asset_payload.assert_called_once_with(asset.asset_id)
    assert out == b"sync-payload"


def test_data_vault_save_adds_secondary_alias(mock_sync_datalake_for_alias_indexing):
    created = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="new_asset",
    )
    mock_sync_datalake_for_alias_indexing.create_asset_from_object = Mock(return_value=created)

    vault = DataVault(mock_sync_datalake_for_alias_indexing)
    vault.save("friendly", b"bytes", kind="image", media_type="image/png")

    mock_sync_datalake_for_alias_indexing.add_alias.assert_called_once_with("new_asset", "friendly")


def test_data_vault_save_image_records_png_size(mock_sync_datalake_for_alias_indexing):
    created = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/image", version="1"),
        asset_id="asset_img",
    )
    mock_sync_datalake_for_alias_indexing.create_asset_from_object = Mock(return_value=created)

    image = Image.new("RGB", (2, 2), color=(12, 34, 56))
    expected_size = len(_pil_image_to_png_bytes(image))

    vault = DataVault(mock_sync_datalake_for_alias_indexing)
    vault.save_image("friendly-image", image)

    kwargs = mock_sync_datalake_for_alias_indexing.create_asset_from_object.call_args.kwargs
    assert kwargs["media_type"] == "image/png"
    assert kwargs["size_bytes"] == expected_size


def test_data_vault_rejects_incomplete_duck():
    class BadDuck:
        get_asset_by_alias = Mock()

    with pytest.raises(TypeError, match="list_assets"):
        DataVault(BadDuck())


@pytest.mark.asyncio
async def test_async_data_vault_rejects_incomplete_duck():
    class BadDuck:
        get_asset_by_alias = AsyncMock()

    with pytest.raises(TypeError, match="list_assets"):
        AsyncDataVault(BadDuck())


def test_normalize_async_backend_wraps_async_datalake_instance():
    raw = AsyncDatalake.__new__(AsyncDatalake)
    backend = _normalize_async_backend(raw)
    assert isinstance(backend, LocalAsyncDataVaultBackend)
    assert isinstance(backend, AsyncDataVaultBackend)
    assert backend._datalake is raw


def test_normalize_async_backend_passes_through_explicit_backend(mock_async_datalake_for_alias_indexing):
    inner = LocalAsyncDataVaultBackend(mock_async_datalake_for_alias_indexing)
    assert _normalize_async_backend(inner) is inner


def test_normalize_sync_backend_wraps_datalake_instance():
    raw = Datalake.__new__(Datalake)
    backend = _normalize_sync_backend(raw)
    assert isinstance(backend, LocalDataVaultBackend)
    assert isinstance(backend, DataVaultBackend)
    assert backend._datalake is raw


def test_normalize_sync_backend_passes_through_explicit_backend(mock_sync_datalake_for_alias_indexing):
    inner = LocalDataVaultBackend(mock_sync_datalake_for_alias_indexing)
    assert _normalize_sync_backend(inner) is inner


def test_normalize_sync_backend_wraps_datalake_service_client(datalake_service_connection_manager):
    cm = datalake_service_connection_manager
    backend = _normalize_sync_backend(cm)
    assert isinstance(backend, DatalakeServiceDataVaultBackend)
    assert backend._cm is cm


@pytest.mark.asyncio
async def test_normalize_async_backend_wraps_datalake_service_client(datalake_service_connection_manager):
    cm = datalake_service_connection_manager
    backend = _normalize_async_backend(cm)
    assert isinstance(backend, DatalakeServiceAsyncDataVaultBackend)
    assert backend._cm is cm


def test_data_vault_accepts_service_connection_manager(datalake_service_connection_manager):
    vault = DataVault(datalake_service_connection_manager)
    assert isinstance(vault._backend, DatalakeServiceDataVaultBackend)


def test_sanitize_object_name_component():
    assert ".." not in _sanitize_object_name_component("a/../b")
    assert _sanitize_object_name_component("ok-name_1") == "ok-name_1"


class _BrokenSuffixPath(Path):
    @property
    def suffix(self) -> str:  # type: ignore[override]
        raise RuntimeError("boom")


@pytest.mark.parametrize(
    "obj,kind,media,expected_kind,expected_media",
    [
        (b"x", "image", "image/png", "image", "image/png"),
        (bytearray(b"x"), None, None, "artifact", "application/octet-stream"),
    ],
)
def test_infer_kind_media_direct(obj, kind, media, expected_kind, expected_media):
    from mindtrace.datalake.data_vault import _infer_kind_media

    k, m = _infer_kind_media(obj, kind, media)
    assert k == expected_kind
    assert m == expected_media


def test_infer_kind_media_path_suffix_exception(tmp_path):
    from mindtrace.datalake.data_vault import _infer_kind_media

    bp = _BrokenSuffixPath(tmp_path / "x.png")
    k, m = _infer_kind_media(bp, None, None)
    assert k == "artifact"
    assert m == "application/octet-stream"


def test_infer_kind_media_path_png(tmp_path):
    from mindtrace.datalake.data_vault import _infer_kind_media

    p = tmp_path / "f.png"
    p.write_bytes(b"\x89PNG")
    k, m = _infer_kind_media(p, None, None)
    assert k == "image"
    assert m == "image/png"


def test_infer_kind_media_path_jpg(tmp_path):
    from mindtrace.datalake.data_vault import _infer_kind_media

    p = tmp_path / "f.jpeg"
    p.write_bytes(b"")
    k, m = _infer_kind_media(p, None, None)
    assert k == "image"
    assert m == "image/jpeg"


def test_infer_kind_media_path_gif_webp_artifact(tmp_path):
    from mindtrace.datalake.data_vault import _infer_kind_media

    for ext, mt in [(".gif", "image/gif"), (".webp", "image/webp"), (".bin", "application/octet-stream")]:
        p = tmp_path / f"a{ext}"
        p.write_bytes(b"1")
        k, m = _infer_kind_media(p, None, None)
        assert k == "image" if ext != ".bin" else "artifact"
        assert m == mt if ext != ".bin" else "application/octet-stream"


def test_infer_kind_media_non_bytes_uses_defaults():
    from mindtrace.datalake.data_vault import _infer_kind_media

    k, m = _infer_kind_media(object(), None, None)
    assert k == "artifact"
    assert m == "application/octet-stream"


@pytest.mark.asyncio
async def test_async_data_vault_re_raises_duplicate_alias():
    dl = MagicMock()
    dl.create_asset_from_object = AsyncMock(
        return_value=Asset.model_construct(
            asset_id="new",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="m", name="n", version="1"),
        )
    )
    dl.add_alias = AsyncMock(side_effect=DuplicateAliasError("taken"))
    dl.get_asset_by_alias = AsyncMock()

    vault = AsyncDataVault(dl)
    with pytest.raises(DuplicateAliasError, match="taken"):
        await vault.save("friendly", b"x", kind="image", media_type="image/png")


def test_data_vault_re_raises_duplicate_alias():
    dl = MagicMock()
    dl.create_asset_from_object = MagicMock(
        return_value=Asset.model_construct(
            asset_id="new",
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="m", name="n", version="1"),
        )
    )
    dl.add_alias = MagicMock(side_effect=DuplicateAliasError("taken"))
    dl.get_asset_by_alias = MagicMock()

    vault = DataVault(dl)
    with pytest.raises(DuplicateAliasError, match="taken"):
        vault.save("friendly", b"x", kind="image", media_type="image/png")


def test_data_vault_export_dataset_writes_split_aware_coco(tmp_path: Path):
    from export_test_utils import (
        png_bytes as export_png_bytes,
    )
    from export_test_utils import (
        sample_annotation_set_export,
        sample_collection_export,
    )
    from export_test_utils import (
        sample_asset as export_sample_asset,
    )

    asset = export_sample_asset()
    item = CollectionItem(collection_id="collection_1", asset_id=asset.asset_id, split="val")
    bbox = BboxAnnotation(
        label="dog",
        x=1,
        y=2,
        width=3,
        height=4,
        source={"type": "human", "name": "annotator"},
    ).to_payload()
    polygon = PolygonAnnotation(
        label="cat",
        vertices=[[0, 0], [10, 0], [10, 10]],
        source={"type": "human", "name": "annotator"},
    ).to_payload()
    classification = ClassificationAnnotation(
        label="scene",
        source={"type": "human", "name": "annotator"},
    ).to_payload()

    backend = Mock()
    backend.list_collections.return_value = [sample_collection_export()]
    backend.list_collection_items.return_value = [item]
    backend.list_annotation_sets.return_value = [
        sample_annotation_set_export(asset.asset_id, ["ann_bbox", "ann_poly", "ann_cls"])
    ]
    backend.get_annotation_record.side_effect = [
        AnnotationRecord(**bbox, annotation_id="ann_bbox"),
        AnnotationRecord(**polygon, annotation_id="ann_poly"),
        AnnotationRecord(**classification, annotation_id="ann_cls"),
    ]
    backend.get_asset.return_value = asset
    backend.get_asset_payload = Mock(return_value=export_png_bytes())

    result = DataVault(backend).export_dataset(
        "dataset-a",
        format="coco",
        destination=tmp_path / "coco",
        split_map={"val": "validation"},
    )

    payload = json.loads((tmp_path / "coco" / "annotations" / "validation.json").read_text())
    assert result.format == "coco"
    assert payload["images"][0]["file_name"] == "images/validation/asset_img.png"
    assert {category["name"] for category in payload["categories"]} == {"cat", "dog"}
    assert len(payload["annotations"]) == 2
    assert (tmp_path / "coco" / "images" / "validation" / "asset_img.png").exists()
    assert any("unsupported COCO annotation kind 'classification'" in warning for warning in result.warnings)


class _FakeHfDataset:
    def __init__(self, rows):
        self.rows = rows

    @classmethod
    def from_list(cls, rows):
        return cls(rows)

    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "dataset.json").write_text(json.dumps(self.rows, sort_keys=True))


class _FakeHfDatasetDict(dict):
    def save_to_disk(self, path: str):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        serialized = {name: dataset.rows for name, dataset in self.items()}
        (target / "dataset_dict.json").write_text(json.dumps(serialized, sort_keys=True))


@pytest.mark.asyncio
async def test_async_data_vault_export_dataset_writes_huggingface_directory(tmp_path: Path, monkeypatch):
    from export_test_utils import (
        png_bytes as export_png_bytes,
    )
    from export_test_utils import (
        sample_annotation_set_export,
        sample_collection_export,
    )
    from export_test_utils import (
        sample_asset as export_sample_asset,
    )

    from mindtrace.datalake.exporters import huggingface as huggingface_exporter

    asset = export_sample_asset()
    item = CollectionItem(collection_id="collection_1", asset_id=asset.asset_id, split="train")
    annotation = BboxAnnotation(
        label="dog",
        x=1,
        y=2,
        width=3,
        height=4,
        source={"type": "human", "name": "annotator"},
    ).to_payload()

    fake_module = SimpleNamespace(Dataset=_FakeHfDataset, DatasetDict=_FakeHfDatasetDict)
    monkeypatch.setattr(huggingface_exporter.importlib, "import_module", lambda name: fake_module)

    backend = AsyncMock()
    backend.list_collections.return_value = [sample_collection_export()]
    backend.list_collection_items.return_value = [item]
    backend.list_annotation_sets.return_value = [sample_annotation_set_export(asset.asset_id, ["ann_bbox"])]
    backend.get_annotation_record.return_value = AnnotationRecord(**annotation, annotation_id="ann_bbox")
    backend.get_asset.return_value = asset
    backend.get_asset_payload = AsyncMock(return_value=export_png_bytes())

    result = await AsyncDataVault(backend).export_dataset(
        "dataset-a",
        format="huggingface",
        destination=tmp_path / "hf",
        include_media=False,
    )

    payload = json.loads((tmp_path / "hf" / "dataset_dict.json").read_text())
    assert result.format == "huggingface"
    assert payload["train"][0]["asset_id"] == asset.asset_id
    assert payload["train"][0]["image_path"] is None
    assert payload["train"][0]["annotations"][0]["label"] == "dog"


def test_data_vault_export_dataset_rejects_unknown_format(tmp_path: Path):
    backend = Mock()
    backend.list_collections.return_value = [Collection(collection_id="collection_1", name="dataset-a")]
    backend.list_collection_items.return_value = []
    backend.list_annotation_sets.return_value = []

    with pytest.raises(ValueError, match="Unsupported dataset export format"):
        DataVault(backend).export_dataset("dataset-a", format="unknown", destination=tmp_path / "export")
