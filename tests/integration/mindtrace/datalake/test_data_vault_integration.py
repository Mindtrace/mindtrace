"""Integration tests for :class:`~mindtrace.datalake.AsyncDataVault` and :class:`~mindtrace.datalake.DataVault`.

Requires MongoDB at ``mongodb://localhost:27018`` (see ``conftest.py``).
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from mindtrace.datalake import AsyncDataVault, DataVault, Datalake

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
