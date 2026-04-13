import base64
import os
from pathlib import Path

import pytest

from mindtrace.datalake import DatalakeService
from mindtrace.datalake.service_types import AssetOutput, DatalakeHealthOutput, DatalakeSummaryOutput, MountsOutput, ObjectOutput
from mindtrace.services.core.types import (
    ClassNameOutput,
    EndpointsOutput,
    HeartbeatOutput,
    PIDFileOutput,
    ServerIDOutput,
    StatusOutput,
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


class TestDatalakeServiceGunicornIntegration:
    def test_datalake_service_gunicorn_default_endpoints(self, datalake_service_manager):
        health = datalake_service_manager.health()
        endpoints = datalake_service_manager.endpoints()
        status = datalake_service_manager.status()
        heartbeat = datalake_service_manager.heartbeat()
        server_id = datalake_service_manager.server_id()
        class_name = datalake_service_manager.class_name()
        pid_file = datalake_service_manager.pid_file()

        reference_service = DatalakeService(live_service=False, initialize_on_startup=False)
        expected_endpoints = set(reference_service.endpoints)

        assert isinstance(health, DatalakeHealthOutput)
        assert isinstance(endpoints, EndpointsOutput)
        assert isinstance(status, StatusOutput)
        assert isinstance(heartbeat, HeartbeatOutput)
        assert isinstance(server_id, ServerIDOutput)
        assert isinstance(class_name, ClassNameOutput)
        assert isinstance(pid_file, PIDFileOutput)

        assert health.status == "ok"
        assert status.status.value == "Available"
        assert class_name.class_name == "DatalakeService"
        assert heartbeat.heartbeat.server_id == server_id.server_id
        assert pid_file.pid_file is not None
        assert os.path.exists(pid_file.pid_file)
        assert set(endpoints.endpoints) == expected_endpoints

        for endpoint in expected_endpoints:
            method_name = endpoint.replace(".", "_")
            assert hasattr(datalake_service_manager, method_name)
            assert hasattr(datalake_service_manager, f"a{method_name}")

    @pytest.mark.asyncio
    async def test_datalake_service_gunicorn_async_smoke(self, datalake_service_manager):
        health = await datalake_service_manager.ahealth()
        endpoints = await datalake_service_manager.aendpoints()
        class_name = await datalake_service_manager.aclass_name()

        assert isinstance(health, DatalakeHealthOutput)
        assert isinstance(endpoints, EndpointsOutput)
        assert isinstance(class_name, ClassNameOutput)
        assert health.status == "ok"
        assert class_name.class_name == "DatalakeService"
        assert "assets.create" in endpoints.endpoints

    def test_datalake_service_gunicorn_smoke_flow(self, datalake_service_manager):
        hopper_path = Path("tests/resources/hopper.png")
        image_bytes = hopper_path.read_bytes()
        encoded_image = _b64(image_bytes)

        mounts = datalake_service_manager.mounts()
        stored_object = datalake_service_manager.objects_put(
            name="gunicorn-hopper.png",
            data_base64=encoded_image,
            metadata={"source_path": str(hopper_path)},
        )
        copied_object = datalake_service_manager.objects_copy(
            source=stored_object.storage_ref,
            target_mount="default",
            target_name="gunicorn-hopper-copy.png",
        )
        asset = datalake_service_manager.assets_create(
            kind="image",
            media_type="image/png",
            storage_ref=stored_object.storage_ref,
            checksum="sha256:gunicorn",
            size_bytes=len(image_bytes),
            metadata={"source": "gunicorn"},
            created_by="pytest",
        )
        fetched_asset = datalake_service_manager.assets_get(id=asset.asset.asset_id)
        updated_asset = datalake_service_manager.assets_update_metadata(
            asset_id=asset.asset.asset_id,
            metadata={"path": "gunicorn"},
        )
        summary = datalake_service_manager.summary()

        assert isinstance(mounts, MountsOutput)
        assert isinstance(stored_object, ObjectOutput)
        assert isinstance(copied_object, ObjectOutput)
        assert isinstance(asset, AssetOutput)
        assert isinstance(fetched_asset, AssetOutput)
        assert isinstance(updated_asset, AssetOutput)
        assert isinstance(summary, DatalakeSummaryOutput)

        assert mounts.default_mount == "default"
        assert copied_object.storage_ref.mount == "default"
        assert fetched_asset.asset.asset_id == asset.asset.asset_id
        assert updated_asset.asset.metadata == {"path": "gunicorn"}
        assert "assets=1" in summary.summary

        assert datalake_service_manager.assets_delete(id=asset.asset.asset_id) is None
