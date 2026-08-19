from __future__ import annotations

import json
import random
from collections.abc import Callable, Collection, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any


def _require_huggingface_dataloader_dependencies():
    try:
        import datasets
        import torch
        from torch.utils.data import DataLoader
        from torchvision.transforms.functional import pil_to_tensor
    except ImportError as exc:
        raise ImportError(
            "Hugging Face training adapters require datasets, torch, and torchvision. "
            "Install mindtrace-models[dataloaders]."
        ) from exc
    return datasets, torch, DataLoader, pil_to_tensor


def _available_splits(payload: Any) -> tuple[str, ...]:
    if isinstance(payload, Mapping):
        return tuple(str(split) for split in payload.keys())
    return ("default",)


def _select_split(payload: Any, split: str):
    available = _available_splits(payload)
    if available == ("default",):
        if split != "default":
            raise KeyError(f"Export contains only the default split; requested {split!r}.")
        return payload
    if split not in available:
        raise KeyError(f"Export does not contain split {split!r}; available splits: {list(available)}.")
    return payload[split]


def _object_rows(objects: Any) -> list[dict[str, Any]]:
    if isinstance(objects, Mapping):
        keys = tuple(objects)
        lengths = {len(objects[key]) for key in keys}
        if len(lengths) > 1:
            raise ValueError("Hugging Face detection object columns have inconsistent lengths.")
        return [dict(zip(keys, values, strict=True)) for values in zip(*(objects[key] for key in keys), strict=True)]
    return list(objects or [])


def _object_feature_fields(dataset: Any) -> Mapping[str, Any]:
    """Return object fields from either Hugging Face Sequence representation."""
    objects_feature = dataset.features.get("objects")
    sequence_fields = getattr(objects_feature, "feature", None)
    if isinstance(sequence_fields, Mapping):
        return sequence_fields
    if isinstance(objects_feature, Mapping):
        return objects_feature
    return {}


def _artifact_metadata(dataset: Any, export_path: str | Path) -> Mapping[str, Any]:
    info_metadata = getattr(getattr(dataset, "info", None), "metadata", None)
    if isinstance(info_metadata, Mapping) and isinstance(info_metadata.get("mindtrace"), Mapping):
        return info_metadata["mindtrace"]
    metadata_path = Path(export_path) / "mindtrace_metadata.json"
    if metadata_path.is_file():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = payload.get("mindtrace", {})
        if isinstance(metadata, Mapping):
            return metadata
    return {}


def _attach_artifact_metadata(dataset: Any, export_path: str | Path) -> None:
    metadata = _artifact_metadata(dataset, export_path)
    info = getattr(dataset, "info", None)
    if not metadata or info is None:
        return
    info_metadata = getattr(info, "metadata", None)
    merged = dict(info_metadata) if isinstance(info_metadata, Mapping) else {}
    merged["mindtrace"] = dict(metadata)
    info.metadata = merged


def _xywh_to_xyxy(bbox: Sequence[float]) -> list[float]:
    x, y, width, height = bbox
    return [x, y, x + width, y + height]


def _require_columns(dataset: Any, profile: str, required_columns: set[str]) -> None:
    missing = sorted(required_columns - set(dataset.column_names))
    if missing:
        raise ValueError(f"Hugging Face {profile} export is missing required column(s): {missing}.")


def _rgb_image(image: Any, *, consumer: str) -> Any:
    if image is None:
        raise ValueError(
            "The Hugging Face export does not include image payloads. "
            f"Re-export with include_media=True before building {consumer}."
        )
    return image.convert("RGB") if hasattr(image, "convert") else image


