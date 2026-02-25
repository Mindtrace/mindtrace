"""Additional unit tests for CameraManagerService stream/performance paths."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.hardware.core.exceptions import CameraNotFoundError
from mindtrace.hardware.services.cameras.models.requests import (
    CameraPerformanceSettingsRequest,
    StreamStartRequest,
    StreamStatusRequest,
    StreamStopRequest,
)
from mindtrace.hardware.services.cameras.service import CameraManagerService


@pytest.fixture
def service_and_manager():
    service = CameraManagerService(include_mocks=True)
    manager = Mock()
    manager.active_cameras = ["Basler:cam1"]
    manager.timeout_ms = 1000
    manager.retrieve_retry_count = 2
    manager.max_concurrent_captures = 4
    manager.open = AsyncMock()
    manager.get_camera = AsyncMock()
    service._camera_manager = manager
    return service, manager


@pytest.mark.asyncio
async def test_get_performance_settings_global(service_and_manager):
    service, _ = service_and_manager

    response = await service.get_performance_settings()

    assert response.success is True
    assert response.data.timeout_ms == 1000
    assert response.data.retrieve_retry_count == 2
    assert response.data.max_concurrent_captures == 4


@pytest.mark.asyncio
async def test_get_performance_settings_camera_not_active_raises(service_and_manager):
    service, _ = service_and_manager

    with pytest.raises(CameraNotFoundError):
        await service.get_performance_settings(CameraPerformanceSettingsRequest(camera="Basler:missing"))


@pytest.mark.asyncio
async def test_set_performance_settings_global_only(service_and_manager):
    service, manager = service_and_manager

    req = CameraPerformanceSettingsRequest(timeout_ms=2500, retrieve_retry_count=5, max_concurrent_captures=9)
    response = await service.set_performance_settings(req)

    assert response.success is True
    assert manager.timeout_ms == 2500
    assert manager.retrieve_retry_count == 5
    assert manager.max_concurrent_captures == 9


@pytest.mark.asyncio
async def test_set_performance_settings_camera_specific_calls_proxy(service_and_manager):
    service, manager = service_and_manager
    camera_proxy = AsyncMock()
    manager.open.return_value = camera_proxy

    req = CameraPerformanceSettingsRequest(
        camera="Basler:cam1", packet_size=9000, inter_packet_delay=100, bandwidth_limit_mbps=800.0
    )
    response = await service.set_performance_settings(req)

    assert response.success is True
    manager.open.assert_awaited_once_with("Basler:cam1")
    camera_proxy.set_packet_size.assert_awaited_once_with(9000)
    camera_proxy.set_inter_packet_delay.assert_awaited_once_with(100)
    camera_proxy.set_bandwidth_limit.assert_awaited_once_with(800.0)


@pytest.mark.asyncio
async def test_start_stream_success_tracks_stream(service_and_manager):
    service, manager = service_and_manager
    camera_proxy = AsyncMock()
    manager.open.return_value = camera_proxy

    with patch("os.getenv", side_effect=lambda k, d=None: {"CAMERA_API_HOST": "localhost", "CAMERA_API_PORT": "8002"}.get(k, d)):
        response = await service.start_stream(StreamStartRequest(camera="Basler:cam1", fps=15, quality=80))

    assert response.success is True
    assert response.data.streaming is True
    assert "Basler_cam1" in response.data.stream_url
    assert "Basler:cam1" in service._active_streams


@pytest.mark.asyncio
async def test_get_stream_status_active_stream(service_and_manager):
    service, manager = service_and_manager
    camera_proxy = AsyncMock()
    camera_proxy.check_connection.return_value = True
    manager.open.return_value = camera_proxy

    service._active_streams["Basler:cam1"] = {
        "stream_url": "http://localhost:8002/stream/Basler_cam1",
        "start_time": datetime.now(timezone.utc),
    }

    response = await service.get_stream_status(StreamStatusRequest(camera="Basler:cam1"))

    assert response.success is True
    assert response.data.streaming is True
    assert response.data.connected is True
    assert response.data.stream_url is not None


def test_stop_stream_when_missing_is_graceful(service_and_manager):
    service, _ = service_and_manager

    response = service.stop_stream(StreamStopRequest(camera="Basler:notactive"))

    assert response.success is True
    assert "already stopped" in response.message


def test_stop_all_streams_clears_dict(service_and_manager):
    service, _ = service_and_manager
    service._active_streams = {"a": {}, "b": {}}

    response = service.stop_all_streams()

    assert response.success is True
    assert service._active_streams == {}
