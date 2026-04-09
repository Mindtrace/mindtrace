from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from beanie import Indexed
from beanie.exceptions import CollectionWasNotInitialized
from pydantic import BaseModel, Field, model_validator

from mindtrace.database import MindtraceDocument


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class DatalakeDocument(MindtraceDocument):
    """Beanie document that can still be instantiated before collection init in unit tests."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        try:
            super().__init__(*args, **kwargs)
        except CollectionWasNotInitialized:
            BaseModel.__init__(self, *args, **kwargs)


class SubjectRef(BaseModel):
    """Reference to the logical subject of an asset or annotation."""

    kind: Literal["asset", "annotation"]
    id: str

    def __str__(self) -> str:
        return f"SubjectRef(kind={self.kind}, id={self.id})"


class StorageRef(BaseModel):
    """Embedded reference to a payload stored in a registry/store mount."""

    mount: str
    name: str
    version: str | None = "latest"
    qualified_key: str | None = None

    def __str__(self) -> str:
        return f"StorageRef({self.qualified_key})"

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

    def __str__(self) -> str:
        version = f", version={self.version}" if self.version else ""
        return f"AnnotationSource(type={self.type}, name={self.name}{version})"


class Asset(DatalakeDocument):
    """Canonical metadata row for a payload-bearing object."""

    def __str__(self) -> str:
        return f"Asset(asset_id={self.asset_id}, kind={self.kind}, storage_ref={self.storage_ref})"

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


class AnnotationRecord(DatalakeDocument):
    """One atomic persisted annotation.

    Membership in annotation sets is maintained only by parent ``AnnotationSet.annotation_record_ids``.
    Records themselves do not store parent set ids, which allows the same atomic record to be reused
    across multiple sets.
    """

    def __str__(self) -> str:
        return f"AnnotationRecord(annotation_id={self.annotation_id}, kind={self.kind}, label={self.label})"

    annotation_id: Annotated[str, Indexed(unique=True)] = Field(default_factory=lambda: new_id("annotation"))
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
            "kind",
            "label",
            "source.type",
            "source.name",
            "subject.kind",
            "subject.id",
        ]


class AnnotationSet(DatalakeDocument):
    """Grouping/provenance boundary for annotation records.

    Membership in datums is maintained only by parent ``Datum.annotation_set_ids``. Sets themselves do
    not store parent datum ids, which allows the same set to be reused across multiple datums when needed.
    """

    def __str__(self) -> str:
        return f"AnnotationSet(annotation_set_id={self.annotation_set_id}, name={self.name}, records={len(self.annotation_record_ids)})"

    annotation_set_id: Annotated[str, Indexed(unique=True)] = Field(default_factory=lambda: new_id("annotation_set"))
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
        indexes = ["purpose", "source_type", "status"]


class Datum(DatalakeDocument):
    """Reusable unit of dataset membership."""

    def __str__(self) -> str:
        return f"Datum(datum_id={self.datum_id}, split={self.split}, assets={list(self.asset_refs.keys())})"

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


class DatasetVersion(DatalakeDocument):
    """Immutable dataset manifest over datum ids."""

    def __str__(self) -> str:
        return f"DatasetVersion(dataset={self.dataset_name}, version={self.version}, datums={len(self.manifest)})"

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

    def __str__(self) -> str:
        return f"ResolvedDatum(datum_id={self.datum.datum_id}, assets={len(self.assets)}, annotation_sets={len(self.annotation_sets)})"


class ResolvedDatasetVersion(BaseModel):
    """Resolved dataset view with all datums and their linked records."""

    dataset_version: DatasetVersion
    datums: list[ResolvedDatum] = Field(default_factory=list)

    def __str__(self) -> str:
        return f"ResolvedDatasetVersion(dataset={self.dataset_version.dataset_name}, version={self.dataset_version.version}, datums={len(self.datums)})"
