from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from mindtrace.datalake.types import AnnotationRecord, AnnotationSet, Asset


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


class ExportableItem(BaseModel):
    """Format-neutral dataset item prepared for exporter backends."""

    assets: dict[str, Asset]
    primary_role: str
    split: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    annotations: list[AnnotationRecord] = Field(default_factory=list)
    annotation_sets: list[AnnotationSet] = Field(default_factory=list)
    payloads: dict[str, bytes] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_roles(self) -> ExportableItem:
        if self.primary_role not in self.assets:
            raise ValueError(f"primary_role {self.primary_role!r} is not present in assets")
        unknown_payload_roles = sorted(set(self.payloads) - set(self.assets))
        if unknown_payload_roles:
            raise ValueError(f"payload roles do not reference known assets: {unknown_payload_roles}")
        return self

    @property
    def asset(self) -> Asset:
        """Return the primary asset."""
        return self.assets[self.primary_role]

    @property
    def payload_bytes(self) -> bytes | None:
        """Return primary-asset payload bytes when media was loaded."""
        return self.payloads.get(self.primary_role)

    @property
    def source_filename(self) -> str:
        """Return the stable export filename for the primary asset."""
        return default_export_filename(self.asset)


class ExportableDataset(BaseModel):
    """Canonical in-memory export view built from a resolved dataset snapshot."""

    name: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    items: list[ExportableItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def asset_count(self) -> int:
        return len(self.items)

    @property
    def annotation_count(self) -> int:
        return sum(len(item.annotations) for item in self.items)


class ExportResult(BaseModel):
    """Summary returned by dataset export operations."""

    format: str
    destination: Path
    dataset_name: str
    asset_count: int
    annotation_count: int
    files_written: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
