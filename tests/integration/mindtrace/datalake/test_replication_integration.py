"""End-to-end one-way replication (metadata-first) with mixed registry backends.

Requires:

- Primary MongoDB at ``mongodb://localhost:27018`` (``mongodb`` service) for the source lake.
- Secondary MongoDB at ``mongodb://localhost:27019`` (``mongodb_secondary``) for the MinIO-backed target lake.
- MinIO / S3 configuration (``MINDTRACE_MINIO__*`` / ``config.ini``), same as other
  datalake integration tests that use MinIO.

The replication scenarios use **local** storage on the source (primary Mongo metadata)
and **MinIO** on the target (secondary Mongo metadata). ``MongoMindtraceODM`` routes
later document-model backends through Motor so multiple ``AsyncDatalake`` instances
can coexist in one process across two URIs.
"""

from __future__ import annotations

import asyncio
import hashlib
import socket
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pymongo import MongoClient

from mindtrace.datalake import AsyncDatalake, ReplicationManager
from mindtrace.datalake.replication import LOCAL_PAYLOAD_TOMBSTONE_STORAGE_REF
from mindtrace.datalake.replication_types import (
    ReplicationBatchRequest,
    ReplicationReclaimRequest,
    ReplicationReconcileRequest,
)
from mindtrace.registry import StoreLocationNotFound
from tests.integration.mindtrace.datalake.conftest import MONGO_URL, MONGO_URL_SECONDARY

_MOUNT_MAP_LOCAL_TO_MINIO = {"local": "minio"}
_HOPPER = Path(__file__).resolve().parents[3] / "resources" / "hopper.png"
_SENTINEL = object()


def _mongo_primary_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 27018), timeout=2.0):
            return True
    except OSError:
        return False


def _mongo_secondary_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 27019), timeout=2.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not (_mongo_primary_reachable() and _mongo_secondary_reachable()),
    reason="Replication integration tests require MongoDB on localhost:27018 and :27019",
)


async def _create_image_asset(datalake: AsyncDatalake, *, name: str) -> Any:
    """Seed a PNG asset the same way as other datalake integration tests (stable ``get_object`` size)."""
    image_bytes = _HOPPER.read_bytes()
    storage_ref = await datalake.put_object(name=name, obj=image_bytes, mount="local")
    digest = hashlib.sha256(image_bytes).hexdigest()
    return await datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=storage_ref,
        size_bytes=len(image_bytes),
        checksum=f"sha256:{digest}",
        metadata={"integration": "replication", "name": name},
        created_by="pytest-replication-integration",
    )


async def _drain_pending_payloads(
    manager: ReplicationManager,
    mount_map: dict[str, str],
    *,
    max_rounds: int = 100,
) -> None:
    for _ in range(max_rounds):
        st = await manager.status()
        pending = st.asset_counts_by_payload_status.get("pending", 0)
        if st.failed_asset_ids:
            details: list[str] = []
            for aid in st.failed_asset_ids[:5]:
                ta = await manager.target.get_asset(aid)
                rep = (ta.metadata or {}).get("replication") or {}
                details.append(f"{aid}: {rep.get('payload_last_error')!r}")
            raise AssertionError(
                f"Payload hydration failed for assets {st.failed_asset_ids!r}; samples: {'; '.join(details)}"
            )
        if pending == 0:
            return
        await manager.reconcile_pending_payloads(ReplicationReconcileRequest(mount_map=mount_map))
        await asyncio.sleep(0.05)
    st = await manager.status()
    raise AssertionError(f"Timed out with pending assets: {st.pending_asset_ids!r}")


async def _assert_target_bytes_match_source(
    *,
    source: AsyncDatalake,
    target: AsyncDatalake,
    asset_ids: list[str],
) -> None:
    for aid in asset_ids:
        src_asset = await source.get_asset(aid)
        tgt_asset = await target.get_asset(aid)
        assert ReplicationManager.get_payload_status(tgt_asset) == "verified"
        src_bytes = await source.get_object(src_asset.storage_ref)
        tgt_bytes = await target.get_object(tgt_asset.storage_ref)
        assert src_bytes == tgt_bytes, f"byte mismatch for asset {aid}"
        assert tgt_asset.checksum == src_asset.checksum


