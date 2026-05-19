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

TargetObjectMatchPolicy = Literal["exists", "size", "checksum"]


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
            "persisted StorageRef values. On cross-lake imports, each distinct mount in bundled assets and "
            "payloads must resolve (after mapping) to a mount that exists on the target datalake. "
            "Unlisted mounts pass through unchanged when the same mount name exists on both lakes."
        ),
    )
    planning_batch_size: int = Field(
        default=500,
        ge=1,
        description="Number of payloads to group into each import-planning progress batch.",
    )
    planning_concurrency: int = Field(
        default=32,
        ge=1,
        description="Maximum concurrent target object-existence probes during import planning.",
    )
    transfer_batch_size: int = Field(
        default=100,
        ge=1,
        description="Number of payloads to group into each import-transfer progress batch.",
    )
    transfer_concurrency: int = Field(
        default=8,
        ge=1,
        description="Maximum concurrent payload transfers during import commit.",
    )
    commit_batch_size: int = Field(
        default=1000,
        ge=1,
        description="Number of metadata rows to group into each bulk commit batch per entity type.",
    )
    staged_payload_storage_refs: dict[str, StorageRef] | None = Field(
        default=None,
        description=(
            "When set, payload bytes for each asset_id are already stored on the target at the given "
            "StorageRef; the importer skips source get_object transfers. Used by import sessions and "
            "caller-orchestrated cross-lake sync when the target cannot read bundle source mounts."
        ),
    )
    greenfield_skip_target_object_probes: bool = Field(
        default=True,
        description=(
            "When True and importing a dataset version graph that does not yet exist on the target, "
            "skip per-payload ``object_exists`` probes for ``copy_if_missing`` (greenfield optimization). "
            "When False, preserve the legacy probe-all behavior."
        ),
    )
    greenfield_skip_target_metadata_probes: bool = Field(
        default=True,
        description=(
            "When True and importing a dataset version graph that does not yet exist on the target, "
            "skip per-row metadata existence probes during commit and rely on direct inserts / duplicate-key "
            "handling instead."
        ),
    )
    target_object_match_policy: TargetObjectMatchPolicy = Field(
        default="exists",
        description=(
            "How strongly to verify that a target payload already matches before ``copy_if_missing`` skips "
            "transfer: ``exists`` checks only object presence, ``size`` also compares content length when "
            "available, and ``checksum`` prefers checksum metadata when both sides expose one."
        ),
    )
    commit_progress_every_items: int = Field(
        default=100,
        ge=1,
        description="Emit committing progress at least every N examined metadata rows.",
    )
    commit_progress_every_seconds: float = Field(
        default=0.25,
        gt=0,
        description="Emit committing progress at least every N seconds while metadata commit is active.",
    )
    metadata_first: bool = Field(
        default=False,
        description=(
            "When True with distinct source/target datalakes, commit dataset graph rows with replication-style "
            "payload_state pending instead of transferring all bytes in-process. Requires Phase B hydration "
            "(e.g. library ``ReplicationManager(source, target).hydrate_asset_payload`` or staging flows)."
        ),
    )
    target_metadata_commit: bool = Field(
        default=False,
        description=(
            "When True, source and target must be the same AsyncDatalake (single-process target-side import): "
            "commit the dataset graph with replication-style payload_pending without transferring payloads. Used by "
            "``dataset_versions.import_session_commit_metadata`` plus caller uploads (``import_session_upload_payload``)."
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
        if self.metadata_first and self.target_metadata_commit:
            raise ValueError("Cannot set both metadata_first and target_metadata_commit on the same request.")
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
    total_payload_bytes: int | None = None
    transfer_required_bytes: int | None = None


class DatasetSyncProgress(BaseModel):
    phase: Literal["planning", "transferring", "committing", "complete", "failed"]
    batch_index: int = 0
    total_batches: int = 0
    completed_items: int = 0
    total_items: int = 0
    message: str = ""
    entity_kind: str | None = None
    phase_detail: str | None = None
    entity_completed_items: int | None = None
    entity_total_items: int | None = None
    skipped_items: int | None = None
    failed_items: int | None = None
    current_asset_id: str | None = None
    items_per_second: float | None = None
    bytes_completed: int | None = None
    bytes_total: int | None = None
    bytes_per_second: float | None = None


class DatasetSyncCommitResult(BaseModel):
    dataset_version: DatasetVersion
    created_assets: int = 0
    created_annotation_schemas: int = 0
    created_annotation_records: int = 0
    created_annotation_sets: int = 0
    created_datums: int = 0
    transferred_payloads: int = 0
    skipped_payloads: int = 0
