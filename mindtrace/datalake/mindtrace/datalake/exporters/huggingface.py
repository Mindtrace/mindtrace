from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from .base import prepare_export_destination, write_export_file
from .types import ExportableDataset, ExportResult


def _configured_class_names(dataset: ExportableDataset, task: str) -> list[str] | None:
    configured = dataset.metadata.get(f"{task}_class_names") or dataset.metadata.get("class_names")
    if configured:
        return [str(name) for name in configured]
    return None


def _classification_class_names(dataset: ExportableDataset) -> list[str]:
    configured = _configured_class_names(dataset, "classification")
    if configured:
        return configured

    labels_by_id: dict[int, str] = {}
    for item in dataset.items:
        for annotation in item.annotations:
            if annotation.kind != "classification" or annotation.label_id is None:
                continue
            previous = labels_by_id.setdefault(annotation.label_id, annotation.label)
            if previous != annotation.label:
                raise ValueError(
                    f"Classification label id {annotation.label_id} maps to both {previous!r} and {annotation.label!r}."
                )
    if not labels_by_id:
        raise ValueError("Classification export requires annotation label IDs or dataset metadata class_names.")
    expected_ids = list(range(len(labels_by_id)))
    if sorted(labels_by_id) != expected_ids:
        raise ValueError(
            "Hugging Face classification export requires contiguous zero-based label IDs; "
            f"found {sorted(labels_by_id)}."
        )
    return [labels_by_id[label_id] for label_id in expected_ids]


def _detection_class_names(dataset: ExportableDataset) -> list[str]:
    configured = _configured_class_names(dataset, "detection")
    labels = {
        annotation.label for item in dataset.items for annotation in item.annotations if annotation.kind == "bbox"
    }
    if configured:
        unknown = sorted(labels - set(configured))
        if unknown:
            raise ValueError(f"Detection annotations use labels missing from detection_class_names: {unknown}.")
        return configured
    if not labels:
        raise ValueError("Detection export requires bbox annotations or dataset metadata detection_class_names.")
    return sorted(labels)


def _classification_annotation(item) -> Any:
    annotations = [annotation for annotation in item.annotations if annotation.kind == "classification"]
    if len(annotations) != 1:
        raise ValueError(
            "Single-label classification export requires exactly one classification annotation per image; "
            f"asset {item.asset.asset_id!r} has {len(annotations)}."
        )
    annotation = annotations[0]
    if annotation.label_id is None:
        raise ValueError(
            f"Classification annotation {annotation.annotation_id!r} must define a contiguous zero-based label_id."
        )
    return annotation


def _classification_features(datasets_module: Any, class_names: list[str]):
    return datasets_module.Features(
        {
            "image": datasets_module.Image(),
            "asset_id": datasets_module.Value("string"),
            "label": datasets_module.ClassLabel(names=class_names),
            "label_name": datasets_module.Value("string"),
            "split": datasets_module.Value("string"),
            "metadata_json": datasets_module.Value("string"),
            "asset_metadata_json": datasets_module.Value("string"),
        }
    )


def _detection_features(datasets_module: Any, class_names: list[str]):
    return datasets_module.Features(
        {
            "image": datasets_module.Image(),
            "asset_id": datasets_module.Value("string"),
            "split": datasets_module.Value("string"),
            "objects": datasets_module.Sequence(
                {
                    "id": datasets_module.Value("string"),
                    "area": datasets_module.Value("float32"),
                    "bbox": datasets_module.Sequence(datasets_module.Value("float32"), length=4),
                    "category": datasets_module.ClassLabel(names=class_names),
                    "category_name": datasets_module.Value("string"),
                    "difficult": datasets_module.Value("bool"),
                    "truncated": datasets_module.Value("bool"),
                    "occluded": datasets_module.Value("bool"),
                }
            ),
            "metadata_json": datasets_module.Value("string"),
            "asset_metadata_json": datasets_module.Value("string"),
        }
    )