async def _replicate_asset_to_verified(
    *,
    source: AsyncDatalake,
    target: AsyncDatalake,
    manager: ReplicationManager,
    asset_name: str,
):
    asset = await _create_image_asset(source, name=asset_name)
    await manager.upsert_metadata_batch(
        ReplicationBatchRequest(
            assets=[asset],
            origin_lake_id=source.mongo_db_name,
            mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
        )
    )
    await manager.reconcile_pending_payloads(ReplicationReconcileRequest(mount_map=_MOUNT_MAP_LOCAL_TO_MINIO))
    await _drain_pending_payloads(manager, _MOUNT_MAP_LOCAL_TO_MINIO)
    target_asset = await target.get_asset(asset.asset_id)
    assert ReplicationManager.get_payload_status(target_asset) == "verified"
    return asset, target_asset


def test_mongodb_secondary_container_accept_connections() -> None:
    """Sanity-check the compose ``mongodb_secondary`` service used by the MinIO-on-secondary-Mongo fixture."""
    if not _mongo_secondary_reachable():
        pytest.skip("Secondary MongoDB not reachable at localhost:27019 (start tests/docker-compose.yml)")
    client = MongoClient(MONGO_URL_SECONDARY, serverSelectionTimeoutMS=5000)
    try:
        names = client.list_database_names()
    finally:
        client.close()
    assert "admin" in names


@pytest.mark.asyncio
async def test_replication_continuous_ingest_local_to_minio_separate_metadata_dbs(
    async_datalake: AsyncDatalake,
    async_datalake_minio_secondary_mongo: AsyncDatalake,
):
    """Producer and consumer tasks: ingest waves on source while replicating to MinIO target."""
    source = async_datalake
    target = async_datalake_minio_secondary_mongo

    assert source.mongo_db_uri == MONGO_URL
    assert target.mongo_db_uri == MONGO_URL_SECONDARY
    assert source.mongo_db_name != target.mongo_db_name
    assert source.store.default_mount == "local"
    assert target.store.default_mount == "minio"

    manager = ReplicationManager(source, target)
    work: asyncio.Queue[Any] = asyncio.Queue(maxsize=8)
    created_asset_ids: list[str] = []

    async def producer() -> None:
        for wave in range(4):
            wave_assets = []
            for i in range(2):
                name = f"replication/continuous/w{wave}_i{i}_{uuid4().hex}.png"
                asset = await _create_image_asset(source, name=name)
                wave_assets.append(asset)
                created_asset_ids.append(asset.asset_id)
            await work.put(wave_assets)
            await asyncio.to_thread(time.sleep, 0.02)
        await work.put(_SENTINEL)

    async def consumer() -> None:
        while True:
            item = await work.get()
            if item is _SENTINEL:
                break
            batch = ReplicationBatchRequest(
                assets=item,
                origin_lake_id=source.mongo_db_name,
                mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
            )
            await manager.upsert_metadata_batch(batch)
            await manager.reconcile_pending_payloads(ReplicationReconcileRequest(mount_map=_MOUNT_MAP_LOCAL_TO_MINIO))

    await asyncio.gather(producer(), consumer())
    await _drain_pending_payloads(manager, _MOUNT_MAP_LOCAL_TO_MINIO)

    ids = list(created_asset_ids)
    assert len(ids) == 8
    await _assert_target_bytes_match_source(source=source, target=target, asset_ids=ids)


