from __future__ import annotations

import importlib
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .base import prepare_export_destination, write_export_file
from .types import ExportableDataset, ExportResult

_INTEGER_DTYPES = {"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"}
_FLOAT_DTYPES = {"float16", "float32", "float64"}
_METADATA_DTYPES = {"string", "bool", *_INTEGER_DTYPES, *_FLOAT_DTYPES}


def _configured_class_names(
    dataset: ExportableDataset,
    task: str,
    options: Mapping[str, Any] | None = None,
) -> list[str] | None:
    configured = None
    if options is not None:
        configured = options.get(f"{task}_class_names") or options.get("class_names")
    configured = configured or dataset.metadata.get(f"{task}_class_names") or dataset.metadata.get("class_names")
    if configured is None:
        return None
    if isinstance(configured, (str, bytes)) or not isinstance(configured, Sequence):
        raise ValueError("Classification class_names must be an ordered sequence of label names.")
    class_names = [str(name) for name in configured]
    if not class_names:
        raise ValueError("Classification class_names cannot be empty.")
    if len(set(class_names)) != len(class_names):
        raise ValueError("Classification class_names must not contain duplicate label names.")
    return class_names


def _annotation_attributes(options: Mapping[str, Any] | None) -> dict[str, Any]:
    configured = (options or {}).get("annotation_attributes")
    if configured is None:
        return {}
    if not isinstance(configured, Mapping) or any(not isinstance(key, str) or not key for key in configured):
        raise ValueError("annotation_attributes must be a mapping with non-empty string keys.")
    return dict(configured)


def _metadata_keys(options: Mapping[str, Any] | None) -> dict[str, str]:
    configured = (options or {}).get("metadata_keys")
    if configured is None:
        return {}
    if not isinstance(configured, Mapping):
        raise ValueError("metadata_keys must map top-level row metadata keys to Hugging Face scalar dtypes.")
    metadata_keys: dict[str, str] = {}
    for key, dtype in configured.items():
        if not isinstance(key, str) or not key:
            raise ValueError("metadata_keys must contain non-empty string keys.")
        if not isinstance(dtype, str) or dtype not in _METADATA_DTYPES:
            raise ValueError(
                f"metadata_keys[{key!r}] must use a supported scalar dtype; found {dtype!r}. "
                f"Supported dtypes: {sorted(_METADATA_DTYPES)}."
            )
        metadata_keys[key] = dtype
    return metadata_keys


def _annotation_matches_attributes(annotation: Any, attributes: Mapping[str, Any]) -> bool:
    return annotation.kind == "classification" and all(
        (annotation.attributes or {}).get(key) == value for key, value in attributes.items()
    )


