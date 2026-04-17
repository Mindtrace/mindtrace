"""Unit tests for AsyncDatalake asset alias APIs (full branch coverage)."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError
from mindtrace.datalake import AsyncDatalake
from mindtrace.datalake.types import Asset, AssetAlias, DuplicateAliasError, StorageRef


def _make_store():
    store = MagicMock()
    store.default_mount = "temp"
    store.list_mount_info.return_value = {"temp": {"backend": "file:///tmp", "mutable": True}}
    store.build_key.side_effect = lambda mount, name, version=None: (
        f"{mount}/{name}" if version is None else f"{mount}/{name}@{version}"
    )
    store.save.return_value = "v1"
    store.load.return_value = b"x"
    return store


def _asset(aid: str = "asset_one") -> Asset:
    return Asset.model_construct(
        asset_id=aid,
        kind="image",
        media_type="image/png",
        storage_ref=StorageRef(mount="temp", name="o", version="1"),
    )


def _alias_row(alias: str, asset_id: str, *, is_primary: bool = False) -> AssetAlias:
    return AssetAlias.model_construct(
        alias_id="alias_id_1",
        alias=alias,
        asset_id=asset_id,
        is_primary=is_primary,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def alias_datalake():
    asset_db = AsyncMock()
    asset_db.initialize = AsyncMock()
    asset_db.insert = AsyncMock(side_effect=lambda obj: obj)
    asset_db.find = AsyncMock(return_value=[])
    asset_db.update = AsyncMock(side_effect=lambda obj: obj)
    asset_db.delete = AsyncMock()

    alias_db = AsyncMock()
    alias_db.initialize = AsyncMock()
    alias_db.insert = AsyncMock(side_effect=lambda obj: obj)
    alias_db.find = AsyncMock(return_value=[])
    alias_db.delete = AsyncMock()

    generic = AsyncMock()
    generic.initialize = AsyncMock()
    generic.insert = AsyncMock(side_effect=lambda obj: obj)
    generic.find = AsyncMock(return_value=[])
    generic.update = AsyncMock(side_effect=lambda obj: obj)
    generic.delete = AsyncMock()

    def mongo_odm(*args, **kwargs):
        model_cls = kwargs.get("model_cls")
        if model_cls is Asset:
            return asset_db
        if model_cls is AssetAlias:
            return alias_db
        return generic

    store = _make_store()
    with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", side_effect=mongo_odm):
        dl = AsyncDatalake("mongodb://test:27017", "test_db", store=store)
    return dl, asset_db, alias_db


@pytest.mark.asyncio
async def test_ensure_primary_returns_existing_matching_row(alias_datalake):
    dl, _asset_db, alias_db = alias_datalake
    asset = _asset("same")
    existing = _alias_row("same", "same", is_primary=True)
    alias_db.find.return_value = [existing]

    out = await dl.ensure_primary_asset_alias(asset)

    assert out is existing
    alias_db.insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_primary_raises_when_alias_maps_elsewhere(alias_datalake):
    dl, _asset_db, alias_db = alias_datalake
    asset = _asset("wanted")
    wrong = _alias_row("wanted", "other_id", is_primary=True)
    alias_db.find.return_value = [wrong]

    with pytest.raises(DuplicateAliasError, match="other_id"):
        await dl.ensure_primary_asset_alias(asset)


@pytest.mark.asyncio
async def test_ensure_primary_inserts_when_missing(alias_datalake):
    dl, _asset_db, alias_db = alias_datalake
    asset = _asset("new_a")
    alias_db.find.return_value = []

    await dl.ensure_primary_asset_alias(asset)

    alias_db.insert.assert_awaited_once()
    inserted = alias_db.insert.await_args.args[0]
    assert inserted.alias == "new_a"
    assert inserted.asset_id == "new_a"
    assert inserted.is_primary is True


@pytest.mark.asyncio
async def test_resolve_alias_not_found(alias_datalake):
    dl, _, alias_db = alias_datalake
    alias_db.find.return_value = []

    with pytest.raises(DocumentNotFoundError, match="nick"):
        await dl.resolve_alias("nick")


@pytest.mark.asyncio
async def test_resolve_alias_returns_asset_id(alias_datalake):
    dl, _, alias_db = alias_datalake
    alias_db.find.return_value = [_alias_row("nick", "real_id", is_primary=False)]

    assert await dl.resolve_alias("nick") == "real_id"


@pytest.mark.asyncio
async def test_add_alias_delegates_to_ensure_when_alias_equals_asset_id(alias_datalake):
    dl, asset_db, alias_db = alias_datalake
    asset = _asset("same")
    asset_db.find.return_value = [asset]
    alias_db.find.return_value = []

    await dl.add_alias("same", "same")

    alias_db.insert.assert_awaited()


@pytest.mark.asyncio
async def test_add_alias_returns_existing_same_target(alias_datalake):
    dl, asset_db, alias_db = alias_datalake
    asset = _asset("aid")
    asset_db.find.return_value = [asset]
    row = _alias_row("nick", "aid", is_primary=False)
    alias_db.find.return_value = [row]

    out = await dl.add_alias("aid", "nick")

    assert out is row
    alias_db.insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_alias_conflict_when_alias_taken(alias_datalake):
    dl, asset_db, alias_db = alias_datalake
    asset_db.find.return_value = [_asset("mine")]
    alias_db.find.return_value = [_alias_row("nick", "other", is_primary=False)]

    with pytest.raises(DuplicateAliasError, match="other"):
        await dl.add_alias("mine", "nick")


@pytest.mark.asyncio
async def test_add_alias_inserts_new_row(alias_datalake):
    dl, asset_db, alias_db = alias_datalake
    asset_db.find.return_value = [_asset("mine")]
    alias_db.find.return_value = []

    await dl.add_alias("mine", "nick")

    alias_db.insert.assert_awaited_once()
    ins = alias_db.insert.await_args.args[0]
    assert ins.alias == "nick"
    assert ins.asset_id == "mine"
    assert ins.is_primary is False


@pytest.mark.asyncio
async def test_add_alias_wraps_duplicate_insert(alias_datalake):
    dl, asset_db, alias_db = alias_datalake
    asset_db.find.return_value = [_asset("mine")]
    alias_db.find.return_value = []
    alias_db.insert = AsyncMock(side_effect=DuplicateInsertError("dup"))

    with pytest.raises(DuplicateAliasError, match="already exists"):
        await dl.add_alias("mine", "nick")


@pytest.mark.asyncio
async def test_remove_alias_not_found(alias_datalake):
    dl, _, alias_db = alias_datalake
    alias_db.find.return_value = []

    with pytest.raises(DocumentNotFoundError):
        await dl.remove_alias("missing")


@pytest.mark.asyncio
async def test_remove_alias_refuses_primary(alias_datalake):
    dl, _, alias_db = alias_datalake
    row = _alias_row("aid", "aid", is_primary=True)
    alias_db.find.return_value = [row]

    with pytest.raises(ValueError, match="primary alias"):
        await dl.remove_alias("aid")


@pytest.mark.asyncio
async def test_remove_alias_deletes_secondary(alias_datalake):
    dl, _, alias_db = alias_datalake
    row = _alias_row("nick", "aid", is_primary=False)
    row.id = "oid123"
    alias_db.find.return_value = [row]

    await dl.remove_alias("nick")

    alias_db.delete.assert_awaited_once_with("oid123")


@pytest.mark.asyncio
async def test_list_aliases_for_asset(alias_datalake):
    dl, _, alias_db = alias_datalake
    alias_db.find.return_value = [
        _alias_row("a", "x", is_primary=True),
        _alias_row("b", "x", is_primary=False),
    ]

    assert await dl.list_aliases_for_asset("x") == ["a", "b"]


@pytest.mark.asyncio
async def test_get_asset_by_alias(alias_datalake):
    dl, asset_db, alias_db = alias_datalake
    asset = _asset("target")
    alias_db.find.return_value = [_alias_row("nick", "target", is_primary=False)]
    asset_db.find.return_value = [asset]

    out = await dl.get_asset_by_alias("nick")

    assert out.asset_id == "target"


@pytest.mark.asyncio
async def test_get_asset_by_alias_propagates_resolve_failure(alias_datalake):
    dl, _, alias_db = alias_datalake
    alias_db.find.return_value = []

    with pytest.raises(DocumentNotFoundError):
        await dl.get_asset_by_alias("none")


class BrokenSuffixPath(Path):
    """Path whose ``.suffix`` raises (covers _infer_kind_media except branch)."""

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

    bp = BrokenSuffixPath(tmp_path / "x.png")
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
    from mindtrace.datalake.data_vault import AsyncDataVault

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
    from mindtrace.datalake.data_vault import DataVault

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
