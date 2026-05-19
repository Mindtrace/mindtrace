from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any

from mindtrace.datalake.types import AnnotationRecord, AnnotationSet, Asset, ResolvedDatasetVersion, ResolvedDatum

from .types import ExportableDataset, ExportableItem


def media_suffix_for_asset(asset: Asset) -> str:
    """Return a best-effort filename suffix for an asset media type."""
    media_type = asset.media_type or "application/octet-stream"
    if media_type == "image/jpeg":
        return ".jpg"
    guessed = mimetypes.guess_extension(media_type)
    return guessed or ".bin"


def default_export_filename(asset: Asset) -> str:
    """Return a stable export filename for an asset."""
    return f"{asset.asset_id}{media_suffix_for_asset(asset)}"


def prepare_export_destination(destination: str | Path, *, overwrite: bool) -> Path:
    """Create or clean the destination directory for an export."""
    path = Path(destination)
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"Export destination already exists: {path}")
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_export_file(destination: Path, relative_path: str | Path, payload: bytes) -> str:
    """Write one file beneath an export destination and return its relative path."""
    rel = Path(relative_path)
    target = destination / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return rel.as_posix()


def _mapped_split(split: str | None, split_map: dict[str, str] | None) -> str | None:
    if split is None or split_map is None:
        return split
    return split_map.get(split, split)


def _annotation_subject_asset_id(annotation: AnnotationRecord) -> str | None:
    subject = annotation.subject
    if subject is None or subject.kind != "asset":
        return None
    return subject.id


def _primary_asset_entry(resolved_datum: ResolvedDatum) -> tuple[str, Asset] | None:
    for role in ("image", "asset"):
        asset = resolved_datum.assets.get(role)
        if asset is not None:
            return role, asset
    for role, asset in resolved_datum.assets.items():
        return role, asset
    return None


def _annotation_sets_for_asset(
    resolved_datum: ResolvedDatum, asset_id: str
) -> tuple[list[AnnotationSet], list[AnnotationRecord], list[str]]:
    warnings: list[str] = []
    annotation_sets: list[AnnotationSet] = []
    annotations: list[AnnotationRecord] = []
    for annotation_set in resolved_datum.annotation_sets:
        set_records = list(resolved_datum.annotation_records.get(annotation_set.annotation_set_id, []))
        matching_records = [
            record for record in set_records if _annotation_subject_asset_id(record) in {None, asset_id}
        ]
        if matching_records:
            annotation_sets.append(annotation_set)
            annotations.extend(matching_records)
            skipped = [
                record.annotation_id
                for record in set_records
                if _annotation_subject_asset_id(record) not in {None, asset_id}
            ]
            if skipped:
                warnings.append(
                    f"Skipped {len(skipped)} annotation(s) in set {annotation_set.annotation_set_id} because they target a non-primary asset."
                )
        elif set_records:
            warnings.append(
                f"Skipped annotation set {annotation_set.annotation_set_id} for datum {resolved_datum.datum.datum_id} because it has no records for asset {asset_id}."
            )
    return annotation_sets, annotations, warnings


def _build_exportable_item(
    resolved_datum: ResolvedDatum,
    *,
    payload_bytes: bytes,
    split_map: dict[str, str] | None = None,
) -> tuple[ExportableItem | None, list[str]]:
    warnings: list[str] = []
    primary_entry = _primary_asset_entry(resolved_datum)
    if primary_entry is None:
        return None, [f"Skipped datum {resolved_datum.datum.datum_id} because it does not reference any assets."]
    role, asset = primary_entry
    if len(resolved_datum.assets) > 1:
        warnings.append(
            f"Datum {resolved_datum.datum.datum_id} has multiple assets; exporting primary role {role!r} only."
        )
    annotation_sets, annotations, annotation_warnings = _annotation_sets_for_asset(resolved_datum, asset.asset_id)
    warnings.extend(annotation_warnings)
    return (
        ExportableItem.model_construct(
            asset=asset,
            split=_mapped_split(resolved_datum.datum.split, split_map),
            metadata=dict(resolved_datum.datum.metadata or {}),
            annotations=annotations,
            annotation_sets=annotation_sets,
            payload_bytes=payload_bytes,
            source_filename=default_export_filename(asset),
        ),
        warnings,
    )


def build_exportable_dataset_from_resolved_version_sync(
    object_loader: Any,
    resolved_dataset_version: ResolvedDatasetVersion,
    *,
    split_map: dict[str, str] | None = None,
) -> ExportableDataset:
    """Build a canonical export view from a resolved dataset snapshot."""
    warnings: list[str] = []
    items: list[ExportableItem] = []
    for resolved_datum in resolved_dataset_version.datums:
        primary_entry = _primary_asset_entry(resolved_datum)
        if primary_entry is None:
            warnings.append(f"Skipped datum {resolved_datum.datum.datum_id} because it does not reference any assets.")
            continue
        _, asset = primary_entry
        payload_loader = getattr(object_loader, "get_asset_payload", None)
        payload_ref = asset.payload_storage_ref or asset.storage_ref
        payload_bytes = (
            payload_loader(asset.asset_id) if callable(payload_loader) else object_loader.get_object(payload_ref)
        )
        export_item, item_warnings = _build_exportable_item(
            resolved_datum,
            payload_bytes=payload_bytes,
            split_map=split_map,
        )
        warnings.extend(item_warnings)
        if export_item is not None:
            items.append(export_item)
    dataset_version = resolved_dataset_version.dataset_version
    return ExportableDataset(
        name=dataset_version.dataset_name,
        description=dataset_version.description,
        metadata=dict(dataset_version.metadata or {}),
        items=items,
        warnings=warnings,
    )


async def build_exportable_dataset_from_resolved_version_async(
    object_loader: Any,
    resolved_dataset_version: ResolvedDatasetVersion,
    *,
    split_map: dict[str, str] | None = None,
) -> ExportableDataset:
    """Build a canonical export view from a resolved dataset snapshot."""
    warnings: list[str] = []
    items: list[ExportableItem] = []
    for resolved_datum in resolved_dataset_version.datums:
        primary_entry = _primary_asset_entry(resolved_datum)
        if primary_entry is None:
            warnings.append(f"Skipped datum {resolved_datum.datum.datum_id} because it does not reference any assets.")
            continue
        _, asset = primary_entry
        payload_loader = getattr(object_loader, "get_asset_payload", None)
        payload_ref = asset.payload_storage_ref or asset.storage_ref
        payload_bytes = (
            await payload_loader(asset.asset_id)
            if callable(payload_loader)
            else await object_loader.get_object(payload_ref)
        )
        export_item, item_warnings = _build_exportable_item(
            resolved_datum,
            payload_bytes=payload_bytes,
            split_map=split_map,
        )
        warnings.extend(item_warnings)
        if export_item is not None:
            items.append(export_item)
    dataset_version = resolved_dataset_version.dataset_version
    return ExportableDataset(
        name=dataset_version.dataset_name,
        description=dataset_version.description,
        metadata=dict(dataset_version.metadata or {}),
        items=items,
        warnings=warnings,
    )
