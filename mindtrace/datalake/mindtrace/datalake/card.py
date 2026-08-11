from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetSource(BaseModel):
    """Minimal provenance reference for a dataset card."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str | None = None
    dataset_version_id: str | None = None
    uri: str | None = None
    description: str = ""


class SplitInfo(BaseModel):
    """Summary of one dataset split."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    description: str = ""


class AnnotationField(BaseModel):
    """Summary of an annotation field documented by a dataset card."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str = ""
    labels: list[str] = Field(default_factory=list)
    description: str = ""


class DatasetCard(BaseModel):
    """Structured documentation for an immutable Datalake dataset version."""

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    task: str = ""
    modalities: list[str] = Field(default_factory=list)
    sources: list[DatasetSource] = Field(default_factory=list)
    splits: dict[str, SplitInfo] = Field(default_factory=dict)
    annotations: list[AnnotationField] = Field(default_factory=list)
    intended_uses: list[str] = Field(default_factory=list)
    out_of_scope_uses: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    markdown: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the card to a JSON-safe dictionary."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetCard:
        """Deserialize a card from a dictionary."""
        return cls.model_validate(data)

    def save_json(self, path: str | Path) -> None:
        """Save the card as formatted JSON."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load_json(cls, path: str | Path) -> DatasetCard:
        """Load a card from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
