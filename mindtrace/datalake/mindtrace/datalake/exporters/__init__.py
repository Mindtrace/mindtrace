from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mindtrace.datalake.types import DatasetVersion

from .types import ExportableDataset, ExportableItem, ExportProgress, ExportResult

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


async def export_dataset_version_streaming(
    object_loader: Any,
    dataset_version: DatasetVersion,
    *,
    format: str,
    destination: str | Path,
    include_media: bool = True,
    overwrite: bool = False,
    split_map: dict[str, str] | None = None,
    exporter_options: dict[str, Any] | None = None,
    page_size: int = 256,
    progress_callback: Callable[[ExportProgress], None] | None = None,
) -> ExportResult:
    """Dispatch a paged DatasetVersion export to a streaming-capable backend."""
    if format.strip().lower() != "huggingface":
        raise ValueError("Streaming dataset export currently supports only format='huggingface'.")
    from .huggingface import export_dataset_version_as_huggingface_streaming

    return await export_dataset_version_as_huggingface_streaming(
        object_loader,
        dataset_version,
        destination=destination,
        include_media=include_media,
        overwrite=overwrite,
        split_map=split_map,
        options=exporter_options,
        page_size=page_size,
        progress_callback=progress_callback,
    )


__all__ = [
    "ExportResult",
    "ExportProgress",
    "ExportableDataset",
    "ExportableItem",
    "export_dataset_to_format",
    "export_dataset_version_streaming",
    "get_dataset_exporter",
]
