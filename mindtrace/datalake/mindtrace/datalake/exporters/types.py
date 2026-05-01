from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mindtrace.datalake.types import AnnotationRecord, AnnotationSet, Asset


class ExportableItem(BaseModel):
    """Format-neutral dataset item prepared for exporter backends."""

    asset: Asset
    split: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    annotations: list[AnnotationRecord] = Field(default_factory=list)
    annotation_sets: list[AnnotationSet] = Field(default_factory=list)
    payload_bytes: bytes | None = None
    source_filename: str | None = None


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
