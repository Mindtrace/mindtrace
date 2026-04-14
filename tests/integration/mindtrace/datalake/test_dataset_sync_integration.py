"""Integration tests for dataset version export/import sync (``DatasetSyncManager``).

Requires MongoDB at ``mongodb://localhost:27018`` (see ``tests/integration/mindtrace/datalake/conftest.py``).

Tests that use ``async_datalake_minio`` additionally require MinIO/S3 configuration
(``MINDTRACE_MINIO__*`` / ``tests/integration/README.md``). Those tests are skipped
automatically when MinIO is unavailable via the shared registry ``s3_config`` fixtures.

Local ? MinIO cases pass ``mount_map={"local": "minio"}`` because the MinIO datalake uses
mount name ``minio`` while seeded source objects live on mount ``local``.
"""

from __future__ import annotations

import socket
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from mindtrace.datalake import AsyncDatalake, DatalakeService
from mindtrace.datalake.service_types import (
    DatasetSyncBundleOutput,
    DatasetSyncImportPlanOutput,
    ExportDatasetVersionInput,
)
from mindtrace.datalake.sync import DatasetSyncManager
from mindtrace.datalake.sync_types import DatasetSyncImportRequest

from tests.integration.mindtrace.datalake.conftest import MONGO_URL

_HOPPER = Path(__file__).resolve().parents[3] / "resources" / "hopper.png"

# Source integration lakes use default mount ``local``; ``async_datalake_minio`` uses ``minio``.
_MOUNT_MAP_LOCAL_TO_MINIO = {"local": "minio"}


def _mongo_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 27018), timeout=2.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _mongo_reachable(),
    reason="MongoDB required at mongodb://localhost:27018 for dataset sync integration tests",
)


async def _post_datalake_json(service: DatalakeService, path: str, payload: dict) -> dict:
    """POST to a ``DatalakeService`` route on the **current** asyncio loop (same as ``AsyncDatalake`` fixtures).

    ``starlette.testclient.TestClient`` runs the app on a different loop, which breaks Motor/Beanie
    when the service reuses a fixture-backed ``AsyncDatalake``.
    """
    async with AsyncClient(transport=ASGITransport(app=service.app), base_url="http://test") as client:
        response = await client.post(path, json=payload)
        if response.status_code != 200:
            raise AssertionError(f"{path} returned {response.status_code}: {response.text}")
        return response.json()


async def _seed_minimal_image_dataset(
    datalake: AsyncDatalake,
    *,
    dataset_name: str,
    version: str,
) -> None:
    image_bytes = _HOPPER.read_bytes()
    storage_ref = await datalake.put_object(
        name=f"sync/{dataset_name}/hopper.png",
        obj=image_bytes,
        mount="local",
    )
    asset = await datalake.create_asset(
        kind="image",
        media_type="image/png",
        storage_ref=storage_ref,
        size_bytes=len(image_bytes),
        metadata={"integration": "dataset-sync"},
        created_by="pytest-dataset-sync",
    )
    datum = await datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={},
        annotation_set_ids=[],
    )
    await datalake.create_dataset_version(
        dataset_name=dataset_name,
        version=version,
        manifest=[datum.datum_id],
        description="dataset sync integration",
        metadata={"suite": "dataset-sync"},
        created_by="pytest-dataset-sync",
    )


@pytest.mark.asyncio
async def test_dataset_sync_local_to_local_transfers_bytes(async_datalake: AsyncDatalake, async_datalake_secondary: AsyncDatalake):
    dataset_name = f"sync-local-{uuid4().hex[:10]}"
    version = "1.0.0"
    image_bytes = _HOPPER.read_bytes()
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)

    manager = DatasetSyncManager(async_datalake, async_datalake_secondary)
    result = await manager.sync_dataset_version(
        dataset_name,
        version,
        transfer_policy="copy_if_missing",
        origin_lake_id=async_datalake.mongo_db_name,
    )

    assert result.transferred_payloads >= 1
    remote = await async_datalake_secondary.get_dataset_version(dataset_name, version)
    assert remote.dataset_name == dataset_name
    datum = await async_datalake_secondary.get_datum(remote.manifest[0])
    image_asset_id = next(iter(datum.asset_refs.values()))
    asset = await async_datalake_secondary.get_asset(image_asset_id)
    loaded = await async_datalake_secondary.get_object(asset.storage_ref)
    assert loaded == image_bytes


@pytest.mark.asyncio
async def test_dataset_sync_local_to_minio_transfers_bytes(async_datalake: AsyncDatalake, async_datalake_minio: AsyncDatalake):
    dataset_name = f"sync-s3-{uuid4().hex[:10]}"
    version = "2.0.0"
    image_bytes = _HOPPER.read_bytes()
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)

    manager = DatasetSyncManager(async_datalake, async_datalake_minio)
    result = await manager.sync_dataset_version(
        dataset_name,
        version,
        transfer_policy="copy_if_missing",
        origin_lake_id=async_datalake.mongo_db_name,
        mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
    )

    assert result.transferred_payloads >= 1
    remote_asset_id = None
    remote = await async_datalake_minio.get_dataset_version(dataset_name, version)
    for datum_id in remote.manifest:
        datum = await async_datalake_minio.get_datum(datum_id)
        for aid in datum.asset_refs.values():
            remote_asset_id = aid
            break
    assert remote_asset_id is not None
    asset = await async_datalake_minio.get_asset(remote_asset_id)
    loaded = await async_datalake_minio.get_object(asset.storage_ref)
    assert loaded == image_bytes
    assert asset.storage_ref.mount == "minio"


