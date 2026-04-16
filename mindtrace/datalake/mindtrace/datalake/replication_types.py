from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from mindtrace.datalake.types import AnnotationRecord, AnnotationSchema, AnnotationSet, Asset, Datum

ReplicationMode = Literal["metadata_first"]
PayloadStatus = Literal["pending", "transferring", "uploaded", "verified", "failed"]


class ReplicatedAssetState(BaseModel):
    origin_lake_id: str
    origin_asset_id: str
    replication_mode: ReplicationMode = "metadata_first"
    payload_status: PayloadStatus = "pending"
    payload_available: bool = False
    payload_last_error: str | None = None
    payload_last_attempt_at: datetime | None = None
    payload_verified_at: datetime | None = None
    local_delete_eligible_at: datetime | None = None
    local_deleted_at: datetime | None = None


class ReplicationBatchRequest(BaseModel):
    assets: list[Asset] = Field(default_factory=list)
    annotation_schemas: list[AnnotationSchema] = Field(default_factory=list)
    annotation_sets: list[AnnotationSet] = Field(default_factory=list)
    annotation_records: list[AnnotationRecord] = Field(default_factory=list)
    datums: list[Datum] = Field(default_factory=list)
    origin_lake_id: str
    replication_mode: ReplicationMode = "metadata_first"
    mount_map: dict[str, str] = Field(default_factory=dict)

    @field_validator("mount_map")
    @classmethod
    def _validate_mount_map_entries(cls, v: dict[str, str]) -> dict[str, str]:
        for key, val in v.items():
            if not key or not val:
                raise ValueError("mount_map keys and target mount names must be non-empty strings")
        return v


class ReplicationBatchResult(BaseModel):
    created_assets: int = 0
    updated_assets: int = 0
    created_annotation_schemas: int = 0
    updated_annotation_schemas: int = 0
    created_annotation_sets: int = 0
    updated_annotation_sets: int = 0
    created_annotation_records: int = 0
    updated_annotation_records: int = 0
    created_datums: int = 0
    updated_datums: int = 0


class ReplicationStatusResult(BaseModel):
    asset_counts_by_payload_status: dict[PayloadStatus, int] = Field(default_factory=dict)
    pending_asset_ids: list[str] = Field(default_factory=list)
    failed_asset_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplicationReconcileRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    limit: int | None = None
    include_failed: bool = True
    mount_map: dict[str, str] = Field(default_factory=dict)

    @field_validator("mount_map")
    @classmethod
    def _validate_mount_map_entries(cls, v: dict[str, str]) -> dict[str, str]:
        for key, val in v.items():
            if not key or not val:
                raise ValueError("mount_map keys and target mount names must be non-empty strings")
        return v


class ReplicationReconcileResult(BaseModel):
    attempted_asset_ids: list[str] = Field(default_factory=list)
    verified_asset_ids: list[str] = Field(default_factory=list)
    failed_asset_ids: list[str] = Field(default_factory=list)
    skipped_asset_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplicationReclaimRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    limit: int | None = None
    require_verified_payload: bool = True


class ReplicationReclaimResult(BaseModel):
    attempted_asset_ids: list[str] = Field(default_factory=list)
    reclaimed_asset_ids: list[str] = Field(default_factory=list)
    failed_asset_ids: list[str] = Field(default_factory=list)
    skipped_asset_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