def _add_metadata(
    output: dict[str, list[Any]],
    batch: Mapping[str, list[Any]],
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> None:
    if return_metadata:
        output["metadata"] = [
            {"asset_id": asset_id, **{key: batch[key][index] for key in metadata_keys}}
            for index, asset_id in enumerate(batch["asset_id"])
        ]


def _transform_classification_batch(
    batch: Mapping[str, list[Any]],
    *,
    classification_type: str,
    transform: Callable[[Any], Any] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> dict[str, list[Any]]:
    _, torch, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
    target_column = "labels" if classification_type == "multi_label" else "label"
    images: list[Any] = []
    targets: list[Any] = []
    for image, raw_target in zip(batch["image"], batch[target_column], strict=True):
        image = _rgb_image(image, consumer="DataLoaders")
        images.append(transform(image) if transform is not None else pil_to_tensor(image).float().div(255))
        target_dtype = torch.float32 if classification_type == "multi_label" else torch.long
        target_value = raw_target if classification_type == "multi_label" else int(raw_target)
        targets.append(torch.tensor(target_value, dtype=target_dtype))
    output = {"image": images, "target": targets}
    _add_metadata(output, batch, return_metadata, metadata_keys)
    return output


def _transform_detection_batch(
    batch: Mapping[str, list[Any]],
    *,
    transform: Callable[[Any, dict[str, Any]], tuple[Any, dict[str, Any]]] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> dict[str, list[Any]]:
    _, torch, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
    images: list[Any] = []
    targets: list[Any] = []
    for image, raw_objects in zip(batch["image"], batch["objects"], strict=True):
        image = _rgb_image(image, consumer="DataLoaders")
        objects = _object_rows(raw_objects)
        difficult = [bool(obj.get("difficult", False)) for obj in objects]
        target = {
            "boxes": torch.tensor([_xywh_to_xyxy(obj["bbox"]) for obj in objects], dtype=torch.float32).reshape(-1, 4),
            "labels": torch.tensor([obj["category"] for obj in objects], dtype=torch.long),
            "area": torch.tensor([obj["area"] for obj in objects], dtype=torch.float32),
            # Torchvision's COCO-style evaluators use iscrowd as the ignore channel.
            # Preserve VOC difficult separately while projecting it for evaluator compatibility.
            "iscrowd": torch.tensor(difficult, dtype=torch.long),
            "difficult": torch.tensor(difficult, dtype=torch.bool),
        }
        if transform is not None:
            image, target = transform(image, target)
        else:
            image = pil_to_tensor(image).float().div(255)
        images.append(image)
        targets.append(target)
    output = {"image": images, "target": targets}
    _add_metadata(output, batch, return_metadata, metadata_keys)
    return output


def _transform_semantic_segmentation_batch(
    batch: Mapping[str, list[Any]],
    *,
    transform: Callable[[Any, Any], tuple[Any, Any]] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> dict[str, list[Any]]:
    _, _, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
    images: list[Any] = []
    targets: list[Any] = []
    for image, mask in zip(batch["image"], batch["mask"], strict=True):
        image = _rgb_image(image, consumer="DataLoaders")
        if mask is None:
            raise ValueError(
                "The Hugging Face export does not include mask payloads. "
                "Re-export with include_media=True before building DataLoaders."
            )
        if transform is not None:
            image, mask = transform(image, mask)
        else:
            image = pil_to_tensor(image).float().div(255)
            mask_tensor = pil_to_tensor(mask)
            if mask_tensor.ndim != 3 or mask_tensor.shape[0] != 1:
                raise ValueError(
                    "Semantic segmentation masks must decode as one-channel class-ID images; "
                    f"received shape {tuple(mask_tensor.shape)}."
                )
            mask = mask_tensor.squeeze(0).long()
        images.append(image)
        targets.append(mask)
    output = {"image": images, "target": targets}
    _add_metadata(output, batch, return_metadata, metadata_keys)
    return output


def _transform_instance_segmentation_batch(
    batch: Mapping[str, list[Any]],
    *,
    transform: Callable[[Any, dict[str, Any]], tuple[Any, dict[str, Any]]] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> dict[str, list[Any]]:
    _, torch, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
    images: list[Any] = []
    targets: list[Any] = []
    for image, raw_objects in zip(batch["image"], batch["objects"], strict=True):
        image = _rgb_image(image, consumer="datasets")
        objects = _object_rows(raw_objects)
        mask_tensors = []
        for obj in objects:
            mask = obj["mask"]
            if mask is None:
                raise ValueError(
                    "The Hugging Face export does not include instance mask payloads. "
                    "Re-export with include_media=True before building datasets."
                )
            mask_tensor = pil_to_tensor(mask)
            if mask_tensor.ndim != 3 or mask_tensor.shape[0] != 1:
                raise ValueError(
                    "Instance masks must decode as one-channel binary images; "
                    f"received shape {tuple(mask_tensor.shape)}."
                )
            mask_tensors.append(mask_tensor.squeeze(0).bool())
        if mask_tensors:
            masks = torch.stack(mask_tensors)
        else:
            masks = torch.zeros((0, image.height, image.width), dtype=torch.bool)
        target = {
            "boxes": torch.tensor([_xywh_to_xyxy(obj["bbox"]) for obj in objects], dtype=torch.float32).reshape(-1, 4),
            "labels": torch.tensor([obj["category"] for obj in objects], dtype=torch.long),
            "masks": masks,
            "area": torch.tensor([obj["area"] for obj in objects], dtype=torch.float32),
            "iscrowd": torch.tensor([int(obj["iscrowd"]) for obj in objects], dtype=torch.long),
        }
        if transform is not None:
            image, target = transform(image, target)
        else:
            image = pil_to_tensor(image).float().div(255)
        images.append(image)
        targets.append(target)
    output = {"image": images, "target": targets}
    _add_metadata(output, batch, return_metadata, metadata_keys)
    return output


def _build_classification_dataset(
    dataset: Any,
    *,
    transform: Callable[..., Any] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> Any:
    classification_type = "multi_label" if "labels" in dataset.column_names else "single_label"
    target_column = "labels" if classification_type == "multi_label" else "label"
    required_columns = {"image", target_column}
    if return_metadata:
        required_columns.update(("asset_id", *metadata_keys))
    _require_columns(dataset, "classification", required_columns)
    return dataset.with_transform(
        partial(
            _transform_classification_batch,
            classification_type=classification_type,
            transform=transform,
            return_metadata=return_metadata,
            metadata_keys=metadata_keys,
        )
    )


def _build_detection_dataset(
    dataset: Any,
    *,
    transform: Callable[..., Any] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> Any:
    _require_columns(dataset, "detection", {"asset_id", "image", "objects", *metadata_keys})
    return dataset.with_transform(
        partial(
            _transform_detection_batch,
            transform=transform,
            return_metadata=return_metadata,
            metadata_keys=metadata_keys,
        )
    )


def _build_semantic_segmentation_dataset(
    dataset: Any,
    *,
    transform: Callable[..., Any] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> Any:
    _require_columns(dataset, "semantic segmentation", {"asset_id", "image", "mask", *metadata_keys})
    return dataset.with_transform(
        partial(
            _transform_semantic_segmentation_batch,
            transform=transform,
            return_metadata=return_metadata,
            metadata_keys=metadata_keys,
        )
    )


def _build_instance_segmentation_dataset(
    dataset: Any,
    *,
    transform: Callable[..., Any] | None,
    return_metadata: bool,
    metadata_keys: Sequence[str],
) -> Any:
    _require_columns(dataset, "instance segmentation", {"asset_id", "image", "objects", *metadata_keys})
    return dataset.with_transform(
        partial(
            _transform_instance_segmentation_batch,
            transform=transform,
            return_metadata=return_metadata,
            metadata_keys=metadata_keys,
        )
    )


_BUILTIN_PROFILE_BUILDERS = {
    "classification": _build_classification_dataset,
    "detection": _build_detection_dataset,
    "semantic_segmentation": _build_semantic_segmentation_dataset,
    "instance_segmentation": _build_instance_segmentation_dataset,
}


def _sample_columns(sample: Any) -> tuple[Any, ...]:
    if isinstance(sample, Mapping):
        columns = (sample["image"], sample["target"])
        return (*columns, sample["metadata"]) if "metadata" in sample else columns
    return tuple(sample)


def _classification_collate_fn(batch: Sequence[Any]):
    _, torch, _, _ = _require_huggingface_dataloader_dependencies()
    columns = tuple(zip(*(_sample_columns(sample) for sample in batch), strict=True))
    collated: tuple[Any, ...] = (torch.stack(columns[0]), torch.stack(columns[1]))
    return (*collated, list(columns[2])) if len(columns) == 3 else collated


def _variable_size_collate_fn(batch: Sequence[Any]):
    columns = tuple(zip(*(_sample_columns(sample) for sample in batch), strict=True))
    return tuple(list(column) for column in columns)


def _worker_init_fn(_: int) -> None:
    _, torch, _, _ = _require_huggingface_dataloader_dependencies()
    worker_seed = torch.initial_seed() % (2**32)
    random.seed(worker_seed)
    try:
        import numpy
    except ImportError:
        return
    numpy.random.seed(worker_seed)


def _transform_for_split(
    transforms: Mapping[str, Callable[..., Any]] | Callable[..., Any] | None,
    split: str,
) -> Callable[..., Any] | None:
    if transforms is None or callable(transforms):
        return transforms
    return transforms.get(split)


def _normalize_task(task: str) -> str:
    normalized_task = task.strip().lower().replace("-", "_")
    aliases = {
        "object_detection": "detection",
        "semantic_segmentation": "semantic_segmentation",
        "instance_segmentation": "instance_segmentation",
    }
    normalized_task = aliases.get(normalized_task, normalized_task)
    if normalized_task not in {
        "classification",
        "detection",
        "segmentation",
        "semantic_segmentation",
        "instance_segmentation",
    }:
        raise ValueError(
            "Generic datasets support task='classification', task='detection', or task='segmentation'. "
            "Explicit task='semantic_segmentation' and task='instance_segmentation' aliases are also accepted."
        )
    return normalized_task


def _infer_segmentation_profile(dataset: Any) -> str:
    columns = set(dataset.column_names)
    has_semantic_mask = "mask" in columns
    object_fields = _object_feature_fields(dataset)
    has_instances = bool({"mask", "masks"} & set(object_fields))
    if has_semantic_mask and has_instances:
        raise ValueError(
            "Segmentation export is ambiguous: it contains both a semantic 'mask' column and an instance "
            "'objects' column. Request task='semantic_segmentation' or task='instance_segmentation' explicitly."
        )
    if has_semantic_mask:
        return "semantic_segmentation"
    if has_instances:
        return "instance_segmentation"
    raise ValueError(
        "Unable to infer segmentation profile from the Hugging Face schema. Expected a semantic 'mask' column "
        "or an instance 'objects' column containing per-object masks."
    )


def _normalize_metadata_keys(metadata_keys: Sequence[str] | None, *, return_metadata: bool) -> tuple[str, ...]:
    if metadata_keys is None:
        return ()
    if isinstance(metadata_keys, (str, bytes)) or not isinstance(metadata_keys, Sequence):
        raise ValueError("metadata_keys must be a sequence of exported field names.")
    normalized = tuple(metadata_keys)
    if any(not isinstance(key, str) or not key for key in normalized):
        raise ValueError("metadata_keys must contain non-empty string field names.")
    if len(set(normalized)) != len(normalized):
        raise ValueError("metadata_keys must not contain duplicate field names.")
    if normalized and not return_metadata:
        raise ValueError("metadata_keys requires return_metadata=True.")
    return normalized


def _build_datasets_and_profiles(
    export_path: str | Path,
    *,
    task: str = "classification",
    splits: Sequence[str] | None = None,
    transforms: Mapping[str, Callable[..., Any]] | Callable[..., Any] | None = None,
    task_profiles: Mapping[str, Callable[..., Any]] | None = None,
    return_metadata: bool = False,
    metadata_keys: Sequence[str] | None = None,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    selected_metadata_keys = _normalize_metadata_keys(metadata_keys, return_metadata=return_metadata)
    custom_profiles = dict(task_profiles or {})
    normalized_task = task.strip().lower().replace("-", "_")
    if normalized_task not in custom_profiles:
        normalized_task = _normalize_task(task)

    datasets_module, _, _, _ = _require_huggingface_dataloader_dependencies()
    payload = datasets_module.load_from_disk(str(export_path))
    available = _available_splits(payload)
    requested = tuple(splits) if splits is not None else available
    missing = sorted(set(requested) - set(available))
    if missing:
        raise KeyError(f"Export does not contain requested split(s) {missing}; available: {list(available)}.")

    built: dict[str, Any] = {}
    built_profiles: dict[str, str | None] = {}
    for split in requested:
        transform = _transform_for_split(transforms, split)
        profile = normalized_task
        selected_dataset = _select_split(payload, split)
        _attach_artifact_metadata(selected_dataset, export_path)
        if profile in custom_profiles:
            built[split] = custom_profiles[profile](selected_dataset, split=split, transform=transform)
            built_profiles[split] = None
            continue
        if profile == "segmentation":
            profile = _infer_segmentation_profile(selected_dataset)
        built[split] = _BUILTIN_PROFILE_BUILDERS[profile](
            selected_dataset,
            transform=transform,
            return_metadata=return_metadata,
            metadata_keys=selected_metadata_keys,
        )
        built_profiles[split] = profile
    return built, built_profiles


def build_datasets(
    export_path: str | Path,
    *,
    task: str = "classification",
    splits: Sequence[str] | None = None,
    transforms: Mapping[str, Callable[..., Any]] | Callable[..., Any] | None = None,
    task_profiles: Mapping[str, Callable[..., Any]] | None = None,
    return_metadata: bool = False,
    metadata_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build split-aware native Hugging Face datasets with on-access PyTorch transforms."""

    built, _ = _build_datasets_and_profiles(
        export_path,
        task=task,
        splits=splits,
        transforms=transforms,
        task_profiles=task_profiles,
        return_metadata=return_metadata,
        metadata_keys=metadata_keys,
    )
    return built


def build_dataloaders(
    export_path: str | Path,
    *,
    task: str = "classification",
    splits: Sequence[str] | None = None,
    transforms: Mapping[str, Callable[..., Any]] | Callable[..., Any] | None = None,
    task_profiles: Mapping[str, Callable[..., Any]] | None = None,
    return_metadata: bool = False,
    metadata_keys: Sequence[str] | None = None,
    batch_size: int = 32,
    num_workers: int = 0,
    pin_memory: bool = False,
    persistent_workers: bool = False,
    prefetch_factor: int | None = None,
    drop_last: bool = False,
    shuffle_splits: Collection[str] | None = None,
    drop_last_splits: Collection[str] | None = None,
    dataloader_kwargs: Mapping[str, Any] | None = None,
    per_split_dataloader_kwargs: Mapping[str, Mapping[str, Any]] | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """Build split-aware PyTorch DataLoaders over a Mindtrace dataset export."""

    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if num_workers < 0:
        raise ValueError("num_workers cannot be negative")
    if persistent_workers and num_workers == 0:
        raise ValueError("persistent_workers=True requires num_workers > 0")
    if prefetch_factor is not None and num_workers == 0:
        raise ValueError("prefetch_factor requires num_workers > 0")

    built_datasets, built_profiles = _build_datasets_and_profiles(
        export_path,
        task=task,
        splits=splits,
        transforms=transforms,
        task_profiles=task_profiles,
        return_metadata=return_metadata,
        metadata_keys=metadata_keys,
    )
    _, torch, DataLoader, _ = _require_huggingface_dataloader_dependencies()
    shuffled = {"train"} if shuffle_splits is None else set(shuffle_splits)
    dropped = ({"train"} if drop_last else set()) if drop_last_splits is None else set(drop_last_splits)

    loaders: dict[str, Any] = {}
    for split, dataset in built_datasets.items():
        generator = torch.Generator()
        generator.manual_seed(seed)
        loader_kwargs: dict[str, Any] = {
            "batch_size": batch_size,
            "shuffle": split in shuffled,
            "num_workers": num_workers,
            "pin_memory": pin_memory,
            "drop_last": split in dropped,
            "generator": generator,
            "worker_init_fn": _worker_init_fn,
        }
        if num_workers > 0:
            loader_kwargs["persistent_workers"] = persistent_workers
            if prefetch_factor is not None:
                loader_kwargs["prefetch_factor"] = prefetch_factor
        loader_kwargs["collate_fn"] = (
            _classification_collate_fn if built_profiles[split] == "classification" else _variable_size_collate_fn
        )
        native_kwargs = {
            **(dataloader_kwargs or {}),
            **((per_split_dataloader_kwargs or {}).get(split, {})),
        }
        if "sampler" in native_kwargs:
            if shuffle_splits is not None and split in shuffled:
                raise ValueError(f"Split {split!r} cannot configure both a sampler and shuffle=True.")
            loader_kwargs["shuffle"] = False
        if "batch_sampler" in native_kwargs:
            for incompatible in ("batch_size", "shuffle", "sampler", "drop_last"):
                loader_kwargs.pop(incompatible, None)
        loader_kwargs.update(native_kwargs)
        loaders[split] = DataLoader(dataset, **loader_kwargs)
    return loaders


__all__ = [
    "build_datasets",
    "build_dataloaders",
]