def _embedded_image(item, *, include_media: bool, task: str):
    if not include_media:
        return None
    if item.payload_bytes is None:
        raise ValueError(f"Hugging Face {task} export requires payload bytes for asset {item.asset.asset_id}.")
    return {
        "bytes": item.payload_bytes,
        "path": item.source_filename or f"{item.asset.asset_id}.bin",
    }


def _export_classification_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
) -> ExportResult:
    class_names = _classification_class_names(dataset)
    features = _classification_features(datasets_module, class_names)
    rows_by_split: dict[str, list[dict[str, Any]]] = {}

    for item in dataset.items:
        annotation = _classification_annotation(item)
        if not 0 <= annotation.label_id < len(class_names):
            raise ValueError(
                f"Classification label id {annotation.label_id} is outside the exported class range "
                f"0..{len(class_names) - 1}."
            )
        expected_label = class_names[annotation.label_id]
        if annotation.label != expected_label:
            raise ValueError(
                f"Classification label id {annotation.label_id} maps to {expected_label!r}, "
                f"but annotation {annotation.annotation_id!r} uses {annotation.label!r}."
            )
        split_name = item.split or "default"
        image = _embedded_image(item, include_media=include_media, task="classification")
        rows_by_split.setdefault(split_name, []).append(
            {
                "image": image,
                "asset_id": item.asset.asset_id,
                "label": annotation.label_id,
                "label_name": annotation.label,
                "split": item.split or "",
                "metadata_json": json.dumps(item.metadata or {}, sort_keys=True, default=str),
                "asset_metadata_json": json.dumps(item.asset.metadata or {}, sort_keys=True, default=str),
            }
        )

    dataset_payload = {
        split: datasets_module.Dataset.from_list(rows, features=features) for split, rows in rows_by_split.items()
    }
    if len(dataset_payload) == 1 and "default" in dataset_payload:
        hf_dataset = dataset_payload["default"]
    else:
        hf_dataset = datasets_module.DatasetDict(dataset_payload)
    hf_dataset.save_to_disk(str(destination))
    return ExportResult(
        format="huggingface",
        destination=destination,
        dataset_name=dataset.name,
        asset_count=dataset.asset_count,
        annotation_count=dataset.annotation_count,
        files_written=["."],
        warnings=list(dataset.warnings),
    )


def _export_detection_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
) -> ExportResult:
    class_names = _detection_class_names(dataset)
    class_ids = {name: index for index, name in enumerate(class_names)}
    features = _detection_features(datasets_module, class_names)
    rows_by_split: dict[str, list[dict[str, Any]]] = {}

    for item in dataset.items:
        objects: dict[str, list[Any]] = {
            "id": [],
            "area": [],
            "bbox": [],
            "category": [],
            "category_name": [],
            "difficult": [],
            "truncated": [],
            "occluded": [],
        }
        for annotation in item.annotations:
            if annotation.kind != "bbox":
                continue
            geometry = annotation.geometry
            if geometry.get("type") != "bbox":
                raise ValueError(f"Detection annotation {annotation.annotation_id!r} must use geometry type 'bbox'.")
            bbox = [float(geometry.get(key, 0)) for key in ("x", "y", "width", "height")]
            if bbox[2] <= 0 or bbox[3] <= 0:
                raise ValueError(
                    f"Detection annotation {annotation.annotation_id!r} must have positive width and height."
                )
            attributes = annotation.attributes or {}
            objects["id"].append(annotation.annotation_id)
            objects["area"].append(bbox[2] * bbox[3])
            objects["bbox"].append(bbox)
            objects["category"].append(class_ids[annotation.label])
            objects["category_name"].append(annotation.label)
            objects["difficult"].append(bool(attributes.get("difficult", False)))
            objects["truncated"].append(bool(attributes.get("truncated", False)))
            objects["occluded"].append(bool(attributes.get("occluded", False)))

        split_name = item.split or "default"
        rows_by_split.setdefault(split_name, []).append(
            {
                "image": _embedded_image(item, include_media=include_media, task="detection"),
                "asset_id": item.asset.asset_id,
                "split": item.split or "",
                "objects": objects,
                "metadata_json": json.dumps(item.metadata or {}, sort_keys=True, default=str),
                "asset_metadata_json": json.dumps(item.asset.metadata or {}, sort_keys=True, default=str),
            }
        )

    dataset_payload = {
        split: datasets_module.Dataset.from_list(rows, features=features) for split, rows in rows_by_split.items()
    }
    if len(dataset_payload) == 1 and "default" in dataset_payload:
        hf_dataset = dataset_payload["default"]
    else:
        hf_dataset = datasets_module.DatasetDict(dataset_payload)
    hf_dataset.save_to_disk(str(destination))
    return ExportResult(
        format="huggingface",
        destination=destination,
        dataset_name=dataset.name,
        asset_count=dataset.asset_count,
        annotation_count=sum(annotation.kind == "bbox" for item in dataset.items for annotation in item.annotations),
        files_written=["."],
        warnings=list(dataset.warnings),
    )