@pytest.mark.asyncio
async def test_replication_concurrent_hydration_gather_local_to_minio(
    async_datalake: AsyncDatalake,
    async_datalake_minio_secondary_mongo: AsyncDatalake,
):
    """Concurrent ``hydrate_asset_payload`` calls (same loop) stress MinIO hydration paths."""
    source = async_datalake
    target = async_datalake_minio_secondary_mongo
    manager = ReplicationManager(source, target)

    assets = []
    for i in range(5):
        name = f"replication/parallel/{i}_{uuid4().hex}.png"
        assets.append(await _create_image_asset(source, name=name))

    await manager.upsert_metadata_batch(
        ReplicationBatchRequest(
            assets=assets,
            origin_lake_id=source.mongo_db_name,
            mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
        )
    )

    st0 = await manager.status()
    assert st0.asset_counts_by_payload_status.get("pending", 0) == len(assets)

    await asyncio.gather(
        *[manager.hydrate_asset_payload(a.asset_id, mount_map=_MOUNT_MAP_LOCAL_TO_MINIO) for a in assets]
    )

    await _drain_pending_payloads(manager, _MOUNT_MAP_LOCAL_TO_MINIO)
    await _assert_target_bytes_match_source(source=source, target=target, asset_ids=[a.asset_id for a in assets])


@pytest.mark.asyncio
async def test_replication_reupsert_preserves_verified_payload_state(
    async_datalake: AsyncDatalake,
    async_datalake_minio_secondary_mongo: AsyncDatalake,
):
    source = async_datalake
    target = async_datalake_minio_secondary_mongo
    manager = ReplicationManager(source, target)

    asset, verified_target_asset = await _replicate_asset_to_verified(
        source=source,
        target=target,
        manager=manager,
        asset_name=f"replication/reupsert/state_{uuid4().hex}.png",
    )
    verified_storage_ref = verified_target_asset.storage_ref
    verified_bytes = await target.get_object(verified_storage_ref)

    await manager.upsert_metadata_batch(
        ReplicationBatchRequest(
            assets=[asset],
            origin_lake_id=source.mongo_db_name,
            mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
        )
    )

    refreshed_target_asset = await target.get_asset(asset.asset_id)
    assert ReplicationManager.get_payload_status(refreshed_target_asset) == "verified"
    assert ReplicationManager.is_payload_available(refreshed_target_asset) is True
    assert refreshed_target_asset.storage_ref == verified_storage_ref
    assert await target.get_object(refreshed_target_asset.storage_ref) == verified_bytes


@pytest.mark.asyncio
async def test_replication_reconcile_after_reupsert_skips_verified_asset(
    async_datalake: AsyncDatalake,
    async_datalake_minio_secondary_mongo: AsyncDatalake,
):
    source = async_datalake
    target = async_datalake_minio_secondary_mongo
    manager = ReplicationManager(source, target)

    asset, _ = await _replicate_asset_to_verified(
        source=source,
        target=target,
        manager=manager,
        asset_name=f"replication/reupsert/reconcile_{uuid4().hex}.png",
    )

    await manager.upsert_metadata_batch(
        ReplicationBatchRequest(
            assets=[asset],
            origin_lake_id=source.mongo_db_name,
            mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
        )
    )

    reconcile_result = await manager.reconcile_pending_payloads(
        ReplicationReconcileRequest(asset_ids=[asset.asset_id], mount_map=_MOUNT_MAP_LOCAL_TO_MINIO)
    )

    assert reconcile_result.attempted_asset_ids == []
    assert reconcile_result.verified_asset_ids == []
    assert reconcile_result.failed_asset_ids == []
    assert reconcile_result.skipped_asset_ids == [asset.asset_id]


