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
        datasets, torch, _, pil_to_tensor = _require_huggingface_dataloader_dependencies()
        payload = datasets.load_from_disk(str(export_path))
        self._dataset = _select_split(payload, split)
        self.split = split
        self.transform = transform
        self._torch = torch
        self._pil_to_tensor = pil_to_tensor

        required_columns = {"image", "label"}
        missing = sorted(required_columns - set(self._dataset.column_names))
        if missing:
            raise ValueError(
                f"Hugging Face classification export is missing required column(s): {missing}."
            )
        label_feature = self._dataset.features.get("label")
        self.class_names = tuple(getattr(label_feature, "names", ()) or ())

    def __len__(self) -> int:
        return len(self._dataset)

    def __getitem__(self, index: int):
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
            image = self._pil_to_tensor(image).float().div(255)
        target = self._torch.tensor(int(row["label"]), dtype=self._torch.long)
        return image, target


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
    transforms: Mapping[str, Callable[[Any], Any]] | Callable[[Any], Any] | None,
    split: str,
) -> Callable[[Any], Any] | None:
    if transforms is None or callable(transforms):
        return transforms
    return transforms.get(split)


def build_dataloaders(
    export_path: str | Path,
    *,
    format: str = "huggingface",
    task: str = "classification",
    splits: Sequence[str] | None = None,
    transforms: Mapping[str, Callable[[Any], Any]] | Callable[[Any], Any] | None = None,
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
        raise ValueError(
            "Generic classification DataLoaders currently support format='huggingface' only."
        )
    normalized_task = task.strip().lower()
    if normalized_task != "classification":
        raise ValueError(
            "Generic DataLoaders currently support task='classification' only; "
            "detection and segmentation adapters have not been implemented."
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
        dataset = HuggingFaceClassificationDataset(
            export_path,
            split=split,
            transform=_transform_for_split(transforms, split),
        )
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
        loaders[split] = DataLoader(dataset, **loader_kwargs)
    return loaders


__all__ = ["HuggingFaceClassificationDataset", "build_dataloaders"]