def _metadata_value_matches_dtype(value: Any, dtype: str) -> bool:
    if dtype == "string":
        return isinstance(value, str)
    if dtype == "bool":
        return isinstance(value, bool)
    if dtype in _INTEGER_DTYPES:
        return isinstance(value, int) and not isinstance(value, bool)
    if dtype in _FLOAT_DTYPES:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _project_metadata_keys(item: Any, metadata_keys: Mapping[str, str]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for key, dtype in metadata_keys.items():
        if key not in item.metadata or item.metadata[key] is None:
            raise ValueError(
                f"Hugging Face export requires row metadata key {key!r}; asset {item.asset.asset_id!r} is missing it."
            )
        value = item.metadata[key]
        if not _metadata_value_matches_dtype(value, dtype):
            raise ValueError(
                f"Hugging Face export metadata key {key!r} on asset {item.asset.asset_id!r} "
                f"must match dtype {dtype!r}; found {type(value).__name__}."
            )
        projected[key] = value
    return projected


def _classification_class_names(
    dataset: ExportableDataset,
    *,
    options: Mapping[str, Any] | None = None,
    annotation_attributes: Mapping[str, Any] | None = None,
) -> list[str]:
    configured = _configured_class_names(dataset, "classification", options)
    if configured:
        return configured

    selected_attributes = annotation_attributes or {}
    labels_by_id: dict[int, str] = {}
    for item in dataset.items:
        for annotation in item.annotations:
            if not _annotation_matches_attributes(annotation, selected_attributes) or annotation.label_id is None:
                continue
            previous = labels_by_id.setdefault(annotation.label_id, annotation.label)
            if previous != annotation.label:
                raise ValueError(
                    f"Classification label id {annotation.label_id} maps to both {previous!r} and {annotation.label!r}."
                )
    if not labels_by_id:
        raise ValueError("Classification export requires annotation label IDs or explicit exporter option class_names.")
    expected_ids = list(range(len(labels_by_id)))
    if sorted(labels_by_id) != expected_ids:
        raise ValueError(
            "Hugging Face classification export requires contiguous zero-based label IDs; "
            f"found {sorted(labels_by_id)}."
        )
    return [labels_by_id[label_id] for label_id in expected_ids]


def _detection_class_names(dataset: ExportableDataset) -> list[str]:
    configured = _configured_class_names(dataset, "detection")
    if configured:
        return configured
    labels = {
        annotation.label for item in dataset.items for annotation in item.annotations if annotation.kind == "bbox"
    }
    if not labels:
        raise ValueError("Detection export requires bbox annotations or dataset metadata detection_class_names.")
    return sorted(labels)


def _classification_annotation(item: Any, annotation_attributes: Mapping[str, Any] | None = None) -> Any:
    selected_attributes = annotation_attributes or {}
    annotations = [
        annotation for annotation in item.annotations if _annotation_matches_attributes(annotation, selected_attributes)
    ]
    if len(annotations) != 1:
        selector = f" matching attributes {dict(selected_attributes)!r}" if selected_attributes else ""
        raise ValueError(
            f"Single-label classification export requires exactly one classification annotation{selector} per image; "
            f"asset {item.asset.asset_id!r} has {len(annotations)}."
        )
    return annotations[0]


def _single_label_classification_features(
    datasets_module: Any,
    class_names: list[str],
    metadata_keys: Mapping[str, str] | None = None,
):
    fields = {
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
    collisions = sorted(set(metadata_keys or {}) & set(fields))
    if collisions:
        raise ValueError(f"metadata_keys collide with reserved Hugging Face fields: {collisions}.")
    fields.update({key: datasets_module.Value(dtype) for key, dtype in (metadata_keys or {}).items()})
    return datasets_module.Features(fields)


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


def _embedded_role_image(item, role: str, *, include_media: bool, task: str):
    if role not in item.assets:
        raise ValueError(f"Hugging Face {task} export requires asset role {role!r}.")
    if not include_media:
        return None
    payload_bytes = item.payloads.get(role)
    if payload_bytes is None:
        raise ValueError(
            f"Hugging Face {task} export requires payload bytes for asset role {role!r} on asset {item.asset.asset_id}."
        )
    asset = item.assets[role]
    return {"bytes": payload_bytes, "path": f"{asset.asset_id}.png"}


def _save_huggingface_rows(
    datasets_module: Any,
    dataset: ExportableDataset,
    rows_by_split: dict[str, list[dict[str, Any]]],
    *,
    destination: Path,
    features: Any | None = None,
    asset_count: int,
    annotation_count: int,
    files_written: list[str] | None = None,
    artifact_metadata: dict[str, Any] | None = None,
) -> ExportResult:
    """Build, save, and summarize a split-aware Hugging Face artifact."""
    dataset_payload = {
        split: datasets_module.Dataset.from_generator(lambda rows=rows: iter(rows), features=features)
        for split, rows in rows_by_split.items()
    }
    if len(dataset_payload) == 1 and "default" in dataset_payload:
        hf_dataset = dataset_payload["default"]
    else:
        hf_dataset = datasets_module.DatasetDict(dataset_payload)
    hf_dataset.save_to_disk(str(destination))
    written = list(files_written or [])
    if artifact_metadata is not None:
        written.append(
            write_export_file(
                destination,
                "mindtrace_metadata.json",
                json.dumps({"schema_version": 1, "mindtrace": artifact_metadata}, sort_keys=True).encode("utf-8"),
            )
        )
    return ExportResult(
        format="huggingface",
        destination=destination,
        dataset_name=dataset.name,
        asset_count=asset_count,
        annotation_count=annotation_count,
        files_written=[*written, "."],
        warnings=list(dataset.warnings),
    )


def _export_single_label_classification_dataset(
    datasets_module: Any,
    dataset: ExportableDataset,
    *,
    destination: Path,
    include_media: bool,
    options: Mapping[str, Any] | None = None,
) -> ExportResult:
    selected_attributes = _annotation_attributes(options)
    selected_metadata_keys = _metadata_keys(options)
    class_names = _classification_class_names(
        dataset,
        options=options,
        annotation_attributes=selected_attributes,
    )
    class_ids = {name: label_id for label_id, name in enumerate(class_names)}
    features = _single_label_classification_features(datasets_module, class_names, selected_metadata_keys)
    rows_by_split: dict[str, list[dict[str, Any]]] = {}

    for item in dataset.items:
        annotation = _classification_annotation(item, selected_attributes)
        if annotation.label not in class_ids:
            raise ValueError(
                f"Classification annotation {annotation.annotation_id!r} on asset {item.asset.asset_id!r} "
                f"uses label {annotation.label!r}, which is not present in class_names."
            )
        label_id = class_ids[annotation.label]
        if annotation.label_id is not None and annotation.label_id != label_id:
            raise ValueError(
                f"Classification annotation {annotation.annotation_id!r} maps label {annotation.label!r} "
                f"to configured id {label_id}, but the annotation uses label_id {annotation.label_id}."
            )
        split_name = item.split or "default"
        image = _embedded_image(item, include_media=include_media, task="classification")
        row = {
            "image": image,
            "asset_id": item.asset.asset_id,
            "label": label_id,
            "label_name": annotation.label,
            "split": item.split or "",
            "source_image_asset_id": item.asset.asset_id,
            "source_annotation_id": annotation.annotation_id,
            "source_bbox": None,
            "metadata_json": json.dumps(item.metadata or {}, sort_keys=True, default=str),
            "asset_metadata_json": json.dumps(item.asset.metadata or {}, sort_keys=True, default=str),
        }
        row.update(_project_metadata_keys(item, selected_metadata_keys))
        rows_by_split.setdefault(split_name, []).append(row)

    requested_provenance = bool(
        selected_attributes
        or selected_metadata_keys
        or (options or {}).get("class_names")
        or (options or {}).get("classification_class_names")
    )
    artifact_metadata = None
    if requested_provenance:
        artifact_metadata = {
            "task": "classification",
            "annotation_attributes": selected_attributes,
            "class_names": class_names,
            "label_to_id": class_ids,
            "metadata_keys": selected_metadata_keys,
        }

    return _save_huggingface_rows(
        datasets_module,
        dataset,
        rows_by_split,
        destination=destination,
        features=features,
        asset_count=dataset.asset_count,
        annotation_count=dataset.asset_count,
        artifact_metadata=artifact_metadata,
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

    return _save_huggingface_rows(
        datasets_module,
        dataset,
        rows_by_split,
        destination=destination,
        features=features,
        asset_count=dataset.asset_count,
        annotation_count=annotation_count,
    )


def _decode_classification_crop_image(item):
    if item.payload_bytes is None:
        raise ValueError(
            f"Hugging Face bbox-crop classification export requires payload bytes for asset {item.asset.asset_id}."
        )
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Bounding-box classification crops require Pillow.") from exc
    with Image.open(io.BytesIO(item.payload_bytes)) as image:
        return image.convert("RGB")


def _crop_image_for_classification(image, item, annotation) -> dict[str, Any]:
    geometry = annotation.geometry
    if geometry.get("type") != "bbox":
        raise ValueError(f"Classification crop annotation {annotation.annotation_id!r} must use bbox geometry.")
    x, y, width, height = (float(geometry.get(key, 0)) for key in ("x", "y", "width", "height"))
    if width <= 0 or height <= 0:
        raise ValueError(f"Classification crop annotation {annotation.annotation_id!r} has an empty bbox.")
    left = max(0, int(x))
    top = max(0, int(y))
    right = min(image.width, int(x + width))
    bottom = min(image.height, int(y + height))
    if right <= left or bottom <= top:
        raise ValueError(f"Classification crop annotation {annotation.annotation_id!r} lies outside its source image.")
    payload = io.BytesIO()
    with image.crop((left, top, right, bottom)) as crop:
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
        annotations = [annotation for annotation in item.annotations if annotation.kind == "bbox"]
        source_image = _decode_classification_crop_image(item) if include_media and annotations else None
        try:
            for annotation in annotations:
                split_name = item.split or "default"
                rows_by_split.setdefault(split_name, []).append(
                    {
                        "image": (
                            _crop_image_for_classification(source_image, item, annotation) if source_image else None
                        ),
                        "asset_id": f"{item.asset.asset_id}:{annotation.annotation_id}",
                        "label": class_ids[annotation.label],
                        "label_name": annotation.label,
                        "split": item.split or "",
                        "source_image_asset_id": item.asset.asset_id,
                        "source_annotation_id": annotation.annotation_id,
                        "source_bbox": [
                            float(annotation.geometry.get(key, 0)) for key in ("x", "y", "width", "height")
                        ],
                        "metadata_json": json.dumps(item.metadata or {}, sort_keys=True, default=str),
                        "asset_metadata_json": json.dumps(item.asset.metadata or {}, sort_keys=True, default=str),
                    }
                )
                crop_count += 1
        finally:
            if source_image is not None:
                source_image.close()

    if not crop_count:
        raise ValueError("Bounding-box classification crop export requires at least one bbox annotation.")
    return _save_huggingface_rows(
        datasets_module,
        dataset,
        rows_by_split,
        destination=destination,
        features=features,
        asset_count=crop_count,
        annotation_count=crop_count,
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
    annotation_count = 0

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
            if annotation.label not in class_ids:
                raise ValueError(
                    f"Detection annotation {annotation.annotation_id!r} uses label {annotation.label!r}, "
                    "which is missing from detection_class_names."
                )
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
            annotation_count += 1

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

    return _save_huggingface_rows(
        datasets_module,
        dataset,
        rows_by_split,
        destination=destination,
        features=features,
        asset_count=dataset.asset_count,
        annotation_count=annotation_count,
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
        semantic_mask_asset = item.assets.get("semantic_mask")
        if semantic_mask_asset is None or semantic_mask_asset.asset_id != mask_asset_id:
            raise ValueError(
                f"Semantic mask annotation for asset {item.asset.asset_id!r} does not match asset role 'semantic_mask'."
            )
        split_name = item.split or "default"
        rows_by_split.setdefault(split_name, []).append(
            {
                "image": _embedded_image(item, include_media=include_media, task="semantic segmentation"),
                "mask": _embedded_role_image(
                    item,
                    "semantic_mask",
                    include_media=include_media,
                    task="semantic segmentation",
                ),
                "asset_id": item.asset.asset_id,
                "split": item.split or "",
                "metadata_json": json.dumps(item.metadata or {}, sort_keys=True, default=str),
                "asset_metadata_json": json.dumps(item.asset.metadata or {}, sort_keys=True, default=str),
            }
        )

    return _save_huggingface_rows(
        datasets_module,
        dataset,
        rows_by_split,
        destination=destination,
        features=features,
        asset_count=dataset.asset_count,
        annotation_count=dataset.asset_count,
        artifact_metadata={
            "profile": "semantic_segmentation",
            "class_names": class_names,
            "background_id": background_id,
            "ignore_index": ignore_index,
        },
    )


def _binary_instance_mask(item, annotation, *, include_media: bool) -> tuple[dict[str, Any] | None, list[float], float]:
    mask_asset = item.assets.get("instance_mask")
    mask_asset_id = annotation.geometry.get("mask_asset_id")
    if mask_asset is None or mask_asset.asset_id != mask_asset_id:
        raise ValueError(
            f"Instance mask annotation {annotation.annotation_id!r} does not match asset role 'instance_mask'."
        )
    instance_id = annotation.geometry.get("instance_id")
    if instance_id is None:
        raise ValueError(f"Instance mask annotation {annotation.annotation_id!r} does not define instance_id.")
    attributes = annotation.attributes or {}
    raw_bbox = attributes.get("bbox_xywh")
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        raise ValueError(
            f"Instance mask annotation {annotation.annotation_id!r} must define attributes.bbox_xywh with 4 values."
        )
    bbox = [float(value) for value in raw_bbox]
    if bbox[2] <= 0 or bbox[3] <= 0:
        raise ValueError(f"Instance mask annotation {annotation.annotation_id!r} has an empty bbox_xywh.")
    raw_area = attributes.get("area")
    if raw_area is None or float(raw_area) <= 0:
        raise ValueError(f"Instance mask annotation {annotation.annotation_id!r} must define a positive area.")
    area = float(raw_area)
    if not include_media:
        return None, bbox, area

    payload = item.payloads.get("instance_mask")
    if payload is None:
        raise ValueError(f"Instance segmentation export requires mask payload bytes for asset {item.asset.asset_id!r}.")
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Instance segmentation export requires NumPy and Pillow.") from exc

    with Image.open(io.BytesIO(payload)) as indexed_mask:
        if indexed_mask.mode not in {"L", "P", "I"}:
            raise ValueError(
                f"Instance mask for asset {item.asset.asset_id!r} must be indexed and single-channel; "
                f"received mode {indexed_mask.mode!r}."
            )
        expected_id = int(instance_id)
        selected = np.asarray(indexed_mask) == expected_id
        if not selected.any():
            raise ValueError(
                f"Instance id {instance_id!r} for annotation {annotation.annotation_id!r} is absent from its mask."
            )
        binary_mask = Image.fromarray(selected.astype(np.uint8) * 255, mode="L")
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

    return _save_huggingface_rows(
        datasets_module,
        dataset,
        rows_by_split,
        destination=destination,
        features=features,
        asset_count=dataset.asset_count,
        annotation_count=annotation_count,
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
                options=options,
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

    return _save_huggingface_rows(
        datasets_module,
        dataset,
        rows_by_split,
        destination=destination_path,
        asset_count=dataset.asset_count,
        annotation_count=dataset.annotation_count,
        files_written=files_written,
    )
