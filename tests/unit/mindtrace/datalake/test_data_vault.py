"""Unit tests for :mod:`mindtrace.datalake.data_vault`."""

from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.datalake.data_vault import (
    AsyncDataVault,
    DataVault,
    _annotations_bound_to_asset,
)
from mindtrace.datalake.types import AnnotationRecord, Asset, StorageRef, SubjectRef


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
