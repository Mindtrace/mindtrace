from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mindtrace.datalake.types import (
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    DatasetVersion,
    Datum,
    StorageRef,
)

TransferPolicy = Literal[
    "copy",
    "copy_if_missing",
    "metadata_only",
    "fail_if_missing_payload",
]


class ObjectPayloadDescriptor(BaseModel):
    asset_id: str
    storage_ref: StorageRef
    media_type: str
    size_bytes: int | None = None
    checksum: str | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetSyncBundle(BaseModel):
    dataset_version: DatasetVersion
    datums: list[Datum] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    annotation_sets: list[AnnotationSet] = Field(default_factory=list)
    annotation_records: list[AnnotationRecord] = Field(default_factory=list)
    annotation_schemas: list[AnnotationSchema] = Field(default_factory=list)
    payloads: list[ObjectPayloadDescriptor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetSyncImportRequest(BaseModel):
    bundle: DatasetSyncBundle
    transfer_policy: TransferPolicy = "copy_if_missing"
    origin_lake_id: str | None = None
    preserve_ids: bool = True
    mount_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps source registry mount names to target mount names for payload probes, uploads, and "
            "persisted StorageRef values. Unlisted mounts pass through unchanged."
        ),
    )

    @field_validator("mount_map")
    @classmethod
    def _validate_mount_map_entries(cls, v: dict[str, str]) -> dict[str, str]:
        for key, val in v.items():
            if not key or not val:
                raise ValueError("mount_map keys and target mount names must be non-empty strings")
        return v

    @model_validator(mode="after")
    def _validate_preserve_ids(self) -> DatasetSyncImportRequest:
        if not self.preserve_ids:
            raise ValueError(
                "preserve_ids=False is not supported yet; imports always preserve source identifiers. "
                "Omit preserve_ids or set it to True."
            )
        return self


class DatasetSyncPayloadPlan(BaseModel):
    asset_id: str
    source_storage_ref: StorageRef
    target_storage_ref: StorageRef
    target_exists: bool
    transfer_required: bool
    reason: str


class DatasetSyncImportPlan(BaseModel):
    dataset_name: str
    version: str
    transfer_policy: TransferPolicy
    payloads: list[DatasetSyncPayloadPlan] = Field(default_factory=list)
    missing_payload_count: int = 0
    transfer_required_count: int = 0
    ready_to_commit: bool = False


class DatasetSyncCommitResult(BaseModel):
    dataset_version: DatasetVersion
    created_assets: int = 0
    created_annotation_schemas: int = 0
    created_annotation_records: int = 0
    created_annotation_sets: int = 0
    created_datums: int = 0
    transferred_payloads: int = 0
    skipped_payloads: int = 0
