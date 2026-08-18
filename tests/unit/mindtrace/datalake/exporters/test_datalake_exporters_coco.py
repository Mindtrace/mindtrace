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
    bbox = AnnotationRecord(
        annotation_id="ann_bbox",
        kind="bbox",
        label="object",
        source={"type": "human", "name": "annotator"},
        geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
    )
    image_asset = sample_asset()
    no_payload_dataset = ExportableDataset(
        name="dataset-a",
        items=[
            ExportableItem(
                asset=image_asset,
                annotations=[bbox],
                payload_bytes=None,
                source_filename="asset_img.png",
            )
        ],
    )
    non_image_asset = Asset(
        asset_id="asset_doc",
        kind="document",
        media_type="application/pdf",
        storage_ref=StorageRef(mount="assets", name="doc", version="1"),
    )
    non_image_dataset = ExportableDataset(
        name="dataset-a",
        items=[
            ExportableItem(
                asset=non_image_asset,
                annotations=[bbox],
                payload_bytes=b"pdf",
                source_filename="asset_doc.pdf",
            )
        ],
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


def test_coco_export_rejects_classification_dataset_with_hf_guidance(tmp_path: Path):
    annotation = AnnotationRecord(
        annotation_id="classification_1",
        kind="classification",
        label="pink primrose",
        label_id=0,
        source={"type": "human", "name": "flowers-102"},
    )
    dataset = ExportableDataset(
        name="flowers-102",
        metadata={"task_type": "classification"},
        items=[
            ExportableItem(
                asset=sample_asset(),
                annotations=[annotation],
                payload_bytes=png_bytes(),
            )
        ],
    )

    with pytest.raises(ValueError, match="format='huggingface'"):
        export_dataset_as_coco(dataset, destination=tmp_path / "flowers-coco")
    assert not (tmp_path / "flowers-coco").exists()


def test_coco_export_rejects_dataset_without_bbox_or_polygon_annotations(tmp_path: Path):
    annotation = AnnotationRecord(
        annotation_id="mask-1",
        kind="mask",
        label="foreground",
        source={"type": "human", "name": "annotator"},
        geometry={"type": "mask", "mask_asset_id": "asset_img"},
    )
    dataset = ExportableDataset(
        name="mask-only",
        items=[
            ExportableItem(
                asset=sample_asset(),
                payload_bytes=png_bytes(),
                annotations=[annotation],
            )
        ],
    )

    with pytest.raises(ValueError, match="bbox.*polygon"):
        export_dataset_as_coco(dataset, destination=tmp_path / "coco")


def test_coco_export_prepares_source_annotations_once_for_validation_categories_and_counts(tmp_path: Path):
    class _CountingList(list):
        def __init__(self, values):
            super().__init__(values)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    bbox = AnnotationRecord(
        annotation_id="bbox-1",
        kind="bbox",
        label="person",
        source={"type": "human", "name": "annotator"},
        geometry={"type": "bbox", "x": 0, "y": 0, "width": 1, "height": 1},
    )
    unsupported = AnnotationRecord(
        annotation_id="mask-1",
        kind="mask",
        label="person",
        source={"type": "human", "name": "annotator"},
        geometry={"type": "mask", "mask_asset_id": "asset_img"},
    )
    annotations = _CountingList([bbox, unsupported])
    item = ExportableItem.model_construct(
        asset=sample_asset(),
        split=None,
        metadata={},
        annotations=annotations,
        annotation_sets=[],
        payload_bytes=png_bytes(),
        source_filename="asset_img.png",
        related_assets={},
        related_payload_bytes={},
    )
    items = _CountingList([item])
    dataset = ExportableDataset.model_construct(name="single-pass", metadata={}, items=items, warnings=[])

    result = export_dataset_as_coco(dataset, destination=tmp_path / "coco", include_media=False)

    assert items.iterations == 1
    assert annotations.iterations == 1
    assert result.annotation_count == 1
    assert any("unsupported COCO annotation kind 'mask'" in warning for warning in result.warnings)