def export_dataset_as_huggingface(
    dataset: ExportableDataset,
    *,
    destination: str | Path,
    include_media: bool = True,
    overwrite: bool = False,
    options: dict[str, Any] | None = None,
) -> ExportResult:
    """Export a canonical dataset view to a Hugging Face datasets directory."""
    try:
        datasets_module = importlib.import_module("datasets")
    except ImportError as exc:
        raise ImportError(
            "Hugging Face export requires the optional 'datasets' dependency. "
            "Install mindtrace-datalake[export-huggingface]."
        ) from exc

    destination_path = prepare_export_destination(destination, overwrite=overwrite)
    requested_task = (options or {}).get("task") or dataset.metadata.get("task_type")
    if requested_task == "classification":
        return _export_classification_dataset(
            datasets_module,
            dataset,
            destination=destination_path,
            include_media=include_media,
        )
    if requested_task in {"detection", "object_detection"}:
        return _export_detection_dataset(
            datasets_module,
            dataset,
            destination=destination_path,
            include_media=include_media,
        )

    warnings = list(dataset.warnings)
    files_written: list[str] = []
    rows_by_split: dict[str, list[dict[str, Any]]] = {}

    for item in dataset.items:
        split_name = item.split or "default"
        media_relative_path: str | None = None
        if include_media and item.payload_bytes is not None:
            media_path = Path("media") / split_name / (item.source_filename or f"{item.asset.asset_id}.bin")
            media_relative_path = write_export_file(destination_path, media_path, item.payload_bytes)
            files_written.append(media_relative_path)
        rows_by_split.setdefault(split_name, []).append(
            {
                "asset_id": item.asset.asset_id,
                "split": item.split,
                "media_type": item.asset.media_type,
                "image_path": media_relative_path,
                "storage_ref": item.asset.storage_ref.model_dump(mode="json"),
                "metadata": dict(item.metadata or {}),
                "asset_metadata": dict(item.asset.metadata or {}),
                "annotations": [annotation.model_dump(mode="json") for annotation in item.annotations],
            }
        )

    dataset_payload = {split: datasets_module.Dataset.from_list(rows) for split, rows in rows_by_split.items()}
    if len(dataset_payload) == 1 and "default" in dataset_payload:
        hf_dataset = dataset_payload["default"]
    else:
        hf_dataset = datasets_module.DatasetDict(dataset_payload)
    hf_dataset.save_to_disk(str(destination_path))

    files_written.append(".")
    return ExportResult(
        format="huggingface",
        destination=destination_path,
        dataset_name=dataset.name,
        asset_count=dataset.asset_count,
        annotation_count=dataset.annotation_count,
        files_written=files_written,
        warnings=warnings,
    )
