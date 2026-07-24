from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
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
            "Datalake DataLoader wrappers require the optional datasets, torch, and torchvision dependencies. "
            "Install mindtrace-datalake[dataloaders]."
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


class HuggingFaceClassificationDataset:
    """Map-style PyTorch dataset over a typed Mindtrace Hugging Face classification export."""

    def __init__(
        self,
        export_path: str | Path,
        *,
        split: str,
        transform: Callable[[Any], Any] | None = None,
    ) -> None:
        datasets, _, _, _ = _require_huggingface_dataloader_dependencies()
        payload = datasets.load_from_disk(str(export_path))
        self._dataset = _select_split(payload, split)
        self.split = split
        self.transform = transform

        columns = set(self._dataset.column_names)
        self.classification_type = "multi_label" if "labels" in columns else "single_label"
        target_column = "labels" if self.classification_type == "multi_label" else "label"
        missing = sorted({"image", target_column} - columns)
        if missing:
            raise ValueError(f"Hugging Face classification export is missing required column(s): {missing}.")
        if self.classification_type == "multi_label":
            label_ids_feature = self._dataset.features.get("label_ids")
            label_feature = getattr(label_ids_feature, "feature", None)
        else:
            label_feature = self._dataset.features.get("label")
        self.class_names = tuple(getattr(label_feature, "names", ()) or ())

    def __len__(self) -> int:
        return len(self._dataset)

    def __getitem__(self, index: int):
        _, torch, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
        row = self._dataset[index]
        image = row["image"]
        if image is None:
            raise ValueError(
                "The Hugging Face export does not include image payloads. "
                "Re-export with include_media=True before building DataLoaders."
            )
        if hasattr(image, "convert"):
            image = image.convert("RGB")
        if self.transform is not None:
            image = self.transform(image)
        else:
            image = pil_to_tensor(image).float().div(255)
        if self.classification_type == "multi_label":
            target = torch.tensor(row["labels"], dtype=torch.float32)
        else:
            target = torch.tensor(int(row["label"]), dtype=torch.long)
        return image, target


def _object_rows(objects: Any) -> list[dict[str, Any]]:
    if isinstance(objects, Mapping):
        keys = tuple(objects)
        lengths = {len(objects[key]) for key in keys}
        if len(lengths) > 1:
            raise ValueError("Hugging Face detection object columns have inconsistent lengths.")
        return [dict(zip(keys, values, strict=True)) for values in zip(*(objects[key] for key in keys), strict=True)]
    return list(objects or [])


def _xywh_to_xyxy(bbox: Sequence[float]) -> list[float]:
    x, y, width, height = bbox
    return [x, y, x + width, y + height]


class HuggingFaceDetectionDataset:
    """Map-style PyTorch dataset over a typed Mindtrace Hugging Face detection export."""

    def __init__(
        self,
        export_path: str | Path,
        *,
        split: str,
        transform: Callable[[Any, dict[str, Any]], tuple[Any, dict[str, Any]]] | None = None,
    ) -> None:
        datasets, _, _, _ = _require_huggingface_dataloader_dependencies()
        payload = datasets.load_from_disk(str(export_path))
        self._dataset = _select_split(payload, split)
        self.split = split
        self.transform = transform

        required_columns = {"asset_id", "image", "objects"}
        missing = sorted(required_columns - set(self._dataset.column_names))
        if missing:
            raise ValueError(f"Hugging Face detection export is missing required column(s): {missing}.")
        objects_feature = self._dataset.features.get("objects")
        category_feature = getattr(getattr(objects_feature, "feature", None), "get", lambda _: None)("category")
        self.class_names = tuple(getattr(category_feature, "names", ()) or ())

    def __len__(self) -> int:
        return len(self._dataset)

    def __getitem__(self, index: int):
        _, torch, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
        row = self._dataset[index]
        image = row["image"]
        if image is None:
            raise ValueError(
                "The Hugging Face export does not include image payloads. "
                "Re-export with include_media=True before building DataLoaders."
            )
        if hasattr(image, "convert"):
            image = image.convert("RGB")
        objects = _object_rows(row["objects"])
        target = {
            "boxes": torch.tensor([_xywh_to_xyxy(obj["bbox"]) for obj in objects], dtype=torch.float32).reshape(-1, 4),
            "labels": torch.tensor([obj["category"] for obj in objects], dtype=torch.long),
            "area": torch.tensor([obj["area"] for obj in objects], dtype=torch.float32),
            "iscrowd": torch.zeros(len(objects), dtype=torch.long),
            "asset_id": row["asset_id"],
        }
        if self.transform is not None:
            return self.transform(image, target)
        return pil_to_tensor(image).float().div(255), target


