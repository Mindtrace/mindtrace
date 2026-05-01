from __future__ import annotations

import json
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from .base import prepare_export_destination, write_export_file
from .types import ExportableDataset, ExportableItem, ExportResult


def _polygon_bbox(vertices: list[list[float]]) -> list[float]:
    xs = [float(v[0]) for v in vertices]
    ys = [float(v[1]) for v in vertices]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def _polygon_area(vertices: list[list[float]]) -> float:
    if len(vertices) < 3:
        return 0.0
    area = 0.0
    points = [(float(v[0]), float(v[1])) for v in vertices]
    for idx, (x1, y1) in enumerate(points):
        x2, y2 = points[(idx + 1) % len(points)]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) / 2.0


def _supported_category_records(dataset: ExportableDataset) -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for item in dataset.items:
        for annotation in item.annotations:
            if annotation.kind in {"bbox", "polygon"}:
                pairs.add((annotation.kind, annotation.label))
    return sorted(pairs, key=lambda pair: (pair[0], pair[1]))


def _image_info(item: ExportableItem, image_id: int, file_name: str) -> dict[str, Any]:
    if item.payload_bytes is None:
        raise ValueError(f"COCO export requires payload bytes for asset {item.asset.asset_id}")
    if not item.asset.media_type.startswith("image/"):
        raise ValueError(
            f"COCO export supports image assets only; asset {item.asset.asset_id} has media type {item.asset.media_type!r}."
        )
    with Image.open(BytesIO(item.payload_bytes)) as image:
        width, height = image.size
    return {
        "id": image_id,
        "file_name": file_name,
        "width": width,
        "height": height,
    }


def export_dataset_as_coco(
    dataset: ExportableDataset,
    *,
    destination: str | Path,
    include_media: bool = True,
    overwrite: bool = False,
    options: dict[str, Any] | None = None,
) -> ExportResult:
    """Export a canonical dataset view to a COCO-style directory."""
    del options
    destination_path = prepare_export_destination(destination, overwrite=overwrite)
    warnings = list(dataset.warnings)
    categories = _supported_category_records(dataset)
    category_ids = {pair: idx + 1 for idx, pair in enumerate(categories)}
    category_rows = [{"id": category_ids[pair], "name": pair[1], "supercategory": pair[0]} for pair in categories]

    split_bundles: dict[str, dict[str, Any]] = defaultdict(lambda: {"images": [], "annotations": []})
    files_written: list[str] = []
    next_annotation_id = 1
    for image_id, item in enumerate(dataset.items, start=1):
        split_name = item.split or "default"
        image_filename = item.source_filename or f"{item.asset.asset_id}.bin"
        image_relative_path = (
            Path("images") / split_name / image_filename if item.split is not None else Path("images") / image_filename
        )
        if include_media and item.payload_bytes is not None:
            files_written.append(write_export_file(destination_path, image_relative_path, item.payload_bytes))
        image_row = _image_info(item, image_id, image_relative_path.as_posix())
        split_bundles[split_name]["images"].append(image_row)

        for annotation in item.annotations:
            category_key = (annotation.kind, annotation.label)
            if annotation.kind == "bbox":
                geometry = annotation.geometry or {}
                bbox = [
                    float(geometry["x"]),
                    float(geometry["y"]),
                    float(geometry["width"]),
                    float(geometry["height"]),
                ]
                coco_annotation = {
                    "id": next_annotation_id,
                    "image_id": image_id,
                    "category_id": category_ids[category_key],
                    "bbox": bbox,
                    "area": float(bbox[2] * bbox[3]),
                    "iscrowd": 0,
                    "segmentation": [],
                }
            elif annotation.kind == "polygon":
                vertices = list(annotation.geometry.get("vertices") or annotation.geometry.get("points") or [])
                if len(vertices) < 3:
                    warnings.append(
                        f"Skipped polygon annotation {annotation.annotation_id} on asset {item.asset.asset_id} because it has fewer than 3 vertices."
                    )
                    continue
                flattened = [float(coord) for vertex in vertices for coord in vertex]
                coco_annotation = {
                    "id": next_annotation_id,
                    "image_id": image_id,
                    "category_id": category_ids[category_key],
                    "bbox": _polygon_bbox(vertices),
                    "area": _polygon_area(vertices),
                    "iscrowd": 0,
                    "segmentation": [flattened],
                }
            else:
                warnings.append(
                    f"Skipped unsupported COCO annotation kind {annotation.kind!r} for annotation {annotation.annotation_id}."
                )
                continue
            split_bundles[split_name]["annotations"].append(coco_annotation)
            next_annotation_id += 1

    multiple_splits = {item.split for item in dataset.items if item.split is not None}
    for split_name, payload in split_bundles.items():
        coco_payload = {
            "info": {"description": dataset.description or dataset.name},
            "licenses": [],
            "categories": category_rows,
            "images": payload["images"],
            "annotations": payload["annotations"],
        }
        if multiple_splits:
            relative_path = Path("annotations") / f"{split_name}.json"
        else:
            relative_path = Path("annotations.json")
        files_written.append(
            write_export_file(
                destination_path,
                relative_path,
                json.dumps(coco_payload, indent=2, sort_keys=True).encode("utf-8"),
            )
        )

    summary = {
        "format": "coco",
        "dataset_name": dataset.name,
        "asset_count": dataset.asset_count,
        "annotation_count": dataset.annotation_count,
        "warnings": warnings,
    }
    files_written.append(
        write_export_file(
            destination_path, "export_summary.json", json.dumps(summary, indent=2, sort_keys=True).encode("utf-8")
        )
    )
    return ExportResult(
        format="coco",
        destination=destination_path,
        dataset_name=dataset.name,
        asset_count=dataset.asset_count,
        annotation_count=dataset.annotation_count,
        files_written=files_written,
        warnings=warnings,
    )
