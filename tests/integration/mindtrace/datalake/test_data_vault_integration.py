"""Integration tests for :class:`~mindtrace.datalake.AsyncDataVault` and :class:`~mindtrace.datalake.DataVault`.

Requires MongoDB at ``mongodb://localhost:27018`` (see ``conftest.py``).
"""

from __future__ import annotations

import socket
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from mindtrace.datalake import AsyncDataVault, Datalake, DataVault
from mindtrace.datalake.data_vault import _pil_image_to_png_bytes

_HOPPER = Path(__file__).resolve().parents[3] / "resources" / "hopper.png"


def _mongo_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 27018), timeout=2.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _mongo_reachable(),
    reason="MongoDB required at mongodb://localhost:27018 for DataVault integration tests",
)


def _hopper_bytes() -> bytes:
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    return _HOPPER.read_bytes()


@pytest.mark.asyncio
async def test_async_data_vault_round_trip_friendly_alias_and_asset_id(async_datalake):
    vault = AsyncDataVault(async_datalake)
    raw = _hopper_bytes()

    asset = await vault.save(
        "integration-hopper",
        raw,
        kind="image",
        media_type="image/png",
        created_by="integration",
    )

    assert asset.asset_id
    assert await async_datalake.resolve_alias("integration-hopper") == asset.asset_id
    assert await async_datalake.resolve_alias(asset.asset_id) == asset.asset_id

    by_nick = await vault.load("integration-hopper")
    by_id = await vault.load(asset.asset_id)
    assert by_nick == raw
    assert by_id == raw

    aliases = await async_datalake.list_aliases_for_asset(asset.asset_id)
    assert asset.asset_id in aliases
    assert "integration-hopper" in aliases


def test_sync_data_vault_round_trip_friendly_alias_and_asset_id(sync_datalake: Datalake):
    vault = DataVault(sync_datalake)
    raw = _hopper_bytes()

    asset = vault.save(
        "sync-vault-hopper",
        raw,
        kind="image",
        media_type="image/png",
        created_by="integration",
    )

    assert asset.asset_id
    assert sync_datalake.resolve_alias("sync-vault-hopper") == asset.asset_id
    assert sync_datalake.resolve_alias(asset.asset_id) == asset.asset_id

    by_nick = vault.load("sync-vault-hopper")
    by_id = vault.load(asset.asset_id)
    assert by_nick == raw
    assert by_id == raw

    aliases = sync_datalake.list_aliases_for_asset(asset.asset_id)
    assert asset.asset_id in aliases
    assert "sync-vault-hopper" in aliases


@pytest.mark.asyncio
async def test_async_data_vault_save_load_image_hopper(async_datalake):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = AsyncDataVault(async_datalake)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"integration-hopper-pil-{uuid4().hex[:10]}"
    await vault.save_image(alias, im)
    out = await vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)


def test_sync_data_vault_save_load_image_hopper(sync_datalake: Datalake):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = DataVault(sync_datalake)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"sync-vault-pil-{uuid4().hex[:10]}"
    vault.save_image(alias, im)
    out = vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)


@pytest.mark.asyncio
async def test_async_data_vault_save_load_image_inprocess_service(datalake_service_local_manager):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = AsyncDataVault(datalake_service_local_manager)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"svc-async-pil-{uuid4().hex[:10]}"
    await vault.save_image(alias, im)
    out = await vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)


def test_sync_data_vault_save_load_image_inprocess_service(datalake_service_local_manager):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = DataVault(datalake_service_local_manager)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"svc-sync-pil-{uuid4().hex[:10]}"
    vault.save_image(alias, im)
    out = vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)
