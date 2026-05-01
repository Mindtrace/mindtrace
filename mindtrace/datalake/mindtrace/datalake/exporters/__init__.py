from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .types import ExportableDataset, ExportableItem, ExportResult

ExporterFunc = Callable[..., ExportResult]


def get_dataset_exporter(format_name: str) -> ExporterFunc:
    """Return the exporter callable for a named format."""
    normalized = format_name.strip().lower()
    if normalized == "coco":
        from .coco import export_dataset_as_coco

        return export_dataset_as_coco
    if normalized == "huggingface":
        from .huggingface import export_dataset_as_huggingface

        return export_dataset_as_huggingface
    raise ValueError(f"Unsupported dataset export format {format_name!r}. Supported formats: 'coco', 'huggingface'.")


def export_dataset_to_format(
    dataset: ExportableDataset,
    *,
    format: str,
    destination: str | Path,
    include_media: bool = True,
    overwrite: bool = False,
    exporter_options: dict[str, Any] | None = None,
) -> ExportResult:
    """Dispatch a canonical export view to a concrete exporter backend."""
    exporter = get_dataset_exporter(format)
    return exporter(
        dataset,
        destination=destination,
        include_media=include_media,
        overwrite=overwrite,
        options=exporter_options,
    )


__all__ = [
    "ExportResult",
    "ExportableDataset",
    "ExportableItem",
    "export_dataset_to_format",
    "get_dataset_exporter",
]
