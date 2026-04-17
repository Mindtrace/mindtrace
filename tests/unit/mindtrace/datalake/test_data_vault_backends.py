"""Unit tests for :mod:`mindtrace.datalake.data_vault_backends`."""

import base64
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.datalake.data_vault import _normalize_async_backend, _normalize_sync_backend
from mindtrace.datalake.data_vault_backends import (
    DatalakeServiceAsyncDataVaultBackend,
    DatalakeServiceDataVaultBackend,
    LocalAsyncDataVaultBackend,
    LocalDataVaultBackend,
    _encode_obj_for_service,
    looks_like_datalake_service_async_client,
    looks_like_datalake_service_sync_client,
)
from mindtrace.datalake.pagination_types import CursorPage, PageInfo
from mindtrace.datalake.service_types import (
    AddAliasInput,
    AddAnnotationRecordsInput,
    AddedAnnotationRecordsOutput,
    AnnotationRecordListOutput,
    AssetAliasOutput,
    AssetListOutput,
    AssetOutput,
    AssetPageOutput,
    CreateAssetFromObjectInput,
    GetAssetByAliasInput,
    GetByIdInput,
    ListAnnotationRecordsForAssetInput,
    ListInput,
    ObjectDataOutput,
    PageInput,
)
from mindtrace.datalake.types import AnnotationRecord, Asset, AssetAlias, StorageRef, SubjectRef


@pytest.mark.parametrize(
    ("obj", "expected_raw"),
    [
        ("hello", b"hello"),
        (b"\x00\xff", b"\x00\xff"),
        (bytearray(b"ab"), b"ab"),
    ],
)
def test_encode_obj_for_service_accepts_str_bytes_bytearray(obj, expected_raw):
    assert _encode_obj_for_service(obj) == base64.b64encode(expected_raw).decode("ascii")


def test_encode_obj_for_service_rejects_unsupported_type():
    with pytest.raises(TypeError, match="materializer"):
        _encode_obj_for_service(42)


@pytest.mark.asyncio
async def test_datalake_service_async_backend_list_and_get_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    cm = Mock()
    cm.aassets_list = AsyncMock(return_value=AssetListOutput(assets=[asset]))
    cm.aassets_get = AsyncMock(return_value=AssetOutput(asset=asset))

    backend = DatalakeServiceAsyncDataVaultBackend(cm)
    assert await backend.list_assets({"kind": "image"}) == [asset]
    lin = cm.aassets_list.await_args.args[0]
    assert isinstance(lin, ListInput)
    assert lin.filters == {"kind": "image"}

    assert await backend.get_asset("a1") is asset
    gin = cm.aassets_get.await_args.args[0]
    assert isinstance(gin, GetByIdInput)
    assert gin.id == "a1"


@pytest.mark.asyncio
async def test_datalake_service_async_backend_list_assets_page_and_iter_assets():
    asset_1 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n-1", version="1"),
        asset_id="a1",
    )
    asset_2 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n-2", version="1"),
        asset_id="a2",
    )
    first_page = AssetPageOutput(
        items=[asset_1],
        page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True, total_count=2),
    )
    second_page = AssetPageOutput(
        items=[asset_2],
        page=PageInfo(limit=1, next_cursor=None, has_more=False),
    )
    cm = Mock()
    cm.aassets_list_page = AsyncMock(side_effect=[first_page, first_page, second_page])

    backend = DatalakeServiceAsyncDataVaultBackend(cm)
    assert await backend.list_assets_page(filters={"kind": "image"}, limit=1, include_total=True) == first_page
    page_input = cm.aassets_list_page.await_args_list[0].args[0]
    assert isinstance(page_input, PageInput)
    assert page_input.filters == {"kind": "image"}
    assert page_input.limit == 1
    assert page_input.include_total is True

    assert [asset async for asset in backend.iter_assets(filters={"kind": "image"}, batch_size=1)] == [asset_1, asset_2]
    first_iter_input = cm.aassets_list_page.await_args_list[1].args[0]
    second_iter_input = cm.aassets_list_page.await_args_list[2].args[0]
    assert first_iter_input.cursor is None
    assert second_iter_input.cursor == "cursor-1"


