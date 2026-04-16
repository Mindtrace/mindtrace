"""Tests for :mod:`mindtrace.datalake.vault_serialization` and vault load materialization."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from mindtrace.datalake.data_vault import AsyncDataVault, DataVault, _pil_image_to_png_bytes
from mindtrace.datalake.types import Asset, DuplicateAliasError, StorageRef
from mindtrace.datalake.vault_serialization import (
    BYTES_CLASS,
    SERIALIZATION_METADATA_KEY,
    augment_asset_metadata_for_vault_save,
    direct_bytes_serialization_block,
    extract_serialization_block,
    materialize_payload_with_hints,
    serialization_block_for_save,
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


def test_data_vault_save_load_image_roundtrip_sync():
    im = Image.new("RGB", (2, 2), color=(10, 20, 30))
    saved_asset: Asset | None = None
    png_payload: bytes | None = None

    def create_from_object(**kwargs):
        nonlocal saved_asset, png_payload
        png_payload = kwargs["obj"]
        assert kwargs["kind"] == "image"
        assert kwargs["media_type"] == "image/png"
        assert isinstance(png_payload, bytes)
        assert png_payload.startswith(b"\x89PNG\r\n\x1a\n")
        saved_asset = Asset(
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="m", name=kwargs["name"], version="1"),
            asset_id="id1",
            metadata=dict(kwargs["asset_metadata"] or {}),
        )
        return saved_asset

    backend = Mock()
    backend.create_asset_from_object = Mock(side_effect=create_from_object)
    backend.add_alias = Mock()
    backend.get_asset_by_alias = Mock(side_effect=lambda _a: saved_asset)
    backend.get_object = Mock(side_effect=lambda _ref: png_payload)

    vault = DataVault(backend)
    vault.save_image("pic", im)
    out = vault.load_image("pic")
    assert out.mode == im.mode and out.size == im.size and out.tobytes() == im.tobytes()


@pytest.mark.asyncio
async def test_data_vault_save_load_image_roundtrip_async():
    im = Image.new("RGB", (2, 2), color=(40, 50, 60))
    saved_asset: Asset | None = None
    png_payload: bytes | None = None

    async def create_from_object(**kwargs):
        nonlocal saved_asset, png_payload
        png_payload = kwargs["obj"]
        assert kwargs["kind"] == "image"
        assert kwargs["media_type"] == "image/png"
        saved_asset = Asset(
            kind="image",
            media_type="image/png",
            storage_ref=StorageRef(mount="m", name=kwargs["name"], version="1"),
            asset_id="id1",
            metadata=dict(kwargs["asset_metadata"] or {}),
        )
        return saved_asset

    backend = Mock()
    backend.create_asset_from_object = AsyncMock(side_effect=create_from_object)
    backend.add_alias = AsyncMock()
    backend.get_asset_by_alias = AsyncMock(side_effect=lambda _a: saved_asset)
    backend.get_object = AsyncMock(side_effect=lambda _ref: png_payload)

    vault = AsyncDataVault(backend)
    await vault.save_image("pic", im)
    out = await vault.load_image("pic")
    assert out.mode == im.mode and out.size == im.size and out.tobytes() == im.tobytes()


def test_data_vault_save_image_rejects_non_pil():
    backend = Mock()
    vault = DataVault(backend)
    with pytest.raises(TypeError, match="PIL.Image.Image"):
        vault.save_image("x", "not-an-image")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_async_save_image_rejects_non_pil():
    vault = AsyncDataVault(Mock())
    with pytest.raises(TypeError, match="PIL.Image.Image"):
        await vault.save_image("x", "no")  # type: ignore[arg-type]


def test_load_image_raises_on_non_image_payload():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="id1",
        metadata={},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value="not-bytes")
    vault = DataVault(backend)
    with pytest.raises(TypeError, match="load_image expected"):
        vault.load_image("x")


@pytest.mark.asyncio
async def test_async_load_image_raises_on_non_image_payload():
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="id1",
        metadata={},
    )
    backend = Mock()
    backend.get_asset_by_alias = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=[])
    vault = AsyncDataVault(backend)
    with pytest.raises(TypeError, match="load_image expected"):
        await vault.load_image("x")


def test_load_image_decodes_bytearray_payload():
    im = Image.new("RGB", (1, 1), color=(9, 8, 7))
    png = _pil_image_to_png_bytes(im)
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="id1",
        metadata={},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value=bytearray(png))
    vault = DataVault(backend)
    out = vault.load_image("x")
    assert out.mode == im.mode and out.tobytes() == im.tobytes()


def test_load_image_passes_through_pil_payload():
    im = Image.new("RGB", (1, 1), color=(1, 2, 3))
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        asset_id="id1",
        metadata={},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value=im)
    vault = DataVault(backend)
    assert vault.load_image("x") is im


def test_direct_bytes_block_custom_files_and_init():
    b = direct_bytes_serialization_block(init_params={"a": 1}, files=("custom.bin",))
    assert b["init_params"] == {"a": 1}
    assert b["_files"] == ["custom.bin"]


def test_serialization_block_for_save_path(tmp_path: Path):
    p = tmp_path / "f.png"
    p.write_bytes(b"x")
    block = serialization_block_for_save(p, registry=None)
    assert block["class"] == BYTES_CLASS


def test_augment_metadata_for_path(tmp_path: Path):
    p = tmp_path / "g.png"
    p.write_bytes(b"x")
    meta = augment_asset_metadata_for_vault_save(p, None, registry=None)
    assert SERIALIZATION_METADATA_KEY in meta


def test_serialization_block_for_save_with_registry_int(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    block = serialization_block_for_save(42, registry=reg)
    assert block["class"] == "builtins.int"
    assert "BuiltInMaterializer" in block["materializer"]


def test_extract_serialization_block_non_dict():
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: "bad"},
    )
    assert extract_serialization_block(asset) is None


def test_extract_serialization_block_missing_keys():
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: {"class": "a"}},
    )
    assert extract_serialization_block(asset) is None


def test_materialize_multi_file_raises(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    block = direct_bytes_serialization_block()
    block["_files"] = ["a", "b"]
    with pytest.raises(NotImplementedError, match="multi-file"):
        materialize_payload_with_hints(reg, b"x", block)


def test_materialize_non_dict_init_params_ignored(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    block = direct_bytes_serialization_block()
    block["init_params"] = "not-a-dict"
    out = materialize_payload_with_hints(reg, b"y", block)
    assert out == b"y"


def test_materialize_files_list_invalid_elements_falls_back_to_default(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    block = direct_bytes_serialization_block()
    block["_files"] = [1, 2]
    out = materialize_payload_with_hints(reg, b"z", block)
    assert out == b"z"


def test_materialize_explicit_data_txt_files_list(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    block = direct_bytes_serialization_block()
    block["_files"] = ["data.txt"]
    out = materialize_payload_with_hints(reg, b"q", block)
    assert out == b"q"


def test_load_skips_materialize_when_no_registry():
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value=b"raw")
    vault = DataVault(backend, registry=None)
    assert vault.load("a") == b"raw"


def test_load_skips_when_no_serialization_hints(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value=b"payload")
    vault = DataVault(backend, registry=reg)
    assert vault.load("a") == b"payload"


def test_load_skips_materialize_when_payload_not_bytes(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset_by_alias = Mock(return_value=asset)
    backend.get_object = Mock(return_value=[1, 2])
    vault = DataVault(backend, registry=reg)
    assert vault.load("a") == [1, 2]


@pytest.mark.asyncio
async def test_async_load_skips_materialize_without_hints(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={},
    )
    backend = Mock()
    backend.get_asset_by_alias = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=b"payload")
    vault = AsyncDataVault(backend, registry=reg)
    assert await vault.load("a") == b"payload"


@pytest.mark.asyncio
async def test_async_load_skips_materialize_when_payload_not_bytes(tmp_path: Path):
    reg = Registry(tmp_path / "r", version_objects=False, mutable=True)
    asset = Asset(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="m", name="n", version="1"),
        metadata={SERIALIZATION_METADATA_KEY: direct_bytes_serialization_block()},
    )
    backend = Mock()
    backend.get_asset_by_alias = AsyncMock(return_value=asset)
    backend.get_object = AsyncMock(return_value=[1, 2])
    vault = AsyncDataVault(backend, registry=reg)
    assert await vault.load("a") == [1, 2]


@pytest.mark.asyncio
async def test_async_save_image_propagates_duplicate_alias_error():
    im = Image.new("RGB", (1, 1), color=(1, 2, 3))
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="asset-id-other",
    )
    backend = Mock()
    backend.create_asset_from_object = AsyncMock(return_value=asset)
    backend.add_alias = AsyncMock(side_effect=DuplicateAliasError("alias clash"))
    vault = AsyncDataVault(backend)
    with pytest.raises(DuplicateAliasError, match="alias clash"):
        await vault.save_image("friendly", im)


def test_sync_save_image_propagates_duplicate_alias_error():
    im = Image.new("RGB", (1, 1), color=(1, 2, 3))
    asset = Asset(
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="m", name="vault/x", version="1"),
        asset_id="asset-id-other",
    )
    backend = Mock()
    backend.create_asset_from_object = Mock(return_value=asset)
    backend.add_alias = Mock(side_effect=DuplicateAliasError("alias clash"))
    vault = DataVault(backend)
    with pytest.raises(DuplicateAliasError, match="alias clash"):
        vault.save_image("friendly", im)


def test_png_roundtrip_helper_matches_save_image_encoding():
    im = Image.new("RGBA", (2, 1), color=(255, 0, 0, 128))
    assert _pil_image_to_png_bytes(im).startswith(b"\x89PNG\r\n\x1a\n")
