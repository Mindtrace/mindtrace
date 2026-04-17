"""Unit tests for asset alias indexing and data vault facades."""

from unittest.mock import AsyncMock, Mock

import pytest
from urllib3.util import parse_url

from mindtrace.core import CoreConfig
from mindtrace.datalake import DatalakeService
from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.data_vault import (
    AsyncDataVault,
    DataVault,
    _normalize_async_backend,
    _normalize_sync_backend,
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
from mindtrace.datalake.types import Asset, StorageRef
from mindtrace.services import Service
from mindtrace.services.core.utils import generate_connection_manager


@pytest.fixture(autouse=True)
def _minimal_service_config(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")
    Service.config = CoreConfig()


@pytest.fixture
def datalake_service_connection_manager():
    CM = generate_connection_manager(DatalakeService)
    return CM(url=parse_url("http://127.0.0.1:8080"))


@pytest.fixture
def mock_async_datalake():
    dl = Mock(spec=AsyncDatalake)
    dl.ensure_primary_asset_alias = AsyncMock()
    dl.resolve_alias = AsyncMock(return_value="asset_target")
    dl.get_asset_by_alias = AsyncMock()
    dl.get_asset = AsyncMock()
    dl.add_alias = AsyncMock()
    dl.create_asset_from_object = AsyncMock()
    dl.get_object = AsyncMock(return_value=b"payload")
    return dl


@pytest.mark.asyncio
async def test_async_data_vault_load_delegates(mock_async_datalake):
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="asset_target",
    )
    mock_async_datalake.get_asset_by_alias = AsyncMock(return_value=asset)

    vault = AsyncDataVault(mock_async_datalake)
    out = await vault.load("my-alias")

    mock_async_datalake.get_asset_by_alias.assert_awaited_once_with("my-alias")
    mock_async_datalake.get_object.assert_awaited_once_with(asset.storage_ref)
    assert out == b"payload"


@pytest.mark.asyncio
async def test_async_data_vault_save_registers_secondary_alias(mock_async_datalake):
    created = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="asset_new123",
    )
    mock_async_datalake.create_asset_from_object = AsyncMock(return_value=created)

    vault = AsyncDataVault(mock_async_datalake)
    asset = await vault.save("friendly", b"data", kind="image", media_type="image/png")

    assert asset.asset_id == "asset_new123"
    mock_async_datalake.create_asset_from_object.assert_awaited()
    mock_async_datalake.add_alias.assert_awaited_once_with("asset_new123", "friendly")


@pytest.mark.asyncio
async def test_async_data_vault_save_skips_add_alias_when_same_as_asset_id(mock_async_datalake):
    created = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="same_id",
    )
    mock_async_datalake.create_asset_from_object = AsyncMock(return_value=created)

    vault = AsyncDataVault(mock_async_datalake)
    await vault.save("same_id", b"data", kind="artifact", media_type="application/octet-stream")

    mock_async_datalake.add_alias.assert_not_called()


@pytest.fixture
def mock_sync_datalake():
    dl = Mock()
    dl.get_asset_by_alias = Mock()
    dl.get_object = Mock(return_value=b"sync-payload")
    dl.create_asset_from_object = Mock()
    dl.add_alias = Mock()
    return dl


def test_data_vault_load(mock_sync_datalake):
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="a1",
    )
    mock_sync_datalake.get_asset_by_alias.return_value = asset

    vault = DataVault(mock_sync_datalake)
    out = vault.load("alias1")

    mock_sync_datalake.get_asset_by_alias.assert_called_once_with("alias1")
    mock_sync_datalake.get_object.assert_called_once_with(asset.storage_ref)
    assert out == b"sync-payload"


def test_data_vault_save_adds_secondary_alias(mock_sync_datalake):
    created = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="new_asset",
    )
    mock_sync_datalake.create_asset_from_object = Mock(return_value=created)

    vault = DataVault(mock_sync_datalake)
    vault.save("friendly", b"bytes", kind="image", media_type="image/png")

    mock_sync_datalake.add_alias.assert_called_once_with("new_asset", "friendly")


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


def test_normalize_async_backend_passes_through_explicit_backend(mock_async_datalake):
    inner = LocalAsyncDataVaultBackend(mock_async_datalake)
    assert _normalize_async_backend(inner) is inner


def test_normalize_sync_backend_wraps_datalake_instance():
    raw = Datalake.__new__(Datalake)
    backend = _normalize_sync_backend(raw)
    assert isinstance(backend, LocalDataVaultBackend)
    assert isinstance(backend, DataVaultBackend)
    assert backend._datalake is raw


def test_normalize_sync_backend_passes_through_explicit_backend(mock_sync_datalake):
    inner = LocalDataVaultBackend(mock_sync_datalake)
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
