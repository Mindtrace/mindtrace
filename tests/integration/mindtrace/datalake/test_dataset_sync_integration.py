"""Integration tests for dataset version export/import sync (``DatasetSyncManager``).

Requires MongoDB at ``mongodb://localhost:27018`` (see ``tests/integration/mindtrace/datalake/conftest.py``).

Tests that use ``async_datalake_minio`` additionally require MinIO/S3 configuration
(``MINDTRACE_MINIO__*`` / ``tests/integration/README.md``). Those tests are skipped
automatically when MinIO is unavailable via the shared registry ``s3_config`` fixtures.

Local ? MinIO cases pass ``mount_map={"local": "minio"}`` because the MinIO datalake uses
mount name ``minio`` while seeded source objects live on mount ``local``.
"""

from __future__ import annotations

import asyncio
import hashlib
import socket
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from mindtrace.datalake import AsyncDatalake, DatalakeDirectUploadClient, DatalakeService
from mindtrace.datalake.service_types import (
    DatasetSyncBundleOutput,
    DatasetSyncCommitResultOutput,
    DatasetSyncImportPlanOutput,
    ExportDatasetVersionInput,
)
from mindtrace.datalake.sync import DatasetSyncManager
from mindtrace.datalake.sync_types import DatasetSyncBundle, DatasetSyncImportRequest
from mindtrace.datalake.types import AnnotationLabelDefinition

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


async def _seed_image_dataset_with_bbox_annotation(
    datalake: AsyncDatalake,
    *,
    dataset_name: str,
    version: str,
) -> None:
    image_bytes = _HOPPER.read_bytes()
    digest = hashlib.sha256(image_bytes).hexdigest()
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
        checksum=f"sha256:{digest}",
        metadata={"integration": "dataset-sync-annotated"},
        created_by="pytest-dataset-sync",
    )
    datum = await datalake.create_datum(
        asset_refs={"image": asset.asset_id},
        split="train",
        metadata={},
        annotation_set_ids=[],
    )
    schema = await datalake.create_annotation_schema(
        name=f"sync-schema-{dataset_name}",
        version="1.0.0",
        task_type="detection",
        allowed_annotation_kinds=["bbox"],
        labels=[AnnotationLabelDefinition(name="hopper", id=1)],
        required_attributes=["quality"],
        created_by="pytest-dataset-sync",
    )
    ann_set = await datalake.create_annotation_set(
        name="gt",
        purpose="ground_truth",
        source_type="human",
        datum_id=datum.datum_id,
        annotation_schema_id=schema.annotation_schema_id,
        created_by="pytest-dataset-sync",
    )
    await datalake.add_annotation_records(
        ann_set.annotation_set_id,
        [
            {
                "kind": "bbox",
                "label": "hopper",
                "label_id": 1,
                "source": {"type": "human", "name": "pytest-dataset-sync"},
                "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                "attributes": {"quality": "high"},
            }
        ],
    )
    await datalake.create_dataset_version(
        dataset_name=dataset_name,
        version=version,
        manifest=[datum.datum_id],
        description="dataset sync integration (annotated)",
        metadata={"suite": "dataset-sync-annotated"},
        created_by="pytest-dataset-sync",
    )


async def _delete_dataset_graph_mongo_only(lake: AsyncDatalake, bundle: DatasetSyncBundle) -> None:
    """Remove dataset graph rows while leaving registry objects (for ``metadata_only`` replay)."""
    dv = bundle.dataset_version
    await lake.dataset_version_database.delete(dv.id)
    for datum in bundle.datums:
        d = await lake.get_datum(datum.datum_id)
        await lake.datum_database.delete(d.id)
    for ann_id in [r.annotation_id for r in bundle.annotation_records]:
        rec = await lake.get_annotation_record(ann_id)
        await lake.annotation_record_database.delete(rec.id)
    for sid in [s.annotation_set_id for s in bundle.annotation_sets]:
        sdoc = await lake.get_annotation_set(sid)
        await lake.annotation_set_database.delete(sdoc.id)
    for schema in bundle.annotation_schemas:
        sch = await lake.get_annotation_schema(schema.annotation_schema_id)
        await lake.annotation_schema_database.delete(sch.id)
    for asset in bundle.assets:
        a = await lake.get_asset(asset.asset_id)
        await lake.asset_database.delete(a.id)


