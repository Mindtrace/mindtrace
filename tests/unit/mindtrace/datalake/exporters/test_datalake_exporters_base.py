"""Tests for :mod:`mindtrace.datalake.exporters.base`."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from export_test_utils import (
    png_bytes,
    resolved_dataset_version,
    sample_annotation_record,
    sample_asset,
)

from mindtrace.datalake.exporters.base import (
    _annotation_subject_asset_id,
    _build_exportable_item,
    _primary_asset_entry,
    build_exportable_dataset_from_resolved_version_async,
    build_exportable_dataset_from_resolved_version_sync,
    default_export_filename,
    prepare_export_destination,
)
from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSet,
    Asset,
    DatasetVersion,
    Datum,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
)


def test_build_exportable_dataset_from_resolved_version_sync_collects_primary_asset_annotations():
    asset = sample_asset()
    non_primary_asset = Asset(
        asset_id="asset_mask",
        kind="mask",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name="asset_mask", version="1"),
    )
    rdv = resolved_dataset_version(
        asset=asset,
        annotation_records=[sample_annotation_record("annotation_1", asset_id=asset.asset_id)],
        extra_assets={"mask": non_primary_asset},
        extra_record_sets={
            "annotation_set_2": [sample_annotation_record("annotation_2", asset_id=non_primary_asset.asset_id)]
        },
    )
    datalake = Mock()
    datalake.get_asset_payload = Mock(return_value=png_bytes())

    exportable = build_exportable_dataset_from_resolved_version_sync(datalake, rdv)

    assert exportable.asset_count == 1
    assert exportable.annotation_count == 1
    assert exportable.items[0].split == "train"
    assert exportable.items[0].source_filename == "asset_img.png"
    assert exportable.items[0].annotations[0].annotation_id == "annotation_1"
    assert any("multiple assets" in warning for warning in exportable.warnings)
    assert any("has no records for asset" in warning for warning in exportable.warnings)


def test_export_snapshot_helper_handles_non_asset_subjects_and_fallback_roles():
    asset = Asset(
        asset_id="asset_other",
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="assets", name="asset_other", version="1"),
    )
    datum = ResolvedDatum(
        datum=Datum(datum_id="datum_other", asset_refs={"thumbnail": asset.asset_id}),
        assets={"thumbnail": asset},
        annotation_sets=[],
        annotation_records={},
    )
    record = AnnotationRecord(
        annotation_id="annotation_subjectless",
        kind="bbox",
        label="car",
        source={"type": "human", "name": "annotator"},
        geometry={"x": 1, "y": 2, "width": 3, "height": 4},
    )

    export_item, warnings = _build_exportable_item(datum, payload_bytes=b"payload")

    assert _annotation_subject_asset_id(record) is None
    assert _primary_asset_entry(datum) == ("thumbnail", asset)
    assert export_item is not None
    assert export_item.asset.asset_id == "asset_other"
    assert warnings == []


def test_build_exportable_dataset_sync_fallback_reads_payload_storage_ref():
    asset = sample_asset()
    asset.payload_storage_ref = StorageRef(mount="payloads", name="asset_img_payload", version="7")
    rdv = resolved_dataset_version(asset=asset)

    class _LegacySyncLoader:
        def __init__(self) -> None:
            self.get_object = Mock(return_value=png_bytes())

    datalake = _LegacySyncLoader()

    build_exportable_dataset_from_resolved_version_sync(datalake, rdv)

    datalake.get_object.assert_called_once_with(asset.payload_storage_ref)


@pytest.mark.asyncio
async def test_build_exportable_dataset_async_fallback_reads_payload_storage_ref():
    asset = sample_asset()
    asset.payload_storage_ref = StorageRef(mount="payloads", name="asset_img_payload", version="7")
    rdv = resolved_dataset_version(asset=asset)

    class _LegacyAsyncLoader:
        get_object = AsyncMock(return_value=png_bytes())

    datalake = _LegacyAsyncLoader()

    await build_exportable_dataset_from_resolved_version_async(datalake, rdv)

    datalake.get_object.assert_awaited_once_with(asset.payload_storage_ref)


def test_export_snapshot_helper_rejects_datums_without_assets():
    export_item, warnings = _build_exportable_item(
        ResolvedDatum(
            datum=Datum(datum_id="datum_empty", asset_refs={}),
            assets={},
            annotation_sets=[],
            annotation_records={},
        ),
        payload_bytes=b"",
    )

    assert export_item is None
    assert any("does not reference any assets" in warning for warning in warnings)


def test_export_snapshot_helper_warns_for_non_primary_records_in_same_set():
    asset = sample_asset()
    mask_asset = Asset(
        asset_id="asset_mask",
        kind="mask",
        media_type="image/png",
        storage_ref=StorageRef(mount="assets", name="asset_mask", version="1"),
    )
    annotation_set = AnnotationSet(
        annotation_set_id="annotation_set_mixed",
        name="mixed",
        purpose="ground_truth",
        source_type="human",
        status="active",
        annotation_record_ids=["annotation_1", "annotation_2"],
    )
    resolved_datum = ResolvedDatum(
        datum=Datum(
            datum_id="datum_1",
            asset_refs={"image": asset.asset_id, "mask": mask_asset.asset_id},
            annotation_set_ids=[annotation_set.annotation_set_id],
        ),
        assets={"image": asset, "mask": mask_asset},
        annotation_sets=[annotation_set],
        annotation_records={
            annotation_set.annotation_set_id: [
                sample_annotation_record("annotation_1", asset_id=asset.asset_id),
                sample_annotation_record("annotation_2", asset_id=mask_asset.asset_id),
            ]
        },
    )

    export_item, warnings = _build_exportable_item(resolved_datum, payload_bytes=png_bytes())

    assert export_item is not None
    assert [record.annotation_id for record in export_item.annotations] == ["annotation_1"]
    assert any("non-primary asset" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_build_exportable_dataset_from_resolved_version_async_skips_datums_without_assets():
    rdv = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="dataset-a", version="1.0.0"),
        datums=[
            ResolvedDatum(
                datum=Datum(datum_id="datum_empty", asset_refs={}),
                assets={},
                annotation_sets=[],
                annotation_records={},
            )
        ],
    )
    datalake = AsyncMock()

    exportable = await build_exportable_dataset_from_resolved_version_async(datalake, rdv)

    assert exportable.items == []
    assert any("does not reference any assets" in warning for warning in exportable.warnings)


def test_build_exportable_dataset_from_resolved_version_sync_skips_datums_without_assets():
    rdv = ResolvedDatasetVersion(
        dataset_version=DatasetVersion(dataset_name="dataset-a", version="1.0.0"),
        datums=[
            ResolvedDatum(
                datum=Datum(datum_id="datum_empty", asset_refs={}),
                assets={},
                annotation_sets=[],
                annotation_records={},
            )
        ],
    )
    datalake = Mock()

    exportable = build_exportable_dataset_from_resolved_version_sync(datalake, rdv)

    assert exportable.items == []
    assert any("does not reference any assets" in warning for warning in exportable.warnings)


def test_export_helpers_choose_stable_filenames_and_overwrite_file_destination(tmp_path: Path):
    jpeg_asset = Asset(
        asset_id="jpeg_asset",
        kind="image",
        media_type="image/jpeg",
        storage_ref=StorageRef(mount="assets", name="jpeg", version="1"),
    )
    unknown_asset = Asset(
        asset_id="blob_asset",
        kind="artifact",
        media_type="application/x-custom-export",
        storage_ref=StorageRef(mount="assets", name="blob", version="1"),
    )
    destination = tmp_path / "existing-file"
    destination.write_text("existing")

    prepared = prepare_export_destination(destination, overwrite=True)

    assert default_export_filename(jpeg_asset) == "jpeg_asset.jpg"
    assert default_export_filename(unknown_asset) == "blob_asset.bin"
    assert prepared.is_dir()


def test_prepare_export_destination_overwrites_directory(tmp_path: Path):
    destination = tmp_path / "existing-dir"
    destination.mkdir()
    (destination / "old.txt").write_text("stale")

    prepared = prepare_export_destination(destination, overwrite=True)

    assert prepared.is_dir()
    assert not (prepared / "old.txt").exists()