@pytest.mark.asyncio
async def test_datalake_service_async_backend_get_asset_by_alias():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    cm = Mock()
    cm.aassets_get_by_alias = AsyncMock(return_value=AssetOutput(asset=asset))

    backend = DatalakeServiceAsyncDataVaultBackend(cm)
    out = await backend.get_asset_by_alias("my-alias")

    assert out is asset
    cm.aassets_get_by_alias.assert_awaited_once()
    call_arg = cm.aassets_get_by_alias.await_args.args[0]
    assert isinstance(call_arg, GetAssetByAliasInput)
    assert call_arg.alias == "my-alias"


@pytest.mark.asyncio
async def test_datalake_service_async_backend_get_object_decodes_base64():
    ref = StorageRef(mount="m", name="n", version="1")
    cm = Mock()
    cm.aobjects_get = AsyncMock(
        return_value=ObjectDataOutput(storage_ref=ref, data_base64=base64.b64encode(b"xyz").decode("ascii"))
    )

    backend = DatalakeServiceAsyncDataVaultBackend(cm)
    out = await backend.get_object(ref)

    assert out == b"xyz"


@pytest.mark.asyncio
async def test_datalake_service_async_backend_get_object_rejects_kwargs():
    ref = StorageRef(mount="m", name="n", version="1")
    backend = DatalakeServiceAsyncDataVaultBackend(Mock())

    with pytest.raises(TypeError, match="does not support extra kwargs"):
        await backend.get_object(ref, foo=1)


@pytest.mark.asyncio
async def test_datalake_service_async_backend_create_asset_from_object():
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="new",
    )
    cm = Mock()
    cm.aassets_create_from_object = AsyncMock(return_value=AssetOutput(asset=asset))

    backend = DatalakeServiceAsyncDataVaultBackend(cm)
    out = await backend.create_asset_from_object(
        name="vault/x",
        obj=b"raw",
        kind="artifact",
        media_type="application/octet-stream",
        mount="m",
        created_by="t",
    )

    assert out is asset
    cm.aassets_create_from_object.assert_awaited_once()
    inp = cm.aassets_create_from_object.await_args.args[0]
    assert isinstance(inp, CreateAssetFromObjectInput)
    assert inp.data_base64 == base64.b64encode(b"raw").decode("ascii")
    assert inp.name == "vault/x"
    assert inp.created_by == "t"


@pytest.mark.asyncio
async def test_datalake_service_async_backend_add_alias():
    row = AssetAlias(alias="friendly", asset_id="a1", is_primary=False)
    cm = Mock()
    cm.aaliases_add = AsyncMock(return_value=AssetAliasOutput(asset_alias=row))

    backend = DatalakeServiceAsyncDataVaultBackend(cm)
    out = await backend.add_alias("a1", "friendly")

    assert out is row
    cm.aaliases_add.assert_awaited_once()
    inp = cm.aaliases_add.await_args.args[0]
    assert isinstance(inp, AddAliasInput)
    assert inp.asset_id == "a1"
    assert inp.alias == "friendly"


@pytest.mark.asyncio
async def test_datalake_service_async_backend_call_raises_when_no_method():
    backend = DatalakeServiceAsyncDataVaultBackend(object())

    with pytest.raises(AttributeError, match="has none of"):
        await backend._call("aassets_get_by_alias", input_obj=GetAssetByAliasInput(alias="x"))


def test_datalake_service_sync_backend_list_and_get_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    cm = Mock()
    cm.assets_list = Mock(return_value=AssetListOutput(assets=[asset]))
    cm.assets_get = Mock(return_value=AssetOutput(asset=asset))

    backend = DatalakeServiceDataVaultBackend(cm)
    assert backend.list_assets({"kind": "image"}) == [asset]
    lin = cm.assets_list.call_args.args[0]
    assert isinstance(lin, ListInput)
    assert lin.filters == {"kind": "image"}

    assert backend.get_asset("a1") is asset
    gin = cm.assets_get.call_args.args[0]
    assert isinstance(gin, GetByIdInput)
    assert gin.id == "a1"