@pytest.mark.asyncio
async def test_dataset_sync_local_to_minio_plan_uses_mapped_target_ref(
    async_datalake: AsyncDatalake, async_datalake_minio: AsyncDatalake
):
    dataset_name = f"sync-plan-s3-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    manager = DatasetSyncManager(async_datalake, async_datalake_minio)
    bundle = await manager.export_dataset_version(dataset_name, version)

    plan = await manager.plan_import(
        DatasetSyncImportRequest(
            bundle=bundle,
            transfer_policy="copy_if_missing",
            mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
        )
    )

    assert plan.payloads[0].source_storage_ref.mount == "local"
    assert plan.payloads[0].target_storage_ref.mount == "minio"


@pytest.mark.asyncio
async def test_dataset_sync_copy_if_missing_second_run_skips_transfer(
    async_datalake: AsyncDatalake,
    async_datalake_secondary: AsyncDatalake,
):
    dataset_name = f"sync-idem-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    manager = DatasetSyncManager(async_datalake, async_datalake_secondary)

    first = await manager.sync_dataset_version(dataset_name, version, transfer_policy="copy_if_missing")
    assert first.transferred_payloads >= 1

    second = await manager.sync_dataset_version(dataset_name, version, transfer_policy="copy_if_missing")
    assert second.transferred_payloads == 0
    assert second.skipped_payloads >= 1


@pytest.mark.asyncio
async def test_dataset_sync_export_prepare_commit_flow(async_datalake: AsyncDatalake, async_datalake_secondary: AsyncDatalake):
    dataset_name = f"sync-plan-{uuid4().hex[:10]}"
    version = "0.5.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    manager = DatasetSyncManager(async_datalake, async_datalake_secondary)
    bundle = await manager.export_dataset_version(dataset_name, version)

    assert bundle.dataset_version.dataset_name == dataset_name
    assert len(bundle.payloads) == 1

    plan = await manager.plan_import(
        DatasetSyncImportRequest(bundle=bundle, transfer_policy="copy_if_missing")
    )
    assert plan.transfer_required_count >= 1
    assert plan.ready_to_commit is True

    result = await manager.commit_import(
        DatasetSyncImportRequest(
            bundle=bundle,
            transfer_policy="copy_if_missing",
            origin_lake_id=async_datalake.mongo_db_name,
        )
    )
    assert result.transferred_payloads >= 1
    await async_datalake_secondary.get_dataset_version(dataset_name, version)


@pytest.mark.asyncio
async def test_dataset_sync_factory_and_metadata_only_same_lake(async_datalake: AsyncDatalake):
    dataset_name = f"sync-meta-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)

    helper = async_datalake.dataset_sync()
    assert isinstance(helper, DatasetSyncManager)
    assert helper.source is async_datalake and helper.target is async_datalake

    bundle = await helper.export_dataset_version(dataset_name, version)
    await helper.commit_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="metadata_only"))


@pytest.mark.asyncio
async def test_datalake_service_export_dataset_version(async_datalake: AsyncDatalake):
    dataset_name = f"sync-http-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)

    service = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=async_datalake.mongo_db_name,
        async_datalake=async_datalake,
        live_service=False,
        initialize_on_startup=False,
    )
    raw = await _post_datalake_json(
        service,
        "/dataset_versions.export",
        ExportDatasetVersionInput(dataset_name=dataset_name, version=version).model_dump(mode="json"),
    )
    out = DatasetSyncBundleOutput.model_validate(raw)

    assert out.bundle.dataset_version.dataset_name == dataset_name
    assert len(out.bundle.payloads) == 1
    assert out.bundle.payloads[0].storage_ref.mount == "local"


@pytest.mark.asyncio
async def test_dataset_sync_copy_policy_forces_transfer(async_datalake: AsyncDatalake, async_datalake_secondary: AsyncDatalake):
    dataset_name = f"sync-copy-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    manager = DatasetSyncManager(async_datalake, async_datalake_secondary)
    bundle = await manager.export_dataset_version(dataset_name, version)

    plan = await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="copy"))
    assert plan.payloads[0].transfer_required is True
    assert plan.payloads[0].reason == "policy_copy"


@pytest.mark.asyncio
async def test_datalake_service_import_prepare_honors_mount_map(
    async_datalake: AsyncDatalake, async_datalake_minio: AsyncDatalake
):
    dataset_name = f"sync-svc-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)

    export_svc = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=async_datalake.mongo_db_name,
        async_datalake=async_datalake,
        live_service=False,
        initialize_on_startup=False,
    )
    target_svc = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=async_datalake_minio.mongo_db_name,
        async_datalake=async_datalake_minio,
        live_service=False,
        initialize_on_startup=False,
    )

    bundle_raw = await _post_datalake_json(
        export_svc,
        "/dataset_versions.export",
        ExportDatasetVersionInput(dataset_name=dataset_name, version=version).model_dump(mode="json"),
    )
    bundle_out = DatasetSyncBundleOutput.model_validate(bundle_raw)
    request = DatasetSyncImportRequest(
        bundle=bundle_out.bundle,
        transfer_policy="copy_if_missing",
        mount_map=_MOUNT_MAP_LOCAL_TO_MINIO,
    )
    plan_raw = await _post_datalake_json(
        target_svc,
        "/dataset_versions.import_prepare",
        request.model_dump(mode="json"),
    )
    plan_out = DatasetSyncImportPlanOutput.model_validate(plan_raw)

    assert plan_out.plan.payloads[0].source_storage_ref.mount == "local"
    assert plan_out.plan.payloads[0].target_storage_ref.mount == "minio"
