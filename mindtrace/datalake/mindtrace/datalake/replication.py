from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

from mindtrace.database.core.exceptions import DocumentNotFoundError
from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.datalake.replication_types import (
    PayloadStatus,
    ReplicatedAssetState,
    ReplicationBatchRequest,
    ReplicationBatchResult,
    ReplicationReclaimRequest,
    ReplicationReclaimResult,
    ReplicationReconcileRequest,
    ReplicationReconcileResult,
    ReplicationStatusResult,
)
from mindtrace.datalake.types import AnnotationRecord, AnnotationSchema, AnnotationSet, Asset, Datum, StorageRef


def _apply_mount_map_to_storage_ref(storage_ref: StorageRef, mount_map: dict[str, str]) -> StorageRef:
    mapped = mount_map.get(storage_ref.mount)
    if mapped is None:
        return storage_ref
    return StorageRef(mount=mapped, name=storage_ref.name, version=storage_ref.version)


def _storage_refs_equivalent(a: StorageRef, b: StorageRef) -> bool:
    av = a.version if a.version is not None else "latest"
    bv = b.version if b.version is not None else "latest"
    return a.mount == b.mount and a.name == b.name and av == bv


def _head_object_size_bytes(meta: dict[str, Any]) -> int | None:
    for key in ("size_bytes", "size", "content_length", "ContentLength"):
        val = meta.get(key)
        if val is None:
            continue
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


LOCAL_PAYLOAD_TOMBSTONE_STORAGE_REF = StorageRef(
    mount="__local_payload_deleted__",
    name=".",
    version=None,
)