def test_datalake_service_sync_backend_list_assets_page_and_iter_assets():
    asset_1 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n-1", version="1"),
        asset_id="a1",
    )
    asset_2 = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n-2", version="1"),
        asset_id="a2",
    )
    first_page = AssetPageOutput(
        items=[asset_1],
        page=PageInfo(limit=1, next_cursor="cursor-1", has_more=True, total_count=2),
    )
    second_page = AssetPageOutput(
        items=[asset_2],
        page=PageInfo(limit=1, next_cursor=None, has_more=False),
    )
    cm = Mock()
    cm.assets_list_page = Mock(side_effect=[first_page, first_page, second_page])

    backend = DatalakeServiceDataVaultBackend(cm)
    assert backend.list_assets_page(filters={"kind": "image"}, limit=1, include_total=True) == first_page
    page_input = cm.assets_list_page.call_args_list[0].args[0]
    assert isinstance(page_input, PageInput)
    assert page_input.filters == {"kind": "image"}
    assert page_input.limit == 1
    assert page_input.include_total is True

    assert list(backend.iter_assets(filters={"kind": "image"}, batch_size=1)) == [asset_1, asset_2]
    first_iter_input = cm.assets_list_page.call_args_list[1].args[0]
    second_iter_input = cm.assets_list_page.call_args_list[2].args[0]
    assert first_iter_input.cursor is None
    assert second_iter_input.cursor == "cursor-1"


def test_datalake_service_sync_backend_get_asset_by_alias():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    cm = Mock()
    cm.assets_get_by_alias = Mock(return_value=AssetOutput(asset=asset))

    backend = DatalakeServiceDataVaultBackend(cm)
    out = backend.get_asset_by_alias("alias")

    assert out is asset
    cm.assets_get_by_alias.assert_called_once()


def test_datalake_service_sync_backend_get_object_decodes_base64():
    ref = StorageRef(mount="m", name="n", version="1")
    cm = Mock()
    cm.objects_get = Mock(
        return_value=ObjectDataOutput(storage_ref=ref, data_base64=base64.b64encode(b"hi").decode("ascii"))
    )

    backend = DatalakeServiceDataVaultBackend(cm)
    assert backend.get_object(ref) == b"hi"


def test_datalake_service_sync_backend_get_object_rejects_kwargs():
    ref = StorageRef(mount="m", name="n", version="1")
    backend = DatalakeServiceDataVaultBackend(Mock())

    with pytest.raises(TypeError, match="does not support extra kwargs"):
        backend.get_object(ref, version_hint="latest")


def test_datalake_service_sync_backend_create_and_add_alias():
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="id1",
    )
    row = AssetAlias(alias="f", asset_id="id1", is_primary=False)
    cm = Mock()
    cm.assets_create_from_object = Mock(return_value=AssetOutput(asset=asset))
    cm.aliases_add = Mock(return_value=AssetAliasOutput(asset_alias=row))

    backend = DatalakeServiceDataVaultBackend(cm)
    assert backend.create_asset_from_object(name="n", obj=b"b", kind="artifact", media_type="application/octet-stream") is asset
    assert backend.add_alias("id1", "f") is row


def test_datalake_service_sync_backend_call_raises_when_no_method():
    backend = DatalakeServiceDataVaultBackend(object())

    with pytest.raises(AttributeError, match="has none of"):
        backend._call("assets_get_by_alias", input_obj=GetAssetByAliasInput(alias="x"))


class _SyncServiceFacade:
    """Non-:class:`~mindtrace.services.ConnectionManager` object with service task methods (in-process test client)."""

    def assets_get(self, *_a, **_kw):
        return None

    def assets_list(self, *_a, **_kw):
        return None

    def assets_list_page(self, *_a, **_kw):
        return None

    def assets_get_by_alias(self, *_a, **_kw):
        return None

    def objects_get(self, *_a, **_kw):
        return None

    def assets_create_from_object(self, *_a, **_kw):
        return None

    def aliases_add(self, *_a, **_kw):
        return None


def test_looks_like_datalake_service_sync_client_accepts_facade():
    assert looks_like_datalake_service_sync_client(_SyncServiceFacade()) is True


def test_looks_like_datalake_service_sync_client_rejects_mock():
    cm = Mock()
    cm.assets_get_by_alias = Mock()
    cm.objects_get = Mock()
    cm.assets_create_from_object = Mock()
    cm.aliases_add = Mock()
    assert looks_like_datalake_service_sync_client(cm) is False


def test_normalize_sync_backend_wraps_service_facade():
    backend = _normalize_sync_backend(_SyncServiceFacade())
    assert isinstance(backend, DatalakeServiceDataVaultBackend)


class _LegacySyncDuckBackend:
    def list_assets(self, *_a, **_kw):
        return []

    def get_asset_by_alias(self, *_a, **_kw):
        return None

    def get_object(self, *_a, **_kw):
        return b""

    def create_asset_from_object(self, *_a, **_kw):
        return None

    def add_alias(self, *_a, **_kw):
        return None


def test_normalize_sync_backend_rejects_legacy_duck_backend_missing_scalable_methods():
    with pytest.raises(TypeError, match="list_assets_page|iter_assets"):
        _normalize_sync_backend(_LegacySyncDuckBackend())