@pytest.mark.asyncio
async def test_dataset_sync_metadata_only_restores_annotation_graph_same_lake(async_datalake: AsyncDatalake):
    """Replay bundle with annotations on one lake (avoids Beanie single-DB binding across two ``AsyncDatalake`` fixtures)."""
    dataset_name = f"sync-ann-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_image_dataset_with_bbox_annotation(async_datalake, dataset_name=dataset_name, version=version)

    manager = DatasetSyncManager(async_datalake, async_datalake)
    bundle = await manager.export_dataset_version(dataset_name, version)
    assert len(bundle.annotation_schemas) >= 1
    assert len(bundle.annotation_sets) >= 1
    assert len(bundle.annotation_records) >= 1

    await _delete_dataset_graph_mongo_only(async_datalake, bundle)

    result = await manager.commit_import(
        DatasetSyncImportRequest(
            bundle=bundle,
            transfer_policy="metadata_only",
            origin_lake_id=async_datalake.mongo_db_name,
        )
    )
    assert result.transferred_payloads == 0
    assert result.skipped_payloads >= 1
    assert result.created_annotation_schemas >= 1
    assert result.created_annotation_sets >= 1
    assert result.created_annotation_records >= 1
    assert result.created_datums >= 1

    remote = await async_datalake.get_dataset_version(dataset_name, version)
    datum = await async_datalake.get_datum(remote.manifest[0])
    assert datum.annotation_set_ids
    ann_set_id = datum.annotation_set_ids[0]
    ann_set = await async_datalake.get_annotation_set(ann_set_id)
    schema = await async_datalake.get_annotation_schema(ann_set.annotation_schema_id)
    assert schema.task_type == "detection"
    record = await async_datalake.get_annotation_record(ann_set.annotation_record_ids[0])
    assert record.label == "hopper"


@pytest.mark.asyncio
async def test_dataset_sync_plan_metadata_only_cross_lake_rejected(
    async_datalake: AsyncDatalake,
    async_datalake_secondary: AsyncDatalake,
):
    dataset_name = f"sync-meta-xl-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    manager = DatasetSyncManager(async_datalake, async_datalake_secondary)
    bundle = await manager.export_dataset_version(dataset_name, version)

    with pytest.raises(ValueError, match="metadata_only"):
        await manager.plan_import(DatasetSyncImportRequest(bundle=bundle, transfer_policy="metadata_only"))


@pytest.mark.asyncio
async def test_dataset_sync_fail_if_missing_payload_blocks_commit(
    async_datalake: AsyncDatalake,
    async_datalake_secondary: AsyncDatalake,
):
    dataset_name = f"sync-miss-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    manager = DatasetSyncManager(async_datalake, async_datalake_secondary)
    bundle = await manager.export_dataset_version(dataset_name, version)

    plan = await manager.plan_import(
        DatasetSyncImportRequest(bundle=bundle, transfer_policy="fail_if_missing_payload")
    )
    assert plan.ready_to_commit is False

    with pytest.raises(ValueError, match="not ready to commit"):
        await manager.commit_import(
            DatasetSyncImportRequest(
                bundle=bundle,
                transfer_policy="fail_if_missing_payload",
                origin_lake_id=async_datalake.mongo_db_name,
            )
        )


@pytest.mark.asyncio
async def test_dataset_sync_fail_if_missing_payload_ready_when_present(
    async_datalake: AsyncDatalake,
    async_datalake_secondary: AsyncDatalake,
):
    dataset_name = f"sync-miss-ok-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    manager = DatasetSyncManager(async_datalake, async_datalake_secondary)
    await manager.sync_dataset_version(dataset_name, version, transfer_policy="copy_if_missing")

    bundle = await manager.export_dataset_version(dataset_name, version)
    plan = await manager.plan_import(
        DatasetSyncImportRequest(bundle=bundle, transfer_policy="fail_if_missing_payload")
    )
    assert plan.ready_to_commit is True
    assert plan.transfer_required_count == 0