class ReplicationManager:
    """One-way source -> target replication (metadata-first: control plane before payloads).

    MVP-A implemented the control-plane foundation (placeholder assets + metadata upsert).
    MVP-B adds payload-state transitions and hydration using the direct-upload flow.
    """

    def __init__(self, source: AsyncDatalake, target: AsyncDatalake | None = None) -> None:
        self.source = source
        if target is None:
            self.target = source
        elif target is source:
            raise ValueError(
                "ReplicationManager requires distinct source and target when both are passed; "
                "pass a single datalake argument for target-only ingestion and status."
            )
        else:
            self.target = target

    @staticmethod
    def map_storage_ref_for_target(storage_ref: StorageRef, mount_map: dict[str, str]) -> StorageRef:
        return _apply_mount_map_to_storage_ref(storage_ref, mount_map)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def get_payload_status(asset: Asset) -> PayloadStatus | None:
        replication = (asset.metadata or {}).get("replication")
        if not isinstance(replication, dict):
            return None
        status = replication.get("payload_status")
        return status if isinstance(status, str) else None

    @staticmethod
    def is_payload_available(asset: Asset) -> bool:
        replication = (asset.metadata or {}).get("replication")
        if not isinstance(replication, dict):
            return False
        available = replication.get("payload_available")
        return bool(available)

    def build_asset_replication_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        origin_lake_id: str,
        origin_asset_id: str,
        replication_mode: str,
        payload_status: PayloadStatus = "pending",
    ) -> dict[str, Any]:
        merged = dict(metadata or {})

        origin = merged.get("origin")
        if not isinstance(origin, dict):
            origin = {}
        origin.setdefault("lake_id", origin_lake_id)
        origin.setdefault("asset_id", origin_asset_id)
        merged["origin"] = origin

        replication = merged.get("replication")
        if not isinstance(replication, dict):
            replication = {}
        state = ReplicatedAssetState(
            origin_lake_id=origin_lake_id,
            origin_asset_id=origin_asset_id,
            replication_mode=replication_mode,
            payload_status=payload_status,
            payload_available=payload_status == "verified",
            payload_last_error=replication.get("payload_last_error"),
            payload_last_attempt_at=replication.get("payload_last_attempt_at"),
            payload_verified_at=replication.get("payload_verified_at"),
            local_delete_eligible_at=replication.get("local_delete_eligible_at"),
            local_deleted_at=replication.get("local_deleted_at"),
        )
        merged["replication"] = state.model_dump(mode="json")
        return merged

    @staticmethod
    def _should_preserve_verified_payload(
        existing_asset: Asset, new_asset: Asset, mapped_storage_ref: StorageRef
    ) -> bool:
        if ReplicationManager.get_payload_status(existing_asset) != "verified":
            return False
        if not _storage_refs_equivalent(existing_asset.storage_ref, mapped_storage_ref):
            return False
        return existing_asset.checksum == new_asset.checksum and existing_asset.size_bytes == new_asset.size_bytes

    async def upsert_metadata_batch(self, request: ReplicationBatchRequest) -> ReplicationBatchResult:
        result = ReplicationBatchResult()

        for schema in request.annotation_schemas:
            if await self._annotation_schema_exists(schema.annotation_schema_id):
                await self._update_annotation_schema(schema, request.origin_lake_id)
                result.updated_annotation_schemas += 1
            else:
                await self.target.annotation_schema_database.insert(
                    AnnotationSchema.model_validate(
                        {
                            **schema.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                schema.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=schema.annotation_schema_id,
                                entity_kind="annotation_schema",
                            ),
                        }
                    )
                )
                result.created_annotation_schemas += 1

        for asset in request.assets:
            mapped_storage_ref = _apply_mount_map_to_storage_ref(asset.storage_ref, request.mount_map)
            existing_asset = None
            try:
                existing_asset = await self.target.get_asset(asset.asset_id)
            except DocumentNotFoundError:
                pass

            metadata_for_replication = dict(asset.metadata or {})
            payload_status: PayloadStatus = "pending"
            if existing_asset is not None and self._should_preserve_verified_payload(
                existing_asset, asset, mapped_storage_ref
            ):
                existing_replication = (existing_asset.metadata or {}).get("replication")
                if isinstance(existing_replication, dict):
                    metadata_for_replication["replication"] = dict(existing_replication)
                payload_status = "verified"

            replicated = Asset.model_validate(
                {
                    **asset.model_dump(),
                    "storage_ref": mapped_storage_ref.model_dump(),
                    "metadata": self.build_asset_replication_metadata(
                        metadata_for_replication,
                        origin_lake_id=request.origin_lake_id,
                        origin_asset_id=asset.asset_id,
                        replication_mode=request.replication_mode,
                        payload_status=payload_status,
                    ),
                }
            )
            if existing_asset is not None:
                await self._update_asset(replicated)
                result.updated_assets += 1
            else:
                await self.target.asset_database.insert(replicated)
                await self.target.ensure_primary_asset_alias(replicated)
                result.created_assets += 1

        for record in request.annotation_records:
            if await self._annotation_record_exists(record.annotation_id):
                await self._update_annotation_record(record, request.origin_lake_id)
                result.updated_annotation_records += 1
            else:
                await self.target.annotation_record_database.insert(
                    AnnotationRecord.model_validate(
                        {
                            **record.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                record.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=record.annotation_id,
                                entity_kind="annotation_record",
                            ),
                        }
                    )
                )
                result.created_annotation_records += 1

        for annotation_set in request.annotation_sets:
            if await self._annotation_set_exists(annotation_set.annotation_set_id):
                await self._update_annotation_set(annotation_set, request.origin_lake_id)
                result.updated_annotation_sets += 1
            else:
                await self.target.annotation_set_database.insert(
                    AnnotationSet.model_validate(
                        {
                            **annotation_set.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                annotation_set.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=annotation_set.annotation_set_id,
                                entity_kind="annotation_set",
                            ),
                        }
                    )
                )
                result.created_annotation_sets += 1

        for datum in request.datums:
            if await self._datum_exists(datum.datum_id):
                await self._update_datum(datum, request.origin_lake_id)
                result.updated_datums += 1
            else:
                await self.target.datum_database.insert(
                    Datum.model_validate(
                        {
                            **datum.model_dump(),
                            "metadata": self._merge_origin_metadata(
                                datum.metadata,
                                origin_lake_id=request.origin_lake_id,
                                entity_id=datum.datum_id,
                                entity_kind="datum",
                            ),
                        }
                    )
                )
                result.created_datums += 1

        return result

    async def hydrate_asset_payload(self, asset_id: str, *, mount_map: dict[str, str] | None = None) -> Asset:
        target_asset = await self.target.get_asset(asset_id)
        source_asset_id = self._get_origin_asset_id(target_asset)
        if source_asset_id is None:
            source_asset_id = asset_id
        source_asset = await self.source.get_asset(source_asset_id)
        source_payload_view = Asset.model_validate(source_asset.model_dump(mode="python"))

        await self._set_asset_replication_state(
            target_asset,
            payload_status="transferring",
            payload_last_attempt_at=self._utc_now(),
            payload_last_error=None,
        )

        try:
            completed_ref = await self._transfer_payload(source_payload_view, mount_map or {})
            await self._verify_transferred_payload(source_payload_view, completed_ref)
            refreshed_target_asset = await self.target.get_asset(asset_id)
            refreshed_target_asset.storage_ref = completed_ref
            await self._set_asset_replication_state(
                refreshed_target_asset,
                payload_status="verified",
                payload_available=True,
                payload_last_attempt_at=self._utc_now(),
                payload_verified_at=self._utc_now(),
                payload_last_error=None,
            )
            return refreshed_target_asset
        except Exception as exc:
            failed_asset = await self.target.get_asset(asset_id)
            await self._set_asset_replication_state(
                failed_asset,
                payload_status="failed",
                payload_available=False,
                payload_last_attempt_at=self._utc_now(),
                payload_last_error=str(exc),
            )
            raise

    async def reconcile_pending_payloads(
        self, request: ReplicationReconcileRequest | None = None
    ) -> ReplicationReconcileResult:
        request = request or ReplicationReconcileRequest()
        assets = await self.target.asset_database.find({})
        attempted_asset_ids: list[str] = []
        verified_asset_ids: list[str] = []
        failed_asset_ids: list[str] = []
        skipped_asset_ids: list[str] = []

        candidate_ids = set(request.asset_ids)
        processed = 0
        for asset in assets:
            if candidate_ids and asset.asset_id not in candidate_ids:
                continue
            status = self.get_payload_status(asset)
            if status not in {"pending", "failed"}:
                skipped_asset_ids.append(asset.asset_id)
                continue
            if status == "failed" and not request.include_failed:
                skipped_asset_ids.append(asset.asset_id)
                continue
            attempted_asset_ids.append(asset.asset_id)
            try:
                await self.hydrate_asset_payload(asset.asset_id, mount_map=request.mount_map)
                verified_asset_ids.append(asset.asset_id)
            except Exception:
                failed_asset_ids.append(asset.asset_id)
            processed += 1
            if request.limit is not None and processed >= request.limit:
                break

        return ReplicationReconcileResult(
            attempted_asset_ids=attempted_asset_ids,
            verified_asset_ids=verified_asset_ids,
            failed_asset_ids=failed_asset_ids,
            skipped_asset_ids=skipped_asset_ids,
        )

    async def mark_local_delete_eligible(self, asset_id: str, *, when: datetime | None = None) -> Asset:
        source_asset = await self.source.get_asset(asset_id)
        target_asset = await self._get_target_asset_for_source_asset(asset_id)
        if target_asset is None:
            raise RuntimeError(f"No replicated target asset found for source asset {asset_id}")
        if self.get_payload_status(target_asset) != "verified":
            raise RuntimeError(f"Source asset {asset_id} is not delete-eligible until target payload is verified")
        await self._set_source_asset_reclaim_state(
            source_asset,
            local_delete_eligible_at=when or self._utc_now(),
            payload_last_error=None,
        )
        return source_asset

    async def delete_local_payload(self, asset_id: str) -> Asset:
        source_asset = await self.source.get_asset(asset_id)
        if self.is_local_deleted(source_asset):
            return source_asset
        if not self.is_local_delete_eligible(source_asset):
            raise RuntimeError(f"Source asset {asset_id} is not delete-eligible")
        storage_ref = source_asset.storage_ref
        key = self.source.store.build_key(storage_ref.mount, storage_ref.name, storage_ref.version)
        version = storage_ref.version if storage_ref.version is not None else "latest"
        self.source.store.delete(key, version=version)
        source_asset.storage_ref = LOCAL_PAYLOAD_TOMBSTONE_STORAGE_REF
        await self._set_source_asset_reclaim_state(
            source_asset,
            local_deleted_at=self._utc_now(),
            payload_available=False,
            payload_last_error=None,
        )
        return source_asset

    async def reclaim_verified_payloads(
        self, request: ReplicationReclaimRequest | None = None
    ) -> ReplicationReclaimResult:
        request = request or ReplicationReclaimRequest()
        assets = await self.source.asset_database.find({})
        attempted_asset_ids: list[str] = []
        reclaimed_asset_ids: list[str] = []
        failed_asset_ids: list[str] = []
        skipped_asset_ids: list[str] = []

        candidate_ids = set(request.asset_ids)
        processed = 0
        for asset in assets:
            if candidate_ids and asset.asset_id not in candidate_ids:
                continue
            if self.is_local_deleted(asset):
                skipped_asset_ids.append(asset.asset_id)
                continue
            if request.require_verified_payload and not await self._is_remote_payload_verified_for_source_asset(
                asset.asset_id
            ):
                skipped_asset_ids.append(asset.asset_id)
                continue
            attempted_asset_ids.append(asset.asset_id)
            try:
                if not self.is_local_delete_eligible(asset):
                    await self.mark_local_delete_eligible(asset.asset_id)
                await self.delete_local_payload(asset.asset_id)
                reclaimed_asset_ids.append(asset.asset_id)
            except Exception:
                failed_asset_ids.append(asset.asset_id)
            processed += 1
            if request.limit is not None and processed >= request.limit:
                break

        return ReplicationReclaimResult(
            attempted_asset_ids=attempted_asset_ids,
            reclaimed_asset_ids=reclaimed_asset_ids,
            failed_asset_ids=failed_asset_ids,
            skipped_asset_ids=skipped_asset_ids,
        )

    async def status(self) -> ReplicationStatusResult:
        assets = await self.target.asset_database.find({})
        counts: dict[PayloadStatus, int] = {
            "pending": 0,
            "transferring": 0,
            "uploaded": 0,
            "verified": 0,
            "failed": 0,
        }
        pending_asset_ids: list[str] = []
        failed_asset_ids: list[str] = []
        local_delete_eligible_ids: list[str] = []
        local_deleted_ids: list[str] = []
        for asset in assets:
            status = self.get_payload_status(asset)
            if status is None or status not in counts:
                continue
            counts[status] += 1
            if status == "pending":
                pending_asset_ids.append(asset.asset_id)
            elif status == "failed":
                failed_asset_ids.append(asset.asset_id)
        source_assets = (
            await self.source.asset_database.find({}) if getattr(self.source, "asset_database", None) else []
        )
        for asset in source_assets:
            if self.is_local_delete_eligible(asset):
                local_delete_eligible_ids.append(asset.asset_id)
            if self.is_local_deleted(asset):
                local_deleted_ids.append(asset.asset_id)
        return ReplicationStatusResult(
            asset_counts_by_payload_status=counts,
            pending_asset_ids=pending_asset_ids,
            failed_asset_ids=failed_asset_ids,
            metadata={
                "local_delete_eligible_asset_ids": local_delete_eligible_ids,
                "local_deleted_asset_ids": local_deleted_ids,
            },
        )

    @staticmethod
    def is_local_delete_eligible(asset: Asset) -> bool:
        replication = (asset.metadata or {}).get("replication")
        if not isinstance(replication, dict):
            return False
        return replication.get("local_delete_eligible_at") is not None and replication.get("local_deleted_at") is None

    @staticmethod
    def is_local_deleted(asset: Asset) -> bool:
        replication = (asset.metadata or {}).get("replication")
        if not isinstance(replication, dict):
            return False
        return replication.get("local_deleted_at") is not None

    def _merge_origin_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        origin_lake_id: str,
        entity_id: str,
        entity_kind: str,
    ) -> dict[str, Any]:
        merged = dict(metadata or {})
        origin = merged.get("origin")
        if not isinstance(origin, dict):
            origin = {}
        origin.setdefault("lake_id", origin_lake_id)
        origin.setdefault("entity_id", entity_id)
        origin.setdefault("entity_kind", entity_kind)
        merged["origin"] = origin
        return merged

    async def _set_asset_replication_state(
        self,
        asset: Asset,
        *,
        payload_status: PayloadStatus,
        payload_available: bool | None = None,
        payload_last_attempt_at: datetime | None = None,
        payload_verified_at: datetime | None = None,
        payload_last_error: str | None = None,
    ) -> None:
        metadata = dict(asset.metadata or {})
        origin = metadata.get("origin")
        if not isinstance(origin, dict):
            origin = {}
        origin_lake_id = origin.get("lake_id") or self.source.mongo_db_name
        origin_asset_id = origin.get("asset_id") or asset.asset_id
        replication = metadata.get("replication")
        if not isinstance(replication, dict):
            replication = {}
        state = ReplicatedAssetState(
            origin_lake_id=origin_lake_id,
            origin_asset_id=origin_asset_id,
            replication_mode=replication.get("replication_mode", "metadata_first"),
            payload_status=payload_status,
            payload_available=(payload_status == "verified") if payload_available is None else payload_available,
            payload_last_error=payload_last_error,
            payload_last_attempt_at=payload_last_attempt_at or replication.get("payload_last_attempt_at"),
            payload_verified_at=payload_verified_at or replication.get("payload_verified_at"),
            local_delete_eligible_at=replication.get("local_delete_eligible_at"),
            local_deleted_at=replication.get("local_deleted_at"),
        )
        metadata["origin"] = origin
        metadata["replication"] = state.model_dump(mode="json")
        asset.metadata = metadata
        await self._update_asset(asset)

    async def _set_source_asset_reclaim_state(
        self,
        asset: Asset,
        *,
        local_delete_eligible_at: datetime | None = None,
        local_deleted_at: datetime | None = None,
        payload_available: bool | None = None,
        payload_last_error: str | None = None,
    ) -> None:
        metadata = dict(asset.metadata or {})
        origin = metadata.get("origin")
        if not isinstance(origin, dict):
            origin = {}
        origin.setdefault("lake_id", self.source.mongo_db_name)
        origin.setdefault("asset_id", asset.asset_id)
        metadata["origin"] = origin

        base = metadata.get("replication")
        if not isinstance(base, dict):
            base = {}
        replication_was_empty = len(base) == 0
        merged: dict[str, Any] = dict(base)

        if local_delete_eligible_at is not None:
            merged["local_delete_eligible_at"] = local_delete_eligible_at
        if local_deleted_at is not None:
            merged["local_deleted_at"] = local_deleted_at
        if payload_available is not None:
            merged["payload_available"] = payload_available
        merged["payload_last_error"] = payload_last_error

        merged.setdefault(
            "origin_lake_id", merged.get("origin_lake_id") or origin.get("lake_id") or self.source.mongo_db_name
        )
        merged.setdefault("origin_asset_id", merged.get("origin_asset_id") or origin.get("asset_id") or asset.asset_id)
        merged.setdefault("replication_mode", merged.get("replication_mode") or "metadata_first")

        if merged.get("payload_status") is None:
            if replication_was_empty:
                merged["payload_status"] = "verified"
                merged.setdefault("payload_available", True)
            else:
                raise ValueError(
                    f"Cannot merge reclaim metadata for asset {asset.asset_id!r}: replication.payload_status is missing"
                )

        state = ReplicatedAssetState.model_validate(merged)
        metadata["replication"] = state.model_dump(mode="json")
        asset.metadata = metadata
        existing = await self.source.asset_database.find({"asset_id": asset.asset_id})
        if not existing:
            await self.source.asset_database.insert(asset)
            await self.source.ensure_primary_asset_alias(asset)
            return
        current = existing[0]
        current.storage_ref = asset.storage_ref
        current.checksum = asset.checksum
        current.size_bytes = asset.size_bytes
        current.media_type = asset.media_type
        current.kind = asset.kind
        current.metadata = asset.metadata
        current.updated_at = asset.updated_at
        await self.source.asset_database.update(current)

    async def _transfer_payload(self, source_asset: Asset, mount_map: dict[str, str]) -> StorageRef:
        data = await self.source.get_object(source_asset.storage_ref)
        if source_asset.size_bytes is not None and len(data) != source_asset.size_bytes:
            raise ValueError(
                f"Source read size mismatch for asset {source_asset.asset_id}: "
                f"expected {source_asset.size_bytes} bytes, read {len(data)}"
            )
        target_write_ref = _apply_mount_map_to_storage_ref(source_asset.storage_ref, mount_map)
        session = await self.target.create_object_upload_session(
            name=target_write_ref.name,
            mount=target_write_ref.mount,
            version=target_write_ref.version,
            metadata=source_asset.metadata,
            on_conflict="skip",
            content_type=source_asset.media_type or self._guess_content_type(source_asset.storage_ref.name),
        )
        if session.upload_method == "local_path":
            if not session.upload_path:
                raise ValueError(f"Upload session {session.upload_session_id} is missing upload_path")
            upload_path = Path(session.upload_path)
            upload_path.parent.mkdir(parents=True, exist_ok=True)
            upload_path.write_bytes(data)
        elif session.upload_method == "presigned_url":
            if not session.upload_url:
                raise ValueError(f"Upload session {session.upload_session_id} is missing upload_url")
            req = urllib_request.Request(session.upload_url, data=data, method="PUT")
            for key, value in session.upload_headers.items():
                req.add_header(key, value)
            with urllib_request.urlopen(req) as response:
                if response.status >= 400:
                    raise RuntimeError(f"Presigned upload failed with status {response.status}")
        else:
            raise ValueError(f"Unsupported upload method: {session.upload_method}")
        completed = await self.target.complete_object_upload_session(
            session.upload_session_id,
            finalize_token=session.finalize_token,
        )
        if completed.storage_ref is None:
            raise RuntimeError(f"Upload session {session.upload_session_id} did not produce a storage_ref")
        return completed.storage_ref

    async def _verify_transferred_payload(self, source_asset: Asset, target_ref: StorageRef) -> None:
        source_bytes = await self.source.get_object(source_asset.storage_ref)
        head = await self.target.head_object(target_ref)
        remote_size = _head_object_size_bytes(head)
        if remote_size is not None and remote_size != len(source_bytes):
            raise RuntimeError(
                f"Post-upload size mismatch for asset {source_asset.asset_id}: "
                f"target head reports {remote_size} bytes, transferred {len(source_bytes)}"
            )
        if source_asset.checksum and not self._payload_checksum_matches(source_bytes, source_asset.checksum):
            raise RuntimeError(f"Post-upload checksum mismatch for asset {source_asset.asset_id}")

    def _payload_checksum_matches(self, data: bytes, declared: str) -> bool:
        declared_stripped = declared.strip()
        lowered = declared_stripped.lower()
        if ":" in lowered:
            algo, _, digest = lowered.partition(":")
            digest = digest.strip()
            algo = algo.strip()
            if algo == "sha256":
                return hashlib.sha256(data).hexdigest() == digest
            if algo == "md5":
                return hashlib.md5(data).hexdigest() == digest
            raise ValueError(f"Unsupported checksum algorithm in payload descriptor: {algo!r}")
        hex_body = lowered.replace("-", "")
        if len(hex_body) == 64 and set(hex_body) <= set("0123456789abcdef"):
            return hashlib.sha256(data).hexdigest() == hex_body
        if len(hex_body) == 32 and set(hex_body) <= set("0123456789abcdef"):
            return hashlib.md5(data).hexdigest() == hex_body
        raise ValueError(f"Unrecognized payload checksum format: {declared_stripped!r}")

    def _guess_content_type(self, name: str) -> str:
        guessed, _ = mimetypes.guess_type(name)
        return guessed or "application/octet-stream"

    def _get_origin_asset_id(self, asset: Asset) -> str | None:
        origin = (asset.metadata or {}).get("origin")
        if not isinstance(origin, dict):
            return None
        value = origin.get("asset_id")
        return value if isinstance(value, str) else None

    async def _get_target_asset_for_source_asset(self, source_asset_id: str) -> Asset | None:
        try:
            return await self.target.get_asset(source_asset_id)
        except DocumentNotFoundError:
            pass

        origin_asset_filter: dict[str, Any] = {"metadata.origin.asset_id": source_asset_id}
        source_lake_id = getattr(self.source, "mongo_db_name", None)
        if isinstance(source_lake_id, str) and source_lake_id:
            matches = await self.target.asset_database.find(
                {**origin_asset_filter, "metadata.origin.lake_id": source_lake_id}
            )
        else:
            matches = await self.target.asset_database.find(origin_asset_filter)

        if len(matches) > 1:
            raise RuntimeError(
                f"Ambiguous replication target lookup for source asset {source_asset_id!r}: "
                f"found {len(matches)} target assets for origin filter"
            )
        if len(matches) == 1:
            return matches[0]

        if isinstance(source_lake_id, str) and source_lake_id:
            loose = await self.target.asset_database.find(origin_asset_filter)
            if len(loose) > 1:
                raise RuntimeError(
                    f"Ambiguous replication target lookup for source asset {source_asset_id!r}: "
                    f"found {len(loose)} target assets for origin asset id only"
                )
            if len(loose) == 1:
                return loose[0]

        return None

    async def _is_remote_payload_verified_for_source_asset(self, source_asset_id: str) -> bool:
        asset = await self._get_target_asset_for_source_asset(source_asset_id)
        if asset is None:
            return False
        return self.get_payload_status(asset) == "verified"

    async def _update_asset(self, new_asset: Asset) -> None:
        existing = await self.target.asset_database.find({"asset_id": new_asset.asset_id})
        if not existing:
            await self.target.asset_database.insert(new_asset)
            await self.target.ensure_primary_asset_alias(new_asset)
            return
        current = existing[0]
        current.storage_ref = new_asset.storage_ref
        current.checksum = new_asset.checksum
        current.size_bytes = new_asset.size_bytes
        current.media_type = new_asset.media_type
        current.kind = new_asset.kind
        current.metadata = new_asset.metadata
        current.updated_at = new_asset.updated_at
        await self.target.asset_database.update(current)

    async def _update_annotation_schema(self, schema: AnnotationSchema, origin_lake_id: str) -> None:
        existing = await self.target.annotation_schema_database.find(
            {"annotation_schema_id": schema.annotation_schema_id}
        )
        if not existing:
            await self.target.annotation_schema_database.insert(schema)
            return
        current = existing[0]
        current.name = schema.name
        current.version = schema.version
        current.task_type = schema.task_type
        current.allowed_annotation_kinds = schema.allowed_annotation_kinds
        current.labels = schema.labels
        current.allow_scores = schema.allow_scores
        current.required_attributes = schema.required_attributes
        current.optional_attributes = schema.optional_attributes
        current.allow_additional_attributes = schema.allow_additional_attributes
        current.metadata = self._merge_origin_metadata(
            schema.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=schema.annotation_schema_id,
            entity_kind="annotation_schema",
        )
        current.updated_at = schema.updated_at
        await self.target.annotation_schema_database.update(current)

    async def _update_annotation_record(self, record: AnnotationRecord, origin_lake_id: str) -> None:
        existing = await self.target.annotation_record_database.find({"annotation_id": record.annotation_id})
        if not existing:
            await self.target.annotation_record_database.insert(record)
            return
        current = existing[0]
        current.subject = record.subject
        current.kind = record.kind
        current.label = record.label
        current.label_id = record.label_id
        current.score = record.score
        current.source = record.source
        current.geometry = record.geometry
        current.attributes = record.attributes
        current.metadata = self._merge_origin_metadata(
            record.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=record.annotation_id,
            entity_kind="annotation_record",
        )
        current.updated_at = record.updated_at
        await self.target.annotation_record_database.update(current)

    async def _update_annotation_set(self, annotation_set: AnnotationSet, origin_lake_id: str) -> None:
        existing = await self.target.annotation_set_database.find(
            {"annotation_set_id": annotation_set.annotation_set_id}
        )
        if not existing:
            await self.target.annotation_set_database.insert(annotation_set)
            return
        current = existing[0]
        current.name = annotation_set.name
        current.purpose = annotation_set.purpose
        current.source_type = annotation_set.source_type
        current.status = annotation_set.status
        current.annotation_schema_id = annotation_set.annotation_schema_id
        current.annotation_record_ids = annotation_set.annotation_record_ids
        current.metadata = self._merge_origin_metadata(
            annotation_set.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=annotation_set.annotation_set_id,
            entity_kind="annotation_set",
        )
        current.updated_at = annotation_set.updated_at
        await self.target.annotation_set_database.update(current)

    async def _update_datum(self, datum: Datum, origin_lake_id: str) -> None:
        existing = await self.target.datum_database.find({"datum_id": datum.datum_id})
        if not existing:
            await self.target.datum_database.insert(datum)
            return
        current = existing[0]
        current.asset_refs = datum.asset_refs
        current.split = datum.split
        current.annotation_set_ids = datum.annotation_set_ids
        current.metadata = self._merge_origin_metadata(
            datum.metadata,
            origin_lake_id=origin_lake_id,
            entity_id=datum.datum_id,
            entity_kind="datum",
        )
        current.updated_at = datum.updated_at
        await self.target.datum_database.update(current)

    async def _asset_exists(self, asset_id: str) -> bool:
        try:
            await self.target.get_asset(asset_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _annotation_schema_exists(self, annotation_schema_id: str) -> bool:
        try:
            await self.target.get_annotation_schema(annotation_schema_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _annotation_record_exists(self, annotation_id: str) -> bool:
        try:
            await self.target.get_annotation_record(annotation_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _annotation_set_exists(self, annotation_set_id: str) -> bool:
        try:
            await self.target.get_annotation_set(annotation_set_id)
            return True
        except DocumentNotFoundError:
            return False

    async def _datum_exists(self, datum_id: str) -> bool:
        try:
            await self.target.get_datum(datum_id)
            return True
        except DocumentNotFoundError:
            return False