class _AsyncServiceFacade:
    async def aassets_get(self, *_a, **_kw):
        return None

    async def aassets_list(self, *_a, **_kw):
        return None

    async def aassets_list_page(self, *_a, **_kw):
        return None

    async def aassets_get_by_alias(self, *_a, **_kw):
        return None

    async def aobjects_get(self, *_a, **_kw):
        return None

    async def aassets_create_from_object(self, *_a, **_kw):
        return None

    async def aaliases_add(self, *_a, **_kw):
        return None


def test_looks_like_datalake_service_async_client_accepts_facade():
    assert looks_like_datalake_service_async_client(_AsyncServiceFacade()) is True


def test_looks_like_datalake_service_async_client_rejects_mock():
    cm = Mock()
    cm.aassets_get_by_alias = AsyncMock()
    cm.aobjects_get = AsyncMock()
    cm.aassets_create_from_object = AsyncMock()
    cm.aaliases_add = AsyncMock()
    assert looks_like_datalake_service_async_client(cm) is False


def test_normalize_async_backend_wraps_service_facade():
    backend = _normalize_async_backend(_AsyncServiceFacade())
    assert isinstance(backend, DatalakeServiceAsyncDataVaultBackend)


class _LegacyAsyncDuckBackend:
    async def list_assets(self, *_a, **_kw):
        return []

    async def get_asset_by_alias(self, *_a, **_kw):
        return None

    async def get_object(self, *_a, **_kw):
        return b""

    async def create_asset_from_object(self, *_a, **_kw):
        return None

    async def add_alias(self, *_a, **_kw):
        return None


def test_normalize_async_backend_rejects_legacy_duck_backend_missing_scalable_methods():
    with pytest.raises(TypeError, match="list_assets_page|iter_assets"):
        _normalize_async_backend(_LegacyAsyncDuckBackend())


@pytest.mark.asyncio
async def test_local_async_backend_delegates_annotation_methods():
    rec = AnnotationRecord(
        kind="bbox",
        label="x",
        subject=SubjectRef(kind="asset", id="a1"),
        source={"type": "human", "name": "t"},
        geometry={},
    )
    dl = AsyncMock()
    dl.add_annotation_records = AsyncMock(return_value=[rec])
    dl.list_annotation_records_for_asset = AsyncMock(return_value=[rec])

    backend = LocalAsyncDataVaultBackend(dl)
    assert await backend.add_annotation_records([{"kind": "bbox"}], annotation_set_id="s1") == [rec]
    dl.add_annotation_records.assert_awaited_once_with([{"kind": "bbox"}], annotation_set_id="s1", annotation_schema_id=None)
    assert await backend.list_annotation_records_for_asset("a1") == [rec]
    dl.list_annotation_records_for_asset.assert_awaited_once_with("a1")


@pytest.mark.asyncio
async def test_local_async_backend_delegates_list_and_get_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    dl = AsyncMock()
    dl.list_assets = AsyncMock(return_value=[asset])
    dl.get_asset = AsyncMock(return_value=asset)
    backend = LocalAsyncDataVaultBackend(dl)
    assert await backend.list_assets() == [asset]
    dl.list_assets.assert_awaited_once_with(None)
    assert await backend.get_asset("a1") is asset
    dl.get_asset.assert_awaited_once_with("a1")


