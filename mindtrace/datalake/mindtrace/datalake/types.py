from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from beanie import Indexed
from pydantic import BaseModel, Field, model_validator

from mindtrace.database import MindtraceDocument


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SubjectRef(BaseModel):
    """Reference to the logical subject of an asset or annotation."""

    kind: Literal["asset", "annotation"]
    id: str


class StorageRef(BaseModel):
    """Embedded reference to a payload stored in a registry/store mount."""

    mount: str
    name: str
    version: str | None = "latest"
    qualified_key: str | None = None

    @model_validator(mode="after")
    def populate_qualified_key(self) -> "StorageRef":
        version_suffix = f"@{self.version}" if self.version is not None else ""
        self.qualified_key = f"{self.mount}/{self.name}{version_suffix}"
        return self


class AnnotationSource(BaseModel):
    """Provenance for an annotation record."""

    type: Literal["human", "machine", "derived"]
    name: str
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Asset(MindtraceDocument):
    """Canonical metadata row for a payload-bearing object."""

    asset_id: Annotated[str, Indexed(unique=True)] = Field(default_factory=lambda: new_id("asset"))
    kind: Literal["image", "mask", "artifact", "embedding", "document", "other"]
    media_type: str
    storage_ref: StorageRef
    checksum: str | None = None
    size_bytes: int | None = None
    subject: SubjectRef | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "datalake_assets"
        indexes = [
            "kind",
            "storage_ref.mount",
            "storage_ref.name",
            "storage_ref.version",
            "subject.kind",
            "subject.id",
        ]


class AnnotationRecord(MindtraceDocument):
    """One atomic persisted annotation."""

    annotation_id: Annotated[str, Indexed(unique=True)] = Field(default_factory=lambda: new_id("annotation"))
    annotation_set_id: Annotated[str | None, Indexed(unique=False)] = None
    subject: SubjectRef | None = None
    kind: Literal[
        "classification",
        "regression",
        "bbox",
        "rotated_bbox",
        "polygon",
        "polyline",
        "ellipse",
        "keypoint",
        "mask",
        "instance_mask",
        "pointcloud_segmentation",
    ]
    label: str
    label_id: int | None = None
    score: float | None = None
    source: AnnotationSource
    geometry: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "datalake_annotation_records"
        indexes = [
            "annotation_set_id",
            "kind",
            "label",
            "source.type",
            "source.name",
            "subject.kind",
            "subject.id",
        ]


class AnnotationSet(MindtraceDocument):
    """Grouping/provenance boundary for annotation records."""

    annotation_set_id: Annotated[str, Indexed(unique=True)] = Field(default_factory=lambda: new_id("annotation_set"))
    datum_id: Annotated[str | None, Indexed(unique=False)] = None
    name: str
    purpose: Literal["ground_truth", "prediction", "review", "snapshot", "other"]
    source_type: Literal["human", "machine", "mixed"]
    status: Literal["draft", "active", "archived"] = "draft"
    annotation_record_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "datalake_annotation_sets"
        indexes = ["datum_id", "purpose", "source_type", "status"]


class Datum(MindtraceDocument):
    """Reusable unit of dataset membership."""

    datum_id: Annotated[str, Indexed(unique=True)] = Field(default_factory=lambda: new_id("datum"))
    split: Literal["train", "val", "test"] | None = None
    asset_refs: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    annotation_set_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "datalake_datums"
        indexes = ["split"]


class DatasetVersion(MindtraceDocument):
    """Immutable dataset manifest over datum ids."""

    dataset_version_id: Annotated[str, Indexed(unique=True)] = Field(default_factory=lambda: new_id("dataset_version"))
    dataset_name: Annotated[str, Indexed(unique=False)]
    version: str
    description: str | None = None
    manifest: list[str] = Field(default_factory=list)
    source_dataset_version_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str | None = None

    class Settings:
        name = "datalake_dataset_versions"
        indexes = [[("dataset_name", 1), ("version", 1)]]


class ResolvedDatum(BaseModel):
    """Fully resolved datum payload for read paths and views."""

    datum: Datum
    assets: dict[str, Asset] = Field(default_factory=dict)
    annotation_sets: list[AnnotationSet] = Field(default_factory=list)
    annotation_records: dict[str, list[AnnotationRecord]] = Field(default_factory=dict)


class ResolvedDatasetVersion(BaseModel):
    """Resolved dataset view with all datums and their linked records."""

    dataset_version: DatasetVersion
    datums: list[ResolvedDatum] = Field(default_factory=list)
