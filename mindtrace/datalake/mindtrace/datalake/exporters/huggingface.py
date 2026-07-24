from __future__ import annotations

import importlib
import io
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


def _single_label_classification_features(datasets_module: Any, class_names: list[str]):
    return datasets_module.Features(
        {
            "image": datasets_module.Image(),
            "asset_id": datasets_module.Value("string"),
            "label": datasets_module.ClassLabel(names=class_names),
            "label_name": datasets_module.Value("string"),
            "split": datasets_module.Value("string"),
            "source_image_asset_id": datasets_module.Value("string"),
            "source_annotation_id": datasets_module.Value("string"),
            "source_bbox": datasets_module.Sequence(datasets_module.Value("float32"), length=4),
            "metadata_json": datasets_module.Value("string"),
            "asset_metadata_json": datasets_module.Value("string"),
        }
    )


def _multi_label_classification_features(datasets_module: Any, class_names: list[str]):
    return datasets_module.Features(
        {
            "image": datasets_module.Image(),
            "asset_id": datasets_module.Value("string"),
            "labels": datasets_module.Sequence(datasets_module.Value("float32"), length=len(class_names)),
            "label_ids": datasets_module.Sequence(datasets_module.ClassLabel(names=class_names)),
            "label_names": datasets_module.Sequence(datasets_module.Value("string")),
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


def _semantic_segmentation_features(datasets_module: Any):
    return datasets_module.Features(
        {
            "image": datasets_module.Image(),
            "mask": datasets_module.Image(),
            "asset_id": datasets_module.Value("string"),
            "split": datasets_module.Value("string"),
            "class_names": datasets_module.Sequence(datasets_module.Value("string")),
            "background_id": datasets_module.Value("int32"),
            "ignore_index": datasets_module.Value("int32"),
            "metadata_json": datasets_module.Value("string"),
            "asset_metadata_json": datasets_module.Value("string"),
        }
    )


def _instance_segmentation_features(datasets_module: Any, class_names: list[str]):
    return datasets_module.Features(
        {
            "image": datasets_module.Image(),
            "asset_id": datasets_module.Value("string"),
            "split": datasets_module.Value("string"),
            "objects": datasets_module.Sequence(
                {
                    "id": datasets_module.Value("string"),
                    "mask": datasets_module.Image(),
                    "bbox": datasets_module.Sequence(datasets_module.Value("float32"), length=4),
                    "category": datasets_module.ClassLabel(names=class_names),
                    "category_name": datasets_module.Value("string"),
                    "area": datasets_module.Value("float32"),
                    "iscrowd": datasets_module.Value("bool"),
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


def _embedded_related_image(item, role: str, *, include_media: bool, task: str):
    if role not in item.related_assets:
        raise ValueError(f"Hugging Face {task} export requires related asset role {role!r}.")
    if not include_media:
        return None
    payload_bytes = item.related_payload_bytes.get(role)
    if payload_bytes is None:
        raise ValueError(
            f"Hugging Face {task} export requires payload bytes for related asset role {role!r} "
            f"on asset {item.asset.asset_id}."
        )
    asset = item.related_assets[role]
    return {"bytes": payload_bytes, "path": f"{asset.asset_id}.png"}


def _export_single_label_classification_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
) -> ExportResult:
    class_names = _classification_class_names(dataset)
    features = _single_label_classification_features(datasets_module, class_names)
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
                "source_image_asset_id": item.asset.asset_id,
                "source_annotation_id": annotation.annotation_id,
                "source_bbox": None,
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
        annotation_count=dataset.asset_count,
        files_written=["."],
        warnings=list(dataset.warnings),
    )


def _export_multi_label_classification_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
) -> ExportResult:
    class_names = _classification_class_names(dataset)
    class_ids = {name: index for index, name in enumerate(class_names)}
    features = _multi_label_classification_features(datasets_module, class_names)
    rows_by_split: dict[str, list[dict[str, Any]]] = {}
    annotation_count = 0

    for item in dataset.items:
        annotations = [annotation for annotation in item.annotations if annotation.kind == "classification"]
        unknown = sorted({annotation.label for annotation in annotations} - set(class_ids))
        if unknown:
            raise ValueError(f"Multi-label classification annotations use unknown labels: {unknown}.")
        positive_ids = sorted({class_ids[annotation.label] for annotation in annotations})
        labels = [0.0] * len(class_names)
        for label_id in positive_ids:
            labels[label_id] = 1.0
        annotation_count += len(annotations)
        split_name = item.split or "default"
        rows_by_split.setdefault(split_name, []).append(
            {
                "image": _embedded_image(item, include_media=include_media, task="classification"),
                "asset_id": item.asset.asset_id,
                "labels": labels,
                "label_ids": positive_ids,
                "label_names": [class_names[label_id] for label_id in positive_ids],
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
        annotation_count=annotation_count,
        files_written=["."],
        warnings=list(dataset.warnings),
    )


def _crop_image_for_classification(item, annotation) -> dict[str, Any]:
    if item.payload_bytes is None:
        raise ValueError(
            f"Hugging Face bbox-crop classification export requires payload bytes for asset {item.asset.asset_id}."
        )
    geometry = annotation.geometry
    if geometry.get("type") != "bbox":
        raise ValueError(f"Classification crop annotation {annotation.annotation_id!r} must use bbox geometry.")
    x, y, width, height = (float(geometry.get(key, 0)) for key in ("x", "y", "width", "height"))
    if width <= 0 or height <= 0:
        raise ValueError(f"Classification crop annotation {annotation.annotation_id!r} has an empty bbox.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Bounding-box classification crops require Pillow.") from exc
    with Image.open(io.BytesIO(item.payload_bytes)) as image:
        left = max(0, int(x))
        top = max(0, int(y))
        right = min(image.width, int(x + width))
        bottom = min(image.height, int(y + height))
        if right <= left or bottom <= top:
            raise ValueError(
                f"Classification crop annotation {annotation.annotation_id!r} lies outside its source image."
            )
        crop = image.convert("RGB").crop((left, top, right, bottom))
        payload = io.BytesIO()
        crop.save(payload, format="JPEG")
    return {
        "bytes": payload.getvalue(),
        "path": f"{item.asset.asset_id}-{annotation.annotation_id}.jpg",
    }


def _export_bbox_crop_classification_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
) -> ExportResult:
    class_names = _detection_class_names(dataset)
    class_ids = {name: index for index, name in enumerate(class_names)}
    features = _single_label_classification_features(datasets_module, class_names)
    rows_by_split: dict[str, list[dict[str, Any]]] = {}
    crop_count = 0

    for item in dataset.items:
        for annotation in item.annotations:
            if annotation.kind != "bbox":
                continue
            split_name = item.split or "default"
            rows_by_split.setdefault(split_name, []).append(
                {
                    "image": _crop_image_for_classification(item, annotation) if include_media else None,
                    "asset_id": f"{item.asset.asset_id}:{annotation.annotation_id}",
                    "label": class_ids[annotation.label],
                    "label_name": annotation.label,
                    "split": item.split or "",
                    "source_image_asset_id": item.asset.asset_id,
                    "source_annotation_id": annotation.annotation_id,
                    "source_bbox": [float(annotation.geometry.get(key, 0)) for key in ("x", "y", "width", "height")],
                    "metadata_json": json.dumps(item.metadata or {}, sort_keys=True, default=str),
                    "asset_metadata_json": json.dumps(item.asset.metadata or {}, sort_keys=True, default=str),
                }
            )
            crop_count += 1

    if not crop_count:
        raise ValueError("Bounding-box classification crop export requires at least one bbox annotation.")
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
        asset_count=crop_count,
        annotation_count=crop_count,
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


def _export_semantic_segmentation_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
) -> ExportResult:
    class_names = _configured_class_names(dataset, "semantic_segmentation")
    if not class_names:
        raise ValueError("Semantic segmentation export requires dataset metadata semantic_segmentation_class_names.")
    background_id = int(dataset.metadata.get("semantic_segmentation_background_id", 0))
    ignore_index = int(dataset.metadata.get("semantic_segmentation_ignore_index", 255))
    features = _semantic_segmentation_features(datasets_module)
    rows_by_split: dict[str, list[dict[str, Any]]] = {}

    for item in dataset.items:
        mask_annotations = [annotation for annotation in item.annotations if annotation.kind == "mask"]
        if len(mask_annotations) != 1:
            raise ValueError(
                "Semantic segmentation export requires exactly one categorical mask annotation per image; "
                f"asset {item.asset.asset_id!r} has {len(mask_annotations)}."
            )
        mask_asset_id = mask_annotations[0].geometry.get("mask_asset_id")
        semantic_mask_asset = item.related_assets.get("semantic_mask")
        if semantic_mask_asset is None or semantic_mask_asset.asset_id != mask_asset_id:
            raise ValueError(
                f"Semantic mask annotation for asset {item.asset.asset_id!r} does not match "
                "related asset role 'semantic_mask'."
            )
        split_name = item.split or "default"
        rows_by_split.setdefault(split_name, []).append(
            {
                "image": _embedded_image(item, include_media=include_media, task="semantic segmentation"),
                "mask": _embedded_related_image(
                    item,
                    "semantic_mask",
                    include_media=include_media,
                    task="semantic segmentation",
                ),
                "asset_id": item.asset.asset_id,
                "split": item.split or "",
                "class_names": class_names,
                "background_id": background_id,
                "ignore_index": ignore_index,
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
        annotation_count=dataset.asset_count,
        files_written=["."],
        warnings=list(dataset.warnings),
    )


def _binary_instance_mask(item, annotation, *, include_media: bool) -> tuple[dict[str, Any] | None, list[float], float]:
    mask_asset = item.related_assets.get("instance_mask")
    mask_asset_id = annotation.geometry.get("mask_asset_id")
    if mask_asset is None or mask_asset.asset_id != mask_asset_id:
        raise ValueError(
            f"Instance mask annotation {annotation.annotation_id!r} does not match related asset role 'instance_mask'."
        )
    instance_id = annotation.geometry.get("instance_id")
    if instance_id is None:
        raise ValueError(f"Instance mask annotation {annotation.annotation_id!r} does not define instance_id.")
    payload = item.related_payload_bytes.get("instance_mask")
    if payload is None:
        raise ValueError(f"Instance segmentation export requires mask payload bytes for asset {item.asset.asset_id!r}.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Instance segmentation export requires Pillow.") from exc

    with Image.open(io.BytesIO(payload)) as indexed_mask:
        if indexed_mask.mode not in {"L", "P", "I"}:
            raise ValueError(
                f"Instance mask for asset {item.asset.asset_id!r} must be indexed and single-channel; "
                f"received mode {indexed_mask.mode!r}."
            )
        width, _ = indexed_mask.size
        binary_values: list[int] = []
        xs: list[int] = []
        ys: list[int] = []
        expected_id = int(instance_id)
        for offset, raw_value in enumerate(indexed_mask.getdata()):
            selected = int(raw_value) == expected_id
            binary_values.append(255 if selected else 0)
            if selected:
                xs.append(offset % width)
                ys.append(offset // width)
        if not xs:
            raise ValueError(
                f"Instance id {instance_id!r} for annotation {annotation.annotation_id!r} is absent from its mask."
            )
        bbox = [
            float(min(xs)),
            float(min(ys)),
            float(max(xs) - min(xs) + 1),
            float(max(ys) - min(ys) + 1),
        ]
        area = float(len(xs))
        embedded_mask = None
        if include_media:
            binary_mask = Image.new("L", indexed_mask.size)
            binary_mask.putdata(binary_values)
            output = io.BytesIO()
            binary_mask.save(output, format="PNG")
            embedded_mask = {
                "bytes": output.getvalue(),
                "path": f"{item.asset.asset_id}-{annotation.annotation_id}.png",
            }
    return embedded_mask, bbox, area


def _export_instance_segmentation_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
) -> ExportResult:
    class_names = _configured_class_names(dataset, "instance_segmentation")
    if not class_names:
        raise ValueError("Instance segmentation export requires dataset metadata instance_segmentation_class_names.")
    class_ids = {name: index for index, name in enumerate(class_names)}
    features = _instance_segmentation_features(datasets_module, class_names)
    rows_by_split: dict[str, list[dict[str, Any]]] = {}
    annotation_count = 0

    for item in dataset.items:
        annotations = [annotation for annotation in item.annotations if annotation.kind == "instance_mask"]
        if not annotations:
            raise ValueError(
                "Instance segmentation export requires at least one instance mask annotation per image; "
                f"asset {item.asset.asset_id!r} has none."
            )
        objects: dict[str, list[Any]] = {
            "id": [],
            "mask": [],
            "bbox": [],
            "category": [],
            "category_name": [],
            "area": [],
            "iscrowd": [],
        }
        for annotation in annotations:
            if annotation.label not in class_ids:
                raise ValueError(
                    f"Instance mask annotation {annotation.annotation_id!r} uses unknown label {annotation.label!r}."
                )
            mask, bbox, area = _binary_instance_mask(item, annotation, include_media=include_media)
            objects["id"].append(annotation.annotation_id)
            objects["mask"].append(mask)
            objects["bbox"].append(bbox)
            objects["category"].append(class_ids[annotation.label])
            objects["category_name"].append(annotation.label)
            objects["area"].append(area)
            objects["iscrowd"].append(bool((annotation.attributes or {}).get("iscrowd", False)))
        split_name = item.split or "default"
        rows_by_split.setdefault(split_name, []).append(
            {
                "image": _embedded_image(item, include_media=include_media, task="instance segmentation"),
                "asset_id": item.asset.asset_id,
                "split": item.split or "",
                "objects": objects,
                "metadata_json": json.dumps(item.metadata or {}, sort_keys=True, default=str),
                "asset_metadata_json": json.dumps(item.asset.metadata or {}, sort_keys=True, default=str),
            }
        )
        annotation_count += len(annotations)

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
        annotation_count=annotation_count,
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
        classification_type = (options or {}).get("classification_type") or dataset.metadata.get(
            "classification_type", "single_label"
        )
        classification_source = (options or {}).get("classification_source") or dataset.metadata.get(
            "classification_source", "annotations"
        )
        if classification_source not in {"annotations", "bbox_crops"}:
            raise ValueError(
                "Hugging Face classification export requires classification_source='annotations' or 'bbox_crops'."
            )
        if classification_type == "single_label" and classification_source == "bbox_crops":
            return _export_bbox_crop_classification_dataset(
                datasets_module,
                dataset,
                destination=destination_path,
                include_media=include_media,
            )
        if classification_type == "single_label":
            return _export_single_label_classification_dataset(
                datasets_module,
                dataset,
                destination=destination_path,
                include_media=include_media,
            )
        if classification_type == "multi_label":
            if classification_source != "annotations":
                raise ValueError("Multi-label classification export only supports classification_source='annotations'.")
            return _export_multi_label_classification_dataset(
                datasets_module,
                dataset,
                destination=destination_path,
                include_media=include_media,
            )
        raise ValueError(
            "Hugging Face classification export requires classification_type='single_label' or 'multi_label'."
        )
    if requested_task in {"detection", "object_detection"}:
        return _export_detection_dataset(
            datasets_module,
            dataset,
            destination=destination_path,
            include_media=include_media,
        )
    if requested_task == "segmentation":
        requested_task = dataset.metadata.get("task_type")
        if requested_task not in {"semantic_segmentation", "instance_segmentation"}:
            raise ValueError(
                "Hugging Face task='segmentation' requires dataset metadata task_type='semantic_segmentation' "
                "or task_type='instance_segmentation'."
            )
    if requested_task in {"semantic_segmentation", "semantic-segmentation"}:
        return _export_semantic_segmentation_dataset(
            datasets_module,
            dataset,
            destination=destination_path,
            include_media=include_media,
        )
    if requested_task in {"instance_segmentation", "instance-segmentation"}:
        return _export_instance_segmentation_dataset(
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