class HuggingFaceSemanticSegmentationDataset:
    """Map-style PyTorch dataset over a typed Mindtrace HF semantic segmentation export."""

    def __init__(
        self,
        export_path: str | Path,
        *,
        split: str,
        transform: Callable[[Any, Any], tuple[Any, Any]] | None = None,
    ) -> None:
        datasets, _, _, _ = _require_huggingface_dataloader_dependencies()
        payload = datasets.load_from_disk(str(export_path))
        self._dataset = _select_split(payload, split)
        self.split = split
        self.transform = transform

        required_columns = {"asset_id", "background_id", "class_names", "ignore_index", "image", "mask"}
        missing = sorted(required_columns - set(self._dataset.column_names))
        if missing:
            raise ValueError(f"Hugging Face semantic segmentation export is missing required column(s): {missing}.")
        metadata_row = self._dataset[0] if len(self._dataset) else {}
        self.class_names = tuple(metadata_row.get("class_names", ()))
        self.background_id = int(metadata_row.get("background_id", 0))
        self.ignore_index = int(metadata_row.get("ignore_index", 255))

    def __len__(self) -> int:
        return len(self._dataset)

    def __getitem__(self, index: int):
        _, _, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
        row = self._dataset[index]
        image = row["image"]
        mask = row["mask"]
        if image is None or mask is None:
            raise ValueError(
                "The Hugging Face export does not include image and mask payloads. "
                "Re-export with include_media=True before building DataLoaders."
            )
        if hasattr(image, "convert"):
            image = image.convert("RGB")
        if self.transform is not None:
            return self.transform(image, mask)
        image_tensor = pil_to_tensor(image).float().div(255)
        mask_tensor = pil_to_tensor(mask)
        if mask_tensor.ndim != 3 or mask_tensor.shape[0] != 1:
            raise ValueError(
                "Semantic segmentation masks must decode as one-channel class-ID images; "
                f"received shape {tuple(mask_tensor.shape)}."
            )
        mask_tensor = mask_tensor.squeeze(0).long()
        return image_tensor, mask_tensor


def _variable_size_collate_fn(batch: Sequence[tuple[Any, Any]]):
    images, targets = zip(*batch, strict=True)
    return list(images), list(targets)


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


def build_dataloaders(
    export_path: str | Path,
    *,
    format: str = "huggingface",
    task: str = "classification",
    splits: Sequence[str] | None = None,
    transforms: Mapping[str, Callable[..., Any]] | Callable[..., Any] | None = None,
    batch_size: int = 32,
    num_workers: int = 0,
    pin_memory: bool = False,
    persistent_workers: bool = False,
    prefetch_factor: int | None = None,
    drop_last: bool = False,
    seed: int = 0,
) -> dict[str, Any]:
    """Build split-aware PyTorch DataLoaders over a Mindtrace dataset export."""

    normalized_format = format.strip().lower()
    if normalized_format != "huggingface":
        raise ValueError("Generic Dataloaders currently support format='huggingface' only.")
    normalized_task = task.strip().lower()
    if normalized_task not in {
        "classification",
        "detection",
        "object_detection",
        "semantic_segmentation",
        "semantic-segmentation",
    }:
        raise ValueError(
            "Generic DataLoaders support task='classification', task='detection', or task='semantic_segmentation'."
        )
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if num_workers < 0:
        raise ValueError("num_workers cannot be negative")
    if persistent_workers and num_workers == 0:
        raise ValueError("persistent_workers=True requires num_workers > 0")
    if prefetch_factor is not None and num_workers == 0:
        raise ValueError("prefetch_factor requires num_workers > 0")

    datasets, torch, DataLoader, _ = _require_huggingface_dataloader_dependencies()
    payload = datasets.load_from_disk(str(export_path))
    available = _available_splits(payload)
    requested = tuple(splits) if splits is not None else available
    missing = sorted(set(requested) - set(available))
    if missing:
        raise KeyError(f"Export does not contain requested split(s) {missing}; available: {list(available)}.")

    loaders: dict[str, Any] = {}
    for split in requested:
        transform = _transform_for_split(transforms, split)
        if normalized_task == "classification":
            dataset = HuggingFaceClassificationDataset(export_path, split=split, transform=transform)
        elif normalized_task in {"detection", "object_detection"}:
            dataset = HuggingFaceDetectionDataset(export_path, split=split, transform=transform)
        else:
            dataset = HuggingFaceSemanticSegmentationDataset(export_path, split=split, transform=transform)
        generator = torch.Generator()
        generator.manual_seed(seed)
        loader_kwargs: dict[str, Any] = {
            "batch_size": batch_size,
            "shuffle": split == "train",
            "num_workers": num_workers,
            "pin_memory": pin_memory,
            "drop_last": drop_last and split == "train",
            "generator": generator,
            "worker_init_fn": _worker_init_fn,
        }
        if num_workers > 0:
            loader_kwargs["persistent_workers"] = persistent_workers
            if prefetch_factor is not None:
                loader_kwargs["prefetch_factor"] = prefetch_factor
        if normalized_task != "classification":
            loader_kwargs["collate_fn"] = _variable_size_collate_fn
        loaders[split] = DataLoader(dataset, **loader_kwargs)
    return loaders


__all__ = [
    "HuggingFaceClassificationDataset",
    "HuggingFaceDetectionDataset",
    "HuggingFaceSemanticSegmentationDataset",
    "build_dataloaders",
]