@pytest.mark.asyncio
async def test_local_async_backend_delegates_page_and_iterator_methods():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    page = CursorPage(items=[asset], page=PageInfo(limit=1, next_cursor=None, has_more=False))
    dl = AsyncMock()
    dl.list_assets_page = AsyncMock(return_value=page)

    async def iter_assets(**kwargs):
        assert kwargs == {"filters": {"kind": "image"}, "sort": "created_desc", "batch_size": 5}
        yield asset

    dl.iter_assets = iter_assets

    backend = LocalAsyncDataVaultBackend(dl)
    assert await backend.list_assets_page(filters={"kind": "image"}, limit=1) == page
    dl.list_assets_page.assert_awaited_once_with(
        filters={"kind": "image"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    assert [item async for item in backend.iter_assets(filters={"kind": "image"}, batch_size=5)] == [asset]


def test_local_sync_backend_delegates_list_and_get_asset():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    dl = Mock()
    dl.list_assets = Mock(return_value=[asset])
    dl.get_asset = Mock(return_value=asset)
    backend = LocalDataVaultBackend(dl)
    assert backend.list_assets() == [asset]
    dl.list_assets.assert_called_once_with(None)
    assert backend.get_asset("a1") is asset
    dl.get_asset.assert_called_once_with("a1")


def test_local_sync_backend_delegates_page_and_iterator_methods():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    page = CursorPage(items=[asset], page=PageInfo(limit=1, next_cursor=None, has_more=False))
    dl = Mock()
    dl.list_assets_page = Mock(return_value=page)
    dl.iter_assets = Mock(return_value=iter([asset]))

    backend = LocalDataVaultBackend(dl)
    assert backend.list_assets_page(filters={"kind": "image"}, limit=1) == page
    dl.list_assets_page.assert_called_once_with(
        filters={"kind": "image"},
        sort="created_desc",
        limit=1,
        cursor=None,
        include_total=False,
    )
    assert list(backend.iter_assets(filters={"kind": "image"}, batch_size=5)) == [asset]
    dl.iter_assets.assert_called_once_with(filters={"kind": "image"}, sort="created_desc", batch_size=5)


def test_local_sync_backend_delegates_annotation_methods():
    rec = AnnotationRecord(
        kind="bbox",
        label="x",
        subject=SubjectRef(kind="asset", id="a1"),
        source={"type": "human", "name": "t"},
        geometry={},
    )
    dl = Mock()
    dl.add_annotation_records = Mock(return_value=[rec])
    dl.list_annotation_records_for_asset = Mock(return_value=[rec])

    backend = LocalDataVaultBackend(dl)
    assert backend.add_annotation_records([{"kind": "bbox"}], annotation_schema_id="sch") == [rec]
    dl.add_annotation_records.assert_called_once_with([{"kind": "bbox"}], annotation_set_id=None, annotation_schema_id="sch")
    assert backend.list_annotation_records_for_asset("a1") == [rec]
    dl.list_annotation_records_for_asset.assert_called_once_with("a1")


@pytest.mark.asyncio
async def test_datalake_service_async_backend_add_and_list_annotation_records():
    rec = AnnotationRecord(
        kind="bbox",
        label="x",
        subject=SubjectRef(kind="asset", id="a1"),
        source={"type": "human", "name": "t"},
        geometry={},
    )
    cm = Mock()
    cm.aannotation_records_add = AsyncMock(return_value=AddedAnnotationRecordsOutput(annotation_records=[rec]))
    cm.aannotation_records_list_for_asset = AsyncMock(return_value=AnnotationRecordListOutput(annotation_records=[rec]))

    backend = DatalakeServiceAsyncDataVaultBackend(cm)
    out = await backend.add_annotation_records([{"kind": "bbox"}], annotation_set_id="s1")
    assert out == [rec]
    cm.aannotation_records_add.assert_awaited_once()
    inp = cm.aannotation_records_add.await_args.args[0]
    assert isinstance(inp, AddAnnotationRecordsInput)
    assert inp.annotations == [{"kind": "bbox"}]
    assert inp.annotation_set_id == "s1"

    listed = await backend.list_annotation_records_for_asset("a1")
    assert listed == [rec]
    linp = cm.aannotation_records_list_for_asset.await_args.args[0]
    assert isinstance(linp, ListAnnotationRecordsForAssetInput)
    assert linp.asset_id == "a1"


def test_datalake_service_sync_backend_add_and_list_annotation_records():
    rec = AnnotationRecord(
        kind="bbox",
        label="x",
        subject=SubjectRef(kind="asset", id="a1"),
        source={"type": "human", "name": "t"},
        geometry={},
    )
    cm = Mock()
    cm.annotation_records_add = Mock(return_value=AddedAnnotationRecordsOutput(annotation_records=[rec]))
    cm.annotation_records_list_for_asset = Mock(return_value=AnnotationRecordListOutput(annotation_records=[rec]))

    backend = DatalakeServiceDataVaultBackend(cm)
    out = backend.add_annotation_records([{"kind": "bbox"}], annotation_set_id="s1")
    assert out == [rec]
    inp = cm.annotation_records_add.call_args.args[0]
    assert isinstance(inp, AddAnnotationRecordsInput)
    assert inp.annotation_set_id == "s1"

    listed = backend.list_annotation_records_for_asset("a1")
    assert listed == [rec]
    linp = cm.annotation_records_list_for_asset.call_args.args[0]
    assert isinstance(linp, ListAnnotationRecordsForAssetInput)
    assert linp.asset_id == "a1"
