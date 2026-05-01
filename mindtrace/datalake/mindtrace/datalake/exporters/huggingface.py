from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from .base import prepare_export_destination, write_export_file
from .types import ExportableDataset, ExportResult


def export_dataset_as_huggingface(
    dataset: ExportableDataset,
    *,
    destination: str | Path,
    include_media: bool = True,
    overwrite: bool = False,
    options: dict[str, Any] | None = None,
) -> ExportResult:
    """Export a canonical dataset view to a Hugging Face datasets directory."""
    del options
    try:
        datasets_module = importlib.import_module("datasets")
    except ImportError as exc:
        raise ImportError(
            "Hugging Face export requires the optional 'datasets' dependency. "
            "Install mindtrace-datalake[export-huggingface]."
        ) from exc

    destination_path = prepare_export_destination(destination, overwrite=overwrite)
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
