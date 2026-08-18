from __future__ import annotations

import json
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from ..types import AnnotationRecord
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


def _prepare_coco_items(
    dataset: ExportableDataset,
    warnings: list[str],
) -> tuple[list[tuple[ExportableItem, list[AnnotationRecord]]], list[tuple[str, str]], set[str]]:
    prepared: list[tuple[ExportableItem, list[AnnotationRecord]]] = []
    categories: set[tuple[str, str]] = set()
    named_splits: set[str] = set()
    for item in dataset.items:
        if item.split is not None:
            named_splits.add(item.split)
        supported_annotations: list[AnnotationRecord] = []
        for annotation in item.annotations:
            if annotation.kind in {"bbox", "polygon"}:
                supported_annotations.append(annotation)
                categories.add((annotation.kind, annotation.label))
            else:
                warnings.append(
                    f"Skipped unsupported COCO annotation kind {annotation.kind!r} "
                    f"for annotation {annotation.annotation_id}."
                )
        prepared.append((item, supported_annotations))
    return prepared, sorted(categories, key=lambda pair: (pair[0], pair[1])), named_splits


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
    destination_path = Path(destination)
    if destination_path.exists() and not overwrite:
        raise FileExistsError(f"Export destination already exists: {destination_path}")
    requested_task = (options or {}).get("task") or dataset.metadata.get("task_type")
    if requested_task == "classification":
        raise ValueError(
            "COCO export does not support image classification datasets. "
            "Export this dataset with format='huggingface' instead."
        )
    warnings = list(dataset.warnings)
    prepared_items, categories, named_splits = _prepare_coco_items(dataset, warnings)
    if not categories:
        raise ValueError("COCO export requires at least one supported bbox or polygon annotation.")
    destination_path = prepare_export_destination(destination_path, overwrite=overwrite)
    category_ids = {pair: idx + 1 for idx, pair in enumerate(categories)}
    category_rows = [{"id": category_ids[pair], "name": pair[1], "supercategory": pair[0]} for pair in categories]

    split_bundles: dict[str, dict[str, Any]] = defaultdict(lambda: {"images": [], "annotations": []})
    files_written: list[str] = []
    next_annotation_id = 1
    for image_id, (item, annotations) in enumerate(prepared_items, start=1):
        split_name = item.split or "default"
        image_filename = item.source_filename or f"{item.asset.asset_id}.bin"
        image_relative_path = (
            Path("images") / split_name / image_filename if item.split is not None else Path("images") / image_filename
        )
        if include_media and item.payload_bytes is not None:
            files_written.append(write_export_file(destination_path, image_relative_path, item.payload_bytes))
        image_row = _image_info(item, image_id, image_relative_path.as_posix())
        split_bundles[split_name]["images"].append(image_row)

        for annotation in annotations:
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
            split_bundles[split_name]["annotations"].append(coco_annotation)
            next_annotation_id += 1

    for split_name, payload in split_bundles.items():
        coco_payload = {
            "info": {"description": dataset.description or dataset.name},
            "licenses": [],
            "categories": category_rows,
            "images": payload["images"],
            "annotations": payload["annotations"],
        }
        if named_splits:
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

    exported_annotation_count = next_annotation_id - 1
    summary = {
        "format": "coco",
        "dataset_name": dataset.name,
        "asset_count": dataset.asset_count,
        "annotation_count": exported_annotation_count,
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
        annotation_count=exported_annotation_count,
        files_written=files_written,
        warnings=warnings,
    )
