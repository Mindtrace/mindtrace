"""Tests for :mod:`mindtrace.datalake.exporters.coco`."""

import json
from pathlib import Path

import pytest
from export_test_utils import png_bytes, sample_asset

from mindtrace.datalake.exporters.coco import _polygon_area, export_dataset_as_coco
from mindtrace.datalake.exporters.types import ExportableDataset, ExportableItem
from mindtrace.datalake.types import AnnotationRecord, Asset, StorageRef


def test_polygon_area_short_segment_is_zero():
    assert _polygon_area([[0, 0], [1, 1]]) == 0.0


def test_coco_export_writes_default_annotations_file_and_skips_invalid_polygon(tmp_path: Path):
    asset = sample_asset()
    polygon = AnnotationRecord(
        annotation_id="ann_poly",
        kind="polygon",
        label="cat",
        source={"type": "human", "name": "annotator"},
        geometry={"vertices": [[0, 0], [1, 1]]},
    )
    dataset = ExportableDataset(
        name="dataset-a",
        items=[
            ExportableItem(
                asset=asset,
                annotations=[polygon],
                payload_bytes=png_bytes(),
                source_filename="asset_img.png",
            )
        ],
    )

    result = export_dataset_as_coco(dataset, destination=tmp_path / "coco", include_media=False)
    payload = json.loads((tmp_path / "coco" / "annotations.json").read_text())

    assert payload["annotations"] == []
    assert any("fewer than 3 vertices" in warning for warning in result.warnings)


def test_coco_export_requires_image_payloads(tmp_path: Path):
    image_asset = sample_asset()
    no_payload_dataset = ExportableDataset(
        name="dataset-a",
        items=[ExportableItem(asset=image_asset, payload_bytes=None, source_filename="asset_img.png")],
    )
    non_image_asset = Asset(
        asset_id="asset_doc",
        kind="document",
        media_type="application/pdf",
        storage_ref=StorageRef(mount="assets", name="doc", version="1"),
    )
    non_image_dataset = ExportableDataset(
        name="dataset-a",
        items=[ExportableItem(asset=non_image_asset, payload_bytes=b"pdf", source_filename="asset_doc.pdf")],
    )

    with pytest.raises(ValueError, match="requires payload bytes"):
        export_dataset_as_coco(no_payload_dataset, destination=tmp_path / "coco-no-payload")
    with pytest.raises(ValueError, match="supports image assets only"):
        export_dataset_as_coco(non_image_dataset, destination=tmp_path / "coco-non-image")


def test_coco_export_rejects_existing_destination_without_overwrite(tmp_path: Path):
    destination = tmp_path / "coco"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="Export destination already exists"):
        export_dataset_as_coco(ExportableDataset(name="dataset-a"), destination=destination)
