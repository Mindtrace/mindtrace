"""Unit tests for asset alias indexing and :class:`~mindtrace.datalake.DataVault`."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from mindtrace.datalake.data_vault import DataVault, _sanitize_object_name_component
from mindtrace.datalake.types import Asset, DuplicateAliasError, StorageRef


@pytest.fixture
def mock_datalake():
    dl = MagicMock()
    dl.ensure_primary_asset_alias = AsyncMock()
    dl.resolve_alias = AsyncMock(return_value="asset_target")
    dl.get_asset_by_alias = AsyncMock()
    dl.get_asset = AsyncMock()
    dl.add_alias = AsyncMock()
    dl.create_asset_from_object = AsyncMock()
    dl.get_object = AsyncMock(return_value=b"payload")
    return dl


@pytest.mark.asyncio
async def test_data_vault_load_delegates(mock_datalake):
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_target",
    )
    mock_datalake.get_asset_by_alias = AsyncMock(return_value=asset)

    vault = DataVault(mock_datalake)
    out = await vault.load("my-alias")

    mock_datalake.get_asset_by_alias.assert_awaited_once_with("my-alias")
    mock_datalake.get_object.assert_awaited_once_with(asset.storage_ref)
    assert out == b"payload"


@pytest.mark.asyncio
async def test_data_vault_save_registers_secondary_alias(mock_datalake):
    created = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="asset_new123",
    )
    mock_datalake.create_asset_from_object = AsyncMock(return_value=created)

    vault = DataVault(mock_datalake)
    asset = await vault.save("friendly", b"data", kind="image", media_type="image/png")

    assert asset.asset_id == "asset_new123"
    mock_datalake.create_asset_from_object.assert_awaited()
    mock_datalake.add_alias.assert_awaited_once_with("asset_new123", "friendly")


@pytest.mark.asyncio
async def test_data_vault_save_skips_add_alias_when_same_as_asset_id(mock_datalake):
    created = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="same_id",
    )
    mock_datalake.create_asset_from_object = AsyncMock(return_value=created)

    vault = DataVault(mock_datalake)
    await vault.save("same_id", b"data", kind="artifact", media_type="application/octet-stream")

    mock_datalake.add_alias.assert_not_called()


def test_sanitize_object_name_component():
    assert ".." not in _sanitize_object_name_component("a/../b")
    assert _sanitize_object_name_component("ok-name_1") == "ok-name_1"