@pytest.mark.asyncio
async def test_datalake_service_import_commit_metadata_only_roundtrip(
    async_datalake: AsyncDatalake,
):
    """``import_commit`` uses ``DatasetSyncManager(target)`` only; cross-store bytes need in-process sync.

    Same-lake ``metadata_only`` re-materializes Mongo rows while reusing existing registry objects.
    """
    dataset_name = f"sync-svc-commit-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)

    svc = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=async_datalake.mongo_db_name,
        async_datalake=async_datalake,
        live_service=False,
        initialize_on_startup=False,
    )

    bundle_raw = await _post_datalake_json(
        svc,
        "/dataset_versions.export",
        ExportDatasetVersionInput(dataset_name=dataset_name, version=version).model_dump(mode="json"),
    )
    bundle_out = DatasetSyncBundleOutput.model_validate(bundle_raw)

    dv = await async_datalake.get_dataset_version(dataset_name, version)
    datum = await async_datalake.get_datum(dv.manifest[0])
    asset_id = next(iter(datum.asset_refs.values()))
    asset = await async_datalake.get_asset(asset_id)
    await async_datalake.dataset_version_database.delete(dv.id)
    await async_datalake.datum_database.delete(datum.id)
    await async_datalake.asset_database.delete(asset.id)

    request = DatasetSyncImportRequest(
        bundle=bundle_out.bundle,
        transfer_policy="metadata_only",
        origin_lake_id=async_datalake.mongo_db_name,
    )
    commit_raw = await _post_datalake_json(
        svc,
        "/dataset_versions.import_commit",
        request.model_dump(mode="json"),
    )
    commit_out = DatasetSyncCommitResultOutput.model_validate(commit_raw)
    assert commit_out.result.transferred_payloads == 0
    assert commit_out.result.skipped_payloads >= 1
    remote = await async_datalake.get_dataset_version(dataset_name, version)
    assert remote.dataset_name == dataset_name
    restored = await async_datalake.get_asset(asset_id)
    loaded = await async_datalake.get_object(restored.storage_ref)
    assert len(loaded) > 0


@pytest.mark.asyncio
async def test_datalake_direct_upload_client_presigned_minio(async_datalake_minio: AsyncDatalake):
    """``DatalakeDirectUploadClient`` async path against MinIO uses presigned PUT (``_aupload_payload``)."""
    client = DatalakeDirectUploadClient(async_datalake_minio)
    name = f"upload-client/{uuid4().hex[:12]}.bin"
    payload = b"presigned-upload-client-bytes"
    session = await client.aupload_bytes(
        name=name,
        data=payload,
        mount="minio",
        content_type="application/octet-stream",
        expires_in_minutes=60,
        created_by="pytest-upload-client",
    )
    assert session.storage_ref is not None
    assert session.storage_ref.mount == "minio"
    loaded = await async_datalake_minio.get_object(session.storage_ref)
    assert loaded == payload


@pytest.mark.asyncio
async def test_datalake_direct_upload_client_acreate_asset_from_bytes_minio(async_datalake_minio: AsyncDatalake):
    client = DatalakeDirectUploadClient(async_datalake_minio)
    name = f"upload-client-asset/{uuid4().hex[:12]}.png"
    data = _HOPPER.read_bytes()
    asset = await client.acreate_asset_from_bytes(
        name=name,
        data=data,
        kind="image",
        media_type="image/png",
        mount="minio",
        created_by="pytest-upload-client",
    )
    assert asset.storage_ref.mount == "minio"
    loaded = await async_datalake_minio.get_object(asset.storage_ref)
    assert loaded == data


@pytest.mark.asyncio
async def test_complete_object_upload_session_is_idempotent(async_datalake: AsyncDatalake):
    """Second finalize on an already-completed session returns the session (short-circuit path)."""
    session = await async_datalake.create_object_upload_session(
        name=f"idempotent/{uuid4().hex[:10]}.bin",
        mount="local",
        content_type="application/octet-stream",
    )
    assert session.upload_path
    Path(session.upload_path).parent.mkdir(parents=True, exist_ok=True)
    Path(session.upload_path).write_bytes(b"done")

    first = await async_datalake.complete_object_upload_session(
        session.upload_session_id,
        finalize_token=session.finalize_token,
    )
    second = await async_datalake.complete_object_upload_session(
        session.upload_session_id,
        finalize_token=session.finalize_token,
    )
    assert first.status == "completed"
    assert second.status == "completed"


@pytest.mark.asyncio
async def test_datalake_service_upload_reconciler_starts_and_stops(async_datalake: AsyncDatalake):
    """Exercise ``_startup_initialize`` / ``_shutdown_cleanup`` and the upload reconciler loop."""
    service = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=async_datalake.mongo_db_name,
        async_datalake=async_datalake,
        live_service=True,
        initialize_on_startup=False,
        upload_reconcile_interval_seconds=0.05,
    )
    await service._startup_initialize()
    try:
        await asyncio.sleep(0.12)
    finally:
        await service._shutdown_cleanup()
