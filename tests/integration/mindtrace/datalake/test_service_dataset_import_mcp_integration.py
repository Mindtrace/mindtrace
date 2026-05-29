"""Integration coverage for dataset import MCP-style service routes not exercised elsewhere.

Exercises :class:`mindtrace.datalake.DatalakeService` handlers for:

- ``dataset_sync.import_graph`` / ``dataset_sync.hydrate_payload`` / ``dataset_sync.finalize_graph``
- ``dataset_versions.import_session_commit_metadata`` / ``dataset_versions.import_session_status``
- ``dataset_versions.streaming_import_*``
- ``dataset_versions.verify_integrity`` (``fast`` and ``full-lake`` modes)

Requires MongoDB at ``mongodb://localhost:27018`` (see ``tests/integration/mindtrace/datalake/conftest.py``).
"""

from __future__ import annotations

import base64
import shutil
import socket
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient, Response

from mindtrace.datalake import AsyncDatalake, DatalakeService
from mindtrace.datalake.service_types import (
    DatasetImportSessionStatusOutput,
    DatasetIntegrityVerifyOutput,
    DatasetStreamingAssetPayloadInput,
    DatasetStreamingImportDatumBatchItem,
    DatasetStreamingImportPushBatchInput,
    DatasetStreamingImportStartInput,
    DatasetSyncCommitResultOutput,
    DatasetSyncHydratePayloadsOutput,
    DatasetSyncImportGraphOutput,
    DatasetSyncImportRequest,
)
from mindtrace.datalake.sync import DatasetSyncManager
from mindtrace.registry import LocalMountConfig, Mount, MountBackendKind, Store
from tests.integration.mindtrace.datalake.conftest import MONGO_URL
from tests.integration.mindtrace.datalake.test_dataset_sync_integration import (
    _post_datalake_json,
    _seed_image_dataset_with_bbox_annotation,
    _seed_minimal_image_dataset,
)


def _mongo_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 27018), timeout=2.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _mongo_reachable(),
    reason="MongoDB required at mongodb://localhost:27018 for dataset import MCP integration tests",
)


async def _post_raw(service: DatalakeService, path: str, payload: dict) -> Response:
    async with AsyncClient(transport=ASGITransport(app=service.app), base_url="http://test") as client:
        return await client.post(path, json=payload)