@pytest.mark.asyncio
async def test_replication_mark_local_delete_eligible_requires_verified_target_payload(
    async_datalake: AsyncDatalake,
    async_datalake_minio_secondary_mongo: AsyncDatalake,
):
    source = async_datalake
    target = async_datalake_minio_secondary_mongo
    manager = ReplicationManager(source, target)

    asset = await _create_image_asset(source, name=f"replication/reclaim/pending_{uuid4().hex}.png")
    await manager.upsert_metadata_batch(
        ReplicationBatchRequest(
            assets=[asset],
            origin_lake_id=source.mongo_db_name,
            mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
        )
    )

    target_asset = await target.get_asset(asset.asset_id)
    assert ReplicationManager.get_payload_status(target_asset) == "pending"

    with pytest.raises(RuntimeError, match="not delete-eligible until target payload is verified"):
        await manager.mark_local_delete_eligible(asset.asset_id)


@pytest.mark.asyncio
async def test_replication_reclaim_verified_payloads_tombstones_source_and_keeps_target_readable(
    async_datalake: AsyncDatalake,
    async_datalake_minio_secondary_mongo: AsyncDatalake,
):
    source = async_datalake
    target = async_datalake_minio_secondary_mongo
    manager = ReplicationManager(source, target)

    asset = await _create_image_asset(source, name=f"replication/reclaim/verified_{uuid4().hex}.png")
    source_bytes = await source.get_object(asset.storage_ref)

    await manager.upsert_metadata_batch(
        ReplicationBatchRequest(
            assets=[asset],
            origin_lake_id=source.mongo_db_name,
            mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
        )
    )
    await manager.reconcile_pending_payloads(ReplicationReconcileRequest(mount_map=_MOUNT_MAP_LOCAL_TO_MINIO))
    await _drain_pending_payloads(manager, _MOUNT_MAP_LOCAL_TO_MINIO)

    reclaim_result = await manager.reclaim_verified_payloads(
        ReplicationReclaimRequest(asset_ids=[asset.asset_id], limit=1)
    )

    assert reclaim_result.attempted_asset_ids == [asset.asset_id]
    assert reclaim_result.reclaimed_asset_ids == [asset.asset_id]
    assert reclaim_result.failed_asset_ids == []

    source_asset = await source.get_asset(asset.asset_id)
    assert source_asset.storage_ref == LOCAL_PAYLOAD_TOMBSTONE_STORAGE_REF
    assert ReplicationManager.is_local_deleted(source_asset) is True

    with pytest.raises(StoreLocationNotFound):
        await source.get_object(source_asset.storage_ref)

    target_asset = await target.get_asset(asset.asset_id)
    assert ReplicationManager.get_payload_status(target_asset) == "verified"
    target_bytes = await target.get_object(target_asset.storage_ref)
    assert target_bytes == source_bytes

    status = await manager.status()
    assert asset.asset_id in status.metadata["local_deleted_asset_ids"]


@pytest.mark.asyncio
async def test_replication_reclaim_is_idempotent_after_source_tombstoned(
    async_datalake: AsyncDatalake,
    async_datalake_minio_secondary_mongo: AsyncDatalake,
):
    source = async_datalake
    target = async_datalake_minio_secondary_mongo
    manager = ReplicationManager(source, target)

    asset, target_asset = await _replicate_asset_to_verified(
        source=source,
        target=target,
        manager=manager,
        asset_name=f"replication/reclaim/idempotent_{uuid4().hex}.png",
    )
    target_bytes = await target.get_object(target_asset.storage_ref)

    first = await manager.reclaim_verified_payloads(ReplicationReclaimRequest(asset_ids=[asset.asset_id], limit=1))
    second = await manager.reclaim_verified_payloads(ReplicationReclaimRequest(asset_ids=[asset.asset_id], limit=1))

    assert first.reclaimed_asset_ids == [asset.asset_id]
    assert second.attempted_asset_ids == []
    assert second.reclaimed_asset_ids == []
    assert second.failed_asset_ids == []
    assert second.skipped_asset_ids == [asset.asset_id]

    source_asset = await source.get_asset(asset.asset_id)
    assert source_asset.storage_ref == LOCAL_PAYLOAD_TOMBSTONE_STORAGE_REF
    assert ReplicationManager.is_local_deleted(source_asset) is True
    assert await target.get_object(target_asset.storage_ref) == target_bytes
