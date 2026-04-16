"""Tests for :mod:`mindtrace.datalake.vault_serialization` and vault load materialization."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.datalake.data_vault import AsyncDataVault, DataVault
from mindtrace.datalake.types import Asset, StorageRef
from mindtrace.datalake.vault_serialization import (
    SERIALIZATION_METADATA_KEY,
    augment_asset_metadata_for_vault_save,
    direct_bytes_serialization_block,
    extract_serialization_block,
    materialize_payload_with_hints,
)
from mindtrace.registry import Registry


def test_augment_asset_metadata_inserts_bytes_hints_without_registry():
    meta = augment_asset_metadata_for_vault_save(b"abc", None, registry=None)
    assert SERIALIZATION_METADATA_KEY in meta
    assert meta[SERIALIZATION_METADATA_KEY]["class"] == "builtins.bytes"


def test_augment_asset_metadata_skips_when_user_provided_block():
    custom = {SERIALIZATION_METADATA_KEY: {"class": "x", "materializer": "y"}}
    out = augment_asset_metadata_for_vault_save(object(), custom, registry=None)
    assert out == custom


def test_augment_non_bytes_requires_registry():
    with pytest.raises(ValueError, match="registry"):
        augment_asset_metadata_for_vault_save(42, None, registry=None)


def test_extract_serialization_block_roundtrip():
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    block = extract_serialization_block(asset)
    assert block is not None
    assert block["materializer"] == "zenml.materializers.BytesMaterializer"


def test_materialize_payload_with_hints_bytes(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    raw = b"hello-bytes"
    block = direct_bytes_serialization_block()
    out = materialize_payload_with_hints(reg, raw, block)
    assert out == raw


def test_data_vault_load_materializes_with_mock_backend(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value=b"payload-bytes")

    vault = DataVault(backend, registry=reg)
    out = vault.load("alias")
    assert out == b"payload-bytes"


def test_data_vault_load_skips_materialize_when_disabled(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value=b"raw")

    vault = DataVault(backend, registry=reg)
    assert vault.load("alias", materialize=False) == b"raw"


@pytest.mark.asyncio
async def test_async_data_vault_load_materializes(tmp_path: Path):
    reg = Registry(tmp_path / "reg", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset_by_alias = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=b"x")

    vault = AsyncDataVault(backend, registry=reg)
    out = await vault.load("alias")
    assert out == b"x"