@pytest.mark.asyncio
async def test_service_dataset_sync_split_graph_hydrate_finalize(async_datalake: AsyncDatalake):
    """Split graph import: ``import_graph`` then per-asset ``hydrate_payload`` then ``finalize_graph``."""
    dataset_name = f"mcp-split-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    bundle = await DatasetSyncManager(async_datalake).export_dataset_version(dataset_name, version)
    payload_desc = bundle.payloads[0]
    image_bytes = await async_datalake.get_object(payload_desc.storage_ref)

    temp_dir = Path(tempfile.mkdtemp(prefix="mindtrace-mcp-split-"))
    try:
        sink_store = Store.from_mounts(
            [
                Mount(
                    name="sink",
                    backend=MountBackendKind.LOCAL,
                    config=LocalMountConfig(uri=temp_dir),
                    is_default=True,
                    registry_options={"mutable": True},
                )
            ],
            default_mount="sink",
        )
        db_name = f"test_mcp_split_{uuid4().hex[:12]}"
        sink_dl = await AsyncDatalake.create(
            mongo_db_uri=MONGO_URL,
            mongo_db_name=db_name,
            store=sink_store,
        )
        try:
            svc = DatalakeService(
                mongo_db_uri=MONGO_URL,
                mongo_db_name=db_name,
                async_datalake=sink_dl,
                live_service=False,
                initialize_on_startup=False,
            )
            start = await _post_datalake_json(
                svc,
                "/dataset_versions.import_session_start",
                DatasetSyncImportRequest(
                    bundle=bundle,
                    transfer_policy="copy_if_missing",
                    mount_map={"local": "sink"},
                ).model_dump(mode="json"),
            )
            session_id = start["session_id"]

            ig_raw = await _post_datalake_json(
                svc,
                "/dataset_sync.import_graph",
                {"session_id": session_id},
            )
            DatasetSyncImportGraphOutput.model_validate(ig_raw)

            hyd_raw = await _post_datalake_json(
                svc,
                "/dataset_sync.hydrate_payload",
                {
                    "session_id": session_id,
                    "asset_id": payload_desc.asset_id,
                    "data_base64": base64.b64encode(image_bytes).decode("ascii"),
                },
            )
            DatasetSyncHydratePayloadsOutput.model_validate(hyd_raw)

            fin_raw = await _post_datalake_json(
                svc,
                "/dataset_sync.finalize_graph",
                {"session_id": session_id},
            )
            fin = DatasetSyncCommitResultOutput.model_validate(fin_raw)
            assert fin.result.dataset_version.dataset_name == dataset_name

            imported = await sink_dl.get_dataset_version(dataset_name, version)
            assert imported.manifest
        finally:
            await sink_dl.asset_database.client.drop_database(db_name)
            await sink_dl.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_service_dataset_sync_finalize_rejects_missing_hydration(async_datalake: AsyncDatalake):
    dataset_name = f"mcp-fin-miss-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    bundle = await DatasetSyncManager(async_datalake).export_dataset_version(dataset_name, version)

    temp_dir = Path(tempfile.mkdtemp(prefix="mindtrace-mcp-fin-miss-"))
    try:
        sink_store = Store.from_mounts(
            [
                Mount(
                    name="sink",
                    backend=MountBackendKind.LOCAL,
                    config=LocalMountConfig(uri=temp_dir),
                    is_default=True,
                    registry_options={"mutable": True},
                )
            ],
            default_mount="sink",
        )
        db_name = f"test_mcp_fin_{uuid4().hex[:12]}"
        sink_dl = await AsyncDatalake.create(
            mongo_db_uri=MONGO_URL,
            mongo_db_name=db_name,
            store=sink_store,
        )
        try:
            svc = DatalakeService(
                mongo_db_uri=MONGO_URL,
                mongo_db_name=db_name,
                async_datalake=sink_dl,
                live_service=False,
                initialize_on_startup=False,
            )
            start = await _post_datalake_json(
                svc,
                "/dataset_versions.import_session_start",
                DatasetSyncImportRequest(
                    bundle=bundle,
                    transfer_policy="copy_if_missing",
                    mount_map={"local": "sink"},
                ).model_dump(mode="json"),
            )
            session_id = start["session_id"]
            await _post_datalake_json(svc, "/dataset_sync.import_graph", {"session_id": session_id})

            resp = await _post_raw(svc, "/dataset_sync.finalize_graph", {"session_id": session_id})
            assert resp.status_code == 400
            assert "Payload hydration still pending" in resp.text
        finally:
            await sink_dl.asset_database.client.drop_database(db_name)
            await sink_dl.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_service_import_session_commit_metadata_and_status(async_datalake: AsyncDatalake):
    """Phase-A metadata commit on an isolated lake + polling ``import_session_status``."""
    dataset_name = f"mcp-meta-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)
    bundle = await DatasetSyncManager(async_datalake).export_dataset_version(dataset_name, version)

    temp_dir = Path(tempfile.mkdtemp(prefix="mindtrace-mcp-meta-"))
    try:
        sink_store = Store.from_mounts(
            [
                Mount(
                    name="sink",
                    backend=MountBackendKind.LOCAL,
                    config=LocalMountConfig(uri=temp_dir),
                    is_default=True,
                    registry_options={"mutable": True},
                )
            ],
            default_mount="sink",
        )
        db_name = f"test_mcp_meta_{uuid4().hex[:12]}"
        sink_dl = await AsyncDatalake.create(
            mongo_db_uri=MONGO_URL,
            mongo_db_name=db_name,
            store=sink_store,
        )
        try:
            svc = DatalakeService(
                mongo_db_uri=MONGO_URL,
                mongo_db_name=db_name,
                async_datalake=sink_dl,
                live_service=False,
                initialize_on_startup=False,
            )
            start = await _post_datalake_json(
                svc,
                "/dataset_versions.import_session_start",
                DatasetSyncImportRequest(
                    bundle=bundle,
                    transfer_policy="copy_if_missing",
                    mount_map={"local": "sink"},
                ).model_dump(mode="json"),
            )
            session_id = start["session_id"]
            assert start["required_asset_ids"]

            await _post_datalake_json(
                svc,
                "/dataset_versions.import_session_commit_metadata",
                {"session_id": session_id},
            )

            stat_raw = await _post_datalake_json(
                svc,
                "/dataset_versions.import_session_status",
                {"session_id": session_id},
            )
            stat = DatasetImportSessionStatusOutput.model_validate(stat_raw)
            assert stat.metadata_graph_committed is True
            assert stat.session_stage == "awaiting_payload_uploads"
            assert stat.required_asset_count >= 1

            dup = await _post_raw(
                svc,
                "/dataset_versions.import_session_commit_metadata",
                {"session_id": session_id},
            )
            assert dup.status_code == 400
            assert "already committed" in dup.text
        finally:
            await sink_dl.asset_database.client.drop_database(db_name)
            await sink_dl.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_service_streaming_import_push_batch_and_finalize(async_datalake: AsyncDatalake):
    """End-to-end streaming import with annotation graph (exercises nested upsert + payload hydrate)."""
    dataset_name = f"mcp-str-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_image_dataset_with_bbox_annotation(async_datalake, dataset_name=dataset_name, version=version)

    bundle = await DatasetSyncManager(async_datalake).export_dataset_version(dataset_name, version)
    assert bundle.datums

    temp_dir = Path(tempfile.mkdtemp(prefix="mindtrace-mcp-stream-"))
    try:
        sink_store = Store.from_mounts(
            [
                Mount(
                    name="sink",
                    backend=MountBackendKind.LOCAL,
                    config=LocalMountConfig(uri=temp_dir),
                    is_default=True,
                    registry_options={"mutable": True},
                )
            ],
            default_mount="sink",
        )
        db_name = f"test_mcp_stream_{uuid4().hex[:12]}"
        sink_dl = await AsyncDatalake.create(
            mongo_db_uri=MONGO_URL,
            mongo_db_name=db_name,
            store=sink_store,
        )
        try:
            svc = DatalakeService(
                mongo_db_uri=MONGO_URL,
                mongo_db_name=db_name,
                async_datalake=sink_dl,
                live_service=False,
                initialize_on_startup=False,
            )
            start_raw = await _post_datalake_json(
                svc,
                "/dataset_versions.streaming_import_start",
                DatasetStreamingImportStartInput(
                    dataset_name=dataset_name,
                    version=version,
                    manifest_total=len(bundle.datums),
                    mount_map={"local": "sink"},
                    preserve_ids=True,
                    origin_lake_id=async_datalake.mongo_db_name,
                ).model_dump(mode="json"),
            )
            session_id = start_raw["session_id"]

            items: list[DatasetStreamingImportDatumBatchItem] = []
            for idx, datum in enumerate(bundle.datums):
                assets_for_datum = [a for a in bundle.assets if a.asset_id in (datum.asset_refs or {}).values()]
                payloads: list[DatasetStreamingAssetPayloadInput] = []
                for asset in assets_for_datum:
                    desc = next(p for p in bundle.payloads if p.asset_id == asset.asset_id)
                    data = await async_datalake.get_object(desc.storage_ref)
                    payloads.append(
                        DatasetStreamingAssetPayloadInput(
                            asset_id=asset.asset_id,
                            data_base64=base64.b64encode(data).decode("ascii"),
                        )
                    )
                items.append(
                    DatasetStreamingImportDatumBatchItem(
                        manifest_index=idx,
                        datum=datum,
                        assets=assets_for_datum,
                        annotation_schemas=list(bundle.annotation_schemas),
                        annotation_records=list(bundle.annotation_records),
                        annotation_sets=list(bundle.annotation_sets),
                        payloads=payloads,
                    )
                )

            batch = DatasetStreamingImportPushBatchInput(session_id=session_id, items=items)
            await _post_datalake_json(
                svc,
                "/dataset_versions.streaming_import_push_batch",
                batch.model_dump(mode="json"),
            )

            fin_raw = await _post_datalake_json(
                svc,
                "/dataset_versions.streaming_import_finalize",
                {"session_id": session_id},
            )
            fin = DatasetSyncCommitResultOutput.model_validate(fin_raw)
            assert fin.result.dataset_version.dataset_name == dataset_name

            datum_id = fin.result.dataset_version.manifest[0]
            datum = await sink_dl.get_datum(datum_id)
            assert datum.annotation_set_ids
        finally:
            await sink_dl.asset_database.client.drop_database(db_name)
            await sink_dl.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_service_verify_integrity_fast_and_full_lake(async_datalake: AsyncDatalake):
    dataset_name = f"mcp-verify-{uuid4().hex[:10]}"
    version = "1.0.0"
    await _seed_minimal_image_dataset(async_datalake, dataset_name=dataset_name, version=version)

    svc = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=async_datalake.mongo_db_name,
        async_datalake=async_datalake,
        live_service=False,
        initialize_on_startup=False,
    )
    fast_raw = await _post_datalake_json(
        svc,
        "/dataset_versions.verify_integrity",
        {"dataset_name": dataset_name, "version": version, "mode": "fast"},
    )
    fast_out = DatasetIntegrityVerifyOutput.model_validate(fast_raw)
    assert fast_out.ok is True

    lake_raw = await _post_datalake_json(
        svc,
        "/dataset_versions.verify_integrity",
        {"dataset_name": dataset_name, "version": version, "mode": "full-lake"},
    )
    lake_out = DatasetIntegrityVerifyOutput.model_validate(lake_raw)
    assert lake_out.ok is True
    assert lake_out.mode == "full-lake"
