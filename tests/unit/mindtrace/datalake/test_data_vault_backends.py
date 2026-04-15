"""Unit tests for :mod:`mindtrace.datalake.data_vault_backends`."""

import base64
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.datalake.data_vault_backends import (
    DatalakeServiceAsyncDataVaultBackend,
    DatalakeServiceDataVaultBackend,
    _encode_obj_for_service,
)
from mindtrace.datalake.service_types import (
    AddAliasInput,
    AssetAliasOutput,
    AssetOutput,
    CreateAssetFromObjectInput,
    GetAssetByAliasInput,
    GetObjectInput,
    ObjectDataOutput,
)
from mindtrace.datalake.types import Asset, AssetAlias, StorageRef


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
